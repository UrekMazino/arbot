from __future__ import annotations

import pytest

from core.chart_audit.curator_state_source import CuratorStateAtResult
from core.chart_audit.marker_types import CuratorState
from core.chart_audit.replay_snapshot import ReplayConfigSnapshot, ReplaySnapshot
from core.chart_audit.replay_snapshot_factory import ReplaySnapshotFactory, build_replay_snapshots


BASE_TS = 1_715_000_000


def _config() -> ReplayConfigSnapshot:
    return ReplayConfigSnapshot(
        config_version="test",
        config_source="historical",
        entry_z_threshold=2.0,
        exit_z_threshold=0.35,
        persistence_candles=1,
        max_hold_seconds=3600.0,
        min_zero_crossings=0,
        min_liquidity_score=0.2,
        max_orderbook_age_ms=1000.0,
        max_spread_bps=5.0,
        max_slippage_bps=8.0,
    )


def _candles(spreads: list[float]) -> list[dict[str, float]]:
    return [
        {"timestamp": BASE_TS + idx * 60, "spread": spread}
        for idx, spread in enumerate(spreads)
    ]


def _curator(timestamp: int) -> CuratorStateAtResult:
    return CuratorStateAtResult(
        curator_state=CuratorState.TRADABLE,
        curator_state_source="historical",
        transition_timestamp=timestamp,
    )


def test_factory_builds_one_prefix_snapshot_per_candle_and_calls_sources() -> None:
    candles = _candles([1.0, 2.0, 3.0])
    curator_calls: list[int] = []
    config_calls: list[int] = []

    def curator_provider(timestamp: int) -> CuratorStateAtResult:
        curator_calls.append(timestamp)
        return _curator(timestamp)

    def config_provider(timestamp: int) -> ReplayConfigSnapshot:
        config_calls.append(timestamp)
        return _config()

    snapshots = list(
        ReplaySnapshotFactory(
            pair="AAA/BBB",
            timeframe="1m",
            candles=candles,
            curator_state_at=curator_provider,
            config_at=config_provider,
        ).iter_snapshots()
    )

    assert [snapshot.timestamp for snapshot in snapshots] == [candle["timestamp"] for candle in candles]
    assert [len(snapshot.candles_until_t) for snapshot in snapshots] == [1, 2, 3]
    assert snapshots[1].candles_until_t == tuple(candles[:2])
    assert isinstance(snapshots[2].candles_until_t, tuple)
    assert isinstance(snapshots[2].zscore_until_t, tuple)
    assert isinstance(snapshots[2].spread_until_t, tuple)
    assert isinstance(snapshots[2].actual_events_at_t, tuple)
    assert curator_calls == [candle["timestamp"] for candle in candles]
    assert config_calls == [candle["timestamp"] for candle in candles]


def test_factory_recomputes_indicators_from_prefix_so_future_candles_do_not_change_t() -> None:
    prefix_candles = _candles([1.0, 2.0, 3.0])
    full_candles = prefix_candles + _candles([100.0])[0:1]
    full_candles[-1] = {"timestamp": BASE_TS + 3 * 60, "spread": 100.0}

    prefix_snapshot = build_replay_snapshots(
        "AAA/BBB",
        "1m",
        prefix_candles,
        curator_state_at=_curator,
        config_at=lambda _timestamp: _config(),
    )[2]
    full_snapshot = build_replay_snapshots(
        "AAA/BBB",
        "1m",
        full_candles,
        curator_state_at=_curator,
        config_at=lambda _timestamp: _config(),
    )[2]

    assert prefix_snapshot.timestamp == full_snapshot.timestamp == BASE_TS + 2 * 60
    assert prefix_snapshot.candles_until_t == full_snapshot.candles_until_t
    assert prefix_snapshot.zscore_until_t == full_snapshot.zscore_until_t
    assert prefix_snapshot.spread_until_t == full_snapshot.spread_until_t
    assert prefix_snapshot.rolling_mean_until_t == full_snapshot.rolling_mean_until_t
    assert prefix_snapshot.rolling_std_until_t == full_snapshot.rolling_std_until_t
    assert prefix_snapshot.zero_crossing_count_until_t == full_snapshot.zero_crossing_count_until_t
    assert full_candles[3] not in full_snapshot.candles_until_t


def test_factory_attaches_orderbook_and_actual_events_at_timestamp() -> None:
    candles = _candles([1.0, 2.0, 3.0])
    orderbooks = {
        BASE_TS: {"timestamp": BASE_TS, "spread_bps": 1.5},
        BASE_TS + 120: {"timestamp": BASE_TS + 120, "spread_bps": 2.5},
        BASE_TS + 10_000: {"timestamp": BASE_TS + 10_000, "spread_bps": 99.0},
    }
    event = {"timestamp": BASE_TS + 60, "event_type": "trade_open", "trade_id": "T1"}

    snapshots = build_replay_snapshots(
        "AAA/BBB",
        "1m",
        candles,
        curator_state_at=_curator,
        config_at=lambda _timestamp: _config(),
        orderbook_snapshots=orderbooks,
        actual_events={BASE_TS + 60: [event]},
    )

    assert snapshots[1].orderbook_snapshot == orderbooks[BASE_TS]
    assert snapshots[1].actual_events_at_t == (event,)
    assert snapshots[2].orderbook_snapshot == orderbooks[BASE_TS + 120]
    assert snapshots[2].actual_events_at_t == ()


def test_replay_loop_passes_each_snapshot_to_engine_without_future_candles() -> None:
    candles = _candles([-2.1, -2.2, -0.2])
    seen_lengths: list[int] = []

    class SpyEngine:
        def evaluate(self, snapshot: ReplaySnapshot) -> list[dict[str, int]]:
            seen_lengths.append(len(snapshot.candles_until_t))
            return [{"timestamp": snapshot.timestamp}]

    markers = ReplaySnapshotFactory(
        pair="AAA/BBB",
        timeframe="1m",
        candles=candles,
        curator_state_at=_curator,
        config_at=lambda _timestamp: _config(),
    ).replay(engine=SpyEngine())

    assert seen_lengths == [1, 2, 3]
    assert markers == [{"timestamp": BASE_TS}, {"timestamp": BASE_TS + 60}, {"timestamp": BASE_TS + 120}]


def test_factory_rejects_non_sequential_candles_that_would_put_future_data_in_snapshot() -> None:
    candles = [
        {"timestamp": BASE_TS + 60, "spread": 2.0},
        {"timestamp": BASE_TS, "spread": 1.0},
    ]

    with pytest.raises(ValueError, match="cannot contain candles after timestamp"):
        build_replay_snapshots(
            "AAA/BBB",
            "1m",
            candles,
            curator_state_at=_curator,
            config_at=lambda _timestamp: _config(),
        )
