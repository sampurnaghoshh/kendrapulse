"""The static snapshot the frontend falls back to when the API is unreachable.

`build_snapshot()` is `build_story()` plus the extra worlds the screens draw and the backend
would otherwise compute on request:

  counterfactual_worlds   per flagged member, the one world her label rests on (Two worlds)
  fix_replays             per week states of each of the top 3 fixes
  ever_flagged_by_week    per member, has she been flagged at some point up to week w (the
                          persistent ring); also inside every world and replay
  validation              the same subset and all observed tables from the n=500 report, as
                          counts, with the sentence saying what the check is and is not
  meta                    generated_at, git commit, seeds

Nothing new is decided here. Every world is replayed through `setup_world`, on the same
roster, shocks and draws as the story, and the label of each member comes from the story's own
attribution records. Floats are rounded to 3 decimals, which is finer than any panel draws.

Layout note: `smallest_fix.ranked[i].weeks` and `smallest_fix.applied.weeks` are moved into
`fix_replays` rather than copied, so the file carries each replay once.
"""

import datetime
import json
import subprocess
from pathlib import Path

from demo.story import (
    CONFIG_PATH,
    _plain,
    _weeks,
    build_story,
    load_config,
    setup_world,
)
from sim.attribution import label_worlds
from sim.params import DEFAULT

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = REPO_ROOT / "frontend" / "public" / "demo_snapshot.json"
VALIDATION_PATH = REPO_ROOT / "data" / "validation_report.json"
DECIMALS = 3


def round_floats(value, decimals=DECIMALS):
    if isinstance(value, dict):
        return {k: round_floats(v, decimals) for k, v in value.items()}
    if isinstance(value, list):
        return [round_floats(v, decimals) for v in value]
    if isinstance(value, float):
        return round(value, decimals)
    return value


def ever_flagged_by_week(weeks):
    """{member_id: [bool per week, week 1 first]}: flagged at some point up to that week.

    Read from `status`, which is amber or worse exactly when s >= amber, so this agrees with
    `Run.flagged(member, as_of_week)` week by week.
    """
    ordered = sorted(weeks, key=int)
    member_ids = list(weeks[ordered[0]])
    out = {}
    for member_id in member_ids:
        seen, series = False, []
        for week in ordered:
            seen = seen or weeks[week][member_id]["status"] != "green"
            series.append(seen)
        out[member_id] = series
    return out


def _git_commit():
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5,
            check=True, cwd=REPO_ROOT,
        ).stdout.strip()
    except Exception:
        return "unknown"


def validation_summary(path=VALIDATION_PATH):
    """The two fair tables, as counts. None when the report has not been produced yet."""
    path = Path(path)
    if not path.exists():
        return None
    report = json.loads(path.read_text(encoding="utf-8"))
    fair = report.get("fairness")
    if fair is None:
        return None

    def table(block):
        parties = ("engine_threshold", "engine_anchored", "baseline")
        return {
            "n": block["n"],
            "overall": {p: {"correct": block[p]["correct"], "of": block[p]["of"]} for p in parties},
            "per_true_label": {
                label: {p: {"correct": row[p]["correct"], "of": row[p]["of"]} for p in parties}
                for label, row in block["per_true_label"].items()
            },
        }

    return {
        "what_this_is": report["what_this_is"],
        "n_scenarios": report["config"]["n_scenarios"],
        "scenarios_scored": report["config"]["scenarios_scored"],
        "report_git_commit": report["config"]["git_commit"],
        "same_subset": table(fair["same_subset"]),
        "all_observed": table(fair["all_observed"]),
        "unexplained_threshold": fair["unexplained_threshold"],
        "no_signal_anchored": fair["no_signal_anchored"],
        "prediction": fair["prediction"],
    }


def counterfactual_worlds(scenario, shocks, draws, records, params=DEFAULT):
    worlds = label_worlds(scenario, shocks, draws, records, params)
    out = {}
    for record in records:
        world = worlds[record["member_id"]]
        weeks = _plain(_weeks(world["run"], scenario)) if world["run"] is not None else None
        removed = world["removed_member_id"]
        out[record["member_id"]] = {
            "label": record["label"],
            "kind": world["kind"],
            "removed_member_id": removed,
            # Screen copy, so no hyphens or dashes.
            "title": (
                f"The world without {scenario.member(removed).name}'s trouble"
                if world["kind"] == "without_source" and removed is not None
                else f"The world where only {scenario.member(record['member_id']).name}'s own "
                     "life went wrong"
                if world["kind"] == "only_own_causes"
                else "No single source to remove"
            ),
            "weeks": weeks,
            "ever_flagged_by_week": ever_flagged_by_week(weeks) if weeks else None,
        }
    return out


def build_snapshot(config_path=CONFIG_PATH, params=DEFAULT, validation_path=VALIDATION_PATH):
    config = load_config(config_path)
    story = build_story(config=config, params=params)
    scenario, draws, shocks = setup_world(config, params)

    fix = story["smallest_fix"]
    fix_replays = []
    for entry in fix["ranked"]:
        weeks = entry.pop("weeks")
        fix_replays.append({
            "rank": entry["rank"],
            "description": entry["description"],
            "intervention": entry["intervention"],
            "weeks": weeks,
            "ever_flagged_by_week": ever_flagged_by_week(weeks),
        })
    if fix["applied"] is not None:
        fix["applied"].pop("weeks")
        fix["applied"]["replay_rank"] = 1

    snapshot = {
        **story,
        "ever_flagged_by_week": ever_flagged_by_week(story["actual"]["weeks"]),
        "counterfactual_worlds": counterfactual_worlds(
            scenario, shocks, draws, story["attribution"], params
        ),
        "fix_replays": fix_replays,
        "validation": validation_summary(validation_path),
        "meta": {
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(
                timespec="seconds"
            ),
            "git_commit": _git_commit(),
            "generator_seed": config["generator"]["seed"],
            "draws_seed": config["draws_seed"],
            "stability_seed": config["stability"]["seed"],
            "float_decimals": DECIMALS,
            "layout_note": (
                "smallest_fix ranked and applied weeks live in fix_replays, one copy each"
            ),
        },
    }
    snapshot.pop("build_seconds", None)
    return round_floats(snapshot)
