# Changelog

All notable changes to StatBot are documented in this file.

## [Unreleased]

### Added
- Regime Router V1 Phase 0 (evaluation-only) with `off|shadow|active` modes.
- New regime evaluation module: `Execution/regime_router.py`.
- New regime state persistence module: `Execution/func_regime_state.py`.
- New runtime state file: `Execution/state/regime_state.json`.
- Structured regime logs: `REGIME_STATUS`, `REGIME_CHANGE`, `REGIME_POLICY`, `REGIME_GATE`.
- Active-mode enforcement log: `REGIME_GATE_ENFORCED`.
- Regime router environment variables in `Execution/.env.example`.
- Router test suite: `Execution/tests/test_regime_router.py`.

### Changed
- Phase 0 uses shadow evaluation only; no entry/exit or kill-switch behavior changes.
- `pnl_fallback` risk signal now applies only when fallback occurs while in-position.
- Thin-liquidity classification is now depth-ratio-led (history low label alone does not force `RISK_OFF`).
- Phase 1 enabled: in `STATBOT_REGIME_ROUTER_MODE=active`, bot now enforces gate-only behavior by skipping new entries when regime policy disallows entries.
- Phase 2 enabled: in `STATBOT_REGIME_ROUTER_MODE=active`, bot now applies regime policy overrides for new entries (`entry_z`, `entry_z_max`, `min_persist_bars`, `min_liquidity_ratio`, `size_multiplier`) in addition to gate enforcement.

## [1.0.0] - 2026-01-29

### Added
- Contract-aware sizing using ctVal/ctMult with pre-trade availEq/availBal checks.
- Per-run log files in Logs/ with rotation controls and concise INFO output.
- PNL alerts for session thresholds and trade close events (post-close equity refresh).
- Report generator that produces per-run evidence packs (summary, equity curve, trades, alerts, config snapshot).
- Optional uptime trigger to auto-generate a report after N hours.
- Liquidity analysis in report packs (high/low classification and ratios).
- Liquidity guard and corrected contract-aware liquidity targets in logs.
- Entry preview logging and slippage metrics in report packs.

### Changed
- Updated BOT_DOCUMENTATION.md and README.md to reflect logging and reporting controls.
