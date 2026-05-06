"""Optional global-market context for advanced regime scoring.

The context is deliberately lightweight and config gated. It consumes metrics
the existing bot may already have and never fetches external data on the order
execution path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from core.config.advanced_ml_config import AdvancedMLConfig


@dataclass(frozen=True)
class GlobalMarketContext:
    risk_score: float
    volatility_score: float
    liquidity_stress_score: float
    breadth_stress_score: float
    state: str
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def estimate_global_market_context(
    metrics: dict[str, Any] | None,
    *,
    config: AdvancedMLConfig | None = None,
) -> GlobalMarketContext:
    cfg = config or AdvancedMLConfig()
    values = metrics or {}
    volatility = _clamp01(
        _read_float(values, "global_market_volatility_score", _read_float(values, "market_volatility_score", 0.0))
    )
    liquidity = _clamp01(
        _read_float(
            values,
            "global_market_liquidity_stress_score",
            _read_float(values, "market_liquidity_stress_score", 0.0),
        )
    )
    breadth = _clamp01(
        _read_float(values, "global_market_breadth_stress_score", _read_float(values, "market_breadth_stress_score", 0.0))
    )
    explicit_risk = values.get("global_market_risk_score", values.get("market_risk_score"))
    if explicit_risk is None:
        risk = _clamp01(0.40 * volatility + 0.35 * liquidity + 0.25 * breadth)
        source = "derived"
    else:
        risk = _clamp01(_read_float({"risk": explicit_risk}, "risk", 0.0))
        source = "provided"

    if risk >= cfg.extensions.global_market_high_risk_threshold:
        state = "risk_off"
    elif risk <= cfg.extensions.global_market_low_risk_threshold:
        state = "supportive"
    else:
        state = "neutral"
    return GlobalMarketContext(
        risk_score=risk,
        volatility_score=volatility,
        liquidity_stress_score=liquidity,
        breadth_stress_score=breadth,
        state=state,
        source=source,
    )


def _read_float(values: dict[str, Any], key: str, default: float) -> float:
    try:
        value = float(values.get(key, default))
    except (TypeError, ValueError):
        return float(default)
    return value


def _clamp01(value: float) -> float:
    if value != value:
        return 0.0
    return max(0.0, min(1.0, float(value)))


__all__ = [
    "GlobalMarketContext",
    "estimate_global_market_context",
]
