# Kill-Switch State Machine Documentation

## Overview
The `kill_switch` variable is a control state that manages the bot's execution flow. All state transitions are **deterministic** and fully logged.

## States

| State | Value | Meaning | Action |
|-------|-------|---------|--------|
| **ACTIVE** | 0 | Normal operation | Seek trades, monitor positions |
| **CLOSING** | 1 | Orders placed | Wait for positions to close |
| **STOP** | 2 | Final exit | Close all positions and exit |

---

## State Transitions (Deterministic)

### From ACTIVE (0):

#### Transition: 0 → 0
**Condition:** No signal detected OR cointegration failed
**Action:** Continue normal cycle
**Return:** kill_switch = 0

```
manage_new_trades(0) → checks signal → cointegration_failed → return 0
```

#### Transition: 0 → 1
**Condition:** Hot signal + Valid cointegration + Extreme Z-score
**Action:** Place entry orders for long and short
**Return:** kill_switch = 1
**Logged:** "Both orders placed. Long: placed, Short: placed"

```
manage_new_trades(0) → hot_trigger=True → coint_flag=1 → place_orders → return 1
```

### From CLOSING (1):

#### Transition: 1 → 2 (Hard Stop - Regime Break)
**Condition:** Z-score exceeds ±2.5 during monitoring
**Trigger:** Spread too extreme = cointegration likely broken
**Action:** Immediately cancel all orders, close positions
**Return:** kill_switch = 2
**Logged:** "⚠️ REGIME BREAK DETECTED: Z-score=2.8 exceeded hard stop 2.5"

```
manage_new_trades(1) → monitor_zscore → abs(zscore) > 2.5 → cancel_all → return 2
```

#### Transition: 1 → 2 (Signal Flip)
**Condition:** Z-score sign changes during trade
**Trigger:** Z was positive at entry, now negative (or vice versa)
**Action:** Signal no longer valid, close immediately
**Return:** kill_switch = 2
**Logged:** "⚠️ SIGNAL FLIPPED: Expected True, got False"

```
manage_new_trades(1) → monitor_zscore → signal_change → cancel_all → return 2
```

#### Transition: 1 → 2 (Cointegration Lost)
**Condition:** p_value ≥ 0.05 during monitoring
**Trigger:** Pair no longer statistically related
**Action:** Close positions to avoid further losses
**Return:** kill_switch = 2
**Logged:** "Cointegration lost during trade (p_value >= 0.05): Closing position"

```
manage_new_trades(1) → check_cointegration → coint_flag != 1 → cancel_all → return 2
```

#### Transition: 1 → 2 (Mean Reversion Complete)
**Condition:** Z-score reverts to ±0.05
**Trigger:** Spread returns to mean = trade complete
**Action:** Profit taken, close positions
**Return:** kill_switch = 2
**Logged:** "✅ Mean reversion complete (Z=0.04 < 0.05): Taking profit"

```
manage_new_trades(1) → monitor_zscore → zscore < 0.05 → return 2
```

---

## Main Loop Integration (main_execution.py)

```python
while True:
    # Check circuit breaker
    if P&L_loss > max_drawdown:
        close_all_positions()
        break  # Exit program
    
    # Check position status
    if is_manage_new_trades:
        kill_switch = manage_new_trades(kill_switch) or kill_switch
        #                               ↓
        #                    Returns: 0, 1, or 2
    
    # Process state
    if kill_switch == 2:
        status = "Closing existing trades..."
        kill_switch = close_all_positions(kill_switch)  # Returns 2
        break  # Exit program
    
    cycles_run += 1
```

---

## Event Timeline Example

```
[Cycle 1] kill_switch = 0 (ACTIVE)
  → Check cointegration: ✅ p_value = 0.03 (valid)
  → Check Z-score: 1.2 (meets threshold)
  → Place orders → kill_switch = 1

[Cycle 2] kill_switch = 1 (CLOSING)
  → Monitor: Z-score = 0.8 (still high, but valid)
  → Monitor: Orders still active
  → Continue monitoring

[Cycle 3] kill_switch = 1 (CLOSING)
  → Monitor: Z-score = 0.04 (mean reversion!)
  → ✅ Take profit condition met
  → kill_switch = 2 (final stop)

[Cycle 4] kill_switch = 2 (STOP)
  → main_execution calls close_all_positions()
  → All orders canceled, positions closed
  → Program exits
```

---

## Exit Scenarios

| Scenario | Trigger | kill_switch Flow | Log Entry |
|----------|---------|-----------------|-----------|
| **Normal Trade** | Z reverts to mean | 0 → 1 → 2 | "Mean reversion complete" |
| **Regime Break** | Z spikes to ±2.6 | 0 → 1 → 2 | "REGIME BREAK DETECTED" |
| **Signal Invalid** | Z sign flips | 0 → 1 → 2 | "SIGNAL FLIPPED" |
| **Lost Cointegration** | p_value ≥ 0.05 | 0 → 1 → 2 | "Cointegration lost" |
| **Circuit Breaker** | Loss > 5% | [any] → exit | "CIRCUIT BREAKER TRIGGERED" |
| **No Signal** | Z < threshold | 0 → 0 (loop) | No exit |

---

## Key Properties

✅ **Deterministic:** Every state transition has clear, documented conditions
✅ **Logged:** Every transition is timestamped and logged
✅ **Safe:** Multiple exit conditions ensure positions don't hang
✅ **Testable:** State machine can be verified independently

---

## Verification Checklist

- [x] All states (0, 1, 2) documented
- [x] All transitions have explicit conditions
- [x] All transitions are logged
- [x] Circuit breaker implemented (5% max loss)
- [x] Hard stop implemented (Z > ±2.5)
- [x] Signal flip detection implemented
- [x] Cointegration check implemented
- [x] Mean reversion exit implemented
