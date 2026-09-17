"""The gate, tested: is the story reproducible, and can it cross a wire?

Two properties matter here and nothing else. If `build_story()` is not deterministic the demo
is a different demo every time it runs, and if it is not JSON serialisable Phase 5 cannot
serve it and Phase 6 has nothing to draw.
"""

import json

import pytest

from demo.story import (
    apply_member_overrides,
    build_story,
    format_rs,
    load_config,
    moved_out_of_stress,
    r_display_series,
)
from sim.attribution import INDEPENDENT, INDEX, TRANSMITTED

# Hyphen, en dash, em dash. Anything a viewer reads must contain none of them.
DASHES = ("-", "–", "—")


@pytest.fixture(scope="module")
def story():
    return build_story()


# ------------------------------------------------------------------------------------
# The two properties the rest of the build depends on
# ------------------------------------------------------------------------------------


def test_the_story_is_deterministic(story):
    """Same config, same story. The only randomness is the two seeds in the config file.

    build_seconds is excluded because it is a stopwatch reading, not part of the story.
    """
    again = build_story()
    assert set(story) == set(again)
    for key in story:
        if key == "build_seconds":
            continue
        assert story[key] == again[key], key


def test_the_story_is_json_serialisable(story):
    """The engine indexes a numpy array, so most of its floats are numpy scalars and
    json.dumps refuses them. This is the test that keeps the boundary honest."""
    encoded = json.dumps(story)
    assert json.loads(encoded)["shocked_kendra"] == story["shocked_kendra"]
    assert len(encoded) > 10_000, "a story this small is not the whole story"


def test_the_config_holds_inputs_only(story):
    """Nothing in data/demo_scenario.json may be an output. If a result were pinned there,
    the demo would be asserting its own conclusion."""
    config = load_config()
    assert story["config"] == config
    assert set(config) >= {"generator", "draws_seed", "shocks", "decision_week", "stability"}
    text = json.dumps(config)
    for word in ("r_potential", "r_live", "members_protected", "flagged", "lender_cost"):
        assert word not in text


# ------------------------------------------------------------------------------------
# The story actually tells the story
# ------------------------------------------------------------------------------------


def test_the_opening_frame_is_green_with_an_r_potential_above_one(story):
    """Section 1 of the script. If anybody were already flagged in week 1, or if the most
    exposed kendra scored below 1, the opening claim would not hold."""
    opening = story["opening"]
    assert opening["all_green"]
    assert opening["flagged_at_week_one"] == []
    assert opening["most_exposed_r_potential"] > 1.0
    assert opening["r_potential"][opening["most_exposed_kendra"]] == pytest.approx(
        opening["most_exposed_r_potential"]
    )


def test_the_shock_lands_in_a_kendra_with_the_highest_r_potential(story):
    """The whole point of planting it there: the shock goes where the network says it would
    spread furthest, and the opening number is the one that predicted it."""
    opening = story["opening"]
    highest = max(opening["r_potential"].values())
    assert opening["r_potential"][story["shocked_kendra"]] == pytest.approx(highest)


def test_all_three_labels_appear(story):
    """A demo that cannot show one of its three labels is not demonstrating the idea."""
    labels = {record["label"] for record in story["attribution"]}
    assert labels == {INDEX, TRANSMITTED, INDEPENDENT}


def test_every_flagged_member_has_a_sentence_and_a_badge(story):
    flagged = set(story["actual"]["flagged"])
    assert {record["member_id"] for record in story["attribution"]} == flagged
    for record in story["attribution"]:
        assert record["sentence"].startswith(record["name"])
        assert record["badge_text"].startswith("flagged in ")
        assert "same cause in" in record["badge_text"]
        assert record["stability"]["n_runs"] == story["config"]["stability"]["n_runs"]


def test_the_transmitted_sentences_name_a_person_a_channel_and_a_week(story):
    """"Transmitted" on its own is a claim. Those three details are the evidence for it."""
    transmitted = [r for r in story["attribution"] if r["label"] == TRANSMITTED]
    assert transmitted, "the demo has no transmitted case, which is the case it exists to show"
    for record in transmitted:
        source_name = next(
            m["name"] for m in story["scenario"]["members"] if m["id"] == record["source_id"]
        )
        assert source_name in record["sentence"]
        assert "transmitted from" in record["sentence"]
        assert f"week {record['first_flag_week']}" in record["sentence"]


def test_r_live_is_undefined_before_the_first_case_and_defined_after(story):
    """Section 5. The screen shows R potential until there is something to divide by."""
    series = r_display_series(story, story["shocked_kendra"])
    kinds = [point["kind"] for point in series]
    assert kinds[0] == "potential"
    assert "live" in kinds
    # It never goes back: once a kendra has a case, it has one for the rest of the horizon.
    first_live = kinds.index("live")
    assert all(kind == "live" for kind in kinds[first_live:])
    assert all(point["value"] is not None for point in series)


def test_the_top_fix_protects_somebody_and_leaves_the_index_case_flagged(story):
    """The honest shape of the result. A lender can stop the spread; it cannot undo an
    illness, and a demo claiming otherwise would be selling a fantasy."""
    applied = story["smallest_fix"]["applied"]
    assert applied is not None
    assert applied["members_protected"]
    assert set(applied["flagged_after"]) < set(applied["flagged_before"])
    assert applied["rupees_at_risk_after"] < applied["rupees_at_risk_before"]

    index_ids = {r["member_id"] for r in story["attribution"] if r["label"] == INDEX}
    assert index_ids <= set(applied["flagged_after"]), "the index case should still be flagged"


def test_the_ranked_fixes_are_ordered_and_numbered(story):
    ranked = story["smallest_fix"]["ranked"]
    assert 1 <= len(ranked) <= 3
    assert [entry["rank"] for entry in ranked] == list(range(1, len(ranked) + 1))
    keys = [(-len(e["members_protected"]), e["lender_cost"]) for e in ranked]
    assert keys == sorted(keys)


def test_the_scenario_block_carries_what_the_frontend_draws(story):
    scenario = story["scenario"]
    member_ids = {m["id"] for m in scenario["members"]}
    assert len(member_ids) == 25
    assert set(scenario["layout"]) == member_ids
    assert all(len(xy) == 2 for xy in scenario["layout"].values())
    assert {edge["type"] for edge in scenario["edges"]} == {
        "guarantee", "shared_income", "shared_lender"
    }
    for edge in scenario["edges"]:
        assert edge["from_id"] in member_ids and edge["to_id"] in member_ids
    # Every panel reads positions from here, so two panels cannot disagree about a node.
    assert len(scenario["layout"]) == len(member_ids)


def test_every_week_of_the_horizon_has_a_state_for_every_member(story):
    weeks = story["actual"]["weeks"]
    assert sorted(int(w) for w in weeks) == list(range(1, story["params"]["horizon_weeks"] + 1))
    member_ids = {m["id"] for m in story["scenario"]["members"]}
    for week_row in weeks.values():
        assert set(week_row) == member_ids
        assert all(row["status"] in ("green", "amber", "red") for row in week_row.values())


# ------------------------------------------------------------------------------------
# Copy that goes on screen
# ------------------------------------------------------------------------------------


def test_rupees_use_indian_digit_grouping():
    """Lakh grouping, not thousands. The audience reads portfolio numbers this way."""
    assert format_rs(273172) == "Rs 2,73,172"
    assert format_rs(420707) == "Rs 4,20,707"
    assert format_rs(58127) == "Rs 58,127"
    assert format_rs(999) == "Rs 999"
    assert format_rs(1000) == "Rs 1,000"
    assert format_rs(12345678) == "Rs 1,23,45,678"
    assert format_rs(0) == "Rs 0"


def test_money_is_moved_out_of_stress_and_never_saved():
    """Never "saved" and never "loss avoided": both would claim the lender banked a number
    we have not measured."""
    text = moved_out_of_stress(273172)
    assert text == "Rs 2,73,172 of loans moved out of stress"
    for word in ("saved", "loss", "avoided", "profit", "recovered"):
        assert word not in text.lower()


def test_no_sentence_the_viewer_reads_contains_a_hyphen_or_a_dash(story):
    """It appears in the judged video. Ids and channel keys are identifiers, not prose, so
    only the prose fields are checked."""
    prose = [
        story["shock"]["sentence"],
        story["actual"]["rupees_at_risk_text"],
    ]
    prose += [record["sentence"] for record in story["attribution"]]
    prose += [record["badge_text"] for record in story["attribution"]]
    prose += [entry["sentence"] for entry in story["smallest_fix"]["ranked"]]
    prose += [entry["description"] for entry in story["smallest_fix"]["ranked"]]
    prose += [entry["moved_text"] for entry in story["smallest_fix"]["ranked"]]
    prose += [entry["lender_cost_text"] for entry in story["smallest_fix"]["ranked"]]
    if story["smallest_fix"]["applied"]:
        prose += [
            story["smallest_fix"]["applied"]["description"],
            story["smallest_fix"]["applied"]["moved_text"],
        ]

    for sentence in prose:
        for dash in DASHES:
            assert dash not in sentence, sentence


def test_no_member_name_contains_a_dash(story):
    """A generated name with a hyphen in it would put one on screen through the back door."""
    for member in story["scenario"]["members"]:
        for dash in DASHES:
            assert dash not in member["name"]


# ------------------------------------------------------------------------------------
# The tuned scenario keeps its story (scripts/tune_demo.py checks the same things)
# ------------------------------------------------------------------------------------


def test_the_hero_kendra_is_where_the_transmitted_cases_are(story):
    """Retuning the shock must not move the story out of the shocked kendra, and must not
    spill flags into other kendras beyond the k0 pair that was already there."""
    kendra_of = {m["id"]: m["kendra_id"] for m in story["scenario"]["members"]}
    heroes = [
        r for r in story["attribution"]
        if r["label"] == TRANSMITTED and r["kendra_id"] == story["shocked_kendra"]
    ]
    assert len(heroes) >= 2
    outside = {mid for mid in story["actual"]["flagged"] if kendra_of[mid] != story["shocked_kendra"]}
    assert outside <= {"m002", "m004"}
    # When a hero is flagged, we name the same neighbour almost every time.
    for record in heroes:
        assert record["stability"]["source_agreement"] > 0.9


def test_m002_is_still_the_independent_case(story):
    by_id = {r["member_id"]: r for r in story["attribution"]}
    assert by_id["m002"]["label"] == INDEPENDENT


def test_the_top_fix_protects_at_least_two_members(story):
    assert len(story["smallest_fix"]["applied"]["members_protected"]) >= 2


def test_every_record_carries_what_the_simple_rule_would_say(story):
    """Reported beside the label, never used to make it."""
    for record in story["attribution"]:
        assert record["simple_rule"]["label"] in (INDEX, TRANSMITTED, INDEPENDENT)


# ------------------------------------------------------------------------------------
# Member overrides: a disclosed edit to the seeded roster
# ------------------------------------------------------------------------------------


def test_member_overrides_apply_and_leave_everyone_else_alone():
    from sim.generator import generate_scenario

    scenario = generate_scenario(n_kendras=5, members_per_kendra=5, seed=42)
    changed = apply_member_overrides(
        scenario, [{"member_id": "m011", "savings_buffer": 123.0, "reason": "probe"}]
    )
    assert changed.member("m011").savings_buffer == 123.0
    for member in scenario.members:
        if member.id != "m011":
            assert changed.member(member.id) == member
    assert apply_member_overrides(scenario, None) is scenario


def test_member_overrides_need_a_reason_and_a_real_field():
    from sim.generator import generate_scenario

    scenario = generate_scenario(n_kendras=5, members_per_kendra=5, seed=42)
    with pytest.raises(ValueError):
        apply_member_overrides(scenario, [{"member_id": "m011", "savings_buffer": 1.0}])
    with pytest.raises(ValueError):
        apply_member_overrides(scenario, [{"member_id": "m011", "luck": 1.0, "reason": "x"}])
    with pytest.raises(ValueError):
        apply_member_overrides(scenario, [{"member_id": "m011", "id": "m999", "reason": "x"}])


# ------------------------------------------------------------------------------------
# The officer's note and the lender freeze
# ------------------------------------------------------------------------------------


def test_the_officer_note_matches_the_run(story):
    """The note is written by hand in the config, so the run has to back it up. If a retuned
    scenario makes her pay short before the meeting, the note must be rewritten."""
    note = story["officer_note"]
    assert note["week"] == story["smallest_fix"]["decision_week"]
    assert note["claims_paid_in_full"] == note["paid_in_full_so_far"]
    if note["claims_paid_in_full"]:
        # "but out of her savings": she must actually have spent them.
        assert note["buffer_at_note"] < note["buffer_start"]
    name = next(m["name"] for m in story["scenario"]["members"] if m["id"] == note["member_id"])
    assert note["text"].startswith(name)
    for dash in DASHES:
        assert dash not in note["text"]


def test_lender_freezes_carry_the_kendra_they_came_from(story):
    """The freeze line names a kendra, never a person, so every freeze event needs one."""
    kendra_of = {m["id"]: m["kendra_id"] for m in story["scenario"]["members"]}
    freezes = [
        e for week in story["actual"]["timeline"] for e in week["events"]
        if e["channel"] == "shared_lender"
    ]
    assert freezes
    for event in freezes:
        assert event["from_kendra_id"] == kendra_of[event["from_id"]]
        assert kendra_of[event["to_id"]] != event["from_kendra_id"]
