Current status:
- Controlled test mode. Experiment group: exp_beta_aware_sizing_v1 (started 2026-05-28).
- Tradeable capital: 200 USDT gross per trade (β-split across legs, not equal-notional).
- Beta-aware sizing ACTIVE: STATBOT_HEDGE_RATIO_SIZING_ENABLED=true. Option C: gross-normalized-beta. gross=$200, leg1=gross/(1+β), leg2=gross×β/(1+β). β from entry cointegration metrics["hedge_ratio"]. Bounds: min=0.20, max=5.00. Fallback: equal-notional if β invalid.
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
- FLOKI-USDT-SWAP permanently graveyarded (high_execution_cost_meme_token, 2026-05-25).
- TEST1234 permanently blocked.
- Startup pair safety validation implemented.
- Cointegration stability entry filter active (Patch 7 + 7.1). Window=5 evaluations, slope_max=0.020, sample interval=60s.
- hedge_ratio now logged in entry_gate_component_scores (Day 1 telemetry for exp_beta_aware_sizing_v1).

Experiment state (exp_beta_aware_sizing_v1):
- experiment_group: exp_beta_aware_sizing_v1 (reset 2026-05-28 after exp_coint_stability_v1 structural review + counterfactual study)
- trades_since_experiment_start: 0
- action_threshold: 20 closed trades before structural review
- primary_diagnostic: $/σ sign stability across trades (should be positive for all normal-exit trades), gross conserved at $200 per trade
- success_criteria: $/σ sign-flip rate ≤ 10% over 20 normal-exit trades; cumulative PnL improvement vs equal-notional baseline
- sizing_mode: gross_normalized_beta (Option C confirmed via retroactive counterfactual — docs/audits/counterfactual_exp_coint_stability_v1.md)

exp_coint_stability_v1 final record (for reference):
- Trades: 14 (T1-T14). Patch 7.1 calibration window: T5-T14 (10 trades). Early review triggered at T14.
- Verdict: 10A CONFIRMED (sizing mismatch); 10B NEGATIVE (coint filter premise wrong). Decision: exp_beta_aware_sizing_v1.
- Cumulative PnL (T1-T14): -$4.240. Win rate (T5-T14): 1/10 = 10%.

Current goal:
- Run exp_beta_aware_sizing_v1 with beta-aware sizing live.
- Verify hedge_ratio logged in entry_gate_component_scores on Day 1 trade.
- Verify BETA_SIZING log line shows expected leg1/leg2 split on each entry.
- Collect minimum 20 closed trades before structural review.

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
