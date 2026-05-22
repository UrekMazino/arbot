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
