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
- **Hero case tuning (timeboxed, TARGET NOT MET)**: `scripts/tune_demo.py`, shock now 6 weeks
  from week 3, decision week 4, no member overrides. 169 tests pass. See "Hero case tuning:
  what the badges are" below; the video must quote those numbers, not the target.

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

## Hero case tuning: what the badges are

Target was every k2 transmitted peer flagged in at least 35 of 50 reruns with source agreement
above 0.9. **No input in the search reached it.** What the demo now shows, exactly:

| member | label | flagged | same cause | agreement | before tuning |
| --- | --- | ---: | ---: | ---: | --- |
| Mamta Kisku m010 | INDEX | 50 of 50 | 50 | 1.00 | 50 of 50 |
| Rani Kisku m014 | TRANSMITTED, week 5 | 27 of 50 | 27 | 1.00 | 12 of 50 |
| Kamala Murmu m011 | TRANSMITTED, week 7 | 28 of 50 | 28 | 1.00 | 23 of 50 |
| Kavita Hansda m012 | TRANSMITTED, week 8 | 22 of 50 | 21 | 0.95 | 12 of 50 |
| Anita Kisku m002 | INDEPENDENT | 37 of 50 | 36 | 0.97 | 37 of 50 |
| Savita Bai m004 | TRANSMITTED from m002, week 12 | 12 of 50 | 12 | 1.00 | 11 of 50 |

Say it in the video as: "each of her neighbours went into stress in roughly half of 50
reruns, and whenever one did, we named Mamta as the cause 95 to 100 percent of the time."
Do not say "stable" about the transmitted cases without the first number.

Inputs changed, all in `data/demo_scenario.json`: health duration 4 -> 6 (default severity kept
at 0.65), start week 2 -> 3, decision week 3 -> 4. The story holds: all 25 green in week 1, k2
still tied top on R potential with k4 at 1.20, only m002 and m004 flagged outside k2, m002 still
INDEPENDENT, top fix is still "cut Mamta Kisku's installment by 50%" and protects all 3 peers
(Rs 104 lender cost, R live 3.00 -> 0.00), the index case stays flagged.

What the search found (40 shock candidates plus 16 buffer override candidates at 20 runs,
best ones confirmed at 50):

- **Severity does nothing** above 0.65. Cover is capped at `cover_capacity_share` of the peer's
  cash plus buffer, so a deeper hole does not make anyone give more.
- **Duration is the only shock lever that works**: more meetings at which a peer rolls
  `p_cover` and covers. Capped at 6 by the grid.
- **Thinner buffers make it worse, not better** (the guess in the plan above was wrong). They
  shrink what a peer can give, and at x0.5 m012's source agreement collapsed to 0.00 to 0.33
  because she started flagging on her own. At x0.25 nobody is transmitted at all.
- **Thicker buffers (x2.0) help two peers a little**: duration 6 week 3 x2.0 gave m011 34 and
  m014 33 of 50, but m012 fell to 19, it needs three disclosed overrides that INCREASE savings,
  and the gain is about 6 reruns. Not taken. `member_overrides` support stays in `story.py`
  (with a mandatory `reason`) but the demo uses none.
- **The ceiling is the dice, not the inputs.** Whether a given neighbour covers at a given
  meeting is a fresh `p_cover` roll in every rerun, and a peer who does not cover never gets
  stressed. Getting to 35 of 50 would need a code or params change (for example cover spread
  over all peers instead of roster order), which is out of bounds for this task.

Simple rule check (the validation baseline, observable data only): it agrees with the replay on
every flagged member in this scenario. Anita Kisku never gave cover, so the rule also calls her
INDEPENDENT, and the line "A simple rule would blame ...'s neighbour" is NOT printed. The story
now carries `simple_rule` per record and `demo_story.py` prints that line automatically if a
future scenario produces the case.

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

### DONE, TARGET NOT MET (see "Hero case tuning" above): make the hero transmitted case less marginal

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

- **Next, in order**: ~~`scripts/run_validation.py --n 500`~~ (done, see Validation fairness RESULT) (about 55
  seconds at the measured 0.11s per scenario), then `validation/reality_check.py` (more lenders
  means more overdue, a weak monsoon hits a shared income source together, low overdue in
  normal conditions) folded into the same report.
- Then **Phase 5**: `app.py` routes plus `scripts/export_snapshot.py`. `build_story()` already
  returns exactly what `GET /scenario/demo` and the snapshot need, and `GET /validation/report`
  is just `data/validation_report.json`, so Phase 5 is mostly plumbing.
- Then **Phase 6** frontend, which is the last thing with real risk in it.
- Deferred on purpose, pick up only if there is time: `scheme_linkage`, a manual intervention
  sandbox, and provoking a genuine cross kendra case.

## Story consistency pass

- **Wording**: every ever flagged count now says "at some point in these 12 weeks" (the flagged
  list, the Rs figure, the before and after block, and each ranked fix's "who would otherwise be
  flagged at some point"). A member who was amber for one week in week 5 is green by week 12,
  and "now sitting on stressed borrowers" claimed otherwise.
- **Officer's note** at the decision week lives in `data/demo_scenario.json` (`officer_note`,
  with `{name}` filled from the roster) and is printed at the top of section 6. It says she
  paid in full, out of savings. The run backs it: through week 4 Mamta has no arrears and no
  cover, and her savings fall from Rs 10,147 to Rs 1,757; her first short week is week 5.
  `build_story()` recomputes `paid_in_full_so_far` and a test fails if the note stops being true.
- **Lender freeze lines** name the kendra ("arrears in k2"), not the worst payer the event log
  happens to record, with singular and plural handled.
- **Section 7** now says "She needs restructuring, not a moratorium", and points at the ranked
  fix for her when one exists (option 2, cut Anita Kisku's installment by 25%).
- **Karnataka setting, DONE** as a same size, same position swap of the name lists (25 first
  names, 12 surnames), branch "Davanagere branch". `tests/test_names.py` rebuilds the whole story
  with the old lists and requires states, event log, attribution, stability, R, smallest fix
  and the officer note to be identical once full names are mapped to member ids. Every badge
  and rupee figure in this file is unchanged; only the names are.

  **Old name -> new name, for reading older sections of this file:**

  | id | before | now |
  | --- | --- | --- |
  | m010 | Mamta Kisku (index) | Lakshmi Gowda |
  | m011 | Kamala Murmu | Savitha Bhat |
  | m012 | Kavita Hansda | Roopa Kamath |
  | m014 | Rani Kisku | Latha Gowda |
  | m002 | Anita Kisku (independent) | Meena Gowda |
  | m004 | Savita Bai | Suma Naik |

  Watch in the video: three of the six flagged members share the surname Gowda (it took
  Kisku's position, which was common in the old roster). Harmless, but say first names.

## Phase 5 part 1: the static snapshot

`scripts/export_snapshot.py` writes `frontend/public/demo_snapshot.json` (about 512 KB, floats
at 3 decimals) from `demo/snapshot.py::build_snapshot()`. It is `build_story()` plus:

- `counterfactual_worlds[member_id]`: `{label, kind, removed_member_id, title, weeks,
  ever_flagged_by_week}`. TRANSMITTED: `kind = without_source`, reality minus her source's
  shocks AND negative trend. INDEX and INDEPENDENT: `kind = only_own_causes`, the world step 1
  flagged her in. Built by `sim.attribution.label_worlds` on the story's own draws. A test
  rebuilds each one from scratch (fresh scenario, fresh draws, shocks filtered and trends zeroed
  by hand) and requires identical weeks.
- `fix_replays[i]`: `{rank, description, intervention, weeks, ever_flagged_by_week}`. The weeks
  are MOVED here from `smallest_fix.ranked[i]` and `smallest_fix.applied` so the file carries
  each replay once; `applied.replay_rank = 1` points at it.
- `ever_flagged_by_week[member_id]`: 12 booleans, the persistent ring.
- `validation`: same subset and all observed tables as counts, `what_this_is`, prediction.
- `meta`: `generated_at`, `git_commit` (the HEAD it was exported from, so one commit behind the
  commit that contains the file), seeds.

`demo/story.py::setup_world(config)` is now the one place a config becomes (scenario, draws,
shocks), shared by the story and the snapshot.

Two worlds note for Phase 6: for the three k2 peers the right panel is the same world (without
Lakshmi), so the view can be drawn once per source rather than once per member.

## Frontend

- Node fill = status at the current slider week.
- A persistent ring = flagged at some point up to the slider week. Fill alone would make a
  transmitted peer who was amber for one week vanish from the picture a week later.
- Explanation cards persist once shown, for the same reason: the slider moving on does not
  make the explanation untrue.

## Validation fairness

The n=100 numbers above are recorded honestly but they are NOT yet a fair comparison, and this
section is the fix. Read it before touching the validation again.

### RESULT, n=500, run once (method commit 1913431)

469 scenarios scored, 1901 observed flagged members, 105 s. Constants were not touched after the
run: own share 0.5, sole share 0.5, no signal below 0.01 excess. Counts are correct of total.

| subset | engine, threshold | engine, anchored | baseline |
| --- | ---: | ---: | ---: |
| **same_subset** (1382) | 1248 of 1382 | 1248 of 1382 | **1269 of 1382** |
| INDEX | 775 of 777 | 775 of 777 | 777 of 777 |
| TRANSMITTED | 388 of 513 | 388 of 513 | **420 of 513** |
| INDEPENDENT | **85 of 92** | **85 of 92** | 72 of 92 |
| **unexplained_subset** (519) | 0 of 519 | 361 of 519 | **420 of 519** |
| INDEX | 0 of 3 | 3 of 3 | 3 of 3 |
| TRANSMITTED | 0 of 477 | 326 of 477 | **388 of 477** |
| INDEPENDENT | 0 of 39 | **32 of 39** | 29 of 39 |
| **all_observed** (1901) | 1248 of 1901 | 1609 of 1901 | **1689 of 1901** |
| INDEX | 775 of 780 | 778 of 780 | 780 of 780 |
| TRANSMITTED | 388 of 990 | 714 of 990 | **808 of 990** |
| INDEPENDENT | 85 of 131 | **117 of 131** | 101 of 131 |

- unexplained (threshold): 519. no_signal (anchored): 35. own_share clipped: 0 of 519 anchored
  members (0 below 0, 0 above 1). The clip is kept as a guard, but it never fired here.
- **Pre registered prediction HELD**: baseline 1269 of 1382 (91.8%) on the same subset, above its
  1689 of 1901 (88.8%) overall.
- **And the consequence the plan named also happened: the baseline is AT OR ABOVE the engine on
  the same subset** (1269 against 1248). The simulation has no measured overall advantage there.

What that means, plainly:

1. **The engine loses to the spreadsheet rule overall, in both modes.** Same subset by 21
   members, all observed by 80 (anchored) and 441 (threshold). The earlier "90.6 against 86.8"
   was the easier subset effect and must not be quoted.
2. **TRANSMITTED goes to the baseline everywhere**: 420 against 388 on the same members, 388
   against 326 on the unexplained ones. In this model guarantee cover is the main channel and
   the event log records it, so "blame whoever she covered most" is a very good rule.
3. **INDEPENDENT goes to the engine everywhere, and now on real counts**: 85 of 92 against 72 of
   92 on the same members, 32 of 39 against 29 of 39 on the unexplained ones, 117 of 131 against
   101 of 131 overall (anchored). That is 16 more members correctly told "this is your own
   income, not contagion". It is the one measured advantage, it is small in count, and it is
   the case that changes what the officer does.
4. **Anchoring fixed coverage, not accuracy.** It explained 484 of the 519 unexplained members
   (35 honest no_signal) and got 361 right, but the baseline got 420 of those same 519.
5. INDEX is solved by both and earns no credit.

Per item 4 below, the video leads with the MECHANISM (counterfactual, two worlds, explanation
path, smallest fix) and the INDEPENDENT case, and says out loud that on transmitted cases a simple
rule from the event log does as well or better. No benchmark win is claimed.

### 1. accuracy_when_explained is measured on an easier subset

`engine 90.6%` is computed over the 297 members the engine explained. `baseline 86.8%` is
computed over all 408. Those are different populations, and the engine's population is the
easier one by construction: a member her own world flags is a member whose stress is well clear
of the threshold, which is also a member the baseline finds easy. So the 90.6 against 86.8
gap is not evidence of anything yet, and we must not quote it as a win.

Add three blocks to the report, all on the SAME members:

- `same_subset`: engine and baseline accuracy over the members the engine explained. This is
  the only apples to apples comparison, and it is the headline number from now on.
- `unexplained_subset`: baseline accuracy over the members the engine could not explain. The
  engine scores 0 there by definition in threshold mode, so what matters is whether the
  baseline does well on them. If it does, the baseline is strictly better on that slice and we
  should say so.
- `all_observed`: what we already report, kept so the two views can be compared.

Expect `baseline` on `same_subset` to come out ABOVE its 86.8% overall figure. If it lands at
or above the engine's 90.6%, the simulation has no measured advantage on that slice and the
pitch has to rest on INDEPENDENT and on the mechanism instead.

### 2. Observation anchored attribution, method fixed BEFORE the rerun

The justification is sound and worth stating plainly: the officer OBSERVED the flag. Attribution
exists to explain a flag, not to re predict it. Asking the engine to first reproduce a flag it
was never going to reproduce under 15% income noise is asking the wrong question, and the
baseline already works from observed data, so anchoring is parity rather than a favour.

Method, pinned now so it cannot be tuned after seeing the result. For a member the engine's own
world does not flag, every `flagged()` test in `attribution.py` is vacuously false, so replace
each threshold crossing with a RELATIVE SHARE of the stress the engine does see. Let

    s_actual  her peak stress in the engine's actual world
    s_floor   her peak stress in the world with no shocks and every negative trend zeroed
    s_own     her peak stress in the world holding only HER OWN causes
    excess    s_actual - s_floor          (the stress there is to explain)
    own_share (s_own - s_floor) / excess  (how much of it her own life accounts for)

Then the same three steps, with shares in place of crossings:

1. `own_share >= 0.5` means her own causes account for most of her excess stress, so she is
   INDEX or INDEPENDENT. Split exactly as now, by whether removing her own SHOCKS takes away
   most of that own share: yes means INDEX, no means INDEPENDENT.
2. Otherwise TRANSMITTED. The source ranking needs no change at all: `_rank_sources` already
   ranks by drop in peak stress, not by threshold.
3. `sole_source` becomes "removing that source alone removes at least 0.5 of `excess`", in place
   of "unflags her".

Constants: `anchored_own_share = 0.5`, `anchored_sole_share = 0.5`. Both are "most of it",
which is the only defensible reading, and both are written down here before the run.

**The residual category must survive.** If `excess < 0.01` the engine sees essentially no stress
to explain, and that member is reported as `no_signal`, NOT given a label. An anchored mode that
made `unexplained` vanish by construction would be rigging the comparison rather than fixing it.
`no_signal` is the honest remainder and it should be small; if it is not, the anchoring did not
work.

Report BOTH modes side by side, threshold and anchored, on all three subsets from item 1. Run
n=500 ONCE. Do not iterate the constants against the output.

### 3. INDEPENDENT at n=23 is too small to quote as a percentage

`88.9% against 65.2%` is 16 of 18 against 15 of 23. That is the most interesting result we have
and it is currently the least supported one, so it must be reported as COUNTS at n=500, with the
percentage secondary. At n=500 expect roughly 115 INDEPENDENT members, which is enough to quote,
but keep the counts visible next to every percentage in the report so nobody reads a headline
percentage off a denominator of 18 again.

### 4. Timebox, and what to do if it does not work

Items 1 and 2 together get 45 MINUTES tomorrow, no more. Item 1 is arithmetic over rows we
already have and should take about 10 of it; item 2 is a second labelling path in
`attribution.py` behind a flag, which is the risky part. If the 45 minutes run out, ship item 1
alone: the same subset comparison is worth more than a half finished anchored mode, because it
tells us whether there is anything to claim.

If the anchored mode does NOT beat the baseline on the same subset, say so in the report and in
the video, and lead with the MECHANISM instead of a percentage: the counterfactual, the two
worlds view, the explanation path, the smallest fix, and the INDEPENDENT case that a spreadsheet
rule gets wrong for a reason anyone can see. That story does not need the engine to win a
benchmark, and a judge who catches us overselling a benchmark will not believe the mechanism
either.

## Handy while working

```
cd backend && .venv/Scripts/python.exe -m pytest
cd backend && .venv/Scripts/python.exe scripts/demo_story.py
cd backend && .venv/Scripts/python.exe scripts/run_validation.py --n 500
cd backend && .venv/Scripts/python.exe scripts/tune_demo.py --with-overrides
```

Demo baseline that exercises the trend as a cause: `generate_scenario()` with
`make_draws(25, DEFAULT, seed=1)` and no shocks -> m002 INDEPENDENT, m004 TRANSMITTED.
