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
  the engine now applies interventions, R live rescoped to the kendra.
- **Phase 3 part 2** `stability.py`: 50 perturbed reruns, "stable in k of 50 runs".
- **Phase 3 part 3 THE GATE IS PASSED.** `data/demo_scenario.json`, `backend/demo/story.py`
  and `backend/scripts/demo_story.py`. The script tells the whole story in the terminal in
  3.3 seconds, so the prototype exists.
- **Two part stability badge**: "flagged in 23 of 50 reruns; same cause in 22 of those".
- **Phase 4 part 1** `validation/cause_recovery.py` + `scripts/run_validation.py`, run at
  n=100. 163 tests pass. `reality_check.py` is still to do.

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

## Phase 3 part 2: what the stability badge counts

`stability(scenario, shocks, interventions, params, base_records, seed, n_runs=50)` returns one
entry per base record, in the same order, so the UI can zip badges onto cards it already has:
`{member_id, base_label, base_source_id, matched, differed, not_flagged, flagged_runs,
source_agreement, n_runs, badge_text}`. The badge text itself is described further down, under
"The stability badge is two numbers now".

- Run k perturbs every `params.PERTURBABLE` field by its own U(0.7, 1.3) AND rolls fresh
  dice. Varying only the settings would answer "robust to our choices", only the dice
  "robust to luck"; an officer is exposed to both at once. Inside run k, the actual world and
  every counterfactual share that one draws array.
- Run k draws with `seed + k + 1`, so the base run's own dice never reappear. A rerun that
  replayed the base world would score itself a free match and inflate every badge.
- A match is the same label, and for TRANSMITTED the same `source_id` too. The sentence on
  screen names a neighbour, and naming a different one has not reproduced anything.
- `differed` and `not_flagged` are counted apart on purpose: "we would have called her
  something else" and "she would not have been on the list" are different admissions.
- One attribution per run, not one per member. `attribute` already labels every flagged
  member off a shared cache of worlds.
- `amber` and `red` are perturbed independently, so a run can have red below amber. Only
  `amber` decides flagging, so no count depends on the pair staying ordered.

## Phase 3 part 3: the gate, and what it actually prints

`data/demo_scenario.json` holds INPUTS only (generator seed 42, draws seed 1, health shock on
m010 in week 2, decision week 3, stability seed 1, 50 runs). A test asserts no result word
appears in it, so the demo can never assert its own conclusion.

`backend/demo/story.py` -> `build_story()` returns one plain dict with everything: roster,
layout, edges, weekly states, a timeline of status changes and transfers, labelled and badged
attribution with sentences, both R series per kendra, the three ranked fixes with replays, and
the applied top fix. It is deterministic and JSON serialisable, which is what lets Phase 5
serve the same dict and Phase 6 draw it. `_plain()` coerces numpy scalars on the way out;
`json.dumps` refuses them and the engine produces them everywhere.

`backend/scripts/demo_story.py` only arranges that dict, so the terminal and the UI can never
tell two different stories. It prints its own runtime.

The story, as it runs today:

1. All 25 members green. R potential k0 0.20, k1 0.20, k2 1.20, k3 1.00, k4 1.20.
2. Mamta Kisku (m010, k2) loses 65% of her income for 4 weeks from week 2.
3. Week 4 she goes red and two peers go amber covering her at the meeting. Week 5 a third
   peer goes amber and a lender freezes top ups for 8 members in OTHER kendras.
4. Six flagged: one INDEX (50 of 50 runs), four TRANSMITTED, one INDEPENDENT (36 of 50).
5. R live in k2: R potential 1.20 through week 3, then live 2.00, then 3.00 from week 5.
6. Smallest fix: cut Mamta's installment by 50% from week 3. Protects 3 members, costs the
   lender Rs 130, Rs 2,73,172 of loans moved out of stress, R live 3.00 becomes 0.00. The
   index case stays flagged, which is the honest shape: a lender cannot undo an illness.
7. Anita Kisku in k0 is INDEPENDENT and her stress still reached Savita Bai in week 12.

## The stability badge is two numbers now

`{matched, differed, not_flagged, flagged_runs, source_agreement, n_runs, badge_text}`, and the
badge reads:

    flagged in 23 of 50 reruns; same cause in 22 of those

`flagged_runs = matched + differed`, `source_agreement = matched / flagged_runs` (None when she
never flagged, because a zero would read as "we never named the right cause" rather than "never
asked"). Perturbation range is untouched at U(0.7, 1.3).

One figure was lying. "Stable in 22 of 50" reads as "the attribution is a coin flip", but
`differed` was 0 or 1 on every transmitted case: almost every miss was `not_flagged`. The demo
now reports 92 to 100 percent source agreement on all four transmitted cases against 11 to 23
reruns flagging them. **A member can be hard to call and easy to explain**, and that is the
distinction to make out loud in the video. The script says it in words under each badge
("A marginal case: only 12 reruns put her over the line at all. When they did, we named the
same cause 100% of the time.").

## Phase 4 part 1: cause recovery, and what n=100 actually says

`validation/cause_recovery.py` runs three parties over each seeded scenario:

- **TRUTH** has true params, true incomes, true dice. Its flagged set is the OBSERVED set (the
  people an officer would be looking at) and its full knowledge labels are ground truth.
- **ENGINE UNDER TEST** gets the same roster, graph, shocks and event log, but params at
  U(0.8, 1.2), `weekly_income` and `income_trend` with 15% multiplicative noise, and a dice
  seed offset by 10,000. It must explain the observed set, which is NOT the set its own world
  flagged. That mismatch is the point: an officer brings you a list of people in trouble, not a
  list your model predicted.
- **BASELINE**, observable data only, no simulation: shock -> INDEX; else gave cover per the
  event log -> TRANSMITTED from whoever she covered most; else INDEPENDENT. A test
  monkeypatches `simulate` to raise inside it so it can never quietly cheat.

Outcomes per observed member: `correct`, `wrong_source`, `wrong_label`, `unexplained` (engine
only: her own world never flagged her). Two accuracies, because they answer different
questions. `accuracy_when_explained` judges the LOGIC; `overall_accuracy` counts `unexplained`
as not correct and judges the DEPLOYED SYSTEM. `perturbed_params` is deliberately a second copy
at a narrower band rather than an import from `stability.py`, so neither range can be widened to
flatter the other.

**n=100, 93 scenarios scored, 408 observed flagged members, 11 seconds:**

|                        | engine | baseline |
| ---------------------- | -----: | -------: |
| accuracy when explained| 90.6%  |  86.8%   |
| overall accuracy       | 65.9%  |  86.8%   |
| INDEX (n 158)          | 100.0% | 100.0%   |
| TRANSMITTED (n 227)    | 78.7%  |  79.7%   |
| INDEPENDENT (n 23)     | 88.9%  |  65.2%   |

Read it honestly, because two of these numbers are uncomfortable:

1. **INDEX is solved by both.** 100% for a spreadsheet rule too. We should not claim credit for
   it; "she has a shock, so she is the index case" needs no simulation.
2. **On TRANSMITTED the simulation ties the spreadsheet** (78.7 against 79.7). The baseline rule
   "she covered somebody, so blame whoever she covered most" is genuinely good, because in this
   model guarantee cover IS the main channel and the event log records it.
3. **The simulation's real win is INDEPENDENT: 88.9% against 65.2%.** The baseline calls a
   declining income TRANSMITTED whenever she happened to cover a neighbour once. Only the
   counterfactual can say "she would have flagged anyway". That is the claim to make in the
   video, and it is exactly the case that changes what the officer should DO (a moratorium is
   useless for her).
4. **27% of observed members are `unexplained`** (111 of 408), and 105 of those are true
   TRANSMITTED cases. The engine's noisy world simply does not flag the same marginal peers.
   This is the same threshold marginality the stability badge found, seen from the other side.
   It is a coverage problem, not a logic problem, and it is why `overall_accuracy` is 65.9%.
5. Near simultaneous shocks (2+ within 2 weeks) barely hurt: 90.0% against 92.6% when
   explained. Worth saying, since the build contract predicted that would be the hard case.

## The shared lender channel fires but never flags anybody

`cross_kendra_reach_by_week` is 0 everywhere; it still is, but now we know why. Week 5 really
does freeze top ups for 8 members across other kendras and takes Rs 10,255 of their savings,
it just never pushes one of them over amber. To get a genuine cross kendra case, lower
`lender_pause_threshold` or thin the buffers of the members sharing m010's lender. Worth one
attempt, because it is the part a single lender cannot see for itself.

## Scenario tuning notes

Done, and pinned in `data/demo_scenario.json`: the shock is planted on m010 in k2, which ties
with k4 for the highest R potential at 1.2. The opening frame is "all green, R potential 1.20".
A test asserts the shock lands in a kendra holding the maximum, so retuning the scenario cannot
silently break that claim.

Still open: the k0 pair (m002 INDEPENDENT, m004 TRANSMITTED) flags in weeks 11 and 12, late
enough that it does not compete with the k2 story and in fact gives section 7 its case. Leave
it. If the video runs long, the k0 pair is the part to cut.

### TOMORROW, FIRST JOB: make the hero transmitted case less marginal

Two separate findings now point at the same root cause. The stability badge says the k2 peers
only flag in 11 to 23 of 50 reruns, and cause recovery says 105 of 227 true TRANSMITTED cases
are `unexplained`. Both are the same thing: a transmitted peer lands a hair over `amber`, so any
nudge to the settings or the dice leaves her green. The attribution is fine. The CASE is thin.

Fix it with SCENARIO INPUTS ONLY. Do not touch `amber`, the stress weights, the perturbation
ranges or any code path. Things to try, cheapest first, checking the badge after each:

1. Raise the health shock severity or duration in `data/demo_scenario.json` (the `Shock` fields
   are already there and override the params default). A deeper shock means a bigger gap at the
   meeting, so the peers who cover it are pushed further past the line.
2. Thin the savings buffers of m011, m012 and m014 specifically, or raise their
   `installment_share`, via the generator seed or a scenario level override. A peer with less
   cushion absorbs the same cover as real distress.
3. Plant a second small shock on another k2 member so two neighbours need cover in the same
   week, which doubles what the givers carry.

Target: the hero transmitted case flagging in 35 or more of 50 reruns while `source_agreement`
stays above 0.9. Re run `scripts/demo_story.py` and `scripts/run_validation.py --n 100` after
each attempt; the validation `unexplained` count should fall too, since it is the same
marginality. If none of the three works, say so in the video rather than moving a threshold.

## Next

- **Tomorrow, in order**: the tuning above, then `scripts/run_validation.py --n 500` (about 55
  seconds at the measured 0.11s per scenario), then `validation/reality_check.py` (more lenders
  means more overdue, a weak monsoon hits a shared income source together, low overdue in
  normal conditions) folded into the same report.
- Then **Phase 5**: `app.py` routes plus `scripts/export_snapshot.py`. `build_story()` already
  returns exactly what `GET /scenario/demo` and the snapshot need, and `GET /validation/report`
  is just `data/validation_report.json`, so Phase 5 is mostly plumbing.
- Then **Phase 6** frontend, which is the last thing with real risk in it.
- Deferred on purpose, pick up only if there is time: `scheme_linkage`, a manual intervention
  sandbox, and provoking a genuine cross kendra case.

## Handy while working

```
cd backend && .venv/Scripts/python.exe -m pytest
cd backend && .venv/Scripts/python.exe scripts/demo_story.py
cd backend && .venv/Scripts/python.exe scripts/run_validation.py --n 100
```

Demo baseline that exercises the trend as a cause: `generate_scenario()` with
`make_draws(25, DEFAULT, seed=1)` and no shocks -> m002 INDEPENDENT, m004 TRANSMITTED.
