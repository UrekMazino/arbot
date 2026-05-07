from __future__ import annotations

import pytest

from core.chart_audit.marker_types import (
    ActualBlockedSignalMarker,
    ActualEntryMarker,
    ActualMarkerType,
    BlockReason,
    MarkerCategory,
    ReplayMarkerType,
    StatisticalMarkerType,
    build_actual_entry_id,
    build_replay_entry_id,
)


def test_actual_entry_id_uses_trade_id_contract() -> None:
    assert build_actual_entry_id("trade-123") == "actual_trade-123"


def test_replay_entry_id_uses_pair_timestamp_side_contract() -> None:
    assert (
        build_replay_entry_id("AAA-USDT-SWAP/BBB-USDT-SWAP", 1_715_000_000, "BUY_SPREAD")
        == "replay_AAA-USDT-SWAP/BBB-USDT-SWAP_1715000000_BUY_SPREAD"
    )


def test_entry_id_builders_reject_missing_required_parts() -> None:
    with pytest.raises(ValueError):
        build_actual_entry_id("")
    with pytest.raises(ValueError):
        build_replay_entry_id("", 1_715_000_000, "BUY_SPREAD")
    with pytest.raises(ValueError):
        build_replay_entry_id("AAA/BBB", "", "BUY_SPREAD")
    with pytest.raises(ValueError):
        build_replay_entry_id("AAA/BBB", 1_715_000_000, "")


def test_actual_entry_marker_defaults_to_actual_category_and_entry_id() -> None:
    marker = ActualEntryMarker(timestamp=1_715_000_000, trade_id="trade-abc")

    assert marker.marker_category == MarkerCategory.ACTUAL
    assert marker.marker_type == ActualMarkerType.ACTUAL_ENTRY
    assert marker.entry_id == "actual_trade-abc"
    assert marker.timestamp_alignment == "exact"


def test_actual_marker_to_dict_serializes_enum_and_tuple_values() -> None:
    marker = ActualBlockedSignalMarker(
        timestamp=1_715_000_000,
        reason="stale orderbook",
        block_reasons=(BlockReason.ORDERBOOK_STALE, BlockReason.LIQUIDITY_FAILED),
    )

    payload = marker.to_dict()

    assert payload["marker_category"] == "actual"
    assert payload["marker_type"] == "actual_blocked_signal"
    assert payload["block_reasons"] == ["orderbook_stale", "liquidity_failed"]


def test_marker_contract_enums_include_phase_1_categories() -> None:
    assert StatisticalMarkerType.HISTORICAL_MEAN_CROSSING.value == "historical_mean_crossing"
    assert ReplayMarkerType.REPLAY_ENTRY_CANDIDATE.value == "replay_entry_candidate"
    assert ActualMarkerType.ACTUAL_BLOCKED_SIGNAL.value == "actual_blocked_signal"
