# Run 115 Post-Run Audit — exp_coint_stability_v1

**Audit template:** exp_coint_stability_v1_per_run_audit.md v1.2
**Run key:** run_115_20260526_154010
**Audit date:** 2026-05-26

---

## Experiment State Block

```
experiment_group: exp_coint_stability_v1
runs_since_experiment_start: 105, 106, 107, 108, 109, 111, 112 (no-trade), 113, 114 (no-trade), 115
trades_since_experiment_start_entering_this_run: 2 (T5, T6)
trades_since_experiment_start_after_this_run: 3 (T7)
trades_remaining_to_action_threshold: 17
patches_active: Patch 4.1, Patch 5, Patch 6, Patch 7 (coint stability entry filter), Patch 7.1 (monitoring-loop buffer population), Patch 7.2 (entry-slope persistence for accepted trades)
experiment_phase: Calibration Window
```

---

## Data Sources

```
Reports/v1/run_115_20260526_154010/
  summary.json
  config_snapshot.json
  trade_closes.csv
  reconciliation_checks.csv
  entry_rejections.csv
  pair_history.csv
bot logs (STRATEGY_TRADE_OPEN slope — Patch 7.2 log path)
```

**Note:** `entry_coint_stability_slope` absent from trade_closes.csv columns — slope obtained from bot log. See Section 4A for details.

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
| Duration | 1,263s (21.1 min) |
| Start / End | 2026-05-26T07:40:11 UTC / 2026-05-26T08:01:14 UTC |
| entry_safety_gate evaluations | 33 |
| Total accepted trades | 1 |
| Total rejected entries | 37 |
| Closed trades | 1 |
| Open trades at run end | 0 |
| Session PnL | −$0.107 |
| Starting equity / Ending equity | $2,657.03 / $2,656.92 |
| Win / Loss / Win rate | 0 / 1 / 0% |
| Avg win / Avg loss | N/A / −$0.107 |
| Avg hold | 14.86 min |
| Pair switches | 0 (single pair BTC/HBAR for full run) |
| Circuit breaker | Not tripped (consecutive losses: 1/3; session loss −$0.107 < $5.00 limit) |

**Note: This run followed a bot restart (run_114 was no-trade). Post-restart buffer caveat applies — see Section 4A.**

---

## Section 2 — Per-Trade Telemetry

### T7 — BTC-USDT-SWAP / HBAR-USDT-SWAP

| Field | Value |
|---|---|
| Side | long BTC / short HBAR (long_negative_short_positive) |
| Entry regime | RANGE |
| Entry strategy | STATARB_MR |
| Entry z-score | −2.2737 |
| Exit z-score | +2.1164 |
| Exit reason | normal |
| Hold duration | 14.86 min |
| Gross MFE | +$0.127 (z at MFE: +1.596 — spread overshot past 0) |
| MAE | −$0.118 (z at MAE: −1.673) |
| Net PnL | −$0.107 |
| Post-entry cointegration | intact (z fully reverted — no cointegration failure) |
| full_tp_touched | True |
| guard_blocked_full_tp_count | 41 |
| partial_exit_before_full_tp | False |
| Outcome | Loss |

**Exit narrative:** z reverted strongly from −2.27 to +2.12, crossing 0 and overshooting past the full_tp zone to the other side. full_tp was blocked 41 times by the profit-lock guard (floor $0.24; MFE peaked at +$0.127, below the activation floor). By the time the guard could allow exit, the z had overshot well past the TP zone and the position reversed. Position-level PnL ≈ −$0.007 (near-breakeven on the spread); the net −$0.107 loss is driven almost entirely by fees + slippage ($0.14 in costs).

**exit_category: normal** — this is the **first non-coint-failure trade in the Patch 7.1 window**.

---

## Section 3 — Reconciliation Telemetry

### T7 — BTC-USDT-SWAP / HBAR-USDT-SWAP

| Field | Value |
|---|---|
| Trade PnL (position) | −$0.0070 |
| Equity delta | −$0.1066 |
| Difference | −$0.0996 |
| Fees | $0.10 |
| Slippage (estimated) | $0.04 |
| Funding | $0.00 |
| Unexplained | +$0.040 |
| large_delta_warning | False |
| large_unexplained_warning | False |
| Result | **PASS** — unexplained +$0.040 < $0.05 threshold |

No anomaly. BTC and HBAR are liquid — no meme-token execution cost pattern.

**Meme-token sub-pattern tracker:** No new occurrence. Cumulative: HMSTR (run_102, −$0.226) + FLOKI (run_111, −$0.093), both permanently graveyarded.

---

## Section 4 — Patch 7 Cointegration Stability Filter — Per-Trade Gate Status

### 4A — Watch-Time and Gate Status (T7)

| Field | Value |
|---|---|
| pair | BTC-USDT-SWAP / HBAR-USDT-SWAP |
| pair_activation_timestamp | 2026-05-26T07:40:15 UTC (startup — only pair this run) |
| entry_timestamp | 2026-05-26T07:46:14 UTC |
| watch_time_before_entry_seconds | 359s |
| watch_time_before_entry_minutes | 5.98 min |
| gate_status | **evaluated** |
| coint_stability_check_evaluated_count | 1 (confirmed from rejection rows at 07:46:04 UTC, immediately before entry) |
| coint_stability_insufficient_history_count | 0 (at entry moment) |
| coint_stability_check_blocked_count | 0 (trade accepted) |
| gate_reached | yes |
| slope at entry | **−7.63e-07 ≈ 0** (from log: STRATEGY_TRADE_OPEN `coint_stability_slope=-0.000001` at 07:46:14 UTC) |
| slope_max threshold | 0.020 |
| delta_from_threshold | **+0.0200** (far below threshold) |
| exit_category | **normal** |

**Post-restart buffer caveat:** Bot restarted before run_115. Buffer `_PAIR_COINT_PVALUE_HISTORY` was empty at startup (07:40:11 UTC). By entry at 07:46:14 UTC (359s = 5.98 min post-restart), monitoring-loop population had filled the buffer to ≥5 samples. Gate was functional at entry — evaluated_count=1 confirmed. This is a borderline watch time for post-restart conditions; it worked correctly.

**Patch 7.2 staleness verification (FIRST T7.2 TRADE — one-time check):**

| Check | Result |
|---|---|
| Slope from rejection row at 07:46:04 | −7.625735e-07 |
| Slope from rejection row at 07:46:09 | −7.625735e-07 |
| Slope from STRATEGY_TRADE_OPEN log at 07:46:14 | −0.000001 (rounds to same value at 6 decimal places) |
| Values consistent? | **YES** |
| Verdict | **STALENESS VERIFIED — PASS** |

The plumbing captured the correct entry-decision slope. No stale value detected. This check can be marked resolved for subsequent runs.

**Patch 7.2 CSV gap — FLAG:** `entry_coint_stability_slope` and `entry_coint_stability_evaluated_count` are absent from trade_closes.csv (32 columns, neither field present). The fields were added to the `trade_close` event payload (Patch 7.2) but the report CSV materializer does not expose them. Slope for T7 was obtained from the STRATEGY_TRADE_OPEN bot log line as a fallback. This gap needs to be fixed in the report generator — trade-record-level slope data should not require log-parsing. The fix is report-layer only and does not affect strategy logic or confound the experiment.

**Distance-from-threshold:** Delta +0.0200 — far below threshold. Exit was normal (not coint-failure). Data point is directionally consistent with the premise (stable/improving slope → non-failure), but a single data point is not sufficient to note a pattern.

### 4B — Session Aggregate (entry_safety_gate rows)

| Metric | Value |
|---|---|
| Total entry_safety_gate rows | 32 |
| evaluated_count ≥ 1 | 7 |
| insufficient_history ≥ 1 | 25 |
| blocked_count ≥ 1 | 0 |
| insuff / (eval + insuff) | 25/32 = **78.1%** |
| Gate fire rate (blocked / evaluated) | 0/7 = **0%** |

Session ratio 78.1% is elevated but explained by post-restart buffer refill: most gate rows in the first ~300s after startup show `insufficient_history=1` because the buffer was still filling. By the time the trade entered (359s watch), the gate had transitioned to `evaluated`. Trade-level gate status for T7 is evaluated.

Cumulative trade-level insuff/(eval+insuff) across Patch 7.1 window (T5–T7): 0/3 = 0%.

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

Patch 7.1 window (T5 onward):
- evaluated: 3
- insufficient_history: 0
- not_reached: 0
- Effectiveness fraction: **3/3 = 100%**

T7 watch time (359s) is the shortest evaluated trade in the window — borderline but functional post-restart.

### 4C-TRIGGER — Gate-Inactivity

```
gate_inactivity_trigger:
  total_closed_trades: 3
  gate_reaching_trades (evaluated + insufficient_history): 3
  evaluated: 3
  insufficient_history: 0
  not_reached: 0
  cumulative_effectiveness_fraction: 3/3 = 100%
  rolling_6_gate_reaching_fraction: N/A (need 6 gate-reaching trades, have 3)
  trigger_status: MONITORING (need 3 more gate-reaching trades)
```

### 4D — Running Slope-vs-Outcome Tally (Evaluated Trades Only)

Population: gate_status=evaluated AND blocked_count=0 AND trade closed.

| Trade # | Run | Pair | Slope at Entry | Delta from Threshold | Exit Category |
|---|---|---|---|---|---|
| T5 | run_111 | FIL/FLOKI | −0.00449 | +0.02449 | coint-failure |
| T6 | run_113 | DOGE/SUI | unavailable (pre-7.2) | unavailable | coint-failure |
| T7 | run_115 | BTC/HBAR | −7.63e-07 ≈ 0 | +0.0200 | **normal** |

coint_stability_slope_exceeded count: **18** (unchanged — 0 blocks this session)

- coint-failure: 2 / normal: 1 / total evaluated: 3
- Both observable slopes (T5, T7) are far below threshold (deltas +0.02449 and +0.0200)
- T5 had far-below slope → coint-failure; T7 had far-below slope → normal exit
- No clustering pattern visible at 3 data points. Record and continue.

**Premise-tracking note:** T7 is the first normal exit. Its slope (≈0, far below threshold) is in the same region as T5 (also far below threshold, coint-failure). The data does not yet show a slope difference between normal and coint-failure exits. This is consistent with early evidence that slope does not strongly predict outcome, but 3 trades (2 with visible slopes) is insufficient to form a direction.

---

## Section 5 — Early-Stop Trigger Check

**Status entering this run:** 2-TRADE CHECK PASSED, 3-TRADE PENDING.

**3-trade check (T5 + T6 + T7):**
- insuff / (evaluated + insuff) = 0/3 = **0%** — not > 0.70 ✓
- evaluated_count ≥ 3 ✓
- **CONTINUE — Section 5 RETIRES**

Gate-inactivity trigger (4C-TRIGGER) is now the sole active stop mechanism for the remainder of the window.

---

## Section 6 — Entry Rejection Distribution

| Reject Type | Count |
|---|---|
| strategy_gate | 5 |
| entry_safety_gate | 32 |
| trade_quality_gate | 0 |
| **Total** | **37** |

entry_safety_gate breakdown:

| Reason | Count |
|---|---|
| advanced_ml_break_risk_high | 30 |
| correlation_component_below_threshold | 2 |
| coint_stability_slope_exceeded | **0** |

No coint_stability blocks this session. Cumulative slope_exceeded: 18 events, 1 distinct pair (AVAX/ADA, run_113 only).

---

## Section 7 — Counter Update and Next Step

```
trades_since_experiment_start: 3
evaluated_trade_count: 3 (T5, T6, T7 all evaluated)
insufficient_history_trade_count: 0
not_reached_trade_count: 0
trades_remaining_to_action_threshold: 17
cumulative PnL (experiment window, T5–T7): −$1.448 (T5 −$0.555, T6 −$0.786, T7 −$0.107)
win rate (experiment window): 0/3 = 0%
coint-exit losses so far: 2 trades, −$1.341 (T5 FIL/FLOKI, T6 DOGE/SUI — T7 was normal exit)
coint_stability_slope_exceeded count: 18 events, 1 distinct pair (AVAX/ADA, unchanged)
gate fire rate (session): 0/7 = 0%
gate_inactivity_trigger_status: MONITORING (need 3 more gate-reaching trades)
Section 5 status: RETIRED — 3-trade check passed
next step: run 116 with frozen configuration
```

**Open follow-up — Patch 7.2 CSV gap:** `entry_coint_stability_slope` missing from trade_closes.csv materialization. Fix required in report generator. Slope currently accessible only via bot log (STRATEGY_TRADE_OPEN). Not blocking the experiment but degrades the structured data path that Patch 7.2 was intended to provide.

---

*Audit completed 2026-05-26. Section 5 retired. Run 116 is next.*
