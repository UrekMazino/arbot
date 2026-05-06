from __future__ import annotations

import logging

import numpy as np
import pytest

from core.config.advanced_ml_config import AdvancedMLConfig
from core.ev.hold_exit_ev import ExitAction, HoldExitEVCalculator, decide_hold_exit_ev


def _config() -> AdvancedMLConfig:
    config = AdvancedMLConfig()
    config.ev.strong_positive_ev_usdt = 1.0
    config.ev.weak_positive_ev_usdt = 0.25
    config.ev.near_zero_ev_usdt = 0.0
    config.ev.time_penalty_rate_per_hour = 0.10
    config.ev.spread_edge_per_sigma_usdt = 0.50
    config.ev.use_historical_spread_edge = False
    config.ev.warn_when_using_default_spread_edge = False
    config.ev.min_spread_edge_per_sigma_usdt = 0.05
    config.ev.max_spread_edge_per_sigma_usdt = 5.00
    config.ev.expected_adverse_sigma_move = 0.50
    config.ev.target_exit_z = 0.50
    config.ev.exit_fee_rate = 0.001
    config.ev.recent_z_vol_window = 4
    config.exit.exit_tighten_threshold = 0.55
    return config


def _kwargs(**overrides):
    data = {
        "position_notional_usdt": 10.0,
        "exit_notional_usdt": 10.0,
        "abs_current_z": 2.0,
        "time_in_trade_seconds": 0.0,
        "half_life_seconds": 100.0,
        "z_history_values": [1.0, 1.1, 1.2, 1.3],
        "bayesian_posterior": 0.50,
        "regime_mean_reversion_confidence": 0.50,
        "z_velocity_toward_mean_score": 0.50,
        "break_risk": 0.10,
        "adverse_z_velocity_score": 0.10,
        "liquidity_score": 0.80,
        "liquidity_risk_score": 0.20,
        "trend_continuation_risk": 0.10,
        "spread_volatility_spike_score": 0.10,
        "slippage_estimate_bps": 0.0,
        "pre_microstructure_exit_score": 0.20,
    }
    data.update(overrides)
    return data


def test_three_outcome_ev_keeps_neutral_probability_when_sum_below_one():
    decision = decide_hold_exit_ev(config=_config(), **_kwargs())

    expected_reversion = (
        0.30 * 0.50
        + 0.25 * 0.50
        + 0.15 * 0.50
        + 0.10 * 1.0
        + 0.10 * 0.90
        + 0.10 * 0.80
    )
    expected_adverse = (
        0.35 * 0.10
        + 0.20 * 0.10
        + 0.15 * 0.20
        + 0.15 * 0.10
        + 0.15 * 0.10
    )

    assert decision.probability_of_reversion == pytest.approx(expected_reversion)
    assert decision.probability_of_adverse_move == pytest.approx(expected_adverse)
    assert decision.probability_of_neutral == pytest.approx(
        1.0 - expected_reversion - expected_adverse
    )


def test_probabilities_normalize_only_when_reversion_and_adverse_exceed_one():
    decision = decide_hold_exit_ev(
        config=_config(),
        **_kwargs(
            bayesian_posterior=1.0,
            regime_mean_reversion_confidence=1.0,
            z_velocity_toward_mean_score=1.0,
            break_risk=1.0,
            adverse_z_velocity_score=1.0,
            liquidity_score=1.0,
            liquidity_risk_score=1.0,
            trend_continuation_risk=1.0,
            spread_volatility_spike_score=1.0,
        ),
    )

    assert decision.probability_of_reversion + decision.probability_of_adverse_move == pytest.approx(1.0)
    assert decision.probability_of_neutral == pytest.approx(0.0)


def test_ev_defines_recent_z_volatility_time_pressure_and_config_aliases():
    config = _config()
    decision = decide_hold_exit_ev(
        config=config,
        **_kwargs(
            time_in_trade_seconds=7_200.0,
            z_history_values=[0.0, 0.5, 1.0, 1.5, 2.0],
        ),
    )

    assert decision.metrics["recent_z_volatility"] == pytest.approx(np.std([0.5, 1.0, 1.5, 2.0]))
    assert decision.metrics["time_pressure_hours"] == pytest.approx(2.0)
    assert decision.metrics["target_exit_z"] == pytest.approx(config.ev.target_exit_z)
    assert decision.metrics["exit_fee_rate"] == pytest.approx(config.ev.exit_fee_rate)
    assert decision.metrics["expected_adverse_sigma_move"] == pytest.approx(
        config.ev.expected_adverse_sigma_move
    )


def test_positive_ev_recommends_hold_when_above_strong_threshold():
    decision = decide_hold_exit_ev(
        config=_config(),
        **_kwargs(
            position_notional_usdt=100.0,
            exit_notional_usdt=10.0,
            bayesian_posterior=1.0,
            regime_mean_reversion_confidence=1.0,
            z_velocity_toward_mean_score=1.0,
            break_risk=0.0,
            adverse_z_velocity_score=0.0,
            liquidity_risk_score=0.0,
            trend_continuation_risk=0.0,
            spread_volatility_spike_score=0.0,
        ),
    )

    assert decision.expected_hold_value_usdt > _config().ev.strong_positive_ev_usdt
    assert decision.recommendation == ExitAction.HOLD


def test_positive_but_not_strong_ev_recommends_tighten_using_pre_microstructure_score():
    config = _config()
    decision = decide_hold_exit_ev(
        config=config,
        **_kwargs(
            position_notional_usdt=1.0,
            exit_notional_usdt=1.0,
            bayesian_posterior=1.0,
            regime_mean_reversion_confidence=1.0,
            z_velocity_toward_mean_score=1.0,
            break_risk=0.0,
            adverse_z_velocity_score=0.0,
            liquidity_risk_score=0.0,
            trend_continuation_risk=0.0,
            spread_volatility_spike_score=0.0,
            pre_microstructure_exit_score=0.10,
            total_exit_score=0.95,
        ),
    )

    assert config.ev.weak_positive_ev_usdt < decision.expected_hold_value_usdt < config.ev.strong_positive_ev_usdt
    assert decision.recommendation == ExitAction.TIGHTEN_STOP
    assert decision.metrics["pre_microstructure_exit_score"] == pytest.approx(0.10)


def test_negative_ev_recommends_full_exit():
    decision = decide_hold_exit_ev(
        config=_config(),
        **_kwargs(
            position_notional_usdt=1.0,
            exit_notional_usdt=100.0,
            bayesian_posterior=0.0,
            regime_mean_reversion_confidence=0.0,
            z_velocity_toward_mean_score=0.0,
            break_risk=1.0,
            adverse_z_velocity_score=1.0,
            liquidity_score=0.0,
            liquidity_risk_score=1.0,
            trend_continuation_risk=1.0,
            spread_volatility_spike_score=1.0,
            slippage_estimate_bps=100.0,
        ),
    )

    assert decision.expected_hold_value_usdt < 0.0
    assert decision.recommendation == ExitAction.FULL_EXIT


def test_high_raw_slippage_reduces_ev_as_direct_cost():
    config = _config()
    no_slippage = decide_hold_exit_ev(config=config, **_kwargs(slippage_estimate_bps=0.0))
    high_slippage = decide_hold_exit_ev(config=config, **_kwargs(slippage_estimate_bps=100.0))

    assert high_slippage.expected_hold_value_usdt < no_slippage.expected_hold_value_usdt
    assert high_slippage.expected_slippage_usdt == pytest.approx(0.10)
    assert high_slippage.metrics["slippage_estimate_bps"] == pytest.approx(100.0)


def test_historical_spread_edge_uses_median_abs_sample_and_clamps(caplog):
    config = _config()
    config.ev.use_historical_spread_edge = True
    config.ev.warn_when_using_default_spread_edge = True
    config.ev.min_spread_edge_per_sigma_usdt = 0.10
    config.ev.max_spread_edge_per_sigma_usdt = 1.00
    calculator = HoldExitEVCalculator(config)

    historical = calculator.decide(
        **_kwargs(historical_sigma_pnl_samples=[-0.20, 10.0, 0.40])
    )
    with caplog.at_level(logging.WARNING):
        defaulted = calculator.decide(**_kwargs(historical_sigma_pnl_samples=[]))

    assert historical.metrics["spread_edge_per_sigma_usdt"] == pytest.approx(0.40)
    assert defaulted.metrics["spread_edge_per_sigma_usdt"] == pytest.approx(0.50)
    assert "Using default spread_edge_per_sigma_usdt" in caplog.text
