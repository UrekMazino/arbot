Current status:
- Controlled test mode. Experiment group: exp_coint_stability_v1.
- Tradeable capital: 200 USDT.
- Entry Safety Gate enabled.
- Entry gate max_break_risk: 0.12.
- Full TP guard multiplier: 0.50 (Patch 5, retained).
- Effective TP floor: $0.120. Profit-lock activation floor: $0.170.
- PnL profit lock enabled.
- Mean reversion escape disabled.
- Regime router: shadow.
- Strategy router: shadow.
- Advanced ML: shadow.
- Circuit breaker state mode: session. Consecutive loss limit: 3.
- STATARB_MR TREND-regime entries blocked (Patch 4 + Patch 4.1 fix, verified 2026-05-20).
- Emergency flatten retry policy: exponential backoff (5s/30s/120s/300s). Patch 6, active run 99+.
- Hard-exit intent persisted across flatten retry cycles. Patch 6, active run 99+.
- ETHFI-USDT-SWAP permanently graveyarded (repeated_pair_losses, Patch 5).
- HMSTR-USDT-SWAP permanently graveyarded (high_execution_cost_meme_token, 2026-05-23).
- TEST1234 permanently blocked.
- Startup pair safety validation implemented.
- Cointegration stability entry filter active (Patch 7 + 7.1). Window=5 evaluations, slope_max=0.020, sample interval=60s. Rejects pairs whose p-value trend is deteriorating at entry.
- Patch 7.1 (2026-05-24): monitoring-loop buffer pre-population. Buffer now fills from every monitoring cycle (when no position open), not only on z-signal gate calls. Fixes buffer starvation on pairs with sparse z-crossings. record_entry_coint_pvalue() called in main loop; same pair key and interval gate as safety gate.

Experiment state:
- experiment_group: exp_coint_stability_v1 (reset 2026-05-23 after structural review)
- trades_since_experiment_start: 4 (T1-T4, context only — excluded from gate-effectiveness analysis)
- calibration_window_start: Patch 7.1 applied 2026-05-24. Effective calibration window restarts now.
- T1-T4 excluded from gate-effectiveness analysis: evaluated_trade_count was 1/4 (gate non-functional under Patch 7 without 7.1). Their PnL is real and stays in the equity record.
- action_threshold: 20 closed trades in the Patch 7.1 calibration window before any further config changes
- primary_diagnostic: coint_stability gate fire rate = coint_stability_check_blocked_count / coint_stability_check_evaluated_count (target 15%–60% for calibration to be in measurable band)
- calibration_rule: if fire rate <15% after 20 trades → loosen slope_max to 0.030; if >60% → tighten to 0.012. Apply after full window only.
- success_criteria: coint-failure rate ≤25% over 20 trades (baseline 36.8%); coint-exit losses ≤$1.50
- first_run_validation: on first gate-reaching trade under 7.1, confirm evaluated_count ≥ 1 (not insufficient_history). If still insufficient_history, 7.1 failed silently — stop and debug before collecting more trades.

Per-hypothesis confidence (carried from exp_guard050_ethfi_excluded_v1 structural review):
- confidence_coint_fragility_as_dominant_problem: HIGH
- confidence_ethfi_toxicity: HIGH
- confidence_trend_regime_mr_block_value: HIGH
- confidence_notional_neutrality: HIGH
- confidence_break_risk_threshold_correctness: MEDIUM
- confidence_guard_mechanism: LOW (both Patch-5 mechanisms inert in 20-trade window)
- confidence_profit_lock_band_mechanism: MEDIUM (mechanism confirmed operational; floor-reduction benefit unconfirmed)

Current goal:
- Run exp_coint_stability_v1.
- Collect minimum 20 closed trades.
- Monitor gate fire rate vs evaluated count (not vs total entries).
- Do not draw conclusions or apply further changes before the 20-trade threshold.

Do not do yet:
- Do not scale notional.
- Do not enable Advanced ML live.
- Do not enable routers active.
- Do not change z exit thresholds.
- Do not change cointegration window.
- Do not change max_break_risk.
- Do not change circuit breaker thresholds.
- Do not enable mean reversion escape.
- Do not adjust slope_max mid-window.
