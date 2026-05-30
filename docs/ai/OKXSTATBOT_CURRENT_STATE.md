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
- trades_since_experiment_start: 12 (T1–T9 as before + T10 AVAX/ETC r137, T11 AVAX/ETC r138, T12 ARB/OP r139)
- $/σ sign-flip rate: 0/5 = 0% (eligible = T2, T5, T6, T7, T8; all positive. T1, T3, T4, T9, T11, T12 excluded as coint-failures; T10 excluded as adverse-normal MFE<0)
- aggregate $/σ (pooled): +$0.044/σ (unchanged — H1 rock-solid 5/5)
- coint-failure count (window): 6/12 = 50% (T1, T3, T4, T9, T11, T12) — trajectory 75→60→50→37.5→44.4→**50** (oscillating, within historical band [36.8, 55.6])
- **E4 EVALUABLE NOW (≥10 closed): 50% in 45–60% REVIEW band, NOT HALT** per calibration note. Flag for structural-review; continue collection. Pre-commit held.
- adverse-normal-exits bucket (NEW, MFE<0): 1 (T10 AVAX/ETC, 35-sec hold, z diverged)
- beta_range_observed: [0.378, 1.495] (T10 β=0.490, T11 β=0.457, T12 β=0.655); β<1.0: 10/12; materially non-unity: 9/12; fallback: 0; β-sizing flawless 12/12
- cumulative PnL (experiment window): -$3.685 (T10 -0.405, T11 -0.563, T12 -0.845 = -$1.813 last 3 — worst drawdown stretch). win rate 1/12
- edge_clears_costs (realized): 1/5 (T7 win). FORK unchanged: pnl_at_mean > cost = 2/5 (T7, T8). SUBSET-VIABLE shape; query 3 the instrument.
- coint-failure mechanism: 4/6 clean β-sized DECOUPLED (T3b, T4b, T9, T11; T1b thin-pair TRACKED, T12 borderline TRACKED) — mean-shift signature continues; refuted-lever guardrail intact (T11/T12 entered benign slopes).
- RISK_OFF-entry vector: now **2/2 → coint-failure** (T9, T12). T12 also carries **2.4× cost overrun** ($0.336 vs textbook $0.14). First candidate entry-side lever for coint-failure that survives refuted-lever guardrail (regime ≠ coint metric; shadow router already computes the signal). Strengthened, still n=2.
- recon FAIL (β-sizing window): 1 (T12 ARB/OP, unexplained −$0.196, RISK_OFF entry).
- pair-re-selection: T11 entered AVAX/ETC ~35 min after T10 lost on same pair (opposite side, also lost). New structural-review deferred item (recently-failed-pair cooldown).
- adverse-normal exits: 1 (T10) — neither $/σ-eligible nor coint-failure. New shape; mechanism in coarse "normal" exit label may be a stop-tier; flag if recurs.
- action_threshold: 20 closed trades before structural review
- trades_remaining: 8 (to 20 total); ≥3 more $/σ-eligible needed (5 eligible after 12 trades)
- primary_diagnostic: $/σ sign stability across trades (should be positive for all normal-exit trades), gross conserved at $200 per trade
- $/σ INCLUSION RULE v1.2 (tightened, T3 run 129): compute $/σ only if exit_reason ∈ {normal, trailing_stop, profit_lock} AND MFE>0 AND |Δz|≥0.5. Coint-failure exits (cointegration_lost, cointegration_watch_timeout) go to the coint-failure tracker, NOT the $/σ table — regardless of z reversion. Mechanical, no per-trade judgment.
- success_criteria: $/σ sign-flip rate ≤ 10% over 20 normal-exit trades; cumulative PnL improvement vs equal-notional baseline
- sizing_mode: gross_normalized_beta (Option C confirmed via retroactive counterfactual — docs/audits/counterfactual_exp_coint_stability_v1.md)
- audit: docs/audits/exp_beta_aware_sizing_v1_per_run_audit.md (runs 125-139, T1-T12)
- run_128: 0 trades, operational event (OKX API outage + 77-min flatten loop), not experimental data
- run_129: T3 BNB/LINK, β=0.378, gross=$200 verified to the cent, exit=cointegration_watch_timeout, gross position_pnl -$0.137 (costs textbook 1.0×), RISK_OFF vol_shock flip ~50s post-entry. Ended via max_session_trades=1.
- run_130: T4 DOGE/AAVE, β=0.760, gross=$200 to the cent, exit=cointegration_lost, gross position_pnl -$0.110 (costs textbook 1.0×), MFE -$0.103 never positive despite z reverting -2.20→-0.10 into exit zone (guard blocked full_tp 23×). Patch 4.1 TREND block fired correctly on ASTER/SOL. Ended via max_session_trades=1.
- run_131: T5 AVAX/DOT, β=0.659, gross=$200 to the cent. 2nd $/σ-ELIGIBLE trade (normal/profit_lock exit, MFE +$0.187>0, Δz=4.00). $/σ=+$0.017 POSITIVE (sign-flip now 0/2). Gross position_pnl +$0.069 (positive) but net -$0.030 (costs ~$0.10). Query 1 finding: pnl_at_mean +$0.052 < costs (MFE was overshoot, not thesis-capturable). First profit-lock activation; floor below cost-clearance. Coint held. Ended via max_session_trades=1.
- run_132: T6 SOL/AVAX, β=0.911 (first near-unity). gross=$200 to the cent (6/6 exact). 3rd $/σ-ELIGIBLE (normal/profit_lock, MFE +$0.179>0, Δz=3.26). $/σ=+$0.020 POSITIVE (sign-flip 0/3). Gross +$0.065 (worked) but net -$0.1285 (costs $0.194). pnl_at_mean +$0.026, in-zone max PnL +$0.0067 — profit at overshoot. 2nd profit-lock activation, below cost-clearance. Coint held. Ended via max_session_trades=1.
- run_134: T7 SOL/CRV, β=0.8865 (8/8 exact). 4th $/σ-ELIGIBLE, FIRST WIN. entry_z=-2.78 (deepest), exit_z=-0.34, hold 1.1 min (fastest). Gross +$0.230 = MFE (exited AT peak, at zone edge z=-0.34); guard blocked 0× (in-zone PnL above floor → full_tp fired). Net +$0.0153, edge cleared costs ($0.215). $/σ=+$0.094 (highest). pnl_at_mean > cost: YES. Deep entry → big reversion → in-zone edge cleared. Ended via max_session_trades=1.
- run_135: T8 BCH/ETC, β=0.8633 (8/8 exact). 5th $/σ-ELIGIBLE. entry_z=+2.17, exit_z=-0.12, hold 9.6 min. Gross +$0.124, net -$0.035 (costs $0.159). KEY: pnl_at_mean +$0.169 (at z=-0.05) > cost $0.159 — thesis-mean edge CLEARED, but exit held past mean into overshoot (z=-0.60, +$0.282) and gave it back → genuine EXIT-TOO-LATE (mean-disciplined exit would have won). $/σ=+$0.054. Ended via max_session_trades=1.
- run_136: T9 AVAX/CRV, β=0.7649 (9/9 exact). COINT-FAILURE (cointegration_watch_timeout, excluded from $/σ). entry_z=+2.20 → exit_z=-0.50, hold 25.7 min. **Entered with regime=RISK_OFF — shadow router did not block** (vector flagged with T3's pre-entry-flip case for structural-review). Gross +$0.006, net -$0.107 (costs $0.113 textbook). pnl_at_mean -$0.015 at z=-0.0006 → **β-sized DECOUPLED** (3rd clean DECOUPLED with T3b/T4b — mean-shift signature strengthens). Benign entry slope +0.000826 (refuted-lever guardrail intact). Ended via max_session_trades=1.
- run_137: T10 AVAX/ETC, β=0.4902 (10/10 exact). NEW SHAPE: "normal" exit with MFE<0. entry_z=-2.08 → exit_z=-3.73 (z DIVERGED). Hold 35 SECONDS, MFE never positive (-$0.138), exited AT MAE. Gross -$0.249, net -$0.405 (costs $0.156 textbook). 1 snapshot only. NEITHER $/σ-eligible NOR coint-failure (adverse-normal exit, new bucket n=1). Mechanism in coarse "normal" label may be stop-tier; flag if recurs.
- run_138: T11 AVAX/ETC, β=0.4571 (11/11 exact). COINT-FAILURE (cointegration_lost). **SAME PAIR as T10, ~35 min after T10 loss** — pair-re-selection observation (new deferred item: recently-failed-pair cooldown). entry_z=+2.02 (opposite side), exit_z=+1.40 (partial revert, didn't reach zone). 10 snapshots, all PnL negative. pnl_at_mean -$0.34 at z=1.40 → **DECOUPLED** (β-sized clean). Gross -$0.441, net -$0.563 (costs $0.122). Benign entry slope -$0.000390.
- run_139: T12 ARB/OP, β=0.6553 (12/12 exact). COINT-FAILURE + **RISK_OFF entry (2nd vector case after T9)** + **RECON FAIL** (unexplained -$0.196). entry_z=+2.35 → exit_z=+1.45, hold 14.5 min. Brief overshoot through 0 to z=-0.53 (MFE +$0.078 there); pnl_at_mean +$0.011 at z=0.89 → **TRACKED-THEN-BROKE (borderline)**. Gross -$0.509, net -$0.845 (costs **$0.336 = 2.4× model** — first elevated-cost trade in window; ARB/OP under RISK_OFF execution). Benign entry slope -$0.000825. RISK_OFF-entry vector now 2/2 → coint-failure.
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
