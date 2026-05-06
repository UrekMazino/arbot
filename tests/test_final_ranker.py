from __future__ import annotations

from dataclasses import dataclass

import pytest

from core.config.advanced_ml_config import AdvancedMLConfig
from core.ranking.final_ranker import FinalRanker, rank_pair
from core.regime.regime_types import RegimeName


@dataclass(frozen=True)
class Pair:
    key: str


@dataclass(frozen=True)
class HardValidation:
    is_valid: bool


@dataclass(frozen=True)
class ValidPairCandidate:
    pair: Pair
    hard_validation: HardValidation
    pair_features: dict[str, float]
    pair_state: str = "stable"


@dataclass(frozen=True)
class RawCandidate:
    pair: Pair


@dataclass(frozen=True)
class RegimeResult:
    regime: RegimeName
    confidence: float
    break_risk: float
    features: dict[str, float]


@dataclass(frozen=True)
class BayesianScore:
    posterior_good_probability: float
    quality_grade: str


@dataclass(frozen=True)
class BanditResult:
    final_rank_score: float


def _config() -> AdvancedMLConfig:
    config = AdvancedMLConfig()
    config.ranking.final_score_soft_cap = 1.50
    return config


def _candidate(
    pair_key: str = "pair",
    *,
    hard_valid: bool = True,
    pair_state: str = "stable",
) -> ValidPairCandidate:
    return ValidPairCandidate(
        pair=Pair(pair_key),
        hard_validation=HardValidation(hard_valid),
        pair_features={"p_value": 0.01},
        pair_state=pair_state,
    )


def _regime(
    regime: RegimeName,
    *,
    confidence: float = 0.90,
    break_risk: float = 0.10,
    slippage_risk: float = 0.05,
    liquidity_stress: float = 0.05,
    hedge_ratio_drift_risk: float = 0.05,
) -> RegimeResult:
    return RegimeResult(
        regime=regime,
        confidence=confidence,
        break_risk=break_risk,
        features={
            "break_risk": break_risk,
            "slippage_risk": slippage_risk,
            "liquidity_stress": liquidity_stress,
            "hedge_ratio_drift_risk": hedge_ratio_drift_risk,
        },
    )


def test_final_ranker_accepts_only_valid_pair_candidate_objects():
    ranker = FinalRanker(_config())

    with pytest.raises(TypeError, match="ValidPairCandidate"):
        ranker.rank(
            RawCandidate(Pair("raw")),
            regime_result=_regime(RegimeName.MEAN_REVERTING),
            bayesian_score=BayesianScore(0.8, "A"),
            bandit_result=BanditResult(1.0),
        )


def test_invalid_valid_pair_candidate_returns_zero_score():
    rank = rank_pair(
        _candidate(hard_valid=False),
        regime_result=_regime(RegimeName.MEAN_REVERTING),
        bayesian_score=BayesianScore(0.9, "A"),
        bandit_result=BanditResult(1.2),
        reputation_state="elite",
        config=_config(),
    )

    assert rank.hard_valid is False
    assert rank.final_score == 0.0
    assert rank.raw_score == 0.0
    assert "failed hard validation" in rank.reasons


def test_elite_mean_reverting_pair_ranks_above_warning_trending_pair():
    ranker = FinalRanker(_config())

    elite_mr = ranker.rank(
        _candidate("elite", pair_state="elite"),
        regime_result=_regime(RegimeName.MEAN_REVERTING, confidence=0.90),
        bayesian_score=BayesianScore(0.80, "A"),
        bandit_result=BanditResult(1.00),
    )
    warning_trending = ranker.rank(
        _candidate("warning", pair_state="warning"),
        regime_result=_regime(RegimeName.TRENDING, confidence=0.90),
        bayesian_score=BayesianScore(0.80, "B"),
        bandit_result=BanditResult(1.00),
    )

    assert elite_mr.regime_score == pytest.approx(1.20)
    assert elite_mr.reputation_score == pytest.approx(1.15)
    assert warning_trending.regime_score == pytest.approx(0.60)
    assert warning_trending.reputation_score == pytest.approx(0.75)
    assert elite_mr.final_score > warning_trending.final_score


def test_final_score_is_clamped_to_zero_when_raw_score_is_negative():
    rank = rank_pair(
        _candidate(),
        regime_result=_regime(
            RegimeName.UNKNOWN,
            break_risk=1.0,
            slippage_risk=1.0,
            liquidity_stress=1.0,
            hedge_ratio_drift_risk=1.0,
        ),
        bayesian_score=BayesianScore(0.8, "B"),
        bandit_result=BanditResult(1.0),
        config=_config(),
    )

    assert rank.risk_penalty == pytest.approx(1.0)
    assert rank.raw_score == pytest.approx(0.0)
    assert rank.final_score == 0.0


def test_raw_score_can_exceed_one_but_final_score_is_capped_at_one():
    config = _config()
    config.ranking.final_score_soft_cap = 1.0

    rank = rank_pair(
        _candidate(pair_state="elite"),
        regime_result=_regime(
            RegimeName.MEAN_REVERTING,
            confidence=0.90,
            break_risk=0.0,
            slippage_risk=0.0,
            liquidity_stress=0.0,
            hedge_ratio_drift_risk=0.0,
        ),
        bayesian_score=BayesianScore(0.99, "A"),
        bandit_result=BanditResult(2.0),
        config=config,
    )

    assert rank.raw_score > 1.0
    assert rank.final_score == 1.0


def test_final_score_uses_final_score_soft_cap():
    config = _config()
    config.ranking.final_score_soft_cap = 2.0

    rank = rank_pair(
        _candidate(),
        regime_result=_regime(
            RegimeName.MEAN_REVERTING,
            confidence=0.90,
            break_risk=0.0,
            slippage_risk=0.0,
            liquidity_stress=0.0,
            hedge_ratio_drift_risk=0.0,
        ),
        bayesian_score=BayesianScore(0.5, "C"),
        bandit_result=BanditResult(1.0),
        config=config,
    )

    assert rank.raw_score == pytest.approx(1.20 * 0.5 * 1.0 * 1.0)
    assert rank.final_score == pytest.approx(rank.raw_score / 2.0)


def test_risk_penalty_uses_explicit_alias_fallbacks():
    rank = rank_pair(
        _candidate(),
        regime_result=RegimeResult(
            regime=RegimeName.UNKNOWN,
            confidence=0.0,
            break_risk=0.40,
            features={
                "slippage_score": 0.20,
                "liquidity_stress": 0.30,
                "normalized_beta_drift": 0.50,
            },
        ),
        bayesian_score=BayesianScore(0.8, "B"),
        bandit_result=BanditResult(1.0),
        config=_config(),
    )

    assert rank.risk_penalty == pytest.approx(
        0.35 * 0.40 + 0.25 * 0.20 + 0.20 * 0.30 + 0.20 * 0.50
    )
