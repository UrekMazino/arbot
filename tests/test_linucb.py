from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from core.config.advanced_ml_config import AdvancedMLConfig
from core.features.feature_schema import FeatureSchema, NamedFeatureVector
from core.online_learning.linucb import BanditContext, LinUCBContextualBandit


@dataclass(frozen=True)
class Pair:
    key: str


@dataclass(frozen=True)
class HardValidation:
    is_valid: bool


@dataclass(frozen=True)
class CandidateContext:
    pair: Pair
    features: NamedFeatureVector
    hard_validation: HardValidation


def _config() -> AdvancedMLConfig:
    config = AdvancedMLConfig()
    config.bandit.alpha = 0.75
    config.bandit.decay = 0.5
    config.bandit.lambda_reg = 1.0
    config.bandit.reward_scale_bps = 50.0
    return config


def _schema() -> FeatureSchema:
    return FeatureSchema(("break_risk", "liquidity_score"))


def _context(values: list[float] | np.ndarray, pair_key: str = "pair") -> BanditContext:
    return BanditContext(
        pair=Pair(pair_key),
        features=NamedFeatureVector(_schema(), np.asarray(values, dtype=float)),
    )


def test_a_matrix_updates_with_regularization_preserving_decay_formula():
    schema = _schema()
    bandit = LinUCBContextualBandit(
        _config(),
        schema=schema,
        A=2.0 * np.eye(2),
        b=np.array([1.0, -1.0]),
    )
    context = _context([2.0, 3.0])

    bandit.update(context, reward=0.25)

    expected_A = 0.5 * (2.0 * np.eye(2)) + 0.5 * np.eye(2) + np.outer([2.0, 3.0], [2.0, 3.0])
    assert bandit.A is not None
    assert np.allclose(bandit.A, expected_A)


def test_b_vector_updates_with_decayed_previous_reward_state():
    bandit = LinUCBContextualBandit(
        _config(),
        schema=_schema(),
        A=2.0 * np.eye(2),
        b=np.array([1.0, -1.0]),
    )

    bandit.update(_context([2.0, 3.0]), reward=0.25)

    assert bandit.b is not None
    assert np.allclose(bandit.b, np.array([1.0, 0.25]))


def test_exploration_bonus_shrinks_as_same_context_is_seen_repeatedly():
    config = _config()
    config.bandit.decay = 1.0
    bandit = LinUCBContextualBandit(config, schema=_schema())
    context = _context([1.0, 0.0])

    before = bandit.rank(context).exploration_bonus
    for _ in range(20):
        bandit.update(context, reward=0.5)
    after = bandit.rank(context).exploration_bonus

    assert after < before


def test_regularization_identity_prior_does_not_vanish_under_many_decayed_updates():
    config = _config()
    config.bandit.decay = 0.1
    config.bandit.lambda_reg = 1.0
    bandit = LinUCBContextualBandit(config, schema=_schema())
    zero_context = _context([0.0, 0.0])

    for _ in range(50):
        bandit.update(zero_context, reward=0.0)

    assert bandit.A is not None
    assert np.allclose(bandit.A, np.eye(2))


def test_raw_numpy_features_are_rejected_before_matrix_math():
    bandit = LinUCBContextualBandit(_config(), schema=_schema())

    with pytest.raises(TypeError, match="NamedFeatureVector"):
        bandit.rank({"pair": Pair("raw"), "features": np.array([1.0, 2.0])})


def test_schema_mismatch_is_rejected_before_matrix_math():
    bandit = LinUCBContextualBandit(_config(), schema=_schema())
    mismatched = BanditContext(
        pair=Pair("bad-schema"),
        features=NamedFeatureVector(
            FeatureSchema(("liquidity_score", "break_risk")),
            np.array([1.0, 0.5]),
        ),
    )

    with pytest.raises(ValueError, match="schema names"):
        bandit.rank(mismatched)


def test_invalid_candidate_is_never_selected_or_updated():
    bandit = LinUCBContextualBandit(_config(), schema=_schema())
    invalid = CandidateContext(
        pair=Pair("invalid"),
        features=NamedFeatureVector(_schema(), np.array([10.0, 10.0])),
        hard_validation=HardValidation(False),
    )
    valid = CandidateContext(
        pair=Pair("valid"),
        features=NamedFeatureVector(_schema(), np.array([0.1, 0.2])),
        hard_validation=HardValidation(True),
    )

    selected = bandit.select([invalid, valid])
    updated = bandit.update(invalid, reward=1.0)

    assert selected is not None
    assert selected.pair == Pair("valid")
    assert updated is False


def test_reward_bps_is_normalized_with_tanh_reward_formula():
    config = _config()
    config.bandit.decay = 1.0
    config.bandit.reward_scale_bps = 50.0
    bandit = LinUCBContextualBandit(config, schema=_schema())

    bandit.update(
        _context([1.0, 0.0]),
        pnl_bps=100.0,
        fee_bps=10.0,
        slippage_bps=5.0,
        drawdown_penalty_bps=5.0,
        regime_break_penalty_bps=0.0,
        excessive_hold_penalty_bps=0.0,
    )

    assert bandit.b is not None
    assert bandit.b[0] == pytest.approx(np.tanh(80.0 / 50.0))


def test_linucb_state_round_trips_with_schema():
    bandit = LinUCBContextualBandit(_config(), schema=_schema())
    bandit.update(_context([0.5, 0.25]), reward=0.4)

    restored = LinUCBContextualBandit.from_dict(bandit.to_dict())

    assert restored.schema == bandit.schema
    assert restored.A is not None
    assert restored.b is not None
    assert np.allclose(restored.A, bandit.A)
    assert np.allclose(restored.b, bandit.b)
