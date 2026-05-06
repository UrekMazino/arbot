"""Heuristic regime detection using the architecture's explicit formulas."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

from core.config.advanced_ml_config import AdvancedMLConfig
from core.regime.regime_types import RegimeDetectionResult, RegimeName
from core.regime.transition_matrix import RegimeTransitionMatrix


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


@dataclass(frozen=True)
class OrderBookRegimeFeatures:
    spread_bps: float
    depth_imbalance: float
    top_depth_usdt: float
    slippage_estimate_bps: float
    book_freshness_ms: float


@dataclass(frozen=True)
class HysteresisInputs:
    previous_regime: RegimeName | str | None = None
    previous_regime_confidence: float = 0.0
    ticks_in_proposed_regime: int = 0
    seconds_since_last_regime_switch: float = float("inf")


class HeuristicRegimeDetector:
    def __init__(
        self,
        config: AdvancedMLConfig | None = None,
        transition_matrix: RegimeTransitionMatrix | None = None,
    ) -> None:
        self.config = config or AdvancedMLConfig()
        self.transition_matrix = transition_matrix

    def detect(
        self,
        *,
        pair: Any,
        z_history: Iterable[tuple[float, float] | list[float] | float],
        spread_history: Iterable[float],
        corr_history: Iterable[float],
        hedge_ratio_history: Iterable[float],
        spread_bps: float,
        depth_imbalance: float,
        top_depth_usdt: float,
        slippage_estimate_bps: float,
        book_freshness_ms: float,
        previous_regime: RegimeName | str | None = None,
        previous_regime_confidence: float = 0.0,
        ticks_in_proposed_regime: int = 0,
        seconds_since_last_regime_switch: float = float("inf"),
        timestamp: float | None = None,
        time_in_trade_seconds: float | None = None,
        half_life_seconds: float | None = None,
    ) -> RegimeDetectionResult:
        orderbook = OrderBookRegimeFeatures(
            spread_bps=float(spread_bps),
            depth_imbalance=float(depth_imbalance),
            top_depth_usdt=float(top_depth_usdt),
            slippage_estimate_bps=float(slippage_estimate_bps),
            book_freshness_ms=float(book_freshness_ms),
        )
        hysteresis = HysteresisInputs(
            previous_regime=previous_regime,
            previous_regime_confidence=float(previous_regime_confidence),
            ticks_in_proposed_regime=int(ticks_in_proposed_regime),
            seconds_since_last_regime_switch=float(seconds_since_last_regime_switch),
        )
        return detect_regime(
            pair=pair,
            z_history=z_history,
            spread_history=spread_history,
            corr_history=corr_history,
            hedge_ratio_history=hedge_ratio_history,
            orderbook=orderbook,
            config=self.config,
            transition_matrix=self.transition_matrix,
            hysteresis=hysteresis,
            timestamp=timestamp,
            time_in_trade_seconds=time_in_trade_seconds,
            half_life_seconds=half_life_seconds,
        )


def detect_regime(
    *,
    pair: Any,
    z_history: Iterable[tuple[float, float] | list[float] | float],
    spread_history: Iterable[float],
    corr_history: Iterable[float],
    hedge_ratio_history: Iterable[float],
    orderbook: OrderBookRegimeFeatures | dict[str, float] | None = None,
    config: AdvancedMLConfig | None = None,
    transition_matrix: RegimeTransitionMatrix | None = None,
    hysteresis: HysteresisInputs | None = None,
    spread_bps: float | None = None,
    depth_imbalance: float | None = None,
    top_depth_usdt: float | None = None,
    slippage_estimate_bps: float | None = None,
    book_freshness_ms: float | None = None,
    previous_regime: RegimeName | str | None = None,
    previous_regime_confidence: float = 0.0,
    ticks_in_proposed_regime: int = 0,
    seconds_since_last_regime_switch: float = float("inf"),
    timestamp: float | None = None,
    time_in_trade_seconds: float | None = None,
    half_life_seconds: float | None = None,
) -> RegimeDetectionResult:
    cfg = config or AdvancedMLConfig()
    h = hysteresis or HysteresisInputs(
        previous_regime=previous_regime,
        previous_regime_confidence=float(previous_regime_confidence),
        ticks_in_proposed_regime=int(ticks_in_proposed_regime),
        seconds_since_last_regime_switch=float(seconds_since_last_regime_switch),
    )
    z_points = _normalize_z_history(z_history)
    if len(z_points) < 2:
        raise ValueError("z_history must include at least two observations.")

    z_values = np.asarray([point[1] for point in z_points], dtype=float)
    spread_array = _finite_array("spread_history", spread_history, min_len=2)
    corr_array = _finite_array("corr_history", corr_history, min_len=1)
    beta_array = _finite_array("hedge_ratio_history", hedge_ratio_history, min_len=1)
    orderbook_features = _coerce_orderbook(
        orderbook,
        spread_bps=spread_bps,
        depth_imbalance=depth_imbalance,
        top_depth_usdt=top_depth_usdt,
        slippage_estimate_bps=slippage_estimate_bps,
        book_freshness_ms=book_freshness_ms,
    )

    features: dict[str, float] = {}
    features.update(_spread_volatility_features(spread_array, cfg))
    features.update(_z_momentum_features(z_points, cfg))
    features.update(_correlation_features(corr_array, cfg))
    features.update(_hedge_ratio_features(beta_array, cfg))
    features.update(_zero_cross_features(z_values, cfg))
    features.update(_volatility_state_features(features, cfg))
    features.update(_liquidity_features(orderbook_features, cfg))
    features.update(_mean_reversion_motion_features(features, z_points, cfg))
    _finalize_scores_and_aliases(
        features,
        cfg,
        time_in_trade_seconds=time_in_trade_seconds,
        half_life_seconds=half_life_seconds,
    )

    proposed_regime = _classify_regime(features, cfg)
    proposed_confidence = _confidence_for_regime(proposed_regime, features, cfg)
    final_regime, final_confidence, hysteresis_reason = _apply_hysteresis(
        proposed_regime=proposed_regime,
        proposed_confidence=proposed_confidence,
        break_risk=features["break_risk"],
        hysteresis=h,
        cfg=cfg,
    )

    reasons = _classification_reasons(proposed_regime, features, cfg)
    if hysteresis_reason is not None:
        reasons.append(hysteresis_reason)

    transition_probability: dict[str, float] = {}
    if transition_matrix is not None:
        previous = _optional_regime(h.previous_regime)
        if previous is not None:
            transition_matrix.update(previous, final_regime)
            transition_probability = transition_matrix.probabilities(previous)
        else:
            transition_probability = transition_matrix.probabilities(final_regime)

    return RegimeDetectionResult(
        pair=pair,
        regime=final_regime,
        confidence=final_confidence,
        break_risk=features["break_risk"],
        volatility_state=_volatility_state_from_features(features, cfg),
        liquidity_state=_liquidity_state_from_features(features, cfg),
        mean_reversion_velocity=features["z_velocity"],
        mean_reversion_acceleration=features["z_acceleration"],
        trend_score=features["trend_score"],
        transition_probability=transition_probability,
        features=features,
        reasons=reasons,
        timestamp=float(timestamp if timestamp is not None else time.time()),
    )


def _spread_volatility_features(spread_history: np.ndarray, config: AdvancedMLConfig) -> dict[str, float]:
    spread_returns = np.diff(spread_history)
    w = int(config.regime.regime_window)
    realized_vol = float(np.std(spread_returns[-w:])) if len(spread_returns) else 0.0
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
    normalized_spread_vol_spike = clamp01(
        ((realized_vol - baseline_vol) / max(baseline_vol, 1e-9))
        / config.regime.vol_spike_scale
    )
    return {
        "realized_vol": realized_vol,
        "baseline_vol": baseline_vol,
        "normalized_spread_vol_spike": normalized_spread_vol_spike,
    }


def _z_momentum_features(
    z_points: list[tuple[float, float]],
    config: AdvancedMLConfig,
) -> dict[str, float]:
    t_now, z_now = z_points[-1]
    t_prev, z_prev = z_points[-2]
    dt_seconds = max(float(t_now - t_prev), 1.0)
    z_velocity_now = (z_now - z_prev) / dt_seconds
    if len(z_points) >= 3:
        t_prev_prev, z_prev_prev = z_points[-3]
        previous_dt_seconds = max(float(t_prev - t_prev_prev), 1.0)
        z_velocity_prev = (z_prev - z_prev_prev) / previous_dt_seconds
    else:
        z_velocity_prev = 0.0
    z_acceleration = (z_velocity_now - z_velocity_prev) / dt_seconds
    abs_z_increasing = abs(z_now) > abs(z_prev)
    adverse_z_velocity_score = (
        clamp01(abs(z_velocity_now) / config.regime.z_velocity_risk_scale)
        if abs_z_increasing
        else 0.0
    )
    adverse_acceleration_score = (
        clamp01(abs(z_acceleration) / config.regime.z_acceleration_risk_scale)
        if abs_z_increasing
        else 0.0
    )
    return {
        "z_now": float(z_now),
        "z_prev": float(z_prev),
        "dt_seconds": dt_seconds,
        "z_velocity": float(z_velocity_now),
        "z_velocity_prev": float(z_velocity_prev),
        "z_acceleration": float(z_acceleration),
        "abs_z_increasing": float(abs_z_increasing),
        "adverse_z_velocity_score": adverse_z_velocity_score,
        "adverse_acceleration_score": adverse_acceleration_score,
    }


def _correlation_features(corr_history: np.ndarray, config: AdvancedMLConfig) -> dict[str, float]:
    lookback = min(int(config.regime.regime_window), len(corr_history))
    corr_now = float(corr_history[-1])
    corr_drift = abs(corr_now - float(np.mean(corr_history[-lookback:])))
    normalized_corr_drift = clamp01(
        corr_drift / config.regime.corr_drift_break_threshold
    )
    return {
        "corr_now": corr_now,
        "corr_drift": corr_drift,
        "normalized_corr_drift": normalized_corr_drift,
        "stable_correlation_score": 1.0 - normalized_corr_drift,
    }


def _hedge_ratio_features(beta_history: np.ndarray, config: AdvancedMLConfig) -> dict[str, float]:
    lookback = min(int(config.regime.regime_window), len(beta_history))
    beta_now = float(beta_history[-1])
    beta_drift = abs(beta_now - float(np.mean(beta_history[-lookback:])))
    normalized_beta_drift = clamp01(
        beta_drift / config.regime.beta_drift_break_threshold
    )
    return {
        "beta_now": beta_now,
        "beta_drift": beta_drift,
        "normalized_beta_drift": normalized_beta_drift,
        "stable_beta_score": 1.0 - normalized_beta_drift,
    }


def _zero_cross_features(z_values: np.ndarray, config: AdvancedMLConfig) -> dict[str, float]:
    transition_count = max(len(z_values) - 1, 0)
    recent_window = min(int(config.regime.regime_window), transition_count)
    if recent_window <= 0:
        crosses_recent = 0
        crosses_baseline = 0
        baseline_window = 1
        recent_window = 1
    else:
        recent_values = z_values[-(recent_window + 1):]
        crosses_recent = _zero_cross_count(recent_values)
        baseline_values = z_values[: len(z_values) - recent_window]
        baseline_window = max(len(baseline_values) - 1, 0)
        if baseline_window <= 0:
            crosses_baseline = crosses_recent
            baseline_window = recent_window
        else:
            crosses_baseline = _zero_cross_count(baseline_values)
    recent_cross_rate = crosses_recent / max(recent_window, 1)
    baseline_cross_rate = crosses_baseline / max(baseline_window, 1)
    zero_cross_rhythm_drop = clamp01(
        (baseline_cross_rate - recent_cross_rate) / max(baseline_cross_rate, 1e-9)
    )
    return {
        "crosses_recent": float(crosses_recent),
        "crosses_baseline": float(crosses_baseline),
        "recent_window": float(recent_window),
        "baseline_window": float(baseline_window),
        "recent_cross_rate": float(recent_cross_rate),
        "baseline_cross_rate": float(baseline_cross_rate),
        "zero_cross_rhythm_drop": zero_cross_rhythm_drop,
        "healthy_cross_rhythm_score": 1.0 - zero_cross_rhythm_drop,
    }


def _volatility_state_features(features: dict[str, float], config: AdvancedMLConfig) -> dict[str, float]:
    vol_ratio = features["realized_vol"] / max(features["baseline_vol"], 1e-9)
    moderate_volatility_score = 1.0 - clamp01(
        abs(vol_ratio - 1.0) / max(config.regime.high_volatility_ratio - 1.0, 1e-9)
    )
    return {
        "vol_ratio": float(vol_ratio),
        "moderate_volatility_score": moderate_volatility_score,
    }


def _liquidity_features(
    orderbook: OrderBookRegimeFeatures,
    config: AdvancedMLConfig,
) -> dict[str, float]:
    stale_book_score = clamp01(
        (orderbook.book_freshness_ms / config.microstructure.max_book_age_ms) - 1.0
    )
    book_fresh_score = 1.0 - stale_book_score
    spread_widening_score = clamp01(
        orderbook.spread_bps / max(config.regime.max_spread_widening_bps, 1e-9)
    )
    low_depth_score = clamp01(
        1.0 - (orderbook.top_depth_usdt / max(config.regime.min_top_depth_usdt, 1e-9))
    )
    slippage_score = clamp01(
        orderbook.slippage_estimate_bps / max(config.microstructure.max_allowed_slippage_bps, 1e-9)
    )
    depth_imbalance_score = clamp01(abs(orderbook.depth_imbalance))
    liquidity_stress = clamp01(
        0.30 * stale_book_score
        + 0.25 * spread_widening_score
        + 0.20 * slippage_score
        + 0.15 * depth_imbalance_score
        + 0.10 * low_depth_score
    )
    return {
        "stale_book_score": stale_book_score,
        "book_fresh_score": book_fresh_score,
        "spread_widening_score": spread_widening_score,
        "low_depth_score": low_depth_score,
        "slippage_score": slippage_score,
        "depth_imbalance_score": depth_imbalance_score,
        "liquidity_stress": liquidity_stress,
        "healthy_liquidity_score": 1.0 - liquidity_stress,
    }


def _mean_reversion_motion_features(
    features: dict[str, float],
    z_points: list[tuple[float, float]],
    config: AdvancedMLConfig,
) -> dict[str, float]:
    z_now = z_points[-1][1]
    z_prev = z_points[-2][1]
    z_moving_toward_mean = abs(z_now) < abs(z_prev)
    z_moving_toward_mean_score = (
        clamp01(abs(features["z_velocity"]) / config.regime.z_velocity_risk_scale)
        if z_moving_toward_mean
        else 0.0
    )
    return {
        "z_moving_toward_mean": float(z_moving_toward_mean),
        "z_moving_toward_mean_score": z_moving_toward_mean_score,
    }


def _finalize_scores_and_aliases(
    features: dict[str, float],
    config: AdvancedMLConfig,
    *,
    time_in_trade_seconds: float | None,
    half_life_seconds: float | None,
) -> None:
    trend_score = clamp01(
        0.40 * features["adverse_z_velocity_score"]
        + 0.30 * features["adverse_acceleration_score"]
        + 0.20 * features["normalized_corr_drift"]
        + 0.10 * features["zero_cross_rhythm_drop"]
    )
    break_risk = clamp01(
        0.25 * features["normalized_corr_drift"]
        + 0.20 * features["normalized_beta_drift"]
        + 0.20 * features["normalized_spread_vol_spike"]
        + 0.15 * features["adverse_z_velocity_score"]
        + 0.10 * features["liquidity_stress"]
        + 0.10 * features["zero_cross_rhythm_drop"]
    )
    mr_confidence = clamp01(
        0.30 * features["z_moving_toward_mean_score"]
        + 0.20 * features["stable_correlation_score"]
        + 0.15 * features["stable_beta_score"]
        + 0.15 * features["healthy_cross_rhythm_score"]
        + 0.10 * features["moderate_volatility_score"]
        + 0.10 * features["healthy_liquidity_score"]
    )
    trend_continuation_risk = clamp01(
        0.50 * trend_score
        + 0.30 * features["adverse_z_velocity_score"]
        + 0.20 * features["normalized_spread_vol_spike"]
    )
    if time_in_trade_seconds is None or half_life_seconds is None:
        half_life_score = 0.50
    else:
        half_life_score = clamp01(
            1.0 - (
                float(time_in_trade_seconds)
                / max(2.0 * float(half_life_seconds), 1.0)
            )
        )

    features.update(
        {
            "trend_score": trend_score,
            "break_risk": break_risk,
            "mr_confidence": mr_confidence,
            "spread_volatility_spike_score": features["normalized_spread_vol_spike"],
            "slippage_risk": features["slippage_score"],
            "hedge_ratio_drift_risk": features["normalized_beta_drift"],
            "low_break_risk_score": 1.0 - break_risk,
            "trend_continuation_risk": trend_continuation_risk,
            "half_life_score": half_life_score,
        }
    )


def _classify_regime(features: dict[str, float], config: AdvancedMLConfig) -> RegimeName:
    if features["break_risk"] >= config.regime.regime_break_threshold:
        return RegimeName.STRUCTURAL_BREAK
    if features["liquidity_stress"] >= config.regime.liquidity_stress_threshold:
        return RegimeName.LIQUIDITY_STRESS
    if features["normalized_corr_drift"] >= config.regime.correlation_breakdown_threshold:
        return RegimeName.CORRELATION_BREAKDOWN
    if features["trend_score"] >= config.regime.trending_threshold:
        return RegimeName.TRENDING
    if features["mr_confidence"] >= config.regime.mean_reverting_threshold:
        return RegimeName.MEAN_REVERTING
    if features["vol_ratio"] >= config.regime.high_volatility_ratio:
        return RegimeName.HIGH_VOLATILITY
    if features["vol_ratio"] <= config.regime.low_volatility_ratio:
        return RegimeName.LOW_VOLATILITY
    return RegimeName.UNKNOWN


def _confidence_for_regime(
    regime: RegimeName,
    features: dict[str, float],
    config: AdvancedMLConfig,
) -> float:
    if regime == RegimeName.STRUCTURAL_BREAK:
        return features["break_risk"]
    if regime == RegimeName.LIQUIDITY_STRESS:
        return features["liquidity_stress"]
    if regime == RegimeName.CORRELATION_BREAKDOWN:
        return features["normalized_corr_drift"]
    if regime == RegimeName.TRENDING:
        return features["trend_score"]
    if regime == RegimeName.MEAN_REVERTING:
        return features["mr_confidence"]
    if regime == RegimeName.HIGH_VOLATILITY:
        return clamp01(
            (features["vol_ratio"] - 1.0)
            / max(config.regime.high_volatility_ratio - 1.0, 1e-9)
        )
    if regime == RegimeName.LOW_VOLATILITY:
        return clamp01(
            (1.0 - features["vol_ratio"])
            / max(1.0 - config.regime.low_volatility_ratio, 1e-9)
        )
    return clamp01(
        max(
            features["mr_confidence"],
            features["trend_score"],
            features["break_risk"],
            features["liquidity_stress"],
            features["normalized_corr_drift"],
        )
    )


def _apply_hysteresis(
    *,
    proposed_regime: RegimeName,
    proposed_confidence: float,
    break_risk: float,
    hysteresis: HysteresisInputs,
    cfg: AdvancedMLConfig,
) -> tuple[RegimeName, float, str | None]:
    previous_regime = _optional_regime(hysteresis.previous_regime)
    if previous_regime is None or previous_regime == proposed_regime:
        return proposed_regime, clamp01(proposed_confidence), None

    can_switch = (
        proposed_regime == RegimeName.STRUCTURAL_BREAK
        and break_risk >= cfg.regime.regime_break_threshold
    ) or (
        hysteresis.ticks_in_proposed_regime >= cfg.regime.min_regime_persistence_ticks
        and hysteresis.seconds_since_last_regime_switch >= cfg.regime.regime_switch_cooldown_seconds
        and proposed_confidence >= (
            hysteresis.previous_regime_confidence
            + cfg.regime.regime_switch_confidence_margin
        )
    )
    if can_switch:
        return proposed_regime, clamp01(proposed_confidence), None

    held_confidence = clamp01(
        0.80 * hysteresis.previous_regime_confidence
        + 0.20 * proposed_confidence
    )
    return previous_regime, held_confidence, "regime switch held by hysteresis"


def _classification_reasons(
    regime: RegimeName,
    features: dict[str, float],
    config: AdvancedMLConfig,
) -> list[str]:
    if regime == RegimeName.STRUCTURAL_BREAK:
        return [f"break_risk >= {config.regime.regime_break_threshold}"]
    if regime == RegimeName.LIQUIDITY_STRESS:
        return [f"liquidity_stress >= {config.regime.liquidity_stress_threshold}"]
    if regime == RegimeName.CORRELATION_BREAKDOWN:
        return [f"normalized_corr_drift >= {config.regime.correlation_breakdown_threshold}"]
    if regime == RegimeName.TRENDING:
        return [f"trend_score >= {config.regime.trending_threshold}"]
    if regime == RegimeName.MEAN_REVERTING:
        return [f"mr_confidence >= {config.regime.mean_reverting_threshold}"]
    if regime == RegimeName.HIGH_VOLATILITY:
        return [f"vol_ratio >= {config.regime.high_volatility_ratio}"]
    if regime == RegimeName.LOW_VOLATILITY:
        return [f"vol_ratio <= {config.regime.low_volatility_ratio}"]
    return ["no regime threshold met"]


def _volatility_state_from_features(features: dict[str, float], config: AdvancedMLConfig) -> str:
    if features["vol_ratio"] >= config.regime.high_volatility_ratio:
        return "high"
    if features["vol_ratio"] <= config.regime.low_volatility_ratio:
        return "low"
    return "normal"


def _liquidity_state_from_features(features: dict[str, float], config: AdvancedMLConfig) -> str:
    if features["liquidity_stress"] >= config.regime.liquidity_stress_threshold:
        return "stress"
    if features["liquidity_stress"] >= 0.5 * config.regime.liquidity_stress_threshold:
        return "warning"
    return "normal"


def _optional_regime(regime: RegimeName | str | None) -> RegimeName | None:
    if regime is None:
        return None
    if isinstance(regime, RegimeName):
        return regime
    return RegimeName(str(regime))


def _normalize_z_history(
    z_history: Iterable[tuple[float, float] | list[float] | float],
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for idx, item in enumerate(z_history):
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            timestamp = float(item[0])
            z_score = float(item[1])
        else:
            timestamp = float(idx)
            z_score = float(item)  # type: ignore[arg-type]
        if not np.isfinite(timestamp) or not np.isfinite(z_score):
            raise ValueError("z_history contains NaN or inf.")
        points.append((timestamp, z_score))
    return points


def _coerce_orderbook(
    orderbook: OrderBookRegimeFeatures | dict[str, float] | None,
    *,
    spread_bps: float | None,
    depth_imbalance: float | None,
    top_depth_usdt: float | None,
    slippage_estimate_bps: float | None,
    book_freshness_ms: float | None,
) -> OrderBookRegimeFeatures:
    if isinstance(orderbook, OrderBookRegimeFeatures):
        return orderbook
    if isinstance(orderbook, dict):
        return OrderBookRegimeFeatures(
            spread_bps=float(orderbook["spread_bps"]),
            depth_imbalance=float(orderbook["depth_imbalance"]),
            top_depth_usdt=float(orderbook["top_depth_usdt"]),
            slippage_estimate_bps=float(orderbook["slippage_estimate_bps"]),
            book_freshness_ms=float(orderbook["book_freshness_ms"]),
        )
    missing = [
        name
        for name, value in {
            "spread_bps": spread_bps,
            "depth_imbalance": depth_imbalance,
            "top_depth_usdt": top_depth_usdt,
            "slippage_estimate_bps": slippage_estimate_bps,
            "book_freshness_ms": book_freshness_ms,
        }.items()
        if value is None
    ]
    if missing:
        raise ValueError(f"Missing orderbook feature(s): {', '.join(missing)}")
    return OrderBookRegimeFeatures(
        spread_bps=float(spread_bps),
        depth_imbalance=float(depth_imbalance),
        top_depth_usdt=float(top_depth_usdt),
        slippage_estimate_bps=float(slippage_estimate_bps),
        book_freshness_ms=float(book_freshness_ms),
    )


def _finite_array(name: str, values: Iterable[float], *, min_len: int) -> np.ndarray:
    array = np.asarray(list(values), dtype=float)
    if array.ndim != 1:
        raise ValueError(f"{name} must be a 1D sequence.")
    if len(array) < min_len:
        raise ValueError(f"{name} must include at least {min_len} observations.")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} contains NaN or inf.")
    return array


def _zero_cross_count(values: np.ndarray) -> int:
    crosses = 0
    last_sign = 0
    for value in values:
        sign = 1 if value > 0.0 else -1 if value < 0.0 else 0
        if sign == 0:
            continue
        if last_sign != 0 and sign != last_sign:
            crosses += 1
        last_sign = sign
    return crosses


__all__ = [
    "HeuristicRegimeDetector",
    "HysteresisInputs",
    "OrderBookRegimeFeatures",
    "clamp01",
    "detect_regime",
]
