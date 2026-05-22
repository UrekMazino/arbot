20-Trade Structural Review — Patch 5 Experiment Outcome Assessment

This is the first structural review of the experiment. It is fundamentally different from the per-run telemetry audits. Per-run audits forbid drawing conclusions; this review exists to draw them.
The review evaluates whether Patch 5 (guard multiplier 0.75 → 0.50 + ETHFI exclusion) produced the effects it was designed to produce, identifies the next research priority from the deferred items list, and decides whether the experiment continues, pivots, or concludes.

---

Trigger Conditions (Must Be Met Before Beginning)

- trades_since_experiment_start ≥ 20
- No active operational incident
- Most recent per-run audit has been completed and filed
- Bot is stopped or in a known stable state during review preparation

If any condition is unmet, halt and complete prerequisites first.

---

Experiment State Block (Required at Top of Review)
Report verbatim:

  experiment_group: exp_guard050_ethfi_excluded_v1
  experiment_phase: Structural Review
  runs_since_experiment_start: [count]
  trades_since_experiment_start: [count, must be ≥ 20]
  closed_trades_with_complete_telemetry: [count]
  closed_trades_with_incomplete_telemetry: [count, list trade IDs and reason]
  circuit_breaker_trips_this_experiment: [count]
  patches_active: Patch 4.1, Patch 5, Patch 6
  review_date: [date]
  prior_baseline_runs: 90, 93, 94

---

Data Sources

Aggregate across all experiment runs (95, 98, 99, 100, 101, …):

- trade_closes.csv from each run
- exit_decision_trace.csv from each run
- exit_opportunity_summary.csv from each run
- entry_rejects.csv from each run
- reconciliation_checks.csv from each run
- bot logs from each run
- pair_supply_control.json and pair_strategy_state.json where available

Baseline dataset (for comparison):

- runs 90, 93, 94 (pre-experiment, total 9 trades)

Data Assembly Protocol (complete before any analysis):

Step 1 — Locate report directories.
For each experiment run, confirm the Reports/ directory exists under Logs/v1/run_NNN_*/. List every CSV file present. If a run has no Reports/ directory at all, mark that entire run's trades as "no telemetry" — they count toward the trade total but are excluded from mechanism analysis.

Step 2 — Assemble the master trade table.
Concatenate trade_closes.csv across all experiment runs. Add a run_id column to each row during concatenation. Verify:
- No duplicate trade_id values exist across runs
- Every row has a non-null realized_pnl field
- entry_time and exit_time fields parse as valid timestamps

Step 3 — Link exit_decision_trace.
For each trade_id in the master table, confirm rows exist in exit_decision_trace.csv for the corresponding run. The trace is per-evaluation (many rows per trade). Group by trade_id to aggregate per-trade trace metrics. If a trade_id has zero trace rows, mark that trade as "no trace."

Step 4 — Link reconciliation_checks.
For each trade_id, confirm a row exists in reconciliation_checks.csv for the corresponding run. If absent, mark that trade as "no reconciliation."

Step 5 — Record available columns.
Before analysis, list the exact column names present in each CSV type (trade_closes, exit_decision_trace, reconciliation_checks, entry_rejects). The column names in the actual files are authoritative — if a column name in this document differs from what is in the file, use the file's column name and note the discrepancy.

Known field naming patterns (verify against actual files at review time):
- trade_closes.csv: trade_id, pair, ticker_1, ticker_2, direction, entry_time, exit_time, hold_duration_seconds, realized_pnl, mfe, mae, entry_z, exit_z, exit_reason
- exit_decision_trace.csv: trade_id, eval_time, elapsed_seconds, current_pnl, mfe_at_eval, mfe_timing_pct (or compute as elapsed_seconds/hold_duration_seconds), z_score, full_tp_guard_passed, profit_lock_activated, shadow_* fields, threshold_crossing_* fields
- reconciliation_checks.csv: trade_id, declared_pnl, reconciled_pnl, residual (reconciled_pnl minus declared_pnl)
- entry_rejects.csv: timestamp, pair, rejection_reason, shadow_* fields

If a field listed above is absent from the actual file, note it, use the closest available equivalent, and document the substitution.

---

Section 1 — Dataset Inventory

Before any analysis, establish what data exists and its quality.

Trade inventory:

- Total experiment trades: [count]
- Per-run breakdown: run 95 (3), run 98 (2), run 99 (3), run 100 (6), run 101 (N), ...
- Win/loss totals across the full experiment
- Trades with complete telemetry: [count]
- Trades with incomplete telemetry: [count, with specific reasons]

Definition of "complete telemetry" — a trade meets this standard if ALL of the following are true:
1. It appears in trade_closes.csv with a non-null realized_pnl
2. exit_decision_trace.csv has ≥ 1 row for that trade_id
3. reconciliation_checks.csv has exactly 1 row for that trade_id
4. The trade was NOT affected by a mid-run restart that reset the profit/loss baseline (a restart creates a gap in the trace — note if present)
5. The trade was NOT a manual close where the bot did not execute the exit (e.g., run 100 LDO/LINK)

Known incomplete-telemetry trades to carry forward from prior audits:
- run 98 ETH/AVAX: restart-baseline drift (trace unreliable)
- run 100 LDO/LINK: manual close on OKX, bot did not execute exit
- [Add any from run 101+]

Telemetry completeness check by file:

For each experiment run, confirm:
- trade_closes.csv: exists, non-empty, all rows have non-null realized_pnl
- exit_decision_trace.csv: exists, non-empty, every complete-telemetry trade_id has ≥ 1 row
- reconciliation_checks.csv: exists, every complete-telemetry trade_id has exactly 1 row
- entry_rejects.csv: exists (may be empty if no rejections that run)

Note any trades excluded from specific analyses (mechanism analysis, timing analysis, reconciliation analysis) and the reason for each exclusion. Exclusions are per-analysis, not blanket — a trade excluded from mechanism analysis may still contribute to outcome comparison.

Baseline dataset (fixed reference — do not re-derive):

- 9 trades from runs 90, 93, 94
- 1 win (KSM/SOL run 93), 8 losses
- Cumulative PnL: -$2.157
- Avg loss: -$0.270, avg win: +$0.133
- Coint-failure exits: 5/9 = 56%

---

Section 2 — Outcome Comparison: Experiment vs Baseline

This section reports raw outcome distributions. Do not interpret in this section.

Per-trade outcome table. Compute for both datasets (experiment, baseline) using trade_closes.csv realized_pnl field:

| Metric            | Baseline (9 trades) | Experiment (N trades) |
|-------------------|---------------------|-----------------------|
| Win rate          | 1/9 = 11%           | [wins]/[total]        |
| Avg PnL/trade     | -$0.239             | [sum / count]         |
| Avg win           | +$0.133             | [sum wins / wins]     |
| Avg loss          | -$0.270             | [sum losses / losses] |
| Largest win       | +$0.133             | [max]                 |
| Largest loss      | -$0.549             | [min]                 |
| Cumulative PnL    | -$2.157             | [sum]                 |
| Profit factor     | 0.05                | [gross wins / |gross losses|] |

Profit factor formula: sum(realized_pnl for wins) / abs(sum(realized_pnl for losses)). A value < 1.0 means losses exceed wins in gross dollar terms. Baseline value of 0.05 reflects the heavily loss-weighted baseline.

Distributional comparisons (experiment only; baseline lacks sufficient granularity for these):

MFE distribution — bin the mfe field from trade_closes.csv:
  < $0.05, $0.05–$0.10, $0.10–$0.14, $0.14–$0.18, $0.18–$0.23, $0.23–$0.30, > $0.30
  Report count and pct per bin. Note how many trades never reached $0.17 (the profit-lock floor).

MAE distribution — bin the mae field using the same bin widths as MFE.

Hold duration distribution — bin hold_duration_seconds converted to hours:
  < 1h, 1–2h, 2–4h, 4–8h, > 8h

Entry z distribution — bin entry_z from trade_closes.csv:
  < 1.5, 1.5–2.0, 2.0–2.5, 2.5–3.0, > 3.0

Exit z distribution — bin exit_z the same way. Include the "how far below entry z did the pair return" field if available.

Per-symbol outcomes:

For each symbol that appeared in ≥ 2 trades (as either leg), report:
- Appearances (as ticker_1 + ticker_2 combined)
- Win rate, avg PnL, avg MFE, avg MAE
- Coint-failure exit count
- If the symbol also appears in baseline: note baseline vs experiment avg PnL

---

Section 3 — Patch 5 Mechanism Effectiveness

This is the primary research question. Patch 5 made two changes: guard multiplier 0.75 → 0.50, and ETHFI exclusion. Each is evaluated separately.

3A. Guard mechanism analysis (full_tp_guard_passed):

Source: exit_decision_trace.csv, column full_tp_guard_passed (boolean or 0/1).
A "TP-zone evaluation" is any row in the trace where the pair is in the TP zone. The guard pass is a row where full_tp_guard_passed = True/1.

For each complete-telemetry trade:
- Count total rows in exit_decision_trace where the trade is in the TP zone
- Count rows where full_tp_guard_passed = True
- If zero TP-zone evaluations for the entire trade: note "never entered TP zone" — this trade does not contribute to guard analysis

Aggregate:
- Total TP-zone evaluations across all complete-telemetry trades: [count]
- Total guard passes: [count]
- Guard pass rate: guard_passes / tp_zone_evaluations

If guard pass rate < 2% across ≥ 10 trades: the full_tp_guard_passed mechanism does not fire in production regardless of the multiplier. State this explicitly — it means the multiplier parameter (0.50 vs 0.75) is irrelevant to guard pass rate. The profit-lock band accessibility analysis (3B) still applies independently.

If full_tp_guard_passed column is absent from the trace file: note the absence, mark 3A as "data unavailable," and rely entirely on 3B for the Patch 5 verdict.

3B. Profit-lock band accessibility analysis:

Threshold derivation (verify against active config at review time):
- TP target (configured full exit PnL): estimated $0.34 based on prior audit references
- Profit-lock activation floor under Patch 5 (multiplier 0.50): $0.34 × 0.50 = $0.170
- Profit-lock activation floor under prior config (multiplier 0.75): $0.34 × 0.75 = $0.255
- The document has used $0.230 as the prior-config floor — verify which is correct against STATBOT_FULL_TP_GUARD_MULTIPLIER history. If the prior value was 0.75 and TP target is $0.34, the prior floor was $0.255 not $0.230. Use whichever value the config history supports, and restate both floors explicitly at review time.
- Patch-5-accessible band: between the old floor and $0.170. Trades activating in this band would NOT have activated profit-lock under prior config.

How to identify profit-lock activation from telemetry:
- Source: exit_decision_trace.csv column profit_lock_activated (True/1 on the evaluation where lock fires)
- Alternative: look for a sudden shift in exit logic (e.g., trailing_stop_active = True appearing for the first time) at a floating PnL near $0.170
- If profit_lock_activated column is absent: use exit_reason from trade_closes.csv — profit_lock or trailing_stop exits are proxy indicators

For each WINNING trade in the experiment:
- Was exit_reason profit_lock, trailing_stop, or similar lock-activated exit? (yes/no)
- If yes: at what floating_pnl value did profit_lock_activated first become True in the trace?
- Did that activation occur in the Patch-5-accessible band (between $0.170 and the old floor)?
- If yes: classify this trade as "Patch-5-enabled win"
- If activation occurred above the old floor: this win would have occurred without Patch 5 — classify as "Patch-5-neutral win"

For each LOSING trade in the experiment:
- Did MFE (from trade_closes.csv) reach $0.170 at any point? (compare mfe field directly)
- If mfe ≥ $0.170: look in the trace for profit_lock_activated = True rows. Did profit-lock activate?
  - If yes, profit-lock activated but trailing stop fired at a loss: note the trailing-stop exit price
  - If no, profit-lock never activated despite mfe ≥ $0.170: investigate why (guard condition, timing)
- If mfe < $0.170: profit-lock was never reachable; Patch 5 irrelevant to this trade

Patch-5-enabled win count: [count] of [total wins]
Patch-5-neutral win count (would have won without Patch 5): [count] of [total wins]

3C. Net Patch 5 impact:

Estimated PnL contribution from Patch-5-enabled wins:
- Sum of realized_pnl for Patch-5-enabled wins: [+$X]
- Counterfactual estimate for these trades without Patch 5:
  Counterfactual method: for each Patch-5-enabled win, look at the exit_decision_trace after the profit-lock activation point. Identify what happened to the pair post-activation (coint continued, deteriorated, etc.). If cointegration later failed (detectable in the trace via exit_reason or coint flags), the counterfactual exit would have been a coint-failure loss — estimate the counterfactual PnL as the median coint-failure exit PnL from other similar trades. If the pair would likely have exited normally, estimate the counterfactual as $0.00 (no profit). Label every counterfactual estimate explicitly as "assumed" with the reasoning shown.
- Net Patch 5 benefit (enabled-win PnL minus counterfactual PnL): [delta]

Estimated PnL cost from Patch 5 changes:
Identify any losing trades where profit_lock_activated = True and the trailing stop fired at a PnL below $0.00 (i.e., the profit-lock caught the trade on the way down, but the trailing stop floor was below breakeven). Under prior config (higher multiplier), profit-lock would not have activated, and the trade might have exited via a different mechanism. This is the potential cost: profit-lock activated at $0.170, trailing stop followed the price down, trade closed at a loss that a non-locked trade might have avoided. Estimate magnitude: (actual exit PnL) vs. (estimated exit PnL without profit-lock — use median non-lock exit for similar trades).

Net Patch 5 effect on experiment PnL: [explicit arithmetic: enabled-win contribution minus cost estimate]

3D. ETHFI exclusion impact:

- Confirm ETHFI-USDT-SWAP appears zero times across all experiment runs' trade_closes.csv files
- Confirm ETHFI-USDT-SWAP appears in graveyard_tickers.json with ttl_days: null throughout the experiment period
- Universe diversity: count distinct symbols across all experiment trades; list top 10 symbols by appearance count
- Did pair selection find replacement symbols consistently? Look for any run where the pair supply scheduler returned < 5 valid pairs (check pair_supply_control.json or logs)
- ETHFI baseline performance (fixed reference): 2 trades in runs 90–94, both losses, avg PnL = -$0.533
- Estimated PnL avoided: assuming ETHFI would have appeared in [N] trades at baseline avg PnL, avoidance = [N] × $0.533. Note this is a projection, not a realized figure.

---

Section 4 — Cointegration Fragility Analysis

This was the largest-magnitude problem identified in baseline ($1.811 in losses from coint-decay exits). Evaluate whether the experiment changed it.

Exit reason classification:
Source field: exit_reason in trade_closes.csv. Map to these categories. Verify the exact string values in the file match the patterns below — they may have different capitalization or underscores:
- cointegration_lost: exact string "cointegration_lost" or close variant — pair failed coint test during hold
- cointegration_watch_timeout: "cointegration_watch_timeout" or similar — pair was on watch and timer expired
- health exits: any exit_reason containing "health" or matching health-check exit codes
- normal / trailing_stop: "trailing_stop," "profit_lock," "normal_exit," "target_reached"
- regime_break: "regime_break," "regime_flip," "trend_block," or similar
- other / unknown: any exit_reason not matching the above categories — list them explicitly

Exit reason distribution across experiment (count + pct of total trades):

| Exit reason              | Baseline (9 trades) | Experiment (N trades) |
|--------------------------|---------------------|-----------------------|
| cointegration_lost       | 5 (56%)             | [count] ([pct])       |
| cointegration_watch_timeout | [count] ([pct])  | [count] ([pct])       |
| health exits             | [count] ([pct])     | [count] ([pct])       |
| trailing_stop / profit_lock | [count] ([pct]) | [count] ([pct])       |
| regime_break             | [count] ([pct])     | [count] ([pct])       |
| other                    | [count] ([pct])     | [count] ([pct])       |

Coint-failure rate:
- Baseline: 5/9 = 56%
- Experiment: [coint_lost + coint_watch_timeout] / [total experiment trades]
- Delta from baseline: [experiment rate minus 56%]; if > ±10 percentage points, treat as material change

Per-trade coint timing (for each coint-failure exit):
- time_to_failure = exit_time minus entry_time (in hours)
- Report: min, median, max time-to-failure across all coint-failure exits
- Baseline comparison: median time-to-failure was [value from prior audits — locate in run 90/93/94 reports]
- If experiment median time-to-failure is materially shorter than baseline: pairs are failing faster (deteriorating entry quality or different pair selection)
- If materially longer: pairs are surviving longer before failing (entry quality may be improving)

Confidence update:
- Prior state entering experiment: HIGH confidence that cointegration fragility is the dominant loss driver
- Post-experiment update: [CONFIRM HIGH / LOWER TO MEDIUM / RAISE — choose one]
- Justification: state the coint-failure rate, total losses attributable to coint exits in dollar terms, and whether this finding is consistent across runs or concentrated in specific runs

---

Section 5 — MFE Timing Pattern Analysis

The locked MFE timing measurement was the primary diagnostic this experiment was designed to produce.

MFE timing bucket computation:
Source: exit_decision_trace.csv. For each complete-telemetry trade, find the row where mfe_at_eval is at its maximum. Compute:
  mfe_timing_pct = elapsed_seconds_at_max_mfe / hold_duration_seconds × 100

If mfe_timing_pct is a pre-computed column in exit_opportunity_summary.csv, use that directly. If computing manually, hold_duration_seconds comes from trade_closes.csv; elapsed_seconds_at_max_mfe comes from the trace row with the highest mfe_at_eval value.

Bucket classification:
- early_hold: mfe_timing_pct 0–33%
- mid_hold: mfe_timing_pct 34–66%
- late_hold: mfe_timing_pct 67–100%

MFE timing bucket distribution (complete-telemetry trades only):

| Bucket        | All trades (count, pct) | Winners only | Losers only |
|---------------|------------------------|--------------|-------------|
| early_hold    | [count] ([pct])        | [count]      | [count]     |
| mid_hold      | [count] ([pct])        | [count]      | [count]     |
| late_hold     | [count] ([pct])        | [count]      | [count]     |

Pattern test — run 100 observation to validate or refute:
- Run 100 showed 2/2 winners in late_hold, 3/3 losers in early_hold
- With ≥ 20 trades, test whether this pattern holds:
  - Winner late_hold rate: [winners in late_hold] / [total winners]
  - Loser early_hold rate: [losers in early_hold] / [total losers]
  - If both rates are ≥ 70%: pattern is consistent — treat as a real finding
  - If either rate is < 50%: pattern did not replicate — run 100 was likely noise

TP-zone PnL pattern:
Definition: "TP-zone PnL" is the max floating PnL reached while z_score ≤ 0.35 (or the configured TP zone threshold — verify the z threshold in config at review time). Source: exit_decision_trace rows where z_score ≤ [threshold]; max(current_pnl) among those rows.
- Per-trade: compute max_pnl_in_tp_zone for each complete-telemetry trade
- Report: count of trades with positive max_pnl_in_tp_zone vs. negative
- Run 94 finding: uniformly negative TP-zone PnL across 9 baseline trades
- Has this changed? Specifically: any experiment trade with positive TP-zone PnL?

Threshold crossing patterns:
Source: exit_decision_trace or a threshold_crossings_* column if available. The six thresholds are $0.12, $0.14, $0.17, $0.18, $0.23, $0.24 (verify these against the profit-lock config at review time — they are the levels at which exit logic transitions).
For each complete-telemetry trade, count distinct thresholds crossed (i.e., current_pnl peaked above that value at least once).

| Thresholds crossed | Winners (count) | Losers (count) |
|--------------------|-----------------|----------------|
| 0 of 6             | [count]         | [count]        |
| 1–2 of 6           | [count]         | [count]        |
| 3–4 of 6           | [count]         | [count]        |
| 5–6 of 6           | [count]         | [count]        |

Run 100 finding to validate: winners crossed all 6, losers crossed 0. With 20 trades, test whether the separation holds — median crossings for winners vs. median crossings for losers.

---

Section 6 — Shadow Block Findings (Deferred Items)

Source: entry_rejects.csv and exit_decision_trace.csv. Shadow filter fields are prefixed with shadow_ and record whether a filter would have fired without actually blocking. Locate the exact column names in the files at review time.

For each shadow filter that fired at least once during the experiment:

shadow_trend_mr_block_would_trigger (or equivalent):
- Source: entry_rejects.csv column shadow_trend_mr_block_would_trigger (True/1 rows)
- Total firings across all experiment entry evaluations: [count]
- Among those firings: entries that were subsequently allowed and became winning trades: [count]
- Among those firings: entries that were subsequently allowed and became losing trades: [count]
- Win rate on shadow-blocked evaluations vs. win rate on non-blocked evaluations: [compare]

trend_or_riskoff_block_would_have_blocked (RISK_OFF observation):
- Same structure as above
- Total firings: [count]
- Winners blocked: [count], Losers blocked: [count]

Any other shadow_*_would_block fields found in the files: same analysis for each.

Recommendation criteria (apply to each shadow filter):
- REJECT the filter if: (winners blocked / total firings) is within ±15 percentage points of the overall experiment win rate. A filter that fires on equal proportions of winners and losers has no discriminating power.
- DEFER with explicit next-step if: winners blocked / total firings < (overall win rate minus 15 pp). The filter fires disproportionately on losers. Next step is activation in a controlled run — specify the proposed activation condition.
- DEFER as INSUFFICIENT DATA if: total firings < 5. No recommendation possible. Carry forward to next structural review.

For each filter, state the recommendation explicitly: REJECT, DEFER (activate next experiment), or DEFER (insufficient data). Do not use hedged language like "may be worth considering."

---

Section 7 — Reconciliation Anomaly Patterns

Definition of residual: residual = reconciled_pnl minus declared_pnl (from reconciliation_checks.csv). A negative residual means the actual PnL recovered from the exchange was worse than what the bot declared. A positive residual means the actual PnL was better. The residual is in USD.

Two patterns to evaluate separately.

7A. Negative residual pattern (adverse-exit fill quality):

Known occurrences to carry forward (verify against reconciliation_checks.csv; do not recompute these from memory):
- Baseline run 93: LDO/FIL, residual = -$0.147
- Experiment run 95: AVAX/FIL, residual = -$0.065
- Experiment run 99: FIL/LINEA, residual = -$0.121
- Experiment run 100 Trade 5: BNB/LDO, residual = -$0.068
- Run 101+: [add all occurrences with residual < -$0.020]

Analysis:
- Confirm all known occurrences have negative residuals on adverse-spread exits (exit_reason matches coint_lost, coint_watch_timeout, or health)
- Count occurrences on normal/trailing-stop exits (expected: zero)
- Median negative residual across all occurrences: [value]
- Cumulative impact on experiment PnL: sum of residuals for negative cases only
- Significance test: if cumulative negative residuals exceed 5% of total experiment losses in absolute terms, this is material — open a diagnostic item

Materiality threshold: if |sum(negative residuals)| > $0.20 across the full experiment, flag for dedicated investigation.

7B. Positive residual anomaly (Trade 4, run 100):

- ETH/ETC run 100 Trade 4: residual = +$0.145, declared PnL = [value], reconciled PnL = [value]
- Mechanism unknown — normal-looking trade, no identified data gap
- Check all experiment runs for any trade with residual > +$0.050
- If zero additional occurrences: defer as one-off, no investigation needed
- If ≥ 1 additional occurrence: this becomes a pattern — open investigation item with both trade IDs, exit conditions, and timing

---

Section 8 — Deferred Research Items Review

Every item below must be given one of three dispositions: NEXT PRIORITY, DEFER (carry forward), or REJECT (close out). Items cannot remain in an ambiguous state.

Item 1 — Forward-looking cointegration stability at entry gate:
- Background: coint fragility caused $1.811 in baseline losses. Proposed mechanism: evaluate half-life trend, residual variance trend, or longer coint validation window at entry to reject pairs already deteriorating.
- Evidence from experiment: coint-failure rate is [computed in Section 4]. Total dollar losses from coint-failure exits in the experiment: [$X].
- Has the experiment data strengthened or weakened the case for this?
- Disposition: [NEXT PRIORITY / DEFER / REJECT] with reasoning

Item 2 — Regime-flip exit timing:
- Background: run 98 ETH/AVAX held 4.5 hours after regime committed to TREND before hard exit fired. Proposed mechanism: faster exit trigger when regime transitions during hold.
- Evidence: did any experiment run exhibit similar multi-hour delay after regime commit? Look for regime_break exit_reason combined with hold_duration_seconds > 3 × median hold.
- Disposition: [NEXT PRIORITY / DEFER / REJECT] with reasoning

Item 3 — max_break_risk recalibration:
- Background: median rejected break_risk = 0.150 (at cap). The cap may be too conservative or too loose.
- Evidence: check entry_rejects.csv for break_risk distribution. Has the rejection pattern changed?
- Prior reasoning: defer until coint stability is addressed. Re-evaluate whether this is still the right order.
- Disposition: [NEXT PRIORITY / DEFER / REJECT] with reasoning

Item 4 — Notional adjustment:
- Background: ratios unchanged with notional (prior finding). No notional-dependent effect identified.
- Evidence: has any experiment trade shown notional sensitivity?
- Disposition: [NEXT PRIORITY / DEFER / REJECT] with reasoning. Default expectation is DEFER unless evidence emerged.

Item 5 — Alert/kill-switch mechanism (Patch 6 item 5):
- Background: the run 98 cascade incident prompted a design for an outer backoff / kill-switch alert. Patch 6 was applied. The incident never recurred.
- Evidence: has the Patch 6 outer backoff triggered in any experiment run? (check bot logs for relevant backoff messages)
- Disposition: [NEXT PRIORITY / DEFER / REJECT] with reasoning. If Patch 6 has never triggered, assess whether it is exercised at all.

Item 6 — Exit z-zone widening:
- Background: lower priority in prior reasoning. The TP zone is defined by z ≤ [threshold]. Widening this zone would allow exits at larger z values.
- Evidence: what is the distribution of exit_z in experiment trades? Any pattern suggesting the zone is too narrow?
- Disposition: [NEXT PRIORITY / DEFER / REJECT] with reasoning

New items to evaluate (from experiment observations):

Item 7 — Profit-lock band mechanism (positive evidence from Patch 5):
If Section 3B confirms Patch-5-enabled wins, this is now a tracked finding. State the evidence clearly and assess whether further study is needed or whether the mechanism is now sufficiently understood.
Disposition: [CONFIRM UNDERSTOOD / DEFER for further measurement / REJECT]

Item 8 — Negative reconciliation residual diagnostic:
If Section 7A finds cumulative negative residuals > -$0.20, add as a formal deferred item: "Investigate fill quality on adverse-spread exits."
Disposition: [ADD AS DEFERRED ITEM / CLOSE — within noise]

Item 9 — Positive reconciliation residual investigation:
If Section 7B finds ≥ 1 additional positive residual: add as a formal deferred item.
If no additional occurrence: CLOSE as one-off.

Item 10 — MFE timing pattern:
If Section 5 confirms the winner-late/loser-early pattern across ≥ 20 trades (winner late_hold rate ≥ 70% AND loser early_hold rate ≥ 70%): promote to formal deferred item — "Investigate whether MFE timing predicts outcome before hold ends; consider early-exit signal."
If pattern did not replicate: CLOSE — run 100 was noise.

Item 11 — Any additional items surfaced during experiment runs 101+:
List each with: what was observed, which run, what the proposed investigation would be, and the preliminary disposition.

---

Section 9 — Confidence Calibration Final Update

Confidence level definitions (apply consistently):
- VERIFIED: Mechanically confirmed in production — not a probability, a confirmed fact (e.g., a patch that has fired and been observed)
- HIGH: ≥ 0.80 probability. Multiple supporting trades (≥ 5), pattern consistent across runs, mechanism understood and matches observations
- MEDIUM: 0.50–0.79 probability. Some evidence (3–5 trades), mechanism plausible, not yet consistently confirmed
- LOW: < 0.50 probability. Hypothesis only, few or conflicting observations (< 3 trades), or mechanism unconfirmed
- UNTRACKED: Not yet measured — no data collected, cannot assign a probability

Update every confidence variable with full-experiment data. For any hypothesis with a confidence change (increase or decrease), the justification must cite specific trade counts and PnL figures.

| Hypothesis | Pre-experiment | End-of-experiment | Justification |
|---|---|---|---|
| confidence_full_tp_guard_pass_mechanism | LOW | [update] | [evidence from 3A: guard pass rate, trade count, sample size] |
| confidence_profit_lock_band_mechanism | UNTRACKED | [new value] | [evidence from 3B: Patch-5-enabled win count, PnL] |
| confidence_trapped_zone_thesis | LOW | [update] | [evidence from Section 5: TP-zone PnL pattern, trade count] |
| confidence_coint_fragility_as_dominant_problem | HIGH | [update] | [evidence from Section 4: coint-failure rate, total dollar losses] |
| confidence_ethfi_toxicity | HIGH | [update] | [evidence from 3D: baseline performance, experiment absence] |
| confidence_trend_regime_mr_block_value | HIGH | [update] | [evidence from Section 6: shadow filter findings] |
| confidence_trend_regime_mr_block_active | VERIFIED | VERIFIED | [Patch 4.1 confirmed in production — see DECISION_LOG.md] |
| confidence_emergency_flatten_safety | PATCH_6_APPLIED | [update] | [was outer backoff exercised in production? yes/no] |
| confidence_notional_neutrality | HIGH | [update] | [evidence from experiment: any notional-dependent effect found?] |
| confidence_break_risk_threshold_correctness | MEDIUM | [update] | [evidence from entry_rejects analysis in Item 3] |

Do not change a confidence level without citing specific evidence. "No change in evidence" is a valid justification for leaving a level unchanged — state it explicitly rather than leaving the field blank.

---

Section 10 — Structural Verdict on Patch 5

Based on Sections 1–9, deliver an explicit verdict. The verdict must be chosen before this section is written — do not write a narrative that hedges between verdicts.

Verdict selection guide (use Section 3 evidence):

Verdict A — Patch 5 succeeded:
Meets ALL of: Patch-5-enabled win count ≥ 1, net Patch 5 PnL contribution (from 3C) > +$0.05, ETHFI exclusion produced non-zero estimated avoidance, and no identified trades that closed materially worse due to the lower activation floor.
Action: retain Patch 5, advance to next research priority.

Verdict B — Patch 5 produced mixed results:
Meets: some Patch-5-enabled wins exist (≥ 1), but net Patch 5 contribution (from 3C) is within ±$0.05 of neutral, OR the guard mechanism (3A) never fires (< 2% guard pass rate) making the multiplier parameter irrelevant. Other factors (coint fragility) dominate PnL outcomes.
Action: retain Patch 5 (no confirmed harm), but mechanism is not the primary lever. Next research must address the dominant problem.

Verdict C — Patch 5 should be reverted:
Meets: net Patch 5 contribution (from 3C) is negative (< -$0.05) — trades that closed worse under the lower floor outweigh the enabled wins. This requires confirmed cases of the trailing stop catching trades at losses that a higher floor would have avoided.
Action: revert STATBOT_FULL_TP_GUARD_MULTIPLIER to 0.75. Pursue a different lever.

State the verdict: [A / B / C]

Evidence summary (required, referencing Section 3 findings):
- Patch-5-enabled win count: [N]
- Net Patch 5 contribution: [+$X or -$X]
- Guard pass rate: [pct or "mechanism did not fire"]
- Identified trades that closed worse under Patch 5: [count, total cost in $]

If the guard mechanism never fired (3A guard pass rate < 2%), state explicitly: "The full_tp_guard_passed mechanism does not operate in production under current conditions. The multiplier parameter only affected the profit-lock activation floor. Verdict is based solely on 3B and 3C evidence."

---

Section 11 — Forward Plan

Based on the structural verdict and deferred items review, propose exactly one next research priority. Do not bundle multiple changes.

Next research priority:

Hypothesis: [one sentence — what is being tested]
Mechanism: [how the proposed change would affect trade outcomes — be specific about which exit/entry path is being altered]
Proposed change: [exact config parameter name and value, or exact code change if config is insufficient]
Success criteria (positive result): [what specific measurable outcome over the next 20 trades would confirm the hypothesis — e.g., "coint-failure rate falls from X% to < 40%" or "profit-lock activation rate increases from X to > Y"]
Null criteria (negative result): [what outcome would definitively rule out the hypothesis — e.g., "coint-failure rate unchanged after 20 trades" or "mechanism fires in < 2 trades out of 20"]
Data requirement: [what telemetry must be collected to measure success/null — if a new CSV column or logging point is needed, specify it]
Action threshold: 20 trades before next structural review (or justify alternative)

Patch specification (if a code or config change is required):
- Patch number: [Patch 7]
- Files to modify: [list]
- Parameter: [name and new value]
- Tests required: [count and description of new test cases]

Forbidden in this section:
- Bundling multiple changes into one "next priority"
- Proposing changes without explicit success AND null criteria
- Selecting a priority that doesn't address the largest remaining problem from the analysis (justify any exception explicitly)
- Proposing notional changes without first resolving the coint stability question

Operational items to address before next experiment phase:

- Any Patch 6 / Patch 7 candidates that should be applied before resuming (with a sentence on why each is pre-requisite vs. optional)
- Any telemetry additions needed to measure the next research item (if a measurement would have been useful this review but was missing, add it now)
- Any documentation updates (DECISION_LOG.md, CURRENT_STATE.md, memory files)

New experiment group name:
experiment_group: [exp_DESCRIPTIVE_NAME_v1] — name should encode the primary variable being tested, not the patch number

New action threshold:
trades_until_next_structural_review = 20 (state any justification for a different number)

---

Section 12 — Audit Hygiene for This Review

Unlike per-run audits, this review IS allowed to draw conclusions. But it must still adhere to the following standards.

Required throughout the review:
- Distinguish "concluded from this experiment" from "still hypothesis" for every claim
- Reference specific trade counts and PnL figures for every claim (not "most trades" or "generally")
- Acknowledge any conclusions that depend on small sub-samples (a sample of 2–4 trades must be marked "preliminary" regardless of direction)
- Do not promote any hypothesis to HIGH confidence on the basis of fewer than 5 supporting trades
- Do not declare an experiment "successful" or "failed" without the explicit A/B/C verdict from Section 10
- Do not introduce new strategy changes outside the deferred items list without justification
- Do not retroactively exclude trades from the denominator to improve a metric

Self-check before publishing the review (complete all before finalizing):

[ ] Data assembly: master trade table built, run_id added, no duplicate trade_ids
[ ] Columns verified: actual column names in CSVs confirmed, discrepancies from this document noted
[ ] Completeness: every trade assigned to complete or incomplete telemetry with reason
[ ] All Section 2 metrics computed from actual data (not estimated from memory)
[ ] Section 3A: guard pass rate computed, or documented as unavailable with reason
[ ] Section 3B: every winning trade classified as Patch-5-enabled or Patch-5-neutral
[ ] Section 3C: counterfactual estimates labeled "assumed" with explicit reasoning
[ ] Section 4: every experiment trade's exit_reason mapped to one category; no "other" without listing the actual values
[ ] Section 5: mfe_timing_pct computed or sourced for every complete-telemetry trade
[ ] Section 6: every shadow filter with ≥ 1 firing has a recommendation (REJECT / DEFER / INSUFFICIENT)
[ ] Section 7: all residuals verified against reconciliation_checks.csv, not from memory
[ ] Section 9: confidence table fully populated; every change has a justification with trade count
[ ] Section 10: verdict is A, B, or C — not a hedge; evidence summary present
[ ] Section 11: exactly one next priority; success AND null criteria both stated
[ ] Section 8: every deferred item has a disposition (NEXT PRIORITY / DEFER / REJECT / CLOSE)
[ ] Trade counter confirmed for experiment_group reset in Section 13

---

Section 13 — Continuation Decision

The review concludes with one of three explicit decisions. State the decision before writing any rationale.

Decision 1 — Continue experiment with new research item:
- Applicable when: Patch 5 verdict A or B, deferred items review surfaced a clear next priority, sufficient data exists to act
- Actions:
  - Apply Patch 7 (if required) per Section 11 specification
  - Update experiment_group to the new name
  - Reset trades_since_experiment_start to 0
  - Update DECISION_LOG.md with Patch 7 entry
  - Update CURRENT_STATE.md with new experiment_group and reset counter
  - Update memory: project_experiment_state.md with new state

Decision 2 — Continue with same configuration (collect more data):
- Applicable when: Patch 5 verdict A or B, but insufficient trades to draw a conclusion on a specific deferred item (state the minimum additional trade count required and why)
- Actions:
  - No config changes
  - Reset trade counter to 0 with same configuration
  - Document specifically what additional data is being collected and the decision criteria that will be applied at the next review
  - Update CURRENT_STATE.md with "collecting additional data" note and next structural review trigger

Decision 3 — Pause experiment for major rework:
- Applicable when: Patch 5 verdict C, or experiment surfaced a fundamental issue that cannot be addressed by a single-variable change
- Actions:
  - Bot paused, no new runs
  - Define the rework scope: what must be changed, what must be understood, what condition constitutes "ready to resume"
  - Update CURRENT_STATE.md with pause status and resumption criteria

State the decision: [1 / 2 / 3]
State the new experiment_group (Decision 1) or the reason more data is needed (Decision 2) or the rework scope (Decision 3).

---

Design Notes (Reference)

1. Verdict required, not optional. Section 10 forces a commitment to A, B, or C with quantitative evidence. Per-run audits exist to delay this commitment; this prompt exists to force it.
2. Confidence calibration is the primary update mechanism. Every hypothesis gets its final reading based on the full experiment dataset, not single-run snapshots. Confidence levels are defined with probability ranges — use them consistently.
3. Patch 5 evaluated as two separate mechanisms. The guard pass (3A) and the profit-lock band (3B) are tracked separately — they share a parameter but they are different mechanisms with different evidence. It is valid for 3A to reject (mechanism never fires) while 3B confirms (activation floor enabled wins).
4. Deferred items get explicit resolution. Every deferred item must be NEXT PRIORITY, DEFER, or REJECT. Items cannot drift across reviews without explicit decision.
5. New items surfaced during the experiment are catalogued in Section 8, items 7–11. This prevents observations from being lost between the experiment and the next phase.
6. The continuation decision is explicit. Three options, not a list of considerations. The review ends with a decision number and the required follow-on actions.
7. Data assembly precedes analysis. The pre-review protocol in the Data Sources section must be completed before any section is started. Doing analysis from memory rather than the assembled dataset is the most common failure mode.
8. Counterfactuals are labeled. Section 3C estimates require assumptions. Every assumption must be stated as "assumed" with explicit reasoning. The reader must be able to distinguish observed data from projected data.
