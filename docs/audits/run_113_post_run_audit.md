# Run 113 Post-Run Audit — exp_coint_stability_v1

**Audit template:** exp_coint_stability_v1_per_run_audit.md v1.1
**Run key:** run_113_20260525_193343
**Audit date:** 2026-05-26

---

## Experiment State Block

```
experiment_group: exp_coint_stability_v1
runs_since_experiment_start: 105, 106, 107, 108, 109, 111, 112 (no-trade), 113
trades_since_experiment_start_entering_this_run: 1 (T5)
trades_since_experiment_start_after_this_run: 2 (T6)
trades_remaining_to_action_threshold: 18
patches_active: Patch 4.1, Patch 5, Patch 6, Patch 7 (coint stability entry filter), Patch 7.1 (monitoring-loop buffer pre-population)
experiment_phase: Calibration Window
```

---

## Data Sources

```
Reports/v1/run_113_20260525_193343/
  summary.json
  config_snapshot.json
  trade_closes.csv
  reconciliation_checks.csv
  entry_rejections.csv
  pair_history.csv
  exit_decision_trace.csv
  strategy_metrics.csv
```

---

## Pre-Audit Config Verification

| Check | Value | Status |
|---|---|---|
| `STATBOT_ENTRY_COINT_STABILITY_ENABLED` | true | PASS |
| `STATBOT_ENTRY_COINT_STABILITY_WINDOW` | 5 | PASS |
| `STATBOT_ENTRY_COINT_STABILITY_SLOPE_MAX` | 0.020 | PASS |
| `STATBOT_ENTRY_COINT_STABILITY_MIN_SAMPLE_INTERVAL_SECONDS` | 60.0 | PASS |
| `STATBOT_FULL_TP_GUARD_MULTIPLIER` | 0.50 | PASS |
| `max_break_risk` | 0.12 | PASS |
| `tradeable_capital_usdt` | 200.0 | PASS |
| ETHFI-USDT-SWAP in graveyard (ttl_days: null) | confirmed | PASS |
| HMSTR-USDT-SWAP in graveyard (ttl_days: null) | confirmed | PASS |
| FLOKI-USDT-SWAP in graveyard (ttl_days: null) | confirmed | PASS |

All frozen variables confirmed unchanged.

---

## Section 1 — Run Summary

| Field | Value |
|---|---|
| Duration | 61,064s (16.96h) |
| Start / End | 2026-05-25T11:33:43 UTC / 2026-05-26T04:31:27 UTC |
| entry_safety_gate evaluations | 268 |
| Total accepted trades | 1 |
| Total rejected entries | 600 |
| Closed trades | 1 |
| Open trades at run end | 0 |
| Session PnL | −$0.786 |
| Starting equity / Ending equity | $2,657.82 / $2,657.03 |
| Win / Loss / Win rate | 0 / 1 / 0% |
| Avg win / Avg loss | N/A / −$0.786 |
| Avg hold duration | 8.5 min |
| Pair switches | 56 |
| Circuit breaker | Not tripped (consecutive losses: 1/3; session loss −$0.786 < $5.00 limit; drawdown −$0.786 < $10.00 limit) |

---

## Section 2 — Per-Trade Telemetry

### T6 — DOGE-USDT-SWAP / SUI-USDT-SWAP

| Field | Value |
|---|---|
| Side | long DOGE / short SUI (long_negative_short_positive) |
| Entry regime | RANGE |
| Entry strategy | STATARB_MR |
| Entry z-score | −2.2100 |
| Exit z-score | −1.6692 |
| Exit reason | cointegration_lost |
| Exit tier | — |
| Hold duration | 8.5 min (510s) |
| Gross MFE | −$0.035 (position never went positive from entry) |
| MAE | −$0.709 |
| Net PnL | −$0.786 |
| z at MFE | −0.709 |
| z at MAE | −2.889 |
| guard_floor_at_MFE | $0.24 |
| full_tp_touched | False |
| partial_exit | False |
| Post-entry cointegration | Lost (cointegration_lost exit) |
| Outcome | Loss |

Note: MFE was negative — the position was immediately adverse from entry and never showed a positive mark-to-market gain. The z-score improved slightly (−2.21 → −1.67) before cointegration was declared lost, but the exit z was still on the wrong side of the entry and the trade closed at a loss.

---

## Section 3 — Reconciliation Telemetry

### T6 — DOGE-USDT-SWAP / SUI-USDT-SWAP

| Field | Value |
|---|---|
| Trade PnL (position-level) | −$0.6756 |
| Equity delta | −$0.7864 |
| Difference | −$0.1108 |
| Fees | $0.10 |
| Slippage (estimated) | $0.04 |
| Funding | $0.00 |
| Unexplained | +$0.029 |
| Unexplained % | 26.3% of difference |
| large_delta_warning | False |
| large_unexplained_warning | False |
| Result | **PASS** |

Unexplained residual $0.029 is below the $0.05 flag threshold. No anomaly. No meme-token execution cost pattern present (DOGE is liquid; residual is within normal range for pre_close_equity_delta basis).

---

## Section 4 — Patch 7 Cointegration Stability Filter — Per-Trade Gate Status

### 4A — Watch-Time and Gate Status (T6)

| Field | Value |
|---|---|
| pair | DOGE-USDT-SWAP / SUI-USDT-SWAP |
| pair_activation_timestamp | 2026-05-26T04:05:31 UTC (pair_history.csv row 57) |
| entry_timestamp | 2026-05-26T04:22:46 UTC |
| watch_time_before_entry_seconds | 1035s |
| watch_time_before_entry_minutes | 17.25 min |
| gate_status | **evaluated** (inferred) |
| coint_stability_check_evaluated_count | unavailable — see data gap note below |
| coint_stability_insufficient_history_count | unavailable |
| coint_stability_check_blocked_count | **0** (confirmed — trade was accepted) |
| gate_reached | yes |
| slope at entry | **unavailable** — see data gap note below |
| slope_max threshold | 0.020 |
| delta_from_threshold | unavailable |
| exit_category | **coint-failure** (cointegration_lost) |

**Data gap — slope unavailable for accepted trade:** DOGE/SUI has zero rows in entry_rejections.csv. The trade was accepted on its first z-signal evaluation — no pre-entry rejection rows were generated. The slope field only appears in entry_gate_component_scores on rejected rows. Gate status is inferred as `evaluated` from: (1) watch time 1035s is well above the 300s minimum for 5 samples at 60s intervals; (2) Patch 7.1 monitoring-loop pre-population is active and confirmed working since run_111. blocked_count=0 is confirmed by the fact that the trade entered. This is a structural data gap in the audit — slope at entry is invisible for any trade that enters on its first z-signal attempt with no prior rejections on the same pair.

**Distance-from-threshold:** Not computable. Gate passed (trade entered), exit was coint-failure. Pattern matches T5 (passed gate → coint-failure) but slope value is unknown.

### 4B — Session Aggregate (entry_safety_gate rows only)

| Metric | Value |
|---|---|
| Total entry_safety_gate rows | 267 |
| Rows with evaluated_count ≥ 1 | 262 |
| Rows with insufficient_history ≥ 1 | 5 |
| Rows with blocked_count ≥ 1 | 18 |
| insuff / (eval + insuff) | 5 / 267 = **1.9%** |
| Gate fire rate (blocked / evaluated) | 18 / 262 = **6.9%** |

**Key finding: Gate fired 18 times this session.** All 18 blocks were on a single pair: AVAX-USDT-SWAP/ADA-USDT-SWAP, slope = 0.04837 (2.4× the 0.020 threshold). This is the first gate fire in the experiment window. slope_exceeded is no longer 0.

Cumulative insuff/(eval+insuff) across Patch 7.1 window (T5–T6 sessions combined): ~1.9%.

### 4C — Watch-Time Distribution Tracker (Cumulative)

| Trade # | Run | Pair | Watch Time (s) | Gate Status |
|---|---|---|---|---|
| T1 | run_106 | LINK/SUI | 22320 (6.2h) | evaluated (pre-7.1, excluded) |
| T2 | run_107 | SUI/AAVE | 85 | insufficient_history (pre-7.1, excluded) |
| T3 | run_108 | ETH/AVAX | 864 (14.4min) | not_reached — RISK_OFF (pre-7.1, excluded) |
| T4 | run_109 | BCH/CRCL | ~1944 (32.4min) | insufficient_history (pre-7.1, excluded) |
| T5 | run_111 | FIL/FLOKI | 878 (14.6min) | **evaluated** |
| T6 | run_113 | DOGE/SUI | 1035 (17.25min) | **evaluated** (inferred) |

Patch 7.1 window (T5 onward):
- evaluated: 2
- insufficient_history: 0
- not_reached: 0
- Effectiveness fraction: **2/2 = 100%**

### 4C-TRIGGER — Gate-Inactivity

```
gate_inactivity_trigger:
  total_closed_trades: 2
  gate_reaching_trades (evaluated + insufficient_history): 2
  evaluated: 2
  insufficient_history: 0
  not_reached: 0
  cumulative_effectiveness_fraction: 2/2 = 100%
  rolling_6_gate_reaching_fraction: N/A (need 6 gate-reaching trades, have 2)
  trigger_status: MONITORING (need 4 more gate-reaching trades)
```

### 4D — Running Slope-vs-Outcome Tally (Evaluated Trades Only)

Population: gate_status=evaluated AND coint_stability_check_blocked_count=0 AND trade closed. Blocked entries go to slope_exceeded count only and are excluded from this table.

| Trade # | Run | Pair | Slope at Entry | Delta from Threshold | Exit Category |
|---|---|---|---|---|---|
| T5 | run_111 | FIL/FLOKI | −0.00449 | +0.02449 | coint-failure |
| T6 | run_113 | DOGE/SUI | unavailable | unavailable | coint-failure |

coint_stability_slope_exceeded count (blocked-entry events): **18**
- Pair: AVAX-USDT-SWAP/ADA-USDT-SWAP
- Slope: 0.04837 (2.4× threshold)
- All 18 blocks in run_113 session

coint-failure count: 2 / evaluated: 2
slope_exceeded count: 18 (first gate fires; criterion void — slope_exceeded is no longer 0)
Gate fire rate (session): 18/262 = 6.9% — below 15% loosen-threshold, above 0%

---

## Section 5 — Early-Stop Trigger Check

**Status entering this run:** PENDING — 2-trade check required 2 Patch 7.1 window trades (had 1).

**2-trade check (T5 + T6):**
- T5: evaluated_count ≥ 1 (confirmed from run_111 audit)
- T6: evaluated (inferred) ≥ 1
- Neither trade has evaluated_count = 0 on both → **CONTINUE**

**3-trade check:** PENDING — requires T7.

---

## Section 6 — Entry Rejection Distribution

| Reject Type | Count |
|---|---|
| strategy_gate | 235 |
| entry_safety_gate | 267 |
| trade_quality_gate | 94 |
| min_capital_unavailable | 4 |
| **Total** | **600** |

entry_safety_gate breakdown:

| Reason | Count |
|---|---|
| advanced_ml_break_risk_high | 156 |
| correlation_component_below_threshold | 66 |
| **coint_stability_slope_high** | **18** |
| cointegration_component_below_threshold | 14 |
| liquidity_at_floor | 13 |

All 18 coint_stability_slope_high blocks: AVAX-USDT-SWAP/ADA-USDT-SWAP, slope = 0.04837.

---

## Section 7 — Counter Update and Next Step

```
trades_since_experiment_start: 2
evaluated_trade_count: 2 (T5 and T6 both evaluated)
insufficient_history_trade_count: 0
not_reached_trade_count: 0
trades_remaining_to_action_threshold: 18
cumulative PnL (experiment window, T5–T6): −$1.341
win rate (experiment window): 0/2 = 0%
coint-exit losses so far: 2 trades, −$1.341 (T5 −$0.555, T6 −$0.786)
coint_stability_slope_exceeded count: 18 events, 1 distinct pair (AVAX/ADA, slope 0.04837)
gate fire rate (run_113 session): 18/262 = 6.9% — below 15% loosen-threshold
gate_inactivity_trigger_status: MONITORING (need 4 more gate-reaching trades)
next step: run 114 with frozen configuration
```

**slope_exceeded=0 resolution criterion:** Void. Gate fired 18 times in run_113 (AVAX/ADA). Fire rate 6.9% is below 15% loosen-threshold — slope_max remains at 0.020. The pre-committed calibration trigger (0.020→0.030) was conditional on fire rate = 0% through 6 evaluated trades; that condition cannot be met.

---

## Section 8 — Forbidden Inferences Check

- No "Patch 7 is working / not working" language present.
- No "gate effective / ineffective" conclusion without watch-time reference.
- No coint-failure rate comparison to baseline (requires 20-trade window).
- No recommendation to adjust slope_max, window, or sample interval mid-window.
- No narrative framing about experiment direction.

---

## Section 9 — Permitted Observations

- T6 watch time 1035s. Gate inferred as evaluated. Slope unavailable — structural data gap for accepted trades with no pre-entry rejections.
- AVAX/ADA blocked 18 times this session (slope 0.04837). This is the first gate fire in the experiment window; slope_exceeded count is now 18.
- T6 reconciliation clean (unexplained +$0.029, PASS).
- 2-trade early-stop check passed: CONTINUE.
- Gate effectiveness fraction: 2/2 = 100% in the Patch 7.1 window.

---

*Audit completed 2026-05-26. Run 114 is active. Next audit at T7.*
