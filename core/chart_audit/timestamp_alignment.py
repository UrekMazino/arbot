"""Timestamp alignment helpers for actual chart audit markers.

Actual bot events may occur between candle bucket timestamps. This module keeps
the real event time intact while returning marker copies whose display
timestamp matches the chart capability.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from core.chart_audit.marker_types import ActualMarker


TIMESTAMP_ALIGNMENT_EXACT = "exact"
TIMESTAMP_ALIGNMENT_SNAPPED_TO_NEAREST_CANDLE = "snapped_to_nearest_candle"


def align_actual_marker_timestamp(
    marker: ActualMarker,
    *,
    chart_supports_exact_timestamp: bool,
    candle_timestamps: Iterable[int | float | datetime | str] | None = None,
) -> ActualMarker:
    """Return a marker copy with timestamp aligned for the chart renderer."""

    original_event_timestamp = (
        marker.original_event_timestamp
        if marker.original_event_timestamp is not None
        else marker.timestamp
    )
    original_event_timestamp_value = _coerce_timestamp(original_event_timestamp)
    if original_event_timestamp_value is None:
        raise ValueError("actual marker timestamp alignment requires a valid event timestamp")

    if chart_supports_exact_timestamp:
        return _replace_marker_timestamp(
            marker,
            timestamp=original_event_timestamp,
            original_event_timestamp=original_event_timestamp,
            timestamp_alignment=TIMESTAMP_ALIGNMENT_EXACT,
        )

    nearest_candle_timestamp = _nearest_candle_timestamp(
        original_event_timestamp_value,
        candle_timestamps,
    )
    return _replace_marker_timestamp(
        marker,
        timestamp=nearest_candle_timestamp,
        original_event_timestamp=original_event_timestamp,
        timestamp_alignment=TIMESTAMP_ALIGNMENT_SNAPPED_TO_NEAREST_CANDLE,
    )


def align_actual_marker_timestamps(
    markers: Iterable[ActualMarker],
    *,
    chart_supports_exact_timestamp: bool,
    candle_timestamps: Iterable[int | float | datetime | str] | None = None,
) -> list[ActualMarker]:
    """Return marker copies with timestamps aligned consistently."""

    candle_timestamp_values = list(candle_timestamps or [])
    return [
        align_actual_marker_timestamp(
            marker,
            chart_supports_exact_timestamp=chart_supports_exact_timestamp,
            candle_timestamps=candle_timestamp_values,
        )
        for marker in markers
    ]


def _replace_marker_timestamp(
    marker: ActualMarker,
    *,
    timestamp: int | float | datetime | str,
    original_event_timestamp: int | float | datetime | str,
    timestamp_alignment: str,
) -> ActualMarker:
    metadata = _metadata_with_alignment(marker.metadata, timestamp_alignment)
    return replace(
        marker,
        timestamp=timestamp,
        original_event_timestamp=original_event_timestamp,
        timestamp_alignment=timestamp_alignment,
        metadata=metadata,
    )


def _metadata_with_alignment(metadata: Mapping[str, Any], timestamp_alignment: str) -> dict[str, Any]:
    updated = dict(metadata)
    updated["timestamp_alignment"] = timestamp_alignment
    return updated


def _nearest_candle_timestamp(
    event_timestamp: float,
    candle_timestamps: Iterable[int | float | datetime | str] | None,
) -> int | float:
    candidates: list[tuple[float, int | float]] = []
    for candle_timestamp in candle_timestamps or []:
        value = _coerce_timestamp(candle_timestamp)
        if value is None:
            continue
        candidates.append((value, _timestamp_output_value(candle_timestamp, value)))

    if not candidates:
        raise ValueError("snapped timestamp alignment requires at least one valid candle timestamp")

    return min(
        candidates,
        key=lambda item: (
            abs(item[0] - event_timestamp),
            item[0] > event_timestamp,
            item[0],
        ),
    )[1]


def _timestamp_output_value(original_value: Any, coerced_value: float) -> int | float:
    if isinstance(original_value, int) and not isinstance(original_value, bool):
        return original_value
    if isinstance(original_value, float):
        return original_value
    return coerced_value


def _coerce_timestamp(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt_value = value
        if dt_value.tzinfo is None:
            dt_value = dt_value.replace(tzinfo=timezone.utc)
        return float(dt_value.timestamp())
    if isinstance(value, (int, float)):
        parsed = float(value)
        if parsed > 10_000_000_000:
            parsed /= 1000.0
        return parsed
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        try:
            parsed_dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return _coerce_timestamp(parsed_dt)
    if parsed > 10_000_000_000:
        parsed /= 1000.0
    return parsed


__all__ = [
    "TIMESTAMP_ALIGNMENT_EXACT",
    "TIMESTAMP_ALIGNMENT_SNAPPED_TO_NEAREST_CANDLE",
    "align_actual_marker_timestamp",
    "align_actual_marker_timestamps",
]
