# Changelog

All notable changes to StatBot are documented in this file.

## [1.0.0] - 2026-01-29

### Added
- Contract-aware sizing using ctVal/ctMult with pre-trade availEq/availBal checks.
- Per-run log files in Logs/ with rotation controls and concise INFO output.
- PNL alerts for session thresholds and trade close events (post-close equity refresh).
- Molt monitor for executive alerts and Discord command listener for !status/!pnl/!pair/!balance/!help.
- Report generator that produces per-run evidence packs (summary, equity curve, trades, alerts, config snapshot).
- Optional uptime trigger to auto-generate a report after N hours.
- Liquidity analysis in report packs (high/low classification and ratios).
- Liquidity guard and corrected contract-aware liquidity targets in logs.
- Entry preview logging and slippage metrics in report packs.

### Changed
- Updated BOT_DOCUMENTATION.md and README.md to reflect logging, alerts, and command controls.
