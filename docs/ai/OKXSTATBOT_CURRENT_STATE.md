Current status:
- Controlled test mode. Experiment group: exp_guard050_ethfi_excluded_v1.
- Tradeable capital: 200 USDT.
- Entry Safety Gate enabled.
- Entry gate max_break_risk: 0.12.
- Full TP guard multiplier: 0.50 (reduced from 0.75 — Patch 5 diagnostic experiment).
- Effective TP floor: $0.120 (was $0.180). Profit-lock activation floor: $0.170 (was $0.230).
- PnL profit lock enabled.
- Mean reversion escape disabled.
- Regime router: shadow.
- Strategy router: shadow.
- Advanced ML: shadow.
- Circuit breaker state mode: session. Consecutive loss limit: 3.
- STATARB_MR TREND-regime entries blocked (Patch 4 + Patch 4.1 fix, verified 2026-05-20). Shadow-router divergence bug fixed; block now fires correctly when shadow router has committed to TREND_SPREAD.
- Emergency flatten retry policy: exponential backoff (5s/30s/120s/300s between outer cycles). Inner 3-retry cycle unchanged. Patch 6, active run 99+.
- Hard-exit intent persisted across flatten retry cycles. EXIT_ORCHESTRATOR HARD exits survive clear_entry_tracking(). Cleared on confirmed flat. Patch 6, active run 99+.
- ETHFI-USDT-SWAP permanently graveyarded (repeated_pair_losses, Patch 5).
- TEST1234 permanently blocked.
- Startup pair safety validation implemented.

Experiment state:
- trades_since_experiment_start: 5
- runs_since_experiment_start: 4
- action_threshold: 20 closed trades minimum before any further config changes

Per-hypothesis confidence:
- confidence_coint_fragility_as_dominant_problem: HIGH
- confidence_ethfi_toxicity: HIGH
- confidence_trend_regime_mr_block_value: HIGH
- confidence_notional_neutrality: HIGH
- confidence_break_risk_threshold_correctness: MEDIUM
- confidence_guard_mechanism: LOW
- confidence_trapped_zone_thesis: LOW

Current goal:
- Run exp_guard050_ethfi_excluded_v1.
- Collect minimum 20 closed trades across however many circuit-breaker-limited sessions required.
- Do not draw conclusions or apply further changes before the 20-trade threshold.

Do not do yet:
- Do not scale notional.
- Do not enable Advanced ML live.
- Do not enable routers active.
- Do not change z exit thresholds.
- Do not change cointegration window.
- Do not change max_break_risk.
- Do not change circuit breaker thresholds.
- Do not enable mean reversion escape yet.
