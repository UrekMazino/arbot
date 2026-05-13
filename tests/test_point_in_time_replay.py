from __future__ import annotations

import pytest

from core.chart_audit.marker_types import BlockReason, CuratorState, MarkerCategory, ReplayMarkerStatus, ReplayMarkerType
from core.chart_audit.point_in_time_indicators import STATUS_VALID_CANDIDATE
from core.chart_audit.point_in_time_replay import (
    BUY_SPREAD,
    SELL_SPREAD,
    PointInTimeReplayEngine,
    ReplayPositionState,
    generate_replay_markers,
)
from core.chart_audit.replay_snapshot import FrozenCointegrationResult, ReplayConfigSnapshot, ReplaySnapshot


BASE_TS = 1_715_000_000


def _config(
    *,
    persistence_candles: int = 2,
    exit_z_threshold: float = 0.35,
    max_hold_seconds: float = 180.0,
    target_gross_pair_notional_usdt: float | None = None,
) -> ReplayConfigSnapshot:
    return ReplayConfigSnapshot(
        config_version="test",
        config_source="historical",
        entry_z_threshold=2.0,
        exit_z_threshold=exit_z_threshold,
        persistence_candles=persistence_candles,
        max_hold_seconds=max_hold_seconds,
        min_zero_crossings=2,
        min_liquidity_score=0.2,
        max_orderbook_age_ms=1_000.0,
        max_spread_bps=5.0,
        max_slippage_bps=8.0,
        min_cointegration_window=1,
        target_gross_pair_notional_usdt=target_gross_pair_notional_usdt,
    )


def _snapshot(
    zscores: list[float],
    *,
    start_ts: int = BASE_TS,
    config: ReplayConfigSnapshot | None = None,
    curator_state: CuratorState = CuratorState.TRADABLE,
    curator_state_source: str = "historical",
    zero_crossings: int | None = 3,
    coint_flag: int | None = 1,
    hedge_ratio: float | None = 1.0,
    orderbook_snapshot: dict[str, float] | None = None,
) -> ReplaySnapshot:
    timestamp = start_ts + (len(zscores) - 1) * 60
    spreads = tuple(float(idx) for idx in range(len(zscores)))
    if orderbook_snapshot is None:
        orderbook_snapshot = {
            "book_freshness_ms": 500.0,
            "spread_bps": 2.0,
            "slippage_bps": 3.0,
            "liquidity_score": 0.8,
        }
    coint_result = (
        FrozenCointegrationResult(
            p_value=0.01,
            adf_stat=-3.0,
            hedge_ratio=hedge_ratio,
            zero_crossings=zero_crossings,
            is_valid=coint_flag in {None, 1},
            reasons=() if coint_flag in {None, 1} else ("cointegration_invalid",),
        )
        if coint_flag is not None
        else None
    )
    return ReplaySnapshot(
        pair="AAA-USDT-SWAP/BBB-USDT-SWAP",
        timeframe="1m",
        timestamp=timestamp,
        candles_until_t=tuple(
            {"timestamp": start_ts + idx * 60, "spread": spread}
            for idx, spread in enumerate(spreads)
        ),
        zscore_until_t=tuple(zscores),
        spread_until_t=spreads,
        rolling_mean_until_t=None,
        rolling_std_until_t=None,
        hedge_ratio_until_t=hedge_ratio,
        cointegration_result_until_t=coint_result,
        zero_crossing_count_until_t=zero_crossings,
        curator_state=curator_state,
        curator_state_source=curator_state_source,
        pair_health_state="stable",
        orderbook_snapshot=orderbook_snapshot,
        config_snapshot=config or _config(),
        config_source=(config or _config()).config_source,
        actual_events_at_t=(),
    )


def test_buy_spread_entry_candidate_when_threshold_and_gates_pass() -> None:
    engine = PointInTimeReplayEngine()

    markers = engine.evaluate(_snapshot([-2.1, -2.2]))

    assert len(markers) == 1
    marker = markers[0]
    assert marker.marker_category == MarkerCategory.REPLAY
    assert marker.marker_type == ReplayMarkerType.REPLAY_ENTRY_CANDIDATE
    assert marker.status == ReplayMarkerStatus.VALID_CANDIDATE
    assert marker.passed is True
    assert marker.side == BUY_SPREAD
    assert marker.entry_id == "replay_AAA-USDT-SWAP/BBB-USDT-SWAP_1715000060_BUY_SPREAD"
    assert engine.position_state == ReplayPositionState.OPEN_BUY_SPREAD


def test_replay_engine_evaluate_requires_replay_snapshot() -> None:
    with pytest.raises(TypeError, match="requires a ReplaySnapshot"):
        PointInTimeReplayEngine().evaluate({"zscore_until_t": [-2.2]})  # type: ignore[arg-type]


def test_sell_spread_entry_candidate_when_threshold_and_gates_pass() -> None:
    markers = PointInTimeReplayEngine().evaluate(_snapshot([2.1, 2.2]))

    assert len(markers) == 1
    assert markers[0].marker_type == ReplayMarkerType.REPLAY_ENTRY_CANDIDATE
    assert markers[0].side == SELL_SPREAD
    assert markers[0].position_state == ReplayPositionState.OPEN_SELL_SPREAD


def test_threshold_reached_but_curator_gate_fails_emits_blocked_signal() -> None:
    markers = PointInTimeReplayEngine().evaluate(
        _snapshot([-2.1, -2.2], curator_state=CuratorState.HOSPITAL)
    )

    assert len(markers) == 1
    marker = markers[0]
    assert marker.marker_type == ReplayMarkerType.REPLAY_BLOCKED_SIGNAL
    assert marker.status == ReplayMarkerStatus.BLOCKED_CANDIDATE
    assert marker.passed is False
    assert BlockReason.PAIR_IN_HOSPITAL in marker.block_reasons


def test_threshold_reached_but_persistence_fails_emits_blocked_signal() -> None:
    markers = PointInTimeReplayEngine().evaluate(
        _snapshot([-1.0, -2.2], config=_config(persistence_candles=2))
    )

    assert len(markers) == 1
    marker = markers[0]
    assert marker.marker_type == ReplayMarkerType.REPLAY_BLOCKED_SIGNAL
    assert marker.status == ReplayMarkerStatus.BLOCKED_CANDIDATE
    assert BlockReason.Z_PERSISTENCE_FAILED in marker.block_reasons


def test_threshold_reached_but_insufficient_replay_data_is_marked() -> None:
    markers = PointInTimeReplayEngine().evaluate(
        _snapshot(
            [-2.2],
            config=_config(persistence_candles=1),
            curator_state=CuratorState.INSUFFICIENT_HISTORY,
            curator_state_source="unavailable",
            zero_crossings=None,
        )
    )

    assert len(markers) == 1
    marker = markers[0]
    assert marker.marker_type == ReplayMarkerType.REPLAY_BLOCKED_SIGNAL
    assert marker.status == ReplayMarkerStatus.INSUFFICIENT_DATA
    assert BlockReason.INSUFFICIENT_HISTORY in marker.block_reasons
    assert BlockReason.CURATOR_STATE_UNAVAILABLE in marker.block_reasons


def test_open_position_exits_when_z_reverts_to_exit_threshold() -> None:
    engine = PointInTimeReplayEngine()
    engine.evaluate(_snapshot([-2.1, -2.2]))

    markers = engine.evaluate(_snapshot([-2.1, -2.2, -0.2]))

    assert len(markers) == 1
    marker = markers[0]
    assert marker.marker_type == ReplayMarkerType.REPLAY_EXIT_CANDIDATE
    assert marker.status == ReplayMarkerStatus.VALID_CANDIDATE
    assert marker.passed is True
    assert marker.position_state == ReplayPositionState.CLOSED
    assert marker.reason == "z_reverted_to_exit_threshold"
    assert marker.exit_trigger == "z_reversion"
    assert engine.position_state == ReplayPositionState.CLOSED


def test_open_position_exits_when_max_hold_reached() -> None:
    engine = PointInTimeReplayEngine()
    config = _config(max_hold_seconds=60.0)
    engine.evaluate(_snapshot([-2.1, -2.2], config=config))

    markers = engine.evaluate(_snapshot([-2.1, -2.2, -1.8], config=config))

    assert len(markers) == 1
    marker = markers[0]
    assert marker.marker_type == ReplayMarkerType.REPLAY_EXIT_CANDIDATE
    assert marker.reason == "max_hold_reached"
    assert marker.exit_trigger == "max_hold"
    assert marker.hold_seconds == 60.0


def test_open_position_exits_when_curator_no_longer_tradable() -> None:
    engine = PointInTimeReplayEngine()
    engine.evaluate(_snapshot([-2.1, -2.2]))

    markers = engine.evaluate(
        _snapshot([-2.1, -2.2, -1.8], curator_state=CuratorState.GRAVEYARD)
    )

    assert len(markers) == 1
    marker = markers[0]
    assert marker.marker_type == ReplayMarkerType.REPLAY_EXIT_CANDIDATE
    assert marker.reason == "curator_state_no_longer_tradable"
    assert marker.exit_trigger == "curator_state_non_tradable"
    assert BlockReason.PAIR_IN_GRAVEYARD in marker.block_reasons


def test_open_position_blocks_new_entry_signal_until_exit() -> None:
    engine = PointInTimeReplayEngine()
    engine.evaluate(_snapshot([-2.1, -2.2]))

    markers = engine.evaluate(_snapshot([-2.1, -2.2, -2.4]))

    assert len(markers) == 1
    marker = markers[0]
    assert marker.marker_type == ReplayMarkerType.REPLAY_BLOCKED_SIGNAL
    assert BlockReason.POSITION_ALREADY_OPEN in marker.block_reasons


def test_generate_replay_markers_is_deterministic_for_same_snapshots() -> None:
    snapshots = [
        _snapshot([-2.1, -2.2]),
        _snapshot([-2.1, -2.2, -0.2]),
        _snapshot([2.1, 2.2, 2.3, 2.4]),
    ]

    first = [marker.to_dict() for marker in generate_replay_markers(snapshots)]
    second = [marker.to_dict() for marker in generate_replay_markers(snapshots)]

    assert first == second


def test_replay_marker_to_dict_serializes_status_enum() -> None:
    marker = PointInTimeReplayEngine().evaluate(_snapshot([-2.1, -2.2]))[0]

    assert marker.status == ReplayMarkerStatus.VALID_CANDIDATE
    assert marker.to_dict()["status"] == STATUS_VALID_CANDIDATE.value


def test_valid_entry_is_not_emitted_when_hedge_ratio_or_cointegration_unavailable() -> None:
    marker = PointInTimeReplayEngine().evaluate(
        _snapshot([-2.1, -2.2], coint_flag=None)
    )[0]

    assert marker.marker_type == ReplayMarkerType.REPLAY_BLOCKED_SIGNAL
    assert marker.status == ReplayMarkerStatus.INSUFFICIENT_DATA
    assert BlockReason.INSUFFICIENT_HISTORY in marker.block_reasons


def test_replay_exit_candidate_to_dict_has_v1_4_schema_fields() -> None:
    engine = PointInTimeReplayEngine()
    engine.evaluate(_snapshot([-2.1, -2.2]))

    marker = engine.evaluate(_snapshot([-2.1, -2.2, -0.2]))[0].to_dict()

    assert marker["marker_type"] == ReplayMarkerType.REPLAY_EXIT_CANDIDATE.value
    assert marker["entry_id"]
    assert marker["timestamp"] == BASE_TS + 120
    assert marker["side"] == BUY_SPREAD
    assert marker["z_score"] == -0.2
    assert marker["spread"] == 2.0
    assert marker["status"] == ReplayMarkerStatus.VALID_CANDIDATE.value
    assert marker["reason"] == "z_reverted_to_exit_threshold"
    assert marker["exit_trigger"] == "z_reversion"
    assert isinstance(marker["metadata"], dict)


def test_replay_marker_includes_hedge_ratio_sizing_metadata() -> None:
    marker = PointInTimeReplayEngine().evaluate(
        _snapshot(
            [-2.1, -2.2],
            config=_config(
                target_gross_pair_notional_usdt=1500.0,
                persistence_candles=2,
            ),
        )
    )[0]

    assert marker.marker_type == ReplayMarkerType.REPLAY_ENTRY_CANDIDATE
    assert marker.metadata["hedge_ratio_at_t"] == 1.0
    assert marker.metadata["hedge_ratio_source"] == "fresh_cointegration_at_entry"
    assert marker.metadata["replay_sizing_mode"] == "equal_notional"
    assert marker.metadata["target_gross_pair_notional_usdt"] == 1500.0
    assert marker.metadata["target_leg1_notional_usdt"] == 750.0
    assert marker.metadata["target_leg2_notional_usdt"] == 750.0
    assert marker.metadata["hedge_ratio_valid"] is True
    assert marker.metadata["hedge_ratio_sizing_enabled"] is False


def test_open_replay_position_can_exit_on_hedge_ratio_drift() -> None:
    engine = PointInTimeReplayEngine()
    config = _config(persistence_candles=2)
    engine.evaluate(_snapshot([-2.1, -2.2], config=config, hedge_ratio=1.8))

    marker = engine.evaluate(_snapshot([-2.1, -2.2, -1.8], config=config, hedge_ratio=1.2))[0]

    assert marker.marker_type == ReplayMarkerType.REPLAY_EXIT_CANDIDATE
    assert marker.exit_trigger == "hedge_ratio_drift"
    assert marker.metadata["hedge_ratio_drift_pct"] == pytest.approx(abs(1.2 - 1.8) / 1.8)
