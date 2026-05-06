"""Configuration dataclasses for the advanced ML architecture.

These config objects are intentionally split by subsystem so downstream modules
can depend on only the knobs they actually use. Valid-only pipeline behavior is
mandatory in the architecture and is not represented as a configurable flag.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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


@dataclass
class PersistenceConfig:
    model_state_flush_ticks: int = 50
    model_state_flush_on_trade_close: bool = True
    model_state_path: str = "data/model_state"
    atomic_write: bool = True
    corrupted_state_policy: str = "safe_defaults"


@dataclass
class FeatureConfig:
    reject_nan_features: bool = True
    feature_schema_version: int = 1


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

    min_regime_persistence_ticks: int = 3
    regime_switch_cooldown_seconds: int = 60
    regime_switch_confidence_margin: float = 0.10


@dataclass
class BayesianConfig:
    alpha0: float = 2.0
    beta0: float = 2.0
    decay: float = 0.995
    feature_weight: float = 0.30
    min_evidence: int = 10
    max_grade_when_low_evidence: str = "C"


@dataclass
class BanditConfig:
    algorithm: str = "linucb"
    alpha: float = 0.75
    decay: float = 0.995
    lambda_reg: float = 1.0
    exploration_budget: float = 0.00
    max_live_exploration_budget: float = 0.05
    reward_scale_bps: float = 50.0


@dataclass
class RankingConfig:
    final_score_soft_cap: float = 1.50


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


__all__ = [
    "AdvancedMLConfig",
    "BanditConfig",
    "BayesianConfig",
    "EVConfig",
    "ExitConfig",
    "FeatureConfig",
    "MicrostructureConfig",
    "PersistenceConfig",
    "PipelineConfig",
    "RankingConfig",
    "RegimeConfig",
]
