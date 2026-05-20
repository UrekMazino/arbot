Run 99 Post-Run Audit — Patch 6 Verified, Patch 5 Continuation
This is the second telemetry run under experiment_group exp_guard050_ethfi_excluded_v1 to produce trade data (run 98 produced 2 trades affected by the OKX incident; run 95 produced 3 trades). The audit is telemetry-focused, not thesis-generating. Structural reassessment remains reserved for the 20-trade threshold review.
Experiment State Block (Required at Top of Audit)
Report verbatim:

experiment_group: exp_guard050_ethfi_excluded_v1
runs_since_experiment_start: 5 (95 + 96 + 97 + 98 + 99; 96 and 97 produced 0 trades)
trades_since_experiment_start_entering_this_run: 5
trades_since_experiment_start_after_this_run: [updated count]
trades_remaining_to_action_threshold: [20 − count]
circuit_breaker_trips_this_experiment: 1 entering this run, [updated] after
patches_active: Patch 4.1 (TREND block fix, VERIFIED), Patch 5 (guard 0.50 + ETHFI excluded), Patch 6 (retry backoff + exit-intent persistence)
experiment_phase: Research Stability Phase

Use

Reports/v1/<run_99>/*
config_snapshot.json
trade_closes.csv
exit_decision_trace.csv
exit_opportunity_summary.csv
entry_rejects.csv
reconciliation_checks.csv
liquidity_checks.csv
pair_supply_control.json
pair_strategy_state.json
bot logs

Pre-Audit Config Verification
Confirm before any analysis:

STATBOT_FULL_TP_GUARD_MULTIPLIER = 0.50
effective TP floor = $0.120
profit-lock activation floor = $0.170
ETHFI-USDT-SWAP present in graveyard with ttl_days: null
Patch 4.1 TREND-regime STATARB_MR block active
Patch 6 retry backoff schedule [5, 30, 120, 300] active
Patch 6 set_pending_hard_exit / get_pending_hard_exit mechanism active
All frozen variables unchanged

If any verification fails, halt audit and report the discrepancy.
Section 1 — Run Summary (Telemetry Only, No Interpretation)
Report:

duration (hours)
total entry signal gate evaluations
total entry attempts
total accepted trades
total rejected entries
closed trades count
open trades at run end
realized session PnL
win count / loss count / win rate
avg win, avg loss
avg MFE, avg MAE
avg hold duration
pair switches
circuit breaker status and trip reason (if any)
consecutive_loss progression (session and persistent counters)

Do not compare to prior runs in this section. Just report.
Section 2 — Per-Trade Telemetry (Required for Every Closed Trade)
For each closed trade, report:

pair
entry regime
entry z-score
exit z-score
exit reason
hold duration
gross MFE
MAE
net PnL
post-entry cointegration status at close

MFE Timing Telemetry (the core measurement of this experiment):
For each trade, compute:

timestamp of MFE peak
mfe_timing_pct = (time_of_MFE_peak − entry_timestamp) / (exit_timestamp − entry_timestamp)
mfe_timing_bucket:

early_hold (0%–33%)
mid_hold (34%–66%)
late_hold (67%–100%)


z-score at MFE peak

Threshold Crossing Telemetry:
For each trade, report whether and when (z-score at first crossing) the following MFE thresholds were crossed:

$0.12 (new effective TP floor)
$0.14 (estimated cost breakeven)
$0.17 (new profit-lock activation floor)
$0.18 (old TP floor)
$0.23 (old profit-lock activation floor)
$0.24 (base guard floor)

If a threshold was never crossed, report "not_crossed."
TP-Zone PnL Telemetry:
For each trade, report:

max floating PnL recorded while z ≤ 0.35 (TP zone)
max floating PnL recorded while z ≤ 1.0
max floating PnL recorded while z ≤ 1.5
whether MFE peak occurred before, during, or after first TP-zone entry

Exit Mechanism Telemetry:
For each trade, report:

did profit-lock activate? (yes/no)
if yes: trace row of activation / total trace rows
did trailing stop fire? (yes/no)
if yes: PnL at fire vs PnL at MFE peak
did full TP guard pass? (count of passes / count of evaluations)

Section 3 — Patch 4.1 Status (TREND Regime Block)

statarb_mr_trend_regime_block fire count in entry_rejections.csv
TREND regime duration as % of run
TREND-regime STATARB_MR entries executed (expected: 0)
shadow_trend_mr_block_would_trigger count

If any TREND-regime STATARB_MR entry executed despite Patch 4.1, flag as critical anomaly — this would indicate Patch 4.1 regressed or a new bypass path exists.
Section 4 — Patch 6 Status (Emergency Flatten Safety)
This is new for run 99. Report:

Were any close-order failures encountered? (any non-success response from OKX on close attempts)
If yes: was the retry backoff schedule observed? (5s, 30s, 120s, 300s between cycles)
Were any close attempts made during which exit-intent persistence was required?
If yes: did get_pending_hard_exit() correctly return the persisted intent across the retry window?
Were any clear_entry_tracking() events logged?
If yes: did the pending hard exit survive (not get cleared by entry-tracking clear)?
Count of _flatten_cycle_count increments during the run
Maximum _flatten_cycle_count reached

If no close failures occurred during the run, state: "Patch 6 not exercised this run. Behavior validated by test suite only."
Section 5 — ETHFI Exclusion Verification

confirm zero ETHFI-USDT-SWAP entries in trade_closes
confirm zero ETHFI-USDT-SWAP entries in entry attempts
if pair_supply_control shows ETHFI was evaluated, report whether it was filtered at graveyard check
which symbols rotated through the pair universe in ETHFI's absence
did universe diversity (distinct symbols traded) increase, decrease, or stay flat vs prior runs

Section 6 — Entry Rejection Distribution
Report rejection reason counts. Do not propose threshold changes.

strategy_gate (coint_invalid)
advanced_ml_break_risk_high
liquidity_at_floor
trade_quality_gate
statarb_mr_trend_regime_block
risk_off_thin_liquidity
cointegration_component_below
other

Report break_risk distribution stats at rejection (mean, median, max).
Section 7 — Reconciliation Telemetry
For each closed trade:

gross PnL (position-level)
equity delta
difference (fees + slippage + unexplained)
unexplained residual after fees and slippage estimates

Flag any trade where unexplained residual exceeds $0.05 and a restart scenario was not active.
Section 8 — PnL Source Mismatch (Audit Template Update Active)
Per the diagnostic note saved 2026-05-20:
For each closed trade, report the early-trace-row delta between floating_pnl_usdt and position_snapshot_unrealized_pnl_usdt.
Expected: $0.09–$0.10 (fees-timing artifact, normal).
Flag only if: delta exceeds $0.25 in the early-trade window without a restart scenario being logged.
If flagged, report as anomaly. Otherwise report as "within expected fees-timing range" with the actual delta value.
Section 9 — Persistent Consecutive Loss Counter

Persistent counter value at session start
Persistent counter value at session end (or at breaker trip if applicable)
Did any session logic reference the persistent counter? (state_mode confirmation)

Section 10 — Confidence Calibration Update
For each hypothesis in the experiment-state confidence block, report:

prior confidence level (from run 98)
new confidence level
explicit justification for any change, with reference to specific telemetry from this run
if no change, state "no change" with brief reason

Hypotheses to address:

confidence_guard_mechanism
confidence_trapped_zone_thesis
confidence_coint_fragility_as_dominant_problem
confidence_ethfi_toxicity
confidence_trend_regime_mr_block_value
confidence_trend_regime_mr_block_active (status: VERIFIED via Patch 4.1)
confidence_emergency_flatten_safety (status: PATCH_6_APPLIED — was not a confidence item before this run, add it now)
confidence_notional_neutrality
confidence_break_risk_threshold_correctness

Rule: a single run is rarely enough to shift confidence. Expect most hypotheses to read "no change." Justify any shift with specific data.
Section 11 — Forbidden Inferences (Audit Hygiene)
The audit must NOT contain:

"guard reduction worked" / "guard reduction failed"
"ETHFI exclusion fixed the problem" / "ETHFI exclusion didn't help"
"Patch 6 worked / didn't work" based on single-run outcomes (validated by tests, not runs)
"the strategy is now profitable" / "the strategy is still broken"
recommendations to revert, extend, or stack additional changes
new structural theses about pair quality, exit architecture, or market regime
any phrase resembling "this suggests," "the data is starting to indicate," "this points toward" applied to multi-trade conclusions

If the audit contains language resembling the above, flag it and rewrite.
Section 12 — Permitted Observations
The audit MAY contain:

factual reports of any single-trade event ("profit-lock activated at $0.18 MFE on trade N")
directional notes on MFE timing bucket distribution
explicit comparisons to baseline distribution (runs 90+93+94+95+98) for the specific telemetry fields above
factual observation of universe composition changes
circuit breaker trip conditions if applicable
sampling caveat: if breaker truncated the run, note that the sample is "first N trades after session start" not steady-state
factual report on whether Patch 6 was exercised and behaved per design (if exercised)

Section 13 — Counter Update and Next Step
Close the audit with:

trades_since_experiment_start: [updated count]
trades_remaining_to_action_threshold: [20 − count]
estimated runs remaining at current pace
next step: run 100 with frozen configuration

No recommendations. No "next priority" lists. No "what to investigate next." The next action is run 100 with the same configuration unless an operational issue surfaces.

That's the prompt. Key differences from the run 95 audit prompt:

Section 4 is new — Patch 6 verification telemetry. Forces the audit to confirm whether the safety mechanism was exercised this run, and if so, whether it behaved correctly.
Section 8 is updated — uses the closed PnL diagnostic as the baseline. Early-trace delta of $0.09–$0.10 is now expected and reported factually, not flagged. Only deltas above $0.25 without a restart scenario get flagged.
Confidence calibration adds confidence_emergency_flatten_safety as a new tracked item (PATCH_6_APPLIED status).
Counter math reflects 5/20 entering this run.

Save the prompt template now and reuse it run-over-run with the counter updated. The structure stays stable, only the numbers change.