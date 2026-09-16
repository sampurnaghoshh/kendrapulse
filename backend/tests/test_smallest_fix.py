"""Phase 3 smallest fix: does the ranked list mean what the panel will claim it means?

The panel says "this is the smallest action that stops the spread". Three things have to be
true for that sentence to be honest, and there is a test here for each: the fix really does
protect the peer, it protects her because of the fix and not because of the dice, and a fix
that would push the burden onto somebody else never appears at all.
"""

from dataclasses import replace

import numpy as np
import pytest

from sim.engine import Run, Shock, make_draws, simulate
from sim.interventions import moratorium, reschedule
from sim.params import DEFAULT
from sim.smallest_fix import (
    candidates,
    protection,
    rupees_at_risk,
    smallest_fix,
)

from tests.conftest import build_scenario, make_member

# Pinned, not swept: whether a peer covers in a given week is a draw, and these are exact
# statements about one world. Matches SEED in test_attribution.py and test_r_number.py.
SEED = 0
SHOCKED = "s000"
PEER = "s001"


@pytest.fixture(scope="module")
def spreading_kendra():
    """One kendra, one shocked member, and the peer who paid for it at the meeting.

    (scenario, shocks, draws). No links outside the kendra, so guarantee cover is the only
    channel that can move anything and a protected peer can only have been protected
    through the meeting.
    """
    scenario = build_scenario([make_member(i, "kA", "tailoring", "Sahyog") for i in range(5)])
    shocks = [Shock(type="health", start_week=1, member_id=SHOCKED)]
    draws = make_draws(scenario.n_members, DEFAULT, seed=SEED)
    return scenario, shocks, draws


@pytest.fixture(scope="module")
def spreading_actual(spreading_kendra):
    scenario, shocks, draws = spreading_kendra
    return simulate(scenario, shocks, [], DEFAULT, draws)


def test_the_fixture_really_does_spread(spreading_kendra, spreading_actual):
    """A precondition, not a result. Every test below is meaningless if nobody caught
    anything in the first place."""
    scenario, _, _ = spreading_kendra
    flagged = {m.id for m in scenario.members if spreading_actual.flagged(m.id)}
    assert flagged == {SHOCKED, PEER}


# ------------------------------------------------------------------------------------
# 1. A fix on the index case protects the peer who was carrying her
# ------------------------------------------------------------------------------------


def test_a_moratorium_on_the_index_case_protects_the_transmitted_peer(
    spreading_kendra, spreading_actual
):
    """The claim the whole prototype is built to make.

    Nothing about the peer changes: not her income, not her savings, not her own
    installment. Pausing the INDEX case's payments removes the gap she used to bring to the
    meeting, so the peer is never asked to cover it, and she comes out green.
    """
    scenario, shocks, draws = spreading_kendra
    fix = moratorium(SHOCKED, start_week=1, weeks=4)
    run = simulate(scenario, shocks, [fix], DEFAULT, draws)

    protected, newly_flagged = protection(scenario, spreading_actual, run)
    assert PEER in protected
    assert newly_flagged == []

    # And the mechanism is the one we just described: she is no longer covering anybody.
    gave_before = sum(spreading_actual.states[w][PEER]["cover_given"] for w in range(1, 13))
    gave_after = sum(run.states[w][PEER]["cover_given"] for w in range(1, 13))
    assert gave_before > 0
    assert gave_after < gave_before

    # It also reaches the ranking, which is what the panel actually shows.
    best = smallest_fix(scenario, shocks, DEFAULT, draws, decision_week=1)
    assert best, "the search found nothing on a kendra that demonstrably spreads"
    assert any(PEER in entry["members_protected"] for entry in best)


def test_the_ranking_prefers_more_protection_then_lower_cost(spreading_kendra):
    scenario, shocks, draws = spreading_kendra
    best = smallest_fix(scenario, shocks, DEFAULT, draws, decision_week=1)

    keys = [(-len(e["members_protected"]), e["lender_cost"]) for e in best]
    assert keys == sorted(keys)
    assert len(best) <= 3
    for entry in best:
        assert entry["members_protected"], "a fix that protects nobody is not an offer"
        assert entry["lender_cost"] >= 0.0
        assert entry["rupees_at_risk_avoided"] > 0.0


def test_every_entry_carries_what_the_panel_needs(spreading_kendra):
    scenario, shocks, draws = spreading_kendra
    for entry in smallest_fix(scenario, shocks, DEFAULT, draws, decision_week=1):
        assert set(entry) == {
            "intervention", "members_protected", "lender_cost", "rupees_at_risk_avoided",
            "run", "r_live_by_week", "cross_kendra_reach_by_week",
        }
        # The replay is a real run on the same slider the actual run uses.
        assert sorted(entry["run"].states) == list(range(1, DEFAULT.horizon_weeks + 1))
        assert set(entry["r_live_by_week"]) == set(scenario.kendras())


def test_rupees_at_risk_is_the_outstanding_of_everyone_flagged(
    spreading_kendra, spreading_actual
):
    scenario, _, _ = spreading_kendra
    expected = sum(
        m.total_outstanding for m in scenario.members if m.id in (SHOCKED, PEER)
    )
    assert rupees_at_risk(scenario, spreading_actual) == pytest.approx(expected)


# ------------------------------------------------------------------------------------
# 2. The identity fix
# ------------------------------------------------------------------------------------


def test_a_reschedule_of_the_whole_installment_replays_identically(spreading_kendra):
    """installment_fraction 1.0 is a fix that changes nothing, so the replay must match the
    actual run float for float. Anything else means an intervention reached past `due`."""
    scenario, shocks, draws = spreading_kendra
    identity = reschedule(SHOCKED, start_week=1, installment_fraction=1.0)
    with_fix = simulate(scenario, shocks, [identity], DEFAULT, draws)
    without = simulate(scenario, shocks, [], DEFAULT, draws)

    assert with_fix.states == without.states
    assert with_fix.events == without.events
    assert protection(scenario, without, with_fix) == ([], [])


# ------------------------------------------------------------------------------------
# 3. A fix cannot act at a distance
# ------------------------------------------------------------------------------------


def test_a_fix_in_another_component_changes_nothing_here(isolated_scenario):
    """kA and kB share no guarantee, no income source and no lender. Helping a member of kB
    must leave every number in kA untouched.

    This is the intervention half of the engine's isolation test. If a fix could move the
    far kendra at all, the ranking could protect somebody by accident and the smallest fix
    panel would be reporting coincidences.
    """
    scenario = isolated_scenario
    draws = make_draws(scenario.n_members, DEFAULT, seed=3)
    shocks = [Shock(type="crop_loss", start_week=2, member_id="s000")]  # kA

    without = simulate(scenario, shocks, [], DEFAULT, draws)
    far_fix = moratorium("s003", start_week=1, weeks=4)  # kB
    with_fix = simulate(scenario, shocks, [far_fix], DEFAULT, draws)

    near = [m.id for m in scenario.members if m.kendra_id == "kA"]
    for week in without.states:
        for member_id in near:
            assert with_fix.states[week][member_id] == without.states[week][member_id], (
                f"{member_id} moved in week {week} because of a fix she has no path to"
            )
    # The fix did land somewhere, so this is not passing by doing nothing at all.
    assert with_fix.states[1]["s003"]["due"] == 0.0


# ------------------------------------------------------------------------------------
# 4. The observation window filters candidates
# ------------------------------------------------------------------------------------


def test_candidates_drop_anything_that_runs_past_the_observation_window(spreading_kendra):
    """With horizon 12 and a 4 week window: at week 8 only reschedules survive, because the
    shortest moratorium would still be deferring payments in week 9. By week 10 nothing
    survives at all, and the honest answer is an empty list rather than a fix we cannot
    judge."""
    scenario, shocks, draws = spreading_kendra

    early = candidates(scenario, DEFAULT, decision_week=1)
    assert len(early) == scenario.n_members * (
        len(DEFAULT.moratorium_weeks_grid) + len(DEFAULT.reschedule_fraction_grid)
    )
    assert all(c.observable(DEFAULT) for c in early)

    at_eight = candidates(scenario, DEFAULT, decision_week=8)
    assert {c.type for c in at_eight} == {"reschedule"}

    assert candidates(scenario, DEFAULT, decision_week=10) == ()
    assert smallest_fix(scenario, shocks, DEFAULT, draws, decision_week=10) == []


# ------------------------------------------------------------------------------------
# 5. Rejection
# ------------------------------------------------------------------------------------


def test_protection_separates_the_protected_from_the_newly_flagged(spreading_kendra):
    """The rule itself, on two runs stated by hand so the arithmetic is unambiguous."""
    scenario, _, _ = spreading_kendra
    ids = [m.id for m in scenario.members]

    def run_flagging(flagged):
        """A Run carrying nothing but the one field `flagged()` reads."""
        return Run(
            states={
                w: {mid: {"s": 1.0 if mid in flagged else 0.0} for mid in ids}
                for w in range(1, DEFAULT.horizon_weeks + 1)
            },
            params=DEFAULT,
        )

    actual = run_flagging({SHOCKED, PEER})
    intervened = run_flagging({SHOCKED, "s002"})  # peer saved, a bystander pushed over
    protected, newly_flagged = protection(scenario, actual, intervened)
    assert protected == [PEER]
    assert newly_flagged == ["s002"]


def test_a_fix_that_newly_flags_anybody_is_never_offered(spreading_kendra, monkeypatch):
    """Rejection is absolute: no cost saving and no amount of protection buys it back.

    Every replay is forced to push one green bystander over, so every candidate must be
    rejected and the search must return nothing. The unpatched search returns a non empty
    list on this same fixture, so an empty result here can only be the rejection rule.
    """
    import sim.smallest_fix as sf

    scenario, shocks, draws = spreading_kendra
    assert smallest_fix(scenario, shocks, DEFAULT, draws, decision_week=1)

    victim = "s004"
    actual = simulate(scenario, shocks, [], DEFAULT, draws)
    assert not actual.flagged(victim), "the bystander has to start out green"

    real_simulate = sf.simulate

    def harmful(scenario_, shocks_, interventions, params, draws_):
        run = real_simulate(scenario_, shocks_, interventions, params, draws_)
        if not interventions:
            return run
        states = {w: {mid: dict(row) for mid, row in week.items()}
                  for w, week in run.states.items()}
        states[1][victim]["s"] = 1.0
        return replace(run, states=states)

    monkeypatch.setattr(sf, "simulate", harmful)
    assert smallest_fix(scenario, shocks, DEFAULT, draws, decision_week=1) == []


# ------------------------------------------------------------------------------------
# 6 and 7. Determinism, and the draws every run must share
# ------------------------------------------------------------------------------------


def test_the_ranking_is_identical_across_two_calls(spreading_kendra):
    """The demo shows these three fixes in this order. It has to do so every time."""
    scenario, shocks, draws = spreading_kendra
    first = smallest_fix(scenario, shocks, DEFAULT, draws, decision_week=1)
    second = smallest_fix(scenario, shocks, DEFAULT, draws, decision_week=1)

    assert [e["intervention"] for e in first] == [e["intervention"] for e in second]
    for a, b in zip(first, second):
        assert a["members_protected"] == b["members_protected"]
        assert a["lender_cost"] == b["lender_cost"]
        assert a["rupees_at_risk_avoided"] == b["rupees_at_risk_avoided"]
        assert a["r_live_by_week"] == b["r_live_by_week"]
        assert a["run"].states == b["run"].states
    assert np.array_equal(draws, make_draws(scenario.n_members, DEFAULT, seed=SEED)), (
        "the search mutated the draws it was given"
    )


def test_every_replay_is_handed_the_same_draws_object(spreading_kendra, monkeypatch):
    """Not equal arrays: the SAME object.

    Every claim on the panel is a subtraction between the actual run and a replay. If the
    search rebuilt draws for either side, "this fix protects Sunita" would be part fix and
    part dice, and would look entirely plausible while meaning nothing. Both modules that
    run a world are watched, because the new R comes from attribution's worlds.
    """
    import sim.attribution as attribution
    import sim.smallest_fix as sf

    seen = []

    def spy(scenario_, shocks_, interventions, params, draws_):
        seen.append(draws_)
        return simulate(scenario_, shocks_, interventions, params, draws_)

    monkeypatch.setattr(sf, "simulate", spy)
    monkeypatch.setattr(attribution, "simulate", spy)

    scenario, shocks, draws = spreading_kendra
    smallest_fix(scenario, shocks, DEFAULT, draws, decision_week=1)

    assert len(seen) > len(candidates(scenario, DEFAULT, 1)), "the replays never happened"
    assert all(d is draws for d in seen)


def test_the_search_refuses_to_invent_its_own_draws(spreading_kendra):
    """A caller who forgets the draws is a caller about to compare two different worlds."""
    scenario, shocks, _ = spreading_kendra
    with pytest.raises(ValueError):
        smallest_fix(scenario, shocks, DEFAULT, None, decision_week=1)
