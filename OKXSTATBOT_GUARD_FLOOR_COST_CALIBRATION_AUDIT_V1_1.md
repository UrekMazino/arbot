# OKXStatBot Patch 2 — Guard Floor Calibration Audit Plan v1.1

## Purpose

Replace the estimated guard floor with an empirically measured one — **but only after collecting a larger controlled-run sample**.

The current guard floor of roughly `$0.18–$0.24` is derived from assumed fee/slippage rates and exit multipliers. It has not yet been fully validated against actual fill data. This plan defines how to collect real execution-cost data, analyze it, and produce a calibrated guard floor that reflects what the bot actually pays per trade.

---

## v1.1 Update Summary

This version adds safeguards to prevent the calibration audit from creating false confidence or degrading the bot.

Key changes:

```txt
1. Patch 2 remains read-only.
2. Patch 3 must not be applied immediately after one small sample.
3. Require a larger sample before applying calibration.
4. Clarify base guard vs effective guard vs actual measured cost.
5. Avoid double-counting sequential leg fill cost.
6. Treat historical mid-price reconstruction as approximate unless true orderbook snapshots exist.
7. Add confidence intervals and low-sample warnings.
8. Add equity-reconciliation sanity checks.
9. Add mark-to-fill delta fields.
10. Separate costs by exit reason, liquidity bucket, and symbol/pair family.
```

Most important rule:

```txt
Do not apply calibrated guard-floor config until after a few more controlled test runs and enough closed trades exist.
```

Recommended minimum before applying Patch 3:

```txt
At least 20–30 closed trades
AND at least 3–5 trades per major exit type if possible
AND no unresolved reconciliation/accounting safety issue
```

If fewer trades exist, Patch 2 may still produce an audit, but it must be labeled:

```txt
LOW CONFIDENCE — DO NOT APPLY DIRECTLY
```

---

## Why This Matters

Across recent runs, full TP has often been blocked or not reached, and many trades have not produced enough MFE to clear cost.

The guard floor blocks exits when:

```txt
floating_pnl < estimated_round_trip_cost × guard_multiplier
```

If the estimate is wrong in either direction, the result is:

```txt
Guard too tight:
- blocks viable exits
- trade stays open
- spread re-widens
- loss

Guard too loose:
- allows exits that appear profitable
- but are net negative after real costs
- creates tiny fake wins or actual losses
```

Neither case is acceptable.

The correct floor should be based on measured execution cost, but only when the measurement is reliable enough.

---

## What Patch 2 Is NOT

Patch 2 is **not**:

```txt
- a trading-logic change
- a config tuning pass
- a new exit feature
- a guard loosening
- a guard tightening
- an automatic Patch 3 approval
```

Patch 2 is a **read-only audit** that produces measured cost statistics and a recommendation.

Patch 3, later, decides whether to apply those numbers.

---

## Important Definitions

Clarify these values before analysis.

### 1. Base Guard Floor

The bot's estimated floor before multipliers.

Example:

```txt
base_min_profit_usdt = 0.24
```

### 2. Effective Exit Guard Floor

The actual threshold used by a specific exit type after multiplier.

Example:

```txt
full_tp_guard_multiplier = 0.75

effective_full_tp_floor = base_min_profit_usdt × full_tp_guard_multiplier
effective_full_tp_floor = 0.24 × 0.75 = 0.18
```

### 3. True Round-Trip Cost

Measured cost from actual execution:

```txt
true_round_trip_cost = actual fees + actual/estimated slippage
```

### 4. Mark-to-Fill Delta

Difference between expected mark-based PnL at decision time and actual fill/equity result.

```txt
mark_to_fill_delta_usdt = actual_fill_or_equity_pnl - decision_time_mark_pnl
```

This is important because previous reconciliation audits showed that mark-based expected PnL can differ materially from actual equity movement during sequential market-order execution.

---

## Current Guard Comparison Rule

Do not compare measured cost against a vague `$0.36` unless that is confirmed as the bot's actual current assumed all-in round-trip cost.

For each trade, compare measured cost against:

```txt
base_min_profit_usdt
effective_full_tp_floor
effective_partial_tp_floor
effective_trailing_stop_floor
```

Required fields:

```txt
base_min_profit_usdt
full_tp_guard_multiplier
partial_tp_guard_multiplier
trailing_stop_guard_multiplier
effective_full_tp_floor_usdt
effective_partial_tp_floor_usdt
effective_trailing_stop_floor_usdt
true_round_trip_cost_usdt
```

---

# Phase 2.0 — Minimum Sample Requirement

Before using Patch 2 output for Patch 3 config changes, collect more controlled test runs.

Recommended sample:

```txt
Minimum: 20 closed trades
Preferred: 30+ closed trades
Better: 50+ closed trades if the bot can safely collect them at 200 USDT
```

The sample should include, if possible:

```txt
- take_profit exits
- trailing_stop exits
- cointegration_lost exits
- cointegration_watch_timeout exits
- regime_break exits
- normal exits
```

If the bot only produces 1–5 trades, the audit can still be run, but output must say:

```txt
Sample too small. Use for diagnosis only. Do not apply guard-floor config yet.
```

Controlled-run config during data collection should remain:

```env
STATBOT_TRADEABLE_CAPITAL_USDT=200
STATBOT_FULL_TP_GUARD_MULTIPLIER=0.75
STATBOT_PNL_PROFIT_LOCK_ENABLED=true
STATBOT_MEAN_REVERSION_ESCAPE_ENABLED=false
STATBOT_ENTRY_SAFETY_GATE_ENABLED=true
STATBOT_ENTRY_GATE_MAX_BREAK_RISK=0.12
STATBOT_RISK_CIRCUIT_BREAKER_STATE_MODE=session
STATBOT_REGIME_ROUTER_MODE=shadow
STATBOT_STRATEGY_ROUTER_MODE=shadow
STATBOT_ADVANCED_ML_SHADOW_MODE=1
```

Do not scale up during calibration.

---

# Phase 2.1 — Data Collection

## Step 1: Pull Actual Fill Prices From OKX

For every closed trade across controlled runs, retrieve from OKX order/fill history:

```txt
For each trade:
  For each leg:
    Entry fill:
      - fill_price
      - fill_size
      - fill_time_ms
      - fee_usdt or fee_ccy + conversion
      - liquidity role: maker/taker if available
      - order_id
      - trade_id

    Exit fill:
      - fill_price
      - fill_size
      - fill_time_ms
      - fee_usdt or fee_ccy + conversion
      - liquidity role: maker/taker if available
      - order_id
      - trade_id
```

Possible source:

```txt
OKX /api/v5/trade/fills
OKX order history UI
local order/fill logs if persisted
```

Important:

```txt
Do not assume all fees are taker fees.
Use actual OKX-reported fees whenever available.
```

---

## Step 2: Pull Mid-Price at Fill Time

For each fill, estimate the mid-price:

```txt
mid = (best_bid + best_ask) / 2
```

Preferred source:

```txt
historical orderbook snapshot captured by the bot at fill time
```

Fallback source:

```txt
closest stored orderbook snapshot before/after fill
```

Lower-confidence fallback:

```txt
closest 1-minute OHLCV candle mid
```

### Important caveat

The live OKX endpoint:

```txt
/api/v5/market/books?instId=XXX&sz=1
```

normally returns the **current** book, not the historical book at an old timestamp.

Therefore:

```txt
Do not call the current orderbook endpoint and treat it as historical fill-time data.
```

If true historical books were not stored, mark slippage estimates as approximate.

Add field:

```txt
mid_price_source = exact_snapshot | nearest_snapshot | candle_proxy | unavailable
```

---

## Step 3: Build the Cost Table

For each trade, compute:

```txt
entry_slippage_leg1_pct = abs(entry_fill_price_leg1 - mid_at_entry_leg1)
                          / mid_at_entry_leg1

entry_slippage_leg2_pct = abs(entry_fill_price_leg2 - mid_at_entry_leg2)
                          / mid_at_entry_leg2

exit_slippage_leg1_pct  = abs(exit_fill_price_leg1 - mid_at_exit_leg1)
                          / mid_at_exit_leg1

exit_slippage_leg2_pct  = abs(exit_fill_price_leg2 - mid_at_exit_leg2)
                          / mid_at_exit_leg2
```

Convert slippage to USDT:

```txt
slippage_usdt = slippage_pct × leg_notional_usdt
```

Then compute:

```txt
total_fee_usdt =
    entry_fee_leg1 + entry_fee_leg2
  + exit_fee_leg1  + exit_fee_leg2

total_slippage_usdt =
    entry_slippage_usdt_leg1
  + entry_slippage_usdt_leg2
  + exit_slippage_usdt_leg1
  + exit_slippage_usdt_leg2

true_round_trip_cost_usdt =
    total_fee_usdt + total_slippage_usdt
```

---

## Step 4: Measure Sequential Leg Fill Gap

For each paired execution, record:

```txt
entry_leg_fill_gap_ms = abs(entry_fill_time_leg2 - entry_fill_time_leg1)
exit_leg_fill_gap_ms  = abs(exit_fill_time_leg2 - exit_fill_time_leg1)
```

If spread snapshots exist at both leg-fill times:

```txt
spread_at_leg1_fill
spread_at_leg2_fill
spread_move_during_gap
```

### Important caveat — avoid double counting

Sequential leg fill cost should be reported separately.

Do **not** automatically add it to `true_round_trip_cost` unless you prove it is not already captured by:

```txt
- fill-vs-mid slippage
- mark-to-fill delta
- reconciliation unexplained PnL gap
```

Report separately:

```txt
sequential_fill_gap_ms
sequential_fill_cost_estimate_usdt
sequential_cost_counted_in_guard = false
```

---

# Phase 2.2 — Analysis

## Output Table

Produce one row per closed trade.

| Field | Description |
|---|---|
| run_id | e.g. run_58, run_84 |
| pair | e.g. ARB/LPT |
| exit_reason | e.g. trailing_stop, cointegration_lost |
| notional_usdt | configured tradeable capital |
| entry_notional_leg1 | actual leg 1 notional |
| entry_notional_leg2 | actual leg 2 notional |
| exit_notional_leg1 | actual exit leg 1 notional |
| exit_notional_leg2 | actual exit leg 2 notional |
| entry_fee_leg1 | OKX reported fee |
| entry_fee_leg2 | OKX reported fee |
| exit_fee_leg1 | OKX reported fee |
| exit_fee_leg2 | OKX reported fee |
| total_fee_usdt | sum of all fill fees |
| entry_slippage_leg1_pct | vs fill-time mid |
| entry_slippage_leg2_pct | vs fill-time mid |
| exit_slippage_leg1_pct | vs fill-time mid |
| exit_slippage_leg2_pct | vs fill-time mid |
| total_slippage_usdt | estimated fill-vs-mid slippage |
| mid_price_source | exact_snapshot / nearest_snapshot / candle_proxy / unavailable |
| entry_leg_fill_gap_ms | time gap between entry legs |
| exit_leg_fill_gap_ms | time gap between exit legs |
| sequential_fill_cost_estimate_usdt | separate estimate only |
| true_round_trip_cost_usdt | fees + slippage only |
| base_min_profit_usdt | bot's base guard floor |
| effective_full_tp_floor_usdt | base × full TP multiplier |
| effective_partial_tp_floor_usdt | base × partial multiplier |
| effective_trailing_stop_floor_usdt | base × trailing multiplier |
| cost_vs_base_guard_pct | (true_cost - base_guard) / base_guard |
| cost_vs_effective_full_tp_pct | (true_cost - effective_full_tp_floor) / effective_full_tp_floor |
| decision_time_mark_pnl_usdt | mark PnL when exit candidate triggered |
| actual_fill_pnl_usdt | fill/equity-based realized PnL |
| mark_to_fill_delta_usdt | actual_fill_pnl - decision_time_mark_pnl |
| gross_mfe_usdt | peak favorable PnL before cost adjustment |
| net_mfe_after_true_costs_usdt | gross_mfe - true_round_trip_cost |
| trade_was_cost_viable | net_mfe_after_true_costs_usdt > 0 |
| reconciliation_status | PASS / FAIL |
| unexplained_pnl_gap_usdt | from reconciliation checks |
| unexplained_pnl_gap_pct | from reconciliation checks |

---

## Key Metrics to Compute

Compute aggregate stats:

```txt
avg_true_round_trip_cost_usdt
median_true_round_trip_cost_usdt
p75_true_round_trip_cost_usdt
p90_true_round_trip_cost_usdt
stddev_true_round_trip_cost_usdt

avg_fee_rate_pct
avg_slippage_pct
avg_mark_to_fill_delta_usdt
p75_abs_mark_to_fill_delta_usdt
avg_entry_leg_fill_gap_ms
avg_exit_leg_fill_gap_ms
avg_sequential_fill_cost_estimate_usdt

viable_trade_count
unviable_trade_count
viability_rate

cost_assumption_error_vs_base_guard_pct
cost_assumption_error_vs_effective_full_tp_pct
```

Compute confidence:

```txt
sample_size
confidence_label = LOW | MEDIUM | HIGH
```

Suggested:

```txt
LOW:    fewer than 20 trades
MEDIUM: 20–49 trades
HIGH:   50+ trades
```

---

## Segment the Costs

Do not use one blended number only.

Break down costs by:

```txt
exit_reason
pair
symbol family
liquidity bucket
notional bucket
maker/taker role
entry side
market regime if available
```

Important segments:

```txt
take_profit exits
trailing_stop exits
cointegration_lost exits
cointegration_watch_timeout exits
regime_break exits
long-tail / meme / low-liquidity symbols
major liquid symbols
```

---

## Questions the Analysis Must Answer

1. What is the actual average round-trip cost at `200 USDT` notional?
2. Is the current base guard accurate, too high, or too low?
3. Is the effective full TP floor accurate, too high, or too low?
4. What percentage of trades had gross MFE above the true cost floor?
5. What percentage of trades were structurally unviable after real costs?
6. What is the typical leg fill gap?
7. How much does sequential leg execution cost, separately from slippage?
8. Is fee rate closer to maker or taker rates?
9. What slippage rate is realistic for your liquidity levels?
10. Which exit type has the worst mark-to-fill delta?
11. Are trailing-stop exits more expensive than full TP exits?
12. What guard floor would have allowed viable trades while blocking unviable ones?
13. Do entries generate enough gross edge to beat real costs?

---

# Phase 2.3 — Guard Floor Recommendation

## Calibrated Floor Formula

Initial recommendation:

```txt
calibrated_guard_floor =
    avg_true_round_trip_cost_usdt
  + (0.5 × stddev_true_round_trip_cost_usdt)
```

But also report alternatives:

```txt
median_cost_floor
p75_cost_floor
p90_cost_floor
```

Do **not** automatically apply the average formula if sample size is low.

Suggested interpretation:

```txt
LOW sample:
- report all floors
- do not apply config

MEDIUM sample:
- consider p75 for conservative guard

HIGH sample:
- choose by exit type and liquidity segment
```

---

## Guard Multiplier Recalculation

Current logic:

```txt
guard_floor = estimated_round_trip_cost × guard_multiplier
```

Future calibrated logic may become:

```txt
guard_floor = measured_cost_floor × exit_type_multiplier
```

But do not apply until Patch 3.

Compute theoretical new multiplier:

```txt
new_full_tp_multiplier =
    calibrated_full_tp_floor / measured_avg_round_trip_cost_usdt
```

But flag:

```txt
If measured_avg_round_trip_cost_usdt is derived from low-N data, multiplier is informational only.
```

---

## Split Guard Recommendation

Assess separate floors:

```txt
full_exit_guard_floor =
    cost distribution for full exits

partial_exit_guard_floor =
    proportional cost of partial close + buffer

trailing_stop_guard_floor =
    trailing-stop cost distribution + larger buffer if mark-to-fill gap is worse
```

Do not assume trailing stop cost equals full TP cost.

---

# Phase 2.4 — Entry Viability Assessment

Alongside cost calibration, assess whether entries can generate enough gross edge.

## Required Gross Edge

For a trade to be viable:

```txt
gross_mfe_usdt > true_round_trip_cost_usdt
```

At `200 USDT` notional, if true cost is `0.18 USDT`:

```txt
required_gross_mfe_pct = 0.18 / 200 = 0.09%
```

If true cost is `0.36 USDT`:

```txt
required_gross_mfe_pct = 0.36 / 200 = 0.18%
```

If typical gross MFE is below that, the entry is structurally unviable.

---

## Per-Trade Viability Check

For each trade:

```txt
gross_mfe_usdt
true_round_trip_cost_usdt
net_mfe_after_true_costs_usdt
trade_was_cost_viable
```

Optional theoretical check if spread units are reliable:

```txt
entry_spread_pct
theoretical_max_profit_pct
theoretical_max_profit_usdt
was_theoretically_viable
```

### Unit warning

Only compute theoretical spread profit if spread units are well defined.

If spread is log-price based, do not multiply directly by notional unless properly converted.

---

# Phase 2.5 — Codex Audit Prompt

Use this prompt after enough data is collected.

```txt
You are working on OKXStatBot.

This is a read-only audit. Do not change any code or config.

Context:
The bot's guard floor is based on estimated round-trip costs. It has not been fully validated against actual fill data.

Important:
Do not apply any config changes from this audit unless there are at least 20–30 closed trades and no unresolved reconciliation issues.

Goal:
Compute the true round-trip cost per trade from actual OKX fill data and determine whether the guard floor is correctly calibrated.

Read:
- trade_closes.csv across controlled runs
- reconciliation_checks.csv across controlled runs
- exit_decision_summary.csv across controlled runs
- position_snapshots.csv across controlled runs
- any OKX fill records available locally
- any stored orderbook snapshots if available
- matching run logs

For each closed trade, compute:
1. Total fee paid from OKX fills if available.
2. Total slippage using fill-vs-mid if historical mid is available.
3. Mark-to-fill delta using reconciliation data.
4. True round-trip cost estimate.
5. Gross MFE.
6. Net MFE after true costs.
7. Whether the trade was cost-viable.
8. Whether the result is high-confidence or approximate.

Important cautions:
- Do not treat current /market/books as historical orderbook data.
- If historical orderbook snapshots are unavailable, mark slippage as approximate.
- Do not double-count sequential leg fill cost.
- Report sequential leg fill cost separately.
- Separate base guard floor from effective exit floor.

Return:
1. Per-trade cost breakdown table.
2. Aggregate cost statistics.
3. Confidence label.
4. Recommended calibrated guard floor.
5. Recommended full/partial/trailing floors if justified.
6. Assessment of whether entries were structurally viable.
7. Clear warning if sample size is too small to apply.

Do not change files.
Do not change config.
Run only read/analysis commands.
```

---

# Phase 2.6 — Output and Decision

Patch 2 output should be:

```txt
recommended_guard_floor_usdt = X.XX
confidence = LOW | MEDIUM | HIGH
apply_now = true | false
```

For current project state, default should be:

```txt
apply_now = false
```

until more controlled trades exist.

Patch 3 may later define:

```env
STATBOT_FULL_TP_GUARD_FLOOR_USDT=X.XX
STATBOT_PARTIAL_TP_GUARD_FLOOR_USDT=X.XX
STATBOT_TRAILING_STOP_GUARD_FLOOR_USDT=X.XX
STATBOT_FEE_RATE_ASSUMED=X.XXXX
STATBOT_SLIPPAGE_RATE_ASSUMED=X.XXXX
```

But Patch 3 should require explicit approval.

---

# Completion Checklist

```txt
✅ More controlled test runs completed before applying config
✅ At least 20–30 closed trades preferred
✅ OKX fill data retrieved where available
✅ True round-trip cost computed per trade
✅ Slippage source labeled clearly
✅ Leg fill gap measured
✅ Sequential fill cost reported separately
✅ No double-counting of sequential fill cost
✅ Mark-to-fill delta computed
✅ Net MFE after true costs computed
✅ Viability rate computed
✅ Base guard and effective guard compared separately
✅ Confidence interval / confidence label reported
✅ Costs segmented by exit type and liquidity bucket
✅ Entry viability assessed
✅ Structured report produced
✅ No code changed
✅ No config changed
✅ Patch 3 values marked apply_now=false unless enough data exists
```

---

# What Patch 2 Does NOT Decide

Patch 2 does not decide:

```txt
- whether to apply the calibrated floor
- whether to split guard floors by exit type
- whether to change fee/slippage assumptions
- whether to raise entry Z thresholds
- whether to increase notional
- whether to loosen Entry Safety Gate
```

Those are Patch 3 decisions.

---

# Risks

| Risk | Mitigation |
|---|---|
| OKX fill history unavailable for older runs | Use reconciliation_checks.csv as proxy and label confidence lower |
| Historical mid-price unavailable | Use stored snapshots if available; otherwise candle proxy with low confidence |
| Current orderbook mistakenly used as historical | Explicitly forbid this |
| Too few trades | Report LOW confidence and apply_now=false |
| Double-counting sequential fill cost | Report separately; do not include unless proven distinct |
| Costs differ by exit type | Segment by exit_reason |
| Spread units misunderstood | Only compute theoretical edge when units are well defined |
| Calibration from losing-only sample | Segment by exit type and report bias caveat |
| Survivorship bias | Exclude open trades or report them separately |
| Reconciliation anomalies unresolved | Do not apply Patch 3 until explained |

---

# Expected Timeline

```txt
Phase 2.0 — More controlled runs:  variable
Phase 2.1 — Data collection:       1–2 hours
Phase 2.2 — Analysis:              1–2 hours
Phase 2.3 — Recommendation:        30 minutes
Phase 2.4 — Entry viability:       30 minutes
Total after enough data:           3–5 hours
```

After completion, proceed to Patch 3 only if:

```txt
sample_size is sufficient
confidence is not LOW
reconciliation issues are resolved
apply_now is explicitly approved
```
