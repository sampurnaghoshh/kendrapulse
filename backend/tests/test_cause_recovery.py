"""Phase 4 cause recovery: is the validation itself trustworthy?

A validation report is the one artefact nobody double checks, so these tests are about the
check not cheating. The baseline must never touch the simulation, the outcome categories must
account for every observed member, and the whole thing has to be reproducible from its seeds.
"""

import json

import pytest

from sim.attribution import INDEPENDENT, INDEX, TRANSMITTED
from sim.engine import Shock, make_draws, simulate
from sim.generator import generate_scenario
from sim.params import DEFAULT, PERTURBABLE
from validation.cause_recovery import (
    CORRECT,
    ENGINE_SEED_OFFSET,
    INCOME_NOISE,
    OUTCOMES,
    PARAM_NOISE,
    UNEXPLAINED,
    WRONG_LABEL,
    WRONG_SOURCE,
    baseline_labels,
    build_report,
    classify,
    noisy_scenario,
    perturbed_params,
    plant_shocks,
    run_scenario,
)

import numpy as np

DASHES = ("-", "–", "—")


@pytest.fixture(scope="module")
def small_report():
    return build_report(n_scenarios=5)


# ------------------------------------------------------------------------------------
# The two properties everything else rests on
# ------------------------------------------------------------------------------------


def test_the_report_is_deterministic(small_report):
    """Every seed is derived from the scenario index, so the same command gives the same
    report. A failure example that cannot be reproduced from its seed is not evidence."""
    again = build_report(n_scenarios=5)
    assert small_report == again


def test_the_report_is_json_serialisable(small_report):
    encoded = json.dumps(small_report)
    assert json.loads(encoded)["totals"] == small_report["totals"]


def test_the_outcome_counts_account_for_every_observed_flagged_member(small_report):
    """The four categories are a partition. If they were not, an accuracy computed from them
    would be dividing by the wrong denominator."""
    observed = small_report["totals"]["observed_flagged_members"]
    for which in ("engine", "baseline"):
        counts = small_report["totals"][which]["counts"]
        assert set(counts) == set(OUTCOMES)
        assert sum(counts.values()) == observed
        assert small_report["totals"][which]["n_observed"] == observed

    # And per label, the same sum split across the true labels.
    for which in ("engine", "baseline"):
        per_label = small_report["per_true_label"][which]
        assert sum(block["n"] for block in per_label.values()) == observed
        for block in per_label.values():
            assert sum(block["counts"].values()) == block["n"]


def test_the_outcome_counts_match_the_rows_they_came_from():
    """The report's totals are recomputed here from the raw rows, so a bug in the tallying
    cannot hide behind numbers that merely look plausible."""
    rows = []
    for k in range(5):
        result = run_scenario(k)
        if result is not None:
            rows.extend(result["rows"])

    report = build_report(n_scenarios=5)
    assert report["totals"]["observed_flagged_members"] == len(rows)
    for which in ("engine", "baseline"):
        for outcome in OUTCOMES:
            expected = sum(1 for row in rows if row[f"{which}_outcome"] == outcome)
            assert report["totals"][which]["counts"][outcome] == expected, (which, outcome)


def test_the_two_accuracies_mean_what_they_say(small_report):
    """accuracy_when_explained judges the logic; overall_accuracy judges the deployed system
    and counts unexplained as not correct. The second can never exceed the first."""
    for which in ("engine", "baseline"):
        block = small_report["totals"][which]
        counts = block["counts"]
        explained = counts[CORRECT] + counts[WRONG_SOURCE] + counts[WRONG_LABEL]
        assert block["n_explained"] == explained
        if explained:
            assert block["accuracy_when_explained"] == pytest.approx(counts[CORRECT] / explained)
        assert block["overall_accuracy"] == pytest.approx(
            counts[CORRECT] / block["n_observed"]
        )
        assert block["overall_accuracy"] <= block["accuracy_when_explained"] + 1e-12


# ------------------------------------------------------------------------------------
# The baseline must not be allowed to cheat
# ------------------------------------------------------------------------------------


def test_the_baseline_never_simulates(monkeypatch):
    """The whole value of the baseline is that it is what an analyst could do WITHOUT the
    model. A baseline that quietly ran a simulation would make the comparison meaningless and
    would flatter whichever side happened to win.
    """
    import validation.cause_recovery as module

    def refuse(*args, **kwargs):
        raise AssertionError("the baseline rule called simulate, which defeats its purpose")

    scenario = generate_scenario(seed=3)
    shocks = plant_shocks(scenario, np.random.default_rng(3))
    draws = make_draws(scenario.n_members, DEFAULT, seed=3)
    truth_run = simulate(scenario, shocks, [], DEFAULT, draws)
    observed = [m.id for m in scenario.members if truth_run.flagged(m.id)]

    monkeypatch.setattr(module, "simulate", refuse)
    labels = baseline_labels(scenario, shocks, truth_run, observed)

    assert set(labels) == set(observed)
    assert all(entry["label"] in (INDEX, TRANSMITTED, INDEPENDENT) for entry in labels.values())


def test_the_baseline_rule_is_the_one_we_documented():
    """Shocked means INDEX. Otherwise, gave cover means TRANSMITTED from whoever she covered
    most. Otherwise INDEPENDENT. Stated on a hand built log so the rule is unambiguous."""
    scenario = generate_scenario(seed=3)
    shocked_id = scenario.members[0].id
    giver_id = scenario.members[1].id
    quiet_id = scenario.members[2].id
    shocks = (Shock(type="health", start_week=1, member_id=shocked_id),)

    class FakeRun:
        events = [
            {"week": 2, "channel": "guarantee", "from_id": giver_id, "to_id": shocked_id,
             "amount": 100.0},
            # A bigger total to somebody else, so "covered most" is doing real work.
            {"week": 3, "channel": "guarantee", "from_id": giver_id, "to_id": quiet_id,
             "amount": 400.0},
            # A non guarantee event must be ignored: it is not cover.
            {"week": 4, "channel": "shared_lender", "from_id": quiet_id, "to_id": giver_id,
             "amount": 900.0},
        ]

    labels = baseline_labels(
        scenario, shocks, FakeRun(), [shocked_id, giver_id, quiet_id]
    )
    assert labels[shocked_id] == {"label": INDEX, "source_id": shocked_id}
    assert labels[giver_id] == {"label": TRANSMITTED, "source_id": quiet_id}
    assert labels[quiet_id] == {"label": INDEPENDENT, "source_id": quiet_id}


def test_the_baseline_is_never_unexplained(small_report):
    """It always has an answer, which is exactly what makes it a fair bar and also what makes
    it wrong more often than the engine when it is wrong at all."""
    assert small_report["totals"]["baseline"]["counts"][UNEXPLAINED] == 0
    assert small_report["failure_examples"]["baseline"][UNEXPLAINED] == []


# ------------------------------------------------------------------------------------
# What the engine under test is denied
# ------------------------------------------------------------------------------------


def test_the_engine_gets_different_dice_from_the_truth():
    """Sharing a dice roll with truth would hand the engine the one thing a deployment can
    never have."""
    assert ENGINE_SEED_OFFSET >= 1000
    truth = make_draws(25, DEFAULT, seed=7)
    engine = make_draws(25, DEFAULT, seed=7 + ENGINE_SEED_OFFSET)
    assert not np.array_equal(truth, engine)


def test_noise_disturbs_incomes_and_trends_but_not_the_network():
    """Only the numbers a lender would have to estimate. If the roster order changed, every
    member would silently inherit somebody else's row in the draws array."""
    scenario = generate_scenario(seed=5)
    noisy = noisy_scenario(scenario, np.random.default_rng(5))

    assert noisy.index_of == scenario.index_of
    assert [m.id for m in noisy.members] == [m.id for m in scenario.members]
    assert noisy.graph is scenario.graph
    assert noisy.layout == scenario.layout

    for before, after in zip(scenario.members, noisy.members):
        assert after.weekly_income != before.weekly_income
        ratio = after.weekly_income / before.weekly_income
        assert 1 - INCOME_NOISE <= ratio <= 1 + INCOME_NOISE
        if before.income_trend != 0:
            trend_ratio = after.income_trend / before.income_trend
            assert 1 - INCOME_NOISE <= trend_ratio <= 1 + INCOME_NOISE
        # Her loans are untouched: a lender knows its own installment exactly.
        assert after.loans == before.loans


def test_parameter_noise_stays_inside_its_stated_band():
    perturbed = perturbed_params(DEFAULT, np.random.default_rng(2))
    for name in PERTURBABLE:
        ratio = getattr(perturbed, name) / getattr(DEFAULT, name)
        assert PARAM_NOISE[0] <= ratio <= PARAM_NOISE[1], name
    # Regulatory caps are not uncertain quantities.
    assert perturbed.max_installment_share == DEFAULT.max_installment_share
    assert perturbed.horizon_weeks == DEFAULT.horizon_weeks


def test_planted_shocks_stay_inside_their_stated_ranges():
    scenario = generate_scenario(seed=11)
    for seed in range(20):
        shocks = plant_shocks(scenario, np.random.default_rng(seed))
        assert 1 <= len(shocks) <= 3
        member_ids = [s.member_id for s in shocks]
        assert len(set(member_ids)) == len(member_ids), "a member carries at most one shock"
        for shock in shocks:
            assert 1 <= shock.start_week <= 6
            assert shock.member_id in {m.id for m in scenario.members}


# ------------------------------------------------------------------------------------
# The outcome rule
# ------------------------------------------------------------------------------------


def test_classify_separates_a_wrong_neighbour_from_a_wrong_label():
    truth = {"member_id": "m001", "label": TRANSMITTED, "source_id": "m002"}
    flagged = {"m001"}
    assert classify(truth, {"label": TRANSMITTED, "source_id": "m002"}, flagged) == CORRECT
    assert classify(truth, {"label": TRANSMITTED, "source_id": "m003"}, flagged) == WRONG_SOURCE
    assert classify(truth, {"label": INDEPENDENT, "source_id": "m001"}, flagged) == WRONG_LABEL


def test_a_member_the_engines_own_world_never_flags_is_unexplained():
    """A real failure mode of a deployed system: it is handed a person it never saw in
    trouble, so whatever it says about her is an artefact of being asked. Counted apart from
    getting the answer wrong, because the fix is different."""
    truth = {"member_id": "m001", "label": TRANSMITTED, "source_id": "m002"}
    assert classify(truth, None, set()) == UNEXPLAINED
    # Even a correct looking guess does not count if her own world never flagged her.
    assert classify(truth, {"label": TRANSMITTED, "source_id": "m002"}, set()) == UNEXPLAINED


def test_an_index_case_is_matched_on_its_label_alone():
    """Her source is her own id by construction, so there is nothing else to compare."""
    truth = {"member_id": "m001", "label": INDEX, "source_id": "m001"}
    assert classify(truth, {"label": INDEX, "source_id": "m001"}, {"m001"}) == CORRECT


# ------------------------------------------------------------------------------------
# Shape of the report
# ------------------------------------------------------------------------------------


def test_the_report_says_what_it_is_not(small_report):
    """Somebody will quote a number from this file out of context. The disclaimer travels
    with the numbers rather than living only in a README."""
    text = small_report["what_this_is"].lower()
    assert "not" in text and "real borrowers" in text


def test_the_config_records_everything_needed_to_reproduce_it(small_report):
    config = small_report["config"]
    assert config["n_scenarios"] == 5
    assert config["param_noise"] == list(PARAM_NOISE)
    assert config["income_noise"] == INCOME_NOISE
    assert config["engine_seed_offset"] == ENGINE_SEED_OFFSET
    assert config["git_commit"]
    assert (
        config["scenarios_scored"] + config["scenarios_skipped_nobody_flagged"]
        == config["n_scenarios"]
    )


def test_the_confusion_matrix_has_a_column_for_unexplained(small_report):
    """A silently dropped row would make the matrix disagree with the totals."""
    matrix = small_report["confusion_truth_by_engine"]
    assert set(matrix) == {INDEX, TRANSMITTED, INDEPENDENT}
    for row in matrix.values():
        assert set(row) == {INDEX, TRANSMITTED, INDEPENDENT, UNEXPLAINED}
    total = sum(count for row in matrix.values() for count in row.values())
    assert total == small_report["totals"]["observed_flagged_members"]


def test_failure_examples_are_capped_and_carry_their_seed(small_report):
    for which in ("engine", "baseline"):
        for outcome, examples in small_report["failure_examples"][which].items():
            assert len(examples) <= 5, outcome
            for entry in examples:
                assert isinstance(entry["generator_seed"], int)
                assert entry["member_id"].startswith("m")
                assert entry["truth_label"] in (INDEX, TRANSMITTED, INDEPENDENT)


def test_hard_and_clean_cases_partition_the_members(small_report):
    hard, clean = small_report["hard_cases"], small_report["clean_cases"]
    assert hard["n_members"] + clean["n_members"] == (
        small_report["totals"]["observed_flagged_members"]
    )
    assert "within 2 weeks" in hard["definition"]


def test_no_human_readable_string_in_the_report_has_a_hyphen_or_dash(small_report):
    """The report is shown in the UI as a ValidationReport panel."""
    prose = [small_report["what_this_is"], small_report["hard_cases"]["definition"],
             small_report["clean_cases"]["definition"]]
    prose += [
        entry["note"]
        for which in ("engine", "baseline")
        for examples in small_report["failure_examples"][which].values()
        for entry in examples
    ]
    for sentence in prose:
        for dash in DASHES:
            assert dash not in sentence, sentence
