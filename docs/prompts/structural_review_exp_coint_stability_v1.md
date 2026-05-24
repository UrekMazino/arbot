20-Trade Structural Review — Cointegration Stability Filter Experiment Outcome Assessment

This is the structural review for exp_coint_stability_v1. It evaluates whether Patch 7 (the entry-gate cointegration stability slope filter) reduces the coint-failure rate, whether the underlying premise (coint failures are predictable from entry-time slope) is true, and what the next research priority is. Per-run audits forbid conclusions; this review exists to draw them.

---

Trigger Conditions (Must Be Met Before Beginning)

- trades_since_experiment_start (Patch 7.1 calibration window) ≥ 20
- OR a named early-resolution trigger has fired: slope_exceeded=0 after 6 evaluated trades (calibration trigger) OR gate-inactivity trigger from Section 4C-TRIGGER in per-run template
- No active operational incident
- Most recent per-run audit completed and filed
- Bot stopped or in a known stable state

If any condition is unmet, halt and complete prerequisites first. If an early-resolution trigger fired before trade 20, note the trigger name and trade count at the top of the review — the verdict must honor the pre-committed consequence of that trigger, not treat it as optional.

---

Experiment State Block (Required at Top of Review)

Report verbatim:

  experiment_group: exp_coint_stability_v1
  experiment_phase: Structural Review
  runs_since_experiment_start: [list all runs: 105, 106, 107, 108, 109, 111, 112, ...]
  trades_since_experiment_start: [count, must be ≥ 20 OR explain early-trigger]
  evaluated_trade_count: [count — gate_status = evaluated; this is the real experimental N]
  insufficient_history_trade_count: [count — gate reached, buffer too small]
  not_reached_trade_count: [count — upstream gate blocked before safety gate ran]
  coint_stability_slope_exceeded_count: [count — filter fires across all experiment evaluations]
  closed_trades_with_complete_telemetry: [count]
  closed_trades_with_incomplete_telemetry: [count, list trade IDs and reason]
  circuit_breaker_trips_this_experiment: [count]
  patches_active: Patch 4.1, Patch 5, Patch 6, Patch 7, Patch 7.1
  review_date: [date]
  early_trigger_status: [NONE / CALIBRATION_TRIGGER (slope_exceeded=0 at N evaluated) / GATE_INACTIVITY]

The single most important state variable: evaluated_trade_count. All filter-effectiveness conclusions in this review rest on that number, not on trades_since_experiment_start. If evaluated_trade_count < 10 when the 20-trade threshold is reached, state this explicitly at the top of the review and reduce confidence levels accordingly.

---

Data Sources

Aggregate across all experiment runs (105, 106, 107, 108, 109, 111, 112, ...):

- trade_closes.csv from each run
- entry_rejections.csv from each run ← primary Patch 7 data source
- exit_decision_trace.csv from each run
- exit_opportunity_summary.csv from each run
- reconciliation_checks.csv from each run
- bot logs from each run (for pair_activation_timestamp per trade)
- pair_supply_control.json and pair_strategy_state.json where available

4D slope-vs-outcome tally: assembled incrementally in per-run audit Section 4D entries. Do not re-derive from raw CSVs — use the accumulated table from the per-run audits. Verify each row against the corresponding per-run audit Section 4A before using.

Prior baseline datasets (fixed references — do not re-derive):
- Raw baseline: runs 90, 93, 94 — 9 trades, 1 win, 56% coint-failure rate, cumPnL -$2.157
- exp_guard050_ethfi_excluded_v1: 20 trades (19 known PnL), 26.3% win rate, 36.8% coint-failure rate, cumPnL -$2.592

Data Assembly Protocol (complete before any analysis):

Step 1 — Locate report directories.
For each experiment run, confirm the Reports/ directory exists under Reports/v1/run_NNN_*/. List every CSV file present. If a run has no Reports/ directory at all, mark that entire run's trades as "no telemetry" — they count toward the trade total but are excluded from mechanism analysis.

Step 2 — Assemble the master trade table.
Concatenate trade_closes.csv across all experiment runs. Add a run_id column to each row. Verify: no duplicate trade_id values across runs, every row has a non-null pnl_usdt field, entry_ts and exit timestamps parse as valid values. Note: trade_closes.csv uses entry_z, exit_z, pnl_usdt, max_favorable_pnl_usdt (MFE), max_adverse_pnl_usdt (MAE), exit_reason, hold_minutes.

Step 3 — Link exit_decision_trace.
For each trade in the master table, confirm rows exist in exit_decision_trace.csv for the corresponding run. If a trade has zero trace rows, mark as "no trace."

Step 4 — Link reconciliation_checks.
For each trade, confirm a row exists in reconciliation_checks.csv for the corresponding run. If absent, mark as "no reconciliation."

Step 5 — Record available columns.
Before analysis, list the exact column names present in each CSV type. The column names in the actual files are authoritative — if a column name in this document differs from what is in the file, use the file's column name and note the discrepancy.

Known field naming patterns (verify against actual files at review time):
- trade_closes.csv: pair, side, entry_ts, exit_ts, entry_z, exit_z, pnl_usdt, pnl_pct, strategy, regime, hold_minutes, exit_reason, entry_notional_usdt, max_favorable_pnl_usdt, max_adverse_pnl_usdt
- entry_rejections.csv: timestamp, pair, gate, reason, component_scores (JSON with coint_stability_check_evaluated_count, coint_stability_insufficient_history_count, coint_stability_check_blocked_count, coint_stability_slope)
- reconciliation_checks.csv: pair, trade_pnl, equity_change, difference, fees, slippage, funding, unexplained, pass_fail

Step 6 — Aggregate the 4D slope-vs-outcome table.
Copy the running slope-vs-outcome tally from the final per-run audit's Section 4D. Verify each row against its source per-run audit Section 4A. Confirm: every row has gate_status = evaluated AND coint_stability_check_blocked_count = 0. Blocked trades must not appear in this table. If any row is uncertain, re-derive from entry_rejections.csv for that pair and run.

---

Section 1 — Dataset Inventory

Before any analysis, establish what data exists and its quality.

Trade inventory:

- Total experiment trades (Patch 7.1 calibration window): [count]
- Per-run breakdown: [run_111 (1), run_112 (N), ...]
- Win/loss totals across the full window
- Trades with complete telemetry: [count]
- Trades with incomplete telemetry: [count, with specific reasons]

Gate-status inventory (the real N computation):

| Gate Status | Count | Pct of total |
|---|---|---|
| evaluated | [N] | [pct] |
| insufficient_history | [N] | [pct] |
| not_reached | [N] | [pct] |
| **evaluated_trade_count (real N)** | **[N]** | |

State explicitly: "The filter-effectiveness verdict in Section 10 rests on [evaluated_trade_count] evaluated trades, not on [trades_since_experiment_start] total trades."

If evaluated_trade_count < 10: "Sample is underpowered. Verdict confidence is reduced. All filter-effectiveness findings in this review are preliminary."
If evaluated_trade_count < 6: "Sample is insufficient for verdict. Verdict C (inconclusive/underpowered) is the required outcome regardless of observed patterns."

Definition of "complete telemetry" — a trade meets this standard if ALL of the following are true:
1. Appears in trade_closes.csv with a non-null pnl_usdt field
2. entry_rejections.csv has rows for this pair in this run (Patch 7 gate status derivable)
3. reconciliation_checks.csv has exactly 1 row for this trade
4. Trade was NOT affected by a mid-run restart that could reset position or baseline
5. Trade was NOT a manual close where the bot did not execute the exit

Known incomplete-telemetry trades to carry forward:
- [Add from per-run audits — note run, pair, reason]

Baseline dataset (fixed references — do not re-derive):
- Raw baseline coint-failure rate: 56% (5/9 trades, runs 90/93/94)
- exp_guard050 coint-failure rate: 36.8% (7/19 known-PnL trades)
- The exp_guard050 rate is the more relevant comparator — same codebase, same pair universe, only experiment group changed

---

Section 2 — Outcome Comparison: Experiment vs Prior Experiments

This section reports raw outcome distributions. Do not interpret in this section.

Per-trade outcome table. Compute using pnl_usdt from trade_closes.csv:

| Metric | Raw baseline (9 trades) | exp_guard050 (19 trades) | exp_coint_stability (N trades) |
|---|---|---|---|
| Win rate | 1/9 = 11% | 5/19 = 26.3% | [wins]/[total] |
| Avg PnL/trade | -$0.239 | -$0.137 | [sum / count] |
| Avg win | +$0.133 | [value] | [sum wins / wins] |
| Avg loss | -$0.270 | [value] | [sum losses / losses] |
| Largest win | +$0.133 | [value] | [max] |
| Largest loss | -$0.549 | [value] | [min] |
| Cumulative PnL | -$2.157 | -$2.592 | [sum] |

MFE distribution — bin max_favorable_pnl_usdt from trade_closes.csv:
  < $0.05, $0.05–$0.10, $0.10–$0.17, $0.17–$0.23, > $0.23
  Report count and pct per bin. Note how many trades never reached $0.17 (the profit-lock floor).

MAE distribution — bin max_adverse_pnl_usdt using the same bins.

Hold duration distribution — bin hold_minutes:
  < 10min, 10–30min, 30min–2h, 2–8h, > 8h

Entry z distribution — bin entry_z:
  < 1.5, 1.5–2.0, 2.0–2.5, 2.5–3.0, > 3.0

Per-symbol outcomes:
For each symbol appearing in ≥ 2 trades, report: appearances, win rate, avg PnL, coint-failure count. Note whether it also appeared in exp_guard050.

---

Section 3 — Filter Effectiveness (Primary Research Question)

This is the centerpiece of the review. The three sub-sections form a chain: 3A establishes whether the filter was ever active, 3B tests whether the premise is true, 3C measures the outcome effect. All three must be populated; do not skip to 3C.

3A — Gate Activity: Was the filter ever active?

Source: entry_rejections.csv for all experiment runs. Count rows where component_scores contains coint_stability_check_blocked_count ≥ 1.

- coint_stability_slope_exceeded_count (cumulative, all evaluations): [N]
- evaluated_count across all evaluations: [N]
- fire_rate = slope_exceeded_count / evaluated_count: [pct]

Pre-committed calibration rule — apply here, do not defer:
- fire_rate < 15%: filter passes nearly everything. Calibration adjustment: slope_max 0.020 → 0.030. State explicitly whether this trigger applies.
- fire_rate > 60%: filter blocks too aggressively. Calibration adjustment: slope_max 0.020 → 0.012. State explicitly whether this trigger applies.
- 15% ≤ fire_rate ≤ 60%: filter is active at a plausible rate. Proceed to 3B.

If slope_exceeded_count = 0:
State: "The filter passed every evaluated entry. Fire rate = 0%. This satisfies the pre-committed calibration trigger (< 15%). The slope_max parameter must be loosened to 0.030 before the next experiment window. The premise cannot be tested via blocks — it can only be assessed via the 3B passed-then-failed analysis."
Do not frame this as "inconclusive" — it has a defined consequence.

3B — Premise Check: Do entry slopes predict cointegration failures?

Source: the 4D slope-vs-outcome tally assembled in Step 6 of Data Assembly. This table contains only gate-evaluated trades that passed the filter (blocked_count = 0) and then closed.

Aggregate the 4D table:

| Exit Category | Count | Mean slope | Median slope | Mean delta_from_threshold | Median delta_from_threshold |
|---|---|---|---|---|---|
| coint-failure | [N] | [value] | [value] | [value] | [value] |
| normal | [N] | [value] | [value] | [value] | [value] |

Delta convention (slope_max − slope_at_entry): large positive delta = slope far below threshold; small or negative delta = slope near or above threshold. Cutoffs: delta < 0.005 → near-catchable; delta > 0.015 → filter could not have caught this failure at current threshold.

Premise assessment:

Near-threshold failures (delta < 0.005): [count] of [total coint-failures]
Far-below-threshold failures (delta > 0.015): [count] of [total coint-failures]

Interpretation guide:
- If most coint-failure deltas are small (< 0.005): slopes were near the threshold — the premise may hold, threshold tuning could reduce failures. Proceed to 3C with higher confidence.
- If most coint-failure deltas are large (> 0.015): slopes were far below threshold (like T5 at delta +0.02449). No threshold tuning would have caught these. The premise — that coint failures are predictable from entry-time slope — is not supported by the data. Note this explicitly; it informs Verdict B.
- If coint-failure slopes are indistinguishable from normal-exit slopes: the slope measurement has no discriminating power.

Do not conclude from this section. State the pattern and defer conclusion to Section 10.

3C — Coint-Failure Rate on Evaluated Trades

Compute coint-failure rate on the evaluated-trades-only population (the real experimental N). Compare against both baselines.

| Population | Coint-failure rate |
|---|---|
| Raw baseline (9 trades) | 56% |
| exp_guard050 (19 trades) | 36.8% |
| exp_coint_stability, ALL trades | [coint-exits / trades_since_experiment_start] |
| exp_coint_stability, evaluated trades only | [coint-exits among evaluated / evaluated_trade_count] |

The evaluated-only rate is the primary comparison. The all-trades rate is context only.

Success threshold: coint-failure rate ≤ 25% among evaluated trades (pre-committed target from Patch 7 specification).
Null threshold: coint-failure rate ≥ 30% among evaluated trades after 20 trades (pre-committed null criterion).

State the rate and which threshold it falls relative to. Do not interpret — that is Section 10's job.

---

Section 4 — Cointegration Fragility Analysis

Exit reason distribution (count + pct of total trades):

| Exit reason | Raw baseline (9) | exp_guard050 (19) | exp_coint_stability (N) |
|---|---|---|---|
| cointegration_lost | 5 (56%) | [count] ([pct]) | [count] ([pct]) |
| cointegration_watch_timeout | [count] ([pct]) | [count] ([pct]) | [count] ([pct]) |
| trailing_stop / profit_lock | [count] ([pct]) | [count] ([pct]) | [count] ([pct]) |
| health exits | [count] ([pct]) | [count] ([pct]) | [count] ([pct]) |
| regime_break | [count] ([pct]) | [count] ([pct]) | [count] ([pct]) |
| other | [count] ([pct]) | [count] ([pct]) | [count] ([pct]) |

For any "other" exit_reason, list the actual string values — do not aggregate unknown exits.

Per-trade coint timing (for each coint-failure exit in the experiment):
- time_to_failure = exit_ts minus entry_ts (minutes)
- Report: min, median, max time-to-failure
- exp_guard050 reference for median: [value from prior audits]
- If experiment median is materially shorter: pairs are failing faster post-entry
- If materially longer: pairs are surviving longer before failing

Split by gate status:

| Gate status | Coint-failure count | Total count | Coint-failure rate |
|---|---|---|---|
| evaluated | [N] | [N] | [pct] |
| insufficient_history | [N] | [N] | [pct] |
| not_reached | [N] | [N] | [pct] |

If the coint-failure rate is materially different across gate status groups, state what that implies: the filter may be correlated with better pairs (selection effect) or the upstream gates already remove most coint-fragile pairs.

Confidence update:
- Prior state: HIGH confidence that cointegration fragility is the dominant loss driver
- Post-experiment update: [CONFIRM HIGH / LOWER TO MEDIUM / raise]
- Justification: cite coint-failure rate, total dollar losses from coint exits, and whether finding is consistent across runs.

---

Section 5 — MFE Timing and Execution Cost Analysis

5A — MFE Timing Pattern (Deferred Item 10)

exp_guard050 finding: early_hold = always loss (0/5 wins in early_hold bucket). Does this replicate?

MFE timing bucket computation:
Source: exit_decision_trace.csv. For each complete-telemetry trade, find the row where mfe_at_eval is maximum. Compute:
  mfe_timing_pct = elapsed_seconds_at_max_mfe / hold_duration_seconds × 100

If mfe_timing_pct is pre-computed in exit_opportunity_summary.csv, use that directly.

Bucket classification: early_hold (0–33%), mid_hold (34–66%), late_hold (67–100%).

| Bucket | All trades (count, pct) | Winners | Losers |
|---|---|---|---|
| early_hold | [count] ([pct]) | [count] | [count] |
| mid_hold | [count] ([pct]) | [count] | [count] |
| late_hold | [count] ([pct]) | [count] | [count] |

exp_guard050 finding validation: winner late_hold rate ≥ 70% AND loser early_hold rate ≥ 70% = pattern confirmed.

If confirmed with ≥ 10 trades: promote Item 10 to NEXT PRIORITY candidate in Section 8.
If not confirmed: CLOSE Item 10 as exp_guard050 noise.

5B — Execution Cost Pattern (Meme-Token Sub-Pattern, Item 12)

Known occurrences going into this review:
- HMSTR run_102: unexplained residual −$0.226 (graveyarded, high_execution_cost_meme_token, $200 notional)
- FLOKI run_111: unexplained residual −$0.093 (monitoring, $200 notional)

From reconciliation_checks.csv across all experiment runs, identify all rows where:
- unexplained residual < −$0.05 (exceeds audit threshold)
- pair includes a low-liquidity or meme-category token (FLOKI, HMSTR, SHIB, or similar)

Count additional meme-token anomalies in this experiment: [N]

Meme-token escalation rule (pre-committed): third occurrence → propose category exclusion at this structural review.

If third occurrence found: state both dispositions — (1) graveyard proposal for the specific token, (2) Item 12 escalation (per-pair-tier cost model). Do not choose between them; carry both forward. The graveyard is the stopgap; the cost model is the real fix.

If fewer than 3 occurrences: confirm n=[count], continue monitoring, no action required at this review.

Standard anomaly tracking (all pairs):
- Total trades with |unexplained residual| > $0.05: [count]
- Total cumulative unexplained residual (negative only): [sum]
- Total cumulative unexplained residual (positive only): [sum]
- Materiality: if |cumulative negative unexplained| > $0.30 across the experiment, flag for dedicated investigation.

---

Section 6 — Shadow Block Findings

Source: entry_rejections.csv. Shadow filter fields are prefixed shadow_ or shadow_* in component_scores. Locate exact column names at review time.

For each shadow filter with ≥ 1 firing:
- Total firings: [count]
- Entries subsequently allowed that became wins: [count]
- Entries subsequently allowed that became losses: [count]
- Win rate on shadow-blocked evaluations vs. overall experiment win rate: [compare]

Recommendation criteria:
- REJECT: winners blocked / total firings is within ±15 pp of overall win rate. No discriminating power.
- DEFER (activate next experiment): winners blocked / total firings < (overall win rate − 15 pp). Filter fires disproportionately on losers.
- DEFER (insufficient data): total firings < 5.

For each filter, state the recommendation explicitly. Do not use hedged language.

---

Section 7 — Reconciliation Anomaly Patterns

7A — Negative residual pattern (adverse-exit fill quality, Item 8):

Known occurrences to carry forward (verify against reconciliation_checks.csv; do not recompute from memory):
- Run 99 FIL/LINEA: unexplained −$0.121
- Run 100 BNB/LDO: unexplained −$0.068
- Run 111 FIL/FLOKI: unexplained −$0.093 (meme-token)
- [Add all experiment occurrences with unexplained < −$0.020]

Analysis:
- Confirm all known occurrences have negative unexplained on adverse-spread exits (cointegration_lost, coint_watch_timeout, health)
- Count occurrences on normal/trailing-stop exits (expected: zero)
- Median negative unexplained across all occurrences: [value]
- Cumulative impact: sum of unexplained for negative cases only
- Materiality: if |cumulative negative unexplained| > $0.30, flag for dedicated investigation (Item 8)

7B — Positive residual anomaly:

Known occurrences: ETH/ETC run_100 +$0.145, DOGE/BNB +$0.078 (from prior experiment).
Check all experiment runs for trades with unexplained > +$0.050.
- If zero additional occurrences: no action.
- If ≥ 1 additional occurrence: state both trade IDs, exit conditions, and timing. Consider pattern.

---

Section 8 — Deferred Research Items Review

Every item must receive one of: NEXT PRIORITY, DEFER (carry forward), or REJECT (close). Items cannot remain ambiguous.

Item 1 — Forward-looking coint stability (this experiment's primary item):
Resolved here. Disposition determined by Section 10 verdict.
- If Verdict A (filter works): NEXT PRIORITY to tune slope_max or extend window.
- If Verdict B (premise wrong): REJECT slope approach, promote alternative mechanism or Item 12.
- If Verdict C (inconclusive): DEFER with explicit minimum additional trade count.

Item 2 — Regime-flip exit timing:
Background: run_98 ETH/AVAX held 4.5h after regime committed to TREND. Did any experiment run show similar delay?
Evidence: check exit_reason = regime_break combined with hold > 3× median hold.
Disposition: [NEXT PRIORITY / DEFER / REJECT]

Item 3 — max_break_risk recalibration:
Background: median rejected break_risk = 0.150 at cap. Prior reasoning: defer until coint first.
Evidence from this experiment: has break_risk distribution changed? Has it been the binding gate on trades that later failed?
Disposition: [NEXT PRIORITY / DEFER / REJECT] — re-evaluate ordering now that coint has been addressed.

Item 4 — Notional adjustment:
Background: ratios unchanged with notional. No notional-dependent effect identified.
Evidence: any experiment trade show notional sensitivity?
Disposition: [NEXT PRIORITY / DEFER / REJECT] — default DEFER unless evidence emerged.

Item 5 — Alert/kill-switch (Patch 6 Item 5):
Background: Patch 6 outer backoff applied. Incident never recurred.
Evidence: has Patch 6 exponential backoff triggered in any experiment run? Check logs for backoff messages.
Disposition: [NEXT PRIORITY / DEFER / REJECT]

Item 6 — Exit z-zone widening:
Background: lower priority. What is the distribution of exit_z across experiment trades?
Evidence: any pattern suggesting the TP zone is too narrow?
Disposition: [NEXT PRIORITY / DEFER / REJECT]

Item 7 — Profit-lock band mechanism (Patch 5):
Prior disposition: confirmed operational, inert in contribution. Verdict B (exp_guard050).
Disposition: RETAIN Patch 5 configuration, do not re-investigate. State as CLOSED — mechanism understood, contribution $0.00 net in prior experiment.

Item 8 — Adverse-exit fill quality:
From Section 7A analysis.
Disposition: [ADD AS DEFERRED ITEM — total and cite amount / CLOSE — within noise]

Item 9 — Positive reconciliation residuals:
From Section 7B analysis.
Disposition: [OPEN investigation if ≥ 1 additional occurrence / CLOSE — one-off]

Item 10 — MFE timing (early_hold = always loss):
From Section 5A analysis.
Disposition: [NEXT PRIORITY if pattern confirmed at ≥ 70% in both buckets / CLOSE if not confirmed]

Item 11 — DOGE/HMSTR execution cost anomaly:
Prior disposition: RESOLVED — root cause HMSTR execution cost 2.6× standard, HMSTR graveyarded. No further action.
Disposition: CLOSED.

Item 12 — Execution cost model:
Background: standard $0.14 flat estimate underestimates real cost on adverse exits and low-liquidity pairs. HMSTR 2.6× standard, FLOKI excess −$0.093. At $200 notional.
Evidence from this experiment: additional meme-token anomalies found? Total cumulative unexplained from Item 8?
Disposition: [NEXT PRIORITY if meme-token n ≥ 3 or cumulative negative unexplained > $0.30 / DEFER / REJECT]

---

Section 9 — Confidence Calibration Final Update

Confidence level definitions (apply consistently):
- VERIFIED: Mechanically confirmed in production — a confirmed fact, not a probability
- HIGH: ≥ 0.80 probability. Multiple supporting trades (≥ 5), pattern consistent, mechanism understood
- MEDIUM: 0.50–0.79 probability. Some evidence (3–5 trades), mechanism plausible, not consistently confirmed
- LOW: < 0.50 probability. Hypothesis only, few or conflicting observations, or mechanism unconfirmed
- UNTRACKED: Not yet measured

Update every confidence variable. Every change must cite specific trade counts and PnL figures.

| Hypothesis | Pre-experiment | End-of-experiment | Justification |
|---|---|---|---|
| confidence_coint_stability_slope_predictive | LOW | [update] | [evidence from 3B: near-threshold vs far-below-threshold failure count, real N] |
| confidence_coint_filter_reduces_failure_rate | UNTRACKED | [new value] | [evidence from 3C: experiment rate vs 36.8% baseline, evaluated N] |
| confidence_coint_fragility_as_dominant_problem | HIGH | [update] | [evidence from Section 4: coint-failure rate, total dollar losses] |
| confidence_meme_token_execution_cost_anomaly | MEDIUM (n=2) | [update] | [evidence from 5B: additional occurrences, cumulative unexplained] |
| confidence_execution_cost_model_accuracy | MEDIUM | [update] | [evidence from 5B and 7A: standard $0.14 estimate vs observed costs] |
| confidence_mfe_timing_predictive | MEDIUM (exp_guard050) | [update] | [evidence from 5A: replication or failure at 20 trades] |
| confidence_profit_lock_band_mechanism | MEDIUM (Patch 5 inert) | [no change expected] | [Patch 5 settled — state "no new evidence, no change"] |
| confidence_trend_regime_mr_block_active | VERIFIED | VERIFIED | [Patch 4.1 confirmed in production — see DECISION_LOG.md] |
| confidence_emergency_flatten_safety | PATCH_6_APPLIED | [update] | [was outer backoff exercised in production in this experiment? yes/no] |
| confidence_break_risk_threshold_correctness | MEDIUM | [update] | [evidence from entry_rejections analysis] |
| confidence_notional_neutrality | HIGH | [update] | [any notional-dependent effect found?] |

Do not change a confidence level without citing specific evidence. "No new evidence, no change" is a valid justification — state it explicitly.

---

Section 10 — Structural Verdict on Coint Stability Filter

Based on Sections 1–9, deliver an explicit verdict. Choose the verdict before writing the narrative. Do not write a narrative that hedges between verdicts.

Verdict selection guide:

Verdict A — Filter works:
Meets ALL of:
- coint_stability_slope_exceeded_count ≥ 3 (filter was active, not just observing)
- Section 3B: coint-failure delta_from_threshold median < 0.010 (failures were near threshold — slope was predictive)
- Section 3C: coint-failure rate among evaluated trades ≤ 25%
Action: retain filter, tune slope_max per calibration rule if fire rate warrants, continue measuring.

Verdict B — Premise wrong:
Meets ANY of:
- Section 3B: median coint-failure delta_from_threshold > 0.015 across ≥ 4 failures (slopes were far below threshold — filter could not have caught these failures regardless of threshold)
- Section 3C: coint-failure rate among evaluated trades ≥ 30% with slope_exceeded ≥ 3 (filter was active but made no difference)
Action: reject the slope-at-entry approach. The premise — that coint failures are predictable from entry-time p-value slope — is not supported. Next priority: alternative coint stability mechanism (half-life trend, residual variance) OR escalate Item 12 (execution cost model). See Section 11.

Verdict C — Inconclusive / underpowered:
Applies when: evaluated_trade_count < 6 at the 20-trade mark, OR 5 ≤ evaluated_trade_count < 10 with slope_exceeded = 0 AND Section 3B has insufficient data to assess the premise.
Action: do not change slope_max. Extend collection window to N additional trades (specify count and rationale), OR investigate why evaluated_trade_count is low (buffer-fill rate problem requiring Patch 7.2).

Noise-floor caveat: the coint-failure rate thresholds (25%/30%) span a range narrower than small-sample variance. If the experiment rate falls between 25% and 30% with evaluated_trade_count < 10, assign Verdict C regardless — the point estimate is within noise for that sample size. Reserve Verdict A and B for results that are either clearly separated from the 36.8% baseline or where the 3B premise check provides corroborating evidence.

State the verdict: [A / B / C]

Evidence summary (required):
- evaluated_trade_count (real N): [N]
- coint_stability_slope_exceeded_count: [N]
- fire_rate: [pct]
- coint-failure rate among evaluated trades: [pct]
- calibration trigger status: [FIRED: slope_max → 0.030 / NOT FIRED]
- Section 3B median delta_from_threshold for coint-failures: [value]
- Verdict: [A / B / C]
- Rationale: [one paragraph, citing the evidence above]

---

Section 11 — Forward Plan

Based on the structural verdict and deferred items review, propose exactly one next research priority. Do not bundle multiple changes.

If Verdict A (filter works):
Apply calibration adjustment if fire rate warranted (Section 3A). Extend window or start new experiment group with adjusted slope_max. Define new success and null criteria based on observed patterns.

If Verdict B (premise wrong):
Select from:
- Option B1: Alternative coint stability mechanism — half-life trend (pairs with shortening half-life at entry) or residual variance trend (rising spread variance). Hypothesis, mechanism, parameters, and test criteria must be fully specified.
- Option B2: Escalate Item 12 (execution cost model) — per-pair or liquidity-tier cost estimates. This requires cost data collection first (add logging) before a full experiment. Specify the logging change and data collection window.
State the chosen option and explain why it ranks above the alternatives.

If Verdict C (inconclusive):
State minimum additional evaluated_trade_count needed and why. If evaluated_trade_count was low due to insufficient_history: investigate buffer-fill rate (Patch 7.2 candidate — specify the diagnosed root cause before proposing the patch). If evaluated_trade_count was low due to not_reached: upstream gate is filtering too aggressively — a different problem.

Next research priority template:

Hypothesis: [one sentence]
Mechanism: [how the proposed change affects entry/exit path — be specific]
Proposed change: [exact config parameter and value, or code change]
Success criteria: [specific measurable outcome over next 20 trades]
Null criteria: [outcome that definitively rules out the hypothesis]
Data requirement: [telemetry needed — if a new CSV column or logging point required, specify]
Action threshold: 20 trades before next structural review (or justify alternative)

Patch specification (if code change required):
- Patch number: [Patch 8 / Patch 7.2 / ...]
- Files to modify: [list]
- Parameters: [name and value]
- Tests required: [count and description]

Forbidden in this section:
- Bundling multiple changes into one priority
- Proposing changes without explicit success AND null criteria
- Selecting a priority that doesn't address the largest remaining problem
- Proposing notional changes without first resolving the coint stability question (unless Verdict B redirects to Item 12)

Operational items before next experiment phase:
- Any config changes that must be applied before resuming (with reason why pre-requisite vs. optional)
- Any telemetry additions identified as missing in this review
- Documentation updates: DECISION_LOG.md, CURRENT_STATE.md, memory files
- Apply calibration adjustment (slope_max change) if Section 3A calibration trigger fired

New experiment group name:
experiment_group: [exp_DESCRIPTIVE_NAME_v1] — encode the primary variable being tested, not the patch number

---

Section 12 — Audit Hygiene for This Review

Required throughout the review:
- Distinguish "concluded from this experiment" from "still hypothesis" for every claim
- Reference specific trade counts and PnL figures for every claim (not "most trades" or "generally")
- Mark any conclusions on sub-samples of 2–4 trades as "preliminary" regardless of direction
- Do not promote any hypothesis to HIGH confidence on fewer than 5 supporting trades
- Do not declare the experiment "successful" or "failed" without the explicit A/B/C verdict from Section 10
- Do not retroactively exclude trades from the denominator to improve a metric
- Do not treat trades_since_experiment_start as the experimental N — the N is evaluated_trade_count

Self-check before publishing (complete all before finalizing):

[ ] Data assembly: master trade table built, run_id added, no duplicate trade_ids
[ ] Columns verified: actual column names confirmed, discrepancies noted
[ ] Completeness: every trade assigned to complete or incomplete telemetry with reason
[ ] Gate-status inventory computed: evaluated_trade_count stated as the real N
[ ] Section 2: all metrics computed from actual data, not memory
[ ] Section 3A: fire_rate computed; calibration trigger status stated explicitly
[ ] Section 3B: 4D table aggregated; median delta_from_threshold for coint-failures computed; near-threshold vs far-below split stated
[ ] Section 3C: coint-failure rate stated for evaluated trades separately from all trades; comparison to 36.8% baseline made
[ ] Section 4: every experiment trade's exit_reason mapped to one category; "other" lists actual strings
[ ] Section 5A: MFE timing buckets computed or documented as unavailable; Item 10 disposition stated
[ ] Section 5B: meme-token anomaly count stated; escalation rule applied if n ≥ 3
[ ] Section 6: every shadow filter with ≥ 1 firing has REJECT / DEFER / INSUFFICIENT DATA disposition
[ ] Section 7: all residuals verified against reconciliation_checks.csv; cumulative negative unexplained computed
[ ] Section 9: confidence table fully populated; every change has justification with trade count
[ ] Section 10: verdict is A, B, or C — not a hedge; evidence summary present with all required fields
[ ] Section 11: exactly one next priority; success AND null criteria both stated; calibration adjustment applied if triggered
[ ] Section 8: every deferred item has disposition; no item left ambiguous
[ ] Section 13: experiment_group reset decision stated

---

Section 13 — Continuation Decision

The review concludes with one of three decisions. State the decision before writing any rationale.

Decision 1 — Continue with new research item:
Applicable when: Verdict A or B, deferred items review surfaced a clear next priority, sufficient data exists to act.
Actions:
  - Apply Patch 8 (or calibration adjustment) per Section 11 specification
  - Update experiment_group to the new name
  - Reset trades_since_experiment_start to 0
  - Update DECISION_LOG.md with Patch 8 entry (or calibration adjustment entry)
  - Update CURRENT_STATE.md with new experiment_group and reset counter
  - Update memory: project_experiment_state.md with new state

Decision 2 — Extend window (collect more data):
Applicable when: Verdict C (inconclusive/underpowered), OR Verdict A/B where a specific deferred item requires more trades to decide.
Actions:
  - No config changes
  - State the minimum additional evaluated_trade_count required and why
  - Document specifically what additional data is being collected and the decision criteria
  - Update CURRENT_STATE.md with "extending window" note and next review trigger

Decision 3 — Pause for rework:
Applicable when: Verdict B and the alternative mechanism requires design work before another experiment, OR Verdict C and evaluated_trade_count was low due to a diagnosed buffer/gate problem requiring a Patch 7.2.
Actions:
  - Bot paused, no new runs
  - Define rework scope: what must be changed, what must be understood, what condition constitutes "ready to resume"
  - Update CURRENT_STATE.md with pause status and resumption criteria

State the decision: [1 / 2 / 3]
State the new experiment_group (Decision 1), the extension rationale (Decision 2), or the rework scope (Decision 3).

---

Design Notes (Reference)

1. Verdict required, not optional. Section 10 forces a commitment to A, B, or C with quantitative evidence. Per-run audits exist to delay this commitment; this review exists to force it.

2. The real N is evaluated_trade_count. trades_since_experiment_start counts total closed trades; evaluated_trade_count counts trades where Patch 7 could have acted. Every filter-effectiveness claim must reference evaluated_trade_count. This distinction is the lesson the 4C/4D apparatus was built around — the review must honor it.

3. The premise check (3B) is the centerpiece. Section 3A (was the filter active?) and 3C (did the rate drop?) are secondary — useful context, not the verdict. The slope-vs-outcome data in the 4D table answers the question that determines whether the slope approach is worth pursuing at all. A filter that never fires says nothing about the premise. A filter that fires but failures cluster far below threshold says the premise is wrong. Only the 4D analysis can distinguish these.

4. Three early-resolution paths exist. (a) slope_exceeded = 0 after 6 evaluated trades → calibration trigger, loosen slope_max. (b) failure slopes cluster far below threshold through 5-6 failures → premise-wrong signal, can resolve before trade 20. (c) failures cluster near threshold → tunable, proceed. Only genuine ambiguity requires the full 20 trades. The template is designed to produce the verdict as soon as the signal is clear.

5. The calibration adjustment is pre-committed, not a judgment call. If fire_rate < 15%, slope_max adjusts to 0.030 regardless of other findings. The adjustment does not require a new structural review — it is applied as part of Section 11's forward plan if the trigger fires. Treating it as optional undermines the pre-commitment.

6. Deferred items get explicit resolution. Every item must be NEXT PRIORITY, DEFER, or REJECT. Items cannot drift across reviews without an explicit decision.

7. Data assembly precedes analysis. The Data Assembly Protocol must be completed before any section is started. Analysis from memory rather than the assembled dataset is the most common failure mode.

8. Counterfactuals must be labeled. Any estimate of what would have happened under a different configuration must be labeled "assumed" with explicit reasoning. The reader must be able to distinguish observed data from projected data.

9. The meme-token execution cost sub-pattern has two framings. Graveyard entries are the stopgap; the per-pair-tier cost model is the real fix. Section 5B and Item 12 must keep both framings alive so the structural review can choose, not collapse to one without evidence.

---

*Template version: exp_coint_stability_v1 structural review v1.0, created 2026-05-24.*
*Supersedes: prompt_for_structural_review_exp_guard050_ethfi_excluded_v1.md (that document is the historical record for exp_guard050 and is kept as-is).*
*Prior structural review completed: docs/audits/structural_review_exp_guard050_ethfi_excluded_v1.md, Verdict B.*
