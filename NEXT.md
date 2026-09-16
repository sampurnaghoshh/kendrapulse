# NEXT

Running note of where the build is. Update at the end of every phase.

## Done

- **Phase 0** skeleton: folders, requirements, pytest wired, `.gitignore`.
- **Phase 1** `params.py`, `generator.py`, `engine.py` with common random numbers and the
  event log. Later fixed so marginal transmission is visible: cover is settled at the
  kendra meeting out of the cash a peer brought for her OWN installment first, then out of
  savings, so helping a neighbour actually costs her something.
- **Phase 2 part 1** `attribution.py` + `tests/test_attribution.py`. 58 tests pass.

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

## Next

- **Phase 2 part 2**: `sim/r_number.py`. R live and R potential per the build contract,
  tests on the same hand built scenarios.
- Then **Phase 3**: interventions, smallest fix, stability, and `scripts/demo_story.py`.
  That script is the gate: if it tells the story in the terminal, the prototype exists.

## Handy while working

```
cd backend && .venv/Scripts/python.exe -m pytest
```

Demo baseline that exercises the trend as a cause: `generate_scenario()` with
`make_draws(25, DEFAULT, seed=1)` and no shocks -> m002 INDEPENDENT, m004 TRANSMITTED.
