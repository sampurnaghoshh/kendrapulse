"""Supportive actions a lender can take, and what each one costs it.

An intervention in this model changes exactly ONE thing: how much a member owes in a given
week. Nothing else. It does not top up her savings, raise her income, or make her peers
more generous. That is a deliberate restriction, not an unfinished one: `due` is the only
quantity a lender actually controls, so every protected member in the smallest fix ranking
is protected by something a branch manager could really authorise.

TWO TYPES
---------
moratorium(member, start_week, weeks)
    Her installments are 0 for those weeks. The money is not forgiven. A real MFI
    moratorium moves the deferred installments to the END of the loan tenure, which is far
    beyond a 12 week horizon, so inside this simulation they simply never come due again.
    Modelling them as a lump repayable in week start_week + weeks would be a different and
    much harsher product, and it would make the "two worlds" view show a cliff that does
    not exist in the field.

reschedule(member, start_week, installment_fraction)
    A smaller installment from start_week to the end of the horizon. A rescheduled loan is
    re-papered over a longer tenure, so the lower installment is the new normal and does
    not expire.

THE OBSERVATION WINDOW
----------------------
An intervention is only valid if it ENDS at least `params.r_window_weeks` before the horizon
ends. This is the rule that keeps the metrics honest. A moratorium running to week 12 would
"protect" a member by simply removing every payment she could have missed inside the chart:
her stress reappears in week 13, where nothing is measured. Requiring a window of weeks
after the fix, during which she is paying again and we can still watch her, is the
difference between a fix and a deferral of the evidence.

A reschedule counts as ENDING at start_week, because it never stops: from the week it
starts she is paying the new installment, so every later week is already observation.

WHY THERE IS NO simulate() IN HERE
----------------------------------
`sim/engine.py` imports `due_multiplier` from this module to apply an intervention, so this
module must not import the engine back. Everything that needs to RUN a world (protection
counts, rupees at risk, ranking) lives in `sim/smallest_fix.py`.
"""

from dataclasses import dataclass

MORATORIUM = "moratorium"
RESCHEDULE = "reschedule"
TYPES = (MORATORIUM, RESCHEDULE)


@dataclass(frozen=True)
class Intervention:
    """One supportive action on one member. Frozen, like everything else in `sim/`."""

    type: str
    member_id: str
    start_week: int
    weeks: int | None = None  # moratorium only
    installment_fraction: float | None = None  # reschedule only

    def __post_init__(self):
        if self.type not in TYPES:
            raise ValueError(f"unknown intervention type {self.type!r}, expected one of {TYPES}")
        if self.start_week < 1:
            raise ValueError("start_week is 1 based, like every week in this model")
        if self.type == MORATORIUM:
            if self.weeks is None or self.weeks < 1:
                raise ValueError("a moratorium needs weeks >= 1")
            if self.installment_fraction is not None:
                raise ValueError("installment_fraction belongs to a reschedule")
        else:
            if self.installment_fraction is None or not 0.0 <= self.installment_fraction <= 1.0:
                raise ValueError("a reschedule needs installment_fraction in [0, 1]")
            if self.weeks is not None:
                raise ValueError("weeks belongs to a moratorium")

    # ----------------------------------------------------------------------------------
    # What it does to `due`
    # ----------------------------------------------------------------------------------

    def applies_to(self, member_id: str, week: int) -> bool:
        if member_id != self.member_id or week < self.start_week:
            return False
        # A reschedule has no end inside the horizon; a moratorium runs for `weeks` weeks.
        return self.type == RESCHEDULE or week < self.start_week + self.weeks

    def multiplier(self, member_id: str, week: int) -> float:
        """The factor this intervention puts on that member's installment that week."""
        if not self.applies_to(member_id, week):
            return 1.0
        return 0.0 if self.type == MORATORIUM else self.installment_fraction

    # ----------------------------------------------------------------------------------
    # When it ends, and whether we are allowed to judge it
    # ----------------------------------------------------------------------------------

    @property
    def last_active_week(self) -> int:
        """The last week the borrower is NOT paying her normal installment.

        A reschedule returns start_week: it never lifts, but from that week onward she is
        paying again, so there is nothing left to wait out.
        """
        return self.start_week + self.weeks - 1 if self.type == MORATORIUM else self.start_week

    def observable(self, params) -> bool:
        """Is there enough horizon left after this fix to see whether it worked?"""
        return params.horizon_weeks - self.last_active_week >= params.r_window_weeks

    # ----------------------------------------------------------------------------------
    # Cost to the lender
    # ----------------------------------------------------------------------------------

    def lender_cost(self, scenario, params) -> float:
        """Rupees moved x carry_cost_rate x weeks late, summed week by week.

        Priced from the week each rupee was DUE to the end of the horizon, so a moratorium
        granted early costs more than the same moratorium granted late: the lender waits
        longer for the same money. That ordering is the whole reason the ranking can prefer
        a smaller fix.
        """
        installment = scenario.member(self.member_id).weekly_due
        if installment <= 0:
            return 0.0

        cost = 0.0
        for week in range(self.start_week, params.horizon_weeks + 1):
            moved = installment * (1.0 - self.multiplier(self.member_id, week))
            if moved <= 0:
                continue
            cost += moved * params.carry_cost_rate * (params.horizon_weeks - week)
        return cost

    # ----------------------------------------------------------------------------------
    # Presentation
    # ----------------------------------------------------------------------------------

    @property
    def burden_key(self) -> tuple:
        """Sort key for "the lighter of two otherwise equal fixes". Smaller is lighter.

        Inside a type it means what it says: fewer moratorium weeks, or a higher remaining
        installment. ACROSS types the leading `type` string is alphabetical order and
        nothing more. It is there so the ranking is a total order and the demo never
        reshuffles between runs, not because a moratorium is inherently lighter than a
        reschedule. By the time this key is reached the two candidates have already tied on
        members protected AND on lender cost, so they are close to interchangeable anyway.
        """
        return (self.type, self.weeks or 0, -(self.installment_fraction or 0.0))

    def describe(self, scenario=None) -> str:
        """One line for the UI. No hyphens or dashes: this appears in the demo video."""
        who = scenario.member(self.member_id).name if scenario is not None else self.member_id
        if self.type == MORATORIUM:
            return f"Pause {who}'s installments for {self.weeks} weeks from week {self.start_week}"
        pct = round(100 * (1.0 - self.installment_fraction))
        return f"Cut {who}'s installment by {pct}% from week {self.start_week}"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "member_id": self.member_id,
            "start_week": self.start_week,
            "weeks": self.weeks,
            "installment_fraction": self.installment_fraction,
        }


# ---------------------------------------------------------------------------------------
# Constructors, so callers read as the build contract does
# ---------------------------------------------------------------------------------------


def moratorium(member_id: str, start_week: int, weeks: int) -> Intervention:
    return Intervention(MORATORIUM, member_id, start_week, weeks=weeks)


def reschedule(member_id: str, start_week: int, installment_fraction: float) -> Intervention:
    return Intervention(
        RESCHEDULE, member_id, start_week, installment_fraction=installment_fraction
    )


# ---------------------------------------------------------------------------------------
# The one hook the engine uses
# ---------------------------------------------------------------------------------------


def due_multiplier(interventions, member_id: str, week: int) -> float:
    """Combined factor on one member's installment in one week.

    A product, so two interventions on the same member compose rather than one silently
    winning. In practice the smallest fix search only ever applies one at a time.
    """
    factor = 1.0
    for intervention in interventions or ():
        factor *= intervention.multiplier(member_id, week)
    return factor
