# OKXStatBot Unified Documentation

Last updated: 2026-03-26  
Scope: Execution engine, regime and strategy routing, scheduler, and V2 platform.

## 1. Single Source of Truth

This file replaces and supersedes the following documents:

- `BOT_DOCUMENTATION.md` (previous version)
- `CHANGELOG.md`
- `COINT_GATE_FIX_SUMMARY.md`
- `EXECUTION_CODE_REVIEW.md`
- `KILL_SWITCH_STATE_MACHINE.md`
- `REGIME_ROUTER_V1_SPEC.md`
- `REGIME_ROUTER_PHASE3_SPEC.md`
- `REGIME_ROUTER_PHASE4_SPEC.md`
- `SCHEDULER_README.md`
- `V2_ROADMAP.md`
- `V2_UI_PLATFORM_SPEC.md`

Maintenance rule: update only this file for architecture, runtime behavior, milestones, and roadmap.

## 2. Product Summary

OKXStatBot is a statistical arbitrage pairs-trading system for OKX with:

1. Continuous execution at 1-minute data resolution.
2. Cointegration-based signal generation.
3. Layered risk controls (entry gates, hard stop, hybrid exits, circuit breaker).
4. Automatic pair lifecycle handling (switching, hospital, graveyard, refresh loop).
5. V2 web platform for observability, reports, and operations.

## 3. Core Trading Model

### 3.1 Strategy and Signal Basics

1. Spread model:
   - OLS on log prices.
   - Spread = ln(A) - beta * ln(B).
2. Cointegration:
   - ADF/coint gates are used to qualify pair behavior.
3. Z-score:
   - Rolling normalization (default runtime baseline: 21 bars for entry timing).
4. Entry baseline (statarb profile):
   - `|z| >= 2.0`
   - Persistence: 3 bars.

### 3.2 Entry Direction

1. `z >= +entry_threshold`: sell spread.
2. `z <= -entry_threshold`: buy spread.

### 3.3 In-Position Exit Priority (Authoritative Runtime)

Exit evaluation order:

1. Tier 5 adaptive profit target.
2. Tier 1 hard stop.
3. Tier 1.5 risk-off + cointegration early exit (when enabled).
4. Tier 2-4 cointegration exits (optional, default off).
5. ATM dynamic exits (trailing, partials, max hold, mean-reversion target).
6. Funding bleed guard.
7. No-entry-context fallback safeguards.

## 4. Risk Management and Safety

### 4.1 Position and Execution Safety

1. Position sizing targets 2 percent risk logic.
2. Contract-aware sizing uses `ctVal` and `ctMult`.
3. Pre-trade equity checks gate entries.
4. Liquidity guard can downsize or reject entries.
5. Circuit breaker can panic-close and stop run on drawdown threshold.

### 4.2 Kill-Switch State Machine

1. `0` ACTIVE: seek and manage normal flow.
2. `1` IN_POSITION: monitor open trade.
3. `2` STOP/CLOSE: force close and exit cycle/run path.
4. `3` PAIR_SWITCH_RESTART: subprocess restart path to load next pair.

Deterministic transitions are logged. No forced semantic changes to this model in regime/strategy upgrades.

## 5. Pair Lifecycle and Reliability

### 5.1 Pair Rotation and Memory

1. Hospital queue for recoverable failed pairs.
2. Graveyard blacklist with reason-based TTL.
3. Cooldown and switch-rate limiting to prevent churn.
4. Re-entry cooldown to avoid clustering re-entry.
5. Strategy refresh loop when no eligible replacement pair exists.

### 5.2 Cointegration Gate Streak Fix (Implemented)

Problem addressed:

- Old behavior could stay indefinitely blocked under repeated `coint_gate` without switching.

Current behavior:

1. Track consecutive `coint_gate` evaluations.
2. Trigger pair switch after configurable streak threshold.
3. Reset streak on recovery.
4. Move failing pair through normal hospital/graveyard lifecycle.

Key env:

- `STATBOT_COINT_GATE_THRESHOLD` (default `2`, bounded `1..10`).

## 6. Regime and Strategy Routing

### 6.1 Regime Router (V1)

Implemented mode controls:

- `STATBOT_REGIME_ROUTER_MODE=off|shadow|active`

Core regimes:

1. `RANGE`
2. `TREND`
3. `RISK_OFF`

Active-mode effects:

1. Gate entries when policy disallows.
2. Apply policy overrides to new entries:
   - `entry_z`
   - `entry_z_max`
   - `min_persist_bars`
   - `min_liquidity_ratio`
   - `size_multiplier`

Structured logs include:

- `REGIME_STATUS`
- `REGIME_CHANGE`
- `REGIME_POLICY`
- `REGIME_GATE`
- `REGIME_GATE_ENFORCED`

### 6.2 Strategy Router (Phase 3)

Route mapping:

1. `RANGE -> STATARB_MR`
2. `TREND -> TREND_SPREAD`
3. `RISK_OFF -> DEFENSIVE`

Behavioral rules:

1. Strategy switch affects new entries, not forced in-position close.
2. Pending strategy can queue while in position.
3. Cointegration gate can block entries without strategy-change churn.
4. Mean-shift gate can block TREND profile entries.

Primary logs:

- `STRATEGY_STATUS`
- `STRATEGY_CHANGE`
- `STRATEGY_PENDING`
- `STRATEGY_GATE_ENFORCED`
- `COINT_GATE`
- `MEAN_SHIFT_GATE`

### 6.3 Phase 4 Quality Loop (Deferred Queue, Partially Implemented)

Execution queue focus:

1. Strategy attribution in state/log/report outputs.
2. Strategy cooldown controller for underperforming profiles.
3. TREND quality upgrades:
   - regime-aware lookback
   - directional filter (`off|shadow|active`)
4. Strategy-specific ATM profile overrides.

Roadmap status from repository docs:

1. P4B cooldown controller: implemented.
2. P4C lookback and directional filter modes: implemented, validation ongoing.
3. P4D strategy ATM overrides: implemented.

## 7. Runtime State, Logs, and Reports

### 7.1 Key State Files

Stored under `Execution/state`:

1. `active_pair.json`
2. `status.json`
3. `pair_strategy_state.json`
4. `strategy_state.json`
5. `regime_state.json`

### 7.2 Logging

1. Per-run log files with rotation controls.
2. Run-level index artifacts (`index.json`, `index.csv`) in log/report directories.
3. Structured runtime lines for regime, strategy, gate, and risk events.

### 7.3 Report Pack

Per-run evidence pack can include:

1. `summary.json` and `summary.txt`
2. `equity_curve.csv`
3. `trades.csv`
4. Strategy/regime scorecards
5. Gate and switch artifacts
6. Reconciliation and data quality checks
7. Liquidity and slippage artifacts
8. Alerts and config snapshot

## 8. Scheduler Operations

Purpose: run Strategy scans periodically without stopping Execution.

Main scripts:

1. `strategy_scheduler.py`
2. `start_bot.py`

Behavior:

1. Scheduler runs strategy discovery at configurable interval.
2. Execution keeps running with active trades unaffected.
3. Updated pair artifacts are consumed when switching.
4. Scheduler respects graveyard exclusions.

Key env:

- `STATBOT_STRATEGY_INTERVAL` (default `3600`, min `300`).

## 9. V2 Platform Architecture

V2 is API-first and separates execution runtime from product UI.

Core stack:

1. Web: Next.js + TypeScript.
2. API: FastAPI + SQLAlchemy + Alembic.
3. DB: PostgreSQL.
4. Realtime and queue: Redis + RQ worker.

Data boundary decision:

1. Bot emits events to API endpoints.
2. API persists and publishes realtime updates.
3. Bot can use spool/retry when API path is unavailable.

### 9.1 V2 Functional Modules

1. Dashboard (live runtime and PnL).
2. Runs and run detail views.
3. Reports generation and downloads.
4. Admin tools (users, roles, audit, control).
5. Analytics (strategy/regime attribution views).

### 9.2 API Surface (MVP)

Main groups:

1. Auth (`login`, `refresh`, `logout`, `me`).
2. Event ingestion (`events/batch`, heartbeat).
3. Runs, trades, metrics, analytics.
4. Report generation and files.
5. WebSocket dashboard stream.

## 10. Milestones and Change Summary

### 10.1 2026-01 Stabilization

Highlights:

1. Contract-aware sizing and pre-trade checks.
2. Per-run logs with rotation.
3. PnL alerting and report evidence packs.
4. Liquidity guard and slippage reporting.

### 10.2 2026-01 Execution Review Fixes

A full execution review identified 14 issues across critical/high/medium/low severity.
Current summary state: resolved in repository history.

Fix themes:

1. PnL and circuit-breaker correctness.
2. Entry/exit logic cleanup and validation.
3. Better exception logging and timeout handling.
4. Kill-switch transition traceability.

### 10.3 2026-02 Routing and Gate Enhancements

Highlights:

1. Regime router integration with shadow/active modes.
2. Gate and entry-policy enforcement in active mode.
3. Cointegration gate streak switch fix.
4. Strategy-routing expansion and deferred Phase 4 queue tracking.

## 11. Current Roadmap Snapshot

### 11.1 Completed or In Progress

1. V2-A UI-first slices: foundational dashboard/report/admin capabilities in place.
2. Deferred engine queue implementation items (P4B/P4C/P4D): implemented.

### 11.2 Pending Validation/Hardening

1. Cooldown shadow/active validation windows.
2. Directional filter shadow-to-active promotion criteria.
3. End-to-end strategy/regime analytics integration polish in V2 dashboard.
4. Production hardening and rollout evidence collection.

## 12. Key Environment Variables (Quick Reference)

Risk and exits:

- `STATBOT_PROFIT_TARGET_PCT`
- `STATBOT_PROFIT_TARGET_MIN_USDT`
- `STATBOT_PROFIT_TARGET_MAX_USDT`
- `STATBOT_HARD_STOP_PNL_PCT`
- `STATBOT_ENABLE_COINT_EXIT_TIERS`
- `STATBOT_TIER2_CONFIRMATION_COUNT`
- `STATBOT_TIER2_MIN_LOSS_PCT`

Switching and routing:

- `STATBOT_MAX_SWITCHES_PER_HOUR`
- `STATBOT_SWITCH_COOLDOWN_SECONDS`
- `STATBOT_COINT_GATE_THRESHOLD`
- `STATBOT_REGIME_ROUTER_MODE`
- `STATBOT_STRATEGY_ROUTER_MODE`

Phase 4 quality controls:

- `STATBOT_STRATEGY_SCORE_WINDOW_TRADES`
- `STATBOT_STRATEGY_SCORE_MIN_TRADES`
- `STATBOT_STRATEGY_SCORE_MIN_WIN_RATE`
- `STATBOT_STRATEGY_SCORE_MAX_ROLLING_LOSS_USDT`
- `STATBOT_STRATEGY_COOLDOWN_SECONDS`
- `STATBOT_RANGE_Z_LOOKBACK`
- `STATBOT_TREND_Z_LOOKBACK`
- `STATBOT_STRATEGY_TREND_DIRECTIONAL_FILTER_MODE`

Scheduler and strategy refresh:

- `STATBOT_STRATEGY_INTERVAL`
- `STATBOT_STRATEGY_KLINE_LIMIT`

## 13. Testing and Operations Checklist

1. Unit and integration tests for regime/strategy routers pass.
2. No regressions in kill-switch semantics (`0/1/2/3`).
3. Pair-switch restart path (exit code 3) remains stable.
4. Report generation captures strategy/regime attribution artifacts.
5. Long-run soak verifies no hidden trade starvation.

## 14. Documentation Governance

When behavior changes:

1. Update this file in the same PR/commit.
2. Keep sections concise and current-state focused.
3. Archive obsolete details by replacing them with milestone summaries.
4. Avoid creating parallel root-level spec files unless explicitly required.


