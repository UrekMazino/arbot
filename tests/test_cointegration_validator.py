from __future__ import annotations

from shared_cointegration_validator import count_spread_zero_crossings


def test_zero_crossings_count_slow_cross_through_neutral_band():
    spread = [1.0, 0.4, 0.05, -0.05, -0.4, -1.0]

    assert count_spread_zero_crossings(spread, threshold=0.25) == 1


def test_zero_crossings_do_not_count_neutral_noise():
    spread = [1.0, 0.2, -0.1, 0.1, -0.2, 0.9]

    assert count_spread_zero_crossings(spread, threshold=0.25) == 0


def test_zero_crossings_count_multiple_direction_changes():
    spread = [1.0, 0.0, -1.0, -0.2, 0.8, 0.1, -0.9]

    assert count_spread_zero_crossings(spread, threshold=0.25) == 3
