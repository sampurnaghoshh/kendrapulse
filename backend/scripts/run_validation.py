"""Run the cause recovery check and write data/validation_report.json.

    cd backend && .venv/Scripts/python.exe scripts/run_validation.py --n 100

This tests the attribution LOGIC. It is not accuracy on real borrowers, and the summary says so
out loud every time it runs, because that is the one sentence somebody will quote out of
context.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from validation.cause_recovery import (  # noqa: E402
    CORRECT,
    OUTCOMES,
    UNEXPLAINED,
    WRONG_LABEL,
    WRONG_SOURCE,
    build_report,
)

REPORT_PATH = Path(__file__).resolve().parents[2] / "data" / "validation_report.json"
WIDTH = 86

OUTCOME_WORDS = {
    CORRECT: "correct",
    WRONG_SOURCE: "right label, wrong neighbour",
    WRONG_LABEL: "wrong label",
    UNEXPLAINED: "could not explain her at all",
}


def pct(value):
    return "not defined" if value is None else f"{100 * value:.1f}%"


def rule():
    print("=" * WIDTH)


def print_block(title, block):
    print(f"  {title}")
    for outcome in OUTCOMES:
        count = block["counts"][outcome]
        if outcome == UNEXPLAINED and count == 0:
            continue
        print(f"      {OUTCOME_WORDS[outcome]:<32} {count:>6}")
    print(f"      {'accuracy when explained':<32} {pct(block['accuracy_when_explained']):>6}")
    print(f"      {'overall accuracy':<32} {pct(block['overall_accuracy']):>6}")


def summarise(report):
    config, totals = report["config"], report["totals"]

    rule()
    print("CAUSE RECOVERY: can the procedure recover a planted cause without the truth?")
    rule()
    print(report["what_this_is"])
    print()
    print(f"  scenarios scored        {config['scenarios_scored']} of {config['n_scenarios']}"
          f"  ({config['scenarios_skipped_nobody_flagged']} had nobody flagged)")
    print(f"  observed flagged        {totals['observed_flagged_members']} members")
    print(f"  parameter noise         U({config['param_noise'][0]}, {config['param_noise'][1]})"
          " on every perturbable field")
    print(f"  income and trend noise  {int(100 * config['income_noise'])}% multiplicative")
    print(f"  dice                    a different seed, offset by {config['engine_seed_offset']}")
    print(f"  commit                  {config['git_commit'][:12]}")
    print()

    print_block("ENGINE UNDER TEST (perturbed params, noisy incomes, different dice)",
                totals["engine"])
    print()
    print_block("BASELINE (no simulation: shock list and event log only)", totals["baseline"])
    print()

    print("  Per true label, engine:")
    for label, block in report["per_true_label"]["engine"].items():
        baseline = report["per_true_label"]["baseline"][label]
        print(f"      {label:<14} n {block['n']:>5}   "
              f"engine {pct(block['accuracy_when_explained']):>10}   "
              f"baseline {pct(baseline['accuracy_when_explained']):>10}")
    print()

    print("  Confusion, true label down, engine label across:")
    columns = list(next(iter(report["confusion_truth_by_engine"].values())))
    print("      " + " " * 14 + "".join(f"{c[:11]:>13}" for c in columns))
    for truth, row in report["confusion_truth_by_engine"].items():
        print(f"      {truth:<14}" + "".join(f"{row[c]:>13}" for c in columns))
    print()

    hard, clean = report["hard_cases"], report["clean_cases"]
    print(f"  Hard cases ({hard['definition']}):")
    if hard["engine"]:
        print(f"      {hard['n_members']} members, engine "
              f"{pct(hard['engine']['accuracy_when_explained'])} when explained")
    else:
        print("      none in this sample")
    if clean["engine"]:
        print(f"  Every other scenario: {clean['n_members']} members, engine "
              f"{pct(clean['engine']['accuracy_when_explained'])} when explained")
    print()

    examples = report["failure_examples"]["engine"]
    shown = [(o, e) for o, e in examples.items() if o != CORRECT and e]
    if shown:
        print("  Engine failures worth reading, reproducible from the seed:")
        for outcome, entries in shown:
            print(f"      {OUTCOME_WORDS[outcome]}")
            for entry in entries[:3]:
                note = f"   [{entry['note']}]" if entry["note"] else ""
                print(f"          seed {entry['generator_seed']:>4}  {entry['member_id']}  "
                      f"truth {entry['truth_label']} from {entry['truth_source_id']}  "
                      f"engine {entry['engine_label']} from {entry['engine_source_id']}{note}")
    print()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the cause recovery validation.")
    parser.add_argument("--n", type=int, default=500, help="scenarios to run (default 500)")
    parser.add_argument("--base-seed", type=int, default=0)
    parser.add_argument("--every", type=int, default=25, help="progress interval")
    parser.add_argument("--out", type=Path, default=REPORT_PATH)
    args = parser.parse_args(argv)

    started = time.perf_counter()

    def progress(done, total, n_rows):
        if done % args.every == 0 or done == total:
            elapsed = time.perf_counter() - started
            rate = done / elapsed if elapsed else 0
            remaining = (total - done) / rate if rate else 0
            print(
                f"  {done:>4} of {total} scenarios   {n_rows:>5} flagged members   "
                f"{elapsed:5.1f}s elapsed   about {remaining:5.1f}s left",
                flush=True,
            )

    print(f"Running {args.n} scenarios from base seed {args.base_seed}.")
    report = build_report(n_scenarios=args.n, base_seed=args.base_seed, progress=progress)
    built = time.perf_counter()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print()
    summarise(report)
    rule()
    print(f"report written to {args.out}")
    print(f"{args.n} scenarios in {built - started:.1f}s "
          f"({(built - started) / max(args.n, 1):.2f}s each), "
          f"total {time.perf_counter() - started:.1f}s")
    rule()
    return report


if __name__ == "__main__":
    main()
