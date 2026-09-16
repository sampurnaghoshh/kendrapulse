"""THE GATE. Prints the whole demo story in the terminal.

If this script tells the story, the prototype exists: every number below came out of a run of
the seeded scenario, and the frontend in Phase 6 is a picture of this same dict.

    cd backend && .venv/Scripts/python.exe scripts/demo_story.py

Nothing is computed in here. `demo/story.py` builds the story and this file only arranges it,
so the terminal and the UI can never tell two different stories.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from demo.story import build_story, format_rs, r_display_series  # noqa: E402

WIDTH = 86
STATUS_MARK = {"green": "ok", "amber": "AMBER", "red": "RED"}


def heading(number, text):
    print()
    print("=" * WIDTH)
    print(f"{number}. {text.upper()}")
    print("=" * WIDTH)


def line(text="", indent=0):
    print(" " * indent + text)


def r_text(value):
    return "not defined yet" if value is None else f"{value:.2f}"


# ---------------------------------------------------------------------------------------


def opening(story):
    heading(1, "The opening frame: every kendra green")
    opening = story["opening"]
    line(
        "Nobody is flagged in week 1."
        if opening["all_green"]
        else f"Flagged already in week 1: {', '.join(opening['flagged_at_week_one'])}"
    )
    line()
    line("R potential, per kendra. How many of her four neighbours would go down with one")
    line(f"member if she fell ill, averaged over the kendra, watched for "
         f"{story['params']['r_window_weeks']} weeks:")
    line()
    highest = opening["most_exposed_kendra"]
    for kendra_id, value in sorted(opening["r_potential"].items()):
        mark = "  <== most exposed" if kendra_id == highest else ""
        line(f"{kendra_id}   R potential {value:.2f}{mark}", indent=4)
    line()
    tied = opening["most_exposed_tied_with"]
    if tied:
        line(f"{highest} is tied with {', '.join(tied)} at "
             f"{opening['most_exposed_r_potential']:.2f}. Either would do; the story plants its")
        line(f"shock in {story['shocked_kendra']}.")
    line()
    line("Every member is green and this number is already above 1. That is the whole pitch:")
    line("the risk is in the network, and it is visible before anything has gone wrong.")


def the_shock(story):
    heading(2, "The shock we plant")
    line(story["shock"]["sentence"])
    line()
    for shock in story["shock"]["shocks"]:
        line(f"type            {shock['type']}", indent=4)
        line(f"member          {shock['member_name']} ({shock['member_id']})", indent=4)
        line(f"starts week     {shock['start_week']}", indent=4)
        line(f"severity        {shock['severity']:.2f} of weekly income", indent=4)
        line(f"lasts           {shock['duration_weeks']} weeks", indent=4)
    line()
    line("One member. One illness. Nothing else in the scenario changes.")


def week_by_week(story):
    heading(3, "Week by week: what the officer would see")
    for week in story["actual"]["timeline"]:
        changes, events = week["changes"], week["events"]
        if not changes and not events:
            continue
        line(f"Week {week['week']:>2}")
        for change in changes:
            line(
                f"{change['name']:<16} {change['from_status']} to {change['to_status']}"
                f"   (stress {change['s']:.2f})   {STATUS_MARK.get(change['to_status'], '')}",
                indent=6,
            )
        for event in events:
            if event["channel"] != "guarantee":
                continue
            line(
                f"{event['from_name']} covers {format_rs(event['amount'])} "
                f"of {event['to_name']}'s installment at the meeting",
                indent=6,
            )
        # The lender freeze is summarised, not listed. It can touch a dozen members in one
        # week, and printing each would bury the status changes that are the point of this
        # section. The count is what matters: this is the channel that leaves the kendra.
        frozen = [e for e in events if e["channel"] == "shared_lender"]
        if frozen:
            total = sum(e["amount"] for e in frozen)
            origins = ", ".join(sorted({e["from_name"] for e in frozen}))
            line(
                f"a lender freezes top ups over arrears traced to {origins}: "
                f"{len(frozen)} members in other kendras lose {format_rs(total)} of savings",
                indent=6,
            )
    line()
    line(f"Flagged by week {story['params']['horizon_weeks']}: "
         f"{', '.join(story['actual']['flagged'])}")
    line(f"{story['actual']['rupees_at_risk_text']} of loans now sitting on stressed borrowers.")


def attribution(story):
    heading(4, "Attribution: why is each of them flagged")
    line("One sentence per flagged member, then two numbers from 50 reruns with every")
    line("perturbable parameter moved by up to 30% and fresh dice each time. How often she")
    line("was in trouble at all, and how often we named the same cause when she was.")
    line()
    for record in story["attribution"]:
        line(record["sentence"], indent=4)
        line(f"{record['badge_text']}.", indent=8)
        stability = record["stability"]
        agreement = stability["source_agreement"]
        if agreement is None:
            line("She never flagged in any rerun, so there was no cause to agree about.", indent=8)
        elif stability["flagged_runs"] < stability["n_runs"] / 2:
            # The distinction the two part badge exists to make: a marginal case is not a
            # shaky explanation, and saying so out loud is the point.
            line(
                f"A marginal case: only {stability['flagged_runs']} reruns put her over the "
                f"line at all. When they did, we named the same cause "
                f"{round(100 * agreement)}% of the time.",
                indent=8,
            )
        elif stability["differed"]:
            line(
                f"{stability['differed']} of those reruns named a different cause.",
                indent=8,
            )
        line()


def r_progression(story):
    heading(5, f"R live in {story['shocked_kendra']}, week by week")
    line("R live counts onward cases inside the kendra per primary case. Before there is a")
    line("case to divide by there is no ratio, so the screen shows R potential instead and")
    line("says which one it is:")
    line()
    for point in r_display_series(story, story["shocked_kendra"]):
        label = "R potential" if point["kind"] == "potential" else "R live     "
        line(f"week {point['week']:>2}   {label}   {point['value']:.2f}", indent=4)
    line()
    row = next(r for r in story["r"] if r["kendra_id"] == story["shocked_kendra"])
    line(f"primary cases     {', '.join(row['primary_ids']) or 'none'}", indent=4)
    line(f"onward, inside    {', '.join(row['transmitted_ids']) or 'none'}", indent=4)
    line(f"onward, elsewhere {', '.join(row['cross_kendra_ids']) or 'none'}", indent=4)


def smallest_fix(story):
    heading(6, "The smallest fix that stops the spread")
    fix = story["smallest_fix"]
    line(f"The officer decides in week {fix['decision_week']}. Every candidate is replayed on the")
    line("same dice as reality, and any fix that would newly flag somebody is thrown out.")
    line()
    if not fix["ranked"]:
        line("No fix protects anybody here. That is the honest answer, not a bug.")
        return

    for entry in fix["ranked"]:
        line(f"{entry['rank']}. {entry['sentence']}", indent=3)
        line()

    applied = fix["applied"]
    line("-" * WIDTH)
    line(f"Applying the top one: {applied['description']}")
    line()
    line(f"flagged before   {', '.join(applied['flagged_before'])}", indent=4)
    line(f"flagged after    {', '.join(applied['flagged_after'])}", indent=4)
    line(f"protected        {', '.join(applied['members_protected'])}", indent=4)
    line()
    line(f"at risk before   {format_rs(applied['rupees_at_risk_before'])}", indent=4)
    line(f"at risk after    {format_rs(applied['rupees_at_risk_after'])}", indent=4)
    line(f"{applied['moved_text']}.", indent=4)
    line()
    before = next(r for r in story["r"] if r["kendra_id"] == story["shocked_kendra"])
    horizon = story["params"]["horizon_weeks"]
    line(
        f"R live in {story['shocked_kendra']} at week {horizon}: "
        f"{r_text(before['r_live_by_week'][horizon - 1])} becomes "
        f"{r_text(applied['r_live_by_week'][story['shocked_kendra']][horizon - 1])}",
        indent=4,
    )
    line()
    line("The index case is still flagged. She was ill; a lender cannot undo that. What the")
    line("fix does is stop her illness becoming her neighbours' arrears.")


def independent_case(story):
    heading(7, "The case that is nobody's contagion")
    others = [
        record
        for record in story["attribution"]
        if record["member_id"] in story["independent_cases"]
        and record["kendra_id"] != story["shocked_kendra"]
    ]
    if not others:
        line("No independent case outside the shocked kendra in this run.")
        return

    line("Not every flag is an outbreak. In another kendra entirely:")
    line()
    for record in others:
        line(record["sentence"], indent=4)
        line(f"{record['badge_text']}.", indent=8)
        onward = [
            other["sentence"]
            for other in story["attribution"]
            if other["source_id"] == record["member_id"] and other["member_id"] != record["member_id"]
        ]
        for sentence in onward:
            line(f"and it did reach somebody: {sentence}", indent=8)
        line()
    line("A moratorium would not help her, because there is no shock to wait out. She needs")
    line("an income conversation, and the label is what says so.")


def main():
    started = time.perf_counter()
    story = build_story()
    built = time.perf_counter()

    print()
    print("KENDRAPULSE: stress tracing in a joint liability group")
    print(f"{story['config']['name']}. Generator seed {story['config']['generator']['seed']}, "
          f"dice seed {story['config']['draws_seed']}.")

    opening(story)
    the_shock(story)
    week_by_week(story)
    attribution(story)
    r_progression(story)
    smallest_fix(story)
    independent_case(story)

    finished = time.perf_counter()
    print()
    print("=" * WIDTH)
    print(f"story built in {built - started:.2f}s, printed in {finished - built:.2f}s, "
          f"total {finished - started:.2f}s")
    print("=" * WIDTH)


if __name__ == "__main__":
    main()
