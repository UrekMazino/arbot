"""Microstructure exit analysis for execution urgency and order style."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.config.advanced_ml_config import AdvancedMLConfig
from core.regime.regime_types import RegimeName


@dataclass(frozen=True)
class MicrostructureExitResult:
    liquidity_fresh: bool
    book_stress_score: float
    slippage_risk_score: float
    depth_imbalance_score: float
    exit_urgency_multiplier: float
    recommended_order_style: str
    reasons: list[str]
    metrics: dict[str, float]


class MicrostructureAnalyzer:
    def __init__(self, config: AdvancedMLConfig | None = None) -> None:
        self.config = config or AdvancedMLConfig()

    def analyze_exit(
        self,
        *,
        update_age_ms: float,
        bid_depth: float,
        ask_depth: float,
        estimated_slippage_bps: float,
        spread_bps: float,
        adverse_z_velocity_score: float,
        regime: RegimeName | str | None,
        hard_kill_triggered: bool = False,
    ) -> MicrostructureExitResult:
        cfg = self.config
        bid_depth = max(float(bid_depth), 0.0)
        ask_depth = max(float(ask_depth), 0.0)
        total_depth = bid_depth + ask_depth
        spread_bps = max(float(spread_bps), 0.0)
        estimated_slippage_bps = max(float(estimated_slippage_bps), 0.0)

        stale_book_score = clamp01(
            (float(update_age_ms) / cfg.microstructure.max_book_age_ms) - 1.0
        )
        liquidity_fresh = stale_book_score <= 0.0
        spread_widening_score = clamp01(
            spread_bps / max(cfg.regime.max_spread_widening_bps, 1e-9)
        )
        depth_imbalance_score = clamp01(
            abs(bid_depth - ask_depth) / max(total_depth, 1e-9)
        )
        raw_slippage_risk_score = clamp01(
            estimated_slippage_bps / max(cfg.microstructure.max_allowed_slippage_bps, 1e-9)
        )
        slippage_risk_score_for_exit_score = min(
            raw_slippage_risk_score,
            cfg.microstructure.exit_score_slippage_cap,
        )
        low_depth_score = clamp01(
            1.0 - (total_depth / max(cfg.regime.min_top_depth_usdt, 1e-9))
        )
        book_stress_score = clamp01(
            0.30 * stale_book_score
            + 0.25 * spread_widening_score
            + 0.20 * slippage_risk_score_for_exit_score
            + 0.15 * depth_imbalance_score
            + 0.10 * low_depth_score
        )
        exit_urgency_multiplier = min(
            1.0 + cfg.microstructure.max_urgency_boost * book_stress_score,
            cfg.microstructure.max_exit_urgency_multiplier,
        )
        recommended_order_style = _recommended_order_style(
            liquidity_fresh=liquidity_fresh,
            hard_kill_triggered=hard_kill_triggered,
            book_stress_score=book_stress_score,
            adverse_z_velocity_score=float(adverse_z_velocity_score),
            spread_bps=spread_bps,
            regime=regime,
            config=cfg,
        )

        return MicrostructureExitResult(
            liquidity_fresh=liquidity_fresh,
            book_stress_score=book_stress_score,
            slippage_risk_score=slippage_risk_score_for_exit_score,
            depth_imbalance_score=depth_imbalance_score,
            exit_urgency_multiplier=exit_urgency_multiplier,
            recommended_order_style=recommended_order_style,
            reasons=_reasons(
                liquidity_fresh=liquidity_fresh,
                book_stress_score=book_stress_score,
                raw_slippage_risk_score=raw_slippage_risk_score,
                slippage_risk_score_for_exit_score=slippage_risk_score_for_exit_score,
                recommended_order_style=recommended_order_style,
                config=cfg,
            ),
            metrics={
                "update_age_ms": float(update_age_ms),
                "stale_book_score": stale_book_score,
                "spread_bps": spread_bps,
                "spread_widening_score": spread_widening_score,
                "bid_depth": bid_depth,
                "ask_depth": ask_depth,
                "total_depth": total_depth,
                "low_depth_score": low_depth_score,
                "estimated_slippage_bps": estimated_slippage_bps,
                "ev_estimated_slippage_bps": estimated_slippage_bps,
                "raw_slippage_risk_score": raw_slippage_risk_score,
                "slippage_risk_score_for_exit_score": slippage_risk_score_for_exit_score,
                "adverse_z_velocity_score": float(adverse_z_velocity_score),
            },
        )


def analyze_microstructure_exit(
    *,
    update_age_ms: float,
    bid_depth: float,
    ask_depth: float,
    estimated_slippage_bps: float,
    spread_bps: float,
    adverse_z_velocity_score: float,
    regime: RegimeName | str | None,
    hard_kill_triggered: bool = False,
    config: AdvancedMLConfig | None = None,
) -> MicrostructureExitResult:
    return MicrostructureAnalyzer(config).analyze_exit(
        update_age_ms=update_age_ms,
        bid_depth=bid_depth,
        ask_depth=ask_depth,
        estimated_slippage_bps=estimated_slippage_bps,
        spread_bps=spread_bps,
        adverse_z_velocity_score=adverse_z_velocity_score,
        regime=regime,
        hard_kill_triggered=hard_kill_triggered,
    )


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _recommended_order_style(
    *,
    liquidity_fresh: bool,
    hard_kill_triggered: bool,
    book_stress_score: float,
    adverse_z_velocity_score: float,
    spread_bps: float,
    regime: RegimeName | str | None,
    config: AdvancedMLConfig,
) -> str:
    regime_name = _optional_regime(regime)
    if not liquidity_fresh:
        return "taker" if hard_kill_triggered else "wait"
    if (
        book_stress_score >= config.microstructure.severe_book_stress_threshold
        and adverse_z_velocity_score >= config.microstructure.fast_adverse_threshold
    ):
        return "taker"
    if book_stress_score >= 0.60:
        return "split"
    if (
        spread_bps >= config.microstructure.wide_spread_bps
        and regime_name not in (RegimeName.TRENDING, RegimeName.STRUCTURAL_BREAK)
    ):
        return "maker"
    return "split"


def _reasons(
    *,
    liquidity_fresh: bool,
    book_stress_score: float,
    raw_slippage_risk_score: float,
    slippage_risk_score_for_exit_score: float,
    recommended_order_style: str,
    config: AdvancedMLConfig,
) -> list[str]:
    reasons: list[str] = []
    if not liquidity_fresh:
        reasons.append("liquidity stale")
    if book_stress_score >= config.microstructure.severe_book_stress_threshold:
        reasons.append("severe book stress")
    elif book_stress_score >= 0.60:
        reasons.append("elevated book stress")
    if raw_slippage_risk_score > slippage_risk_score_for_exit_score:
        reasons.append("slippage contribution capped for exit score")
    reasons.append(f"recommended_order_style={recommended_order_style}")
    return reasons


def _optional_regime(regime: RegimeName | str | None) -> RegimeName | None:
    if regime is None:
        return None
    if isinstance(regime, RegimeName):
        return regime
    try:
        return RegimeName(str(regime))
    except ValueError:
        return None


__all__ = [
    "MicrostructureAnalyzer",
    "MicrostructureExitResult",
    "analyze_microstructure_exit",
    "clamp01",
]
