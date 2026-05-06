from __future__ import annotations

from core.config.advanced_ml_config import AdvancedMLConfig, load_advanced_ml_config_from_env


def test_load_advanced_ml_config_from_env_maps_shadow_pipeline_aliases():
    config = load_advanced_ml_config_from_env(
        {
            "STATBOT_ADVANCED_ML_ENABLED": "1",
            "STATBOT_ADVANCED_ML_SHADOW": "0",
            "STATBOT_ADVANCED_ML_SHADOW_EVAL_WINDOW": "25",
            "STATBOT_ADVANCED_ML_MAX_SHADOW_DISAGREEMENT_RATE": "0.15",
            "STATBOT_ADVANCED_ML_MIN_SHADOW_POLICY_DELTA_USDT": "3.5",
            "STATBOT_ADVANCED_ML_EMERGENCY_DISABLE_ON_SHADOW_DIVERGENCE": "false",
            "STATBOT_ADVANCED_ML_ROLLOUT_PHASE": "7",
            "STATBOT_ADVANCED_ML_LIVE_TRADE_PERCENTAGE": "0.25",
            "STATBOT_ADVANCED_ML_ROLLOUT_REQUIRE_POSITIVE_SHADOW_REPORT": "0",
        }
    )

    assert config.pipeline.enabled is True
    assert config.pipeline.shadow_mode is False
    assert config.pipeline.shadow_eval_window == 25
    assert config.pipeline.max_shadow_disagreement_rate == 0.15
    assert config.pipeline.min_shadow_policy_delta_usdt == 3.5
    assert config.pipeline.emergency_disable_on_shadow_divergence is False
    assert config.rollout.phase == 7
    assert config.rollout.live_trade_percentage == 0.25
    assert config.rollout.require_positive_shadow_report is False


def test_load_advanced_ml_config_from_env_maps_subsystem_thresholds():
    config = load_advanced_ml_config_from_env(
        {
            "STATBOT_ADVANCED_ML_FEATURE_SCHEMA_VERSION": "4",
            "STATBOT_ADVANCED_ML_REJECT_NAN_FEATURES": "0",
            "STATBOT_ADVANCED_ML_MODEL_STATE_PATH": "state/advanced",
            "STATBOT_ADVANCED_ML_MAX_BOOK_AGE_MS": "900",
            "STATBOT_ADVANCED_ML_FAST_ADVERSE_THRESHOLD": "0.42",
            "STATBOT_ADVANCED_ML_WIDE_SPREAD_BPS": "4.5",
            "STATBOT_ADVANCED_ML_TARGET_EXIT_Z": "0.4",
            "STATBOT_ADVANCED_ML_EXIT_FEE_RATE": "0.0007",
            "STATBOT_ADVANCED_ML_MAX_DRAWDOWN_USDT": "15",
            "STATBOT_ADVANCED_ML_MIN_REGIME_PERSISTENCE_TICKS": "5",
            "STATBOT_ADVANCED_ML_FINAL_SCORE_SOFT_CAP": "1.25",
            "STATBOT_ADVANCED_ML_HMM_REGIME_ENABLED": "1",
            "STATBOT_ADVANCED_ML_GLOBAL_MARKET_CONTEXT_ENABLED": "1",
            "STATBOT_ADVANCED_ML_GLOBAL_MARKET_RISK_WEIGHT": "0.2",
        }
    )

    assert config.features.feature_schema_version == 4
    assert config.features.reject_nan_features is False
    assert config.persistence.model_state_path == "state/advanced"
    assert config.microstructure.max_book_age_ms == 900.0
    assert config.microstructure.fast_adverse_threshold == 0.42
    assert config.microstructure.wide_spread_bps == 4.5
    assert config.ev.target_exit_z == 0.4
    assert config.ev.exit_fee_rate == 0.0007
    assert config.exit.max_drawdown_usdt == 15.0
    assert config.regime.min_regime_persistence_ticks == 5
    assert config.ranking.final_score_soft_cap == 1.25
    assert config.extensions.hmm_regime_enabled is True
    assert config.extensions.global_market_context_enabled is True
    assert config.extensions.global_market_risk_weight == 0.2


def test_load_advanced_ml_config_from_env_ignores_invalid_optional_values():
    defaults = AdvancedMLConfig()
    config = load_advanced_ml_config_from_env(
        {
            "STATBOT_ADVANCED_ML_SHADOW_EVAL_WINDOW": "not-an-int",
            "STATBOT_ADVANCED_ML_EXIT_FEE_RATE": "not-a-float",
            "STATBOT_ADVANCED_ML_REJECT_NAN_FEATURES": "maybe",
        }
    )

    assert config.pipeline.shadow_eval_window == defaults.pipeline.shadow_eval_window
    assert config.ev.exit_fee_rate == defaults.ev.exit_fee_rate
    assert config.features.reject_nan_features == defaults.features.reject_nan_features
