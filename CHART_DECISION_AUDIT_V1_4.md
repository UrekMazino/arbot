OKXStatBot Chart Decision Audit Dashboard Prompt v1.4
Includes Phase 2.25 — Hedge-Ratio Exposure Alignment + Contract Fixes
Actual Bot Decision Overlay + Curator-Aware Point-In-Time Replay + Counterfactual Exit Study + Decision Score Timeline

================================================================================
HOW TO USE THIS DOCUMENT WITH CODEX / COPILOT
================================================================================

This is a focused implementation prompt for improving the OKXStatBot dashboard chart.

Save this file as:

CHART_DECISION_AUDIT_V1_4.md

Then ask Codex / Copilot to implement it in phases.

Important:

Do NOT ask Codex to implement the whole thing at once.

Use this file as the master spec, then implement module-by-module.

Recommended first Codex instruction:

"Read CHART_DECISION_AUDIT_V1_4.md. Do not write code yet.
Summarize the modules, data sources, marker categories, and the no-lookahead rules.
Then wait for my specific command naming the first file/module to implement."

================================================================================
PURPOSE
================================================================================

You are helping me improve my OKXStatBot dashboard chart.

Current chart shows:

- Normalized price path for pair symbols
- Spread Z-score line
- +2 / -2 entry threshold lines
- Z-score 0 mean line
- Yellow dots called "Chart crossing"
- Replay markers
- Pair universe fullscreen chart

Important clarification:

Yellow dots are NOT automatic trade-entry signals.
They are historical mean-reversion crossings only.

They represent where the spread crossed back through its historical mean area after applying a small deadband/noise filter.

Current meaning:

- Orange line = live/rolling spread Z-score
- Red dashed line = +2 entry zone
- Green dashed line = -2 entry zone
- Gray dashed line = Z-score 0
- Yellow dots = historical mean-reversion crossings
- Other colored markers = replay markers

Goal:

Upgrade the chart from a visual study tool into a point-in-time decision audit system.

The chart should answer:

"At this timestamp, what did the spread do, what would the bot have considered, what was blocked, what actually happened, and could the exit have been improved?"

The goal is not just:

"Where did the Z-score go?"

The goal is:

"What did the bot know at that time, what decision did it make, why did it make it, and would another decision have been better?"

Implement these systems:

1. Actual Bot Decision Overlay
2. Curator-Aware Point-In-Time Replay
3. Counterfactual Exit Study
4. Decision Score Timeline
5. Clear Marker Semantics

Recommended starting point:

Implement Phase 1 and Phase 2 first:

1. Actual Bot Decision Overlay
2. Curator-Aware Point-In-Time Replay

These give the most accurate learning value because they separate:

- what looked like an opportunity on the chart
- what the bot was allowed to trade
- what the bot actually traded
- what the bot correctly blocked
- what exit could have been improved

================================================================================
V1.1 PATCH NOTES — WHAT THIS VERSION ADDS
================================================================================

This v1.1 version improves the original chart audit prompt by adding:

1. ReplaySnapshot interface
   - Enforces no-lookahead at the data interface level.
   - The replay engine receives only data available up to timestamp t.

2. Historical curator state sourcing
   - Defines curator_state_at(t).
   - Prevents using today's pair state for historical replay.

3. Historical config sourcing
   - Defines config_at(t).
   - If historical config is unavailable, replay must mark config_source = "current_approximate".

4. CounterfactualExitResult schema
   - Defines how counterfactual exit results are represented.
   - Defines behavior when an exit condition never triggers.

5. BlockReason enum
   - Prevents inconsistent block reason strings.

6. Integration with Advanced ML v3.1 architecture
   - Replay/audit should consume HardValidationResult, ValidPairCandidate, RegimeDetectionResult, BayesianPairScore, FinalPairRank, ExitDecision, and MicrostructureExitResult when available.

7. MVP replay boundary
   - MVP replay should use only basic Z-score, hard validation, curator state, and liquidity checks.
   - Advanced ML replay should come later.

8. Timestamp alignment rules
   - Handles mismatch between candle timestamps and exact trade-event timestamps.

9. Marker z-index rules
   - Actual markers render on top of replay markers.

10. Frontend layer toggles
   - User can hide/show statistical, replay, actual, counterfactual, and decision score layers.

11. Lazy counterfactual loading
   - Avoids expensive computation on initial chart load.

12. Deterministic replay test
   - Same historical inputs must produce identical replay markers.


================================================================================
V1.2 TARGETED PATCH NOTES — ONLY THESE EDITS WERE ADDED
================================================================================

This v1.2 version keeps v1.1 intact and applies only the targeted implementation fixes:

1. ReplaySnapshot now uses immutable tuples instead of mutable lists:
   - candles_until_t: tuple[Candle, ...]
   - zscore_until_t: tuple[float, ...]
   - spread_until_t: tuple[float, ...]
   - actual_events_at_t: tuple[ActualBotEvent, ...]

2. Adds explicit incremental indicator rule:
   - Do not precompute full-series Z-scores, hedge ratios, rolling mean/std, or cointegration results and then slice.
   - Compute them incrementally inside the replay loop from candles[: i + 1], unless the computation is proven point-in-time safe.

3. Defines ReplayConfigSnapshot dataclass.

4. Defines CuratorState enum.

5. Adds CURATOR_LOW_LIQUIDITY to BlockReason.

6. Defines explicit entry_id format:
   - actual entry: entry_id = f"actual_{trade_id}"
   - replay entry: entry_id = f"replay_{pair_key}_{timestamp}_{side}"

7. Replaces ambiguous MAE/MFE fields with explicit unit fields:
   - max_adverse_excursion_z
   - max_favorable_excursion_z
   - max_adverse_excursion_usdt
   - max_favorable_excursion_usdt

8. Adds decision timeline downsampling:
   - max_timeline_points
   - downsample_method
   - optional resolution parameter

9. Adds ML unavailable fallback behavior:
   - optional ML fields must be null if no stored output exists.
   - do not recompute retrospectively unless the ReplaySnapshot-based pipeline is available and score_source is "recomputed_point_in_time".

10. Adds safe dataframe/window view note:
   - ReplaySnapshot may use immutable tuples, safe dataframe slices, or read-only rolling window views as long as the replay engine cannot access data after timestamp t.

After this v1.2 patch, the next implementation step is:

Phase 1: Actual Bot Decision Overlay.


================================================================================
V1.3 PATCH NOTES — PHASE 2.25 HEDGE-RATIO EXPOSURE ALIGNMENT
================================================================================

This version extends CHART_DECISION_AUDIT_V1_2 with a new prerequisite phase:

Phase 2.25 — Hedge-Ratio Exposure Alignment

Why this is necessary:

The bot's statistical signal is hedge-ratio aware:

spread = log(asset1) - hedge_ratio * log(asset2)

But current entry sizing may still be equal-notional per leg:

leg1_notional = X
leg2_notional = X

That means the executed position may not match the statistical spread being measured.

If hedge_ratio = 1.8 and the bot enters equal-notional, the trade is not actually positioned as:

asset1 - 1.8 * asset2

This can cause the graph/Z-score to show mean reversion while PnL does not improve as expected.

Important design decision:

Do NOT simply multiply one leg by hedge_ratio if that increases total gross exposure unexpectedly.

Use gross-normalized hedge-ratio sizing:

beta = abs(hedge_ratio)

leg1_notional = gross_pair_notional / (1.0 + beta)
leg2_notional = gross_pair_notional * beta / (1.0 + beta)

This preserves total gross exposure while matching the hedge-ratio relationship.

Example:

gross_pair_notional = 1500
hedge_ratio = 1.8

leg1_notional = 1500 / 2.8 = 535.71
leg2_notional = 1500 * 1.8 / 2.8 = 964.29
gross = 1500

Phase 2.25 should be completed before Phase 2.5 Advanced ML Replay Integration because advanced replay and decision scoring are less useful if actual executed positions do not match the spread model.

Do not auto-rebalance open positions yet.

For MVP:

- apply hedge-ratio-aware sizing at new entries only when explicitly enabled
- store hedge ratio at entry
- store target and actual leg notionals
- monitor hedge-ratio drift during open trades
- emit an ExitCandidate for hedge-ratio drift through the Exit Orchestrator
- add hedge-ratio fields to chart audit markers and tooltips
- add counterfactual comparison: equal-notional vs hedge-ratio-sized PnL


================================================================================
V1.4 PATCH NOTES — CONTRACT FIXES BEFORE PHASE 2.25 IMPLEMENTATION
================================================================================

This version keeps v1.3 intact and adds the remaining implementation-contract fixes:

1. FrozenCointegrationResult

Replaces ambiguous:

cointegration_result_until_t: dict | None

with a frozen, explicit result type:

cointegration_result_until_t: FrozenCointegrationResult | None

This avoids mutable dicts inside ReplaySnapshot and prevents Codex from inventing fields.

2. OrderBookSnapshot immutability guidance

If OrderBookSnapshot is stored inside ReplaySnapshot, it should be frozen/read-only.
If the existing runtime object is mutable, convert it into a FrozenOrderBookSnapshot or safe immutable DTO before placing it in ReplaySnapshot.

3. ReplayConfigSnapshot hedge-ratio fields

Adds replay-relevant hedge-ratio config fields:

- hedge_ratio_sizing_enabled
- hedge_sizing_mode
- min_hedge_ratio
- max_hedge_ratio
- reject_negative_hedge_ratio
- max_hedge_sizing_error_pct
- max_hedge_ratio_drift_pct
- severe_hedge_ratio_drift_pct
- min_cointegration_window

This prevents historical replay from silently using current hedge-ratio settings.

4. ExitAction.TIGHTEN_STOP

Adds tighten_stop as a valid Exit Orchestrator action.

If the current orchestrator cannot support tighten_stop yet, map it to:

action = "warn"
metadata.intent = "tighten_stop"

but the recommended fix is to add TIGHTEN_STOP to the enum.

5. hedge_sizing_error_pct and hedge_ratio_execution_error_pct formulas

Defines both formulas explicitly so Codex does not choose arbitrarily.

6. Minimum window behavior

If len(candles_until_t) < config.min_cointegration_window:

- hedge_ratio_until_t = None
- cointegration_result_until_t = None
- replay status = insufficient_data
- block reason = insufficient_history

7. replay_exit_candidate schema

Adds a full JSON schema example for replay_exit_candidate.

8. ActualBotEvent dataclass

Defines the actual event adapter type used by ReplaySnapshot.

9. ReplayMarkerStatus enum

Replaces raw string statuses with a proper enum:

- valid_candidate
- blocked_candidate
- ignored_candidate
- insufficient_data

10. Equal-notional counterfactual baseline

Defines the baseline as:

equal_leg_notional = gross_pair_notional / 2.0

This keeps total gross exposure constant when comparing equal-notional vs hedge-ratio-sized PnL.

================================================================================
CORE CONCEPT
================================================================================

Right now, the chart is useful for visual study, but it is not yet a full point-in-time decision audit.

Best approaches:

1. Point-In-Time Replay

Replay each candle using only data available up to that candle.

This gives honest markers:

- would enter
- would exit
- would block
- insufficient data

No future candles.
No current full-window hedge-ratio hindsight.
No full-series normalization hindsight.

2. Curator-Aware Replay

Add curator state to the replay:

- tradable
- analysis_only
- excluded
- hospital
- graveyard
- stale_data
- insufficient_history
- low_liquidity

Then mark signals as:

- valid at the time
- invalid because curator would not allow it
- blocked because quality/liquidity/cointegration failed

3. Actual Bot Decision Overlay

Overlay real bot events:

- actual entries
- actual exits
- actual partial exits
- actual blocked signals
- quality-gate blocks
- liquidity blocks
- cointegration invalid blocks
- advanced ML exit decisions
- manual exits

This teaches why the bot acted or refused to act.

4. Counterfactual Exit Study

For each actual or replay entry, test exits:

- exit at Z = 0.50
- exit at Z = 0.35
- exit at Z = 0.00
- exit on crossing mean
- exit on adverse acceleration
- exit on time stop
- exit on trailing stop
- exit on advanced EV manager
- exit on microstructure stress

Then compare which exit would have performed better.

5. Decision Score Timeline

Add lower panels showing:

- regime confidence
- regime break risk
- Bayes posterior
- LinUCB score
- microstructure risk
- EV hold-vs-exit score
- liquidity score
- trade quality score
- exit score
- curator state

This turns the chart from "price picture" into "decision explanation."

================================================================================
INTEGRATION WITH ADVANCED ML V3.1 ARCHITECTURE
================================================================================

This chart audit system must integrate with the Advanced ML v3.1 architecture when those modules are available.

Replay/audit may consume these outputs:

- HardValidationResult
- ValidPairCandidate
- RegimeDetectionResult
- BayesianPairScore
- FinalPairRank
- ExitDecision
- MicrostructureExitResult

Important:

- All advanced outputs must obey point-in-time replay rules.
- If an advanced ML score is unavailable at timestamp t, return null for that score.
- Do not use current/latest ML scores for historical timestamps unless explicitly marked as approximate.
- Hard validation remains the gate.
- Invalid pairs must not be displayed as valid replay candidates.
- Shadow-mode recommendations must be labeled as shadow recommendations, not executed trades.

Replay marker fields should optionally include:

- hard_validation_valid
- regime_name
- regime_confidence
- break_risk
- bayesian_posterior
- final_rank_score
- microstructure_risk
- exit_score
- ev_hold_value_usdt
- quality_gate_passed

================================================================================
MVP REPLAY BOUNDARY
================================================================================

Phase 2 replay can become as complex as the live bot if not scoped carefully.

For MVP, implement simplified replay using only:

- rolling Z-score threshold
- persistence check
- hard validation result if available
- curator state
- pair health state
- liquidity/orderbook freshness
- active replay position state

MVP should not require these advanced modules:

- Bayesian scoring
- LinUCB / bandit scoring
- probabilistic EV exit manager
- dynamic partial exit sizing
- learned exit policy

Add advanced replay in Phase 2.5 after the core v3.1 scoring pipeline is stable.

Phase 2.5 advanced replay may add:

- RegimeDetectionResult
- BayesianPairScore
- FinalPairRank
- ExitDecision
- MicrostructureExitResult
- shadow-mode ML recommendations

================================================================================
STRICT NO-LOOKAHEAD RULE
================================================================================

Replay markers must use only data available up to that timestamp.

At candle timestamp t, replay logic may use only:

- candles <= t
- rolling mean/std computed up to t
- rolling hedge ratio computed up to t
- rolling cointegration result computed up to t
- rolling zero-crossing count up to t
- rolling Z-score computed up to t
- liquidity/orderbook snapshot known at t
- curator state known at t
- pair health state known at t
- bot config known at t
- quality gate status known at t

Replay logic must NOT use:

- future candles
- future rolling mean/std
- future hedge ratio
- future cointegration result
- future exit result
- future knowledge that the spread reverted later
- full-window hindsight
- full-series normalization
- current hedge-ratio hindsight
- today's curator state for historical candles
- current config silently applied to historical candles

If any replay calculation needs unavailable historical data, mark it as:

INSUFFICIENT_DATA

Do not silently use future data.

================================================================================
REPLAY SNAPSHOT — INTERFACE-LEVEL NO-LOOKAHEAD ENFORCEMENT
================================================================================


-------------------------------------------------------------------------------
FrozenCointegrationResult
-------------------------------------------------------------------------------

Do not store a raw dict in ReplaySnapshot for cointegration_result_until_t.

Use a frozen explicit result type:

@dataclass(frozen=True)
class FrozenCointegrationResult:
    p_value: float | None
    adf_stat: float | None
    hedge_ratio: float | None
    zero_crossings: int | None
    is_valid: bool
    reasons: tuple[str, ...]

ReplaySnapshot field:

cointegration_result_until_t: FrozenCointegrationResult | None

If there is insufficient history:

cointegration_result_until_t = None

and replay status must be:

ReplayMarkerStatus.INSUFFICIENT_DATA

with block reason:

BlockReason.INSUFFICIENT_HISTORY

-------------------------------------------------------------------------------
FrozenOrderBookSnapshot / Read-Only Orderbook Guidance
-------------------------------------------------------------------------------

If an orderbook snapshot is stored inside ReplaySnapshot, do not pass a mutable live runtime object.

Preferred:

@dataclass(frozen=True)
class FrozenOrderBookSnapshot:
    timestamp: int | float
    bid_depth_usdt: float | None
    ask_depth_usdt: float | None
    spread_bps: float | None
    slippage_bps: float | None
    liquidity_score: float | None
    is_fresh: bool
    source: str | None = None

ReplaySnapshot field:

orderbook_snapshot: FrozenOrderBookSnapshot | None

If the existing code already has OrderBookSnapshot and it is mutable, convert it into a frozen/read-only DTO before placing it in ReplaySnapshot.

-------------------------------------------------------------------------------
ActualBotEvent
-------------------------------------------------------------------------------

Define an adapter type for actual bot events used by Actual Bot Decision Overlay and ReplaySnapshot.

@dataclass(frozen=True)
class ActualBotEvent:
    event_id: str
    event_type: str
    pair: str
    timestamp: float

    side: str | None = None
    trade_id: str | None = None
    z_score: float | None = None
    spread: float | None = None
    reason: str | None = None

    pnl_usdt: float | None = None
    fees_usdt: float | None = None
    slippage_usdt: float | None = None

    # Use immutable metadata to preserve frozen semantics.
    metadata: tuple[tuple[str, object], ...] = ()

If the source event has a dict metadata field, convert it to a stable tuple of key/value pairs before constructing ActualBotEvent.

Example conversion:

metadata=tuple(sorted(source_metadata.items()))

-------------------------------------------------------------------------------
ExitAction Alignment With Exit Orchestrator
-------------------------------------------------------------------------------

Hedge-ratio drift may recommend a stop tightening action.

Recommended ExitAction enum:

class ExitAction(str, Enum):
    HOLD = "hold"
    WARN = "warn"
    TIGHTEN_STOP = "tighten_stop"
    PARTIAL_EXIT = "partial_exit"
    FULL_EXIT = "full_exit"
    SWITCH_AFTER_CLOSE = "switch_after_close"

If the current Exit Orchestrator does not support TIGHTEN_STOP yet, use this compatibility mapping:

action = "warn"
metadata = {
    "intent": "tighten_stop",
    "source": "hedge_ratio_drift"
}

But the preferred implementation is to add TIGHTEN_STOP to the orchestrator action enum.

The no-lookahead rule must be enforced in code, not only in comments.

The replay engine must evaluate one timestamp at a time using a ReplaySnapshot object.

The replay engine should not receive the full future candle array.

Required type:

@dataclass(frozen=True)
class ReplaySnapshot:
    pair: str
    timeframe: str
    timestamp: int

    # Data available only up to this timestamp.
    # Use immutable tuples to keep ReplaySnapshot read-only and safe.
    candles_until_t: tuple["Candle", ...]
    zscore_until_t: tuple[float, ...]
    spread_until_t: tuple[float, ...]

    # Optional rolling values computed only from data <= t.
    rolling_mean_until_t: float | None
    rolling_std_until_t: float | None
    hedge_ratio_until_t: float | None
    cointegration_result_until_t: "FrozenCointegrationResult | None"
    zero_crossing_count_until_t: int | None

    # State known at or before this timestamp.
    curator_state: "CuratorState"
    curator_state_source: str
    pair_health_state: str | None
    orderbook_snapshot: "FrozenOrderBookSnapshot | None"
    config_snapshot: "ReplayConfigSnapshot"
    config_source: str

    # Actual bot event context at timestamp, if any.
    actual_events_at_t: tuple["ActualBotEvent", ...]


-------------------------------------------------------------------------------
ReplayConfigSnapshot
-------------------------------------------------------------------------------

Do not pass the entire current live config object into historical replay.

Use a point-in-time config snapshot containing only replay-relevant fields.

@dataclass(frozen=True)
class ReplayConfigSnapshot:
    config_version: str
    config_source: str  # "historical" or "current_approximate"

    entry_z_threshold: float
    exit_z_threshold: float
    persistence_candles: int
    max_hold_seconds: float
    min_zero_crossings: int

    min_liquidity_score: float | None = None
    max_orderbook_age_ms: float | None = None
    max_spread_bps: float | None = None
    max_slippage_bps: float | None = None

    # Hedge-ratio sizing config active at timestamp t.
    hedge_ratio_sizing_enabled: bool = False
    hedge_sizing_mode: str = "equal_notional"  # "equal_notional" | "gross_normalized_beta"
    min_hedge_ratio: float = 0.20
    max_hedge_ratio: float = 5.00
    reject_negative_hedge_ratio: bool = True
    max_hedge_sizing_error_pct: float = 0.10
    max_hedge_ratio_drift_pct: float = 0.20
    severe_hedge_ratio_drift_pct: float = 0.35
    min_cointegration_window: int = 120

    warning: str | None = None

If historical config is unavailable and current config is used:

config_source = "current_approximate"
warning = "Historical config unavailable; current config used for replay."

-------------------------------------------------------------------------------
Safe Snapshot Storage Note
-------------------------------------------------------------------------------

ReplaySnapshot may use:

- immutable tuples
- safe pandas DataFrame slices/views
- read-only rolling window objects

as long as the replay engine cannot access data after timestamp t.

The implementation must enforce the same rule:

snapshot only contains data <= t.

If a dataframe slice is used, it must be physically restricted to rows <= t.
Do not pass the full dataframe with an index pointer and trust replay logic not to look ahead.


Replay loop pattern:

for i, candle in enumerate(candles):
    snapshot = ReplaySnapshot(
        pair=pair,
        timeframe=timeframe,
        timestamp=candle.timestamp,
        candles_until_t=tuple(candles[: i + 1]),
        zscore_until_t=tuple(z_scores_until_t),
        spread_until_t=tuple(spreads_until_t),
        curator_state=curator_state_at(candle.timestamp),
        config_snapshot=config_at(candle.timestamp),
        orderbook_snapshot=orderbook_at(candle.timestamp),
        actual_events_at_t=actual_events_at(candle.timestamp),
        ...
    )

    replay_engine.evaluate(snapshot)


-------------------------------------------------------------------------------
Incremental Indicator Rule
-------------------------------------------------------------------------------

Do not precompute full-series indicators and then slice them.

Forbidden:

z_scores = compute_zscore(all_candles)
hedge_ratios = compute_hedge_ratio(all_candles)
cointegration_results = compute_cointegration(all_candles)

for i, candle in enumerate(candles):
    snapshot = ReplaySnapshot(
        zscore_until_t=z_scores[: i + 1],
        ...
    )

Reason:

The full-series values may already contain future-derived information.

Required:

At each timestamp i, compute indicators using only candles[: i + 1]:

candles_until_t = candles[: i + 1]

z_scores_until_t = compute_zscore_point_in_time(candles_until_t)
hedge_ratio_until_t = compute_hedge_ratio_point_in_time(candles_until_t)
cointegration_result_until_t = compute_cointegration_point_in_time(candles_until_t)

snapshot = ReplaySnapshot(
    candles_until_t=tuple(candles_until_t),
    zscore_until_t=tuple(z_scores_until_t),
    spread_until_t=tuple(spreads_until_t),
    ...
)

Exception:

A precomputed series is allowed only if the function is proven point-in-time safe, for example:

- rolling(window).mean() with no centered windows
- rolling(window).std() with no future shift
- expanding calculations that use only past rows

If precomputation is used, document it with:

indicator_source = "precomputed_point_in_time_safe"

Otherwise compute inside the loop.

Forbidden pattern:

z_series = compute_zscore(all_candles)
for t in timestamps:
    replay_at(t, z_series[t])

Reason:

Computing the full z-score series first may accidentally use full-series information, future normalization, or future hedge-ratio hindsight.

================================================================================
CURATOR STATE SOURCING: curator_state_at(t)
================================================================================

The replay engine must not use the current curator state for historical timestamps.

curator_state_at(t) must be sourced in this order:

1. Historical curator state log table / event store

Use historical state transitions:

- pair
- timestamp
- previous_state
- new_state
- reason
- source

For timestamp t:

- use the latest curator state transition where transition_timestamp <= t
- if exact timestamp does not exist, use last known state before t

2. Re-derived point-in-time state

If no historical state log exists, re-derive curator state using only data available up to t:

- closed candles <= t
- point-in-time cointegration result
- point-in-time zero-crossing count
- point-in-time liquidity state
- point-in-time pair health logic

If re-derivation is used, set:

curator_state_source = "recomputed_point_in_time"

3. Unknown / insufficient data

If neither historical log nor safe recomputation is available:

curator_state = "insufficient_history"
curator_state_source = "unavailable"
replay status = "insufficient_data"

Do not emit replay_entry_candidate as valid.

Never use today's current pair state to judge historical replay candles unless explicitly marked:

curator_state_source = "current_approximate"

If current approximate state is used, markers must include warning metadata.

================================================================================
CONFIG SOURCING: config_at(t)
================================================================================

Replay should use the bot config active at timestamp t.

config_at(t) must be sourced in this order:

1. Historical config version log

Use config version active at timestamp t.

Required fields:

- config_version
- activated_at
- config values
- source

2. Current config fallback

If historical config versioning is unavailable:

- use current config
- set config_source = "current_approximate"
- include warning in replay marker metadata

Do not silently use current config for historical replay.

Replay marker metadata should include:

{
  "config_version": "v12",
  "config_source": "historical"
}

or:

{
  "config_version": "current",
  "config_source": "current_approximate",
  "warning": "Historical config unavailable; current config used for replay."
}

================================================================================
MARKER ENUMS AND CATEGORIES
================================================================================

Separate markers into three semantic categories:

A. Statistical markers
B. Replay markers
C. Actual bot markers

Do not mix these into one vague marker type.

-------------------------------------------------------------------------------
MarkerCategory
-------------------------------------------------------------------------------

class MarkerCategory(str, Enum):
    STATISTICAL = "statistical"
    REPLAY = "replay"
    ACTUAL = "actual"

-------------------------------------------------------------------------------
StatisticalMarkerType
-------------------------------------------------------------------------------

class StatisticalMarkerType(str, Enum):
    HISTORICAL_MEAN_CROSSING = "historical_mean_crossing"
    ZERO_CROSSING = "zero_crossing"
    EXTREME_Z_PEAK = "extreme_z_peak"

-------------------------------------------------------------------------------
ReplayMarkerType
-------------------------------------------------------------------------------

class ReplayMarkerType(str, Enum):
    REPLAY_ENTRY_CANDIDATE = "replay_entry_candidate"
    REPLAY_EXIT_CANDIDATE = "replay_exit_candidate"
    REPLAY_BLOCKED_SIGNAL = "replay_blocked_signal"

-------------------------------------------------------------------------------
ActualMarkerType
-------------------------------------------------------------------------------

class ActualMarkerType(str, Enum):
    ACTUAL_ENTRY = "actual_entry"
    ACTUAL_EXIT = "actual_exit"
    ACTUAL_PARTIAL_EXIT = "actual_partial_exit"
    ACTUAL_BLOCKED_SIGNAL = "actual_blocked_signal"
    ACTUAL_REGIME_EXIT = "actual_regime_exit"
    ACTUAL_MANUAL_EXIT = "actual_manual_exit"
    ACTUAL_ADVANCED_ML_SHADOW_RECOMMENDATION = "actual_advanced_ml_shadow_recommendation"


-------------------------------------------------------------------------------
CuratorState
-------------------------------------------------------------------------------

class CuratorState(str, Enum):
    TRADABLE = "tradable"
    ANALYSIS_ONLY = "analysis_only"
    EXCLUDED = "excluded"
    HOSPITAL = "hospital"
    GRAVEYARD = "graveyard"
    STALE_DATA = "stale_data"
    INSUFFICIENT_HISTORY = "insufficient_history"
    LOW_LIQUIDITY = "low_liquidity"


-------------------------------------------------------------------------------
ReplayMarkerStatus
-------------------------------------------------------------------------------

Use an enum for replay marker status.

class ReplayMarkerStatus(str, Enum):
    VALID_CANDIDATE = "valid_candidate"
    BLOCKED_CANDIDATE = "blocked_candidate"
    IGNORED_CANDIDATE = "ignored_candidate"
    INSUFFICIENT_DATA = "insufficient_data"

Do not use raw status strings directly.

All replay markers should use one of these values.

-------------------------------------------------------------------------------
BlockReason
-------------------------------------------------------------------------------

Use an enum for block reasons so strings stay consistent.

class BlockReason(str, Enum):
    CURATOR_NOT_TRADABLE = "curator_not_tradable"
    ANALYSIS_ONLY = "analysis_only"
    PAIR_EXCLUDED = "pair_excluded"
    PAIR_IN_HOSPITAL = "pair_in_hospital"
    PAIR_IN_GRAVEYARD = "pair_in_graveyard"
    STALE_DATA = "stale_data"
    INSUFFICIENT_HISTORY = "insufficient_history"
    COINTEGRATION_INVALID = "cointegration_invalid"
    ADF_FAILED = "adf_failed"
    ZERO_CROSSINGS_TOO_LOW = "zero_crossings_too_low"
    HEDGE_RATIO_UNSTABLE = "hedge_ratio_unstable"
    HEDGE_RATIO_INVALID = "hedge_ratio_invalid"
    HEDGE_RATIO_DRIFT = "hedge_ratio_drift"
    LIQUIDITY_FAILED = "liquidity_failed"
    ORDER_CAPACITY_FAILED = "order_capacity_failed"
    QUALITY_GATE_FAILED = "quality_gate_failed"
    POSITION_ALREADY_OPEN = "position_already_open"
    ORDERBOOK_STALE = "orderbook_stale"
    REGIME_BREAK_RISK_HIGH = "regime_break_risk_high"
    Z_PERSISTENCE_FAILED = "z_persistence_failed"
    CONFIG_UNAVAILABLE = "config_unavailable"
    CURATOR_STATE_UNAVAILABLE = "curator_state_unavailable"
    CURATOR_LOW_LIQUIDITY = "curator_low_liquidity"

Rule:

block_reasons must contain BlockReason enum values only.

Do not use ad-hoc strings from bot logs directly.

If bot logs use different internal strings, map them into BlockReason values before returning chart audit markers.

Use BlockReason.CURATOR_LOW_LIQUIDITY when the curator state itself is LOW_LIQUIDITY.
Use BlockReason.LIQUIDITY_FAILED when the live/point-in-time liquidity gate fails at signal time.



================================================================================
ENTRY ID FORMAT
================================================================================

Every actual_entry and replay_entry_candidate must have a stable entry_id.

This entry_id is used for:

- lazy counterfactual loading
- linking counterfactual exit results to an entry
- linking selected chart marker to detail panels

Rules:

Actual entry:

entry_id = f"actual_{trade_id}"

Example:

actual_T123

Replay entry:

entry_id = f"replay_{pair_key}_{timestamp}_{side}"

Where:

- pair_key = pair symbols joined and sanitized
- timestamp = replay entry timestamp
- side = BUY_SPREAD or SELL_SPREAD

Example:

replay_CRV-USDT-SWAP_XAG-USDT-SWAP_1715000200_BUY_SPREAD

Do not allow replay entry IDs to collide with actual entry IDs.

All counterfactual requests must use this entry_id:

GET /api/chart-audit/counterfactual?entry_id={entry_id}


================================================================================
STATISTICAL MARKERS
================================================================================

These describe spread behavior only.

They are NOT bot decisions.

Marker types:

- historical_mean_crossing
- zero_crossing
- extreme_z_peak

Yellow dots should be renamed from:

Chart crossing

to:

historical_mean_crossing

Tooltip must clearly say:

"Historical mean crossing. This is not a trade signal."

Example:

{
  "marker_category": "statistical",
  "marker_type": "historical_mean_crossing",
  "timestamp": 1715000000,
  "z_score": 0.04,
  "spread": -4.1516,
  "label": "Historical mean crossing",
  "is_trade_signal": false
}

================================================================================
REPLAY MARKERS
================================================================================

Replay markers are hypothetical point-in-time bot decisions.

They answer:

"If the bot were evaluating this pair at this exact timestamp, what would it have considered?"

Marker types:

- replay_entry_candidate
- replay_exit_candidate
- replay_blocked_signal

Visual style:

- green hollow triangle up = replay BUY_SPREAD candidate
- red hollow triangle down = replay SELL_SPREAD candidate
- blue hollow diamond = replay exit candidate
- amber hollow X = replay blocked signal

Replay markers are hypothetical and must be visually hollow/unfilled.

Replay marker schema:

{
  "marker_category": "replay",
  "marker_type": "replay_entry_candidate",
  "entry_id": "replay_CRV-USDT-SWAP_XAG-USDT-SWAP_1715000200_BUY_SPREAD",
  "timestamp": 1715000200,
  "side": "BUY_SPREAD",
  "z_score": -2.14,
  "spread": -4.1781,
  "status": "valid_candidate",
  "curator_state": "tradable",
  "curator_state_source": "historical",
  "config_source": "historical",
  "passed": true,
  "block_reasons": [],
  "reason": "z threshold and persistence passed",
  "metadata": {
    "config_version": "v12",
    "hard_validation_valid": true,
    "regime_name": "mean_reverting",
    "bayesian_posterior": 0.74,
    "final_rank_score": 0.81,
    "break_risk": 0.18
  }
}


-------------------------------------------------------------------------------
Replay Exit Candidate Schema
-------------------------------------------------------------------------------

replay_exit_candidate must have a complete schema.

Example:

{
  "marker_category": "replay",
  "marker_type": "replay_exit_candidate",
  "entry_id": "replay_CRV-USDT-SWAP_XAG-USDT-SWAP_1715000200_BUY_SPREAD",
  "timestamp": 1715000400,
  "side": "BUY_SPREAD",
  "z_score": -0.42,
  "spread": -4.1612,
  "status": "valid_candidate",
  "reason": "abs(z_score) <= exit_z_threshold",
  "exit_trigger": "z_reversion",
  "curator_state": "tradable",
  "curator_state_source": "historical",
  "config_source": "historical",
  "passed": true,
  "block_reasons": [],
  "metadata": {
    "entry_timestamp": 1715000200,
    "entry_z": -2.14,
    "exit_z_threshold": 0.50,
    "hedge_ratio_at_entry": 1.80,
    "hedge_ratio_at_exit": 1.76,
    "hedge_ratio_drift_pct": 0.022,
    "exit_reason": "z_reversion"
  }
}

If the exit is triggered by hedge-ratio drift:

{
  "marker_category": "replay",
  "marker_type": "replay_exit_candidate",
  "entry_id": "replay_CRV-USDT-SWAP_XAG-USDT-SWAP_1715000200_BUY_SPREAD",
  "timestamp": 1715000500,
  "side": "BUY_SPREAD",
  "z_score": -0.88,
  "spread": -4.1705,
  "status": "valid_candidate",
  "reason": "hedge ratio drift exceeded configured threshold",
  "exit_trigger": "hedge_ratio_drift",
  "metadata": {
    "entry_hedge_ratio": 1.80,
    "current_hedge_ratio": 1.28,
    "hedge_ratio_drift_pct": 0.2889,
    "max_hedge_ratio_drift_pct": 0.20
  }
}


================================================================================
ACTUAL BOT MARKERS
================================================================================

Actual markers come from actual bot logs, DB events, executed orders, or live trade records.

Marker types:

- actual_entry
- actual_exit
- actual_partial_exit
- actual_blocked_signal
- actual_regime_exit
- actual_manual_exit
- actual_advanced_ml_shadow_recommendation

Visual style:

- solid green triangle up = actual BUY_SPREAD entry
- solid red triangle down = actual SELL_SPREAD entry
- solid blue diamond = actual exit
- solid amber X = actual blocked signal

Actual markers must be visually solid/filled.

Actual markers must NOT be generated from chart inference.
They must come from real bot events, DB rows, trade logs, or execution records.

================================================================================
IMPLEMENTATION ORDER
================================================================================

-------------------------------------------------------------------------------
Phase 1: Actual Bot Decision Overlay
-------------------------------------------------------------------------------

Start with the easiest and most reliable source of truth: real bot events.

Use bot DB/log events:

- actual entries
- actual exits
- actual partial exits
- actual blocked signals
- actual PnL
- fees
- slippage
- exit reason
- block reason

Output marker types:

- actual_entry
- actual_exit
- actual_partial_exit
- actual_blocked_signal
- actual_regime_exit
- actual_manual_exit
- actual_advanced_ml_shadow_recommendation

Purpose:

This gives immediate value because it shows what the bot actually did,
not what the chart appears to suggest.

Actual markers must come from real bot events, not inferred from Z-score.

Visual rule:

- solid green triangle = actual BUY_SPREAD entry
- solid red triangle = actual SELL_SPREAD entry
- solid blue diamond = actual exit
- solid amber X = actual blocked signal

Tooltip should include:

- trade_id
- side
- z_score
- spread
- reason
- pnl_usdt
- fees_usdt
- slippage_usdt
- timestamp
- pair
- exit reason or block reason

Do not change live trading behavior.

-------------------------------------------------------------------------------
Phase 2: Curator-Aware Point-In-Time Replay
-------------------------------------------------------------------------------

Generate hypothetical replay markers using only data available up to each candle timestamp.

Replay must use ReplaySnapshot.

Replay must use:

- candles <= timestamp
- rolling Z-score up to timestamp
- rolling hedge ratio up to timestamp
- rolling cointegration result up to timestamp
- rolling zero-crossing count up to timestamp
- curator state at timestamp
- liquidity/orderbook state at timestamp
- pair health state at timestamp
- quality gate state at timestamp
- bot config at timestamp

Replay must not use:

- future candles
- future reversion
- future exit result
- full-window hindsight
- current hedge-ratio hindsight
- today's curator state unless marked current_approximate
- current config unless marked current_approximate

Output marker types:

- replay_entry_candidate
- replay_exit_candidate
- replay_blocked_signal

Purpose:

This shows what the bot would have considered at that exact point in time.

Replay marker examples:

- green hollow triangle = replay BUY_SPREAD candidate
- red hollow triangle = replay SELL_SPREAD candidate
- blue hollow diamond = replay exit candidate
- amber hollow X = replay blocked signal

Curator states:

- tradable
- analysis_only
- excluded
- hospital
- graveyard
- stale_data
- insufficient_history
- low_liquidity

Blocked replay signals must include explicit BlockReason values.

Purpose:

This gives learning value without changing live trading.


-------------------------------------------------------------------------------
Phase 2.25: Hedge-Ratio Exposure Alignment
-------------------------------------------------------------------------------

Before integrating Advanced ML replay metadata, align the actual executed position with the hedge-ratio-aware spread model.

Problem:

The spread and Z-score are computed using:

spread = log(asset1) - hedge_ratio * log(asset2)

But if the bot enters both legs using equal USDT notional, the actual exposure does not match the modeled spread.

Goal:

Make entry sizing, replay markers, actual markers, and exit audit aware of hedge ratio.

This phase has four parts:

1. Hedge-ratio-aware entry sizing
2. Hedge-ratio-at-entry persistence
3. Hedge-ratio drift monitoring during open trades
4. Chart audit metadata for hedge-ratio sizing and drift

Important:

This phase may touch live entry sizing logic, so implement it separately and carefully.

Recommended rollout:

- first implement as sizing preview / shadow log
- compare current equal-notional sizing vs hedge-ratio gross-normalized sizing
- then enable live hedge-ratio sizing only after validation

Do not change live trading behavior silently.

Add config flag:

hedge_ratio_sizing_enabled: bool = False

When false:

- keep current sizing behavior
- log what hedge-ratio sizing would have produced

When true:

- use gross-normalized hedge-ratio sizing for new entries only

Do not auto-rebalance already-open positions in this phase.

-------------------------------------------------------------------------------
Hedge-Ratio-Aware Entry Sizing
-------------------------------------------------------------------------------

Use a fresh hedge ratio at entry time.

Do not use stale hedge ratio from discovery CSV unless no better source exists and it is explicitly marked stale/approximate.

Preferred source order:

1. fresh evaluate_cointegration() result at entry time
2. latest monitoring cointegration metrics computed point-in-time
3. discovery CSV hedge ratio only as fallback, marked "discovery_stale"

Entry sizing formula:

beta = abs(hedge_ratio)

gross_pair_notional = target_total_pair_notional_usdt

leg1_notional = gross_pair_notional / (1.0 + beta)
leg2_notional = gross_pair_notional * beta / (1.0 + beta)

Direction logic:

If spread = log(asset1) - beta * log(asset2)

BUY_SPREAD:

- long asset1
- short asset2

SELL_SPREAD:

- short asset1
- long asset2

Use the same notional ratio for both directions:

leg2_notional ~= beta * leg1_notional

Config:

hedge_sizing_mode: "equal_notional" | "gross_normalized_beta"
hedge_ratio_sizing_enabled: bool = False
min_hedge_ratio: float = 0.20
max_hedge_ratio: float = 5.00
reject_negative_hedge_ratio: bool = True
max_hedge_sizing_error_pct: float = 0.10

Validation:

If hedge_ratio is missing, NaN, infinite, negative when reject_negative_hedge_ratio=True, or outside allowed range:

- block live hedge-ratio sizing
- fall back to safe behavior based on config
- add block reason or warning:
  hedge_ratio_invalid

-------------------------------------------------------------------------------
Persist Hedge Ratio at Entry
-------------------------------------------------------------------------------

Every actual entry event should store:

- entry_hedge_ratio
- hedge_ratio_source
- hedge_sizing_mode
- hedge_ratio_sizing_enabled
- target_gross_pair_notional_usdt
- target_leg1_notional_usdt
- target_leg2_notional_usdt
- actual_leg1_notional_usdt
- actual_leg2_notional_usdt
- hedge_sizing_error_pct
- leg1_side
- leg2_side

This data must be included in actual_entry marker metadata when available.

Actual entry marker should include:

{
  "entry_hedge_ratio": 1.8,
  "hedge_ratio_source": "fresh_cointegration_at_entry",
  "hedge_sizing_mode": "gross_normalized_beta",
  "target_gross_pair_notional_usdt": 1500,
  "target_leg1_notional_usdt": 535.71,
  "target_leg2_notional_usdt": 964.29,
  "actual_leg1_notional_usdt": 534.90,
  "actual_leg2_notional_usdt": 963.80,
  "hedge_sizing_error_pct": 0.0012,
    "hedge_ratio_execution_error_pct": 0.0021
}


-------------------------------------------------------------------------------
Hedge Sizing Error Formulas
-------------------------------------------------------------------------------

Define hedge_sizing_error_pct explicitly.

Primary definition:

hedge_sizing_error_pct = max(
    abs(actual_leg1_notional_usdt - target_leg1_notional_usdt)
    / max(target_leg1_notional_usdt, 1e-9),

    abs(actual_leg2_notional_usdt - target_leg2_notional_usdt)
    / max(target_leg2_notional_usdt, 1e-9),
)

Meaning:

This measures how far the executed leg notionals are from the intended target notionals.

Also compute hedge_ratio_execution_error_pct:

actual_ratio = actual_leg2_notional_usdt / max(actual_leg1_notional_usdt, 1e-9)

hedge_ratio_execution_error_pct = abs(actual_ratio - beta) / max(beta, 1e-9)

Meaning:

This measures how far the executed leg2/leg1 notional ratio is from the target beta.

Store both when possible:

- hedge_sizing_error_pct
- hedge_ratio_execution_error_pct

Do not use ambiguous formulas.


-------------------------------------------------------------------------------
Hedge-Ratio Drift Monitoring
-------------------------------------------------------------------------------

During open trades, monitor whether the current hedge ratio has drifted materially from the entry hedge ratio.

Formula:

hedge_ratio_drift_pct = abs(current_hedge_ratio - entry_hedge_ratio) / max(abs(entry_hedge_ratio), 1e-9)

Config:

max_hedge_ratio_drift_pct: float = 0.20
severe_hedge_ratio_drift_pct: float = 0.35

If hedge_ratio_drift_pct > max_hedge_ratio_drift_pct:

Emit an ExitCandidate through the Exit Orchestrator:

source = "hedge_ratio_drift"
priority = "quality"
action = "tighten_stop" | "partial_exit" | "full_exit"
severity = clamp01(hedge_ratio_drift_pct / severe_hedge_ratio_drift_pct)
reason = "Hedge ratio drift exceeded configured threshold"
blockable_by_net_profit_guard = False

Do not directly close from random modules.

This belongs in the Exit Orchestrator as a Pair Quality exit candidate.

Suggested severity behavior:

- drift < max_hedge_ratio_drift_pct:
  no exit candidate, log only

- max_hedge_ratio_drift_pct <= drift < severe_hedge_ratio_drift_pct:
  candidate action = "tighten_stop" or "partial_exit"

- drift >= severe_hedge_ratio_drift_pct:
  candidate action = "full_exit"

-------------------------------------------------------------------------------
Chart Audit Metadata for Hedge Ratio
-------------------------------------------------------------------------------

Actual markers should include hedge-ratio sizing details when available.

Replay markers should include:

- hedge_ratio_at_t
- hedge_ratio_source
- replay_sizing_mode
- target_leg1_notional_usdt
- target_leg2_notional_usdt
- hedge_ratio_valid

If hedge ratio is invalid at replay timestamp:

- emit replay_blocked_signal
- block reason = hedge_ratio_unstable or hedge_ratio_invalid

If hedge ratio drift is detected during an open replay/actual trade:

- replay exit reason may include hedge_ratio_drift
- actual exit marker may include hedge_ratio_drift_pct if logged

-------------------------------------------------------------------------------
Counterfactual Hedge-Ratio Sizing Study
-------------------------------------------------------------------------------

Phase 3 counterfactual exit study should include a sizing comparison:

- equal_notional_pnl
- hedge_ratio_sized_pnl
- pnl_delta_usdt
- pnl_delta_pct
- max_adverse_excursion_equal_notional_usdt
- max_adverse_excursion_hedged_usdt
- max_favorable_excursion_equal_notional_usdt
- max_favorable_excursion_hedged_usdt

Purpose:

Prove whether hedge-ratio sizing would have improved the trade outcome.

This comparison is analysis-only.

It must not modify live trading behavior.

-------------------------------------------------------------------------------
Phase 2.5: Advanced ML Replay Integration
-------------------------------------------------------------------------------

Only after MVP replay works, integrate advanced ML pipeline outputs.

Use point-in-time versions of:

- HardValidationResult
- ValidPairCandidate
- RegimeDetectionResult
- BayesianPairScore
- FinalPairRank
- ExitDecision
- MicrostructureExitResult

The replay marker should show if advanced scoring would have:

- allowed the signal
- blocked the signal
- recommended exit
- recommended partial exit
- recommended hold

Do not let this affect live trading.

-------------------------------------------------------------------------------
Phase 3: Counterfactual Exit Study
-------------------------------------------------------------------------------

For each actual entry or replay entry, simulate alternative exit policies.

Counterfactuals may be computed for:

- actual_entry
- replay_entry_candidate

Counterfactuals must NOT be computed for:

- historical_mean_crossing
- replay_blocked_signal unless explicitly requested for analysis
- actual_blocked_signal unless explicitly requested for analysis

Compare:

- actual exit
- exit_at_z_0_50
- exit_at_z_0_35
- exit_at_z_0_00
- exit_on_mean_crossing
- exit_on_trailing_stop
- exit_on_max_hold
- exit_on_adverse_acceleration
- exit_on_regime_break
- exit_on_ev_manager
- exit_on_microstructure_stress

For each policy, compute:

- exit timestamp
- exit z-score
- estimated pnl
- hold time
- max adverse excursion
- max favorable excursion
- estimated fees
- estimated slippage
- exit reason

Purpose:

This helps tune the exit manager.

Important:

Counterfactual studies may use future data only after the entry marker already exists.

Counterfactual results must not affect entry marker generation.

Counterfactual results are analysis-only and must not change live trading behavior.

-------------------------------------------------------------------------------
Phase 4: Decision Score Timeline
-------------------------------------------------------------------------------

Add lower panels that show the bot's internal decision scores over time.

Add panels for:

- regime confidence
- regime break risk
- Bayesian posterior
- LinUCB score
- EV hold value
- microstructure risk
- liquidity score
- trade quality score
- exit score
- curator state

Purpose:

This turns the chart from a price picture into a full decision audit dashboard.

The chart should answer:

- What looked like an opportunity?
- Was the bot allowed to trade it?
- Did the bot actually trade it?
- Why was a signal blocked?
- Did the exit happen too early or too late?
- Would another exit rule have performed better?

================================================================================
CURATOR-AWARE POINT-IN-TIME REPLAY
================================================================================

Implement a backend replay engine that scans each candle sequentially.

The replay must simulate the bot's decision process at each timestamp.

The replay engine should know curator state at each timestamp.

Possible curator states:

- tradable
- analysis_only
- excluded
- hospital
- graveyard
- stale_data
- insufficient_history
- low_liquidity

Replay should classify each detected signal as:

- valid_candidate
- blocked_candidate
- ignored_candidate
- insufficient_data


-------------------------------------------------------------------------------
Minimum Window Behavior for Hedge Ratio / Cointegration
-------------------------------------------------------------------------------

Do not compute hedge_ratio_until_t when there is insufficient historical data.

Rule:

if len(candles_until_t) < config_snapshot.min_cointegration_window:
    hedge_ratio_until_t = None
    cointegration_result_until_t = None
    replay_status = ReplayMarkerStatus.INSUFFICIENT_DATA
    block_reasons = [BlockReason.INSUFFICIENT_HISTORY]

Do not emit replay_entry_candidate as valid when hedge ratio or cointegration is unavailable because of insufficient history.

This case should produce either:

- no marker, if no threshold was touched, or
- replay_blocked_signal / insufficient_data marker if the Z threshold was touched but the bot could not evaluate the setup.


-------------------------------------------------------------------------------
Entry Candidate Logic
-------------------------------------------------------------------------------

BUY_SPREAD candidate if:

- z_score <= -entry_z_threshold
- persistence check passed
- pair has no active replay position
- curator state == tradable
- cointegration valid at timestamp
- ADF valid at timestamp
- zero-crossing requirement passed
- hedge ratio sane
- liquidity check passed
- order capacity check passed
- quality gate passed
- pair not in hospital
- pair not in graveyard
- orderbook not stale

SELL_SPREAD candidate if:

- z_score >= +entry_z_threshold
- same validations as above

If Z threshold is reached but any gate fails, emit:

replay_blocked_signal

Blocked marker must include explicit BlockReason values.

-------------------------------------------------------------------------------
Replay Exit Candidate Logic
-------------------------------------------------------------------------------

If replay position is open, emit replay_exit_candidate when any configured exit rule triggers:

- abs(z_score) <= exit_z_threshold
- spread crosses mean
- trailing stop hit
- stall detected
- divergence detected
- max hold reached
- regime break detected
- adverse acceleration detected
- EV manager recommends exit
- microstructure risk recommends exit

For MVP, implement simple replay exits first:

- exit at abs(z_score) <= exit_z_threshold
- exit at max hold
- exit on divergence
- exit on curator state no longer tradable

Advanced EV exits can be added later.

================================================================================
ACTUAL BOT DECISION OVERLAY
================================================================================

Overlay real bot decisions from logs, DB, or trade event store.

Actual overlay must include:

- actual entries
- actual exits
- actual partial exits
- actual blocked signals
- quality gate blocks
- liquidity blocks
- cointegration invalid blocks
- regime break exits
- max hold exits
- manual exits
- advanced ML shadow recommendations if available

Actual markers must not be generated from chart inference.
They must come from real bot events.

Actual entry marker schema:

{
  "marker_category": "actual",
  "marker_type": "actual_entry",
  "entry_id": "actual_T123",
  "timestamp": 1715000000,
  "original_event_timestamp": 1715000023.527,
  "side": "BUY_SPREAD",
  "z_score": -2.14,
  "spread": -4.1781,
  "trade_id": "T123",
  "reason": "entry_signal_confirmed",
  "pnl_usdt": null,
  "fees_usdt": null,
  "slippage_usdt": null,
  "metadata": {
    "entry_hedge_ratio": 1.8,
    "hedge_ratio_source": "fresh_cointegration_at_entry",
    "hedge_sizing_mode": "gross_normalized_beta",
    "hedge_ratio_sizing_enabled": true,
    "target_gross_pair_notional_usdt": 1500,
    "target_leg1_notional_usdt": 535.71,
    "target_leg2_notional_usdt": 964.29,
    "actual_leg1_notional_usdt": 534.90,
    "actual_leg2_notional_usdt": 963.80,
    "hedge_sizing_error_pct": 0.0012,
    "hedge_ratio_execution_error_pct": 0.0021
  }
}

Actual exit marker schema:

{
  "marker_category": "actual",
  "marker_type": "actual_exit",
  "timestamp": 1715000400,
  "original_event_timestamp": 1715000421.245,
  "side": "BUY_SPREAD",
  "z_score": -0.35,
  "spread": -4.1612,
  "trade_id": "T123",
  "reason": "mean_reversion_exit",
  "pnl_usdt": 4.23,
  "fees_usdt": 0.18,
  "slippage_usdt": 0.07,
  "metadata": {}
}

Actual blocked marker schema:

{
  "marker_category": "actual",
  "marker_type": "actual_blocked_signal",
  "timestamp": 1715000300,
  "original_event_timestamp": 1715000312.993,
  "side": "SELL_SPREAD",
  "z_score": 2.05,
  "spread": -4.1310,
  "trade_id": null,
  "reason": "liquidity_failed",
  "block_reasons": ["liquidity_failed", "order_capacity_failed"],
  "metadata": {}
}

Actual ML shadow recommendation marker schema:

{
  "marker_category": "actual",
  "marker_type": "actual_advanced_ml_shadow_recommendation",
  "timestamp": 1715000450,
  "original_event_timestamp": 1715000450.221,
  "side": "BUY_SPREAD",
  "z_score": -0.62,
  "spread": -4.1660,
  "trade_id": "T123",
  "shadow_action": "PARTIAL_EXIT",
  "executed": false,
  "exit_score": 0.63,
  "ev_hold_value_usdt": -0.12,
  "regime": "mean_reverting",
  "reason": "Shadow EV manager recommended partial exit",
  "metadata": {
    "note": "Shadow mode recommendation only; not executed."
  }
}

================================================================================
COUNTERFACTUAL EXIT STUDY
================================================================================

For each actual entry or replay entry, run a counterfactual exit study.

Goal:

Compare how different exit policies would have performed.

Test exit policies:

- exit_at_z_0_50
- exit_at_z_0_35
- exit_at_z_0_00
- exit_on_mean_crossing
- exit_on_trailing_stop
- exit_on_max_hold
- exit_on_adverse_acceleration
- exit_on_regime_break
- exit_on_ev_manager
- exit_on_microstructure_stress


-------------------------------------------------------------------------------
Equal-Notional Counterfactual Baseline
-------------------------------------------------------------------------------

When comparing equal-notional PnL versus hedge-ratio-sized PnL, keep total gross exposure constant.

Definition:

equal_leg_notional = gross_pair_notional / 2.0

Equal-notional baseline:

leg1_notional = equal_leg_notional
leg2_notional = equal_leg_notional

Hedge-ratio-sized baseline:

beta = abs(hedge_ratio)
leg1_notional = gross_pair_notional / (1.0 + beta)
leg2_notional = gross_pair_notional * beta / (1.0 + beta)

This ensures the comparison isolates sizing method while keeping total gross capital the same.

Do not compare:

equal-notional using $X per leg

against

hedge-ratio sizing using $X and $X * beta

because that changes total exposure and makes the comparison unfair.


-------------------------------------------------------------------------------
CounterfactualExitResult Schema
-------------------------------------------------------------------------------

@dataclass
class CounterfactualExitResult:
    entry_id: str
    exit_strategy: str
    status: str  # "triggered", "not_triggered", "forced_close_at_window_end"

    hypothetical_exit_timestamp: int | None
    hypothetical_exit_z: float | None

    hypothetical_gross_pnl_usdt: float | None
    hypothetical_fees_usdt: float | None
    hypothetical_slippage_usdt: float | None
    hypothetical_net_pnl_usdt: float | None

    hold_seconds: int | None
    max_adverse_excursion_z: float | None
    max_favorable_excursion_z: float | None
    max_adverse_excursion_usdt: float | None
    max_favorable_excursion_usdt: float | None

    # Optional sizing comparison fields for Phase 2.25 / Phase 3.
    equal_notional_pnl_usdt: float | None = None
    hedge_ratio_sized_pnl_usdt: float | None = None
    pnl_delta_usdt: float | None = None
    pnl_delta_pct: float | None = None

    note: str


Units:

Use explicit unit fields.

Z-score excursion fields:

- max_adverse_excursion_z
- max_favorable_excursion_z

USDT excursion fields:

- max_adverse_excursion_usdt
- max_favorable_excursion_usdt

Do not use ambiguous fields named only:

- max_adverse_excursion
- max_favorable_excursion


If the counterfactual exit condition never triggers before the chart window ends:

- status = "not_triggered"
- hypothetical_exit_timestamp = None
- hypothetical_net_pnl_usdt = None
- note = "Exit condition did not trigger within selected chart window."

Optional forced close analysis:

If enabled, compute forced close at the last candle in the selected range:

- status = "forced_close_at_window_end"
- note must clearly say it was forced by analysis window end, not by strategy logic.

Important:

Counterfactual study is allowed to evaluate future outcomes only AFTER the entry marker already exists.

Do not use counterfactual future outcomes to create entry markers.

Counterfactual results are analysis only.

================================================================================
LAZY COUNTERFACTUAL LOADING
================================================================================

Counterfactual studies can be expensive.

Do not compute all counterfactuals for all replay entries on initial chart load.

Initial chart load should return:

- zscore_series
- statistical_markers
- replay_markers
- actual_markers
- decision_score_timeline if available

Counterfactuals should be lazy-loaded when:

- user clicks an actual_entry marker
- user clicks a replay_entry_candidate marker
- user opens a "Compare exits" panel

API:

GET /api/chart-audit/counterfactual?entry_id={entry_id}

Response:

{
  "entry_id": "actual_T123",
  "counterfactual_exit_results": [
    {
      "entry_id": "actual_T123",
      "exit_strategy": "exit_at_z_0_50",
      "status": "triggered",
      "hypothetical_exit_timestamp": 1715000300,
      "hypothetical_exit_z": -0.48,
      "hypothetical_gross_pnl_usdt": 2.30,
      "hypothetical_fees_usdt": 0.12,
      "hypothetical_slippage_usdt": 0.08,
      "hypothetical_net_pnl_usdt": 2.10,
      "hold_seconds": 1800,
      "max_adverse_excursion_z": -2.45,
      "max_favorable_excursion_z": -0.32,
      "max_adverse_excursion_usdt": -1.20,
      "max_favorable_excursion_usdt": 2.35,
      "note": "Z reverted to 0.50 exit threshold."
    }
  ]
}

================================================================================
DECISION SCORE TIMELINE
================================================================================

Add optional lower panels to explain bot decision quality over time.

Score series to support:

- regime_confidence
- regime_break_risk
- bayesian_posterior
- linucb_rank_score
- liquidity_score
- microstructure_risk
- EV_hold_value
- exit_score
- trade_quality_score
- curator_state_encoded


-------------------------------------------------------------------------------
Decision Timeline Downsampling
-------------------------------------------------------------------------------

Decision score timelines can become large.

Example:

7 days of 1-minute candles = 10,080 score rows.

API should support:

- max_timeline_points: int = 1440
- downsample_method: "last" | "mean" | "none"
- resolution query parameter, such as:
  - ?resolution=1m
  - ?resolution=5m
  - ?resolution=15m
  - ?resolution=1h

Default behavior:

- if number of points <= max_timeline_points, return as-is
- if number of points > max_timeline_points, downsample to fit
- default downsample_method = "last"

Downsampling rule:

For each bucket:

- "last" uses the latest score snapshot in the bucket
- "mean" averages numeric scores and uses the last categorical state
- "none" returns all points and may be slower

The API response should include:

{
  "timeline_resolution": "5m",
  "timeline_downsample_method": "last",
  "timeline_original_points": 10080,
  "timeline_returned_points": 1440
}


Source rules:

1. Stored live score snapshots

If the bot stores decision score snapshots per tick, use those.

score_source = "stored_live"

2. Recomputed point-in-time replay scores

If stored live scores are unavailable, recompute using ReplaySnapshot and point-in-time rules.

score_source = "recomputed_point_in_time"

3. Unavailable scores

If neither source is available:

- omit the timestamp from timeline, or
- return null fields

Do not use current/latest scores for historical timestamps unless explicitly marked:

score_source = "current_approximate"


-------------------------------------------------------------------------------
Advanced ML Unavailable Fallback
-------------------------------------------------------------------------------

If no stored ML output exists for timestamp t:

- regime = null
- regime_confidence = null
- break_risk = null
- bayesian_posterior = null
- linucb_score = null
- final_rank_score = null
- exit_score = null
- ev_hold_value_usdt = null
- score_source = "unavailable"

Do not recompute ML scores retrospectively unless the full ReplaySnapshot-based pipeline is available.

If recomputed safely using ReplaySnapshot:

score_source = "recomputed_point_in_time"

If current/latest ML values are used for historical display:

score_source = "current_approximate"

and include a warning.


Example:

{
  "decision_score_timeline": [
    {
      "timestamp": 1715000000,
      "score_source": "recomputed_point_in_time",
      "regime": "mean_reverting",
      "regime_confidence": 0.82,
      "break_risk": 0.18,
      "bayesian_posterior": 0.74,
      "linucb_score": 0.61,
      "liquidity_score": 0.88,
      "microstructure_risk": 0.22,
      "ev_hold_value_usdt": 0.42,
      "exit_score": 0.31,
      "trade_quality_score": 0.79,
      "curator_state": "tradable"
    }
  ]
}

This turns the chart from a price picture into a decision explanation system.

================================================================================
TIMESTAMP ALIGNMENT
================================================================================

Candle data usually uses bucket timestamps:

Example:
1-minute candles:
1715000000
1715000060
1715000120

Actual trade events may use exact millisecond timestamps:

Example:
1715000023.527

Rules:

1. If the frontend chart supports continuous timestamps:

- plot actual marker at exact original_event_timestamp

2. If frontend chart only supports candle bucket timestamps:

- snap marker to nearest candle timestamp
- preserve original_event_timestamp in metadata

Marker should include both:

{
  "timestamp": 1715000000,
  "original_event_timestamp": 1715000023.527,
  "timestamp_alignment": "snapped_to_nearest_candle"
}

or:

{
  "timestamp": 1715000023.527,
  "original_event_timestamp": 1715000023.527,
  "timestamp_alignment": "exact"
}

Do not lose original event timestamp.

================================================================================
API RESPONSE DESIGN
================================================================================

Do not return one mixed marker list.

Return separated arrays:

{
  "pair": "CRV-USDT-SWAP/XAG-USDT-SWAP",
  "timeframe": "1m",
  "window": 10080,

  "zscore_series": [
    {
      "timestamp": 1715000000,
      "z_score": 1.24,
      "spread": -4.1512
    }
  ],

  "statistical_markers": [
    {
      "marker_category": "statistical",
      "marker_type": "historical_mean_crossing",
      "timestamp": 1715000100,
      "z_score": 0.04,
      "spread": -4.1517,
      "is_trade_signal": false
    }
  ],

  "replay_markers": [
    {
      "marker_category": "replay",
      "marker_type": "replay_entry_candidate",
      "timestamp": 1715000200,
      "side": "BUY_SPREAD",
      "z_score": -2.14,
      "spread": -4.1781,
      "status": "valid_candidate",
      "curator_state": "tradable",
      "curator_state_source": "historical",
      "config_source": "historical",
      "passed": true,
      "block_reasons": [],
      "reason": "z threshold and persistence passed"
    },
    {
      "marker_category": "replay",
      "marker_type": "replay_blocked_signal",
      "timestamp": 1715000300,
      "side": "SELL_SPREAD",
      "z_score": 2.05,
      "spread": -4.1310,
      "status": "blocked_candidate",
      "curator_state": "hospital",
      "curator_state_source": "historical",
      "config_source": "historical",
      "passed": false,
      "block_reasons": ["pair_in_hospital", "liquidity_failed"],
      "reason": "signal detected but blocked"
    }
  ],

  "actual_markers": [
    {
      "marker_category": "actual",
      "marker_type": "actual_entry",
      "entry_id": "actual_T123",
      "timestamp": 1715000250,
      "original_event_timestamp": 1715000250.557,
      "side": "BUY_SPREAD",
      "z_score": -2.11,
      "spread": -4.1774,
      "trade_id": "T123",
      "reason": "entry_signal_confirmed"
    },
    {
      "marker_category": "actual",
      "marker_type": "actual_exit",
      "timestamp": 1715000410,
      "original_event_timestamp": 1715000410.229,
      "side": "BUY_SPREAD",
      "z_score": -0.18,
      "spread": -4.1612,
      "trade_id": "T123",
      "pnl_usdt": 4.23,
      "fees_usdt": 0.18,
      "slippage_usdt": 0.07,
      "reason": "reverted_to_exit_band"
    }
  ],

  "counterfactual_exit_studies": [],

  "counterfactuals_lazy_load": true,

  "decision_score_timeline": [],

  "decision_timeline_meta": {
    "timeline_resolution": "5m",
    "timeline_downsample_method": "last",
    "timeline_original_points": 10080,
    "timeline_returned_points": 1440
  }
}

================================================================================
FRONTEND RENDERING RULES
================================================================================

Render marker categories differently.

Statistical markers:

- historical_mean_crossing:
  - yellow small circle
  - tooltip says "not a trade signal"

Replay markers:

- replay BUY_SPREAD:
  - green hollow triangle up

- replay SELL_SPREAD:
  - red hollow triangle down

- replay exit:
  - blue hollow diamond

- replay blocked:
  - amber hollow X

Actual markers:

- actual BUY_SPREAD:
  - solid green triangle up

- actual SELL_SPREAD:
  - solid red triangle down

- actual exit:
  - solid blue diamond

- actual blocked:
  - solid amber X

================================================================================
MARKER Z-INDEX / RENDER ORDER
================================================================================

Render in this order:

1. Z-score line and threshold lines
2. statistical_markers
3. replay_markers
4. actual_markers
5. selected marker highlight
6. counterfactual overlays

actual_markers must render on top of replay_markers.

If replay_entry_candidate and actual_entry share the same timestamp and z-score:

- render replay marker slightly larger and hollow
- render actual marker solid and on top
- this creates a "candidate was actually executed" visual confirmation

================================================================================
FRONTEND LAYER TOGGLES
================================================================================

The frontend must provide independent layer toggles:

- show/hide statistical markers
- show/hide replay markers
- show/hide actual markers
- show/hide counterfactual overlays
- show/hide decision score panels

Recommended default:

- statistical markers: on
- actual markers: on
- replay markers: on
- counterfactual overlays: off
- decision score panels: off or collapsed

This prevents the chart from becoming unreadable when many markers exist.

================================================================================
TOOLTIPS
================================================================================

Historical crossing tooltip:

Historical mean crossing
Z-score: {z_score}
Spread: {spread}
Meaning: spread crossed historical mean band
Note: this is not a trade signal

Replay entry tooltip:

Replay {side} candidate
Z-score: {z_score}
Spread: {spread}
Curator state: {curator_state}
Curator source: {curator_state_source}
Config source: {config_source}
Passed: {passed}
Reason: {reason}
Blocked by: {block_reasons}

Replay blocked tooltip:

Replay {side} blocked
Z-score: {z_score}
Spread: {spread}
Curator state: {curator_state}
Blocked by: {block_reasons}
Reason: {reason}

Actual entry tooltip:

Actual {side} entry
Trade ID: {trade_id}
Z-score: {z_score}
Spread: {spread}
Reason: {reason}
Timestamp: {original_event_timestamp}

Actual exit tooltip:

Actual exit
Trade ID: {trade_id}
Z-score: {z_score}
PnL: {pnl_usdt}
Fees: {fees_usdt}
Slippage: {slippage_usdt}
Reason: {reason}
Timestamp: {original_event_timestamp}

Advanced ML shadow recommendation tooltip:

Shadow ML recommendation: {shadow_action}
Executed: {executed}
Exit score: {exit_score}
EV hold value: {ev_hold_value_usdt}
Regime: {regime}
Reason: {reason}
Note: Shadow mode recommendation only; not executed.

================================================================================
BACKEND IMPLEMENTATION REQUIREMENTS
================================================================================

Create or extend modules:

core/chart_audit/
  __init__.py
  marker_types.py
  replay_snapshot.py
  point_in_time_replay.py
  curator_state_source.py
  config_snapshot_source.py
  curator_replay.py
  actual_event_overlay.py
  counterfactual_exit_study.py
  decision_score_timeline.py
  timestamp_alignment.py
  hedge_ratio_sizing_audit.py
  hedge_ratio_drift_audit.py

API/service layer should expose:

get_pair_decision_audit_chart(pair, timeframe, start_ts, end_ts)

This service should return:

- zscore_series
- statistical_markers
- replay_markers
- actual_markers
- counterfactual_exit_studies
- counterfactuals_lazy_load
- decision_score_timeline

Lazy API:

get_counterfactual_exit_study(entry_id, start_ts, end_ts)

Do not compute replay markers directly in the frontend.

Frontend should render backend-provided marker arrays only.

================================================================================
TESTING REQUIREMENTS
================================================================================

Add tests:

1. No-lookahead replay test

Given candles from t0 to t100,
when replay is evaluating t50,
assert ReplaySnapshot contains only candles t0 to t50.

2. Replay engine interface test

Replay engine evaluate() must accept ReplaySnapshot only,
not the full candle series.

2.1 ReplaySnapshot immutability test

ReplaySnapshot should use tuple fields for candles_until_t, zscore_until_t,
spread_until_t, and actual_events_at_t.

2.2 Incremental indicator test

Z-score, hedge ratio, and cointegration values at timestamp t must be computed from
candles <= t only. Adding candles after t must not change indicator values at t.

3. Mean-crossing marker test

Historical mean crossing marker should not be marked as trade signal.

4. Replay valid entry test

If Z <= -2 and all gates pass,
emit replay_entry_candidate BUY_SPREAD.

5. Replay blocked signal test

If Z <= -2 but curator_state == hospital,
emit replay_blocked_signal with block reason pair_in_hospital.

6. Actual marker source test

Actual markers must be created only from real bot events/trade logs,
not inferred from chart Z-score.

7. Counterfactual isolation test

Counterfactual exit study may use future data only after entry marker exists.
It must not affect entry marker generation.

8. Counterfactual entry-anchor test

Counterfactual study for actual trade must anchor to actual trade entry timestamp,
not nearest replay candidate timestamp.

9. Counterfactual not-triggered test

If exit condition never triggers within chart window,
return status = "not_triggered".

10. Marker separation test

API response must separate:

- statistical_markers
- replay_markers
- actual_markers

11. Tooltip data completeness test

Each marker type must include fields required by its tooltip.

12. Actual overlay test

Given actual bot events,
API returns actual_entry, actual_exit, actual_blocked_signal markers correctly.

13. Decision score timeline test

Given score snapshots,
API returns aligned score series by timestamp.

14. Curator state sourcing test

If no exact curator state exists at t,
use last known state before t.

If no prior state exists,
mark replay as insufficient_data.

15. Config source test

If historical config exists,
use config_at(t).

If unavailable,
use current config and set config_source = "current_approximate".

16. Deterministic replay test

Running replay twice with the same historical inputs must produce identical replay markers.

17. Timestamp alignment test

Actual event with millisecond timestamp must preserve original_event_timestamp
even if marker timestamp is snapped to candle bucket.

18. Layer toggle rendering test

Frontend must be able to independently show/hide:

- statistical
- replay
- actual
- counterfactual
- decision score panels


19. ReplayConfigSnapshot test

ReplayConfigSnapshot must include replay-relevant fields only and must not pass
the full current live config object into historical replay.

20. Entry ID format test

Actual entry IDs must follow:

actual_{trade_id}

Replay entry IDs must follow:

replay_{pair_key}_{timestamp}_{side}

21. Counterfactual MAE/MFE unit test

CounterfactualExitResult must expose explicit Z and USDT excursion fields.

22. Decision timeline downsampling test

Given more than max_timeline_points,
API returns downsampled timeline metadata and no more than max_timeline_points rows.

23. Advanced ML unavailable fallback test

If no stored ML output exists for timestamp t,
optional ML score fields are null and score_source = "unavailable".



24. Hedge-ratio sizing formula test

Given gross_pair_notional and hedge_ratio,
leg1_notional + leg2_notional must equal gross_pair_notional,
and leg2_notional / leg1_notional must approximately equal abs(hedge_ratio).

25. Hedge-ratio entry metadata test

Actual entry marker must include:

- entry_hedge_ratio
- hedge_ratio_source
- hedge_sizing_mode
- target_leg1_notional_usdt
- target_leg2_notional_usdt
- actual_leg1_notional_usdt
- actual_leg2_notional_usdt
- hedge_sizing_error_pct

26. Hedge-ratio invalid test

Missing, NaN, infinite, negative when reject_negative_hedge_ratio=True,
or out-of-range hedge ratio must not be silently used for live hedge-ratio sizing.

27. Hedge-ratio drift test

Given entry_hedge_ratio and current_hedge_ratio,
hedge_ratio_drift_pct must be computed correctly.

If drift exceeds max_hedge_ratio_drift_pct,
an ExitCandidate with source = "hedge_ratio_drift" must be emitted.

28. Hedge-ratio replay metadata test

Replay entry marker must include:

- hedge_ratio_at_t
- hedge_ratio_source
- replay_sizing_mode
- target_leg1_notional_usdt
- target_leg2_notional_usdt
- hedge_ratio_valid

29. Hedge-ratio counterfactual sizing comparison test

Counterfactual study should be able to compare:

- equal_notional_pnl
- hedge_ratio_sized_pnl
- pnl_delta_usdt


30. FrozenCointegrationResult test

ReplaySnapshot must use FrozenCointegrationResult or None, not a raw dict,
for cointegration_result_until_t.

31. Frozen orderbook snapshot test

ReplaySnapshot must not contain a mutable live OrderBookSnapshot object.
If an orderbook snapshot exists, it must be frozen/read-only.

32. ReplayConfigSnapshot hedge config test

ReplayConfigSnapshot must include:

- hedge_ratio_sizing_enabled
- hedge_sizing_mode
- min_hedge_ratio
- max_hedge_ratio
- reject_negative_hedge_ratio
- max_hedge_sizing_error_pct
- max_hedge_ratio_drift_pct
- severe_hedge_ratio_drift_pct
- min_cointegration_window

33. ExitAction tighten_stop test

Exit Orchestrator must either support TIGHTEN_STOP directly,
or map it to action = "warn" with metadata.intent = "tighten_stop".

34. Hedge sizing error formula test

hedge_sizing_error_pct must be computed as max per-leg target notional error.

hedge_ratio_execution_error_pct must be computed as the actual leg ratio error versus beta.

35. Minimum cointegration window test

If len(candles_until_t) < config_snapshot.min_cointegration_window:

- hedge_ratio_until_t is None
- cointegration_result_until_t is None
- replay status is insufficient_data
- block reason includes insufficient_history

36. Replay exit candidate schema test

replay_exit_candidate marker must include:

- entry_id
- timestamp
- side
- z_score
- spread
- status
- reason
- exit_trigger
- metadata

37. ActualBotEvent type test

ActualBotEvent must be defined and used by ReplaySnapshot actual_events_at_t.

38. ReplayMarkerStatus enum test

Replay marker status must use ReplayMarkerStatus values, not arbitrary raw strings.

39. Equal-notional counterfactual baseline test

Equal-notional baseline must use:

gross_pair_notional / 2 per leg

so total gross exposure matches the hedge-ratio-sized comparison.


================================================================================
ACCEPTANCE CRITERIA
================================================================================

Implementation is complete when:

- ReplaySnapshot no longer uses raw dict for cointegration_result_until_t
- FrozenCointegrationResult is defined and used
- Orderbook snapshots in ReplaySnapshot are frozen/read-only DTOs
- ReplayConfigSnapshot contains hedge-ratio sizing fields
- ExitAction.TIGHTEN_STOP is supported or explicitly mapped to WARN with metadata.intent
- hedge_sizing_error_pct formula is explicitly defined and tested
- hedge_ratio_execution_error_pct formula is explicitly defined and tested
- insufficient history for hedge-ratio/cointegration maps to ReplayMarkerStatus.INSUFFICIENT_DATA and BlockReason.INSUFFICIENT_HISTORY
- replay_exit_candidate has a complete schema
- ActualBotEvent is defined
- ReplayMarkerStatus enum is defined and used
- equal-notional counterfactual baseline uses gross_pair_notional / 2 per leg
- Phase 2.25 Hedge-Ratio Exposure Alignment is documented and implemented before Phase 2.5
- hedge-ratio-aware sizing uses gross-normalized beta sizing, not uncontrolled notional multiplication
- fresh hedge ratio is used at entry when available
- stale discovery hedge ratio is clearly marked if used as fallback
- actual entry markers include hedge-ratio sizing metadata
- replay markers include hedge-ratio sizing metadata
- hedge-ratio drift emits an ExitCandidate through the Exit Orchestrator, not a direct close
- counterfactual exit study can compare equal-notional vs hedge-ratio-sized PnL
- ReplaySnapshot uses immutable tuple fields or safe read-only views
- Z-score / rolling indicators are computed incrementally or proven point-in-time safe
- ReplayConfigSnapshot is defined and used
- CuratorState enum is defined and used
- BlockReason.CURATOR_LOW_LIQUIDITY exists and is used for low_liquidity curator state
- entry_id format is stable for both actual and replay entries
- counterfactual MAE/MFE fields explicitly include Z and USDT units
- decision score timeline supports downsampling
- unavailable ML outputs return null fields with score_source = "unavailable"
- yellow dots are clearly labeled as historical_mean_crossing
- yellow dots are not described as trade signals
- statistical/replay/actual markers are separated
- replay markers are generated with ReplaySnapshot
- ReplaySnapshot prevents future candle access
- replay markers are generated point-in-time without lookahead
- curator_state_at(t) uses historical state or safe recomputation
- curator state fallback is explicit and never silent
- config_at(t) uses historical config or marks current config as approximate
- curator state can block replay signals
- blocked replay signals include explicit BlockReason values
- actual bot events are rendered from real logs/DB
- actual markers are visually distinct from replay markers
- actual markers render on top of replay markers
- timestamp alignment preserves original_event_timestamp
- counterfactual exits are lazy-loaded or computed only on demand
- counterfactual exits do not affect replay entry generation
- counterfactual not-triggered cases are represented clearly
- decision score timeline explains bot decision quality over time
- frontend has independent layer toggles
- chart can answer:
  - what looked like an opportunity
  - whether the bot was allowed to trade it
  - whether the bot actually traded it
  - why a signal was blocked
  - whether the exit could have been improved

Do not modify live trading behavior in this task.
This is a chart audit / replay / visualization improvement only.


================================================================================
NEXT IMPLEMENTATION STEP AFTER THIS PROMPT
================================================================================

After saving this v1.2 prompt, start with:

Phase 1: Actual Bot Decision Overlay

Reason:

- It uses real bot events.
- It gives immediate value.
- It has the lowest lookahead risk.
- It does not require the full replay engine yet.
- It does not change live trading behavior.

Recommended first implementation prompt:

"Read CHART_DECISION_AUDIT_V1_4.md. Do not implement everything.
Start only with Phase 1: Actual Bot Decision Overlay.
Create marker types/enums and an API/service function that maps real bot events into actual_markers.
Do not infer actual markers from Z-score.
Do not implement replay, counterfactuals, or decision score panels yet."


================================================================================
NEXT CODEX PROMPT — PHASE 2.25 ONLY
================================================================================

If Phase 1 and Phase 2 are already complete, your next implementation prompt should be:

Read CHART_DECISION_AUDIT_V1_4.md.

Do not implement everything.

Start only with Phase 2.25: Hedge-Ratio Exposure Alignment, including the v1.4 contract fixes.

Tasks:

1. Add hedge-ratio-aware sizing preview/logging first.
2. Use gross-normalized beta sizing:
   leg1 = gross_pair_notional / (1 + abs(beta))
   leg2 = gross_pair_notional * abs(beta) / (1 + abs(beta))
3. Persist hedge-ratio metadata on actual entries.
4. Add hedge-ratio drift ExitCandidate generation through the Exit Orchestrator.
5. Update chart audit actual/replay marker metadata with hedge-ratio fields.
6. Add tests for sizing formula, metadata, invalid hedge ratio, drift candidate, counterfactual sizing comparison, FrozenCointegrationResult, ReplayMarkerStatus, ActualBotEvent, ReplayConfigSnapshot hedge fields, and replay_exit_candidate schema.

Do not implement Phase 2.5 yet.
Do not auto-rebalance open positions.
Do not change live behavior unless hedge_ratio_sizing_enabled is explicitly true.
