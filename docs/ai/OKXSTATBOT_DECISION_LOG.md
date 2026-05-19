- Full TP now outranks partial TP.
- ExitOrchestrator guard now aligns with trade-manager guard.
- PnL profit lock added, disabled by default but enabled in controlled config.
- Entry Safety Gate added, disabled by code default but enabled in controlled runtime.
- Stop-loss trigger validation hardened.
- Emergency flatten verification added.
- Circuit breaker state split into session vs persistent.
- Startup pair hospital/graveyard validation added.
- Guard Floor Cost Calibration Audit and Apply Plan added to repo.

Patch 4 — Regime-Aligned Mean Reversion Safety (runs 94+):
- STATARB_MR entries blocked when regime == TREND (live hard gate).
- Rejection reason: statarb_mr_trend_regime_block.
- Evidence: FIL/LDO (run 93) entered fully in TREND regime, shadow_trend_mr_block fired 100% of evaluations, largest equity loss of any run.
- Confirmed zero activations in run 94 — TREND regime and cointegration failures are correlated; pairs fail strategy_gate before reaching the safety gate in TREND conditions.

Patch 5 — Guard Calibration + ETHFI Exclusion (exp_guard050_ethfi_excluded_v1, run 95+):
- STATBOT_FULL_TP_GUARD_MULTIPLIER reduced 0.75 → 0.50.
  Effective TP floor: $0.180 → $0.120. Profit-lock activation: $0.230 → $0.170.
  Rationale: diagnostic experiment — 0 guard passes across 9 trades, 3 runs. Change is diagnostic (not a profit fix); guard fires only if MFE peaks inside z≤0.35 window.
- ETHFI-USDT-SWAP added to graveyard (repeated_pair_losses).
  Rationale: 2 appearances, 2 cointegration failures, avg PnL -$0.533, worst MAE cluster. ETH staking derivative structurally misaligned with stat-arb cointegration assumptions.
- Two-variable change accepted: changes target orthogonal failure classes (guard → TP-zone activation rate; ETHFI → coint-failure rate). Attribution is recoverable via different telemetry channels.
- Action threshold: 20 closed trades before any further config changes.
