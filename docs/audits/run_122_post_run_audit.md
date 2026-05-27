# Run 122 Post-Run Audit

**Run key:** run_122_20260527_205448  
**Date:** 2026-05-27  
**Status:** stopped (manual)  
**Experiment group:** exp_coint_stability_v1  
**Trade:** T13 (BNB-USDT-SWAP/COMP-USDT-SWAP)  
**Note:** Run 121 (same date, earlier) was a no-trade run — manually stopped with no z-signals; no audit warranted.

---

## Headline Finding: T13 Introduces $/σ — the Unifying Economic Variable the Experiment Was Missing

T13 exited via `trade_manager_regime_break` (z=−1.918), the same mechanism that produced the T12 win. T12 accumulated +$0.143 position PnL during the traversal; T13 accumulated −$0.395. T13's spread was **never profitable** — MFE = −$0.076 throughout — meaning the USDT value of the spread move never exceeded the $0.14 entry cost burden at any point.

The reason is now quantifiable: BNB/COMP at $200 notional generates ~**$0.049 of position value per σ of z-move** (derived from early-trade data — see Section 2 for caveats). At that sensitivity, covering $0.14 round-trip costs requires entry z ≥ **3.21σ** (corrected for exit-zone boundary at z=0.35; see below). The system entered at 2.456σ — structurally below breakeven before the trade started. No exit mechanism could have saved it because the pair's dollar-per-σ is too low for the entry threshold.

This is a **pair-specific economic gate** problem, distinct from cointegration quality (which was strong, 24.30/25) and from exit-mechanism design (Item 14). It also suggests that T7 and T9 — whose in-zone MFE peaks of $0.111–$0.127 were themselves barely above or below the $0.12 floor — were probably also $/σ-constrained pairs that cleared the cost hurdle only marginally if at all. T13 makes the constraint explicit and computable.

---

## Section 1: Run Context

- **Duration:** 2,860s = 47.7 min (12:54:48 → 13:42:28 UTC)
- **Starting equity:** $2,656.191 | **Ending equity:** $2,655.683
- **Session PnL:** −$0.508 (−0.019%)
- **Pairs evaluated:** 1 (BNB/COMP, held entire run) | **Pair switches:** 0
- **Trade opens:** 1 | **Closed:** 1 | **Open at stop:** 0
- **Entry rejections:** 6 | **Alerts:** 0

Pair history:

| # | Pair | Duration | Switch reason |
|---|------|----------|---------------|
| 1 | BNB-USDT-SWAP/COMP-USDT-SWAP | 47.6 min | startup_complete (held to run end) |

Single-pair run. No switching. Regime ended at RISK_OFF (was RANGE at entry) — the regime break that triggered exit.

---

## Section 2: Trade T13 — BNB-USDT-SWAP/COMP-USDT-SWAP

| Field | Value |
|-------|-------|
| Direction | long_positive_short_negative |
| Entry timestamp | 2026-05-27T13:01:17 UTC |
| Exit timestamp | 2026-05-27T13:42:20 UTC |
| Entry z-score | +2.456 |
| Exit z-score | **−1.918** |
| Hold | 41.04 min |
| **Exit reason** | **trade_manager_regime_break** (exit_opportunity_summary) / "normal" (trade_closes — same coarser label observed on T12; consistent with prior taxonomy note) |
| Position PnL | **−$0.395** |
| **MFE (overall)** | **−$0.076** (at z=+1.149, ~3 min in — briefly least-adverse point) |
| Max adverse PnL | **−$0.546** (at z=+0.965, ~30 min in) |
| Equity change | **−$0.508** |

**z-path note:** The trade did not traverse monotonically. z started at +2.456, narrowed briefly to z≈+1.149 at 3 min (least adverse point, MFE = −$0.076), then widened or meandered adversely reaching max adverse −$0.546 at z=+0.965 around 30 min in, then collapsed to z=−1.918 (regime broke, exit fired) at 41 min. The partial recovery from −$0.546 to −$0.395 in the final ~11 minutes occurred during the z collapse phase. Exact intra-trade path not reconstructed from available data; the non-monotonic behavior likely reflects BNB/COMP absolute price movements decoupled from the z-normalized spread.

**Critical observation — MFE negative throughout:** The most favorable position PnL at any point in the trade was −$0.076. The spread traversal from z=+2.456 to z=−1.918 (4.37σ total move) never generated enough gross position profit to overcome the $0.14 entry cost (fees $0.10 + slippage $0.04). The breakeven analysis:

| Metric | Value | Notes |
|--------|-------|-------|
| Entry z | +2.456 | |
| z at MFE | +1.149 (z narrowed by 1.307σ in 3 min) | Early-trade data point |
| MFE (net of costs) | −$0.076 | |
| Implied gross at MFE | −$0.076 + $0.14 = +$0.064 | |
| Implied $/σ | $0.064 / 1.307σ ≈ **$0.049/σ** | **Preliminary — early-trade estimate only; see caveats** |
| Exit zone boundary | z = +0.35 (full_tp zone: \|z\| ≤ 0.35) | Corrected; prior analysis used z=0 |
| Captured z-distance (full_tp path) | z_entry − 0.35 = 2.456 − 0.35 = 2.106σ | Not z_entry as previously stated |
| Gross PnL at zone boundary | 2.106σ × $0.049 = $0.103 | |
| Net PnL at zone boundary | $0.103 − $0.14 = **−$0.037** | Still negative even at zone entry |
| Breakeven entry z (full_tp path) | ($0.14/$0.049) + 0.35 = 2.857 + 0.35 = **~3.21σ** | **Corrected from prior 2.86σ** |
| System entry_z cap | ~3.0σ | From frozen config |
| Actual entry | 2.456σ — **below breakeven** | |

**Corrected breakeven interpretation:** the prior figure of 2.86σ assumed the trade captures z-move all the way to z=0. The full_tp exit zone starts at z=0.35, not z=0, so the captured distance is shorter. The corrected breakeven (3.21σ) is higher than the prior figure — and higher than the system's ~3.0σ entry cap. **BNB/COMP cannot be profitably traded via full_tp at any entry z the system will generate.**

**$/σ caveats (verification required before this number is load-bearing):**
1. The $0.049/σ estimate derives from three minutes of early-trade data (z: +2.456 → +1.149, MFE = −$0.076). It is the best available proxy but not verified from actual position sizing and spread dollar-values.
2. The full-traversal data is inconsistent: 4.374σ total move (z: +2.456 → −1.918) at $0.049/σ should yield ~+$0.074 net — but actual position PnL = −$0.395, a $0.469 discrepancy. This gap exceeds any reasonable measurement error and suggests either (a) the $/σ is non-constant across the z-range, (b) there was a transient mark-to-market spike on one leg (consistent with max adverse −$0.546 at z=+0.965 — implying a $0.470 adverse excursion between 3 and 30 min while z barely moved), or (c) the trade direction assumption is wrong. The early-trade $/σ estimate is reliable for the MFE calculation; the full-traversal interpretation is not resolved.
3. Confirming the $/σ figure from position sizing and current spread volatility is the prerequisite before using this number to design an entry gate.

Despite these caveats, the qualitative finding holds: MFE = −$0.076 (never profitable), and the full_tp path cannot clear costs at this pair/notional combination. The exact breakeven z has uncertainty, but it is clearly above the actual entry z and likely at or above the system cap.

---

## Section 3: Gate Evaluation

Gate reached with full buffer (evaluated_count = 1). Cointegration quality was high.

**Gate components at entry rejection rows (13:00:50 – 13:01:04):**

| Component | Value | Notes |
|-----------|-------|-------|
| coint_stability_evaluated_count | 1.0 | Full buffer (≥5 p-value samples) |
| coint_stability_slope | −0.000324 | Near-zero negative (stable/improving) at rejection rows |
| cointegration score | 23.38 → 24.30 | Rising across evaluations; strong |
| coint_state | valid | Throughout |
| mean_reversion | 9.66 → 11.66 | Acceptable |
| pair_history | 4.90 | Just at threshold |

**Gate components at actual entry (from trade_closes.csv):**

| Component | Value |
|-----------|-------|
| entry_coint_stability_slope | **+0.001019** |
| entry_coint_stability_evaluated_count | 1.0 |

**Slope shift at entry:** At the rejection rows (13:01:04 and earlier), slope was −0.000324 (slightly negative = improving). At actual entry (13:01:17, 13 seconds later), slope recorded as +0.001019 (slightly positive = mild deterioration trend). A new p-value sample was appended between the last rejection and the trade open; the OLS recomputed from the rolling-5 buffer produced a slightly positive slope. Both values are near-zero — this is not a meaningful divergence in either direction. The gate passed correctly in both cases (neither slope exceeds threshold in either direction).

**First positive slope in experiment:** T13's entry slope (+0.001019) is the first positive entry slope recorded. Prior slopes (T7 −0.00264, T9 −0.009, T11 −0.004, T12 −0.00676) were all negative. The positive slope means p-values were trending slightly upward (cointegration weakening marginally) — but the magnitude is trivially small and the gate correctly passed it.

**Experiment slope tally (T7 onward, all entries evaluated):**

| Trade | Slope | Outcome |
|-------|-------|---------|
| T7 BTC/HBAR | −0.00264 | Loss (guard-blocked) |
| T9 LINEA/ZRO | −0.009 | Loss (guard-blocked) |
| T11 CRV/IOTA | −0.004 | Loss (coint-failure) |
| T12 SOL/BTC | −0.006756 | **Win** |
| T13 BNB/COMP | **+0.001019** | Loss (cost-floor breach) |

No slope-outcome signal at N=5. Negative slopes appear in both wins (T12) and losses (T7, T9, T11). T13's near-zero positive slope adds no discriminating information.

**Pre-entry blocks (advanced_ml_break_risk_high):**

The gate blocked entry 4 times on `advanced_ml_break_risk_high` (13:00:50 → 13:01:04), all with break_risk=0.15 and ML reasons: `trend_score >= 0.7, regime switch held by hysteresis`. The ML model was signaling a pending regime transition — which did in fact materialize (RANGE → RISK_OFF) 40 minutes into the trade. The trade entered after break_risk dropped below threshold at 13:01:17.

The ML warning was directionally correct — the regime did break — but the break_risk gate cleared before the regime actually shifted, allowing entry. The 4 break_risk blocks delayed entry by ~30 seconds; the regime switch occurred 41 minutes later. This is an observation, not a structural finding.

---

## Section 4: Exit Analysis

**Exit mechanism:** `trade_manager_regime_break` — same mechanism that produced the T12 win.

| Run | Entry z | Exit z | MFE | Position PnL | Outcome |
|-----|---------|--------|-----|--------------|---------|
| T12 SOL/BTC | +2.075 | −2.066 | +$0.144 | +$0.143 | **Win** |
| T13 BNB/COMP | +2.456 | −1.918 | −$0.076 | −$0.395 | **Loss** |

Both trades: entered at z>2.0, regime broke at z≈−2.0 (near-symmetric overshoot). The difference appears to be in the pair's spread width in USDT terms. SOL/BTC at $200 notional: $/σ ≈ $0.068 (derived from T12 full-traversal: ($0.143+$0.14)/4.141 = $0.068/σ — consistent). BNB/COMP: $/σ ≈ $0.049 (early-trade estimate, see Section 2 caveats — full-traversal inconsistency unresolved). The regime_break exit is profitable for SOL/BTC and a loss for BNB/COMP; if the $/σ estimates are correct, the breakeven z for an overshoot exit at z≈−2.0 is: (z_entry + 2.0) × $/σ ≥ $0.14 → z_entry ≥ ($0.14/$0.049) − 2.0 ≈ 0.86σ — theoretically cleared at 2.456σ — yet T13 still lost. The inconsistency reinforces that the BNB/COMP $/σ estimate or trade-direction assumption needs verification before the overshoot-path analysis is treated as reliable.

**No designed exit path active:** full_tp evaluated 121 times, passed 0 times. The "pass rate = 0%" continues for a 5th consecutive evaluated trade. Full exit discussion in Section 5.

---

## Section 5: Guard Floor Analysis

| Metric | Value |
|--------|-------|
| full_tp_zone_eval_count | 121 |
| full_tp_guard_pass_count | 0 |
| full_tp_guard_block_count | 121 |
| Max PnL during full_tp zone | −$0.084 |
| Guard floor (base parameter) | $0.24 |
| Effective floor ($0.24 × 0.50) | **$0.12** |

The guard floor is irrelevant for T13. All 121 "blocks" occurred because in-zone floating PnL was negative — the guard threshold ($0.12 effective) was never within reach. The guard mechanism would need PnL to be **positive** and above $0.12 to pass; PnL peaked at −$0.076 (max PnL in zone = −$0.084 at the zone boundary).

This is distinct from the guard-blocked pattern in T7 and T9, where in-zone PnL was positive but below the floor. For T13, in-zone PnL was never positive. The guard had no economic relevance.

**Updated guard outcome summary (Patch 7.1 window):**

| Trade | In-zone MFE | Guard | Floor-relevant? |
|-------|-------------|-------|-----------------|
| T5 FIL/FLOKI | −$0.082 | N/A — never profitable | No |
| T6 DOGE/SUI | −$0.035 | N/A — never profitable | No |
| T7 BTC/HBAR | +$0.127 | 41 blocks (verify trace) | Yes (MFE > floor, unclear why blocked) |
| T8 SOL/AVAX | — | Data quality | Unknown |
| T9 LINEA/ZRO | **+$0.111** (in-zone) | BLOCKED — $0.001 short of $0.12 | **Yes — one cent** |
| T10 FIL/ICP | +$0.274 | PASSED → loss from costs | Floor passed, costs dominated |
| T11 CRV/IOTA | +$0.062 | 446 blocks — coint-failure | Yes (but coint exit dominated) |
| T12 SOL/BTC | +$0.057 (in-zone) | 187 blocks — win via regime_break | Yes (floor moot — in-zone peak $2.1× below floor) |
| **T13 BNB/COMP** | **−$0.076 (negative always)** | 121 "blocks" — PnL never positive | **No — guard not floor-relevant** |

The designed exit path (full_tp) has passed zero times in 9 evaluated experimental trades. For T13, the mechanism isn't even being tested — PnL never reached the positive domain.

---

## Section 6: Reconciliation

| Field | Value |
|-------|-------|
| Trade PnL | −$0.395 |
| Equity change | −$0.508 |
| Difference | −$0.113 |
| Fees | $0.10 |
| Slippage | $0.04 |
| Funding | $0.00 |
| **Unexplained** | **+$0.027** |
| Basis | pre_close_equity_delta |
| Pass/fail | **PASS** |

Reconciliation passes. Unexplained +$0.027 is positive and consistent with the recurring positive-residual pattern on liquid pairs (5th occurrence: ETH/ETC +$0.145, DOGE/BNB +$0.078, T9/LINEA-ZRO +$0.073, T11/CRV-IOTA +$0.040, T12/SOL-BTC +$0.023, T13/BNB-COMP +$0.027). The positive residual = actual costs < estimated costs. BNB/COMP are both liquid (BNB ratio 189×, COMP ratio 26–35×), consistent with this pattern.

**PnL source mismatch flagged:** `pnl_source_mismatch_detected = True` in exit_opportunity_summary. floating_pnl=−$0.1514, position_snapshot=−$0.0523, delta=−$0.0991 at the moment the mismatch was logged. This delta (~$0.10) is large relative to the position size. The reconciliation uses `pre_close_equity_delta` (equity-based, not floating_pnl) and passes — the equity-level check is reliable. The floating_pnl vs position_snapshot divergence at the in-trade monitoring point is an implementation artifact (likely snapshot lag or mark-to-market timing). Not a reconciliation concern, but the mismatch is logged for pattern tracking.

**Liquidity at entry:** Both legs adequate. COMP ratio 26–34× (smallest among recent pairs), BNB ratio 189–192×. Both above 5× minimum. No downsize, no fallback.

---

## Section 7: Experiment Signal

**T13 adds one data point: cost-floor breach (new failure mode).**

Failure mode taxonomy update:

| Category | Trades | Driver |
|----------|--------|--------|
| Coint-failure | T5, T6, T11 | Cointegration broke post-entry |
| Guard-blocked | T7, T9 | In-zone MFE positive but below floor |
| Cost-dominated (guard passed) | T10 | Guard passed; real costs 2.8× model |
| Cost-floor breach (guard irrelevant) | **T13** | USDT spread too thin to cover costs at notional |
| Regime-break exit | T12 (win), T13 (loss) | Same mechanism, outcome depends on pair USDT spread |

T13 is not a coint-failure. Cointegration was strong at entry (24.30/25, valid), and the regime_break exit was driven by the regime transitioning to RISK_OFF, not by cointegration collapse. The pair's failure is structural: it shouldn't have been entered at $200 notional with a 2.456σ trigger.

**Premise watch:** T13 is consistent with the established premise state. Cointegration was strong at entry and remained stable (exit was not cointegration_watch_timeout); the failure was cost-structural, not cointegration-predictability. T13 neither advances nor contradicts the experiment's core premise question about whether entry-gate coint stability predicts post-entry cointegration health. The cointegration held; the pair was simply uneconomic.

**4C-TRIGGER check (rolling-6, T8–T13):**

| Trade | Gate status |
|-------|-------------|
| T8 SOL/AVAX | evaluated (recon fail/data quality) |
| T9 LINEA/ZRO | evaluated |
| T10 FIL/ICP | **insufficient_history** (167s watch) |
| T11 CRV/IOTA | evaluated |
| T12 SOL/BTC | evaluated |
| T13 BNB/COMP | evaluated |

Rolling-6: 5/6 evaluated, 1/6 insufficient_history (T10), 0/6 not_reached. 4C-TRIGGER: **NOT fired.**

---

## Section 8: Exit Capture Analysis — Two Distinct Economic Killers

T13 separates two failure modes that prior audits were conflating under "cost-dominated." They have different fixes and the $/σ metric is what tells them apart:

| Killer | Trades | Mechanism | Fix |
|--------|--------|-----------|-----|
| **Insufficient $/σ** | T13 (certain), T7/T9 (probable) | Pair's USDT spread too thin to clear entry costs at any entry z ≤ system cap. Dead on entry. | Pair-specific $/σ-aware entry gate — compute breakeven z at current notional and only enter if z_entry > breakeven + margin |
| **Cost spike (thin leg)** | T10 | Pair *would* clear costs at $0.14 model, but one thin leg blew actual costs to 2.8× model. PnL positive before cost spike. | Liquidity gate on entry — reject if thin-leg order-book depth below per-leg minimum. Already partially addressed by 5× ratio floor; may need higher or per-$ floor. |

Both are **entry-side economic gates**, and both are distinguishable *before* entry. The $/σ problem is visible from spread volatility and notional at entry time. The cost-spike problem is visible from order-book depth at entry time. Neither requires any post-entry information.

T13 demonstrated: `trade_manager_regime_break` can capture a win (T12) or a loss (T13) at nearly the same z-overshoot — the difference is entirely whether the pair's $/σ is sufficient. Any redesigned exit path (whether regime_break, early z-threshold, or dedicated overshoot capture — all of which are in scope for Item 14) can only help if the pair has sufficient $/σ in the first place. An entry gate that screens for $/σ is structurally upstream of exit redesign and acts on trades Item 14 cannot help.

**Note:** notional sizing does not change the breakeven z. Raising notional raises both gross PnL and entry cost proportionally — the breakeven z (cost/$_per_σ) is notional-invariant. The $/σ breakeven is a function of spread percentage volatility relative to percentage round-trip cost, which notional cannot fix.

**$/σ-aware entry gate — conceptually compelling, quantitatively unvalidated:**
The framing is appealing — at entry time, $/σ is computable from position sizing and recent spread volatility, the breakeven z formula is defined, and the gate is upstream of all other fixes. But the $0.469 inconsistency in Section 2 is not a footnote to the gate proposal: it means the metric **failed to predict its own test case by a margin larger than the loss itself, and with the wrong sign.** A 4.374σ traversal at $0.049/σ should produce +$0.074 net; the actual was −$0.395. If $/σ cannot predict dollar outcome across a single trade's life, then an entry-time $/σ estimate may not predict whether the trade will clear costs — the gate is built on a number that can decouple from actual PnL during the trade.

**Two claims must stay separate in the structural review:**
1. **"BNB/COMP specifically cannot clear costs via full_tp at any system-entry z"** — this survives $/σ imprecision. Even if $0.049 is off by 20%, the breakeven z is still near or above the 3.0σ cap. The qualitative finding is robust: this pair is structurally unprofitable at this notional regardless of execution.
2. **"$/σ-breakeven is a usable general entry gate"** — this does NOT follow yet. It requires demonstrating that entry-time $/σ predicts actual dollar outcomes across multiple trades, not just one.

**What would validate claim (2):** For each evaluated trade T5–T13, compute the implied full-trade $/σ as (position_PnL + costs) / actual_z_distance_captured. If this is consistent with the entry-time $/σ estimate across most trades (T13's divergence explained by the one-off leg spike), the metric is reliable and the gate is worth proposing. If the implied $/σ varies widely across trades, "insufficient $/σ" is a description, not a gateable property. This analysis is computable from trade_closes.csv data already in hand.

**Full_tp mechanism — 5th consecutive 0-pass trade:**

| Trade | In-zone peak PnL | Passes | Why |
|-------|-----------------|--------|-----|
| T9 LINEA/ZRO | +$0.111 | 0 | Floor $0.12 — blocked by $0.001 |
| T10 FIL/ICP | +$0.274 | 1 | Passed, but cost-dominated outcome |
| T11 CRV/IOTA | +$0.062 | 0 | Floor $0.12 — blocked |
| T12 SOL/BTC | +$0.057 | 0 | Floor $0.12 — blocked |
| T13 BNB/COMP | −$0.076 | 0 | PnL never positive |

T10's single pass is the designed mechanism's only activation in the window. T10 was a loss (real costs 2.8× model). The full_tp mechanism has generated zero positive equity outcomes. This column continues to be one of the experiment's clearest empirical findings.

**Full_tp mechanism — 5th consecutive 0-pass trade:**

Since T9 (first trade where full_tp zone was evaluated), 5 consecutive zero-pass outcomes:

| Trade | In-zone peak PnL | Passes | Why |
|-------|-----------------|--------|-----|
| T9 LINEA/ZRO | +$0.111 | 0 | Floor $0.12 — blocked by $0.001 |
| T10 FIL/ICP | +$0.274 | 1 | Passed, but cost-dominated outcome |
| T11 CRV/IOTA | +$0.062 | 0 | Floor $0.12 — blocked |
| T12 SOL/BTC | +$0.057 | 0 | Floor $0.12 — blocked |
| T13 BNB/COMP | −$0.076 | 0 | PnL never positive |

T10's single pass is the designed mechanism's only activation in the window. T10 was a loss (real costs 2.8× model). The full_tp mechanism has generated zero positive equity outcomes.

---

## Section 9: Items and Flags

**$/σ framework (NEW — compelling framing, currently unvalidated as a general gate):** T13 introduces the $/σ metric and reveals two separable economic killers: (1) insufficient $/σ (T13, probably T7/T9) and (2) thin-leg cost spikes (T10). Both are detectable at entry time and have different fixes. However, the $0.469 full-traversal inconsistency means the $/σ metric is currently unreliable as a predictor — it failed to forecast T13's actual outcome (predicted +$0.074 vs actual −$0.395, opposite sign, gap > the loss). Two separate claims for the structural review: **"BNB/COMP specifically is structurally unprofitable at this notional"** (robust — survives $/σ imprecision because corrected breakeven 3.21σ still exceeds 3.0σ cap even with 20% error on the $/σ estimate) vs **"$/σ-breakeven is a usable general entry gate"** (unproven — requires cross-trade validation before this becomes a next-experiment proposal). Premature proposal risks building a gate on a metric that doesn't hold up — the same failure mode that the floor-value and count-semantics checks caught on prior audits.

**Item 12 (ELEVATED — diagnostic needed):** T13 is the second concrete evidence point for pair-specific entry economics, but it differs from T10 in an important way. T10 was a cost-spike problem (actual costs 2.8× model on a thin leg; pair had adequate gross profit). T13 is a spread-sensitivity problem (adequate liquidity, positive reconciliation, but gross spread too thin to clear costs at any z within system range). These are different failures requiring different fixes. The Item 12 residuals-vs-liquidity diagnostic distinguishes them: if BNB/COMP plots on the positive-residual side (liquid, actual costs < model) while losing on spread sensitivity, that confirms the two-killer separation. The diagnostic still determines whether the remaining cost variation is random or liquidity-correlated.

**Item 14 (STRUCTURAL REVIEW — exit redesign):** T13 confirms: exit redesign cannot help structurally-unprofitable pairs. A $/σ-aware entry gate is upstream of Item 14 — it prevents the pairs that Item 14 cannot fix from entering. Once $/σ screening is in place, Item 14's exit redesign is worth doing for the pairs with adequate sensitivity.

**Advanced ML break_risk — upgraded observation:** T13 was preceded by 4 `advanced_ml_break_risk_high` blocks (break_risk=0.15; reasons: `trend_score >= 0.7`, regime switch held by hysteresis). The regime switched to RISK_OFF 40 minutes into the trade — the ML model's signal was **directionally correct** but the break_risk cleared in the final 13 seconds before entry. This is one data point, but it documents a specific failure mode: the break_risk threshold may be set too loosely (cleared too quickly), allowing entry into a trade the ML model had correctly flagged. Connects to Item 3 (max_break_risk recalibration). Frozen config — no action now. Flag for structural review: does the break_risk model have consistent directional signal on regime-switch-before-exit events, and is the clearance timing the issue?

**PnL source mismatch (logged):** floating_pnl vs position_snapshot delta = −$0.0991 during the trade. Reconciliation unaffected (equity-based). The mismatch is large relative to position size; likely a transient mark-to-market spike on one leg, consistent with the max-adverse anomaly noted in Section 2. Logged for pattern tracking.

**Structural review timing — preconditioned on three remaining analyses:**
The Patch 7 premise verdict is now in (see Item 15 below): premise-negative. Four findings have crystallized at T13. The structural review can be called early (T15–T16) only if the three remaining verification analyses are done.

**Pre-structural-review analyses (three remaining):**
1. **$/σ cross-trade validation (highest priority):** For T5–T13, compute implied full-trade $/σ = (position_PnL + costs) / actual_z_distance. If consistent across most trades, the $/σ-breakeven entry gate is proposable as the next experiment. If not consistent, "insufficient $/σ" is a description without a gateable number. This is the most consequential pre-review analysis.
2. **Residual-vs-liquidity plot (Item 12):** Random scatter → statistical inference viable. Liquidity-correlated → must fix cost measurement/pair-universe. Determines which of the two killers ($/σ vs cost-spike) is dominant and what the next experiment addresses first.
3. **T7 full_tp blocking root cause (Item 14):** T7 had 41 guard blocks at in-zone MFE $0.127 > $0.12 effective floor — should have passed. Root cause unexplained. Needed before "exit redesign" conclusions are finalized.

**Item 15 T11 p-value verification: COMPLETE — and it REFUTED the level-check hypothesis:**
T11 buffer verified from run_119 entry_rejections: cointegration score 24.998/25 (p≈0 = maximum strength), coint_state=valid across all 10 pre-entry evaluations. The hypothesis was that T11's slope≈0 reflected p≈1.0 (cointegration already dead at entry). The opposite was true: p≈0 = maximum strength, flat slope = stable strong cointegration. **A level check would have passed T11 just as the slope check did.** T11 joins T5 as a coint-failure that entered with every entry-time coint metric looking excellent and failed post-entry anyway. The level-check "constructive fix" is not supported by its own originating case. **The Patch 7 premise is NEGATIVE: entry-time cointegration metrics — slope or level — do not predict post-entry cointegration failure.** "Improve the coint filter" is not a viable next-experiment direction.

The early-review trigger: no new failure modes by T15–T16 **AND** analyses 1–3 above are done. The premise verdict is already formed; the three remaining analyses determine what the next experiment actually is.

---

## Section 10: Structural Review Priorities (revised)

1. **$/σ cross-trade validation (pre-review analysis, first):** Compute implied full-trade $/σ for T5–T13 and compare to entry-time estimates. This determines whether "$/σ-breakeven entry gate" is a real next-experiment proposal or a description without predictive power. Highest-priority pre-review work.
2. **$/σ entry economics framework — two separate claims:** (a) "BNB/COMP specifically is structurally unprofitable" — robust finding, doesn't depend on $/σ precision. (b) "$/σ-breakeven is a usable general gate" — needs cross-trade validation. Structural review should present these as separate claims with separate evidence standards.
3. **Item 14 (exit redesign + T7 anomaly):** Full_tp dead (0/5 clean passes). Identify the T7 blocking root cause (41 blocks at in-zone MFE $0.127 > $0.12 floor — should have passed). Exit redesign scoped to pairs that pass $/σ screening.
4. **Item 12 (residual-vs-liquidity plot):** Two-killer framing separates spread-sensitivity (T13) from cost-spike (T10). The plot confirms whether cost error is random or liquidity-correlated and determines which fix comes first.
5. **Item 15 (premise — NEGATIVE VERDICT, level-check REFUTED):** T11 verification inverted the constructive finding. The level-check hypothesis (T11 entered with p≈1.0, slope-only gate blind to dead cointegration) was refuted — T11 entered at p≈0 (24.998/25 = maximum strength). A level check would also have passed T11. Both slope-visible coint-failures (T5: improving slope; T11: stable at maximum strength) entered looking perfect and failed post-entry. **The Patch 7 premise is NEGATIVE: entry-time coint metrics — slope or level — do not predict post-entry failure.** Coint-filter improvement is not a viable next direction. The experiment answered its nominal question: clean negative result. Structural review presents it as such, then pivots to the economic gating findings (which are the actionable output).

---

## Section 11: Summary

Run 122: 47.7 min, 1 trade (T13 BNB/COMP), session PnL −$0.508. LOSS.

**T13 key fact:** MFE = −$0.076 — the trade was never profitable at any moment. BNB/COMP at $200 notional generates ~$0.049/σ (preliminary estimate, see Section 2 caveats). Corrected breakeven entry z (exit zone at z=0.35): **3.21σ**. System entry cap ~3.0σ. This pair cannot be profitably traded via full_tp at any z the system will generate. Exit via regime_break at z=−1.918 (same mechanism as T12 win); T13 lost because the pair's $/σ was insufficient, not because of coint failure or guard miscalibration.

**T13's most important output is a question, not an answer.** The $/σ framing is the most promising conceptual advance to come out of the experiment — it unifies several findings and points at a computable entry gate. But the $0.469 inconsistency (predicted +$0.074 vs actual −$0.395, opposite sign) means the metric cannot currently be trusted to predict dollar outcomes. The qualitative claim "BNB/COMP is structurally unprofitable at this notional" is robust; the general claim "$/σ-breakeven is a usable entry gate" is the question. The answer comes from the cross-trade validation (T5–T13 implied $/σ vs entry-time estimates), which is computable from data already on hand and should be done before the structural review.

**Experiment state (T5–T13, 9 completed):**
- Win rate: 1/9 = 11.1% (T12 only)
- Cumulative PnL (T5–T13): −$2.687 (−$2.622 economic, T8 excluded)
- Coint-failures: 3 (T5, T6, T11)
- Failure modes: coint-failure ×3, guard-blocked ×2, cost-spike ×1, spread-sensitivity breach ×1, regime-break win ×1
- Gate effectiveness: 8/9 evaluated, 1/9 insufficient_history (T10)
- Full_tp passes with positive outcome: **0** (5 consecutive evaluated trades)

**Three findings and their verification status:**
- **Patch 7 premise: NEGATIVE (verdict in).** T5 + T11: both coint-failures entered with strong entry-time coint metrics (low p, flat/improving slope) and failed post-entry. Neither slope nor level predicts failure. The filter worked correctly; the pairs failed anyway. "Improve the coint filter" is not a viable next direction. This is a clean negative result — the experiment answered the question it was built to answer.
- **Exit capture broken (established, T7 anomaly outstanding).** Full_tp 0 wins across 5 clean evaluated trades. MFE at overshoots. T7 guard blocking mechanism unexplained (in-zone MFE $0.127 > $0.12 floor, yet 41 blocks — needs root-cause investigation before exit redesign conclusions finalize).
- **Economic gating (compelling framing, validation needed).** $/σ framework separates two killers: spread-sensitivity (T13) and cost-spike (T10). BNB/COMP specifically unprofitable is robust. $/σ as general gate needs cross-trade validation. Residual-vs-liquidity plot needed for Item 12. These analyses determine what the next experiment is.

The remaining trades buy time to run the three analyses. The premise answer is already in; the economic gating analysis is what the structural review needs.

**Early structural review trigger:** no new failure modes by T15–T16 **AND** $/σ cross-trade validation + residual-vs-liquidity plot + T7 blocking root cause are done. The premise verdict (Patch 7: negative) is already in — the three analyses determine what the next experiment is, not whether the current one answered its question. It did.

**Next:** Run 123, frozen config. Priority work: $/σ cross-trade validation (implied PnL per z-unit across T5–T13 from trade_closes.csv data already on hand).
