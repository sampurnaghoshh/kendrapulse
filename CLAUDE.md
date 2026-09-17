# CLAUDE.md: KendraPulse prototype (build contract)

Hackathon prototype for microfinance "stress tracing". Deadline is tight: a demo that WORKS beats an ambitious one that breaks.
Pitch and strategy context lives in `docs/STRATEGY.md` (git ignored). Do not read it unless asked.

## What we are building
When a borrower in a joint liability group (kendra) becomes stressed, label her as:
* INDEX: her own shock caused it.
* TRANSMITTED: stress arrived from another member (guarantee cover, shared income, shared lender).
* INDEPENDENT: her own income trend is slipping, unrelated to any shock.
Then find the smallest supportive intervention that stops the spread, and show the counterfactual visually ("Two worlds" view).

## Working rules for Claude Code
* Work phase by phase (see Build phases). Finish a phase, run its checks, summarise the design decisions in 5 lines, then STOP and wait.
* Simple, readable code over clever code. Comment the WHY. The team must be able to explain every line to judges.
* `sim/` is pure functions: no global state, no I/O, everything driven by an explicit seed.
* NEVER hardcode demo outputs (R values, "47 of 50", members protected). They must come from real runs. Tuning the seeded demo scenario's inputs (severities, buffers, incomes) to get a clear story is fine; special casing code paths for it is not.
* Do not add dependencies, a database, auth or Docker without asking.
* All tunable numbers live in `backend/sim/params.py` with a comment giving the source or the reason.
* UI copy visible on screen avoids hyphens and dashes (it appears in the judged video). Code, identifiers and URLs are exempt.
* Commit after each working phase with a clear message.

## Stack
* Backend: Python 3.11, FastAPI, NumPy, NetworkX, pytest. No database: scenarios are JSON files.
* Frontend: React + Vite, plain SVG for the graph (fixed layout, no physics engine), plain CSS. No component library.
* LLM: one JSON mode call for note extraction, key in backend env var `LLM_API_KEY`, with a keyword fallback parser.
* Deploy last (Vercel frontend, Render backend) with a static snapshot fallback.

## Repo layout
```
backend/
  app.py
  sim/ params.py generator.py engine.py attribution.py r_number.py interventions.py smallest_fix.py stability.py
  nlp/ extract.py
  validation/ cause_recovery.py reality_check.py
  scripts/ demo_story.py export_snapshot.py run_validation.py
  tests/
frontend/ src/components/ GraphView TwoWorldsView WeekSlider ExplanationCard StabilityBadge SmallestFixPanel NoteInput ValidationReport
data/ demo_scenario.json validation_report.json
```

## Data model
* Member: `id, name, kendra_id, weekly_income, income_source, seasonality[52], income_trend, savings_buffer, household_size, loans[{lender, weekly_installment, outstanding}]`.
* Calibration: at most 3 lenders and Rs 2,00,000 total microfinance exposure per borrower (MFIN guardrails, Nov 2024); total installments at most 50% of household income (RBI 2022 framework). The generator must enforce these and a test must check them.
* Edges (NetworkX MultiGraph, `type` attribute): `guarantee` (all members of the same kendra, strongest), `shared_income` (same employer, crop or market, can cross kendras), `shared_lender` (same lender, can cross kendras).
* Shock: `{member_id | income_source, type, start_week, duration_weeks, severity}`. Types: `health, crop_loss, job_loss, festival_spend` (one member) and `weak_monsoon` (every member on an income source; counts as each affected member's OWN shock, tagged `common_shock`).
* Demo: 5 kendras x 5 members, synthetic Indian names, seeded. Generator must scale to a branch (for example 40 kendras).

## Simulation engine (`sim/engine.py`)
* Horizon 12 weeks, weekly steps. Signature: `simulate(scenario, shocks, interventions, params, draws) -> Run`.
* Each week per member: income = base x seasonality x trend x shock multiplier; cash = income + buffer draw; due = sum of installments (after interventions).
* Pays in full if cash >= due. Otherwise partial; each guarantee peer covers part of the shortfall if `draw < p_cover`, which reduces that peer's cash and buffer (guarantee channel).
* Shared income shocks hit all members on that source together (correlated channel).
* Shared lender channel: if a kendra's overdue share passes `lender_pause_threshold`, that lender pauses top ups for linked members in other kendras, lowering their buffer.
* Stress s in [0, 1] from shortfall ratio and buffer depletion. Status: green / amber (s >= `amber`) / red (s >= `red`). "Flagged" means amber or worse.
* COMMON RANDOM NUMBERS (critical): all randomness is pre drawn once per scenario as `draws[member, week, channel]` from the seed. Actual and counterfactual runs reuse the SAME draws, so any difference between the two worlds comes only from the removed shock, never from dice.
* EVENT LOG: record every transfer `{week, channel, from_id, to_id, amount}`. Used for explanation paths and as ground truth in validation.
* Output per week per member: cash, paid, shortfall, buffer, s, status. Plus event log.

## Attribution (`sim/attribution.py`)
For each member j flagged at any week up to `as_of_week` in the actual run, in this order:
1. Run with NO shocks. If j is still flagged: INDEPENDENT.
2. Run with ONLY j's own shocks (including common shocks on her income source). If j is flagged: INDEX (carry the `common_shock` tag if relevant).
3. Otherwise TRANSMITTED. For each other shocked member i, run actual minus i's shocks and measure the drop in j's peak stress. Source = largest drop. If removing that source alone unflags j: `sole_source = true`; else `sole_source = false` and return the top 2 contributors.
4. Explanation path: the chain of event log transfers from source to j (fall back to shortest graph path if none).
Return `{member_id, label, source_id, sole_source, path, first_flag_week, tags}`.

## R number (`sim/r_number.py`)
* R live (kendra, week w): transmitted cases flagged by week w whose source is an index case in that kendra, divided by index cases flagged by week w. Only defined when there is at least one index case.
* R potential (kendra): plant a standard health shock on each member alone, count other members flagged within 4 weeks, average. Defined even when everyone is green.
* UI shows R potential when there are no index cases, R live otherwise, and says which one it is.

## Interventions (`sim/interventions.py`, `sim/smallest_fix.py`)
* `moratorium(member, start_week, weeks)`: installments deferred. Lender cost = deferred amount x `carry_cost_rate`.
* `reschedule(member, start_week, installment_fraction)`: lower installment. Lender cost = reduction over horizon x `carry_cost_rate`.
* `scheme_linkage(member, start_week, income_boost)`: takes effect after `scheme_delay_weeks` (default 3). Lender cost 0, tagged "depends on scheme approval" so it does not unrealistically dominate.
* Members protected = flagged in actual AND not flagged with the intervention. An intervention that newly flags anyone is rejected.
* Smallest fix: try every member x type x small parameter grid, rank by members protected desc, then lender cost asc. Return top 3 with their replays and new R.

## Stability (`sim/stability.py`)
50 runs; each run uses a new seed and multiplies each parameter in `params.PERTURBABLE` by U(0.7, 1.3). Within a run, actual and counterfactual share draws. Stability = runs where the label (and source, for transmitted) matches the base label. Display as "stable in k of 50 runs".

## Note extraction (`nlp/extract.py`)
`POST /notes/extract {kendra_id, text}` returns
`{signals: [{member_name, member_id, paid_fraction, covered_by: [ids], shock_type, confidence}], source: "llm" | "fallback"}`.
Resolve names against the kendra roster. On missing key, error, invalid JSON or a timeout over 8 s, use the keyword fallback. The officer confirms fields in the UI before they become a shock in the scenario.

## API (`app.py`)
* `GET /scenario/demo` roster, edges, fixed layout coordinates, seeded shocks
* `POST /simulate {shocks, interventions, weeks, seed}` weekly states, event log, R per week, Rs at risk
* `POST /attribute {shocks, interventions, as_of_week, seed, with_stability}` labels, paths, stability
* `POST /counterfactual {member_id, seed}` actual run and run without the attributed source (for Two worlds)
* `POST /smallest_fix {shocks, seed}` top 3 interventions with replays
* `POST /notes/extract` as above
* `GET /validation/report` contents of `data/validation_report.json`

## Validation (`validation/`)
Tests the LOGIC, never accuracy on real borrowers.
* Cause recovery: ~500 random scenarios with 1 to 3 planted shocks. Ground truth = attribution procedure run with TRUE params and TRUE draws (full knowledge). Engine under test attributes with perturbed params (+/-20%), noisy incomes and a DIFFERENT seed, as a real deployment could not see hidden incomes or dice. Report agreement per class, confusion matrix, and listed failure cases (for example two simultaneous shocks). Save to `data/validation_report.json`.
* Reality check: more lenders -> more overdue; weak monsoon hits a shared income source together; low overdue in normal conditions. Present as sanity checks, not evidence.

## Frontend
* GraphView: 5 kendra clusters on a ring, members on small circles, coordinates from the backend so every panel uses identical positions. Node colour = status at current week; edges pulse when the event log has a transfer that week.
* WeekSlider: shared slider plus play button (about 700 ms per week).
* TwoWorldsView: two GraphViews side by side on the SAME slider (left reality, right world without the source shock). Fallback if short on time: one view with a "what if" toggle.
* ExplanationCard: one sentence per flag ("Transmitted from Lakshmi through group guarantee cover in week 3") + StabilityBadge.
* SmallestFixPanel: ranked top 3, "Apply" replays with the intervention and shows new R and Rs at risk avoided.
* NoteInput: textarea, extracted fields shown as editable chips, Confirm button.
* Privacy by design: no screen implies peers see a member's status; only supportive actions exist.
* If the API is unreachable, load `frontend/public/demo_snapshot.json` (exported by `scripts/export_snapshot.py`) so the seeded story still plays.

## Build phases (stop after each)
0. Skeleton: folders, requirements, FastAPI health route, Vite app that calls it, pytest running, `.gitignore` (includes `docs/STRATEGY.md`, `.env`).
1. `params.py`, `generator.py`, `engine.py` with draws and event log. Tests: same seed gives identical output; a run with no shocks is identical to its counterfactual; MFIN and RBI caps hold.
2. `attribution.py`, `r_number.py`. Tests on hand built mini scenarios: one clear index, one clear transmitted, one clear independent.
3. Interventions, smallest fix, stability. Then `scripts/demo_story.py` prints the whole demo story in the terminal. THIS IS THE GATE: if it tells the story, the prototype exists.
4. `validation/` and `scripts/run_validation.py` producing the report.
5. FastAPI routes + `export_snapshot.py`.
6. Frontend: GraphView + WeekSlider, then ExplanationCard, then TwoWorldsView, then SmallestFixPanel, then ValidationReport.
7. Note extraction with fallback + NoteInput.
8. README (setup, data assumptions, every parameter and its source, demo steps), deploy.

Cut order if behind: deploy, reality check, LLM (keep fallback parser), manual intervention sandbox, Two worlds animation (use toggle).
