from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import pytest

from core.bayes.bayesian_pair_scorer import BayesianPairScorer
from core.config.advanced_ml_config import AdvancedMLConfig
from core.regime.regime_types import RegimeName


@dataclass(frozen=True)
class Pair:
    symbol_1: str = "AAA-USDT-SWAP"
    symbol_2: str = "BBB-USDT-SWAP"
    timeframe: str = "1m"
    window: int = 200

    @property
    def key(self) -> str:
        return f"{self.symbol_1}|{self.symbol_2}|{self.timeframe}|{self.window}"


@dataclass(frozen=True)
class HardValidation:
    is_valid: bool = True
    p_value: float | None = 0.01
    reasons: list[str] | None = None


@dataclass(frozen=True)
class RegimeResult:
    regime: RegimeName
    confidence: float
    break_risk: float
    features: dict[str, float]


def _config() -> AdvancedMLConfig:
    config = AdvancedMLConfig()
    config.bayes.alpha0 = 2.0
    config.bayes.beta0 = 2.0
    config.bayes.decay = 1.0
    config.bayes.feature_weight = 0.30
    config.bayes.min_evidence = 10
    config.bayes.max_grade_when_low_evidence = "C"
    config.bandit.reward_scale_bps = 50.0
    return config


def _good_regime(break_risk: float = 0.10) -> RegimeResult:
    return RegimeResult(
        regime=RegimeName.MEAN_REVERTING,
        confidence=0.90,
        break_risk=break_risk,
        features={"break_risk": break_risk},
    )


def test_sparse_data_returns_neutralish_posterior_and_low_evidence_reason():
    scorer = BayesianPairScorer(_config())

    score = scorer.score(
        pair=Pair(),
        hard_validation=HardValidation(is_valid=True, p_value=0.01),
        regime_result=_good_regime(),
    )

    assert score.evidence_count == 0
    assert score.posterior_good_probability == pytest.approx(0.5, abs=0.02)
    assert score.quality_grade == "C"
    assert "low Bayesian evidence" in score.reasons


def test_low_evidence_caps_grade_at_configured_maximum():
    scorer = BayesianPairScorer.from_dict(
        {
            "states": {
                Pair().key: {
                    "alpha": 40.0,
                    "beta": 2.0,
                    "evidence_count": 1,
                }
            }
        }
    )
    scorer.config = _config()

    score = scorer.score(
        pair=Pair(),
        hard_validation=HardValidation(is_valid=True, p_value=0.001),
        regime_result=_good_regime(break_risk=0.05),
    )

    assert score.posterior_good_probability > 0.80
    assert score.quality_grade == "C"
    assert "low Bayesian evidence" in score.reasons


def test_ten_consecutive_successes_raise_posterior_above_point_seven_five():
    scorer = BayesianPairScorer(_config())
    pair = Pair()
    hard_validation = HardValidation(is_valid=True, p_value=0.01)

    for _ in range(10):
        updated = scorer.update(
            pair=pair,
            hard_validation=hard_validation,
            net_pnl_after_fees=10.0,
            net_pnl_bps=100.0,
            slippage_bps=1.0,
            hold_time_seconds=60.0,
        )
        assert updated is True

    score = scorer.score(pair=pair, hard_validation=hard_validation, regime_result=_good_regime())

    assert score.evidence_count == 10
    assert score.posterior_good_probability > 0.75


def test_ten_consecutive_failures_drop_posterior_below_point_three():
    scorer = BayesianPairScorer(_config())
    pair = Pair()
    hard_validation = HardValidation(is_valid=True, p_value=0.01)

    for _ in range(10):
        scorer.update(
            pair=pair,
            hard_validation=hard_validation,
            net_pnl_after_fees=-10.0,
            net_pnl_bps=-100.0,
            slippage_bps=1.0,
            hold_time_seconds=60.0,
        )

    score = scorer.score(pair=pair, hard_validation=hard_validation, regime_result=_good_regime())

    assert score.evidence_count == 10
    assert score.posterior_good_probability < 0.30


def test_feature_multipliers_alter_posterior_in_expected_direction():
    scorer = BayesianPairScorer.from_dict(
        {
            "states": {
                Pair().key: {
                    "alpha": 10.0,
                    "beta": 10.0,
                    "evidence_count": 10,
                }
            }
        }
    )
    scorer.config = _config()

    favorable = scorer.score(
        pair=Pair(),
        hard_validation=HardValidation(is_valid=True, p_value=0.001),
        regime_result=_good_regime(break_risk=0.10),
    )
    unfavorable = scorer.score(
        pair=Pair(),
        hard_validation=HardValidation(is_valid=True, p_value=0.20),
        regime_result=RegimeResult(
            regime=RegimeName.STRUCTURAL_BREAK,
            confidence=0.95,
            break_risk=0.90,
            features={"break_risk": 0.90},
        ),
    )

    assert favorable.feature_likelihoods == {
        "p_value": pytest.approx(1.20),
        "regime": pytest.approx(1.20),
    }
    assert unfavorable.feature_likelihoods == {
        "p_value": pytest.approx(0.70),
        "regime": pytest.approx(0.30),
    }
    assert favorable.posterior_good_probability > unfavorable.posterior_good_probability


def test_failed_hard_validation_returns_zero_posterior_grade_d_and_does_not_update():
    scorer = BayesianPairScorer(_config())
    pair = Pair()
    invalid = HardValidation(is_valid=False, p_value=0.001, reasons=["bad alignment"])

    score = scorer.score(pair=pair, hard_validation=invalid, regime_result=_good_regime())
    updated = scorer.update(
        pair=pair,
        hard_validation=invalid,
        net_pnl_after_fees=100.0,
        net_pnl_bps=100.0,
    )

    assert score.posterior_good_probability == 0.0
    assert score.quality_grade == "D"
    assert "failed hard validation" in score.reasons
    assert updated is False
    assert scorer.to_dict()["states"] == {}


def test_updates_are_thread_safe_and_state_round_trips():
    scorer = BayesianPairScorer(_config())
    pair = Pair()
    hard_validation = HardValidation(is_valid=True, p_value=0.01)

    def update_once(_: int) -> bool:
        return scorer.update(
            pair=pair,
            hard_validation=hard_validation,
            net_pnl_after_fees=5.0,
            net_pnl_bps=50.0,
            slippage_bps=1.0,
            hold_time_seconds=60.0,
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert all(executor.map(update_once, range(100)))

    serialized = scorer.to_dict()
    restored = BayesianPairScorer.from_dict(serialized)
    restored.config = scorer.config

    assert serialized["states"][pair.key]["evidence_count"] == 100
    assert restored.to_dict()["states"][pair.key]["evidence_count"] == 100
    assert restored.score(
        pair=pair,
        hard_validation=hard_validation,
        regime_result=_good_regime(),
    ).posterior_good_probability == pytest.approx(
        scorer.score(
            pair=pair,
            hard_validation=hard_validation,
            regime_result=_good_regime(),
        ).posterior_good_probability
    )
