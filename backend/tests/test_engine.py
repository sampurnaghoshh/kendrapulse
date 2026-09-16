"""Phase 1 engine guarantees.

The determinism and isolation tests are the point of this file. Everything Phase 2 does is
a subtraction between two runs, so if the dice can shift between those runs the labels are
measuring noise. These tests are what stops that happening silently.
"""

import networkx as nx
import pytest

from sim.engine import Shock, make_draws, simulate
from sim.generator import generate_scenario
from sim.params import DEFAULT, N_CHANNELS

from tests.conftest import build_scenario, make_member


@pytest.fixture(scope="module")
def demo():
    return generate_scenario()


@pytest.fixture(scope="module")
def draws(demo):
    return make_draws(demo.n_members, DEFAULT, seed=7)


def run(scenario, shocks, draws, params=DEFAULT):
    return simulate(scenario, shocks, [], params, draws)


# ------------------------------------------------------------------------------------
# Common random numbers
# ------------------------------------------------------------------------------------


def test_same_seed_gives_identical_output(demo, draws):
    a = run(demo, [], draws)
    b = run(demo, [], draws)
    assert a.states == b.states
    assert a.events == b.events


def test_draws_are_reproducible_from_the_seed(demo):
    assert (make_draws(demo.n_members, DEFAULT, seed=7)
            == make_draws(demo.n_members, DEFAULT, seed=7)).all()
    assert not (make_draws(demo.n_members, DEFAULT, seed=7)
                == make_draws(demo.n_members, DEFAULT, seed=8)).all()


def test_draws_shape_matches_scenario_and_horizon(demo, draws):
    assert draws.shape == (demo.n_members, DEFAULT.horizon_weeks + 1, N_CHANNELS)
    assert ((draws >= 0.0) & (draws < 1.0)).all()


def test_wrong_shaped_draws_are_rejected(demo):
    """A mismatched array is almost always a caller who built a fresh one for the
    counterfactual, which is exactly the bug common random numbers exist to prevent."""
    with pytest.raises(ValueError):
        run(demo, [], make_draws(demo.n_members + 1, DEFAULT, seed=7))


def test_no_shock_run_equals_its_counterfactual(demo, draws):
    """With nothing planted, removing a member's shocks removes nothing, so the two worlds
    must agree float for float. Any drift here is the engine rolling its own dice."""
    shocks = []
    actual = run(demo, shocks, draws)
    counterfactual = run(demo, [s for s in shocks if s.member_id != "m000"], draws)
    assert actual.states == counterfactual.states
    assert actual.events == counterfactual.events


def test_removing_a_shock_changes_only_the_shocked_component(isolated_scenario):
    """The load bearing test.

    Two kendras sharing no guarantee, no income source and no lender are separate
    connected components, so a shock inside one cannot reach the other through any
    modelled channel. If the far kendra's numbers move at all, randomness leaked: some
    draw was consumed in event order rather than being pinned to a (person, week, channel).
    """
    sc = isolated_scenario
    assert nx.number_connected_components(sc.graph) == 2
    draws = make_draws(sc.n_members, DEFAULT, seed=3)

    shock = Shock(type="crop_loss", start_week=2, member_id="s000")
    actual = run(sc, [shock], draws)
    without = run(sc, [], draws)

    far_kendra = [m.id for m in sc.members if m.kendra_id == "kB"]
    for week in actual.states:
        for member_id in far_kendra:
            assert actual.states[week][member_id] == without.states[week][member_id], (
                f"{member_id} moved in week {week} despite no path to the shock"
            )

    # And the shock did land, and did travel inside its own component, so the test is not
    # passing by simply doing nothing anywhere.
    assert actual.peak_stress("s000") > without.peak_stress("s000")
    near_kendra = [m.id for m in sc.members if m.kendra_id == "kA" and m.id != "s000"]
    assert any(
        actual.states[w][mid] != without.states[w][mid]
        for w in actual.states
        for mid in near_kendra
    ), "the shock never reached the peers it shares a guarantee with"


# ------------------------------------------------------------------------------------
# Behaviour
# ------------------------------------------------------------------------------------


def test_baseline_is_mostly_green(demo):
    """Ordinary life is not a crisis. If a no shock run flags people, every later label is
    describing the simulator's own pessimism rather than anything that happened."""
    declining = {m.id for m in demo.members if m.income_trend <= DEFAULT.declining_trend}
    for seed in range(10):
        base = run(demo, [], make_draws(demo.n_members, DEFAULT, seed=seed))
        flagged = [m.id for m in demo.members if base.flagged(m.id)]
        assert len(flagged) <= 3, f"seed {seed}: {flagged}"
        # Whoever does flag must be one of the deliberately slipping livelihoods.
        assert set(flagged) <= declining, f"seed {seed}: {flagged}"


def test_a_severe_shock_raises_stress(demo, draws):
    base = run(demo, [], draws)
    shocked = run(demo, [Shock(type="crop_loss", start_week=2, member_id="m000")], draws)
    assert shocked.peak_stress("m000") > base.peak_stress("m000")
    assert shocked.flagged("m000")


def test_shock_is_confined_to_its_weeks(demo, draws):
    """Income returns to normal once the shock ends; only the stress memory persists."""
    shock = Shock(type="job_loss", start_week=3, member_id="m000")
    shocked = run(demo, [shock], draws)
    base = run(demo, [], draws)
    severity, duration = shock.resolve(DEFAULT)
    for week in range(1, DEFAULT.horizon_weeks + 1):
        same = shocked.states[week]["m000"]["income"] == pytest.approx(
            base.states[week]["m000"]["income"]
        )
        assert same is not (shock.start_week <= week < shock.start_week + duration)


def test_a_source_wide_shock_hits_everyone_on_that_source(demo, draws):
    source = "farm_labour"
    on_source = [m.id for m in demo.members if m.income_source == source]
    assert len(on_source) >= 2
    base = run(demo, [], draws)
    monsoon = run(demo, [Shock(type="weak_monsoon", start_week=2, income_source=source)], draws)
    for member_id in on_source:
        assert monsoon.states[3][member_id]["income"] < base.states[3][member_id]["income"]


def test_stress_and_status_stay_consistent(demo, draws):
    shocked = run(demo, [Shock(type="crop_loss", start_week=2, member_id="m000")], draws)
    for week_row in shocked.states.values():
        for row in week_row.values():
            assert 0.0 <= row["s"] <= 1.0
            expected = (
                "red" if row["s"] >= DEFAULT.red
                else "amber" if row["s"] >= DEFAULT.amber
                else "green"
            )
            assert row["status"] == expected


def test_stress_decays_but_never_ratchets(demo, draws):
    """The memory term is a floor that halves each week, not a running total. If it were
    additive the whole roster would saturate at 1.0 before the horizon ended."""
    shocked = run(demo, [Shock(type="crop_loss", start_week=2, member_id="m000")], draws)
    for week in range(2, DEFAULT.horizon_weeks + 1):
        for member_id, row in shocked.states[week].items():
            previous = shocked.states[week - 1][member_id]["s"]
            assert row["s"] >= DEFAULT.stress_memory * previous - 1e-9


# ------------------------------------------------------------------------------------
# Event log: ground truth for Phase 2 explanations and Phase 4 validation
# ------------------------------------------------------------------------------------


def test_event_log_is_sane(demo, draws):
    shocked = run(demo, [Shock(type="crop_loss", start_week=2, member_id="m000")], draws)
    ids = {m.id for m in demo.members}
    assert shocked.events, "a severe shock should produce at least one transfer"
    for event in shocked.events:
        assert event["amount"] > 0
        assert event["from_id"] in ids and event["to_id"] in ids
        assert event["from_id"] != event["to_id"]
        assert 1 <= event["week"] <= DEFAULT.horizon_weeks
        assert event["channel"] in {"guarantee", "shared_lender"}


def test_cover_never_exceeds_the_shortfall_it_is_covering(demo, draws):
    shocked = run(demo, [Shock(type="crop_loss", start_week=2, member_id="m000")], draws)
    for week, week_row in shocked.states.items():
        for member_id, row in week_row.items():
            assert row["covered_in"] <= row["own_shortfall"] + 1e-9, (member_id, week)


def test_the_two_shortfalls_reconcile(demo, draws):
    """own_shortfall drives her stress, unpaid drives what the lender sees. They must
    differ by exactly what her peers put in, or one of the two is lying."""
    shocked = run(demo, [Shock(type="crop_loss", start_week=2, member_id="m000")], draws)
    for week_row in shocked.states.values():
        for row in week_row.values():
            assert row["unpaid"] == pytest.approx(row["own_shortfall"] - row["covered_in"])
            assert row["paid"] + row["unpaid"] == pytest.approx(row["due"])
            assert row["unpaid"] >= -1e-9


def test_guarantee_transfers_reconcile_with_member_totals(demo, draws):
    """Every rupee logged left one member's buffer and arrived at another's shortfall."""
    shocked = run(demo, [Shock(type="crop_loss", start_week=2, member_id="m000")], draws)
    for week, week_row in shocked.states.items():
        covers = [e for e in shocked.events if e["week"] == week and e["channel"] == "guarantee"]
        for member_id, row in week_row.items():
            given = sum(e["amount"] for e in covers if e["from_id"] == member_id)
            got = sum(e["amount"] for e in covers if e["to_id"] == member_id)
            assert given == pytest.approx(row["covered_out"])
            assert got == pytest.approx(row["covered_in"])


def test_cover_only_flows_between_kendra_peers(demo, draws):
    """Guarantee cover is joint liability, which exists only inside a kendra. A transfer
    crossing kendras would mean the channel is not what the explanation claims it is."""
    shocked = run(demo, [Shock(type="crop_loss", start_week=2, member_id="m000")], draws)
    for event in shocked.events:
        if event["channel"] == "guarantee":
            assert demo.member(event["from_id"]).kendra_id == demo.member(event["to_id"]).kendra_id


def test_a_flagged_peer_does_not_rescue_anyone():
    """Someone already in trouble is not a source of help. Built by hand: one member with
    almost no savings and a heavy shock, peers deliberately left fragile."""
    members = [
        make_member(0, "kA", "tailoring", "Sahyog", buffer_weeks=0.2),
        make_member(1, "kA", "tailoring", "Sahyog", buffer_weeks=0.2, income_trend=-0.05),
        make_member(2, "kA", "tailoring", "Sahyog", buffer_weeks=2.0),
    ]
    sc = build_scenario(members)
    draws = make_draws(sc.n_members, DEFAULT, seed=1)
    result = run(sc, [Shock(type="job_loss", start_week=1, member_id="s000")], draws)

    for event in result.events:
        if event["channel"] != "guarantee":
            continue
        previous = result.states[event["week"] - 1] if event["week"] > 1 else None
        if previous is not None:
            assert previous[event["from_id"]]["s"] < DEFAULT.cover_min_peer_stress_block


def test_interventions_are_not_silently_ignored(demo, draws):
    """They arrive in Phase 3. Until then, accepting and dropping them would be worse than
    refusing them."""
    with pytest.raises(NotImplementedError):
        simulate(demo, [], [{"type": "moratorium"}], DEFAULT, draws)
