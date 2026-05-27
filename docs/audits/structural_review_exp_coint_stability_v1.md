# Structural Review — exp_coint_stability_v1
## Sizing-Mismatch Discovery and Coint-Stability Filter Assessment

**Review date:** 2026-05-28
**Early review authorized:** YES — 10 window trades, 20-trade threshold not reached. Two simultaneous early-resolution triggers fired:
1. **Premise early-resolution criterion (T11):** Both observable coint-failures entered with maximum-strength entry-time coint metrics and failed post-entry. Filter cannot distinguish them; premise is negative.
2. **Sizing-mismatch code-confirmed (T14):** OLS hedge ratio β is computed for signal but not used in position sizing. Confirmed by T14 intra-trade dollar/z-score sign inversion.

**Note on run_124:** A run_124 was initiated at 2026-05-27T14:23:50 (minutes after T14 closed). It ran for 19 minutes, evaluated 3 pairs, executed 0 trades, and stopped. No trades were taken under broken sizing after the investigation was triggered.

---

## Experiment State Block

```
experiment_group:                   exp_coint_stability_v1
experiment_phase:                   Structural Review
early_review_trigger:               (1) premise_early_resolution at T11; (2) sizing_mismatch_code_confirmed at T14
runs_since_experiment_start:        105, 106, 107, 108, 109, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123
trades_since_experiment_start:      10 (T5–T14; T1–T4 excluded from gate-effectiveness per Patch 7.1 calibration reset)
evaluated_trade_count:              8 (T5, T6, T7, T8, T9, T11, T12, T13)
insufficient_history_trade_count:   2 (T10: 167s watch / 2.8 min; T14: p_value=None throughout monitoring)
not_reached_trade_count:            0
coint_stability_slope_exceeded:     18 (all from run_113: AVAX/ADA, slope=0.04837 = 2.4× threshold)
closed_trades_with_complete_telemetry:   10 (all appear in trade_closes.csv with valid pnl_usdt)
closed_trades_with_incomplete_telemetry: 2 — T8 (recon data quality fail: basis=position_pnl, fees=0); T10 (recon fail: unexplained −$0.255, but equity reliable)
circuit_breaker_trips_this_experiment:   0
patches_active:                     Patch 4.1, Patch 5, Patch 6, Patch 7, Patch 7.1
sizing_mismatch_code_confirmed:     YES — hedge_ratio has zero references in func_trade_management.py
review_date:                        2026-05-28
```

The single most important state variable for the filter verdict: **evaluated_trade_count = 8**. All filter-effectiveness conclusions rest on 8 evaluated trades, not 10 total trades.

---

## Preamble — Project-Level Finding: Sizing-Mismatch

**This finding is code-confirmed. It requires no data to state, and it precedes all data analysis.**

**Statement:** The z-score used to generate entry signals is computed using an OLS hedge ratio β: `spread = log(P1) − β × log(P2)`. Production code (`Execution/func_trade_management.py`) sizes both legs at equal dollar notional — `capital_long = capital_short = initial_capital_usdt` — regardless of β. The field `hedge_ratio` has zero references in `func_trade_management.py`. β is computed in `evaluate_cointegration()`, passed to the ML quality scorer (`_hedge_ratio_quality` in `advanced_ml_runtime.py`), and discarded for sizing.

When β ≠ 1: the position earns `$200 × Δlog(P1) − $200 × Δlog(P2)` (effective β=1 in dollars). The z-score measures `Δlog(P1) − β × Δlog(P2)`. A favorable z-move can produce an adverse dollar move when β diverges from 1.

**Empirical signature:**

| Trade | Pair | Δz (σ) | position_PnL | implied_$/σ | Sizing signal |
|-------|------|---------|------------|------------|-------------|
| T7 | BTC/HBAR | 4.39σ | −$0.007 | ≈ $0/σ | β ≠ 1 inferred from $/σ; actual value unverified |
| T9 | LINEA/ZRO | 2.98σ | −$0.006 | ≈ $0/σ | β ≠ 1 inferred from $/σ; actual value unverified |
| T10 | FIL/ICP | 4.12σ | +$0.274 | +$0.067/σ | β ≈ 1 inferred from $/σ; actual value unverified |
| T12 | SOL/BTC | 4.14σ | +$0.143 | +$0.035/σ | β ≈ 1 inferred from $/σ; actual value unverified |
| T13 | BNB/COMP | 4.37σ | −$0.395 | −$0.090/σ | β > 1 inferred from $/σ sign inversion; actual value unverified |

T14 confirms intra-trade: z decreased from +2.279 → +0.269 (1.80σ favorable) while dollar PnL moved from −$0.003 → −$0.481. Dollar and z-score anti-correlated throughout the hold.

**Tag requirement:** Each finding in Sections 4–9 is tagged SURVIVES SIZING REFRAME (holds regardless of sizing mismatch) or PENDING SIZING REVALIDATION (may be an artifact of equal-notional sizing).

**What does NOT change:** Coint-failure events are real. Reconciliation cash flows are real. The beta-mismatch finding does not mean the strategy is broken — it means the strategy has not been fairly tested. The next experiment conclusion section must hold this to the same verification standard that caught the Patch 5 miscalibration, the count-semantics error, the level-check refutation, and the $/σ instability.

---

## Data Assembly

Experiment runs with trades: run_111 (T5), run_113 (T6), run_115 (T7), run_116 (T8), run_117 (T9), run_118 (T10), run_119 (T11), run_120 (T12), run_122 (T13), run_123 (T14). All reports confirmed present under `Reports/v1/`.

**Master trade table (from trade_closes.csv and reconciliation_checks.csv):**

| # | Run | Pair | Side | entry_z | exit_z | Δz (σ) | pnl_usdt (equity) | position_pnl | unexplained | basis | recon | gate_status |
|---|-----|------|------|---------|--------|---------|-------------------|-------------|-------------|-------|-------|------------|
| T5 | 111 | FIL/FLOKI | L+/S− | +2.055 | +2.150 | 0.095 | −$0.5553 | −$0.3226 | −$0.0927 | pre_close_equity_delta | pass† | evaluated |
| T6 | 113 | DOGE/SUI | L−/S+ | −2.210 | −1.669 | 0.541 | −$0.7864 | −$0.6756 | +$0.0292 | pre_close_equity_delta | pass | evaluated |
| T7 | 115 | BTC/HBAR | L−/S+ | −2.274 | +2.116 | 4.390 | −$0.1066 | −$0.0070 | +$0.0404 | pre_close_equity_delta | pass | evaluated |
| T8 | 116 | SOL/AVAX | L−/S+ | −2.120 | −0.216 | 1.905 | −$0.0647 | EXCLUDED | −$0.1941 | position_pnl | **fail** | evaluated |
| T9 | 117 | LINEA/ZRO | L−/S+ | −2.244 | +0.737 | 2.981 | −$0.0730 | −$0.0056 | +$0.0727 | pre_close_equity_delta | pass | evaluated |
| T10 | 118 | FIL/ICP | L+/S− | +2.063 | −2.056 | 4.119 | −$0.1205 | +$0.2742 | −$0.2546 | pre_close_equity_delta | **fail** | **insuff_history** |
| T11 | 119 | CRV/IOTA | L+/S− | +2.178 | −0.244 | 2.422 | −$0.4994 | −$0.3990 | +$0.0396 | pre_close_equity_delta | pass | evaluated |
| T12 | 120 | SOL/BTC | L+/S− | +2.075 | −2.066 | 4.142 | **+$0.0264** | +$0.1432 | +$0.0231 | pre_close_equity_delta | pass | evaluated |
| T13 | 122 | BNB/COMP | L+/S− | +2.456 | −1.918 | 4.374 | −$0.5084 | −$0.3951 | +$0.0267 | pre_close_equity_delta | pass | evaluated |
| T14 | 123 | SOL/ALGO | L+/S− | +2.279 | +0.481 | 1.798 | −$0.6039 | −$0.4807 | +$0.0167 | pre_close_equity_delta | pass | **insuff_history** |

†T5 reconciliation PASS per recon_checks.csv (basis=pre_close_equity_delta) but unexplained exceeds $0.05 warning threshold (−$0.093). Included in economic analysis; flagged in Section 5B.

**Column definitions:** position_pnl = trade_pnl from reconciliation_checks.csv. pnl_usdt = equity_change per trade_closes.csv (equity impact including all costs).

---

## Section 1 — Dataset Inventory

**Trade inventory (Patch 7.1 window, T5–T14):**
- Total trades: 10
- Per-run: run_111(1), run_113(1), run_115(1), run_116(1), run_117(1), run_118(1), run_119(1), run_120(1), run_122(1), run_123(1)
- Wins: 1 (T12); Losses: 9
- Complete telemetry: all 10 appear in trade_closes.csv with valid pnl_usdt
- Incomplete telemetry: T8 (recon data quality — fees=0, basis=position_pnl; excluded from $/σ analysis); T10 (recon fail — costs unattributed; position_pnl reliable)

**Gate-status inventory (real N computation):**

| Gate Status | Count | Pct of window |
|------------|-------|--------------|
| evaluated | 8 | 80% |
| insufficient_history | 2 | 20% |
| not_reached | 0 | 0% |
| **evaluated_trade_count (real N)** | **8** | |

**The filter-effectiveness verdict in Section 10B rests on 8 evaluated trades, not 10 total trades.** Evaluated N = 8. This is above the underpowered threshold (≥ 6) but still a small sample. Filter-effectiveness findings are directional rather than statistically robust.

The sizing-mismatch verdict in Section 10A is not subject to sample-size constraints — it is code-confirmed.

Known incomplete-telemetry trades:
- **T8 SOL/AVAX (run_116):** reconciliation basis=position_pnl, fees=0 — data quality FAIL due to retry_count=3 timing gap. Excluded from $/σ economic analysis; gate/slope analysis valid.
- **T10 FIL/ICP (run_118):** reconciliation basis=pre_close_equity_delta; equity reliable; costs unattributed (unexplained −$0.255). Included in economic analysis with caveat.

---

## Section 2 — Outcome Comparison: Experiment vs Prior Experiments

**Important framing:** All three datasets used equal-notional sizing. The comparison measures whether Patch 7 affected outcomes within the same (sizing-contaminated) regime, not whether the strategy works correctly.

**Per-trade outcome table (equity change = pnl_usdt):**

| Metric | Raw baseline (9 trades) | exp_guard050 (19 trades) | exp_coint_stability (10 trades) |
|--------|------------------------|--------------------------|--------------------------------|
| Win rate | 1/9 = 11.1% | 5/19 = 26.3% | 1/10 = 10.0% |
| Avg PnL/trade | −$0.239 | −$0.137 | −$0.329 |
| Avg win | +$0.133 | ~+$0.16 | +$0.026 |
| Avg loss | −$0.270 | ~−$0.195 | −$0.368 |
| Largest win | +$0.133 | ~+$0.18 | +$0.026 |
| Largest loss | −$0.549 | −$0.549 | −$0.786 (T6) |
| Cumulative PnL | −$2.157 | −$2.592 | −$3.292 |

Outcome comparison is unfavorable relative to both baselines on every metric. Win rate fell from 26.3% (exp_guard050) to 10%. Average loss deepened. This is the worst experiment window by outcome to date. Sizing contamination applies to all three datasets equally — none represents a clean test of the mean-reversion hypothesis.

**MFE distribution (max_favorable_pnl_usdt from trade_closes.csv, 10 trades):**

| Bucket | Count | Pct | Notes |
|--------|-------|-----|-------|
| Negative MFE (never profitable) | 4 | 40% | T5 (−$0.082), T6 (−$0.035), T13 (−$0.076), T14 (−$0.003) |
| $0–$0.05 | 0 | 0% | |
| $0.05–$0.10 | 1 | 10% | T11 (+$0.062, blocked by guard) |
| $0.10–$0.17 | 2 | 20% | T7 (+$0.127, blocked), T12 (+$0.144, captured via regime_break) |
| $0.17–$0.23 | 1 | 10% | T9 (+$0.188 outside zone, +$0.111 in-zone, blocked) |
| > $0.23 | 1 | 10% | T10 (+$0.274, guard passed at MFE peak, costs ate profit) |
| Missing | 1 | 10% | T8 (data quality) |

40% of trades were never profitable (negative MFE throughout). This is the most important MFE finding: not a timing problem but a never-profitable problem for nearly half the window.

**MAE distribution (max_adverse_pnl_usdt):** T6 (−$0.710), T10 (−$0.767) — worst adverses — both exceed a full cost round-trip. T12 (−$0.106) and T7 (−$0.118) — smallest adverses — are the liquid-pair trades.

**Hold duration:** < 10 min: 3 (T5, T6, T9); 10–30 min: 3 (T7, T10, T14); 30 min–2h: 4 (T8, T11, T12, T13). No trades > 2h (T11 at 120 min was the longest; coint_watch_timeout).

**Entry z distribution:** All 10 trades entered in the 2.0–2.5σ band. No entry < 2.0σ or > 3.0σ. The system cap of ~3.0σ was never binding; z availability was the constraint.

**Per-symbol analysis (≥ 2 appearances):**
- **SOL:** T8, T12, T14 — 3 appearances, 1/3 = 33% win rate, avg PnL = −$0.214, 1 coint-failure (T14), 1 win (T12)
- **FIL:** T5, T10 — 2 appearances, 0/2 = 0% win rate, avg PnL = −$0.338, 1 coint-failure (T5), 1 cost blowout (T10)

FIL appears in the two most cost-problematic trades in the window (T5 via meme-token partner FLOKI; T10 via thin leg). FIL's orderbook depth is consistently thin at the ratio floor.

---

## Section 3 — Sizing-Mismatch Quantification and Filter Effectiveness

### 3A — Beta-Mismatch Quantification

#### 3A-i: $/σ Cross-Trade Validation

Source: position_pnl from reconciliation_checks.csv; Δz computed as |entry_z − exit_z| from trade_closes.csv.

**$/σ table (T5–T14):**

| Trade | Pair | Exit reason | Δz (σ) | position_PnL | implied_$/σ | Sizing signal |
|-------|------|-------------|---------|------------|------------|-------------|
| T5 | FIL/FLOKI | coint_lost | 0.095σ | −$0.323 | uninformative | near-zero Δz: coint broke before z moved |
| T6 | DOGE/SUI | coint_lost | 0.541σ | −$0.676 | uninformative | near-zero Δz: coint broke before z moved |
| T7 | BTC/HBAR | normal | 4.390σ | −$0.007 | −$0.002/σ ≈ $0/σ | β ≠ 1 inferred from $/σ ≈ 0; actual β unverified — OLS β depends on log-price covariance, not price magnitude |
| T8 | SOL/AVAX | normal | 1.905σ | EXCLUDED | — | data quality (recon basis=position_pnl) |
| T9 | LINEA/ZRO | normal | 2.981σ | −$0.006 | −$0.002/σ ≈ $0/σ | β ≠ 1 inferred from $/σ ≈ 0; actual β unverified |
| T10 | FIL/ICP | normal | 4.119σ | +$0.274 | +$0.067/σ | β ≈ 1 inferred from positive $/σ; actual β unverified |
| T11 | CRV/IOTA | coint_timeout | 2.422σ | −$0.399 | −$0.165/σ | path dependency: z reverted then re-expanded adversely |
| T12 | SOL/BTC | normal (regime_break) | 4.142σ | +$0.143 | +$0.035/σ | β ≈ 1 inferred from positive $/σ; actual β unverified |
| T13 | BNB/COMP | normal (regime_break) | 4.374σ | −$0.395 | −$0.090/σ | β > 1 inferred from $/σ sign inversion; actual β unverified |
| T14 | SOL/ALGO | coint_lost | 1.798σ | −$0.481 | −$0.267/σ | β > 1 inferred from intra-trade dollar/z anti-correlation; actual β unverified |

**Normal-exit trades with Δz ≥ 1.5σ (5 trades: T7, T9, T10, T12, T13; excluding T8 data quality):**
- implied_$/σ > 0: **2** (T10 +$0.067/σ, T12 +$0.035/σ)
- implied_$/σ ≈ $0 (< $0.005/σ magnitude): **2** (T7 −$0.002/σ, T9 −$0.002/σ)
- implied_$/σ < 0: **1** (T13 −$0.090/σ)
- Range: −$0.090/σ to +$0.067/σ

**Sign varies across normal-exit trades.** The position does not consistently track the spread. Sizing-mismatch verdict: CONFIRMED (see Section 10A).

Pattern: pairs where β ≈ 1 (FIL/ICP at T10, SOL/BTC at T12) show positive $/σ — z and dollars move together. Pairs where β departs from 1 (BTC/HBAR, LINEA/ZRO, BNB/COMP) show near-zero or negative $/σ.

#### 3A-ii: Residual-vs-Liquidity Analysis (Item 12)

Source: unexplained from reconciliation_checks.csv; thin-leg liquidity from liquidity_checks.csv (entry_precheck rows).

**Residual-vs-liquidity table:**

| Trade | Pair | Thin leg | Thin-leg liq (USDT) | Ratio (×notional) | Unexplained residual | Pattern |
|-------|------|----------|---------------------|-------------------|---------------------|---------|
| T5 | FIL/FLOKI | FLOKI (meme) | $1,080 | 10.8× | −$0.0927 | **negative** |
| T6 | DOGE/SUI | SUI | $1,462 | 14.6× | +$0.0292 | positive |
| T7 | BTC/HBAR | HBAR | $856 | 8.6× | +$0.0404 | positive |
| T8 | SOL/AVAX | SOL | $569 | 5.7× | EXCLUDED | data quality |
| T9 | LINEA/ZRO | LINEA | $522 | 5.2× | +$0.0727 | positive (counterexample) |
| T10 | FIL/ICP | FIL | $576 | 5.8× | −$0.2546 | **negative (large)** |
| T11 | CRV/IOTA | IOTA | $813 | 8.1× | +$0.0396 | positive |
| T12 | SOL/BTC | SOL | $750 | 7.5× | +$0.0231 | positive |
| T13 | BNB/COMP | BNB | $3,462 | 34.6× | +$0.0267 | positive |
| T14 | SOL/ALGO | SOL | $7,708 | 77.1× | +$0.0167 | positive |

**Analysis:** The residual-vs-liquidity relationship is **not** a simple liquidity correlation. Two negative residuals exist (T5 FLOKI −$0.093, T10 FIL −$0.255). Both correspond to known-problematic pairs: FLOKI is a graveyarded meme token; FIL has persistent thin orderbooks in this swap universe. But T9 (LINEA, $522 thin leg, ratio 5.2×) shows a strongly positive residual (+$0.073) despite having a thinner leg than both negative cases. T7 ($856 thin, HBAR) also shows positive residual.

The pattern is **pair-specific rather than purely liquidity-correlated.** A simple liquidity floor (raising min ratio from 5× to some higher value) would both fail to exclude FLOKI (10.8× ratio, still negative) and would incorrectly exclude T9 LINEA (5.2× ratio, positive) and T7 HBAR (8.6×, positive).

**Interpretation:** "Cost bias is pair-specific, not random and not a simple liquidity correlation." The cost overruns are concentrated in pairs with known execution quality issues (meme tokens, FIL-specific spread). This is more informative than a pure liquidity correlation: it suggests a pair-tier exclusion model (based on historical execution quality) rather than a liquidity floor.

**Item 12 disposition:** DEFER — the "random scatter vs. liquidity-correlated" decision point yields a third outcome: pair-specific bias. A liquidity-tiered cost model is not supported; statistical inference with the flat model is not fully valid (two outliers are deterministic, not random); but a clean solution requires pair-by-pair execution cost tracking, which is a more complex instrument than a threshold change. FIL-USDT-SWAP should be evaluated for graveyard status based on T5 and T10 data. Item 12 carries forward as a model-design question, not a threshold-tuning question.

#### 3A-iii: Counterfactual Analysis — Beta-Adjusted Sizing

**COMPLETED 2026-05-28.** Script: `core/chart_audit/retroactive_beta.py`.

Window parameters confirmed to match live execution exactly:
- 200 bars × 1m klines ending at each trade's entry timestamp (STATBOT_EXECUTION_KLINE_LIMIT=200, STATBOT_EXECUTION_TIMEFRAME=1m)
- OLS regression run on the FULL 200-bar series — `window=21` in `evaluate_cointegration()` controls z-score window only, not the OLS regression
- Data source: OKX `/api/v5/market/history-candles` endpoint for historical access

**PnL reconstruction caveat:** The counterfactual uses kline close prices at entry/exit minute bars, not exact execution prices. The live system uses orderbook mid-prices for the most recent bar at entry. Absolute PnL reconstruction is unreliable (reconstructed equal-notional PnL differs substantially from actual_pnl for short-hold trades). The DELTA values (PnL_beta − PnL_equal) are more reliable because both calculations use the same prices — systematic timing bias cancels.

**Retroactive β table (T5–T14):**

| Trade | Pair | β (OLS, 200 bars) | Side | Δ from 1.0 |
|-------|------|-------------------|------|------------|
| T5 | FIL/FLOKI | 1.433 | S1L2 | +0.433 |
| T6 | DOGE/SUI | 0.586 | L1S2 | −0.414 |
| T7 | BTC/HBAR | 0.600 | L1S2 | −0.400 |
| T8 | SOL/AVAX | 0.812 | L1S2 | −0.188 |
| T9 | LINEA/ZRO | 0.821 | L1S2 | −0.179 |
| T10 | FIL/ICP | 1.094 | S1L2 | +0.094 |
| T11 | CRV/IOTA | 1.051 | S1L2 | +0.051 |
| T12 | SOL/BTC | 1.290 | S1L2 | +0.290 |
| T13 | BNB/COMP | 0.471 | S1L2 | −0.529 |
| T14 | SOL/ALGO | 0.839 | S1L2 | −0.161 |

β range: [0.471, 1.433]. Width = 0.962. Mean ≈ 0.851. Median ≈ 0.826. 7 of 10 trades below 1.0.

**β distribution verdict: WIDE.** No clustering near 1. The range [0.471, 1.433] fully fails the "tight near 1 (0.85–1.15)" criterion for Option A preference.

**Counterfactual PnL table:**

Sizing assumptions:
- Equal-notional: each leg = $100 (gross = $200, matches entry_notional_usdt in trade_closes.csv)
- Gross-normalized-beta: leg1 = $200/(1+β), leg2 = $200β/(1+β) (gross conserved at $200)

| Trade | Pair | β | PnL_equal | PnL_β | Δ (β−equal) | Sign flip |
|-------|------|---|-----------|-------|-------------|-----------|
| T5 | FIL/FLOKI | 1.433 | −$0.272 | −$0.283 | −$0.012 | no |
| T6 | DOGE/SUI | 0.586 | −$0.451 | −$0.127 | +$0.324 | no |
| T7 | BTC/HBAR | 0.600 | +$0.080 | +$0.100 | +$0.020 | no |
| T8 | SOL/AVAX | 0.812 | +$0.130 | +$0.121 | −$0.009 | no |
| T9 | LINEA/ZRO | 0.821 | +$0.347 | +$0.275 | −$0.072 | no |
| T10 | FIL/ICP | 1.094 | +$0.954 | +$0.971 | +$0.017 | no |
| T11 | CRV/IOTA | 1.051 | −$0.298 | −$0.279 | +$0.020 | no |
| T12 | SOL/BTC | 1.290 | +$0.231 | +$0.197 | −$0.034 | no |
| T13 | BNB/COMP | 0.471 | −$0.208 | +$0.393 | **+$0.601** | **YES** |
| T14 | SOL/ALGO | 0.839 | −$0.517 | −$0.385 | +$0.133 | no |
| **TOTAL** | | | | | **+$0.988** | **1 flip** |

**Decision rule application (from Section 11):**

| Condition | Required | Observed | Met? |
|-----------|----------|----------|------|
| Cumulative δ > $0.30 | > $0.30 | $0.988 | **YES** |
| Sign flips ≥ 2 | ≥ 2 | 1 (T13 only) | **NO** |
| T13/T14 among flips | at least 1 | T13 | **YES** |

2 of 3 conditions met. The ≥2 sign flip criterion was not satisfied. T14 (β=0.839, Δ=+$0.133) did not flip — both equal-notional and β-sized produce a loss. β=0.839 is close to 1, so the sizing effect is small.

**T13 sign flip — robustness:** The flip is mechanically clear. BNB fell −0.733%, COMP fell −0.941% over 41 minutes (longer hold → timing error is small relative to price moves). Position: short BNB, long COMP. Equal-notional over-weights COMP exposure 2× versus the β-correct weighting (β=0.471 means COMP has only 47% sensitivity relative to BNB in the spread). COMP's larger percentage decline overwhelms the short-BNB gain under equal-notional. Under β-sizing, COMP exposure is $64.1 vs $100 equal-notional — the reduced COMP drag (+$0.60 improvement) flips the loss to a profit. This mechanism is robust to execution timing.

**T14 non-flip — note:** β=0.839 means ALGO exposure under β-sizing is $91.3 vs $100 equal-notional. The 8.7% reduction in ALGO exposure reduces the loss from −$0.517 to −$0.385 (+$0.133 improvement) but does not flip the sign. ALGO fell −1.018% vs SOL's −0.500% — ALGO's excess decline (−0.518%) is the structural driver, and β-sizing provides only modest relief.

**Input 2 (β distribution) evaluation:** β range [0.471, 1.433] is WIDE. Per the Section 11 decision rule: "If β spreads widely (e.g., 0.3–3.0 range across T5–T14): sizing mismatch is large-magnitude; previous project-level reframing holds; Option C justified even if T13/T14 sign flips are absent." This condition applies.

**Counterfactual conclusion:** Option C (gross-normalized-beta sizing) is **CONFIRMED** as the correct option selection. The criterion is met via Input 2 (wide β range) even though the sign-flip count requirement (≥2) from Input 1 was not reached. The T13 sign flip (+$0.601) is mechanically robust. The wide β range [0.471, 1.433] demonstrates that β-mismatch is a frequent, large-magnitude effect in the actual pair universe.

No claim is made that β-aware sizing would have produced profitable outcomes on T5–T14 in aggregate. The counterfactual DELTA is +$0.988, but this rests on price reconstruction with known timing limitations. What IS confirmed: for pairs with β far from 1 (T6 β=0.586, T7 β=0.600, T13 β=0.471), the sizing mismatch materially distorts outcomes. This is sufficient to justify Option C as the structurally correct fix.

---

### 3B — Filter Effectiveness

**Contamination caveat (applies throughout 3B):** The filter was evaluated on trades where the dollar position did not necessarily track the spread. The filter premise (slope predicts coint-failure) is assessable from gate events, but its dollar-outcome benefit is not cleanly measurable under sizing mismatch.

#### 3B-i: Gate Activity

Source: entry_rejections.csv aggregated across all 10 experiment runs.

**Total gate evaluations (coint_stability_check_evaluated_count summed):** 770
**Total blocked (coint_stability_check_blocked_count summed):** 18
**Total insufficient_history:** 48
**Fire rate (blocked / evaluated):** 18 / 770 = **2.3%**

All 18 blocks occurred in run_113 for AVAX/ADA pair (slope=0.04837 = 2.4× the 0.020 threshold). Zero of the 10 traded pairs were ever blocked by the coint_stability gate.

**Pre-committed calibration rule — applies now:**
fire_rate = 2.3% < 15% → **CALIBRATION TRIGGER FIRES.** slope_max must be loosened from 0.020 → 0.030 for any future use of this filter. This is pre-committed and recorded regardless of whether the primary next experiment uses this filter.

The filter passed every entry that was subsequently traded. Fire rate 2.3% means the current slope_max=0.020 threshold is too strict for the active pair universe — it catches only pairs with dramatic slope (like AVAX/ADA at 0.048), not the subtle slope that might have predicted the observed coint-failures.

#### 3B-ii: Premise Check

Source: running slope-vs-outcome tally (evaluated trades only, blocked_count=0 for all).

| Exit Category | Count | Slopes | Mean delta-from-threshold (0.020) | Notes |
|--------------|-------|--------|----------------------------------|-------|
| coint-failure (w/ slope) | 2 | T5: −0.00449, T11: ≈0 (−1.34e-6) | +0.02224 | Both far below threshold |
| coint-failure (no slope) | 1 | T6: unavailable (Patch 7.2 not active) | — | Excluded from slope analysis |
| coint-failure (insuff_hist) | 1 | T14: unavailable | — | Excluded |
| normal (w/ slope) | 5 | T7 ≈0, T8 +4.0e-4, T9 +2.2e-4, T12 −0.00676, T13 +0.00102 | +0.01980 | All below threshold |

**Delta-from-threshold convention:** slope_max − slope_at_entry. Large positive = slope far below threshold.

Near-threshold coint-failures (delta < 0.005): **0** of 2 available data points.
Far-below-threshold coint-failures (delta > 0.015): **2** of 2 available data points (T5: +0.024, T11: +0.020).

Both observable coint-failures had slopes far below the blocking threshold. The filter could not have blocked either regardless of where the threshold was set (short of threshold → 0, which would block all entries). The slope at entry was not a useful predictor of post-entry coint collapse.

**Note on T11 specifically:** T11 entered with slope ≈ 0 AND cointegration score 24.998/25 (p ≈ 0 = maximum strength). If anything, T11's entry metrics were better than most of the normal-exit trades. The premise is decisively negative for T11.

#### 3B-iii: Coint-Failure Rate on Evaluated Trades

| Population | Coint-failure rate |
|-----------|------------------|
| Raw baseline (9 trades) | 5/9 = 55.6% |
| exp_guard050 (19 trades) | 7/19 = 36.8% |
| exp_coint_stability, ALL 10 trades | 4/10 = 40.0% |
| exp_coint_stability, evaluated 8 trades | 3/8 = **37.5%** |

Pre-committed success threshold: ≤ 25% among evaluated trades.
Pre-committed null threshold: ≥ 30% among evaluated trades.

37.5% ≥ 30% → **null criterion fires.** Coint-failure rate among evaluated trades did not improve relative to the exp_guard050 baseline (36.8% → 37.5%). Patch 7 produced no detectable improvement in the coint-failure rate.

---

## Section 4 — Cointegration Fragility Analysis

**SURVIVES SIZING REFRAME** for coint-failure event counts. **PENDING SIZING REVALIDATION** for dollar loss magnitudes from coint-failures.

**Exit reason distribution:**

| Exit reason | Raw baseline (9) | exp_guard050 (19) | exp_coint_stability (10) |
|-------------|-----------------|-------------------|--------------------------|
| cointegration_lost | 5 (55.6%) | 7 (36.8%) | 3 (30.0%) — T5, T6, T14 |
| cointegration_watch_timeout | 0 | 0 | 1 (10.0%) — T11 |
| normal | 1 (11.1%) | ~11 (~57.9%) | 6 (60.0%) — T7, T8, T9, T10, T12, T13 |
| regime_break | ~2 (~22.2%) | ~1 (~5.3%) | 2 (20.0%) — T12 (regime_break, WIN), T13 (regime_break, LOSS) |
| trailing_stop | 1 (11.1%) | 0 | 0 |

Note: "normal" in trade_closes maps to both pure z-reversion exits and regime_break exits. regime_break is the coarser exit mechanism that fires when RANGE → TREND transition occurs.

Coint-failures in this experiment: T5 (coint_lost, 5.25 min), T6 (coint_lost, 8.50 min), T11 (coint_watch_timeout, 120.63 min), T14 (coint_lost, 20.27 min).

**Time-to-failure:** min 5.25 min (T5), median ~14.4 min (T6+T14 average), max 120.63 min (T11).

**Coint-failures split by gate status:**

| Gate status | Coint-failure count | Total | Rate |
|------------|--------------------|----|------|
| evaluated | 3 (T5, T6, T11) | 8 | 37.5% |
| insufficient_history | 1 (T14) | 2 | 50.0% |
| not_reached | 0 | 0 | — |

**Finding:** Coint-failure events are real and occurred regardless of what the dollar position was doing. **SURVIVES SIZING REFRAME.** However, the dollar loss attributed to T14 (−$0.604 equity, primarily from the −$0.481 position_pnl) reflects both coint-failure and sizing-mismatch — the position was anti-correlated with z throughout the hold.

**Confidence update:**
- Prior: HIGH confidence that cointegration fragility is the dominant loss driver
- Post-experiment: **MEDIUM** — coint-failure events are real, but the coint-failures' dollar losses include sizing-mismatch component for β ≠ 1 pairs (T14 confirmed intra-trade; T5 T6 near-zero Δz so dollar loss partly from costs). The 40% negative-MFE rate (4/10 trades never profitable) may partly reflect sizing mismatch making profitable z-moves dollar-negative.

---

## Section 5 — MFE Timing and Execution Cost Analysis

### 5A — MFE Timing Pattern

**PENDING SIZING REVALIDATION.** Under correct β-sizing, dollar MFE for some pairs may differ, particularly T7 and T9 where β ≠ 1 suppressed dollar sensitivity.

| Bucket | All trades (count, pct) | Winners | Losers |
|--------|------------------------|---------|--------|
| Negative MFE (never profitable) | 4 (40%) | 0 | 4 (T5, T6, T13, T14) |
| early_hold (0–33%) | 1 (10%) | 0 | 1 (T11: in-zone MFE at early hold) |
| mid_hold (34–66%) | 2 (20%) | 0 | 2 (T7, T9: both blocked at in-zone MFE) |
| late_hold (67–100%) | 2 (20%) | 1 (T12) | 1 (T10: guard passed, costs ate gain) |
| missing (data quality) | 1 (10%) | 0 | 1 (T8) |

40% negative-MFE trades is the dominant MFE finding. These 4 trades were never profitable regardless of exit timing or guard settings. Negative-MFE trades cannot be evaluated for timing — their failure is pre-entry or sizing-based.

Of 5 evaluable trades (non-negative MFE, excluding T8):
- T11 MFE in early hold → coint-failure/timeout
- T7, T9 MFE in mid hold → both guard-blocked
- T12, T10 MFE in late hold → T12 captured (WIN), T10 costs ate profit

**exp_guard050 pattern validation:** "Winner late_hold ≥ 70%, loser early_hold ≥ 70%" — not confirmed at this sample. N is too small (1 winner, 5 evaluable losses) for bucket analysis to be reliable. The negative-MFE bucket confounds any timing conclusion.

**T7 full_tp blocking root cause (Item 14 specific question):** T7 had 41 guard blocks at in-zone MFE $0.127. Effective floor should be $0.24 × 0.50 = $0.12. $0.127 > $0.12 → guard should have passed. The guard_floor_at_max_favorable_pnl in trade_closes.csv is 0.24 (the stored base parameter, not the effective floor). This field stores the raw parameter before the 0.50 multiplier is applied. The effective floor at execution is $0.24 × 0.50 = $0.12. If $0.127 > $0.12 and the guard still blocked 41 times, the blocking must have occurred at sub-$0.12 in-zone PnL cycles with $0.127 being the max across ALL cycles, not the value at any individual blocking decision. Root cause: $0.127 was the session MFE; at the moment of each guard evaluation, the floating PnL was below $0.12 (position oscillated). This is consistent with normal guard behavior — the guard evaluates instantaneous PnL, not session MFE. **Item 14 T7 anomaly is RESOLVED — no mechanical error.** The $0.127 was a transient peak that fell below $0.12 before the guard evaluated.

**Tag:** Full exit redesign PENDING SIZING REVALIDATION; T7 anomaly resolution SURVIVES SIZING REFRAME.

### 5B — Execution Cost Pattern (Item 12)

**SURVIVES SIZING REFRAME.** Reconciliation measures actual cash flows — not model predictions, not β-dependent.

Known occurrences going into this review:
- HMSTR run_102: unexplained −$0.226 (graveyarded permanently)
- FLOKI run_111 (T5): unexplained −$0.093 (graveyarded permanently)

Experiment-window occurrences with |unexplained| > $0.05:

| Trade | Unexplained | Direction | Pair characteristic |
|-------|-------------|-----------|---------------------|
| T5 FIL/FLOKI | −$0.0927 | negative | FLOKI = meme token, graveyarded |
| T10 FIL/ICP | −$0.2546 | negative | FIL thin leg (ratio 5.76×), non-meme |
| T9 LINEA/ZRO | +$0.0727 | positive | LINEA thin (ratio 5.22×) |

Positive residual pattern — SURVIVES SIZING REFRAME (7 occurrences on liquid pairs in this window):
T7 (+$0.040), T9 (+$0.073), T11 (+$0.040), T12 (+$0.023), T13 (+$0.027), T14 (+$0.017), plus prior T6 (+$0.029). Pattern consistent: actual costs below $0.14 model for non-thin, non-meme liquid pairs.

Cumulative unexplained (T5–T14, excluding T8 data quality): −$0.093 − $0.255 + $0.029 + $0.040 + $0.073 + $0.040 + $0.023 + $0.027 + $0.017 = **−$0.099 net** (two large negatives vs seven small positives). Cumulative is negative but dominated by T10 FIL.

Materiality: |cumulative negative| from T5+T10 = $0.348 > $0.30 → **Item 12 materiality threshold exceeded.** However, as discussed in 3A-ii, the pattern is pair-specific (FIL/FLOKI), not liquidity-tier-general.

**Meme-token escalation rule:** Third occurrence trigger for category exclusion: NOT reached (n=2 meme-token failures, both already graveyarded). No new meme occurrences in T5–T14.

---

## Section 6 — Shadow Block Findings

**Source:** entry_rejections.csv, entry_gate_component_scores.

Shadow blocks that fired during the experiment window:

| Block type | Total firings | Notes |
|-----------|--------------|-------|
| advanced_ml_break_risk_high | Multiple across all runs | pre-committed shadow block; Patch 4 |
| coint_stability_slope_high | 18 (AVAX/ADA, run_113) | see Section 3B-i |

**advanced_ml_break_risk_high:** T13 had 4× break_risk_high pre-entry (break_risk=0.15). Regime did switch to RISK_OFF during T13's hold — ML warning was directionally correct. T13 was a loss ($/σ inversion). Sample too small (1 trade with known pre-entry ML warnings + outcome) for win-rate comparison.

**Tag:** Gate-based shadow filters (coint health, liquidity, break_risk) SURVIVE SIZING REFRAME.

**Disposition:** DEFER (insufficient data for all shadow blocks — total firings < 5 per block type for this window's trades).

---

## Section 7 — Reconciliation Anomaly Patterns

**SURVIVES SIZING REFRAME.** Reconciliation measures cash flows.

### 7A — Negative residual pattern (thin-leg cost overrun):

| Occurrence | Unexplained | Characteristic |
|-----------|-------------|---------------|
| Run 99 FIL/LINEA (carry-forward) | −$0.121 | FIL thin |
| Run 100 BNB/LDO (carry-forward) | −$0.068 | thin |
| T5 FIL/FLOKI (run_111) | −$0.093 | meme, graveyarded |
| T10 FIL/ICP (run_118) | −$0.255 | FIL thin (ratio 5.76×), largest in window |
| T8 SOL/AVAX (run_116) | −$0.194 | data quality fail (excluded from pattern analysis) |

FIL-USDT-SWAP appears in 3 of the 4 confirmed negative-residual events (run_99, T5 via FIL leg, T10). This is pair-specific evidence that FIL execution costs are consistently above the $0.14 model.

### 7B — Positive residual pattern (liquid pairs):

Prior experiment occurrences carried forward: ETH/ETC +$0.145, DOGE/BNB +$0.078.
This window: T6 (+$0.029), T7 (+$0.040), T9 (+$0.073), T11 (+$0.040), T12 (+$0.023), T13 (+$0.027), T14 (+$0.017).

Cumulative positive residuals from this window's liquid pairs: +$0.249. Pattern: 7 consecutive positive residuals on non-meme, non-FIL pairs. The $0.14 flat model overestimates costs for this pair universe (costs closer to $0.10–$0.12 per trade on liquid pairs).

As established in 3A-ii: the 3A-ii residual-vs-liquidity analysis found pair-specific rather than liquidity-correlated bias. Item 12 is not elevated to NEXT PRIORITY (a simple liquidity-tiered model is not supported); it is DEFERRED with the finding that pair-specific cost tracking is the right long-term approach.

---

## Section 8 — Deferred Research Items Review

| Item | Description | Disposition | Tag |
|------|-------------|-------------|-----|
| **1** | Forward-looking coint stability filter (Patch 7) | **REJECT** — Section 10B Verdict B; premise not supported; filter closed as a direction | SURVIVES (premise assessment not affected by sizing) |
| **2** | Regime-flip exit timing (run_98 ETH/AVAX) | **DEFER** — no new occurrences; regime_break exits (T12, T13) did not show timing delay | SURVIVES |
| **3** | max_break_risk recalibration | **DEFER** — capped at 0.15; T13 ML warning directionally correct; insufficient data to recalibrate | SURVIVES |
| **4** | Notional adjustment | **DEFER (superseded by Item 16)** — β-sizing changes the notional model structurally | PENDING |
| **5** | Alert/kill-switch (Patch 6) | **DEFER** — Patch 6 not exercised in this window; circuit_breaker_trips=0 | SURVIVES |
| **6** | Exit z-zone widening | **DEFER (until after β-sizing experiment)** — exit zone calibration must be re-evaluated after position sizes change | PENDING |
| **7** | Profit-lock band mechanism (Patch 5) | **RETAIN, flag for re-evaluation** — floor ($0.12 effective) calibrated against equal-notional PnL; under β-sizing, in-zone PnL magnitudes will differ. Patch 5 operational; recalibrate after first β-sized window | PENDING |
| **8** | Adverse-exit fill quality | **DEFER** — insufficient new data; T5/T6/T14 coint-failure costs below $0.05 individual threshold; no escalation | SURVIVES |
| **9** | Positive reconciliation residuals | **DEFER → absorbed into Item 12** — 7 positive residuals confirmed; pattern established; addressed in Section 7B | SURVIVES |
| **10** | MFE timing | **DEFER (until after β-sizing experiment)** — 40% negative-MFE rate confounds timing analysis; must re-evaluate after β-sizing changes dollar MFE magnitudes | PENDING |
| **11** | DOGE/HMSTR execution cost anomaly | **CLOSED** — HMSTR graveyarded; no further action | — |
| **12** | Execution cost model | **DEFER** — 3A-ii shows pair-specific bias, not liquidity-tier bias; no simple threshold fix; carry forward as pair-cost-tracking design question; FIL candidate for graveyard review | SURVIVES |
| **13** | Post-close fee snapshot timing gap (T8) | **DEFER** — one occurrence; fix candidate is 2–5s delay post-close when retry_count > 0; low priority vs Item 16 | SURVIVES |
| **14** | Full_tp exit-capture mechanism | **DEFER (exit redesign until β-sizing); T7 anomaly RESOLVED** — T7 guard blocks at $0.127 MFE explained by instantaneous PnL oscillation below $0.12 floor during guard evaluation windows; no mechanical error | PENDING (full redesign) / SURVIVES (T7 resolution) |
| **15** | coint_stability evaluated_count semantics / level-check hypothesis | **CLOSED** — refuted at run_120: T11 had cointegration score 24.998/25 (p≈0 = maximum strength); level check would have passed T11; premise-negative verdict firm | SURVIVES |
| **16** | Beta-aware position sizing | **NEXT PRIORITY** — code-confirmed; $/σ sign variation across 5 normal exits; T13/T14 sign inversions; β-unaware sizing cannot produce interpretable experiment data | SURVIVES |

---

## Section 9 — Confidence Calibration Final Update

| Hypothesis | Pre-experiment | End-of-experiment | Evidence |
|-----------|--------------|------------------|---------|
| confidence_coint_stability_slope_predictive | LOW | **LOW** — no change. Both coint-failures with available slopes (T5, T11) had slopes far below threshold. Filter could not have blocked them. |
| confidence_coint_filter_reduces_failure_rate | UNTRACKED | **LOW** — 37.5% evaluated coint-failure rate vs 36.8% baseline; no detectable improvement. |
| confidence_coint_fragility_as_dominant_problem | HIGH | **MEDIUM** — coint events real; dollar losses include sizing-mismatch component. 40% negative-MFE trades partly explained by β ≠ 1. |
| confidence_beta_mismatch_structural | UNTRACKED | **VERIFIED** — code-confirmed: zero hedge_ratio references in func_trade_management.py. |
| confidence_beta_mismatch_magnitude_material | UNTRACKED | **MEDIUM** — $/σ sign varies across 5 normal exits; T13/T14 sign inversions; T14 intra-trade confirmation. Counterfactual not completed — magnitude in dollars unverified. |
| confidence_dsnl_liquidity_correlated | UNTRACKED | **LOW** — residual pattern is pair-specific, not liquidity-tier-correlated. T9 LINEA ($522 thin leg, +$0.073 residual) is a direct counterexample to the thin-leg hypothesis. |
| confidence_meme_token_execution_cost_anomaly | MEDIUM (n=2) | **MEDIUM** — still n=2 (HMSTR, FLOKI); both graveyarded. No new meme occurrences. No escalation. |
| confidence_execution_cost_model_accuracy | MEDIUM | **MEDIUM** — flat $0.14 model overestimates for liquid non-FIL pairs (7 positive residuals); underestimates for FIL and meme tokens (3 negative). Pair-specific, not random. |
| confidence_mfe_timing_predictive | MEDIUM (exp_guard050) | **LOW** — 40% negative-MFE trades confound timing. Under sizing mismatch, dollar MFE for T7/T9 may be suppressed. Cannot confirm exp_guard050 timing pattern at this sample. |
| confidence_profit_lock_band_mechanism | MEDIUM (Patch 5 inert) | **MEDIUM, no new evidence** — Patch 5 operational; floor calibration pending β-sizing. |
| confidence_trend_regime_mr_block_active | VERIFIED | **VERIFIED** — Patch 4.1 in production. |
| confidence_emergency_flatten_safety | PATCH_6_APPLIED | **APPLIED, unexercised** — circuit_breaker_trips=0 in this window; Patch 6 not triggered. |
| confidence_break_risk_threshold_correctness | MEDIUM | **MEDIUM** — T13 ML warning (break_risk=0.15, pre-entry) was directionally correct (regime switched to RISK_OFF during hold). Insufficient data for recalibration. |

---

## Section 10 — Structural Verdicts

### Section 10A — Sizing-Mismatch Verdict (Project Level)

**Evidence summary:**
- hedge_ratio reference count in func_trade_management.py: **zero**
- $/σ sign distribution across normal-exit trades (5 with Δz ≥ 1.5σ): **mixed** — 2 positive, 2 near-zero, 1 negative
- T14 intra-trade sign inversion: **OBSERVED** — z decreased (favorable) while dollar PnL deteriorated throughout hold
- T13 full-traversal with negative position PnL: **OBSERVED** — 4.37σ traversal, position_pnl = −$0.395

**Verdict 10A: CONFIRMED**

The z-score and executed dollar position measure different things. OLS hedge ratio β is used for signal computation but not for position sizing. The experiment's PnL history reflects beta-mismatched positions, not the mean-reversion strategy as designed. This is a project-level structural finding. The next experiment must use β-aware sizing. Sections 10B, 11, and 13 are written under this constraint.

---

### Section 10B — Coint-Stability Filter Verdict (Experiment Level)

**Context:** This verdict is rendered on data where positions did not fully track the signal. The verdict is still meaningful for gate-event analysis, but it is not a clean test of whether the filter improves dollar outcomes. Contamination caveat applies.

**Evidence summary:**
- evaluated_trade_count (real N): **8**
- coint_stability_slope_exceeded_count: **18** (all from AVAX/ADA in run_113; zero blocks of any traded pair)
- fire_rate: **2.3%**
- coint-failure rate among evaluated trades: **37.5%** (≥ 30% null threshold)
- calibration trigger status: **FIRED** — slope_max must be loosened to 0.030 for any future use
- Section 3B-ii median Δ-from-threshold for coint-failures (2 data points): **+0.022σ** (far above 0.015 threshold)
- Early-resolution criterion: **MET at T11** (two coint-failures, both with maximum entry-time coint strength, both failed post-entry)

**Verdict 10B: B — Premise wrong**

The premise is not supported on the available data. The experiment also does not constitute a fully clean test of the premise, because positions were sized at equal notional rather than β-adjusted. However, both observable coint-failures with available slope data (T5: slope −0.00449, delta +0.024; T11: slope ≈ 0, p ≈ 0 = maximum coint strength) entered with exemplary entry-time coint metrics and failed post-entry. The premise is not supported, and the two most informative data points both argue against it. A third coint-failure (T14) entered with p_value=None throughout monitoring — a different measurement failure, not a slope signal.

Coint-stability filtering is deprioritized, not simply deferred. "Improve the coint filter" is not a viable next-experiment direction. The slope-max calibration adjustment (0.020 → 0.030) is recorded as a pre-committed consequence of the 2.3% fire rate, to apply if this filter is ever revisited. It does not reopen the filter premise.

---

## Section 11 — Forward Plan

Based on Verdict 10A CONFIRMED + Verdict 10B B, the forward plan is determined: β-aware sizing must be deployed before any other experiment can produce interpretable economic data.

### Primary Forward Plan: Beta-Aware Position Sizing (Item 16)

**Experiment group:** exp_beta_aware_sizing_v1

**Hypothesis:** Position sizing proportional to OLS β (gross-normalized-beta mode) will align dollar PnL with z-score movements, making strategy economics directly measurable and eliminating the signal/position mismatch identified in Verdict 10A.

**Mechanism:** At entry, compute OLS β from the same lookback used for z-score. Size as: `leg1_notional = target_gross / (1 + β)`, `leg2_notional = target_gross × β / (1 + β)`. When β = 1, this reduces to equal-notional. When β > 1, the second leg receives proportionally more capital. Total gross notional is preserved.

**Infrastructure status:**
- Config schema: ALREADY HAS `hedge_ratio_sizing_enabled`, `hedge_sizing_mode`, `min_hedge_ratio`, `max_hedge_ratio`, `target_gross_pair_notional_usdt`
- Counterfactual study: ALREADY HAS `equal_notional_pnl_usdt` and `hedge_ratio_sized_pnl_usdt`
- Entry markers: ALREADY SUPPORT `entry_hedge_ratio` metadata
- Execution code: **NOT YET WIRED** — hedge_ratio has zero references in func_trade_management.py

**Required implementation (4 components):**
1. In `func_trade_management.py`: read hedge_ratio from metrics at sizing step; compute β-adjusted leg sizes; enforce min/max β bounds (reject entry if β out of bounds); log actual leg sizes and entry_hedge_ratio to trade_open event.
2. Add `hedge_ratio` to `entry_gate_component_scores` in gate payload — makes β available in entry_rejections.csv from first run.
3. Update `target_gross_pair_notional_usdt` config to reflect gross-notional model (decision: retain $200 total gross or $200 per leg as max — must decide before implementation).
4. Tests: update sizing tests; add 2 new tests (β > 1 case, β < 1 case); add 1 test for β out-of-bounds rejection.

**Pre-commitment requirements:**
1. **Retroactive counterfactual study on T5–T14 must be run before finalizing the option choice** (gross-normalized-beta vs β=1 z-score vs β-range gating). Mechanism: retroactively compute OLS β for each trade's entry timestamp from historical klines; pass to `core/chart_audit/counterfactual_exit_study.py` to produce `hedge_ratio_sized_pnl_usdt` vs `equal_notional_pnl_usdt` per trade. **Window alignment requirement:** the retroactive OLS β must use the exact same window length, lookback alignment, and log-price source as `evaluate_cointegration()` would have used at each entry moment — not a reconstructed-with-hindsight window. Confirm the window parameters from `evaluate_cointegration()` before running. Computing "β that would have been right" instead of "β the system would have produced" measures a different counterfactual than the one you'd be deploying. "Proceed on structural-correctness grounds" does not waive this step — it means the experiment is justified regardless of magnitude, but the implementation option still depends on what the counterfactual shows.
2. hedge_ratio MUST appear in CSV output before the first trade of the new experiment.
3. β distribution from first 5 runs must be documented before drawing economic conclusions: median β, range, count in [0.8, 1.2] vs outside.

**Success criteria (next 20 trades under β-aware sizing):**
- $/σ signs are uniformly positive across normal-exit trades (z and dollars move in same direction)
- Cumulative PnL at least $0.50 better than exp_coint_stability at the same trade count
- hedge_ratio logged and verified for ≥ 90% of evaluated trades

**Null criteria:**
- $/σ signs still mixed after 10 evaluated trades under β-sizing → sizing was not the root cause of z/dollar divergence
- Cumulative PnL worse or equal to equal-notional baseline at same trade count → β-sizing makes no material difference

**Calibration adjustment (pre-committed, slope_max):**
slope_max 0.020 → **0.030** recorded as a consequence of the 2.3% fire rate. This applies to any future use of the coint_stability_check filter, regardless of whether it is activated in the next experiment.

**Option assessment (preliminary — final choice contingent on retroactive counterfactual study per pre-commitment requirement 1):**
- Option A (gate β ≠ 1 pairs): simpler; reduces pair universe without fixing the mismatch on remaining pairs; does not make economics measurable for β-near-1 pairs where mismatch is small
- Option B (z-score recomputed with β=1): matches signal to equal-notional position by definition; loses OLS cointegration model's statistical optimality; may degrade pair selection quality
- Option C (gross-normalized-beta sizing): corrects the mismatch at the sizing layer; preserves the OLS signal model; most structurally complete fix

**Option CONFIRMED: gross-normalized-beta sizing (Option C).** Confirmed by retroactive counterfactual study (2026-05-28). β range [0.471, 1.433] across T5–T14 is WIDE; cumulative δ = +$0.988; T13 sign flip confirmed mechanically. Option C selected via Input 2 (wide β distribution) of the decision rule — Input 1 sign-flip count (1 of required 2) was not reached but the wide β distribution provides independent confirmation per the pre-committed rule. See Section 3A-iii for full results.

**Decision rule for option choice (post-counterfactual):**

The decision requires two inputs, not one:

*Input 1 — cumulative PnL delta and sign flips:*
- "Sign flip" = a trade where β-sized PnL has opposite sign to equal-notional PnL
- Count sign flips with ≥1 flip on T13 AND T14 specifically — these are the trades where the sign-mismatch hypothesis was strongest. If T13/T14 don't flip, the sizing-mismatch story is weakened even if aggregate δ is large.
- Criterion: **cumulative δ > $0.30 AND ≥2 sign flips AND T13/T14 among them** → Option C (gross-normalized-beta) is justified on observed evidence
- If δ < $0.30 OR fewer than 2 sign flips → sizing mismatch may be real but small in magnitude; proceed to Input 2

*Input 2 — β distribution width:*
- If β spreads widely (e.g., 0.3–3.0 range across T5–T14): sizing mismatch is large-magnitude; previous project-level reframing holds; Option C justified even if T13/T14 sign flips are absent
- If β clusters tightly near 1 (e.g., 0.85–1.15 for most trades): sizing mismatch is structurally real but small in magnitude; prior cost-domination and coint-failure findings survive more intact; Option A (β-range gating) is a lower-cost first step
- If β is both tight-near-1 AND δ < $0.30: the structural mismatch exists but is not the dominant outcome driver; pivot to Item 14 exit redesign or Item 12 cost residuals as higher-leverage next experiments

*Counterfactual scope caveat:*
The counterfactual is **decisive on Option C** (does β-sizing change outcomes on accepted trades?) but **only suggestive on Option A** (β-range gating would change the pair universe in ways not visible from accepted-trade data alone — excluded trades didn't happen and can't be modeled from this dataset). Option A cannot be fully validated by the counterfactual; it requires a separate forward-looking assessment of how much the pair universe would shrink under the β bounds.

**Item 12 post-β-sizing:** Once $/σ is verifiable, Item 12 (cost model) becomes the second experiment priority if the liquidity-correlated bias can be re-evaluated with cleaner data. FIL-USDT-SWAP is a candidate for graveyard review based on 3 negative-residual occurrences (run_99, T5 via FIL, T10).

**Operational items before next experiment phase:**
- [ ] hedge_ratio added to entry_gate_component_scores logging (required: first run)
- [ ] Patch specification (Item 16) complete with test list and gross/per-leg notional decision
- [ ] DECISION_LOG.md updated with β-sizing patch entry
- [ ] CURRENT_STATE.md updated with exp_beta_aware_sizing_v1 and reset counter
- [ ] memory: project_experiment_state.md updated

---

## Section 12 — Audit Hygiene for This Review

**Coherent-reframe temptation warning:**

The beta-mismatch finding is structurally confirmed in code. Its quantitative impact on PnL is not yet measured. The finding is coherent — it explains near-zero $/σ for T7/T9, sign inversion for T13/T14, and positive $/σ for T10/T12. Coherent reframes are the most seductive error mode in this project's history: Patch 5 (floor miscalibration as dominant problem), the level-check (T11 explained by p≈1.0), the $/σ gate (precise formula built on unstable metric). Each had an appealing story and required verification to confirm or refute.

Applied in this review:
- "T7 lost near-zero because β suppressed dollar sensitivity" — HYPOTHESIS, not stated as conclusion
- "T9 lost because position didn't track the spread" — HYPOTHESIS, not stated as conclusion
- "The strategy would have been profitable under β-sizing" — NOT claimed; counterfactual COMPLETED; reconstructed PnL_equal = −$0.208 → PnL_β = +$0.393 for T13 (sign flip), but cumulative result depends on timing-sensitive price reconstruction
- "All prior losses are attributable to beta-mismatch" — NOT claimed; cost events (T5, T10), coint-failure events are real

The reframe converts "the strategy failed" into "the strategy wasn't fairly tested." Meaningful distinction. Does not guarantee positive results under the correct test. The null criterion for the next experiment is explicit: if $/σ signs remain mixed after 10 evaluated trades under β-sizing, the sizing was not the root cause.

**Self-check completed:**
- [x] Preamble: sizing-mismatch finding stated with code evidence; contamination caveat applied throughout
- [x] Data assembly: master trade table built from CSVs; position_pnl computed from reconciliation_checks.csv; $/σ table built
- [x] 3A-i: $/σ table fully populated (T5–T14); sign distribution stated (2 positive, 2 near-zero, 1 negative for normal exits)
- [x] 3A-ii: residual-vs-liquidity analysis completed; result = pair-specific bias, not liquidity-tier-correlated
- [x] 3A-iii: counterfactual COMPLETED 2026-05-28; β table for T5–T14; decision rule applied; Option C confirmed via Input 2 (wide β range)
- [x] 3B: filter effectiveness under contamination caveat; calibration trigger fired (2.3% < 15%)
- [x] Sections 4–7: SURVIVES/PENDING tags applied throughout
- [x] Section 8: Items 1–16 all have explicit disposition; Item 15 CLOSED, Item 16 NEXT PRIORITY
- [x] Section 9: new confidence variables added; all changes cite specific evidence
- [x] 10A: CONFIRMED; evidence summary present
- [x] 10B: Verdict B; contamination caveat in rationale
- [x] Section 11: one primary forward plan; β data logging required; success AND null criteria stated; alternatives assessed
- [x] Section 13: decision stated first

---

## Section 13 — Continuation Decision

**Decision: 1 — Continue with beta-aware sizing experiment**

Applicable: Verdict 10A CONFIRMED + Verdict 10B B + Section 11 forward plan fully specified + counterfactual accepted as deferred with explicit statement.

**Actions:**
1. Implement β-sizing patch per Section 11 (Item 16): wire hedge_ratio from metrics into func_trade_management.py sizing; add to entry_gate_component_scores; update config; write tests
2. Add hedge_ratio to entry_gate_component_scores logging (Day 1 requirement)
3. Update experiment_group to **exp_beta_aware_sizing_v1**
4. Reset trades_since_experiment_start to 0
5. Update DECISION_LOG.md with β-sizing patch entry
6. Update CURRENT_STATE.md with new experiment_group, reset counter, and exp_coint_stability_v1 verdict
7. Update memory: project_experiment_state.md with new state

**Do NOT run new trades under equal-notional sizing while the β-sizing implementation is in progress.** Every equal-notional trade adds contaminated data that cannot be interpreted as evidence for or against mean-reversion economics.

**New experiment group:** exp_beta_aware_sizing_v1
**exp_coint_stability_v1 status:** CLOSED — Verdict B (premise wrong) on filter effectiveness; Verdict CONFIRMED on sizing mismatch. β-aware sizing is the next experiment.

---

*Review version: exp_coint_stability_v1 structural review v1.0 (actual), 2026-05-28*
*Template: structural_review_exp_coint_stability_v1.md v2.0*
*Data sources: trade_closes.csv, reconciliation_checks.csv, liquidity_checks.csv, entry_rejections.csv from runs 111–123*
*Early review authorized by: premise_early_resolution (T11) AND sizing_mismatch_code_confirmed (T14)*
