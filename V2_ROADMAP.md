# V2 Roadmap (UI + Deferred Phase Work)

Date: 2026-02-18
Status: Active planning

Reference:

1. Detailed implementation spec: `V2_UI_PLATFORM_SPEC.md`

## 1. Goal

Ship a usable V2 UI first, while deferring remaining execution-engine upgrades from V1 Phase 4 into a tracked queue.

## 2. Scope Split

### 2.1 V2-A (UI First)

1. [x] Run browser (list runs, status, PnL, duration) - initial scaffold in `Platform/web`.
2. [x] Charts (equity curve, drawdown, strategy/regime attribution) - initial panel set in `Platform/web`.
3. [ ] Event timeline (switches, gates, alerts, exits).
4. [ ] Data quality and reconciliation panels.
5. [ ] Config snapshot viewer and report artifact links.

### 2.2 V2-B (Deferred Engine Queue)

The following V1 Phase 4 items are queued for later execution in V2:

1. `P4B` Strategy cooldown controller.
2. `P4C` TREND quality upgrades:
   - regime-aware z-lookback,
   - directional filter (`off|shadow|active`).
3. `P4D` Strategy-specific ATM profile overrides.

## 3. Deferred Queue Details

### 3.1 P4B Strategy Cooldown Controller (Queued)

Target:
- Temporarily block new entries for underperforming strategy profiles.

Pending implementation:
- Runtime cooldown logic in `Execution/strategy_router.py`.
- State fields and thresholds in `Execution/func_strategy_state.py` and `Execution/.env.example`.
- Runtime logs:
  - `STRATEGY_COOLDOWN_ON`
  - `STRATEGY_COOLDOWN_OFF`

Acceptance:
- Cooldown behavior visible in logs and reports.
- No hidden trade starvation.
- No increase in emergency pair switches.

### 3.2 P4C TREND Quality Upgrades (Queued)

Target:
- Reduce low-quality TREND entries.

Pending implementation:
- Regime-aware lookback wiring:
  - `STATBOT_RANGE_Z_LOOKBACK`
  - `STATBOT_TREND_Z_LOOKBACK`
- Directional filter runtime modes:
  - `STATBOT_STRATEGY_TREND_DIRECTIONAL_FILTER_MODE=off|shadow|active`
- Runtime logs:
  - `TREND_LOOKBACK_APPLIED`
  - `DIRECTIONAL_FILTER_SHADOW`
  - `DIRECTIONAL_FILTER_ACTIVE_BLOCK`

Acceptance:
- Lower TREND false-entry rate.
- Stable or improved realized PnL per TREND trade.

### 3.3 P4D Strategy-Specific ATM Profiles (Queued)

Target:
- Align exit behavior with strategy risk profile.

Pending implementation:
- Strategy-specific ATM overrides in:
  - `Execution/advanced_trade_management.py`
  - `Execution/func_trade_management.py`

Acceptance:
- `TREND_SPREAD` exits faster/tighter than `STATARB_MR`.
- Exit-stack priority remains unchanged.

## 4. Profit-Uplift Evaluation Template (Use Later)

Use this template when implementing queued V2-B items.

### 4.1 Cohorts

1. Baseline cohort: runs before a feature is enabled.
2. Candidate cohort: runs with only one new feature enabled.
3. Keep pair universe, account size, and key risk limits unchanged between cohorts.

### 4.2 Minimum Sample Size

1. At least 100 closed trades total per comparison.
2. At least 30 `TREND_SPREAD` trades for TREND-specific claims.
3. At least 5 calendar days per cohort.

### 4.3 Primary Metrics

1. Realized PnL per trade.
2. Realized PnL per day.
3. Max drawdown percent.
4. Strategy-level win rate and expectancy.

### 4.4 Secondary Metrics

1. Trade frequency (avoid accidental starvation).
2. Gate counts by type (`coint`, `mean_shift`, `cooldown`, `directional`).
3. Pair switch rate and switch reasons.
4. Reconciliation warning rate.

### 4.5 Promotion Criteria

Promote a queued feature from shadow to active only if:

1. PnL/day improves by at least 5%, or drawdown improves by at least 15%.
2. Max drawdown does not worsen by more than 10%.
3. Trade frequency does not drop by more than 35% unless explicitly intended.
4. No increase in critical runtime/data-quality failures.

## 5. Tracking

Use this status checklist:

- [ ] P4B implemented
- [ ] P4B shadow validated
- [ ] P4B active validated
- [ ] P4C lookback implemented
- [ ] P4C directional filter shadow validated
- [ ] P4C directional filter active validated
- [ ] P4D ATM profile overrides implemented
- [ ] V2 UI dashboard integrated with strategy/regime analytics
