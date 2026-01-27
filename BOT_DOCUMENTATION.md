# OKX StatBot - Statistical Arbitrage Documentation

## 1. Overview
StatBot is an autonomous trading system designed for the OKX exchange. It implements a **Statistical Arbitrage** strategy, specifically **Pairs Trading**, based on the cointegration of two assets. The bot identifies when the "spread" between two statistically related assets diverges from its historical mean and bets on its eventual reversion.

---

## 2. Core Strategy & Mathematics

### Cointegration (The ADF Test)
The bot uses the **Augmented Dickey-Fuller (ADF)** test to verify if a pair of assets is cointegrated. Cointegration means that although the individual prices might move randomly, a specific linear combination of them stays within a stable range.
*   **P-Value Threshold**: 0.15 (A p-value < 0.15 indicates a statistically significant relationship).

### Hedge Ratio & Spread
To calculate the spread, the bot performs an **Ordinary Least Squares (OLS)** regression on the log-prices of the two assets. Using log-prices ensures the hedge ratio is proportional and accounts for percentage moves rather than absolute price moves.
*   **Formula**: `Spread = ln(Price_A) - (Hedge_Ratio * ln(Price_B))`
*   The **Hedge Ratio** determines how many units of Asset B are needed to offset the price movements of Asset A.

### Execution Price Buffers
To ensure immediate execution and account for exchange fees, the bot applies a buffer to the entry prices:
*   **Taker Fee/Slippage Buffer**: 0.07% (0.0007) is added/subtracted from the mid-price to ensure orders are filled quickly while maintaining safety margins.

### Z-Score
The Z-Score represents how many standard deviations the current spread is away from its moving average.
*   **Window**: 21 periods (1-minute bars).
*   **Formula**: `Z = (Current_Spread - Mean_Spread) / StdDev_Spread`

---

## 3. The Trade Cycle

### Subprocess Manager
StatBot runs inside a manager process (`main_execution.py`). 
*   If the bot needs to switch pairs, it saves the new configuration and exits with **Code 3**.
*   The Manager detects Code 3 and automatically restarts the bot, ensuring a fresh initialization of all API sessions and parameters without manual intervention.

### The "Cycle" Heartbeat
Each cycle (approx. 5-7 seconds) performs:
1.  **Consolidated API Fetch**: Retrieves all account positions and orders in a single call to minimize rate limits.
2.  **Market Data Update**: Fetches 1m Klines and live Orderbook mid-prices.
3.  **Circuit Breaker Check**: Evaluates cumulative P&L against the total capital.
4.  **Decision Engine**:
    *   **Seeking Trades**: If no position is open, checks for entry signals.
    *   **Monitoring**: If a position is open, checks for exit or stop-loss conditions.

---

## 4. Signal Generation

### Entry Criteria (🎯)
*   **Threshold**: |Z-Score| >= 2.0.
*   **Persistence**: The Z-Score must remain above the threshold for **3 consecutive bars** (3 minutes) to filter out flash spikes.
*   **Direction**:
    *   **Positive Z (> 2.0)**: Sell the spread (Short Asset A, Long Asset B).
    *   **Negative Z (< -2.0)**: Buy the spread (Long Asset A, Short Asset B).

### Exit Criteria (🟢)
*   **Mean Reversion**: |Z-Score| <= 0.5.
*   The trade is closed when the spread returns significantly toward its mean, capturing the profit from the convergence.

---

## 5. Health Scoring System
Every hour (or upon a potential break), the bot performs a **Periodic Health Check**. It calculates a score from 0 to 100 based on statistical metrics.

| Metric | Threshold | Deduction | Importance |
|--------|-----------|-----------|------------|
| **P-Value** | >= 0.15 | -50 pts | Critical |
| **Spread Trend** | > 0.002 | -30 pts | Critical |
| **Z-Score** | > 6.0 | -25 pts | Critical |
| **Consecutive Losses**| >= 3 | -20 pts | Performance |
| **Correlation** | < 0.60 | -15 pts | Warning |
| **ADF Ratio** | < 0.8 | -15 pts | Warning |
| **Zero Crossings** | < 15 | -15 pts | Warning |

*   **Action**: If the score drops below **40**, the bot triggers a pair switch.

---

## 6. Risk Management

### Circuit Breaker
*   **Max Drawdown**: 5% of total capital. If hit, the bot closes all positions and stops trading.

### Position Sizing (2% Rule)
*   The bot risks exactly **2% of total capital** per trade.
*   Position size is calculated based on the distance to the fail-safe stop loss.

### Safety Exits
*   **Regime Break (Hard Stop)**: If |Z| exceeds **2.5** after a trade is placed, the bot closes immediately (indicates the statistical relationship has broken).
*   **Fail-Safe Stop Loss**: 3% price move against the position.
*   **Signal Flip**: If the Z-score sign changes unexpectedly, the trade is closed.

### Strategy Memory
*   **Graveyard**: Pairs that fail health checks are moved to a graveyard and skipped for **7 days**.
*   **Cooldown**: Mandatory **24-hour wait** between pair switches to prevent over-trading and fee erosion.

---

## 7. Files & Configuration

*   **`config_execution_api.py`**: Global settings, thresholds, and API credentials.
*   **`active_pair.json`**: Stores the currently traded pair for persistence across restarts.
*   **`2_cointegrated_pairs.csv`**: The master list of 1,800+ prospective pairs for switching.
*   **`pair_strategy_state.json`**: Persistent memory of Graveyard, Cooldowns, and Losses.
*   **`logfile_okx.log`**: Detailed audit trail of every decision, computation, and API call.
*   **`status.json`**: High-level status for external monitoring.

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
