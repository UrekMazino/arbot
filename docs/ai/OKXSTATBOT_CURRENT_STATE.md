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
- trades_since_experiment_start: 8 (T1 JUP/YGG r125, T2 LTC/KSM r126, T3 BNB/LINK r129, T4 DOGE/AAVE r130, T5 AVAX/DOT r131, T6 SOL/AVAX r132, T7 SOL/CRV r134, T8 BCH/ETC r135)
- $/σ sign-flip rate: 0/5 = 0% (eligible = T2, T5, T6, T7, T8; all positive. T1, T3, T4 excluded as coint-failures)
- aggregate $/σ (pooled): +$0.044/σ (T2 +0.064, T5 +0.017, T6 +0.020, T7 +0.094, T8 +0.054) — H1 rock-solid, β-sizing aligns signal/position 5/5
- coint-failure count (window): 3/8 = 37.5% (T1, T3, T4) — trending DOWN 75→60→50→37.5%, now BELOW the 40% baseline
- E4 WATCH (not firing): 37.5% below baseline; needs ≥10 closed (currently 8). Trending strongly favorable — universe fragility looking less like the binding problem.
- beta_range_observed: [0.378, 1.495] (T6/T7/T8 near-unity 0.91/0.89/0.86); β<1.0: 6/8; materially non-unity: 5/8; fallback: 0; β-sizing flawless 8/8 (exact to the cent)
- cumulative PnL (experiment window): -$1.765 (T1 -0.962, T2 -0.105, T3 -0.267, T4 -0.253, T5 -0.030, T6 -0.1285, T7 +0.0153 WIN, T8 -0.035); win rate 1/8
- edge_clears_costs (realized): 1/5 (T7 win, +$0.0153). KEY FORK UPDATE: pnl_at_mean > cost now 2/5 (T7 +0.230>0.215, T8 +0.169>0.159), up from 0/3. In-zone edge is PAIR-DEPENDENT, not uniformly thin (BCH/ETC, SOL/CRV cleared at mean; AVAX/DOT, SOL/AVAX, LTC/KSM didn't). Edge-too-thin NOT a universal verdict. Exit-redesign/Item 14 REOPENS for the edge-bearing subset (T7 captured edge→win; T8 cleared at mean but exit leaked it→loss = genuine EXIT-TOO-LATE). SUBSET-VIABLE shape materializing → query 3 is the instrument.
- action_threshold: 20 closed trades before structural review
- trades_remaining: 12 (to 20 total); ≥3 more $/σ-eligible needed (5 eligible after 8 trades)
- primary_diagnostic: $/σ sign stability across trades (should be positive for all normal-exit trades), gross conserved at $200 per trade
- $/σ INCLUSION RULE v1.2 (tightened, T3 run 129): compute $/σ only if exit_reason ∈ {normal, trailing_stop, profit_lock} AND MFE>0 AND |Δz|≥0.5. Coint-failure exits (cointegration_lost, cointegration_watch_timeout) go to the coint-failure tracker, NOT the $/σ table — regardless of z reversion. Mechanical, no per-trade judgment.
- success_criteria: $/σ sign-flip rate ≤ 10% over 20 normal-exit trades; cumulative PnL improvement vs equal-notional baseline
- sizing_mode: gross_normalized_beta (Option C confirmed via retroactive counterfactual — docs/audits/counterfactual_exp_coint_stability_v1.md)
- audit: docs/audits/exp_beta_aware_sizing_v1_per_run_audit.md (runs 125-135, T1-T8)
- run_128: 0 trades, operational event (OKX API outage + 77-min flatten loop), not experimental data
- run_129: T3 BNB/LINK, β=0.378, gross=$200 verified to the cent, exit=cointegration_watch_timeout, gross position_pnl -$0.137 (costs textbook 1.0×), RISK_OFF vol_shock flip ~50s post-entry. Ended via max_session_trades=1.
- run_130: T4 DOGE/AAVE, β=0.760, gross=$200 to the cent, exit=cointegration_lost, gross position_pnl -$0.110 (costs textbook 1.0×), MFE -$0.103 never positive despite z reverting -2.20→-0.10 into exit zone (guard blocked full_tp 23×). Patch 4.1 TREND block fired correctly on ASTER/SOL. Ended via max_session_trades=1.
- run_131: T5 AVAX/DOT, β=0.659, gross=$200 to the cent. 2nd $/σ-ELIGIBLE trade (normal/profit_lock exit, MFE +$0.187>0, Δz=4.00). $/σ=+$0.017 POSITIVE (sign-flip now 0/2). Gross position_pnl +$0.069 (positive) but net -$0.030 (costs ~$0.10). Query 1 finding: pnl_at_mean +$0.052 < costs (MFE was overshoot, not thesis-capturable). First profit-lock activation; floor below cost-clearance. Coint held. Ended via max_session_trades=1.
- run_132: T6 SOL/AVAX, β=0.911 (first near-unity). gross=$200 to the cent (6/6 exact). 3rd $/σ-ELIGIBLE (normal/profit_lock, MFE +$0.179>0, Δz=3.26). $/σ=+$0.020 POSITIVE (sign-flip 0/3). Gross +$0.065 (worked) but net -$0.1285 (costs $0.194). pnl_at_mean +$0.026, in-zone max PnL +$0.0067 — profit at overshoot. 2nd profit-lock activation, below cost-clearance. Coint held. Ended via max_session_trades=1.
- run_134: T7 SOL/CRV, β=0.8865 (8/8 exact). 4th $/σ-ELIGIBLE, FIRST WIN. entry_z=-2.78 (deepest), exit_z=-0.34, hold 1.1 min (fastest). Gross +$0.230 = MFE (exited AT peak, at zone edge z=-0.34); guard blocked 0× (in-zone PnL above floor → full_tp fired). Net +$0.0153, edge cleared costs ($0.215). $/σ=+$0.094 (highest). pnl_at_mean > cost: YES. Deep entry → big reversion → in-zone edge cleared. Ended via max_session_trades=1.
- run_135: T8 BCH/ETC, β=0.8633 (8/8 exact). 5th $/σ-ELIGIBLE. entry_z=+2.17, exit_z=-0.12, hold 9.6 min. Gross +$0.124, net -$0.035 (costs $0.159). KEY: pnl_at_mean +$0.169 (at z=-0.05) > cost $0.159 — thesis-mean edge CLEARED, but exit held past mean into overshoot (z=-0.60, +$0.282) and gave it back → genuine EXIT-TOO-LATE (mean-disciplined exit would have won). $/σ=+$0.054. Ended via max_session_trades=1.
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
