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
*   **Signal Flip**: If the Z-score sign changes unexpectedly (e.g., from +2.0 to -0.1), the trade is closed to prevent exposure to a broken relationship.

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
*   **Margin Mode**: Configured for **cross margin** (recommended for pairs trading). In cross mode, all positions share the account's margin pool, making it capital efficient for simultaneous long+short positions. Isolated mode requires separate margin for each position.

### Safety Exits

#### Regime Break Detection (Context-Aware)
The bot uses **intelligent regime break detection** that tracks entry context to avoid false exits:

**TRUE Regime Breaks (triggers exit):**
1. **Z-Score Diverging**: Current Z worsens by >1.5σ from entry
   - Example: Entered at Z=-4.36, now at Z=-6.0 (+1.64σ worse)
   - Indicates relationship deteriorating, not oscillating
2. **Sign Flip**: Spread reverses direction
   - Example: Entered oversold (Z=-4.36), now overbought (Z=+2.5)
   - Indicates mean-reversion failed and spread broke
3. **Persistent Extreme**: Z > 6.0 after 30+ minutes in trade
   - Example: Z=6.2 after 35 minutes
   - Indicates pair not mean-reverting as expected
4. **Z-Stall Detector (dynamic)**: Adaptive stall detection for flat/stuck regimes
   - Window adapts to entry extremity (30-120 min based on |entry Z|)
   - Epsilon adapts to recent Z volatility (0.2-0.5 sigma)
   - No stall evaluation before 30 min; stricter after 2h
   - Triggers when improvement < epsilon after the window and |Z| > 1.5; warns if |Z| > 1.0
   - Volatility acceleration (recent > 1.5x prior) raises warnings
5. **Time-Based Exit**: Position held longer than max(60 min, 2x stall window) without reversion
   - Example: 125 minutes in trade, Z still far from mean
   - Realizes profit when structural repricing prevents full mean reversion
6. **Partial Mean Reversion**: Z improved >1.5σ and now < 2.0
   - Example: Entered at Z=4.2, now at Z=1.8 (-2.4σ improvement)
   - Takes profit on significant improvement even without full reversion to 0.5
7. **Funding Bleed Guard**: Funding fees eroding unrealized profits
   - Triggers when:
     - Unrealized PnL > $5 (profitable position)
     - Funding cost > $2 (significant bleed)
     - Funding cost > 30% of unrealized PnL (high erosion ratio)
   - Example: +$20 unrealized profit, -$8 funding cost (40% erosion)
   - Prevents scenario where position PnL is positive but session PnL is negative

**NOT Regime Breaks (continues holding):**
- ❌ Z oscillating at entry level (entered -4.36, revisits -4.36) → Normal volatility
- ❌ Z improving toward mean (entered -4.36, now -1.05) → Desired behavior

**Implementation:**
- Entry Z-score and timestamp recorded when position opens
- Z-history stored with timestamps (up to ~4 hours) for adaptive stall windows and volatility trend checks
- Each cycle compares current Z against entry context
- Funding fees and unrealized PnL extracted from OKX position data
- Stall warnings logged at 1h/2h/3h milestones when trades remain open
- Prevents premature exits on expected volatility oscillations
- **Bug Fixes (2026-01)**: 
  - Old logic exited when Z returned to entry level, missing profitable mean reversions
  - Added exit mechanisms for persistent divergence regimes (structural repricing, narrative shifts)
  - Added funding bleed detection to prevent fee erosion of profits

*   **Fail-Safe Stop Loss**: Hard 3% price move limit per asset.
*   **Circuit Breaker**: 5% total account drawdown triggers a "Panic Close" of all positions and system halt.

### Strategy Memory
*   **Graveyard**: Failed pairs are blacklisted for **7 days**.
*   **Cooldown**: Mandatory **24-hour wait** between pair switches to prevent over-trading and fee erosion.
*   **Re-Entry Cooldown**: 5-minute wait after exit before re-entering same pair to prevent clustering at same Z-level.

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

### Log Rotation and Retention
StatBot uses a rotating log file to prevent indefinite growth. Control it via `.env`:
```
STATBOT_LOG_MAX_MB=4
STATBOT_LOG_BACKUPS=2
```
This keeps the current log up to ~4 MB plus 2 rotated backups (total ~12 MB).  
Optional: `STATBOT_LOG_LEVEL=INFO|WARNING|ERROR` to control verbosity.

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
