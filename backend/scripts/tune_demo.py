"""Search the demo scenario's INPUTS for a transmitted case that is clear, not marginal.

    cd backend && .venv/Scripts/python.exe scripts/tune_demo.py
    cd backend && .venv/Scripts/python.exe scripts/tune_demo.py --with-overrides

Only `data/demo_scenario.json` inputs move here: the health shock's duration, severity and start
week, and (with --with-overrides) scaled savings buffers for the k2 peers the story already calls
TRANSMITTED. params.py, the
engine, amber and red, and the perturbation range are never touched, because validation and the
tests rest on those defaults.

Every candidate runs the real `build_story()` with a 20 run stability badge for speed; the best
two that pass are then confirmed at 50 runs, which is what the demo actually shows. Nothing is
chosen by hand from inside this file: it prints the table and the pick, and the pick is copied
into the JSON by a person who has read the table.

The pick is the passing candidate CLOSEST TO THE DEFAULTS, not the one with the best badges. A
shock tuned until every number looks perfect would be a shock nobody recognises.
"""

import argparse
import copy
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from demo.story import build_story, load_config  # noqa: E402
from sim.attribution import INDEPENDENT, TRANSMITTED  # noqa: E402
from sim.params import DEFAULT  # noqa: E402

# The targets from NEXT.md, written down before the search ran.
MIN_FLAGGED_RUNS_OF_50 = 35
MIN_SOURCE_AGREEMENT = 0.9  # strictly above
MIN_PROTECTED = 2

DURATIONS = (3, 4, 5, 6)
SEVERITIES = (0.6, 0.65, 0.7, 0.75, 0.8)
START_WEEKS = (2, 3)
# Only with --with-overrides. Both directions, because thinner turned out to be the wrong
# guess: cover is paid from meeting cash first and capped at a share of cash PLUS buffer, so a
# thinner buffer shrinks what a peer can give and a thicker one pushes more of it through her
# own installment money.
BUFFER_SCALES = (0.5, 0.75, 1.5, 2.0)


def candidate_config(base, duration, severity, start_week, buffer_scale=None, story=None):
    config = copy.deepcopy(base)
    shock = config["shocks"][0]
    shock["duration_weeks"] = duration
    shock["severity"] = severity
    shock["start_week"] = start_week
    # Keep the decision one week after the shock starts, as in the seeded story: the officer
    # sees it at a meeting and acts the week after, never before.
    config["decision_week"] = start_week + 1
    config.pop("member_overrides", None)
    if buffer_scale is not None and story is not None:
        hero_kendra = story["shocked_kendra"]
        # Only the peers the seeded story already calls TRANSMITTED. Thinning a member who is
        # not in the story would add a new case rather than clarify an existing one.
        heroes = {
            r["member_id"] for r in story["attribution"]
            if r["label"] == TRANSMITTED and r["kendra_id"] == hero_kendra
        }
        config["member_overrides"] = [
            {
                "member_id": m["id"],
                "savings_buffer": round(m["savings_buffer"] * buffer_scale),
                "reason": f"tuning probe x{buffer_scale}",
            }
            for m in story["scenario"]["members"]
            if m["id"] in heroes
        ]
    return config


def distance_from_defaults(config):
    """How far the inputs moved. One default duration week, one start week and 0.05 of
    severity each count as one step; every overridden member counts as two."""
    default_severity, default_duration = DEFAULT.shock_defaults["health"]
    shock = config["shocks"][0]
    return (
        abs(shock["duration_weeks"] - default_duration)
        + abs(shock["start_week"] - 2)
        + abs(shock["severity"] - default_severity) / 0.05
        + 2 * len(config.get("member_overrides", []))
    )


def summarise(config, n_runs):
    config = copy.deepcopy(config)
    config["stability"]["n_runs"] = n_runs
    story = build_story(config=config)
    hero_kendra = story["shocked_kendra"]
    by_id = {r["member_id"]: r for r in story["attribution"]}

    flagged_per_kendra = {k: 0 for k in sorted(story["scenario"]["kendras"])}
    kendra_of = {m["id"]: m["kendra_id"] for m in story["scenario"]["members"]}
    for mid in story["actual"]["flagged"]:
        flagged_per_kendra[kendra_of[mid]] += 1

    heroes = [
        r for r in story["attribution"]
        if r["label"] == TRANSMITTED and r["kendra_id"] == hero_kendra
    ]
    badges = [
        (r["member_id"], r["stability"]["flagged_runs"], r["stability"]["source_agreement"])
        for r in heroes
    ]
    scaled_min = MIN_FLAGGED_RUNS_OF_50 * n_runs / 50

    outside = {mid for mid in story["actual"]["flagged"] if kendra_of[mid] != hero_kendra}
    r_pot = story["opening"]["r_potential"]
    applied = story["smallest_fix"]["applied"]
    top = story["smallest_fix"]["ranked"][0] if story["smallest_fix"]["ranked"] else None

    checks = {
        "green_wk1": story["opening"]["all_green"],
        "k2_top_R": r_pot[hero_kendra] >= max(r_pot.values()),
        "outside_ok": outside <= {"m002", "m004"},
        "m002_indep": "m002" not in by_id or by_id["m002"]["label"] == INDEPENDENT,
        "fix_ge_2": applied is not None and len(applied["members_protected"]) >= MIN_PROTECTED,
        "heroes": len(badges) >= 2 and all(
            runs >= scaled_min and agree is not None and agree > MIN_SOURCE_AGREEMENT
            for _, runs, agree in badges
        ),
    }
    return {
        "config": config,
        "distance": distance_from_defaults(config),
        "flagged_per_kendra": flagged_per_kendra,
        "badges": badges,
        "top_fix": top["description"] if top else "none",
        "protected": len(applied["members_protected"]) if applied else 0,
        "checks": checks,
        "passes": all(checks.values()),
        "story": story,
    }


def row_text(result, n_runs):
    shock = result["config"]["shocks"][0]
    overrides = result["config"].get("member_overrides") or []
    inputs = (
        f"dur {shock['duration_weeks']} sev {shock['severity']:.2f} wk {shock['start_week']}"
        + (f" {overrides[0]['reason'].split()[-1]} on {len(overrides)}" if overrides else "")
    )
    kendras = " ".join(f"{v}" for v in result["flagged_per_kendra"].values())
    badges = " ".join(
        f"{mid}:{runs}/{n_runs}@{'none' if agree is None else f'{agree:.2f}'}"
        for mid, runs, agree in result["badges"]
    ) or "no transmitted peers"
    failed = ",".join(k for k, ok in result["checks"].items() if not ok) or "PASS"
    return (
        f"{inputs:<30} d={result['distance']:<4.1f} flagged[{kendras}]  "
        f"prot {result['protected']}  {failed:<22} {badges}\n"
        f"{'':<34}top fix: {result['top_fix']}"
    )


def _run(args):
    config, n_runs = args
    result = summarise(config, n_runs)
    result.pop("story")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-overrides", action="store_true")
    parser.add_argument("--quick-runs", type=int, default=20)
    parser.add_argument("--buffer-scales", type=float, nargs="+", default=list(BUFFER_SCALES))
    parser.add_argument("--override-durations", type=int, nargs="+", default=[4, 5, 6])
    parser.add_argument("--override-start-weeks", type=int, nargs="+", default=[2])
    args = parser.parse_args()

    started = time.perf_counter()
    base = load_config()
    grid = [
        candidate_config(base, d, s, w)
        for w in START_WEEKS for d in DURATIONS for s in SEVERITIES
    ]
    if args.with_overrides:
        # Buffer overrides on the peers the seeded story calls TRANSMITTED, stacked on the
        # default severity. Added to the shock grid, not instead of it, so the pick can still
        # land on a shock only candidate when one is good enough.
        probe = build_story(config={**copy.deepcopy(base), "stability": {"seed": 1, "n_runs": 1}})
        grid += [
            candidate_config(base, d, 0.65, w, buffer_scale=scale, story=probe)
            for scale in args.buffer_scales
            for w in args.override_start_weeks
            for d in args.override_durations
        ]

    with ProcessPoolExecutor() as pool:
        results = list(pool.map(_run, [(c, args.quick_runs) for c in grid]))

    print()
    print(f"QUICK PASS: {len(results)} candidates, {args.quick_runs} runs each "
          f"(hero target scaled to {MIN_FLAGGED_RUNS_OF_50 * args.quick_runs / 50:.0f})")
    print("inputs / distance / flagged per kendra k0..k4 / protected / failed checks / hero badges")
    for result in sorted(results, key=lambda r: (not r["passes"], r["distance"])):
        print(row_text(result, args.quick_runs))

    # Confirm the two best at 50 runs. If nothing passes outright, the two best NEAR MISSES
    # are confirmed instead: every story check holds, and the most hero peers meet the
    # target, then the most hero reruns in total, then closest to defaults. That keeps
    # the fallback pick honest rather than silently picking the prettiest failure.
    def story_ok(r):
        return all(ok for name, ok in r["checks"].items() if name != "heroes")

    def near_miss_key(r):
        scaled = MIN_FLAGGED_RUNS_OF_50 * args.quick_runs / 50
        meeting = sum(runs >= scaled and (agree or 0) > MIN_SOURCE_AGREEMENT
                      for _, runs, agree in r["badges"])
        total = sum(runs for _, runs, _ in r["badges"])
        return (-meeting, -total, r["distance"])

    passing = sorted((r for r in results if r["passes"]), key=lambda r: r["distance"])[:2]
    if not passing:
        print()
        print("No candidate passes at the quick run count; confirming the two best near misses.")
        passing = sorted((r for r in results if story_ok(r)), key=near_miss_key)[:2]

    with ProcessPoolExecutor() as pool:
        confirmed = list(pool.map(_run, [(r["config"], 50) for r in passing]))

    print()
    print("CONFIRMED AT 50 RUNS")
    for result in confirmed:
        print(row_text(result, 50))
    final = [r for r in confirmed if r["passes"]]
    if final:
        pick = min(final, key=lambda r: r["distance"])
        verdict = "PICK (closest to defaults that passes at 50)"
    else:
        # Most heroes meeting the target, then the most hero reruns in total, then closest to
        # defaults. Total, not weakest, so dropping a hero from the story cannot win.
        pick = min(confirmed, key=lambda r: (
            -sum(runs >= MIN_FLAGGED_RUNS_OF_50 and (a or 0) > MIN_SOURCE_AGREEMENT
                 for _, runs, a in r["badges"]),
            -sum(runs for _, runs, _ in r["badges"]),
            r["distance"],
        ))
        verdict = "BEST AVAILABLE (targets NOT met for every hero)"
    shock = pick["config"]["shocks"][0]
    print()
    print(f"{verdict}: duration {shock['duration_weeks']}, "
          f"severity {shock['severity']}, start week {shock['start_week']}, "
          f"decision week {pick['config']['decision_week']}, "
          f"overrides {pick['config'].get('member_overrides') or 'none'}")
    print(f"{time.perf_counter() - started:.0f}s")


if __name__ == "__main__":
    main()
