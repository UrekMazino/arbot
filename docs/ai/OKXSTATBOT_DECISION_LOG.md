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

Patch 4.1 — entry_strategy_name override for TREND block (2026-05-20):
- Type: Bug fix.
- Evidence: run_95 — 0 statarb_mr_trend_regime_block rejections; AVAX/FIL pair active 65 min in TREND regime.
- Root cause: Shadow strategy router commits active_strategy="TREND_SPREAD" via hysteresis (≥900s hold + 2 confirms). Gate reads strategy_decision.active_strategy via _router_state(); when this is "TREND_SPREAD", the check strategy_name == "STATARB_MR" fails silently. Policy-resolved execution strategy (always STATARB_MR in shadow mode, from resolve_strategy_policy_overrides) was never passed to the gate.
- Fix: Added entry_strategy_name parameter to evaluate_entry_safety_gate(). Call site in func_trade_management.py passes strategy_name resolved from resolve_strategy_policy_overrides — the actual execution strategy, not the shadow router's internal state.
- Files: entry_safety_gate.py, func_trade_management.py, test_entry_safety_gate.py.
- Tests: 2 new tests — shadow router shows TREND_SPREAD but block fires with entry_strategy_name="STATARB_MR"; blind-spot documented for regression tracking.
- Trade counter at fix: 3/20. No new trades during investigation.

Patch 5 — Guard Calibration + ETHFI Exclusion (exp_guard050_ethfi_excluded_v1, run 95+):
- STATBOT_FULL_TP_GUARD_MULTIPLIER reduced 0.75 → 0.50.
  Effective TP floor: $0.180 → $0.120. Profit-lock activation: $0.230 → $0.170.
  Rationale: diagnostic experiment — 0 guard passes across 9 trades, 3 runs. Change is diagnostic (not a profit fix); guard fires only if MFE peaks inside z≤0.35 window.
- ETHFI-USDT-SWAP added to graveyard (repeated_pair_losses).
  Rationale: 2 appearances, 2 cointegration failures, avg PnL -$0.533, worst MAE cluster. ETH staking derivative structurally misaligned with stat-arb cointegration assumptions.
- Two-variable change accepted: changes target orthogonal failure classes (guard → TP-zone activation rate; ETHFI → coint-failure rate). Attribution is recoverable via different telemetry channels.
- Action threshold: 20 closed trades before any further config changes.
