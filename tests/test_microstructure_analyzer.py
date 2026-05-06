from __future__ import annotations

import pytest

from core.config.advanced_ml_config import AdvancedMLConfig
from core.microstructure.microstructure_analyzer import (
    MicrostructureAnalyzer,
    analyze_microstructure_exit,
)
from core.regime.regime_types import RegimeName


def _config() -> AdvancedMLConfig:
    config = AdvancedMLConfig()
    config.microstructure.max_book_age_ms = 1_000.0
    config.microstructure.max_allowed_slippage_bps = 10.0
    config.microstructure.severe_book_stress_threshold = 0.85
    config.microstructure.max_urgency_boost = 0.75
    config.microstructure.max_exit_urgency_multiplier = 1.40
    config.microstructure.exit_score_slippage_cap = 0.50
    config.microstructure.fast_adverse_threshold = 0.60
    config.microstructure.wide_spread_bps = 5.0
    config.regime.max_spread_widening_bps = 10.0
    config.regime.min_top_depth_usdt = 1_000.0
    return config


def test_stale_book_produces_liquidity_fresh_false_and_wait_style():
    result = analyze_microstructure_exit(
        update_age_ms=2_500.0,
        bid_depth=500.0,
        ask_depth=500.0,
        estimated_slippage_bps=1.0,
        spread_bps=1.0,
        adverse_z_velocity_score=0.0,
        regime=RegimeName.MEAN_REVERTING,
        config=_config(),
    )

    assert result.liquidity_fresh is False
    assert result.metrics["stale_book_score"] == pytest.approx(1.0)
    assert result.recommended_order_style == "wait"
    assert "liquidity stale" in result.reasons


def test_stale_book_hard_kill_prefers_taker_instead_of_wait():
    result = analyze_microstructure_exit(
        update_age_ms=2_500.0,
        bid_depth=500.0,
        ask_depth=500.0,
        estimated_slippage_bps=1.0,
        spread_bps=1.0,
        adverse_z_velocity_score=0.0,
        regime=RegimeName.MEAN_REVERTING,
        hard_kill_triggered=True,
        config=_config(),
    )

    assert result.liquidity_fresh is False
    assert result.recommended_order_style == "taker"


def test_severe_book_stress_increases_urgency_multiplier():
    result = analyze_microstructure_exit(
        update_age_ms=2_000.0,
        bid_depth=0.0,
        ask_depth=50.0,
        estimated_slippage_bps=50.0,
        spread_bps=40.0,
        adverse_z_velocity_score=0.20,
        regime=RegimeName.MEAN_REVERTING,
        config=_config(),
    )

    assert result.book_stress_score >= _config().microstructure.severe_book_stress_threshold
    assert result.exit_urgency_multiplier > 1.0
    assert "severe book stress" in result.reasons


def test_urgency_multiplier_never_exceeds_configured_maximum():
    config = _config()
    config.microstructure.max_urgency_boost = 10.0
    config.microstructure.max_exit_urgency_multiplier = 1.25

    result = analyze_microstructure_exit(
        update_age_ms=4_000.0,
        bid_depth=0.0,
        ask_depth=1_000.0,
        estimated_slippage_bps=100.0,
        spread_bps=100.0,
        adverse_z_velocity_score=1.0,
        regime=RegimeName.STRUCTURAL_BREAK,
        config=config,
    )

    assert result.exit_urgency_multiplier == pytest.approx(1.25)


def test_slippage_contribution_to_exit_score_is_capped_but_raw_kept_for_ev():
    config = _config()
    analyzer = MicrostructureAnalyzer(config)

    result = analyzer.analyze_exit(
        update_age_ms=1_000.0,
        bid_depth=500.0,
        ask_depth=500.0,
        estimated_slippage_bps=100.0,
        spread_bps=0.0,
        adverse_z_velocity_score=0.0,
        regime=RegimeName.MEAN_REVERTING,
    )

    assert result.metrics["raw_slippage_risk_score"] == pytest.approx(1.0)
    assert result.slippage_risk_score == pytest.approx(0.50)
    assert result.metrics["slippage_risk_score_for_exit_score"] == pytest.approx(0.50)
    assert result.metrics["estimated_slippage_bps"] == pytest.approx(100.0)
    assert result.metrics["ev_estimated_slippage_bps"] == pytest.approx(100.0)
    assert result.book_stress_score == pytest.approx(0.20 * 0.50)
    assert "slippage contribution capped for exit score" in result.reasons


def test_wide_spread_stable_regime_prefers_maker():
    config = _config()

    result = analyze_microstructure_exit(
        update_age_ms=500.0,
        bid_depth=500.0,
        ask_depth=500.0,
        estimated_slippage_bps=0.0,
        spread_bps=config.microstructure.wide_spread_bps,
        adverse_z_velocity_score=0.0,
        regime=RegimeName.MEAN_REVERTING,
        config=config,
    )

    assert result.book_stress_score < 0.60
    assert result.recommended_order_style == "maker"


def test_wide_spread_trending_regime_uses_split_not_maker():
    config = _config()

    result = analyze_microstructure_exit(
        update_age_ms=500.0,
        bid_depth=500.0,
        ask_depth=500.0,
        estimated_slippage_bps=0.0,
        spread_bps=config.microstructure.wide_spread_bps,
        adverse_z_velocity_score=0.0,
        regime=RegimeName.TRENDING,
        config=config,
    )

    assert result.recommended_order_style == "split"


def test_fast_adverse_thin_book_prefers_taker_using_config_threshold():
    config = _config()
    config.microstructure.severe_book_stress_threshold = 0.30
    config.microstructure.fast_adverse_threshold = 0.70

    result = analyze_microstructure_exit(
        update_age_ms=1_000.0,
        bid_depth=1.0,
        ask_depth=999.0,
        estimated_slippage_bps=100.0,
        spread_bps=10.0,
        adverse_z_velocity_score=config.microstructure.fast_adverse_threshold,
        regime=RegimeName.MEAN_REVERTING,
        config=config,
    )

    assert result.book_stress_score >= config.microstructure.severe_book_stress_threshold
    assert result.recommended_order_style == "taker"
