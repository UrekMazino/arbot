from __future__ import annotations

import numpy as np
import pytest

from core.config.advanced_ml_config import AdvancedMLConfig
from core.regime.heuristic_regime_detector import (
    HeuristicRegimeDetector,
    OrderBookRegimeFeatures,
    clamp01,
    detect_regime,
)
from core.regime.regime_types import RegimeName
from core.regime.transition_matrix import RegimeTransitionMatrix


def _config() -> AdvancedMLConfig:
    config = AdvancedMLConfig()
    config.regime.regime_window = 5
    config.regime.corr_drift_break_threshold = 0.20
    config.regime.beta_drift_break_threshold = 0.20
    config.regime.high_volatility_ratio = 2.0
    config.regime.low_volatility_ratio = 0.50
    config.regime.vol_spike_scale = 1.0
    config.regime.z_velocity_risk_scale = 1.0
    config.regime.z_acceleration_risk_scale = 1.0
    config.regime.max_spread_widening_bps = 10.0
    config.regime.min_top_depth_usdt = 1_000.0
    config.microstructure.max_book_age_ms = 1_000.0
    config.microstructure.max_allowed_slippage_bps = 10.0
    return config


def _orderbook(**overrides: float) -> OrderBookRegimeFeatures:
    data = {
        "spread_bps": 2.0,
        "depth_imbalance": 0.40,
        "top_depth_usdt": 750.0,
        "slippage_estimate_bps": 3.0,
        "book_freshness_ms": 1_500.0,
    }
    data.update(overrides)
    return OrderBookRegimeFeatures(**data)


def _expected_volatility(spread_history: list[float], window: int) -> tuple[float, float, float]:
    spread_returns = np.diff(np.asarray(spread_history, dtype=float))
    realized_vol = float(np.std(spread_returns[-window:]))
    rolling_stds = [
        float(np.std(spread_returns[max(0, i - window):i]))
        for i in range(window, len(spread_returns) + 1)
        if len(spread_returns[max(0, i - window):i]) >= max(5, window // 4)
    ]
    baseline_vol = float(np.median(rolling_stds)) if rolling_stds else max(realized_vol, 1e-9)
    normalized_spike = clamp01(((realized_vol - baseline_vol) / max(baseline_vol, 1e-9)))
    return realized_vol, baseline_vol, normalized_spike


def test_detector_computes_explicit_formula_features_and_aliases():
    config = _config()
    spread_history = [0.0, 1.0, 1.5, 2.5, 1.0, 1.2, 2.2, 1.7, 1.9, 2.6, 2.4]
    result = detect_regime(
        pair="BTC-ETH",
        z_history=[(0.0, 1.0), (10.0, 1.5), (20.0, 1.7)],
        spread_history=spread_history,
        corr_history=[0.80, 0.82, 0.81, 0.79, 0.70],
        hedge_ratio_history=[1.00, 1.02, 0.98, 1.01, 1.10],
        orderbook=_orderbook(),
        config=config,
        timestamp=123.0,
    )

    realized_vol, baseline_vol, normalized_spike = _expected_volatility(spread_history, 5)
    expected_corr_drift = abs(0.70 - np.mean([0.80, 0.82, 0.81, 0.79, 0.70]))
    expected_beta_drift = abs(1.10 - np.mean([1.00, 1.02, 0.98, 1.01, 1.10]))
    expected_liquidity_stress = clamp01(
        0.30 * 0.50 + 0.25 * 0.20 + 0.20 * 0.30 + 0.15 * 0.40 + 0.10 * 0.25
    )
    expected_trend = clamp01(
        0.40 * 0.02
        + 0.30 * 0.003
        + 0.20 * (expected_corr_drift / config.regime.corr_drift_break_threshold)
        + 0.10 * 0.0
    )

    assert result.timestamp == 123.0
    assert result.features["realized_vol"] == pytest.approx(realized_vol)
    assert result.features["baseline_vol"] == pytest.approx(baseline_vol)
    assert result.features["normalized_spread_vol_spike"] == pytest.approx(normalized_spike)
    assert result.features["z_velocity"] == pytest.approx(0.02)
    assert result.features["z_acceleration"] == pytest.approx(-0.003)
    assert result.features["adverse_acceleration_score"] == pytest.approx(0.003)
    assert result.features["normalized_corr_drift"] == pytest.approx(
        expected_corr_drift / config.regime.corr_drift_break_threshold
    )
    assert result.features["normalized_beta_drift"] == pytest.approx(
        expected_beta_drift / config.regime.beta_drift_break_threshold
    )
    assert result.features["liquidity_stress"] == pytest.approx(expected_liquidity_stress)
    assert result.features["trend_score"] == pytest.approx(expected_trend)
    assert result.features["spread_volatility_spike_score"] == pytest.approx(
        result.features["normalized_spread_vol_spike"]
    )
    assert result.features["slippage_risk"] == pytest.approx(result.features["slippage_score"])
    assert result.features["hedge_ratio_drift_risk"] == pytest.approx(
        result.features["normalized_beta_drift"]
    )
    assert result.features["low_break_risk_score"] == pytest.approx(
        1.0 - result.features["break_risk"]
    )
    assert result.features["trend_continuation_risk"] == pytest.approx(
        clamp01(
            0.50 * result.features["trend_score"]
            + 0.30 * result.features["adverse_z_velocity_score"]
            + 0.20 * result.features["normalized_spread_vol_spike"]
        )
    )
    assert result.features["half_life_score"] == pytest.approx(0.50)


def test_mr_confidence_uses_all_required_subscores():
    config = _config()
    config.regime.z_velocity_risk_scale = 0.05
    config.regime.mean_reverting_threshold = 0.95
    detector = HeuristicRegimeDetector(config)

    result = detector.detect(
        pair="MR",
        z_history=[(0.0, 2.0), (10.0, 1.5), (20.0, 1.0)],
        spread_history=[0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0],
        corr_history=[0.90, 0.90, 0.90, 0.90, 0.90],
        hedge_ratio_history=[1.0, 1.0, 1.0, 1.0, 1.0],
        spread_bps=0.0,
        depth_imbalance=0.0,
        top_depth_usdt=1_000.0,
        slippage_estimate_bps=0.0,
        book_freshness_ms=1_000.0,
    )

    expected_mr_confidence = clamp01(
        0.30 * result.features["z_moving_toward_mean_score"]
        + 0.20 * result.features["stable_correlation_score"]
        + 0.15 * result.features["stable_beta_score"]
        + 0.15 * result.features["healthy_cross_rhythm_score"]
        + 0.10 * result.features["moderate_volatility_score"]
        + 0.10 * result.features["healthy_liquidity_score"]
    )
    assert result.regime == RegimeName.MEAN_REVERTING
    assert result.confidence == pytest.approx(expected_mr_confidence)
    assert result.features["z_moving_toward_mean_score"] == pytest.approx(1.0)
    assert result.features["stable_correlation_score"] == pytest.approx(1.0)
    assert result.features["stable_beta_score"] == pytest.approx(1.0)
    assert result.features["healthy_cross_rhythm_score"] == pytest.approx(1.0)
    assert result.features["moderate_volatility_score"] == pytest.approx(1.0)
    assert result.features["healthy_liquidity_score"] == pytest.approx(1.0)


def test_classification_prioritizes_structural_break_over_other_thresholds():
    config = _config()
    config.regime.regime_break_threshold = 0.05
    config.regime.liquidity_stress_threshold = 0.05

    result = detect_regime(
        pair="BREAK",
        z_history=[(0.0, 0.0), (10.0, 2.0), (20.0, 4.0)],
        spread_history=[0.0, 5.0, -5.0, 5.0, -5.0, 5.0, -5.0],
        corr_history=[0.90, 0.70, 0.40, 0.20, 0.00],
        hedge_ratio_history=[1.0, 1.2, 1.4, 1.6, 2.0],
        orderbook=_orderbook(spread_bps=10.0, slippage_estimate_bps=10.0),
        config=config,
    )

    assert result.regime == RegimeName.STRUCTURAL_BREAK


def test_hysteresis_holds_previous_regime_when_switch_is_not_persistent():
    config = _config()
    config.regime.trending_threshold = 0.05
    config.regime.regime_break_threshold = 1.0
    config.regime.correlation_breakdown_threshold = 0.95
    config.regime.min_regime_persistence_ticks = 3
    config.regime.regime_switch_cooldown_seconds = 60
    config.regime.regime_switch_confidence_margin = 0.10

    result = detect_regime(
        pair="HOLD",
        z_history=[(0.0, 0.0), (10.0, 1.0), (20.0, 2.0)],
        spread_history=[0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0],
        corr_history=[0.90, 0.90, 0.90, 0.90, 0.70],
        hedge_ratio_history=[1.0, 1.0, 1.0, 1.0, 1.0],
        orderbook=_orderbook(spread_bps=0.0, slippage_estimate_bps=0.0),
        config=config,
        previous_regime=RegimeName.MEAN_REVERTING,
        previous_regime_confidence=0.80,
        ticks_in_proposed_regime=0,
        seconds_since_last_regime_switch=0.0,
    )

    assert result.regime == RegimeName.MEAN_REVERTING
    assert result.confidence == pytest.approx(0.80 * 0.80 + 0.20 * result.features["trend_score"])
    assert "regime switch held by hysteresis" in result.reasons


def test_structural_break_bypasses_hysteresis():
    config = _config()
    config.regime.regime_break_threshold = 0.05

    result = detect_regime(
        pair="FAST_BREAK",
        z_history=[(0.0, 0.0), (10.0, 2.0), (20.0, 4.0)],
        spread_history=[0.0, 5.0, -5.0, 5.0, -5.0, 5.0, -5.0],
        corr_history=[0.90, 0.70, 0.40, 0.20, 0.00],
        hedge_ratio_history=[1.0, 1.2, 1.4, 1.6, 2.0],
        orderbook=_orderbook(),
        config=config,
        previous_regime=RegimeName.MEAN_REVERTING,
        previous_regime_confidence=0.99,
        ticks_in_proposed_regime=0,
        seconds_since_last_regime_switch=0.0,
    )

    assert result.regime == RegimeName.STRUCTURAL_BREAK
    assert "regime switch held by hysteresis" not in result.reasons


def test_half_life_score_uses_formula_when_trade_timing_is_available():
    config = _config()

    result = detect_regime(
        pair="TIMED",
        z_history=[(0.0, 2.0), (10.0, 1.5), (20.0, 1.0)],
        spread_history=[0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0],
        corr_history=[0.90, 0.90, 0.90, 0.90, 0.90],
        hedge_ratio_history=[1.0, 1.0, 1.0, 1.0, 1.0],
        orderbook=_orderbook(spread_bps=0.0, depth_imbalance=0.0, slippage_estimate_bps=0.0),
        config=config,
        time_in_trade_seconds=100.0,
        half_life_seconds=200.0,
    )

    assert result.features["half_life_score"] == pytest.approx(0.75)


def test_direct_detector_accepts_raw_orderbook_kwargs_and_records_previous_transition():
    config = _config()
    config.regime.z_velocity_risk_scale = 0.05
    config.regime.mean_reverting_threshold = 0.95
    matrix = RegimeTransitionMatrix(decay=1.0)

    result = detect_regime(
        pair="RAW_BOOK",
        z_history=[(0.0, 2.0), (10.0, 1.5), (20.0, 1.0)],
        spread_history=[0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0],
        corr_history=[0.90, 0.90, 0.90, 0.90, 0.90],
        hedge_ratio_history=[1.0, 1.0, 1.0, 1.0, 1.0],
        spread_bps=0.0,
        depth_imbalance=0.0,
        top_depth_usdt=1_000.0,
        slippage_estimate_bps=0.0,
        book_freshness_ms=1_000.0,
        config=config,
        transition_matrix=matrix,
        previous_regime=RegimeName.UNKNOWN,
        previous_regime_confidence=0.0,
        ticks_in_proposed_regime=3,
        seconds_since_last_regime_switch=60.0,
    )

    assert result.regime == RegimeName.MEAN_REVERTING
    assert result.transition_probability == {"mean_reverting": pytest.approx(1.0)}
