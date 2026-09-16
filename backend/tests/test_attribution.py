"""Phase 2 attribution: does the label say what actually happened?

Each test states ONE fact about a world we built by hand, so a failure names the mistake
instead of just saying the demo looks wrong. The generated demo scenario is one connected
component; it can confirm a story but it cannot isolate a mechanism.
"""

import numpy as np
import pytest

from sim.attribution import (
    INDEPENDENT,
    INDEX,
    TRANSMITTED,
    _Worlds,
    attribute,
    expand_shocks,
)
from sim.engine import Shock, make_draws, simulate
from sim.generator import generate_scenario
from sim.params import DEFAULT

from tests.conftest import build_scenario, make_member

# Seed pinned, not swept: transmission depends on which peers happen to be willing in
# which weeks, and these tests are exact statements about one world and its
# counterfactuals. Matches TRANSMISSION_SEED in test_engine.py, where the same kendra is
# shown to transmit at all.
SEED = 0
SHOCKED = "s000"
PEER = "s001"
DECLINING = "s005"


@pytest.fixture(scope="module")
def three_labels():
    """One kendra that will carry a shock, plus a second kendra that shares nothing.

    The declining member sits in the far kendra on a different income source with a
    different lender, so no guarantee, correlated income or lender freeze path can reach
    her. When she flags, her own slipping income is the only thing that could have done
    it, which is what makes the INDEPENDENT assertion mean something.
    """
    near = [make_member(i, "kA", "tailoring", "Sahyog") for i in range(5)]
    far = [make_member(i, "kB", "dairy", "Uday Credit") for i in range(5, 8)]
    # Thin savings, a large household and an installment near the top of the generator's
    # target band: the profile a slipping income actually catches up with inside 12 weeks.
    # With the default comfortable profile her trend never reaches amber and the
    # INDEPENDENT case would be untestable.
    far[0] = make_member(
        5,
        "kB",
        "dairy",
        "Uday Credit",
        income_trend=DEFAULT.declining_trend,
        buffer_weeks=0.95,
        due_share=0.32,
        household_size=7,
    )
    return build_scenario(near + far)


@pytest.fixture(scope="module")
def three_labels_records(three_labels):
    draws = make_draws(three_labels.n_members, DEFAULT, seed=SEED)
    shocks = [Shock(type="health", start_week=1, member_id=SHOCKED)]
    return {r["member_id"]: r for r in attribute(three_labels, shocks, draws, DEFAULT)}


# ------------------------------------------------------------------------------------
# The three labels, on a scenario built to contain exactly one of each
# ------------------------------------------------------------------------------------


def test_the_shocked_member_is_an_index_case(three_labels_records):
    record = three_labels_records[SHOCKED]
    assert record["label"] == INDEX
    assert record["source_cause"] == "shock"
    assert record["source_id"] == SHOCKED  # an index case is her own source


def test_the_covering_peer_is_transmitted_from_the_shocked_member(three_labels_records):
    """She never had a cause of her own; she paid for somebody else's."""
    record = three_labels_records[PEER]
    assert record["label"] == TRANSMITTED
    assert record["source_id"] == SHOCKED
    assert record["source_cause"] == "shock"


def test_the_transmitted_peer_has_a_guarantee_path_back_to_the_source(three_labels_records):
    path = three_labels_records[PEER]["path"]
    assert path, "a transmitted case with no path leaves the UI nothing to explain"
    assert path[0]["from_id"] == SHOCKED
    assert path[-1]["to_id"] == PEER
    assert all(step["channel"] == "guarantee" for step in path)
    # Observed in the event log, not guessed from the graph.
    assert not any(step["inferred"] for step in path)
    assert all(step["week"] <= three_labels_records[PEER]["first_flag_week"] for step in path)


def test_the_declining_member_is_independent(three_labels_records):
    record = three_labels_records[DECLINING]
    assert record["label"] == INDEPENDENT
    assert record["source_cause"] == "trend"
    assert "declining_income" in record["tags"]
    assert record["path"] == []


def test_no_label_reaches_across_the_two_components(three_labels, three_labels_records):
    """kA and kB share no guarantee, no income source and no lender, so no stress can
    cross between them. A source named on the far side of that gap would be the procedure
    inventing a culprit out of a coincidence in the dice."""
    kendra_of = {m.id: m.kendra_id for m in three_labels.members}
    for record in three_labels_records.values():
        if record["source_id"] is None:
            continue
        assert kendra_of[record["source_id"]] == kendra_of[record["member_id"]]


# ------------------------------------------------------------------------------------
# The case that forced the revision: a trend is a cause
# ------------------------------------------------------------------------------------

BASELINE_DRAWS_SEED = 1


@pytest.fixture(scope="module")
def baseline_records():
    """The seeded demo scenario with NO shocks planted anywhere."""
    scenario = generate_scenario()
    draws = make_draws(scenario.n_members, DEFAULT, seed=BASELINE_DRAWS_SEED)
    return {r["member_id"]: r for r in attribute(scenario, [], draws, DEFAULT)}


def test_baseline_m004_is_transmitted_from_m002s_declining_income(baseline_records):
    """The regression this revision exists for.

    m004 has no shock, no negative trend and a comfortable buffer. She flags in week 12
    only because she covered m002 at the meeting, and m002 is flagged because her income
    is eroding. Treating a shock as the only kind of cause would put m004 in the no shock
    world, find her still flagged and call her INDEPENDENT.
    """
    record = baseline_records["m004"]
    assert record["label"] == TRANSMITTED
    assert record["source_id"] == "m002"
    assert record["source_cause"] == "trend"
    assert record["sole_source"] is True
    assert [step["channel"] for step in record["path"]] == ["guarantee"]


def test_baseline_m002_is_independent(baseline_records):
    """The other half: the source herself had nobody to catch it from."""
    record = baseline_records["m002"]
    assert record["label"] == INDEPENDENT
    assert record["source_cause"] == "trend"


def test_a_trend_only_baseline_produces_no_index_cases(baseline_records):
    """With no shock planted anywhere, nothing can be an index case by definition."""
    assert all(r["label"] != INDEX for r in baseline_records.values())


# ------------------------------------------------------------------------------------
# Common random numbers: the property every label rests on
# ------------------------------------------------------------------------------------


def test_every_world_is_handed_the_same_draws_object(three_labels, monkeypatch):
    """Not "equal arrays": the SAME object.

    Rebuilding draws for a counterfactual is the one bug that would make every label in
    this module meaningless while leaving the numbers looking perfectly plausible, so the
    test checks identity and counts that several worlds really were run.
    """
    import sim.attribution as attribution

    seen = []

    def spy(scenario, shocks, interventions, params, draws):
        seen.append(draws)
        return simulate(scenario, shocks, interventions, params, draws)

    monkeypatch.setattr(attribution, "simulate", spy)

    draws = make_draws(three_labels.n_members, DEFAULT, seed=SEED)
    attribute(three_labels, [Shock(type="health", start_week=1, member_id=SHOCKED)], draws)

    assert len(seen) > 1, "only one world was run, so nothing was actually compared"
    assert all(d is draws for d in seen)


def test_counterfactual_worlds_keep_every_member_on_her_own_draws_row(three_labels):
    """Neutralising a trend must not renumber anybody.

    The worlds are built by replacing members inside the scenario. If that ever changed
    the roster order, `index_of` would stop matching the rows of `draws` and every member
    would silently inherit somebody else's dice.
    """
    draws = make_draws(three_labels.n_members, DEFAULT, seed=SEED)
    worlds = _Worlds(three_labels, [], draws, DEFAULT)
    for trends_kept in ((), (DECLINING,)):
        scenario = worlds._scenario_with(frozenset(trends_kept))
        assert scenario.index_of == three_labels.index_of
        assert [m.id for m in scenario.members] == [m.id for m in three_labels.members]


def test_neutralising_a_trend_leaves_positive_trends_alone(three_labels):
    """A positive trend is part of the stage, not part of what went wrong. Zeroing it
    would make a member poorer in the counterfactual than she is in reality."""
    members = list(three_labels.members)
    members[1] = make_member(1, "kA", "tailoring", "Sahyog", income_trend=0.002)
    scenario = build_scenario(members)

    draws = make_draws(scenario.n_members, DEFAULT, seed=SEED)
    worlds = _Worlds(scenario, [], draws, DEFAULT)
    neutralised = worlds._scenario_with(frozenset())

    assert neutralised.member(members[1].id).income_trend == 0.002
    assert neutralised.member(DECLINING).income_trend == 0.0


# ------------------------------------------------------------------------------------
# Shock expansion: a source wide shock is everybody's OWN shock
# ------------------------------------------------------------------------------------


def test_a_source_wide_shock_expands_to_one_shock_per_member(three_labels):
    expanded = expand_shocks(
        three_labels, [Shock(type="weak_monsoon", start_week=2, income_source="dairy")]
    )
    dairy = {m.id for m in three_labels.members if m.income_source == "dairy"}
    assert {s.member_id for s in expanded} == dairy
    assert all("common_shock" in s.tags for s in expanded)


def test_expansion_does_not_change_the_simulation(three_labels):
    """The flattening is bookkeeping for the filters, never a change to the physics."""
    draws = make_draws(three_labels.n_members, DEFAULT, seed=SEED)
    source_wide = [Shock(type="weak_monsoon", start_week=2, income_source="dairy")]
    a = simulate(three_labels, source_wide, [], DEFAULT, draws)
    b = simulate(three_labels, expand_shocks(three_labels, source_wide), [], DEFAULT, draws)
    assert a.states == b.states
    assert a.events == b.events


def test_a_member_hit_by_a_common_shock_is_her_own_index_case(three_labels):
    """A weak monsoon is not something the dairy members caught from each other."""
    draws = make_draws(three_labels.n_members, DEFAULT, seed=SEED)
    shocks = [Shock(type="weak_monsoon", start_week=1, income_source="dairy")]
    dairy = {m.id for m in three_labels.members if m.income_source == "dairy"}

    # Both windows: the declining member on that source is hit by the monsoon in week 2
    # and her own trend would have caught up with her by week 11 regardless. She is an
    # INDEX case at every point on the slider, not only before week 11.
    for as_of_week in (6, DEFAULT.horizon_weeks):
        records = {
            r["member_id"]: r
            for r in attribute(three_labels, shocks, draws, DEFAULT, as_of_week)
        }
        flagged = dairy & set(records)
        assert flagged, f"the monsoon flagged nobody by week {as_of_week}"
        for member_id in flagged:
            assert records[member_id]["label"] == INDEX, (member_id, as_of_week)
            assert "common_shock" in records[member_id]["tags"]


# ------------------------------------------------------------------------------------
# Shock versus trend when a member carries both
# ------------------------------------------------------------------------------------


def test_a_shock_on_a_declining_member_is_still_an_index_case(three_labels):
    """Her income was slipping AND she was hit. The shock is what pushed her over, so the
    label is INDEX.

    Checked at two windows on purpose. Her trend alone would have flagged her eventually,
    so a necessity test judged at `as_of_week` would call her INDEX early in the demo and
    flip her to INDEPENDENT once the slider passed the week her trend caught up. The label
    has to describe what happened, not how far the slider has been dragged.
    """
    draws = make_draws(three_labels.n_members, DEFAULT, seed=SEED)
    shocks = [Shock(type="job_loss", start_week=1, member_id=DECLINING)]
    for as_of_week in (6, DEFAULT.horizon_weeks):
        records = {
            r["member_id"]: r
            for r in attribute(three_labels, shocks, draws, DEFAULT, as_of_week)
        }
        assert records[DECLINING]["label"] == INDEX, as_of_week
        assert records[DECLINING]["source_cause"] == "shock"


def test_a_late_flag_on_a_declining_member_stays_independent(three_labels):
    """Same member, same slipping income, but the shock is long over by the time she
    flags. Her trend alone still flags her, so the shock was never necessary."""
    draws = make_draws(three_labels.n_members, DEFAULT, seed=SEED)
    trend_only = attribute(three_labels, [], draws, DEFAULT)
    assert trend_only, "nobody flags without a shock, so there is no late flag to test"
    assert {r["member_id"] for r in trend_only} == {DECLINING}
    assert trend_only[0]["label"] == INDEPENDENT


# ------------------------------------------------------------------------------------
# Shape of the record
# ------------------------------------------------------------------------------------


def test_every_flagged_member_gets_exactly_one_record(three_labels, three_labels_records):
    draws = make_draws(three_labels.n_members, DEFAULT, seed=SEED)
    actual = simulate(
        three_labels, [Shock(type="health", start_week=1, member_id=SHOCKED)], [], DEFAULT, draws
    )
    flagged = {m.id for m in three_labels.members if actual.flagged(m.id)}
    assert set(three_labels_records) == flagged


def test_records_carry_every_promised_field(three_labels_records):
    expected = {
        "member_id", "label", "source_id", "source_cause", "sole_source",
        "path", "first_flag_week", "tags", "contributors",
    }
    for record in three_labels_records.values():
        assert set(record) == expected
        assert record["label"] in (INDEX, TRANSMITTED, INDEPENDENT)
        assert record["first_flag_week"] is not None


def test_transmitted_records_list_their_top_contributors(three_labels_records):
    """Ranked, at most two, and the first one is the source we named."""
    for record in three_labels_records.values():
        if record["label"] != TRANSMITTED or record["source_id"] is None:
            continue
        contributors = record["contributors"]
        assert 1 <= len(contributors) <= 2
        assert contributors[0]["member_id"] == record["source_id"]
        drops = [c["drop"] for c in contributors]
        assert drops == sorted(drops, reverse=True)
        assert all(c["drop"] > 0 for c in contributors)


def test_as_of_week_only_looks_at_flags_up_to_that_week(three_labels):
    """The officer asks "who is flagged today", so a flag in week 9 must not appear in the
    week 3 answer."""
    draws = make_draws(three_labels.n_members, DEFAULT, seed=SEED)
    shocks = [Shock(type="health", start_week=1, member_id=SHOCKED)]
    early = attribute(three_labels, shocks, draws, DEFAULT, as_of_week=2)
    late = attribute(three_labels, shocks, draws, DEFAULT, as_of_week=DEFAULT.horizon_weeks)

    assert {r["member_id"] for r in early} <= {r["member_id"] for r in late}
    assert all(r["first_flag_week"] <= 2 for r in early)


def test_attribution_is_deterministic(three_labels):
    draws = make_draws(three_labels.n_members, DEFAULT, seed=SEED)
    shocks = [Shock(type="health", start_week=1, member_id=SHOCKED)]
    first = attribute(three_labels, shocks, draws, DEFAULT)
    second = attribute(three_labels, shocks, draws, DEFAULT)
    assert first == second
    assert np.array_equal(draws, make_draws(three_labels.n_members, DEFAULT, seed=SEED)), (
        "attribution mutated the draws it was given"
    )
