# Post-Run Audit — run_111_20260524_033754

**Template:** exp_coint_stability_v1 per-run audit v1.1
**Audited:** 2026-05-24

---

## Experiment State Block

```
experiment_group: exp_coint_stability_v1
runs_since_experiment_start: 105, 106, 107, 108, 109, 111
trades_since_experiment_start_entering_this_run: 0  (Patch 7.1 calibration window; T1–T4 excluded)
trades_since_experiment_start_after_this_run: 1     (T5)
trades_remaining_to_action_threshold: 19
patches_active: Patch 4.1, Patch 5, Patch 6, Patch 7 (coint stability entry filter), Patch 7.1
experiment_phase: Calibration Window (Patch 7.1)
```

Note: T1–T4 (runs 106–109) are excluded from gate-effectiveness analysis. Their PnL remains in the equity record. The Patch 7.1 calibration window trade counter starts at T5 = this run.

---

## Pre-Audit Config Verification

- `STATBOT_ENTRY_COINT_STABILITY_ENABLED = true` ✓
- `STATBOT_ENTRY_COINT_STABILITY_WINDOW = 5` ✓
- `STATBOT_ENTRY_COINT_STABILITY_SLOPE_MAX = 0.020` ✓
- `STATBOT_ENTRY_COINT_STABILITY_MIN_SAMPLE_INTERVAL_SECONDS = 60` ✓ (60.0)
- `STATBOT_FULL_TP_GUARD_MULTIPLIER = 0.50` ✓
- ETHFI-USDT-SWAP in graveyard with `ttl_days: null` ✓
- HMSTR-USDT-SWAP in graveyard with `ttl_days: null` ✓
- max_break_risk = 0.12 ✓

All verifications PASS.

---

## Section 1 — Run Summary

- Duration: 38,117s (10.59h)
- Pair switches: 30
- Total entry_safety_gate evaluations: 160 (from entry_rejections.csv)
- Total entry_reject rows: 431 (strategy_gate: 241 + entry_safety_gate: 160 + other: 30)
- Total accepted trades: 1
- Total rejected entries: 431
- Closed trades: 1
- Open trades at run end: 0
- Realized session PnL: −$0.5553
- Win count: 0 / Loss count: 1 / Win rate: 0%
- Avg win: n/a / Avg loss: −$0.555
- Avg hold duration: 5.25 min
- Pair switches: 30
- Circuit breaker: not tripped
- consecutive_loss progression: session=1, persistent (carried forward)

---

## Section 2 — Per-Trade Telemetry

### T5 — FIL-USDT-SWAP / FLOKI-USDT-SWAP

| Field | Value |
|---|---|
| pair | FIL/FLOKI |
| entry regime | RANGE |
| entry z-score | +2.055 |
| exit z-score | +2.150 |
| exit reason | cointegration_lost |
| hold duration | 5.25 min |
| gross MFE (position level) | −$0.082 (spread never reverted to positive PnL; best z reached +1.815) |
| MAE | −$0.323 (z reached +2.264 before coint broke) |
| net PnL | −$0.555 |
| post-entry coint status at close | lost |
| outcome | LOSS |

MFE note: trade entered at z=+2.055 expecting mean reversion. Spread briefly reverted to z=+1.815 (MFE = −$0.082 position-level, still a loss due to costs) then widened to z=+2.264 at MAE. Cointegration broke at exit z=+2.150. Classic coint failure — spread widened post-entry despite improving p-value trend at entry.

---

## Section 3 — Reconciliation Telemetry

| Field | Value |
|---|---|
| pair | FIL/FLOKI |
| gross PnL (position-level) | −$0.323 |
| equity delta | −$0.555 |
| difference | −$0.233 |
| fees (estimated) | $0.100 |
| slippage (estimated) | $0.040 |
| funding | $0.000 |
| unexplained residual | −$0.093 |
| pass_fail | pass (bot threshold $0.15; audit threshold $0.05) |

**FLAG: unexplained residual −$0.093 exceeds audit threshold ($0.05). No restart scenario active.**

Context: FLOKI-USDT-SWAP is a meme token. This is the same direction and category of anomaly as run_102 HMSTR-USDT-SWAP (−$0.226 unexplained, subsequently graveyarded). FLOKI anomaly is less severe ($0.093 vs $0.226) and is a single occurrence — insufficient for graveyard under the pattern-based standard. Flag as Item 12 candidate (execution cost model) and as a potential future graveyard candidate if recurrence observed. Do not action this run.

---

## Section 4 — Patch 7 Cointegration Stability Filter

### 4A — Watch-Time and Gate Status (T5)

| Field | Value |
|---|---|
| pair | FIL/FLOKI |
| pair_activation_timestamp | 2026-05-24T05:53:08 UTC (pair_history seq 30) |
| entry_timestamp | 2026-05-24T06:07:46 UTC |
| watch_time_before_entry_seconds | 878s |
| watch_time_before_entry_minutes | 14.6 min |
| gate_status | **evaluated** |
| coint_stability_check_evaluated_count | 1 |
| coint_stability_insufficient_history_count | 0 |
| coint_stability_check_blocked_count | 0 |
| gate_reached | yes |
| slope at entry | −0.00449 (improving trend, well below slope_max=0.020) |

**First-run Patch 7.1 validation result: PASS.**

The first gate-reaching entry call in this run (ADA/LINK at 03:47:50 UTC, ~8.5 min after pair activation) showed evaluated_count=1, insufficient_history_count=0. Buffer pre-populated from monitoring loop before first z-signal fired. Patch 7.1 is confirmed working. This resolves the binary that was pending.

T5 (FIL/FLOKI) independently confirms: evaluated_count=1 after 14.6 min of watch. Gate reached the slope check, computed −0.00449 (improving trend), and did not block. The coint stability gate passed this entry correctly — FIL/FLOKI's p-value trend was stable-to-improving at entry. Subsequent cointegration failure reflects post-entry deterioration, not a failure to screen.

### 4B — Session Aggregate (Rejected-Entry Rows)

From entry_rejections.csv (160 entry_safety_gate rows):

- Total `entry_safety_gate` rows: 160
- Rows with `evaluated_count ≥ 1` (gate reached): 160
- Rows with `insufficient_history_count = 1` (buffer too small to compute slope): ~52 (from short-lived pairs; see note)
- Rows where slope was computed (evaluated=1, insufficient=0): ~108
- Aggregate ratio: insufficient / (evaluated + insufficient) ≈ 52 / 160 = 32.5%

Note on the 52 insufficient rows: these are concentrated in short-lived pairs from the 30-pair rotation cycle (e.g., DOGE/LTC at 121s watch, SOL/1INCH at 74s, BCH/FLOKI at 71s, FIL/HOOD at 174s). None of these pairs produced a trade. The insufficient rows are expected behavior — Patch 7.1 cannot pre-populate a buffer in under 5 minutes. They do not indicate a Patch 7.1 malfunction.

Running cumulative ratio (Patch 7.1 window, T5 only, rejected-row basis): 32.5%

### 4C — Watch-Time Distribution Tracker (Cumulative, Patch 7.1 Window)

| Trade # | Run | Pair | Watch Time (s) | Gate Status |
|---|---|---|---|---|
| T5 | run_111 | FIL/FLOKI | 878s (14.6 min) | evaluated |

After this run:
- Count of `evaluated` trades: 1
- Count of `insufficient_history` trades: 0
- Count of `not_reached` trades: 0
- Fraction of gate-reachable trades evaluated: 1 / 1 = 100%

### 4C-TRIGGER — Gate-Inactivity Soft Trigger

```
gate_inactivity_trigger:
  total_closed_trades: 1
  gate_reaching_trades (evaluated + insufficient_history): 1
  evaluated: 1
  insufficient_history: 0
  not_reached: 0
  cumulative_effectiveness_fraction: 1/1 = 100%
  rolling_6_gate_reaching_fraction: N/A (need 6 gate-reaching trades; have 1)
  trigger_status: MONITORING (need 5 more gate-reaching trades)
```

---

## Section 5 — Early-Stop Trigger Check

**Status entering this run:** PENDING (first trade in Patch 7.1 calibration window)

After this run (1 Patch 7.1 window trade): 2-trade check not yet applicable. Still PENDING.

T5 result: evaluated_count=1 → if T6 also shows evaluated_count≥1, 2-trade check will be CONTINUE.

---

## Section 6 — Entry Rejection Distribution

From entry_rejections.csv (431 total rows):

- `strategy_gate`: 241 rows
- `entry_safety_gate`: 160 rows
  - `liquidity_at_floor`: 3 rows (ADA/LINK at 03:47, LINK liquidity too thin)
  - `advanced_ml_break_risk_high`: ~147 rows (FIL/FLOKI break_risk=0.15 > 0.12 before entry, plus other pairs)
  - `coint_stability_slope_exceeded`: 0 rows (gate passed on all evaluated entries)
  - other: ~10 rows
- Other/unclassified: 30 rows
- Total: 431

Break-risk at rejection: values clustered at 0.15 (max observed), with 0.0 on stable pairs. Mean/median data not extracted; distribution is bimodal (0.0 for stable pairs, 0.15 for ML-flagged pairs).

Note on FIL/FLOKI pre-entry sequence: 18+ consecutive rejections for `advanced_ml_break_risk_high` (break_risk=0.15). Break_risk dropped below 0.12 at entry (06:07:46), at which point the entry cleared all gates including coint stability.

---

## Section 7 — Counter Update and Next Step

```
trades_since_experiment_start: 1  (Patch 7.1 calibration window; T5 = first window trade)
evaluated_trade_count: 1          (real experimental N — gate reached AND slope computed)
insufficient_history_trade_count: 0
not_reached_trade_count: 0
trades_remaining_to_action_threshold: 19
cumulative PnL (Patch 7.1 calibration window): −$0.555
win rate (Patch 7.1 calibration window): 0/1 = 0%
coint-exit losses so far: 1 trade (cointegration_lost, position loss −$0.323, equity −$0.555)
gate_inactivity_trigger_status: MONITORING (need 5 more gate-reaching trades)
next step: run_112+ with frozen configuration
```

`evaluated_trade_count` = 1 = `trades_since_experiment_start` = 1. Gate was effective on the first trade (slope computed, did not block). The real experimental N tracks the window counter exactly so far.

Patch 7.1 validation is resolved: evaluated_count≥1 confirmed on first gate-reaching entry in this run. Calibration window is live.

---

## Section 8 — Forbidden Inferences

None present.

---

## Section 9 — Permitted Observations

- T5 gate_status: `evaluated`. FIL/FLOKI had 14.6 min watch time. Buffer population confirmed working under Patch 7.1.
- Coint stability slope at entry: −0.00449 (improving). Gate correctly passed. Cointegration failure occurred post-entry. The gate is designed to reduce, not eliminate, coint failures.
- Reconciliation anomaly: −$0.093 unexplained residual on FLOKI (meme token). Same direction as HMSTR (run_102). Single occurrence; flagged for monitoring.
- Run produced 30 pair switches over 10.59h before a single tradeable entry occurred. ADA/LINK (03:47 UTC) had signals blocked by `liquidity_at_floor` (LINK depth only $40.56). Multiple other pairs rejected by break_risk or insufficient z persistence. The eventual entry came on FIL/FLOKI after break_risk cleared.

---

*Audit completed 2026-05-24. Template: exp_coint_stability_v1 v1.1.*
