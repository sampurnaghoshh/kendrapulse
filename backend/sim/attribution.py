"""Why is this member flagged? INDEX, TRANSMITTED or INDEPENDENT.

Every label here is a SUBTRACTION between two runs of the same world. We rebuild the
world with one cause taken out and see whether the member still flags. That only means
anything because `simulate` never rolls its own dice: every run in this file is handed the
SAME `draws` array, so the difference between two worlds is the removed cause and nothing
else. If you ever find yourself building a second draws array in here, the labels stop
being evidence and become noise.

WHAT COUNTS AS A CAUSE
----------------------
A planted shock is obviously a cause. So is a NEGATIVE income trend: a member whose
livelihood is quietly eroding is under real stress, and she can push that stress onto a
peer who covers for her at the meeting exactly the way a shock victim can.

That second half is not a refinement, it is the difference between a right and a wrong
label. In the seeded baseline, m004 flags in week 12 with no shock anywhere in the
scenario, purely because she covered m002, whose income is declining. A procedure that
only knew about shocks would run a no shock world, find m004 still flagged, and call her
INDEPENDENT. She is not: she is the clearest TRANSMITTED case in the demo.

So a cause is: a member's own shocks, plus her own negative trend. A trend is neutralised
by setting it to 0, which is the trend equivalent of deleting a shock.

A POSITIVE trend is never a cause and is never neutralised. It is part of the stage, not
part of what went wrong, and removing it would make a member poorer in the counterfactual
than she is in reality, which would quietly manufacture stress we then attribute to
somebody else.
"""

from dataclasses import replace

import networkx as nx

from sim.engine import simulate
from sim.params import DEFAULT

INDEX = "INDEX"
TRANSMITTED = "TRANSMITTED"
INDEPENDENT = "INDEPENDENT"

# Which way does STRESS travel along a logged transfer? Not always the way the money went.
#
#   guarantee:     money moves giver -> receiver. The giver is the one who ends up short,
#                  so stress moves receiver -> giver, against the cash.
#   shared_lender: the event already records arrears origin -> the member whose top up
#                  froze, so stress moves with it.
#
# Getting this backwards would draw every explanation path the wrong way round.
_STRESS_FOLLOWS_MONEY = {"guarantee": False, "shared_lender": True}

# Preference when the fallback graph path has to pick one edge type between two members.
# Strongest channel first, which is also the order a field officer would explain them in.
_EDGE_PREFERENCE = ("guarantee", "shared_income", "shared_lender")

_EPS = 1e-9


# ---------------------------------------------------------------------------------------
# Causes
# ---------------------------------------------------------------------------------------


def expand_shocks(scenario, shocks):
    """Rewrite every source wide shock as one per member shock, one per affected member.

    A weak_monsoon counts as the OWN shock of each member on that income source, so the
    only honest way to remove "member i's causes" is to remove i's share of it while
    leaving her neighbours' share standing. `Shock` can address one member or one source,
    never a source minus somebody, so we flatten to per member shocks up front and every
    later filter becomes a set membership test.

    The simulation is unchanged by this: the engine applies a shock to a member if it hits
    her, and the expansion hits exactly the same members with the same severity and weeks.
    """
    out = []
    for shock in shocks:
        if shock.member_id is not None:
            out.append(shock)
            continue
        tags = tuple(dict.fromkeys(shock.tags + ("common_shock",)))
        for owner_id in shock.owner_ids(scenario):
            out.append(replace(shock, member_id=owner_id, income_source=None, tags=tags))
    return tuple(out)


def cause_owners(scenario, expanded_shocks):
    """(members with at least one own shock, members with a negative trend)."""
    shock_owners = frozenset(s.member_id for s in expanded_shocks if s.member_id is not None)
    trend_owners = frozenset(m.id for m in scenario.members if m.income_trend < 0.0)
    return shock_owners, trend_owners


# ---------------------------------------------------------------------------------------
# Worlds
# ---------------------------------------------------------------------------------------


class _Worlds:
    """Builds and caches counterfactual worlds, all sharing one draws array.

    A world is named by the two sets of causes left STANDING in it: whose shocks are
    active, and whose negative trends are active. Every question this module asks is one
    of those pairs, so the pair is also the cache key. That matters more than it looks:
    "actual minus i's causes" is asked once per flagged member, and without the cache a
    25 member scenario would replay the same handful of worlds hundreds of times.
    """

    def __init__(self, scenario, shocks, draws, params=DEFAULT, interventions=()):
        self.scenario = scenario
        self.params = params
        self.draws = draws
        # Interventions are held FIXED across every world in here. The question an
        # intervened attribution answers is "given this fix, who is still stressed and
        # why", so the fix belongs to the stage, exactly like a positive income trend.
        self.interventions = tuple(interventions)
        self.shocks = expand_shocks(scenario, shocks)
        self.shock_owners, self.trend_owners = cause_owners(scenario, self.shocks)
        self._runs = {}
        self._scenarios = {}

    def _scenario_with(self, trends_kept):
        """The scenario with every negative trend zeroed except the ones named."""
        key = tuple(sorted(trends_kept & self.trend_owners))
        if key not in self._scenarios:
            keep = set(key)
            members = tuple(
                m if (m.income_trend >= 0.0 or m.id in keep) else replace(m, income_trend=0.0)
                for m in self.scenario.members
            )
            # index_of, graph and layout are untouched: same people, same rows in `draws`.
            self._scenarios[key] = replace(self.scenario, members=members)
        return self._scenarios[key]

    def run(self, shocks_kept, trends_kept):
        shocks_kept = frozenset(shocks_kept) & self.shock_owners
        trends_kept = frozenset(trends_kept) & self.trend_owners
        key = (tuple(sorted(shocks_kept)), tuple(sorted(trends_kept)))
        if key not in self._runs:
            self._runs[key] = simulate(
                self._scenario_with(trends_kept),
                [s for s in self.shocks if s.member_id in shocks_kept],
                self.interventions,
                self.params,
                self.draws,  # THE same array in every world. Never rebuild it.
            )
        return self._runs[key]

    def actual(self):
        return self.run(self.shock_owners, self.trend_owners)

    def only(self, member_id):
        """The world where the only thing that ever went wrong is this member's own life."""
        return self.run({member_id}, {member_id})

    def without(self, member_id, shocks=True, trends=True):
        """The actual world minus some or all of one member's causes."""
        return self.run(
            self.shock_owners - ({member_id} if shocks else set()),
            self.trend_owners - ({member_id} if trends else set()),
        )

    def has_cause(self, member_id):
        return member_id in self.shock_owners or member_id in self.trend_owners

    def own_shocks(self, member_id):
        return tuple(s for s in self.shocks if s.member_id == member_id)


# ---------------------------------------------------------------------------------------
# Explanation path
# ---------------------------------------------------------------------------------------


def _event_path(run, source_id, member_id, until_week):
    """The chain of logged transfers that carried stress from source to member.

    A temporal breadth first search: a hop is only usable if we had already reached its
    start by the week it happens. Stress cannot travel backwards in time, and walking the
    log in week order while keeping the EARLIEST week each member is reached is enough to
    find a feasible chain if one exists.
    """
    edges = []
    for order, event in enumerate(run.events):
        if event["week"] > until_week:
            continue
        follows = _STRESS_FOLLOWS_MONEY.get(event["channel"], True)
        u, v = (
            (event["from_id"], event["to_id"])
            if follows
            else (event["to_id"], event["from_id"])
        )
        edges.append((event["week"], order, u, v, event))
    edges.sort(key=lambda e: (e[0], e[1]))

    reached = {source_id: 0}
    prev = {}
    for week, _, u, v, event in edges:
        if u in reached and reached[u] <= week and v not in reached:
            reached[v] = week
            prev[v] = (u, event)
            if v == member_id:
                break

    if member_id not in prev:
        return []

    steps, node = [], member_id
    while node in prev:
        u, event = prev[node]
        steps.append({
            "week": event["week"],
            "channel": event["channel"],
            "from_id": u,  # stress direction, so the path reads source -> member
            "to_id": node,
            "amount": event["amount"],
            "inferred": False,
        })
        node = u
    steps.reverse()
    return steps


def _graph_path(scenario, source_id, member_id):
    """Fallback when the log has no chain: the shortest route through the network.

    Marked `inferred` so the UI never claims a transfer we did not actually observe.
    """
    try:
        nodes = nx.shortest_path(scenario.graph, source_id, member_id)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []

    steps = []
    for u, v in zip(nodes, nodes[1:]):
        types = {d.get("type") for d in scenario.graph.get_edge_data(u, v).values()}
        channel = next((t for t in _EDGE_PREFERENCE if t in types), sorted(types)[0])
        steps.append({
            "week": None,
            "channel": channel,
            "from_id": u,
            "to_id": v,
            "amount": None,
            "inferred": True,
        })
    return steps


def _path(worlds, run, source_id, member_id, as_of_week, first_flag_week):
    if source_id is None or source_id == member_id:
        return []
    # Cap at her first flag: the transfers that explain a flag are the ones that happened
    # before it, not whatever else the log picked up later in the horizon.
    until = min(as_of_week, first_flag_week if first_flag_week is not None else as_of_week)
    steps = _event_path(run, source_id, member_id, until)
    return steps or _graph_path(worlds.scenario, source_id, member_id)


# ---------------------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------------------


def _own_cause_label(worlds, member_id, as_of_week):
    """Step 1. In a world holding only her own causes, is she flagged, and by what?

    Returns (label, source_cause, tags), or None when her own causes are not enough and
    the stress must have come from somebody else.
    """
    only = worlds.only(member_id)
    if not only.flagged(member_id, as_of_week):
        return None

    own_shocks = worlds.own_shocks(member_id)
    if own_shocks:
        # Are the shocks NECESSARY, or is her trend alone already doing it? Two details
        # decide this correctly.
        #
        # Removing ALL her shocks at once, rather than one at a time, keeps the answer
        # right when she carries two shocks that would each be enough on their own.
        #
        # And necessity is judged at the week her own causes first put her over, NOT at
        # as_of_week. A member hit by a weak monsoon in week 2 whose income would also
        # have caught up with her by week 11 is an INDEX case: the monsoon is what
        # flagged her. Judging at as_of_week would call her INDEX all through the demo
        # and then silently flip her to INDEPENDENT when the slider passed week 11, which
        # is both wrong and the kind of thing a judge notices.
        own_flag_week = only.first_flag_week(member_id)
        if not worlds.run(set(), {member_id}).flagged(member_id, own_flag_week):
            tags = tuple(
                dict.fromkeys(t for s in own_shocks for t in s.tags if t == "common_shock")
            )
            return INDEX, "shock", tags

    # Her own life explains it, but no shock of hers was needed: her income is slipping.
    declining = member_id in worlds.trend_owners
    return (
        INDEPENDENT,
        "trend" if declining else None,
        ("declining_income",) if declining else (),
    )


def _dominant_cause(worlds, source_id, member_id, as_of_week, actual_peak):
    """Was it the source's shock or her slipping income that reached this member?

    When she has only one kind of cause the answer is free. When she has both, we remove
    them one at a time and let the bigger relief decide, rather than assuming a shock
    always outweighs a trend.
    """
    has_shock = source_id in worlds.shock_owners
    has_trend = source_id in worlds.trend_owners
    if not (has_shock and has_trend):
        return "shock" if has_shock else "trend"

    shock_drop = actual_peak - worlds.without(
        source_id, shocks=True, trends=False
    ).peak_stress(member_id, as_of_week)
    trend_drop = actual_peak - worlds.without(
        source_id, shocks=False, trends=True
    ).peak_stress(member_id, as_of_week)
    return "shock" if shock_drop >= trend_drop else "trend"


def _rank_sources(worlds, member_id, as_of_week, actual_peak):
    """Step 2. Which other member's causes, when removed, most relieves this member?"""
    ranked = []
    for other in sorted(worlds.shock_owners | worlds.trend_owners):
        if other == member_id:
            continue
        run = worlds.without(other)
        drop = actual_peak - run.peak_stress(member_id, as_of_week)
        if drop <= _EPS:
            continue
        ranked.append({
            "member_id": other,
            "cause": _dominant_cause(worlds, other, member_id, as_of_week, actual_peak),
            "drop": drop,
            "unflags": not run.flagged(member_id, as_of_week),
        })
    # Largest relief first; member id breaks ties so the demo never reorders between runs.
    ranked.sort(key=lambda c: (-c["drop"], c["member_id"]))
    return ranked


def attribute_member(worlds, member_id, as_of_week=None):
    """Label one member. Assumes she is flagged in the actual run."""
    as_of_week = worlds.params.horizon_weeks if as_of_week is None else as_of_week
    actual = worlds.actual()

    record = {
        "member_id": member_id,
        "label": None,
        "source_id": member_id,  # her own id unless somebody else turns out to be behind it
        "source_cause": None,
        "sole_source": None,
        "path": [],
        "first_flag_week": actual.first_flag_week(member_id),
        "tags": (),
        "contributors": [],
    }

    own = _own_cause_label(worlds, member_id, as_of_week)
    if own is not None:
        record["label"], record["source_cause"], record["tags"] = own
        return record

    # Her own causes are not enough to flag her, so it arrived from somebody else.
    record["label"] = TRANSMITTED
    ranked = _rank_sources(
        worlds, member_id, as_of_week, actual.peak_stress(member_id, as_of_week)
    )
    record["contributors"] = [
        {k: c[k] for k in ("member_id", "cause", "drop")} for c in ranked[:2]
    ]

    if not ranked:
        # Flagged, not by her own causes, and no single removal helps her at all. Say so
        # rather than invent a culprit: this is the case the validation report should see.
        record["source_id"] = None
        record["sole_source"] = False
        return record

    top = ranked[0]
    record["source_id"] = top["member_id"]
    record["source_cause"] = top["cause"]
    record["sole_source"] = top["unflags"]
    if top["cause"] == "trend":
        record["tags"] = ("source_declining_income",)
    else:
        record["tags"] = tuple(
            dict.fromkeys(
                t
                for s in worlds.own_shocks(top["member_id"])
                for t in s.tags
                if t == "common_shock"
            )
        )
    record["path"] = _path(
        worlds, actual, top["member_id"], member_id, as_of_week, record["first_flag_week"]
    )
    return record


def attribute(scenario, shocks, draws, params=DEFAULT, as_of_week=None, interventions=()):
    """Label every member flagged in the actual run up to `as_of_week`.

    One record per flagged member, earliest flag first:
    {member_id, label, source_id, source_cause, sole_source, path, first_flag_week,
     tags, contributors}.

    `interventions` labels an INTERVENED world instead of the raw one, which is how
    `smallest_fix` reports the R live a fix would leave behind. It is held fixed in every
    counterfactual, so the labels still answer "what caused this", never "what would the
    fix have done".
    """
    as_of_week = params.horizon_weeks if as_of_week is None else as_of_week
    worlds = _Worlds(scenario, shocks, draws, params, interventions)
    actual = worlds.actual()

    flagged = [m.id for m in scenario.members if actual.flagged(m.id, as_of_week)]
    records = [attribute_member(worlds, mid, as_of_week) for mid in flagged]
    records.sort(key=lambda r: (r["first_flag_week"], r["member_id"]))
    return records
