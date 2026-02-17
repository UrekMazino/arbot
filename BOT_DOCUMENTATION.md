# OKX StatBot - Statistical Arbitrage Documentation

## 1. System Overview
StatBot is a high-frequency (1-minute resolution) autonomous trading system optimized for the OKX exchange. It implements a **Statistical Arbitrage** strategy, specifically **Pairs Trading**, utilizing cointegration as the primary mean-reversion engine. The system is architected to handle long-running execution with automated pair switching and self-healing capabilities.

---

## 2. Core Strategy & Mathematics

### Cointegration (The ADF Test)
The bot uses the **Augmented Dickey-Fuller (ADF)** test to verify the stationarity of the spread between two assets. 
*   **P-Value Threshold**: 0.15 (A p-value < 0.15 indicates a statistically significant cointegrated relationship).
*   **Stationarity**: Cointegration ensures that a linear combination of two non-stationary price series produces a stationary residual (the spread), which is predictable and mean-reverting.

### Hedge Ratio & Spread Calculation
The spread is calculated using an **Ordinary Least Squares (OLS)** regression on the natural logarithms of the asset prices. Using log-prices ensures the hedge ratio is scale-invariant and represents percentage moves.
*   **OLS Model**: `ln(Price_A) = α + β * ln(Price_B) + ε`
*   **Formula**: `Spread = ln(Price_A) - (β * ln(Price_B))`
*   **Hedge Ratio (β)**: Determined dynamically by the OLS fit, representing the units of Asset B needed to hedge one unit of Asset A.

### Z-Score Normalization
The Z-Score represents the number of standard deviations the current spread is from its moving average, allowing for a standardized entry/exit signal.
*   **Window**: 21 periods (1-minute bars).
*   **Formula**: `Z = (Spread_t - μ_Spread) / σ_Spread`
*   Where `μ` is the 21-period moving average and `σ` is the 21-period standard deviation.

---

## 3. Architecture & Execution Flow

### Subprocess Manager (Self-Healing)
StatBot employs a dual-process architecture (`main_execution.py`):
1.  **Manager Process**: Monitors the execution process.
2.  **Execution Process**: Performs the trading logic.
*   **Exit Code 3**: When a pair switch is required, the execution process exits with code 3. The Manager detects this, re-loads the new configuration from `active_pair.json`, and restarts the bot. This ensures clean memory management and fresh API session initialization.

### The Trade Cycle (Latency: ~5-7s)
1.  **Consolidated API Fetch**: Single call to retrieve all account positions and orders to minimize rate limit consumption.
2.  **Market Data Update**: Fetches 1m Klines and live Orderbook (5-level depth) mid-prices.
3.  **Circuit Breaker**: Evaluates cumulative P&L against `tradeable_capital_usdt`.
4.  **Decision Engine**: Evaluates Z-score against persistence requirements and health metrics.
5.  **Regime Router (Phase 2, Optional)**: Evaluates market regime and, in `active` mode, applies gate enforcement plus entry-policy overrides for new positions.

---

## 4. Signal Generation

### Entry Criteria (🎯)
*   **Threshold**: `|Z-Score| >= 2.0`.
*   **Persistence**: The Z-Score must satisfy the threshold for **3 consecutive bars** (3 minutes) to filter out noise and flash spikes.
*   **Direction**:
    *   **Positive Z (> 2.0)**: Sell the spread (Short Asset A, Long Asset B).
    *   **Negative Z (< -2.0)**: Buy the spread (Long Asset A, Short Asset B).

### Exit Criteria (Current Runtime Order)
Exits are evaluated as a priority stack while in position:

1. **Tier 5 Profit Take (adaptive)**: Exit when floating PnL reaches a dynamic USDT target based on entry notional.
2. **Tier 1 Hard Stop**: Exit when trade PnL% reaches the configured hard-stop threshold (basis: notional by default, equity optional).
3. **Tier 1.5 Risk-Off Cointegration Loss**: Exit early when regime is `RISK_OFF`, cointegration is lost, and the trade remains negative after confirm/grace safeguards.
4. **Tier 2-4 Cointegration Exits (optional)**: Disabled by default; can be enabled via env flags.
5. **ATM Dynamic Exit**: Advanced Trade Manager handles trailing stop, partial exit, max hold, and mean-reversion target exits.
6. **Funding Bleed Guard**: Exit if funding cost materially erodes unrealized gains.
7. **No-entry-context fallback**: Conservative catastrophic-stop and mean-reversion fallback when entry context is missing (e.g., restart with open positions).

Notes:
* In normal operation, mean reversion is primarily handled by ATM.
* ATM mean-reversion target hits are signal-based exits and are not guaranteed to be positive realized PnL after fees/slippage.
* Hard-stop exits can trigger a post-close pair switch.

---

## 5. Health Scoring System (0-100)
A periodic health check (default every 1 hour) calculates a score based on the following weights. If the score falls below **40**, a pair switch is triggered.

| Metric | Threshold | Penalty | Category |
|--------|-----------|-----------|------------|
| **P-Value** | >= 0.15 | -50 pts | Critical |
| **P-Value** | 0.05 - 0.15 | -15 pts | Warning |
| **Spread Trend** | > 0.002 | -30 pts | Critical |
| **Z-Score** | > 6.0 | -25 pts | Critical |
| **Consecutive Losses**| >= 3 | -20 pts | Performance |
| **Recent Loss** | per loss | -5 pts | Performance |
| **Correlation** | < 0.60 | -15 pts | Warning |
| **ADF Ratio** | < 0.8 | -15 pts | Warning |
| **Zero Crossings** | < 15 | -15 pts | Warning |

---

## 6. Risk Management & Safety

### Position Sizing & Precision
*   **2% Rule**: The bot risks exactly **2% of total capital** per trade. Position sizes are calculated based on the distance to the fail-safe stop loss.
*   **Execution Buffer**: A **0.07% (7 bps)** buffer is applied to mid-prices for entries (0.05% taker fee + 0.02% slippage margin) to ensure immediate execution.
*   **Dynamic Rounding**: Tick size and lot size are fetched dynamically from the OKX API to ensure order precision.
*   **Contract-Aware Notional**: Swap sizing uses `ctVal` and `ctMult` to compute quote-per-contract for each leg. Contract values are logged at entry for transparency.
*   **Pre-Trade Balance Gate (USDT)**: On entry signal, the bot logs a USDT balance snapshot (`availBal`/`availEq`) and runs a pre-trade notional check against `availEq`. Orders are skipped if they would exceed available equity.
*   **Liquidity Guard (Optional)**: If enabled, the bot skips entries when available liquidity / target size is below a configured ratio (`STATBOT_MIN_LIQUIDITY_RATIO`, legacy `STATBOT_LIQUIDITY_MIN_RATIO`). If the ratio fails, it first attempts to downsize per-leg capital, then progressively relaxes the minimum ratio (default steps: 3.0 -> 2.5 -> 2.0 -> 1.5 -> 1.0). If the adjusted target falls below the exchange minimum order size, the entry is skipped.
*   **Margin Mode**: Configured for **cross margin** (recommended for pairs trading). In cross mode, all positions share the account's margin pool, making it capital efficient for simultaneous long+short positions. Isolated mode requires separate margin for each position.

### Safety Exits

#### Hybrid Exit Stack + ATM
The runtime exit controller applies a hybrid stack before/with ATM:

1. **Tier 5 Profit Take (adaptive)**
   - Target USDT = `clamp(entry_notional * STATBOT_PROFIT_TARGET_PCT, STATBOT_PROFIT_TARGET_MIN_USDT, STATBOT_PROFIT_TARGET_MAX_USDT)`
   - Defaults: `0.5%`, min `5`, max `50`.
2. **Tier 1 Hard Stop**
   - Triggers at `-STATBOT_HARD_STOP_PNL_PCT` (default `-5%`).
   - Basis controlled by `STATBOT_HARD_STOP_PNL_BASIS` (`notional` default, `equity` optional).
3. **Tier 1.5 Risk-Off + Cointegration Lost (default ON)**
   - Controlled by `STATBOT_ENABLE_RISKOFF_COINT_EARLY_EXIT=1`.
   - Guardrails:
     - confirm count: `STATBOT_RISKOFF_COINT_CONFIRM_COUNT` (default `3`)
     - grace: `STATBOT_RISKOFF_COINT_GRACE_SECONDS` (default `90`)
     - minimum loss: `STATBOT_RISKOFF_COINT_MIN_LOSS_PCT` (default `0.25`)
4. **Tier 2-4 Cointegration tiers (optional, default OFF)**
   - Controlled by `STATBOT_ENABLE_COINT_EXIT_TIERS=1`.
   - Tier 2 includes flicker protection:
     - confirm count: `STATBOT_TIER2_CONFIRMATION_COUNT` (default `3`)
     - min-loss override: `STATBOT_TIER2_MIN_LOSS_PCT` (default `1.5`)
5. **ATM Dynamic Exits**
   - Trailing stop, partial exits, mean reversion, max hold, and stall logic.
6. **Funding Bleed Guard**
7. **No-entry-context fallback**

**Not exits:**
- Z oscillating near entry or improving toward the mean.

**Implementation:**
- Entry Z/time recorded on fill; recent Z-history retained for adaptive checks.
- Partial exits close both legs via market reduce-only orders with lot/min size adjustment.
- Funding fees and unrealized PnL are pulled from OKX position data.
- Warnings are logged at 1h/2h/3h trade duration milestones.

*   **Fail-Safe Stop Loss**: 3% fail-safe remains in sizing/safety checks; in-position hybrid hard-stop defaults to 5% PnL unless overridden by env.
*   **Circuit Breaker**: 5% total account drawdown triggers a "Panic Close" of all positions and system halt.

### Strategy Memory
*   **Hospital**: Pairs with good trade history that fail health/cointegration get a 1-hour cooldown, then are prioritized for re-evaluation. When the active pair fails, hospital pairs that have completed cooldown are selected FIFO (oldest ready first). Good history defaults to: min_trades=1, win_rate > 50%, total_win_usdt > total_loss_usdt.
*   **Graveyard**: Failed pairs are blacklisted using reason-based TTLs:
    - `cointegration_lost_bad_history`: 7 days
    - `health_bad_history`: 7 days
    - `orderbook_dead`: 30 days
    - `compliance_restricted`: no expiry
    - `manual`: 3 days
    - `settle_ccy_filter`: 30 days
    - default: 7 days
*   **Cooldown**: Base **24-hour wait** between pair switches (with emergency override for critically bad health).
*   **Switch Rate Limiter / Defensive Mode**: Max switches per hour (`STATBOT_MAX_SWITCHES_PER_HOUR`, default `5`). If exceeded, switching is blocked for `STATBOT_SWITCH_COOLDOWN_SECONDS` (default `3600s`) and the bot enters defensive mode (skips new entries until cooldown expires).
*   **Re-Entry Cooldown**: 5-minute wait after exit before re-entering same pair to prevent clustering at same Z-level.
*   **Pair Universe Refresh**: If a switch finds no eligible replacement, Execution runs `Strategy/main_strategy.py` to regenerate `Strategy/output/2_cointegrated_pairs.csv` and waits 5 minutes before retrying. The refresh loop continues until a valid pair is available.
*   **Strategy Outputs**: Strategy writes artifacts to `Strategy/output` (`1_price_list.json`, `2_cointegrated_pairs.csv`, `3_backtest_file.csv`, `4_summary_report.csv`).
*   **Strategy Liquidity Filter**: Strategy can bias pair selection toward more liquid legs using `STATBOT_STRATEGY_LIQUIDITY_PCT`. If a scan yields zero pairs, it retries at progressively lower percentiles (0.30, 0.25, 0.20, 0.15, 0.10, 0.00) and restores the base value afterward.
*   **Strategy Fast Path (Optional)**: When `STATBOT_STRATEGY_FAST_PATH=1`, Strategy uses the kline cache plus a correlation prefilter (`STATBOT_STRATEGY_CORR_MIN`, optional `STATBOT_STRATEGY_CORR_LOOKBACK`) to reduce pair count before running full-length cointegration.
*   **Strategy Kline Cache (Optional)**: When `STATBOT_STRATEGY_CACHE_KLINES=1`, Strategy reuses `output/1_price_list.json` and only fetches the latest candles if the gap is small (`STATBOT_STRATEGY_CACHE_MAX_GAP_BARS`, `STATBOT_STRATEGY_CACHE_REFRESH_BARS`).

### Performance Tracking (Per-Cycle Logging)
Each trading cycle logs comprehensive performance metrics:

```
--- Cycle 207 | SKY-USDT-SWAP/SPK-USDT-SWAP | 🟢 PnL: +0.00 USDT (+0.00%) | Equity: 1986.45 USDT | 🔴 Session: -13.55 USDT (-0.68%) ---
```

**Metrics Explained:**
- **PnL**: Unrealized profit/loss from current open positions (real-time mark-to-market)
- **Equity**: Current total account balance (includes all realized gains/losses)
- **Session**: Actual profit/loss since bot started (Equity - Starting Equity)
  - This is your **true performance indicator**
  - Tracks cumulative realized gains/losses across all trades in the session
  - Resets on bot restart

**Why Three Metrics?**
1. **PnL** → Shows if your current trade is winning (goes to 0 when position closes)
2. **Equity** → Shows your total account value right now
3. **Session** → Shows if you're actually making money overall (the real scoreboard)

**Additional Enhancements (2026-01):**
- **Delisted Ticker Detection**: Automatically switches pairs after 5 consecutive orderbook fetch failures
- **Starting Equity Capture**: Recorded at bot startup for accurate session P&L calculation
- **Emergency Override**: Health score < 40 bypasses 24h cooldown for immediate pair switching
- **Enhanced Error Logging**: Detailed diagnostics for orderbook fetch failures (timeout, delisting, rate limits, illiquidity)
- **Cross Margin Mode**: Capital-efficient margin sharing for long+short hedged positions
- **Manual Close Auto-Reset**: If the bot is monitoring (`kill_switch=1`) and no positions/orders exist for 3 cycles, it clears entry tracking and resumes trading
- **Equity Reconciliation Logs**: Estimated entry/exit fees and slippage are logged at trade close to explain equity drift
- **Compliance Restricted Ticker Filter**: sCode=51155 marks a ticker as restricted; pairs containing restricted tickers are skipped on future switches
- **Empty Universe Refresh Loop**: If a switch cannot find a valid replacement, the bot re-runs Strategy and waits 5 minutes between attempts until a pair is available
- **Concise Logging**: Cycle logs move to DEBUG; periodic status updates summarize PnL, equity, and session performance at INFO
- **Per-Run Logs Directory**: Logs live in `OKXStatBot/Logs/v1/run_XX_YYYYMMDD_HHMMSS/log_YYYYMMDD_HHMMSS.log`
- **Entry Signal Snapshots**: One-time startup balance snapshot plus pre-trade snapshots (USDT availBal/availEq) at entry signal
- **PNL Alerts**: `PNL_ALERT` fires on session threshold breaches and trade closes; trade-close alerts log after positions close and equity refresh

**Additional Enhancements (2026-02):**
- **Regime Router V1 Phase 2**: Added optional regime evaluation module with `off|shadow|active` modes and active-mode policy enforcement.
- **Structured Regime Logs**: `REGIME_STATUS`, `REGIME_CHANGE`, `REGIME_POLICY`, and `REGIME_GATE` for attribution and verification.
- **Gate Enforcement Log**: `REGIME_GATE_ENFORCED` when active mode blocks new entries.
- **Policy Application Logs**: Active mode entry sizing traces include `Regime size multiplier applied` when regime policy scales position size.
- **Regime State Persistence**: Router state is persisted in `Execution/state/regime_state.json` (`current_regime`, `candidate_regime`, confidence, pending state, diagnostics).
- **Conservative Router Inputs**: `pnl_fallback` contributes to risk only while in-position; thin-liquidity classification is depth-ratio-led.

### Log Rotation and Retention
StatBot writes per-run logs to `OKXStatBot/Logs/v1` (or `STATBOT_LOG_PATH` if set) with a timestamped filename.
Rotation prevents indefinite growth. Control it via `.env`:
```
STATBOT_LOG_MAX_MB=4
STATBOT_LOG_BACKUPS=2
STATBOT_LOG_PATH=OKXStatBot/Logs/v1/run_01_20260130_161128/log_20260130_161128.log
```
This keeps the current log up to ~4 MB plus 2 rotated backups (total ~12 MB).  
Optional: `STATBOT_LOG_LEVEL=INFO|WARNING|ERROR` to control verbosity.

`OKXStatBot/Logs/v1` maintains:
- `index.json` (all runs + key log metadata)
- `index.csv` (CSV version of the same index)

### Execution State Files
Runtime state is stored under `OKXStatBot/Execution/state`:
- `active_pair.json`
- `status.json`
- `pair_strategy_state.json`
- `strategy_state.json` (strategy router + rolling strategy performance state)
- `regime_state.json` (Regime Router V1 state when enabled)

### Regime Router V1 Phase 2 (Gate + Entry Policy Enforcement)
Regime Router is currently integrated in **Phase 2**. In `active` mode it both blocks disallowed entries and applies regime policy overrides to new-entry execution.

Modes:
- `STATBOT_REGIME_ROUTER_MODE=off`: disabled.
- `STATBOT_REGIME_ROUTER_MODE=shadow`: evaluate + log + persist state; no enforcement.
- `STATBOT_REGIME_ROUTER_MODE=active`: gate enforcement plus active policy overrides for new entries.
  Overrides applied in active mode: `entry_z`, `entry_z_max`, `min_persist_bars`, `min_liquidity_ratio` floor, `size_multiplier`.

Expected verification artifacts:
- Log lines: `REGIME_STATUS`, `REGIME_CHANGE`, `REGIME_POLICY`, `REGIME_GATE`.
- Enforcement log in active mode: `REGIME_GATE_ENFORCED`.
- Execution log when active policy scales size: `Regime size multiplier applied`.
- State file updates: `Execution/state/regime_state.json`.

### Reports (V1 Evidence Pack)
StatBot can generate a per-run report pack under `OKXStatBot/Reports/v1/run_XX_YYYYMMDD_HHMMSS` that captures effectiveness data:
- `summary.json` (run metadata, PnL, drawdown, win rate)
- `summary.txt` (executive summary + files list)
- `equity_curve.csv` (equity/session/PNL timeline)
- `trades.csv` (trade closes with PnL and hold time)
- `strategy_regime_scorecard.csv` (trade outcomes grouped by entry strategy + entry regime)
- `strategy_performance.csv` (strategy-level PnL, win rate, hold, and common exit reason)
- `strategy_switches.csv` (strategy-router switch timeline from runtime logs)
- `strategy_gates.csv` (strategy gate events: coint/mean-shift/policy and future cooldown/filter gates)
- `data_quality_checks.csv` (structured pass/warn/fail checks for data quality)
- `reconciliation_checks.csv` (post-close equity reconciliation records and warning flags)
- `liquidity_checks.csv` (per-entry liquidity snapshot with ratios + high/low classification)
- `entry_slippage.csv` (entry fill slippage vs preview price, bps)
- `alerts.txt` (errors, PNL alerts, critical events)
- `config_snapshot.json` (redacted .env snapshot)
- `report_manifest.json` (machine-readable inventory with schema version and row counts)

`OKXStatBot/Reports/v1` maintains:
- `index.json` (all runs + key metrics)
- `index.csv` (CSV version of the same index)
  - Includes strategy/regime attribution metrics, reconciliation warning counts, and data-quality counters.

Manual/analysis variants:
- Running `report_generator.py --output manual_*` or `analysis_*` routes the pack into `run_XX_.../variants/<name>` for the matching run timestamp.

Enable/disable:
```
STATBOT_REPORT_ENABLE=1
```
Optional uptime trigger:
```
STATBOT_REPORT_UPTIME_HOURS=24
```

Run end tracking:
- Logs emit `RUN_END: reason=... detail=... exit_code=...`
- Reports capture `run_end_reason`, `run_end_detail`, `run_end_time`
- Reasons: `manual_stop`, `error`, `max_uptime`, `max_cycles`, `circuit_breaker`

Max uptime (optional):
```
STATBOT_MAX_UPTIME_HOURS=24
```

### Pre-live Fee Check (Rebates/Discounts)
Before switching to live, use the checklist script to verify your fee tier and recent bill credits:
```
cd OKXStatBot/Execution
python pre_live_checklist.py --mode live --inst-type SWAP
```
The script respects `OKX_FLAG` by default; `--mode live` overrides it.

### Min Equity Filtering (Strategy + Execution)
Strategy can auto-filter expensive pairs before writing `Strategy/output/2_cointegrated_pairs.csv`:
```
STATBOT_STRATEGY_MIN_EQUITY=0
```
Pairs with `min_equity_recommended` above this threshold are removed.

Execution also reads `min_equity_recommended` and skips pairs during pair switching if
your current account equity is below the requirement.

### Strategy Lookback (Klines)
Control how many candles the Strategy fetches per symbol:
```
STATBOT_STRATEGY_KLINE_LIMIT=500
```
OKX limits each request to 100 candles, so the Strategy paginates until it reaches
the requested limit (or runs out of data).

### Settle Currency Filtering (Strategy + Execution)
To avoid mixed-margin pairs (e.g., COIN-margined vs USDT-margined), you can filter by settle currency:
```
STATBOT_STRATEGY_SETTLE_CCY=USDT
STATBOT_EXECUTION_SETTLE_CCY=USDT
```
Defaults are `USDT`. Execution will also skip pairs where both legs do not share the same `settleCcy`.
Set either variable to `ALL` (or leave empty) to disable filtering.

---

## 7. Technical Stack
*   **Language**: Python 3.x
*   **Mathematics**: `statsmodels` (OLS, ADF), `numpy`, `scipy`.
*   **Data Handling**: `pandas` for time-series and CSV management.
*   **API**: `okx` SDK for REST (Account, Trade, Market, Funding).
*   **State Management**: Persistent JSON files for state tracking across restarts.
*   **Diagnostics**: Built-in balance checker (`check_balance.py`) for account configuration verification.

---

## 8. Logic Breakdown (Visual)

```text
[ Cycle Start ]
      |
      v
[ Fetch Account State ] ---> [ Drawdown > 5%? ] ---> YES [ PANIC CLOSE & EXIT ]
      |                           |
      |                           v NO
      |
[ Fetch Market Data ] <--- [ Z-Score / ADF / Metrics ]
      |
      +---- [ Position Open? ]
      |          |
      |          +-- NO [ Seeking Trades ] ---> [ |Z| > 2.0 (3 bars)? ] ---> YES [ PLACE ORDERS ]
      |          |                                   |
      |          +-- YES [ Monitoring ]              +-- NO [ Log "Waiting" ]
      |               |
      |               +-- [ |Z| < 0.5? ] -----> YES [ TAKE PROFIT ]
      |               +-- [ |Z| > 2.5? ] -----> YES [ REGIME BREAK STOP ]
      |               +-- [ P-val > 0.15? ] --> YES [ COINT LOST STOP ]
      |
[ Health Check Due? ] ---> YES [ Score < 40? ] ---> YES [ TRIGGER SWITCH (Code 3) ]
      |                                                 |
[ Cycle End ] <-----------------------------------------+
```
