"""Builds a synthetic kendra network: members, loans, the three edge types, a fixed layout.

Generation has its own RNG, seeded and separate from the simulation `draws`. That is
deliberate: the scenario is the STAGE, identical in both worlds. Only the simulation needs
common random numbers, because only the simulation is replayed with and without a shock.
"""

from dataclasses import dataclass
from math import cos, pi, sin

import networkx as nx
import numpy as np

from sim.params import DEFAULT, Params

# Synthetic names. First x last gives 300 unique combinations, enough for a 40 kendra
# branch at 5 members each with room to spare.
FIRST_NAMES = (
    "Lakshmi", "Sunita", "Meena", "Radha", "Kavita", "Anita", "Savita", "Pushpa",
    "Rekha", "Geeta", "Sarita", "Mamta", "Usha", "Nirmala", "Shanti", "Kamala",
    "Vimla", "Asha", "Prema", "Sudha", "Rani", "Jyoti", "Manju", "Babita", "Seema",
)
LAST_NAMES = (
    "Devi", "Kumari", "Bai", "Yadav", "Mahato", "Oraon", "Singh",
    "Murmu", "Hansda", "Kisku", "Tudu", "Soren",
)

# Members on the same source take a shock together: that is the correlated channel.
INCOME_SOURCES = ("farm_labour", "dairy", "tailoring", "petty_trade", "construction")
# Sources with a real lean season. Dairy, tailoring and petty trade are treated as flat.
SEASONAL_SOURCES = ("farm_labour", "construction")

# A small lender pool, so lenders are necessarily shared across kendras. That sharing is
# what creates the cross kendra contagion path.
LENDERS = ("Sahyog", "Grameen Vikas", "Adhar MFI", "Saphal Finance", "Uday Credit", "Nav Jeevan")


@dataclass(frozen=True)
class Loan:
    lender: str
    weekly_installment: float
    outstanding: float


@dataclass(frozen=True)
class Member:
    id: str
    name: str
    kendra_id: str
    weekly_income: float  # household weekly income; microfinance underwrites the household
    income_source: str
    seasonality: tuple[float, ...]  # length 52, multiplier by week of year
    income_trend: float  # per week multiplicative drift
    savings_buffer: float
    household_size: int
    loans: tuple[Loan, ...]

    @property
    def weekly_due(self) -> float:
        return sum(loan.weekly_installment for loan in self.loans)

    @property
    def total_outstanding(self) -> float:
        return sum(loan.outstanding for loan in self.loans)

    @property
    def lenders(self) -> frozenset[str]:
        return frozenset(loan.lender for loan in self.loans)


@dataclass(frozen=True)
class Scenario:
    members: tuple[Member, ...]
    graph: nx.MultiGraph
    layout: dict[str, tuple[float, float]]  # fixed coordinates so every UI panel agrees
    index_of: dict[str, int]  # member id -> row in draws[member, week, channel]
    seed: int

    @property
    def n_members(self) -> int:
        return len(self.members)

    def member(self, member_id: str) -> Member:
        return self.members[self.index_of[member_id]]

    def kendras(self) -> dict[str, list[str]]:
        """kendra_id -> member ids, in roster order."""
        out: dict[str, list[str]] = {}
        for m in self.members:
            out.setdefault(m.kendra_id, []).append(m.id)
        return out

    def guarantee_peers(self, member_id: str) -> tuple[str, ...]:
        """Other members of the same kendra, in roster order. The order is load bearing:
        it is what makes the cover pass reproducible."""
        me = self.member(member_id)
        return tuple(
            m.id for m in self.members if m.kendra_id == me.kendra_id and m.id != member_id
        )


def _seasonality_for(source, rng, params):
    """A 52 week multiplier. Flat for non seasonal work, one cycle for seasonal work."""
    weeks = params.weeks_per_year
    if source not in SEASONAL_SOURCES:
        return tuple([1.0] * weeks)
    peak_week = int(rng.integers(0, weeks))
    return tuple(
        1.0 + params.seasonality_amplitude * cos(2 * pi * (w - peak_week) / weeks)
        for w in range(weeks)
    )


def _assign_loans(weekly_income, rng, params):
    """Assign 1 to 3 loans sized to a TARGET share of income, not to the regulatory cap.

    The RBI 50% figure is a ceiling we must never cross, not a place to put people. If
    every member sat at the ceiling the no shock baseline would be permanently fragile,
    and every label we produced later would be noise about people already drowning.
    """
    n_loans = int(rng.integers(1, params.max_lenders_per_borrower + 1))
    lender_idxs = rng.choice(len(LENDERS), size=n_loans, replace=False)

    low, high = params.installment_share_target
    total_due = float(rng.uniform(low, high)) * weekly_income

    # Split the total across lenders. Dirichlet keeps every slice strictly positive, so
    # nobody ends up with a token loan that exists only to pad the lender count.
    weights = rng.dirichlet(np.ones(n_loans) * 3.0)

    loans = []
    for lender_idx, weight in zip(lender_idxs, weights):
        installment = float(total_due * weight)
        tenure = int(rng.integers(20, 90))  # remaining weeks; outstanding follows from it
        loans.append(Loan(LENDERS[int(lender_idx)], installment, installment * tenure))

    # MFIN exposure cap. If the drawn tenures push total outstanding over the cap, shorten
    # them proportionally rather than cutting the installment: the weekly burden on the
    # household is what the RBI cap governs, and we have already sized that deliberately.
    total_outstanding = sum(loan.outstanding for loan in loans)
    if total_outstanding > params.max_total_exposure_rs:
        scale = params.max_total_exposure_rs / total_outstanding
        loans = [
            Loan(loan.lender, loan.weekly_installment, loan.outstanding * scale)
            for loan in loans
        ]

    return tuple(loans)


def _build_graph(members):
    """The three channels, as a typed MultiGraph."""
    graph = nx.MultiGraph()
    for m in members:
        graph.add_node(m.id, kendra_id=m.kendra_id, name=m.name, income_source=m.income_source)

    by_kendra, by_source, by_lender = {}, {}, {}
    for m in members:
        by_kendra.setdefault(m.kendra_id, []).append(m.id)
        by_source.setdefault(m.income_source, []).append(m.id)
        for lender in sorted(m.lenders):
            by_lender.setdefault(lender, []).append(m.id)

    # Guarantee: complete graph inside each kendra. Joint liability really is everyone to
    # everyone, and a kendra is only 5 members, so the edge count stays small.
    for ids in by_kendra.values():
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                graph.add_edge(a, b, type="guarantee")

    # Shared income and shared lender: a RING, not a complete graph. A complete graph over
    # 40 members on one income source is 780 edges that render as a hairball and tell the
    # viewer nothing. A ring still makes the group one connected component, which is what
    # explanation paths actually depend on. The engine never walks these edges to decide
    # mechanics (shared income shocks are applied by income_source, lender pauses by
    # lender), so the ring is a faithful summary rather than a load bearing simplification.
    for edge_type, grouping in (("shared_income", by_source), ("shared_lender", by_lender)):
        for ids in grouping.values():
            if len(ids) < 2:
                continue
            for i, a in enumerate(ids):
                if len(ids) == 2 and i == 1:
                    break  # a 2 member ring would otherwise add the same edge twice
                graph.add_edge(a, ids[(i + 1) % len(ids)], type=edge_type)

    return graph


def _layout(members, n_kendras):
    """Kendras on a ring, members on a small circle inside each. Computed once in the
    backend so GraphView and both panels of TwoWorldsView use identical positions."""
    by_kendra = {}
    for m in members:
        by_kendra.setdefault(m.kendra_id, []).append(m.id)

    ring_radius, cluster_radius = 320.0, 78.0
    layout = {}
    for k_idx, kendra_id in enumerate(sorted(by_kendra)):
        angle = 2 * pi * k_idx / n_kendras - pi / 2
        cx, cy = ring_radius * cos(angle), ring_radius * sin(angle)
        member_ids = by_kendra[kendra_id]
        for m_idx, member_id in enumerate(member_ids):
            a = 2 * pi * m_idx / len(member_ids) - pi / 2
            layout[member_id] = (
                round(cx + cluster_radius * cos(a), 2),
                round(cy + cluster_radius * sin(a), 2),
            )
    return layout


def generate_scenario(n_kendras=5, members_per_kendra=5, seed=42, params=DEFAULT):
    """Build a seeded scenario. Same seed gives the same people, loans and graph."""
    rng = np.random.default_rng(seed)
    n_members = n_kendras * members_per_kendra

    # Which members get a clearly slipping income. These become the INDEPENDENT cases in
    # Phase 2: stress with no shock behind it, just a livelihood quietly eroding.
    n_declining = max(1, int(round(n_members * params.declining_share)))
    declining = set(rng.choice(n_members, size=n_declining, replace=False).tolist())

    # Seasonality is a property of the SOURCE, not the person, so draw it once per source.
    seasonality_by_source = {s: _seasonality_for(s, rng, params) for s in INCOME_SOURCES}

    # Names are drawn without replacement so no two members share one, which would make
    # the officer note extraction in Phase 7 ambiguous for no good reason.
    name_pairs = [(f, l) for l in LAST_NAMES for f in FIRST_NAMES]
    chosen = rng.choice(len(name_pairs), size=n_members, replace=False)

    members = []
    for idx in range(n_members):
        first, last = name_pairs[int(chosen[idx])]
        source = INCOME_SOURCES[int(rng.integers(0, len(INCOME_SOURCES)))]
        weekly_income = float(round(rng.uniform(2000, 6000), 2))
        trend = (
            params.declining_trend
            if idx in declining
            else float(rng.uniform(*params.trend_range))
        )
        members.append(
            Member(
                id=f"m{idx:03d}",
                name=f"{first} {last}",
                kendra_id=f"k{idx // members_per_kendra}",
                weekly_income=weekly_income,
                income_source=source,
                seasonality=seasonality_by_source[source],
                income_trend=trend,
                savings_buffer=float(
                    round(weekly_income * rng.uniform(*params.buffer_weeks_range), 2)
                ),
                household_size=int(rng.integers(3, 8)),
                loans=_assign_loans(weekly_income, rng, params),
            )
        )

    members = tuple(members)
    return Scenario(
        members=members,
        graph=_build_graph(members),
        layout=_layout(members, n_kendras),
        index_of={m.id: i for i, m in enumerate(members)},
        seed=seed,
    )
