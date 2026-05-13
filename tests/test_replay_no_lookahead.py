from __future__ import annotations

from core.chart_audit.curator_state_source import CuratorStateAtResult
from core.chart_audit.marker_types import CuratorState
from core.chart_audit.replay_snapshot import ReplayConfigSnapshot
from core.chart_audit.replay_snapshot_factory import ReplaySnapshotFactory, build_replay_snapshots


BASE_TS = 1_715_000_000
PAIR = "AAA-USDT-SWAP/BBB-USDT-SWAP"


def _config(_timestamp: int) -> ReplayConfigSnapshot:
    return ReplayConfigSnapshot(
        config_version="test",
        config_source="historical",
        entry_z_threshold=2.0,
        exit_z_threshold=0.35,
        persistence_candles=1,
        max_hold_seconds=3600.0,
        min_zero_crossings=0,
    )


def _curator(timestamp: int) -> CuratorStateAtResult:
    return CuratorStateAtResult(
        curator_state=CuratorState.TRADABLE,
        curator_state_source="historical",
        transition_timestamp=timestamp,
    )


def _candles(spreads: list[float]) -> list[dict[str, float]]:
    return [
        {"timestamp": BASE_TS + idx * 60, "spread": spread}
        for idx, spread in enumerate(spreads)
    ]


def _replay_payloads_until(candles: list[dict[str, float]], timestamp: int) -> list[dict[str, object]]:
    markers = ReplaySnapshotFactory(
        pair=PAIR,
        timeframe="1m",
        candles=candles,
        curator_state_at=_curator,
        config_at=_config,
    ).replay()
    return [marker.to_dict() for marker in markers if int(marker.timestamp) <= timestamp]


def test_replay_result_at_t_does_not_change_when_future_candles_are_added() -> None:
    prefix_candles = _candles([0.0, 0.0, 0.0, 0.0, 0.0, -10.0])
    future_candles = prefix_candles + [
        {"timestamp": BASE_TS + 6 * 60, "spread": 25.0},
        {"timestamp": BASE_TS + 7 * 60, "spread": -50.0},
        {"timestamp": BASE_TS + 8 * 60, "spread": 75.0},
    ]
    replay_timestamp = prefix_candles[-1]["timestamp"]

    prefix_result = _replay_payloads_until(prefix_candles, replay_timestamp)
    future_result = _replay_payloads_until(future_candles, replay_timestamp)

    assert prefix_result
    assert prefix_result == future_result


def test_snapshot_at_t_contains_same_prefix_after_future_candles_are_added() -> None:
    prefix_candles = _candles([0.0, 0.0, 0.0, 0.0, 0.0, -10.0])
    future_candles = prefix_candles + [
        {"timestamp": BASE_TS + 6 * 60, "spread": 25.0},
        {"timestamp": BASE_TS + 7 * 60, "spread": -50.0},
    ]
    snapshot_index = len(prefix_candles) - 1

    prefix_snapshot = build_replay_snapshots(
        PAIR,
        "1m",
        prefix_candles,
        curator_state_at=_curator,
        config_at=_config,
    )[snapshot_index]
    future_snapshot = build_replay_snapshots(
        PAIR,
        "1m",
        future_candles,
        curator_state_at=_curator,
        config_at=_config,
    )[snapshot_index]

    assert prefix_snapshot.timestamp == future_snapshot.timestamp == prefix_candles[-1]["timestamp"]
    assert prefix_snapshot.candles_until_t == tuple(prefix_candles)
    assert future_snapshot.candles_until_t == tuple(prefix_candles)
    assert prefix_snapshot.zscore_until_t == future_snapshot.zscore_until_t
    assert prefix_snapshot.spread_until_t == future_snapshot.spread_until_t
    assert prefix_snapshot.rolling_mean_until_t == future_snapshot.rolling_mean_until_t
    assert prefix_snapshot.rolling_std_until_t == future_snapshot.rolling_std_until_t
    assert future_candles[-1] not in future_snapshot.candles_until_t
