# Run 120 Post-Run Audit

**Run key:** run_120_20260527_154518  
**Date:** 2026-05-27  
**Status:** stopped  
**Experiment group:** exp_coint_stability_v1  
**Trade:** T12 (SOL-USDT-SWAP/BTC-USDT-SWAP)

---

## Headline Finding: First Win — Captured via Overshoot, Not via Full_TP

T12 is the first equity-positive trade in the Patch 7.1 window (+$0.026). The win was **not** captured by the full_tp guard — the guard blocked all 187 in-zone exit attempts (in-zone MFE $0.057, 2.1× below the $0.12 effective floor). The win was captured by the `trade_manager_regime_break` mechanism at z=−2.066, where the spread had overshot the exit zone by nearly 2 full z-scores.

This confirms the dual-constraint picture from T9 and T11: the full_tp exit path is structurally inactive for most trades (in-zone peaks stay below the $0.12 effective floor), and wins — when they occur — are captured by secondary mechanisms (regime break, z-crossing at overshoot). The guard did not contribute to this win. It worked around it.

---

## Section 1: Run Context

- **Duration:** 3,909s = 1.09 hours (07:45:19 → 08:50:28 UTC)
- **Starting equity:** $2,656.16 | **Ending equity:** $2,656.19
- **Session PnL:** +$0.026 (+0.001%) — **first positive session in Patch 7.1 window**
- **Pairs evaluated:** 2 | **Pair switches:** 1
- **Trade opens:** 1 | **Closed:** 1 | **Open at stop:** 0
- **Entry rejections:** 19 | **Alerts:** 0

Pair history:

| # | Pair | Duration | Switch reason |
|---|------|----------|---------------|
| 1 | SOL-USDT-SWAP/AVAX-USDT-SWAP | 1.2 min | startup_complete (re-entry cooldown from run_119) |
| 2 | SOL-USDT-SWAP/BTC-USDT-SWAP | 63.9 min | cointegration_lost (run end) |

Clean run. No alerts, no circuit breaker. SOL/AVAX brief startup pair cleared immediately.

---

## Section 2: Trade T12 — SOL-USDT-SWAP/BTC-USDT-SWAP

| Field | Value |
|-------|-------|
| Direction | long SOL / short BTC |
| Entry timestamp | 2026-05-27T08:05:46 UTC |
| Exit timestamp | 2026-05-27T08:50:19 UTC |
| Entry z-score | +2.075 |
| Exit z-score | **−2.066** |
| Hold | 44.56 min |
| **Exit reason** | **trade_manager_regime_break** (exit_opportunity_summary) / "normal" (trade_closes — discrepancy noted) |
| Position PnL | **+$0.143** |
| Equity change | **+$0.026** |

**Exit z = −2.066:** the spread reverted from +2.075 through zero and overshot nearly symmetrically to the other side. The MFE ($0.144) occurred at z=−2.066 — the exit extremum, not inside the TP exit zone.

**Exit reason discrepancy:** trade_closes.csv records "normal"; exit_opportunity_summary records "trade_manager_regime_break". These are consistent with the sequence: cointegration deteriorated → regime changed → trade_manager_regime_break fired → pair switch (cointegration_lost). The "normal" label in trade_closes appears to be a coarser category that subsumes regime_break. A trade that exits via full_tp also shows "normal" — the distinction is invisible at the trade_closes level. Item to note for exit-reason taxonomy.

---

## Section 3: Gate Evaluation

**Pair activated:** 07:46:34 UTC | **Entry:** 08:05:46 UTC | **Watch time:** 1,152s = 19.2 min

| Field | Value |
|---|---|
| entry_coint_stability_evaluated_count | **1** |
| entry_coint_stability_slope | **−0.006756** (negative — improving cointegration) |
| Threshold | 0.020 |
| Gate result | PASS (slope far below threshold) |
| Gate classification | **EVALUATED** |

**Item 15 root cause resolved — the buffer was not starved.** Reading [entry_safety_gate.py:403-433](Execution/entry_safety_gate.py#L403-L433) directly:

```python
_coint_eval = 0
...
if len(_p_values) >= config.coint_stability_window:   # ≥5 samples required
    _slope = _ols_slope(_recent)
    _coint_eval = 1      # ← binary: "evaluated this call"
else:
    _coint_insuff = 1
...
components["coint_stability_check_evaluated_count"] = float(_coint_eval)
```

`coint_stability_check_evaluated_count` is a **binary per-call flag** — 0 = insufficient history (<5 samples), 1 = gate evaluated (≥5 samples, slope computed). It is NOT a buffer depth count. Confirmed by the test at [test_entry_safety_gate.py:503-506](Execution/tests/test_entry_safety_gate.py#L503-L506): 5 samples pre-loaded → one gate call → `evaluated_count == 1.0`.

`entry_coint_stability_evaluated_count = 1` in trade_closes means: **the buffer had ≥5 samples at entry time and the OLS slope was computed.** T12 was not starved. T11 was not starved. Both had ≥5 p-value samples in their buffers.

**The changing slope with fixed count=1 is expected, not anomalous.** Each rejection fires the gate; each gate call can add a new p-value to the buffer (using the same 60s interval gate) and recomputes the OLS slope from the latest 5 samples. The count stays at 1 (it is always 1 per call when the buffer is sufficient) while the slope updates as new samples accumulate. This is correct behavior.

**The 4D slope values are trustworthy.** All slopes in the slope-vs-outcome table were computed by OLS from ≥5 real p-value samples. The premise check was running properly on T11 and T12.

**T11 buffer p-values verified directly — the level-check hypothesis is wrong for T11.**

T11 entry_rejections (10 pre-entry safety gate evaluations, verified from run_119 logs):

| Metric | Value |
|---|---|
| Cointegration score | **24.976–24.998 ≈ 25/25 (maximum)** |
| coint_state | **valid** |
| Slope range | −8.67e-6 to −8.12e-6 ≈ 0 |
| insuff_history_count | 0 |

T11 had **maximum cointegration strength** at entry — the highest possible score, coint_state valid, throughout the entire pre-entry monitoring period. The slope ≈ 0 reflects a **flat-at-LOW-p series** (p-values stably very low = strong cointegration), not flat-at-high-p. The "p≈1.0 flat buffer" hypothesis was incorrect. A level check (reject if mean p-value high) would also have **passed** T11 — p was very low.

**T11 failure mode: strong at entry, broke post-entry.** Cointegration was genuinely intact at entry. It deteriorated during the trade (cointegration_watch_timeout = monitoring detected rising p-values post-entry, timeout fired after 26.7 min). The filter correctly passed T11; there was no pre-entry signal to catch. This is the harder failure mode: **not predictable from any pre-entry cointegration metric**, whether slope or level.

The design limitation (slope-blind to flat-at-high-p) is theoretically valid for future unknown pairs — but T11 is not the evidence for it. T11 is evidence of the premise's harder limit: the filter works correctly and the pair fails anyway.

---

## Section 4: Reconciliation

| Field | Value |
|-------|-------|
| Result | **PASS** |
| Basis | pre_close_equity_delta |
| Position PnL | +$0.143 |
| Equity change | +$0.026 |
| Fees | $0.10 |
| Slippage | $0.04 |
| Unexplained | **+$0.023** |
| Unexplained pct | 19.8% |

Reconciliation PASS. The +$0.023 positive residual continues the liquid-pair pattern — 5th occurrence (ETH/ETC +$0.145, DOGE/BNB +$0.078, T9/LINEA-ZRO +$0.073, T11/CRV-IOTA +$0.040, T12/SOL-BTC +$0.023). SOL and BTC are the most liquid pair in the universe; actual costs ($0.117) came in below the $0.14 estimated.

**PnL source mismatch flagged in exit_opportunity_summary:** floating_pnl=−$0.086 vs position_snapshot=+$0.013 at the mismatch evaluation point (delta −$0.099). This is a timing discrepancy in the shadow exit system and does not affect the reconciled position PnL (+$0.143), which is from the OKX fill API. The mismatch is logged but not material to this trade's economics.

---

## Section 5: Trade Timeline

| Time (min) | z-score | Position PnL | Event |
|---|---|---|---|
| 0 | +2.075 | $0.00 | Entry |
| +4.3 | ~+0.35 | ~+$0.057 | **First full_tp zone entry** — in-zone MFE |
| ~+15–40 | inside zone | **+$0.057 max** | **In-zone peak** — guard blocks |
| +44.5 | **−2.066** | **+$0.144** | **MFE — spread overshot** — regime_break exit |

The spread made a near-symmetrical reversion: +2.075 in → −2.066 out. The exit zone (|z|<0.35) was traversed in both directions. The in-zone peak PnL was $0.057. The MFE occurred at the exit extremum (z=−2.066), captured by the regime_break mechanism.

| Guard metric | Value |
|---|---|
| full_tp_zone_eval_count | 187 |
| full_tp_guard_pass_count | **0** |
| full_tp_guard_block_count | 187 |
| Base parameter (guard_floor_at_max_favorable_pnl) | $0.24 |
| **Effective enforced floor** | **$0.12** |
| Max in-zone PnL | **+$0.057** |
| Effective floor / Max in-zone MFE | **2.1×** |
| MFE total (at z=−2.066, outside zone) | +$0.144 |

**Floor gap:** $0.12 − $0.057 = **$0.063** (T12 in-zone peak missed the floor by six cents, not one cent as in T9). A recalibrated floor of $0.10 would still not have enabled a full_tp exit for T12. The floor recalibration proposed in Item 14 would help T9 (one cent) but not T12.

---

## Section 6: Entry Liquidity

From liquidity_checks.csv at 08:05:45 UTC:

| Leg | Liquidity (USDT) | Ratio |
|---|---|---|
| BTC (long) | 47,121 | 471 |
| SOL (short) | 750 | 7.5 |

SOL leg is the thin leg at 750 USDT (ratio 7.5, near the 5.0 floor). BTC extremely liquid. Consistent with positive reconciliation residual — actual costs came in below model estimate.

---

## Section 7: Experiment State

### Trade Counter and Gate Status

| Metric | Value |
|---|---|
| Trades in Patch 7.1 window | **8** (T5–T12) |
| Remaining | **12** |
| Evaluated | 7 (T5, T6, T7, T8, T9, T11, T12) |
| Insufficient_history | 1 (T10) |
| Not_reached | 0 |

4C-TRIGGER rolling-6 (T7–T12): 5/6 evaluated, 1/6 insufficient_history (T10), 0/6 not_reached. **NOT fired.**

### Slope-vs-Outcome Tally

| Trade | Slope at Entry | Gate | Exit Category |
|---|---|---|---|
| T5 | −0.00449 | evaluated | coint-failure |
| T6 | unavailable | evaluated (inferred) | coint-failure |
| T7 | ≈0 (−7.63e-07) | evaluated | normal |
| T8 | +3.99e-04 | evaluated | normal |
| T9 | +2.19e-04 | evaluated | normal |
| T10 | unavailable | insuff_history | normal |
| T11 | ≈0 (−1.34e-06) | evaluated | coint-failure (watch_timeout) |
| T12 | −0.006756 | evaluated | **normal (regime_break)** |

Coint-failures: 3 (T5, T6, T11). Normal exits: 5 (T7, T8, T9, T10, T12). **Win count: 1 (T12).**

T12 slope (−0.006756) is the largest negative (most improving) slope in the window — improving cointegration at entry. Trade succeeded. T5 (coint-failure) had the most deteriorating slope (−0.00449, but note this is still negative = improving; T5 failed despite an improving pre-entry trend). The filter threshold (0.020) was not approached by any trade. No slope exceeded the block threshold.

**Item 15 resolved (see Section 3).** evaluated_count=1 means buffer had ≥5 samples, not 1 sample. Both T11 and T12 were properly evaluated. The 4D slopes are trustworthy OLS computations from real data. The premise check was running. The slopes just don't cluster by outcome — all are far below threshold regardless of coint-failure or win.

---

## Section 8: The Full_TP Mechanism Is Not Capturing Profit — The Primary Finding

### What T12 Adds to the Picture

T9, T11, and T12 all reverted through the exit zone and overshot. The full_tp mechanism (the designed profit-capture path) captured none of them.

| Trade | In-zone MFE | Effective floor | Guard result | Total MFE / location | Outcome |
|---|---|---|---|---|---|
| T9 | $0.111 | $0.12 | BLOCKED — $0.001 short | $0.188 at z=+0.623 (outside zone) | Loss |
| T11 | $0.062 | $0.12 | BLOCKED — $0.06 short | $0.062 (never left zone profitably) | Loss (coint-failure) |
| T12 | $0.057 | $0.12 | BLOCKED — $0.063 short | $0.144 at z=−2.066 (outside zone) | **Win** |

T12's win did not come from the full_tp mechanism. The in-zone peak was $0.057 — six cents below even a floor recalibrated to $0.10. The win was captured by `trade_manager_regime_break` at z=−2.066, where the spread had overshot nearly symmetrically to the other side and the regime broke.

**Floor recalibration (Item 14, floor axis) helps T9 by one cent. It does not help T12.** T12's in-zone peak ($0.057) is below any reasonable floor. The T9 finding is real and trace-anchored but narrow — one trade, one cent. T12 demonstrates that the in-zone peak can be far too small for any floor to enable a full_tp exit, and the trade can still win via a secondary mechanism.

### The Real Finding: Full_TP Captures Nothing — MFE Lives at the Overshoot

Across all guard-tested trades, the profitable moments occur outside the full_tp zone at overshoot extrema. The full_tp mechanism — the designed profit-capture path — has captured zero exits in the Patch 7.1 window. Wins (T12) and marginal misses (T9) are both at overshoot extrema outside the zone. The floor recalibration fixes one cent for one trade; it doesn't touch the structural problem that MFE is systematically occurring outside the capture zone.

The outcomes at the overshoot vary by what secondary mechanism fires:
- **T9**: modest overshoot (z=+0.623), no mechanism fired, position decayed to ≈$0 → loss
- **T12**: extreme overshoot (z=−2.066), regime broke, regime_break fired → win

T12 won because the overshoot was large enough to trigger a regime change. T9 lost because the overshoot was too small. This is not a designed profit-capture mechanism — it is an incidental secondary exit that fires when an unrelated condition (regime change) coincides with an overshoot. It is not reliably triggerable.

**The structural review headline (Item 14, revised):** The full_tp profit-capture mechanism is functionally dead at $200 notional on this pair universe. MFE consistently occurs at overshoot extrema outside the |z|<0.35 capture zone. Wins occur when incidental secondary mechanisms happen to fire at those extrema. The structural review must evaluate whether the exit design can be re-architected to capture MFE where it actually occurs — at overshoots, outside the current zone — not just whether the floor can be lowered by a few cents. Floor recalibration is a minor sub-component of a larger exit-redesign question.

---

## Section 9: Open Items

**Resolved this trade:**
- **Item 15 (RESOLVED):** Root cause identified from code. `coint_stability_check_evaluated_count` is a binary per-call flag (0=insufficient history, 1=evaluated ≥5 samples). Neither T11 nor T12 was buffer-starved — both had ≥5 samples. Changing slope with fixed count=1 is correct behavior (new samples added between gate calls, count always 1 per call when sufficient). The 4D slopes are trustworthy. The actual design limitation: the gate is slope-only with no level check — it passes pairs where p has already plateaued at p≈1.0 (zero-slope from flat-at-bad-level), which may describe T11.

**Continuing:**
- **Item 14 (STRUCTURAL REVIEW — first priority, reframed):** Full_tp mechanism captures no profit — MFE at overshoots outside the zone, wins via incidental secondary exits. Floor recalibration (one cent for T9) is a minor sub-finding. The structural review must evaluate whether the exit can be re-architected to capture MFE at overshoot extrema. Do not let floor recalibration become the headline.
- **Item 12 (ELEVATED):** Residual-vs-liquidity diagnostic. T12 (liquid, +$0.023) continues the pattern — 5 positive residuals on liquid pairs.

**Item 15 — verified, not inferred.** T11 buffer p-values read directly from run_119 entry_rejections. Cointegration score 24.998/25, coint_state=valid at every pre-entry gate evaluation. T11 had maximum cointegration strength at entry; broke post-entry. Level-check hypothesis is wrong for T11 — level check would also have passed. The design limitation (slope-blind to flat-at-high-p) remains theoretically valid for future pairs, but T11 is not its evidence. T11 is evidence of the harder limit: filter correct, pair failed anyway. **Premise verdict implication: pre-entry cointegration stability cannot predict post-entry collapse at these timescales.** This is the constructive finding: not "abandon the idea," but "the entry gate is the wrong layer — post-entry monitoring (cointegration_watch_timeout) is the mechanism that actually catches post-entry collapse." The structural review should evaluate whether the watch_timeout parameters are calibrated to exit quickly enough when collapse is detected, rather than whether a better entry filter could have prevented entry.

---

## Summary

T12: SOL/BTC, spread reverted from +2.075 to −2.066 (full reversion + near-symmetrical overshoot). **First win in Patch 7.1 window — +$0.026 equity.** Win captured by trade_manager_regime_break at the overshoot extremum. Full_tp mechanism irrelevant — guard blocked all 187 in-zone exits (in-zone peak $0.057, 2.1× below effective floor). Reconciliation PASS, basis=pre_close_equity_delta, positive residual +$0.023.

**Item 15 resolved.** evaluated_count=1 is a binary "gate evaluated with ≥5 samples" flag, not a buffer depth. T12 (and T11) were not buffer-starved. The 4D slopes are trustworthy. The actual gate limitation: slope-only design with no level check — passes pairs with p already plateaued at p≈1.0. Design-level finding for structural review.

**Premise check fully resolved.** T11 buffer p-values verified: cointegration score 24.998/25 at entry (maximum strength) — strong at entry, broke post-entry. T5 also appeared healthy at entry (improving slope). Both observable coint-failures had no detectable pre-entry signal — they appeared genuinely stable and then failed. The filter was running correctly; the failure mode is post-entry collapse that a pre-entry gate cannot catch by construction. **Premise verdict: the slope signal is the wrong layer. Pre-entry cointegration stability does not predict post-entry collapse at these timescales. The cointegration_watch_timeout mechanism (post-entry monitoring) is what actually catches the failure — the question for the structural review is whether it exits fast enough, not whether the entry filter is better calibrated.**

Experiment cumulative (T5–T12): −$2.179 (all), −$2.114 (economic, T8 excluded). Win rate: 1/8 = 12.5%. Coint-failures: 3 (T5, T6, T11). Run 121, frozen config.
