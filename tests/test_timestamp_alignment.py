from __future__ import annotations

from core.chart_audit.marker_types import ActualEntryMarker, ActualExitMarker
from core.chart_audit.timestamp_alignment import (
    TIMESTAMP_ALIGNMENT_EXACT,
    TIMESTAMP_ALIGNMENT_SNAPPED_TO_NEAREST_CANDLE,
    align_actual_marker_timestamp,
)


def test_exact_timestamp_mode_preserves_exact_event_timestamp() -> None:
    marker = ActualEntryMarker(
        timestamp=1_715_000_023.527,
        original_event_timestamp=1_715_000_023.527,
        trade_id="trade-exact",
        metadata={"source": "event"},
    )

    aligned = align_actual_marker_timestamp(
        marker,
        chart_supports_exact_timestamp=True,
    )

    assert aligned.timestamp == 1_715_000_023.527
    assert aligned.original_event_timestamp == 1_715_000_023.527
    assert aligned.timestamp_alignment == TIMESTAMP_ALIGNMENT_EXACT
    assert aligned.metadata["timestamp_alignment"] == TIMESTAMP_ALIGNMENT_EXACT


def test_snapped_timestamp_mode_uses_nearest_candle_timestamp() -> None:
    marker = ActualEntryMarker(
        timestamp=1_715_000_023.527,
        original_event_timestamp=1_715_000_023.527,
        trade_id="trade-snapped",
    )

    aligned = align_actual_marker_timestamp(
        marker,
        chart_supports_exact_timestamp=False,
        candle_timestamps=[
            1_715_000_000,
            1_715_000_060,
            1_715_000_120,
        ],
    )

    assert aligned.timestamp == 1_715_000_000
    assert aligned.original_event_timestamp == 1_715_000_023.527
    assert aligned.timestamp_alignment == TIMESTAMP_ALIGNMENT_SNAPPED_TO_NEAREST_CANDLE
    assert aligned.metadata["timestamp_alignment"] == TIMESTAMP_ALIGNMENT_SNAPPED_TO_NEAREST_CANDLE


def test_original_event_timestamp_is_never_lost() -> None:
    marker = ActualExitMarker(
        timestamp=1_715_000_060,
        original_event_timestamp=None,
        trade_id="trade-no-original",
    )

    aligned = align_actual_marker_timestamp(
        marker,
        chart_supports_exact_timestamp=False,
        candle_timestamps=[
            1_715_000_000,
            1_715_000_060,
            1_715_000_120,
        ],
    )

    assert aligned.timestamp == 1_715_000_060
    assert aligned.original_event_timestamp == 1_715_000_060
    assert aligned.timestamp_alignment == TIMESTAMP_ALIGNMENT_SNAPPED_TO_NEAREST_CANDLE
