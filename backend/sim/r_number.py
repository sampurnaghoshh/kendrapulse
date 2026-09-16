"""How many onward cases does one stressed borrower produce? R live and R potential.

Two numbers, because a field officer needs an answer in both of the situations she is
actually in.

R LIVE answers "what is already happening in this kendra". It is a ratio of counted cases:
onward (TRANSMITTED) flags inside the kendra divided by the primary cases that started them.
It is only defined once there is at least one primary case, which is exactly the situation
where the officer can already see somebody in trouble. Stress that crossed into a different
kendra is counted separately by CROSS KENDRA REACH, so that the two numbers the UI puts
under one cluster, R live and R potential, are on one scale: peers of this kendra.

R POTENTIAL answers "what would happen if somebody here got sick". It is a stress test, so
it is defined even when every member is green, which is when it is most useful: it is the
only one of the two that can tell a lender which kendra to shore up BEFORE anything goes
wrong.

WHAT COUNTS AS A PRIMARY CASE
-----------------------------
INDEX and INDEPENDENT both do, not just INDEX. A member whose income is quietly eroding
starts a chain the same way a member with a hospital bill does: in the seeded baseline m002
has no shock at all, and m004 flags because she covered m002 at the meeting. That is real
spread, and counting only INDEX cases would leave a transmitted case in the numerator with
nothing in the denominator to have caused it.

NO NEW RANDOMNESS
-----------------
R live reads the attribution records it is handed and simulates nothing at all. R potential
does simulate, but every planted world and the baseline it is compared against are handed
the SAME `draws` array, so a count is the effect of the planted shock and never a
difference in the dice. Building a second draws array in here would turn both numbers into
noise.
"""

from sim.attribution import INDEPENDENT, INDEX, TRANSMITTED, attribute
from sim.engine import Shock, simulate
from sim.params import DEFAULT

# Labels that can START a chain, and so sit in the denominator of R live.
PRIMARY_LABELS = (INDEX, INDEPENDENT)

# The standard probe for R potential. One health shock at its default severity and
# duration, always in week 1, so every member in every kendra is stress tested with
# exactly the same event and the numbers are comparable across a whole branch. Health is
# the right probe: it is the most common shock in this segment and it hits both sides of
# the household budget (earnings lost AND a bill to pay).
R_PROBE_TYPE = "health"
R_PROBE_START_WEEK = 1


def _is_primary(record):
    return record["label"] in PRIMARY_LABELS


# ---------------------------------------------------------------------------------------
# R live
# ---------------------------------------------------------------------------------------


def _onward_by_week(scenario, records, params, inside):
    """Onward cases per primary case, week by week, for one kendra at a time.

    `inside` picks which onward cases are counted: those that landed among the source's own
    kendra peers (R live), or those that landed in OTHER kendras (cross kendra reach).

    Shared rules, whichever set we are counting:

    A kendra owns an onward case through its SOURCE, never through where the onward case
    lives. The kendra that should carry a number is the one the stress came from.

    An onward case only counts once its source is a counted case too. Without that
    condition a transmitted member flagged in week 3 whose source does not flag until week
    5 would be an onward case in a week with nothing to divide by.

    The entry is None when the kendra has no primary case flagged yet. A ratio with nothing
    in the denominator has no honest value, so the UI falls back to R potential for those
    weeks rather than printing a zero it cannot justify.
    """
    kendra_of = {m.id: m.kendra_id for m in scenario.members}
    primary = {r["member_id"]: r for r in records if _is_primary(r)}
    # A TRANSMITTED record can name a source who never flags herself, or no source at all.
    # Neither is a case, so neither can be the start of a chain we count.
    transmitted = [
        r
        for r in records
        if r["label"] == TRANSMITTED
        and r["source_id"] in primary
        and (kendra_of[r["member_id"]] == kendra_of[r["source_id"]]) == inside
    ]

    out = {}
    for kendra_id in scenario.kendras():
        series = []
        for week in range(1, params.horizon_weeks + 1):
            cases = [
                r
                for r in primary.values()
                if kendra_of[r["member_id"]] == kendra_id and r["first_flag_week"] <= week
            ]
            if not cases:
                series.append(None)
                continue
            onward = [
                r
                for r in transmitted
                if kendra_of[r["source_id"]] == kendra_id
                and r["first_flag_week"] <= week
                and primary[r["source_id"]]["first_flag_week"] <= week
            ]
            series.append(len(onward) / len(cases))
        out[kendra_id] = series
    return out


def r_live_by_week(scenario, records, params=DEFAULT):
    """kendra_id -> [R live at week 1, ..., R live at week horizon].

    Onward cases INSIDE the source's own kendra, divided by that kendra's primary cases.

    Restricting the numerator to the kendra is what puts R live on the same scale as
    R potential, which counts kendra peers for the same reason: the UI shows one number per
    cluster and swaps between the two as soon as a case appears. If R live counted onward
    cases anywhere in the branch while R potential counted only peers, the number under a
    kendra would silently change meaning the moment somebody flagged, and the bound that
    lets the ring be drawn as a fraction would hold for only one of the two.

    Stress that crosses into another kendra is not thrown away. It is reported separately
    by `cross_kendra_reach_by_week`, which is the honest place for it: a different scale
    deserves a different number, not a quietly inflated one.
    """
    return _onward_by_week(scenario, records, params, inside=True)


def cross_kendra_reach_by_week(scenario, records, params=DEFAULT):
    """kendra_id -> [reach at week 1, ..., reach at week horizon].

    Onward cases in OTHER kendras charged to this kendra's primary cases, per primary case.
    Same denominator as R live, so the two read as a pair: "each case here has pulled down
    0.5 of her own group and 0.3 of somebody else's".

    This is the number that makes the shared lender channel visible. Guarantee cover cannot
    leave a kendra, so anything counted here arrived through a lender freezing top ups for
    linked members in another group, which is the contagion path a single lender looking at
    its own portfolio cannot see at all.
    """
    return _onward_by_week(scenario, records, params, inside=False)


# ---------------------------------------------------------------------------------------
# R potential
# ---------------------------------------------------------------------------------------


def r_potential(scenario, draws, params=DEFAULT):
    """kendra_id -> average number of PEERS one member's health shock would flag.

    For every member of the kendra in turn: plant the standard probe on her alone, run it
    against a no shock baseline on the same draws, and count how many of her kendra peers
    are newly flagged inside the window. Average over the members.

    Three choices worth stating, because all three are visible in the tests.

    NEWLY flagged, judged against the SAME window in the no shock world. Some members are
    already in trouble before anything is planted (m004 in the seeded baseline covers a
    neighbour whose income is eroding and flags on her own). Counting them would credit
    every probe in the kendra with a case it did not cause, and a kendra whose members
    were already struggling would score as the most ROBUST once a shock arrived, which is
    backwards.

    PEERS inside the kendra, not the whole branch. The number is read off one cluster in
    the UI as "how many of her four neighbours go down with her", so it is bounded by
    members_per_kendra - 1 and can be drawn as a fraction of that ring. R live is scoped
    the same way for the same reason, and onward cases that land in other kendras are
    reported by `cross_kendra_reach_by_week` instead of being folded into either figure.

    The scenario's own planted shocks are IGNORED here. R potential is a property of the
    roster and the network, not of whatever happens to have gone wrong this quarter, which
    is what lets it stay defined when everybody is green.
    """
    # The probe starts in week 1 and we watch it for r_window_weeks weeks, so week 1
    # itself is inside the window. Capped at the horizon so a short run stays valid.
    window_end = min(R_PROBE_START_WEEK + params.r_window_weeks - 1, params.horizon_weeks)

    # One baseline for the whole scenario, on the shared draws. It keeps every income
    # trend: a trend is part of the stage in both worlds, so the only thing that differs
    # between the baseline and a probe run is the shock we planted.
    baseline = simulate(scenario, [], [], params, draws)

    out = {}
    for kendra_id, member_ids in scenario.kendras().items():
        counts = []
        for planted_id in member_ids:
            probe = Shock(
                type=R_PROBE_TYPE, start_week=R_PROBE_START_WEEK, member_id=planted_id
            )
            run = simulate(scenario, [probe], [], params, draws)
            counts.append(
                sum(
                    1
                    for peer_id in member_ids
                    if peer_id != planted_id
                    and run.flagged(peer_id, window_end)
                    and not baseline.flagged(peer_id, window_end)
                )
            )
        out[kendra_id] = sum(counts) / len(counts)
    return out


# ---------------------------------------------------------------------------------------
# Both numbers, one row per kendra
# ---------------------------------------------------------------------------------------


def r_numbers(scenario, shocks, draws, params=DEFAULT, as_of_week=None, records=None):
    """One row per kendra, sorted by kendra id:

    {kendra_id, r_potential, r_live_by_week, cross_kendra_reach_by_week,
     primary_ids, transmitted_ids, cross_kendra_ids}

    `transmitted_ids` are the onward cases inside the kendra, the ones R live counts.
    `cross_kendra_ids` are the onward cases this kendra's primaries pushed into OTHER
    kendras, which `cross_kendra_reach_by_week` counts. Every onward case in the scenario
    appears in exactly one of the two lists of exactly one kendra: its source's.

    `records` accepts an attribution result that has already been computed, so a caller
    answering "who is flagged AND what is R" does not pay for attribution twice.
    """
    if records is None:
        records = attribute(scenario, shocks, draws, params, as_of_week)

    kendra_of = {m.id: m.kendra_id for m in scenario.members}
    primary = {r["member_id"]: r for r in records if _is_primary(r)}
    live = r_live_by_week(scenario, records, params)
    reach = cross_kendra_reach_by_week(scenario, records, params)
    potential = r_potential(scenario, draws, params)

    def onward_ids(kendra_id, inside):
        return sorted(
            r["member_id"]
            for r in records
            if r["label"] == TRANSMITTED
            and r["source_id"] in primary
            and kendra_of[r["source_id"]] == kendra_id
            and (kendra_of[r["member_id"]] == kendra_id) == inside
        )

    return [
        {
            "kendra_id": kendra_id,
            "r_potential": potential[kendra_id],
            "r_live_by_week": live[kendra_id],
            "cross_kendra_reach_by_week": reach[kendra_id],
            "primary_ids": sorted(mid for mid in primary if kendra_of[mid] == kendra_id),
            "transmitted_ids": onward_ids(kendra_id, inside=True),
            "cross_kendra_ids": onward_ids(kendra_id, inside=False),
        }
        for kendra_id in sorted(scenario.kendras())
    ]


def r_for_display(row, week):
    """Which number does the UI put on this kendra this week, and what is it called?

    R live the moment there is a case to divide by, R potential before that. The `kind`
    travels with the value because a screen showing a bare number the viewer cannot name
    is worse than a screen showing nothing.
    """
    live = row["r_live_by_week"][week - 1]
    if live is not None:
        return {"kind": "live", "value": live}
    return {"kind": "potential", "value": row["r_potential"]}
