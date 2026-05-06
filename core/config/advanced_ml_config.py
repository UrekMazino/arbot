"""Configuration dataclasses for the advanced ML architecture.

These config objects are intentionally split by subsystem so downstream modules
can depend on only the knobs they actually use. Valid-only pipeline behavior is
mandatory in the architecture and is not represented as a configurable flag.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from typing import Any


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
class RolloutConfig:
    phase: int = 6
    live_trade_percentage: float = 0.10
    require_elite_or_stable_pair: bool = True
    require_positive_shadow_report: bool = True
    min_shadow_reports: int = 10
    max_phase6_break_risk: float = 0.30
    max_phase6_book_age_ms: float = 1500.0
    max_phase6_position_notional_usdt: float = 500.0
    decision_salt: str = "advanced_ml_v3_1"


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
class ExtensionConfig:
    hmm_regime_enabled: bool = False
    global_market_context_enabled: bool = False
    global_market_risk_weight: float = 0.15
    global_market_high_risk_threshold: float = 0.70
    global_market_low_risk_threshold: float = 0.30


@dataclass
class AdvancedMLConfig:
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    rollout: RolloutConfig = field(default_factory=RolloutConfig)
    persistence: PersistenceConfig = field(default_factory=PersistenceConfig)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    regime: RegimeConfig = field(default_factory=RegimeConfig)
    bayes: BayesianConfig = field(default_factory=BayesianConfig)
    bandit: BanditConfig = field(default_factory=BanditConfig)
    ranking: RankingConfig = field(default_factory=RankingConfig)
    microstructure: MicrostructureConfig = field(default_factory=MicrostructureConfig)
    ev: EVConfig = field(default_factory=EVConfig)
    exit: ExitConfig = field(default_factory=ExitConfig)
    extensions: ExtensionConfig = field(default_factory=ExtensionConfig)


_ENV_ALIASES: dict[tuple[str, str], tuple[str, ...]] = {
    ("pipeline", "enabled"): ("STATBOT_ADVANCED_ML_ENABLED",),
    ("pipeline", "shadow_mode"): (
        "STATBOT_ADVANCED_ML_SHADOW_MODE",
        "STATBOT_ADVANCED_ML_SHADOW",
    ),
    ("pipeline", "max_pairs_active"): ("STATBOT_ADVANCED_ML_MAX_PAIRS_ACTIVE",),
    ("pipeline", "emergency_disable_on_shadow_divergence"): (
        "STATBOT_ADVANCED_ML_EMERGENCY_DISABLE_ON_SHADOW_DIVERGENCE",
    ),
    ("pipeline", "max_shadow_disagreement_rate"): (
        "STATBOT_ADVANCED_ML_MAX_SHADOW_DISAGREEMENT_RATE",
    ),
    ("pipeline", "min_shadow_policy_delta_usdt"): (
        "STATBOT_ADVANCED_ML_MIN_SHADOW_POLICY_DELTA_USDT",
    ),
    ("pipeline", "audit_log_level"): ("STATBOT_ADVANCED_ML_AUDIT_LOG_LEVEL",),
    ("pipeline", "shadow_eval_window"): ("STATBOT_ADVANCED_ML_SHADOW_EVAL_WINDOW",),
    ("rollout", "phase"): ("STATBOT_ADVANCED_ML_ROLLOUT_PHASE",),
    ("rollout", "live_trade_percentage"): (
        "STATBOT_ADVANCED_ML_LIVE_TRADE_PERCENTAGE",
        "STATBOT_ADVANCED_ML_ROLLOUT_LIVE_TRADE_PERCENTAGE",
    ),
    ("rollout", "require_elite_or_stable_pair"): (
        "STATBOT_ADVANCED_ML_ROLLOUT_REQUIRE_ELITE_OR_STABLE_PAIR",
    ),
    ("rollout", "require_positive_shadow_report"): (
        "STATBOT_ADVANCED_ML_ROLLOUT_REQUIRE_POSITIVE_SHADOW_REPORT",
    ),
    ("rollout", "min_shadow_reports"): (
        "STATBOT_ADVANCED_ML_ROLLOUT_MIN_SHADOW_REPORTS",
    ),
    ("rollout", "max_phase6_break_risk"): (
        "STATBOT_ADVANCED_ML_ROLLOUT_MAX_PHASE6_BREAK_RISK",
    ),
    ("rollout", "max_phase6_book_age_ms"): (
        "STATBOT_ADVANCED_ML_ROLLOUT_MAX_PHASE6_BOOK_AGE_MS",
    ),
    ("rollout", "max_phase6_position_notional_usdt"): (
        "STATBOT_ADVANCED_ML_ROLLOUT_MAX_PHASE6_POSITION_NOTIONAL_USDT",
    ),
    ("rollout", "decision_salt"): ("STATBOT_ADVANCED_ML_ROLLOUT_DECISION_SALT",),
    ("persistence", "model_state_path"): ("STATBOT_ADVANCED_ML_MODEL_STATE_PATH",),
    ("persistence", "model_state_flush_ticks"): (
        "STATBOT_ADVANCED_ML_MODEL_STATE_FLUSH_TICKS",
    ),
    ("persistence", "model_state_flush_on_trade_close"): (
        "STATBOT_ADVANCED_ML_MODEL_STATE_FLUSH_ON_TRADE_CLOSE",
    ),
    ("features", "feature_schema_version"): (
        "STATBOT_ADVANCED_ML_FEATURE_SCHEMA_VERSION",
    ),
    ("features", "reject_nan_features"): ("STATBOT_ADVANCED_ML_REJECT_NAN_FEATURES",),
    ("ranking", "final_score_soft_cap"): ("STATBOT_ADVANCED_ML_FINAL_SCORE_SOFT_CAP",),
    ("microstructure", "max_book_age_ms"): ("STATBOT_ADVANCED_ML_MAX_BOOK_AGE_MS",),
    ("microstructure", "max_allowed_slippage_bps"): (
        "STATBOT_ADVANCED_ML_MAX_ALLOWED_SLIPPAGE_BPS",
    ),
    ("microstructure", "exit_score_slippage_cap"): (
        "STATBOT_ADVANCED_ML_EXIT_SCORE_SLIPPAGE_CAP",
    ),
    ("microstructure", "fast_adverse_threshold"): (
        "STATBOT_ADVANCED_ML_FAST_ADVERSE_THRESHOLD",
    ),
    ("microstructure", "wide_spread_bps"): ("STATBOT_ADVANCED_ML_WIDE_SPREAD_BPS",),
    ("ev", "time_penalty_rate_per_hour"): (
        "STATBOT_ADVANCED_ML_TIME_PENALTY_RATE_PER_HOUR",
    ),
    ("ev", "spread_edge_per_sigma_usdt"): (
        "STATBOT_ADVANCED_ML_SPREAD_EDGE_PER_SIGMA_USDT",
    ),
    ("ev", "expected_adverse_sigma_move"): (
        "STATBOT_ADVANCED_ML_EXPECTED_ADVERSE_SIGMA_MOVE",
    ),
    ("ev", "target_exit_z"): ("STATBOT_ADVANCED_ML_TARGET_EXIT_Z",),
    ("ev", "exit_fee_rate"): ("STATBOT_ADVANCED_ML_EXIT_FEE_RATE",),
    ("exit", "exit_hold_threshold"): ("STATBOT_ADVANCED_ML_EXIT_HOLD_THRESHOLD",),
    ("exit", "exit_tighten_threshold"): (
        "STATBOT_ADVANCED_ML_EXIT_TIGHTEN_THRESHOLD",
    ),
    ("exit", "exit_partial_threshold"): (
        "STATBOT_ADVANCED_ML_EXIT_PARTIAL_THRESHOLD",
    ),
    ("exit", "max_hold_seconds"): ("STATBOT_ADVANCED_ML_MAX_HOLD_SECONDS",),
    ("exit", "max_drawdown_usdt"): ("STATBOT_ADVANCED_ML_MAX_DRAWDOWN_USDT",),
    ("regime", "min_regime_persistence_ticks"): (
        "STATBOT_ADVANCED_ML_MIN_REGIME_PERSISTENCE_TICKS",
    ),
    ("regime", "regime_switch_cooldown_seconds"): (
        "STATBOT_ADVANCED_ML_REGIME_SWITCH_COOLDOWN_SECONDS",
    ),
    ("regime", "regime_switch_confidence_margin"): (
        "STATBOT_ADVANCED_ML_REGIME_SWITCH_CONFIDENCE_MARGIN",
    ),
    ("extensions", "hmm_regime_enabled"): (
        "STATBOT_ADVANCED_ML_HMM_REGIME_ENABLED",
    ),
    ("extensions", "global_market_context_enabled"): (
        "STATBOT_ADVANCED_ML_GLOBAL_MARKET_CONTEXT_ENABLED",
    ),
    ("extensions", "global_market_risk_weight"): (
        "STATBOT_ADVANCED_ML_GLOBAL_MARKET_RISK_WEIGHT",
    ),
    ("extensions", "global_market_high_risk_threshold"): (
        "STATBOT_ADVANCED_ML_GLOBAL_MARKET_HIGH_RISK_THRESHOLD",
    ),
    ("extensions", "global_market_low_risk_threshold"): (
        "STATBOT_ADVANCED_ML_GLOBAL_MARKET_LOW_RISK_THRESHOLD",
    ),
}


def load_advanced_ml_config_from_env(
    env: Mapping[str, str] | None = None,
) -> AdvancedMLConfig:
    """Build AdvancedMLConfig from STATBOT_ADVANCED_ML_* environment values.

    Missing or malformed values keep dataclass defaults so runtime startup does
    not fail because of a mistyped optional tuning field.
    """

    source = os.environ if env is None else env
    config = AdvancedMLConfig()
    for section_field in fields(config):
        section_name = section_field.name
        section = getattr(config, section_name)
        for value_field in fields(section):
            raw = _first_env_value(
                source,
                *_env_names_for_field(section_name, value_field.name),
            )
            if raw is None:
                continue
            current_value = getattr(section, value_field.name)
            setattr(section, value_field.name, _parse_env_value(raw, current_value))
    return config


def _env_names_for_field(section: str, field_name: str) -> tuple[str, ...]:
    aliases = _ENV_ALIASES.get((section, field_name), ())
    default_name = f"STATBOT_ADVANCED_ML_{section.upper()}_{field_name.upper()}"
    return (*aliases, default_name)


def _first_env_value(env: Mapping[str, str], *names: str) -> str | None:
    for name in names:
        raw = env.get(name)
        if raw is not None and str(raw).strip() != "":
            return str(raw).strip()
    return None


def _parse_env_value(raw: str, default: Any) -> Any:
    try:
        if isinstance(default, bool):
            return _parse_bool(raw, default)
        if isinstance(default, int) and not isinstance(default, bool):
            return int(float(raw))
        if isinstance(default, float):
            return float(raw)
        return str(raw)
    except (TypeError, ValueError):
        return default


def _parse_bool(raw: str, default: bool) -> bool:
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "on", "enabled", "active", "shadow"}:
        return True
    if value in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


__all__ = [
    "AdvancedMLConfig",
    "BanditConfig",
    "BayesianConfig",
    "EVConfig",
    "ExitConfig",
    "ExtensionConfig",
    "FeatureConfig",
    "MicrostructureConfig",
    "PersistenceConfig",
    "PipelineConfig",
    "RankingConfig",
    "RegimeConfig",
    "RolloutConfig",
    "load_advanced_ml_config_from_env",
]
