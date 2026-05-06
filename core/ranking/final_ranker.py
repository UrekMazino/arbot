"""Final ranking combiner for hard-valid pair candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.config.advanced_ml_config import AdvancedMLConfig
from core.regime.regime_types import RegimeName


@dataclass(frozen=True)
class FinalPairRank:
    pair: Any
    hard_valid: bool
    final_score: float
    raw_score: float
    regime_score: float
    bayesian_score: float
    bandit_score: float
    reputation_score: float
    risk_penalty: float
    quality_grade: str
    reasons: list[str]


class FinalRanker:
    def __init__(self, config: AdvancedMLConfig | None = None) -> None:
        self.config = config or AdvancedMLConfig()

    def rank(
        self,
        candidate: Any,
        *,
        regime_result: Any,
        bayesian_score: Any,
        bandit_result: Any,
        reputation_state: Any | None = None,
    ) -> FinalPairRank:
        _assert_valid_pair_candidate_object(candidate)
        pair = _read_attr(candidate, "pair")
        hard_valid = bool(_read_attr(_read_attr(candidate, "hard_validation"), "is_valid", False))
        quality_grade = str(_read_attr(bayesian_score, "quality_grade", "D"))
        if not hard_valid:
            return FinalPairRank(
                pair=pair,
                hard_valid=False,
                final_score=0.0,
                raw_score=0.0,
                regime_score=0.0,
                bayesian_score=0.0,
                bandit_score=0.0,
                reputation_score=0.0,
                risk_penalty=1.0,
                quality_grade=quality_grade,
                reasons=["failed hard validation"],
            )

        regime_score = _regime_score(regime_result, self.config)
        bayes_score = _bayesian_score(bayesian_score)
        bandit_score = _bandit_score(bandit_result)
        reputation_score = _reputation_score(
            reputation_state
            if reputation_state is not None
            else _read_attr(candidate, "pair_state", _read_attr(candidate, "state", "stable"))
        )
        risk_penalty = _risk_penalty(regime_result)
        raw_score = (
            regime_score
            * bayes_score
            * bandit_score
            * reputation_score
            * (1.0 - risk_penalty)
        )
        final_score = clamp01(raw_score / max(self.config.ranking.final_score_soft_cap, 1e-9))

        return FinalPairRank(
            pair=pair,
            hard_valid=True,
            final_score=final_score,
            raw_score=float(raw_score),
            regime_score=regime_score,
            bayesian_score=bayes_score,
            bandit_score=bandit_score,
            reputation_score=reputation_score,
            risk_penalty=risk_penalty,
            quality_grade=quality_grade,
            reasons=_rank_reasons(regime_result, reputation_state, risk_penalty),
        )

    def rank_many(
        self,
        candidates: list[Any] | tuple[Any, ...],
        *,
        regime_results: dict[Any, Any],
        bayesian_scores: dict[Any, Any],
        bandit_results: dict[Any, Any],
        reputation_states: dict[Any, Any] | None = None,
    ) -> list[FinalPairRank]:
        ranks = [
            self.rank(
                candidate,
                regime_result=regime_results[_pair_key(_read_attr(candidate, "pair"))],
                bayesian_score=bayesian_scores[_pair_key(_read_attr(candidate, "pair"))],
                bandit_result=bandit_results[_pair_key(_read_attr(candidate, "pair"))],
                reputation_state=(
                    reputation_states or {}
                ).get(_pair_key(_read_attr(candidate, "pair"))),
            )
            for candidate in candidates
        ]
        return sorted(ranks, key=lambda rank: rank.final_score, reverse=True)


def rank_pair(
    candidate: Any,
    *,
    regime_result: Any,
    bayesian_score: Any,
    bandit_result: Any,
    reputation_state: Any | None = None,
    config: AdvancedMLConfig | None = None,
) -> FinalPairRank:
    return FinalRanker(config).rank(
        candidate,
        regime_result=regime_result,
        bayesian_score=bayesian_score,
        bandit_result=bandit_result,
        reputation_state=reputation_state,
    )


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _assert_valid_pair_candidate_object(candidate: Any) -> None:
    if candidate.__class__.__name__ != "ValidPairCandidate":
        raise TypeError("FinalRanker accepts only ValidPairCandidate objects.")
    required = ("pair", "hard_validation", "pair_features")
    missing = [name for name in required if not hasattr(candidate, name)]
    if missing:
        raise TypeError(f"ValidPairCandidate missing required field(s): {', '.join(missing)}")


def _regime_score(regime_result: Any, config: AdvancedMLConfig) -> float:
    regime = _optional_regime(_read_attr(regime_result, "regime"))
    confidence = float(_read_attr(regime_result, "confidence", 0.0))
    if regime == RegimeName.MEAN_REVERTING:
        return 1.20 if confidence >= config.regime.mean_reverting_threshold else 1.00
    if regime == RegimeName.UNKNOWN:
        return 0.90
    if regime == RegimeName.HIGH_VOLATILITY:
        return 0.85
    if regime == RegimeName.TRENDING:
        return 0.60
    if regime == RegimeName.CORRELATION_BREAKDOWN:
        return 0.30
    if regime == RegimeName.LIQUIDITY_STRESS:
        return 0.25
    if regime == RegimeName.STRUCTURAL_BREAK:
        return 0.0
    return 0.90


def _bayesian_score(score: Any) -> float:
    value = _read_attr(score, "posterior_good_probability", score)
    return clamp01(float(value))


def _bandit_score(score: Any) -> float:
    value = _read_attr(score, "final_rank_score", score)
    return max(0.0, float(value))


def _reputation_score(state: Any) -> float:
    normalized = _state_value(state)
    if normalized == "elite":
        return 1.15
    if normalized == "stable":
        return 1.00
    if normalized == "warning":
        return 0.75
    if normalized == "hospital":
        return 0.25
    if normalized == "graveyard":
        return 0.0
    return 1.00


def _risk_penalty(regime_result: Any) -> float:
    features = _features_to_dict(_read_attr(regime_result, "features"))
    break_risk = float(_read_attr(regime_result, "break_risk", features.get("break_risk", 0.0)))
    slippage_risk = float(features.get("slippage_risk", features.get("slippage_score", 0.0)))
    liquidity_stress = float(features.get("liquidity_stress", 0.0))
    hedge_ratio_drift_risk = float(
        features.get("hedge_ratio_drift_risk", features.get("normalized_beta_drift", 0.0))
    )
    return clamp01(
        0.35 * break_risk
        + 0.25 * slippage_risk
        + 0.20 * liquidity_stress
        + 0.20 * hedge_ratio_drift_risk
    )


def _rank_reasons(regime_result: Any, reputation_state: Any | None, risk_penalty: float) -> list[str]:
    return [
        f"regime={_state_value(_read_attr(regime_result, 'regime', 'unknown'))}",
        f"reputation={_state_value(reputation_state) if reputation_state is not None else 'candidate/default'}",
        f"risk_penalty={risk_penalty:.4f}",
    ]


def _features_to_dict(features: Any) -> dict[str, Any]:
    if features is None:
        return {}
    if isinstance(features, dict):
        return dict(features)
    if hasattr(features, "to_dict"):
        return dict(features.to_dict())
    return {}


def _optional_regime(regime: Any) -> RegimeName | None:
    if regime is None:
        return None
    if isinstance(regime, RegimeName):
        return regime
    try:
        return RegimeName(str(regime))
    except ValueError:
        return None


def _read_attr(source: Any, name: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _state_value(state: Any) -> str:
    value = _read_attr(state, "value", state)
    return str(value).lower()


def _pair_key(pair: Any) -> str:
    key = _read_attr(pair, "key")
    return str(key if key is not None else pair)


__all__ = [
    "FinalPairRank",
    "FinalRanker",
    "clamp01",
    "rank_pair",
]
