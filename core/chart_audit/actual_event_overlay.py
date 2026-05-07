"""Actual bot decision overlay adapters.

This module maps real bot events, trade-log dictionaries, or DB-row-like
objects into actual chart markers. It does not infer decisions from chart
z-score paths and does not generate replay or counterfactual markers.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

from core.chart_audit.marker_types import (
    ActualAdvancedMLShadowRecommendationMarker,
    ActualBlockedSignalMarker,
    ActualEntryMarker,
    ActualExitMarker,
    ActualManualExitMarker,
    ActualMarker,
    ActualPartialExitMarker,
    ActualRegimeExitMarker,
    BlockReason,
)


EVENT_TYPE_TRADE_OPEN = "trade_open"
EVENT_TYPE_TRADE_CLOSE = "trade_close"
EVENT_TYPE_ENTRY_REJECT = "entry_reject"
EVENT_TYPE_GATE_ENFORCED = "gate_enforced"
EVENT_TYPE_TRADE_QUALITY_GATE = "trade_quality_gate"
EVENT_TYPE_ADVANCED_ML_EXIT_SHADOW = "advanced_ml_exit_shadow"


def actual_markers_from_events(
    events: Iterable[Any],
    *,
    pair: str | None = None,
    start_ts: int | float | datetime | str | None = None,
    end_ts: int | float | datetime | str | None = None,
) -> list[ActualMarker]:
    """Convert real event dictionaries/objects into actual markers."""

    start_value = _coerce_timestamp(start_ts)
    end_value = _coerce_timestamp(end_ts)
    markers: list[ActualMarker] = []
    for event in events:
        marker = actual_marker_from_event(event, pair=pair)
        if marker is None or not _timestamp_in_range(marker.timestamp, start_value, end_value):
            continue
        markers.append(marker)
    return sorted(markers, key=lambda marker: (float(marker.timestamp), str(marker.marker_type.value)))


def actual_marker_from_event(event: Any, *, pair: str | None = None) -> ActualMarker | None:
    payload = _payload(event)
    event_type = _event_type(event) or _event_type(payload)
    timestamp = _event_timestamp(event, payload)
    if timestamp is None:
        return None

    original_timestamp = _coerce_timestamp(
        _get_any(payload, "original_event_timestamp", "event_timestamp", "ts")
    )
    if original_timestamp is None:
        original_timestamp = timestamp

    if pair is not None and not _event_matches_pair(event, payload, pair):
        return None

    if event_type == EVENT_TYPE_TRADE_OPEN:
        return _actual_entry_marker(event, payload, timestamp, original_timestamp)
    if event_type == EVENT_TYPE_TRADE_CLOSE:
        return _actual_exit_marker(event, payload, timestamp, original_timestamp)
    if event_type in {
        EVENT_TYPE_ENTRY_REJECT,
        EVENT_TYPE_GATE_ENFORCED,
        EVENT_TYPE_TRADE_QUALITY_GATE,
    }:
        return _actual_blocked_marker(event, payload, timestamp, original_timestamp)
    if event_type in {"partial_exit", "trade_partial_exit"}:
        return _actual_partial_exit_marker(event, payload, timestamp, original_timestamp)
    if event_type in {"manual_exit", "trade_manual_exit"}:
        return _actual_manual_exit_marker(event, payload, timestamp, original_timestamp)
    if event_type == EVENT_TYPE_ADVANCED_ML_EXIT_SHADOW:
        return _actual_advanced_ml_shadow_marker(event, payload, timestamp, original_timestamp)
    return None


def actual_markers_from_trade_rows(
    trades: Iterable[Any],
    *,
    pair: str | None = None,
    start_ts: int | float | datetime | str | None = None,
    end_ts: int | float | datetime | str | None = None,
    include_entries: bool = True,
    include_exits: bool = True,
) -> list[ActualMarker]:
    """Convert ORM-like trade rows into actual entry/exit markers."""

    start_value = _coerce_timestamp(start_ts)
    end_value = _coerce_timestamp(end_ts)
    markers: list[ActualMarker] = []
    for trade in trades:
        trade_pair = _get_any(trade, "pair_key", "pair")
        if pair is not None and str(trade_pair or "").strip() != str(pair).strip():
            continue
        trade_id = _trade_id(trade)

        entry_ts = _coerce_timestamp(_get_any(trade, "entry_ts", "entry_timestamp"))
        if include_entries and entry_ts is not None and _timestamp_in_range(entry_ts, start_value, end_value):
            markers.append(
                ActualEntryMarker(
                    timestamp=entry_ts,
                    original_event_timestamp=entry_ts,
                    side=_normalize_side(_get_any(trade, "side")),
                    z_score=_coerce_float(_get_any(trade, "entry_z", "z_score")),
                    spread=_coerce_float(_get_any(trade, "entry_spread", "spread")),
                    trade_id=trade_id,
                    reason=_normalize_text(_get_any(trade, "entry_reason")) or "trade_row_entry",
                    metadata=_compact_metadata(
                        {
                            "source": "trade_row",
                            "pair": trade_pair,
                        }
                    ),
                )
            )

        exit_ts = _coerce_timestamp(_get_any(trade, "exit_ts", "exit_timestamp"))
        if include_exits and exit_ts is not None and _timestamp_in_range(exit_ts, start_value, end_value):
            marker_cls = _exit_marker_class(_normalize_text(_get_any(trade, "exit_reason")))
            markers.append(
                marker_cls(
                    timestamp=exit_ts,
                    original_event_timestamp=exit_ts,
                    side=_normalize_side(_get_any(trade, "side")),
                    z_score=_coerce_float(_get_any(trade, "exit_z", "z_score")),
                    spread=_coerce_float(_get_any(trade, "exit_spread", "spread")),
                    trade_id=trade_id,
                    reason=_normalize_text(_get_any(trade, "exit_reason")) or "trade_row_exit",
                    pnl_usdt=_coerce_float(_get_any(trade, "pnl_usdt")),
                    fees_usdt=_coerce_float(_get_any(trade, "fees_usdt", "fee_usdt")),
                    slippage_usdt=_coerce_float(_get_any(trade, "slippage_usdt")),
                    metadata=_compact_metadata(
                        {
                            "source": "trade_row",
                            "pair": trade_pair,
                        }
                    ),
                )
            )
    return sorted(markers, key=lambda marker: (float(marker.timestamp), str(marker.marker_type.value)))


def actual_markers_from_records(
    records: Iterable[Any],
    *,
    pair: str | None = None,
    start_ts: int | float | datetime | str | None = None,
    end_ts: int | float | datetime | str | None = None,
) -> list[ActualMarker]:
    """Convert mixed event/trade-row records into actual markers."""

    event_records: list[Any] = []
    trade_records: list[Any] = []
    for record in records:
        if _event_type(record):
            event_records.append(record)
        elif _get_any(record, "entry_ts", "exit_ts", "entry_timestamp", "exit_timestamp") is not None:
            trade_records.append(record)

    markers = actual_markers_from_events(event_records, pair=pair, start_ts=start_ts, end_ts=end_ts)
    markers.extend(actual_markers_from_trade_rows(trade_records, pair=pair, start_ts=start_ts, end_ts=end_ts))
    return sorted(markers, key=lambda marker: (float(marker.timestamp), str(marker.marker_type.value)))


def normalize_block_reason(reason: Any) -> BlockReason:
    """Map bot/log reason strings into the chart-audit BlockReason enum."""

    if isinstance(reason, BlockReason):
        return reason
    text = str(reason or "").strip().lower()
    text = text.replace("-", "_").replace(" ", "_")
    if not text:
        return BlockReason.QUALITY_GATE_FAILED

    direct = {item.value: item for item in BlockReason}
    if text in direct:
        return direct[text]

    if "hospital" in text:
        return BlockReason.PAIR_IN_HOSPITAL
    if "graveyard" in text:
        return BlockReason.PAIR_IN_GRAVEYARD
    if "analysis_only" in text:
        return BlockReason.ANALYSIS_ONLY
    if "excluded" in text:
        return BlockReason.PAIR_EXCLUDED
    if "curator" in text and "liquidity" in text:
        return BlockReason.CURATOR_LOW_LIQUIDITY
    if "liquidity" in text or "depth" in text:
        return BlockReason.LIQUIDITY_FAILED
    if "capacity" in text or "notional" in text or "capital" in text:
        return BlockReason.ORDER_CAPACITY_FAILED
    if "orderbook" in text and "stale" in text:
        return BlockReason.ORDERBOOK_STALE
    if "stale" in text:
        return BlockReason.STALE_DATA
    if "coint" in text or "cointegration" in text or "p_value" in text:
        return BlockReason.COINTEGRATION_INVALID
    if "adf" in text:
        return BlockReason.ADF_FAILED
    if "zero_cross" in text:
        return BlockReason.ZERO_CROSSINGS_TOO_LOW
    if "hedge" in text:
        return BlockReason.HEDGE_RATIO_UNSTABLE
    if "persist" in text:
        return BlockReason.Z_PERSISTENCE_FAILED
    if "position" in text and ("open" in text or "already" in text):
        return BlockReason.POSITION_ALREADY_OPEN
    if "regime" in text or "break_risk" in text:
        return BlockReason.REGIME_BREAK_RISK_HIGH
    if "config" in text:
        return BlockReason.CONFIG_UNAVAILABLE
    if "history" in text:
        return BlockReason.INSUFFICIENT_HISTORY
    return BlockReason.QUALITY_GATE_FAILED


def _actual_entry_marker(event: Any, payload: Mapping[str, Any], timestamp: float, original_timestamp: float) -> ActualMarker:
    trade_id = _trade_id(payload) or _event_id(event, payload) or str(timestamp)
    z_score = _coerce_float(_get_any(payload, "entry_z", "z_score", "current_z"))
    return ActualEntryMarker(
        timestamp=timestamp,
        original_event_timestamp=original_timestamp,
        side=_normalize_side(_get_any(payload, "side", "spread_side", "signal_side")),
        z_score=z_score,
        spread=_coerce_float(_get_any(payload, "spread", "entry_spread")),
        trade_id=trade_id,
        reason=_normalize_text(_get_any(payload, "reason")) or "trade_open",
        metadata=_event_metadata(event, payload, source="event"),
    )


def _actual_exit_marker(event: Any, payload: Mapping[str, Any], timestamp: float, original_timestamp: float) -> ActualMarker:
    reason = _normalize_text(_get_any(payload, "exit_reason", "reason", "result"))
    marker_cls = _exit_marker_class(reason)
    z_score = _coerce_float(_get_any(payload, "exit_z", "z_score", "current_z"))
    return marker_cls(
        timestamp=timestamp,
        original_event_timestamp=original_timestamp,
        side=_normalize_side(_get_any(payload, "side", "spread_side", "signal_side")),
        z_score=z_score,
        spread=_coerce_float(_get_any(payload, "spread", "exit_spread")),
        trade_id=_trade_id(payload) or _event_id(event, payload),
        reason=reason or "trade_close",
        pnl_usdt=_coerce_float(_get_any(payload, "pnl_usdt")),
        fees_usdt=_coerce_float(_get_any(payload, "fees_usdt", "fee_usdt")),
        slippage_usdt=_coerce_float(_get_any(payload, "slippage_usdt")),
        metadata=_event_metadata(event, payload, source="event"),
    )


def _actual_partial_exit_marker(
    event: Any,
    payload: Mapping[str, Any],
    timestamp: float,
    original_timestamp: float,
) -> ActualMarker:
    z_score = _coerce_float(_get_any(payload, "exit_z", "z_score", "current_z"))
    return ActualPartialExitMarker(
        timestamp=timestamp,
        original_event_timestamp=original_timestamp,
        side=_normalize_side(_get_any(payload, "side", "spread_side", "signal_side")),
        z_score=z_score,
        spread=_coerce_float(_get_any(payload, "spread")),
        trade_id=_trade_id(payload) or _event_id(event, payload),
        reason=_normalize_text(_get_any(payload, "reason", "exit_reason")) or "partial_exit",
        pnl_usdt=_coerce_float(_get_any(payload, "pnl_usdt")),
        fees_usdt=_coerce_float(_get_any(payload, "fees_usdt", "fee_usdt")),
        slippage_usdt=_coerce_float(_get_any(payload, "slippage_usdt")),
        exit_percentage=_coerce_float(_get_any(payload, "exit_percentage", "percentage")),
        metadata=_event_metadata(event, payload, source="event"),
    )


def _actual_manual_exit_marker(
    event: Any,
    payload: Mapping[str, Any],
    timestamp: float,
    original_timestamp: float,
) -> ActualMarker:
    z_score = _coerce_float(_get_any(payload, "exit_z", "z_score", "current_z"))
    return ActualManualExitMarker(
        timestamp=timestamp,
        original_event_timestamp=original_timestamp,
        side=_normalize_side(_get_any(payload, "side", "spread_side", "signal_side")),
        z_score=z_score,
        spread=_coerce_float(_get_any(payload, "spread")),
        trade_id=_trade_id(payload) or _event_id(event, payload),
        reason=_normalize_text(_get_any(payload, "reason", "exit_reason")) or "manual_exit",
        pnl_usdt=_coerce_float(_get_any(payload, "pnl_usdt")),
        fees_usdt=_coerce_float(_get_any(payload, "fees_usdt", "fee_usdt")),
        slippage_usdt=_coerce_float(_get_any(payload, "slippage_usdt")),
        metadata=_event_metadata(event, payload, source="event"),
    )


def _actual_blocked_marker(
    event: Any,
    payload: Mapping[str, Any],
    timestamp: float,
    original_timestamp: float,
) -> ActualMarker | None:
    if _event_type(event) == EVENT_TYPE_TRADE_QUALITY_GATE and _truthy(_get_any(payload, "passed")):
        return None
    z_score = _coerce_float(_get_any(payload, "z_score", "entry_z", "current_z"))
    reasons = _block_reasons(payload)
    return ActualBlockedSignalMarker(
        timestamp=timestamp,
        original_event_timestamp=original_timestamp,
        side=_normalize_side(_get_any(payload, "side", "spread_side", "signal_side")),
        z_score=z_score,
        spread=_coerce_float(_get_any(payload, "spread")),
        trade_id=_trade_id(payload),
        reason=_normalize_text(_get_any(payload, "reason", "reject_type", "gate_type")) or "blocked_signal",
        block_reasons=reasons,
        metadata=_event_metadata(event, payload, source="event"),
    )


def _actual_advanced_ml_shadow_marker(
    event: Any,
    payload: Mapping[str, Any],
    timestamp: float,
    original_timestamp: float,
) -> ActualMarker:
    z_score = _coerce_float(_get_any(payload, "z_score", "current_z"))
    return ActualAdvancedMLShadowRecommendationMarker(
        timestamp=timestamp,
        original_event_timestamp=original_timestamp,
        side=_normalize_side(_get_any(payload, "side", "spread_side", "signal_side")),
        z_score=z_score,
        spread=_coerce_float(_get_any(payload, "spread")),
        trade_id=_trade_id(payload),
        reason=_normalize_text(_get_any(payload, "reason", "rollout_reason")) or "advanced_ml_shadow_recommendation",
        shadow_action=_normalize_text(_get_any(payload, "new_action", "shadow_action", "action")),
        executed=False,
        exit_score=_coerce_float(_get_any(payload, "total_exit_score", "exit_score")),
        ev_hold_value_usdt=_coerce_float(_get_any(payload, "expected_hold_value_usdt", "ev_hold_value_usdt")),
        regime=_normalize_text(_get_any(payload, "regime", "regime_name")),
        metadata=_event_metadata(
            event,
            payload,
            source="event",
            extra={"note": "Shadow mode recommendation only; not executed."},
        ),
    )


def _exit_marker_class(reason: str | None) -> type[ActualExitMarker]:
    reason_text = str(reason or "").strip().lower()
    if "manual" in reason_text:
        return ActualManualExitMarker
    if "regime" in reason_text or "structural_break" in reason_text or "riskoff" in reason_text:
        return ActualRegimeExitMarker
    return ActualExitMarker


def _block_reasons(payload: Mapping[str, Any]) -> tuple[BlockReason, ...]:
    raw_reasons = _get_any(payload, "block_reasons", "reasons", "reason_codes")
    normalized: list[BlockReason] = []
    if isinstance(raw_reasons, str):
        raw_iterable = [part for part in raw_reasons.replace("|", ",").split(",") if part.strip()]
    elif isinstance(raw_reasons, Mapping):
        raw_iterable = list(raw_reasons.values())
    elif isinstance(raw_reasons, Iterable):
        raw_iterable = list(raw_reasons)
    else:
        raw_iterable = []
    for reason in raw_iterable:
        mapped = normalize_block_reason(reason)
        if mapped not in normalized:
            normalized.append(mapped)

    for key in ("reason", "reject_type", "gate_type", "status"):
        value = _get_any(payload, key)
        if value is None:
            continue
        mapped = normalize_block_reason(value)
        if mapped not in normalized:
            normalized.append(mapped)
    return tuple(normalized or [BlockReason.QUALITY_GATE_FAILED])


def _event_matches_pair(event: Any, payload: Mapping[str, Any], pair: str) -> bool:
    pair_value = _normalize_text(
        _get_any(payload, "pair", "pair_key") or _get_any(event, "pair", "pair_key")
    )
    if not pair_value:
        return True
    return pair_value == str(pair).strip()


def _event_metadata(
    event: Any,
    payload: Mapping[str, Any],
    *,
    source: str,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata_value = _get_any(payload, "metadata")
    metadata = dict(metadata_value) if isinstance(metadata_value, Mapping) else {}
    metadata.update(
        _compact_metadata(
            {
                "source": source,
                "event_id": _event_id(event, payload),
                "event_type": _event_type(event) or _event_type(payload),
                "pair": _get_any(payload, "pair", "pair_key") or _get_any(event, "pair", "pair_key"),
                "timestamp_alignment": _get_any(payload, "timestamp_alignment") or "exact",
            }
        )
    )
    if extra:
        metadata.update(_compact_metadata(dict(extra)))
    return metadata


def _payload(event: Any) -> Mapping[str, Any]:
    payload = _get_any(event, "payload", "payload_json")
    if isinstance(payload, Mapping):
        return payload
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, Mapping):
            return parsed
    if isinstance(event, Mapping):
        return event
    return {}


def _event_type(event: Any) -> str:
    return str(_get_any(event, "event_type", "type") or "").strip().lower()


def _event_id(event: Any, payload: Mapping[str, Any] | None = None) -> str | None:
    return _normalize_text(
        _get_any(event, "event_id", "id") or _get_any(payload or {}, "event_id", "id")
    )


def _event_timestamp(event: Any, payload: Mapping[str, Any]) -> float | None:
    return _coerce_timestamp(
        _get_any(event, "ts", "timestamp", "created_at")
        or _get_any(payload, "timestamp", "ts", "entry_ts", "exit_ts")
    )


def _trade_id(record: Any) -> str | None:
    return _normalize_text(_get_any(record, "trade_id", "id", "entry_id"))


def _normalize_side(value: Any) -> str | None:
    text = _normalize_text(value)
    if text:
        normalized = text.upper()
        if normalized in {"BUY", "LONG", "LONG_SPREAD", "BUY_SPREAD", "POSITIVE"}:
            return "BUY_SPREAD"
        if normalized in {"SELL", "SHORT", "SHORT_SPREAD", "SELL_SPREAD", "NEGATIVE"}:
            return "SELL_SPREAD"
        return normalized
    return None


def _get_any(record: Any, *keys: str) -> Any:
    for key in keys:
        if isinstance(record, Mapping) and key in record:
            return record[key]
        if not isinstance(record, Mapping) and hasattr(record, key):
            return getattr(record, key)
    return None


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


def _timestamp_in_range(timestamp: int | float, start_ts: float | None, end_ts: float | None) -> bool:
    value = float(timestamp)
    if start_ts is not None and value < start_ts:
        return False
    if end_ts is not None and value > end_ts:
        return False
    return True


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on", "pass", "passed"}


def _compact_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if value is not None}


__all__ = [
    "actual_marker_from_event",
    "actual_markers_from_events",
    "actual_markers_from_records",
    "actual_markers_from_trade_rows",
    "normalize_block_reason",
]
