"""The static snapshot: valid JSON, and its extra worlds are real engine runs.

The counterfactual worlds are checked against runs built HERE, independently of `_Worlds`:
a fresh scenario, a freshly built draws array from the seed, the shock list filtered and the
negative trends zeroed by hand. If the snapshot's world matches that, the Two worlds view is
showing an actual replay and not something the export quietly assembled.
"""

import json
from dataclasses import replace

import pytest

from demo.snapshot import SNAPSHOT_PATH, build_snapshot, round_floats
from demo.story import _plain, _weeks, apply_member_overrides, load_config, setup_world
from sim.attribution import INDEPENDENT, INDEX, TRANSMITTED, expand_shocks
from sim.engine import make_draws, simulate
from sim.generator import generate_scenario
from sim.params import DEFAULT

DASHES = ("-", "–", "—")


@pytest.fixture(scope="module")
def snapshot():
    return build_snapshot()


def _fresh_world(member_id, label, source_id):
    """The label's world, rebuilt from scratch without any attribution machinery."""
    config = load_config()
    scenario = generate_scenario(
        n_kendras=config["generator"]["n_kendras"],
        members_per_kendra=config["generator"]["members_per_kendra"],
        seed=config["generator"]["seed"],
    )
    scenario = apply_member_overrides(scenario, config.get("member_overrides"))
    _, _, shocks = setup_world(config)
    shocks = expand_shocks(scenario, shocks)
    draws = make_draws(scenario.n_members, DEFAULT, seed=config["draws_seed"])  # fresh array

    if label == TRANSMITTED:
        # Reality minus the source: her shocks gone, her negative trend zeroed.
        kept_shocks = [s for s in shocks if s.member_id != source_id]
        members = tuple(
            replace(m, income_trend=0.0) if m.id == source_id and m.income_trend < 0 else m
            for m in scenario.members
        )
    else:
        # Only her own life: her shocks and her trend, every other negative trend zeroed.
        kept_shocks = [s for s in shocks if s.member_id == member_id]
        members = tuple(
            replace(m, income_trend=0.0) if m.id != member_id and m.income_trend < 0 else m
            for m in scenario.members
        )
    world = replace(scenario, members=members)
    run = simulate(world, kept_shocks, [], DEFAULT, draws)
    return run, world


def test_the_snapshot_is_valid_json_and_round_trips(snapshot):
    text = json.dumps(snapshot, separators=(",", ":"))
    assert json.loads(text) == snapshot


def test_the_written_file_is_valid_json_when_present():
    if not SNAPSHOT_PATH.exists():
        pytest.skip("snapshot not exported yet")
    data = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert {"counterfactual_worlds", "fix_replays", "ever_flagged_by_week", "meta"} <= set(data)


def test_every_counterfactual_world_matches_a_fresh_engine_run(snapshot):
    records = {r["member_id"]: r for r in snapshot["attribution"]}
    assert set(snapshot["counterfactual_worlds"]) == set(records)
    for member_id, world in snapshot["counterfactual_worlds"].items():
        record = records[member_id]
        assert world["label"] == record["label"]
        if record["label"] == TRANSMITTED:
            assert world["kind"] == "without_source"
            assert world["removed_member_id"] == record["source_id"]
        else:
            assert record["label"] in (INDEX, INDEPENDENT)
            assert world["kind"] == "only_own_causes"
        run, scenario = _fresh_world(member_id, record["label"], record["source_id"])
        assert world["weeks"] == round_floats(_plain(_weeks(run, scenario))), member_id


def test_the_counterfactual_worlds_tell_the_label(snapshot):
    """A transmitted member is not flagged once her source is removed; an index or independent
    member is flagged in the world holding only her own causes."""
    for member_id, world in snapshot["counterfactual_worlds"].items():
        flagged_there = world["ever_flagged_by_week"][member_id][-1]
        if world["label"] == TRANSMITTED:
            assert not flagged_there, member_id
        else:
            assert flagged_there, member_id


def test_ever_flagged_by_week_is_monotone_and_matches_the_flagged_list(snapshot):
    ever = snapshot["ever_flagged_by_week"]
    horizon = snapshot["params"]["horizon_weeks"]
    for member_id, series in ever.items():
        assert len(series) == horizon
        assert all(not a or b for a, b in zip(series, series[1:]))  # never switches off
    assert sorted(m for m, s in ever.items() if s[-1]) == sorted(snapshot["actual"]["flagged"])


def test_each_top_fix_has_its_replay_once(snapshot):
    ranked = snapshot["smallest_fix"]["ranked"]
    replays = snapshot["fix_replays"]
    assert [r["rank"] for r in replays] == [e["rank"] for e in ranked]
    assert all("weeks" not in e for e in ranked)
    assert "weeks" not in snapshot["smallest_fix"]["applied"]
    for replay, entry in zip(replays, ranked):
        assert replay["intervention"] == entry["intervention"]
        protected = set(entry["members_protected"])
        assert not any(replay["ever_flagged_by_week"][m][-1] for m in protected)


def test_floats_are_rounded_to_three_decimals(snapshot):
    def floats(value):
        if isinstance(value, dict):
            for v in value.values():
                yield from floats(v)
        elif isinstance(value, list):
            for v in value:
                yield from floats(v)
        elif isinstance(value, float):
            yield value

    assert all(round(x, 3) == x for x in floats(snapshot))


def test_validation_and_meta_are_carried(snapshot):
    validation = snapshot["validation"]
    assert validation is not None
    assert "not of accuracy on real borrowers" in validation["what_this_is"]
    for subset in ("same_subset", "all_observed"):
        for party, counts in validation[subset]["overall"].items():
            assert set(counts) == {"correct", "of"}
            assert 0 <= counts["correct"] <= counts["of"]
    meta = snapshot["meta"]
    assert {"generated_at", "git_commit", "generator_seed", "draws_seed"} <= set(meta)


def test_world_titles_have_no_hyphen_or_dash(snapshot):
    for world in snapshot["counterfactual_worlds"].values():
        for dash in DASHES:
            assert dash not in world["title"]
