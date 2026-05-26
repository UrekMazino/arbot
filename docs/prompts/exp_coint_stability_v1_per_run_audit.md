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
patches_active: Patch 4.1, Patch 5, Patch 6, Patch 7 (coint stability entry filter), Patch 7.1 (monitoring-loop buffer population), Patch 7.2 (entry-slope persistence for accepted trades)
experiment_phase: Calibration Window
```

If trades_since_experiment_start crosses 20 in this run, do NOT use this template. Use the 20-trade structural review template instead.

---

## Data Sources

```
Reports/v1/<run_id>/
  config_snapshot.json
  trade_closes.csv            ← now includes entry_coint_stability_slope + entry_coint_stability_evaluated_count (Patch 7.2, T7+)
  exit_decision_trace.csv
  exit_opportunity_summary.csv
  entry_rejections.csv        ← primary Patch 7 blocked-entry data source
  reconciliation_checks.csv
  liquidity_checks.csv
bot logs (STRATEGY_TRADE_OPEN now logs coint_stability_slope — Patch 7.2)
```

---

## Pre-Audit Config Verification

Confirm before any analysis:

- `STATBOT_ENTRY_COINT_STABILITY_ENABLED = true`
- `STATBOT_ENTRY_COINT_STABILITY_WINDOW = 5`
- `STATBOT_ENTRY_COINT_STABILITY_SLOPE_MAX = 0.020`
- `STATBOT_ENTRY_COINT_STABILITY_MIN_SAMPLE_INTERVAL_SECONDS = 60`
- `STATBOT_FULL_TP_GUARD_MULTIPLIER = 0.50`
- ETHFI-USDT-SWAP, HMSTR-USDT-SWAP, FLOKI-USDT-SWAP all permanently graveyarded with `ttl_days: null`
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

**Meme-token execution-cost sub-pattern tracker (cumulative):**
Both at $200 notional. Negative unexplained residuals on meme tokens:
- HMSTR (run_102): −$0.226 → graveyarded
- FLOKI (run_111): −$0.093 → graveyarded

If this run produces a third meme-token negative residual: escalate to a category-exclusion proposal (exclude meme tokens generally) rather than another individual graveyard, and route to Item 12 (execution cost model) for the structural review. Note notional context on any new occurrence.

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
| coint_stability_check_evaluated_count | **(from trade_closes.csv `entry_coint_stability_evaluated_count` — Patch 7.2; fall back to entry_rejections.csv only for pre-T7 trades)** |
| coint_stability_insufficient_history_count | (from entry_rejections.csv, this pair's rows) |
| coint_stability_check_blocked_count | (from entry_rejections.csv, this pair's rows) |
| gate_reached | yes / no (no = upstream gate blocked before safety gate) |
| slope at entry | **(from trade_closes.csv `entry_coint_stability_slope` — Patch 7.2; negative = improving. Pre-T7 trades use entry_rejections.csv final pre-entry row, or "unavailable" if entered on first signal)** |
| slope_max threshold | 0.020 (frozen) |
| delta_from_threshold | slope_max − slope_at_entry (positive = how far below threshold; negative = blocked) |
| exit_category | `coint-failure` (cointegration_lost / coint_watch_timeout) / `normal` (trailing_stop / full_tp / other) |

**Patch 7.2 slope source (T7 onward):** Accepted trades now persist `entry_coint_stability_slope` directly in trade_closes.csv, including trades that entered on first signal with no pre-entry rejection rows. The "unavailable" gap that affected T6 is closed. Read slope from the structured field, not from rejection-row inference.

**One-time staleness verification (perform on the FIRST trade with a Patch 7.2 slope value):**
Confirm the persisted `entry_coint_stability_slope` matches the slope from the *accepting* gate evaluation — cross-reference against the `STRATEGY_TRADE_OPEN` log line at the entry timestamp.
- If they match → persistence captured the correct (entry-decision) evaluation. No need to re-verify on subsequent trades.
- If the persisted value corresponds to an earlier watch-period evaluation → the plumbing is capturing a stale slope. Flag immediately; the 4D data is not trustworthy until fixed.

Report the verification result explicitly on the first 7.2 trade, then mark "staleness verified" for subsequent runs.

**Post-restart buffer caveat:** After any bot restart, `_PAIR_COINT_PVALUE_HISTORY` starts empty and needs ~5 minutes of monitoring-loop population before the gate can compute a slope. A trade entering with <5 min of post-restart watch may show `insufficient_history` — this is expected buffer refill, NOT a Patch 7.1/7.2 regression. The first valid slope test after a restart is the first trade with ≥5 min of post-restart watch time. Note in the audit if this run followed a restart and whether any early trade was affected.

**Distance-from-threshold interpretation (record, do not conclude):**
- Delta near 0 (e.g., < 0.005): filter was close to blocking — threshold tuning might have caught it.
- Delta large (e.g., > 0.015): slope was far below threshold — no threshold tuning would have caught it; if exit was coint-failure, this is evidence against the premise.
- T5 reference: slope −0.00449, delta = 0.020 − (−0.00449) = 0.02449 → far below threshold, coint-failure.

**gate_status derivation:**
- `not_reached`: upstream gate (strategy_gate or regime_gate) blocked before safety gate was evaluated — coint_stability counters absent or 0 for this pair
- `insufficient_history`: gate reached but evaluated_count=0, insufficient_history_count≥1
- `evaluated`: gate reached and evaluated_count≥1

**Watch-time source:** Check log for `PAIR_SWITCH` or startup ticker config lines to determine when the pair became active.

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
| T1 | run_106 | LINK/SUI | 22320 (6.2h) | evaluated (pre-7.1, excluded) |
| T2 | run_107 | SUI/AAVE | 85 | insufficient_history (pre-7.1, excluded) |
| T3 | run_108 | ETH/AVAX | 864 (14.4min) | not_reached — RISK_OFF (pre-7.1, excluded) |
| T4 | run_109 | BCH/CRCL | 1944 (32.4min) | insufficient_history (pre-7.1, excluded) |
| T5 | run_111 | FIL/FLOKI | 878 (14.6min) | evaluated |
| T6 | run_113 | DOGE/SUI | 1035 (17.25min) | evaluated |
| T[N] | run_[X] | [pair] | [seconds] | [status] |

After each run, report:
- Count of `evaluated` trades (Patch 7.1 window, T5 onward): [N]
- Count of `insufficient_history` trades: [N]
- Count of `not_reached` trades: [N]
- Fraction of trades where gate was reachable and evaluated: `evaluated / (evaluated + insufficient_history)` = [X%]
  (Excludes `not_reached` trades — those are upstream blocks, not Patch 7 outcomes. Excludes pre-7.1 trades T1–T4 — gate population mechanism was not yet functional.)

**Why this matters:** The coint-failure rate effect can only appear in `evaluated` trades. If `evaluated / (evaluated + insufficient_history)` is low, the gate is functionally inactive on a large fraction of entries. At the 20-trade structural review, coint-failure rate must be split by gate status.

### 4D — Running Slope-vs-Outcome Tally (Cumulative, Evaluated Trades Only)

Maintain this table across all gate-evaluated trades in the window. Update each run. **Only include trades where the filter passed and the trade closed** (gate_status = `evaluated` AND `coint_stability_check_blocked_count = 0` AND trade was accepted). Insufficient-history, not-reached, and **blocked** trades do not belong here. Blocked entries go to the `coint_stability_slope_exceeded` count — a separate population. These two populations must never mix: 4D = passed-then-outcome; slope_exceeded = blocked-before-entry. Since blocked trades never become closed trades this separation is automatic in practice, but state it explicitly to prevent ambiguity.

**Delta convention (slope_max − slope_at_entry):** large positive delta = slope far below threshold (filter was not close to catching it); small positive or negative delta = slope near or above threshold (near-miss or should have been caught). Cutoffs: delta < 0.005 → tunable; delta > 0.015 → premise question. A trade with slope above 0.020 gets blocked and never appears in this tally.

**Slope source:** T7 onward read from trade_closes.csv `entry_coint_stability_slope` (Patch 7.2). T5 read from entry_rejections.csv. T6 = unavailable (entered on first signal pre-7.2; permanent gap, leave as "unavailable").

| Trade # | Run | Pair | Slope at Entry | Delta from Threshold | Exit Category |
|---|---|---|---|---|---|
| T5 | run_111 | FIL/FLOKI | −0.00449 | +0.02449 | coint-failure |
| T6 | run_113 | DOGE/SUI | unavailable (pre-7.2) | unavailable | coint-failure |
| T[N] | run_[X] | [pair] | [value] | [0.020 − slope] | coint-failure / normal |

After each run, note:
- Count of coint-failure trades: [N] / total evaluated: [N]
- Whether coint-failures cluster at higher slopes than normal exits (eyeball check, no statistics)
- Whether failure deltas are near-threshold (< 0.005 → tunable) or far-below (> 0.015 → premise question)
- **Premise-tracking note:** the open question is whether coint-failures are predictable from entry slope. T5 (only observable failure so far) had a far-below-threshold slope (premise-negative). Record each new evaluated coint-failure's delta to build this signal. Do not conclude mid-window.

Do not conclude from this table mid-window. Record and report.

---

### 4C-TRIGGER — Gate-Inactivity Soft Trigger (Closed-Trade Based)

This trigger watches for the condition the rejected-row ratio cannot see: the gate being functionally inactive across the actual experimental units (closed trades), not just rejected-entry rows.

**Check after every trade once 6+ gate-reaching trades have accumulated (evaluated + insufficient_history ≥ 6):**

If `evaluated / (evaluated + insufficient_history)` falls below **40%** over the last 6 gate-reaching trades:

→ **FLAG: gate-inactivity condition.** Stop the window and investigate before continuing.

The rolling window counts **gate-reaching trades only** (evaluated + insufficient_history), not closed trades. `not_reached` trades are excluded from the window count — a run heavy on RISK_OFF upstream blocks could otherwise produce a rolling window whose denominator is only 2-3, making the 40% threshold meaningless on a tiny sample. The denominator is always ≥6 when the trigger first evaluates.

The reasoning: if 4 of any 6 consecutive gate-reaching trades are `insufficient_history` (gate ran but couldn't act), the gate is functionally inactive on the majority of trades it's actually seeing. Continuing to trade produces a confounded sample, not a larger one.

**Note on remedy:** Patch 7.1 (monitoring-loop buffer population) is already deployed. If this trigger fires *despite* 7.1, the remedy is not "apply 7.1 again" — it's to investigate why buffers aren't filling even with monitoring-loop population (e.g., pairs switching faster than 5 min, or the monitoring call not reached on some path). Diagnose the specific cause before continuing.

**This trigger is independent of Section 5.** Section 5 retired at 3-trade CONTINUE. This trigger remains active for the full window.

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

**Status: 2-TRADE CHECK PASSED — CONTINUE (confirmed run_113, T5+T6 both evaluated).**

The 3-trade check is the last remaining Section 5 gate. Apply at T7:

**3-trade check (at T7):**
- If `insufficient_history / (evaluated + insufficient_history) > 0.70` → **FIRED: stop window, investigate.**
- If ratio ≤ 0.70 AND `evaluated_count ≥ 3` → **CONTINUE — Section 5 retires.**

Once the 3-trade check passes, Section 5 becomes "N/A — 3-trade check passed, CONTINUE confirmed" for all subsequent runs, and the gate-inactivity trigger (4C-TRIGGER) is the sole active stop mechanism.

**Status entering this run:** [2-TRADE CHECK PASSED, 3-TRADE PENDING / 3-TRADE CHECK PASSED — CONTINUE]

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
  - `coint_stability_slope_exceeded` (Patch 7 block — report count, pair(s), and slope value(s))
  - other
- Total rows

Report break_risk distribution at rejection (mean, median, max) if present.

**slope_exceeded tracker:** The gate first fired in run_113 (18 blocks, all AVAX/ADA, slope 0.04837 = 2.4× threshold). Report this run's blocks distinctly: how many distinct pairs were blocked (not just block count — repeated blocks of one pair inflate the count). A high block count on a single re-evaluated pair is "1 pair caught N times," not "N pairs caught."

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
coint_stability_slope_exceeded count: [N events, M distinct pairs]
gate fire rate (session): [blocked / evaluated]
gate_inactivity_trigger_status: MONITORING / FIRED
next step: [if count < 20: "run [N+1] with frozen configuration"; if count ≥ 20: "20-trade Structural Review"]
```

`trades_since_experiment_start` is the window-completion counter. `evaluated_trade_count` is the real experimental N — the number of trades on which Patch 7 could actually have acted. If `evaluated_trade_count` is tracking far below `trades_since_experiment_start`, the window is underpowered and the structural review must state this explicitly rather than treating 20 trades as the sample size.

**slope_exceeded resolution criterion (RESOLVED — no longer pending):**
The gate fired in run_113 (18 blocks, AVAX/ADA, slope 0.04837). The "slope_exceeded = 0 after 6 evaluated trades → loosen slope_max to 0.030" calibration trigger is **void** — the precondition (sustained 0% fire rate) did not occur. Current fire rate (run_113: 6.9%) is below the 15% loosen-threshold, so slope_max remains 0.020. Continue reporting fire rate each run; if it climbs above 60% it would trigger the tighten rule (0.020 → 0.012), but no adjustment is made mid-window — only at the structural review.

No recommendations. No "next priority" lists. If trades_since_experiment_start is still below 20 and the gate-inactivity trigger has not fired, the next action is the next run with frozen configuration.

---

## Section 8 — Forbidden Inferences (Audit Hygiene)

The audit must NOT contain:

- "Patch 7 is working / not working" based on fire count alone
- "the gate is effective / ineffective" without reference to watch-time distribution and slope-vs-outcome data
- "coint-failure rate improved / didn't improve" (requires 20-trade window split by gate status)
- "the premise is confirmed / refuted" based on fewer than ~5 evaluated coint-failures (record the direction, don't conclude)
- "short watch times are a problem" as a conclusion (it's an observation, reported in Section 4C)
- any recommendation to adjust `slope_max`, `window`, or `min_sample_interval` mid-window
- any narrative framing about the experiment's direction based on early trades

If language resembles the above, flag it and rewrite.

---

## Section 9 — Permitted Observations

The audit MAY contain:

- Factual per-trade gate status and slope reports ("T7 slope 0.013, delta 0.007, coint-failure")
- Factual running tally of watch-time and slope-vs-outcome distributions
- Direct observation of watch-time vs gate-status correlation (no interpretation)
- Direct observation of slope-vs-outcome direction in the 4D table (record which side of the premise the data leans, without concluding)
- Factual coint_stability block count with distinct-pair count and slope values
- Factual reconciliation anomalies, including the meme-token sub-pattern tracker
- Factual circuit-breaker state
- Factual note on whether the run followed a restart and any post-restart buffer-refill effects

---

*Template version: exp_coint_stability_v1 v1.2, updated 2026-05-26.*
*v1.2 changes: Patch 7.2 slope source (trade_closes.csv structured field) replaces rejection-row inference; one-time staleness verification added; post-restart buffer caveat added; slope_exceeded resolution criterion updated to RESOLVED (gate fired run_113); Section 5 reduced to 3-trade check only (2-trade passed); meme-token sub-pattern tracker added to Section 3; slope_exceeded distinct-pair-count clarification added to Section 6.*
*run_105 confirmed 0 trades — window starts at T1=run_106. T1–T4 pre-Patch-7.1, excluded from gate-effectiveness analysis.*
*Structural review must report coint-failure rate split by gate_status and state evaluated_trade_count as the actual experimental N, not trades_since_experiment_start.*
