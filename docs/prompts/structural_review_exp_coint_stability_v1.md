Structural Review — exp_coint_stability_v1: Sizing-Mismatch Discovery and Coint-Stability Filter Assessment

This review covers two levels of finding. It is not only a verdict on the Patch 7 cointegration stability slope filter. During the experiment, a project-level structural issue was discovered: the z-score and the executed dollar position measure different things, because OLS hedge ratio β is computed for the signal but equal dollar notional is used for sizing. This sizing-mismatch finding leads the review, because it recasts how every other finding — filter verdict, economic analysis, cost model, exit capture — must be interpreted. A review that leads with the slope-filter verdict would bury the more important finding.

Section 10 delivers two verdicts: first the sizing-mismatch verdict (project-level, not A/B/C), then the filter verdict (A/B/C, contextualized under the mismatch). Section 11 derives the next experiment from both. The original template structure is preserved where the bones are sound; the framing is changed where needed to reflect what the experiment actually found.

---

Trigger Conditions (Must Be Met Before Beginning)

- trades_since_experiment_start (Patch 7.1 calibration window) ≥ 20
- OR premise early-resolution criterion met: both observable coint-failures entered with strong entry-time coint metrics and failed post-entry — filter cannot distinguish them, premise negative
- OR sizing-mismatch finding code-confirmed in production execution: z-score β and position-sizing β structurally disconnected
- OR gate-inactivity trigger from 4C-TRIGGER (per-run template)
- No active operational incident
- Most recent per-run audit completed and filed
- Bot stopped or in a known stable state

If any condition is unmet, halt and complete prerequisites first. If an early-resolution trigger fired before trade 20, note the trigger name and trade count at the top of the review. The verdict must honor the pre-committed consequence of that trigger, not treat it as optional.

This review is called at T14 (10 window trades) on two simultaneous early-resolution triggers: premise early-resolution criterion met at T11, and sizing-mismatch code-confirmed at T14. The 20-trade threshold was not reached; state this at the top and note the triggers that authorized early review.

---

Experiment State Block (Required at Top of Review)

Report verbatim:

  experiment_group: exp_coint_stability_v1
  experiment_phase: Structural Review
  early_review_trigger: [state which triggers fired and at which trade]
  runs_since_experiment_start: [list all runs: 105, 106, 107, 108, 109, 111, 112, ...]
  trades_since_experiment_start: [count — note if < 20 and name the early-trigger]
  evaluated_trade_count: [count — gate_status = evaluated; this is the real experimental N]
  insufficient_history_trade_count: [count — gate reached, buffer too small]
  not_reached_trade_count: [count — upstream gate blocked before safety gate ran]
  coint_stability_slope_exceeded_count: [count — filter fires across all experiment evaluations]
  closed_trades_with_complete_telemetry: [count]
  closed_trades_with_incomplete_telemetry: [count, list trade IDs and reason]
  circuit_breaker_trips_this_experiment: [count]
  patches_active: Patch 4.1, Patch 5, Patch 6, Patch 7, Patch 7.1
  sizing_mismatch_code_confirmed: [YES — hedge_ratio has zero references in func_trade_management.py]
  review_date: [date]

The single most important state variable for the filter verdict: evaluated_trade_count. All filter-effectiveness conclusions in Section 10B rest on that number, not on trades_since_experiment_start.

---

Preamble — Project-Level Finding: Sizing-Mismatch

This section must be written before any data assembly begins. It is code-confirmed and requires no data to state.

Statement of the finding:

The z-score used to generate entry signals is computed using an OLS hedge ratio β: spread = log(P1) − β × log(P2). The production execution code (Execution/func_trade_management.py) sizes both legs at equal dollar notional — capital_long = capital_short = initial_capital_usdt — regardless of what β is. The hedge_ratio field has zero references in func_trade_management.py. The β value is computed, passed to the ML quality scorer (_hedge_ratio_quality in advanced_ml_runtime.py), and discarded for sizing purposes.

When β ≠ 1, the position does not track the spread the z-score is measuring. The position earns $200 × Δlog(P1) − $200 × Δlog(P2) — effectively β = 1 in dollar terms. The z-score measures Δlog(P1) − β × Δlog(P2). The two are identical only when β = 1. When β diverges from 1, a favorable z-move can correspond to an adverse dollar move, or near-zero dollar move, or no consistent mapping between signal and outcome.

Empirical signature in the experiment:

The $/σ cross-trade validation (T5–T14) shows the signature of beta-mismatch:

| Trade | Pair | Δz | position_PnL | implied_$/σ | Sizing verdict |
|---|---|---|---|---|---|
| T7 | BTC/HBAR | 4.39σ | −$0.007 | ≈ $0/σ | β probably ≪ 1 (HBAR tiny vs BTC) |
| T9 | LINEA/ZRO | 2.98σ | −$0.006 | ≈ $0/σ | β off 1 |
| T10 | FIL/ICP | 4.12σ | +$0.274 | +$0.067/σ | β probably ≈ 1 |
| T12 | SOL/BTC | 4.14σ | +$0.143 | +$0.035/σ | β probably ≈ 1 |
| T13 | BNB/COMP | 4.37σ | −$0.395 | −$0.090/σ | β >> 1 (COMP more volatile) |
| T14 | SOL/ALGO | 1.80σ | −$0.481 | −$0.267/σ | β confirmed by intra-trade path |

T14 confirms the mechanism intra-trade: z decreased from +2.279 to +0.269 (1.98σ favorable z-move) while position PnL went from −$0.003 to −$0.538, moving more adverse as z reverted. Dollar PnL anti-correlated with z-score direction during the trade.

Pairs where β ≈ 1 in practice (T10, T12) show positive $/σ — z and dollars move together. Pairs where β ≠ 1 (T7, T9, T13, T14) show near-zero or negative $/σ — z and dollars diverge or oppose.

Implication for prior findings:

Every economic conclusion drawn from this experiment's PnL is potentially contaminated by beta-mismatch. Section 3A quantifies the magnitude of the mismatch via counterfactual analysis. Until that analysis is complete, each finding in Sections 4–9 must be tagged as either:

- SURVIVES SIZING REFRAME — the finding holds regardless of beta-mismatch (e.g., coint-failure events are real; T10's thin-leg cost blowout is real)
- PENDING SIZING REVALIDATION — the finding may be an artifact of equal-notional sizing rather than a true economic constraint (e.g., "T7/T9 lost on costs" — but if β was wrong, there was no edge for costs to eat)

Tag every finding in Sections 4–9 with one of these labels before drawing conclusions.

What does NOT change:

- The coint-stability premise verdict is still meaningful even under sizing mismatch: T5 and T11 both had maximum-strength coint metrics at entry and failed post-entry. The filter premise is NEGATIVE regardless of what sizing was doing.
- The cost residual pattern (positive residuals on liquid pairs, negative on thin legs) is real and survives the reframe: reconciliation_checks.csv measures actual cash flow, not model predictions.
- The beta-mismatch finding does not mean the strategy is broken or wrong. It means the strategy has not been fairly tested. Equal-notional sizing has its own logic (symmetric per-leg dollar risk). The finding is not "sizing is wrong" — it is "the signal and the position are not aligned, so the experiment's outcomes cannot be interpreted as evidence for or against the mean-reversion hypothesis."

---

Data Sources

Aggregate across all experiment runs (105, 106, 107, 108, 109, 111, 112, ...):

- trade_closes.csv from each run — primary economic data
- entry_rejections.csv from each run — primary Patch 7 gate data
- reconciliation_checks.csv from each run — cost and PnL confirmation
- exit_decision_trace.csv from each run
- position_snapshots.csv from each run
- liquidity_checks.csv from each run — needed for Item 12 residual-vs-liquidity analysis
- bot logs from each run (for pair_activation_timestamp per trade)

Note: hedge_ratio is NOT present in any of the above CSV outputs. It is computed in evaluate_cointegration() and passed to the ML quality model but not logged to any CSV field. β values for existing trades require retroactive OLS computation from historical kline data, or access via the events database. Do not rely on CSV data to supply β values — they are not there.

Prior baseline datasets (fixed references — do not re-derive):
- Raw baseline: runs 90, 93, 94 — 9 trades, 1 win, 56% coint-failure rate, cumPnL −$2.157
- exp_guard050_ethfi_excluded_v1: 20 trades (19 known PnL), 26.3% win rate, 36.8% coint-failure rate, cumPnL −$2.592

Important baseline caveat: both prior baselines also used equal-notional sizing. The comparison is between two equally-sizing-contaminated datasets. This is informative — it shows whether Patch 7 changed anything relative to no-Patch-7 — but it does not compare against a correctly-sized baseline, which does not yet exist.

Data Assembly Protocol (complete before any section analysis):

Step 1 — Locate report directories.
For each experiment run, confirm the Reports/ directory exists under Reports/v1/run_NNN_*/. List every CSV file present. If a run has no Reports/ directory, mark that run's trades as "no telemetry" — they count toward the trade total but are excluded from mechanism analysis.

Step 2 — Assemble the master trade table.
Concatenate trade_closes.csv across all experiment runs. Add a run_id column. Verify: no duplicate trade entries, every row has a non-null pnl_usdt field, timestamps parse as valid values.

Step 3 — Compute position_pnl per trade.
position_pnl = trade_pnl from reconciliation_checks.csv (not pnl_usdt from trade_closes, which is equity_change). For each trade, confirm: position_pnl + fees + slippage − unexplained ≈ pnl_usdt (equity_change). Flag any trade where this reconciliation does not hold.

Step 4 — Compute implied $/σ per trade.
For each evaluated trade with Δz ≥ 0.5σ (exclude near-zero-move coint-failures): implied_$/σ = position_pnl / |entry_z − exit_z|. Report sign and magnitude. Δz < 0.5σ trades are not informative for $/σ — mark as "uninformative (near-zero Δz)."

Step 5 — Link exit_decision_trace.
For each trade, confirm rows exist in exit_decision_trace.csv. If a trade has zero trace rows, mark as "no trace."

Step 6 — Link liquidity_checks.csv.
For each trade, find the pre-entry liquidity check row. Record liquidity_long_usdt and liquidity_short_usdt at entry. This is the x-axis for the residual-vs-liquidity plot in Section 3A.

Step 7 — Assemble the slope-vs-outcome tally.
Copy the running slope-vs-outcome tally from the final per-run audit's Section 4D entries. Verify each row against its source per-run audit. Confirm: every row has gate_status = evaluated AND coint_stability_check_blocked_count = 0.

Step 8 — Record available columns.
Before analysis, list the exact column names present in each CSV type. The files are authoritative — if a column name in this document differs from what is in the file, use the file's column name and note the discrepancy.

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

State explicitly: "The filter-effectiveness verdict in Section 10B rests on [evaluated_trade_count] evaluated trades, not on [trades_since_experiment_start] total trades."

If evaluated_trade_count < 10: "Sample is underpowered. Filter-effectiveness verdict confidence is reduced. All filter-effectiveness findings are preliminary."
If evaluated_trade_count < 6: "Sample is insufficient for filter verdict. Verdict C (inconclusive/underpowered) is required regardless of observed patterns."

The sizing-mismatch verdict in Section 10A is not subject to sample-size constraints — it is code-confirmed and does not depend on trade count.

Definition of complete telemetry — a trade meets this standard if ALL of:
1. Appears in trade_closes.csv with a non-null pnl_usdt field
2. entry_rejections.csv has rows for this pair in this run (gate status derivable)
3. reconciliation_checks.csv has exactly 1 row for this trade with a valid trade_pnl field
4. Trade was NOT affected by a mid-run restart
5. Trade was NOT a manual close where the bot did not execute the exit
6. For $/σ analysis: reconciliation basis = pre_close_equity_delta (excludes T8 which used basis=position_pnl with fees=0)

Known incomplete-telemetry trades to carry forward:
- T8 SOL/AVAX (run_116): reconciliation basis=position_pnl, fees=0 — data quality FAIL due to retry_count=3 timing gap. Excluded from economic analysis; gate/slope analysis valid.
- [Add any additional from per-run audits]

---

Section 2 — Outcome Comparison: Experiment vs Prior Experiments

This section reports raw outcome distributions. Do not interpret here.

Important framing note before this section: the prior baselines also used equal-notional sizing. The comparison measures whether Patch 7 affected outcomes within the same sizing regime, not whether the strategy works correctly.

Per-trade outcome table (compute from pnl_usdt in trade_closes.csv = equity change per trade):

| Metric | Raw baseline (9 trades) | exp_guard050 (19 trades) | exp_coint_stability (N trades) |
|---|---|---|---|
| Win rate | 1/9 = 11% | 5/19 = 26.3% | [wins]/[total] |
| Avg PnL/trade | −$0.239 | −$0.137 | [sum / count] |
| Avg win | +$0.133 | [value] | [sum wins / wins] |
| Avg loss | −$0.270 | [value] | [sum losses / losses] |
| Largest win | +$0.133 | [value] | [max] |
| Largest loss | −$0.549 | [value] | [min] |
| Cumulative PnL | −$2.157 | −$2.592 | [sum] |

MFE distribution — bin max_favorable_pnl_usdt from trade_closes.csv:
  Negative (never profitable), $0–$0.05, $0.05–$0.10, $0.10–$0.17, $0.17–$0.23, > $0.23
  Report count and pct per bin. Note how many trades had negative MFE (never profitable throughout hold). Note how many never reached $0.17 (the profit-lock floor). "Negative MFE" is a distinct category from previous reviews — add it explicitly.

MAE distribution — bin max_adverse_pnl_usdt using equivalent bins.

Hold duration distribution — bin hold_minutes:
  < 10min, 10–30min, 30min–2h, 2–8h, > 8h

Entry z distribution — bin entry_z:
  < 1.5, 1.5–2.0, 2.0–2.5, 2.5–3.0, > 3.0

Per-symbol outcomes:
For each symbol appearing in ≥ 2 trades, report: appearances, win rate, avg PnL, coint-failure count. Note whether it also appeared in exp_guard050.

---

Section 3 — Sizing-Mismatch Quantification and Filter Effectiveness

This section has two subsections. 3A quantifies the magnitude of the sizing mismatch via $/σ analysis and counterfactual study. 3B assesses filter effectiveness subordinated to that context. Both must be populated. Do not skip to 3B.

3A — Beta-Mismatch Quantification

3A-i: $/σ Cross-Trade Validation

Source: position_pnl from reconciliation_checks.csv and entry_z, exit_z from trade_closes.csv.

Populate the $/σ table (built from Data Assembly Steps 3–4):

| Trade | Pair | Exit reason | Δz (σ) | position_PnL | implied_$/σ | Sizing signal |
|---|---|---|---|---|---|---|
| T5 | FIL/FLOKI | coint_lost | [Δz] | [value] | [value] | [near-zero Δz: uninformative] |
| T6 | DOGE/SUI | coint_lost | [Δz] | [value] | [value] | |
| T7 | BTC/HBAR | normal | [Δz] | [value] | [value] | |
| T8 | SOL/AVAX | normal | [Δz] | EXCLUDED | — | data quality |
| T9 | LINEA/ZRO | normal | [Δz] | [value] | [value] | |
| T10 | FIL/ICP | normal | [Δz] | [value] | [value] | |
| T11 | CRV/IOTA | coint_timeout | [Δz] | [value] | [value] | [path dependency: z re-expanded mid-hold] |
| T12 | SOL/BTC | normal (regime) | [Δz] | [value] | [value] | |
| T13 | BNB/COMP | normal (regime) | [Δz] | [value] | [value] | |
| T14 | SOL/ALGO | coint_lost | [Δz] | [value] | [value] | [sign inversion confirmed intra-trade] |

For the five normal-exit trades with Δz ≥ 1.5σ (excluding T8 data quality, T5/T6 near-zero Δz), separately report:
- Count with implied_$/σ > 0: [N]
- Count with implied_$/σ ≈ 0 (< $0.005/σ): [N]
- Count with implied_$/σ < 0: [N]
- Range: [min] to [max]

The sizing-mismatch verdict (Section 10A) is determined here. If implied_$/σ sign varies across normal-exit trades, the position is not tracking the spread, confirming mismatch.

3A-ii: Residual-vs-Liquidity Analysis (Item 12)

Source: reconciliation_checks.csv (unexplained field) and liquidity_checks.csv (liquidity_long_usdt, liquidity_short_usdt, entry_precheck rows).

For each evaluated trade with a valid reconciliation:
- x-axis: min(liquidity_long_usdt, liquidity_short_usdt) at entry (thin-leg liquidity)
- y-axis: unexplained residual from reconciliation_checks.csv

Plot description (or tabular equivalent):

| Trade | Thin-leg liquidity (USDT) | Unexplained residual | Pattern |
|---|---|---|---|
| [each trade] | [value] | [value] | [positive / negative / near-zero] |

Interpretation rule:
- If residuals scatter randomly around zero regardless of thin-leg liquidity: cost model bias is random, ±$0.06 per-trade error averages out across trades, statistical inference viable. State: "cost bias is imprecise but unbiased."
- If negative residuals cluster on low-liquidity trades (< 1,000 USDT thin leg) and positive residuals cluster on high-liquidity trades: cost bias is liquidity-correlated. State: "cost model is systematically biased, must be fixed before per-trade economic conclusions are reliable." This finding elevates Item 12 to NEXT PRIORITY.
- Existing pattern from per-run audits (7 positive residuals on liquid pairs, negative residuals on thin/meme legs) is suggestive of bias. The plot determines whether this is confirmed or coincidence.

3A-iii: Counterfactual Analysis — Beta-Adjusted Sizing

Source: core/chart_audit/counterfactual_exit_study.py. This module computes equal_notional_pnl_usdt (actual) and hedge_ratio_sized_pnl_usdt (what PnL would have been with β-adjusted position sizing) for each trade, given intra-trade candle data and the entry marker's entry_hedge_ratio metadata.

Note: hedge_ratio is not in any existing CSV output. Running this analysis requires either:
(a) Retroactively computing OLS β from historical kline data at each trade's entry timestamp and passing it to the counterfactual study, or
(b) Adding hedge_ratio to entry event logging and collecting it from the next run.

If counterfactual analysis is available at review time:

For each trade, report:
- equal_notional_pnl_usdt (actual position_pnl)
- hedge_ratio_sized_pnl_usdt (β-adjusted counterfactual)
- pnl_delta_usdt = β-adjusted minus equal-notional
- entry_hedge_ratio used

Aggregate:
- Cumulative equal_notional PnL (T5-T14): [sum]
- Cumulative β-sized PnL counterfactual: [sum]
- Net delta: [value]
- Trades where β-sizing would have produced materially different sign (win→loss or loss→win): [count]

Interpretation:
- If cumulative PnL delta > $1.00 in β-sizing's favor: sizing mismatch is large-magnitude, β-aware sizing is a high-priority experiment. Justify the next experiment on quantitative grounds.
- If cumulative PnL delta < $0.30: sizing mismatch is structural but small in magnitude on this sample. β-aware sizing is correct but not the dominant lever; prioritize based on which other findings (cost model, exit design) show larger expected improvement.

If counterfactual analysis is NOT available at review time:
State explicitly: "Counterfactual analysis was not completed. The sizing-mismatch finding is code-confirmed but its quantitative impact on outcomes is unverified. The next experiment (β-aware sizing) is justified on structural-correctness grounds, not on observed PnL improvement. β data collection must be a Day 1 requirement of the next experiment."

Do not propose β-aware sizing as "likely to improve outcomes by X%" without the counterfactual analysis. State it as "structurally necessary for a fair test."

3B — Filter Effectiveness

This subsection is the former primary research question, contextualized under the sizing-mismatch finding.

All filter-effectiveness conclusions must acknowledge the contamination caveat: the filter was evaluated on trades where the position did not necessarily track the spread. A coint-failure verdict of "premise wrong" is correct, but its interpretation is "the premise is not supported on the data available, and the data may not have been a clean test of the premise."

3B-i: Gate Activity

Source: entry_rejections.csv. Count rows where component_scores contains coint_stability_check_blocked_count ≥ 1.

- coint_stability_slope_exceeded_count (cumulative): [N]
- evaluated_count across all evaluations: [N]
- fire_rate = slope_exceeded_count / evaluated_count: [pct]

Pre-committed calibration rule — apply here, do not defer:
- fire_rate < 15%: filter passes nearly everything. Calibration adjustment: slope_max 0.020 → 0.030. State explicitly whether this trigger applies.
- fire_rate > 60%: filter blocks too aggressively. Calibration adjustment: slope_max 0.020 → 0.012. State explicitly whether this trigger applies.
- 15% ≤ fire_rate ≤ 60%: filter is active at a plausible rate. Proceed to 3B-ii.

If slope_exceeded_count = 0:
State: "The filter passed every evaluated entry. Fire rate = 0%. This satisfies the pre-committed calibration trigger (< 15%). The slope_max parameter must be loosened to 0.030 before any future window using this filter. The premise cannot be tested via blocks — it can only be assessed via the 3B-ii passed-then-failed analysis."
Do not frame this as "inconclusive" — it has a defined consequence.

3B-ii: Premise Check

Source: slope-vs-outcome tally (Data Assembly Step 7). Only gate-evaluated trades with blocked_count = 0.

| Exit Category | Count | Mean slope | Median slope | Mean Δ-from-threshold | Median Δ-from-threshold |
|---|---|---|---|---|---|
| coint-failure | [N] | [value] | [value] | [value] | [value] |
| normal | [N] | [value] | [value] | [value] | [value] |

Delta convention: slope_max − slope_at_entry. Large positive delta = slope far below threshold; small or negative = near or above threshold.

Near-threshold failures (delta < 0.005): [count] of [total coint-failures]
Far-below-threshold failures (delta > 0.015): [count] of [total coint-failures]

Premise verdict under contamination caveat:
- If most failures were far below threshold (delta > 0.015): slopes were far from catchable regardless of threshold. Premise not supported. Under contaminated sizing, this could mean: (a) coint-failures were truly unpredictable from slope, OR (b) the dollar losses from coint-failures were partly artifacts of sizing. Both lead to the same conclusion for this filter: slope-at-entry is not the lever to pull.
- If most failures were near-threshold: premise may hold, threshold tuning could help. Even so, addressing sizing first is required before a clean premise test.

Do not conclude from this sub-section. State the pattern and defer conclusion to Section 10B.

3B-iii: Coint-Failure Rate on Evaluated Trades

| Population | Coint-failure rate |
|---|---|
| Raw baseline (9 trades) | 56% |
| exp_guard050 (19 trades) | 36.8% |
| exp_coint_stability, ALL trades | [coint-exits / trades_since_experiment_start] |
| exp_coint_stability, evaluated trades only | [coint-exits among evaluated / evaluated_trade_count] |

The evaluated-only rate is the primary comparison. All-trades rate is context only.

Success threshold: ≤ 25% among evaluated trades (pre-committed target from Patch 7 specification).
Null threshold: ≥ 30% among evaluated trades (pre-committed null criterion).

State the rate and which threshold applies. Do not interpret — that is Section 10B.

---

Section 4 — Cointegration Fragility Analysis

SURVIVES/PENDING SIZING REVALIDATION tag required on each finding.

Exit reason distribution (count + pct of total trades):

| Exit reason | Raw baseline (9) | exp_guard050 (19) | exp_coint_stability (N) |
|---|---|---|---|
| cointegration_lost | 5 (56%) | [count] ([pct]) | [count] ([pct]) |
| cointegration_watch_timeout | [count] ([pct]) | [count] ([pct]) | [count] ([pct]) |
| trailing_stop / profit_lock | [count] ([pct]) | [count] ([pct]) | [count] ([pct]) |
| regime_break | [count] ([pct]) | [count] ([pct]) | [count] ([pct]) |
| other | [count] ([pct]) | [count] ([pct]) | [count] ([pct]) |

For any "other" exit_reason, list the actual string values — do not aggregate unknown exits.

Per-trade coint timing (for each coint-failure exit):
- time_to_failure = exit_ts minus entry_ts (minutes)
- Min, median, max time-to-failure

Split by gate status:

| Gate status | Coint-failure count | Total count | Coint-failure rate |
|---|---|---|---|
| evaluated | [N] | [N] | [pct] |
| insufficient_history | [N] | [N] | [pct] |
| not_reached | [N] | [N] | [pct] |

Coint-failure finding: SURVIVES SIZING REFRAME. The cointegration events (lost, timeout) are real and occurred regardless of what the dollar position was doing. However, the dollar loss from each coint-failure may partly reflect sizing mismatch — a position that was already losing due to β ≠ 1 before cointegration broke. State this distinction: "coint-failure events are real; coint-failure dollar losses may include sizing-mismatch component."

Confidence update:
- Prior state: HIGH confidence that cointegration fragility is the dominant loss driver
- Post-experiment update: [CONFIRM HIGH / LOWER TO MEDIUM / raise]
- Justification: note that some of the dollar loss attributed to coint-failures may be sizing-driven; the failure events themselves are real but the loss magnitude is uncertain under sizing mismatch

---

Section 5 — MFE Timing and Execution Cost Analysis

SURVIVES/PENDING SIZING REVALIDATION tag required on each finding.

5A — MFE Timing Pattern

MFE timing bucket computation (from exit_decision_trace.csv):

| Bucket | All trades (count, pct) | Winners | Losers |
|---|---|---|---|
| early_hold (0–33%) | [count] ([pct]) | [count] | [count] |
| mid_hold (34–66%) | [count] ([pct]) | [count] | [count] |
| late_hold (67–100%) | [count] ([pct]) | [count] | [count] |
| negative MFE (never profitable) | [count] ([pct]) | 0 | [count] |

"Negative MFE" is a distinct bucket not present in prior templates — add it here. T13 (−$0.076) and T14 (−$0.003) belong in this bucket. A trade that is never profitable cannot be evaluated for MFE timing; its failure is pre-entry, not post-entry.

Tag on MFE timing finding: PENDING SIZING REVALIDATION. Under correct sizing (β-adjusted), the dollar MFE for some trades may be different. T7 and T9, which appeared to have low in-zone MFE at equal notional, might have different MFEs under β-sizing if their dollar sensitivity to z-movement was systematically suppressed by equal notional.

exp_guard050 finding validation: winner late_hold rate ≥ 70% AND loser early_hold rate ≥ 70% = pattern confirmed.
Negative-MFE trades should be excluded from this bucket computation — they were never profitable and confound the timing analysis.

5B — Execution Cost Pattern (Item 12)

Tag: SURVIVES SIZING REFRAME. Actual costs from reconciliation_checks.csv represent real cash flows and are not distorted by the equal-notional sizing of positions. The cost residual pattern (positive on liquid pairs, negative on thin/meme legs) is independent of whether the position tracked the spread correctly.

Known occurrences going into this review:
- HMSTR run_102: unexplained −$0.226 (graveyarded)
- FLOKI run_111 (T5): unexplained −$0.093

Experiment occurrences to add: [from reconciliation_checks.csv for all runs]

Positive residual pattern (also SURVIVES SIZING REFRAME):
7 positive residual occurrences identified on liquid pairs during the experiment: T7 (+$0.040), T9 (+$0.073), T11 (+$0.040), T12 (+$0.023), T13 (+$0.027), T14 (+$0.017), and [confirm ETH/ETC and DOGE/BNB from prior experiment]. The pattern is consistent with actual costs being below the $0.14 flat model for liquid pairs. This is liquidity-correlated — the 3A-ii residual-vs-liquidity analysis converts this suggestive pattern into a confirmed or refuted finding.

Standard anomaly tracking:
- Negative residuals > $0.05: [list all, with run and trade]
- Positive residuals > $0.05: [list all, with run and trade]
- Cumulative negative unexplained (all experiment runs): [sum]
- Materiality threshold: |cumulative negative| > $0.30 → flag for Item 12 dedicated investigation

Meme-token escalation rule (pre-committed): third occurrence → propose category exclusion at this review.

---

Section 6 — Shadow Block Findings

Source: entry_rejections.csv. For each shadow filter with ≥ 1 firing:
- Total firings: [count]
- Entries subsequently allowed that became wins: [count]
- Entries subsequently allowed that became losses: [count]
- Win rate on shadow-blocked evaluations vs overall experiment win rate: [compare]

Tag: PENDING SIZING REVALIDATION if the shadow filter is economically motivated (e.g., $/σ-based). Gate-based shadow filters (coint health, liquidity) SURVIVE SIZING REFRAME.

Recommendation criteria:
- REJECT: winners blocked / total firings within ±15 pp of overall win rate. No discriminating power.
- DEFER: winners blocked / total firings < (overall win rate − 15 pp). Filter disproportionately fires on losers.
- DEFER (insufficient data): total firings < 5.

State the recommendation explicitly. Do not use hedged language.

---

Section 7 — Reconciliation Anomaly Patterns

Tag: SURVIVES SIZING REFRAME. Reconciliation measures cash flows, not model predictions.

7A — Negative residual pattern (thin-leg cost overrun):

Known occurrences to carry forward (verify against reconciliation_checks.csv):
- Run 99 FIL/LINEA: unexplained −$0.121
- Run 100 BNB/LDO: unexplained −$0.068
- T5 FIL/FLOKI: unexplained −$0.093 (meme-token; FLOKI graveyarded)
- T10 FIL/ICP: unexplained −$0.255 (thin FIL leg, 575 USDT at entry — extends negative pattern to non-meme pairs)
- T8 SOL/AVAX: FAIL (data quality — excluded from pattern analysis)
- [Add all experiment occurrences with unexplained < −$0.020]

7B — Positive residual pattern (liquid pairs):

Known occurrences from prior experiment: ETH/ETC +$0.145, DOGE/BNB +$0.078.
Experiment additions (7 total identified; verify all against reconciliation_checks.csv):
T7 (+$0.040), T9 (+$0.073), T11 (+$0.040), T12 (+$0.023), T13 (+$0.027), T14 (+$0.017).

Report the confirmed count and cumulative value. If the 3A-ii residual-vs-liquidity analysis confirms liquidity correlation, promote Item 12 to NEXT PRIORITY.

---

Section 8 — Deferred Research Items Review

Every item must receive one of: NEXT PRIORITY, DEFER (carry forward), or REJECT (close). Items cannot remain ambiguous. Include SURVIVES/PENDING tag where applicable.

Item 1 — Forward-looking coint stability filter (this experiment's primary item):
Resolved here. Disposition determined by Section 10B verdict.
- If Verdict A: NEXT PRIORITY to tune slope_max per calibration rule.
- If Verdict B: REJECT slope approach; advance Item 16 (beta-sizing) and Item 12 (liquidity cost model).
- If Verdict C: DEFER with explicit minimum additional trade count — but note that early-resolution via sizing-mismatch finding changes the calculus: collecting more trades under broken sizing does not help decide the premise question cleanly.

Item 2 — Regime-flip exit timing:
Background: run_98 ETH/AVAX held post-regime-commit. Did any experiment run show similar delay?
Tag: SURVIVES SIZING REFRAME (exit timing is independent of position sizing).
Disposition: [NEXT PRIORITY / DEFER / REJECT]

Item 3 — max_break_risk recalibration:
Background: median rejected break_risk = 0.150 at cap.
Tag: SURVIVES SIZING REFRAME.
Disposition: [NEXT PRIORITY / DEFER / REJECT]

Item 4 — Notional adjustment:
Background: ratios unchanged with notional.
Tag: PENDING SIZING REVALIDATION. Under β-adjusted sizing, the effective notional per trade changes. "Notional adjustment" as previously conceived assumed equal-notional as the baseline. This item is superseded by Item 16 (β-sizing) and should be DEFERRED until after Item 16 is evaluated.
Disposition: DEFER (Item 16 supersedes)

Item 5 — Alert/kill-switch (Patch 6):
Tag: SURVIVES SIZING REFRAME.
Disposition: [NEXT PRIORITY / DEFER / REJECT]

Item 6 — Exit z-zone widening:
Tag: PENDING SIZING REVALIDATION. Zone widening affects only trades that reach the exit zone; under correct sizing, the dollar value of reaching the zone may differ, changing the calibration calculus.
Disposition: [NEXT PRIORITY / DEFER / REJECT]

Item 7 — Profit-lock band mechanism (Patch 5):
Prior disposition: confirmed operational, inert in contribution, Verdict B in exp_guard050.
Tag: PENDING SIZING REVALIDATION. The effective floor ($0.12) was calibrated against equal-notional PnL distributions. Under β-sizing, in-zone PnL magnitudes will differ for β ≠ 1 pairs.
Disposition: RETAIN Patch 5 configuration, do not re-investigate NOW. Flag for re-evaluation after one β-sized experiment window provides new MFE distribution data. State: "Floor calibration is pending β-sizing validation — Patch 5 is operational but may need recalibration after Item 16 is deployed."

Item 8 — Adverse-exit fill quality:
Tag: SURVIVES SIZING REFRAME.
Disposition from Section 7A analysis: [NEXT PRIORITY / DEFER / REJECT]

Item 9 — Positive reconciliation residuals:
Tag: SURVIVES SIZING REFRAME. Positive residuals on liquid pairs are real cash flow patterns.
Disposition from Section 7B analysis: If n ≥ 7 positive residuals with liquidity correlation confirmed by 3A-ii → NEXT PRIORITY (escalated into Item 12). Else DEFER.

Item 10 — MFE timing:
Tag: PENDING SIZING REVALIDATION. Under β-sizing, MFE magnitudes differ for β ≠ 1 pairs.
Disposition from Section 5A: [NEXT PRIORITY if confirmed at ≥ 70% in both early/late buckets, pending sizing re-evaluation / REJECT if pattern breaks down at this sample]

Item 11 — DOGE/HMSTR execution cost anomaly:
Prior disposition: RESOLVED. HMSTR graveyarded. No further action.
Disposition: CLOSED.

Item 12 — Execution cost model (liquidity-residual analysis):
Tag: SURVIVES SIZING REFRAME (cost cash flows are independent of positioning).
If 3A-ii residual-vs-liquidity plot shows clear liquidity correlation (negative residuals on thin-leg trades, positive on liquid): NEXT PRIORITY — implement liquidity-tier cost model or strengthen thin-leg entry gate.
If random scatter: DEFER — statistical inference viable with flat model, accumulate more trades.
State the disposition based on Section 3A-ii outcome, not on prior hypothesis.

Item 13 — Post-close fee snapshot timing gap:
Background: T8 (run_116) retry_count=3 caused post-close fee snapshot to miss fills; basis=position_pnl, fees=0. Possible fix: delay snapshot by 2–5s when retry_count > 0.
Tag: SURVIVES SIZING REFRAME.
Disposition: [NEXT PRIORITY / DEFER / REJECT]

Item 14 — Full_tp exit-capture mechanism:
Background: full_tp captured zero exits in the Patch 7.1 window. T12 win came from regime_break at z=−2.066 overshoot. MFE systematically occurs outside |z| < 0.35 zone or below effective floor.
Tag: PENDING SIZING REVALIDATION. Under β-adjusted sizing, dollar MFE for some pairs will change. The zone calibration and floor calibration were set for equal-notional PnL distributions. The T7 anomaly (41 blocks at in-zone MFE $0.127 > $0.12 effective floor) is a specific mechanical question that SURVIVES SIZING REFRAME — investigate root cause regardless of sizing.
- T7 full_tp blocking root cause: IN MFE $0.127 > effective floor $0.12 → guard should have passed. 41 blocks without a pass is unexplained. Verify that floor at time of blocking matches $0.12 and not $0.24 (the base parameter). Source: exit_decision_trace.csv for T7 (effective_full_tp_floor_usdt column).
Disposition: DEFER exit-zone redesign until after β-sizing experiment. INVESTIGATE T7 anomaly independently — this is a mechanical question.

Item 15 — coint_stability_check_evaluated_count semantics AND level-check hypothesis:
Prior hypothesis: evaluated_count was a buffer depth count; T11 (slope ≈ 0, coint-failure) entered with p ≈ 1.0 (cointegration dead, slope-blind). A level check would have caught T11.
Verification at run_120 audit: evaluated_count is a binary flag per-call, NOT buffer depth. T11 cointegration score 24.998/25 (p ≈ 0 = MAXIMUM strength) — opposite of p ≈ 1.0. Level-check hypothesis was REFUTED by its own originating case.
Structural consequence: T11 joins T5 as a coint-failure that entered with strong entry-time coint metrics and failed post-entry. Premise-negative verdict firm on N=2 clean data points.
Disposition: CLOSED — refuted. Do not carry forward. The "improve the coint filter" direction is closed.

Item 16 — Beta-aware position sizing (NEW):
Background: Code-confirmed in this experiment. hedge_ratio (OLS β) is computed in evaluate_cointegration() but has zero references in func_trade_management.py. Position sizing is always equal dollar notional regardless of β.
Evidence: $/σ sign varies across normal-exit trades (positive for T10/T12 where β ≈ 1, near-zero for T7/T9, negative for T13 where β >> 1). T14 confirms intra-trade: z moved favorably while position PnL moved adversely.
Infrastructure already exists: config schema has hedge_ratio_sizing_enabled, hedge_sizing_mode (equal_notional / gross_normalized_beta), min_hedge_ratio, max_hedge_ratio, target_gross_pair_notional_usdt. Counterfactual exit study (core/chart_audit/counterfactual_exit_study.py) computes hedge_ratio_sized_pnl_usdt for analysis. β-adjusted sizing is designed but not wired to Execution/ code.
Pre-requirement: hedge_ratio must be added to logged fields (entry_gate_component_scores or trade_open event) before the next experiment can verify β at entry time from CSV data.
Disposition: NEXT PRIORITY — implement beta-aware sizing before resuming production trades. See Section 11 for specification.

---

Section 9 — Confidence Calibration Final Update

Confidence level definitions:
- VERIFIED: Mechanically confirmed in production
- HIGH: ≥ 0.80 probability, ≥ 5 supporting trades, mechanism understood
- MEDIUM: 0.50–0.79 probability, 3–5 trades, mechanism plausible
- LOW: < 0.50 probability, few or conflicting observations
- UNTRACKED: Not yet measured

| Hypothesis | Pre-experiment | End-of-experiment | Justification |
|---|---|---|---|
| confidence_coint_stability_slope_predictive | LOW | [update] | Evidence from 3B-ii: near-threshold vs far-below-threshold coint-failure count |
| confidence_coint_filter_reduces_failure_rate | UNTRACKED | [value] | Evidence from 3B-iii: experiment rate vs 36.8% baseline |
| confidence_coint_fragility_as_dominant_problem | HIGH | [update] | Note: coint-failure events real; dollar losses may include sizing component |
| confidence_beta_mismatch_structural | UNTRACKED | VERIFIED | Code-confirmed: zero references to hedge_ratio in func_trade_management.py |
| confidence_beta_mismatch_magnitude_material | UNTRACKED | [value] | From 3A-iii counterfactual analysis; if not completed, state UNTRACKED |
| confidence_dsnl_liquidity_correlated | UNTRACKED | [value] | From 3A-ii residual-vs-liquidity analysis |
| confidence_meme_token_execution_cost_anomaly | MEDIUM (n=2) | [update] | From 5B: additional occurrences, cumulative unexplained |
| confidence_execution_cost_model_accuracy | MEDIUM | [update] | From 5B and 7A: known-biased on thin/meme legs; directionality confirmed |
| confidence_mfe_timing_predictive | MEDIUM (exp_guard050) | [update] | From 5A: note pending sizing revalidation if confirmed |
| confidence_profit_lock_band_mechanism | MEDIUM (Patch 5 inert) | [no change expected] | No new evidence — note pending β-sizing calibration |
| confidence_trend_regime_mr_block_active | VERIFIED | VERIFIED | Patch 4.1 confirmed in production |
| confidence_emergency_flatten_safety | PATCH_6_APPLIED | [update] | Was outer backoff exercised in this experiment? yes/no |
| confidence_break_risk_threshold_correctness | MEDIUM | [update] | Evidence from entry_rejections analysis |

Do not change a confidence level without citing specific evidence. "No new evidence, no change" is valid — state it explicitly.

---

Section 10 — Structural Verdicts

This section delivers two verdicts in order. Verdict 10A leads. Deliver each verdict before writing its narrative.

Section 10A — Sizing-Mismatch Verdict (Project Level)

This verdict does not follow the A/B/C format. It is binary: CONFIRMED or NOT CONFIRMED.

Evidence required:
- hedge_ratio reference count in func_trade_management.py: [must be zero for CONFIRMED]
- $/σ sign distribution across normal-exit trades (from 3A-i): [positive only / mixed / negative present]
- T14 intra-trade sign inversion: [OBSERVED / NOT OBSERVED]
- T13 full-traversal with negative position PnL: [OBSERVED / NOT OBSERVED]

Verdict 10A: [CONFIRMED / NOT CONFIRMED]

If CONFIRMED:
State: "The z-score and executed dollar position measure different things. OLS hedge ratio β is used for signal computation but not for position sizing. The experiment's PnL history reflects beta-mismatched positions, not the mean-reversion strategy as designed. This is a project-level structural finding. The next experiment must use β-aware sizing. Sections 10B, 11, and 13 are written under this constraint."

If NOT CONFIRMED (unexpected — would require hedge_ratio to appear in sizing code or $/σ signs to be uniformly positive):
State what evidence contradicted the hypothesis and proceed with standard filter-effectiveness verdict.

Section 10B — Coint-Stability Filter Verdict (Experiment Level)

Context: this verdict is rendered on data where positions did not fully track the signal due to sizing mismatch. The verdict is still meaningful — coint-filter premise is assessable from the gate events — but it is not a clean test of whether the filter improves dollar outcomes. State the contamination caveat explicitly in the verdict.

Choose the verdict before writing the narrative. The contamination caveat does not change the verdict category, only its interpretation.

Verdict selection guide:

Verdict B — Premise wrong (expected, given per-run audit accumulation):
Applies when ANY of:
- Section 3B-ii: median coint-failure Δ-from-threshold > 0.015 across ≥ 4 failures (slopes were far below threshold — filter could not have caught these failures regardless of threshold)
- Section 3B-iii: coint-failure rate among evaluated trades ≥ 30% with slope_exceeded ≥ 3

Contaminated-premise caveat for Verdict B: "The premise is not supported on the available data. The experiment also does not constitute a fully clean test of the premise, because positions were sized at equal notional rather than β-adjusted. However, both observable coint-failures (T5 slope far below threshold, T11 slope ≈ 0 with p ≈ 0 = maximum coint strength) entered with exemplary entry-time coint metrics and failed post-entry. The premise is not supported and the two most informative data points both argue against it. Coint-stability filtering is deprioritized, not simply deferred."

Verdict A — Filter works:
Meets ALL of: slope_exceeded ≥ 3, 3B-ii median Δ < 0.010, 3B-iii failure rate ≤ 25%.
Under sizing mismatch: if Verdict A, state — "Filter verdict A holds on evaluated-trade coint-failure rate, but the economic benefit of A cannot be measured cleanly because positions did not track the spread. Verdict A means 'continue measuring this filter' only after β-sizing is implemented, to assess whether the improvement in coint-failure rate translates to economic improvement."

Verdict C — Inconclusive / underpowered:
Applies when evaluated_trade_count < 6 at review time, or insufficient data to assess premise.
Under sizing mismatch + early-resolution triggers: Verdict C is superseded if the premise was resolved by early-resolution criteria (both observable coint-failures passed all entry-time metrics). State: "While the data is insufficient for a statistically robust filter-effectiveness verdict, the qualitative evidence from T5 and T11 (both entered with maximum coint strength, both failed post-entry) is consistent with the early-resolution criterion and supports Verdict B." Do not artificially preserve Verdict C if the early-resolution criterion has fired.

Evidence summary (required):
- evaluated_trade_count (real N): [N]
- coint_stability_slope_exceeded_count: [N]
- fire_rate: [pct]
- coint-failure rate among evaluated trades: [pct]
- calibration trigger status: [FIRED: slope_max → 0.030 / NOT FIRED]
- Section 3B-ii median Δ-from-threshold for coint-failures: [value]
- Verdict 10B: [A / B / C]
- Rationale: [one paragraph, citing evidence; include contamination caveat if applicable]

---

Section 11 — Forward Plan

Based on the two verdicts in Section 10, propose the next research priority. Under Verdict 10A (CONFIRMED sizing mismatch), the forward plan is determined: β-aware sizing must be deployed before any other experiment can produce interpretable economic data. This is not optional regardless of Verdict 10B.

Primary forward plan: Beta-Aware Position Sizing

Hypothesis: Position sizing proportional to OLS β (gross-normalized-beta mode) will align dollar PnL with z-score movements, making strategy economics directly measurable and eliminating the signal/position mismatch identified in Verdict 10A.

Mechanism: At entry, compute OLS β from the same lookback used for z-score computation. Size legs as: leg1_notional = target_gross / (1 + β), leg2_notional = target_gross × β / (1 + β). Total gross notional is preserved; each leg's allocation reflects the statistical hedge ratio. When β = 1, this reduces to equal-notional (no change). When β > 1, the second leg receives proportionally more capital.

Infrastructure status:
- Config schema: ALREADY HAS hedge_ratio_sizing_enabled, hedge_sizing_mode, min_hedge_ratio, max_hedge_ratio, target_gross_pair_notional_usdt
- Counterfactual study: ALREADY HAS equal_notional_pnl_usdt and hedge_ratio_sized_pnl_usdt computation
- Entry markers: ALREADY SUPPORT entry_hedge_ratio metadata field
- Execution code: NOT YET IMPLEMENTED — hedge_ratio has zero references in func_trade_management.py

Required implementation:
1. In func_trade_management.py: read hedge_ratio from metrics at the sizing step; compute β-adjusted leg sizes; enforce min_hedge_ratio/max_hedge_ratio bounds (reject entry if β out of bounds per config); log actual leg sizes and entry_hedge_ratio to the trade_open event.
2. Add hedge_ratio to entry_gate_component_scores in the gate payload — this makes β available in entry_rejections.csv for future verification.
3. Update target_gross_pair_notional_usdt config to reflect the new gross-notional model (or retain $200/leg as maximum, adjusting the formula accordingly — decide which before implementation).
4. Tests: update sizing-related tests, add 2 tests for β-adjusted sizing logic (β > 1 case, β < 1 case), add 1 test for β out-of-bounds rejection.

Pre-commitment requirements before starting the next experiment:
1. Counterfactual analysis from 3A-iii must be completed. If β-adjusted sizing produces < $0.30 cumulative difference on T5-T14, document that and proceed anyway on structural-correctness grounds, but do not claim expected economic improvement.
2. hedge_ratio must appear in CSV output (entry_gate_component_scores or trade_open event) before the first trade of the next experiment. The first run's β values must be verifiable from CSV data.
3. β distribution from first N runs must be summarized before drawing any economic conclusions. Record: median β, range, count of trades with β in [0.8, 1.2] vs outside. This determines whether the fix is primarily addressing near-1-β pairs (expected small impact) or high-β pairs (expected large impact).

Success criteria (next 20 trades under β-aware sizing):
- $/σ signs are uniformly positive across normal-exit trades (z and dollars move in the same direction)
- Cumulative PnL at least $0.50 better than exp_coint_stability at the same trade count (not "profitable" — just improved against a sizing-contaminated baseline)
- hedge_ratio logged and verified for ≥ 90% of evaluated trades (gate quality)
- Beta distribution documented: median β and range established for the pair universe

Null criteria:
- $/σ signs still mixed after 10 evaluated trades under β-sizing — rejects the hypothesis that sizing was the root cause (something else is causing z/dollar divergence)
- Cumulative PnL worse than or equal to equal-notional baseline at same trade count — β-sizing makes no material difference

Alternative options if β-sized sizing not yet deployable (Decision 3):

Option A (gate β ≠ 1): Gate entries where β falls outside [min_hedge_ratio, max_hedge_ratio]. Simpler implementation (no sizing change, just a new gate condition). Advantage: retains equal-notional for β ≈ 1 pairs, excludes only the problematic β ≠ 1 pairs. Disadvantage: reduces pair universe and may not fix the structural issue for pairs near the boundary. Specify: min_hedge_ratio, max_hedge_ratio, and the gate rejection message.

Option B (z-score recomputed with β = 1): Use spread = log(P1) − log(P2) instead of OLS-β-weighted spread. This makes the z-score match the equal-notional position by definition. Advantage: no sizing change required. Disadvantage: loses the cointegration model's statistical optimality; may degrade pair selection. Investigate whether the existing coint_flag and p_value would remain meaningful with β = 1.

Choose the primary option before this section is complete. State the rationale for the choice over alternatives.

Operational items before next experiment phase:
- hedge_ratio added to entry_gate_component_scores logging (required: first run)
- Patch specification (see Item 16 in Section 8) complete with test list
- DECISION_LOG.md updated with β-sizing patch entry
- CURRENT_STATE.md updated with new experiment_group and reset counter
- memory: project_experiment_state.md updated

If Verdict 10B = B (premise wrong) AND 10A = CONFIRMED (sizing mismatch):
Item 12 (liquidity cost model) is the next deferred item after β-sizing is deployed. If 3A-ii confirmed liquidity-correlated residuals, Item 12 should be the second experiment in the new group — run β-sizing first, then layer Item 12 on top once $/σ is verifiable.

New experiment group name: exp_beta_aware_sizing_v1 (encode the primary variable; do not use patch numbers)

---

Section 12 — Audit Hygiene for This Review

Required throughout the review:
- Distinguish "concluded from this experiment" from "still hypothesis" for every claim
- Reference specific trade counts and PnL figures for every claim
- Mark any conclusions on sub-samples of 2–4 trades as "preliminary" regardless of direction
- Do not promote any hypothesis to HIGH confidence on fewer than 5 supporting trades
- Do not declare the experiment "successful" or "failed" without the Section 10A and 10B verdicts explicitly stated
- Do not retroactively exclude trades from the denominator to improve a metric
- Do not treat trades_since_experiment_start as the experimental N — the N is evaluated_trade_count for filter-effectiveness claims; total trade count for economic claims

Specific addendum for this review — the coherent-reframe temptation:

The beta-mismatch finding is structurally confirmed in code but its quantitative impact on PnL outcomes is not yet measured. The finding is coherent: it explains the $/σ sign pattern, it explains why T7/T9 earned near-zero despite favorable z-moves, it explains why T13/T14 lost money despite z-reversion. Coherent reframes are the most seductive form of error in this project's history — Patch 5 (floor miscalibration as dominant problem), the level-check (T11's slope-≈-0 explained by p ≈ 1.0), the $/σ breakeven gate (quantitatively precise formula built on an unstable metric). Each had an appealing coherent story and required a verification step to confirm or refute.

The beta-mismatch reframe must be held to the same standard:

Do NOT attribute specific prior losses to beta-mismatch without the counterfactual analysis showing what those trades would have produced under correct sizing. "T7 lost near-zero because β suppressed dollar sensitivity" is a hypothesis, not a conclusion. "T9 lost because the position didn't track the spread" is a hypothesis. The pattern is consistent with the hypothesis; the hypothesis is not confirmed until counterfactual analysis is run.

Do NOT conclude that "the strategy would have been profitable under β-sizing" — that requires the counterfactual study to show positive PnL, which may or may not be the case. The strategy may have had positive $/σ under correct sizing, or it may still have had negative expected value. The reframe converts "the strategy failed" into "the strategy wasn't tested" — a meaningful difference, but it does not guarantee positive results under the correct test.

Do NOT use the sizing-mismatch finding to dismiss all prior conclusions. The coint-failure events are real. The cost overruns on thin legs are real. The reconciliation patterns are real. The β-mismatch finding adds a necessary caveat to economic conclusions; it does not erase the non-economic findings.

The reframe is correct and important. Apply the same verification standard that caught the Patch 5 miscalibration, the count-semantics error, the level-check refutation, and the $/σ unreliability. Verify before enshrining.

Self-check before publishing:

[ ] Preamble: sizing-mismatch finding stated with code evidence; contamination caveat applied to all economic sections
[ ] Data assembly complete: master trade table, position_pnl computed, $/σ table built, liquidity_checks linked
[ ] Section 3A-i: $/σ table fully populated; sign distribution stated
[ ] Section 3A-ii: residual-vs-liquidity analysis completed or explicitly deferred with reason
[ ] Section 3A-iii: counterfactual analysis completed or explicitly deferred with reason; "not completed" framing used if deferred
[ ] Section 3B: filter effectiveness assessed under contamination caveat; calibration trigger status stated
[ ] Sections 4–7: SURVIVES/PENDING tag applied to every finding
[ ] Section 8: Items 1-16 all have explicit disposition; Items 15 CLOSED, Item 16 NEXT PRIORITY
[ ] Section 9: new confidence variables added (beta_mismatch_structural, beta_mismatch_magnitude_material, dsnl_liquidity_correlated); all changes cite evidence
[ ] Section 10A: verdict 10A stated first; evidence summary present
[ ] Section 10B: verdict A/B/C stated; contamination caveat in rationale
[ ] Section 11: exactly one primary forward plan; β data logging requirement stated; success AND null criteria both stated; alternative options assessed
[ ] Section 13: decision stated before rationale; experiment_group reset stated

---

Section 13 — Continuation Decision

The review concludes with one of three decisions. State the decision before writing any rationale.

Decision 1 — Continue with beta-aware sizing experiment:
Applicable when: Verdict 10A CONFIRMED + Verdict 10B B or A + Section 11 forward plan fully specified + counterfactual analysis completed (or accepted as deferred with explicit statement).
Actions:
  - Implement β-sizing patch per Section 11 specification (Item 16)
  - Add hedge_ratio to entry_gate_component_scores logging
  - Update experiment_group to exp_beta_aware_sizing_v1
  - Reset trades_since_experiment_start to 0
  - Update DECISION_LOG.md with β-sizing patch entry
  - Update CURRENT_STATE.md with new experiment_group and reset counter
  - Update memory: project_experiment_state.md with new state

Decision 2 — Extend window (collect more data):
Applicable when: Verdict 10B = C (inconclusive/underpowered) and the early-resolution criteria are genuinely unresolved — meaning additional evaluated trades would materially change the filter-effectiveness verdict.
Important: extending the window under equal-notional sizing when Verdict 10A is CONFIRMED produces more contaminated data. Decision 2 is not appropriate if Verdict 10A fired — more equal-notional trades do not help resolve either the β-mismatch magnitude or the filter premise more clearly.

Decision 3 — Pause for rework:
Applicable when: Verdict 10A CONFIRMED and β-sizing implementation requires design work not captured in Section 11 specification — e.g., the counterfactual analysis produced unexpected results requiring a rethink of the sizing mode, or min/max β bounds require calibration from data not yet available.
Actions:
  - Bot paused, no new runs under equal-notional sizing
  - Define rework scope: what must be designed, what must be understood
  - Update CURRENT_STATE.md with pause status and resumption criteria (specific conditions, not "when ready")

State the decision: [1 / 2 / 3]
State the new experiment_group (Decision 1), the extension rationale (Decision 2), or the rework scope (Decision 3).

Under Verdict 10A CONFIRMED: Decision 3 (Pause for Rework) is the default if the β-sizing implementation is not ready. Do not run new trades under broken sizing while the rework is in progress.

---

Design Notes (Reference)

1. Two verdicts, not one. This review produces a project-level verdict (10A: sizing mismatch) and an experiment-level verdict (10B: filter A/B/C). Prior reviews had one verdict. This is not a deviation from the review structure — it's an accurate representation of what the experiment found.

2. The sizing-mismatch finding does not require a trade count. It is code-confirmed and does not have a sample size. It leads the review not because it is more important than the quantitative analysis but because it is the lens through which all quantitative findings must be read.

3. The filter verdict (10B) is still meaningful. Even under contaminated sizing, the observation that both observable coint-failures entered with strong coint metrics and failed post-entry is informative: the premise is negative regardless of what sizing was doing. The sizing mismatch makes the dollar-outcome analysis unreliable; it does not make the gate-event analysis unreliable.

4. The coherent-reframe standard applies to this review. The beta-mismatch reframe is the most appealing explanation the project has produced. That makes it the most important hypothesis to verify before committing resources to the next experiment. Section 12's addendum applies this standard explicitly.

5. The calibration adjustment is pre-committed, not a judgment call. If fire_rate < 15% (as expected given 0 or very few blocks), slope_max adjusts to 0.030 per the pre-committed rule from Patch 7 specification. This is recorded as part of Section 11's forward plan even though β-sizing is the primary next experiment. The slope_max adjustment is applied for any future use of this filter — the calibration rule doesn't expire because the primary experiment direction changed.

6. The residual-vs-liquidity analysis (3A-ii) converts a pattern into a decision. The pattern (positive residuals on liquid pairs, negative on thin legs) has been observed across 7+ instances. Section 3A-ii determines whether it is confirmed as liquidity-correlated (elevating Item 12 to NEXT PRIORITY after β-sizing) or dismissed as coincidence. Do not carry the pattern forward indefinitely without converting it to a confirmed or refuted finding at this review.

7. Data assembly precedes analysis. The protocol must be completed before any section is started. Analysis from memory is the most common failure mode.

8. Counterfactuals must be labeled. Any estimate of what would have happened under β-sizing must be labeled as a counterfactual with its assumptions explicit. The reader must be able to distinguish observed data from projected data.

9. Deferred items get explicit resolution. Every item must be NEXT PRIORITY, DEFER, or REJECT. Items cannot drift across reviews.

---

*Template version: exp_coint_stability_v1 structural review v2.0, revised 2026-05-28.*
*Revision rationale: sizing-mismatch finding (beta-mismatch, code-confirmed) identified during experiment, requiring restructured review framing. Prior template version 1.0 (2026-05-24) is superseded. The structural bones of v1.0 are retained; the primary finding section (Section 3), verdict (Section 10), forward plan (Section 11), and audit hygiene addendum (Section 12) are substantially revised.*
*Supersedes: prompt_for_structural_review_exp_guard050_ethfi_excluded_v1.md (kept as historical record for that experiment).*
*Prior structural review completed: docs/audits/structural_review_exp_guard050_ethfi_excluded_v1.md, Verdict B.*
