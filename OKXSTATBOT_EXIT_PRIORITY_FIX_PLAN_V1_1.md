# OKXStatBot Exit Priority Fix Plan v1.1

## Purpose

This document defines a small, targeted fix for the advanced trade-management exit priority logic.

The current issue appears to be that **partial-profit exit can be selected before full take-profit**, even when the spread/Z-score is already inside the full take-profit zone.

That can cause the bot to close only part of a profitable/reverted position, leaving the remaining position exposed. If the spread diverges again, the final trade can turn into a loss.

---

## v1.1 Update Summary

This v1.1 update incorporates the useful parts of Claude's review while keeping the implementation safe and controlled.

Added:

```txt
1. Stronger validation that the full-TP-before-partial-TP fix is correct.
2. Extra regression test:
   when Z crosses from partial-profit zone into full take-profit zone mid-trade,
   full TP must fire on the next evaluation.
3. Explicit separation between:
   Patch 1: exit priority ordering
   Patch 2: profit guard calibration audit
   Patch 3: possible guard tuning
4. Warning that leg_desync / stop-loss setup failure is a separate urgent execution-safety issue.
5. Clear instruction not to lower the profit guard in this first patch.
```

Key decision:

```txt
Do NOT combine exit priority fix and profit guard calibration in one patch.
```

Reason:

```txt
If priority ordering and guard calibration are changed together,
you cannot tell which change improved or worsened results.
```

---

## Current Finding

Recent read-only review found that the current drawdown is mostly realized, not just open-position mark-to-market.

### Current Snapshot

```txt
Current drawdown: -26.57 USDT
Current equity: about 2707.12 USDT
Realized PnL: -20.36 USDT
Win rate: 20%
Profit factor: 0.016
```

Risk alerts include:

```txt
6 consecutive losses
critical leg_desync from a stop-loss setup failure
multiple graveyard pair alerts
```

The profit factor is especially concerning.

A profit factor far below `1.0` means losses are dominating winners in aggregate. At around `0.016`, the bot is not just in a normal bad streak; the exit behavior should be treated as structurally suspicious until proven otherwise.

---

## Profit Exit Finding

The profit-exit logic is likely too conservative and also has a sequencing issue.

The net-profit guard requires roughly:

```txt
entry_notional * (fee_rate + slippage_rate) + buffer
```

For a `1500 USDT` pair, that is about:

```txt
~1.20 USDT
```

before soft profit exits are allowed.

Several trades touched mean-reversion / profit zones but did not clear that guard:

```txt
AAVE/ARB:
- hit Z 0.22
- max UPL +0.71
- guard floor ~0.95
- final PnL -5.33

ADA/SUSHI:
- hit Z 0.004
- max UPL +1.09
- guard floor ~1.14
- final PnL -0.24

BTC/XLM:
- profit opportunity appeared
- only a partial exit happened
- final PnL -1.74
```

There is also a likely sequencing flaw in:

```txt
Execution/advanced_trade_management.py
```

Observed issue:

```txt
partial exit is checked before full take-profit
```

So when Z is already inside the full take-profit zone, the system can take only a `50%` partial exit first, leaving the rest exposed.

Observed log pattern:

```txt
BTC/XLM hit Z=-0.23
selected trade_manager_partial_profit
later exited on divergence at Z=4.03
final result: loss
```

This is not just an edge case.

If the partial-profit condition is a wider or earlier condition and the full take-profit condition is also true, then checking partial-profit first means the system can repeatedly choose a weaker action even when the stronger action is already valid.

---

## Main Diagnosis

The bot is likely losing profit opportunity from two causes:

```txt
1. Profit guard floor may be too high for the current trade size / realized edge.
2. Partial-profit is preempting full take-profit when Z is already close enough to mean.
```

Advanced ML exit is not saving these yet because logs show:

```txt
rollout_allowed=false
```

So this patch should focus on deterministic trade-manager ordering first.

---

# Patch Strategy

## Patch 1 — Exit Priority Ordering

This is the first patch.

It should be small, targeted, and testable.

### Why this should be first

The profit guard may be too conservative, but if partial-profit can preempt full take-profit, the bot can still mishandle good exits even after guard tuning.

Current issue:

```txt
Z reaches full take-profit zone
↓
partial-profit condition is checked first
↓
bot exits only 50%
↓
remaining 50% stays exposed
↓
spread diverges again
↓
final trade becomes loss
```

Required behavior:

```txt
partial_profit must never preempt full_take_profit
```

### Safe Exit Priority Order

Recommended priority:

```txt
1. Critical safety exits
   - leg desync
   - orphan position
   - emergency stop
   - hard stop loss

2. Full take-profit
   - abs(z) <= take_profit_z
   - net profit guard passed

3. Partial profit
   - partial threshold passed
   - full TP not already eligible

4. Soft / advanced exits
   - EV exit
   - ML exit
   - time stop
   - divergence
```

The critical rule:

```txt
If full take-profit is eligible, partial-profit must not be selected.
```

### Intended logic shape

Current risky pattern:

```python
if partial_exit_condition:
    return partial_profit_exit

if full_take_profit_condition:
    return full_take_profit_exit
```

Safer pattern:

```python
if full_take_profit_condition:
    return full_take_profit_exit

if partial_exit_condition:
    return partial_profit_exit
```

Or, if the code must preserve a shared guard/evaluation structure:

```python
full_tp_eligible = (
    abs(current_z) <= take_profit_z
    and net_profit_guard_passed
)

partial_tp_eligible = (
    not full_tp_eligible
    and partial_profit_condition
    and partial_profit_guard_passed
)

if full_tp_eligible:
    return full_take_profit_exit

if partial_tp_eligible:
    return partial_profit_exit
```

---

## Patch 2 — Read-Only Profit Guard Calibration Audit

This comes after Patch 1.

Do not adjust the guard until you collect structured evidence.

Audit:

```txt
Compare max favorable UPL versus net-profit guard floor across recent trades.

For each trade:
- pair
- entry notional
- max UPL
- guard floor
- Z at max UPL
- final PnL
- whether full TP zone was touched
- whether guard blocked exit
- whether partial exit preempted full exit
```

Purpose:

```txt
Determine whether the guard should be lowered, split, or made dynamic.
```

---

## Patch 3 — Optional Guard Tuning

Only after Patch 2.

Claude suggested a Z-proximity-aware guard:

```python
if abs(current_z) <= config.tight_exit_z:
    effective_guard_floor = config.min_net_profit_usdt * 0.5
else:
    effective_guard_floor = config.min_net_profit_usdt
```

This idea is reasonable, but it is intentionally **not part of Patch 1**.

Why:

```txt
Relaxing the guard can accidentally allow too many tiny exits
that are not truly profitable after fees/slippage.
```

A safer future design may be a separate exit mode:

```txt
emergency_mean_reversion_escape
```

Possible behavior:

```txt
If Z fully reverted near mean,
profit is near breakeven,
and risk is rising,
allow exit to avoid turning a good reversion into a loss.
```

But this should be implemented only after the guard calibration audit proves it is needed.

---

# Separate Urgent Safety Task — leg_desync

The `leg_desync` / stop-loss setup failure is separate from exit priority ordering.

It should be treated as an urgent execution-safety investigation.

Reason:

```txt
An unresolved desync can leave orphaned or imbalanced legs,
which may silently accumulate exposure.
```

Do not mix this with the profit-exit priority patch.

Create a separate task for:

```txt
Investigate critical leg_desync from stop-loss setup failure.
```

That task should inspect:

```txt
- whether both legs were opened correctly
- whether both stop-loss orders were created
- whether one stop-loss leg failed validation
- whether the system detected and reconciled the mismatch
- whether orphan protection closed or hedged the remaining exposure
- whether alerts were emitted early enough
```

---

# Regression Tests

Add tests for the exact missed-profit shape and priority ordering.

## Test A — Full TP Wins Over Partial

Given:

```txt
z_score is inside the full TP zone
partial-profit condition is also true
net-profit guard passes
```

Expected:

```txt
selected exit = full_take_profit
selected exit != partial_profit
```

---

## Test B — Partial TP Still Works

Given:

```txt
partial-profit condition is true
full take-profit is not eligible
net-profit guard passes
```

Expected:

```txt
selected exit = partial_profit
```

---

## Test C — Net-Profit Guard Still Blocks Profit Exits

Given:

```txt
z_score is inside profit zone
profit is below guard floor
```

Expected:

```txt
profit exit is blocked
existing guard behavior is preserved
```

---

## Test D — Critical Safety Still Wins

Given:

```txt
critical safety exit is active
profit exit is also eligible
```

Expected:

```txt
selected exit = critical safety exit
```

Safety exits must remain highest priority.

---

## Test E — Missed-Profit BTC/XLM Shape

Given:

```txt
z_score around -0.23
take_profit_z around 0.35 or 0.50
partial-profit condition is also true
net-profit guard passes
```

Expected:

```txt
selected exit = full_take_profit
selected exit != trade_manager_partial_profit
```

---

## Test F — Crossing From Partial Zone Into Full TP Zone

Given:

```txt
at evaluation N:
- partial-profit zone is reached
- full take-profit is not yet eligible

at evaluation N+1:
- Z crosses further into full take-profit zone
- partial-profit condition is still true
- full take-profit condition is now true
- net-profit guard passes
```

Expected:

```txt
evaluation N may select or prepare partial-profit if allowed by existing behavior
evaluation N+1 must select full_take_profit
evaluation N+1 must not select partial_profit
```

This prevents a trade from remaining stuck in partial-profit behavior once full take-profit becomes valid.

---

# Codex Prompt — Targeted Exit Priority Patch

Use this prompt in Codex.

```txt
You are working on OKXStatBot.

Read the current advanced trade management logic.

Focus on:

Execution/advanced_trade_management.py

Known issue:
Profit exit selection appears to check partial-profit before full take-profit. This can cause the bot to take only a partial exit even when Z-score is already inside the full take-profit zone.

Observed example:
BTC/XLM hit Z around -0.23, selected trade_manager_partial_profit, then later exited on divergence around Z=4.03 for a loss.

Goal:
Make full take-profit higher priority than partial-profit when full TP is already eligible.

Do not change live trading behavior beyond this exit-priority fix.
Do not modify entry logic.
Do not modify order execution.
Do not modify ML rollout behavior.
Do not lower the net-profit guard yet.
Do not change fee/slippage assumptions yet.
Do not implement dynamic/tight_exit_z guard changes yet.
Do not investigate leg_desync in this patch; that is a separate urgent safety task.

Required behavior:

1. Preserve critical safety exits as highest priority:
   - leg desync
   - orphan position
   - emergency stop
   - hard stop loss
   - any existing critical close behavior

2. Evaluate full take-profit before partial-profit.

3. If abs(z_score) <= take_profit_z and the existing net-profit guard passes:
   select full take-profit.

4. Partial-profit may only be selected if:
   - full take-profit is not eligible
   - partial-profit condition is eligible
   - existing guard rules pass

5. Preserve existing reason/source naming as much as possible.
   If source names already exist, reuse them.
   Do not break existing logs/dashboard parsing.

6. Add regression tests for:
   - full TP wins over partial when both are eligible
   - partial TP still works when full TP is not eligible
   - net-profit guard still blocks profit exits when profit is below floor
   - critical safety exit still outranks profit exits
   - Z crossing from partial zone into full TP zone causes full TP to fire on next evaluation

7. Add a test based on the missed-profit shape:
   - Z is inside full TP zone
   - partial condition is also true
   - guard passes
   - expected selected exit is full_take_profit, not partial_profit

Run:
python -m compileall Execution core
pytest tests -q

Important:
Normal pytest is now safe by default because exchange demo tests are marked integration and deselected.
Do not enable RUN_EXCHANGE_TESTS.
```

---

# What Not To Change In Patch 1

Do **not** change the profit guard in this patch.

Do **not** lower this yet:

```txt
net_profit_guard = entry_notional * (fee_rate + slippage_rate) + buffer
```

Do **not** change:

```txt
fee rate
slippage assumptions
ML rollout behavior
entry logic
order execution
hedge-ratio sizing
dynamic/tight_exit_z guard behavior
leg_desync handling
```

This patch is only about **exit priority ordering**.

---

# Possible Future Guard Improvements

Do not implement these in the first patch, but consider them after the audit.

## Split Profit Guards

Instead of one guard for all profit exits:

```txt
full_exit_profit_floor
partial_exit_profit_floor
emergency_mean_reversion_escape_floor
```

Possible behavior:

```txt
full take-profit:
- must clear full estimated round-trip cost + buffer

partial profit:
- must clear proportional cost for the closed portion

mean-reversion escape:
- can exit near breakeven if Z fully reverted and risk is rising
```

---

# Completion Checklist

This patch is complete when:

```txt
✅ critical safety exits still outrank all profit exits
✅ full take-profit is checked before partial profit
✅ partial profit cannot preempt full take-profit
✅ partial profit still works when full take-profit is not eligible
✅ net-profit guard behavior is preserved
✅ dynamic/tight_exit_z guard behavior is not introduced yet
✅ existing source/reason names are preserved where possible
✅ dashboard/log parsing is not broken
✅ regression tests cover the missed-profit shape
✅ regression tests cover crossing from partial zone into full TP zone
✅ no entry logic changed
✅ no order execution changed
✅ no ML rollout behavior changed
✅ no fee/slippage assumptions changed
✅ leg_desync handling is left for a separate urgent safety task
✅ pytest tests -q passes safely without exchange order-placement tests
```
