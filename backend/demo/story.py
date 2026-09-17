"""The whole demo, assembled once into one plain dict.

`build_story()` runs the seeded scenario end to end and returns everything the story needs:
the roster and the network, the weekly states, a labelled and badged explanation for every
flagged member, both R numbers per kendra, the three smallest fixes, and the replay of the
best one. `scripts/demo_story.py` prints it, and Phase 5 will serve the same dict over HTTP,
so there is exactly one place where the story is decided.

THREE RULES THIS MODULE FOLLOWS
------------------------------
Everything comes from a run. No number is written down here. The scenario, the shock, the
decision week and the stability seed are read from `data/demo_scenario.json`, which holds
INPUTS only; every figure in the output is computed.

Everything is JSON serialisable. The engine indexes a numpy array, so most of its floats are
numpy scalars, and `json.dumps` refuses those. `_plain` coerces the whole tree on the way
out, which is also what lets Phase 5 hand this straight to FastAPI.

No hyphens and no dashes in any string a viewer reads. It appears in the judged video.
Member ids, income source keys and channel keys are identifiers, not prose, and are exempt.
"""

import dataclasses
import json
import time
from pathlib import Path

from sim.attribution import INDEPENDENT, INDEX, TRANSMITTED, attribute
from sim.engine import Shock, make_draws, simulate
from sim.generator import generate_scenario
from sim.interventions import MORATORIUM
from sim.params import DEFAULT
from sim.r_number import r_for_display, r_numbers
from sim.smallest_fix import rupees_at_risk, smallest_fix
from sim.stability import stability
from validation.cause_recovery import baseline_labels

CONFIG_PATH = Path(__file__).resolve().parents[2] / "data" / "demo_scenario.json"

# How a channel reads in a sentence an officer would say out loud.
CHANNEL_PHRASE = {
    "guarantee": "group guarantee cover",
    "shared_income": "a shared income source",
    "shared_lender": "a shared lender pausing top ups",
}

# How a shock type reads. Present tense, because the officer is describing what happened to
# a person, not naming a row in a table.
SHOCK_PHRASE = {
    "health": "health shock",
    "crop_loss": "crop loss",
    "job_loss": "job loss",
    "festival_spend": "festival spending",
    "weak_monsoon": "weak monsoon",
}


# ---------------------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------------------


def format_rs(amount) -> str:
    """Rupees in Indian digit grouping: 273172 reads Rs 2,73,172.

    Lakh grouping, not thousands grouping. The audience reads portfolio numbers this way, and
    "Rs 273,172" would look like a foreign document. Negative amounts spell the word rather
    than using a minus sign, which is a dash.
    """
    value = int(round(float(amount)))
    digits = str(abs(value))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    return f"Rs {digits}" if value >= 0 else f"minus Rs {digits}"


def moved_out_of_stress(amount) -> str:
    """The one sentence we use for money.

    Never "saved" and never "loss avoided". Both would claim the lender banked a number we
    have not measured: this is exposure that is no longer sitting on a stressed borrower, not
    a profit and not a recovery.
    """
    return f"{format_rs(amount)} of loans moved out of stress"


def _plain(value):
    """Coerce a tree of engine output into something `json.dumps` accepts.

    numpy scalars are the reason this exists. They behave like floats everywhere else in the
    codebase, which is exactly why they reach the boundary unnoticed.
    """
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if hasattr(value, "item"):  # numpy scalar
        value = value.item()
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value, 4)
    return str(value)


# ---------------------------------------------------------------------------------------
# Sentences
# ---------------------------------------------------------------------------------------


def _shock_sentence(scenario, shocks, member_id):
    """Her own shock, named with its week, for an index case."""
    own = [s for s in shocks if s.hits(scenario.member(member_id))]
    if not own:
        return "her own situation"
    shock = own[0]
    phrase = SHOCK_PHRASE.get(shock.type, shock.type)
    return f"her own {phrase} in week {shock.start_week}"


def explanation_sentence(scenario, shocks, record):
    """One sentence per flagged member, in the words a field officer would use.

    The transmitted case is the one that has to carry weight: it names the person, the
    channel and the week, because "transmitted" on its own is a claim and those three details
    are the evidence for it.
    """
    name = scenario.member(record["member_id"]).name
    label = record["label"]

    if label == INDEX:
        return f"{name}: index case. It started with {_shock_sentence(scenario, shocks, record['member_id'])}."

    if label == INDEPENDENT:
        if record["source_cause"] == "trend":
            return (
                f"{name}: independent. Her own income is slipping week by week and no shock "
                "anywhere is behind it."
            )
        return f"{name}: independent. It started with {_shock_sentence(scenario, shocks, record['member_id'])}."

    if record["source_id"] is None:
        return (
            f"{name}: transmitted, but no single source explains her. Several members are "
            "pressing on her at once."
        )

    source = scenario.member(record["source_id"])
    channel = record["path"][-1]["channel"] if record["path"] else "guarantee"
    week = record["first_flag_week"]
    sentence = (
        f"{name}: transmitted from {source.name} through "
        f"{CHANNEL_PHRASE.get(channel, channel)} in week {week}."
    )
    if record["source_cause"] == "trend":
        sentence += f" {source.name}'s own income is slipping."
    if not record["sole_source"]:
        sentence += " She is carrying more than one member, so this is the largest of several causes."
    return sentence


def shock_sentence(scenario, shock, params=DEFAULT):
    """The planted event, described the way the demo narrates it."""
    severity, duration = shock.resolve(params)
    who = (
        scenario.member(shock.member_id).name
        if shock.member_id
        else f"every member working in {shock.income_source}"
    )
    kendra = f" of {scenario.member(shock.member_id).kendra_id}" if shock.member_id else ""
    return (
        f"Week {shock.start_week}: {who}{kendra} is hit by a "
        f"{SHOCK_PHRASE.get(shock.type, shock.type)}. She loses {round(severity * 100)}% of "
        f"her income for {duration} weeks."
    )


def fix_sentence(scenario, entry):
    """A ranked fix, as the panel will read it."""
    names = ", ".join(scenario.member(mid).name for mid in entry["members_protected"])
    return (
        f"{entry['intervention'].describe(scenario)}. "
        f"Protects {len(entry['members_protected'])} "
        f"{'member' if len(entry['members_protected']) == 1 else 'members'} ({names}) who "
        "would otherwise be flagged at some point. "
        f"Costs the lender {format_rs(entry['lender_cost'])}. "
        f"{moved_out_of_stress(entry['rupees_at_risk_avoided'])}."
    )


# ---------------------------------------------------------------------------------------
# Pieces of the story
# ---------------------------------------------------------------------------------------


def _roster(scenario):
    return [
        {
            "id": m.id,
            "name": m.name,
            "kendra_id": m.kendra_id,
            "weekly_income": m.weekly_income,
            "income_source": m.income_source,
            "income_trend": m.income_trend,
            "savings_buffer": m.savings_buffer,
            "household_size": m.household_size,
            "weekly_due": m.weekly_due,
            "total_outstanding": m.total_outstanding,
            "loans": [
                {
                    "lender": loan.lender,
                    "weekly_installment": loan.weekly_installment,
                    "outstanding": loan.outstanding,
                }
                for loan in m.loans
            ],
        }
        for m in scenario.members
    ]
    # Seasonality is deliberately left out: 52 numbers per member that no panel draws.


def _edges(scenario):
    """One entry per typed edge. Sorted so the frontend never sees them reorder."""
    seen = sorted(
        {
            (min(u, v), max(u, v), data.get("type"))
            for u, v, data in scenario.graph.edges(data=True)
        }
    )
    return [{"from_id": u, "to_id": v, "type": edge_type} for u, v, edge_type in seen]


def _weeks(run, scenario):
    """states, trimmed to what a panel draws, one entry per week."""
    keep = ("income", "due", "paid", "unpaid", "shortfall_ratio", "buffer", "cover_given",
            "cover_received", "s", "status")
    return {
        str(week): {
            m.id: {k: v for k, v in run.states[week][m.id].items() if k in keep}
            for m in scenario.members
        }
        for week in sorted(run.states)
    }


def _timeline(scenario, run):
    """Week by week: who changed status, and which transfers happened.

    This is what the WeekSlider animates and what section 3 of the script prints, so it is
    computed once here rather than twice in two places that could drift apart.
    """
    previous = {m.id: "green" for m in scenario.members}
    out = []
    for week in sorted(run.states):
        changes = []
        for m in scenario.members:
            status = run.states[week][m.id]["status"]
            if status != previous[m.id]:
                changes.append({
                    "member_id": m.id,
                    "name": m.name,
                    "from_status": previous[m.id],
                    "to_status": status,
                    "s": run.states[week][m.id]["s"],
                })
                previous[m.id] = status
        events = [
            {
                "channel": e["channel"],
                "from_id": e["from_id"],
                "from_name": scenario.member(e["from_id"]).name,
                "from_kendra_id": scenario.member(e["from_id"]).kendra_id,
                "to_id": e["to_id"],
                "to_name": scenario.member(e["to_id"]).name,
                "amount": e["amount"],
            }
            for e in run.events
            if e["week"] == week
        ]
        out.append({"week": week, "changes": changes, "events": events})
    return out


def _flagged(scenario, run, as_of_week=None):
    return [m.id for m in scenario.members if run.flagged(m.id, as_of_week)]


def apply_member_overrides(scenario, overrides):
    """Apply the optional `member_overrides` block of the demo config to a generated roster.

    Each entry is `{member_id, <field>: value, reason}`. Only fields that already exist on
    `Member` can be set, and every entry must carry a `reason` string, because an override is
    a disclosed edit to the seeded data (the README lists them), never a quiet one. The graph
    and layout do not depend on the fields an override is allowed to touch, so they are kept.
    """
    if not overrides:
        return scenario
    members = list(scenario.members)
    allowed = {f.name for f in dataclasses.fields(members[0])} - {"id", "name", "kendra_id"}
    for entry in overrides:
        if not entry.get("reason"):
            raise ValueError(f"member override for {entry.get('member_id')} has no reason")
        changes = {k: v for k, v in entry.items() if k not in ("member_id", "reason")}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"member override sets unknown fields {sorted(unknown)}")
        i = scenario.index_of[entry["member_id"]]
        members[i] = dataclasses.replace(members[i], **changes)
    return dataclasses.replace(scenario, members=tuple(members))


def load_config(path=CONFIG_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------------------
# The whole thing
# ---------------------------------------------------------------------------------------


def build_story(config=None, params=DEFAULT, config_path=CONFIG_PATH):
    """Run the seeded demo end to end and return every number the story tells.

    Deterministic: the only randomness is the two seeds in the config, and the draws array is
    built once and shared by every run in here, including the smallest fix replays and the
    counterfactuals inside attribution.
    """
    started = time.perf_counter()
    config = load_config(config_path) if config is None else config

    scenario = generate_scenario(
        n_kendras=config["generator"]["n_kendras"],
        members_per_kendra=config["generator"]["members_per_kendra"],
        seed=config["generator"]["seed"],
        params=params,
    )
    scenario = apply_member_overrides(scenario, config.get("member_overrides"))
    # ONE draws array for the whole story. Every world below is handed this object.
    draws = make_draws(scenario.n_members, params, seed=config["draws_seed"])
    shocks = [
        Shock(
            type=s["type"],
            start_week=s["start_week"],
            member_id=s.get("member_id"),
            income_source=s.get("income_source"),
            severity=s.get("severity"),
            duration_weeks=s.get("duration_weeks"),
        )
        for s in config["shocks"]
    ]
    decision_week = config["decision_week"]

    # 1. The opening frame: nothing planted yet, so R potential is the only number there is.
    baseline = simulate(scenario, [], [], params, draws)
    baseline_rows = r_numbers(scenario, [], draws, params)
    # Highest R potential, lowest kendra id breaking a tie. Ties are real and common on a
    # small branch, so the tied kendras come back too rather than one of them being quietly
    # crowned the worst.
    by_exposure = sorted(baseline_rows, key=lambda row: (-row["r_potential"], row["kendra_id"]))
    most_exposed = by_exposure[0]
    tied_with = [
        row["kendra_id"]
        for row in by_exposure[1:]
        if row["r_potential"] == most_exposed["r_potential"]
    ]

    # 2 and 3. The actual run.
    actual = simulate(scenario, shocks, [], params, draws)
    actual_at_risk = rupees_at_risk(scenario, actual)

    # 4. Labels, sentences and badges.
    records = attribute(scenario, shocks, draws, params)
    # What the no simulation rule from the validation would say about the same people, from
    # the same event log. Reported, never used to label: it is here so the story can point at
    # the one kind of case where the replay and a spreadsheet disagree.
    simple_rule = baseline_labels(scenario, shocks, actual, [r["member_id"] for r in records])
    badges = {
        entry["member_id"]: entry
        for entry in stability(
            scenario,
            shocks,
            (),
            params,
            records,
            seed=config["stability"]["seed"],
            n_runs=config["stability"]["n_runs"],
        )
    }
    attribution = [
        {
            **record,
            "name": scenario.member(record["member_id"]).name,
            "kendra_id": scenario.member(record["member_id"]).kendra_id,
            "sentence": explanation_sentence(scenario, shocks, record),
            "badge_text": badges[record["member_id"]]["badge_text"],
            "stability": badges[record["member_id"]],
            "simple_rule": simple_rule[record["member_id"]],
        }
        for record in records
    ]

    # 5. Both R numbers, on the same records so the labels and the ratios cannot disagree.
    rows = r_numbers(scenario, shocks, draws, params, records=records)
    shocked_kendra = scenario.member(shocks[0].member_id).kendra_id if shocks[0].member_id else None

    # 6. The smallest fix, and the replay of the best one.
    fixes = smallest_fix(scenario, shocks, params, draws, decision_week=decision_week)
    ranked = [
        {
            "rank": i + 1,
            "intervention": entry["intervention"].to_dict(),
            "description": entry["intervention"].describe(scenario),
            "sentence": fix_sentence(scenario, entry),
            "members_protected": entry["members_protected"],
            "member_names": [scenario.member(mid).name for mid in entry["members_protected"]],
            "lender_cost": entry["lender_cost"],
            "lender_cost_text": format_rs(entry["lender_cost"]),
            "rupees_at_risk_avoided": entry["rupees_at_risk_avoided"],
            "moved_text": moved_out_of_stress(entry["rupees_at_risk_avoided"]),
            "r_live_by_week": entry["r_live_by_week"],
            "cross_kendra_reach_by_week": entry["cross_kendra_reach_by_week"],
            "weeks": _weeks(entry["run"], scenario),
        }
        for i, entry in enumerate(fixes)
    ]

    applied = None
    if fixes:
        best = fixes[0]
        applied = {
            "intervention": best["intervention"].to_dict(),
            "description": best["intervention"].describe(scenario),
            "flagged_before": _flagged(scenario, actual),
            "flagged_after": _flagged(scenario, best["run"]),
            "members_protected": best["members_protected"],
            "rupees_at_risk_before": actual_at_risk,
            "rupees_at_risk_after": rupees_at_risk(scenario, best["run"]),
            "rupees_at_risk_avoided": best["rupees_at_risk_avoided"],
            "moved_text": moved_out_of_stress(best["rupees_at_risk_avoided"]),
            "r_live_by_week": best["r_live_by_week"],
            "cross_kendra_reach_by_week": best["cross_kendra_reach_by_week"],
            "timeline": _timeline(scenario, best["run"]),
            "weeks": _weeks(best["run"], scenario),
        }

    # 6b. The officer's note at the decision week. The text is an INPUT written in the config;
    # the fact it asserts is recomputed here from the run, so a retuned scenario that made the
    # note untrue fails a test instead of quietly narrating something that did not happen.
    note_config = config["officer_note"]
    note_member = scenario.member(note_config["member_id"])
    paid_short = any(
        actual.states[w][note_member.id]["unpaid"] > 0
        or actual.states[w][note_member.id]["cover_received"] > 0
        for w in range(1, decision_week + 1)
    )
    officer_note = {
        "week": decision_week,
        "member_id": note_member.id,
        "text": note_config["text"].format(name=note_member.name),
        "claims_paid_in_full": note_config["claims_paid_in_full"],
        "paid_in_full_so_far": not paid_short,
        "buffer_start": note_member.savings_buffer,
        "buffer_at_note": actual.states[decision_week][note_member.id]["buffer"],
    }

    # 7. The case that is nobody's fault and nobody's contagion.
    independent = [r for r in attribution if r["label"] == INDEPENDENT]

    story = {
        "config": config,
        "params": {
            "horizon_weeks": params.horizon_weeks,
            "amber": params.amber,
            "red": params.red,
            "r_window_weeks": params.r_window_weeks,
        },
        "scenario": {
            "members": _roster(scenario),
            "layout": {mid: list(xy) for mid, xy in scenario.layout.items()},
            "edges": _edges(scenario),
            "kendras": scenario.kendras(),
        },
        "opening": {
            "all_green": not _flagged(scenario, baseline, as_of_week=1),
            "flagged_at_week_one": _flagged(scenario, baseline, as_of_week=1),
            "r_potential": {row["kendra_id"]: row["r_potential"] for row in baseline_rows},
            "most_exposed_kendra": most_exposed["kendra_id"],
            "most_exposed_r_potential": most_exposed["r_potential"],
            "most_exposed_tied_with": tied_with,
        },
        "shock": {
            "sentence": shock_sentence(scenario, shocks[0], params),
            "shocks": [
                {
                    "type": s.type,
                    "member_id": s.member_id,
                    "member_name": scenario.member(s.member_id).name if s.member_id else None,
                    "income_source": s.income_source,
                    "start_week": s.start_week,
                    "severity": s.resolve(params)[0],
                    "duration_weeks": s.resolve(params)[1],
                }
                for s in shocks
            ],
        },
        "actual": {
            "weeks": _weeks(actual, scenario),
            "timeline": _timeline(scenario, actual),
            "flagged": _flagged(scenario, actual),
            "rupees_at_risk": actual_at_risk,
            "rupees_at_risk_text": format_rs(actual_at_risk),
        },
        "attribution": attribution,
        "r": rows,
        "shocked_kendra": shocked_kendra,
        "officer_note": officer_note,
        "smallest_fix": {"decision_week": decision_week, "ranked": ranked, "applied": applied},
        "independent_cases": [r["member_id"] for r in independent],
        "build_seconds": time.perf_counter() - started,
    }
    return _plain(story)


def r_display_series(story, kendra_id):
    """[{week, kind, value}] for one kendra, as the UI would label it week by week.

    Lives here so the script and the frontend agree on when the number on screen stops being
    R potential and becomes R live.
    """
    row = next(r for r in story["r"] if r["kendra_id"] == kendra_id)
    return [
        {"week": week, **r_for_display(row, week)}
        for week in range(1, story["params"]["horizon_weeks"] + 1)
    ]
