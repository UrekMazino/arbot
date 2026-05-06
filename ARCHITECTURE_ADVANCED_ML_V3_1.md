OKXStatBot Advanced Architecture Upgrade Prompt v3.1
Regime Detection + Bayesian Pair Scoring + Online Learning Ranking + Probabilistic Exit Management

================================================================================
HOW TO USE THIS DOCUMENT WITH CODEX / COPILOT
================================================================================

This is a MASTER ARCHITECTURE DOCUMENT.

Do NOT ask Codex to implement the whole document in one pass.

Save this file as:

ARCHITECTURE_ADVANCED_ML_V3_1.md

Then prompt Codex file-by-file.

Recommended initial instruction to Codex:

"You are an expert quantitative Python developer. I will provide a Master Architecture Document.
Do NOT write all code at once. First summarize the dependency map between modules.
Then wait for my command naming the specific file/module to implement.
When implementing, edit only the requested files and strictly follow the interfaces in the architecture document."

================================================================================
0. PURPOSE
================================================================================

You are helping me upgrade my Python statistical arbitrage bot named OKXStatBot.

Current bot already has:

- Engle-Granger / ADF cointegration validation
- zero-crossing checks
- hedge-ratio estimation
- z-score spread signals
- orderbook liquidity filters
- min-capital / order-capacity filters
- pair health states: elite / stable / warning / hospital / graveyard
- rolling pair analytics
- caching / worker-based fetching / orderbook cache
- aligned candle matrix architecture using closed candles only
- advanced trade management:
  - max hold exit
  - stall detection
  - trailing stop
  - partial exit
  - divergence exit
  - regime-break exit
  - net profit guard

I want to implement four advanced systems:

1. Regime Detection
2. Bayesian Pair Scoring
3. Online Learning Ranking
4. Probabilistic Trade Exit Management

CRITICAL RULE:

These systems must improve ranking, selection, adaptation, and exit timing only.

They must NEVER bypass hard validation:

- cointegration
- ADF
- zero crossings
- hedge ratio sanity
- liquidity freshness
- order-capacity checks
- closed-candle data validation
- stale feed checks

Invalid candidates must not flow into downstream scoring as normal candidates.

Correct pipeline:

RawCandidate
→ DataValidation
→ HardValidation
→ ValidPairCandidate only
→ RegimeDetection
→ BayesianPairScoring
→ OnlineLearningRanking
→ FinalRanking

If HardValidationResult.is_valid is False:

- do not rank the pair
- do not explore the pair
- do not trade the pair
- do not let Bayesian or Bandit scores override this
- return a clear FailedHardValidation result

================================================================================
0.1 MVP SCOPE — RECOMMENDED FIRST DELIVERY
================================================================================

Implement this first before attempting the full system.

MVP Phase 1-3 target:

- FeatureSchema + NamedFeatureVector
- BotAdapterSpec / ExistingBotAdapter Protocol
- ModelStateStore with atomic persistence
- Heuristic Regime Detector only
- MicrostructureAnalyzer
- Bayesian Pair Scorer:
  - Beta-Bernoulli
  - feature multipliers
  - evidence threshold behavior
- FinalRanker:
  - ValidPairCandidate gate
  - score normalization
  - dashboard-safe output
- Shadow ranking only

Defer until MVP is stable:

- Full LinUCB contextual bandit live selection
- Probabilistic Exit Manager live execution
- Dynamic partial sizing live execution
- Learned exit-weight updates
- HMM regime detector
- Hierarchical Bayesian model
- GlobalMarketContext live impact

================================================================================
0.2 NON-NEGOTIABLE CODEX RULES
================================================================================

When Codex implements this architecture:

1. Do not alter, simplify, or optimize explicit mathematical formulas in this document.
   Implement them exactly unless the user explicitly asks to revise the math.

2. Do not invent missing functions, class names, or bot integrations.
   Use the BotAdapterSpec / ExistingBotAdapter Protocol.

3. Do not pass invalid pairs downstream.
   Only ValidPairCandidate objects may enter Regime/Bayes/Bandit/Ranking.

4. Do not use unnamed raw np.ndarray feature vectors without FeatureSchema validation.

5. Do not block emergency exits with heavy model scoring.

6. Do not execute probabilistic exits in shadow mode.

7. Do not remove the existing rule-based AdvancedTradeManager.
   Add the new engine beside it.


================================================================================
0.3 V3.1 PATCH NOTES — WHAT THIS VERSION FIXES
================================================================================

This version keeps v3's architecture but closes the last implementation gaps:

- Adds missing EVConfig fields:
  - expected_adverse_sigma_move
  - target_exit_z
  - exit_fee_rate
  - recent_z_vol_window
  - warn_when_using_default_spread_edge

- Replaces remaining pseudocode in order-style decisions:
  - "adverse move is fast"
  - "spread is wide but regime is stable"

- Adds concrete formulas for:
  - trend_continuation_risk
  - execution_risk_score
  - drawdown_risk_score
  - spread_volatility_spike_score alias
  - half_life_score
  - low_break_risk_score
  - slippage_risk
  - hedge_ratio_drift_risk
  - recent_z_volatility
  - time_pressure_hours

- Replaces rolling_std_of_spread_returns pseudocode with an actual rolling-std computation.

- Adds shadow_eval_window for circuit breakers.

- Adds regime hysteresis / cooldown fields:
  - min_regime_persistence_ticks
  - regime_switch_cooldown_seconds
  - regime_switch_confidence_margin

- Makes MicrostructureConfig the canonical source for max_book_age_ms.

- Adds end-to-end invalid-pair integration test:
  invalid pair → no regime/bayes/bandit scoring → final_score = 0.

IMPORTANT NOTE ABOUT FORMULAS:

Most weights and thresholds in this document are engineering heuristics.
They are not guaranteed alpha and are not "PhD paper constants."

Treat them as safe scaffolding for shadow-mode testing.
They must be calibrated using your own historical trades, exchange data,
and shadow-mode policy delta reports before being trusted live.

================================================================================
1. TARGET PACKAGE STRUCTURE
================================================================================

Create or extend this structure:

core/
  config/
    __init__.py
    advanced_ml_config.py

  adapters/
    __init__.py
    bot_adapter_types.py
    existing_bot_adapter.py

  features/
    __init__.py
    feature_types.py
    feature_schema.py
    pair_features.py
    trade_features.py
    microstructure_features.py
    normalization.py
    feature_store.py

  regime/
    __init__.py
    regime_types.py
    regime_detector.py
    heuristic_regime_detector.py
    transition_matrix.py

  bayes/
    __init__.py
    bayes_types.py
    bayesian_pair_scorer.py
    beta_bernoulli.py
    priors.py

  online_learning/
    __init__.py
    bandit_types.py
    contextual_bandit.py
    thompson_sampling.py
    linucb.py
    reward.py

  ranking/
    __init__.py
    rank_types.py
    final_ranker.py
    pair_reputation.py
    scoring_pipeline.py

  ev/
    __init__.py
    ev_types.py
    hold_exit_ev.py

  microstructure/
    __init__.py
    orderbook_types.py
    microstructure_analyzer.py

  trade_management/
    __init__.py
    exit_types.py
    probabilistic_exit_manager.py
    exit_policy_shadow.py
    exit_outcome_store.py

  storage/
    __init__.py
    json_store.py
    parquet_store.py
    model_state_store.py

tests/
  test_feature_schema.py
  test_model_state_store.py
  test_regime_detector.py
  test_transition_matrix.py
  test_bayesian_pair_scorer.py
  test_contextual_bandit.py
  test_linucb.py
  test_final_ranker.py
  test_probabilistic_exit_manager.py
  test_microstructure_analyzer.py
  test_ev_decision.py
  test_shadow_policy.py

================================================================================
2. GLOBAL DESIGN RULES
================================================================================

Use:

- Python 3.11+
- dataclasses
- type hints
- explicit return types
- numpy
- pandas
- scipy
- statsmodels
- scikit-learn if useful
- optional: pydantic v2 for config validation
- optional: hmmlearn, river

Avoid:

- notebook-style code
- hidden global state
- unbounded memory growth
- hardcoded magic constants outside config
- changing existing hard validation behavior
- using current unfinished candles for discovery
- using stale orderbook data as clean liquidity
- raw unlabelled np.ndarray feature vectors without a schema

Every major component must support:

- config-driven parameters
- serialization
- state hydration/dehydration
- dashboard-ready metrics
- structured logging hooks
- shadow mode
- unit tests that validate math, not only types

================================================================================
3. CONFIG ARCHITECTURE
================================================================================

Do not create one huge flat config.

Use smaller config dataclasses and compose them.

File:

core/config/advanced_ml_config.py

-------------------------------------------------------------------------------
PipelineConfig
-------------------------------------------------------------------------------

@dataclass
class PipelineConfig:
    enabled: bool = False
    shadow_mode: bool = True
    max_pairs_active: int = 1
    emergency_disable_on_shadow_divergence: bool = True
    max_shadow_disagreement_rate: float = 0.25
    min_shadow_policy_delta_usdt: float = 0.0
    audit_log_level: str = "INFO"
    shadow_eval_window: int = 50

IMPORTANT:

There is no valid_only_pipeline flag.

Valid-only behavior is mandatory and not configurable.

-------------------------------------------------------------------------------
PersistenceConfig
-------------------------------------------------------------------------------

@dataclass
class PersistenceConfig:
    model_state_flush_ticks: int = 50
    model_state_flush_on_trade_close: bool = True
    model_state_path: str = "data/model_state"
    atomic_write: bool = True
    corrupted_state_policy: str = "safe_defaults"

If state load fails because the JSON is missing, corrupted, or incompatible:

- initialize with safe defaults
- log a critical warning
- do not crash the bot
- do not enable live advanced mode automatically

-------------------------------------------------------------------------------
FeatureConfig
-------------------------------------------------------------------------------

@dataclass
class FeatureConfig:
    reject_nan_features: bool = True
    feature_schema_version: int = 1

-------------------------------------------------------------------------------
RegimeConfig
-------------------------------------------------------------------------------

@dataclass
class RegimeConfig:
    regime_window: int = 120
    regime_break_threshold: float = 0.85
    structural_break_confidence_threshold: float = 0.80

    corr_drift_break_threshold: float = 0.20
    beta_drift_break_threshold: float = 0.15

    high_volatility_ratio: float = 1.75
    low_volatility_ratio: float = 0.60
    vol_spike_scale: float = 1.00

    liquidity_stress_threshold: float = 0.80
    correlation_breakdown_threshold: float = 0.75
    trending_threshold: float = 0.70
    mean_reverting_threshold: float = 0.65

    z_velocity_risk_scale: float = 0.005
    z_acceleration_risk_scale: float = 0.0002

    max_spread_widening_bps: float = 20.0
    min_top_depth_usdt: float = 1_000.0

    # Regime-switch hysteresis to prevent flicker in choppy markets.
    min_regime_persistence_ticks: int = 3
    regime_switch_cooldown_seconds: int = 60
    regime_switch_confidence_margin: float = 0.10

    # Do not duplicate max_book_age_ms here.
    # Use config.microstructure.max_book_age_ms as the canonical source.

-------------------------------------------------------------------------------
BayesianConfig
-------------------------------------------------------------------------------

@dataclass
class BayesianConfig:
    alpha0: float = 2.0
    beta0: float = 2.0
    decay: float = 0.995
    feature_weight: float = 0.30
    min_evidence: int = 10
    max_grade_when_low_evidence: str = "C"

-------------------------------------------------------------------------------
BanditConfig
-------------------------------------------------------------------------------

@dataclass
class BanditConfig:
    algorithm: str = "linucb"
    alpha: float = 0.75
    decay: float = 0.995
    lambda_reg: float = 1.0
    exploration_budget: float = 0.00
    max_live_exploration_budget: float = 0.05
    reward_scale_bps: float = 50.0

-------------------------------------------------------------------------------
RankingConfig
-------------------------------------------------------------------------------

@dataclass
class RankingConfig:
    final_score_soft_cap: float = 1.50

-------------------------------------------------------------------------------
MicrostructureConfig
-------------------------------------------------------------------------------

@dataclass
class MicrostructureConfig:
    max_book_age_ms: float = 1500.0
    max_allowed_slippage_bps: float = 8.0
    severe_book_stress_threshold: float = 0.85
    max_urgency_boost: float = 0.75
    max_exit_urgency_multiplier: float = 1.75
    exit_score_slippage_cap: float = 0.50
    fast_adverse_threshold: float = 0.60
    wide_spread_bps: float = 5.0

-------------------------------------------------------------------------------
EVConfig
-------------------------------------------------------------------------------

@dataclass
class EVConfig:
    strong_positive_ev_usdt: float = 1.0
    weak_positive_ev_usdt: float = 0.25
    near_zero_ev_usdt: float = 0.0
    time_penalty_rate_per_hour: float = 0.0001
    spread_edge_per_sigma_usdt: float = 0.50
    use_historical_spread_edge: bool = True
    min_spread_edge_per_sigma_usdt: float = 0.05
    max_spread_edge_per_sigma_usdt: float = 5.00
    warn_when_using_default_spread_edge: bool = True

    expected_adverse_sigma_move: float = 0.50
    target_exit_z: float = 0.50
    exit_fee_rate: float = 0.0006
    recent_z_vol_window: int = 20

-------------------------------------------------------------------------------
ExitConfig
-------------------------------------------------------------------------------

@dataclass
class ExitConfig:
    exit_hold_threshold: float = 0.30
    exit_tighten_threshold: float = 0.55
    exit_partial_threshold: float = 0.75
    mean_reversion_hold_discount: float = 0.35

    default_half_life_seconds: float = 1800.0
    min_expected_progress_sigma: float = 0.25
    max_hold_seconds: float = 6 * 3600
    z_still_high_threshold: float = 1.5
    max_drawdown_usdt: float = 10.0

    base_partial_exit: float = 0.15
    min_partial_exit: float = 0.10
    max_partial_exit: float = 0.80

-------------------------------------------------------------------------------
AdvancedMLConfig
-------------------------------------------------------------------------------

@dataclass
class AdvancedMLConfig:
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    persistence: PersistenceConfig = field(default_factory=PersistenceConfig)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    regime: RegimeConfig = field(default_factory=RegimeConfig)
    bayes: BayesianConfig = field(default_factory=BayesianConfig)
    bandit: BanditConfig = field(default_factory=BanditConfig)
    ranking: RankingConfig = field(default_factory=RankingConfig)
    microstructure: MicrostructureConfig = field(default_factory=MicrostructureConfig)
    ev: EVConfig = field(default_factory=EVConfig)
    exit: ExitConfig = field(default_factory=ExitConfig)

================================================================================
4. BOT ADAPTER CONTRACT
================================================================================

Before implementing advanced modules, create an adapter layer so Codex does not guess existing project structure.

File:

core/adapters/bot_adapter_types.py

-------------------------------------------------------------------------------
PairState
-------------------------------------------------------------------------------

class PairState(str, Enum):
    ELITE = "elite"
    STABLE = "stable"
    WARNING = "warning"
    HOSPITAL = "hospital"
    GRAVEYARD = "graveyard"
    UNKNOWN = "unknown"

-------------------------------------------------------------------------------
BotAdapterSpec
-------------------------------------------------------------------------------

@dataclass
class BotAdapterSpec:
    pair_state_source: str
    orderbook_cache_source: str
    trade_manager_source: str
    trade_lifecycle_hooks: list[str]
    supports_async_execution: bool
    supports_position_reconciliation: bool

-------------------------------------------------------------------------------
ExistingBotAdapter Protocol
-------------------------------------------------------------------------------

class ExistingBotAdapter(Protocol):
    def get_pair_state(self, pair: "PairIdentity") -> PairState:
        ...

    def get_orderbook_snapshot(self, symbol: str) -> "OrderBookSnapshot | None":
        ...

    def get_current_position(self, pair: "PairIdentity") -> dict | None:
        ...

    def get_trade_lifecycle_event(self) -> dict | None:
        ...

    def read_existing_trade_state(self) -> dict | None:
        ...

    def submit_exit_order(
        self,
        pair: "PairIdentity",
        exit_percentage: float,
        order_style: str,
        reason: str,
    ) -> dict:
        ...

Rule:

- The new modules must call the adapter.
- They must not directly guess names of existing bot classes.
- If a required adapter method is unavailable, fail closed and log a clear warning.

================================================================================
5. COMMON DATA TYPES
================================================================================

-------------------------------------------------------------------------------
PairIdentity
-------------------------------------------------------------------------------

@dataclass(frozen=True)
class PairIdentity:
    symbol_1: str
    symbol_2: str
    timeframe: str
    window: int

    @property
    def key(self) -> str:
        return f"{self.symbol_1}|{self.symbol_2}|{self.timeframe}|{self.window}"

-------------------------------------------------------------------------------
HardValidationResult
-------------------------------------------------------------------------------

@dataclass
class HardValidationResult:
    is_valid: bool
    p_value: float | None
    adf_stat: float | None
    zero_crossings: int
    hedge_ratio: float | None
    hedge_ratio_valid: bool
    liquidity_valid: bool
    capacity_valid: bool
    data_valid: bool
    closed_candles_only: bool
    latest_ts_1: int | None
    latest_ts_2: int | None
    reasons: list[str]

This result remains the hard gate.

No ranking/scoring layer may turn is_valid=False into tradable=True.

-------------------------------------------------------------------------------
ValidPairCandidate
-------------------------------------------------------------------------------

@dataclass
class ValidPairCandidate:
    pair: PairIdentity
    hard_validation: HardValidationResult
    pair_features: "PairFeatureVector"

    def __post_init__(self) -> None:
        if not self.hard_validation.is_valid:
            raise ValueError("ValidPairCandidate cannot wrap failed hard validation.")

Only ValidPairCandidate objects may enter:

- Regime detector
- Bayesian scorer
- Bandit ranker
- Final ranker

================================================================================
6. FEATURE SCHEMA AND SAFE NUMPY ARRAYS
================================================================================

Raw np.ndarray vectors are allowed only after schema validation.

Never use unnamed matrix columns.

-------------------------------------------------------------------------------
FeatureSchema
-------------------------------------------------------------------------------

@dataclass(frozen=True)
class FeatureSchema:
    names: tuple[str, ...]
    version: int = 1

    def index(self, name: str) -> int:
        if name not in self.names:
            raise KeyError(f"Feature not in schema: {name}")
        return self.names.index(name)

    def validate(self, values: np.ndarray) -> None:
        if values.ndim != 1:
            raise ValueError("Feature vector must be 1D.")
        if values.shape[0] != len(self.names):
            raise ValueError("Feature vector length does not match schema.")
        if not np.all(np.isfinite(values)):
            raise ValueError("Feature vector contains NaN or inf.")

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "names": list(self.names),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FeatureSchema":
        return cls(
            names=tuple(data["names"]),
            version=int(data.get("version", 1)),
        )

-------------------------------------------------------------------------------
NamedFeatureVector
-------------------------------------------------------------------------------

@dataclass
class NamedFeatureVector:
    schema: FeatureSchema
    values: np.ndarray

    def __post_init__(self) -> None:
        self.schema.validate(self.values)

    def get(self, name: str) -> float:
        return float(self.values[self.schema.index(name)])

    def to_dict(self) -> dict[str, float]:
        return {name: float(self.values[i]) for i, name in enumerate(self.schema.names)}

Rule:

- LinUCB and other matrix methods receive NamedFeatureVector.
- Matrix multiplication uses values only after schema validation.
- Saved model state must include feature_schema_version.
- If loaded model schema version does not match current schema, fail closed:
  - do not use old model weights
  - initialize safe defaults
  - log critical warning

================================================================================
7. STATE PERSISTENCE, HYDRATION, AND THREAD SAFETY
================================================================================

All learning/stateful models must implement:

class StatefulModel(Protocol):
    def to_dict(self) -> dict:
        ...

    @classmethod
    def from_dict(cls, data: dict):
        ...

    def save_state(self, store: "ModelStateStore") -> None:
        ...

    def load_state(self, store: "ModelStateStore") -> None:
        ...

Applicable to:

- BayesianPairScorer
- LinUCBContextualBandit
- ThompsonSamplingBandit
- RegimeTransitionMatrix
- PairReputationStore
- ExitOutcomeStore
- ShadowPolicyEvaluator

State flush rules:

- flush every N ticks
- flush after every closed trade
- flush on graceful shutdown
- flush before enabling live advanced mode
- use atomic write: write temp file then rename

State load fallback:

If model state is missing, corrupted, incompatible, or partially written:

- initialize safe defaults
- log critical warning
- keep advanced live mode disabled
- allow shadow mode
- do not crash the bot

Thread safety:

- Any mutable learning state must be protected by threading.RLock or asyncio.Lock.
- Updates to alpha/beta, LinUCB A/b, transition matrices, and reputation states must be atomic.
- Order execution and hard kill switch checks must not wait for heavy model updates.

Concurrency split:

- hard kill checks: synchronous and lightweight
- order execution: async/non-blocking if bot is async
- heavy math such as matrix inversion or scipy beta.ppf:
  - use cached values where possible
  - or run outside the order execution path
  - or dispatch to ProcessPoolExecutor / background worker if latency becomes significant

Do not allow model scoring to block emergency exit orders.

================================================================================
8. REGIME DETECTION
================================================================================

Goal:

Detect whether the current pair/market environment favors mean reversion or signals danger.

Regime labels:

class RegimeName(str, Enum):
    MEAN_REVERTING = "mean_reverting"
    TRENDING = "trending"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    CORRELATION_BREAKDOWN = "correlation_breakdown"
    LIQUIDITY_STRESS = "liquidity_stress"
    STRUCTURAL_BREAK = "structural_break"
    UNKNOWN = "unknown"

-------------------------------------------------------------------------------
RegimeDetectionResult
-------------------------------------------------------------------------------

@dataclass
class RegimeDetectionResult:
    pair: PairIdentity
    regime: RegimeName
    confidence: float
    break_risk: float
    volatility_state: str
    liquidity_state: str
    mean_reversion_velocity: float
    mean_reversion_acceleration: float
    trend_score: float
    transition_probability: dict[str, float]
    features: dict[str, float]
    reasons: list[str]
    timestamp: float

-------------------------------------------------------------------------------
Heuristic Regime Detector
-------------------------------------------------------------------------------

Implement this first. HMM can be optional later.

Inputs:

- z_history: list[(timestamp, z_score)]
- spread_history: residual/spread array
- corr_history: rolling correlation values
- hedge_ratio_history: rolling beta/hedge ratio values
- orderbook features:
  - spread_bps
  - depth_imbalance
  - top_depth_usdt
  - slippage_estimate_bps
  - book_freshness_ms

Utility:

def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))

-------------------------------------------------------------------------------
Required Explicit Formulas
-------------------------------------------------------------------------------

1. Realized spread volatility:

spread_returns = np.diff(spread_history)
realized_vol = float(np.std(spread_returns[-config.regime.regime_window:]))

2. Baseline volatility:

w = config.regime.regime_window

rolling_stds = [
    float(np.std(spread_returns[max(0, i - w):i]))
    for i in range(w, len(spread_returns) + 1)
    if len(spread_returns[max(0, i - w):i]) >= max(5, w // 4)
]

baseline_vol = (
    float(np.median(rolling_stds))
    if rolling_stds
    else max(realized_vol, 1e-9)
)

3. Normalized spread volatility spike:

normalized_spread_vol_spike = clamp01(
    ((realized_vol - baseline_vol) / max(baseline_vol, 1e-9))
    / config.regime.vol_spike_scale
)

4. Z velocity:

z_velocity = (z_now - z_prev) / max(dt_seconds, 1.0)

5. Z acceleration:

z_acceleration = (z_velocity_now - z_velocity_prev) / max(dt_seconds, 1.0)

6. Directional adverse movement:

abs_z_increasing = abs(z_now) > abs(z_prev)

adverse_z_velocity_score = (
    clamp01(abs(z_velocity) / config.regime.z_velocity_risk_scale)
    if abs_z_increasing
    else 0.0
)

adverse_acceleration_score = (
    clamp01(abs(z_acceleration) / config.regime.z_acceleration_risk_scale)
    if abs_z_increasing
    else 0.0
)

7. Correlation drift:

corr_drift = abs(corr_now - mean(corr_history[-lookback:]))

normalized_corr_drift = clamp01(
    corr_drift / config.regime.corr_drift_break_threshold
)

stable_correlation_score = 1.0 - normalized_corr_drift

8. Hedge ratio drift:

beta_drift = abs(beta_now - mean(beta_history[-lookback:]))

normalized_beta_drift = clamp01(
    beta_drift / config.regime.beta_drift_break_threshold
)

stable_beta_score = 1.0 - normalized_beta_drift

9. Zero-cross rhythm degradation:

recent_cross_rate = crosses_recent / max(recent_window, 1)
baseline_cross_rate = crosses_baseline / max(baseline_window, 1)

zero_cross_rhythm_drop = clamp01(
    (baseline_cross_rate - recent_cross_rate) / max(baseline_cross_rate, 1e-9)
)

healthy_cross_rhythm_score = 1.0 - zero_cross_rhythm_drop

10. Volatility state and moderate volatility score:

vol_ratio = realized_vol / max(baseline_vol, 1e-9)

if vol_ratio >= config.regime.high_volatility_ratio:
    volatility_state = "high"
elif vol_ratio <= config.regime.low_volatility_ratio:
    volatility_state = "low"
else:
    volatility_state = "normal"

moderate_volatility_score = 1.0 - clamp01(
    abs(vol_ratio - 1.0) / max(config.regime.high_volatility_ratio - 1.0, 1e-9)
)

11. Book freshness score:

stale_book_score = clamp01(
    (book_freshness_ms / config.microstructure.max_book_age_ms) - 1.0
)

book_fresh_score = 1.0 - stale_book_score

12. Spread widening score:

spread_widening_score = clamp01(
    spread_bps / max(config.regime.max_spread_widening_bps, 1e-9)
)

13. Low depth score:

low_depth_score = clamp01(
    1.0 - (top_depth_usdt / max(config.regime.min_top_depth_usdt, 1e-9))
)

14. Slippage score:

slippage_score = clamp01(
    slippage_estimate_bps / max(config.microstructure.max_allowed_slippage_bps, 1e-9)
)

15. Depth imbalance score:

depth_imbalance_score = clamp01(abs(depth_imbalance))

16. Liquidity stress:

liquidity_stress = clamp01(
    0.30 * stale_book_score
    + 0.25 * spread_widening_score
    + 0.20 * slippage_score
    + 0.15 * depth_imbalance_score
    + 0.10 * low_depth_score
)

healthy_liquidity_score = 1.0 - liquidity_stress

17. Z moving toward mean score:

z_moving_toward_mean = abs(z_now) < abs(z_prev)

z_moving_toward_mean_score = (
    clamp01(abs(z_velocity) / config.regime.z_velocity_risk_scale)
    if z_moving_toward_mean
    else 0.0
)

18. Trend score:

trend_score = clamp01(
    0.40 * adverse_z_velocity_score
    + 0.30 * adverse_acceleration_score
    + 0.20 * normalized_corr_drift
    + 0.10 * zero_cross_rhythm_drop
)

19. Break risk:

break_risk = clamp01(
    0.25 * normalized_corr_drift
    + 0.20 * normalized_beta_drift
    + 0.20 * normalized_spread_vol_spike
    + 0.15 * adverse_z_velocity_score
    + 0.10 * liquidity_stress
    + 0.10 * zero_cross_rhythm_drop
)

20. Mean reversion confidence:

mr_confidence = clamp01(
    0.30 * z_moving_toward_mean_score
    + 0.20 * stable_correlation_score
    + 0.15 * stable_beta_score
    + 0.15 * healthy_cross_rhythm_score
    + 0.10 * moderate_volatility_score
    + 0.10 * healthy_liquidity_score
)


-------------------------------------------------------------------------------
Regime Feature Aliases for Downstream Modules
-------------------------------------------------------------------------------

Use these exact aliases when passing regime features into ranking, EV, and exit logic:

spread_volatility_spike_score = normalized_spread_vol_spike

slippage_risk = slippage_score

hedge_ratio_drift_risk = normalized_beta_drift

low_break_risk_score = 1.0 - break_risk

trend_continuation_risk = clamp01(
    0.50 * trend_score
    + 0.30 * adverse_z_velocity_score
    + 0.20 * normalized_spread_vol_spike
)

half_life_score = clamp01(
    1.0 - (
        time_in_trade_seconds
        / max(2.0 * half_life_seconds, 1.0)
    )
)

If time_in_trade_seconds or half_life_seconds is unavailable in pair-ranking mode:

half_life_score = 0.50

-------------------------------------------------------------------------------
Classification
-------------------------------------------------------------------------------

if break_risk >= config.regime.regime_break_threshold:
    regime = RegimeName.STRUCTURAL_BREAK
elif liquidity_stress >= config.regime.liquidity_stress_threshold:
    regime = RegimeName.LIQUIDITY_STRESS
elif normalized_corr_drift >= config.regime.correlation_breakdown_threshold:
    regime = RegimeName.CORRELATION_BREAKDOWN
elif trend_score >= config.regime.trending_threshold:
    regime = RegimeName.TRENDING
elif mr_confidence >= config.regime.mean_reverting_threshold:
    regime = RegimeName.MEAN_REVERTING
elif vol_ratio >= config.regime.high_volatility_ratio:
    regime = RegimeName.HIGH_VOLATILITY
elif vol_ratio <= config.regime.low_volatility_ratio:
    regime = RegimeName.LOW_VOLATILITY
else:
    regime = RegimeName.UNKNOWN


-------------------------------------------------------------------------------
Regime Hysteresis / Cooldown
-------------------------------------------------------------------------------

To prevent rapid flickering between regimes, do not immediately switch regimes
unless the new regime is materially stronger.

Inputs:

- previous_regime
- previous_regime_confidence
- proposed_regime
- proposed_regime_confidence
- ticks_in_proposed_regime
- seconds_since_last_regime_switch

Switch rule:

can_switch = (
    proposed_regime == RegimeName.STRUCTURAL_BREAK
    and break_risk >= config.regime.regime_break_threshold
) or (
    ticks_in_proposed_regime >= config.regime.min_regime_persistence_ticks
    and seconds_since_last_regime_switch >= config.regime.regime_switch_cooldown_seconds
    and proposed_regime_confidence >= (
        previous_regime_confidence
        + config.regime.regime_switch_confidence_margin
    )
)

If can_switch is False:

- keep previous_regime
- update confidence gradually
- add reason: "regime switch held by hysteresis"

-------------------------------------------------------------------------------
Transition Matrix
-------------------------------------------------------------------------------

Use decayed float weights, not integer semantics.

@dataclass
class RegimeTransitionMatrix:
    weights: dict[str, dict[str, float]]
    decay: float = 0.995
    min_mass: float = 1e-6

    def update(self, previous: RegimeName, current: RegimeName) -> None:
        # multiply all existing transition weights by decay
        # increment previous -> current by 1.0
        # prune tiny weights below min_mass
        ...

    def probabilities(self, current: RegimeName) -> dict[str, float]:
        # normalize outgoing weights from current regime
        ...

Smoothing:

- do not switch from MEAN_REVERTING to STRUCTURAL_BREAK on one noisy tick unless break_risk is extreme
- use persistence_count or confidence hysteresis

================================================================================
9. BAYESIAN PAIR SCORING
================================================================================

Goal:

Estimate probability that a HARD-VALID pair is a high-quality tradable pair.

If HardValidationResult.is_valid is False:

- return posterior_good_probability = 0.0
- quality_grade = "D"
- reasons include "failed hard validation"
- do not update learning state from invalid candidate selection

-------------------------------------------------------------------------------
BayesianPairScore
-------------------------------------------------------------------------------

@dataclass
class BayesianPairScore:
    pair: PairIdentity
    posterior_good_probability: float
    confidence_interval: tuple[float, float]
    alpha: float
    beta: float
    evidence_count: int
    quality_grade: str
    feature_likelihoods: dict[str, float]
    reasons: list[str]
    timestamp: float

-------------------------------------------------------------------------------
Beta-Bernoulli Model
-------------------------------------------------------------------------------

Each pair has:

alpha = prior_success + weighted_successes
beta = prior_failures + weighted_failures

Posterior mean:

posterior = alpha / (alpha + beta)

Credible interval:

lower = scipy.stats.beta.ppf(0.05, alpha, beta)
upper = scipy.stats.beta.ppf(0.95, alpha, beta)

Sparse data smoothing:

default prior:
alpha0 = 2.0
beta0 = 2.0

Decay:

alpha = alpha0 + decay * (alpha - alpha0)
beta = beta0 + decay * (beta - beta0)

-------------------------------------------------------------------------------
Evidence Threshold Behavior
-------------------------------------------------------------------------------

If evidence_count < config.bayes.min_evidence:

- compute base posterior from alpha/beta
- do not apply feature likelihood adjustment aggressively
- either skip feature adjustment or multiply config.bayes.feature_weight by 0.25
- cap quality grade at config.bayes.max_grade_when_low_evidence
- add reason: "low Bayesian evidence"

Example:

effective_feature_weight = (
    config.bayes.feature_weight
    if evidence_count >= config.bayes.min_evidence
    else config.bayes.feature_weight * 0.25
)

-------------------------------------------------------------------------------
Outcome Definition
-------------------------------------------------------------------------------

Trade success is true when:

- net_pnl_after_fees > 0
- no severe regime break occurred
- slippage_bps <= max_expected_slippage_bps
- hold_time_seconds <= max_expected_hold_time_seconds

Normalized reward:

normalized_reward = tanh(net_pnl_bps / config.bandit.reward_scale_bps)

Convert to Bayesian update:

if normalized_reward >= 0:
    alpha += weight * normalized_reward
    beta += weight * (1.0 - normalized_reward)
else:
    beta += weight * abs(normalized_reward)

-------------------------------------------------------------------------------
Feature Likelihood Adjustment
-------------------------------------------------------------------------------

Use logit adjustment:

base_posterior = alpha / (alpha + beta)

feature_adjusted_logit = logit(base_posterior) + (
    sum(log(multiplier_i)) * effective_feature_weight
)

posterior_good_probability = clamp(sigmoid(feature_adjusted_logit), 0.01, 0.99)

Feature multipliers must be explicit and bounded between 0.30 and 1.50.

Examples:

p-value:
    p < 0.005 -> 1.20
    p < 0.010 -> 1.10
    p < 0.030 -> 1.00
    p < 0.050 -> 0.90
    else -> 0.70

regime:
    mean_reverting and confidence high -> 1.20
    unknown -> 0.95
    trending -> 0.75
    correlation_breakdown -> 0.50
    liquidity_stress -> 0.45
    structural_break -> 0.30

-------------------------------------------------------------------------------
Quality Grade
-------------------------------------------------------------------------------

Use explicit top-down elif chain:

if posterior >= 0.80 and lower_ci >= 0.55 and break_risk < 0.30:
    grade = "A"
elif posterior >= 0.65 and break_risk < 0.45:
    grade = "B"
elif posterior >= 0.50 and break_risk < 0.65:
    grade = "C"
else:
    grade = "D"

If evidence_count < config.bayes.min_evidence:

grade = min_grade_by_order(grade, config.bayes.max_grade_when_low_evidence)

Grade ordering:

A > B > C > D

================================================================================
10. ONLINE LEARNING RANKING
================================================================================

Goal:

Learn which valid pair is most attractive now under the current regime.

Start with LinUCB for interpretability.

Only valid candidates may enter the bandit.

Exploration among invalid candidates is forbidden.

-------------------------------------------------------------------------------
BanditContext
-------------------------------------------------------------------------------

@dataclass
class BanditContext:
    pair: PairIdentity
    features: NamedFeatureVector

-------------------------------------------------------------------------------
BanditRankResult
-------------------------------------------------------------------------------

@dataclass
class BanditRankResult:
    pair: PairIdentity
    expected_reward: float
    uncertainty: float
    exploration_bonus: float
    final_rank_score: float
    selected_for_exploration: bool
    reasons: list[str]

-------------------------------------------------------------------------------
LinUCB Implementation
-------------------------------------------------------------------------------

Maintain:

A: np.ndarray
b: np.ndarray
lambda_reg: float

theta = solve(A + lambda_reg * I, b)

For candidate context x:

mean = theta.T @ x

A_inv_x = solve(A + lambda_reg * I, x)

uncertainty = alpha * sqrt(x.T @ A_inv_x)

score = mean + uncertainty

Update after trade:

A = decay * A + (1.0 - decay) * lambda_reg * I + outer(x, x)
b = decay * b + reward * x

Do not use:

A = decay * A + outer(x, x)

because it erodes the identity prior.

Suggested:

alpha = 0.75
decay = 0.995
lambda_reg = 1.0

Reward:

reward_bps = (
    pnl_bps
    - fee_bps
    - slippage_bps
    - drawdown_penalty_bps
    - regime_break_penalty_bps
    - excessive_hold_penalty_bps
)

reward_norm = tanh(reward_bps / config.bandit.reward_scale_bps)

-------------------------------------------------------------------------------
Exploration Controls
-------------------------------------------------------------------------------

Never explore invalid pairs.

Only explore among HARD-VALID pairs.

Start with exploration disabled in live mode.

Safe exploration schedule:

- shadow only: may simulate exploration
- live phase 1: exploration_budget = 0.00
- live phase 2: exploration_budget = 0.01
- live phase 3: exploration_budget = 0.03
- live max: exploration_budget = 0.05

Safety filters:

- break_risk <= 0.60
- liquidity_score >= 0.50
- not graveyard
- not stale orderbook
- no position desync

================================================================================
11. FINAL RANKING STACK
================================================================================

Pipeline:

RawCandidate
→ DataValidation
→ HardValidation
→ ValidPairCandidate
→ RegimeDetection
→ BayesianPairScoring
→ OnlineLearningRanking
→ FinalRanking

-------------------------------------------------------------------------------
FinalPairRank
-------------------------------------------------------------------------------

@dataclass
class FinalPairRank:
    pair: PairIdentity
    hard_valid: bool
    final_score: float
    raw_score: float
    regime_score: float
    bayesian_score: float
    bandit_score: float
    reputation_score: float
    risk_penalty: float
    quality_grade: str
    reasons: list[str]

-------------------------------------------------------------------------------
Final Score Formula
-------------------------------------------------------------------------------

If hard_valid is False:

final_score = 0.0

Else:

raw_score = (
    regime_score
    * bayesian_score
    * bandit_score
    * reputation_score
    * (1.0 - risk_penalty)
)

Because some multipliers can exceed 1.0, raw_score is a relative score.

To produce a bounded final_score in [0, 1]:

final_score = clamp01(raw_score / config.ranking.final_score_soft_cap)

Default:

final_score_soft_cap = 1.50

Interpretation:

- raw_score: relative rank strength
- final_score: normalized dashboard-safe score

regime_score:
    mean_reverting high confidence -> 1.20
    unknown -> 0.90
    high volatility -> 0.85
    trending -> 0.60
    correlation breakdown -> 0.30
    liquidity stress -> 0.25
    structural break -> 0.0

reputation_score:
    elite -> 1.15
    stable -> 1.00
    warning -> 0.75
    hospital -> 0.25
    graveyard -> 0.0

risk_penalty:

Use explicit aliases:

slippage_risk = slippage_score
hedge_ratio_drift_risk = normalized_beta_drift

risk_penalty = clamp01(
    0.35 * break_risk
    + 0.25 * slippage_risk
    + 0.20 * liquidity_stress
    + 0.20 * hedge_ratio_drift_risk
)

================================================================================
12. PROBABILISTIC TRADE EXIT MANAGEMENT
================================================================================

Goal:

Upgrade the existing AdvancedTradeManager without deleting its hard exits.

Existing rule-based logic remains available.

New exit engine must support:

- shadow mode
- live mode
- rollback to old rule engine
- dashboard metrics
- post-trade outcome learning

Architecture:

OpenPosition
→ UpdateTradeFeatures
→ HardKillSwitches
→ ProbabilisticExitScoring
→ ExpectedValueDecision
→ MicrostructureModifier
→ DynamicExitSizing
→ FinalExitDecision
→ ExecuteOrShadowLog
→ LearnFromOutcome

-------------------------------------------------------------------------------
ExitAction
-------------------------------------------------------------------------------

class ExitAction(str, Enum):
    HOLD = "hold"
    TIGHTEN_STOP = "tighten_stop"
    PARTIAL_EXIT = "partial_exit"
    FULL_EXIT = "full_exit"
    FREEZE_NEW_ENTRIES = "freeze_new_entries"

-------------------------------------------------------------------------------
ExitScores
-------------------------------------------------------------------------------

@dataclass
class ExitScores:
    take_profit_score: float
    stall_score: float
    regime_break_score: float
    liquidity_risk_score: float
    execution_risk_score: float
    mean_reversion_score: float
    trend_continuation_risk: float
    drawdown_risk_score: float
    time_risk_score: float
    trailing_stop_pressure: float
    risk_pressure_score: float
    total_exit_score: float

-------------------------------------------------------------------------------
ExitDecision
-------------------------------------------------------------------------------

@dataclass
class ExitDecision:
    action: ExitAction
    exit_percentage: float
    reason: str
    scores: ExitScores
    ev: "ExpectedValueDecision"
    microstructure: "MicrostructureExitResult"
    hard_kill_triggered: bool
    blocked_by_net_profit_guard: bool
    metadata: dict[str, Any]

================================================================================
12.1 HARD KILL SWITCHES
================================================================================

Hard kill exits override probabilistic scoring.

Immediate / near-immediate risk exits:

- max hold time exceeded
- catastrophic divergence:
    abs(current_z) > abs(entry_z) + catastrophic_divergence_sigma
- confirmed structural break:
    regime == STRUCTURAL_BREAK and confidence >= threshold
- sustained sign flip:
    opposite sign and abs(z) > sign_flip_z_threshold for N seconds
- stale orderbook:
    freshness_ms > max_book_staleness_ms
- liquidity collapse:
    liquidity_score < min_exit_liquidity_score
- API/feed degradation:
    missing updates for N seconds
- position desync:
    local position != exchange position
- risk limit breach:
    drawdown or exposure exceeds config

@dataclass
class HardKillResult:
    triggered: bool
    action: ExitAction
    exit_percentage: float
    reason: str
    severity: float

Rules:

- hard kill result overrides probabilistic scoring
- net profit guard may block only soft profit exits, not catastrophic risk exits
- safety exits should not wait for positive pnl

================================================================================
12.2 PROBABILISTIC EXIT SCORING
================================================================================

Separate risk pressure from hold support.

Risk weights must sum to 1.0.

@dataclass
class ExitRiskWeights:
    take_profit: float = 0.16
    stall: float = 0.14
    regime_break: float = 0.22
    liquidity: float = 0.14
    execution: float = 0.10
    drawdown: float = 0.10
    trend: float = 0.09
    time_risk: float = 0.05

    def validate(self) -> None:
        total = (
            self.take_profit + self.stall + self.regime_break
            + self.liquidity + self.execution + self.drawdown
            + self.trend + self.time_risk
        )
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Exit risk weights must sum to 1.0, got {total}")


-------------------------------------------------------------------------------
Required Exit Sub-Score Formulas
-------------------------------------------------------------------------------

trend_continuation_risk:

trend_continuation_risk = clamp01(
    0.50 * trend_score
    + 0.30 * adverse_z_velocity_score
    + 0.20 * normalized_spread_vol_spike
)

Execution risk sub-scores:

taker_cost_score = clamp01(
    expected_taker_fee_bps / max(config.microstructure.max_allowed_slippage_bps, 1e-9)
)

low_maker_fill_score = 1.0 - clamp01(recent_maker_fill_probability)

capacity_pressure_score = clamp01(
    desired_exit_notional_usdt / max(order_capacity_usdt, 1e-9)
)

api_health_score = clamp01(
    api_latency_ms / max(config.microstructure.max_book_age_ms, 1e-9)
)

recent_order_failure_score = clamp01(
    recent_order_failures / max(config.execution_failure_window if available else 10, 1)
)

execution_risk_score = clamp01(
    0.30 * taker_cost_score
    + 0.25 * low_maker_fill_score
    + 0.20 * capacity_pressure_score
    + 0.15 * api_health_score
    + 0.10 * recent_order_failure_score
)

Drawdown risk:

drawdown_risk_score = clamp01(
    current_drawdown_usdt / max(config.exit.max_drawdown_usdt, 1e-9)
)

If current_drawdown_usdt is unavailable:

drawdown_risk_score = 0.0

Formula:

risk_pressure_score = (
    w.take_profit * take_profit_score
    + w.stall * stall_score
    + w.regime_break * regime_break_score
    + w.liquidity * liquidity_risk_score
    + w.execution * execution_risk_score
    + w.drawdown * drawdown_risk_score
    + w.trend * trend_continuation_risk
    + w.time_risk * time_risk_score
)

hold_discount = 1.0 - config.exit.mean_reversion_hold_discount * mean_reversion_score

microstructure multiplier is applied after EV is computed.

pre_microstructure_exit_score = clamp01(
    risk_pressure_score * hold_discount
)

total_exit_score = clamp01(
    pre_microstructure_exit_score * microstructure.exit_urgency_multiplier
)

Action mapping uses total_exit_score:

score < 0.30:
    HOLD
0.30 <= score < 0.55:
    TIGHTEN_STOP
0.55 <= score < 0.75:
    PARTIAL_EXIT
score >= 0.75:
    FULL_EXIT

-------------------------------------------------------------------------------
Explicit Stall Formula
-------------------------------------------------------------------------------

Define expected_progress_sigma.

half_life_seconds = max(
    estimated_half_life_seconds or config.exit.default_half_life_seconds,
    1.0
)

expected_progress_fraction = 1.0 - exp(
    -time_in_trade_seconds / half_life_seconds
)

expected_progress_sigma = max(
    abs_entry_z * expected_progress_fraction,
    config.exit.min_expected_progress_sigma
)

actual_progress_sigma = abs_entry_z - abs_current_z

stall_ratio = 1.0 - clamp01(
    actual_progress_sigma / expected_progress_sigma
)

abs_z_increasing_or_flat = abs_current_z >= abs_previous_z

velocity_bad = 1.0 if abs_z_increasing_or_flat else 0.0

time_pressure = clamp01(
    time_in_trade_seconds / max(config.exit.max_hold_seconds, 1.0)
)

abs_z_still_high = clamp01(
    abs_current_z / max(config.exit.z_still_high_threshold, 1e-9)
)

stall_score = clamp01(
    0.45 * stall_ratio
    + 0.25 * velocity_bad
    + 0.20 * time_pressure
    + 0.10 * abs_z_still_high
)

================================================================================
12.3 EXPECTED VALUE HOLD/EXIT DECISION
================================================================================

Use a 3-outcome EV model:

- reversion
- adverse move
- neutral/no meaningful move

Do not force p_reversion + p_adverse = 1 unless their sum exceeds 1.

-------------------------------------------------------------------------------
ExpectedValueDecision
-------------------------------------------------------------------------------

@dataclass
class ExpectedValueDecision:
    expected_hold_value_usdt: float
    expected_hold_value_bps: float
    probability_of_reversion: float
    probability_of_adverse_move: float
    probability_of_neutral: float
    expected_gain_usdt: float
    expected_loss_usdt: float
    expected_fees_usdt: float
    expected_slippage_usdt: float
    time_risk_penalty_usdt: float
    recommendation: ExitAction
    reasons: list[str]


-------------------------------------------------------------------------------
EV Input Aliases
-------------------------------------------------------------------------------

Use the following already-computed values:

spread_volatility_spike_score = normalized_spread_vol_spike
low_break_risk_score = 1.0 - break_risk

half_life_score = clamp01(
    1.0 - (
        time_in_trade_seconds
        / max(2.0 * half_life_seconds, 1.0)
    )
)

z_history_tail = z_history_values[-config.ev.recent_z_vol_window:]

recent_z_volatility = (
    float(np.std(z_history_tail))
    if len(z_history_tail) >= 2
    else 0.0
)

time_pressure_hours = time_in_trade_seconds / 3600.0

target_exit_z = config.ev.target_exit_z
expected_exit_fee_rate = config.ev.exit_fee_rate

-------------------------------------------------------------------------------
Probability Model
-------------------------------------------------------------------------------

p_reversion = clamp01(
    0.30 * bayesian_posterior
    + 0.25 * regime_mean_reversion_confidence
    + 0.15 * z_velocity_toward_mean_score
    + 0.10 * half_life_score
    + 0.10 * low_break_risk_score
    + 0.10 * liquidity_score
)

p_adverse = clamp01(
    0.35 * break_risk
    + 0.20 * adverse_z_velocity_score
    + 0.15 * liquidity_risk_score
    + 0.15 * trend_continuation_risk
    + 0.15 * spread_volatility_spike_score
)

if p_reversion + p_adverse > 1.0:
    total = p_reversion + p_adverse
    p_reversion = p_reversion / total
    p_adverse = p_adverse / total
    p_neutral = 0.0
else:
    p_neutral = 1.0 - p_reversion - p_adverse

-------------------------------------------------------------------------------
Expected Spread Edge Per Sigma
-------------------------------------------------------------------------------

Do not leave estimated_spread_edge_per_sigma undefined.

Use:

if config.ev.use_historical_spread_edge and historical_sigma_pnl_samples exist:
    spread_edge_per_sigma_usdt = median(abs(pnl_usdt_per_sigma_move))
else:
    spread_edge_per_sigma_usdt = config.ev.spread_edge_per_sigma_usdt
    if config.ev.warn_when_using_default_spread_edge:
        logger.warning(
            "Using default spread_edge_per_sigma_usdt; calibrate with historical trades."
        )

Then clamp:

spread_edge_per_sigma_usdt = clamp(
    spread_edge_per_sigma_usdt,
    config.ev.min_spread_edge_per_sigma_usdt,
    config.ev.max_spread_edge_per_sigma_usdt,
)

-------------------------------------------------------------------------------
Expected Gain / Loss
-------------------------------------------------------------------------------

remaining_z_move = max(abs_current_z - config.ev.target_exit_z, 0.0)

expected_gain_usdt = (
    position_notional_usdt
    * spread_edge_per_sigma_usdt
    * remaining_z_move
)

adverse_z_move = max(
    config.ev.expected_adverse_sigma_move,
    recent_z_volatility
)

expected_loss_usdt = (
    position_notional_usdt
    * spread_edge_per_sigma_usdt
    * adverse_z_move
)

expected_fees_usdt = config.ev.exit_fee_rate * exit_notional_usdt

expected_slippage_usdt = (
    slippage_estimate_bps / 10000.0
) * exit_notional_usdt

time_risk_penalty_usdt = (
    position_notional_usdt
    * config.ev.time_penalty_rate_per_hour
    * time_pressure_hours
)

EV:

expected_hold_value_usdt = (
    p_reversion * expected_gain_usdt
    - p_adverse * expected_loss_usdt
    + p_neutral * 0.0
    - expected_fees_usdt
    - expected_slippage_usdt
    - time_risk_penalty_usdt
)

Decision:

IMPORTANT:

EV must use pre_microstructure_exit_score or risk_pressure_score for threshold context.
Do not reference total_exit_score before microstructure is applied.

if EV > config.ev.strong_positive_ev_usdt:
    recommendation = HOLD
elif EV > config.ev.weak_positive_ev_usdt and pre_microstructure_exit_score < config.exit.exit_tighten_threshold:
    recommendation = TIGHTEN_STOP
elif EV >= config.ev.near_zero_ev_usdt:
    recommendation = PARTIAL_EXIT
else:
    recommendation = FULL_EXIT

Slippage note:

- EV subtracts expected slippage as direct cost.
- exit_score uses slippage as urgency/risk pressure.
- To avoid double domination:
  - cap slippage contribution inside exit score using config.microstructure.exit_score_slippage_cap
  - use raw slippage estimate in EV

================================================================================
12.4 MICROSTRUCTURE EXIT INTELLIGENCE
================================================================================

-------------------------------------------------------------------------------
MicrostructureExitResult
-------------------------------------------------------------------------------

@dataclass
class MicrostructureExitResult:
    liquidity_fresh: bool
    book_stress_score: float
    slippage_risk_score: float
    depth_imbalance_score: float
    exit_urgency_multiplier: float
    recommended_order_style: str
    reasons: list[str]
    metrics: dict[str, float]

-------------------------------------------------------------------------------
Formula
-------------------------------------------------------------------------------

stale_book_score = clamp01(
    (update_age_ms / config.microstructure.max_book_age_ms) - 1.0
)

depth_imbalance_score = clamp01(
    abs(bid_depth - ask_depth) / max(bid_depth + ask_depth, 1e-9)
)

raw_slippage_risk_score = clamp01(
    estimated_slippage_bps / max(config.microstructure.max_allowed_slippage_bps, 1e-9)
)

slippage_risk_score_for_exit_score = min(
    raw_slippage_risk_score,
    config.microstructure.exit_score_slippage_cap
)

book_stress_score = clamp01(
    0.30 * stale_book_score
    + 0.25 * spread_widening_score
    + 0.20 * slippage_risk_score_for_exit_score
    + 0.15 * depth_imbalance_score
    + 0.10 * low_depth_score
)

exit_urgency_multiplier = min(
    1.0 + config.microstructure.max_urgency_boost * book_stress_score,
    config.microstructure.max_exit_urgency_multiplier
)

Order style:

if not liquidity_fresh:
    recommended_order_style = "wait" unless hard_kill_triggered
elif (
    book_stress_score >= config.microstructure.severe_book_stress_threshold
    and adverse_z_velocity_score >= config.microstructure.fast_adverse_threshold
):
    recommended_order_style = "taker"
elif book_stress_score >= 0.60:
    recommended_order_style = "split"
elif (
    spread_bps >= config.microstructure.wide_spread_bps
    and regime not in (RegimeName.TRENDING, RegimeName.STRUCTURAL_BREAK)
):
    recommended_order_style = "maker"
else:
    recommended_order_style = "split"

================================================================================
12.5 DYNAMIC PARTIAL EXIT SIZING
================================================================================

Use risk_pressure_score instead of total_exit_score to avoid double-counting microstructure.

Do not double-count regime_break_score if it is already in risk_pressure_score.

Use break_risk from regime detection as an extra independent risk input instead.

positive_ev_score = clamp01(
    max(ev.expected_hold_value_usdt, 0.0)
    / max(config.ev.strong_positive_ev_usdt, 1e-9)
)

liquidity_stress_score = microstructure.book_stress_score

risk_score = clamp01(
    0.35 * risk_pressure_score
    + 0.20 * break_risk
    + 0.20 * liquidity_stress_score
    + 0.15 * execution_risk_score
    + 0.10 * drawdown_risk_score
)

if hard_kill_triggered:
    exit_percentage = 1.0
else:
    exit_percentage = clamp(
        config.exit.base_partial_exit
        + 0.40 * risk_score
        - 0.20 * positive_ev_score
        + 0.20 * liquidity_stress_score,
        config.exit.min_partial_exit,
        config.exit.max_partial_exit,
    )

Round exit_percentage to exchange-compatible position precision.

================================================================================
13. SHADOW MODE
================================================================================

Shadow mode must not execute new policy.

In shadow mode:

- existing AdvancedTradeManager still controls real exits
- new probabilistic engine computes recommendation only
- log both old_action and new_action
- store decision snapshot
- compute counterfactual metrics after trade close

-------------------------------------------------------------------------------
ShadowDecisionRecord
-------------------------------------------------------------------------------

@dataclass
class ShadowDecisionRecord:
    pair: PairIdentity
    timestamp: float
    old_action: str
    new_action: str
    old_reason: str
    new_reason: str
    exit_score: float
    expected_hold_value_usdt: float
    microstructure_stress: float
    trade_features: dict[str, Any]

Do NOT include would_have_exited_earlier/later here because those are unknowable at decision time.

-------------------------------------------------------------------------------
PostTradeShadowReport
-------------------------------------------------------------------------------

@dataclass
class PostTradeShadowReport:
    pair: PairIdentity
    trade_id: str
    agreement_rate: float
    disagreement_rate: float
    would_have_exited_earlier_count: int
    would_have_exited_later_count: int
    avoided_loss_estimate_usdt: float
    missed_profit_estimate_usdt: float
    net_policy_delta_usdt: float
    false_exit_rate_estimate: float
    late_exit_rate_estimate: float
    exit_time_distribution_shift_seconds: float

Circuit breakers:

If shadow disagreement rate > config.pipeline.max_shadow_disagreement_rate over last config.pipeline.shadow_eval_window trades:
    disable advanced live exits

If shadow net_policy_delta_usdt < config.pipeline.min_shadow_policy_delta_usdt over last config.pipeline.shadow_eval_window trades:
    keep shadow mode enabled and do not promote to live

================================================================================
14. LEARNED EXIT POLICY
================================================================================

Store trade outcomes:

@dataclass
class ExitOutcome:
    pair: PairIdentity
    entry_ts: float
    exit_ts: float
    exit_reason: str
    exit_action: str
    exit_percentage: float
    exit_score: float
    ev_estimate_usdt: float
    realized_pnl_usdt: float
    realized_pnl_bps: float
    fees_usdt: float
    slippage_usdt: float
    missed_profit_after_exit_usdt: float | None
    avoided_loss_after_exit_usdt: float | None
    regime_at_exit: str
    book_stress_at_exit: float
    hold_time_seconds: float

Learning updates:

- update Bayesian exit efficiency
- update bandit reward
- update pair reputation
- optionally adjust exit score weights within safe bounded ranges

Do not allow learned policy to change:

- hard kill switch thresholds beyond configured safety bounds
- max exposure
- max hold
- exchange risk limits
- stale feed behavior

================================================================================
15. OBSERVABILITY AND DASHBOARD METRICS
================================================================================

Use structured logs with a decision_id / trace_id per decision.

Expose dashboard metrics:

Per pair:

- hard validation status
- regime
- regime confidence
- break risk
- Bayesian posterior
- Bayesian CI
- Bayesian evidence count
- quality grade
- bandit expected reward
- bandit uncertainty
- final rank score
- pair reputation state
- reasons

Per open trade:

- hard kill status
- risk pressure score
- pre-microstructure exit score
- total exit score
- exit action recommendation
- expected hold value
- probability of reversion
- probability of adverse move
- probability of neutral
- book stress
- slippage risk
- recommended order style
- dynamic exit percentage
- shadow disagreement status

Strategy-level:

- shadow agreement rate
- shadow net policy delta
- advanced policy enabled/disabled
- model state flush status
- feature NaN rejection count
- hard validation rejection count
- emergency circuit breaker status
- state recovery fallback count
- schema mismatch count

================================================================================
16. TESTING REQUIREMENTS
================================================================================

Tests must validate math and behavior, not only types.

-------------------------------------------------------------------------------
Feature Schema Tests
-------------------------------------------------------------------------------

- schema rejects wrong vector length
- schema rejects NaN/inf
- schema get("liquidity_score") returns correct index
- changing feature order changes index deterministically
- saved schema includes version
- schema version mismatch fails closed

-------------------------------------------------------------------------------
Model State Tests
-------------------------------------------------------------------------------

- missing state initializes safe defaults
- corrupted JSON initializes safe defaults and logs critical warning
- atomic write writes temp file then renames
- schema mismatch prevents old model weights from loading

-------------------------------------------------------------------------------
Regime Tests
-------------------------------------------------------------------------------

- stable decreasing abs(z) with low drift -> MEAN_REVERTING
- increasing abs(z) + high corr drift -> CORRELATION_BREAKDOWN or STRUCTURAL_BREAK
- stale/wide orderbook -> LIQUIDITY_STRESS
- adverse_acceleration_score increases with adverse acceleration
- normalized_spread_vol_spike increases with realized vol spike
- mr_confidence components are finite and bounded
- trend_score formula increases with adverse velocity and acceleration
- realized_vol thresholds classify high/low volatility correctly

-------------------------------------------------------------------------------
Bayesian Tests
-------------------------------------------------------------------------------

- sparse data returns neutral-ish posterior near 0.5
- low evidence caps grade at C
- 10 consecutive successes raises posterior above 0.75
- 10 consecutive failures drops posterior below 0.30
- feature multipliers alter posterior in expected direction
- failed hard validation returns posterior 0.0 and grade D

-------------------------------------------------------------------------------
LinUCB Tests
-------------------------------------------------------------------------------

- A matrix updates correctly after reward
- b vector updates correctly after reward
- exploration_bonus shrinks as same context is repeatedly seen
- regularization does not vanish after many decayed updates
- invalid candidates are never selected

-------------------------------------------------------------------------------
Final Ranker Tests
-------------------------------------------------------------------------------

- invalid candidate final_score is 0.0
- elite + mean-reverting pair has higher score than warning + trending pair
- final_score is clamped to [0, 1]
- raw_score can exceed 1.0 but final_score remains safe

-------------------------------------------------------------------------------
EV Tests
-------------------------------------------------------------------------------

- p_neutral exists when p_reversion + p_adverse < 1
- only normalize p_reversion/p_adverse if sum > 1
- positive EV recommends HOLD/TIGHTEN
- negative EV recommends PARTIAL/FULL
- high slippage reduces EV
- EV uses pre_microstructure_exit_score, not total_exit_score before microstructure is applied
- spread_edge_per_sigma_usdt uses historical median when available and config default otherwise

-------------------------------------------------------------------------------
Microstructure Tests
-------------------------------------------------------------------------------

- stale book produces liquidity_fresh=False
- severe book stress increases urgency multiplier
- urgency multiplier never exceeds max_exit_urgency_multiplier
- slippage contribution to exit_score is capped
- wide spread + stable regime prefers maker/split
- fast adverse + thin book prefers taker

-------------------------------------------------------------------------------
End-to-End Pipeline Tests
-------------------------------------------------------------------------------

- invalid pair fails HardValidationResult
- invalid pair cannot be wrapped as ValidPairCandidate
- invalid pair does not enter regime detection
- invalid pair does not enter Bayesian scoring
- invalid pair does not enter LinUCB/bandit scoring
- invalid pair returns final_score = 0.0
- shadow ranking records failed validation reason

-------------------------------------------------------------------------------
Exit Manager Tests
-------------------------------------------------------------------------------

- hard kill overrides soft scoring
- net profit guard blocks soft profit exits only, not catastrophic risk exits
- dynamic partial size increases with risk
- positive EV reduces partial exit size
- dynamic risk_score does not double-count regime_break_score through total_exit_score
- shadow mode does not execute new policy
- ShadowDecisionRecord does not contain post-trade-only fields

================================================================================
17. MIGRATION PLAN
================================================================================

Phase 0:
- Save this document as ARCHITECTURE_ADVANCED_ML_V3_1.md.
- Ask Codex only to summarize module dependencies.
- Do not generate code yet.

Phase 1:
- implement split config dataclasses
- implement core types
- implement BotAdapterSpec
- implement FeatureSchema / NamedFeatureVector
- implement ModelStateStore

Phase 2:
- implement heuristic regime detector
- implement microstructure analyzer
- add dashboard logging only

Phase 3:
- implement Bayesian scorer
- implement final ranker
- run shadow ranking beside current ranking

Phase 4:
- implement LinUCB contextual bandit
- update after closed trades only
- keep live exploration disabled

Phase 5:
- implement probabilistic exit manager in shadow mode
- compare old vs new exit decisions
- generate PostTradeShadowReport

Phase 6:
- enable advanced exits only for:
  - elite/stable pairs
  - low break risk
  - fresh orderbook
  - small position size
  - positive shadow-mode report

Phase 7:
- gradual rollout:
  - 10% trades
  - 25% trades
  - 50% trades
  - 100% only after shadow report remains positive

================================================================================
18. CODEX FILE-BY-FILE EXECUTION PLAN
================================================================================

Use prompts like these.

Prompt 1:

"Read ARCHITECTURE_ADVANCED_ML_V3_1.md. Do not write code yet. Summarize the dependency map between adapters, features, regime, bayes, online_learning, ranking, microstructure, ev, and trade_management."

Prompt 2:

"Implement only core/config/advanced_ml_config.py. Reminder: split config into nested dataclasses exactly as specified. Do not create a valid_only_pipeline flag. Include shadow_eval_window, EV utility fields, microstructure order-style thresholds, regime hysteresis fields, and max_drawdown_usdt."

Prompt 3:

"Implement only core/features/feature_schema.py and tests/test_feature_schema.py. Reminder: include feature_schema_version, schema validation, NaN rejection, and version mismatch behavior."

Prompt 4:

"Implement only core/adapters/bot_adapter_types.py. Reminder: create Protocols only; do not guess existing bot class names."

Prompt 5:

"Implement only core/storage/model_state_store.py and tests/test_model_state_store.py. Reminder: atomic writes, corrupted JSON fallback to safe defaults, critical logging, and no bot crash."

Prompt 6:

"Implement only core/regime/regime_types.py, core/regime/transition_matrix.py, and tests/test_transition_matrix.py. Reminder: transition weights are decayed floats, not integer counts."

Prompt 7:

"Implement only core/regime/heuristic_regime_detector.py and tests/test_regime_detector.py. Reminder: implement the explicit formulas exactly, including the real rolling baseline volatility computation, adverse_acceleration_score, normalized_spread_vol_spike, liquidity_stress, trend_score, regime aliases, hysteresis, and all mr_confidence sub-scores."

Prompt 8:

"Implement only core/bayes/bayesian_pair_scorer.py and tests/test_bayesian_pair_scorer.py. Reminder: hard validation failure returns posterior 0.0/grade D, low evidence caps grade, and updates must be thread-safe with to_dict/from_dict."

Prompt 9:

"Implement only core/online_learning/linucb.py and tests/test_linucb.py. Reminder: preserve regularization under decay with A = decay*A + (1-decay)*lambda_reg*I + outer(x,x), and validate FeatureSchema before matrix math."

Prompt 10:

"Implement only core/ranking/final_ranker.py and tests/test_final_ranker.py. Reminder: accept only ValidPairCandidate objects and clamp final_score to [0,1] using final_score_soft_cap."

Prompt 11:

"Implement only core/microstructure/microstructure_analyzer.py and tests/test_microstructure_analyzer.py. Reminder: cap slippage contribution to exit_score but keep raw slippage for EV. Replace order-style pseudocode with fast_adverse_threshold and wide_spread_bps config fields."

Prompt 12:

"Implement only core/ev/hold_exit_ev.py and tests/test_ev_decision.py. Reminder: use the 3-outcome EV model with neutral probability, define recent_z_volatility/time_pressure_hours/target_exit_z/exit_fee_rate/expected_adverse_sigma_move, and use pre_microstructure_exit_score instead of total_exit_score before microstructure is applied."

Prompt 13:

"Implement only core/trade_management/probabilistic_exit_manager.py and tests/test_probabilistic_exit_manager.py. Reminder: ExistingBotAdapter only, hard kills override soft scoring, no execution in shadow mode, define trend_continuation_risk/execution_risk_score/drawdown_risk_score exactly, and ShadowDecisionRecord must not contain post-trade-only fields."

================================================================================
19. OPTIONAL FUTURE EXTENSIONS — DO NOT IMPLEMENT IN MVP
================================================================================

Only after MVP is stable, consider:


- GlobalMarketContext placeholder interface:

@dataclass
class GlobalMarketContext:
    timestamp: float
    btc_volatility_state: str | None = None
    eth_volatility_state: str | None = None
    total_market_volatility_score: float | None = None
    funding_stress_score: float | None = None
    exchange_liquidity_stress_score: float | None = None
    risk_on_off_score: float | None = None

This is a placeholder only in MVP.
Do not allow it to override hard validation.


- Hierarchical Bayesian priors:
  - family-level priors
  - sector priors
  - liquidity-bucket priors

- Dirichlet-Multinomial outcome model:
  - big win
  - small win
  - breakeven
  - loss
  - disaster

- HMM / Bayesian regime switching
- Hypothesis property-based tests
- Prometheus / OpenTelemetry metrics
- replay simulation engine with slippage, queue position, partial fills, and funding

================================================================================
20. ACCEPTANCE CRITERIA
================================================================================

Implementation is complete when:

- all modules are typed
- all new systems are config-driven
- split config dataclasses exist
- all tests pass
- explicit formulas are implemented exactly
- no remaining formula pseudocode such as 'if available', 'is wide', or 'move is fast'
- order-style rules use concrete config thresholds
- EVConfig contains all variables used in EV formulas
- circuit breakers use config.pipeline.shadow_eval_window
- existing hard validation is untouched
- invalid candidates cannot enter downstream scoring as valid candidates
- new ranking never admits invalid pairs
- model states can be saved and loaded
- corrupted/missing state recovers safely
- feature schema versioning prevents incompatible model loads
- thread-safe updates exist for mutable learning state
- shadow mode can compare old and new exits
- post-trade shadow report computes counterfactual metrics after trade close
- dashboard metrics are serializable
- bot can run with new systems disabled
- bot can run with shadow mode enabled
- bot can run with live advanced mode enabled only by config

================================================================================
FINAL INSTRUCTION TO CODEX
================================================================================

Inspect the existing repository before editing.

Do not rewrite unrelated code.

Do not implement all modules at once.

Prefer small, reviewable patches.

Start by adding config, types, interfaces, and tests.

Keep backward compatibility with the existing AdvancedTradeManager.

Do not remove the current rule-based exits.

Add the probabilistic engine beside it first, using shadow mode.

Generate production-ready Python code with clear interfaces, unit tests, logging, persistence, thread safety, and safe defaults.
