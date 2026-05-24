# Per-Run Audit Template — exp_coint_stability_v1

**Use this template for every run in the exp_coint_stability_v1 window (runs 105+) that closes at least one trade.**
**Stop using it when trades_since_experiment_start ≥ 20. Use the structural review template instead.**

---

## Experiment State Block (Required at Top of Audit)

Report verbatim:

```
experiment_group: exp_coint_stability_v1
runs_since_experiment_start: [list]
trades_since_experiment_start_entering_this_run: [N]
trades_since_experiment_start_after_this_run: [N+closed]
trades_remaining_to_action_threshold: [20 − count]
patches_active: Patch 4.1, Patch 5, Patch 6, Patch 7 (coint stability entry filter)
experiment_phase: Calibration Window
```

If trades_since_experiment_start crosses 20 in this run, do NOT use this template. Use the 20-trade structural review template instead.

---

## Data Sources

```
Reports/v1/<run_id>/
  config_snapshot.json
  trade_closes.csv
  exit_decision_trace.csv
  exit_opportunity_summary.csv
  entry_rejections.csv        ← primary Patch 7 data source
  reconciliation_checks.csv
  liquidity_checks.csv
bot logs
```

---

## Pre-Audit Config Verification

Confirm before any analysis:

- `STATBOT_ENTRY_COINT_STABILITY_ENABLED = true`
- `STATBOT_ENTRY_COINT_STABILITY_WINDOW = 5`
- `STATBOT_ENTRY_COINT_STABILITY_SLOPE_MAX = 0.020`
- `STATBOT_ENTRY_COINT_STABILITY_MIN_SAMPLE_INTERVAL_SECONDS = 60`
- `STATBOT_FULL_TP_GUARD_MULTIPLIER = 0.50`
- ETHFI-USDT-SWAP and HMSTR-USDT-SWAP in graveyard with `ttl_days: null`
- All frozen variables unchanged (exit z-thresholds, max_break_risk=0.12, notional=$200, circuit breaker, profit-lock giveback=0.50)

If any verification fails, halt audit and report the discrepancy.

---

## Section 1 — Run Summary (Telemetry Only, No Interpretation)

Report:

- duration (hours)
- total entry signal gate evaluations
- total entry attempts
- total accepted trades
- total rejected entries
- closed trades count
- open trades at run end
- realized session PnL
- win count / loss count / win rate
- avg win, avg loss
- avg hold duration
- pair switches
- circuit breaker status and trip reason (if any)
- consecutive_loss progression (session and persistent counters)

Do not compare to prior runs in this section. Just report.

---

## Section 2 — Per-Trade Telemetry (Required for Every Closed Trade)

For each closed trade, report:

- pair
- entry regime
- entry z-score
- exit z-score
- exit reason
- hold duration (minutes)
- gross MFE
- MAE
- net PnL
- post-entry cointegration status at close
- outcome (win / loss)

---

## Section 3 — Reconciliation Telemetry

For each closed trade:

- gross PnL (position-level)
- equity delta
- difference (fees + slippage + unexplained)
- unexplained residual after fees and slippage estimates

Flag any trade where unexplained residual exceeds $0.05 and a restart scenario was not active.

---

## Section 4 — Patch 7 Cointegration Stability Filter — Per-Trade Gate Status

**This section is the primary experiment measurement. Complete it for every closed trade.**

For each closed trade, report:

### 4A — Watch-Time and Gate Status (Per Trade)

| Field | Value |
|---|---|
| pair | |
| pair_activation_timestamp | (from log: when pair became active/switched-to) |
| entry_timestamp | (from trade_closes.csv or log) |
| watch_time_before_entry_seconds | (entry_timestamp − pair_activation_timestamp) |
| watch_time_before_entry_minutes | |
| gate_status | `evaluated` / `insufficient_history` / `not_reached` |
| coint_stability_check_evaluated_count | (from entry_rejections.csv, this pair's rows) |
| coint_stability_insufficient_history_count | (from entry_rejections.csv, this pair's rows) |
| coint_stability_check_blocked_count | (from entry_rejections.csv, this pair's rows) |
| gate_reached | yes / no (no = upstream gate blocked before safety gate) |
| slope at entry | (from entry_rejections.csv final pre-entry row for this pair; negative = improving) |
| slope_max threshold | 0.020 (frozen) |
| delta_from_threshold | slope_max − slope_at_entry (positive = how far below threshold; negative = blocked) |
| exit_category | `coint-failure` (cointegration_lost / coint_watch_timeout) / `normal` (trailing_stop / full_tp / other) |

**Distance-from-threshold interpretation (record, do not conclude):**
- Delta near 0 (e.g., < 0.005): filter was close to blocking — threshold tuning might have caught it.
- Delta large (e.g., > 0.015): slope was far below threshold — no threshold tuning would have caught it; if exit was coint-failure, this is evidence against the premise.
- T5 reference: slope −0.00449, delta = 0.020 − (−0.00449) = 0.02449 → far below threshold, coint-failure.

**gate_status derivation:**
- `not_reached`: upstream gate (strategy_gate or regime_gate) blocked before safety gate was evaluated — coint_stability counters will be absent or 0 in entry_rejections.csv for this pair
- `insufficient_history`: gate reached but evaluated_count=0, insufficient_history_count≥1 for this pair's rows
- `evaluated`: gate reached and evaluated_count≥1 for this pair's rows

**Watch-time source:** Check log for `PAIR_SWITCH` or startup ticker config lines to determine when the pair became active.

**First-run Patch 7.1 validation (applies to the first gate-reaching trade after 7.1 was deployed, 2026-05-24):**
If this is the first gate-reaching trade under Patch 7.1, the result is an immediate binary test:
- `evaluated_count ≥ 1` → 7.1 working. Buffer filled from monitoring ticks. Proceed.
- `insufficient_history` → 7.1 failed silently. Stop window, diagnose before collecting more trades.
Common failure modes: (1) pair-key mismatch between monitoring path and gate, (2) `is_manage_new_trades` guard logic inverted. Do not dismiss this as "just one trade with short watch time" — after 7.1, any pair with ≥5 minutes of watch should show `evaluated_count ≥ 1`.

### 4B — Session Aggregate (Rejected-Entry Rows Only)

From entry_rejections.csv (all rows, not just the traded pair):

- Total `entry_safety_gate` rows: [N]
- Rows with `evaluated_count = 0` AND `insufficient_history = 1`: [N]
- Rows with `evaluated_count ≥ 1`: [N]
- Aggregate ratio: `insufficient / (evaluated + insufficient)` = [X%]
- Running cumulative ratio across trades 1–N in this experiment window: [X%]

Report counts only. Do not interpret threshold proximity.

### 4C — Watch-Time Distribution Tracker (Cumulative)

Maintain a running table across all trades in the experiment window. Update it each run.

| Trade # | Run | Pair | Watch Time (s) | Gate Status |
|---|---|---|---|---|
| T1 | run_106 | LINK/SUI | 22320 (6.2h) | evaluated |
| T2 | run_107 | SUI/AAVE | 85 | insufficient_history |
| T3 | run_108 | ETH/AVAX | 864 (14.4min) | not_reached (RISK_OFF blocked) |
| T[N] | run_[X] | [pair] | [seconds] | [status] |

After each run, report:
- Count of `evaluated` trades: [N]
- Count of `insufficient_history` trades: [N]
- Count of `not_reached` trades: [N]
- Fraction of trades where gate was reachable and evaluated: `evaluated / (evaluated + insufficient_history)` = [X%]
  (Excludes `not_reached` trades — those are upstream blocks, not Patch 7 outcomes)

**Why this matters:** The coint-failure rate effect can only appear in `evaluated` trades. If `evaluated / (evaluated + insufficient_history)` is low, the gate is functionally inactive on a large fraction of entries. At the 20-trade structural review, coint-failure rate must be split by gate status.

### 4D — Running Slope-vs-Outcome Tally (Cumulative, Evaluated Trades Only)

Maintain this table across all gate-evaluated trades in the window. Update each run. **Only include trades where the filter passed and the trade closed** (gate_status = `evaluated` AND `coint_stability_check_blocked_count = 0` AND trade was accepted). Insufficient-history, not-reached, and **blocked** trades do not belong here. Blocked entries go to the `coint_stability_slope_exceeded` count — a separate population. These two populations must never mix: 4D = passed-then-outcome; slope_exceeded = blocked-before-entry. Since blocked trades never become closed trades this separation is automatic in practice, but state it explicitly to prevent ambiguity if slope_exceeded starts counting.

**Delta convention (slope_max − slope_at_entry):** large positive delta = slope far below threshold (filter was not close to catching it); small positive or negative delta = slope near or above threshold (near-miss or should have been caught). Cutoffs: delta < 0.005 → tunable; delta > 0.015 → premise question. A trade with slope above 0.020 gets blocked and never appears in this tally.

| Trade # | Run | Pair | Slope at Entry | Delta from Threshold | Exit Category |
|---|---|---|---|---|---|
| T5 | run_111 | FIL/FLOKI | −0.00449 | +0.02449 | coint-failure |
| T[N] | run_[X] | [pair] | [value] | [0.020 − slope] | coint-failure / normal |

After each run, note:
- Count of coint-failure trades: [N] / total evaluated: [N]
- Whether coint-failures cluster at higher slopes than normal exits (eyeball check, no statistics)
- Whether failure deltas are near-threshold (< 0.005 → tunable) or far-below (> 0.015 → premise question)

Do not conclude from this table mid-window. Record and report.

---

### 4C-TRIGGER — Gate-Inactivity Soft Trigger (Closed-Trade Based)

This trigger watches for the condition the rejected-row ratio cannot see: the gate being functionally inactive across the actual experimental units (closed trades), not just rejected-entry rows.

**Check after every trade once 6+ gate-reaching trades have accumulated (evaluated + insufficient_history ≥ 6):**

If `evaluated / (evaluated + insufficient_history)` falls below **40%** over the last 6 gate-reaching trades:

→ **FLAG: gate-inactivity condition.** Stop the window and apply Patch 7.1 before continuing.

The rolling window counts **gate-reaching trades only** (evaluated + insufficient_history), not closed trades. `not_reached` trades are excluded from the window count — a run heavy on RISK_OFF upstream blocks could otherwise produce a rolling window whose denominator is only 2-3, making the 40% threshold meaningless on a tiny sample. The denominator is always ≥6 when the trigger first evaluates.

The reasoning: if 4 of any 6 consecutive gate-reaching trades are `insufficient_history` (gate ran but couldn't act), the gate is functionally inactive on the majority of trades it's actually seeing. Continuing to trade produces a confounded sample, not a larger one. The cost of applying Patch 7.1 mid-window is one restart. The cost of discovering gate-inactivity at trade 20 is an unusable 20-trade window.

**This trigger is independent of Section 5.** Section 5 retired at 3-trade CONTINUE. This trigger remains active for the full window.

**`not_reached` trades are fully excluded.** They don't reflect Patch 7 behavior — the gate never ran. They don't count toward the rolling window, and they don't count toward the denominator.

Report trigger status each run:
```
gate_inactivity_trigger:
  total_closed_trades: [N]
  gate_reaching_trades (evaluated + insufficient_history): [N]
  evaluated: [N]
  insufficient_history: [N]
  not_reached: [N]
  cumulative_effectiveness_fraction: [evaluated / (evaluated + insufficient_history)]
  rolling_6_gate_reaching_fraction: [N/A if gate_reaching < 6 / value if ≥6]
  trigger_status: MONITORING (need N gate-reaching) / MONITORING / FIRED
```

---

## Section 5 — Early-Stop Trigger Check (Patch 7.1)

Apply after every trade (pre-committed rules — do not modify):

**After 2 trades (if not yet checked):**
- If `evaluated_count = 0` on BOTH trades → **FIRED: stop window, apply Patch 7.1**
- If `evaluated_count ≥ 1` on either trade → **CONTINUE**

**After 3 trades (if continuing):**
- If `insufficient_history / (evaluated + insufficient_history) > 0.70` → **FIRED: stop window, apply Patch 7.1**
- If ratio ≤ 0.70 AND `evaluated_count ≥ 3` → **CONTINUE**

Report trigger check result explicitly each run. Once a CONTINUE decision is confirmed at 3 trades, this section becomes "N/A — 3-trade check passed, CONTINUE confirmed" for subsequent runs.

**Status entering this run:** [PENDING / 2-TRADE CHECK PASSED / 3-TRADE CHECK PASSED — CONTINUE]

---

## Section 6 — Entry Rejection Distribution

Report rejection reason counts from entry_rejections.csv:

- `strategy_gate` (coint_invalid or similar)
- `entry_safety_gate` (all reasons)
  - `advanced_ml_break_risk_high`
  - `liquidity_at_floor`
  - `trade_quality_gate`
  - `statarb_mr_trend_regime_block`
  - `risk_off_thin_liquidity`
  - `cointegration_component_below`
  - `coint_stability_slope_exceeded` (Patch 7 block — report if present)
  - other
- Total rows

Report break_risk distribution at rejection (mean, median, max) if present.

---

## Section 7 — Counter Update and Next Step

Close the audit with:

```
trades_since_experiment_start: [updated count]       ← window completion counter
evaluated_trade_count: [N]                           ← real experimental N (gate reached AND evaluated)
insufficient_history_trade_count: [N]                ← gate reached but couldn't act
not_reached_trade_count: [N]                         ← upstream block, gate never ran
trades_remaining_to_action_threshold: [20 − count]
cumulative PnL (experiment window): [sum]
win rate (experiment window): [wins/total]
coint-exit losses so far: [count and $ sum — cointegration_lost + cointegration_watch_timeout exits]
gate_inactivity_trigger_status: MONITORING / FIRED
next step: [if count < 20: "run [N+1] with frozen configuration"; if count ≥ 20: "20-trade Structural Review"]
```

`trades_since_experiment_start` is the window-completion counter. `evaluated_trade_count` is the real experimental N — the number of trades on which Patch 7 could actually have acted. If `evaluated_trade_count` is tracking far below `trades_since_experiment_start`, the window is underpowered and the structural review must state this explicitly rather than treating 20 trades as the sample size.

**slope_exceeded=0 resolution criterion (pre-committed):**
If `coint_stability_slope_exceeded` remains 0 after 6 gate-evaluated trades:
- Fire rate = 0/6 = 0%, below the 15% loosen-threshold.
- This is not "inconclusive" — it is the pre-committed calibration trigger: slope_max 0.020 → 0.030.
- The calibration adjustment is applied at the structural review (or noted as pending if fewer than 20 trades have closed).
- Fire rate denominator = evaluated trades only. Insufficient-history and not-reached trades are excluded.

No recommendations. No "next priority" lists. If trades_since_experiment_start is still below 20 and the gate-inactivity trigger has not fired, the next action is the next run with frozen configuration.

---

## Section 8 — Forbidden Inferences (Audit Hygiene)

The audit must NOT contain:

- "Patch 7 is working / not working" based on fire count alone
- "the gate is effective / ineffective" without reference to watch-time distribution
- "coint-failure rate improved / didn't improve" (requires 20-trade window)
- "short watch times are a problem" as a conclusion (it's an observation, reported in Section 4C)
- any recommendation to adjust `slope_max`, `window`, or `min_sample_interval` mid-window
- any narrative framing about the experiment's direction based on early trades

If language resembles the above, flag it and rewrite.

---

## Section 9 — Permitted Observations

The audit MAY contain:

- Factual per-trade gate status reports ("gate was insufficient_history for Trade N due to 85s watch time")
- Factual running tally of watch-time distribution
- Direct observation of watch-time vs gate-status correlation (no interpretation)
- Factual coint_stability block count (if `coint_stability_slope_exceeded` appears — report pair, timing, and p-value slope that triggered it)
- Factual reconciliation anomalies
- Factual circuit-breaker state

---

*Template version: exp_coint_stability_v1 v1.1, created 2026-05-23, updated 2026-05-23.*
*run_105 confirmed 0 trades — experiment window trade table correctly starts at T1=run_106.*
*Supersedes per-run audit structure from prior experiments (RUN_100.md, RUN_101.md).*
*20-trade structural review template to be created separately. Structural review must report coint-failure rate split by gate_status (evaluated vs insufficient_history) and must state evaluated_trade_count as the actual experimental N, not trades_since_experiment_start.*
