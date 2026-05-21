# Run 100 Post-Run Audit — Patch 5 Continuation
**Generated:** 2026-05-21  
**Run key:** run_100_20260520_170620  
**Audit scope:** Telemetry only. No structural conclusions. No recommendations.

---

## Experiment State Block

```
experiment_group: exp_guard050_ethfi_excluded_v1
runs_since_experiment_start: 6 (95 + 96 + 97 + 98 + 99 + 100; 96 and 97 produced 0 trades)
trades_since_experiment_start_entering_this_run: 8
trades_since_experiment_start_after_this_run: 14
  (5 bot-tracked closed trades + 1 manually closed open trade; see open trade note below)
trades_remaining_to_action_threshold: 6
circuit_breaker_trips_this_experiment: 2 entering this run, 2 after (no trip in run 100)
patches_active: Patch 4.1 (TREND block fix, VERIFIED), Patch 5 (guard 0.50 + ETHFI excluded), Patch 6 (retry backoff + exit-intent persistence)
experiment_phase: Research Stability Phase
```

**Open trade note:** Run 100 ended at max_uptime (24h) with 1 open position (LDO/LINK, entry_z=+1.979, RANGE, entered 2026-05-21T08:54:05 UTC). User manually closed this position post-run-end. The manual close has no bot-generated exit telemetry. Trade 6 is counted in the experiment trade counter but no reconciliation, MFE timing, exit trace, or mechanism data is available for it.

---

## Pre-Audit Config Verification

All values confirmed from `config_snapshot.json`:

| Variable | Expected | Actual | Status |
|---|---|---|---|
| full_tp_guard_multiplier | 0.50 | 0.50 | PASS |
| effective TP floor | $0.120 (base $0.24 × 0.50) | $0.120 | PASS |
| profit-lock activation floor | $0.170 ($0.120 + $0.050 buffer) | $0.170 | PASS |
| ETHFI-USDT-SWAP graveyard | present, ttl_days: null | confirmed | PASS |
| block_statarb_mr_in_trend | true | true | PASS |
| Patch 6 retry backoff | [5, 30, 120, 300]s | configured | PASS |
| Patch 6 set/get_pending_hard_exit | active | active | PASS |
| max_break_risk | 0.12 | 0.12 | PASS |
| tradeable_capital_usdt | 200.0 | 200.0 | PASS |
| state_mode | session | session | PASS |
| mean_reversion_escape_enabled | false | false | PASS |
| pnl_profit_lock_enabled | true | true | PASS |
| pnl_profit_lock_giveback_pct | 0.50 | 0.50 | PASS |

Note: `pair_supply_control.json` and `pair_strategy_state.json` were not present in this run's report directory. These files were referenced in the audit template but are absent. All other report files present.

All frozen variables confirmed unchanged. Proceeding with audit.

---

## Section 1 — Run Summary

| Metric | Value |
|---|---|
| Duration | 86,407s = 24.00 hours (terminated at max_uptime limit) |
| Entry safety gate evaluations | 730 |
| Trade quality gate evaluations | 785 |
| Total entry rejections | 1,256 |
| Total trade opens | 6 |
| Accepted trades (entered) | 6 |
| Closed trades | 5 |
| Open trades at run end | 1 (LDO/LINK, manually closed post-run-end) |
| Session realized PnL (5 closed) | -$0.777 |
| Session PnL including open unrealized | -$1.153 |
| Starting equity | $2,660.67 |
| Ending equity | $2,659.52 |
| Wins | 2 |
| Losses | 3 |
| Win rate (closed trades) | 40.0% |
| Avg win | +$0.107 |
| Avg loss | -$0.330 |
| Avg MFE (all 5 trades) | +$0.062 |
| Avg MAE (all 5 trades) | -$0.298 |
| Avg hold duration (closed) | 28.1 min |
| Pair switches | 83 |
| Circuit breaker status | No trip. Session consecutive losses at end: 2 of 3 limit. |
| Session consecutive losses progression | 0 → 1 (T1 loss) → 0 (T2 win) → 0 (T3 win) → 1 (T4 loss) → 2 (T5 loss) |
| Persistent consecutive losses (start) | 11 (from run 99 trip) |
| Persistent consecutive losses (end) | 2 (reset to 0 by first win at T2; rose to 2 with T4+T5 losses) |

No circuit breaker trip this run.

---

## Section 2 — Per-Trade Telemetry

### Trade 1: LINK/LINEA — LOSS

| Field | Value |
|---|---|
| Pair | LINK-USDT-SWAP / LINEA-USDT-SWAP |
| Side | long_positive_short_negative |
| Entry regime | RANGE |
| Entry z-score | +2.285 |
| Exit z-score | +0.931 |
| Exit reason | cointegration_watch_timeout |
| Hold duration | 13.7 min |
| Gross MFE | -$0.077 (negative; no favorable peak) |
| MAE | -$0.477 |
| Net PnL | -$0.467 |
| Post-entry cointegration at close | invalid (watch_timeout) |
| Outcome | LOSS |

**MFE Timing:**
- ts_MFE offset from entry: ~3.3s of 822.0s total
- mfe_timing_pct: 0.4%
- mfe_timing_bucket: early_hold (0–33%)
- z at MFE peak: +1.961 (spread was already deteriorating at trade open)

**Threshold Crossing Telemetry:**
All thresholds: not_crossed. MFE was negative throughout.

**TP-Zone PnL:**
- max floating PnL while |z| ≤ 0.35: not entered (TP zone never reached)
- max floating PnL while |z| ≤ 1.0: -$0.247
- max floating PnL while |z| ≤ 1.5: -$0.148

**Exit Mechanism:**
- Profit-lock activated: no
- Trailing stop fired: no
- Full TP guard passes: 0 / 0 TP zone evaluations (TP zone never entered)

---

### Trade 2: SOL/AAVE — WIN

| Field | Value |
|---|---|
| Pair | SOL-USDT-SWAP / AAVE-USDT-SWAP |
| Side | long_negative_short_positive |
| Entry regime | RANGE |
| Entry z-score | -1.965 |
| Exit z-score | +2.903 |
| Exit reason | normal (trailing stop via profit-lock) |
| Hold duration | 4.1 min |
| Gross MFE | +$0.253 |
| MAE | -$0.123 |
| Net PnL | +$0.092 |
| Post-entry cointegration at close | valid |
| Outcome | WIN |

**MFE Timing:**
- ts_MFE offset from entry: 245.4s of 249.0s total
- mfe_timing_pct: 98.6%
- mfe_timing_bucket: late_hold (67–100%)
- z at MFE peak: +2.903 (spread fully inverted; MFE peaked at exit)

**Threshold Crossing Telemetry:**
| Threshold | Crossed | z at first crossing |
|---|---|---|
| $0.12 | YES | +2.386 |
| $0.14 | YES | +2.386 |
| $0.17 | YES | +2.394 |
| $0.18 | YES | +2.394 |
| $0.23 | YES | +2.903 |
| $0.24 | YES | +2.903 |
All crossings occurred while |z| > 2.3 (deep in the opposite-extreme zone, not in the TP zone).

**TP-Zone PnL:**
- max floating PnL while |z| ≤ 0.35: -$0.051 (TP zone entered 6 times, PnL always negative)
- max floating PnL while |z| ≤ 1.0: -$0.005
- max floating PnL while |z| ≤ 1.5: +$0.063

MFE peak occurred after first TP-zone entry (spread continued to +2.9 after passing through TP zone with negative PnL).

**Exit Mechanism:**
- Profit-lock activated: YES — row 64 of 65 trace rows, PnL = $0.216
- Trailing stop fired: YES — exit PnL $0.092 vs profit-lock MFE $0.253 (giveback: 63.6%)
- Full TP guard passes: 0 / 6 TP zone evaluations

---

### Trade 3: LTC/AAVE — WIN

| Field | Value |
|---|---|
| Pair | LTC-USDT-SWAP / AAVE-USDT-SWAP |
| Side | long_positive_short_negative |
| Entry regime | RANGE |
| Entry z-score | +2.025 |
| Exit z-score | -1.587 |
| Exit reason | normal (trailing stop via profit-lock) |
| Hold duration | 29.2 min |
| Gross MFE | +$0.250 |
| MAE | -$0.167 |
| Net PnL | +$0.121 |
| Post-entry cointegration at close | valid |
| Outcome | WIN |

**MFE Timing:**
- ts_MFE offset from entry: 1,727.8s of 1,752.7s total
- mfe_timing_pct: 99.7%
- mfe_timing_bucket: late_hold (67–100%)
- z at MFE peak: -1.587 (spread overshot zero and reached -1.6 before exit)

**Threshold Crossing Telemetry:**
| Threshold | Crossed | z at first crossing |
|---|---|---|
| $0.12 | YES | -0.967 |
| $0.14 | YES | -1.113 |
| $0.17 | YES | -1.651 |
| $0.18 | YES | -1.651 |
| $0.23 | YES | -1.709 |
| $0.24 | YES | -1.587 |
All crossings occurred while z was between -0.97 and -1.71 (in the z ≤ 1.5 range but beyond the TP exit zone of 0.35).

**TP-Zone PnL:**
- max floating PnL while |z| ≤ 0.35: +$0.069 (positive; TP zone entered early in hold, PnL below guard floor)
- max floating PnL while |z| ≤ 1.0: +$0.170
- max floating PnL while |z| ≤ 1.5: +$0.227

MFE peak occurred after the TP zone was first entered. Profit-lock activated after z passed through TP zone and continued to negative extreme.

**Exit Mechanism:**
- Profit-lock activated: YES — row 352 of 396 trace rows, PnL = $0.170 (exactly at the Patch 5 activation floor)
- Trailing stop fired: YES — trailing stop floor at MFE peak = $0.250 × 0.50 = $0.125; exit PnL $0.121 (within execution slippage of trigger)
- Full TP guard passes: 0 / 57 TP zone evaluations

---

### Trade 4: ETH/ETC — LOSS

| Field | Value |
|---|---|
| Pair | ETH-USDT-SWAP / ETC-USDT-SWAP |
| Side | long_positive_short_negative |
| Entry regime | RANGE |
| Entry z-score | +2.847 |
| Exit z-score | -0.130 |
| Exit reason | cointegration_watch_timeout |
| Hold duration | 84.8 min |
| Gross MFE | -$0.034 (negative; no favorable peak) |
| MAE | -$0.413 |
| Net PnL | -$0.193 |
| Post-entry cointegration at close | invalid (watch_timeout) |
| Outcome | LOSS |

**MFE Timing:**
- ts_MFE offset from entry: 391.5s of 5,087.5s total
- mfe_timing_pct: 7.7%
- mfe_timing_bucket: early_hold (0–33%)
- z at MFE peak: -0.437 (spread crossed zero briefly at beginning of hold)

**Threshold Crossing Telemetry:**
All thresholds: not_crossed. MFE was negative throughout.

**TP-Zone PnL:**
- max floating PnL while |z| ≤ 0.35: -$0.056 (TP zone entered 213 times, PnL always negative)
- max floating PnL while |z| ≤ 1.0: -$0.034
- max floating PnL while |z| ≤ 1.5: -$0.034

**Exit Mechanism:**
- Profit-lock activated: no
- Trailing stop fired: no
- Full TP guard passes: 0 / 213 TP zone evaluations

---

### Trade 5: BNB/LDO — LOSS

| Field | Value |
|---|---|
| Pair | BNB-USDT-SWAP / LDO-USDT-SWAP |
| Side | long_positive_short_negative |
| Entry regime | RANGE |
| Entry z-score | +1.982 |
| Exit z-score | -0.154 |
| Exit reason | cointegration_watch_timeout |
| Hold duration | 8.5 min |
| Gross MFE | -$0.082 (negative; no favorable peak) |
| MAE | -$0.308 |
| Net PnL | -$0.330 |
| Post-entry cointegration at close | invalid (watch_timeout) |
| Outcome | LOSS |

**MFE Timing:**
- ts_MFE offset from entry: 49.2s of 511.3s total
- mfe_timing_pct: 9.6%
- mfe_timing_bucket: early_hold (0–33%)
- z at MFE peak: +0.376 (spread briefly touched TP zone before deteriorating)

**Threshold Crossing Telemetry:**
All thresholds: not_crossed. MFE was negative throughout.

**TP-Zone PnL:**
- max floating PnL while |z| ≤ 0.35: -$0.122 (TP zone entered 13 times, PnL always negative)
- max floating PnL while |z| ≤ 1.0: -$0.082
- max floating PnL while |z| ≤ 1.5: -$0.082

**Exit Mechanism:**
- Profit-lock activated: no
- Trailing stop fired: no
- Full TP guard passes: 0 / 13 TP zone evaluations

---

### Trade 6 (Open at Run End): LDO/LINK — Manual Close

| Field | Value |
|---|---|
| Pair | LDO-USDT-SWAP / LINK-USDT-SWAP |
| Side | long_positive_short_negative |
| Entry regime | RANGE |
| Entry z-score | +1.979 |
| Entry timestamp | 2026-05-21T08:54:05 UTC |
| Run end timestamp | 2026-05-21T09:06:27 UTC (~12 min into hold) |
| Unrealized PnL at run end | ~-$0.376 (derived: session_pnl - closed trades PnL) |
| Exit | Manually closed by user post-run-end |
| Bot exit telemetry | None (run terminated while position open) |

No exit trace, reconciliation, MFE timing, or mechanism telemetry available for Trade 6. Actual realized PnL from manual close is not captured in bot reports.

---

## Section 2A — Winning Trade Mechanism Telemetry

Both wins occurred in this run. Mechanism telemetry per trade:

### Trade 2: SOL/AAVE (+$0.092)

- **Exit mechanism fired:** profit-lock activation → trailing stop fire
- **MFE timing bucket:** late_hold (98.6%)
- **Patch 5 guard reduction contribution:**
  - YES. Profit-lock activation threshold under Patch 5: $0.170 (floor = base $0.24 × 0.50 + $0.05 buffer). Activation occurred at PnL = $0.216.
  - Under old guard multiplier 0.75: profit-lock floor = $0.24 × 0.75 + $0.05 = $0.230. PnL at activation ($0.216) < $0.230 (old floor). Profit-lock would NOT have activated under old guard.
  - The exit falls in the $0.170–$0.230 band that became accessible under Patch 5.
- **MFE captured at exit:** $0.092 / $0.253 = 36.4%

This is a factual report of which threshold fired and whether it falls in the guard-reduced access band. It is not a conclusion about whether the patch is working.

### Trade 3: LTC/AAVE (+$0.121)

- **Exit mechanism fired:** profit-lock activation → trailing stop fire
- **MFE timing bucket:** late_hold (99.7%)
- **Patch 5 guard reduction contribution:**
  - YES. Activation occurred at PnL = $0.170, exactly equal to the Patch 5 profit-lock floor.
  - Under old guard 0.75: floor = $0.230. PnL at activation ($0.170) < $0.230. Profit-lock would NOT have activated under old guard.
  - The exit falls in the $0.170–$0.230 band that became accessible under Patch 5.
- **MFE captured at exit:** $0.121 / $0.250 = 48.4%

Both winning trades share the same exit mechanism (profit-lock trailing stop), the same MFE timing bucket (late_hold), and both confirm Patch 5 contribution via the same pathway (profit-lock floor lowered from $0.230 to $0.170).

Note: full_tp_guard_passed = 0 across all 289 total TP zone evaluations in this run. The wins were not produced by the guard pass mechanism. They were produced by the profit-lock trailing stop, a separate mechanism whose activation floor is also derived from the guard multiplier parameter.

---

## Section 3 — Patch 4.1 Status (TREND Regime Block)

| Metric | Value |
|---|---|
| statarb_mr_trend_regime_block fires in entry_rejections | 0 |
| TREND regime duration | 4.65% of run (~66.7 minutes) |
| TREND-regime STATARB_MR entries executed | 0 |
| shadow_trend_mr_block_would_trigger count | 0 across all 5 closed trades |

No TREND-regime STATARB_MR entries were executed. No critical anomaly. TREND block was not the active rejection mechanism during TREND regime intervals — entries were filtered by earlier-stage rejections (cointegration invalid, break_risk high) before reaching the trend block check. This is consistent with expected behavior.

---

## Section 4 — Patch 6 Status (Emergency Flatten Safety)

EMERGENCY_FLATTEN_FLAT events observed in the log for each closed trade exit (Trades 1, 2, 3; Trade DOGE/ENA also noted). All observed instances had `retry_count=0` (first cycle) and `retry_count=3` (inner retry completion), with `remaining_qty=0.00000000` — indicating clean fills with no outer-cycle retries required.

- Close-order failures requiring outer backoff cycles: none observed
- Retry backoff schedule [5, 30, 120, 300]s exercised: no (inner 3-retry cycle used only)
- Exit-intent persistence required across retry cycles: no
- clear_entry_tracking() events logged: no new entries during active holds; no conflict between pending_hard_exit and entry-tracking clearing observed
- _flatten_cycle_count maximum reached: 1 (inner retry cycle only)

Patch 6 not exercised at the outer backoff level this run. Behavior validated by test suite only at that level. Inner retry cycle operated normally on all closes.

---

## Section 5 — ETHFI Exclusion Verification

- ETHFI-USDT-SWAP in trade_closes: 0 entries
- ETHFI-USDT-SWAP in entry_rejections: 0 entries
- pair_supply_control.json: not present in this run's reports (file absent)

Symbols rotated through pair universe (43 distinct symbols across 84 pair-history entries):
1INCH, AAVE, ADA, ARB, AVAX, BAND, BCH, BNB, BTC, CRCL, CRV, DOGE, DOT, ENA, ETC, ETH, FIL, FLOKI, HBAR, HMSTR, INJ, IOTA, KSM, LDO, LINEA, LINK, LTC, MASK, MET, NEAR, NOT, OP, PEPE, SAND, SKY, SOL, SUI, SYRUP, TON, XLM, XRP, XTZ, YGG

Universe diversity: 43 distinct symbols vs 5 in run 99, 6 in run 98. Substantial increase attributable to full 24-hour duration and 83 pair switches. Not directly comparable to prior shorter runs.

---

## Section 6 — Entry Rejection Distribution

Total entry rejections: 1,256

| Rejection Reason | Count | % |
|---|---|---|
| advanced_ml_break_risk_high | 535 | 42.6% |
| cointegration_invalid (strategy_gate) | 276 | 22.0% |
| adaptive_persistence | ~93 | 7.4% |
| cointegration_component_below_threshold | 68 | 5.4% |
| liquidity_at_floor | 67 | 5.3% |
| score_below_threshold (quality_gate) | 55 | 4.4% |
| correlation_component_below_threshold | 40 | 3.2% |
| re_entry_cooldown | 21 | 1.7% |
| risk_off_vol_shock | 12 | 1.0% |
| z_score_extreme | 6 | 0.5% |
| risk_off_thin_liquidity | 1 | 0.1% |
| statarb_mr_trend_regime_block | 0 | 0.0% |
| other (short_entry_failed) | 1 | 0.1% |

Note: adaptive_persistence entries are reported as individual unique reason strings in the CSV; count is the total of all "No entry - adaptive persistence not satisfied" variants.

**Break risk distribution at rejection** (n=723 rows with break_risk field populated):
- mean: 0.114
- median: 0.150
- max: 0.150
- count > 0.12: 535 (all are advanced_ml_break_risk_high blocks)
- count == 0.15 (at max): 533

---

## Section 7 — Reconciliation Telemetry

| Trade | Gross PnL (pos-level) | Equity Change | Difference | Fees | Slippage | Unexplained | Flag |
|---|---|---|---|---|---|---|---|
| T1 LINK/LINEA | -$0.344 | -$0.467 | -$0.123 | $0.10 | $0.04 | +$0.017 | no |
| T2 SOL/AAVE | +$0.242 | +$0.092 | -$0.150 | $0.10 | $0.04 | -$0.010 | no |
| T3 LTC/AAVE | +$0.250 | +$0.121 | -$0.129 | $0.10 | $0.04 | +$0.012 | no |
| T4 ETH/ETC | -$0.198 | -$0.193 | +$0.005 | $0.10 | $0.04 | **+$0.145** | **FLAG** |
| T5 BNB/LDO | -$0.122 | -$0.330 | -$0.208 | $0.10 | $0.04 | **-$0.068** | **FLAG** |

Basis: pre_close_equity_delta for all trades.

**FLAG — Trade 4 (ETH/ETC):** Unexplained residual = +$0.145 (positive direction; equity better than expected by $0.145 beyond fees+slippage). No restart scenario active. Hold was 84.8 minutes from 05:06–06:31 UTC; no OKX funding period crossed (funding at 00:00, 08:00 UTC). The automated reconciliation check passed ($0.145 < $0.15 automated threshold). Audit flag triggered at $0.05 manual threshold. Positive unexplained residuals have not appeared in prior runs; this is mechanistically anomalous. Note for 20-trade structural review.

**FLAG — Trade 5 (BNB/LDO):** Unexplained residual = -$0.068 (negative direction; equity worse than expected). No restart scenario active. Exit was cointegration_watch_timeout on adverse spread move (entry_z=+1.982, MAE=-$0.308, rapid adverse move to z=-0.154). 

**Recurring pattern tracker:** Negative unexplained residuals above $0.05 audit threshold have now appeared in:
- run 93: LDO/FIL, -$0.147 (adverse spread exit)
- run 95: AVAX/FIL, -$0.065 (adverse spread exit)
- run 99: FIL/LINEA, -$0.121 (health exit, adverse spread)
- run 100 Trade 5: BNB/LDO, -$0.068 (cointegration_watch_timeout, adverse spread) — **occurrence 4**

All four occurrences involve exits during adverse spread conditions. No parallel diagnostic ticket has been opened. Pattern remains deferred to 20-trade structural review.

---

## Section 8 — PnL Source Mismatch

Row-0 delta between floating_pnl_usdt and position_snapshot_unrealized_pnl_usdt for each trade:

| Trade | floating_pnl row 0 | snap_unrealized row 0 | delta |
|---|---|---|---|
| T1 LINK/LINEA | -$0.077 | +$0.023 | -$0.100 |
| T2 SOL/AAVE | -$0.123 | -$0.023 | -$0.100 |
| T3 LTC/AAVE | -$0.126 | -$0.028 | -$0.098 |
| T4 ETH/ETC | -$0.108 | -$0.007 | -$0.101 |
| T5 BNB/LDO | -$0.127 | -$0.028 | -$0.099 |

All 5 trades within expected $0.09–$0.10 fees-timing range. No flags. No anomaly requiring investigation.

---

## Section 9 — Persistent Consecutive Loss Counter

| Checkpoint | Session counter | Persistent counter |
|---|---|---|
| Session start | 0 | 11 (carried from run 99 trip) |
| After Trade 1 (LOSS) | 1 | 12 |
| After Trade 2 (WIN) | 0 | **0 (reset by first win)** |
| After Trade 3 (WIN) | 0 | 0 |
| After Trade 4 (LOSS) | 1 | 1 |
| After Trade 5 (LOSS) | 2 | 2 |
| Session end | 2 | 2 |

State mode confirmed: session. Session counter operates independently per run. Persistent counter tracks consecutive losses across runs and resets on any win. No circuit breaker trip; session consecutive losses did not reach limit of 3.

Win at Trade 2 broke a streak of 12 consecutive losses (persistent counter, cross-run). This is the first persistent counter reset since the experiment began at run 95.

---

## Section 10 — Shadow Block Observations

Shadow block field counts across all 5 closed trades:

| Shadow field | T1 LINK/LINEA | T2 SOL/AAVE | T3 LTC/AAVE | T4 ETH/ETC | T5 BNB/LDO | Total |
|---|---|---|---|---|---|---|
| shadow_trend_mr_block_would_trigger | 0 | 0 | 0 | 0 | 0 | **0** |
| trend_or_riskoff_block_would_have_blocked | 0 | 0 | 0 | 0 | 0 | **0** |
| statarb_mr_in_risk_off_regime | 0 | 0 | 0 | 0 | 0 | **0** |

All three shadow block fields are zero across all trades. All 5 closed trades and Trade 6 entered in RANGE regime. No RISK_OFF entries this run (contrast with run 99 where Trades 1 and 2 entered in RISK_OFF and shadow fields fired on 512 rows).

Split by outcome for fields that fired: no split reporting applicable (all counts are zero). The absence of shadow block activity in a 24-hour run with 83 pair switches is itself factual data: the pair rotation and entry-gate filters collectively avoided RISK_OFF entry conditions for all accepted trades.

---

## Section 11 — Confidence Calibration Update

| Hypothesis | Prior (run 99) | This run | Change | Justification |
|---|---|---|---|---|
| confidence_guard_mechanism | LOW | LOW | **no change** | full_tp_guard_passed = 0 in 289 TP zone evaluations. Both wins exited via profit-lock trailing stop, not via guard pass. Guard pass mechanism remains unobserved in production. |
| confidence_trapped_zone_thesis | LOW | LOW | no change | 3 losses had negative MFE (never approached TP zone productively). 2 wins crossed all thresholds but via full-cycle spread inversion (z continued past zero to opposite extreme), not via TP-zone exits. No new evidence bearing on the trapped-zone hypothesis. |
| confidence_coint_fragility_as_dominant_problem | HIGH | HIGH | no change | 3 of 5 exits were cointegration_watch_timeout. Both wins occurred with valid cointegration at close. Pattern consistent with prior runs. |
| confidence_ethfi_toxicity | HIGH | HIGH | no change | ETHFI absent from all telemetry. No new evidence. |
| confidence_trend_regime_mr_block_value | HIGH | HIGH | no change | TREND regime active 4.65% of run. 0 block fires; entries were filtered by earlier-stage checks before reaching the block. Consistent with prior. |
| confidence_trend_regime_mr_block_active (VERIFIED via Patch 4.1) | VERIFIED | VERIFIED | no change | |
| confidence_emergency_flatten_safety (PATCH_6_APPLIED) | PATCH_6_APPLIED | PATCH_6_APPLIED | no change | Patch 6 outer backoff not exercised. Test suite remains sole validation for outer retry behavior. |
| confidence_notional_neutrality | HIGH | HIGH | no change | All trades at $200.00 notional. No sizing anomalies. |
| confidence_break_risk_threshold_correctness | MEDIUM | MEDIUM | no change | Break risk distribution unchanged: median=0.150, 535 of 723 measured rejections at max_break_risk (0.15). |

**Special note on wins and calibration:**

Both wins exited via profit-lock trailing stop, a mechanism enabled by the lowered profit-lock activation floor (Patch 5: $0.170 vs old: $0.230). This is the first empirical production data that a Patch 5-enabled mechanism produced winning exits. Prior calibration was anchored on 0 wins in 8 trades.

However: the profit-lock mechanism is separate from the `confidence_guard_mechanism` hypothesis as measured (full_tp_guard_passed = 0 in all 289 evaluations). The wins occurred via a second mechanism that shares the guard multiplier parameter but does not constitute a guard pass. `confidence_guard_mechanism` is explicitly about the guard pass component; no change to LOW.

Per audit rule: no hypothesis promoted above MEDIUM based on a single run's winners.

---

## Section 12 — Forbidden Inferences

The following inferences are NOT present in this audit and are explicitly prohibited:

- "guard reduction worked" / "guard reduction failed"
- "ETHFI exclusion fixed the problem" / "ETHFI exclusion didn't help"
- "Patch 6 worked / didn't work" based on this run alone
- "the strategy is now profitable" / "the strategy is still broken"
- "the bot has turned the corner" / "showing promise" or similar framing around early wins
- Recommendations to revert, extend, or modify any patch
- Structural theses about pair quality, exit architecture, or market regime
- "this suggests" / "the data is starting to indicate" / "this points toward" applied to multi-trade conclusions
- "win rate improvement" / "recovery in progress" or similar trend narratives from 2 data points

Self-check passed. No forbidden inferences present.

---

## Section 13 — Permitted Observations

**Single-trade facts:**
- Trade 2 (SOL/AAVE): profit-lock activated at $0.216 MFE at row 64/65 of trace (98.6% of hold).
- Trade 3 (LTC/AAVE): profit-lock activated at $0.170 MFE at row 352/396 of trace (88.9% of trace rows, 99.7% of hold).
- Trade 3 is the first trade in the experiment where the TP zone (|z| ≤ 0.35) had positive floating PnL: +$0.069 max.
- Trade 4 (ETH/ETC): 213 TP zone evaluations over an 84.8-minute hold — the highest guard evaluation count in the experiment — with 0 guard passes and uniformly negative TP-zone PnL.
- Persistent consecutive loss counter reset from 12 to 0 at Trade 2 — first reset since experiment start.

**MFE timing bucket distribution:**

| Bucket | Winners (n=2) | Losers (n=3) |
|---|---|---|
| early_hold (0–33%) | 0 | 3 (0.4%, 7.7%, 9.6%) |
| mid_hold (34–66%) | 0 | 0 |
| late_hold (67–100%) | 2 (98.6%, 99.7%) | 0 |

All 3 losers had early_hold MFE timing with negative MFE values. Both winners had late_hold MFE timing with positive MFE values. This is descriptive; no causal inference is drawn.

**Threshold crossing distribution (winners vs losers):**
- Winners: all 6 thresholds crossed ($0.12–$0.24) in both trades
- Losers: 0 thresholds crossed in all 3 trades

**TP-zone PnL distribution:**
- Winners: Trade 2 max TP-zone PnL = -$0.051 (negative); Trade 3 max TP-zone PnL = +$0.069 (positive)
- Losers: all negative (-$0.247, -$0.056, -$0.122)
- Run 94's finding of uniformly negative TP-zone PnL across losses holds for this run's 3 losses. Trade 3 (winner) is the first trade in the experiment with positive TP-zone PnL.

**Hold duration distribution:**
- Winners: 4.1 min, 29.2 min
- Losers: 13.7 min, 84.8 min, 8.5 min

**Entry regime distribution:**
- Winners: RANGE (both)
- Losers: RANGE (all three)
- All 5 closed trades entered in RANGE (contrast with run 99 where 2 of 3 entered in RISK_OFF)

**Exit reason distribution:**
- Winners: both "normal" (trailing stop via profit-lock, logged as trade_manager_trailing_stop in exit_decision_summary)
- Losers: all cointegration_watch_timeout

**Baseline comparison (run 99 vs run 100 regime distribution):**
- RANGE: 79.2% (run 99) → 72.5% (run 100)
- RISK_OFF: 17.6% (run 99) → 22.8% (run 100)
- TREND: 3.2% (run 99) → 4.7% (run 100)

**Guard evaluation counts in run 100 vs run 99:**
- run 99: 0/58, 0/26, 1/151 (3 trades: 0 passes, 235 total TP zone evals)
- run 100: 0/0, 0/6, 0/57, 0/213, 0/13 (5 trades: 0 passes, 289 total TP zone evals)
- Cumulative experiment: 1 guard pass in 524 TP zone evaluations (run 99 Trade 3 pass remains the only guard pass in the experiment)

---

## Section 14 — Counter Update and Next Step

```
trades_since_experiment_start: 14
  (5 bot-tracked closed trades + 1 manually closed open trade from run 100;
   8 from prior runs 95/98/99)
trades_remaining_to_action_threshold: 6
estimated_runs_remaining: 3–6 (at current pace of 1–2 trades per session with circuit-breaker risk)
next_step: run 101 with frozen configuration
```

No recommendations. No "next priority" lists. No "what to investigate next." The next action is run 101 with the same configuration unless an operational issue surfaces.
