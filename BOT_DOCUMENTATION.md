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

---

## 4. Signal Generation

### Entry Criteria (🎯)
*   **Threshold**: `|Z-Score| >= 2.0`.
*   **Persistence**: The Z-Score must satisfy the threshold for **3 consecutive bars** (3 minutes) to filter out noise and flash spikes.
*   **Direction**:
    *   **Positive Z (> 2.0)**: Sell the spread (Short Asset A, Long Asset B).
    *   **Negative Z (< -2.0)**: Buy the spread (Long Asset A, Short Asset B).

### Exit Criteria (🟢)
*   **Mean Reversion**: `|Z-Score| <= 0.5`.
*   **Sustained Sign Flip**: Exits only after the Z-score crosses the opposite zone and persists there for ~5 minutes, avoiding false exits on brief oscillations.

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
*   **Margin Mode**: Configured for **cross margin** (recommended for pairs trading). In cross mode, all positions share the account's margin pool, making it capital efficient for simultaneous long+short positions. Isolated mode requires separate margin for each position.

### Safety Exits

#### Advanced Trade Manager (Dynamic Exits)
The bot delegates exit decisions to `AdvancedTradeManager`, which uses entry context and recent Z-history to avoid false exits.

**Exit conditions (priority order):**
1. **Max Hold**: Default 6 hours (warning at 4 hours).
2. **Regime Break**: Sustained sign flip or divergence > 1.5 sigma from entry.
3. **Trailing Stop**: Activates near the mean and trails by 0.5 sigma.
4. **Partial Exit**: Default 50% when `|Z| < 1.0` (skips if below min/lot size).
5. **Mean Reversion**: `|Z| <= EXIT_Z`.
6. **Dynamic Stall**: Adaptive window (30-120 min) and epsilon (0.2-0.5 sigma); warns above 1.0 and exits above 1.5 when improvement is insufficient.
7. **Funding Bleed Guard**: Exits when funding costs materially erode unrealized gains.

**Not exits:**
- Z oscillating near entry or improving toward the mean.

**Implementation:**
- Entry Z/time recorded on fill; recent Z-history retained for adaptive checks.
- Partial exits close both legs via market reduce-only orders with lot/min size adjustment.
- Funding fees and unrealized PnL are pulled from OKX position data.
- Warnings are logged at 1h/2h/3h trade duration milestones.

*   **Fail-Safe Stop Loss**: Hard 3% price move limit per asset.
*   **Circuit Breaker**: 5% total account drawdown triggers a "Panic Close" of all positions and system halt.

### Strategy Memory
*   **Graveyard**: Failed pairs are blacklisted using reason-based TTLs:
    - `cointegration_lost`: 10 days
    - `orderbook_dead`: 30 days
    - `compliance_restricted`: no expiry
    - `manual`: 3 days
    - `health`: 7 days
    - `settle_ccy_filter`: 30 days
    - default: 7 days
*   **Cooldown**: Mandatory **24-hour wait** between pair switches to prevent over-trading and fee erosion.
*   **Re-Entry Cooldown**: 5-minute wait after exit before re-entering same pair to prevent clustering at same Z-level.
*   **Pair Universe Refresh**: If a switch finds no eligible replacement, Execution runs `Strategy/main_strategy.py` to regenerate `2_cointegrated_pairs.csv` and waits 5 minutes before retrying. The refresh loop continues until a valid pair is available.

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
- **Per-Run Logs Directory**: Logs live in `OKXStatBot/Logs` with per-run filenames like `log_MM_MMDDYY_HHMMSS.log`
- **Entry Signal Snapshots**: One-time startup balance snapshot plus pre-trade snapshots (USDT availBal/availEq) at entry signal
- **PNL Alerts**: `PNL_ALERT` fires on session threshold breaches and trade closes; trade-close alerts log after positions close and equity refresh
- **Discord Command Listener**: Optional listener answers `!status`, `!pnl`, `!pair`, `!balance`, `!help` via Clawdbot

### Log Rotation and Retention
StatBot writes per-run logs to `OKXStatBot/Logs` (or `STATBOT_LOG_PATH` if set) with a timestamped filename.
Rotation prevents indefinite growth. Control it via `.env`:
```
STATBOT_LOG_MAX_MB=4
STATBOT_LOG_BACKUPS=2
STATBOT_LOG_PATH=OKXStatBot/Logs/log_01_012926_161128.log
```
This keeps the current log up to ~4 MB plus 2 rotated backups (total ~12 MB).  
Optional: `STATBOT_LOG_LEVEL=INFO|WARNING|ERROR` to control verbosity.

### Molt Monitoring (Optional)
Stream StatBot alerts into Molt/Clawdbot using the monitor:
```
python OKXStatBot/Execution/molt_monitor.py
```

The monitor tails the newest `OKXStatBot/Logs/log_*.log` file and posts executive-level alerts
for critical events and `PNL_ALERT` lines.

Delivery modes:
- `MOLT_DELIVERY_MODE=gateway` (default, uses `clawdbot gateway call send`)
- `MOLT_DELIVERY_MODE=hooks` (uses webhook token)

Environment options:
```
MOLT_GATEWAY_URL=http://127.0.0.1:18789
MOLT_GATEWAY_TOKEN=<gateway token>        # or CLAWDBOT_GATEWAY_TOKEN
MOLT_HOOK_TOKEN=<shared-secret>           # for hooks mode
MOLT_CHANNEL=discord
MOLT_TO=channel:1234567890
MOLT_ALERT_COOLDOWN_SECONDS=60
MOLT_ALERT_CONTEXT_LINES=5
MOLT_ALERT_INCLUDE_CONTEXT=1
MOLT_MONITOR_FROM_START=1
MOLT_DELIVERY_MODE=gateway
```

Notes:
- The monitor auto-detects the latest log file in `OKXStatBot/Logs`.
- If no token is provided for hooks mode, it will read `gateway.auth.token` from
  `~/.clawdbot/clawdbot.json`.

### Discord Command Listener (Optional)
Enable a lightweight listener for bot status queries (via Clawdbot):
```
STATBOT_COMMAND_LISTENER=1
STATBOT_COMMAND_CHANNEL=discord
STATBOT_COMMAND_TARGET=channel:1234567890
STATBOT_COMMAND_PREFIX_REQUIRED=1
STATBOT_COMMAND_PREFIXES=!,/
STATBOT_COMMAND_POLL_SECONDS=5
STATBOT_COMMAND_READ_LIMIT=20
STATBOT_COMMAND_INCLUDE_THREAD=0
```

Supported commands:
- `!status` (executive summary)
- `!pnl`
- `!pair`
- `!balance`
- `!help`

### Min Equity Filtering (Strategy + Execution)
Strategy can auto-filter expensive pairs before writing `2_cointegrated_pairs.csv`:
```
STATBOT_STRATEGY_MIN_EQUITY=170
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
