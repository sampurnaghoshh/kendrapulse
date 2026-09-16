"""How much of a label is the model, and how much is the settings we chose?

Every number in `params.py` is either a regulation or a judgement call. The judgement calls
could reasonably have been 30% different. So before a label goes on screen we rerun the whole
attribution 50 times, each time with every perturbable parameter multiplied by U(0.7, 1.3)
AND a fresh dice roll, and report how often the same answer comes back:

    "stable in 46 of 50 runs"

That sentence is the most honest thing in the prototype. A label that survives 46 reruns is
a finding. A label that survives 20 is a coin flip we should not be showing an officer, and
the badge says so in the same words either way, which is the point: the number is reported
whether it flatters us or not.

WHAT IS PERTURBED, AND WHAT IS NOT
----------------------------------
`params.PERTURBABLE` only. Regulatory caps (the MFIN exposure limit, the RBI 50% rule) are
not uncertain quantities and are never touched. Neither is the generator shape: perturbing
that would change who the borrowers ARE, which is a different question from how confident we
are about the physics acting on them.

TWO SOURCES OF DOUBT, VARIED TOGETHER
-------------------------------------
Each run k gets new parameters AND a new `draws` array. Varying only the parameters would
answer "is this label robust to our settings", and varying only the dice would answer "is it
robust to luck". An officer is exposed to both at once, so a run varies both at once.

But INSIDE run k, the actual world and every counterfactual share that one draws array. That
is the same common random numbers rule the labels rest on, applied one level up: if a
counterfactual inside a run got its own dice, the label produced in that run would be noise
and the badge would be counting noise.

THE BASE RUN'S DICE ARE NEVER REUSED
------------------------------------
Run k draws with `seed + k + 1`, so k = 0 uses `seed + 1` and the base run's own `seed` never
reappears. A rerun that silently replayed the base world would score itself a free match and
inflate every badge in the demo.
"""

from dataclasses import replace

import numpy as np

from sim.attribution import TRANSMITTED, attribute
from sim.engine import make_draws
from sim.params import DEFAULT, PERTURBABLE

N_RUNS = 50

# REASON: plus or minus 30%. Wide enough that a label surviving it has survived something
# real, narrow enough that the simulation is still recognisably the one we calibrated. It
# lives here rather than in params.py because it is a property of the ROBUSTNESS CHECK, not
# of the world being checked, and stability must never perturb its own perturbation.
PERTURB_RANGE = (0.7, 1.3)


def perturbed_params(params, rng):
    """Every PERTURBABLE field multiplied by its own U(0.7, 1.3) draw.

    Each field gets an independent factor, drawn in the fixed order of the PERTURBABLE
    tuple, which is what makes a run reproducible from its seed alone.

    One consequence worth knowing: `amber` and `red` are perturbed independently, so a run
    can end up with red below amber. That only affects which colour name a status string
    carries. Flagging, and therefore every count in this module, is decided by `amber`
    alone, so no stability number depends on the pair staying ordered.
    """
    return replace(
        params,
        **{name: getattr(params, name) * rng.uniform(*PERTURB_RANGE) for name in PERTURBABLE},
    )


def _matches(base_record, record):
    """Did this rerun produce the same answer?

    Same label, and for TRANSMITTED the same source too. A transmitted case whose source
    moves from one neighbour to another has NOT reproduced: the sentence on screen names
    that neighbour, and naming the wrong person is the failure mode this badge exists to
    warn about.
    """
    if record["label"] != base_record["label"]:
        return False
    if base_record["label"] == TRANSMITTED:
        return record["source_id"] == base_record["source_id"]
    return True


def stability(
    scenario, shocks, interventions, params, base_records, seed, n_runs=N_RUNS
):
    """Rerun the attribution `n_runs` times and count how often each base label survives.

    `base_records` is an attribution result over the full horizon; one entry comes back per
    record, in the same order, so the UI can zip badges onto the cards it already has.

    Each entry:
      member_id, base_label, base_source_id
      matched      reruns that produced the same answer
      differed     reruns that flagged her but gave a different answer
      not_flagged  reruns where she never flagged at all
      n_runs       so the three counts can be read as a partition of it
      badge_text   "stable in {matched} of {n_runs} runs"

    `differed` and `not_flagged` are kept apart on purpose. "We would have called her
    something else" and "she would not have been on the list" are different admissions, and
    collapsing them into one failure count would hide which one is happening.
    """
    base = [
        {
            "member_id": r["member_id"],
            "base_label": r["label"],
            "base_source_id": r["source_id"],
            "matched": 0,
            "differed": 0,
            "not_flagged": 0,
            "n_runs": n_runs,
        }
        for r in base_records
    ]
    by_id = {entry["member_id"]: entry for entry in base}
    base_by_id = {r["member_id"]: r for r in base_records}

    for k in range(n_runs):
        # Two independent streams. The perturbation rng is seeded far away from the draws
        # seeds (seed * 1000 + k against seed + k + 1) so the parameters of run k cannot
        # end up correlated with the dice of run k, which would make a run's outcome
        # depend on an accident of arithmetic rather than on the two sources of doubt.
        run_params = perturbed_params(params, np.random.default_rng(seed * 1000 + k))
        draws = make_draws(scenario.n_members, run_params, seed=seed + k + 1)

        # ONE attribution for the whole run, not one per member: `attribute` already labels
        # every flagged member off a shared cache of worlds, so asking per member would
        # replay the same worlds again for each of them.
        records = {
            r["member_id"]: r
            for r in attribute(
                scenario, shocks, draws, run_params, interventions=interventions
            )
        }

        for member_id, entry in by_id.items():
            record = records.get(member_id)
            if record is None:
                entry["not_flagged"] += 1
            elif _matches(base_by_id[member_id], record):
                entry["matched"] += 1
            else:
                entry["differed"] += 1

    for entry in base:
        # No hyphens and no dashes: this string is rendered on screen in the judged video.
        entry["badge_text"] = f"stable in {entry['matched']} of {n_runs} runs"
    return base
