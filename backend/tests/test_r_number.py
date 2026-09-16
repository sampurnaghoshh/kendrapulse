"""Phase 2 R numbers: does the ratio count the right cases, and is the stress test honest?

Same discipline as the attribution tests: each test states ONE fact about a world built by
hand, so a failure names the mistake. The generated demo scenario appears only where the
point IS the demo story.
"""

import numpy as np
import pytest

from sim.attribution import INDEPENDENT, INDEX, TRANSMITTED, attribute
from sim.engine import Shock, make_draws, simulate
from sim.generator import generate_scenario
from sim.params import DEFAULT
from sim.r_number import (
    cross_kendra_reach_by_week,
    r_for_display,
    r_live_by_week,
    r_numbers,
    r_potential,
)

from tests.conftest import build_scenario, make_member

# Pinned, not swept. Whether a peer covers in a given week is a draw, and these tests are
# exact statements about one world. Matches SEED in test_attribution.py.
SEED = 0
SHOCKED = "s000"
PEER = "s001"

# The seeded baseline story from Phase 2: nobody is shocked, m002's income erodes, m004
# flags because she covered her at the meeting.
BASELINE_DRAWS_SEED = 1


def _kendra(n=5, **kwargs):
    return build_scenario(
        [make_member(i, "kA", "tailoring", "Sahyog", **kwargs) for i in range(n)]
    )


# ------------------------------------------------------------------------------------
# R live
# ------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def one_index_one_transmitted():
    """One kendra, one shocked member, and the peer who paid for it.

    A single kendra with no outside links: guarantee cover is the only channel that can
    move anything, so a peer who flags can only have got there through the meeting. That
    makes the numerator of R live unambiguous.
    """
    scenario = _kendra()
    draws = make_draws(scenario.n_members, DEFAULT, seed=SEED)
    records = attribute(
        scenario, [Shock(type="health", start_week=1, member_id=SHOCKED)], draws, DEFAULT
    )
    return scenario, records


def test_one_index_case_and_one_transmitted_peer_gives_r_live_of_one(
    one_index_one_transmitted,
):
    """The textbook case: one primary case, one onward case, R = 1."""
    scenario, records = one_index_one_transmitted
    by_id = {r["member_id"]: r for r in records}
    assert by_id[SHOCKED]["label"] == INDEX
    assert by_id[PEER]["label"] == TRANSMITTED
    assert by_id[PEER]["source_id"] == SHOCKED

    series = r_live_by_week(scenario, records, DEFAULT)["kA"]
    peer_week = by_id[PEER]["first_flag_week"]
    index_week = by_id[SHOCKED]["first_flag_week"]

    # Before the index case is counted there is nothing to divide by.
    assert all(series[w - 1] is None for w in range(1, index_week))
    # Between the two flags the denominator exists and the numerator does not yet.
    assert all(series[w - 1] == 0.0 for w in range(index_week, peer_week))
    # From her first flag week onward, one onward case per primary case.
    assert all(series[w - 1] == 1.0 for w in range(peer_week, DEFAULT.horizon_weeks + 1))


def test_r_live_is_none_every_week_with_no_shocks_and_no_declining_members(
    one_index_one_transmitted,
):
    """No cause anywhere means no case anywhere, and R is a ratio with no denominator.

    Reporting 0.0 here would read as "this kendra is not spreading stress", which is a
    claim about a kendra where nothing has happened at all. None is the honest answer and
    it is what tells the UI to show R potential instead.
    """
    scenario, _ = one_index_one_transmitted
    draws = make_draws(scenario.n_members, DEFAULT, seed=SEED)
    records = attribute(scenario, [], draws, DEFAULT)

    assert records == [], "this fixture is meant to have no cause of any kind in it"
    assert r_live_by_week(scenario, records, DEFAULT)["kA"] == [None] * DEFAULT.horizon_weeks


def test_a_declining_member_counts_as_a_primary_case():
    """INDEPENDENT sits in the denominator too, not only INDEX.

    In the seeded baseline m004 is TRANSMITTED from m002, whose income is simply eroding.
    Counting only INDEX cases would leave that onward case in the numerator with a zero
    denominator, and the whole k0 story would report R as undefined.
    """
    scenario = generate_scenario()
    draws = make_draws(scenario.n_members, DEFAULT, seed=BASELINE_DRAWS_SEED)
    records = attribute(scenario, [], draws, DEFAULT)
    by_id = {r["member_id"]: r for r in records}
    assert by_id["m002"]["label"] == INDEPENDENT
    assert by_id["m004"]["label"] == TRANSMITTED

    row = next(r for r in r_numbers(scenario, [], draws, DEFAULT, records=records)
               if r["kendra_id"] == "k0")
    assert row["primary_ids"] == ["m002"]
    assert row["transmitted_ids"] == ["m004"]
    assert row["r_live_by_week"][-1] == 1.0


def test_r_live_waits_for_the_source_to_become_a_case_too():
    """An onward case is only onward once the case it came from is counted.

    m004 flags in week 12 and her source m002 in week 11, so week 11 must read 0.0 and
    week 12 must read 1.0. If the numerator ignored the source's own flag week, a
    transmitted member could be counted in a week where her source was still green.
    """
    scenario = generate_scenario()
    draws = make_draws(scenario.n_members, DEFAULT, seed=BASELINE_DRAWS_SEED)
    records = attribute(scenario, [], draws, DEFAULT)
    series = r_live_by_week(scenario, records, DEFAULT)["k0"]

    assert series[10] == 0.0  # week 11: m002 is a case, m004 is not yet
    assert series[11] == 1.0  # week 12: both


# ------------------------------------------------------------------------------------
# Scale: R live stays inside the kendra, cross kendra reach reports the rest
# ------------------------------------------------------------------------------------


def _record(member_id, label, source_id, first_flag_week):
    """A minimal attribution record. Both R functions read records and simulate nothing, so
    writing the labels by hand is the only way to state a fact about the COUNTING rule
    without also depending on whichever channel happened to fire in a generated world."""
    return {
        "member_id": member_id,
        "label": label,
        "source_id": source_id,
        "source_cause": "shock",
        "sole_source": True,
        "path": [],
        "first_flag_week": first_flag_week,
        "tags": (),
        "contributors": [],
    }


@pytest.fixture
def spread_across_two_kendras(isolated_scenario):
    """One primary case in kA with two onward cases: a peer in kA, and a member of kB.

    kB shares no guarantee edge with kA, so in the real engine an onward case there could
    only have arrived through a lender freezing top ups. What is being tested here is the
    arithmetic that follows from such a case, so the labels are stated rather than grown.
    """
    records = [
        _record("s000", INDEX, "s000", 2),
        _record("s001", TRANSMITTED, "s000", 3),  # same kendra as her source
        _record("s003", TRANSMITTED, "s000", 4),  # kB: charged to kA, counted separately
    ]
    return isolated_scenario, records


def test_r_live_counts_only_onward_cases_inside_the_source_kendra(spread_across_two_kendras):
    """One of the two onward cases is a kendra peer, so R live is 1.0 and not 2.0.

    This is what puts R live on R potential's scale. Both numbers now answer "per case,
    how much of THIS group goes down", so the figure under a cluster does not change
    meaning the moment somebody flags.
    """
    scenario, records = spread_across_two_kendras
    series = r_live_by_week(scenario, records, DEFAULT)

    assert series["kA"][1] == 0.0  # week 2: s000 is a case, nobody has caught it yet
    assert series["kA"][2] == 1.0  # week 3: the kendra peer s001 flags
    assert series["kA"][3] == 1.0  # week 4: s003 flags in kB and does NOT raise this
    assert series["kA"][-1] == 1.0
    # kB has no primary case of its own, so it has no R live at all.
    assert series["kB"] == [None] * DEFAULT.horizon_weeks


def test_cross_kendra_reach_counts_the_onward_case_in_the_other_kendra(
    spread_across_two_kendras,
):
    """Charged to kA, whose primary case caused it, and never to kB, where it landed."""
    scenario, records = spread_across_two_kendras
    reach = cross_kendra_reach_by_week(scenario, records, DEFAULT)

    assert reach["kA"][2] == 0.0  # week 3: only the kendra peer has flagged so far
    assert reach["kA"][3] == 1.0  # week 4: one primary in kA, one onward case outside it
    assert reach["kB"] == [None] * DEFAULT.horizon_weeks


def test_the_two_series_share_one_denominator(spread_across_two_kendras):
    """They are read as a pair under one cluster, so they must divide by the same thing."""
    scenario, records = spread_across_two_kendras
    live = r_live_by_week(scenario, records, DEFAULT)["kA"]
    reach = cross_kendra_reach_by_week(scenario, records, DEFAULT)["kA"]

    assert [v is None for v in live] == [v is None for v in reach]
    # Two onward cases, one primary: the pair adds up to the whole spread, split by scale.
    assert live[-1] + reach[-1] == 2.0


def test_cross_kendra_reach_is_zero_when_the_spread_stayed_at_home(demo_rows):
    """Zero, not None: k0 HAS a case to divide by, and the honest answer is that none of
    its stress left the kendra. None would wrongly say "no denominator"."""
    _, rows = demo_rows
    k0 = next(r for r in rows if r["kendra_id"] == "k0")
    assert k0["r_live_by_week"][-1] == 1.0
    assert k0["cross_kendra_reach_by_week"][-1] == 0.0
    assert k0["cross_kendra_ids"] == []


# ------------------------------------------------------------------------------------
# R potential
# ------------------------------------------------------------------------------------


def test_r_potential_ignores_members_already_flagged_at_baseline():
    """The exclusion, stated as an exact number.

    This kendra is underwritten at the RBI ceiling with essentially no savings, so every
    member is already flagged inside the window before anything is planted. A count that
    forgot the baseline would see all four peers flagged in every probe run and report
    R potential of 4.0, the most fragile kendra possible, when in truth the probe changed
    nothing about anybody. The right answer is 0.0.
    """
    scenario = _kendra(due_share=0.50, buffer_weeks=0.01, household_size=7)
    draws = make_draws(scenario.n_members, DEFAULT, seed=SEED)
    window_end = DEFAULT.r_window_weeks  # the probe starts in week 1

    baseline = simulate(scenario, [], [], DEFAULT, draws)
    assert all(baseline.flagged(m.id, window_end) for m in scenario.members), (
        "the fixture only makes its point if everybody is flagged before the probe"
    )
    # What a baseline blind count would have reported.
    naive = []
    for planted in scenario.members:
        run = simulate(
            scenario,
            [Shock(type="health", start_week=1, member_id=planted.id)],
            [],
            DEFAULT,
            draws,
        )
        naive.append(
            sum(1 for m in scenario.members if m.id != planted.id and run.flagged(m.id, window_end))
        )
    assert sum(naive) / len(naive) == pytest.approx(scenario.n_members - 1)

    assert r_potential(scenario, draws, DEFAULT)["kA"] == 0.0


@pytest.mark.parametrize("n_kendras,members_per_kendra", [(5, 5), (3, 4), (4, 7)])
def test_r_potential_stays_between_zero_and_the_number_of_peers(
    n_kendras, members_per_kendra
):
    """It counts peers inside the kendra, so it cannot exceed members_per_kendra - 1.

    The bound is what lets the UI draw R potential as a fraction of the kendra ring. It is
    parametrised over kendra sizes because the generator must scale to a branch and the
    bound has to scale with it.
    """
    scenario = generate_scenario(
        n_kendras=n_kendras, members_per_kendra=members_per_kendra
    )
    draws = make_draws(scenario.n_members, DEFAULT, seed=BASELINE_DRAWS_SEED)
    for kendra_id, value in r_potential(scenario, draws, DEFAULT).items():
        assert 0.0 <= value <= members_per_kendra - 1, (kendra_id, value)


def test_r_potential_is_defined_when_every_member_is_green(one_index_one_transmitted):
    """The reason R potential exists. R live has nothing to say about a healthy kendra,
    and a healthy kendra is exactly where a lender still has time to act."""
    scenario, _ = one_index_one_transmitted
    draws = make_draws(scenario.n_members, DEFAULT, seed=SEED)
    baseline = simulate(scenario, [], [], DEFAULT, draws)

    assert not any(baseline.flagged(m.id) for m in scenario.members)
    value = r_potential(scenario, draws, DEFAULT)["kA"]
    assert value is not None
    assert value > 0.0, "a kendra of five joint liability peers is not immune to a shock"


def test_r_potential_ignores_the_scenarios_own_shocks(one_index_one_transmitted):
    """It is a property of the roster and the network, not of this quarter's events. If a
    planted shock could move it, the number would stop being comparable between kendras
    and the UI could not use it as a susceptibility score."""
    scenario, _ = one_index_one_transmitted
    draws = make_draws(scenario.n_members, DEFAULT, seed=SEED)
    shocks = [Shock(type="crop_loss", start_week=2, member_id=SHOCKED)]

    without = r_numbers(scenario, [], draws, DEFAULT)
    with_shock = r_numbers(scenario, shocks, draws, DEFAULT)
    assert [r["r_potential"] for r in without] == [r["r_potential"] for r in with_shock]


def test_every_probe_world_is_handed_the_same_draws_object(one_index_one_transmitted, monkeypatch):
    """Not equal arrays: the SAME object.

    R potential is a subtraction between a probe world and a baseline. If it rebuilt draws
    for either one, the difference would be part shock and part dice, and the number would
    look perfectly plausible while meaning nothing.
    """
    import sim.r_number as r_number

    seen = []

    def spy(scenario, shocks, interventions, params, draws):
        seen.append(draws)
        return simulate(scenario, shocks, interventions, params, draws)

    monkeypatch.setattr(r_number, "simulate", spy)

    scenario, _ = one_index_one_transmitted
    draws = make_draws(scenario.n_members, DEFAULT, seed=SEED)
    r_potential(scenario, draws, DEFAULT)

    assert len(seen) == scenario.n_members + 1, "one baseline plus one probe per member"
    assert all(d is draws for d in seen)


# ------------------------------------------------------------------------------------
# Shape of the result
# ------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def demo_rows():
    scenario = generate_scenario()
    draws = make_draws(scenario.n_members, DEFAULT, seed=BASELINE_DRAWS_SEED)
    return scenario, r_numbers(scenario, [], draws, DEFAULT)


def test_one_row_per_kendra_carrying_every_promised_field(demo_rows):
    scenario, rows = demo_rows
    assert [r["kendra_id"] for r in rows] == sorted(scenario.kendras())
    for row in rows:
        assert set(row) == {
            "kendra_id", "r_potential", "r_live_by_week", "cross_kendra_reach_by_week",
            "primary_ids", "transmitted_ids", "cross_kendra_ids",
        }
        for key in ("r_live_by_week", "cross_kendra_reach_by_week"):
            assert len(row[key]) == DEFAULT.horizon_weeks
            assert all(v is None or v >= 0.0 for v in row[key])
        # Both series share one denominator, so they are defined in exactly the same weeks.
        assert [v is None for v in row["r_live_by_week"]] == [
            v is None for v in row["cross_kendra_reach_by_week"]
        ]


def test_primary_and_transmitted_ids_agree_with_the_labels(demo_rows):
    """primary_ids lists this kendra's own cases. transmitted_ids lists the onward cases
    inside it, cross_kendra_ids the ones its primaries pushed into another kendra, and
    every onward case is claimed by exactly one list of exactly one kendra: its source's."""
    scenario, rows = demo_rows
    draws = make_draws(scenario.n_members, DEFAULT, seed=BASELINE_DRAWS_SEED)
    records = {r["member_id"]: r for r in attribute(scenario, [], draws, DEFAULT)}
    kendra_of = {m.id: m.kendra_id for m in scenario.members}

    for row in rows:
        for member_id in row["primary_ids"]:
            assert records[member_id]["label"] in (INDEX, INDEPENDENT)
            assert kendra_of[member_id] == row["kendra_id"]
        for member_id in row["transmitted_ids"] + row["cross_kendra_ids"]:
            assert records[member_id]["label"] == TRANSMITTED
            assert kendra_of[records[member_id]["source_id"]] == row["kendra_id"]
        # The split is on where the onward case LIVES, not on where it came from.
        assert all(kendra_of[mid] == row["kendra_id"] for mid in row["transmitted_ids"])
        assert all(kendra_of[mid] != row["kendra_id"] for mid in row["cross_kendra_ids"])

    claimed = [mid for row in rows for mid in row["transmitted_ids"] + row["cross_kendra_ids"]]
    assert len(claimed) == len(set(claimed))


def test_r_numbers_reuses_the_records_it_is_given(demo_rows, monkeypatch):
    """The API hands one attribution result to both answers. Attributing twice would be
    the same work again and, worse, an invitation to do it with different draws."""
    import sim.r_number as r_number

    scenario, rows = demo_rows
    draws = make_draws(scenario.n_members, DEFAULT, seed=BASELINE_DRAWS_SEED)
    records = attribute(scenario, [], draws, DEFAULT)

    def refuse(*args, **kwargs):
        raise AssertionError("attribute was called again despite records being supplied")

    monkeypatch.setattr(r_number, "attribute", refuse)
    assert r_numbers(scenario, [], draws, DEFAULT, records=records) == rows


def test_the_display_choice_names_the_number_it_shows(demo_rows):
    """R live the moment there is a case to divide by, R potential before that."""
    _, rows = demo_rows
    k0 = next(r for r in rows if r["kendra_id"] == "k0")

    early = r_for_display(k0, 1)
    assert early == {"kind": "potential", "value": k0["r_potential"]}
    late = r_for_display(k0, DEFAULT.horizon_weeks)
    assert late == {"kind": "live", "value": k0["r_live_by_week"][-1]}

    for row in rows:
        for week in range(1, DEFAULT.horizon_weeks + 1):
            shown = r_for_display(row, week)
            assert shown["kind"] in ("live", "potential")
            assert shown["value"] is not None


def test_r_numbers_is_deterministic_and_does_not_touch_the_draws(demo_rows):
    scenario, rows = demo_rows
    draws = make_draws(scenario.n_members, DEFAULT, seed=BASELINE_DRAWS_SEED)
    assert r_numbers(scenario, [], draws, DEFAULT) == rows
    assert np.array_equal(
        draws, make_draws(scenario.n_members, DEFAULT, seed=BASELINE_DRAWS_SEED)
    ), "the R numbers mutated the draws they were given"
