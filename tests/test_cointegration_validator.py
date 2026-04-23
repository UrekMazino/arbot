from __future__ import annotations

from shared_cointegration_validator import (
    count_mean_reversion_crossings,
    count_spread_zero_crossings,
    mean_reversion_crossing_indices,
    spread_zero_crossing_indices,
)


def test_zero_crossings_count_slow_cross_through_neutral_band():
    spread = [1.0, 0.4, 0.05, -0.05, -0.4, -1.0]

    assert count_spread_zero_crossings(spread, threshold=0.25) == 1


def test_zero_crossings_do_not_count_neutral_noise():
    spread = [1.0, 0.2, -0.1, 0.1, -0.2, 0.9]

    assert count_spread_zero_crossings(spread, threshold=0.25) == 0


def test_zero_crossings_count_multiple_direction_changes():
    spread = [1.0, 0.0, -1.0, -0.2, 0.8, 0.1, -0.9]

    assert count_spread_zero_crossings(spread, threshold=0.25) == 3
    assert spread_zero_crossing_indices(spread, threshold=0.25) == [2, 4, 6]


def test_mean_reversion_crossings_use_spread_mean_not_literal_zero():
    spread = [10.8, 10.3, 9.7, 9.2, 10.4, 10.9, 9.6]

    assert count_spread_zero_crossings(spread, threshold=0.25) == 0
    assert count_mean_reversion_crossings(spread, threshold=0.25) == 3
    assert mean_reversion_crossing_indices(spread, threshold=0.25) == [2, 4, 6]
