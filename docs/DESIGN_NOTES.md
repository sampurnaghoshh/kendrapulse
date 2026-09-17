# Design notes

The decisions behind KendraPulse and why each was made, plus the validation method and its
results. The README says what the system does; this file says why it does it that way. Member
names refer to the seeded demo scenario (`data/demo_scenario.json`).

## Engine

- **Cover is settled at the kendra meeting out of the cash a peer brought for her own
  installment first, then out of savings.** Without that order a member with a comfortable week
  absorbs a peer's whole shortfall out of spare change, and the guarantee channel leaves no trace
  on her. With it, helping a neighbour can leave her short on the day, which is what makes
  transmission visible as transmission.
- **Each week resolves in ordered passes over the whole roster** (lender pause, own money,
  meeting, stress). A single loop per member would let one member's outcome depend on whether
  another had been processed yet, an order sensitivity that silently diverges between the actual
  and counterfactual runs. Pledges are computed simultaneously and a gap is split equally among
  willing peers, the only allocation with no invented priority between neighbours. A peer whose
  pledges exceed her capacity scales all of them down by one factor.
- **Common random numbers.** The engine never creates randomness. Every uncertain quantity is
  read from `draws[member, week, channel]`, built once per scenario. A draw belongs to a person,
  week and channel, never to an event, so removing a shock cannot reshuffle downstream coin
  flips. Draw channels are append only, because inserting one would reshuffle a tuned seed.
  Tests assert that the same draws object (identity, not equality) reaches every world.
- **Stress uses two shortfalls.** Her stress excludes cover she received (so the index case stays
  visible after being bailed out) and includes cover she gave (so a giver becomes visible). The
  arrears a lender sees only count what actually arrived at the meeting.
- **Stress memory is `max(raw, 0.5 x last week)`, not a sum.** The additive form compounds and
  pins the whole roster at 1.0 by the end of the horizon; max gives a floor that decays.
- **The household eats before it pays.** A consumption gap comes out of savings first; otherwise
  a severe income shock would leave no trace.

## Attribution

- **A cause is a member's own shocks plus her own negative income trend.** In the seeded baseline
  with no shocks, Suma flags in week 12 purely because she covered Meena, whose income is
  eroding. A shocks only procedure would find Suma still flagged in the no shock world and call
  her INDEPENDENT, when she is the clearest TRANSMITTED case. A trend is neutralised by setting it
  to zero. A positive trend is never a cause, because removing it would make a member poorer in
  the counterfactual than in reality and manufacture stress.
- **Necessity is judged at the week her own causes first put her over, not at `as_of_week`.**
  Otherwise a member hit early whose trend would also catch up with her late flips from INDEX to
  INDEPENDENT as the slider moves.
- **Stress travels against the money on a guarantee edge.** The log records cover giver to
  receiver, but the giver ends up short, so explanation paths walk guarantee edges backwards and
  shared lender edges forwards.

## R numbers

- **A primary case is INDEX or INDEPENDENT.** A declining income starts a chain the same way an
  illness does; counting only INDEX would leave onward cases with a zero denominator.
- **R live counts onward cases inside the source's kendra**, the same scale as R potential, so the
  number under a cluster keeps its meaning when it switches from potential to live. Stress that
  crosses into another kendra is reported separately as cross kendra reach, charged to the kendra
  the stress came from.
- **R live is None, never 0.0, before a kendra has a primary case.** 0.0 would read as "not
  spreading" where nothing has happened, and None is what tells the UI to show R potential.
- **An onward case only counts once its source is a counted case too.**
- **R potential** plants one standard health shock on each member in turn and counts kendra peers
  newly flagged within the window, against a no shock baseline on the same draws. Newly flagged,
  so members already in trouble do not make a fragile kendra look robust. The scenario's own
  shocks are ignored, so it stays defined when everybody is green. `r_window_weeks = 4` because
  the counts saturate at 4 on the demo and 4 is where kendras separate most.

## Interventions and the smallest fix

- **An intervention changes exactly one quantity: the installment due.** Everything else moves
  because due moved. A reschedule with fraction 1.0 must replay identically to no intervention,
  and a test checks it.
- **Moratorium money moves to the end of the loan tenure**, which is how MFI moratoriums work.
  Making it repayable inside the horizon would show a cliff that is not there. A reschedule does
  not expire, because the loan is re papered over a longer tenure.
- **Observation window.** A fix is valid only if it ends at least `r_window_weeks` before the
  horizon. A moratorium to week 12 would "protect" a member by deleting every payment she could
  have missed inside the chart. A reschedule counts as ending at its start week, since she is
  paying again from then. An empty candidate list late in the quarter is the honest answer.
- **Lender cost is one formula**: rupees moved times `carry_cost_rate` times weeks late. Deferring
  money does not destroy it; the lender loses the use of it. The same fix granted later costs
  less.
- **Rejection is absolute.** A candidate that newly flags anybody is dropped at any cost saving,
  and one that protects nobody is dropped too. Ranking is members protected, then lender cost,
  then the lighter fix, then roster order so the list is deterministic.
- **Rupees at risk is total outstanding of flagged members**, not the missed installment: once a
  joint liability borrower is in distress, the exposure at stake is the loan.
- New R after a fix is computed with the fix held fixed across every counterfactual, so labels
  still answer "what caused this", not "what would the fix have done".
- Scheme linkage is deferred; the two due side actions already tell the story.

## Stability

- Each of 50 reruns perturbs every `PERTURBABLE` field by U(0.7, 1.3) and rolls fresh dice.
  Varying only settings answers "robust to our choices", only dice "robust to luck"; an officer
  faces both. Inside one rerun, reality and its counterfactuals share draws.
- Rerun k uses seed `seed + k + 1`, so the base run's dice never reappear and score a free match.
- Regulatory caps and generator shape are never perturbed: a cap is not uncertain, and changing
  the generator would change who the borrowers are.
- A match is the same label, and for TRANSMITTED the same source.
- **The badge is two numbers**: reruns that flag her, and reruns among those that name the same
  cause. A single "stable in 22 of 50" read as a coin flip, but almost every miss was the member
  not being flagged at all, not a different cause. A member can be hard to call and easy to
  explain.

## Demo scenario

- `data/demo_scenario.json` holds inputs only, and a test fails if a result appears in it.
- The shock is on Lakshmi in Kendra 3, which ties for the highest R potential, and a test asserts
  the shock lands in a kendra holding the maximum.
- Tuning with `scripts/tune_demo.py` changed the health shock duration from 4 to 6 weeks, the start
  week from 2 to 3 and the decision week from 3 to 4. The target (every transmitted peer flagged in
  at least 35 of 50 reruns with source agreement above 0.9) was not reached. What the search found:
  - Severity above 0.65 does nothing, because cover is capped at a share of the peer's cash plus
    savings, so a deeper hole does not make anyone give more.
  - Duration is the only shock lever that works: more meetings at which a peer covers.
  - Thinner savings make transmission weaker, not stronger. They shrink what a peer can give and
    she starts flagging on her own, which destroys source agreement.
  - Thicker savings for three members helped by about 6 reruns and needed disclosed overrides
    that increase savings. Not taken; the demo uses no member overrides.
  - The ceiling is the dice: whether a neighbour covers at a meeting is a fresh roll in every
    rerun, and a peer who does not cover never gets stressed.
- Demo badges after tuning (flagged of 50, then same cause): Lakshmi INDEX 50, 50. Latha
  TRANSMITTED 27, 27. Savitha TRANSMITTED 28, 28. Roopa TRANSMITTED 22, 21. Meena INDEPENDENT
  37, 36. Suma TRANSMITTED from Meena 12, 12.
- The officer's note ("paid in full, out of her savings") is recomputed from the run and a test
  fails if it stops being true.
- `display_name_overrides` changes name strings only, so first names on screen are unique. A
  test rebuilds the story with and without them and requires identical states, event log,
  attribution, stability, R and fixes.
- **Shared lender channel**: it fires, freezing top ups for members in other kendras and taking
  their savings, but never pushes any of them to amber, so cross kendra reach is 0 everywhere.
  Lowering `lender_pause_threshold` or thinning the savings of members who share Lakshmi's lender
  would be the way to produce a genuine cross kendra case.

## Snapshot

`scripts/export_snapshot.py` writes `frontend/public/demo_snapshot.json`: the story plus
counterfactual worlds (for a TRANSMITTED member, reality minus her source's shocks and negative
trend; for INDEX and INDEPENDENT, the world holding only her own causes), fix replays stored
once each, the persistent ring per member and week, and the validation counts. A test rebuilds
each counterfactual world from scratch and requires identical weeks.

## Frontend

- Node fill is status at the slider week. A persistent ring marks "flagged at some point so far";
  fill alone would make a peer who was amber for one week vanish a week later.
- Explanation cards persist once shown, because moving the slider does not make an explanation
  untrue, and never appear before her first flag week.
- Only one alternate world at a time in the single graph: What if and an applied fix share one
  state value. Protected markers mean flagged by this week in reality and not with the fix, which
  equals `members_protected` at week 12.
- R chips use a fix replay's own R live where it exists. Elsewhere in an alternate world, a kendra
  with nobody flagged shows R potential and one with a flag says "R live not scored here" rather
  than borrowing reality's number.
- Side by side keeps its own state, so closing it restores the single graph exactly. Both panels
  read the one slider week. The divergence week is the first week the member's status differs
  between the two worlds. The transmitted label under the right panel follows the slider, so a
  replay from week 1 does not name the cause early.

## Validation

### Method

`validation/cause_recovery.py` runs three parties over each generated scenario:

- **Truth** has true parameters, true incomes and true dice. Its flagged members are the observed
  set, the people an officer would be looking at, and its full knowledge labels are ground truth.
- **Engine under test** gets the same roster, graph, shocks and event log, but parameters at
  U(0.8, 1.2), incomes and trends with 15% multiplicative noise, and a dice seed offset by 10,000.
  It must explain the observed set, not the set its own world flags: an officer brings a list of
  people in trouble, not a list the model predicted. The validation band is a separate copy from
  the stability band, so neither can be widened to flatter the other.
- **Baseline**, observable data only: a shock means INDEX; else, if the event log shows her giving
  cover, TRANSMITTED from whoever she covered most; else INDEPENDENT. A test makes `simulate`
  raise inside it.

Outcomes per observed member: correct, wrong source, wrong label, unexplained (the engine's own
world never flagged her).

### Fairness corrections, fixed before the n = 500 run

1. **Same subset.** An n = 100 run reported the engine's accuracy on the members it explained
   (90.6%) against the baseline's on all members (86.8%). Those are different populations, and
   the engine's is easier by construction: a member its own noisy world flags is one well clear
   of the threshold. That comparison is superseded. The report now scores both on the same
   members: `same_subset` (members the engine explained), `unexplained_subset`, and
   `all_observed`.
2. **Observation anchored attribution.** The officer observed the flag, and attribution exists to
   explain a flag, not to re predict it. For a member the engine's world does not flag, threshold
   tests are replaced by shares of the stress it does see: with `excess` = her peak stress minus
   her peak in the world with no shocks and no negative trends, `own_share` = the part her own
   causes account for. `own_share >= 0.5` means INDEX or INDEPENDENT (split as before), else
   TRANSMITTED with the same source ranking; `sole_source` means removing that source removes at
   least 0.5 of excess. If `excess < 0.01` the member is `no_signal`, not labelled, so the
   residual cannot vanish by construction. Constants written down before the run and not changed
   after.
3. **Counts, not percentages**, so no headline rests on a small denominator (INDEPENDENT was 18
   members at n = 100).

Pre registered prediction: the baseline scores higher on the same subset than on all members. If
it then lands at or above the engine on the same subset, the simulation has no measured overall
advantage and the claim rests on INDEPENDENT and on the mechanism.

### Results, n = 500, run once

469 scenarios scored, 1901 observed flagged members. Correct of total.

| Subset | Engine, threshold | Engine, anchored | Baseline |
| --- | ---: | ---: | ---: |
| **Same subset** (1382) | 1248 of 1382 | 1248 of 1382 | **1269 of 1382** |
| INDEX | 775 of 777 | 775 of 777 | 777 of 777 |
| TRANSMITTED | 388 of 513 | 388 of 513 | **420 of 513** |
| INDEPENDENT | **85 of 92** | **85 of 92** | 72 of 92 |
| **Unexplained subset** (519) | 0 of 519 | 361 of 519 | **420 of 519** |
| INDEX | 0 of 3 | 3 of 3 | 3 of 3 |
| TRANSMITTED | 0 of 477 | 326 of 477 | **388 of 477** |
| INDEPENDENT | 0 of 39 | **32 of 39** | 29 of 39 |
| **All observed** (1901) | 1248 of 1901 | 1609 of 1901 | **1689 of 1901** |
| INDEX | 775 of 780 | 778 of 780 | 780 of 780 |
| TRANSMITTED | 388 of 990 | 714 of 990 | **808 of 990** |
| INDEPENDENT | 85 of 131 | **117 of 131** | 101 of 131 |

No signal (anchored): 35. The own share clip never fired.

- **The prediction held**: baseline 1269 of 1382 on the same subset, above 1689 of 1901 overall.
  **The named consequence also happened**: the baseline is at or above the engine on the same
  subset (1269 against 1248).
- **The baseline wins overall in both modes**, and wins TRANSMITTED everywhere. Guarantee cover is
  the main channel in this model and the event log records it, so "blame whoever she covered
  most" is a very good rule.
- **The engine wins INDEPENDENT everywhere**: 85 of 92 against 72 of 92 on the same members, 32 of
  39 against 29 of 39 on the unexplained ones, 117 of 131 against 101 of 131 overall. The rule
  calls a declining income TRANSMITTED whenever she once covered a neighbour; only the
  counterfactual can say she would have flagged anyway. It is the one measured advantage, small
  in count, and it is the case that changes what the officer should do.
- **Anchoring fixed coverage, not accuracy**: it explained 484 of the 519 unexplained members and
  got 361 right; the baseline got 420 of the same 519.
- INDEX is solved by both and earns no credit.
- Near simultaneous shocks (two within 2 weeks) were not harder: 912 of 1012 correct when
  explained, against 336 of 370 in the other scenarios.
