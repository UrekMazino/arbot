from __future__ import annotations

import pytest

from core.chart_audit.marker_types import BlockReason, CuratorState
from core.chart_audit.point_in_time_indicators import (
    STATUS_BLOCKED_CANDIDATE,
    STATUS_INSUFFICIENT_DATA,
    STATUS_OK,
    STATUS_VALID_CANDIDATE,
    compute_basic_hard_validation_point_in_time,
    compute_spread_point_in_time,
    compute_zero_crossings_point_in_time,
    compute_zscore_point_in_time,
)
from core.chart_audit.replay_snapshot import ReplayConfigSnapshot, ReplaySnapshot


def _config(min_zero_crossings: int = 3) -> ReplayConfigSnapshot:
    return ReplayConfigSnapshot(
        config_version="test",
        config_source="historical",
        entry_z_threshold=2.0,
        exit_z_threshold=0.35,
        persistence_candles=4,
        max_hold_seconds=21_600.0,
        min_zero_crossings=min_zero_crossings,
        min_liquidity_score=0.2,
        max_orderbook_age_ms=1_000.0,
        max_spread_bps=5.0,
        max_slippage_bps=8.0,
    )


def _candles_from_spreads(spreads: list[float]) -> tuple[dict[str, float], ...]:
    return tuple(
        {"timestamp": 1_715_000_000 + idx * 60, "spread": spread}
        for idx, spread in enumerate(spreads)
    )


def _snapshot(**overrides: object) -> ReplaySnapshot:
    payload = {
        "pair": "AAA-USDT-SWAP/BBB-USDT-SWAP",
        "timeframe": "1m",
        "timestamp": 1_715_000_120,
        "candles_until_t": _candles_from_spreads([1.0, 2.0, 3.0]),
        "zscore_until_t": (0.0, 1.0),
        "spread_until_t": (1.0, 2.0, 3.0),
        "rolling_mean_until_t": 2.0,
        "rolling_std_until_t": 1.0,
        "hedge_ratio_until_t": 1.0,
        "cointegration_result_until_t": {"status": STATUS_OK, "coint_flag": 1},
        "zero_crossing_count_until_t": 3,
        "curator_state": CuratorState.TRADABLE,
        "curator_state_source": "historical",
        "pair_health_state": "stable",
        "orderbook_snapshot": {
            "book_freshness_ms": 500.0,
            "spread_bps": 2.0,
            "slippage_bps": 3.0,
            "liquidity_score": 0.8,
        },
        "config_snapshot": _config(),
        "config_source": "historical",
        "actual_events_at_t": (),
    }
    payload.update(overrides)
    return ReplaySnapshot(**payload)  # type: ignore[arg-type]


def test_compute_zscore_point_in_time_uses_only_candles_until_t() -> None:
    prefix = _candles_from_spreads([1.0, 2.0, 3.0])
    with_future = _candles_from_spreads([1.0, 2.0, 3.0, 100.0])

    prefix_result = compute_zscore_point_in_time(prefix, _config())
    repeated_prefix_result = compute_zscore_point_in_time(with_future[:3], _config())
    full_future_result = compute_zscore_point_in_time(with_future, _config())

    assert prefix_result.status == STATUS_OK
    assert repeated_prefix_result.latest_zscore == pytest.approx(prefix_result.latest_zscore)
    assert prefix_result.latest_zscore == pytest.approx(1.0)
    assert full_future_result.latest_zscore != pytest.approx(prefix_result.latest_zscore)


def test_compute_zscore_point_in_time_returns_insufficient_history() -> None:
    result = compute_zscore_point_in_time(_candles_from_spreads([1.0]), _config())

    assert result.status == STATUS_INSUFFICIENT_DATA
    assert "insufficient" in str(result.reason)


def test_compute_spread_point_in_time_uses_price_pairs_and_computes_hedge_ratio() -> None:
    candles = tuple(
        {
            "timestamp": 1_715_000_000 + idx * 60,
            "close_1": close_1,
            "close_2": close_2,
        }
        for idx, (close_1, close_2) in enumerate(
            [(100.0, 50.0), (101.0, 50.8), (102.0, 51.1), (103.5, 51.7)]
        )
    )

    result = compute_spread_point_in_time(candles, _config())

    assert result.status == STATUS_OK
    assert len(result.spread_until_t) == len(candles)
    assert result.latest_spread == result.spread_until_t[-1]
    assert result.hedge_ratio is not None
    assert result.metadata["spread_source"] == "log_price_ols"


def test_compute_zero_crossings_point_in_time_counts_mean_reversion_crossings() -> None:
    result = compute_zero_crossings_point_in_time([10.8, 10.3, 9.7, 9.2, 10.4, 10.9, 9.6])

    assert result.status == STATUS_OK
    assert result.zero_crossings == 3


def test_basic_hard_validation_passes_clean_point_in_time_snapshot() -> None:
    result = compute_basic_hard_validation_point_in_time(_snapshot())

    assert result.status == STATUS_VALID_CANDIDATE
    assert result.passed is True
    assert result.block_reasons == ()


def test_basic_hard_validation_blocks_curator_and_low_zero_crossings() -> None:
    result = compute_basic_hard_validation_point_in_time(
        _snapshot(
            curator_state=CuratorState.HOSPITAL,
            zero_crossing_count_until_t=1,
        )
    )

    assert result.status == STATUS_BLOCKED_CANDIDATE
    assert result.passed is False
    assert BlockReason.PAIR_IN_HOSPITAL in result.block_reasons
    assert BlockReason.ZERO_CROSSINGS_TOO_LOW in result.block_reasons


def test_basic_hard_validation_marks_insufficient_data_when_curator_unavailable() -> None:
    result = compute_basic_hard_validation_point_in_time(
        _snapshot(
            curator_state=CuratorState.INSUFFICIENT_HISTORY,
            curator_state_source="unavailable",
        )
    )

    assert result.status == STATUS_INSUFFICIENT_DATA
    assert result.passed is False
    assert BlockReason.CURATOR_STATE_UNAVAILABLE in result.block_reasons
    assert BlockReason.INSUFFICIENT_HISTORY in result.block_reasons


def test_basic_hard_validation_blocks_orderbook_liquidity_failures() -> None:
    result = compute_basic_hard_validation_point_in_time(
        _snapshot(
            orderbook_snapshot={
                "book_freshness_ms": 1_500.0,
                "spread_bps": 8.0,
                "slippage_bps": 10.0,
                "liquidity_score": 0.1,
            }
        )
    )

    assert result.status == STATUS_BLOCKED_CANDIDATE
    assert BlockReason.ORDERBOOK_STALE in result.block_reasons
    assert BlockReason.LIQUIDITY_FAILED in result.block_reasons
