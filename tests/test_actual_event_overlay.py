from __future__ import annotations

import json

from core.chart_audit.actual_event_overlay import (
    actual_marker_from_event,
    actual_markers_from_events,
    actual_markers_from_trade_rows,
)
from core.chart_audit.marker_types import (
    ActualBlockedSignalMarker,
    ActualEntryMarker,
    ActualManualExitMarker,
    ActualMarkerType,
    ActualPartialExitMarker,
    ActualAdvancedMLShadowRecommendationMarker,
    BlockReason,
)


def test_actual_events_map_to_actual_markers_only_from_logged_events() -> None:
    events = [
        {
            "event_type": "trade_open",
            "event_id": "evt-entry",
            "timestamp": "2026-05-07T01:00:00+00:00",
            "payload": {
                "trade_id": "trade-1",
                "pair": "AAA-USDT-SWAP/BBB-USDT-SWAP",
                "side": "buy_spread",
                "z_score": -2.1,
                "reason": "entry_signal_confirmed",
            },
        },
        {
            "event_type": "entry_reject",
            "event_id": "evt-block",
            "timestamp": "2026-05-07T01:01:00+00:00",
            "payload": {
                "pair": "AAA-USDT-SWAP/BBB-USDT-SWAP",
                "side": "sell_spread",
                "z_score": 2.3,
                "block_reasons": ["stale orderbook", "order capacity failed"],
                "reason": "liquidity depth too low",
            },
        },
        {
            "event_type": "advanced_ml_exit_shadow",
            "event_id": "evt-shadow",
            "timestamp": "2026-05-07T01:02:00+00:00",
            "payload": {
                "trade_id": "trade-1",
                "pair": "AAA-USDT-SWAP/BBB-USDT-SWAP",
                "new_action": "exit",
                "executed": True,
                "total_exit_score": 0.82,
            },
        },
    ]

    markers = actual_markers_from_events(events, pair="AAA-USDT-SWAP/BBB-USDT-SWAP")

    assert [marker.marker_type for marker in markers] == [
        ActualMarkerType.ACTUAL_ENTRY,
        ActualMarkerType.ACTUAL_BLOCKED_SIGNAL,
        ActualMarkerType.ACTUAL_ADVANCED_ML_SHADOW_RECOMMENDATION,
    ]
    entry = markers[0]
    assert isinstance(entry, ActualEntryMarker)
    assert entry.entry_id == "actual_trade-1"

    blocked = markers[1]
    assert isinstance(blocked, ActualBlockedSignalMarker)
    assert BlockReason.ORDERBOOK_STALE in blocked.block_reasons
    assert BlockReason.ORDER_CAPACITY_FAILED in blocked.block_reasons

    shadow = markers[2]
    assert isinstance(shadow, ActualAdvancedMLShadowRecommendationMarker)
    assert shadow.shadow_action == "exit"
    assert shadow.executed is False


def test_actual_marker_does_not_infer_side_from_z_score() -> None:
    marker = actual_marker_from_event(
        {
            "event_type": "trade_open",
            "timestamp": 1_777_777_777,
            "payload": {
                "trade_id": "z-only",
                "z_score": 2.5,
            },
        }
    )

    assert isinstance(marker, ActualEntryMarker)
    assert marker.side is None


def test_payload_json_db_row_is_supported() -> None:
    marker = actual_marker_from_event(
        {
            "event_type": "trade_open",
            "event_id": "evt-json",
            "timestamp": 1_777_777_777,
            "pair_key": "AAA-USDT-SWAP/BBB-USDT-SWAP",
            "payload_json": json.dumps(
                {
                    "trade_id": "json-trade",
                    "side": "long_spread",
                    "reason": "db_event_entry",
                }
            ),
        },
        pair="AAA-USDT-SWAP/BBB-USDT-SWAP",
    )

    assert isinstance(marker, ActualEntryMarker)
    assert marker.entry_id == "actual_json-trade"
    assert marker.side == "BUY_SPREAD"


def test_partial_exit_event_maps_to_actual_partial_exit_marker() -> None:
    marker = actual_marker_from_event(
        {
            "event_type": "trade_partial_exit",
            "event_id": "evt-partial",
            "timestamp": 1_777_777_800,
            "payload": {
                "trade_id": "trade-partial",
                "pair": "AAA-USDT-SWAP/BBB-USDT-SWAP",
                "side": "sell_spread",
                "exit_z": 0.42,
                "exit_percentage": 50,
                "pnl_usdt": 0.75,
                "reason": "reduce risk",
            },
        },
        pair="AAA-USDT-SWAP/BBB-USDT-SWAP",
    )

    assert isinstance(marker, ActualPartialExitMarker)
    assert marker.marker_type == ActualMarkerType.ACTUAL_PARTIAL_EXIT
    assert marker.trade_id == "trade-partial"
    assert marker.exit_percentage == 50
    assert marker.pnl_usdt == 0.75


def test_trade_rows_emit_actual_entry_and_exit_markers() -> None:
    markers = actual_markers_from_trade_rows(
        [
            {
                "id": "row-1",
                "pair_key": "AAA-USDT-SWAP/BBB-USDT-SWAP",
                "entry_ts": 1_777_777_700,
                "exit_ts": 1_777_777_760,
                "side": "sell",
                "entry_z": 2.05,
                "exit_z": 0.12,
                "exit_reason": "manual dashboard close",
                "pnl_usdt": 1.25,
            }
        ],
        pair="AAA-USDT-SWAP/BBB-USDT-SWAP",
    )

    assert len(markers) == 2
    assert isinstance(markers[0], ActualEntryMarker)
    assert markers[0].entry_id == "actual_row-1"
    assert isinstance(markers[1], ActualManualExitMarker)
    assert markers[1].side == "SELL_SPREAD"
    assert markers[1].pnl_usdt == 1.25


def test_actual_entry_marker_attaches_hedge_ratio_sizing_metadata() -> None:
    marker = actual_marker_from_event(
        {
            "event_type": "trade_open",
            "event_id": "evt-hedge",
            "timestamp": 1_777_777_777,
            "payload": {
                "trade_id": "hedge-trade",
                "pair": "AAA-USDT-SWAP/BBB-USDT-SWAP",
                "side": "buy_spread",
                "entry_hedge_ratio": 1.8,
                "hedge_ratio_source": "fresh_cointegration_at_entry",
                "hedge_sizing_mode": "gross_normalized_beta",
                "hedge_ratio_sizing_enabled": True,
                "target_gross_pair_notional_usdt": 1500.0,
                "actual_leg1_notional_usdt": 534.9,
                "actual_leg2_notional_usdt": 963.8,
            },
        }
    )

    assert isinstance(marker, ActualEntryMarker)
    assert marker.metadata["entry_hedge_ratio"] == 1.8
    assert marker.metadata["hedge_ratio_source"] == "fresh_cointegration_at_entry"
    assert marker.metadata["hedge_sizing_mode"] == "gross_normalized_beta"
    assert marker.metadata["hedge_ratio_sizing_enabled"] is True
    assert marker.metadata["target_gross_pair_notional_usdt"] == 1500.0
    assert marker.metadata["target_leg1_notional_usdt"] > 0
    assert marker.metadata["target_leg2_notional_usdt"] > 0
    assert marker.metadata["actual_leg1_notional_usdt"] == 534.9
    assert marker.metadata["actual_leg2_notional_usdt"] == 963.8
    assert marker.metadata["hedge_sizing_error_pct"] >= 0
    assert marker.metadata["hedge_ratio_execution_error_pct"] >= 0
    assert marker.metadata["leg1_side"] == "long"
    assert marker.metadata["leg2_side"] == "short"
