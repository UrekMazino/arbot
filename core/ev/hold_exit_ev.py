"""Expected value hold/exit decision model."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from statistics import median
from typing import Iterable

import numpy as np

from core.config.advanced_ml_config import AdvancedMLConfig


logger = logging.getLogger(__name__)


class ExitAction(str, Enum):
    HOLD = "hold"
    TIGHTEN_STOP = "tighten_stop"
    PARTIAL_EXIT = "partial_exit"
    FULL_EXIT = "full_exit"
    FREEZE_NEW_ENTRIES = "freeze_new_entries"


@dataclass(frozen=True)
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
    metrics: dict[str, float]


class HoldExitEVCalculator:
    def __init__(self, config: AdvancedMLConfig | None = None) -> None:
        self.config = config or AdvancedMLConfig()

    def decide(
        self,
        *,
        position_notional_usdt: float,
        exit_notional_usdt: float,
        abs_current_z: float,
        time_in_trade_seconds: float,
        half_life_seconds: float,
        z_history_values: Iterable[float],
        bayesian_posterior: float,
        regime_mean_reversion_confidence: float,
        z_velocity_toward_mean_score: float,
        break_risk: float,
        adverse_z_velocity_score: float,
        liquidity_score: float,
        liquidity_risk_score: float,
        trend_continuation_risk: float,
        slippage_estimate_bps: float,
        pre_microstructure_exit_score: float,
        spread_volatility_spike_score: float | None = None,
        normalized_spread_vol_spike: float | None = None,
        low_break_risk_score: float | None = None,
        historical_sigma_pnl_samples: Iterable[float] | None = None,
        total_exit_score: float | None = None,
    ) -> ExpectedValueDecision:
        del total_exit_score
        cfg = self.config
        position_notional_usdt = max(float(position_notional_usdt), 0.0)
        exit_notional_usdt = max(float(exit_notional_usdt), 0.0)
        abs_current_z = max(float(abs_current_z), 0.0)
        time_in_trade_seconds = max(float(time_in_trade_seconds), 0.0)
        half_life_seconds = max(float(half_life_seconds), 1.0)
        pre_microstructure_exit_score = clamp01(pre_microstructure_exit_score)

        z_history_tail = list(float(value) for value in z_history_values)[-cfg.ev.recent_z_vol_window:]
        recent_z_volatility = (
            float(np.std(z_history_tail))
            if len(z_history_tail) >= 2
            else 0.0
        )
        time_pressure_hours = time_in_trade_seconds / 3600.0
        target_exit_z = cfg.ev.target_exit_z
        expected_exit_fee_rate = cfg.ev.exit_fee_rate
        expected_adverse_sigma_move = cfg.ev.expected_adverse_sigma_move
        half_life_score = clamp01(
            1.0 - (
                time_in_trade_seconds
                / max(2.0 * half_life_seconds, 1.0)
            )
        )
        spread_volatility_spike_score = clamp01(
            spread_volatility_spike_score
            if spread_volatility_spike_score is not None
            else normalized_spread_vol_spike if normalized_spread_vol_spike is not None
            else 0.0
        )
        low_break_risk_score = clamp01(
            low_break_risk_score
            if low_break_risk_score is not None
            else 1.0 - float(break_risk)
        )

        p_reversion = clamp01(
            0.30 * clamp01(bayesian_posterior)
            + 0.25 * clamp01(regime_mean_reversion_confidence)
            + 0.15 * clamp01(z_velocity_toward_mean_score)
            + 0.10 * half_life_score
            + 0.10 * low_break_risk_score
            + 0.10 * clamp01(liquidity_score)
        )
        p_adverse = clamp01(
            0.35 * clamp01(break_risk)
            + 0.20 * clamp01(adverse_z_velocity_score)
            + 0.15 * clamp01(liquidity_risk_score)
            + 0.15 * clamp01(trend_continuation_risk)
            + 0.15 * spread_volatility_spike_score
        )
        if p_reversion + p_adverse > 1.0:
            total = p_reversion + p_adverse
            p_reversion = p_reversion / total
            p_adverse = p_adverse / total
            p_neutral = 0.0
        else:
            p_neutral = 1.0 - p_reversion - p_adverse

        spread_edge_per_sigma_usdt = _spread_edge_per_sigma_usdt(
            historical_sigma_pnl_samples,
            cfg,
        )
        remaining_z_move = max(abs_current_z - target_exit_z, 0.0)
        expected_gain_usdt = (
            position_notional_usdt
            * spread_edge_per_sigma_usdt
            * remaining_z_move
        )
        adverse_z_move = max(
            expected_adverse_sigma_move,
            recent_z_volatility,
        )
        expected_loss_usdt = (
            position_notional_usdt
            * spread_edge_per_sigma_usdt
            * adverse_z_move
        )
        expected_fees_usdt = expected_exit_fee_rate * exit_notional_usdt
        expected_slippage_usdt = (
            max(float(slippage_estimate_bps), 0.0) / 10000.0
        ) * exit_notional_usdt
        time_risk_penalty_usdt = (
            position_notional_usdt
            * cfg.ev.time_penalty_rate_per_hour
            * time_pressure_hours
        )
        expected_hold_value_usdt = (
            p_reversion * expected_gain_usdt
            - p_adverse * expected_loss_usdt
            + p_neutral * 0.0
            - expected_fees_usdt
            - expected_slippage_usdt
            - time_risk_penalty_usdt
        )
        expected_hold_value_bps = (
            expected_hold_value_usdt / max(exit_notional_usdt, 1e-9)
        ) * 10000.0
        recommendation = _recommendation(
            expected_hold_value_usdt,
            pre_microstructure_exit_score,
            cfg,
        )

        return ExpectedValueDecision(
            expected_hold_value_usdt=expected_hold_value_usdt,
            expected_hold_value_bps=expected_hold_value_bps,
            probability_of_reversion=p_reversion,
            probability_of_adverse_move=p_adverse,
            probability_of_neutral=p_neutral,
            expected_gain_usdt=expected_gain_usdt,
            expected_loss_usdt=expected_loss_usdt,
            expected_fees_usdt=expected_fees_usdt,
            expected_slippage_usdt=expected_slippage_usdt,
            time_risk_penalty_usdt=time_risk_penalty_usdt,
            recommendation=recommendation,
            reasons=_reasons(expected_hold_value_usdt, pre_microstructure_exit_score, cfg),
            metrics={
                "recent_z_volatility": recent_z_volatility,
                "time_pressure_hours": time_pressure_hours,
                "target_exit_z": target_exit_z,
                "exit_fee_rate": expected_exit_fee_rate,
                "expected_exit_fee_rate": expected_exit_fee_rate,
                "expected_adverse_sigma_move": expected_adverse_sigma_move,
                "half_life_score": half_life_score,
                "low_break_risk_score": low_break_risk_score,
                "spread_volatility_spike_score": spread_volatility_spike_score,
                "spread_edge_per_sigma_usdt": spread_edge_per_sigma_usdt,
                "remaining_z_move": remaining_z_move,
                "adverse_z_move": adverse_z_move,
                "slippage_estimate_bps": max(float(slippage_estimate_bps), 0.0),
                "pre_microstructure_exit_score": pre_microstructure_exit_score,
            },
        )


def decide_hold_exit_ev(
    *,
    config: AdvancedMLConfig | None = None,
    **kwargs,
) -> ExpectedValueDecision:
    return HoldExitEVCalculator(config).decide(**kwargs)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def clamp(value: float, low: float, high: float) -> float:
    return max(float(low), min(float(high), float(value)))


def _spread_edge_per_sigma_usdt(
    historical_sigma_pnl_samples: Iterable[float] | None,
    config: AdvancedMLConfig,
) -> float:
    samples = [
        abs(float(value))
        for value in (historical_sigma_pnl_samples or [])
        if np.isfinite(float(value))
    ]
    if config.ev.use_historical_spread_edge and samples:
        spread_edge_per_sigma_usdt = float(median(samples))
    else:
        spread_edge_per_sigma_usdt = config.ev.spread_edge_per_sigma_usdt
        if config.ev.warn_when_using_default_spread_edge:
            logger.warning(
                "Using default spread_edge_per_sigma_usdt; calibrate with historical trades."
            )
    return clamp(
        spread_edge_per_sigma_usdt,
        config.ev.min_spread_edge_per_sigma_usdt,
        config.ev.max_spread_edge_per_sigma_usdt,
    )


def _recommendation(
    expected_hold_value_usdt: float,
    pre_microstructure_exit_score: float,
    config: AdvancedMLConfig,
) -> ExitAction:
    if expected_hold_value_usdt > config.ev.strong_positive_ev_usdt:
        return ExitAction.HOLD
    if (
        expected_hold_value_usdt > config.ev.weak_positive_ev_usdt
        and pre_microstructure_exit_score < config.exit.exit_tighten_threshold
    ):
        return ExitAction.TIGHTEN_STOP
    if expected_hold_value_usdt >= config.ev.near_zero_ev_usdt:
        return ExitAction.PARTIAL_EXIT
    return ExitAction.FULL_EXIT


def _reasons(
    expected_hold_value_usdt: float,
    pre_microstructure_exit_score: float,
    config: AdvancedMLConfig,
) -> list[str]:
    if expected_hold_value_usdt > config.ev.strong_positive_ev_usdt:
        action_reason = "strong positive EV"
    elif (
        expected_hold_value_usdt > config.ev.weak_positive_ev_usdt
        and pre_microstructure_exit_score < config.exit.exit_tighten_threshold
    ):
        action_reason = "positive EV with low pre-microstructure exit pressure"
    elif expected_hold_value_usdt >= config.ev.near_zero_ev_usdt:
        action_reason = "near-zero positive EV"
    else:
        action_reason = "negative EV"
    return [
        action_reason,
        "used pre_microstructure_exit_score for EV threshold context",
    ]


__all__ = [
    "ExitAction",
    "ExpectedValueDecision",
    "HoldExitEVCalculator",
    "clamp",
    "clamp01",
    "decide_hold_exit_ev",
]
