from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from core.chart_audit.marker_types import CuratorState
from core.chart_audit.replay_snapshot import (
    ReplayConfigSnapshot,
    ReplaySnapshot,
    candle_timestamp,
    validate_snapshot_timestamp_matches_last_candle,
)


def _config(source: str = "historical") -> ReplayConfigSnapshot:
    return ReplayConfigSnapshot(
        config_version="test-v1",
        config_source=source,
        entry_z_threshold=2.0,
        exit_z_threshold=0.35,
        persistence_candles=4,
        max_hold_seconds=3600.0,
        min_zero_crossings=3,
        min_liquidity_score=0.7,
        max_orderbook_age_ms=1500.0,
        max_spread_bps=12.0,
        max_slippage_bps=18.0,
    )


def _snapshot(**overrides: object) -> ReplaySnapshot:
    payload = {
        "pair": "AAA-USDT-SWAP/BBB-USDT-SWAP",
        "timeframe": "1m",
        "timestamp": 1_715_000_120,
        "candles_until_t": (
            {"timestamp": 1_715_000_000, "close": 10.0},
            {"timestamp": 1_715_000_060, "close": 10.1},
            {"timestamp": 1_715_000_120, "close": 10.2},
        ),
        "zscore_until_t": (0.0, -1.2, -2.1),
        "spread_until_t": (-4.2, -4.3, -4.4),
        "rolling_mean_until_t": -4.25,
        "rolling_std_until_t": 0.12,
        "hedge_ratio_until_t": 0.8,
        "cointegration_result_until_t": {"p_value": 0.01, "lags": [1, 2]},
        "zero_crossing_count_until_t": 4,
        "curator_state": CuratorState.TRADABLE,
        "curator_state_source": "historical",
        "pair_health_state": "stable",
        "orderbook_snapshot": None,
        "config_snapshot": _config(),
        "config_source": "historical",
        "actual_events_at_t": ({"event_type": "entry_reject"},),
    }
    payload.update(overrides)
    return ReplaySnapshot(**payload)  # type: ignore[arg-type]


def test_replay_snapshot_contains_only_candles_until_t() -> None:
    candles = [{"timestamp": 1_715_000_000 + idx * 60, "close": 10.0 + idx} for idx in range(101)]

    snapshot = _snapshot(
        timestamp=candles[50]["timestamp"],
        candles_until_t=tuple(candles[:51]),
        zscore_until_t=tuple(float(idx) for idx in range(51)),
        spread_until_t=tuple(float(-idx) for idx in range(51)),
        actual_events_at_t=(),
    )

    assert len(snapshot.candles_until_t) == 51
    assert snapshot.candles_until_t[-1] == candles[50]
    assert all(candle_timestamp(candle) <= snapshot.timestamp for candle in snapshot.candles_until_t)
    assert candles[51] not in snapshot.candles_until_t


def test_replay_snapshot_uses_tuple_fields_and_is_frozen() -> None:
    snapshot = _snapshot(
        candles_until_t=[
            {"timestamp": 1_715_000_000},
            {"timestamp": 1_715_000_060},
            {"timestamp": 1_715_000_120},
        ],
        zscore_until_t=[0.0, 1.0, 2.0],
        spread_until_t=[-1.0, -2.0, -3.0],
        actual_events_at_t=[{"event_type": "trade_open"}],
    )

    assert isinstance(snapshot.candles_until_t, tuple)
    assert isinstance(snapshot.zscore_until_t, tuple)
    assert isinstance(snapshot.spread_until_t, tuple)
    assert isinstance(snapshot.actual_events_at_t, tuple)
    assert isinstance(snapshot.cointegration_result_until_t["lags"], tuple)
    with pytest.raises(FrozenInstanceError):
        snapshot.timestamp = 1  # type: ignore[misc]


def test_replay_snapshot_rejects_timestamp_that_does_not_match_last_candle() -> None:
    with pytest.raises(ValueError, match="must match the last candle timestamp"):
        _snapshot(timestamp=1_715_000_060)


def test_replay_snapshot_rejects_future_candle_even_if_last_candle_matches_timestamp() -> None:
    with pytest.raises(ValueError, match="cannot contain candles after timestamp"):
        _snapshot(
            timestamp=1_715_000_120,
            candles_until_t=(
                {"timestamp": 1_715_000_000},
                {"timestamp": 1_715_000_180},
                {"timestamp": 1_715_000_120},
            ),
        )


def test_validate_snapshot_timestamp_matches_last_candle_accepts_valid_snapshot() -> None:
    snapshot = _snapshot()

    validate_snapshot_timestamp_matches_last_candle(snapshot)


def test_replay_config_snapshot_uses_replay_relevant_fields_only() -> None:
    field_names = {item.name for item in fields(ReplayConfigSnapshot)}

    assert field_names == {
        "config_version",
        "config_source",
        "entry_z_threshold",
        "exit_z_threshold",
        "persistence_candles",
        "max_hold_seconds",
        "min_zero_crossings",
        "min_liquidity_score",
        "max_orderbook_age_ms",
        "max_spread_bps",
        "max_slippage_bps",
        "warning",
    }


def test_current_approximate_config_snapshot_gets_warning() -> None:
    config = _config(source="current_approximate")

    assert config.warning == "Historical config unavailable; current config used for replay."


def test_replay_snapshot_config_source_must_match_config_snapshot() -> None:
    with pytest.raises(ValueError, match="config_source must match"):
        _snapshot(config_source="current_approximate", config_snapshot=_config("historical"))
