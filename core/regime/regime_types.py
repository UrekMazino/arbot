"""Regime labels and detection result contracts for the advanced ML stack."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    PairIdentity = Any


class RegimeName(str, Enum):
    MEAN_REVERTING = "mean_reverting"
    TRENDING = "trending"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    CORRELATION_BREAKDOWN = "correlation_breakdown"
    LIQUIDITY_STRESS = "liquidity_stress"
    STRUCTURAL_BREAK = "structural_break"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RegimeDetectionResult:
    pair: PairIdentity
    regime: RegimeName
    confidence: float
    break_risk: float
    volatility_state: str
    liquidity_state: str
    mean_reversion_velocity: float
    mean_reversion_acceleration: float
    trend_score: float
    transition_probability: dict[str, float]
    features: dict[str, float]
    reasons: list[str]
    timestamp: float


__all__ = [
    "RegimeDetectionResult",
    "RegimeName",
]
