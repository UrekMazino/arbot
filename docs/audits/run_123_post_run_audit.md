# Post-Run Audit: run_123 — T14 SOL/ALGO + $/σ Cross-Trade Validation

**Run:** run_123_20260527_214231  
**Trade:** T14 (10th in Patch 7.1 experimental window)  
**Status:** stopped (normal)  
**Session duration:** 41.3 min | 6 pairs | 5 switches | 1 trade  
**Session PnL:** −$0.604 (equity)  
**Audit date:** 2026-05-28

---

## 1. Session Summary

Short session: entered T14 on SOL/ALGO at 40.8 min into the run, exited 20.3 min later via `cointegration_lost`. The session is unremarkable on its own — T14 is the 4th coint-failure in the Patch 7.1 window and adds a second `insufficient_history` gate event.

The more important work this session produces is the **$/σ cross-trade validation** across T5–T14. The full data is now available. The validation result is the headline of this audit.

---

## 2. T14 Trade Analysis — SOL/ALGO

**Entry:** z = +2.279, notional $200, side = long_positive_short_negative  
**Exit:** z = +0.481, hold = 20.27 min, exit_reason = `cointegration_lost`  
**Position PnL:** −$0.481 | **Equity change:** −$0.604

### 2.1 Gate Status: insufficient_history (second in window)

`entry_coint_stability_evaluated_count = 0` — no slope available.

This is the second `insufficient_history` event in the Patch 7.1 window (T10 was the first). But the mechanism appears different:

| | T10 FIL/ICP | T14 SOL/ALGO |
|---|---|---|
| Watch time before entry | 167s (2.8 min) | ~20+ min (full hold) |
| Likely cause | Physical ceiling — < 5 samples in 167s at 60s interval | p_value returned `None` throughout monitoring → buffer never populated |

T10 hit a hard time floor — the pair activated 167s before entry, limiting samples to 2. Patch 7.1 can't fix that. T14 had adequate time but apparently received no valid p_values during pre-entry monitoring, so the buffer never accumulated. This is a new failure mode for the gate: **time-adequate but p_value-starved**. Mechanism unconfirmed; worth flagging for investigation.

### 2.2 Trade Path

| Metric | Value |
|---|---|
| Entry z | +2.279 |
| Exit z | +0.481 |
| z_distance (entry → exit) | 1.798σ |
| z at MFE (max_favorable_pnl) | +1.282 |
| MFE (position PnL) | **−$0.003** (never profitable) |
| z at MAE (max_adverse_pnl) | +0.269 |
| MAE (position PnL) | −$0.538 |
| Exit position PnL | −$0.481 |

Two observations:
1. **MFE = −$0.003.** The position was essentially never profitable. Despite z declining from +2.279 toward zero (the expected favorable direction), the floating PnL stayed negative throughout.
2. **MAE occurred at z = +0.269 (inside the exit zone |z| < 0.35).** The position was most adverse when the spread had reverted the most. This is inverted — dollar PnL moved *opposite* to z-score direction. This connects directly to the $/σ validation below.

**guard_blocked_full_tp_count = 29, full_tp_touched = True.** The guard correctly blocked at negative PnL. These blocks are irrelevant (guard is working; position economics were the issue).

### 2.3 Reconciliation

| Field | Value |
|---|---|
| trade_pnl (position PnL) | −$0.4807 |
| equity_change | −$0.6039 |
| fees | $0.10 |
| slippage | $0.04 |
| funding | $0.00 |
| unexplained | **+$0.017** |
| basis | pre_close_equity_delta |
| pass/fail | **PASS** |

Unexplained = +$0.017: actual costs slightly below model. **Seventh positive residual on a liquid pair** (SOL and ALGO are reasonably liquid). Pattern now N=7, all on liquid pairs.

---

## 3. $/σ Cross-Trade Validation — T5 through T14

This is the primary analysis output of this audit.

### 3.1 Methodology

For each trade:
- **position_pnl** = `trade_pnl` from `reconciliation_checks.csv` (the raw mark-to-market of the position, before costs)
- **Δz** = |entry_z − exit_z| (total z-score traversal, entry to exit)
- **implied_$/σ** = position_pnl / Δz

The $/σ metric was proposed as an entry gate: if implied_$/σ × (entry_z − exit_zone) < costs, the pair cannot clear entry costs and should be rejected. For the gate to work, $/σ must be a stable, positive, predictable property of each pair at entry time.

### 3.2 Full Table (T5–T14)

| # | Pair | Exit reason | entry_z | exit_z | Δz (σ) | position_PnL | implied_$/σ | Notes |
|---|---|---|---|---|---|---|---|---|
| T5 | FIL/FLOKI | coint_lost | +2.055 | +2.150 | **0.095** | −$0.323 | −$3.38/σ | Spread widened adversely; 0.10σ move; **uninformative** |
| T6 | DOGE/SUI | coint_lost | −2.210 | −1.669 | 0.541 | −$0.676 | −$1.25/σ | Coint-failure; partial adverse move; limited informative value |
| T7 | BTC/HBAR | normal | −2.274 | +2.116 | **4.390** | −$0.007 | **≈ $0/σ** | Full traversal + overshoot; near-zero dollar sensitivity |
| T8 | SOL/AVAX | normal | −2.120 | −0.216 | 1.905 | +$0.129 | +$0.068/σ | ⚠️ DATA QUALITY: fees=0, basis=position_pnl; **excluded** |
| T9 | LINEA/ZRO | normal | −2.244 | +0.737 | **2.981** | −$0.006 | **≈ $0/σ** | Full traversal + overshoot; near-zero dollar sensitivity |
| T10 | FIL/ICP | normal | +2.063 | −2.056 | **4.119** | **+$0.274** | **+$0.067/σ** | Full traversal; positive $/σ; costs were the problem (2.8×) |
| T11 | CRV/IOTA | coint_timeout | +2.178 | −0.244 | 2.422 | −$0.399 | **−$0.165/σ** | Coint-failure; path dependency (z re-expanded to +1.07 mid-trade) |
| T12 | SOL/BTC | normal (regime) | +2.076 | −2.066 | **4.142** | **+$0.143** | **+$0.035/σ** | Full traversal; positive $/σ; only win in window |
| T13 | BNB/COMP | normal (regime) | +2.456 | −1.918 | **4.374** | −$0.395 | **−$0.090/σ** | Full traversal + overshoot; **normal exit with negative $/σ** |
| T14 | SOL/ALGO | coint_lost | +2.279 | +0.481 | 1.798 | −$0.481 | −$0.267/σ | Coint-failure; partial reversion; sign inversion vs z-path |

### 3.3 Findings

**Finding 1: $/σ is not a stable, predictable metric.**

Among the five normal-exit trades with meaningful Δz (T7, T9, T10, T12, T13 — excluding T8 data quality issue):

| Trade | Pair | Δz | position_PnL | implied_$/σ |
|---|---|---|---|---|
| T7 | BTC/HBAR | 4.39σ | −$0.007 | ≈ $0 |
| T9 | LINEA/ZRO | 2.98σ | −$0.006 | ≈ $0 |
| T10 | FIL/ICP | 4.12σ | +$0.274 | +$0.067 |
| T12 | SOL/BTC | 4.14σ | +$0.143 | +$0.035 |
| T13 | BNB/COMP | 4.37σ | −$0.395 | **−$0.090** |

The range spans −$0.090/σ to +$0.067/σ. On three of five normal-exit trades, the position earned essentially nothing (T7, T9) or actively lost money (T13) despite large favorable z-traversals. **The $/σ metric cannot be predicted from entry-time information and is not stable across pairs.**

**Finding 2: T13 is not an outlier — T14 confirms the pattern.**

T14 (SOL/ALGO) shows the same sign inversion: z decreased from +2.279 toward +0.269 (1.98σ of favorable z-movement by definition), while the position PnL went from −$0.003 to −$0.538 — becoming *more* adverse as z reverted. Dollar PnL moved **opposite** to the z-score direction. This is the same phenomenon as T13 but observable in the intra-trade path, not just the start-to-end comparison.

**Finding 3: Root cause — OLS beta vs notional-balanced sizing mismatch.**

The z-score is computed using an OLS hedge ratio β (the statistical relationship between the two legs). Positions are sized by equal dollar notional ($200 per leg regardless of β).

When β ≈ 1 (pairs with similar dollar volatility per unit), z-movement and dollar PnL track each other (T10 FIL/ICP, T12 SOL/BTC). When β >> 1 or β << 1, they diverge. A z-score "reversion" can correspond to a dollar *loss* if the notional-balanced position is not the statistical hedge.

Evidence:
- T12 SOL/BTC: both major assets, similar price scale, β probably close to dollar-balanced. Positive $/σ. ✓
- T10 FIL/ICP: both mid-tier assets, similar volatility. Positive $/σ. ✓
- T7 BTC/HBAR: BTC very large, HBAR very small. Near-zero dollar sensitivity — z moves don't register in dollars at $200 notional.
- T9 LINEA/ZRO: both small altcoins with similar volatility profiles. Near-zero — spread moves in z-space are tiny in dollars.
- T13 BNB/COMP: different volatility and price scaling. Negative $/σ — dollar PnL anti-correlated with z-movement.

The $/σ metric is **not a property of the pair at entry time** — it depends on the alignment between the statistical hedge ratio and the actual dollar position, which varies with market conditions and is not estimable from static pair characteristics.

**Finding 4: The BNB/COMP qualitative finding survives; the quantitative formula does not.**

The corrected breakeven formula (3.21σ based on $/σ = $0.049/σ) is numerically wrong — the $/σ estimate was based on an early-trade approximation and the metric itself is unreliable. However, the qualitative finding is confirmed by direct observation: BNB/COMP at $200 notional produced MFE = −$0.076 (never profitable) with a 4.374σ full traversal. The pair *empirically cannot make money* under current conditions. The mechanism is the beta-mismatch, not an insufficient spread in the z-score sense.

**Finding 5: $/σ as a DESCRIPTION survives; $/σ as an ENTRY GATE does not.**

The "two-killer" framework from the run_122 audit remains valid as a taxonomy:
- Type 1: Insufficient dollar sensitivity — pair earns near zero or negative despite favorable z-moves (T7, T9, T13, T14)
- Type 2: Thin-leg cost spike — pair has positive $/σ but real costs exceed model (T10)

These are distinct economic failure modes. The Type 1 description is accurate. What does NOT hold is the proposed gate mechanism: *entry_z ≥ (costs / $/σ) + exit_zone*. The gate requires stable positive $/σ at entry time, which the validation shows does not exist.

### 3.4 Verdict

**$/σ-breakeven entry gate: NOT PROPOSABLE in current form.**

The validation kills the gate proposal — not by showing the threshold is hard to calibrate, but by showing the underlying metric (position_pnl / Δz) is not stable, not consistently positive on normal-exit trades, and in some cases has the wrong sign. A gate built on this metric would block trades that have positive $/σ and pass trades with negative $/σ (which are the bad ones), since $/σ cannot be estimated correctly from entry-time pair characteristics.

**Prerequisite for any $/σ gate: beta-adjusted position sizing.** If positions were sized proportional to OLS β (not equal dollar notional), z-score movement would map linearly to dollar PnL, and $/σ would become a stable, predictable property. This is a significant architecture change, not a threshold adjustment.

---

## 4. What This Changes

### 4.1 Next experiment direction

The $/σ gate proposal is off the table. The next experiment candidates must come from different reasoning:

1. **Liquidity-gating / pair universe restriction** (Item 12): If dollar sensitivity and cost behavior both correlate with pair liquidity, then liquidity-based pair selection addresses both Type 1 and Type 2 failure modes simultaneously. This is the first analysis that needs to complete before the structural review.

2. **Beta-adjusted sizing**: Align position notional with OLS hedge ratios. Makes z-score economically meaningful in dollar terms. Large architecture change; requires careful validation.

3. **Exit redesign** (Item 14): Still valid as an independent question, but the structural review should not assume $/σ-based screening is a prerequisite fix.

### 4.2 Pair-beta mismatch as primary economic finding

The structural review's economic headline is now more precise than "spread capture at $200 notional doesn't clear costs":

**At equal dollar notional ($200/leg), the z-score does not reliably correspond to dollar PnL for pairs where OLS β ≠ 1. The wins (T12) and the profitable positions (T10) occur on pairs where β is approximately dollar-balanced. The losses on normal-exit trades (T7 near-zero, T9 near-zero, T13 negative) occur on pairs where β diverges.**

This is a structural architecture point — the strategy is sound in z-score space but the economic realization of z-moves depends on position sizing that the system doesn't currently implement.

---

## 5. Running Metrics Update

### 5.1 Trade counter

| Metric | Value |
|---|---|
| Total trades (T1–T14) | 14 |
| Patch 7.1 window trades (T5–T14) | 10 |
| Coint-failures (window) | **4** (T5, T6, T11, T14) |
| Normal exits (window) | 6 (T7, T8, T9, T10, T12, T13) |
| Wins | 1 (T12) |
| Win rate (window) | 10% |
| Insufficient_history events | **2** (T10, T14) |

Coint-failure rate: 4/10 = 40% (was 3/9 = 33% after T13). Still well above the Patch 7 null criterion (30%).

### 5.2 Gate-inactivity trigger (4C-TRIGGER)

Rolling-6: **T9, T10, T11, T12, T13, T14**

| Trade | Gate status |
|---|---|
| T9 LINEA/ZRO | evaluated |
| T10 FIL/ICP | **insufficient_history** |
| T11 CRV/IOTA | evaluated |
| T12 SOL/BTC | evaluated |
| T13 BNB/COMP | evaluated |
| T14 SOL/ALGO | **insufficient_history** |

Result: 4/6 evaluated, **2/6 insufficient_history**, 0/6 not_reached. **NOT fired** (trigger fires on not_reached; 0 not_reached).

Two insufficient_history events in the rolling-6 is noteworthy. Both T10 and T14 had evaluated_count=0 — neither via the same mechanism (T10: time-starved, T14: p_value-starved). Gate coverage is degrading at the tail. Worth flagging at structural review if a third insufficient_history appears.

### 5.3 Reconciliation summary (cumulative, window)

| Trade | Result | Unexplained | Pattern |
|---|---|---|---|
| T5 FIL/FLOKI | FAIL | −$0.093 | Meme-token cost overrun |
| T7 BTC/HBAR | PASS | +$0.040 | Liquid pair: actual < estimated |
| T8 SOL/AVAX | FAIL | −$0.194 | Data quality (fees=0, timing) |
| T9 LINEA/ZRO | PASS | +$0.073 | Liquid pair: actual < estimated |
| T10 FIL/ICP | FAIL | −$0.255 | Thin leg (FIL 575 USDT at entry) |
| T11 CRV/IOTA | PASS | +$0.040 | Liquid pair |
| T12 SOL/BTC | PASS | +$0.023 | Liquid pair |
| T13 BNB/COMP | PASS | +$0.027 | Liquid pair |
| T14 SOL/ALGO | PASS | **+$0.017** | Liquid pair — 7th positive |

Positive residual pattern: **7 occurrences, all liquid pairs**. Negative residuals: all thin-leg or meme-token pairs. Pattern is consistent and suggestive of liquidity-correlated cost bias. (Confirmation requires Item 12 residual-vs-liquidity plot.)

### 5.4 MFE update

| Trade | In-zone MFE | Note |
|---|---|---|
| T5 | −$0.082 | Never profitable |
| T6 | −$0.035 | Never profitable |
| T7 | +$0.127 | Blocked (41 blocks) |
| T8 | blank | Data quality |
| T9 | +$0.111 | Blocked ($0.001 below floor) |
| T10 | +$0.274 | Passed; costs 2.8× |
| T11 | +$0.062 | Blocked (446 blocks); coint-timeout |
| T12 | +$0.057 in-zone | Blocked; win via regime_break at z=−2.066 |
| T13 | **−$0.076** | Never profitable ($/σ inversion) |
| **T14** | **−$0.003** | Never profitable ($/σ inversion) |

T13 and T14 both had negative MFE throughout — the position never reached positive territory despite z-score "reversion." Both are beta-mismatch pairs.

---

## 6. Pre-Review Analysis Status

| Analysis | Status | Result |
|---|---|---|
| **1. $/σ cross-trade validation** | **COMPLETE** | **NEGATIVE — metric unstable, gate not proposable** |
| 2. Residual-vs-liquidity plot (Item 12) | PENDING | Will determine if cost bias is random or liquidity-structured |
| 3. T7 full_tp blocking root cause (Item 14) | PENDING | 41 blocks at in-zone MFE $0.127 > $0.12 effective floor |
| Item 15 T11 p-value check | COMPLETE | REFUTED — cointegration was at maximum strength at T11 entry |

Early structural review is possible at **T15–T16** once analyses 2 and 3 complete. The $/σ validation result (now complete, negative) does not block the early review — it changes what the review discusses. The premise-negative finding (Patch 7) and the beta-mismatch finding (this audit) are both solid enough to anchor the structural review document.

**The case for early review is now stronger:** All four crystallized findings are in place. Analyses 2 and 3 will sharpen the economic framing but are unlikely to change the top-line structural verdict. The remaining 10 trades primarily buy time to run those analyses.

---

## 7. Summary

**T14** is the 4th coint-failure in the Patch 7.1 window. Insufficient gate history (second occurrence, different mechanism from T10). Reconciliation PASS with +$0.017 positive residual. Unremarkable operationally.

**$/σ cross-trade validation** is the main output. The verdict: the metric is not stable, not predictable from entry-time pair characteristics, and in two normal-exit trades (T13, T14) the dollar PnL moved opposite to the z-score direction. The $/σ-breakeven entry gate is not proposable without beta-adjusted position sizing. The root cause is an architectural mismatch: z-score computed with OLS hedge ratios; positions sized by equal dollar notional.

**What changes:** Next experiment direction shifts away from $/σ-gating and toward liquidity-based pair selection (Item 12) or beta-adjusted sizing. The structural review headline is now more specific: not "costs exceed spread at $200 notional" but "z-score dollar realization is beta-dependent, and equal-notional sizing makes it pair-specific and unpredictable."

**Pre-review checklist:** 1 of 3 analyses complete. Two remaining: residual-vs-liquidity plot (Item 12) and T7 full_tp blocking root cause (Item 14). Target: complete both before T16, then call early structural review.
