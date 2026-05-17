# OKXStatBot Guard Floor Calibration Apply Plan v1.0

## Recommended Naming

Use clearer names instead of "Patch 2" and "Patch 3":

```txt
Old name: Patch 2
Better name: Guard Floor Cost Calibration Audit
Short name: Cost Calibration Audit
Purpose: Measure true execution cost from real fills. Read-only.

Old name: Patch 3
Better name: Guard Floor Calibration Apply Plan
Short name: Guard Floor Apply Plan
Purpose: Apply measured cost floors to bot config/logic after enough data.
```

Recommended file names:

```txt
OKXSTATBOT_GUARD_FLOOR_COST_CALIBRATION_AUDIT_V1_1.md
OKXSTATBOT_GUARD_FLOOR_CALIBRATION_APPLY_PLAN_V1_0.md
```

---

# Purpose

This document defines the **apply phase** after the Guard Floor Cost Calibration Audit is complete.

The goal is to safely apply empirically measured execution-cost floors to OKXStatBot's exit guard system.

This plan must only be used after the audit produces:

```txt
recommended_guard_floor_usdt
confidence = MEDIUM or HIGH
apply_now = true
```

If the audit confidence is LOW, this apply plan must not be executed.

---

# Required Pre-Conditions

Do not proceed unless all are true:

```txt
✅ At least 20–30 controlled closed trades collected
✅ True round-trip cost measured or estimated per trade
✅ Slippage source labeled clearly
✅ Mark-to-fill delta reviewed
✅ Reconciliation issues resolved or explained
✅ Entry viability assessed
✅ Audit confidence is MEDIUM or HIGH
✅ apply_now = true
✅ Current bot is stable at 200 USDT notional
✅ No unresolved leg_desync / emergency_flatten_not_flat / orphan position issue
```

If any item fails:

```txt
Stop. Do not apply calibrated floors yet.
Continue controlled runs and data collection.
```

---

# What This Plan Applies

The Cost Calibration Audit may produce several recommended values:

```txt
recommended_full_tp_guard_floor_usdt
recommended_partial_tp_guard_floor_usdt
recommended_trailing_stop_guard_floor_usdt

recommended_fee_rate_assumed
recommended_slippage_rate_assumed

recommended_full_tp_guard_multiplier
recommended_partial_tp_guard_multiplier
recommended_trailing_stop_guard_multiplier
```

This apply plan decides how to introduce those values safely.

---

# Core Principle

Do not replace multiple systems at once.

Apply changes in this order:

```txt
1. Add config support for absolute guard floors, disabled by default.
2. Wire absolute floors into diagnostics only.
3. Enable absolute floor for full TP only at 200 USDT.
4. Compare against previous multiplier behavior.
5. Add partial/trailing floors only if data supports them.
6. Keep entry safety gate and circuit breaker unchanged.
```

---

# Design Option A — Preferred: Absolute Guard Floors

The cleanest long-term design is to support explicit USDT floors.

Add config keys:

```env
STATBOT_FULL_TP_GUARD_FLOOR_USDT=
STATBOT_PARTIAL_TP_GUARD_FLOOR_USDT=
STATBOT_TRAILING_STOP_GUARD_FLOOR_USDT=
```

Behavior:

```txt
If explicit guard floor is set:
    effective_guard_floor = explicit_guard_floor

Else:
    effective_guard_floor = base_min_profit_usdt × guard_multiplier
```

This preserves current behavior when the new config keys are unset.

Example:

```env
STATBOT_FULL_TP_GUARD_FLOOR_USDT=0.19
STATBOT_PARTIAL_TP_GUARD_FLOOR_USDT=
STATBOT_TRAILING_STOP_GUARD_FLOOR_USDT=
```

Meaning:

```txt
Full take-profit uses calibrated absolute floor.
Partial and trailing stop continue using existing multiplier logic.
```

---

# Design Option B — Fallback: Adjust Multipliers Only

If absolute floors are too invasive for now, apply only new multipliers.

Example:

```env
STATBOT_FULL_TP_GUARD_MULTIPLIER=0.82
STATBOT_PARTIAL_TP_GUARD_MULTIPLIER=1.0
STATBOT_TRAILING_STOP_GUARD_MULTIPLIER=1.1
```

This is simpler, but weaker because it still depends on the correctness of the base guard estimate.

Use this only if:

```txt
- absolute floors require too much code change
- audit confidence is not high enough for hard floor replacement
- you want a reversible config-only experiment
```

---

# Recommended Implementation Path

## Phase A — Config Support Only

Goal:

```txt
Add explicit guard floor config keys but leave them unset.
```

Tasks:

```txt
1. Add config parsing for:
   STATBOT_FULL_TP_GUARD_FLOOR_USDT
   STATBOT_PARTIAL_TP_GUARD_FLOOR_USDT
   STATBOT_TRAILING_STOP_GUARD_FLOOR_USDT

2. Include these values in config_snapshot.json.

3. Do not change behavior when values are empty/null.

4. Add tests proving default behavior is unchanged.
```

Expected default:

```json
"exit_guards": {
  "full_tp_guard_floor_usdt": null,
  "partial_tp_guard_floor_usdt": null,
  "trailing_stop_guard_floor_usdt": null
}
```

---

## Phase B — Guard Selection Logic

Goal:

```txt
Use explicit floor only when configured.
```

Effective guard selection:

```python
def resolve_effective_guard_floor(
    exit_type: str,
    base_min_profit_usdt: float,
    multiplier: float,
    explicit_floor_usdt: float | None,
) -> float:
    if explicit_floor_usdt is not None:
        return explicit_floor_usdt
    return base_min_profit_usdt * multiplier
```

Apply to:

```txt
full take-profit
partial profit
trailing stop
pnl_profit_lock activation threshold if it depends on the full TP effective floor
exit decision trace diagnostics
ExitOrchestrator guard checks
```

Do not apply to:

```txt
entry logic
order execution
pair selection
ML rollout
router behavior
hedge-ratio sizing
```

---

## Phase C — Diagnostics

Add trace/report fields:

```txt
guard_floor_source = explicit_floor | multiplier_formula
base_min_profit_usdt
guard_multiplier
explicit_guard_floor_usdt
effective_min_profit_usdt
exit_type
```

Update:

```txt
exit_decision_trace.csv
exit_decision_summary.csv
trade_closes.csv if useful
config_snapshot.json
```

This makes it clear whether an exit used the old multiplier formula or the new calibrated explicit floor.

---

## Phase D — Controlled Runtime Test

Only after tests pass, enable full TP floor first.

Example controlled config:

```env
STATBOT_TRADEABLE_CAPITAL_USDT=200

STATBOT_FULL_TP_GUARD_FLOOR_USDT=0.19
STATBOT_PARTIAL_TP_GUARD_FLOOR_USDT=
STATBOT_TRAILING_STOP_GUARD_FLOOR_USDT=

STATBOT_FULL_TP_GUARD_MULTIPLIER=0.75
STATBOT_PARTIAL_TP_GUARD_MULTIPLIER=1.0
STATBOT_TRAILING_STOP_GUARD_MULTIPLIER=1.0

STATBOT_PNL_PROFIT_LOCK_ENABLED=true
STATBOT_MEAN_REVERSION_ESCAPE_ENABLED=false

STATBOT_ENTRY_SAFETY_GATE_ENABLED=true
STATBOT_ENTRY_GATE_MAX_BREAK_RISK=0.12

STATBOT_RISK_CIRCUIT_BREAKER_STATE_MODE=session
STATBOT_SESSION_MAX_LOSS_USDT=5.0
STATBOT_MAX_CONSECUTIVE_LOSSES=3
STATBOT_MAX_DRAWDOWN_USDT=10.0

STATBOT_REGIME_ROUTER_MODE=shadow
STATBOT_STRATEGY_ROUTER_MODE=shadow

STATBOT_ADVANCED_ML_ENABLED=0
STATBOT_ADVANCED_ML_SHADOW_MODE=1
STATBOT_ADVANCED_ML_ROLLOUT_LIVE_TRADE_PERCENTAGE=0.0
```

Important:

```txt
Only one calibrated floor should be enabled first:
FULL TP only.
```

Do not enable partial and trailing stop floors in the same first run.

---

# Validation Metrics After Apply

After 10–20 trades using the applied floor, audit:

```txt
full_tp_selected_count
full_tp_guard_block_count
guard_floor_source distribution
average win
average loss
profit factor
MFE vs final PnL
trades with MFE > floor but final loss
reconciliation failures
cointegration_lost/watch_timeout exits
circuit breaker activation
```

Success signs:

```txt
✅ full TP selected more often when MFE clears measured cost
✅ no increase in fake tiny wins
✅ average win improves
✅ average loss does not worsen
✅ profit factor improves
✅ reconciliation remains clean
✅ circuit breaker does not trigger quickly
```

Failure signs:

```txt
❌ exits happen too early with near-zero or negative net PnL
❌ full TP selected but equity change is still negative
❌ reconciliation gaps increase
❌ average win remains tiny
❌ average loss worsens
❌ profit factor stays near zero
```

---

# Rollback Plan

If applied floor worsens performance:

```txt
1. Remove/blank explicit floor env keys.
2. Revert to existing multiplier behavior.
3. Keep diagnostics fields.
4. Do not change other systems until audit is complete.
```

Rollback config:

```env
STATBOT_FULL_TP_GUARD_FLOOR_USDT=
STATBOT_PARTIAL_TP_GUARD_FLOOR_USDT=
STATBOT_TRAILING_STOP_GUARD_FLOOR_USDT=
```

The bot should then return to:

```txt
effective_guard_floor = base_min_profit_usdt × guard_multiplier
```

---

# Tests Required

Add/update tests for:

```txt
1. explicit full TP floor overrides multiplier formula
2. unset full TP floor preserves multiplier formula
3. explicit partial floor affects only partial profit
4. explicit trailing floor affects only trailing stop
5. explicit full TP floor propagates to ExitOrchestrator
6. PnL profit-lock activation uses the correct effective full TP floor
7. exit_decision_trace records guard_floor_source
8. config_snapshot includes explicit floor values
9. rollback with unset floor restores old behavior
10. no order execution behavior changed
11. no entry logic changed
12. no ML rollout/router behavior changed
```

Run:

```bash
python -m compileall Execution core Platform
pytest Execution/tests/test_advanced_trade_management_net_profit.py -q
pytest tests/test_exit_decision_trace.py -q
pytest tests/test_exit_orchestrator.py -q
pytest tests -q
```

Do not enable:

```txt
RUN_EXCHANGE_TESTS
```

---

# Codex Implementation Prompt

Use this only after the Cost Calibration Audit says `apply_now=true`.

```txt
You are working on OKXStatBot.

Task:
Implement Guard Floor Calibration Apply Plan v1.0.

Important:
Proceed only if the guard floor audit produced:
- confidence = MEDIUM or HIGH
- apply_now = true
- recommended full TP guard floor exists

Do not change trading strategy logic beyond guard floor selection.
Do not modify order execution.
Do not modify entry signals.
Do not modify pair selection.
Do not modify ML rollout/router behavior.
Do not scale notional.

Goal:
Add explicit optional USDT guard floors for exit types while preserving current default behavior.

Add config keys:
- STATBOT_FULL_TP_GUARD_FLOOR_USDT
- STATBOT_PARTIAL_TP_GUARD_FLOOR_USDT
- STATBOT_TRAILING_STOP_GUARD_FLOOR_USDT

Behavior:
- If explicit floor is set, use it as effective guard floor for that exit type.
- If unset/null/blank, preserve current formula:
  base_min_profit_usdt × guard_multiplier

Apply to:
- AdvancedTradeManager guard calculations
- ExitOrchestrator guard calculations
- PnL profit-lock activation threshold if based on effective full TP floor
- exit decision trace diagnostics
- config_snapshot.json

Add diagnostics:
- guard_floor_source
- explicit_guard_floor_usdt
- effective_min_profit_usdt
- base_min_profit_usdt
- guard_multiplier

Do not enable partial/trailing floors by default.
Do not change defaults.

Tests:
- explicit floor overrides multiplier only for matching exit type
- unset floor preserves old behavior
- orchestrator uses explicit floor from candidate
- trace records guard_floor_source
- config snapshot includes new fields
- no order execution behavior changed

Run:
python -m compileall Execution core Platform
pytest Execution/tests/test_advanced_trade_management_net_profit.py -q
pytest tests/test_exit_decision_trace.py -q
pytest tests/test_exit_orchestrator.py -q
pytest tests -q

Do not enable RUN_EXCHANGE_TESTS.
```

---

# Decision Rules

Proceed with this apply plan only if the Cost Calibration Audit says:

```txt
confidence = MEDIUM or HIGH
apply_now = true
```

Do not proceed if:

```txt
sample_size < 20
confidence = LOW
reconciliation issue unresolved
true cost cannot be estimated reliably
slippage source is unavailable for most trades
bot is not stable at 200 USDT
```

---

# Completion Checklist

```txt
✅ explicit guard floor config keys added
✅ defaults preserve existing multiplier behavior
✅ full TP explicit floor can be enabled independently
✅ partial/trailing floors remain optional
✅ ExitOrchestrator aligned with explicit floor
✅ PnL profit lock uses correct effective floor
✅ trace/report shows floor source
✅ config_snapshot shows explicit floor values
✅ tests pass
✅ controlled run completed at 200 USDT
✅ no order execution changed
✅ no entry logic changed
✅ rollback is simple by blanking env keys
```
