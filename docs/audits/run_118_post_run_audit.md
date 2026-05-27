# Run 118 Post-Run Audit — exp_coint_stability_v1

**Audit template:** exp_coint_stability_v1_per_run_audit.md v1.2
**Run key:** run_118_20260527_031435
**Audit date:** 2026-05-27

---

## Experiment State Block

```
experiment_group: exp_coint_stability_v1
runs_since_experiment_start: 105, 106, 107, 108, 109, 111, 112 (no-trade), 113, 114 (no-trade), 115, 116, 117, 118
trades_since_experiment_start_entering_this_run: 5 (T5–T9)
trades_since_experiment_start_after_this_run: 6 (T10)
trades_remaining_to_action_threshold: 14
patches_active: Patch 4.1, Patch 5, Patch 6, Patch 7 (coint stability entry filter), Patch 7.1 (monitoring-loop buffer population), Patch 7.2 (entry-slope persistence for accepted trades)
experiment_phase: Calibration Window
```

---

## Data Sources

```
Reports/v1/run_118_20260527_031435/
  summary.json
  config_snapshot.json
  trade_closes.csv
  reconciliation_checks.csv
  risk_alerts.csv
  entry_rejections.csv
  pair_history.csv
bot logs (run_118_20260527_031435)
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
| Duration | 23,995s (6.67 h) |
| Start / End | 2026-05-26T19:14:35 UTC / 2026-05-27T01:54:30 UTC |
| entry_safety_gate evaluations | 88 |
| Total accepted trades | 1 |
| Total rejected entries | 383 |
| Closed trades | 1 |
| Open trades at run end | 0 |
| Session PnL | −$0.120 |
| Starting equity / Ending equity | $2,656.78 / $2,656.66 |
| Win / Loss / Win rate | 0 / 1 / 0% |
| Avg hold | 17.1 min |
| Pair switches | 19 (20 pairs total) |
| Circuit breaker | Not tripped (consecutive losses: 1/3; session loss −$0.120 < $5.00 limit) |

**Run context — high pair churn:** 19 switches across 20 pairs in 6.67h (avg ~20 min per pair). Most pairs exited on cointegration health failures (cointegration_lost, cointegration_watch_timeout, pair_universe_pruned) before a trade could form. This is the most chaotic run in the experiment window; the pair universe was poor quality throughout. Notable pairs by duration:

| Pair | Duration | Exit reason |
|---|---|---|
| LINEA/ZRO (pair 1 — carryover from run_117) | 53 min | startup_complete |
| HBAR/XRP (pair 4) | 52 min | cointegration_watch_timeout |
| BCH/BTC (pair 6) | 38 min | pair_universe_pruned |
| AVAX/HBAR (pair 10) | 57 min | cointegration_lost |
| AVAX/ETC (pair 17) | 59 min | cointegration_lost |
| FIL/ICP (pair 20 — **T10 traded here**) | 20 min | cointegration_lost (at run end) |

All other 14 pairs lasted < 12 minutes. T10 formed on the 20th and final pair, 2.8 min after activation.

**Alert:** 1 `reconciliation_warning` event fired (FIL/ICP close, large_delta_warning + large_unexplained_warning). See Section 3.

---

## Section 2 — Per-Trade Telemetry

### T10 — FIL-USDT-SWAP / ICP-USDT-SWAP

| Field | Value |
|---|---|
| Side | long FIL / short ICP (long_positive_short_negative) |
| Entry regime | RANGE |
| Entry strategy | STATARB_MR |
| Entry z-score | +2.063 |
| Exit z-score | −2.056 |
| Exit reason | normal |
| Hold duration | 17.1 min (01:37:14 → 01:54:22 UTC) |
| Gross MFE | +$0.274 at z=−2.056 (at exit — MFE was the exit point) |
| MAE | −$0.767 at z=+1.908 |
| Net PnL | −$0.120 (equity-based; position PnL = +$0.274 — see Section 3) |
| Post-entry cointegration | intact (exit_reason=normal; z completed full reversal and overshoot from +2.063 to −2.056) |
| full_tp_touched | True |
| guard_blocked_full_tp_count | 35 |
| partial_exit_before_full_tp | False |
| Outcome | Loss |

**Exit narrative:** z entered at +2.063 (long FIL, short ICP). z reverted through the exit zone and full_tp zone, overshooting to −2.056 — a complete 4.1-unit swing. The full_tp guard blocked 35 times (position PnL was below the guard floor of $0.24 during the traversal through the full_tp zone). MFE of +$0.274 was reached at exit (z=−2.056), where position PnL finally crossed the guard floor and the exit triggered via the normal MR path. Despite position PnL of +$0.274, real costs (~$0.394 total) produced the equity loss of −$0.120.

**Fourth consecutive normal exit** (T7, T8, T9, T10 all normal exits). The pattern of "cointegration holds, spread reverts fully, loss on costs" continues. T10 is the strongest individual illustration: z completed a full reversal and 4.1-unit swing, position made +$0.274, but equity still lost −$0.120.

**MAE note:** MAE of −$0.767 at z=+1.908. For a long_positive trade entered at z=+2.063, the adverse direction is z moving more positive (spread widening). The z=+1.908 MAE is slightly favorable from entry, suggesting the equity trough at that point may reflect mark-to-market timing or z oscillation during the initial hold rather than a direct adverse z move.

---

## Section 3 — Reconciliation Telemetry

### T10 — FIL-USDT-SWAP / ICP-USDT-SWAP

| Field | Value |
|---|---|
| Trade PnL (position) | +$0.274 |
| Equity delta | −$0.120 |
| Difference | −$0.394 |
| Fees | $0.10 |
| Slippage (estimated) | $0.04 |
| Funding | $0.00 |
| Unexplained | **−$0.255** |
| Unexplained % | 64.5% of equity delta |
| Basis | pre_close_equity_delta |
| large_delta_warning | True |
| large_unexplained_warning | True |
| Result | **FAIL** — unexplained −$0.255 >> $0.15 threshold |

**Reconciliation FAIL — equity is reliable; costs are not.** Basis is `pre_close_equity_delta` (post-close equity available; no retry fallback). Unlike T8 (where the equity number itself was unreliable), T10's equity delta (−$0.120) is the trusted economic outcome. The FAIL means the accounting between position PnL and equity change cannot be explained by modeled costs. The −$0.120 equity loss IS real.

**Real cost estimate:** position_pnl − equity_change = +$0.274 − (−$0.120) = **$0.394 total costs** (vs estimated $0.14, ratio ~2.8×). The unexplained −$0.255 represents costs absorbed into the trade that the flat fee model doesn't capture.

**Included in economic analysis:** T10 PnL of −$0.120 is reliable (equity basis confirmed). T10 contributes to the cumulative economic total, unlike T8. The reconciliation FAIL is flagged for the structural review cost-model analysis but does not make the PnL measurement untrustworthy.

**Liquidity-correlated cost pattern:** FIL (Filecoin) and ICP (Internet Computer) are mid-tier altcoins — not meme tokens, but materially less liquid than top-tier pairs (BTC, ETH, SOL, DOGE). Real costs of $0.394 on a $200 notional pair at mid-tier liquidity strengthens the hypothesis that cost overruns scale with pair illiquidity. Comparison:

| Trade | Pair | Liquidity tier | Unexplained |
|---|---|---|---|
| HMSTR (run_102) | DOGE/HMSTR | Meme (HMSTR) | −$0.226 |
| T5 | FIL/FLOKI | Meme (FLOKI) | −$0.093 |
| T10 | FIL/ICP | Mid-tier (both) | **−$0.255** |
| T9 | LINEA/ZRO | Mid-tier/liquid | +$0.073 |
| T7 | BTC/HBAR | Liquid (BTC) | +$0.040 |

The pattern is not purely meme/non-meme — FIL/ICP produced the largest negative unexplained in the window without a meme token. Consistent with liquidity-dependent bias rather than meme-specific execution cost.

**This is not a new item for graveyarding** — FIL and ICP are individually market-normal pairs. The high real cost is a pair-combination or liquidity-tier phenomenon to be assessed at the structural review via the residual-vs-liquidity analysis (Item 12).

**Meme-token sub-pattern tracker:** No new occurrence. Cumulative: HMSTR (run_102) + FLOKI (run_111), both permanently graveyarded.

---

## Section 4 — Patch 7 Cointegration Stability Filter — Per-Trade Gate Status

### 4A — Watch-Time and Gate Status (T10)

| Field | Value |
|---|---|
| pair | FIL-USDT-SWAP / ICP-USDT-SWAP |
| pair_activation_timestamp | 2026-05-27T01:34:27 UTC (pair_history.csv row 20) |
| entry_timestamp | 2026-05-27T01:37:14 UTC |
| watch_time_before_entry_seconds | **167s** (01:34:27 → 01:37:14) |
| watch_time_before_entry_minutes | **2.8 min** |
| gate_status | **insufficient_history** |
| coint_stability_check_evaluated_count | 0 (from trade_closes.csv — no slope computed) |
| coint_stability_insufficient_history_count | 1 |
| coint_stability_check_blocked_count | 0 |
| gate_reached | yes (gate ran, returned insufficient_history) |
| slope at entry | **unavailable** (buffer < 5 samples at entry) |
| exit_category | normal |

**Insufficient_history explained:** Watch time of 167s with a 60s minimum sample interval allows at most 2 samples before entry. The gate requires ≥5 samples (window=5). Shortfall is fully explained by pair timing: FIL/ICP was the 20th pair in a high-churn run, activated only 2.8 min before the z-signal fired. The gate ran and correctly returned insufficient_history. The trade was allowed through (insufficient_history does not block entry).

**First insufficient_history in Patch 7.1 window:** T5–T9 all showed evaluated gate status. T10 is the first trade in the calibration window where the gate lacked sufficient buffer at entry. Mechanism is identical to pre-7.1 insufficient_history cases (T2, T4) — short watch time on a late-cycle pair. The buffer pre-population (Patch 7.1) works when the pair has been active long enough; it cannot fill a buffer from a 2.8-min window.

**T10 does not contribute to slope-vs-outcome tally.** No slope was computed. Exit category (normal) is recorded but cannot be plotted against entry slope.

### 4B — Session Aggregate (entry_safety_gate rows)

| Metric | Value |
|---|---|
| Total entry_safety_gate rows | 88 |
| evaluated_count ≥ 1 | 87 |
| insufficient_history ≥ 1 | 1 (FIL/ICP at entry — 01:37:14 UTC) |
| blocked_count ≥ 1 | 0 |
| insuff / (eval + insuff) | 1/88 = **1.1%** |
| Gate fire rate (blocked / evaluated) | 0/87 = **0%** |

88 gate evaluations across 20 pairs in 6.67h — largest single-run gate sample in the experiment window. 87 showed evaluated (buffer sufficient), 1 showed insufficient_history (T10 entry, 2.8 min watch). Zero blocks throughout. The gate was consistently functional across all 19 prior pairs despite the high churn.

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
| T9 | run_117 | LINEA/ZRO | 1440 (24 min) | **evaluated** |
| T10 | run_118 | FIL/ICP | **167 (2.8 min)** | **insufficient_history** (first in 7.1 window) |

Patch 7.1 window (T5 onward):
- evaluated: 5 (T5–T9)
- insufficient_history: 1 (T10)
- not_reached: 0
- Effectiveness fraction: **5/6 = 83.3%** (evaluated / gate-reaching)

### 4C-TRIGGER — Gate-Inactivity

```
gate_inactivity_trigger:
  total_closed_trades: 6
  gate_reaching_trades (evaluated + insufficient_history): 6
  evaluated: 5
  insufficient_history: 1 (T10 — 2.8 min watch, pair #20 of 20)
  not_reached: 0
  rolling_6_effectiveness: 5/6 = 83.3% evaluated
  rolling_6_not_reached_fraction: 0/6 = 0%
  trigger_status: CHECK PERFORMED — NOT FIRED
```

**4C-TRIGGER unlocked and checked.** With T10, the rolling-6 gate-reaching threshold is now met. The check looks for gate-inactivity (trades where the gate was never reached — `not_reached`). Result: 0/6 not_reached. The trigger does **not** fire. Gate has been functionally active on all 6 trades. The 1 insufficient_history (T10) reflects watch-time constraint on a late-cycle pair, not a structural gate-reach failure.

4C-TRIGGER status changes from MONITORING to **ACTIVE** (rolling check can now update with each subsequent trade).

### 4D — Running Slope-vs-Outcome Tally (Evaluated Trades Only)

Population: gate_status=evaluated AND blocked_count=0 AND trade closed.

| Trade # | Run | Pair | Slope at Entry | Delta from Threshold | Exit Category |
|---|---|---|---|---|---|
| T5 | run_111 | FIL/FLOKI | −0.00449 | +0.02449 | coint-failure |
| T6 | run_113 | DOGE/SUI | unavailable (pre-7.2) | unavailable | coint-failure |
| T7 | run_115 | BTC/HBAR | −7.63e-07 ≈ 0 | +0.0200 | normal |
| T8 | run_116 | SOL/AVAX | +3.99e-04 | +0.01960 | normal |
| T9 | run_117 | LINEA/ZRO | +2.19e-04 | +0.01978 | normal |
| T10 | run_118 | FIL/ICP | **unavailable (insuff.)** | unavailable | **normal** |

coint_stability_slope_exceeded count: **18** (unchanged)

**T10 does not advance the premise check.** Exit category is normal (no coint-failure), and slope is unavailable (insufficient_history). T10 adds a fourth data point to the normal-exit category but does not provide a slope observation.

**Premise watch condition unchanged:** The deciding data point remains the **next coint-failure's slope.** T5 is the only observable coint-failure slope (far below threshold). T6 slope unavailable. One more coint-failure with a visible slope either firms up the premise-negative lean (far below threshold) or revives the premise (near/above threshold).

---

## Section 5 — Early-Stop Trigger Check

**Status: RETIRED** — 3-trade check passed at T7 (run_115). Gate-inactivity trigger (4C-TRIGGER) is now ACTIVE (rolling-6 check unlocked by T10).

---

## Section 6 — Entry Rejection Distribution

| Reject Type | Count |
|---|---|
| strategy_gate | ~295 |
| entry_safety_gate | 88 |
| **Total** | **383** |

88 entry_safety_gate evaluations. Breakdown by dominant block reason (approximated from 20 pairs):
- advanced_ml_break_risk_high: majority of blocks on mid/thin pairs
- cointegration-related (strategy_gate): most of the 295 strategy_gate rejections (~pairs with invalid coint)
- coint_stability_slope_exceeded: **0** (no coint_stability blocks this session)

383 rejections across a 6.67h chaotic run with 20 pairs — by far the most rejections of any run in the experiment window. Consistent with the high pair churn (most pairs had weak cointegration health and were unable to form entries).

---

## Section 7 — Counter Update and Next Step

```
trades_since_experiment_start: 6
evaluated_trade_count: 5 (T5–T9)
insufficient_history_trade_count: 1 (T10 — watch time 167s, pair #20 of high-churn run)
not_reached_trade_count: 0
trades_remaining_to_action_threshold: 14
cumulative PnL (experiment window, economic analysis): −$1.641 [T5+T6+T7+T9+T10; T8 excluded (PnL unreliable)]
cumulative PnL (experiment window, all trades): −$1.706 (T5 −$0.555, T6 −$0.786, T7 −$0.107, T8 −$0.065 [unreliable], T9 −$0.073, T10 −$0.120)
win rate (experiment window): 0/6 = 0%
coint-exit losses so far: 2 trades, −$1.341 (T5, T6)
normal-exit losses: 4 trades; reliable contributions: T7 −$0.107, T9 −$0.073, T10 −$0.120 = −$0.300 (T8 excluded)
coint_stability_slope_exceeded count: 18 events, 1 distinct pair (AVAX/ADA, unchanged)
gate fire rate: 0% across all 6 trade-level evaluations
gate_inactivity_trigger_status: ACTIVE (rolling-6 check functional; NOT fired — 0/6 not_reached)
Section 5 status: RETIRED
next step: run 119 with frozen configuration
```

**T10 reconciliation note:** T10 is included in economic analysis (basis=pre_close_equity_delta, equity measurement reliable). The reconciliation FAIL (unexplained −$0.255) is a cost-accounting failure, not an equity-measurement failure. Real costs ~$0.394 vs estimated $0.14 on FIL/ICP (mid-tier liquidity pair). Adds to the liquidity-correlated cost bias evidence for structural review Item 12 analysis.

**Cost pattern update (experiment window):**
The T10 unexplained (−$0.255) is the largest magnitude negative residual in the Patch 7.1 window. Combined with T9's positive residual (+$0.073 on liquid LINEA/ZRO), the liquidity pattern is now clearer:

| PnL type | Pairs | Pattern |
|---|---|---|
| Positive residual (model overestimates) | Liquid pairs (ETH/ETC, DOGE/BNB, T9 LINEA/ZRO) | Costs < $0.14 |
| Negative residual (model underestimates) | Meme/thin/mid pairs (HMSTR, FLOKI, T5 FIL/FLOKI, T10 FIL/ICP) | Costs > $0.14 |

T10 extends the negative-residual pattern to a non-meme mid-tier pair. The structural-review first analysis remains: plot residuals against order-book depth at entry (liquidity_checks.csv). If the pattern is liquidity-correlated rather than random, the flat $0.14 cost model is systematically biased and the economic question cannot be answered without fixing the measurement.

**4D watch condition unchanged:** The next coint-failure's slope is still the single deciding data point. T10 is a normal exit with no slope — does not move the premise needle.

---

*Audit completed 2026-05-27. T10 adds a fourth normal-exit loss on costs; FIL/ICP reconciliation FAIL strengthens the liquidity-correlated cost pattern. 4C-TRIGGER now active (not fired). Run 119 is next.*
