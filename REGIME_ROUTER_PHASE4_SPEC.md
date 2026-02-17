# Regime Router Phase 4 Spec (Adaptive Strategy Quality Loop)

Date: 2026-02-17  
Status: Deferred execution queue (moved under V2 roadmap)

Queue note:

1. Phase 4 remains the technical reference for pending engine work.
2. Active implementation order is now tracked in `V2_ROADMAP.md`.
3. V2 priority is UI-first, then deferred Phase 4 workstreams.

## 1. Objective

Phase 4 converts the current regime/strategy routing into a measurable and self-protecting system.

Primary goals:

1. Improve confidence in strategy attribution (what strategy made/lost money).
2. Reduce low-quality TREND entries without increasing pair-switch churn.
3. Add safety controls that temporarily throttle bad strategy behavior before account-level damage.

## 2. Current Baseline (From Phase 3)

Already in runtime:

1. Regime router (`off|shadow|active`) with gate + policy overrides.
2. Strategy router (`off|shadow|active`) with:
- `RANGE -> STATARB_MR`
- `TREND -> TREND_SPREAD`
- `RISK_OFF -> DEFENSIVE`
3. Cointegration gate and mean-shift gate (TREND) for entry blocking.
4. Hybrid exit stack + ATM.
5. Notional-based hard-stop option and risk-off coint early exit.
6. Post-close realized PnL classification and improved reconciliation warnings (post-close based).

Known gaps:

1. No first-class per-strategy trade attribution in reports.
2. TREND entry logic still shares the generic entry signal path (parameterized, not fully strategy-specific).
3. Directional filter remains experimental and not validated.
4. No performance-driven cooldown for underperforming strategy mode.

## 3. Phase 4 Scope

## 3.1 In Scope

1. Strategy-level trade attribution and metrics.
2. Strategy guardrails based on rolling performance.
3. TREND signal-quality upgrades:
- regime-aware z-score lookback (adaptive mean handling),
- optional directional filter with shadow-first rollout.
4. Strategy-specific exit profile overrides for ATM.
5. Strategy metrics in `report_generator` outputs and run summaries.

## 3.2 Out of Scope

1. Single-leg directional trading engine.
2. Exchange adapter redesign.
3. Pair-universe selection redesign.
4. Forced pair switch purely due to strategy underperformance.
5. Explicit regime-anchored mean recalibration (`range_mean` / `trend_mean` persistent anchors).

## 4. Design Principles

1. No forced close only because strategy changed.
2. No pair switch only because strategy changed.
3. Strategy safety actions affect new entries first.
4. Shadow-first for any new gate/filter.
5. Reportability is mandatory for every new control.

## 5. Workstreams

## 5.1 Workstream A: Strategy Attribution (Foundation)

Purpose: Make strategy performance measurable and auditable.

### Changes

1. Persist entry strategy context per open trade:
- add to `Execution/state/pair_strategy_state.json` (pair-local only):
  - `entry_strategy`
  - `entry_regime`
  - `entry_policy_snapshot` (entry_z, persist, size_mult)
  - `entry_ts`

2. On trade close, record strategy-level result:
- strategy name
- realized PnL (post-close equity delta source of truth)
- hold minutes
- exit reason

3. Extend `Execution/state/strategy_state.json` with rolling strategy performance:
- cumulative and rolling (for example last 20 trades) stats by strategy.

### File Mapping

1. `Execution/func_pair_state.py`
2. `Execution/func_strategy_state.py`
3. `Execution/main_execution.py`
4. `Execution/func_trade_management.py`

### Required Logs

1. `STRATEGY_TRADE_OPEN: strategy=... regime=... entry_z=... size_mult=...`
2. `STRATEGY_TRADE_CLOSE: strategy=... pnl=... hold_min=... exit_reason=...`

## 5.2 Workstream B: Strategy Safety Controller

Purpose: Prevent repeated low-quality entries from one strategy profile.

### Behavior

1. Maintain rolling strategy stats (example window: 20 trades).
2. If strategy underperforms minimum thresholds, enter strategy cooldown:
- block new entries for that strategy for N minutes,
- route remains intact, but `allow_new_entries=False` when cooldown active.
3. Emit explicit reason codes and logs.

### Suggested default logic (v1)

1. Minimum trades before evaluation: 8
2. Cooldown trigger if either:
- rolling win-rate < 35%
- rolling pnl_usdt < -X (env)
3. Cooldown duration: 60 minutes

### File Mapping

1. `Execution/strategy_router.py`
2. `Execution/func_strategy_state.py`
3. `Execution/main_execution.py`

### Required Logs

1. `STRATEGY_COOLDOWN_ON: strategy=... reason=... until_ts=...`
2. `STRATEGY_COOLDOWN_OFF: strategy=...`

## 5.3 Workstream C: TREND Signal Quality

Purpose: Reduce TREND false positives caused by equilibrium drift.

### C1. Regime-aware z-score lookback (Phase 4 required)

1. Use shorter lookback for TREND evaluation path (adaptive mean handling):
- `RANGE`: existing baseline window (current behavior)
- `TREND`: shorter window (env-configurable)
2. This changes entry qualification only; no forced changes to exit stack.
3. Scope guard: keep this stateless for Phase 4.
- Do not persist regime-specific mean anchors.
- Do not replace exit targets with anchor-based targets.

Implementation note:

1. Add spread history export from `func_get_zscore.py` metrics.
2. Use spread-based calculations first, z-score fallback only when spread unavailable.

### C2. Directional filter (Phase 4 shadow-first)

1. Default mode: shadow only.
2. In shadow mode: log whether entry would be blocked.
3. Promote to active only after evidence from report metrics.

### File Mapping

1. `Execution/func_get_zscore.py`
2. `Execution/strategy_router.py`
3. `Execution/func_trade_management.py`
4. `Execution/main_execution.py`

### Required Logs

1. `TREND_LOOKBACK_APPLIED: lookback=... regime=...`
2. `DIRECTIONAL_FILTER_SHADOW: strategy=TREND_SPREAD allow_new=... reason=...`
3. `DIRECTIONAL_FILTER_ACTIVE_BLOCK: strategy=TREND_SPREAD reason=...`

## 5.4 Workstream D: Strategy-Specific Exit Profile Overrides

Purpose: Align exit behavior with entry profile risk.

### Behavior

1. Apply strategy-specific ATM profile on open position:
- `STATARB_MR`: existing baseline profile
- `TREND_SPREAD`: shorter max hold, tighter trailing profile
2. Exit stack priority remains unchanged.

### File Mapping

1. `Execution/advanced_trade_management.py`
2. `Execution/func_trade_management.py`
3. `Execution/main_execution.py`

## 5.5 Workstream E: Reporting and Analytics

Purpose: Make Phase 4 decisions evidence-based.

### Add report outputs

1. `strategy_performance.csv`
2. `strategy_switches.csv`
3. `strategy_gates.csv`

### Extend `summary.json`

1. `strategy_trade_counts`
2. `strategy_pnl_usdt`
3. `strategy_win_rate_pct`
4. `strategy_cooldown_events`
5. `directional_filter_shadow_blocks`
6. `directional_filter_active_blocks`

### File Mapping

1. `Execution/report_generator.py`
2. `Reports/v1/index.json` writer path (existing index update flow)

## 6. Configuration Additions (`Execution/.env.example`)

```env
# Phase 4 - strategy attribution and cooldown
STATBOT_STRATEGY_SCORE_WINDOW_TRADES=20
STATBOT_STRATEGY_SCORE_MIN_TRADES=8
STATBOT_STRATEGY_SCORE_MIN_WIN_RATE=0.35
STATBOT_STRATEGY_SCORE_MAX_ROLLING_LOSS_USDT=20
STATBOT_STRATEGY_COOLDOWN_SECONDS=3600

# Phase 4 - TREND adaptive mean handling
STATBOT_TREND_Z_LOOKBACK=60
STATBOT_RANGE_Z_LOOKBACK=200

# Phase 4 - directional filter
STATBOT_STRATEGY_TREND_DIRECTIONAL_FILTER_MODE=shadow  # off | shadow | active
STATBOT_STRATEGY_TREND_DIRECTIONAL_FILTER_STRENGTH=1.0
```

Compatibility:

1. Defaults must preserve current behavior when unset.
2. Directional filter must remain non-blocking unless explicitly `active`.

## 7. Test Plan

## 7.1 Unit

1. `Execution/tests/test_strategy_router.py`:
- cooldown triggers/clears correctly
- cooldown blocks entries in active mode only
- directional filter shadow does not block entries
- directional filter active can block entries

2. `Execution/tests/test_strategy_state.py` (new):
- rolling strategy stats updates
- serialization/backward compatibility of state schema

## 7.2 Integration

1. `Execution/tests/test_strategy_integration.py` (new):
- strategy entry context persisted on open and consumed on close
- strategy trade close attribution uses realized PnL
- TREND lookback applied in TREND regime path

## 7.3 Regression

1. Existing:
- `Execution/tests/test_regime_router.py`
- `Execution/tests/test_manage_new_trades_sim.py`
- `Execution/tests/test_price_calls.py`

## 8. Rollout Plan

## Phase 4A (Observability Only, 2-3 days)

1. Ship Workstream A + E logs/reporting only.
2. No entry behavior changes.

Exit criteria:

1. Strategy trade attribution present for >= 95% of closed trades.
2. No runtime regressions.

## Phase 4B (Safety Controller, 3-5 days)

1. Enable strategy cooldown in shadow first, then active.
2. Verify no strategy-flapping or hidden trade starvation.

Exit criteria:

1. Cooldown logs are explainable.
2. No increase in emergency pair switches.

## Phase 4C (TREND Quality Upgrades, 5-7 days)

1. Enable TREND adaptive lookback.
2. Run directional filter in shadow for evidence.
3. Promote directional filter to active only if shadow metrics support it.

Exit criteria:

1. Lower TREND false-entry rate.
2. Stable or improved realized PnL per TREND trade.

## 8.1 Archived For Now

1. Explicit Mean Recalibration on Regime Change (stateful `range_mean`/`trend_mean` anchors) is archived for now.
2. Revisit only after Phase 4 evidence is stable for:
- strategy attribution quality,
- strategy cooldown behavior,
- TREND adaptive lookback performance.

## 9. Acceptance Criteria

Phase 4 is complete when:

1. Every trade close can be attributed to a strategy in logs and reports.
2. Strategy cooldowns work and are visible in state + logs.
3. TREND adaptive lookback is active and test-covered.
4. Directional filter supports off/shadow/active with clear logs.
5. Strategy metrics are included in report artifacts and summary.
6. No regression in kill-switch, pair-switch, and reconciliation behavior.

## 10. Suggested Commit Sequence

1. `feat(strategy-state): add strategy trade attribution and rolling metrics`
2. `feat(execution): persist entry strategy context and close-time attribution logs`
3. `feat(strategy-router): add strategy cooldown controller`
4. `feat(signal): add TREND regime-aware lookback and directional-filter shadow mode`
5. `feat(exit): add strategy-specific ATM profile overrides`
6. `feat(reporting): add strategy performance/gate artifacts`
7. `test: add phase4 unit/integration coverage`
8. `docs: update BOT_DOCUMENTATION and README for phase4`
