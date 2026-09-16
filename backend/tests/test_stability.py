"""Phase 3 stability: is the badge counting what it claims to count?

The badge is the most honest sentence in the prototype, so the tests are mostly about it not
cheating: not replaying the base world, not scoring a match it did not earn, and giving the
same number twice in a row.
"""

import numpy as np
import pytest

from sim.attribution import INDEPENDENT, INDEX, TRANSMITTED, attribute
from sim.engine import Shock, make_draws
from sim.params import DEFAULT, PERTURBABLE
from sim.stability import (
    PERTURB_RANGE,
    _matches,
    perturbed_params,
    stability,
)

from tests.conftest import build_scenario, make_member

SEED = 0
SHOCKED = "s000"


@pytest.fixture(scope="module")
def robust_case():
    """A member who loses nearly all her income for the whole horizon.

    (scenario, shocks, base_records). No perturbation inside plus or minus 30% can make this
    not a shock, and with no income trend anywhere there is no other cause in the world that
    could explain her, so INDEX is the only label available in every rerun. If THIS one ever
    wobbles, the badge is measuring something other than the label.
    """
    scenario = build_scenario([make_member(i, "kA", "tailoring", "Sahyog") for i in range(5)])
    shocks = [
        Shock(
            type="job_loss",
            start_week=1,
            member_id=SHOCKED,
            severity=0.95,
            duration_weeks=DEFAULT.horizon_weeks,
        )
    ]
    draws = make_draws(scenario.n_members, DEFAULT, seed=SEED)
    records = attribute(scenario, shocks, draws, DEFAULT)
    return scenario, shocks, records


def _index_record(records):
    return [r for r in records if r["label"] == INDEX]


# ------------------------------------------------------------------------------------
# The badge
# ------------------------------------------------------------------------------------


def test_a_trivially_robust_index_case_scores_every_run(robust_case):
    scenario, shocks, records = robust_case
    base = _index_record(records)
    assert [r["member_id"] for r in base] == [SHOCKED], "the fixture is meant to have one"

    result = stability(scenario, shocks, (), DEFAULT, base, seed=SEED)
    entry = result[0]
    assert entry["base_label"] == INDEX
    assert entry["base_source_id"] == SHOCKED
    assert entry["matched"] == 50
    assert entry["differed"] == 0
    assert entry["not_flagged"] == 0
    assert entry["badge_text"] == "stable in 50 of 50 runs"


def test_the_three_counts_partition_the_runs(robust_case):
    """matched, differed and not_flagged are a partition, which is what lets a reader treat
    "50 minus matched" as the whole of the doubt."""
    scenario, shocks, records = robust_case
    for entry in stability(scenario, shocks, (), DEFAULT, records, seed=SEED, n_runs=8):
        assert entry["matched"] + entry["differed"] + entry["not_flagged"] == 8
        assert entry["n_runs"] == 8


def test_the_badge_text_carries_no_hyphens_or_dashes(robust_case):
    """It is rendered on screen in the judged video."""
    scenario, shocks, records = robust_case
    for entry in stability(scenario, shocks, (), DEFAULT, records, seed=SEED, n_runs=5):
        assert entry["badge_text"] == f"stable in {entry['matched']} of 5 runs"
        for char in ("-", "–", "—"):
            assert char not in entry["badge_text"]


def test_one_entry_per_base_record_in_the_same_order(robust_case):
    """The UI zips these onto explanation cards it has already laid out, so the order has to
    be the order attribution returned."""
    scenario, shocks, records = robust_case
    result = stability(scenario, shocks, (), DEFAULT, records, seed=SEED, n_runs=3)
    assert [e["member_id"] for e in result] == [r["member_id"] for r in records]
    for entry, record in zip(result, records):
        assert entry["base_label"] == record["label"]
        assert entry["base_source_id"] == record["source_id"]
        assert set(entry) == {
            "member_id", "base_label", "base_source_id", "matched", "differed",
            "not_flagged", "n_runs", "badge_text",
        }


def test_a_small_number_of_runs_works(robust_case):
    """n_runs is a knob, not a constant. The demo may want 50 and a test may want 3."""
    scenario, shocks, records = robust_case
    base = _index_record(records)
    three = stability(scenario, shocks, (), DEFAULT, base, seed=SEED, n_runs=3)
    assert three[0]["matched"] == 3
    assert three[0]["n_runs"] == 3
    assert three[0]["badge_text"] == "stable in 3 of 3 runs"
    # And the first three runs of a 50 run check are the same three runs.
    fifty = stability(scenario, shocks, (), DEFAULT, base, seed=SEED, n_runs=50)
    assert fifty[0]["matched"] >= three[0]["matched"]


# ------------------------------------------------------------------------------------
# What counts as the same answer
# ------------------------------------------------------------------------------------


def test_a_transmitted_case_must_reproduce_its_source_too():
    """The sentence on screen names a neighbour. Naming a different one is not a match, even
    though the word TRANSMITTED is unchanged."""
    base = {"label": TRANSMITTED, "source_id": "s000"}
    assert _matches(base, {"label": TRANSMITTED, "source_id": "s000"})
    assert not _matches(base, {"label": TRANSMITTED, "source_id": "s002"})
    assert not _matches(base, {"label": INDEX, "source_id": "s001"})


def test_an_index_or_independent_case_is_matched_on_its_label(robust_case):
    """Their source is their own id by construction, so there is nothing else to compare."""
    for label in (INDEX, INDEPENDENT):
        base = {"label": label, "source_id": "s000"}
        assert _matches(base, {"label": label, "source_id": "s000"})
        assert not _matches(base, {"label": TRANSMITTED, "source_id": "s001"})


# ------------------------------------------------------------------------------------
# The two sources of doubt
# ------------------------------------------------------------------------------------


def test_every_perturbable_field_moves_and_nothing_else_does():
    rng = np.random.default_rng(1)
    perturbed = perturbed_params(DEFAULT, rng)

    for name in PERTURBABLE:
        base_value, new_value = getattr(DEFAULT, name), getattr(perturbed, name)
        assert new_value != base_value, name
        assert PERTURB_RANGE[0] <= new_value / base_value <= PERTURB_RANGE[1], name

    # Regulatory caps are not uncertain quantities, and the horizon is an array shape.
    for name in ("max_lenders_per_borrower", "max_total_exposure_rs",
                 "max_installment_share", "horizon_weeks", "declining_trend"):
        assert getattr(perturbed, name) == getattr(DEFAULT, name), name


def test_the_base_runs_draws_are_never_reused(robust_case, monkeypatch):
    """A rerun that silently replayed the base world would score itself a free match.

    Run k draws with seed + k + 1, so the base seed never comes back around.
    """
    import sim.stability as stability_module

    seeds = []
    real = stability_module.make_draws

    def spy(n_members, params, seed):
        seeds.append(seed)
        return real(n_members, params, seed)

    monkeypatch.setattr(stability_module, "make_draws", spy)

    scenario, shocks, records = robust_case
    stability(scenario, shocks, (), DEFAULT, records, seed=SEED, n_runs=5)

    assert seeds == [SEED + 1, SEED + 2, SEED + 3, SEED + 4, SEED + 5]
    assert SEED not in seeds
    assert len(set(seeds)) == len(seeds), "two runs shared one dice roll"


def test_each_run_varies_both_the_parameters_and_the_dice(robust_case, monkeypatch):
    """Varying only the settings would answer "is this robust to our choices" and varying
    only the dice "is it robust to luck". An officer is exposed to both at once."""
    import sim.stability as stability_module

    seen = []
    real = stability_module.attribute

    def spy(scenario, shocks, draws, params, as_of_week=None, interventions=()):
        seen.append((params, draws))
        return real(scenario, shocks, draws, params, as_of_week, interventions)

    monkeypatch.setattr(stability_module, "attribute", spy)

    scenario, shocks, records = robust_case
    stability(scenario, shocks, (), DEFAULT, records, seed=SEED, n_runs=4)

    assert len(seen) == 4, "one attribution per run, not one per member"
    assert len({id(draws) for _, draws in seen}) == 4
    assert len({tuple(getattr(p, n) for n in PERTURBABLE) for p, _ in seen}) == 4
    # And inside a run the params reaching attribution are that run's perturbed set, not
    # the originals: attribution then hands them to every counterfactual it builds.
    assert all(p.amber != DEFAULT.amber for p, _ in seen)


# ------------------------------------------------------------------------------------
# Determinism
# ------------------------------------------------------------------------------------


def test_stability_is_deterministic(robust_case):
    """A badge that changed between two runs of the same command would be unusable: the
    number is going on a slide."""
    scenario, shocks, records = robust_case
    first = stability(scenario, shocks, (), DEFAULT, records, seed=SEED, n_runs=6)
    second = stability(scenario, shocks, (), DEFAULT, records, seed=SEED, n_runs=6)
    assert first == second


def test_a_different_seed_is_a_different_experiment(robust_case):
    """Same procedure, different reruns. The INDEX case still survives all of them, which is
    what makes it a robust case rather than a lucky one."""
    scenario, shocks, records = robust_case
    base = _index_record(records)
    assert (
        stability(scenario, shocks, (), DEFAULT, base, seed=SEED, n_runs=10)[0]["matched"]
        == stability(scenario, shocks, (), DEFAULT, base, seed=SEED + 99, n_runs=10)[0]["matched"]
        == 10
    )


def test_stability_does_not_mutate_the_records_it_is_given(robust_case):
    scenario, shocks, records = robust_case
    before = [dict(r) for r in records]
    stability(scenario, shocks, (), DEFAULT, records, seed=SEED, n_runs=3)
    assert [dict(r) for r in records] == before
