# Run 117 Post-Run Audit — exp_coint_stability_v1

**Audit template:** exp_coint_stability_v1_per_run_audit.md v1.2
**Run key:** run_117_20260527_015502
**Audit date:** 2026-05-27

---

## Experiment State Block

```
experiment_group: exp_coint_stability_v1
runs_since_experiment_start: 105, 106, 107, 108, 109, 111, 112 (no-trade), 113, 114 (no-trade), 115, 116, 117
trades_since_experiment_start_entering_this_run: 4 (T5, T6, T7, T8)
trades_since_experiment_start_after_this_run: 5 (T9)
trades_remaining_to_action_threshold: 15
patches_active: Patch 4.1, Patch 5, Patch 6, Patch 7 (coint stability entry filter), Patch 7.1 (monitoring-loop buffer population), Patch 7.2 (entry-slope persistence for accepted trades)
experiment_phase: Calibration Window
```

---

## Data Sources

```
Reports/v1/run_117_20260527_015502/
  summary.json
  config_snapshot.json
  trade_closes.csv
  reconciliation_checks.csv
  entry_rejections.csv
  pair_history.csv
bot logs (run_117_20260527_015502)
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
| ETHFI/HMSTR/FLOKI permanently graveyarded (ttl_days: null) | confirmed | PASS |

All frozen variables confirmed unchanged.

---

## Section 1 — Run Summary

| Field | Value |
|---|---|
| Duration | 4,770s (1.33 h) |
| Start / End | 2026-05-26T17:55:02 UTC / 2026-05-26T19:14:33 UTC |
| entry_safety_gate evaluations | 25 |
| Total accepted trades | 1 |
| Total rejected entries | 38 |
| Closed trades | 1 |
| Open trades at run end | 0 |
| Session PnL | −$0.073 |
| Starting equity / Ending equity | $2,656.86 / $2,656.78 |
| Win / Loss / Win rate | 0 / 1 / 0% |
| Avg hold | 5.24 min |
| Pair switches | 5 (6 pairs total) |
| Circuit breaker | Not tripped (consecutive losses: 1/3; session loss −$0.073 < $5.00 limit) |

**Pair sequence (from pair_history.csv):**

| # | Pair | Activated (UTC) | Duration | Switch reason |
|---|---|---|---|---|
| 1 | SOL/LTC | 17:55:07 | 29.6 min | startup_complete |
| 2 | MASK/XRP | 18:24:46 | 1.2 min | pair_universe_pruned |
| 3 | SOL/HBAR | 18:25:59 | 6.25 min | cointegration_lost |
| 4 | LDO/XRP | 18:32:14 | 7.27 min | cointegration_watch_timeout |
| 5 | OP/PEPE | 18:39:30 | 5.67 min | cointegration_watch_timeout |
| 6 | LINEA/ZRO | 18:45:11 | 29.4 min (to run end) | cointegration_lost (at run end) |

T9 traded on pair 6 (LINEA/ZRO). Pairs 2–5 cycled quickly (all < 8 min) on cointegration health issues with no trades.

---

## Section 2 — Per-Trade Telemetry

### T9 — LINEA-USDT-SWAP / ZRO-USDT-SWAP

| Field | Value |
|---|---|
| Side | long LINEA / short ZRO (long_negative_short_positive) |
| Entry regime | RANGE |
| Entry strategy | STATARB_MR |
| Entry z-score | −2.2437 |
| Exit z-score | +0.7375 |
| Exit reason | normal |
| Hold duration | 5.24 min (19:09:10 → 19:14:25 UTC) |
| Gross MFE | +$0.188 at z=+0.623 |
| MAE | −$0.197 at z=−2.472 |
| Net PnL | −$0.073 (equity-based) |
| Position PnL | −$0.006 (nearly breakeven on position) |
| Post-entry cointegration | intact (exit_reason=normal; z reverted from −2.24 through exit zone to +0.737) |
| full_tp_touched | True |
| guard_blocked_full_tp_count | 12 |
| partial_exit_before_full_tp | False |
| Outcome | Loss |

**Exit narrative:** z entered at −2.244 and reverted fully through the exit threshold (−0.35) and the full_tp zone, overshooting to +0.737. The full_tp exit was blocked 12 times because MFE (+$0.188) never reached the guard floor ($0.24). The position PnL was nearly breakeven (−$0.006) but estimated costs (fees $0.10 + slippage $0.04 = $0.14) produced the equity loss. Final exit at z=+0.737 via normal MR exit path.

**Third consecutive normal exit** (T7: normal, T8: normal, T9: normal). All three lost money on costs with position PnL near breakeven. Pattern consistent with the dual-problem structure: clean reversion but costs exceed spread capture at $200 notional.

**guard_floor note:** Guard floor at MFE = $0.24, consistent with full_tp_guard_multiplier=0.50 and implied min_profit_exit ≈ $0.48. MFE was +$0.188, which is $0.052 below the guard floor. Guard working as designed.

---

## Section 3 — Reconciliation Telemetry

### T9 — LINEA-USDT-SWAP / ZRO-USDT-SWAP

| Field | Value |
|---|---|
| Trade PnL (position) | −$0.006 |
| Equity delta | −$0.073 |
| Difference | −$0.067 |
| Fees | $0.10 |
| Slippage (estimated) | $0.04 |
| Funding | $0.00 |
| Unexplained | **+$0.073** |
| Basis | pre_close_equity_delta |
| large_delta_warning | False |
| large_unexplained_warning | False |
| Result | **PASS** |

**Reconciliation PASS — clean close.** Basis is `pre_close_equity_delta` (post-close equity available; no retry issues — contrast with T8's `position_pnl` fallback). Fees and slippage captured normally.

**Positive unexplained (+$0.073):** The model estimated $0.14 in costs (fees+slippage), but the actual costs embedded in the equity delta were ~$0.067. Model overestimated costs by +$0.073. This is the "positive unexplained" pattern consistent with Item 9 (positive residuals on prior trades: ETH/ETC +$0.145, DOGE/BNB +$0.078). The standard $0.14 flat cost model appears to overestimate on some pairs. Below the $0.15 unexplained threshold — no flag required.

**Meme-token sub-pattern tracker:** No new occurrence. Cumulative: HMSTR (run_102) + FLOKI (run_111), both permanently graveyarded. T9 is LINEA/ZRO — liquid, standard pair.

---

## Section 4 — Patch 7 Cointegration Stability Filter — Per-Trade Gate Status

### 4A — Watch-Time and Gate Status (T9)

| Field | Value |
|---|---|
| pair | LINEA-USDT-SWAP / ZRO-USDT-SWAP |
| pair_activation_timestamp | 2026-05-26T18:45:10 UTC (from pair_history.csv row 6) |
| entry_timestamp | 2026-05-26T19:09:10 UTC |
| watch_time_before_entry_seconds | **1,440s** (18:45:10 → 19:09:10) |
| watch_time_before_entry_minutes | **24 min** |
| gate_status | **evaluated** |
| coint_stability_check_evaluated_count | 1 (from trade_closes.csv) |
| coint_stability_insufficient_history_count | 0 |
| coint_stability_check_blocked_count | 0 |
| gate_reached | yes |
| slope at entry | **+2.19e-04 = +0.000219** (from trade_closes.csv `entry_coint_stability_slope`) |
| slope_max threshold | 0.020 |
| delta_from_threshold | **+0.01978** (far below threshold) |
| exit_category | **normal** |

**Watch-time note:** 24 min (1,440s) is the longest monitored watch time in the evaluated window (T5: 878s, T6: 1035s, T7: 359s, T8: 267s, T9: 1,440s). Buffer would have ~24 samples by entry (well over window=5). Slope computed on the most recent 5 of those samples. The long watch time provides the most stable slope estimate of any trade in the experiment window.

**Distance-from-threshold:** Delta +0.01978 — far below threshold, same region as T7 (+0.0200) and T8 (+0.01960). LINEA/ZRO is cointegration-stable.

### 4B — Session Aggregate (entry_safety_gate rows)

| Metric | Value |
|---|---|
| Total entry_safety_gate rows | 25 |
| evaluated_count ≥ 1 | 25 (all) |
| insufficient_history ≥ 1 | 0 |
| blocked_count ≥ 1 | 0 |
| insuff / (eval + insuff) | 0/25 = **0%** |
| Gate fire rate (blocked / evaluated) | 0/25 = **0%** |

Zero insufficient_history across all 25 gate evaluations this session. Even short-lived pairs (MASK/XRP at 1.2 min) showed evaluated rather than insufficient_history — indicating the buffer either carried over from prior monitoring or was pre-populated quickly. No coint_stability blocks.

All slopes in the rejection rows:
- SOL/LTC: range −6.43e-05 to −3.61e-03 (all negative, trending toward cointegration improvement)
- LINEA/ZRO: +2.23e-04 (slightly positive but far below threshold)

### 4C — Watch-Time Distribution Tracker (Cumulative)

| Trade # | Run | Pair | Watch Time (s) | Gate Status |
|---|---|---|---|---|
| T1 | run_106 | LINK/SUI | 22320 (6.2h) | evaluated (pre-7.1, excluded) |
| T2 | run_107 | SUI/AAVE | 85 | insufficient_history (pre-7.1, excluded) |
| T3 | run_108 | ETH/AVAX | 864 (14.4min) | not_reached — RISK_OFF (pre-7.1, excluded) |
| T4 | run_109 | BCH/CRCL | 1944 (32.4min) | insufficient_history (pre-7.1, excluded) |
| T5 | run_111 | FIL/FLOKI | 878 (14.6min) | **evaluated** |
| T6 | run_113 | DOGE/SUI | 1035 (17.25min) | **evaluated** |
| T7 | run_115 | BTC/HBAR | 359 (5.98min) | **evaluated** |
| T8 | run_116 | SOL/AVAX | 267 (4.45min) | **evaluated** |
| T9 | run_117 | LINEA/ZRO | **1,440 (24 min)** | **evaluated** |

Patch 7.1 window (T5 onward):
- evaluated: 5
- insufficient_history: 0
- not_reached: 0
- Effectiveness fraction: **5/5 = 100%**

### 4C-TRIGGER — Gate-Inactivity

```
gate_inactivity_trigger:
  total_closed_trades: 5
  gate_reaching_trades (evaluated + insufficient_history): 5
  evaluated: 5
  insufficient_history: 0
  not_reached: 0
  cumulative_effectiveness_fraction: 5/5 = 100%
  rolling_6_gate_reaching_fraction: N/A (need 6 gate-reaching trades, have 5)
  trigger_status: MONITORING (need 1 more gate-reaching trade)
```

### 4D — Running Slope-vs-Outcome Tally (Evaluated Trades Only)

Population: gate_status=evaluated AND blocked_count=0 AND trade closed.

| Trade # | Run | Pair | Slope at Entry | Delta from Threshold | Exit Category |
|---|---|---|---|---|---|
| T5 | run_111 | FIL/FLOKI | −0.00449 | +0.02449 | coint-failure |
| T6 | run_113 | DOGE/SUI | unavailable (pre-7.2) | unavailable | coint-failure |
| T7 | run_115 | BTC/HBAR | −7.63e-07 ≈ 0 | +0.0200 | normal |
| T8 | run_116 | SOL/AVAX | +3.99e-04 | +0.01960 | normal |
| T9 | run_117 | LINEA/ZRO | **+2.19e-04** | **+0.01978** | **normal** |

coint_stability_slope_exceeded count: **18** (unchanged — 0 blocks this session)

- coint-failure: 2 / normal: 3 / total evaluated: 5
- All four visible slopes (T5, T7, T8, T9) are far below threshold
- T5 = coint-failure (slope −0.00449); T7, T8, T9 = normal exits (slopes near 0)
- Slopes do not separate by outcome. All visible slopes occupy the far-below-threshold region.

**Premise-tracking note:** At 5 trades (2 coint-failure, 3 normal exits), all observable slopes are far below threshold and in the same region. The slope-vs-outcome clustering needed to validate the premise is not emerging. T9 (slope +0.000219, delta +0.01978) adds a third data point in the far-below zone for normal exits, reinforcing the pattern. Record and continue.

---

## Section 5 — Early-Stop Trigger Check

**Status: RETIRED** — 3-trade check passed at T7 (run_115). Gate-inactivity trigger (4C-TRIGGER) is the sole active stop mechanism.

---

## Section 6 — Entry Rejection Distribution

| Reject Type | Count |
|---|---|
| strategy_gate | ~13 |
| entry_safety_gate | ~25 |
| **Total** | **38** |

entry_safety_gate breakdown (all via advanced_ml_break_risk_high, break_risk=0.15):

| Pair | Count | Context |
|---|---|---|
| SOL/LTC (pair 1) | ~9 | TREND regime; break_risk=0.15 throughout |
| LINEA/ZRO (pair 6, pre-entry) | 12 | RANGE regime; break_risk=0.15 persisted until entry |
| Other pairs (2-5) | ~4 | Short-lived pairs; health exits before gate |

strategy_gate rejections: adaptive persistence not satisfied (LTC/SOL showing z-scores in range but persistence logic not clearing), plus 1 cointegration_invalid rejection on PEPE/OP.

coint_stability blocks: **0** this session. Cumulative: 18 events, 1 distinct pair (AVAX/ADA, run_113 only).

**LTC/SOL note:** Pair 1 (SOL/LTC) was active 29.6 min with z-score signals in the entry zone, but TREND regime (break_risk=0.15) blocked all entry_safety_gate evaluations. The strategy router was showing TREND_SPREAD via hysteresis. No trade on this pair — blocked by break_risk before the coint stability gate was ever the gating factor.

---

## Section 7 — Counter Update and Next Step

```
trades_since_experiment_start: 5
evaluated_trade_count: 5 (T5, T6, T7, T8, T9 all evaluated)
insufficient_history_trade_count: 0
not_reached_trade_count: 0
trades_remaining_to_action_threshold: 15
cumulative PnL (experiment window, economic analysis): −$1.521 [T5+T6+T7+T9; T8 excluded (PnL unreliable)]
cumulative PnL (experiment window, all trades): −$1.586 (T5 −$0.555, T6 −$0.786, T7 −$0.107, T8 −$0.065 [unreliable], T9 −$0.073)
win rate (experiment window): 0/5 = 0%
coint-exit losses so far: 2 trades, −$1.341 (T5 FIL/FLOKI, T6 DOGE/SUI — T7, T8, T9 all normal exits)
normal-exit losses: 3 trades, −$0.245 reliable (T7 −$0.107, T9 −$0.073; T8 excluded)
coint_stability_slope_exceeded count: 18 events, 1 distinct pair (AVAX/ADA, unchanged)
gate fire rate (session): 0/25 = 0%
gate_inactivity_trigger_status: MONITORING (need 1 more gate-reaching trade, have 5/6)
Section 5 status: RETIRED
next step: run 118 with frozen configuration
```

**T9 reconciliation status:** PASS. Basis=pre_close_equity_delta, post-close equity available. No exclusion needed. Unexplained +$0.073 is within threshold and consistent with the positive-residual pattern (Item 9). T9 included in all economic analysis.

**Dual-problem structure — clarifying signal:** At 5 trades, the pattern is now:
- T5, T6: coint-failure losses (−$1.341 combined). These are the trades the gate is supposed to prevent. Slopes were below threshold — gate found them acceptable and they failed anyway.
- T7, T8, T9: normal exits, all losses, all driven by costs (position PnL near zero). These are the trades that "passed" cointegration. The gate worked — cointegration held — but the spread capture was insufficient to cover costs at $200 notional.

Neither failure mode is being addressed by the coint stability filter: (a) the coint-failure trades had low slope anyway, so the filter wouldn't have blocked them; (b) the normal-exit trades with coint-intact still lose to costs regardless of entry slope.

---

*Audit completed 2026-05-27. T9 adds a third normal-exit data point with slope far below threshold. Run 118 is next.*
