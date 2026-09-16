"""Can the attribution procedure recover a planted cause when it cannot see the truth?

WHAT THIS TESTS, AND WHAT IT DOES NOT
-------------------------------------
This tests the LOGIC of the procedure. It is not accuracy on real borrowers, and no number it
produces is a claim about real borrowers. There is no dataset of Indian microfinance
households with labelled contagion, which is exactly why the procedure has to be defensible on
its own terms instead.

The question it answers is narrow and worth answering: if stress really did spread the way we
model it, and a deployed system could not see the hidden numbers, would the procedure still
name the right cause?

THE THREE PARTIES
-----------------
TRUTH knows everything. True parameters, true incomes, true dice. It runs the world, and the
members flagged in that run are the OBSERVED FLAGGED SET: the people a field officer would
actually be looking at. Its labels, produced with full knowledge, are the ground truth.

The ENGINE UNDER TEST sees what a deployment sees: the same roster, graph, planted shocks and
event log, but perturbed parameters (U(0.8, 1.2)), member incomes and trends carrying 15%
multiplicative noise, and a DIFFERENT dice seed. It is asked to explain the observed flagged
set, which is not the set its own world would have flagged. That mismatch is the point: a real
officer brings you a list of people who are in trouble, not a list your model predicted.

The BASELINE is what a sensible analyst would do with a spreadsheet and no simulation at all:
if she has a shock, call it INDEX; else if the event log shows her covering somebody, call it
TRANSMITTED from whoever she covered most; else INDEPENDENT. It is not a straw man. It is a
genuinely reasonable rule, and it is the bar the simulation has to clear to be worth its
complexity. A test monkeypatches `simulate` to raise inside it, so it can never quietly cheat.

WHY NOISE ON INCOME MATTERS MOST
--------------------------------
Perturbed parameters test robustness to our modelling choices. But a lender genuinely does not
know a borrower's weekly income to the rupee, and `income_trend` is not observable at all: it
is inferred from a few months of collection records at best. Putting 15% noise on both is the
harshest and most realistic part of this check, because the trend is one half of what counts
as a cause.
"""

import subprocess
from dataclasses import replace

import numpy as np

from sim.attribution import INDEPENDENT, INDEX, TRANSMITTED, attribute, expand_shocks
from sim.engine import Shock, make_draws, simulate
from sim.generator import generate_scenario
from sim.params import DEFAULT, PERTURBABLE

# Outcomes, per observed flagged member.
CORRECT = "correct"
WRONG_SOURCE = "wrong_source"  # right that it was transmitted, named the wrong neighbour
WRONG_LABEL = "wrong_label"
UNEXPLAINED = "unexplained"  # the engine's own world never flags her, so it cannot explain her
OUTCOMES = (CORRECT, WRONG_SOURCE, WRONG_LABEL, UNEXPLAINED)

LABELS = (INDEX, TRANSMITTED, INDEPENDENT)

# What the engine under test is denied. Narrower than stability's U(0.7, 1.3) on purpose:
# stability asks "is this label robust to our settings", and this asks "could a deployment
# that mis-specified the model by a fifth still work". Both numbers live in their own module
# so neither can be widened to flatter the other.
PARAM_NOISE = (0.8, 1.2)
INCOME_NOISE = 0.15  # multiplicative, on weekly_income AND income_trend
ENGINE_SEED_OFFSET = 10_000  # so no engine run can ever share a dice roll with truth

SHOCK_TYPES = ("health", "crop_loss", "job_loss", "festival_spend")
MAX_SHOCKS = 3
MAX_START_WEEK = 6

# Two shocks landing within this many weeks of each other are hard for ANY procedure to
# separate, and the report tags those scenarios rather than burying them in the average.
SIMULTANEOUS_WEEKS = 2


# ---------------------------------------------------------------------------------------
# One scenario
# ---------------------------------------------------------------------------------------


def plant_shocks(scenario, rng):
    """1 to 3 shocks on random members, random types, starting in weeks 1 to 6.

    Members are drawn without replacement so a member never carries two shocks. Two shocks on
    one person would make "her own shock" ambiguous in a way the procedure has a documented
    answer for already (it removes them together), and this check is about spread between
    people.
    """
    n_shocks = int(rng.integers(1, MAX_SHOCKS + 1))
    member_idxs = rng.choice(scenario.n_members, size=n_shocks, replace=False)
    return tuple(
        Shock(
            type=SHOCK_TYPES[int(rng.integers(0, len(SHOCK_TYPES)))],
            start_week=int(rng.integers(1, MAX_START_WEEK + 1)),
            member_id=scenario.members[int(idx)].id,
        )
        for idx in member_idxs
    )


def noisy_scenario(scenario, rng, noise=INCOME_NOISE):
    """The roster as a deployment would see it: incomes and trends off by up to 15%.

    The graph, the layout and `index_of` are untouched, so every member keeps her row in the
    draws array and her place in the network. Only the numbers a lender would have to estimate
    are disturbed.
    """
    members = tuple(
        replace(
            m,
            weekly_income=m.weekly_income * float(rng.uniform(1 - noise, 1 + noise)),
            income_trend=m.income_trend * float(rng.uniform(1 - noise, 1 + noise)),
        )
        for m in scenario.members
    )
    return replace(scenario, members=members)


def perturbed_params(params, rng, noise=PARAM_NOISE):
    """Every PERTURBABLE field multiplied by its own U(0.8, 1.2) draw."""
    return replace(
        params,
        **{name: getattr(params, name) * rng.uniform(*noise) for name in PERTURBABLE},
    )


def baseline_labels(scenario, shocks, truth_run, observed):
    """The no simulation rule. Observable data only: the planted shocks and the event log.

    This function must never call `simulate`, and a test enforces that by monkeypatching it to
    raise. The whole value of the baseline is that it is what you can do WITHOUT the model, so
    a baseline that quietly ran the model would make the comparison meaningless.
    """
    shocked = {s.member_id for s in expand_shocks(scenario, shocks)}

    # Who did she cover, and for how much, according to the log. The member she gave the most
    # to is the best guess a spreadsheet can make about where her trouble came from.
    given = {member_id: {} for member_id in observed}
    for event in truth_run.events:
        if event["channel"] != "guarantee" or event["from_id"] not in given:
            continue
        totals = given[event["from_id"]]
        totals[event["to_id"]] = totals.get(event["to_id"], 0.0) + event["amount"]

    out = {}
    for member_id in observed:
        if member_id in shocked:
            out[member_id] = {"label": INDEX, "source_id": member_id}
            continue
        covered = given[member_id]
        if covered:
            # Largest amount wins; member id breaks a tie so the rule is deterministic.
            source_id = max(sorted(covered), key=lambda mid: covered[mid])
            out[member_id] = {"label": TRANSMITTED, "source_id": source_id}
            continue
        out[member_id] = {"label": INDEPENDENT, "source_id": member_id}
    return out


def classify(truth_record, guess, engine_flagged=None):
    """One observed flagged member, one outcome.

    `engine_flagged` is the set the engine's OWN world flagged. A member outside it is
    `unexplained`: the engine was handed a person its world never saw in trouble, so whatever
    it says about her is an artefact of being asked. That is a real failure mode of a deployed
    system and it is counted as one, but it is counted apart from getting the answer wrong,
    because the fix for it is different.
    """
    if engine_flagged is not None and truth_record["member_id"] not in engine_flagged:
        return UNEXPLAINED
    if guess is None:
        return UNEXPLAINED
    if guess["label"] != truth_record["label"]:
        return WRONG_LABEL
    if truth_record["label"] == TRANSMITTED and guess["source_id"] != truth_record["source_id"]:
        return WRONG_SOURCE
    return CORRECT


def run_scenario(k, base_seed=0, params=DEFAULT, n_kendras=5, members_per_kendra=5):
    """One scenario end to end. Returns per member rows for the engine and the baseline.

    Every seed is derived from `k`, so scenario k is the same scenario on every machine and a
    failure example in the report can be reproduced from its seed alone.
    """
    generator_seed = base_seed + k
    scenario = generate_scenario(
        n_kendras=n_kendras,
        members_per_kendra=members_per_kendra,
        seed=generator_seed,
        params=params,
    )

    plant_rng = np.random.default_rng(generator_seed * 7 + 1)
    shocks = plant_shocks(scenario, plant_rng)

    # ---- TRUTH: true params, true incomes, true dice ---------------------------------
    truth_draws = make_draws(scenario.n_members, params, seed=generator_seed)
    truth_run = simulate(scenario, shocks, [], params, truth_draws)
    observed = [m.id for m in scenario.members if truth_run.flagged(m.id)]
    if not observed:
        return None  # nobody flagged, so there is nothing to explain and nothing to score

    truth_records = {r["member_id"]: r for r in attribute(scenario, shocks, truth_draws, params)}

    # ---- ENGINE UNDER TEST: perturbed params, noisy roster, different dice ------------
    noise_rng = np.random.default_rng(generator_seed * 13 + 3)
    engine_params = perturbed_params(params, noise_rng)
    engine_scenario = noisy_scenario(scenario, noise_rng)
    engine_draws = make_draws(
        scenario.n_members, engine_params, seed=generator_seed + ENGINE_SEED_OFFSET
    )
    engine_records = {
        r["member_id"]: r
        for r in attribute(engine_scenario, shocks, engine_draws, engine_params)
    }
    engine_flagged = set(engine_records)

    # ---- BASELINE: the event log and the shock list, no simulation --------------------
    baseline = baseline_labels(scenario, shocks, truth_run, observed)

    starts = sorted(s.start_week for s in shocks)
    near_simultaneous = any(
        b - a <= SIMULTANEOUS_WEEKS for a, b in zip(starts, starts[1:])
    )

    rows = []
    for member_id in observed:
        truth_record = truth_records[member_id]
        rows.append({
            "scenario": k,
            "generator_seed": generator_seed,
            "member_id": member_id,
            "truth_label": truth_record["label"],
            "truth_source_id": truth_record["source_id"],
            "engine_label": engine_records.get(member_id, {}).get("label"),
            "engine_source_id": engine_records.get(member_id, {}).get("source_id"),
            "engine_outcome": classify(
                truth_record, engine_records.get(member_id), engine_flagged
            ),
            "baseline_label": baseline[member_id]["label"],
            "baseline_source_id": baseline[member_id]["source_id"],
            # The baseline is never asked to simulate, so it can never be `unexplained`: it
            # always has an answer, which is part of what makes it a fair bar and part of
            # what makes it wrong more often.
            "baseline_outcome": classify(truth_record, baseline[member_id]),
            "n_shocks": len(shocks),
            "near_simultaneous_shocks": near_simultaneous,
        })
    return {"rows": rows, "n_shocks": len(shocks), "near_simultaneous": near_simultaneous}


# ---------------------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------------------


def _git_commit():
    """The commit the report was produced from, so a number can be traced to a codebase."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def _tally(rows, which):
    counts = {outcome: 0 for outcome in OUTCOMES}
    for row in rows:
        counts[row[f"{which}_outcome"]] += 1
    return counts


def _rates(counts):
    """Two accuracies, because they answer two different questions.

    accuracy_when_explained is "when the procedure had an opinion, was it right". It is the
    number that judges the LOGIC, which is what this file exists to test.

    overall_accuracy counts `unexplained` as not correct. It is the number that judges the
    procedure as a DEPLOYED SYSTEM, where being unable to explain the person in front of you
    is a failure whatever the reason.

    Reporting only the first would be flattering and reporting only the second would blame the
    logic for a coverage problem, so both are reported side by side.
    """
    explained = counts[CORRECT] + counts[WRONG_SOURCE] + counts[WRONG_LABEL]
    total = explained + counts[UNEXPLAINED]
    return {
        "accuracy_when_explained": counts[CORRECT] / explained if explained else None,
        "overall_accuracy": counts[CORRECT] / total if total else None,
        "n_explained": explained,
        "n_observed": total,
    }


def _block(rows, which):
    counts = _tally(rows, which)
    return {"counts": counts, **_rates(counts)}


def _per_label(rows, which):
    out = {}
    for label in LABELS:
        subset = [row for row in rows if row["truth_label"] == label]
        out[label] = {"n": len(subset), **_block(subset, which)}
    return out


def _confusion(rows):
    """truth label x engine label. `unexplained` gets its own column, not a silent drop."""
    matrix = {
        truth: {guess: 0 for guess in (*LABELS, UNEXPLAINED)} for truth in LABELS
    }
    for row in rows:
        guess = (
            UNEXPLAINED if row["engine_outcome"] == UNEXPLAINED else row["engine_label"]
        )
        matrix[row["truth_label"]][guess] += 1
    return matrix


def _failures(rows, which, limit=5):
    """Up to `limit` worked examples per outcome, each reproducible from its seed."""
    out = {}
    for outcome in OUTCOMES:
        examples = []
        for row in rows:
            if row[f"{which}_outcome"] != outcome or len(examples) >= limit:
                continue
            examples.append({
                "generator_seed": row["generator_seed"],
                "member_id": row["member_id"],
                "truth_label": row["truth_label"],
                "truth_source_id": row["truth_source_id"],
                f"{which}_label": row[f"{which}_label"],
                f"{which}_source_id": row[f"{which}_source_id"],
                "n_shocks": row["n_shocks"],
                "near_simultaneous_shocks": row["near_simultaneous_shocks"],
                "note": (
                    "two or more shocks started within "
                    f"{SIMULTANEOUS_WEEKS} weeks of each other, which is hard for any "
                    "procedure to separate"
                    if row["near_simultaneous_shocks"]
                    else ""
                ),
            })
        out[outcome] = examples
    return out


def build_report(n_scenarios=500, base_seed=0, params=DEFAULT, progress=None):
    """Run `n_scenarios` and return the whole report as a plain dict.

    `progress(k, n, n_rows)` is called as scenarios complete, so a script can show it without
    this module knowing anything about printing.
    """
    rows = []
    skipped = 0
    n_shock_counts = {1: 0, 2: 0, 3: 0}
    near_simultaneous_scenarios = 0

    for k in range(n_scenarios):
        result = run_scenario(k, base_seed=base_seed, params=params)
        if result is None:
            skipped += 1
        else:
            rows.extend(result["rows"])
            n_shock_counts[result["n_shocks"]] += 1
            near_simultaneous_scenarios += int(result["near_simultaneous"])
        if progress is not None:
            progress(k + 1, n_scenarios, len(rows))

    hard = [row for row in rows if row["near_simultaneous_shocks"]]
    easy = [row for row in rows if not row["near_simultaneous_shocks"]]

    return {
        "what_this_is": (
            "A test of the attribution LOGIC, not of accuracy on real borrowers. It asks "
            "whether the procedure recovers a planted cause when it is denied the true "
            "parameters, the true incomes and the true dice. No number here is a claim "
            "about any real household."
        ),
        "config": {
            "n_scenarios": n_scenarios,
            "scenarios_scored": n_scenarios - skipped,
            "scenarios_skipped_nobody_flagged": skipped,
            "base_seed": base_seed,
            "generator_seeds": f"{base_seed} to {base_seed + n_scenarios - 1}",
            "engine_seed_offset": ENGINE_SEED_OFFSET,
            "param_noise": list(PARAM_NOISE),
            "income_noise": INCOME_NOISE,
            "trend_noise": INCOME_NOISE,
            "shocks_per_scenario": f"1 to {MAX_SHOCKS}",
            "shock_start_weeks": f"1 to {MAX_START_WEEK}",
            "shock_types": list(SHOCK_TYPES),
            "kendras": 5,
            "members_per_kendra": 5,
            "git_commit": _git_commit(),
            "shock_count_mix": {str(k): v for k, v in n_shock_counts.items()},
            "scenarios_with_near_simultaneous_shocks": near_simultaneous_scenarios,
        },
        "totals": {
            "observed_flagged_members": len(rows),
            "engine": _block(rows, "engine"),
            "baseline": _block(rows, "baseline"),
        },
        "per_true_label": {
            "engine": _per_label(rows, "engine"),
            "baseline": _per_label(rows, "baseline"),
        },
        "confusion_truth_by_engine": _confusion(rows),
        "hard_cases": {
            "definition": (
                "scenarios where two or more shocks started within "
                f"{SIMULTANEOUS_WEEKS} weeks of each other"
            ),
            "n_members": len(hard),
            "engine": _block(hard, "engine") if hard else None,
            "baseline": _block(hard, "baseline") if hard else None,
        },
        "clean_cases": {
            "definition": "every other scenario",
            "n_members": len(easy),
            "engine": _block(easy, "engine") if easy else None,
            "baseline": _block(easy, "baseline") if easy else None,
        },
        "failure_examples": {
            "engine": _failures(rows, "engine"),
            "baseline": _failures(rows, "baseline"),
        },
    }
