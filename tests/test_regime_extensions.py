from __future__ import annotations

from core.config.advanced_ml_config import AdvancedMLConfig
from core.regime.global_market_context import estimate_global_market_context
from core.regime.hmm_regime_detector import OptionalHMMRegimeRefiner
from core.regime.regime_types import RegimeDetectionResult, RegimeName


def test_global_market_context_is_configurable_and_serializable():
    config = AdvancedMLConfig()
    config.extensions.global_market_high_risk_threshold = 0.70

    context = estimate_global_market_context(
        {
            "global_market_volatility_score": 0.8,
            "global_market_liquidity_stress_score": 0.7,
            "global_market_breadth_stress_score": 0.6,
        },
        config=config,
    )

    assert context.state == "risk_off"
    assert context.to_dict()["risk_score"] > 0.70


def test_optional_hmm_refiner_is_inert_until_enabled():
    config = AdvancedMLConfig()
    result = RegimeDetectionResult(
        pair="AAA/BBB",
        regime=RegimeName.UNKNOWN,
        confidence=0.40,
        break_risk=0.10,
        volatility_state="normal",
        liquidity_state="normal",
        mean_reversion_velocity=0.50,
        mean_reversion_acceleration=0.10,
        trend_score=0.10,
        transition_probability={},
        features={},
        reasons=[],
        timestamp=1.0,
    )

    assert OptionalHMMRegimeRefiner(config).refine(result) is result

    config.extensions.hmm_regime_enabled = True
    context = estimate_global_market_context({"global_market_risk_score": 0.05}, config=config)
    refined = OptionalHMMRegimeRefiner(config).refine(result, global_context=context)

    assert refined.regime == RegimeName.MEAN_REVERTING
    assert refined.features["hmm_refined"] == 1.0
