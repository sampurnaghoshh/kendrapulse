"""What is the SMALLEST supportive action that stops the spread?

This is the answer the whole prototype exists to give. Attribution says who caught what from
whom; this module searches the short list of things a branch manager could actually
authorise on Monday and reports the ones that protect the most people for the least cost.

HOW A CANDIDATE IS JUDGED
-------------------------
Every candidate is replayed against ONE actual run, on the SAME draws array. So the
difference between the two is the intervention and nothing else: a member who stops flagging
stopped because her installment changed, not because her dice landed differently. This is
the same common random numbers property the labels rest on, and it is what lets the UI claim
"this fix protects Sunita" rather than "Sunita happened to be fine in this replay".

  members_protected  flagged in the actual run, not flagged with the fix
  newly_flagged      not flagged in the actual run, flagged with the fix. ANY of these and
                     the candidate is REJECTED outright, at any rank and any cost saving.
                     A fix that quietly moves the burden onto a neighbour is not a fix, and
                     a ranking that could surface one would be worse than no ranking.
  rupees_at_risk     total outstanding of every member flagged at any week. The portfolio
                     number a lender recognises, and the one that makes the case for acting
                     early rather than collecting later.

RANKING
-------
members protected desc, then lender cost asc, then the lighter intervention, then roster
order. The first two are the build contract. The last two exist only so the demo shows the
same three fixes in the same order every single time it runs.

WHY THE COST TIEBREAK MATTERS MORE THAN IT LOOKS
------------------------------------------------
Protection is a small integer, so ties are the normal case, not the exception. Without the
cost tiebreak the "smallest fix" would be whichever equally effective fix happened to be
generated first, which is the opposite of the claim the panel makes on screen.
"""

from sim.attribution import attribute
from sim.engine import simulate
from sim.interventions import Intervention, MORATORIUM, RESCHEDULE
from sim.params import DEFAULT
from sim.r_number import cross_kendra_reach_by_week, r_live_by_week

TOP_N = 3


# ---------------------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------------------


def rupees_at_risk(scenario, run, as_of_week=None) -> float:
    """Total outstanding principal of every member flagged at any week up to `as_of_week`.

    Whole outstanding, not the missed installment. Once a joint liability borrower is in
    distress the exposure at stake is the loan, not this week's payment, and that is the
    number a portfolio manager is actually deciding about.
    """
    return sum(
        m.total_outstanding for m in scenario.members if run.flagged(m.id, as_of_week)
    )


def protection(scenario, actual, intervened, as_of_week=None):
    """(protected ids, newly flagged ids) between the actual run and an intervened one."""
    protected, newly_flagged = [], []
    for m in scenario.members:
        was = actual.flagged(m.id, as_of_week)
        now = intervened.flagged(m.id, as_of_week)
        if was and not now:
            protected.append(m.id)
        elif now and not was:
            newly_flagged.append(m.id)
    return protected, newly_flagged


# ---------------------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------------------


def candidates(scenario, params=DEFAULT, decision_week=1):
    """Every member x every grid point, all starting the week the officer decides.

    Filtered by the observation window: a fix still running when the horizon ends has not
    been shown to work, it has only pushed the stress past the edge of the chart. Returns
    them in roster order, which is the order the ranking's last tiebreak assumes.
    """
    out = []
    for m in scenario.members:
        for weeks in params.moratorium_weeks_grid:
            out.append(Intervention(MORATORIUM, m.id, decision_week, weeks=weeks))
        for fraction in params.reschedule_fraction_grid:
            out.append(
                Intervention(RESCHEDULE, m.id, decision_week, installment_fraction=fraction)
            )
    return tuple(c for c in out if c.observable(params))


# ---------------------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------------------


def _rank_key(scenario, entry):
    """members protected desc, lender cost asc, lighter fix, roster order.

    Roster index last, so two candidates that are genuinely equivalent on every stated
    criterion still come back in one fixed order. Nothing about the demo should depend on
    dict ordering.
    """
    intervention = entry["intervention"]
    return (
        -len(entry["members_protected"]),
        entry["lender_cost"],
        intervention.burden_key,
        scenario.index_of[intervention.member_id],
    )


def smallest_fix(
    scenario, shocks, params=DEFAULT, draws=None, decision_week=1, top_n=TOP_N
):
    """Rank every candidate fix and return the best `top_n`.

    Each returned entry:
      intervention             the Intervention object
      members_protected        member ids, flagged without the fix and not with it
      lender_cost              rupees, carry cost of the money moved
      r_live_by_week           R live per kendra in the intervened world
      cross_kendra_reach_by_week  the companion series, same world
      rupees_at_risk_avoided   actual rupees at risk minus intervened
      run                      the replay, so the UI can animate it on the same slider

    Candidates that newly flag ANYBODY are dropped before ranking, and a candidate that
    protects nobody is dropped too: offering it would put a cost on screen next to no
    benefit.
    """
    if draws is None:
        raise ValueError("smallest_fix needs the scenario's draws; it must not build its own")

    actual = simulate(scenario, shocks, [], params, draws)
    actual_at_risk = rupees_at_risk(scenario, actual)

    ranked = []
    for intervention in candidates(scenario, params, decision_week):
        # One replay per candidate, on the SAME draws object as the actual run.
        run = simulate(scenario, shocks, [intervention], params, draws)
        protected, newly_flagged = protection(scenario, actual, run)
        if newly_flagged or not protected:
            continue
        ranked.append({
            "intervention": intervention,
            "members_protected": protected,
            "lender_cost": intervention.lender_cost(scenario, params),
            "rupees_at_risk_avoided": actual_at_risk - rupees_at_risk(scenario, run),
            "run": run,
        })

    ranked.sort(key=lambda entry: _rank_key(scenario, entry))
    best = ranked[:top_n]

    # Attribution is the expensive part, so the new R is computed for the shortlist only.
    # Nothing about the ranking depends on it, so this changes no result.
    for entry in best:
        records = attribute(
            scenario, shocks, draws, params, interventions=(entry["intervention"],)
        )
        entry["r_live_by_week"] = r_live_by_week(scenario, records, params)
        entry["cross_kendra_reach_by_week"] = cross_kendra_reach_by_week(
            scenario, records, params
        )
    return best
