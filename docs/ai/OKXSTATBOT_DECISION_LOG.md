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

Patch 6 — Emergency Flatten Safety (run 99+, 2026-05-20):
- Type: Operational safety fix. No strategy or config changes.
- Evidence: run_98 OKX 50001 outage (09:15:11–09:19:29 UTC). ~20 outer retry cycles fired in 4m18s with no delay between them. Spread moved 1.77 sigma adverse. Exit intent (hard exit, priority=90) lost after clear_entry_tracking() called inside close_all_positions.
- Item 1 — Exponential backoff retry policy:
  After first failed outer flatten cycle: 5s wait.
  After second: 30s. After third: 120s. After fourth and beyond: 300s (capped).
  Inner cycle (3 retries × ~1s poll) unchanged.
  Cycle count and elapsed outage time logged at CRITICAL on each failure.
  Files: main_execution.py (_FLATTEN_BACKOFF_SCHEDULE, _flatten_backoff_delay, kill_switch==2 block).
- Item 2 — Persist hard-exit intent across retry cycles:
  When EXIT_ORCHESTRATOR issues a full_exit with category=HARD, intent is stored in-memory via set_pending_hard_exit().
  If the bot later enters the "restart scenario" branch (entry_z is None), it checks get_pending_hard_exit() and adds a HARD exit candidate restoring the original priority. This prevents the exit decision from downgrading to mean-reversion-only when the entry context is lost mid-outage.
  Cleared only when close_account_positions_and_confirm() confirms flat.
  Known limitation: pending_hard_exit is in-memory only. A subprocess restart (exit code 3) during the retry window clears it; on next startup the bot reverts to mean-reversion-only exit mode. File-based persistence is a future enhancement (Patch 7 candidate if this scenario occurs).
  Files: func_pair_state.py (set/get/clear_pending_hard_exit), func_trade_management.py (_apply_exit_orchestrator_decision + restart scenario branch), main_execution.py (clear on success).
- Tests: 12 new tests in test_patch6_flatten_safety.py covering backoff schedule values and intent persistence through clear_entry_tracking().
- Trade counter at fix: 5/20. No new trades during investigation.
- Deferred (not in this patch): EMERGENCY_FLATTEN_FLAT partial-fill telemetry label (item 3), provisional PnL recorded as final (item 4), alert/kill-switch after N consecutive failures (item 5 — needs design).

Structural Review — exp_guard050_ethfi_excluded_v1 (20-trade review, 2026-05-23):
- Verdict: B (Patch 5 inconclusive — no attributable wins, net contribution $0.00).
- Guard pass mechanism: 0.34% pass rate across ~881 TP-zone evaluations. Dead in production. Multiplier setting irrelevant.
- Profit-lock band mechanism: 5/5 winning trades had MFE > $0.230 old floor. Profit-lock would have activated under old config for all 5. 0 Patch-5-enabled wins.
- Coint fragility confirmed dominant: 7/19 trades (36.8%) ended in coint failure; $2.027 = 63.8% of all losses.
- Patch 5 retained: no evidence of cost; no evidence of benefit in this window. The floor reduction (0.230→0.170) was never the deciding factor on any trade.
- Process note — Verdict A→B correction: initial analysis computed old activation floor as $0.255 (derived as $0.34 TP-target × 0.75, omitting the additive buffer). Corrected to $0.230 after tracing _resolve_net_profit_exit_floor_usdt and _check_pnl_profit_lock in code. Formula is activation_floor = (min_profit_usdt × multiplier) + activation_buffer; with min_profit_usdt=$0.240 at $200 notional and buffer=$0.05, old floor = ($0.240 × 0.75) + $0.05 = $0.230. The correction inverted the headline conclusion (A→B). Lesson: verify load-bearing constants against code, not derivation.

Patch 7 — Forward-Looking Cointegration Stability Entry Filter (exp_coint_stability_v1, pending implementation):
- Hypothesis: pairs entering coint failure during hold can be identified at entry by evaluating whether the p-value trend is deteriorating over recent evaluations.
- Mechanism: entry gate evaluates slope of cointegration p-value over last N evaluations (default window=5). Rejects if slope exceeds threshold (default 0.020). Affects entry path only — no exit logic changes.
- New config: STATBOT_ENTRY_COINT_STABILITY_WINDOW (int, default 5), STATBOT_ENTRY_COINT_STABILITY_SLOPE_MAX (float, default 0.020).
- Parameter provenance: heuristic starting values, not data-derived. First 20 trades are a calibration window.
- Pre-committed adjustment rule: if gate fire rate <15% of entries, loosen to slope_max=0.030; if >60%, tighten to slope_max=0.012. Re-run 20 trades before evaluating coint-failure-rate effect.
- Success criteria: coint-failure rate ≤ 25% over next 20 trades; coint-exit losses ≤ $1.50.
- Null criteria: coint-failure rate ≥ 30%, OR gate fires < 3 times total.
- Shadow counter required: add coint_stability_check_evaluated_count to entry_gate_component_scores in entry_rejections.csv. Increments every time an entry attempt reaches the coint-stability check regardless of whether it fires. Distinguishes "gate didn't fire because pairs were stable" from "gate never reached because an earlier gate rejected first" — the Patch 4.1 blind-spot applied to calibration. If evaluated_count = 0 after 20 trades, gate is unreachable, not just inactive.
- Files: Execution/entry_safety_gate.py, Execution/func_trade_management.py.
- Tests required: 3 — reject rising p-value trend exceeding slope threshold; pass stable p-value; pass improving (decreasing) p-value.
- Pre-run blockers: (1) Patch 7 implementation + shadow counter + tests; (2) CURRENT_STATE.md updated.

HMSTR-USDT-SWAP added to graveyard (2026-05-23):
- Reason: high_execution_cost_meme_token, permanent.
- Evidence: run_102 T1 unexplained -$0.226 (161% of $0.070 position gain). Total execution cost ~$0.366 vs standard estimate $0.14 (2.6×). pnl_source_mismatch confirmed: equity_delta MFE $0.203 vs position_snapshot $0.370 at MFE peak — entry costs depressed the equity_delta by $0.167, causing profit_lock to fire at a distorted PnL level.
- Caveat: single occurrence. Standard threshold for graveyard is pattern-based (multiple occurrences). Exception justified by magnitude (161% of gain) and structural meme-token argument (structurally wide bid-ask spreads economically incompatible with stat-arb at $200 notional). Not a pattern-based exclusion — flag if needed to revisit in future review.

Patch 7.1 — Monitoring-Loop Buffer Population for Coint Stability Gate (2026-05-24):
- Root cause confirmed: ring buffer in entry_safety_gate._PAIR_COINT_PVALUE_HISTORY fills only on entry-signal gate calls, not monitoring ticks. Pairs with sparse z-crossings cannot accumulate 5 samples regardless of watch time. T4 (run_109, BCH/CRCL): 72 min watch, only 4/5 samples accumulated by entry.
- Evidence for early application: evaluated_trade_count=1 after 4 closed trades. Gate-inactivity trigger at MONITORING (3/6 gate-reaching trades). Early application justified because root cause is mechanistically confirmed (not statistical noise), the fix is staged, and continuing collects predictably-wasted trades.
- Fix: export record_entry_coint_pvalue() from entry_safety_gate.py. Call it in main_execution.py main loop every monitoring cycle when no position is open (is_manage_new_trades=True) and p_value < 1.0. The 60s min_sample_interval gate inside record_entry_coint_pvalue ensures buffer contents are identical to what the gate records — rapid monitoring-loop calls (every ~3-5s) do not produce sub-interval samples.
- Verified: (1) same p_value computation — monitoring loop and gate both use metrics["p_value"] from get_latest_zscore(); (2) interval gate applies in monitoring path via same logic as gate's internal writes; (3) pair key alignment — monitoring path uses f"{signal_positive_ticker}/{signal_negative_ticker}" matching _active_pair_key() in func_trade_management.py.
- Files: Execution/entry_safety_gate.py (record_entry_coint_pvalue function + __all__), Execution/main_execution.py (import + call after metrics fetch), Execution/tests/test_entry_safety_gate.py (2 new tests).
- Tests: test_record_entry_coint_pvalue_enables_gate_evaluation (buffer pre-populated → evaluated_count=1 on first gate call), test_record_entry_coint_pvalue_respects_sample_interval (rapid calls don't bypass 60s interval gate).
- Calibration window restarted at T=0 after T4. Prior T1–T4 trades discarded for gate-effectiveness purposes (evaluated_trade_count was 1/4).
- Trade counter: 4 closed trades in exp_coint_stability_v1 window (not reset — used as context, not experiment N).

Patch 7.2 — entry_coint_stability_slope exposed in trade_closes.csv (2026-05-27):
- Patch 7.1 logged slope to bot log only. Patch 7.2 adds it to the trade_close event payload so it appears in trade_closes.csv.
- Files: main_execution.py (attach entry_gate_components to trade_close payload), report generator (consume new field).

Beta-Aware Sizing — exp_beta_aware_sizing_v1 (2026-05-28):
- Type: Architecture patch
- Evidence: exp_coint_stability_v1 structural review (2026-05-28) confirmed sizing mismatch (Verdict 10A CONFIRMED). OLS hedge ratio β is computed at every entry by evaluate_cointegration() and stored in metrics["hedge_ratio"], but func_trade_management.py sizes both legs at equal dollar notional regardless of β. Retroactive counterfactual on T5–T14: β range [0.471, 1.433] (wide), cumulative δ (PnL_β − PnL_equal) = +$0.988. Option C (gross-normalized-beta) confirmed via Input 2 (wide β distribution). See docs/audits/counterfactual_exp_coint_stability_v1.md.
- Decision: Option C — gross-normalized-beta sizing. Gross conserved at $200 total. Leg sizes: leg1 = gross/(1+β), leg2 = gross×β/(1+β). inst_1 = signal_negative_ticker, inst_2 = signal_positive_ticker.
- Implementation: β-sizing applied AFTER liquidity selection (initial_capital_usdt = selected_target_usdt). gross = initial_capital_usdt × 2. β taken from metrics["hedge_ratio"]. Validated with min=0.20, max=5.00 bounds. If invalid β: fallback to equal-notional. Both preflight and actual order calls use the β-sized capital per leg. remaining_capital_long/short updated to β-sized values.
- hedge_ratio added to entry_gate_component_scores unconditionally (Day 1 telemetry).
- New config: STATBOT_HEDGE_RATIO_SIZING_ENABLED=true, STATBOT_MIN_HEDGE_RATIO=0.20, STATBOT_MAX_HEDGE_RATIO=5.00.
- Files: Execution/config_execution_api.py (3 new vars), Execution/entry_safety_gate.py (hedge_ratio in component_scores), Execution/func_trade_management.py (β-sizing block + order loop), Execution/tests/test_beta_sizing.py (8 new tests).
- Tests: 8 new tests (β>1 gross conservation, β<1 leg sizes, β=1 equal-notional, boundary values, out-of-bounds rejection).
- Experiment: exp_beta_aware_sizing_v1, trade counter reset to 0. No new trades under equal-notional sizing.

Operational Finding — Run 128 sustained-API-outage flatten loop (2026-05-28):
- Type: Operational gap (no code bug, but aggregate behavior unacceptable).
- Occurrence: Second occurrence of run-98-class sustained API outage (first: run 98, ~4m18s; second: run 128, ~77 minutes).
- What happened: OKX fetch-all-open-orders API began timing out at 18:10 UTC. Bot could not verify account exposure was zero, correctly deferred pair switch (fail-closed), and triggered emergency flatten to clear any potential open position. Flatten routine needed the same timed-out API. Retry cycles 1–14 fired over 77 minutes (5.5 min/cycle average — Patch 6 backoff working as designed, capped at 300s), each failing identically. Manual stop required at 19:35 UTC.
- Backoff confirmed working: 14 cycles × ~5.5 min/cycle ≈ 77 min, consistent with 300s ceiling applied from cycle 4 onward. Backoff slowed retries correctly — it just had no terminal state.
- No position open: run 128 closed with 0 trades, starting equity = ending equity = $2,653.76. Emergency flatten was precautionary under untrusted account state, not due to a real open position.
- Gap identified: Patch 6 exponential backoff was designed for transient outages (API recovers within minutes). It has no terminal state for sustained outages — after N failed cycles at the 300s ceiling, the correct action is to alert and halt cleanly rather than loop indefinitely. This requires manual intervention today.
- This confirms the deferred item: Patch 6 item 5 (alert/kill-switch after N consecutive flatten failures) was scoped and explicitly deferred at implementation time ("needs design"). Run 128 is the second occurrence confirming the need.
- Elevated priority: Patch 6 item 5 elevated from "deferred, needs design" to NEXT OPERATIONAL PRIORITY. Must be implemented before any move toward live trading.
- Experiment impact: 0 trades entered in run 128. No experiment data. Counter stays at 2/20. Run classified as operational event, not experimental event.
- Phase 1 note: ACT/NOT had 19 entry signals (Z +2.0–+2.8) blocked by advanced_ml_break_risk_high (break_risk=0.150 > cap=0.120) and liquidity_at_floor (NOT depth ~$39–46 USDT, forcing 5× downsize). Both gates correct. Not-enough-signal run: this is a "gate correctly refused thin/high-break-risk pairs" run, not a "no signal" run. Thin pair access is a pair-universe-quality observation for structural review.
