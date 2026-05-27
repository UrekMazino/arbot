# Run 119 Post-Run Audit

**Run key:** run_119_20260527_095432  
**Date:** 2026-05-27  
**Status:** stopped  
**Experiment group:** exp_coint_stability_v1  
**Trade:** T11 (CRV-USDT-SWAP/IOTA-USDT-SWAP)

---

## Headline Finding: Guard Floor Structure and the T9 Near-Miss

The full_tp guard has three distinct numbers, only one of which is the actual enforced threshold. The `guard_floor_at_max_favorable_pnl` field in trade_closes.csv stores the **base parameter** ($0.24). The enforced threshold checked against current PnL is **effective_full_tp_floor_usdt = $0.12** (base × full_tp_guard_multiplier 0.50). A third number, the **profit-lock activation floor = $0.17** ($0.12 + $0.05 buffer), is when the trailing-stop mechanism activates.

Prior audit sections incorrectly cited $0.24 as "the guard floor." The actual enforced floor is $0.12.

With this corrected, the picture changes: T9's in-zone MFE was **$0.111** — blocked by the $0.12 effective floor (one cent short). If the base parameter were $0.20 (effective floor $0.10), the guard passes at $0.111 and T9 exits in profit (~+$0.07 equity). T11 remains uniquely guard-trapped: MFE $0.062 was below the effective floor regardless of any reasonable recalibration.

This finding is addressed in detail in Section 8.

---

## Section 1: Run Context

- **Duration:** 21,041s = 5.84 hours (01:54:32 → 07:45:14 UTC)
- **Starting equity:** $2,656.66 | **Ending equity:** $2,656.16
- **Session PnL:** −$0.499 (−0.019%)
- **Pairs evaluated:** 7 | **Pair switches:** 6
- **Trade opens:** 1 | **Closed:** 1 | **Open at stop:** 0
- **Entry rejections:** 322 | **Alerts:** 0

Pair history:

| # | Pair | Duration | Switch reason |
|---|------|----------|---------------|
| 1 | FIL-USDT-SWAP/ICP-USDT-SWAP | 9.5 min | startup_complete (re-entry cooldown from run_118) |
| 2 | ENA-USDT-SWAP/ETC-USDT-SWAP | 36.4 min | cointegration_lost |
| 3 | SOL-USDT-SWAP/KSM-USDT-SWAP | 109.7 min | pair_universe_pruned |
| 4 | JUP-USDT-SWAP/YGG-USDT-SWAP | 2.4 min | cointegration_watch_timeout |
| 5 | SOL-USDT-SWAP/BTC-USDT-SWAP | 45.1 min | pair_universe_pruned |
| 6 | CRV-USDT-SWAP/IOTA-USDT-SWAP | 147.3 min | cointegration_watch_timeout (T11) |
| 7 | SOL-USDT-SWAP/AVAX-USDT-SWAP | 9.9s | stop (run end) |

Clean run. No alerts, no circuit breaker. FIL/ICP re-entry cooldown from run_118 cleared as expected.

---

## Section 2: Trade T11 — CRV-USDT-SWAP/IOTA-USDT-SWAP

| Field | Value |
|-------|-------|
| Direction | long IOTA / short CRV |
| Entry timestamp | 2026-05-27T05:44:25 UTC |
| Exit timestamp | 2026-05-27T07:45:02 UTC |
| Entry z-score | +2.177 |
| Exit z-score | −0.244 |
| Hold | 120.63 min |
| **Exit reason** | **cointegration_watch_timeout** (confirmed string — not "normal") |
| Position PnL | −$0.399 |
| Equity change | −$0.499 |

---

## Section 3: Gate Evaluation

**Pair activated:** 05:17:44 UTC | **Entry:** 05:44:25 UTC | **Watch time:** 1,601s = 26.7 min

| Field | Value |
|---|---|
| entry_coint_stability_evaluated_count | **1** |
| entry_coint_stability_slope | **−1.34×10⁻⁶ ≈ 0** |
| Threshold | 0.020 |
| Gate result | PASS (slope far below threshold) |
| Gate classification | **EVALUATED** |

**Evaluated_count=1 — resolved in run_120 audit (Item 15 closed). Buffer starvation narrative was incorrect.**

`entry_coint_stability_evaluated_count = 1` is a **binary per-call flag**: 0 = insufficient history (<5 samples), 1 = gate evaluated with ≥5 samples and computed OLS slope. It is NOT a buffer depth count. Confirmed from [entry_safety_gate.py:403-433](Execution/entry_safety_gate.py#L403-L433). T11 was NOT buffer-starved — the buffer had ≥5 p-value samples at entry.

**T11 buffer p-values verified directly** (entry_rejections.csv, 10 pre-entry gate evaluations):

| Metric | Value |
|---|---|
| Cointegration score at gate evaluations | **24.976–24.998** (≈ 25/25 max) |
| coint_state | **valid** |
| Unique slopes in buffer | −8.67e-6, −8.12e-6 ≈ 0 |
| insuff_history_count | 0 |

T11 had **maximum cointegration strength** at entry. The slope ≈ 0 reflects a **flat-at-low-p series** (p-values stably very low = strong cointegration), not flat-at-high-p. The "p≈1.0 flat buffer" hypothesis was wrong — T11's cointegration was genuinely, strongly intact at entry.

**The T11 failure mode is post-entry cointegration collapse.** Cointegration was valid and strong at entry; it deteriorated during the trade (cointegration_watch_timeout = monitoring detected rising p-values post-entry, timeout after 26.7 min). The filter correctly passed T11 — there was no pre-entry signal to catch. A level check would also have passed T11 (p was very low at entry). This is the harder case: **strong at entry, broke post-entry — not predictable from any pre-entry cointegration metric.**

---

## Section 4: Reconciliation

| Field | Value |
|-------|-------|
| Result | **PASS** |
| Basis | pre_close_equity_delta |
| Trade PnL (position) | −$0.399 |
| Equity change | −$0.499 |
| Fees | $0.10 |
| Slippage | $0.04 |
| Unexplained | **+$0.040** |
| Unexplained pct | 39.4% |

Reconciliation PASS. The +$0.040 positive residual continues the liquid-pair pattern (4th occurrence — ETH/ETC +$0.145, DOGE/BNB +$0.078, T9/LINEA-ZRO +$0.073, T11/CRV-IOTA +$0.040). Adequate liquidity correlates with sub-model costs; thin liquidity correlates with super-model costs.

---

## Section 5: Trade Timeline

| Time (min) | z-score | Position PnL | Event |
|---|---|---|---|
| 0 | +2.177 | $0.00 | Entry |
| +6.1 | +0.081 | +$0.028 | **First full_tp zone trigger** — guard blocks |
| +77.9 | **−0.750** | **+$0.062** | **Max favorable** — guard still blocks |
| +112.9 | +1.069 | **−$0.546** | **Max adverse** — spread re-expanded |
| +120.6 | −0.244 | −$0.399 | **Exit: cointegration_watch_timeout** |

z reverted from +2.177 to −0.75 (full reversion and overshoot). The guard blocked every one of 446 exit attempts. The spread re-expanded adversely. Timeout fired at 120 min mark.

| Guard metric | Value |
|---|---|
| full_tp_zone_eval_count | 446 |
| full_tp_guard_pass_count | **0** |
| full_tp_guard_block_count | 446 |
| Base parameter (guard_floor_at_max_favorable_pnl) | $0.24 |
| **Effective enforced floor** (base × 0.50 multiplier) | **$0.12** |
| Profit-lock activation floor (effective + $0.05 buffer) | $0.17 |
| Max in-zone PnL achieved | **+$0.062** |
| Effective floor / Max in-zone MFE | **1.9×** |

The loss is −$0.399 position PnL plus ~$0.10 actual costs. Costs were NOT the primary driver here — the guard trap and adverse re-expansion were.

---

## Section 6: Entry Liquidity

From liquidity_checks.csv at 05:44:24 UTC:

| Leg | Liquidity (USDT) | Ratio |
|---|---|---|
| IOTA (long) | 813.34 | 8.13 |
| CRV (short) | 2,312.99 | 23.13 |

Both legs comfortable. Not a thin liquidity entry. Consistent with positive reconciliation residual.

---

## Section 7: Experiment State

### Trade Counter and Gate Status

| Metric | Value |
|---|---|
| Trades in Patch 7.1 window | 7 (T5–T11) |
| Remaining | **13** |
| Evaluated | 6 (T5, T6, T7, T8, T9, T11) |
| Insufficient_history | 1 (T10) |
| Not_reached | 0 |

4C-TRIGGER rolling-6 (T6–T11): 5/6 evaluated, 1/6 insufficient_history, 0/6 not_reached. **NOT fired.**

### Slope-vs-Outcome Tally

| Trade | Slope at Entry | Exit Category |
|---|---|---|
| T5 | −0.00449 | coint-failure |
| T6 | unavailable | coint-failure |
| T7 | ≈0 | normal |
| T8 | +3.99e-04 | normal |
| T9 | +2.19e-04 | normal |
| T10 | insuff_history | normal |
| T11 | ≈0 (−1.34e-06) | **coint-failure (watch_timeout)** |

**Three coint-failures total: T5, T6, T11.** cointegration_watch_timeout is a coint-failure category. Only T5 has a visible slope — T6 was pre-Patch-7.2 (no slope logging), T11 was buffer-starved (evaluated_count=1 despite 26.7 min watch). Two of three coint-failures arrived slope-blind. Next coint-failure's slope remains the deciding data point, but two slope-blind entries in succession is itself a signal about Patch 7's observability on deteriorating pairs (see Item 15, Section 9).

---

## Section 8: Exit-Capture Calibration — The Headline Finding

### Guard Floor Structure: Three Distinct Numbers

The `guard_floor_at_max_favorable_pnl` field in trade_closes.csv stores the **base parameter ($0.24)**. This is not the enforced threshold. The actual enforced threshold is the **effective full_tp floor = $0.12** (base × full_tp_guard_multiplier 0.50). A separate third number, the **profit-lock activation floor = $0.17** ($0.12 + $0.05 buffer), governs when the trailing-stop mechanism activates.

Prior audit drafts cited "$0.24 as the guard floor." The enforced floor the gate actually checks against floating PnL is $0.12.

### Complete MFE Table Across All Evaluated Trades

| Trade | In-zone MFE | Effective floor | Guard blocks | Guard result | Actual equity outcome |
|---|---|---|---|---|---|
| T5 | −$0.082 | $0.12 | 0 | N/A (never profitable) | −$0.555 coint-failure |
| T6 | −$0.035 | $0.12 | 0 | N/A (never profitable) | −$0.786 coint-failure |
| T7 | +$0.127 | $0.12 | 41 | **BLOCKED** | −$0.107 |
| T8 | blank | $0.12 | 0 | Unknown (data quality) | −$0.065 (unreliable) |
| T9 | **+$0.111** (in-zone) | $0.12 | — | **BLOCKED — $0.001 short** | −$0.073 |
| T10 | +$0.274 | $0.12 | 35 | **PASSED** (after 35 blocks) | −$0.120 (costs 2.8×) |
| T11 | +$0.062 | $0.12 | 446 | **BLOCKED** | −$0.499 coint-failure |

T9 footnote: total MFE across all time was +$0.188, but this peak occurred at z=0.623, outside the |z|<0.35 full_tp exit zone. The full_tp mechanism does not fire outside the zone. In-zone MFE was $0.111 — one cent below the $0.12 effective floor. These are two different numbers requiring two different mechanisms to address.

### The T9 Dual-Constraint Finding

T9's position had two distinct constraints between its best PnL and a profitable exit:

**Constraint 1 — Exit zone.** The full_tp mechanism only fires when |z| < take_profit_z (≈ 0.35). T9's spread reverted from −2.67 and overshot. At z=0.623, the position's floating PnL was +$0.188 — the position's best moment. But the full_tp mechanism does not operate outside the zone. This peak was never capturable by full_tp regardless of the floor setting.

**Constraint 2 — Guard floor.** By the time z re-entered the exit zone (z ≈ 0.07–0.34), PnL had decayed to $0.111. The effective floor is $0.12. Guard blocked — short by $0.001.

Trace evidence (exit_decision_trace.csv, T9):
- In-zone rows (4): floating_pnl=$0.111, full_tp_zone_hit=True, full_tp_guard_passed=False, effective_full_tp_floor_usdt=0.12, why="trade_manager_net_profit_guard_blocked"
- Outside-zone rows (2): floating_pnl=$0.188, full_tp_zone_hit=False, pnl_profit_lock_active=True (MFE $0.188 ≥ floor $0.17), selected_exit_reason="no exit candidates"

**Corrected counterfactual (trace-anchored, conservative):** If the base floor parameter were $0.20 (effective $0.10), the guard passes at $0.111. Estimated equity at that exit: +$0.111 minus remaining costs ≈ **+$0.07 (a win).** This is anchored to the actual observed in-zone PnL that the guard actually blocked — not an assumed exit at the $0.188 peak which was never in the exit zone.

**What a lower floor cannot fix:** T9's MFE peak (+$0.188 at z=0.623) was outside the exit zone. No floor recalibration allows full_tp to fire outside |z|<0.35. Capturing peaks that occur outside the zone requires a different mechanism — zone widening, a separate MFE-triggered exit, or profit-lock with different parameters.

**Caution before structural review claims T9 as a win:**
- Finding rests on **one trade and a one-cent margin.** A penny of different fill → T9 still blocked under the corrected $0.10 effective floor.
- Counterfactual assumes clean exit at $0.111. The guard stopping blocking does not guarantee an exit fires — the profit-lock and trailing-stop logic also runs. Verify from the trace that an exit would have been selected, not just that the guard would have cleared.
- This is a frozen-variable counterfactual. T9 will remain speculative until a recalibration experiment actually runs with a lower floor and produces outcomes to compare.
- Honest framing: **"This warrants a recalibration experiment, not a presumption that recalibration fixes the economics."**

### Retroactive Contamination of the "Cost-Dominated" Framing

Prior audits characterized T7, T9 as cost-dominated losses: strategy worked, spread reverted, costs ate the edge. That framing needs a qualification for both.

For T7 and T9, the actual sequence:
1. Spread reverted → position reached in-zone MFE
2. Guard blocked exit at in-zone MFE (floor not met)
3. Spread re-narrowed → position PnL dropped from MFE to near-zero
4. Normal exit fired at near-zero position PnL
5. Costs then pushed equity negative

Step 2 is not a cost problem. The guard blocked capture of the in-zone MFE. The trade gave back most of its favorable position before the next exit mechanism fired. "Edge ≈ 0, costs = loss" is partly "edge was +$0.111–$0.127 inside the zone, guard prevented capturing it, edge decayed to ≈ 0, costs = loss."

T10 is genuinely cost-dominated: the guard passed at $0.274, the trade exited at its MFE peak, real costs of $0.394 exceeded the position profit. No guard problem in T10.

### Corrected Failure Mode Taxonomy

| Category | Trades | Primary driver |
|---|---|---|
| Coint-failure | **T5, T6, T11** | Cointegration broke or timed out with re-expansion; spread diverged before exit |
| Guard-blocked (in-zone MFE not captured) | T7, T9 | Guard prevented exit at in-zone MFE; position PnL decayed to near-zero; costs caused equity loss |
| Cost-dominated (guard passed) | T10 | Guard passed at $0.274; exited at MFE peak; real costs 2.8× model exceeded profit |

T11 is a coint-failure. cointegration_watch_timeout is a coint-failure category — the pair's cointegration deteriorated, the spread re-expanded adversely, and the timeout fired. The 446 guard blocks are a consequence of that deterioration, not the primary failure mode.

### Item 14 Widened: Exit-Capture Calibration (Floor + Zone)

Prior framing: "guard floor recalibration — lower base parameter from $0.24 to ~$0.13–$0.15."

Corrected framing — **exit-capture calibration on two axes:**

**Floor axis:** Effective floor $0.12 is above achievable in-zone MFE for T9 ($0.111, blocked by $0.001) and T11 ($0.062, blocked regardless). T7 at $0.127 clears the $0.12 effective floor — T7 was blocked by the old $0.24 base misreading; under the correct $0.12 effective floor, T7 should have passed. Verify whether T7 guard blocks were checked against $0.12 or $0.24 in the trace.

**Zone axis:** T9's true MFE (+$0.188) occurred at z=0.623, outside the |z|<0.35 capture zone. Floor recalibration alone cannot capture this. A floor-only fix means: if the next trade has its MFE outside the zone (as T9's best moment did), the recalibrated floor still produces zero improvement. The structural review must evaluate zone parameters alongside the floor — or a floor-only fix will hit its ceiling immediately.

### Rhyme with Patch 5

Second guard-related mechanism found dead because a threshold is set outside the achievable range. Patch 5 review found guard_pass_rate = 0.34% (mechanism dead). Now the effective guard floor ($0.12) sits above achievable in-zone MFE for T9 ($0.111), and the zone itself excludes MFE peaks for trades where reversion overshoots (T9 $0.188 at z=0.623). Both mechanisms were calibrated against assumed distributions that don't match production at $200 notional on this pair universe.

This is a frozen variable. The structural review must address both axes before re-running.

---

## Section 9: Open Items

**New from T11:**

- **Item 14 (STRUCTURAL REVIEW — first priority — widened):** Exit-capture calibration on two axes. Floor axis: effective floor $0.12 was above T9's in-zone MFE ($0.111, blocked by one cent); recalibrating base from $0.24 to ~$0.20 (effective $0.10) plausibly makes T9 a ~+$0.07 equity win — but rests on one trade and one-cent margin; frame as experiment, not presumption. Zone axis: T9's true MFE ($0.188) occurred at z=0.623, outside the |z|<0.35 exit zone — floor recalibration alone cannot capture it. Structural review must evaluate both floor and zone parameters, or a floor-only fix hits its ceiling immediately.

- **Item 15 (RESOLVED — run_120 audit):** `evaluated_count=1` is a binary per-call flag (≥5 samples evaluated), not a buffer depth. T11 was NOT buffer-starved. T11 buffer p-values verified from entry_rejections: cointegration score 24.998/25 (max), coint_state=valid across all 10 pre-entry evaluations. T11 had maximum cointegration strength at entry. Slope ≈ 0 reflects flat-at-LOW-p (stable, strong cointegration), not flat-at-high-p. Level-check hypothesis is wrong for T11 — level check would also have passed. **T11 failure mode: strong at entry, broke post-entry. Not predictable from any pre-entry cointegration metric.** This is the harder failure mode — the filter worked correctly; the pair failed anyway.

**Continuing open:**
- Item 12 (elevated): Residual-vs-liquidity diagnostic. T10 is the anchor data point (FIL 575 USDT thin, −$0.255 residual). T11 (liquid, +$0.040 residual) continues the pattern.
- Item 13: Post-close fee snapshot timing gap (T8, retry_count=3).

---

## Section 10: Structural Review Priority Reorder

Three findings, ordered by actionability and likely impact:

1. **Item 15 / Patch 7 verdict (premise-level, constructive).** T11 buffer p-values verified: cointegration score ≈25/25 at entry (maximum strength), broke post-entry. Both observable coint-failures (T5, T11) appeared genuinely healthy at entry — failed post-entry. Filter was running correctly; the failure mode was not catchable at entry by any pre-entry metric. Premise verdict: **slope incomplete (structurally cannot catch post-entry collapse), not "premise wrong."** Next iteration: slope + a mechanism that monitors deterioration post-entry more aggressively (this may already exist — the cointegration_watch_timeout mechanism). Evaluate at structural review.

2. **Item 14 — exit redesign (exit mechanism, not just floor).** Full_tp capture path captured 0 exits. MFE at overshoots outside zone; wins via incidental secondary exits (regime_break at T12 z=−2.066). Redesign exit capture; floor recalibration is a minor sub-item.

3. **Item 12 / thin-leg liquidity gate (T10 anchor).** Cost model diagnostic; min-leg liquidity gate candidate.

The experiment was built to answer #3. It is answering it — but the more actionable findings (#1 and #2) are emerging as side effects, and both are parameter mismatches with concrete fixes. The structural review document must address #1 before re-running the premise question.

---

## Summary

T11: spread reverted correctly (z: +2.177 → −0.75, full reversion in 78 min). Guard blocked 446 in-zone exits (effective floor $0.12, in-zone MFE $0.062). Spread re-expanded adversely. Timeout at 120 min. Loss = −$0.499. T11 is a coint-failure (cointegration_watch_timeout), not a new taxonomy category.

The headline finding from T11 combined with T9 trace analysis: the exit-capture mechanism is mis-calibrated on two axes. (1) Floor: effective $0.12 is above T9's in-zone MFE of $0.111 — one cent blocked a probable win. (2) Zone: T9's true MFE ($0.188) occurred outside the |z|<0.35 exit zone — floor recalibration alone cannot capture it. A floor-only fix misses half the problem.

Three coint-failures (T5, T6, T11); only T5 has a visible slope; two of three arrived slope-blind. Item 15 is premise-level: if the buffer starves on deteriorating pairs, Patch 7's premise is untestable as implemented — not just wrong.

Run 120, frozen config. Watching for one number: next coint-failure's slope. Exit-capture recalibration and Item 15 root cause are structural-review gates.
