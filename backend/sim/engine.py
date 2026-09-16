"""The weekly simulation. Pure: no I/O, no global state, and no RNG of its own.

The single most important property in this file is that `simulate` NEVER creates
randomness. Every uncertain quantity is read out of `draws[member, week, channel]`, an
array the caller builds once and hands to both the actual run and the counterfactual run.

That is what makes the Two Worlds view honest. If the engine rolled its own dice, removing
a shock would also reshuffle every coin flip downstream, and the difference between the two
worlds would be a mix of "the shock mattered" and "the dice landed differently". With common
random numbers, the only thing that can differ is the shock. Every label Phase 2 produces
rests on this.

The corollary, which is easy to break by accident: a draw belongs to a (person, week,
channel), never to an EVENT. draws[peer, w, CH_COVER] is "how willing was this peer in week
w", read whether or not a cover actually happens and regardless of whom she would cover.
Indexing a draw by a pair, or consuming draws in event order, would reintroduce exactly the
coupling we are trying to remove.
"""

from dataclasses import dataclass, field

import numpy as np

from sim.params import (
    CH_COVER,
    CH_COVER_SIZE,
    CH_EXPENSE,
    CH_INCOME_NOISE,
    CH_LENDER,
    DEFAULT,
    N_CHANNELS,
    Params,
)


@dataclass(frozen=True)
class Shock:
    """One planted event. Either a single member's shock, or a whole income source's.

    A source wide shock (weak_monsoon) counts as each affected member's OWN shock, so
    Phase 2 labels those members INDEX and not TRANSMITTED. The `common_shock` tag is what
    carries that through to the explanation.
    """

    type: str
    start_week: int
    member_id: str | None = None
    income_source: str | None = None
    severity: float | None = None  # None means take the default for this type
    duration_weeks: int | None = None
    tags: tuple[str, ...] = ()

    def resolve(self, params: Params) -> tuple[float, int]:
        default_severity, default_duration = params.shock_defaults[self.type]
        return (
            default_severity if self.severity is None else self.severity,
            default_duration if self.duration_weeks is None else self.duration_weeks,
        )

    def active(self, week: int, params: Params) -> bool:
        _, duration = self.resolve(params)
        return self.start_week <= week < self.start_week + duration

    def hits(self, member) -> bool:
        if self.member_id is not None:
            return member.id == self.member_id
        if self.income_source is not None:
            return member.income_source == self.income_source
        return False

    def owner_ids(self, scenario) -> tuple[str, ...]:
        """Members for whom this counts as their own shock."""
        return tuple(m.id for m in scenario.members if self.hits(m))


@dataclass(frozen=True)
class Run:
    """Result of one simulation. states[week][member_id] -> dict of that week's numbers."""

    states: dict[int, dict[str, dict]]
    events: list[dict] = field(default_factory=list)
    seed: int | None = None
    params: Params = DEFAULT

    def series(self, member_id: str, key: str) -> list[float]:
        return [self.states[w][member_id][key] for w in sorted(self.states)]

    def peak_stress(self, member_id: str, as_of_week: int | None = None) -> float:
        weeks = [w for w in sorted(self.states) if as_of_week is None or w <= as_of_week]
        return max(self.states[w][member_id]["s"] for w in weeks)

    def flagged(self, member_id: str, as_of_week: int | None = None) -> bool:
        return self.peak_stress(member_id, as_of_week) >= self.params.amber

    def first_flag_week(self, member_id: str) -> int | None:
        for w in sorted(self.states):
            if self.states[w][member_id]["s"] >= self.params.amber:
                return w
        return None

    def to_dict(self) -> dict:
        return {
            "states": {str(w): self.states[w] for w in sorted(self.states)},
            "events": self.events,
            "seed": self.seed,
        }


def make_draws(n_members: int, params: Params = DEFAULT, seed: int = 0) -> np.ndarray:
    """Pre draw every uniform the simulation will ever need.

    Shape (n_members, horizon_weeks + 1, N_CHANNELS). Row week=0 is the pre simulation
    state and stays unused, so week indices read 1..12 exactly as the UI shows them.
    """
    rng = np.random.default_rng(seed)
    return rng.random((n_members, params.horizon_weeks + 1, N_CHANNELS))


def _noise(u: float, halfwidth: float) -> float:
    """Map a uniform draw to a multiplier on [1 - halfwidth, 1 + halfwidth]."""
    return 1.0 + halfwidth * (2.0 * u - 1.0)


def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _status(s: float, params: Params) -> str:
    if s >= params.red:
        return "red"
    if s >= params.amber:
        return "amber"
    return "green"


def _expense_share(member, params: Params) -> float:
    """Consumption floor as a share of income, scaled by household size."""
    extra = member.household_size - params.expense_baseline_household
    return max(0.15, params.expense_floor_share + params.expense_per_extra_member * extra)


def _paused_lenders(scenario, prev_states, params):
    """Which lenders froze top ups, and which kendra's arrears triggered each freeze.

    Read from LAST week's state on purpose. Judging a freeze on the same week's arrears
    would create a within week feedback loop whose outcome depends on the order we happen
    to process members in, and order dependence is exactly what breaks reproducibility
    between the two worlds.
    """
    paused: dict[str, set[str]] = {}
    if prev_states is None:
        return paused

    for kendra_id, member_ids in scenario.kendras().items():
        for lender in sorted({l for mid in member_ids for l in scenario.member(mid).lenders}):
            linked = [mid for mid in member_ids if lender in scenario.member(mid).lenders]
            due = sum(prev_states[mid]["due"] for mid in linked)
            unpaid = sum(prev_states[mid]["unpaid"] for mid in linked)
            if due > 0 and unpaid / due > params.lender_pause_threshold:
                paused.setdefault(lender, set()).add(kendra_id)
    return paused


def _worst_payer(scenario, prev_states, kendra_id):
    """The member whose arrears most plausibly triggered a freeze. Used only to give the
    explanation path a real person to start from, never to change the mechanics."""
    ids = scenario.kendras()[kendra_id]
    return max(ids, key=lambda mid: (prev_states[mid]["unpaid"], mid))


def simulate(scenario, shocks, interventions, params, draws) -> Run:
    """Run the horizon week by week and return every member's weekly state plus the log.

    Each week resolves in three ordered passes over the whole roster rather than one loop
    per member. A single member loop would let member 3's outcome depend on whether member
    7 had already been processed this week, which is the kind of order sensitivity that
    silently diverges between the actual and counterfactual runs.
    """
    if interventions:
        raise NotImplementedError("Interventions are Phase 3; pass an empty list for now.")

    if draws.shape != (scenario.n_members, params.horizon_weeks + 1, N_CHANNELS):
        raise ValueError(
            f"draws shape {draws.shape} does not match this scenario and horizon. "
            "Actual and counterfactual runs must share one array."
        )

    members = scenario.members
    idx = scenario.index_of

    buffer = {m.id: m.savings_buffer for m in members}
    # Depletion is always measured against the WEEK 0 buffer. A moving baseline would make
    # stress incomparable across weeks and, worse, across the two worlds.
    buffer_start = {m.id: max(m.savings_buffer, 1.0) for m in members}
    s_prev = {m.id: 0.0 for m in members}

    states: dict[int, dict[str, dict]] = {}
    events: list[dict] = []
    prev_states = None

    for week in range(1, params.horizon_weeks + 1):
        week_of_year = (week - 1) % params.weeks_per_year

        # ---- Lender pause, judged on last week's arrears ------------------------------
        paused = _paused_lenders(scenario, prev_states, params)
        lender_hit = {m.id: 0.0 for m in members}
        if paused:
            for m in members:
                origins = {
                    k
                    for lender in m.lenders
                    for k in paused.get(lender, set())
                    if k != m.kendra_id  # a freeze reaches ACROSS kendras
                }
                if not origins:
                    continue
                if draws[idx[m.id], week, CH_LENDER] >= params.p_lender_pause_bites:
                    continue
                amount = buffer[m.id] * params.lender_pause_buffer_hit
                if amount <= 0:
                    continue
                buffer[m.id] -= amount
                lender_hit[m.id] = amount
                events.append({
                    "week": week,
                    "channel": "shared_lender",
                    "from_id": _worst_payer(scenario, prev_states, sorted(origins)[0]),
                    "to_id": m.id,
                    "amount": amount,
                })

        # ---- Pass A: income, expenses, own payment ------------------------------------
        # Independent per member. Nothing here reads another member's state.
        week_row: dict[str, dict] = {}
        for m in members:
            income_mult, expense_add = 1.0, 0.0
            for shock in shocks:
                if not (shock.hits(m) and shock.active(week, params)):
                    continue
                severity, _ = shock.resolve(params)
                if shock.type in params.expense_side_shocks:
                    expense_add += severity * m.weekly_income
                else:
                    income_mult *= max(0.0, 1.0 - severity)
                    if shock.type == "health":
                        # A health shock is both: she cannot work AND the bill arrives.
                        expense_add += params.health_expense_share * m.weekly_income

            i = idx[m.id]
            income = (
                m.weekly_income
                * m.seasonality[week_of_year]
                * (1.0 + m.income_trend) ** week
                * income_mult
                * _noise(draws[i, week, CH_INCOME_NOISE], params.income_noise_halfwidth)
            )
            expenses = (
                _expense_share(m, params)
                * m.weekly_income
                * _noise(draws[i, week, CH_EXPENSE], params.expense_noise_halfwidth)
                + expense_add
            )

            # The household eats before it pays. A consumption gap has to come out of
            # savings; without this the model would let a shocked household live on air,
            # and a severe income shock would leave no trace at all.
            consumption_draw = min(buffer[m.id], max(expenses - income, 0.0))
            buffer[m.id] -= consumption_draw

            net = max(income - expenses, 0.0)
            due = m.weekly_due
            # Savings are drawn only for the gap that is actually there: she does not
            # liquidate a cushion she has no use for this week.
            buffer_draw = min(buffer[m.id] * params.buffer_draw_cap, max(due - net, 0.0))
            buffer[m.id] -= buffer_draw

            cash = net + buffer_draw
            week_row[m.id] = {
                "income": income,
                "expenses": expenses,
                "due": due,
                "cash": cash,
                "consumption_draw": consumption_draw,
                "buffer_draw": buffer_draw,
                "lender_hit": lender_hit[m.id],
                "own_shortfall": max(due - cash, 0.0),
                "covered_in": 0.0,
                "covered_out": 0.0,
                "surplus": max(net - due, 0.0),
            }

        # ---- Pass B: guarantee cover (the only cross member pass) ---------------------
        for m in members:
            remaining = week_row[m.id]["own_shortfall"]
            if remaining <= 0:
                continue
            for peer_id in scenario.guarantee_peers(m.id):
                if remaining <= 0:
                    break
                # Eligibility uses LAST week's stress, not this week's. This week's stress
                # does not exist yet in pass B, and using a partially computed one would
                # make the outcome depend on roster order.
                if s_prev[peer_id] >= params.cover_min_peer_stress_block:
                    continue
                p = idx[peer_id]
                if draws[p, week, CH_COVER] >= params.p_cover:
                    continue
                capacity = (
                    draws[p, week, CH_COVER_SIZE]
                    * params.cover_capacity_share
                    * buffer[peer_id]
                )
                amount = min(capacity, remaining)
                if amount <= 0:
                    continue
                # This is the transmission: the money leaves HER cushion.
                buffer[peer_id] -= amount
                week_row[peer_id]["covered_out"] += amount
                week_row[m.id]["covered_in"] += amount
                remaining -= amount
                events.append({
                    "week": week,
                    "channel": "guarantee",
                    "from_id": peer_id,
                    "to_id": m.id,
                    "amount": amount,
                })

        # ---- Pass C: buffer top up, stress, status ------------------------------------
        for m in members:
            row = week_row[m.id]
            buffer[m.id] += row["surplus"] * params.buffer_topup_rate

            # Two shortfalls, and the distinction is load bearing:
            #   own_shortfall drives HER stress. Being rescued by a neighbour does not
            #     mean she was fine this week.
            #   unpaid drives the kendra arrears the LENDER sees. It only knows what
            #     actually arrived.
            unpaid = row["own_shortfall"] - row["covered_in"]
            shortfall_ratio = row["own_shortfall"] / row["due"] if row["due"] > 0 else 0.0
            depletion = _clip01(1.0 - buffer[m.id] / buffer_start[m.id])
            raw = params.w_shortfall * shortfall_ratio + params.w_buffer * depletion

            # max(), not sum. The additive form compounds week on week and pins the whole
            # roster at 1.0 by the end of the horizon; max gives stress a floor that decays
            # by half each week, so distress persists without ever ratcheting.
            s = _clip01(max(raw, params.stress_memory * s_prev[m.id]))

            row["unpaid"] = unpaid
            row["paid"] = row["due"] - unpaid
            row["buffer"] = buffer[m.id]
            row["depletion"] = depletion
            row["s"] = s
            row["status"] = _status(s, params)
            s_prev[m.id] = s

        states[week] = week_row
        prev_states = week_row

    return Run(states=states, events=events, seed=scenario.seed, params=params)
