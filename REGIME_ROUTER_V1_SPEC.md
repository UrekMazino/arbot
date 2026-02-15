# Regime Router V1 Implementation Spec (OKXStatBot)

Date: 2026-02-15  
Scope: Execution-side regime-aware routing for existing stat-arb engine.

## 1. Goal

Reduce losses and churn when the market is trending or stressed, while preserving the current stable execution architecture:

- Keep `main_execution.py` loop and subprocess restart model.
- Keep existing `kill_switch` semantics (`0/1/2/3`).
- Add a regime decision layer that controls how aggressively stat-arb can enter.

## 2. V1 Scope and Non-Goals

### In scope (V1)

- Regime detection with 3 states: `RANGE`, `TREND`, `RISK_OFF`.
- Entry gating and parameter overrides for existing stat-arb flow.
- Regime state persistence and logging.
- Unit/integration tests for regime classification and enforcement.

### Out of scope (V1)

- New order executors for momentum or volatility sleeves.
- Portfolio allocator across independent sleeves.
- Strategy-side pair discovery changes.

V1 implements two practical sleeves only:

- `statarb` (existing entry/exit engine)
- `defensive` (entry suppression + tighter pre-entry requirements)

## 3. Current Integration Points (Codebase)

- `Execution/main_execution.py`
  - Fetches one `zscore_results` per cycle.
  - Calls `manage_new_trades(...)` and `monitor_exit(...)`.
  - Owns session PnL/equity context and pair-switch handling.
- `Execution/func_trade_management.py`
  - `generate_signal(...)` entry logic.
  - `manage_new_trades(...)` order preflight, liquidity gating, entries.
  - `monitor_exit(...)` ongoing position monitoring.
- `Execution/advanced_trade_management.py`
  - Dynamic exit manager already in production.
- `Execution/func_pair_state.py`
  - Existing JSON-backed state conventions under `Execution/state`.
- `Execution/report_generator.py`
  - Parses structured log patterns into report summary fields.

## 4. V1 Architecture

## 4.1 New Files

1. `Execution/regime_router.py`  
Purpose: pure regime logic + decision output.

2. `Execution/func_regime_state.py`  
Purpose: read/write `Execution/state/regime_state.json`.

3. `Execution/tests/test_regime_router.py`  
Purpose: unit tests for classification, precedence, hysteresis.

4. `Execution/tests/test_regime_integration.py`  
Purpose: integration tests for entry gating + threshold overrides.

## 4.2 Updated Files

1. `Execution/main_execution.py`
2. `Execution/func_trade_management.py`
3. `Execution/report_generator.py` (optional in phase 1; required by phase 2)

## 5. Data Contract

## 5.1 `RegimeInput` (new dataclass in `Execution/regime_router.py`)

```python
@dataclass
class RegimeInput:
    ts: float
    ticker_1: str
    ticker_2: str
    latest_zscore: float
    z_metrics: dict
    market_candles: list  # normalized 1m candles for market proxy symbol
    liq_long: dict         # from get_ticker_liquidity_analysis
    liq_short: dict        # from get_ticker_liquidity_analysis
    per_leg_target_usdt: float
    pnl_fallback_active: bool
    session_drawdown_pct: float
```

## 5.2 `RegimeDecision` (new dataclass in `Execution/regime_router.py`)

```python
@dataclass
class RegimeDecision:
    regime: str                  # RANGE | TREND | RISK_OFF
    candidate_regime: str
    confidence: float            # 0..1
    changed: bool
    allow_new_entries: bool
    entry_z: float
    entry_z_max: float
    min_persist_bars: int
    min_liquidity_ratio: float
    size_multiplier: float       # scales initial_capital_usdt
    reason_codes: list[str]
    diagnostics: dict
```

## 6. Regime Model

## 6.1 Metrics (all derivable from current codebase data)

1. Trend score (market proxy, default `BTC-USDT-SWAP`)
- Use EMA spread normalized by ATR:
  - `trend_raw = (ema20 - ema60) / atr14`
  - `trend_strength = abs(trend_raw)`
  - `trend_direction = sign(trend_raw)`

2. Volatility state
- `norm_atr = atr14 / close`
- `vol_percentile` over last 120 bars.
- `vol_expansion = (norm_atr_now / norm_atr_60bars_ago) - 1`
- Shock condition: `vol_percentile >= 0.95 and vol_expansion >= 0.5`.

3. Liquidity state
- Use `get_ticker_liquidity_analysis(...)` for both legs.
- Compute `depth_ratio_min = min(orderbook_depth_notional_leg / per_leg_target_usdt)`.
- Thin condition:
  - any leg `label == "low"`, or
  - `depth_ratio_min < 1.2`.

4. Pair quality hard flags
- `coint_flag == 0`
- `orderbook_dead == True`
- `pnl_fallback_active == True`

## 6.2 Candidate Classification and Precedence

Deterministic priority (highest first):

1. `RISK_OFF` if any:
- `orderbook_dead`
- `coint_flag == 0`
- volatility shock
- thin liquidity
- `pnl_fallback_active`
- `session_drawdown_pct <= -1.5`

2. `TREND` if:
- `trend_strength >= 1.2`
- not `RISK_OFF`

3. `RANGE` otherwise.

## 6.3 Hysteresis and Transition Control

State fields persisted:
- `current_regime`
- `since_ts`
- `pending_candidate`
- `pending_count`

Rules:

1. Immediate switch into `RISK_OFF` if trigger is hard-risk (`orderbook_dead`, `coint_flag=0`, shock).
2. Switch from `RISK_OFF` to other states only if:
- hold time >= `STATBOT_REGIME_MIN_HOLD_SECONDS` (default 1200), and
- same candidate seen for at least `STATBOT_REGIME_CONFIRM_COUNT` cycles (default 2), and
- confidence >= `0.70`.
3. `RANGE <-> TREND` transitions require:
- min hold + confirm count, or
- confidence delta >= `0.25`.

## 7. Policy Mapping (Decision to Existing Engine)

### RANGE
- `allow_new_entries = True`
- `entry_z = ENTRY_Z`
- `entry_z_max = ENTRY_Z_MAX`
- `min_persist_bars = MIN_PERSIST_BARS`
- `min_liquidity_ratio = max(base_env_ratio, 1.5)`
- `size_multiplier = 1.0`

### TREND
- `allow_new_entries = True` (reduced aggressiveness)
- `entry_z = max(2.6, ENTRY_Z * 1.3)`
- `entry_z_max = max(3.6, ENTRY_Z_MAX * 1.2)`
- `min_persist_bars = max(MIN_PERSIST_BARS + 1, 5)`
- `min_liquidity_ratio = max(base_env_ratio, 2.5)`
- `size_multiplier = 0.50`

### RISK_OFF
- `allow_new_entries = False`
- `entry_z = 999.0` (sentinel)
- `entry_z_max = 999.0`
- `min_persist_bars = max(MIN_PERSIST_BARS + 2, 6)`
- `min_liquidity_ratio = max(base_env_ratio, 3.0)`
- `size_multiplier = 0.0`

## 8. File-Level Implementation Plan

## 8.1 `Execution/regime_router.py` (new)

Implement:

```python
class RegimeRouter:
    def __init__(self, state_store=None, config=None):
        ...
    def evaluate(self, inputs: RegimeInput) -> RegimeDecision:
        ...
```

Required internals:
- `_compute_trend_features(candles)`
- `_compute_vol_features(candles)`
- `_compute_liquidity_features(liq_long, liq_short, per_leg_target_usdt)`
- `_classify_candidate(features, inputs)`
- `_apply_hysteresis(candidate, confidence, reasons, ts)`
- `_build_policy(regime, base_liq_ratio)`

## 8.2 `Execution/func_regime_state.py` (new)

Functions:
- `load_regime_state() -> dict`
- `save_regime_state(state: dict) -> None`
- `update_regime_state(decision: RegimeDecision, inputs: RegimeInput) -> None`

State file: `Execution/state/regime_state.json`.

## 8.3 `Execution/main_execution.py`

1. Initialize router once before main loop:
- `regime_router = RegimeRouter(...)`

2. Each cycle, after `zscore_results` + equity/session fields are available:
- Collect market candles via `get_price_klines(market_symbol, bar="1m", limit=180)`.
- Collect per-leg liquidity analysis via `get_ticker_liquidity_analysis(...)`.
- Build `RegimeInput`.
- Call `regime_decision = regime_router.evaluate(regime_input)`.

3. Pass decision through:
- `manage_new_trades(..., regime_decision=regime_decision)`
- `monitor_exit(..., regime_decision=regime_decision)`

4. Add periodic status log line:
- `REGIME_STATUS: regime=... conf=... candidate=... reasons=...`

## 8.4 `Execution/func_trade_management.py`

1. Update signatures:

```python
def manage_new_trades(kill_switch, health_check_due=False, zscore_results=None, regime_decision=None):
def monitor_exit(kill_switch, health_check_due=False, zscore_results=None, regime_decision=None):
def generate_signal(z_history, cointegration_ok, in_position,
                    entry_z=None, exit_z=None, entry_z_max=None, min_persist_bars=None):
```

2. Entry gating:
- If `regime_decision.allow_new_entries` is `False`, return hold (`kill_switch` unchanged).

3. Entry threshold overrides:
- Use `entry_z`, `entry_z_max`, `min_persist_bars` from decision.
- Default to existing constants if decision missing.

4. Liquidity ratio override:
- When reading `STATBOT_MIN_LIQUIDITY_RATIO`, enforce:
  - `min_liquidity_ratio = max(env_ratio, regime_decision.min_liquidity_ratio)`.

5. Position size override:
- Before order placement:
  - `initial_capital_usdt *= regime_decision.size_multiplier` (clip to [0, base]).

6. Monitor path:
- For V1, no forced early exit from router.
- Log current regime with hold decisions for attribution.

## 8.5 `Execution/report_generator.py` (phase 2 required)

Add parsers for:

- `REGIME_CHANGE: from=... to=... conf=... reasons=...`
- `REGIME_GATE: regime=... allow_new_entries=0 reason=...`

Add summary fields:

- `regime_switches`
- `regime_gate_blocks`
- `regime_last`
- `regime_time_range_pct`
- `regime_time_trend_pct`
- `regime_time_risk_off_pct`

## 9. Environment Variables

Add (default values shown):

```env
STATBOT_REGIME_ROUTER_MODE=off            # off | shadow | active
STATBOT_REGIME_MARKET_SYMBOL=BTC-USDT-SWAP
STATBOT_REGIME_EVAL_SECONDS=60
STATBOT_REGIME_MIN_HOLD_SECONDS=1200
STATBOT_REGIME_CONFIRM_COUNT=2
STATBOT_REGIME_TREND_THRESHOLD=1.2
STATBOT_REGIME_VOL_SHOCK_PCT=0.95
STATBOT_REGIME_VOL_EXPANSION=0.5
STATBOT_REGIME_THIN_DEPTH_RATIO=1.2
STATBOT_REGIME_RISKOFF_DRAWDOWN_PCT=1.5
```

Mode behavior:

- `off`: no evaluation, no behavior change.
- `shadow`: evaluate/log/save state, no behavior enforcement.
- `active`: evaluate + enforce policy in `manage_new_trades`.

## 10. Logging Contract

Use these exact structured lines for stable parsing:

```text
REGIME_STATUS: regime=RANGE candidate=RANGE conf=0.82 trend=0.47 vol_pct=0.44 depth=2.80 coint=1 fallback=0
REGIME_CHANGE: from=RANGE to=RISK_OFF conf=0.91 hold=1840s reasons=thin_liquidity|vol_shock
REGIME_GATE: regime=RISK_OFF allow_new_entries=0 reason=thin_liquidity
REGIME_POLICY: regime=TREND entry_z=2.60 entry_z_max=3.60 min_persist=5 min_liq=2.50 size_mult=0.50
```

## 11. Tests

## 11.1 `Execution/tests/test_regime_router.py`

Cases:

1. Thin liquidity forces `RISK_OFF` even when trend is strong.
2. Vol shock forces `RISK_OFF`.
3. Strong trend + healthy liquidity -> `TREND`.
4. Neutral trend + healthy liquidity -> `RANGE`.
5. Hysteresis blocks rapid `RANGE <-> TREND` oscillation.
6. Immediate hard-risk transition to `RISK_OFF`.

## 11.2 `Execution/tests/test_regime_integration.py`

Cases:

1. `regime=RISK_OFF` blocks entry in `manage_new_trades`.
2. `regime=TREND` increases effective entry threshold.
3. Liquidity floor from regime overrides lower env ratio.
4. `shadow` mode does not alter behavior.
5. Missing/invalid decision falls back to legacy defaults.

## 12. Rollout Plan

1. Phase 0 (1-2 days): `STATBOT_REGIME_ROUTER_MODE=shadow`  
Validate logs/state only. No behavior impact.

2. Phase 1 (2-4 days): `active` with gate-only  
Enforce only `allow_new_entries` for `RISK_OFF`.

3. Phase 2 (3-7 days): full active policy  
Enable threshold/size/liquidity overrides.

4. Phase 3: report integration  
Track regime attribution in `Reports/v1` summary.

## 13. Acceptance Criteria

Relative to prior baseline runs on comparable market hours:

1. `cointegration_lost` pair switches per hour reduced by >= 30%.
2. `pnl_fallback_pct_runtime` reduced by >= 20%.
3. `liquidity_low_pct` reduced by >= 20%.
4. No increase in `max_drawdown_pct` > 20% versus baseline median.
5. No regression in kill-switch behavior (`0/1/2/3` semantics unchanged).

## 14. Notes for V2

After V1 stabilizes, add real `momentum` sleeve as separate executor module and route notional by soft weights (`statarb/momentum/defensive`) instead of only stat-arb parameter modulation.

