# NEXT

Running note of where the build is. Update at the end of every phase.

## Done

- **Phase 0** skeleton: folders, requirements, pytest wired, `.gitignore`.
- **Phase 1** `params.py`, `generator.py`, `engine.py` with common random numbers and the
  event log. Later fixed so marginal transmission is visible: cover is settled at the
  kendra meeting out of the cash a peer brought for her OWN installment first, then out of
  savings, so helping a neighbour actually costs her something.
- **Phase 2 part 1** `attribution.py` + `tests/test_attribution.py`.
- **Phase 2 part 2** `r_number.py` + `tests/test_r_number.py`. Phase 2 is done.
- **Phase 3 part 1** `interventions.py` + `smallest_fix.py` (moratorium and reschedule),
  the engine now applies interventions, R live rescoped to the kendra. 110 tests pass.

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
kendra: `{kendra_id, r_potential, r_live_by_week, cross_kendra_reach_by_week, primary_ids,
transmitted_ids, cross_kendra_ids}`.
`r_live_by_week` is a list of 12 entries, week 1 first. `r_for_display(row, week)` returns
`{kind, value}` so a screen never shows a number the viewer cannot name.

Five definitions that refine the build contract, each pinned by a test:

- **A primary case is INDEX or INDEPENDENT, not only INDEX.** A declining income starts a
  chain the same way a hospital bill does. In the seeded baseline m002 (INDEPENDENT)
  is the source of m004 (TRANSMITTED); counting only INDEX cases would leave an onward
  case in the numerator with a zero denominator.
- **R live counts only onward cases INSIDE the source's kendra**, which puts it on the same
  scale as R potential. The UI shows one number per cluster and swaps between the two the
  moment a case appears, so if R live counted the whole branch while R potential counted
  peers, the figure under a kendra would silently change meaning. Stress that crossed into
  another kendra is reported by `cross_kendra_reach_by_week`: same denominator, so the two
  read as a pair, and it is the number that makes the shared lender channel visible at all
  (guarantee cover cannot leave a kendra, so anything counted there arrived through a
  lender freezing top ups). `transmitted_ids` and `cross_kendra_ids` split the same way.
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

## Phase 3 part 1: interventions and the smallest fix

`Intervention(type, member_id, start_week, weeks | installment_fraction)`, frozen, built by
`moratorium(member_id, start_week, weeks)` or
`reschedule(member_id, start_week, installment_fraction)`. Only these two for now;
`scheme_linkage` is deferred because it needs an income side effect and the two due side
actions already tell the story.

**An intervention changes exactly one quantity: `due`.** That is the only engine change
(`sim/engine.py` Pass A multiplies `m.weekly_due` by `due_multiplier(...)`, and the
`NotImplementedError` guard is gone). Everything else that moves has to move because `due`
moved. The sharpest test of it is a reschedule with `installment_fraction=1.0`, which must
replay float for float identically to no intervention.

- **Moratorium**: installments are 0 for `weeks` weeks. The deferred money goes to the END
  of the loan tenure, far beyond a 12 week horizon, so it never comes due again inside the
  simulation. That is how MFI moratoriums actually work; making it repayable in week
  `start + weeks` would be a much harsher product and would show a cliff that is not there.
- **Reschedule**: a smaller installment from `start_week` to the horizon end. It does not
  expire, because a rescheduled loan is re papered over a longer tenure.

**The observation window is the rule that keeps the metrics honest.** An intervention is
only valid if it ends at least `r_window_weeks` before the horizon ends. A moratorium
running to week 12 would "protect" a member by deleting every payment she could have missed
inside the chart; her arrears reappear in week 13, where nothing is measured. A reschedule
counts as ending at `start_week`, because from that week she is paying again and everything
later is already observation. With horizon 12 and window 4: moratoriums must stop deferring
by week 8, and reschedules must start by week 8. At `decision_week=10` the candidate list is
empty, and an empty list is the honest answer.

**Lender cost is one formula for both types**: rupees moved x `carry_cost_rate` x weeks from
the week it was due to the horizon end. Deferring money does not destroy it, so the lender
only loses the use of that rupee. Consequence that matters to the ranking: the same fix
granted later costs less.

`smallest_fix(scenario, shocks, params, draws, decision_week)` returns the top 3, each
`{intervention, members_protected, lender_cost, rupees_at_risk_avoided, run,
r_live_by_week, cross_kendra_reach_by_week}`.

- One actual run, one replay per candidate, all on the SAME draws object (asserted by
  identity across both `smallest_fix` and `attribution`). A protected member is protected by
  the fix, never by the dice.
- **Rejection is absolute.** A candidate that newly flags ANYBODY is dropped before ranking,
  at any cost saving. A candidate that protects nobody is dropped too: a cost on screen next
  to no benefit is not an offer.
- Rank: members protected desc, lender cost asc, lighter fix, roster index. The last two are
  there only so the demo shows the same three fixes in the same order every run. Protection
  is a small integer, so ties are the normal case and the cost tiebreak is doing most of the
  real work.
- `rupees_at_risk(run)` is the total OUTSTANDING of everyone flagged, not the missed
  installment: once a joint liability borrower is in distress, the exposure at stake is the
  loan.
- New R comes from `attribute(..., interventions=(fix,))`, computed for the shortlist only
  because attribution is the expensive part. `attribute` and `_Worlds` gained an optional
  `interventions` argument that is held FIXED across every counterfactual, so the labels
  still answer "what caused this", not "what would the fix have done".

## Tomorrow: scenario tuning for the demo

**Plant the demo shock in the kendra with the highest R potential.** On `generate_scenario()`
with draws seed 1 that is k2 or k4, both at 1.2 (k0 and k1 are 0.2, k3 is 1.0). The opening
frame is then "all green, R potential 1.2": a kendra where nothing has happened yet and the
only number on screen is the one saying how much could.

Observed today with a health shock on m010 (Mamta Kisku, k2) in week 2 and
`decision_week=3`, so these are a starting point to tune from, not values to hardcode:

- flagged: m010, m011, m012, m014 in k2, plus the baseline k0 pair m002 and m004
- Rs 4,20,707 at risk
- smallest fix: cut Mamta Kisku's installment by 50% from week 3. Protects 3 members, costs
  the lender Rs 130, avoids Rs 2,73,172 at risk

Two things to check while tuning: that the k0 baseline pair does not distract from the k2
story (it may be better to show k2 alone first), and whether a cross kendra case can be
provoked, because `cross_kendra_reach_by_week` is currently 0 everywhere and the shared
lender channel is the part a single lender cannot see for itself.

## Next

- **Phase 3 part 2**: `stability.py`. 50 runs, each with a new seed and every
  `params.PERTURBABLE` field multiplied by U(0.7, 1.3); within a run, actual and
  counterfactual share draws. Report "stable in k of 50 runs" for the label and, for
  TRANSMITTED, the source too.
- Then `scripts/demo_story.py`, which prints the whole story in the terminal. THAT IS THE
  GATE: if it tells the story, the prototype exists.
- Deferred on purpose, pick up only if there is time: `scheme_linkage`, and a manual
  intervention sandbox.

## Handy while working

```
cd backend && .venv/Scripts/python.exe -m pytest
```

Demo baseline that exercises the trend as a cause: `generate_scenario()` with
`make_draws(25, DEFAULT, seed=1)` and no shocks -> m002 INDEPENDENT, m004 TRANSMITTED.
