# Run 101 Post-Run Audit — Patch 5 Continuation

**Audit date:** 2026-05-22  
**Run:** run_101_20260521_184708  
**Report source:** Reports/v1/run_101_20260521_184708/

---

## Experiment State Block

```
experiment_group: exp_guard050_ethfi_excluded_v1
runs_since_experiment_start: 8 (95 + 96 + 97 + 98 + 99 + 100 + 101; 96 and 97 produced 0 trades)
trades_since_experiment_start_entering_this_run: 14
trades_since_experiment_start_after_this_run: 19
trades_remaining_to_action_threshold: 1
circuit_breaker_trips_this_experiment: 2 entering this run, 2 after (no trip this run)
patches_active: Patch 4.1 (TREND block fix, VERIFIED), Patch 5 (guard 0.50 + ETHFI excluded), Patch 6 (retry backoff + exit-intent persistence)
experiment_phase: Research Stability Phase
```

19 trades after this run. 1 trade remaining to structural review threshold.

---

## Pre-Audit Config Verification

All the following verified from config_snapshot.json:

| Parameter | Required | Observed | Status |
|---|---|---|---|
| STATBOT_FULL_TP_GUARD_MULTIPLIER | 0.50 | 0.5 | PASS |
| Effective TP floor | $0.120 | 0.24 × 0.50 = $0.120 | PASS |
| Profit-lock activation floor | $0.170 | 0.120 + 0.050 (buffer) = $0.170 | PASS |
| ETHFI-USDT-SWAP in graveyard | ttl_days: null | ttl_days=None, reason=repeated_pair_losses | PASS |
| Patch 4.1 TREND block (block_statarb_mr_in_trend) | true | true | PASS |
| Patch 6 backoff schedule | [5, 30, 120, 300] | Outer cycle backoff implemented | PASS |
| Patch 6 set/get_pending_hard_exit | active | mechanism in production code | PASS |
| max_uptime_hours | 24 | 24 (note: was changed to 0 mid-run; change not applied until restart) | PASS |

**Frozen variable check:** All verified unchanged. state_mode="session" confirmed in risk_circuit_breaker config.

---

## Section 1 — Run Summary

| Field | Value |
|---|---|
| Duration | 86,403.6 seconds (24.0 hours) — ended at max_uptime_hours=24 limit |
| Entry safety gate evaluations | 634 |
| Total entry rejections | 1,070 |
| Total accepted trades | 5 |
| Closed trades | 5 |
| Open trades at run end | 0 |
| Session realized PnL | +$0.2954 |
| Win / Loss / Win rate | 3W / 2L / 60.0% |
| Avg win | +$0.123 |
| Avg loss | -$0.037 |
| Profit factor | 5.0 ($0.370 wins / $0.074 losses) |
| Avg MFE | $0.242 |
| Avg MAE | $0.287 |
| Avg hold duration | 12.49 minutes |
| Pair switches | 82 (83 distinct pair rotations) |
| Circuit breaker | NO TRIP |
| Session consecutive losses at start | 2 (persistent, carried from run 100) |
| Session consecutive losses at end | 2 (reset to 0 by T1 win; rose to 2 via T4+T5 losses) |

---

## Section 2 — Per-Trade Telemetry

### Trade 1 — LINK-USDT-SWAP / ZRO-USDT-SWAP

| Field | Value |
|---|---|
| Pair | LINK / ZRO |
| Entry side | long_negative_short_positive |
| Entry regime | RANGE |
| Entry z-score | −2.122 |
| Exit z-score | +0.905 |
| Exit reason | normal (trade_manager_trailing_stop) |
| Hold duration | 7.4 min |
| Gross MFE | $0.244 |
| MAE | −$0.601 |
| Net PnL | **+$0.072 (WIN)** |
| Cointegration at close | Valid (normal exit) |

**MFE Timing:**
- Timestamp at MFE peak: 1779371218.44 (Unix)
- Elapsed to MFE: 436.2s of 445.0s total hold
- mfe_timing_pct: **98.0% → late_hold**
- z-score at MFE peak: +0.905 (equals exit z — spread continued moving favorably through TP zone and beyond)

**Threshold Crossings:**

| Threshold | Crossed? |
|---|---|
| $0.12 (new effective TP floor) | YES |
| $0.14 (cost breakeven) | YES |
| $0.17 (profit-lock activation floor) | YES |
| $0.18 (old TP floor) | YES |
| $0.23 (old profit-lock activation floor) | YES |
| $0.24 (base guard floor) | YES |

All 6 thresholds crossed.

**TP-Zone PnL:**
- Max PnL while z ≤ 0.35: $0.119
- Max PnL while z ≤ 1.0: $0.244
- Max PnL while z ≤ 1.5: $0.244
- MFE peak relative to TP zone: MFE occurred AFTER passing through TP zone (spread continued past zero to z=+0.905)

**Exit Mechanism:**
- Profit lock activated: YES (1/82 trace rows active — activated at final evaluation row)
- Profit lock selected exit: NO
- Trailing stop fired: YES (at MFE peak)
- Full TP guard passes: 0 of 82 evaluations

---

### Trade 2 — AVAX-USDT-SWAP / LINEA-USDT-SWAP

| Field | Value |
|---|---|
| Pair | AVAX / LINEA |
| Entry side | long_positive_short_negative |
| Entry regime | RANGE |
| Entry z-score | +2.080 |
| Exit z-score | −1.731 |
| Exit reason | normal (trade_manager_trailing_stop) |
| Hold duration | 26.2 min |
| Gross MFE | $0.253 |
| MAE | −$0.199 |
| Net PnL | **+$0.143 (WIN)** |
| Cointegration at close | Valid (normal exit) |

**MFE Timing:**
- Elapsed to MFE: 1,565.1s of 1,571.3s total hold
- mfe_timing_pct: **99.6% → late_hold**
- z-score at MFE peak: −1.731 (equals exit z)

**Threshold Crossings:** All 6 crossed (MFE $0.253 > $0.24 base floor).

**TP-Zone PnL:**
- Max PnL while z ≤ 0.35: −$0.048 (negative — spread passed through TP zone at a loss)
- Max PnL while z ≤ 1.0: $0.041
- Max PnL while z ≤ 1.5: $0.216
- MFE peak relative to TP zone: MFE occurred AFTER passing through TP zone

**Exit Mechanism:**
- Profit lock activated: YES (48/351 trace rows active)
- Profit lock selected exit: NO
- Trailing stop fired: YES (at MFE peak)
- Full TP guard passes: 0 of 351 evaluations

---

### Trade 3 — DOGE-USDT-SWAP / BNB-USDT-SWAP (first)

| Field | Value |
|---|---|
| Pair | DOGE / BNB |
| Entry side | long_positive_short_negative |
| Entry regime | RANGE |
| Entry z-score | +2.104 |
| Exit z-score | −0.771 |
| Exit reason | normal (trade_manager_pnl_profit_lock) |
| Hold duration | 11.6 min |
| Gross MFE | $0.447 |
| MAE | −$0.221 |
| Net PnL | **+$0.155 (WIN)** |
| Cointegration at close | Valid (normal exit) |

**MFE Timing:**
- Elapsed to MFE: 374.6s of 695.3s total hold
- mfe_timing_pct: **53.9% → mid_hold**
- z-score at MFE peak: −1.573

**Threshold Crossings:** All 6 crossed (MFE $0.447 >> $0.24 base floor).

**TP-Zone PnL:**
- Max PnL while z ≤ 0.35: $0.086
- Max PnL while z ≤ 1.0: $0.306
- Max PnL while z ≤ 1.5: $0.402
- MFE peak relative to TP zone: MFE occurred AFTER passing through TP zone

**Exit Mechanism:**
- Profit lock activated: YES (104/159 trace rows active)
- Profit lock selected exit: YES (profit lock fired when PnL declined from $0.447 MFE toward locked floor)
- Trailing stop fired: NO
- Full TP guard passes: 0 of 159 evaluations

---

### Trade 4 — DOGE-USDT-SWAP / BNB-USDT-SWAP (second)

| Field | Value |
|---|---|
| Pair | DOGE / BNB |
| Entry side | long_positive_short_negative |
| Entry regime | RANGE |
| Entry z-score | +1.999 |
| Exit z-score | −1.656 |
| Exit reason | normal (trade_manager_regime_break) |
| Hold duration | 11.1 min |
| Gross MFE | $0.141 |
| MAE | −$0.143 |
| Net PnL | **−$0.014 (LOSS)** |
| Cointegration at close | Unknown (regime_break exit; coint status not separable from available data) |

**MFE Timing:**
- Elapsed to MFE: 548.0s of 666.9s total hold
- mfe_timing_pct: **82.2% → late_hold**
- z-score at MFE peak: −2.050

**Threshold Crossings:**

| Threshold | Crossed? |
|---|---|
| $0.12 (new effective TP floor) | YES |
| $0.14 (cost breakeven) | YES |
| $0.17 (profit-lock activation floor) | NOT CROSSED ($0.141 < $0.170) |
| $0.18 (old TP floor) | NOT CROSSED |
| $0.23 (old profit-lock activation floor) | NOT CROSSED |
| $0.24 (base guard floor) | NOT CROSSED |

2 of 6 thresholds crossed.

**TP-Zone PnL:**
- Max PnL while z ≤ 0.35: −$0.046 (negative — TP zone entered at a loss)
- Max PnL while z ≤ 1.0: $0.034
- Max PnL while z ≤ 1.5: $0.103
- MFE peak relative to TP zone: MFE occurred AFTER passing through TP zone

**Exit Mechanism:**
- Profit lock activated: NO (MFE $0.141 < $0.170 activation floor; should_profit_lock_have_activated = False)
- Trailing stop fired: NO
- Full TP guard passes: 0 of 153 evaluations
- Exit trigger: regime break (trade_manager_regime_break)

---

### Trade 5 — ARB-USDT-SWAP / DOT-USDT-SWAP

| Field | Value |
|---|---|
| Pair | ARB / DOT |
| Entry side | long_negative_short_positive |
| Entry regime | RANGE |
| Entry z-score | −1.954 |
| Exit z-score | −0.123 |
| Exit reason | normal (trade_manager_take_profit) |
| Hold duration | 6.1 min |
| Gross MFE | $0.123 |
| MAE | −$0.272 |
| Net PnL | **−$0.060 (LOSS)** |
| Cointegration at close | Valid (normal exit) |

**MFE Timing:**
- Elapsed to MFE: 359.3s of 368.8s total hold
- mfe_timing_pct: **97.5% → late_hold**
- z-score at MFE peak: −0.358 (within TP zone)

**Threshold Crossings:**

| Threshold | Crossed? |
|---|---|
| $0.12 (new effective TP floor) | YES |
| $0.14 (cost breakeven) | NOT CROSSED ($0.123 < $0.140) |
| $0.17 (profit-lock activation floor) | NOT CROSSED |
| $0.18 (old TP floor) | NOT CROSSED |
| $0.23 (old profit-lock activation floor) | NOT CROSSED |
| $0.24 (base guard floor) | NOT CROSSED |

1 of 6 thresholds crossed.

**TP-Zone PnL:**
- Max PnL while z ≤ 0.35: $0.123 (equals MFE — peak was IN the TP zone)
- Max PnL while z ≤ 1.0: $0.123
- Max PnL while z ≤ 1.5: $0.123
- MFE peak relative to TP zone: MFE occurred **DURING** TP-zone period (MFE peak z = −0.358, within z ≤ 0.35)

**Exit Mechanism:**
- Profit lock activated: NO (MFE $0.123 < $0.170 activation floor)
- Trailing stop fired: NO
- Full TP guard passes: **1 of 83 evaluations** (first guard pass on a trade with negative final PnL)
- Exit trigger: full TP guard pass at floating PnL ≈ $0.123 gross

**Note on T5 execution gap:** Position snapshot at exit trigger showed gross floating PnL $0.123. Actual equity change = −$0.060. Total execution cost = $0.183 ($0.123 gross − (−$0.060) = $0.183). Standard fee+slippage estimate = $0.140. Unexplained residual = −$0.043 (execution-side; see Section 7). The full TP guard passed the PnL floor check at floating $0.123 > effective floor $0.120; however, the realized fill PnL after execution was negative. Spread movement during close-order execution may account for part of the gap.

---

## Section 2A — Winning Trade Mechanism Telemetry

### T1 — LINK/ZRO (+$0.072), trailing stop

- **Exit mechanism:** trailing stop (profit lock activated at final trace row, locked floor set; trailing stop fired at MFE peak coinciding with exit)
- **MFE timing bucket:** late_hold (98.0%)
- **Patch 5 contribution:** MFE $0.244 exceeds old profit-lock activation floor $0.230. Old guard would also have activated the profit lock. Exit does not fall in the Patch-5-exclusive band ($0.12–$0.18 effective TP / $0.17–$0.23 profit-lock activation). **No: this exit was not blocked under the old 0.75 multiplier.**
- **Gross MFE captured at exit:** 100% of MFE peak ($0.244 gross = MFE; trailing stop fired at peak)
- **Net MFE captured:** $0.072 / $0.244 = 29.5% (fees and slippage consumed 70.5% of gross gain)

### T2 — AVAX/LINEA (+$0.143), trailing stop

- **Exit mechanism:** trailing stop (profit lock activated at row 48/351; locked floor set; trailing stop fired at MFE peak)
- **MFE timing bucket:** late_hold (99.6%)
- **Patch 5 contribution:** MFE $0.253 exceeds old profit-lock activation floor $0.230. Old guard would also have activated. **No: this exit was not blocked under the old 0.75 multiplier.**
- **Gross MFE captured at exit:** 100% ($0.253 gross = MFE)
- **Net MFE captured:** $0.143 / $0.253 = 56.5%

### T3 — DOGE/BNB (+$0.155), profit lock selected

- **Exit mechanism:** profit lock selected exit (lock activated at row 1 of 104 active rows, spread continued to MFE $0.447, profit lock floor tracked at MFE × 0.50; lock fired when PnL fell below floor from peak)
- **MFE timing bucket:** mid_hold (53.9%)
- **Patch 5 contribution:** Profit-lock activation floor under Patch 5 = $0.170 vs old $0.230. MFE $0.447 exceeds both thresholds. Exit gross PnL ≈ $0.216 (from reconciliation position snapshot) is above old TP floor $0.180. Old guard would also have activated the profit lock (when PnL first crossed $0.230) and would likely have produced a similar tracked floor at peak MFE $0.447. **No: this exit does not fall in the Patch-5-exclusive band.**
- **Gross MFE captured at exit:** $0.216 gross / $0.447 MFE = 48.3%
- **Net MFE captured:** $0.155 / $0.447 = 34.7%

**Run 101 winning trade summary:** All 3 winners had MFE peaks above $0.230 (old profit-lock activation floor). None of the 3 exits are attributable exclusively to the Patch 5 guard reduction. This contrasts with run 100, where both wins were in the $0.170–$0.230 band accessible only under Patch 5. T3 is the first win via profit_lock_selected mechanism (run 100 wins were trailing-stop-after-lock). T1 and T2 used the same trailing-stop-after-lock mechanism as run 100.

---

## Section 3 — Patch 4.1 Status (TREND Regime Block)

| Field | Value |
|---|---|
| statarb_mr_trend_regime_block fire count (entry_rejections.csv) | **0** |
| TREND regime duration | 6.75% of run (≈1.62 hours) |
| TREND-regime STATARB_MR entries executed | **0** |
| shadow_trend_mr_block_would_trigger (exit_decision_trace) | **0** |

**No critical anomaly.** 0 TREND-regime STATARB_MR entries executed, which is the expected outcome.

**Explanation for 0 block fires:** All 46 TREND-regime entry rejections were stopped before reaching the Patch 4.1 check. In the safety gate evaluation order, the break_risk check fires before the TREND block check. All TREND-regime pairs in this run had break_risk = 0.15 (> max_break_risk threshold of 0.12), which triggered the "advanced_ml_break_risk_high" rejection before the TREND block was evaluated. Patch 4.1 would fire if a TREND-regime pair had break_risk < 0.12 — that condition did not occur in this run.

Pairs blocked in TREND regime: THETA/BTC (2 entries), LDO/SOL (1 entry), WCT/ACT (38+ entries via break_risk and correlation), DOT/ARB (1 strategy_gate). All rejections were via strategy_gate or entry_safety_gate at break_risk/correlation stage, not statarb_mr_trend_regime_block.

---

## Section 4 — Patch 6 Status (Emergency Flatten Safety)

**Patch 6 not exercised this run. Behavior validated by test suite only.**

No close-order failures encountered. The exit_decision_trace contains no flatten_cycle_count data (field present in schema, no populated values). No pending_hard_exit persistence events were required. No clear_entry_tracking interactions with the hard exit flag were triggered.

All 5 trades closed normally on first attempt.

---

## Section 5 — ETHFI Exclusion Verification

| Check | Result |
|---|---|
| ETHFI in trade_closes | 0 entries — CONFIRMED |
| ETHFI in entry_rejections (any field) | 0 entries — CONFIRMED |
| ETHFI in pair_history | NOT PRESENT — CONFIRMED |
| Graveyard entry | ETHFI-USDT-SWAP, ttl_days=None, reason=repeated_pair_losses |

**Universe in ETHFI's absence:** 49 distinct symbols across 83 pair rotations. Includes: 1INCH, AAVE, ACT, ADA, ALGO, ARB, AUCTION, AVAX, BCH, BNB, BOME, BTC, CFX, CRCL, CRO, CRV, DOGE, DOT, ETC, ETH, FIL, FLOKI, HBAR, HMSTR, ICP, IOTA, JUP, KSM, LDO, LINEA, LINK, LPT, LTC, MASK, MET, MINA, NOT, OP, PEPE, SKY, and more.

**Universe diversity comparison:** 49 symbols in run 101 vs comparison data from prior runs not directly computed here (prior runs not merged in this audit). Universe composition includes several tokens (WCT, ACT, CRCL, BOME, HMSTR) that suggest newer/smaller-cap rotation. No ETHFI appearances across any telemetry source.

---

## Section 6 — Entry Rejection Distribution

| Reject type | Count |
|---|---|
| entry_safety_gate | 629 |
| strategy_gate | 381 |
| trade_quality_gate | 60 |
| **Total** | **1,070** |

**Entry safety gate block reasons:**

| Block reason | Count |
|---|---|
| advanced_ml_break_risk_high | 409 |
| correlation_component_below_threshold | 60 |
| liquidity_at_floor | 55 |
| risk_off_vol_shock | 50 |
| cointegration_component_below_threshold | 45 |
| advanced_ml_trending | 10 |

**Break risk distribution at rejection:**
- Count: 629 sampled
- Mean: 0.1041
- Median: 0.1500
- Max: 0.1500
- Non-zero count: 484 of 629

Break risk distribution is consistent with run 100 (median 0.150 = max_break_risk threshold in both runs). The floor at 0.15 in both the mean and max suggests the break_risk signal frequently saturates at the threshold boundary.

Note: statarb_mr_trend_regime_block = 0 (see Section 3).

---

## Section 7 — Reconciliation Telemetry

| Trade | Gross PnL (position) | Equity Delta | Difference | Fees | Slippage | Unexplained | Flag |
|---|---|---|---|---|---|---|---|
| T1 LINK/ZRO | $0.244 | +$0.072 | −$0.172 | $0.100 | $0.040 | **−$0.033** | No ($0.033 < $0.05) |
| T2 AVAX/LINEA | $0.264 | +$0.143 | −$0.121 | $0.100 | $0.040 | **+$0.019** | No ($0.019 < $0.05) |
| T3 DOGE/BNB | $0.217 | +$0.155 | −$0.062 | $0.100 | $0.040 | **+$0.078** | **YES — see below** |
| T4 DOGE/BNB | $0.114 | −$0.014 | −$0.128 | $0.100 | $0.040 | **+$0.012** | No ($0.012 < $0.05) |
| T5 ARB/DOT | $0.123 | −$0.060 | −$0.183 | $0.100 | $0.040 | **−$0.043** | No ($0.043 < $0.05) |

All reconciliation checks: pass_fail = "pass" (system thresholds at $0.15).

**T3 DOGE/BNB flag:** Unexplained residual = +$0.078 (positive), exceeds $0.05 audit threshold. No pair-switch restart was active during T3 hold. T3 was a continuous hold with DOGE/BNB as the active pair throughout.

**Recurring negative-residual pattern tracker (adverse exits):** 0 new occurrences in run 101. Current count remains **4** (runs 93, 95, 99, 100 Trade 5). Counter at 4; 5th occurrence would trigger dedicated diagnostic ticket.

**Positive residual anomaly tracker:** T3 DOGE/BNB +$0.078 is the **second occurrence** (first was run 100 Trade 4 ETH/ETC +$0.145). Per audit template: **flag as new pattern — do not group with the negative-residual pattern.** Two occurrences are now on record: run 100 T4 ETH/ETC +$0.145, run 101 T3 DOGE/BNB +$0.078. Both are positive unexplained residuals on winning trades with normal exits. No diagnostic ticket threshold has been stated for this pattern; recording occurrence count for structural review.

---

## Section 8 — PnL Source Mismatch

Per diagnostic note 2026-05-20: all early-trace-row deltas (floating_pnl − position_snapshot_unrealized_pnl) are within the expected fees-timing range of $0.09–$0.10.

| Trade | Delta | Assessment |
|---|---|---|
| T1 LINK/ZRO | $0.089 | Within expected fees-timing range |
| T2 AVAX/LINEA | $0.100 | Within expected fees-timing range |
| T3 DOGE/BNB | $0.099 | Within expected fees-timing range |
| T4 DOGE/BNB | $0.099 | Within expected fees-timing range |
| T5 ARB/DOT | $0.100 | Within expected fees-timing range |

All 5 trades within $0.09–$0.10 range. No flags. The pnl_source_mismatch_detected field is True for all trades (consistent with confirmed fees-timing artifact). Maximum delta = $0.100, well below the $0.25 anomaly threshold.

---

## Section 9 — Persistent Consecutive Loss Counter

| Checkpoint | Value |
|---|---|
| Persistent counter at session start (entering run 101) | 2 |
| After T1 LINK/ZRO (WIN) | **Reset to 0** |
| After T2 AVAX/LINEA (WIN) | 0 |
| After T3 DOGE/BNB (WIN) | 0 |
| After T4 DOGE/BNB (LOSS) | 1 |
| After T5 ARB/DOT (LOSS) | **2** |
| Persistent counter at session end | **2** |

- state_mode = "session" confirmed in config_snapshot.json (persistent counter active)
- Session circuit breaker threshold: max_consecutive_losses=3; current counter 2 is one loss from trip threshold
- Run 100 context: persistent counter reset to 0 at Trade 2 (run 100 first win, after 12-loss streak from experiment start). This run starts at 2 (from run 100 T4+T5 losses). T1 win resets to 0 again; T4+T5 losses bring counter back to 2 by run end.

---

## Section 10 — Shadow Block Observations (Deferred Research Tracking)

**shadow_trend_mr_block_would_trigger:** 0 fires across all 828 trace rows. All 5 trades were in RANGE regime during hold; no in-hold TREND-regime events recorded.

**shadow_early_net_profit_capture_would_trigger counts (per trade):**

| Trade | Outcome | Fire count |
|---|---|---|
| T1 LINK/ZRO | WIN | 2 |
| T2 AVAX/LINEA | WIN | 3 |
| T3 DOGE/BNB | WIN | 20 |
| T4 DOGE/BNB | LOSS | 0 |
| T5 ARB/DOT | LOSS | 0 |
| **Total** | — | **25** |

All 25 shadow_early_net_profit_capture fires occurred on winning trades. 0 fires on losing trades.

**shadow_exit_z_1_50_would_trigger counts:**

| Trade | Outcome | Fire count |
|---|---|---|
| T1 LINK/ZRO | WIN | 2 |
| T2 AVAX/LINEA | WIN | 16 |
| T3 DOGE/BNB | WIN | 53 |
| T4 DOGE/BNB | LOSS | 0 |
| T5 ARB/DOT | LOSS | 2 |
| **Total** | — | **73** |

71 fires on winners, 2 fires on losers (T5 — these correspond to the brief period where T5 was in the TP zone at MFE; shadow z_1_50 and actual full TP fired at the same point).

**shadow_exit_z_1_00_would_trigger counts:**

| Trade | Outcome | Fire count |
|---|---|---|
| T1 LINK/ZRO | WIN | 2 |
| T2 AVAX/LINEA | WIN | 0 |
| T3 DOGE/BNB | WIN | 5 |
| T4 DOGE/BNB | LOSS | 0 |
| T5 ARB/DOT | LOSS | 2 |
| **Total** | — | **9** |

7 fires on winners, 2 fires on losers (T5 — same coincidence as z_1_50).

**Deferred observation:** shadow_early_net_profit_capture fired exclusively on winning trades (25/25 fires on winners). The shadow exit at z_1_50 fired predominantly on winners (71 of 73 fires). The 2 loser fires (T5 at z_1_50 and z_1_00) correspond to T5's MFE in the TP zone — the shadow would have captured $0.123 gross, the same level the actual full TP fired at. Note counts without proposing activation. These are deferred research items for the 20-trade structural review. The shadow_early fires exclusively on winners is important data; whether this holds at the structural review sample size is unknown.

---

## Section 11 — Confidence Calibration Update

| Hypothesis | Prior (run 100) | This run | Change | Justification |
|---|---|---|---|---|
| confidence_guard_mechanism | LOW | LOW | **no change** | First full TP guard pass since run 99 T3: T5 ARB/DOT, 1 pass in 83 evaluations, but trade was a LOSS. Guard passes remain 2/all-time on losing trades. No guard pass has produced a winning close. |
| confidence_trapped_zone_thesis | LOW | LOW | no change | 3 winners crossed all 6 thresholds and exited with spread continuing past zero. 1 loser (T4) crossed 2 thresholds but hit regime break. 1 loser (T5) crossed 1 threshold and had MFE in TP zone but net negative after execution costs. No new evidence bearing on whether the TP zone specifically causes exits to fail. |
| confidence_coint_fragility_as_dominant_problem | HIGH | HIGH | no change | 0 cointegration_watch_timeout exits this run (contrast: 3 of 5 in run 100). The absence does not contradict the hypothesis — all 5 trades had holds ≤26 min, consistent with exits occurring before coint failure window. Pair history shows 83 rotations driven by cointegration_lost and cointegration_watch_timeout switches, confirming fragility at the pair-supply level. |
| confidence_ethfi_toxicity | HIGH | HIGH | no change | ETHFI absent from all telemetry. No new evidence. |
| confidence_trend_regime_mr_block_value | HIGH | HIGH | no change | TREND regime 6.75% of run, 0 TREND-regime STATARB_MR executions. All TREND entries blocked by break_risk before reaching TREND block. Consistent with prior runs. |
| confidence_trend_regime_mr_block_active (VERIFIED via Patch 4.1) | VERIFIED | VERIFIED | no change | |
| confidence_emergency_flatten_safety (PATCH_6_APPLIED) | PATCH_6_APPLIED | PATCH_6_APPLIED | no change | Outer backoff not exercised. Test suite remains sole validation. |
| confidence_notional_neutrality | HIGH | HIGH | no change | All 5 trades at $200.00 notional. No sizing anomalies. |
| confidence_break_risk_threshold_correctness | MEDIUM | MEDIUM | no change | Break risk median = 0.150, mean = 0.104, max = 0.150. Distribution nearly identical to run 100. 409 advanced_ml_break_risk_high blocks (largest single rejection category). |

**Special note on wins and calibration:**

Run 101 wins (T1, T2, T3) all had MFE peaks above $0.230 (old profit-lock activation floor). Unlike run 100's wins (which were in the $0.170–$0.230 Patch-5-exclusive band), run 101's wins would have produced profit-lock activations under either guard. This run does not add distinct Patch 5 mechanism evidence of the same type as run 100. Per audit rule: no hypothesis promoted above MEDIUM based on this run alone.

The first run 100 observation that both wins used the profit-lock trailing stop mechanism remains the sole production evidence of the Patch 5 profit-lock pathway. Run 101 adds 3 wins via profit-lock mechanisms but at higher MFE levels that are not Patch-5-exclusive.

---

## Section 12 — Forbidden Inferences

The following inferences are NOT present in this audit and are explicitly prohibited:

- "guard reduction worked" / "guard reduction failed"
- "ETHFI exclusion fixed the problem" / "ETHFI exclusion didn't help"
- "Patch 6 worked / didn't work" based on this run alone
- "the strategy is now profitable" / "the strategy is still broken"
- "the bot has turned the corner" / "the experiment is showing promise" / "recovery in progress" / similar narrative framings around early wins
- "the losing pattern has returned" / "back to normal losses" / similar framings around losses after wins
- recommendations to revert, extend, or stack additional changes
- new structural theses about pair quality, exit architecture, or market regime
- "this suggests," "the data is starting to indicate," "this points toward" applied to multi-trade conclusions

No violations identified.

---

## Section 13 — Permitted Observations

**MFE timing distribution:**

| Bucket | Winners | Losers |
|---|---|---|
| early_hold (0–33%) | 0 | 0 |
| mid_hold (34–66%) | T3 (53.9%) | — |
| late_hold (67–100%) | T1 (98.0%), T2 (99.6%) | T4 (82.2%), T5 (97.5%) |

Run 100 baseline: winners = 100% late_hold; losers = 100% early_hold. Run 101 differs: losers are now late_hold (T4 82.2%, T5 97.5%), not early_hold. This is descriptive reporting only.

**Threshold crossing split:**

| Trade | Outcome | Thresholds crossed |
|---|---|---|
| T1 LINK/ZRO | WIN | 6/6 |
| T2 AVAX/LINEA | WIN | 6/6 |
| T3 DOGE/BNB | WIN | 6/6 |
| T4 DOGE/BNB | LOSS | 2/6 ($0.12, $0.14 only) |
| T5 ARB/DOT | LOSS | 1/6 ($0.12 only) |

Run 100 baseline: winners = 6/6; losers = 0/6. Run 101 pattern: winners 6/6 (consistent); losers now cross 1–2 thresholds (run 100 losers crossed 0). Descriptive reporting only.

**TP-zone PnL split:**

| Trade | Outcome | Max PnL at z ≤ 0.35 |
|---|---|---|
| T1 LINK/ZRO | WIN | +$0.119 |
| T2 AVAX/LINEA | WIN | −$0.048 |
| T3 DOGE/BNB | WIN | +$0.086 |
| T4 DOGE/BNB | LOSS | −$0.046 |
| T5 ARB/DOT | LOSS | +$0.123 |

T2 (winner) had negative TP-zone PnL; T5 (loser) had positive TP-zone PnL (MFE was in TP zone). Run 100 baseline: winners 1/2 had positive TP-zone PnL; losers 100% negative TP-zone PnL. Descriptive reporting only.

**Hold duration split:**
- Winners: 7.4 min, 26.2 min, 11.6 min (avg 15.1 min)
- Losers: 11.1 min, 6.1 min (avg 8.6 min)
- No clear hold-duration separation; T2 at 26.2 min is the longest trade in the run.

**Entry regime split:** All 5 entries in RANGE regime. RISK_OFF regime was entered during pair rotation (13.15% of run time) but no trades executed in RISK_OFF.

**Exit reason distribution:**

| Exit reason | Count | Outcome |
|---|---|---|
| trade_manager_trailing_stop | 2 | 2 WIN |
| trade_manager_pnl_profit_lock | 1 | 1 WIN |
| trade_manager_take_profit | 1 | 1 LOSS |
| trade_manager_regime_break | 1 | 1 LOSS |

Run 100 baseline: wins = trailing_stop, losses = cointegration_watch_timeout. Run 101: wins = trailing_stop + profit_lock; losses = take_profit + regime_break (no cointegration_watch_timeout exits). Descriptive reporting only.

**Guard threshold crossings:** 1 full TP guard pass in run 101 (T5 ARB/DOT, row 1 of 83 evaluations). Run 99 T3 had 1 pass at row 408/414. Run 100 had 0 passes in 289 evaluations. Cumulative experiment: 2 guard passes of 812+ evaluated rows, both on losing trades. This is a factual count — not an inference.

**Profit-lock activations in Patch-5-exclusive band ($0.170–$0.230):** 0 explicit activations documented at the $0.170–$0.230 level this run. Run 100 had 2 activations in this band (Trades 2 and 3 at $0.170 and $0.216). Run 101 profit locks activated at higher levels (T1 MFE $0.244, T2 MFE $0.253, T3 MFE $0.447). Factual count.

**T5 execution gap observation:** T5 exited via full TP guard at floating gross PnL $0.123 but realized net PnL −$0.060. This is the first trade where the full TP guard passed and the final realized PnL was negative. Unexplained execution residual −$0.043 (within Section 7 no-flag threshold). Factual report only.

---

## Section 14 — Counter Update and Next Step

```
trades_since_experiment_start: 19
trades_remaining_to_action_threshold: 1
estimated runs remaining at current pace: ~1 run (run 101 averaged 5 trades/run; 1 remaining)
next step: run 102 with frozen configuration
```

19 trades total after this run. 1 trade remains to the 20-trade structural review threshold. The next run (102) should be the run that closes trade 20. After that run ends, use the 20-Trade Structural Review template (`docs/prompts/20-Trade_Structural_Review.md`) instead of the per-run audit template.

**No recommendations. Configuration is frozen.**
