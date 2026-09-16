# NEXT

Running note of where the build is. Update at the end of every phase.

## Done

- **Phase 0** skeleton: folders, requirements, pytest wired, `.gitignore`.
- **Phase 1** `params.py`, `generator.py`, `engine.py` with common random numbers and the
  event log. Later fixed so marginal transmission is visible: cover is settled at the
  kendra meeting out of the cash a peer brought for her OWN installment first, then out of
  savings, so helping a neighbour actually costs her something.
- **Phase 2 part 1** `attribution.py` + `tests/test_attribution.py`.
- **Phase 2 part 2** `r_number.py` + `tests/test_r_number.py`. 74 tests pass. Phase 2 is done.

## Phase 2 part 1: what attribution does now

A **cause** is a member's own shocks PLUS her own negative income trend. That second half
is a revision, not a detail. In the seeded baseline (`generate_scenario()`, draws seed 1)
m004 flags in week 12 with no shock planted anywhere, purely because she covered m002 at
the meeting and m002's income is eroding. A shocks only procedure would run the no shock
world, find m004 still flagged and call her INDEPENDENT. She is the clearest TRANSMITTED
case in the demo. A trend is neutralised by setting it to 0. A POSITIVE trend is never a
cause and is never neutralised.

Procedure for each member flagged in the actual run up to `as_of_week`:

1. Run the world holding only HER causes. Not flagged there -> TRANSMITTED (step 2).
   Flagged there, and removing all her own shocks unflags her -> INDEX. Otherwise
   INDEPENDENT.
2. TRANSMITTED: for every other member with a cause, run actual minus that member's
   causes. Source = largest drop in this member's peak stress. `sole_source` is whether
   removing that source alone unflags her; the top 2 contributors come back either way.
3. Path: temporal walk of the event log from source to member, falling back to the
   shortest graph path (marked `inferred`).

Record: `{member_id, label, source_id, source_cause, sole_source, path, first_flag_week,
tags, contributors}`. `source_id` is the member's own id for INDEX and INDEPENDENT, so
`source_cause` ("shock" | "trend") always says which of her own causes it was.

Two decisions worth remembering, both visible in the tests:

- **Necessity is judged at the week her own causes first put her over, not at
  `as_of_week`.** A member hit by a weak monsoon in week 2 whose trend would also have
  caught up with her by week 11 is INDEX at every point on the slider. Judging at
  `as_of_week` made her flip to INDEPENDENT once the slider passed week 11.
- **Stress travels against the money on a guarantee edge.** The event log records cover as
  giver -> receiver, but it is the GIVER who ends up short, so explanation paths walk
  guarantee edges backwards and shared_lender edges forwards.

All worlds are cached in `_Worlds` and every one of them is handed the same `draws` object;
a test asserts identity, not equality.

## Phase 2 part 2: what the R numbers count

`r_numbers(scenario, shocks, draws, params, as_of_week, records)` returns one row per
kendra: `{kendra_id, r_potential, r_live_by_week, primary_ids, transmitted_ids}`.
`r_live_by_week` is a list of 12 entries, week 1 first. `r_for_display(row, week)` returns
`{kind, value}` so a screen never shows a number the viewer cannot name.

Four definitions that refine the build contract, each pinned by a test:

- **A primary case is INDEX or INDEPENDENT, not only INDEX.** A declining income starts a
  chain the same way a hospital bill does. In the seeded baseline m002 (INDEPENDENT)
  is the source of m004 (TRANSMITTED); counting only INDEX cases would leave an onward
  case in the numerator with a zero denominator.
- **R live is None, never 0.0, when a kendra has no primary case yet.** 0.0 would read as
  "not spreading" for a kendra where nothing has happened. None is what tells the UI to
  show R potential instead.
- **An onward case only counts once its SOURCE is a counted case too.** m004 flags in week
  12 and m002 in week 11, so k0 reads 0.0 in week 11 and 1.0 in week 12.
- **A kendra owns an onward case through its source, not through where the case lives**, so
  cross kendra transmission is charged to the group the stress came from.

R potential plants one standard health shock (`health`, defaults, week 1) on each member in
turn and counts her KENDRA PEERS who are newly flagged inside `r_window_weeks`, judged
against a no shock baseline on the same draws. Three deliberate choices:

- **Newly flagged, same window in both worlds.** Members already in trouble (m004) must not
  count, or a kendra whose members were already struggling would score as the most robust.
- **Peers inside the kendra only**, so the number is bounded by `members_per_kendra - 1`
  and the UI can draw it as a fraction of the ring. R live is the one that counts onward
  cases landing in other kendras; mixing the two scales in one figure would be unreadable.
- **The scenario's own shocks are ignored.** R potential is a property of the roster and
  the network, which is what keeps it defined when everybody is green.

`r_window_weeks = 4` is the right window, not a guess: on the demo scenario the counts
saturate at 4 (identical at 6, 8 and 12) and 4 is where the kendras separate most, k0 and
k1 at 0.2 against k2 and k4 at 1.2. Same draws in every probe world; a test asserts
identity of the array, not equality.

## Next

- **Phase 3**: `interventions.py`, `smallest_fix.py`, `stability.py`, then
  `scripts/demo_story.py`. That script is the gate: if it tells the story in the terminal,
  the prototype exists.
- Start with `interventions.py`. `engine.simulate` currently raises
  `NotImplementedError` on a non empty `interventions` list, so the first job is to make
  moratorium, reschedule and scheme_linkage change `weekly_due` per member per week inside
  Pass A, keeping the draws contract untouched. Then `smallest_fix.py` ranks every member x
  type x parameter grid by members protected desc, lender cost asc, and reports the new R
  by calling `r_numbers` on the replay.

## Handy while working

```
cd backend && .venv/Scripts/python.exe -m pytest
```

Demo baseline that exercises the trend as a cause: `generate_scenario()` with
`make_draws(25, DEFAULT, seed=1)` and no shocks -> m002 INDEPENDENT, m004 TRANSMITTED.
