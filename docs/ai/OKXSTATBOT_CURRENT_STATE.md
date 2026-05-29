Current status:
- Controlled test mode. Experiment group: exp_beta_aware_sizing_v1 (started 2026-05-28).
- Tradeable capital: 200 USDT gross per trade (β-split across legs, not equal-notional).
- Beta-aware sizing ACTIVE: STATBOT_HEDGE_RATIO_SIZING_ENABLED=true. Option C: gross-normalized-beta. gross=$200, leg1=gross/(1+β), leg2=gross×β/(1+β). β from entry cointegration metrics["hedge_ratio"]. Sizing-fallback bounds: min=0.20, max=5.00 (convention-derived [1/N, N], unsourced). Fallback: equal-notional if β invalid. NOTE: binding β constraint is the tighter upstream discovery filter STATBOT_STRATEGY_MIN/MAX_HEDGE_RATIO=[0.3, 3.0] (func_cointegration.py:1720) — observable β is bounded to [0.3, 3.0], so the [0.20, 5.00] sizing fallback is nearly inert.
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
- Patch 6 item 5 (alert/kill-switch after N consecutive flatten failures): NEXT OPERATIONAL PRIORITY. Run 128 sustained-outage flatten loop (77 min, 14 cycles, manual stop required) is the second occurrence of the run-98 class. Backoff working as designed but no terminal state. Must be implemented before any live trading.
- ETHFI-USDT-SWAP permanently graveyarded (repeated_pair_losses, Patch 5).
- HMSTR-USDT-SWAP permanently graveyarded (high_execution_cost_meme_token, 2026-05-23).
- FLOKI-USDT-SWAP permanently graveyarded (high_execution_cost_meme_token, 2026-05-25).
- TEST1234 permanently blocked.
- Startup pair safety validation implemented.
- Cointegration stability entry filter active (Patch 7 + 7.1). Window=5 evaluations, slope_max=0.020, sample interval=60s.
- hedge_ratio now logged in entry_gate_component_scores (Day 1 telemetry for exp_beta_aware_sizing_v1).

Experiment state (exp_beta_aware_sizing_v1):
- experiment_group: exp_beta_aware_sizing_v1 (reset 2026-05-28 after exp_coint_stability_v1 structural review + counterfactual study)
- trades_since_experiment_start: 4 (T1 JUP/YGG run_125, T2 LTC/KSM run_126, T3 BNB/LINK run_129, T4 DOGE/AAVE run_130)
- $/σ sign-flip rate: 0/1 = 0% (computable population = T2 only; T1, T3, T4 excluded as coint-failures under Rule v1.2)
- cumulative_aggregate_sigma: +$0.064/σ (positive; unchanged — T4 not in population)
- coint-failure count (window): 3/4 = 75% (T1 cointegration_lost, T3 cointegration_watch_timeout, T4 cointegration_lost)
- E4 WATCH (not firing): coint-failure 75% is above the >60% kill-line, but E4 requires ≥10 closed trades to evaluate (currently 4). If rate holds, E4 fires at trade 10 → halt sizing test, address coint-fragility/universe. Experiment may resolve via E4 before H1/H2 readable.
- beta_range_observed: [0.378, 1.495] (T4 β=0.760 inside existing range); β<1.0: 3/4; non-unity: 4/4; fallback: 0; β-sizing mechanically flawless 4/4 (exact to the cent)
- cumulative PnL (experiment window): -$1.587 (T1: -$0.962, T2: -$0.105, T3: -$0.267, T4: -$0.253)
- edge_clears_costs: 0/1 (T2 position_pnl +$0.146 < real_costs $0.251)
- action_threshold: 20 closed trades before structural review
- trades_remaining: 16 (to 20 total); ≥7 more $/σ-eligible needed (only T2 eligible after 4 trades — dilution problem materializing)
- primary_diagnostic: $/σ sign stability across trades (should be positive for all normal-exit trades), gross conserved at $200 per trade
- $/σ INCLUSION RULE v1.2 (tightened, T3 run 129): compute $/σ only if exit_reason ∈ {normal, trailing_stop, profit_lock} AND MFE>0 AND |Δz|≥0.5. Coint-failure exits (cointegration_lost, cointegration_watch_timeout) go to the coint-failure tracker, NOT the $/σ table — regardless of z reversion. Mechanical, no per-trade judgment.
- success_criteria: $/σ sign-flip rate ≤ 10% over 20 normal-exit trades; cumulative PnL improvement vs equal-notional baseline
- sizing_mode: gross_normalized_beta (Option C confirmed via retroactive counterfactual — docs/audits/counterfactual_exp_coint_stability_v1.md)
- audit: docs/audits/exp_beta_aware_sizing_v1_per_run_audit.md (runs 125-130, T1-T4)
- run_128: 0 trades, operational event (OKX API outage + 77-min flatten loop), not experimental data
- run_129: T3 BNB/LINK, β=0.378, gross=$200 verified to the cent, exit=cointegration_watch_timeout, gross position_pnl -$0.137 (costs textbook 1.0×), RISK_OFF vol_shock flip ~50s post-entry. Ended via max_session_trades=1.
- run_130: T4 DOGE/AAVE, β=0.760, gross=$200 to the cent, exit=cointegration_lost, gross position_pnl -$0.110 (costs textbook 1.0×), MFE -$0.103 never positive despite z reverting -2.20→-0.10 into exit zone (guard blocked full_tp 23×). Patch 4.1 TREND block fired correctly on ASTER/SOL. Ended via max_session_trades=1.
- structural-review template: docs/prompts/structural_review_exp_beta_aware_sizing_v1_template_v1.md (v1.1; §4 gate = ≥20 total AND ≥8 eligible whichever later; E4 kill-criterion; §5 negative bar locked)
- deferred (structural review): pre-entry regime-flip detection — can the regime indicator flag imminent vol_shock flips at entry to block T3-class entries? (entry-side analogue of the run-98 regime-flip exit-timing item)

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
