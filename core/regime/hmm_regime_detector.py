"""Optional HMM-style regime refinement.

This module intentionally avoids a hard hmmlearn dependency. When enabled, it
uses transition probabilities and global-market risk as a small smoothing layer
over the explicit heuristic detector. The heuristic result remains the source
of truth unless the optional extension is turned on by config.
"""

from __future__ import annotations

from dataclasses import replace

from core.config.advanced_ml_config import AdvancedMLConfig
from core.regime.global_market_context import GlobalMarketContext
from core.regime.regime_types import RegimeDetectionResult, RegimeName


class OptionalHMMRegimeRefiner:
    def __init__(self, config: AdvancedMLConfig | None = None) -> None:
        self.config = config or AdvancedMLConfig()

    def refine(
        self,
        result: RegimeDetectionResult,
        *,
        global_context: GlobalMarketContext | None = None,
    ) -> RegimeDetectionResult:
        if not self.config.extensions.hmm_regime_enabled:
            return result
        context_risk = float(global_context.risk_score) if global_context is not None else 0.0
        features = dict(result.features)
        reasons = list(result.reasons)
        confidence = float(result.confidence)
        break_risk = float(result.break_risk)
        regime = result.regime

        if global_context is not None:
            features["global_market_risk_score"] = context_risk
            features["global_market_volatility_score"] = global_context.volatility_score
            features["global_market_liquidity_stress_score"] = global_context.liquidity_stress_score

        if context_risk >= self.config.extensions.global_market_high_risk_threshold:
            break_risk = _clamp01(
                break_risk + self.config.extensions.global_market_risk_weight * context_risk
            )
            if regime == RegimeName.MEAN_REVERTING and confidence < 0.85:
                regime = RegimeName.HIGH_VOLATILITY
                confidence = max(confidence, 0.55 + 0.30 * context_risk)
                reasons.append("hmm_global_market_risk_overlay")
        elif context_risk <= self.config.extensions.global_market_low_risk_threshold:
            if regime == RegimeName.UNKNOWN and result.mean_reversion_velocity > 0.0:
                regime = RegimeName.MEAN_REVERTING
                confidence = max(confidence, 0.55)
                reasons.append("hmm_supportive_market_overlay")

        features["hmm_refined"] = 1.0
        return replace(
            result,
            regime=regime,
            confidence=_clamp01(confidence),
            break_risk=_clamp01(break_risk),
            features=features,
            reasons=reasons,
        )


def _clamp01(value: float) -> float:
    if value != value:
        return 0.0
    return max(0.0, min(1.0, float(value)))


__all__ = ["OptionalHMMRegimeRefiner"]
