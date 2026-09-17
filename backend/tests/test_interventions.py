"""Phase 3 interventions: does a supportive action change only what a lender controls?

The Intervention object and its price, tested on their own. The search that uses them is in
test_smallest_fix.py.
"""

import pytest

from sim.engine import make_draws, simulate
from sim.interventions import (
    MORATORIUM,
    RESCHEDULE,
    Intervention,
    due_multiplier,
    moratorium,
    reschedule,
)
from sim.params import DEFAULT

from tests.conftest import build_scenario, make_member

MEMBER = "s000"
OTHER = "s001"


@pytest.fixture(scope="module")
def kendra():
    return build_scenario([make_member(i, "kA", "tailoring", "Sahyog") for i in range(5)])


# ------------------------------------------------------------------------------------
# What it does to `due`
# ------------------------------------------------------------------------------------


def test_a_moratorium_zeroes_only_its_own_weeks_and_only_its_own_member():
    fix = moratorium(MEMBER, start_week=3, weeks=2)
    assert [due_multiplier([fix], MEMBER, w) for w in range(1, 7)] == [1.0, 1.0, 0.0, 0.0, 1.0, 1.0]
    assert all(due_multiplier([fix], OTHER, w) == 1.0 for w in range(1, 13))


def test_a_reschedule_does_not_expire():
    """A rescheduled loan is re papered over a longer tenure, so the lower installment is
    the new normal. Letting it lapse mid horizon would model a product nobody sells."""
    fix = reschedule(MEMBER, start_week=4, installment_fraction=0.5)
    assert [due_multiplier([fix], MEMBER, w) for w in range(1, 7)] == [1.0, 1.0, 1.0, 0.5, 0.5, 0.5]
    assert due_multiplier([fix], MEMBER, DEFAULT.horizon_weeks) == 0.5


def test_no_interventions_leaves_every_installment_alone():
    assert due_multiplier([], MEMBER, 1) == 1.0
    assert due_multiplier(None, MEMBER, 1) == 1.0


def test_a_full_installment_reschedule_is_the_identity(kendra):
    """installment_fraction 1.0 changes nothing, and the run must be identical float for
    float. This is the sharpest available check that the engine really does route
    interventions through `due` alone: if it touched income, savings or willingness to
    cover, a no op fix would still shift the numbers."""
    draws = make_draws(kendra.n_members, DEFAULT, seed=0)
    identity = reschedule(MEMBER, start_week=1, installment_fraction=1.0)
    with_fix = simulate(kendra, [], [identity], DEFAULT, draws)
    without = simulate(kendra, [], [], DEFAULT, draws)
    assert with_fix.states == without.states
    assert with_fix.events == without.events


# ------------------------------------------------------------------------------------
# The observation window
# ------------------------------------------------------------------------------------


def test_a_moratorium_must_end_a_full_window_before_the_horizon():
    """The rule that stops a fix from "protecting" somebody by hiding her stress.

    A moratorium running to week 12 removes every payment she could have missed inside the
    chart; her arrears reappear in week 13, where nothing is measured. With horizon 12 and
    a 4 week window, the last deferred week may be 8 at the latest.
    """
    assert moratorium(MEMBER, start_week=5, weeks=4).last_active_week == 8
    assert moratorium(MEMBER, start_week=5, weeks=4).observable(DEFAULT)
    assert not moratorium(MEMBER, start_week=6, weeks=4).observable(DEFAULT)
    assert not moratorium(MEMBER, start_week=11, weeks=2).observable(DEFAULT)


def test_a_reschedule_counts_as_ending_the_week_it_starts():
    """It never lifts, but from start_week she is paying the new installment, so every later
    week is already observation. Judging it by its end would rule out every reschedule."""
    fix = reschedule(MEMBER, start_week=8, installment_fraction=0.5)
    assert fix.last_active_week == 8
    assert fix.observable(DEFAULT)
    assert not reschedule(MEMBER, start_week=9, installment_fraction=0.5).observable(DEFAULT)


# ------------------------------------------------------------------------------------
# Cost to the lender
# ------------------------------------------------------------------------------------


def test_moratorium_cost_is_each_deferred_installment_priced_to_the_horizon(kendra):
    """Hand computed, so the formula in params is the one the code actually uses.

    Installment 1200, weeks 1 and 2 deferred, horizon 12: the first rupee is 11 weeks late
    and the second 10, so the cost is 1200 x rate x (11 + 10).
    """
    installment = kendra.member(MEMBER).weekly_due
    assert installment == pytest.approx(1200.0)
    expected = installment * DEFAULT.carry_cost_rate * (11 + 10)
    assert moratorium(MEMBER, 1, 2).lender_cost(kendra, DEFAULT) == pytest.approx(expected)


def test_reschedule_cost_is_each_weekly_reduction_priced_to_the_horizon(kendra):
    installment = kendra.member(MEMBER).weekly_due
    reduction = installment * 0.5
    expected = reduction * DEFAULT.carry_cost_rate * sum(12 - w for w in range(1, 13))
    cost = reschedule(MEMBER, 1, 0.5).lender_cost(kendra, DEFAULT)
    assert cost == pytest.approx(expected)


def test_the_same_fix_granted_later_costs_the_lender_less(kendra):
    """Money deferred in week 1 is waited on for longer than money deferred in week 6. That
    ordering is the whole reason the ranking can prefer a smaller, later fix."""
    early = moratorium(MEMBER, 1, 2).lender_cost(kendra, DEFAULT)
    late = moratorium(MEMBER, 6, 2).lender_cost(kendra, DEFAULT)
    assert late < early


def test_a_no_op_reschedule_costs_nothing(kendra):
    assert reschedule(MEMBER, 1, 1.0).lender_cost(kendra, DEFAULT) == 0.0


# ------------------------------------------------------------------------------------
# Shape
# ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"type": "scheme_linkage", "member_id": MEMBER, "start_week": 1},
        {"type": MORATORIUM, "member_id": MEMBER, "start_week": 0, "weeks": 2},
        {"type": MORATORIUM, "member_id": MEMBER, "start_week": 1},
        {"type": MORATORIUM, "member_id": MEMBER, "start_week": 1, "weeks": 2,
         "installment_fraction": 0.5},
        {"type": RESCHEDULE, "member_id": MEMBER, "start_week": 1},
        {"type": RESCHEDULE, "member_id": MEMBER, "start_week": 1, "installment_fraction": 1.5},
        {"type": RESCHEDULE, "member_id": MEMBER, "start_week": 1,
         "installment_fraction": 0.5, "weeks": 2},
    ],
)
def test_a_malformed_intervention_is_refused_at_construction(kwargs):
    """Better a ValueError here than a silently ignored parameter in a replay the UI is
    about to present as evidence."""
    with pytest.raises(ValueError):
        Intervention(**kwargs)


def test_the_lighter_of_two_fixes_of_one_type_sorts_first():
    """Inside a type the key means what it says: fewer moratorium weeks, and a higher
    remaining installment, come first."""
    assert moratorium(MEMBER, 1, 2).burden_key < moratorium(MEMBER, 1, 4).burden_key
    assert reschedule(MEMBER, 1, 0.75).burden_key < reschedule(MEMBER, 1, 0.5).burden_key


def test_the_description_avoids_hyphens_and_dashes(kendra):
    """It appears on screen in the demo video."""
    for fix in (moratorium(MEMBER, 1, 2), reschedule(MEMBER, 1, 0.5)):
        text = fix.describe(kendra)
        assert kendra.member(MEMBER).name in text
        assert "-" not in text and "–" not in text and "—" not in text
