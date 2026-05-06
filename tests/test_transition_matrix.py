from __future__ import annotations

import pytest

from core.regime.regime_types import RegimeName
from core.regime.transition_matrix import RegimeTransitionMatrix


def test_transition_update_uses_decayed_float_weights_not_counts():
    matrix = RegimeTransitionMatrix(decay=0.5)

    matrix.update(RegimeName.MEAN_REVERTING, RegimeName.TRENDING)
    matrix.update(RegimeName.MEAN_REVERTING, RegimeName.TRENDING)

    weight = matrix.weights["mean_reverting"]["trending"]
    assert isinstance(weight, float)
    assert weight == pytest.approx(1.5)


def test_transition_probabilities_normalize_outgoing_weights():
    matrix = RegimeTransitionMatrix(decay=1.0)

    matrix.update(RegimeName.MEAN_REVERTING, RegimeName.TRENDING)
    matrix.update(RegimeName.MEAN_REVERTING, RegimeName.LIQUIDITY_STRESS)

    probabilities = matrix.probabilities(RegimeName.MEAN_REVERTING)

    assert probabilities == {
        "trending": pytest.approx(0.5),
        "liquidity_stress": pytest.approx(0.5),
    }
    assert sum(probabilities.values()) == pytest.approx(1.0)


def test_update_decays_existing_rows_before_recording_new_transition():
    matrix = RegimeTransitionMatrix(decay=0.5)

    matrix.update(RegimeName.MEAN_REVERTING, RegimeName.TRENDING)
    matrix.update(RegimeName.HIGH_VOLATILITY, RegimeName.LOW_VOLATILITY)

    assert matrix.weights["mean_reverting"]["trending"] == pytest.approx(0.5)
    assert matrix.weights["high_volatility"]["low_volatility"] == pytest.approx(1.0)


def test_update_prunes_tiny_decayed_weights():
    matrix = RegimeTransitionMatrix(decay=0.1, min_mass=0.2)

    matrix.update(RegimeName.MEAN_REVERTING, RegimeName.TRENDING)
    matrix.update(RegimeName.HIGH_VOLATILITY, RegimeName.LOW_VOLATILITY)

    assert "mean_reverting" not in matrix.weights
    assert matrix.weights["high_volatility"]["low_volatility"] == pytest.approx(1.0)


def test_probabilities_for_unseen_regime_return_empty_dict():
    matrix = RegimeTransitionMatrix()

    assert matrix.probabilities(RegimeName.UNKNOWN) == {}


def test_transition_matrix_round_trips_serialized_state():
    matrix = RegimeTransitionMatrix(decay=0.75, min_mass=0.01)
    matrix.update(RegimeName.CORRELATION_BREAKDOWN, RegimeName.STRUCTURAL_BREAK)
    matrix.update(RegimeName.CORRELATION_BREAKDOWN, RegimeName.UNKNOWN)

    restored = RegimeTransitionMatrix.from_dict(matrix.to_dict())

    assert restored.decay == pytest.approx(0.75)
    assert restored.min_mass == pytest.approx(0.01)
    assert restored.weights == matrix.weights
    assert restored.probabilities(RegimeName.CORRELATION_BREAKDOWN) == matrix.probabilities(
        RegimeName.CORRELATION_BREAKDOWN
    )


def test_invalid_regime_name_fails_closed():
    matrix = RegimeTransitionMatrix()

    with pytest.raises(ValueError):
        matrix.update("not_a_regime", RegimeName.UNKNOWN)
