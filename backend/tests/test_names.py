"""Changing the names must change nothing but the names.

Names are drawn from the generator's RNG before every income, buffer and loan draw, so the
only safe way to rename the roster is a same size, same position swap of the name lists. This
test rebuilds the whole demo story with the previous (Jharkhand) lists and with the current
(Karnataka) ones, maps every full name to its member id, and requires the two to be identical:
weekly states, event log, attribution, stability badges, R numbers and the smallest fix.
"""

import json

import pytest

import sim.generator as generator
from demo.story import build_story, load_config

# The lists as they were before the Karnataka swap, kept here as the reference world.
PREVIOUS_FIRST_NAMES = (
    "Lakshmi", "Sunita", "Meena", "Radha", "Kavita", "Anita", "Savita", "Pushpa",
    "Rekha", "Geeta", "Sarita", "Mamta", "Usha", "Nirmala", "Shanti", "Kamala",
    "Vimla", "Asha", "Prema", "Sudha", "Rani", "Jyoti", "Manju", "Babita", "Seema",
)
PREVIOUS_LAST_NAMES = (
    "Devi", "Kumari", "Bai", "Yadav", "Mahato", "Oraon", "Singh",
    "Murmu", "Hansda", "Kisku", "Tudu", "Soren",
)

# Every part of the story that comes out of a run. `config` and `scenario` are compared too;
# `build_seconds` is a stopwatch reading.
COMPARED = (
    "actual", "attribution", "r", "smallest_fix", "opening", "shock", "officer_note",
    "independent_cases", "scenario", "config",
)


def _scrubbed(story):
    """The story as JSON with every full name replaced by its member id, longest first so a
    short name can never eat part of a longer one."""
    names = sorted(
        ((m["name"], m["id"]) for m in story["scenario"]["members"]),
        key=lambda pair: -len(pair[0]),
    )
    out = {}
    for key in COMPARED:
        text = json.dumps(story[key], sort_keys=True)
        for name, member_id in names:
            text = text.replace(name, f"<{member_id}>")
        out[key] = text
    return out


@pytest.fixture(scope="module")
def both_stories():
    current = build_story()
    saved = generator.FIRST_NAMES, generator.LAST_NAMES
    try:
        generator.FIRST_NAMES, generator.LAST_NAMES = PREVIOUS_FIRST_NAMES, PREVIOUS_LAST_NAMES
        previous = build_story()
    finally:
        generator.FIRST_NAMES, generator.LAST_NAMES = saved
    return previous, current


def test_the_name_lists_kept_their_sizes():
    assert len(generator.FIRST_NAMES) == len(PREVIOUS_FIRST_NAMES)
    assert len(generator.LAST_NAMES) == len(PREVIOUS_LAST_NAMES)
    assert len(set(generator.FIRST_NAMES)) == len(generator.FIRST_NAMES)
    assert len(set(generator.LAST_NAMES)) == len(generator.LAST_NAMES)


def test_the_names_actually_changed(both_stories):
    previous, current = both_stories
    before = [m["name"] for m in previous["scenario"]["members"]]
    after = [m["name"] for m in current["scenario"]["members"]]
    assert all(b != a for b, a in zip(before, after))
    by_id = {m["id"]: m["name"] for m in current["scenario"]["members"]}
    assert by_id["m010"].startswith("Lakshmi ")
    assert by_id["m011"].startswith("Savitha ")
    assert by_id["m002"].startswith("Meena ")


@pytest.mark.parametrize("key", COMPARED)
def test_everything_but_the_names_is_identical(both_stories, key):
    previous, current = both_stories
    assert _scrubbed(previous)[key] == _scrubbed(current)[key], key


# ---------------------------------------------------------------------------------------
# display_name_overrides: unique first names on screen, nothing else moves
# ---------------------------------------------------------------------------------------

# The six members the story is told about keep the names the video uses.
STORY_NAMES = {
    "m010": "Lakshmi", "m011": "Savitha", "m012": "Roopa",
    "m014": "Latha", "m002": "Meena", "m004": "Suma",
}


def test_every_first_name_is_unique_across_the_branch(both_stories):
    _, current = both_stories
    firsts = [m["name"].split(" ")[0] for m in current["scenario"]["members"]]
    duplicates = sorted({f for f in firsts if firsts.count(f) > 1})
    assert duplicates == []


def test_the_story_members_keep_their_first_names(both_stories):
    _, current = both_stories
    by_id = {m["id"]: m["name"].split(" ")[0] for m in current["scenario"]["members"]}
    assert {mid: by_id[mid] for mid in STORY_NAMES} == STORY_NAMES


@pytest.fixture(scope="module")
def with_and_without_overrides(both_stories):
    _, current = both_stories
    config = load_config()
    assert config["display_name_overrides"], "the demo config should carry name overrides"
    config.pop("display_name_overrides")
    return build_story(config=config), current


@pytest.mark.parametrize("key", [k for k in COMPARED if k != "config"])
def test_name_overrides_change_nothing_but_names(with_and_without_overrides, key):
    plain, overridden = with_and_without_overrides
    assert _scrubbed(plain)[key] == _scrubbed(overridden)[key], key
