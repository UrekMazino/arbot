# Regime Router Phase 3 Spec (Strategy Routing)

Date: 2026-02-15  
Status: Draft (post-Phase 2 baseline)

## 1. Objective

Phase 3 upgrades the current regime-aware stat-arb bot from:

- Phase 2: gate + entry policy overrides on one strategy

to:

- Multi-strategy routing by market regime, with safe switching rules.

Primary target:

- Reduce bad entries during non-mean-reverting conditions without increasing pair-switch churn.

## 2. Current Baseline (Already in Code)

Current behavior confirmed in:

- `Execution/main_execution.py`
- `Execution/regime_router.py`
- `Execution/func_trade_management.py`

What exists now:

1. Regime evaluation (`RANGE`, `TREND`, `RISK_OFF`).
2. Active-mode entry gate (`REGIME_GATE_ENFORCED`).
3. Policy overrides for stat-arb entry thresholds, persistence, liquidity floor, and size multiplier.
4. Hybrid exit stack + ATM is active in runtime:
   - Tier 5 adaptive profit target (`STATBOT_PROFIT_TARGET_*`).
   - Tier 1 hard stop (`STATBOT_HARD_STOP_PNL_PCT`).
   - Tier 2-4 cointegration tiers are optional and disabled by default (`STATBOT_ENABLE_COINT_EXIT_TIERS=0`).
   - ATM exits remain active (trailing, partials, mean reversion, hold limits).
   - Funding bleed and no-entry-context fallbacks remain active.
5. Post-close realized equity is used as source of truth for:
   - trade WIN/LOSS classification,
   - pair history PnL,
   - trade-close PnL alert output.
6. Switch rate limiter is active:
   - max switches/hour with cooldown (`STATBOT_MAX_SWITCHES_PER_HOUR`, `STATBOT_SWITCH_COOLDOWN_SECONDS`),
   - defensive mode blocks new entries while cooldown is active.

## 2.1 Current Exit Criteria (Authoritative Runtime)

In-position exit priority order:

1. Tier 5 adaptive profit target.
2. Tier 1 hard stop.
3. Tier 2-4 cointegration exits (optional; off by default).
4. ATM dynamic exit logic.
5. Funding bleed guard.
6. No-entry-context fallback.

Notes:

- Hard-stop and enabled cointegration tiers can set post-close forced switch reasons.
- Strategy/regime routing should not bypass this exit stack.

## 2.2 Source-of-Truth Defaults (Current vs Planned)

This section is the canonical defaults reference for this spec.

### A. Current runtime defaults (already in code / `.env.example`)

| Area | Parameter | Default | Source |
|---|---|---:|---|
| Hybrid exit | `STATBOT_PROFIT_TARGET_PCT` | `0.5` | `Execution/.env.example` |
| Hybrid exit | `STATBOT_PROFIT_TARGET_MIN_USDT` | `5.0` | `Execution/.env.example` |
| Hybrid exit | `STATBOT_PROFIT_TARGET_MAX_USDT` | `50.0` | `Execution/.env.example` |
| Hybrid exit | `STATBOT_HARD_STOP_PNL_PCT` | `5.0` | `Execution/.env.example` |
| Hybrid exit | `STATBOT_ENABLE_COINT_EXIT_TIERS` | `0` | `Execution/.env.example` |
| Hybrid exit | `STATBOT_TIER2_CONFIRMATION_COUNT` | `3` | `Execution/.env.example` |
| Hybrid exit | `STATBOT_TIER2_MIN_LOSS_PCT` | `1.5` | `Execution/.env.example` |
| Switch limiter | `STATBOT_MAX_SWITCHES_PER_HOUR` | `5` | `Execution/.env.example` |
| Switch limiter | `STATBOT_SWITCH_COOLDOWN_SECONDS` | `3600` | `Execution/.env.example` |
| Regime router | `STATBOT_REGIME_ROUTER_MODE` | `off` | `Execution/.env.example` |

### B. Planned Phase 3 strategy-router defaults (spec target)

| Strategy | Entry Z | Entry Z Max | Min Persist | Size Mult | Max Hold |
|---|---:|---:|---:|---:|---|
| `STATARB_MR` | `2.0` | `3.0` | `3` | `1.0` (RANGE baseline) | `6h` |
| `TREND_SPREAD` | `2.8` | `5.0` | `4` | `0.35` | `2h` |
| `DEFENSIVE` | N/A | N/A | N/A | `0.0` | N/A |

Naming note:
- `TREND_SPREAD` in this spec means *persistent-divergence mean-reversion* (not pure momentum continuation).

## 3. Phase 3 Scope

## 3.1 In Scope

1. Add strategy routing layer with 3 route targets:
- `STATARB_MR` (mean reversion, existing behavior profile)
- `TREND_SPREAD` (persistent-divergence mean-reversion profile on same pair infrastructure)
- `DEFENSIVE` (no new entries; monitor/exit only)

2. Route strategy by regime with hysteresis and safe transitions.

3. Persist strategy state and add strategy-level logs and report fields.

4. Keep current subprocess restart model and current kill-switch semantics.

## 3.2 Out of Scope

1. Single-leg directional engine (BTC-only, etc.).
2. New broker execution adapters.
3. Strategy-side pair discovery redesign.
4. Forced close on every strategy change.
5. Enabling directional filter in production routing (experimental; Phase 4 validation item).

## 4. Design Principles

1. No forced strategy switch while in position.
2. Regime change does not imply pair switch.
3. Strategy switch only affects new entries.
4. Existing hybrid risk exits remain authoritative.
5. Rollout in shadow first, then active.

## 5. Strategy Routing Model

## 5.1 Route Mapping

Default mapping:

- `RANGE` -> `STATARB_MR`
- `TREND` -> `TREND_SPREAD`
- `RISK_OFF` -> `DEFENSIVE`

## 5.2 Strategy Decision Contract

Add new dataclass in a new router module:

```python
@dataclass
class StrategyDecision:
    mode: str                     # off|shadow|active
    active_strategy: str          # currently effective strategy
    desired_strategy: str         # regime-mapped target strategy
    pending_strategy: str         # queued while in-position
    changed: bool                 # active strategy changed this cycle
    allow_new_entries: bool
    size_multiplier: float
    entry_z: float
    entry_z_max: float
    min_persist_bars: int
    min_liquidity_ratio: float
    reason_codes: list[str]
    diagnostics: dict
```

## 5.3 Strategy Profiles

Profiles are per-entry policy sets.

### `STATARB_MR` (Mean-Reversion, Standard)

- Current Phase 2 behavior.
- Entry on divergence with standard persistence (3 bars).
- Uses regime-policy resolved thresholds from Phase 2.
- Full size allocation (1.0x multiplier in RANGE).
- Standard hold limits (6 hours max).

Entry logic:
- `z >= +2.0` after 3 bars persistence -> `SELL_SPREAD` (expect reversion to 0)
- `z <= -2.0` after 3 bars persistence -> `BUY_SPREAD` (expect reversion to 0)

### `TREND_SPREAD` (Persistent Divergence Mean-Reversion)

Core principle: still mean-reversion, but requires stronger confirmation before entry.

Entry contract:
1. Cointegration gate is mandatory (`coint_flag == 1`).
   - If cointegration is weak/lost: keep `active_strategy` unchanged and set `allow_new_entries=False`.
   - Emit gate log (`COINT_GATE` / `STRATEGY_GATE_ENFORCED`) and do not emit `STRATEGY_CHANGE`.
2. Higher divergence threshold:
   - Require `z >= +2.8` or `z <= -2.8` (vs 2.0 in `STATARB_MR`).
3. Longer persistence requirement:
   - Require at least 4 bars sustained divergence (vs 3 in `STATARB_MR`).
4. Entry side mapping remains mean-reversion:
   - `z >= +2.8` with persistence -> `SELL_SPREAD` (expect reversion down to 0)
   - `z <= -2.8` with persistence -> `BUY_SPREAD` (expect reversion up to 0)
   - Not continuation: the thesis is reversion, not momentum follow-through.
5. Optional directional filter (future toggle):
   - Controlled by `STATBOT_STRATEGY_TREND_USE_DIRECTIONAL_FILTER`.
   - Can suppress entries strongly misaligned with broader market context.
   - Does not invert the side mapping above.
   - Default is OFF; treat as experimental until pair-specific validation is complete (Phase 4 target).
6. Mean-shift gate (Phase 3 safety filter, default ON):
   - Purpose: avoid TREND entries when divergence mostly reflects equilibrium drift rather than tradable dislocation.
   - Compute shift score on spread series:
     - `mu_short = mean(spread[-short_window:])`
     - `mu_long = mean(spread[-long_window:])`
     - `sigma_short = std(spread[-short_window:])`
     - `shift_z = abs(mu_short - mu_long) / max(sigma_short, eps)`
   - Default windows align with current runtime behavior:
     - `short_window=21` (current z-score window baseline)
     - `long_window=200` (current fetched candle history baseline)
   - Gate behavior:
     - if `shift_z > threshold`, block new TREND entries for the cycle (`allow_new_entries=False` for that decision path only)
     - keep `active_strategy` unchanged
     - emit gate reason (`mean_shift_gate`)
   - Scope note:
     - This is a gate-only Phase 3 control.
     - It does not change z-score centering target or introduce regime-specific mean persistence state.

Default risk controls:
- Smaller size multiplier (0.35x vs 1.0x in `STATARB_MR`).
- Tighter max hold (2 hours vs 6 hours in `STATARB_MR`).
- Tighter exit profile (implemented via profile overrides in trade management).

### `DEFENSIVE` (No New Entries)

- `allow_new_entries=False`
- Existing positions are managed by monitor/exit stack only.
- Used for `RISK_OFF` regime or when gating conditions block entry.

## 6. State Machine (Strategy Switch)

Inputs each cycle:

- regime decision
- in-position status
- current active strategy
- pair-health gate status (`coint_flag`)

Rules:

1. Compute `desired_strategy` from regime only.
2. Apply pair-health gate:
   - if `coint_flag != 1`: keep `active_strategy` unchanged and set `allow_new_entries=False`.
   - log as `COINT_GATE` (or `STRATEGY_GATE_ENFORCED` with reason `coint_gate`).
   - do not emit `STRATEGY_CHANGE` for this condition.
3. If no cointegration gate and `desired_strategy == active_strategy`: clear pending.
4. If no cointegration gate and different while flat: switch immediately.
5. If no cointegration gate and different while in-position: keep active, set `pending_strategy`.
6. On transition to flat: apply pending if still valid.
7. If `RISK_OFF`: route to `DEFENSIVE` and block new entries, independent of pending/active.

This removes unnecessary pair switching when only market regime changes.

## 7. File-by-File Implementation Plan

## 7.1 New Files

1. `Execution/strategy_router.py`
- Define `StrategyDecision`.
- Implement `StrategyRouter.evaluate(...)`.
- Implement hysteresis/min-hold for strategy changes.

2. `Execution/func_strategy_state.py`
- Persist strategy routing state to `Execution/state/strategy_state.json`.
- `load_strategy_state()`, `save_strategy_state()`.
- Strategy ownership is global/cross-pair and remains in this file only.

3. `Execution/tests/test_strategy_router.py`
- Unit tests for route mapping, hysteresis, pending behavior.

4. `Execution/tests/test_strategy_integration.py`
- Integration tests for active vs shadow behavior through entry flow.

## 7.2 Update `Execution/main_execution.py`

Additions:

1. Initialize strategy router once near regime router initialization.
2. After regime evaluation, evaluate strategy decision:
- pass `in_position_now`, `last_regime_decision`, and current strategy state.
3. Pass `strategy_decision` into:
- `manage_new_trades(...)`
- `monitor_exit(...)` (for strategy-specific hold/exit config if needed)
4. Add structured logs:
- `STRATEGY_STATUS`
- `STRATEGY_CHANGE`
- `STRATEGY_PENDING`
- `STRATEGY_GATE_ENFORCED`
- `COINT_GATE`

Do not:

- Trigger pair switch due only to strategy change.

## 7.3 Update `Execution/func_trade_management.py`

Refactor entry logic:

1. Add strategy-aware signal dispatch:
- `_generate_signal_statarb(...)` (current behavior)
- `_generate_signal_trend(...)` (persistent-divergence mean-reversion behavior)

2. Update signature:

```python
def manage_new_trades(..., regime_mode="off", regime_decision=None, strategy_decision=None):
```

3. Apply policy precedence for new entries:

`strategy_decision` overrides `regime_decision` where both provide entry policy.

4. Keep existing liquidity and risk checks; apply strategy size multiplier before preflight.

5. Add logs:
- `STRATEGY_ENTRY_SIGNAL`
- `STRATEGY_ENTRY_REJECT`
- `STRATEGY_SIZE_APPLIED`
- `COINT_GATE` when `coint_flag != 1` blocks entry under any strategy.

## 7.4 Update `Execution/advanced_trade_management.py`

Add profile-level config support:

1. Add method to load profile overrides at entry open.
2. Define two profile presets:
- `mr_profile`
- `trend_profile` (shorter hold, tighter trailing behavior)

This lets trend trades exit under different tolerance without replacing exit engine.

## 7.5 Update `Execution/func_pair_state.py`

State ownership boundary:

- `Execution/state/strategy_state.json` is the only source of truth for strategy routing and strategy performance.
- `Execution/state/pair_strategy_state.json` remains pair-specific only.
- Do not add `active_strategy`, `pending_strategy`, strategy counters, or strategy PnL fields to pair state.

## 7.6 Update `Execution/report_generator.py`

Parse and aggregate new strategy logs into summary:

- strategy time share
- strategy trades
- strategy pnl contribution
- strategy switch count

New summary fields:

- `strategy_active_time_pct`
- `strategy_trade_counts`
- `strategy_pnl_usdt`
- `strategy_switches`

## 8. Config Additions (`Execution/.env.example`)

Add:

```env
# Strategy Router (Phase 3)
STATBOT_STRATEGY_ROUTER_MODE=off        # off | shadow | active
STATBOT_STRATEGY_MIN_HOLD_SECONDS=900
STATBOT_STRATEGY_CONFIRM_COUNT=2
STATBOT_STRATEGY_ALLOW_SWITCH_IN_POSITION=0
STATBOT_STRATEGY_TREND_ENTRY_Z=2.8
STATBOT_STRATEGY_TREND_ENTRY_Z_MAX=5.0
STATBOT_STRATEGY_TREND_MIN_PERSIST=4
STATBOT_STRATEGY_TREND_SIZE_MULT=0.35
STATBOT_STRATEGY_TREND_MAX_HOLD_HOURS=2
STATBOT_STRATEGY_TREND_USE_DIRECTIONAL_FILTER=0  # experimental, keep OFF in Phase 3
STATBOT_STRATEGY_TREND_ENABLE_MEAN_SHIFT_GATE=1
STATBOT_STRATEGY_TREND_MEAN_SHORT_WINDOW=21
STATBOT_STRATEGY_TREND_MEAN_LONG_WINDOW=200
STATBOT_STRATEGY_TREND_MEAN_SHIFT_Z_THRESHOLD=1.0

# Existing hybrid exit controls (already active runtime baseline)
STATBOT_PROFIT_TARGET_PCT=0.5
STATBOT_PROFIT_TARGET_MIN_USDT=5.0
STATBOT_PROFIT_TARGET_MAX_USDT=50.0
STATBOT_HARD_STOP_PNL_PCT=5.0
STATBOT_ENABLE_COINT_EXIT_TIERS=0
STATBOT_TIER2_CONFIRMATION_COUNT=3
STATBOT_TIER2_MIN_LOSS_PCT=1.5
STATBOT_MAX_SWITCHES_PER_HOUR=5
STATBOT_SWITCH_COOLDOWN_SECONDS=3600
```

Compatibility:

- Current runtime hybrid-exit/switch-limiter variables above are already active in code.
- Strategy-router variables are Phase 3 additions and can stay inert until the router is wired.
- If strategy router is `off`, Phase 2 behavior remains unchanged.
- Directional filter remains OFF by default and is not part of Phase 3 acceptance criteria.
- Mean-shift gate is a Phase 3 entry filter for `TREND_SPREAD`; it is gate-only and does not re-anchor spread mean targets.

## 9. Logging Contract (Required)

New lines (single-line structured text):

1. `STRATEGY_STATUS: mode=... active=... desired=... pending=... allow_new=... reason=...`
2. `STRATEGY_CHANGE: from=... to=... reason=... in_position=...`
3. `STRATEGY_PENDING: active=... desired=... pending=...`
4. `STRATEGY_GATE_ENFORCED: strategy=... reason=...`
5. `COINT_GATE: strategy=... coint_flag=0 allow_new=0`
6. `MEAN_SHIFT_GATE: strategy=TREND_SPREAD shift_z=... threshold=... allow_new=0`

These must be emitted at controlled intervals (same anti-spam style as current regime logs).
Do not emit `STRATEGY_CHANGE` for temporary cointegration-loss gating.

## 10. Rollout Plan

## Phase 3A (Shadow, 2-4 days)

1. Enable strategy router shadow.
2. Emit status/pending/change logs only.
3. Verify switches are sensible and not flapping.

Exit criteria:

- No runtime errors.
- Stable strategy state persistence.
- Clear strategy logs each eval interval.

## Phase 3B (Active, entry-only enforcement, 3-7 days)

1. Enable active routing for new entries.
2. Keep in-position strategy lock.
3. Keep current hybrid exit stack unchanged; allow profile overrides only.

Exit criteria:

- Lower bad-entry count in trend/risk-off windows.
- No increase in unintended pair switches.
- No regression in kill-switch behavior.

## Phase 3C (Report hardening + live readiness)

1. Strategy metrics integrated in reports/index.
2. Validate long run behavior (24-72h demo).
3. Then small-cap live trial.

## 11. Test Plan

## 11.1 Unit Tests

`Execution/tests/test_strategy_router.py`:

1. regime-to-strategy mapping.
2. hysteresis/min-hold.
3. pending behavior while in position.
4. no active switch while in position.
5. active switch on flat transition.

## 11.2 Integration Tests

`Execution/tests/test_strategy_integration.py`:

1. shadow mode does not alter entries.
2. active mode changes entry decision path by strategy.
3. defensive strategy blocks new entries.
4. trend strategy applies configured size multiplier and thresholds.
5. trend strategy blocks entry when mean-shift gate triggers (`shift_z > threshold`).
6. trend strategy allows entry when mean-shift gate does not trigger (`shift_z <= threshold`).

## 11.3 Regression Tests

Run existing:

- `Execution/tests/test_regime_router.py`

And ensure no break in:

- startup
- pair switch restart path (`exit code 3`)
- report generation path.

## 12. Acceptance Criteria

Phase 3 is complete when:

1. Strategy router works in `off|shadow|active`.
2. At least one logged `STRATEGY_CHANGE` and one `STRATEGY_PENDING` event in soak runs.
3. Defensive mode blocks entries reliably in `RISK_OFF`.
4. No forced pair switch solely due to strategy changes.
5. Cointegration loss blocks entries via gate without changing `active_strategy`.
6. TREND mean-shift gate blocks entries (with logs) when configured threshold is exceeded.
7. Report includes strategy-level metrics.

## 13. Suggested Commit Sequence

1. `feat(strategy-router): add router + state + tests (shadow only)`
2. `feat(execution): wire strategy decision into main loop and trade entry path`
3. `feat(trade-mgmt): add trend signal profile + strategy-aware sizing`
4. `feat(reporting): add strategy metrics to report pack`
5. `docs: update README/BOT_DOCUMENTATION/CHANGELOG for phase 3`
