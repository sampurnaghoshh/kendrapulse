# KendraPulse

Stress tracing for joint liability microfinance groups (kendras). When a borrower is flagged as
stressed, KendraPulse replays her quarter with one cause removed at a time and labels her:

* **INDEX**: her own shock caused it.
* **TRANSMITTED**: the stress arrived from another member, mostly through guarantee cover paid
  at the kendra meeting. The label names that member.
* **INDEPENDENT**: her own income is slipping, and she would have been flagged without any shock.

It then searches for the **smallest fix**: the supportive action (a short pause or a smaller
installment for one member) that keeps the most members out of stress at the lowest cost to the
lender, and shows reality and the fixed world side by side on the same weeks.

Everything in this repository is synthetic. No real borrower data was used.

## Run it

### Frontend (the demo)

The app plays a static snapshot of real runs (`frontend/public/demo_snapshot.json`), so it needs
no backend server.

```
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Tip: `http://localhost:5173/?week=7` opens straight on week 7, which
is handy for rehearsing one moment of the story.

Demo path: press Play and watch Kendra 3. Click Savitha once she turns amber (week 7), read her
card, try the What if switch or Side by side. From week 4, press Find the smallest fix, Apply
option 1, then Side by side. The header button How we tested it shows the validation counts.

### Backend tests

Python 3.11.

```
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows; on macOS or Linux: source .venv/bin/activate
pip install -r requirements.txt
pytest
```

### Regenerate the outputs

From `backend/` with the virtual environment active:

```
python scripts/demo_story.py              # prints the whole demo story in the terminal
python scripts/export_snapshot.py         # rewrites frontend/public/demo_snapshot.json
python scripts/run_validation.py --n 500  # rewrites data/validation_report.json (about 2 minutes)
```

`export_snapshot.py` copies the validation counts from `data/validation_report.json`, so run the
validation first if you change the model.

## How it works

### The weekly engine

[`backend/sim/engine.py`](backend/sim/engine.py) simulates 12 weeks for every member. Each week
resolves in ordered passes over the whole roster, so no member's outcome depends on where she
sits in the list:

1. **Shared lender.** If a kendra's unpaid share last week passed `lender_pause_threshold`, its
   lenders freeze top ups, and linked members in *other* kendras lose part of their savings.
   This is the only channel that crosses kendras.
2. **Pass A, own money.** Income is base income times seasonality, trend, shock and a small
   weekly wobble. The household eats first; any gap comes out of savings. She then brings the
   money for her own installment to the meeting, drawing on savings if needed.
3. **Pass B, the kendra meeting (guarantee cover).** Each peer who is willing this week (a draw
   below `p_cover`) and not already stressed pledges up to `cover_capacity_share` of her meeting
   cash plus savings. A member's gap is split equally among willing peers, and pledges are paid
   out of the cash the peer brought for her *own* installment first, then out of savings. That
   order is what makes helping a neighbour visible as stress on the helper.
4. **Pass C, stress.** Stress `s` combines her shortfall (excluding cover she received, including
   cover she gave) and how far her savings have fallen from week 0, with last week's stress
   decaying by half. Green below `amber`, amber at `amber`, red at `red`. Flagged means amber
   or worse.

**Shared income** works through shocks: a shock planted on an income source (for example a weak
monsoon) hits every member on that source in the same weeks and counts as each member's own
shock. Every transfer is written to an **event log** `{week, channel, from_id, to_id, amount}`,
which drives the explanation paths and the edge pulses on screen.

Loans are generated inside the regulatory caps; see [Data and parameters](#data-and-parameters).

### Common random numbers

The engine never rolls its own dice. Every uncertain quantity is read from one array
`draws[member, week, channel]` built once from a seed ([`make_draws`](backend/sim/engine.py)).
Reality and every counterfactual share that array, so the difference between two worlds is the
removed cause and nothing else. A draw belongs to a person, week and channel, never to an event,
so removing a shock cannot reshuffle anyone else's luck.

### Attribution

[`backend/sim/attribution.py`](backend/sim/attribution.py). A **cause** is a member's own shocks
plus her own negative income trend (a trend is removed by setting it to zero; a positive trend is
never treated as a cause). For each flagged member:

1. Run the world holding only her own causes. If she is still flagged there, she is INDEX when
   removing her own shocks unflags her, otherwise INDEPENDENT. Whether her own causes are
   enough is judged at the week they first push her over, so a label does not flip as the
   slider moves.
2. Otherwise she is TRANSMITTED. For every other member with a cause, run reality minus that
   member's causes; the source is the one whose removal lowers her peak stress most.
   `sole_source` says whether removing that source alone unflags her.
3. The explanation path walks the event log from source to member, and falls back to the
   shortest graph path when no transfer connects them.

### R potential and R live

[`backend/sim/r_number.py`](backend/sim/r_number.py). **R potential** is a property of the
network: plant a standard health shock on each member in turn and count kendra peers newly
flagged within 4 weeks, averaged. It exists even when everyone is green. **R live** counts
transmitted cases inside a kendra whose source is a flagged index or independent case there,
divided by those source cases. It is empty until a kendra has a source case, and the screen
shows R potential until then. Every chip says which one it is.

### Interventions and the observation window

[`backend/sim/interventions.py`](backend/sim/interventions.py). An intervention changes exactly
one number, the installment due:

* **Moratorium**: installments paused for 2 or 4 weeks; the deferred money moves to the end of
  the loan.
* **Reschedule**: installment cut to 50% or 75% from the decision week onward.

Lender cost is the rupees moved times `carry_cost_rate` times the weeks each rupee is late by.
**Observation window rule**: a fix must leave at least `r_window_weeks` (4) of the 12 weeks
after it, so a pause that runs to the end of the chart cannot claim to protect anyone by hiding
her missed payments past week 12. Government scheme linkage is described in the plan but not
built.

### Smallest fix

[`backend/sim/smallest_fix.py`](backend/sim/smallest_fix.py) tries every member with every
option from the decision week, replays each on the same draws, and keeps a candidate only if it
protects someone (flagged in reality, not flagged with the fix) and newly flags nobody. Ranking:
members protected, then lower lender cost, then the lighter fix. The top 3 come back with their
replays and new R.

In the demo, option 1 is "Cut Lakshmi's installment by 50% from week 4": it protects Savitha,
Roopa and Latha, costs the lender Rs 104, and Kendra 3's R live goes from 3.00 to 0.00. Lakshmi
herself stays flagged; a lender cannot undo an illness.

### Stability

[`backend/sim/stability.py`](backend/sim/stability.py) reruns the whole attribution 50 times. Each
rerun multiplies every parameter in `PERTURBABLE` by its own U(0.7, 1.3) draw and uses fresh dice
(never the base run's). Inside one rerun, reality and its counterfactuals still share draws. The
badge shows two numbers: how many reruns flag her at all, and how many of those name the same
cause (same label, and same source for transmitted cases).

## Data and parameters

**Fully synthetic.** [`backend/sim/generator.py`](backend/sim/generator.py) builds kendras of
members with Indian first names, incomes, income sources, seasonality, savings and loans from a
seed. The demo is 5 kendras of 5 members; the generator scales to a whole branch.

**Regulatory caps**, enforced by the generator and checked by tests, and never perturbed:

* At most 3 lenders and Rs 2,00,000 total microfinance exposure per borrower: MFIN industry
  guardrails, November 2024.
* Total repayment obligations at most 50% of household income: RBI Regulatory Framework for
  Microfinance Loans, 2022.

### Every parameter

All tunable numbers live in [`backend/sim/params.py`](backend/sim/params.py), each with a source
or a reason. Fields marked P are perturbed by the stability check.

| Field | Value | Source or reason |
| --- | --- | --- |
| `max_lenders_per_borrower` | 3 | MFIN guardrails, Nov 2024 |
| `max_total_exposure_rs` | 200000 | MFIN guardrails, Nov 2024 |
| `max_installment_share` | 0.50 | RBI microfinance framework, 2022: ceiling on repayment share of household income |
| `installment_share_target` | 0.22 to 0.35 | Where the generator places members; lending at the ceiling would make everyone fragile before any shock |
| `horizon_weeks` | 12 | One quarter of weekly collections |
| `weeks_per_year` | 52 | Length of the seasonality array |
| `amber` (P) | 0.35 | Flagged: roughly a third of a week's due unmet, or savings down to two thirds, or a milder mix |
| `red` (P) | 0.65 | Sustained shortfall with the savings largely gone |
| `w_shortfall` (P) | 0.60 | The missed payment is what a field officer sees |
| `w_buffer` (P) | 0.40 | Paying in full by burning savings is fragility, not safety; without it cover would be invisible until default |
| `stress_memory` (P) | 0.50 | Distress does not reset every week; last week's stress decays by half |
| `expense_floor_share` (P) | 0.52 | Share of income that is essential consumption; calibrated, at 0.35 even a severe shock never reached amber |
| `expense_per_extra_member` | 0.02 | Each household member beyond the baseline size adds this share to consumption |
| `expense_baseline_household` | 4 | Household size the floor is quoted at |
| `buffer_draw_cap` (P) | 0.50 | A household does not empty all its savings into one week's installment |
| `buffer_topup_rate` (P) | 0.05 | Share of any surplus that becomes savings |
| `income_noise_halfwidth` (P) | 0.08 | Informal income varies week to week (uniform wobble) |
| `expense_noise_halfwidth` (P) | 0.10 | Same, for consumption |
| `p_cover` (P) | 0.55 | A peer steps in more often than not, but joint liability is social pressure, not automatic |
| `cover_capacity_share` (P) | 0.30 | Most of her meeting cash plus savings a peer commits to someone else in one week |
| `cover_min_peer_stress_block` (P) | 0.35 | A peer who is already stressed does not rescue anyone |
| `lender_pause_threshold` (P) | 0.30 | Unpaid share of a kendra's dues at which a lender stops top ups |
| `lender_pause_buffer_hit` (P) | 0.25 | Savings lost by a linked member in another kendra when her lender freezes |
| `p_lender_pause_bites` (P) | 0.60 | A freeze only hurts members who needed a top up that week |
| `shock_defaults` | health 0.65 for 4 weeks; crop loss 0.70 for 6; job loss 0.80 for 4; festival spend 0.30 for 2; weak monsoon 0.50 for 8 | Share of income lost (festival spend is an expense) and duration; scenario inputs |
| `expense_side_shocks` | festival spend | Shocks that raise expenses instead of cutting income |
| `health_expense_share` (P) | 0.25 | A health shock also adds a medical bill worth this share of income each week |
| `carry_cost_rate` | 0.0035 per week | Lender's cost of deferred money, roughly an 18% annual cost of funds |
| `scheme_delay_weeks` | 3 | A scheme does not pay out the week you apply (scheme linkage not built yet) |
| `r_window_weeks` | 4 | Look ahead for R, and the observation window a fix must leave; on the demo the counts saturate at 4 |
| `moratorium_weeks_grid` | 2, 4 | One or two fortnightly collection cycles |
| `reschedule_fraction_grid` | 0.5, 0.75 | Halve the installment, or take a quarter off |
| `buffer_weeks_range` | 0.8 to 2.0 weeks of income | Liquid savings in this segment are thin; at 1.5 to 4 weeks no shock ever bit inside a quarter |
| `seasonality_amplitude` | 0.15 | Lean season dip for agricultural income |
| `trend_range` | minus 0.002 to 0.002 per week | Ordinary drift |
| `declining_trend` | minus 0.030 per week | Given to a few members so genuine INDEPENDENT cases exist |
| `declining_share` | 0.10 | Share of members given that slipping trend |

### The demo scenario inputs, disclosed

[`data/demo_scenario.json`](data/demo_scenario.json) holds inputs only; a test checks it contains
no result words.

* Generator seed 42, draws seed 1, stability seed 1 with 50 reruns.
* One health shock on Lakshmi (m010) in Kendra 3, the kendra tied for the highest R potential
  (1.20). Severity is the default 0.65. **Duration 6 weeks (default 4) and start week 3 were
  chosen so the story is clear**, selected with [`scripts/tune_demo.py`](backend/scripts/tune_demo.py):
  a longer illness gives her peers more meetings at which to cover her. The target of every
  transmitted peer flagging in 35 of 50 reruns was not reached by any input, and no member was
  given special savings or income.
* Decision week 4: the officer hears of the illness at the week 3 meeting.
* The officer's note is checked against the run by a test.
* `display_name_overrides` gives seven members unique first names so the screen never shows two
  Pushpas. It changes name strings only;
  [`tests/test_names.py`](backend/tests/test_names.py) rebuilds the story with and without the
  overrides and requires every number to be identical.

## Validation, stated honestly

This tests the **logic**, not accuracy on real borrowers. No labelled dataset of microfinance
contagion exists, so the question is narrow: if stress spread the way the model says, and a
deployment could not see the hidden numbers, would the procedure name the right cause?

### Method

[`backend/validation/cause_recovery.py`](backend/validation/cause_recovery.py), 500 generated
scenarios with 1 to 3 planted shocks each (469 had someone flagged; 1901 flagged members).

* **Truth** runs with true parameters, incomes and dice. Its flagged members are the observed
  set, and its full knowledge labels are ground truth.
* **Replay under test** gets the same roster, shocks and event log, but parameters moved by up to
  20%, 15% noise on incomes and trends, and different dice. It must explain the observed set.
  In **threshold** mode it can only explain members its own noisy world also flags. In
  **anchored** mode (fixed before the run: own share 0.5, sole share 0.5, no signal below 0.01)
  it explains an observed flag by shares of the stress it does see, and reports `no_signal` when
  it sees almost none.
* **Simple rule**, no simulation: a shock means INDEX; otherwise, if the event log shows her
  covering someone, TRANSMITTED from whoever she covered most; otherwise INDEPENDENT. A test
  makes the simulator raise inside it, so it cannot cheat.

### Results, n = 500, run once (correct of total)

**Same subset**: the members the threshold replay could explain. The fair head to head.

| True label | Replay, threshold | Replay, anchored | Simple rule |
| --- | ---: | ---: | ---: |
| INDEX | 775 of 777 | 775 of 777 | 777 of 777 |
| TRANSMITTED | 388 of 513 | 388 of 513 | **420 of 513** |
| INDEPENDENT | **85 of 92** | **85 of 92** | 72 of 92 |
| Total | 1248 of 1382 | 1248 of 1382 | **1269 of 1382** |

**Unexplained subset**: members the threshold replay could not explain.

| True label | Replay, threshold | Replay, anchored | Simple rule |
| --- | ---: | ---: | ---: |
| INDEX | 0 of 3 | 3 of 3 | 3 of 3 |
| TRANSMITTED | 0 of 477 | 326 of 477 | **388 of 477** |
| INDEPENDENT | 0 of 39 | **32 of 39** | 29 of 39 |
| Total | 0 of 519 | 361 of 519 | **420 of 519** |

**All observed members.** This is the table the app shows.

| True label | Replay, threshold | Replay, anchored | Simple rule |
| --- | ---: | ---: | ---: |
| INDEX | 775 of 780 | 778 of 780 | 780 of 780 |
| TRANSMITTED | 388 of 990 | 714 of 990 | **808 of 990** |
| INDEPENDENT | 85 of 131 | **117 of 131** | 101 of 131 |
| Total | 1248 of 1901 | 1609 of 1901 | **1689 of 1901** |

Anchored mode left 35 members as `no_signal`.

What this means:

* **The simple rule wins overall**, on the same subset (1269 against 1248) and on all members
  (1689 against 1609 anchored).
* **The simple rule names contagion sources better.** In this model guarantee cover is the main
  channel and the event log records it, so "blame whoever she covered most" is a strong rule.
* **The replay better identifies borrowers whose own income is slipping**: 117 of 131 against
  101 of 131. The rule calls a slipping income TRANSMITTED whenever she once covered a
  neighbour. This is a small count, and it is the case that changes what the officer should do.
* **Only the replay can test a fix before it is tried**, which a rule over past records cannot.
* INDEX is solved by both and earns no credit.

**Pre registered prediction.** Before the run we predicted the simple rule would score higher on
the same subset than on all members, because the members the replay can explain are the easier
ones. **It held**: 1269 of 1382 against 1689 of 1901. We also wrote down that if the rule then
matched or beat the replay on the same subset, we would say so. It did, and we do.

**Superseded.** An earlier n = 100 run compared the replay's accuracy on the members it explained
with the rule's accuracy on all members. Those are different populations, so that comparison is
withdrawn and replaced by the tables above.

Near simultaneous shocks (two within 2 weeks) were not harder for either method: the replay
explained 912 of 1012 correctly there against 336 of 370 in the other scenarios.

### Stability of the demo labels

From the snapshot, 50 reruns each:

| Member | Label | Reruns that flag her | Same cause among those |
| --- | --- | ---: | ---: |
| Lakshmi | INDEX | 50 of 50 | 50 of 50 |
| Latha | TRANSMITTED from Lakshmi, week 5 | 27 of 50 | 27 of 27 |
| Savitha | TRANSMITTED from Lakshmi, week 7 | 28 of 50 | 28 of 28 |
| Roopa | TRANSMITTED from Lakshmi, week 8 | 22 of 50 | 21 of 22 |
| Meena | INDEPENDENT | 37 of 50 | 36 of 37 |
| Suma | TRANSMITTED from Meena, week 12 | 12 of 50 | 12 of 12 |

The transmitted cases are **marginal**: a neighbour lands just over the amber line, so in about
half the reruns she stays green. When she is flagged, the cause named is almost always the same.
Hard to call, easy to explain. The same marginality is why the replay leaves many transmitted
members unexplained in threshold mode.

## Limitations

* **Synthetic only.** Every number describes the model, not any real household. The parameters
  are reasoned, not fitted to data.
* **The transmitted demo cases are marginal** under parameter noise (22 to 28 of 50 reruns).
* **The shared lender channel flags nobody in the demo.** It fires in five weeks (in one of
  them 13 members in other kendras lose savings when a lender freezes top ups) but never pushes
  anyone in another kendra to amber, so cross kendra contagion is modelled but not shown.
* **Directional reality checks** (more lenders means more overdue, and so on) are not built.
* **Not built yet:** LLM note extraction and its fallback parser (the officer's note in the demo
  is scenario input), voice input, the HTTP API (the app reads a static snapshot), integrations
  with lender systems, government scheme linkage, and deployment.

## Privacy by design

* **Officer only view.** The screen is for the loan officer. Nothing implies that group members
  see each other's status, and the app says "Visible to the loan officer only".
* **Supportive actions only.** The only actions are a pause or a smaller installment. There is no
  penalty, no ranking of borrowers and no action against a member.
* The screen shows first names only. All names are synthetic.
