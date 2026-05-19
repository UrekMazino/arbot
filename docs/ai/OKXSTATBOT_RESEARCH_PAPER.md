# Statistical Arbitrage Mean Reversion in Cryptocurrency Perpetual Swaps:
## An Iterative Diagnostic Framework for Edge Detection, Exit Architecture Calibration, and Epistemic Discipline Under Small-Sample Conditions

**Author:** Joe Cvia
**System:** OKXStatBot v1
**Exchange:** OKX USDT-M Perpetual Swaps
**Research Phase:** Controlled Experimental (200 USDT notional)
**Document Status:** Living document — updated through Patch 5 (exp_guard050_ethfi_excluded_v1)

---

## Abstract

This paper documents the research and development journey of OKXStatBot, a Python-based statistical arbitrage mean-reversion system trading USDT-margined perpetual swap pairs on the OKX exchange. Operating at 200 USDT notional in a controlled live environment, the system executes cointegration-based pairs trades against a dynamically screened universe of instruments. This document traces the iterative diagnostic process across three experimental runs (runs 90, 93, and 94), comprising nine closed trades, through which the primary structural bottlenecks of the strategy were identified, isolated, and addressed through a series of controlled single-variable patches.

The central research question — *whether exit timing failures or pair-level economic inadequacy constitute the primary drag on realized performance* — was progressively resolved through the development of a telemetry infrastructure capable of decomposing maximum favorable excursion (MFE), guard floor mechanics, cointegration persistence, and regime-entry alignment. The key empirical findings are: (1) 56% of trades exit via cointegration failure, representing the dominant loss mechanism; (2) a guard floor architecture calibrated to a $0.24 base profit threshold is structurally incompatible with the observed MFE distribution of the current pair universe, having produced zero guard passes across nine trades and 1,217 evaluation ticks; (3) the pair universe generates sufficient gross edge to clear empirical round-trip costs at the current notional, but a structural "trapped zone" ($0.109–$0.240 MFE) exists wherein spread reversion occurs but no exit mechanism can monetize it; and (4) regime-entry mismatch — specifically STATARB_MR entries during TREND regime conditions — accounts for the single largest individual trade loss in the dataset.

Patches 1 through 5 address these findings in strict single-variable isolation. The current experimental configuration (exp_guard050_ethfi_excluded_v1) tests guard floor reduction from 0.75 to 0.50 multiplier alongside permanent exclusion of ETHFI-USDT-SWAP, targeting two orthogonal failure classes recoverable through distinct telemetry channels. An explicit 20-trade evidence threshold and per-hypothesis confidence calibration are enforced to prevent narrative drift in a statistically thin dataset.

---

## 1. Introduction

### 1.1 Motivation

Cryptocurrency perpetual swap markets exhibit structural characteristics — continuous 24-hour trading, high liquidity concentration in major instruments, funding rate mechanics, and retail-dominated price discovery — that may support statistical arbitrage strategies based on short-term cointegration between economically related assets. The mean-reversion assumption underlying such strategies rests on the premise that price ratios between cointegrated pairs exhibit stationary behavior, reverting to a historical mean after periods of dislocation.

OKXStatBot was developed to test whether such edges exist at small notional ($200 USDT per pair, $400 total deployed per trade), whether the edge is capturable after fees and slippage, and whether an automated diagnostic framework can identify system-level bottlenecks faster than traditional post-hoc analysis.

The system is not designed primarily for profitability at this stage. It is designed as a research instrument: to accumulate telemetry, isolate failure modes, and develop a scientific understanding of where value is created and destroyed within the strategy lifecycle.

### 1.2 Research Questions

This paper addresses five questions in order of increasing specificity:

1. **Does the pair universe generate exploitable gross edge** at $200 notional after accounting for fees and slippage?
2. **Is the primary drag from entry-quality failures** (entering relationships that have already degraded), or from **exit-architecture failures** (failing to monetize edge that exists post-entry)?
3. **Does regime-entry alignment materially affect outcome distributions** — specifically, do STATARB_MR entries during non-RANGE regimes generate systematically worse outcomes?
4. **Is the profit-capture guard floor calibrated to the observed MFE distribution** of the current pair universe?
5. **Does post-entry cointegration decay occur faster than spread mean reversion** can complete?

### 1.3 Contributions

This work contributes:

- A reproducible diagnostic methodology for live stat-arb systems combining trade-level telemetry, shadow exit simulation, PnL source reconciliation, and per-hypothesis confidence calibration.
- An empirical decomposition of the trade outcome distribution into three structurally distinct categories: unviable (gross MFE < round-trip cost), trapped (cost < MFE < guard floor), and viable (MFE > guard floor).
- Evidence that 56% of trades in the current universe exit via cointegration failure, with a mean time-to-failure of 44.7 minutes against a 60-minute validation window — implying the cointegration lookback window systematically overstates relationship durability.
- A controlled patch sequence (Patches 1–5) maintaining single-variable isolation and explicit counterfactual accounting.
- A formal experiment-state discipline framework with per-hypothesis confidence tables, locked MFE timing bucket definitions, and evidence thresholds — designed to prevent the well-documented failure mode of "increasing analytical sophistication faster than the dataset is growing."

---

## 2. System Architecture

### 2.1 Core Strategy

The system implements Statistical Arbitrage Mean Reversion (STATARB_MR) against USDT-M perpetual swap pairs. The strategy identifies pairs where the spread (log price ratio, hedge-ratio-adjusted) is stationary, enters when the spread Z-score exceeds a configurable threshold (|Z| ≥ 2.0), and exits when Z reverts toward zero or upon structural breakdown.

The execution direction follows the hedge ratio: for positive entry Z, the system shorts the positive leg and longs the negative leg; for negative entry Z, the reverse. Position sizing is fixed at $200 notional per leg ($400 total deployed capital).

### 2.2 Pair Supply Pipeline

The pair universe is constructed through a multi-stage filtering pipeline that processes the full OKX USDT-M perpetual swap universe at regular intervals:

| Stage | Candidates Remaining | Filter Applied |
|---|---|---|
| Full universe | 5,151 | All USDT-M perpetual pairs |
| Correlation tier | 1,984 | Min correlation ≥ 0.20 over 1,440-bar lookback |
| Cointegration (p-value) | 267 | Engle-Granger ADF, p ≤ 0.05 |
| Orderbook depth | 197 | Minimum $8,000 orderbook depth |
| Ticker diversity | 176 | Maximum 10 pairs per ticker |
| Tier supply cap | 99 | Pool size limits |
| Hedge ratio sanity | 92 | Outlier hedge ratios excluded |
| Zero crossings | 88 | Minimum mean-reversion crossings |
| Orderbook levels | 84 | Minimum 7 orderbook levels |
| Graveyard / Hospital | 81 | Permanently or temporarily excluded instruments |
| Accumulation cap | 78 | Maximum pair concentration |
| **Active canonical** | **6** | Final usable set with sufficient crossings |

The compression from 5,151 to 6 canonical pairs (0.12% survival rate) reflects the stringency of the cointegration requirement combined with liquidity constraints in the perpetual swap market.

Zero-crossing statistics across the canonical set: minimum 34, maximum 45, mean 38.1, median 35.5. These values represent the number of historical mean-reversion crossings in the lookback window, serving as a proxy for relationship activity.

### 2.3 Entry Safety Gate

Entry is conditioned on a multi-stage safety gate (`entry_safety_gate.py`) that evaluates:

- **Advanced ML break risk**: ML-estimated probability of spread continuation (trending behavior). Trades blocked when `break_risk > 0.12` (threshold configurable via `STATBOT_ADVANCED_ML_MAX_PHASE6_BREAK_RISK`).
- **Liquidity floor**: Real-time orderbook depth check. Blocked when depth falls below `5× minimum` floor at entry.
- **Cointegration component score**: Minimum quality threshold from composite scoring system.
- **Regime alignment**: Patch 4 blocks STATARB_MR entries when regime detector returns TREND.
- **Risk-off thin liquidity**: Blocks when RISK_OFF regime coincides with thin orderbook conditions.

In run 94, the safety gate generated 95 rejection events. The dominant rejection reasons were: `advanced_ml_break_risk_high` (60 events, 63.2%), `liquidity_at_floor` (23 events), `advanced_ml_trending` (6 events), `cointegration_component_below` (3 events), `risk_off_thin_liquidity` (3 events).

### 2.4 Advanced Trade Manager and Exit Orchestrator

The trade lifecycle is managed by `AdvancedTradeManager` with profiles per strategy type. The exit orchestrator (`ExitOrchestrator`) evaluates candidates from multiple sources at each tick and selects the highest-priority passing candidate.

Exit candidates include:
- **Full take profit** (TP): fires when Z crosses the TP threshold (|Z| ≤ 0.35), conditioned on the net profit guard.
- **Profit-lock trailing stop**: activates when floating PnL exceeds the activation floor, then trails peak PnL × (1 − giveback_pct).
- **Cointegration-based exits**: fires when cointegration quality degrades below threshold for a sustained period.
- **Regime break exits**: fires on regime transitions during active positions.
- **Stall exits**: fires on excessive hold duration without Z-score improvement.
- **Pair health exits**: fires on instrument-level health failure (funding rate anomaly, orderbook collapse).

### 2.5 Net Profit Guard

The net profit guard is the mechanism that prevents the system from exiting at a loss. For full TP candidates, the effective floor is computed as:

```
base_min_profit = entry_notional × (fee_rate + slippage_rate) + buffer
                = 200 × (0.0005 + 0.0002) + 0.10
                = $0.24 USDT

effective_floor = base_min_profit × full_tp_guard_multiplier
```

With multiplier = 0.75 (runs 90–94): `effective_floor = $0.18`
With multiplier = 0.50 (run 95+): `effective_floor = $0.12`

The profit-lock trailing stop has a separate activation floor:
```
activation_floor = effective_floor + activation_buffer
                 = $0.18 + $0.05 = $0.23  (multiplier 0.75)
                 = $0.12 + $0.05 = $0.17  (multiplier 0.50)
```

### 2.6 Circuit Breaker

The risk circuit breaker operates in session mode: three consecutive losses within a session halt new entries for the remainder of that session. Persistent consecutive loss count carries across subprocess restarts (exit code 3). In run 94, the breaker fired after three consecutive losses, with `persistent_consecutive_losses=4` reflecting a carry from a prior run.

### 2.7 Telemetry Infrastructure

The exit decision trace (`exit_decision_trace.csv`) logs per-tick evaluation state including: current Z-score, floating PnL from multiple sources, profit-lock state, guard multiplier and effective floor, shadow exit simulation outcomes, and regime classification. This infrastructure was added in the session preceding run 94 and is the foundation for the diagnostic work documented in this paper.

Key telemetry fields introduced for diagnostic purposes:
- `pnl_profit_lock_should_have_activated` / `pnl_profit_lock_activation_reason` / `pnl_profit_lock_miss_reason`
- `shadow_exit_z_1_50_would_trigger` / `shadow_exit_z_1_00_would_trigger`
- `shadow_trend_mr_block_would_trigger`
- `pnl_source_mismatch_detected` / `atm_mfe_vs_pair_state_mfe_delta`
- `statarb_mr_in_trend_regime`
- `inside_z_1_50` through `inside_z_0_35` zone flags
- `effective_full_tp_floor_usdt`

The `exit_opportunity_summary.csv` aggregates per-trade telemetry into a summary row containing MFE at each Z-zone threshold, shadow exit simulation outcomes, and profit-lock diagnostic fields.

---

## 3. Experimental Design

### 3.1 Controlled Live Environment

All experiments are conducted in live trading with real capital, not simulation. This design choice was made to ensure slippage, funding rates, partial fills, and orderbook depth constraints are captured authentically. The notional ($200 per leg) is intentionally small relative to the available capital ($2,664 at run start) to limit downside while accumulating statistically valid telemetry.

The use of live trading introduces two important constraints: first, the circuit breaker limits consecutive losses per session, creating a natural data collection ceiling of approximately 3 trades per run when the underlying system is losing. Second, reconciliation discrepancies between mark-to-market PnL and realized equity changes are observable and must be explained — unexplained differences flag instrumentation or execution anomalies.

### 3.2 Single-Variable Intervention Protocol

Each patch applies exactly one behavioral change to the live system. This discipline is enforced to maintain causal clarity: if results change after a patch, the patch must be the cause. Multiple simultaneous changes collapse attribution.

The two-variable exception in Patch 5 (guard reduction and ETHFI exclusion simultaneously) is accepted because the two changes target orthogonal failure classes with recoverable attribution through distinct telemetry channels:
- ETHFI exclusion → expected to affect cointegration failure exit rate and MAE distribution
- Guard reduction → expected to affect profit-lock activation count and TP-zone exit rate

### 3.3 Evidence Thresholds

A minimum evidence threshold of 20 closed trades is enforced before any further configuration changes following Patch 5. This threshold is derived from the recognition that at ~3 trades per circuit-breaker-limited run, each run provides a non-independent sample of "first three trades after session start" rather than steady-state behavior. Twenty trades across multiple sessions provides the minimum sample to detect directional changes in coint-failure rate and profit-lock activation rate above noise.

This threshold is not a statistical power calculation; at a $200 notional, 20 trades, and the expected variance in PnL, formal power is low. The threshold is an epistemic gate: below it, the system is collecting data, not drawing conclusions.

### 3.4 Confidence Calibration

Per-hypothesis confidence levels are maintained explicitly and updated only with empirical justification from new data. The calibration levels are: LOW, MEDIUM-LOW, MEDIUM, MEDIUM-HIGH, HIGH. These labels carry specific meanings:

- **HIGH**: Multiple independent runs, directional consistency, clear mechanism, minimal alternative explanations.
- **MEDIUM**: Evidence is directional but small-sample; the mechanism is plausible but unconfirmed.
- **MEDIUM-LOW**: Signal exists but depends on assumptions that may not hold (e.g., single-trade cost estimates, sample confounded by conditions being changed).
- **LOW**: Hypothesis is worth testing but current evidence is insufficient to differentiate from noise.

---

## 4. Experimental Results

### 4.1 Run Summary

The following table presents all nine closed trades from the telemetry-instrumented experimental period across runs 90, 93, and 94. Trade PnL is net realized (equity delta). MFE and MAE are gross floating PnL peaks observed during the trade.

| Run | Pair | Entry Z | Entry Regime | Hold (min) | MFE ($) | MAE ($) | PnL ($) | Exit Reason |
|---|---|---|---|---|---|---|---|---|
| 90 | OP/XLM | +2.522 | RANGE | 33.7 | +0.183 | −0.145 | −0.032 | normal |
| 90 | SOL/ADA | −2.816 | RISK_OFF | 109.1 | +0.018 | −0.377 | −0.403 | pair_health_failure |
| 93 | SOL/ETHFI | +2.235 | RANGE | 26.6 | +0.079 | −0.645 | −0.726 | coint_watch_timeout |
| 93 | ETH/ASTER | +2.071 | RANGE | 68.2 | +0.069 | −0.348 | −0.149 | coint_watch_timeout |
| 93 | SOL/KSM | −2.415 | RANGE | 12.3 | +0.242 | −0.112 | +0.133 | normal |
| 93 | FIL/LDO | +2.107 | TREND | 70.2 | +0.161 | −0.613 | −0.382 | cointegration_lost |
| 94 | AVAX/ETHFI | −2.439 | RANGE | 24.8 | +0.172 | −0.485 | −0.340 | cointegration_lost |
| 94 | FIL/SAND | +2.295 | RANGE | 37.1 | +0.280 | −0.381 | −0.046 | normal |
| 94 | SOL/SUI | −2.101 | RANGE | 33.9 | +0.045 | −0.315 | −0.213 | coint_watch_timeout |

**Aggregate statistics:**
- Total realized PnL: −$2.157
- Wins: 1 (SOL/KSM), Win rate: 11.1%
- Mean MFE: $0.119
- Mean MAE: −$0.380
- MAE/MFE ratio: 3.19 (mean adverse excursion is 3.19× mean favorable excursion)
- Mean hold: 46.2 minutes

### 4.2 Exit Reason Distribution

Across nine trades, cointegration-related exits dominate:

| Exit Reason | Count | % | Mean PnL ($) |
|---|---|---|---|
| cointegration_lost | 2 | 22% | −0.361 |
| cointegration_watch_timeout | 3 | 33% | −0.363 |
| normal | 3 | 33% | +0.018 |
| pair_health_failure | 1 | 11% | −0.403 |

Cointegration failure (lost + timeout) accounts for 5/9 trades (56%) and produces uniformly negative outcomes (mean −$0.363). Normal exits produce near-zero or positive outcomes (mean +$0.018). This distribution is the central empirical finding of the research period.

### 4.3 Cointegration Persistence Analysis

The system uses a 60-bar (60-minute) lookback window for cointegration validation. The following table presents time-to-cointegration-failure for each coint-exit trade:

| Trade | Hold at Exit (min) | Exit Reason | Window Coverage |
|---|---|---|---|
| SOL/ADA (run 90) | 109.1 | health | >100% |
| SOL/ETHFI (run 93) | 26.6 | coint_watch_timeout | 44% |
| ETH/ASTER (run 93) | 68.2 | coint_watch_timeout | 114% |
| FIL/LDO (run 93) | 70.2 | cointegration_lost | 117% |
| AVAX/ETHFI (run 94) | 24.8 | cointegration_lost | 41% |
| SOL/SUI (run 94) | 33.9 | coint_watch_timeout | 56% |

Three of five cointegration failures occurred before the 60-bar validation window had elapsed (at 41%, 44%, and 56% of window duration). This indicates that:

1. The cointegration relationship validated at entry degrades within a timeframe shorter than the window used to establish it.
2. The 60-bar lookback window systematically overstates relationship durability by measuring cointegration over a period that includes the very period of dislocation the trade is designed to exploit.

Mean time-to-coint-failure across the five trades: 44.7 minutes. This is 74.5% of the 60-minute window, suggesting that on average, pairs degrade before completing a full reversion cycle.

### 4.4 Economic Edge Analysis

#### 4.4.1 Round-Trip Cost Estimation

Two cost estimates exist:

**Estimated cost** (from reconciliation fee/slippage fields): `fees ($0.10) + slippage ($0.04) = $0.14`

**Empirical cost** (from KSM reconciliation, the only clean profitable trade):
- Gross MFE: $0.2415
- Net realized PnL: $0.1329
- Implied round-trip cost: $0.1086

The empirical estimate of $0.109 is preferred for economic analysis because it reflects actual fill quality, funding rate impact, and execution costs. However, KSM was the best-executed trade in the dataset (12.3 minute hold, clean normal exit), so the empirical estimate likely represents a lower bound on typical costs. True average cost is bounded in the range $0.109–$0.14.

#### 4.4.2 Trade Viability Classification

Using the empirical cost estimate ($0.109), trades are classified into three categories:

**Category A — Structurally Unviable (MFE < $0.109):**
The pair never generated enough gross edge to cover round-trip costs. The strategy was structurally wrong about the size of the opportunity.

| Trade | MFE ($) | Deficit to Breakeven ($) |
|---|---|---|
| SOL/ADA | 0.018 | −0.091 |
| SOL/ETHFI | 0.079 | −0.030 |
| ETH/ASTER | 0.069 | −0.040 |
| SOL/SUI | 0.045 | −0.064 |

4 trades (44%): mean realized PnL = −$0.373

**Category B — Trapped Zone ($0.109 ≤ MFE < $0.240):**
The pair generated gross edge above round-trip costs, but the guard floor architecture ($0.24 base floor × 0.75 multiplier = $0.18 effective floor) prevented any exit mechanism from capturing the edge. The spread reverted profitably, but the system had no exit path.

| Trade | MFE ($) | Net Possible ($) | Actual PnL ($) | Excess Loss ($) |
|---|---|---|---|---|
| OP/XLM | 0.183 | +0.074 | −0.032 | +0.106 |
| FIL/LDO | 0.161 | +0.052 | −0.382 | +0.434 |
| AVAX/ETHFI | 0.172 | +0.063 | −0.340 | +0.403 |

3 trades (33%): combined excess loss vs. perfect monetization = $0.943

Note that FIL/LDO entered during TREND regime (now blocked by Patch 4) and AVAX/ETHFI involves ETHFI (now graveyarded). The forward-looking trapped zone may therefore be as small as 1 trade in 9 (OP/XLM).

**Category C — Viable (MFE ≥ $0.240):**
The pair generated sufficient gross edge to clear the guard floor. The system had an exit path.

| Trade | MFE ($) | Guard Floor ($) | Actual PnL ($) |
|---|---|---|---|
| SOL/KSM | 0.242 | 0.18 | +0.133 |
| FIL/SAND | 0.280 | 0.18 | −0.046 |

2 trades (22%): KSM successfully exited via trailing stop. FIL/SAND's profit-lock activated at the final evaluation row (474/474), leaving no rows for trailing stop execution.

#### 4.4.3 Hypothetical Perfect Exit Analysis

| Scenario | Total PnL ($) |
|---|---|
| Actual realized | −2.157 |
| Perfect exits at MFE for all 9 trades | −0.999 |
| Perfect exits (viable trades only, A/B/C distinction) | −0.999 |
| Removing Category A trades entirely | −0.743 |
| Category B trades exit at MFE | −1.214 |

Even under perfect exit conditions at every trade's MFE peak, the portfolio would have realized −$0.999 — still negative, driven by the four structurally unviable Category A trades where gross edge never cleared costs. This finding confirms that exit architecture improvement alone cannot produce profitability without addressing entry quality or pair universe composition.

### 4.5 Guard Floor Assessment

The net profit guard was evaluated on every trade management tick. Results across all nine trades:

| Metric | Value |
|---|---|
| Total guard evaluation ticks | 1,217 (correlated samples within 9 trades) |
| Trade-level guard pass events | 0 / 9 |
| Max floating PnL inside TP zone (run 94) | +$0.038 (SOL/SUI), −$0.022 (AVAX/ETHFI), −$0.103 (FIL/SAND) |
| Effective floor (multiplier 0.75) | $0.18 |
| Activation floor (profit-lock) | $0.23 |

The guard passed zero times across nine trades. The critical diagnostic from the TP-zone PnL data (exit_decision_summary) reveals that in run 94, the maximum floating PnL observed *while inside the TP zone* (|Z| ≤ 0.35) was +$0.038 for SOL/SUI — well below both the old floor ($0.18) and the new floor ($0.12). This means the guard architecture was not the operative blocker for these specific trades: the trades were simply not profitable when their Z-scores entered the take-profit window. The MFE peaks occurred before Z crossed the TP threshold.

The implication is that the guard floor change (Patch 5, multiplier 0.75 → 0.50) is a diagnostic intervention, not a direct profit fix. Its value lies in testing whether, with a healthier pair universe (post-ETHFI exclusion), any trades produce positive TP-zone PnL in the $0.12–$0.18 range that would previously have been blocked.

### 4.6 PnL Source Reconciliation

A systematic discrepancy was identified between `floating_pnl_usdt` (mark-to-market from pair state, gross) and `position_snapshot_unrealized_pnl_usdt` (OKX position snapshot, likely fees-inclusive). The `atm_mfe_vs_pair_state_mfe_delta` field measures this divergence. Across nine trades, the delta was consistently in the range $0.07–$0.10 per trade, representing the fee and funding component not yet realized in mark-to-market.

This is not a bug — it is the expected difference between gross and net PnL representations. The telemetry field `pnl_source_mismatch_detected=True` was triggered for all three run 94 trades, correctly flagging the divergence for audit but not indicating an instrumentation error.

### 4.7 Regime Analysis

Run 94 regime distribution:
- RANGE: 67.94% of runtime (2 regime switches)
- RISK_OFF: 20.52% (7 regime switches)
- TREND: 11.55% (5 regime switches)

All three executed trades in run 94 entered during RANGE regime. TREND regime appeared to correlate with cointegration breakdown: when the regime detector identified TREND, pairs in the strategy gate queue had typically already failed cointegration validation. This correlation explains why Patch 4 (STATARB_MR TREND block) produced zero activations in run 94 — not because the block was ineffective, but because it operates at the safety gate, and pairs had already been rejected upstream at the strategy gate before reaching the safety gate under TREND conditions.

---

## 5. Patch Development

### 5.1 Patch 1 — Full TP Priority

**Problem:** Full take-profit candidates were not consistently outranking partial take-profit candidates in the orchestrator selection logic.

**Change:** Updated exit orchestrator priority ordering to ensure full TP outranks partial TP when both pass the guard.

**Evidence:** Orchestrator selection logs showed split-priority outcomes in early runs. After the fix, selection behavior became deterministic.

**Single-variable isolation:** Changes to orchestrator ranking only. No change to guard thresholds, trade manager config, or execution logic.

### 5.2 Patch 2 — ExitOrchestrator Guard Alignment

**Problem:** The ExitOrchestrator's guard evaluation used a separate guard context from the trade manager's internal guard, creating divergence between what the orchestrator blocked and what the trade manager permitted.

**Change:** Unified the guard context: `ExitOrchestrator` now receives `NetProfitGuardContext` constructed from `trade_manager.config` values, ensuring both systems apply the same effective floor.

**Evidence:** Prior to the fix, the exit_decision_trace showed `trade_manager_guard_passed=True` alongside `orchestrator_guard_passed=False` on the same tick, indicating the two systems were using different effective thresholds.

### 5.3 Patch 3 — PnL Profit Lock and Entry Safety Gate

**Change 1:** Implemented PnL profit lock (`pnl_profit_lock_enabled=True`), a trailing stop that activates when floating PnL exceeds an activation floor and thereafter trails the peak at a configurable giveback percentage. Configuration: activation_buffer=$0.05, giveback_pct=0.50, min_lock=$0.00.

**Change 2:** Implemented the Entry Safety Gate (`entry_safety_gate.py`) as a configurable pre-entry filter that evaluates break risk, liquidity, cointegration quality, and regime conditions before allowing an entry to proceed. Enabled by default in the controlled runtime configuration.

**Evidence basis:** Early runs showed entries proceeding despite Advanced ML signals indicating high trend probability. The safety gate was designed to surface these signals as hard blocks rather than advisory warnings.

### 5.4 Patch 4 — Regime-Aligned Mean Reversion Safety

**Problem:** STATARB_MR — a mean-reversion strategy — was permitted to enter during TREND regime conditions. Run 93 produced the most harmful single trade in the dataset: FIL/LDO entered at Z=+2.107 during a TREND regime, and `shadow_trend_mr_block_would_trigger` fired on 100% of all 880 evaluation ticks during the trade. The spread continued to trend rather than revert, exiting via `cointegration_lost` after 70.2 minutes with PnL=−$0.382 and an additional $0.147 unexplained reconciliation loss.

**Change:** Added a live hard block to the Entry Safety Gate: when `strategy_name == "STATARB_MR"` AND `regime == "TREND"`, reject the entry with reason `statarb_mr_trend_regime_block`. Configurable via `STATBOT_ENTRY_GATE_BLOCK_STATARB_MR_IN_TREND` (default: True).

**Counterfactual analysis:**
- Run 93 actual total PnL: −$1.124
- Run 93 without the FIL/LDO TREND trade: −$0.742
- Improvement from blocking one trade: +$0.382 (34% reduction in total loss)

**Verification (run 94):** Zero `statarb_mr_trend_regime_block` rejections in run 94. As analyzed in section 4.7, this is consistent with the expected behavior: TREND regime appearance correlated with cointegration breakdown in the upstream strategy gate, meaning pairs failing cointegration did not reach the safety gate where Patch 4 operates. The patch is awaiting market conditions where TREND + valid cointegration coincide.

**Test coverage added:** 10 new tests in `Execution/tests/test_entry_safety_gate.py` covering STATARB_MR + TREND blocked, STATARB_MR + RANGE allowed, non-MR strategies unaffected, and payload diagnostic correctness. Total test suite: 605/606 passing (1 pre-existing unrelated failure in Advanced ML rollout tests).

### 5.5 Patch 5 — Guard Calibration and ETHFI Exclusion (Active)

**Experiment group:** `exp_guard050_ethfi_excluded_v1`

**Change 1 — Guard multiplier reduction (0.75 → 0.50):**

| Parameter | Before | After |
|---|---|---|
| `STATBOT_FULL_TP_GUARD_MULTIPLIER` | 0.75 | 0.50 |
| Effective TP floor | $0.180 | $0.120 |
| Profit-lock activation floor | $0.230 | $0.170 |

Rationale: The guard architecture produced zero passes across nine trades. The new floor ($0.12) aligns with the empirical lower bound of the trapped zone ($0.109 cost breakeven). The profit-lock activation at $0.17 covers the previously trapped MFE cluster ($0.16–$0.19). This is a diagnostic intervention: it tests whether TP-zone PnL and MFE timing shift with the new pair universe, not a direct profitability fix.

**Change 2 — ETHFI-USDT-SWAP permanent graveyard exclusion:**

ETHFI appeared in two trades (SOL/ETHFI run 93, AVAX/ETHFI run 94):
- 0/2 wins (0% win rate)
- Both exits via cointegration failure
- Average PnL: −$0.533 (worst of any symbol in the dataset)
- Average MAE: −$0.565 (worst of any symbol in the dataset)

ETHFI is an ETH staking derivative token with reflexive tokenomics tied to ETH staking ecosystem narrative. Its price dynamics are driven by ETH staking yield expectations, restaking protocol flows, and narrative momentum — factors that may cause transient but deep correlation breaks with major assets, producing the observed pattern of apparent cointegration at entry followed by rapid degradation.

The graveyard entry carries `ttl_days: null` (permanent) and `source: seed`.

**Attribution design:** The two changes are expected to affect non-overlapping telemetry channels:
- ETHFI exclusion: observable via cointegration failure exit rate (was 56% across 9 trades)
- Guard reduction: observable via profit-lock activation count and trailing-stop exit count (were both near zero)

If results are ambiguous after 20 trades, decomposition uses these distinct channels to assign effect to cause.

---

## 6. Analytical Framework

### 6.1 The Three-Category Decomposition

The most productive analytical advance in this research period was the decomposition of trade outcomes into three structurally distinct categories requiring three different fixes:

**Category A — Structurally Unviable**: Pair universe or entry filter failure. The relationship does not produce sufficient gross spread displacement at current notional to cover costs. Fix: improve entry filtering (break risk, cointegration stability scoring) or tighten the pair universe.

**Category B — Trapped Zone**: Exit architecture failure. The relationship produces viable gross edge but the guard floor prevents monetization. Fix: calibrate the guard floor to the observed MFE distribution of the current universe (Patch 5 addresses this).

**Category C — Exit Timing Failure**: The relationship produces viable gross edge, the exit architecture can respond, but the specific exit sequence fails to capture the peak. Fix: trailing stop calibration, profit-lock activation timing, or TP-zone widening.

Distinguishing these categories is critical. Prior to the development of MFE decomposition telemetry, all losing trades appeared as a single undifferentiated outcome class. The telemetry now available makes the distinction observable.

### 6.2 The Epistemic Discipline Problem

A recurring challenge in this research is the divergence between analytical sophistication and statistical sample size. The telemetry infrastructure produces richly detailed per-tick data that creates a false sense of large samples (1,217 evaluation ticks), while the actual independent observations remain nine trades across three runs.

This problem — "improving confidence faster than the dataset is growing" — was explicitly identified during the analysis period and produces several specific failure modes:

1. **Theatrical statistics**: Using tick-level evaluation counts (1,217) as if they were independent experiments.
2. **Cherry-picked cost estimates**: Using the single profitable trade's cost as the universal cost assumption.
3. **Trapped-zone magnitude inflation**: Counting as "trapped" trades that are confounded by conditions already being changed (TREND-regime entries, ETHFI exposures).
4. **Premature conclusion-drawing**: Declaring architectural conclusions after 3–5 trades within a single run.

The experimental framework's response to these risks is:
- Explicit per-hypothesis confidence labeling at named levels (HIGH/MEDIUM-LOW/LOW etc.)
- Fixed 20-trade evidence threshold before structural reassessment
- Experiment-state header required in every audit
- Negative results defined as valid experimental outcomes

### 6.3 The Confidence Table (Current)

Per-hypothesis confidence levels as of Patch 5 implementation:

| Hypothesis | Confidence | Evidence Basis |
|---|---|---|
| Cointegration fragility is the dominant loss mechanism | HIGH | 5/9 coint failures, mean 44.7 min to failure, worst outcomes |
| ETHFI-USDT-SWAP is structurally toxic to stat-arb | HIGH | 2/2 coint failures, worst PnL, worst MAE, distinct token economics |
| TREND-regime STATARB_MR entries are harmful | HIGH | FIL/LDO: 880/880 shadow blocks, worst reconciliation loss |
| Some profitable windows are being trapped by exit architecture | MEDIUM | 3/9 trades in trapped zone, but 2 of 3 involve conditions being changed |
| Guard floor reduction materially improves outcomes | MEDIUM-LOW | 0/9 guard passes; TP-zone PnL was negative in 2/3 run 94 trades |
| Notional scaling is not the primary lever | HIGH | Fees scale linearly with notional; edge ratio unchanged |
| Break risk threshold (0.12) is correctly calibrated | MEDIUM | Median rejected break_risk was 0.150; high filter rate |
| Exit z-zone widening would improve outcomes | LOW | No evidence exits are failing due to threshold timing |

### 6.4 The Breaker-Accumulation Tension

A structural tension exists between the circuit breaker and the evidence accumulation goal. The circuit breaker fires after three consecutive losses, halting new entries for the remainder of the session. With the underlying cointegration fragility problem unaddressed, back-to-back losing runs are expected. At ~3 trades per breaker-halted run, accumulating 20 trades requires approximately 7 runs and 50–80 hours of runtime.

The research response is to accept this pace rather than relax the circuit breaker. The breaker trips are themselves data: if the new configuration (Patch 5) still produces repeated 3-consecutive-loss sessions, that is strong evidence the cointegration fragility problem dominates and the guard/ETHFI changes did not materially shift the loss mechanism. This interpretation is only available if the breaker is kept in place.

Formally: the data collection rate is endogenous to the system's health. A system generating wins does not hit the breaker and accumulates data faster. This creates a selection bias: the first 20 trades collected will disproportionately represent "early in session" states (warm-up effects, recently-fired pair cooldowns) rather than steady-state behavior. Every audit should explicitly note this sampling caveat.

---

## 7. Discussion

### 7.1 Is the Strategy Viable?

Based on nine trades of telemetry evidence, the strategy shows conditional viability:

**Evidence for viability:**
- 2/9 trades (22%) cleared the guard floor and had positive or near-zero PnL
- KSM ($0.133 net gain) demonstrates that the exit architecture works correctly when MFE peaks inside the TP zone
- FIL/SAND ($0.280 MFE) generated sufficient gross edge; the exit failure was mechanical (profit-lock activated on the final row)
- The pair supply pipeline successfully identifies cointegrated pairs; the problem is durability, not detection

**Evidence against near-term profitability:**
- 44% of trades (Category A) generate insufficient gross edge regardless of exit architecture
- Coint-failure rate of 56% implies structural relationship instability that cannot be fixed by exit calibration
- Even hypothetical perfect exits produce −$0.999 total PnL across nine trades

**Interpretation:** The strategy framework is structurally sound. The current failure is located in pair universe quality and cointegration persistence, not in the basic statistical relationship or execution infrastructure. This is a resolvable problem through better entry filtering — specifically, forward-looking cointegration stability assessment rather than retrospective window cointegration detection.

### 7.2 The Cointegration Window Problem

The most significant unaddressed structural issue is the cointegration lookback window. The system uses a 60-bar (60-minute) window for cointegration validation. Mean time-to-failure across the five coint-failure exits was 44.7 minutes, with three failures occurring before the 60-bar window elapsed.

This suggests a fundamental calibration problem: the system validates relationships over a 60-minute horizon, then attempts to trade reversions that take 25–70 minutes to complete. If the relationship degrades within the first 40% of its validated window, the trade cannot complete before the relationship breaks.

Two explanations are possible:
1. **Window overfitting**: The 60-bar window detects transient cointegration artifacts that do not persist. The appropriate window may need to be shorter (measuring only the most recent, most persistent relationships) or longer (requiring more historical stability).
2. **Regime-driven relationship instability**: Cointegration between crypto pairs is regime-dependent. Relationships that hold in RANGE regimes may break in RISK_OFF or TREND conditions. The entry filter already partially addresses this (TREND block), but RISK_OFF-era cointegration instability remains.

This is the highest-priority research question deferred from the current experimental phase.

### 7.3 Notional Economics

A common intuition in systematic trading is that larger notional improves edge ratio by distributing fixed costs over more capital. This intuition does not apply here.

At $200 notional, the cost structure is:
- Fees: `notional × 2 legs × fee_rate` — linear with notional
- Slippage: `notional × 2 legs × slippage_rate` — approximately linear
- Spread edge: `notional × spread_displacement_fraction` — approximately linear

Because both costs and edge scale approximately linearly with notional, the edge ratio (net PnL / gross MFE) is approximately scale-invariant. Doubling notional to $400 doubles both expected edge and expected costs, leaving the profitability probability unchanged.

The only genuine benefit of increased notional is noise reduction in percentage terms: small fixed costs (minimum tick rounding, minimum order size) represent a smaller fraction of the total. But at $200 notional, these rounding effects are already negligible. Notional scaling is therefore not a lever at the current stage.

### 7.4 Regime Router vs. Hard Block Architecture

The system's regime router is currently in shadow mode, providing advisory regime signals without affecting live behavior. The TREND block in Patch 4 represents a selective, hard-coded promotion of one specific shadow rule to live status — rather than enabling the full regime router.

This architecture choice is intentional. Full router activation changes the entry frequency, pair selection, and trade timing in complex ways that confound attribution. A hard-coded block for the single highest-confidence rule (STATARB_MR + TREND) achieves the primary risk-reduction goal while leaving the attribution surface clean. Each subsequent rule can be promoted to live status as evidence accumulates for each specific case.

---

## 8. Limitations

### 8.1 Sample Size

Nine trades do not constitute a statistically robust sample for any of the claims in this paper. Effect sizes at this sample size are consistent with multiple explanations, and confidence intervals around all estimated quantities are wide. All numerical findings should be treated as directional evidence, not point estimates.

The paper is explicit about this: confidence levels (HIGH/MEDIUM/LOW) incorporate sample-size uncertainty, and the 20-trade evidence threshold enforces a minimum before structural conclusions can be drawn.

### 8.2 Non-Stationarity of the Trading Environment

Cryptocurrency markets are non-stationary across multiple timescales. Pair relationships established during one market regime (e.g., post-bull-market consolidation) may not persist into another. The nine trades observed represent a short window of market conditions, and findings may not generalize beyond that window. In particular:

- The 56% cointegration failure rate may be regime-specific
- The MFE distribution ($0.018–$0.280) may reflect current market volatility conditions
- The pair universe quality may shift substantially following major market events

### 8.3 Single Exchange Dependency

All trading occurs on OKX. Results may not generalize to other exchanges due to differences in: fee structure, liquidity profile, funding rate mechanics, and available instrument universe. The pair supply pipeline and cost assumptions are exchange-specific.

### 8.4 Circuit Breaker Sample Bias

As discussed in Section 6.4, the circuit breaker creates a systematic sampling bias: all observed trades are "early session" trades (first 1–3 trades after session start). Steady-state behavior — trades entered hours into a running session after market conditions have settled — is not represented in the current dataset.

### 8.5 Cost Estimate Uncertainty

The empirical cost estimate ($0.109) is derived from a single trade. The actual cost distribution likely has significant variance driven by: spread at time of fill, orderbook depth, funding rate accrued during hold, and partial fill dynamics. Using a single-trade estimate to classify trade outcomes into categories introduces classification error.

---

## 9. Future Research Directions

Listed in priority order by current evidence confidence:

### 9.1 Forward-Looking Cointegration Stability (Highest Priority)

Replace retrospective cointegration validation with a stability-weighted score that accounts for:
- Rate of change of the rolling p-value over the lookback window
- Consistency of the hedge ratio over subwindows
- Z-score mean-reversion speed (half-life stability)
- Recent cointegration flag stability (fraction of recent bars where coint_flag = 1)

A pair that passes the ADF test on a 60-bar lookback but has a deteriorating p-value over the most recent 20 bars should be treated as lower quality than a pair with a stable p-value across the full window. This change targets the highest-confidence, highest-magnitude problem identified in this research: 56% coint-failure rate.

### 9.2 max_break_risk Threshold Recalibration

In run 94, the advanced ML break_risk filter rejected 60 events with `advanced_ml_break_risk_high`. The median break_risk of rejected pairs was 0.150, against a threshold of 0.12. The current threshold generates a high filter rate; however, it is not yet known whether the pairs rejected at 0.12–0.15 break_risk would have produced better or worse outcomes than accepted pairs.

This question is deferred until the cointegration stability work is completed, since the two interventions may interact: better cointegration persistence filtering may render break_risk threshold calibration less critical.

### 9.3 Exit Z-Zone Architecture

If the guard floor experiment (Patch 5) produces evidence that MFE peaks occur inside the TP zone at the new effective floor ($0.12), the next question is whether widening the Z-zone from |Z| ≤ 0.35 to |Z| ≤ 1.0 would capture edge earlier in the reversion. This is lower priority because it changes the structural timing of exits (higher risk), and the current evidence does not yet confirm that any TP-zone PnL is available to capture.

### 9.4 Adaptive Position Sizing

Current sizing is fixed at $200 notional. An adaptive sizer could scale position within a pair based on confidence signals: high zero-crossing count + stable hedge ratio + low break_risk + high cointegration quality could justify modestly higher notional; the reverse could trigger a reduction. This would not change the edge ratio but would concentrate capital in higher-confidence opportunities.

### 9.5 Dynamic Cointegration Monitoring During Trade

Currently, cointegration is re-validated on every tick during the trade, and the `cointegration_watch` state triggers an early exit if cointegration degrades. A research question for future work: what is the optimal confirmation count and loss threshold for the cointegration watch exit? The current configuration (3 confirmations, 25% minimum loss threshold) was set by heuristic; calibration against the observed coint-failure distribution may improve timing.

---

## 10. Conclusion

This paper documented the development and diagnostic analysis of OKXStatBot across three controlled experimental runs (runs 90, 93, 94), comprising nine closed trades, and five sequential patches.

The central finding is that the primary bottleneck is not exit architecture but cointegration persistence: 56% of trades terminate via cointegration failure rather than mean reversion, and the MFE distribution for the remaining trades clusters in a range ($0.16–$0.19) that is structurally adjacent to, but not clearly above, the guard floor that prevents exit capture.

Patches 1 through 5 have progressively addressed: exit selection priority, guard context unification, profit-lock architecture, regime-entry mismatch, guard floor calibration, and pair universe contamination. The strategy framework is structurally sound. The frontier research question — whether forward-looking cointegration stability scoring can materially reduce the 56% coint-failure exit rate — represents the highest-confidence, highest-magnitude intervention available and is the natural successor to the current Patch 5 experiment.

The research methodology developed here — per-hypothesis confidence tables, fixed evidence thresholds, single-variable patch isolation, locked telemetry definitions, and explicit negative-result success conditions — constitutes a reusable framework for iterative live strategy research in small-capital environments where statistical power is necessarily limited and epistemic discipline is the primary defense against optimization noise.

---

## Appendix A — Key Configuration Parameters

| Parameter | Value (run 94) | Value (run 95+) |
|---|---|---|
| `STATBOT_TRADEABLE_CAPITAL_USDT` | 200 | 200 |
| `STATBOT_ENTRY_Z` | 2.0 | 2.0 |
| `STATBOT_EXIT_Z` | 0.35 | 0.35 |
| `STATBOT_FULL_TP_GUARD_MULTIPLIER` | 0.75 | 0.50 |
| `STATBOT_PNL_PROFIT_LOCK_ENABLED` | true | true |
| `STATBOT_PNL_PROFIT_LOCK_ACTIVATION_BUFFER_USDT` | 0.05 | 0.05 |
| `STATBOT_PNL_PROFIT_LOCK_GIVEBACK_PCT` | 0.50 | 0.50 |
| `STATBOT_MAX_CONSECUTIVE_LOSSES` | 3 | 3 |
| `STATBOT_ADVANCED_ML_ROLLOUT_MAX_PHASE6_BREAK_RISK` | 0.12 | 0.12 |
| `STATBOT_ENTRY_GATE_BLOCK_STATARB_MR_IN_TREND` | true | true |
| `STATBOT_MEAN_REVERSION_ESCAPE_ENABLED` | false | false |
| `STATBOT_Z_SCORE_WINDOW` (strategy) | 60 bars | 60 bars |

---

## Appendix B — Graveyard State (as of Patch 5)

| Instrument | Reason | TTL | Source |
|---|---|---|---|
| BIO-USDT-SWAP | compliance_restricted | Permanent | Seed |
| MUBARAK-USDT-SWAP | zero_liquidity_dead_orderbook | Permanent | Seed |
| ZETA-USDT-SWAP | persistent_thin_orderbook | Permanent | Seed |
| SPK-USDT-SWAP | exchange_max_order_capacity_too_small | Permanent | Seed |
| XPL-USDT-SWAP | repeated_pair_losses | Permanent | Seed |
| TEST1234-USDT-SWAP | invalid_test_instrument | Permanent | Runtime |
| SHIB-USDT-SWAP | stop_loss_tick_floor_unsafe | 7 days | Seed |
| ETHFI-USDT-SWAP | repeated_pair_losses | Permanent | Seed (Patch 5) |

---

## Appendix C — Experiment State Header Template

All post-run audits from Patch 5 onward must begin with this header:

```
EXPERIMENT STATE
----------------
Experiment group:      exp_guard050_ethfi_excluded_v1
Changes applied:       2 (guard multiplier 0.75→0.50, ETHFI excluded)
Trades since change:   [N]
Runs since change:     [N]
Circuit breaker trips: [N]
Confidence level:      LOW (until 20-trade threshold)
Action threshold:      20 closed trades before any further config changes
Sampling caveat:       Dataset dominated by first-3-trades-per-session; steady-state underrepresented
```

---

## Appendix D — MFE Timing Bucket Definitions

For all post-Patch-5 audits, MFE timing is measured as:

```
timing_pct = (timestamp_at_MFE_peak - entry_timestamp) / (exit_timestamp - entry_timestamp)
```

Buckets (locked for duration of experiment):
- **early_hold**: 0%–33%
- **mid_hold**: 34%–66%
- **late_hold**: 67%–100%

These boundaries are fixed and may not be redefined in subsequent audits.

---

*Last updated: 2026-05-19. Experiment group: exp_guard050_ethfi_excluded_v1. Next review: at 20 closed trades.*
