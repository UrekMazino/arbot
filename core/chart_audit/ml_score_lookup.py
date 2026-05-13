"""Stored Advanced ML score lookup for point-in-time chart replay."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core.chart_audit.marker_types import BlockReason
from core.chart_audit.ml_replay_types import MLScoreSource, ReplayMLScoreSnapshot


ADVANCED_ML_EVENT_TYPES = {
    "advanced_ml_regime_shadow",
    "advanced_ml_regime_live",
    "advanced_ml_exit_shadow",
    "advanced_ml_exit_live",
    "advanced_ml_learning_update",
    "advanced_ml_rollout_guard",
    "trade_quality_gate",
}


@dataclass(frozen=True)
class _NormalizedScoreEvent:
    timestamp: int
    event_type: str
    payload: Mapping[str, Any]
    fields: Mapping[str, Any]
    block_reasons: tuple[BlockReason, ...]


class StoredMLScoreLookup:
    """Point-in-time lookup over already-stored Advanced ML events."""

    def __init__(self, pair: str, stored_events: Iterable[Any] | None = None) -> None:
        self.pair = _normalize_pair_key(pair)
        self._events = tuple(_iter_records(stored_events or ()))

    def get_stored_score_at(self, pair: str, timestamp: int | float | datetime | str) -> ReplayMLScoreSnapshot | None:
        if not _same_pair(pair, self.pair):
            return None
        return get_stored_score_at(self.pair, timestamp, stored_events=self._events)

    def get_score_source_for_range(
        self,
        pair: str,
        start_ts: int | float | datetime | str | None,
        end_ts: int | float | datetime | str | None,
    ) -> tuple[ReplayMLScoreSnapshot, ...]:
        if not _same_pair(pair, self.pair):
            return ()
        return get_score_source_for_range(self.pair, start_ts, end_ts, stored_events=self._events)


def get_stored_score_at(
    pair: str,
    timestamp: int | float | datetime | str,
    *,
    stored_events: Iterable[Any] | None = None,
) -> ReplayMLScoreSnapshot | None:
    """Return the latest stored score known at or before ``timestamp``.

    This function never reads live runtime state. Callers must pass stored
    database/file records if they want a score; otherwise the result is missing.
    """

    target_timestamp = _coerce_timestamp(timestamp)
    if target_timestamp is None:
        raise ValueError("get_stored_score_at requires a valid timestamp")
    normalized_pair = _normalize_pair_key(pair)
    candidates = [
        event
        for event in _normalized_score_events(normalized_pair, stored_events or ())
        if event.timestamp <= int(target_timestamp)
    ]
    if not candidates:
        return None

    candidates.sort(key=lambda event: event.timestamp)
    merged: dict[str, Any] = {}
    block_reasons: list[BlockReason] = []
    event_types: list[str] = []
    for event in candidates:
        event_types.append(event.event_type)
        for key, value in event.fields.items():
            if value is not None:
                merged[key] = value
        block_reasons.extend(event.block_reasons)

    latest_timestamp = candidates[-1].timestamp
    return ReplayMLScoreSnapshot(
        pair=normalized_pair,
        timestamp=latest_timestamp,
        score_source=MLScoreSource.STORED_LIVE,
        hard_validation_valid=merged.get("hard_validation_valid"),
        regime_name=merged.get("regime_name"),
        regime_confidence=merged.get("regime_confidence"),
        break_risk=merged.get("break_risk"),
        bayesian_posterior=merged.get("bayesian_posterior"),
        bayesian_quality_grade=merged.get("bayesian_quality_grade"),
        final_rank_score=merged.get("final_rank_score"),
        microstructure_risk=merged.get("microstructure_risk"),
        liquidity_score=merged.get("liquidity_score"),
        ev_hold_value_usdt=merged.get("ev_hold_value_usdt"),
        exit_score=merged.get("exit_score"),
        quality_gate_passed=merged.get("quality_gate_passed"),
        block_reasons=_unique_block_reasons(block_reasons),
        metadata={
            "requested_timestamp": int(target_timestamp),
            "source_event_count": len(candidates),
            "source_event_types": tuple(event_types),
        },
    )


def get_score_source_for_range(
    pair: str,
    start_ts: int | float | datetime | str | None,
    end_ts: int | float | datetime | str | None,
    *,
    stored_events: Iterable[Any] | None = None,
) -> tuple[ReplayMLScoreSnapshot, ...]:
    """Return normalized stored score rows in a range, using stored events only."""

    start_value = _coerce_timestamp(start_ts)
    end_value = _coerce_timestamp(end_ts)
    normalized_pair = _normalize_pair_key(pair)
    rows: list[ReplayMLScoreSnapshot] = []
    for event in _normalized_score_events(normalized_pair, stored_events or ()):
        if start_value is not None and event.timestamp < int(start_value):
            continue
        if end_value is not None and event.timestamp > int(end_value):
            continue
        rows.append(
            ReplayMLScoreSnapshot(
                pair=normalized_pair,
                timestamp=event.timestamp,
                score_source=MLScoreSource.STORED_LIVE,
                hard_validation_valid=event.fields.get("hard_validation_valid"),
                regime_name=event.fields.get("regime_name"),
                regime_confidence=event.fields.get("regime_confidence"),
                break_risk=event.fields.get("break_risk"),
                bayesian_posterior=event.fields.get("bayesian_posterior"),
                bayesian_quality_grade=event.fields.get("bayesian_quality_grade"),
                final_rank_score=event.fields.get("final_rank_score"),
                microstructure_risk=event.fields.get("microstructure_risk"),
                liquidity_score=event.fields.get("liquidity_score"),
                ev_hold_value_usdt=event.fields.get("ev_hold_value_usdt"),
                exit_score=event.fields.get("exit_score"),
                quality_gate_passed=event.fields.get("quality_gate_passed"),
                block_reasons=event.block_reasons,
                metadata={"source_event_type": event.event_type},
            )
        )
    return tuple(sorted(rows, key=lambda row: int(row.timestamp or 0)))


def _normalized_score_events(pair: str, records: Iterable[Any]) -> tuple[_NormalizedScoreEvent, ...]:
    events: list[_NormalizedScoreEvent] = []
    for record in _iter_records(records):
        event = _normalize_score_event(record, pair)
        if event is not None:
            events.append(event)
    return tuple(sorted(events, key=lambda event: event.timestamp))


def _normalize_score_event(record: Any, pair: str) -> _NormalizedScoreEvent | None:
    event_type = _normalize_text(_get_any(record, "event_type", "type", "action"))
    payload = _record_payload(record)
    if event_type is None:
        event_type = _normalize_text(_get_any(payload, "event_type", "type", "action"))
    if event_type not in ADVANCED_ML_EVENT_TYPES:
        return None

    record_pair = _record_pair_key(record, payload)
    if record_pair and not _same_pair(record_pair, pair):
        return None

    timestamp = _coerce_timestamp(
        _get_any(record, "timestamp", "ts", "event_timestamp", "created_at", "updated_at")
        or _get_any(payload, "timestamp", "ts", "event_timestamp", "created_at", "updated_at")
    )
    if timestamp is None:
        return None

    fields = _score_fields_from_payload(event_type, payload)
    block_reasons = _block_reasons_from_payload(payload)
    if not fields and not block_reasons:
        return None
    return _NormalizedScoreEvent(
        timestamp=int(timestamp),
        event_type=event_type,
        payload=payload,
        fields=fields,
        block_reasons=block_reasons,
    )


def _score_fields_from_payload(event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    fields["hard_validation_valid"] = _optional_bool(
        _first_extracted(
            payload,
            ("hard_validation_valid",),
            ("hard_valid",),
            ("hard_validation", "is_valid"),
            ("hard_validation", "passed"),
        )
    )
    hard_reasons = _sequence_value(_first_extracted(payload, ("hard_reasons",), ("hard_validation", "reasons")))
    if fields["hard_validation_valid"] is None and hard_reasons is not None:
        fields["hard_validation_valid"] = len(hard_reasons) == 0

    if event_type == "trade_quality_gate":
        fields["quality_gate_passed"] = _optional_bool(
            _first_extracted(payload, ("quality_gate_passed",), ("passed",), ("allow",))
        )
    else:
        fields["quality_gate_passed"] = _optional_bool(
            _first_extracted(payload, ("quality_gate_passed",), ("quality_gate", "passed"))
        )

    fields["regime_name"] = _normalize_text(
        _first_extracted(
            payload,
            ("regime_name",),
            ("advanced_regime",),
            ("regime",),
            ("regime_result", "regime"),
        )
    )
    fields["regime_confidence"] = _optional_float(
        _first_extracted(payload, ("regime_confidence",), ("confidence",), ("regime_result", "confidence"))
    )
    fields["break_risk"] = _optional_float(
        _first_extracted(payload, ("break_risk",), ("regime_break_score",), ("regime_result", "break_risk"))
    )
    fields["bayesian_posterior"] = _optional_float(
        _first_extracted(
            payload,
            ("bayesian_posterior",),
            ("advanced_bayes_probability",),
            ("posterior_good_probability",),
            ("bayesian", "posterior_good_probability"),
            ("bayesian", "posterior"),
        )
    )
    fields["bayesian_quality_grade"] = _normalize_text(
        _first_extracted(
            payload,
            ("bayesian_quality_grade",),
            ("quality_grade",),
            ("bayesian", "quality_grade"),
        )
    )
    fields["final_rank_score"] = _optional_float(
        _first_extracted(
            payload,
            ("final_rank_score",),
            ("final_score",),
            ("rank_score",),
            ("linucb_score",),
            ("bandit", "final_rank_score"),
        )
    )
    fields["microstructure_risk"] = _microstructure_risk(payload)
    fields["liquidity_score"] = _liquidity_score(payload)
    fields["ev_hold_value_usdt"] = _optional_float(
        _first_extracted(payload, ("ev_hold_value_usdt",), ("expected_hold_value_usdt",), ("ev", "expected_hold_value_usdt"))
    )
    fields["exit_score"] = _optional_float(
        _first_extracted(payload, ("exit_score",), ("total_exit_score",), ("scores", "total_exit_score"))
    )
    return {key: value for key, value in fields.items() if value is not None}


def _microstructure_risk(payload: Mapping[str, Any]) -> float | None:
    explicit = _optional_float(
        _first_extracted(
            payload,
            ("microstructure_risk",),
            ("book_stress_score",),
            ("book_stress",),
            ("microstructure", "book_stress_score"),
        )
    )
    slippage = _optional_float(
        _first_extracted(payload, ("slippage_risk_score",), ("slippage_risk",), ("microstructure", "slippage_risk_score"))
    )
    liquidity_risk = _optional_float(_first_extracted(payload, ("liquidity_risk_score",),))
    values = [value for value in (explicit, slippage, liquidity_risk) if value is not None]
    return max(values) if values else None


def _liquidity_score(payload: Mapping[str, Any]) -> float | None:
    explicit = _optional_float(_first_extracted(payload, ("liquidity_score",), ("microstructure", "liquidity_score")))
    if explicit is not None:
        return explicit
    risk = _optional_float(_first_extracted(payload, ("liquidity_risk_score",),))
    if risk is None:
        return None
    return max(0.0, min(1.0, 1.0 - risk))


def _block_reasons_from_payload(payload: Mapping[str, Any]) -> tuple[BlockReason, ...]:
    raw_values: list[Any] = []
    for path in (
        ("block_reasons",),
        ("hard_reasons",),
        ("reasons",),
        ("rollout_reasons",),
        ("rollout", "reasons"),
    ):
        value = _first_extracted(payload, path)
        if value is None:
            continue
        raw_values.extend(_as_list(value))
    rollout_reason = _first_extracted(payload, ("rollout_reason",))
    if isinstance(rollout_reason, str):
        raw_values.extend(item for item in rollout_reason.split("|") if item)

    reasons: list[BlockReason] = []
    for raw in raw_values:
        reason = _block_reason_from_value(raw)
        if reason is not None:
            reasons.append(reason)
    return _unique_block_reasons(reasons)


def _block_reason_from_value(value: Any) -> BlockReason | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    normalized = text.replace("-", "_").replace(" ", "_")
    try:
        return BlockReason(normalized)
    except ValueError:
        pass
    if "break" in normalized or "regime" in normalized:
        return BlockReason.REGIME_BREAK_RISK_HIGH
    if "liquidity" in normalized or "slippage" in normalized or "depth" in normalized:
        return BlockReason.LIQUIDITY_FAILED
    if "book" in normalized or "stale" in normalized:
        return BlockReason.ORDERBOOK_STALE
    if "quality" in normalized or "score" in normalized or "gate" in normalized:
        return BlockReason.QUALITY_GATE_FAILED
    if "cointegration" in normalized or "coint" in normalized:
        return BlockReason.COINTEGRATION_INVALID
    if "zero" in normalized:
        return BlockReason.ZERO_CROSSINGS_TOO_LOW
    if "hedge" in normalized and "drift" in normalized:
        return BlockReason.HEDGE_RATIO_DRIFT
    if "hedge" in normalized:
        return BlockReason.HEDGE_RATIO_INVALID
    if "insufficient" in normalized:
        return BlockReason.INSUFFICIENT_HISTORY
    return None


def _record_payload(record: Any) -> Mapping[str, Any]:
    for key in ("payload_json", "payload", "metadata", "data"):
        value = _get_any(record, key)
        payload = _mapping_payload(value)
        if payload:
            return payload
    if isinstance(record, Mapping):
        nested = _mapping_payload(record.get("payload_json") or record.get("payload"))
        if nested:
            return nested
        return record
    return {}


def _mapping_payload(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, Mapping) else {}
    return {}


def _record_pair_key(record: Any, payload: Mapping[str, Any]) -> str | None:
    pair_value = (
        _get_any(record, "pair_key", "pair")
        or _get_any(payload, "pair_key", "pair")
        or _pair_from_symbols(payload)
    )
    if pair_value is None:
        return None
    return _normalize_pair_key(pair_value)


def _pair_from_symbols(payload: Mapping[str, Any]) -> str | None:
    left = payload.get("sym_1") or payload.get("ticker_1") or payload.get("long_ticker")
    right = payload.get("sym_2") or payload.get("ticker_2") or payload.get("short_ticker")
    if left and right:
        return f"{left}/{right}"
    return None


def _same_pair(left: str, right: str) -> bool:
    left_symbols = _split_pair_key(_normalize_pair_key(left))
    right_symbols = _split_pair_key(_normalize_pair_key(right))
    if left_symbols is None or right_symbols is None:
        return _normalize_pair_key(left) == _normalize_pair_key(right)
    return set(left_symbols) == set(right_symbols)


def _split_pair_key(pair_key: str) -> tuple[str, str] | None:
    if "/" not in pair_key:
        return None
    left, right = pair_key.split("/", 1)
    left = left.strip()
    right = right.strip()
    if not left or not right:
        return None
    return left, right


def _normalize_pair_key(pair: Any) -> str:
    if isinstance(pair, (tuple, list)) and len(pair) >= 2:
        return f"{str(pair[0]).strip()}/{str(pair[1]).strip()}"
    text = str(pair or "").strip()
    if "__" in text:
        left, right = text.split("__", 1)
        return f"{left.strip()}/{right.strip()}"
    if "/" in text:
        left, right = text.split("/", 1)
        return f"{left.strip()}/{right.strip()}"
    return text


def _get_any(record: Any, *keys: str) -> Any:
    for key in keys:
        if isinstance(record, Mapping) and key in record:
            return record[key]
        if not isinstance(record, Mapping) and hasattr(record, key):
            return getattr(record, key)
    return None


def _first_extracted(source: Any, *paths: tuple[str, ...]) -> Any:
    for path in paths:
        value = _extract_value(source, path)
        if value is not None:
            return value
    return None


def _extract_value(source: Any, path: tuple[str, ...]) -> Any:
    current = source
    for key in path:
        if current is None:
            return None
        if isinstance(current, Mapping):
            current = current.get(key)
        elif hasattr(current, key):
            current = getattr(current, key)
        else:
            return None
    return current


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return list(value)
    return [value]


def _sequence_value(value: Any) -> list[Any] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return list(value)
    return [value]


def _unique_block_reasons(reasons: Iterable[BlockReason]) -> tuple[BlockReason, ...]:
    seen: set[BlockReason] = set()
    output: list[BlockReason] = []
    for reason in reasons:
        if reason in seen:
            continue
        seen.add(reason)
        output.append(reason)
    return tuple(output)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "n", "off", "disabled"}:
        return False
    return None


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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
        if not math.isfinite(parsed):
            return None
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
    if not math.isfinite(parsed):
        return None
    if parsed > 10_000_000_000:
        parsed /= 1000.0
    return parsed


def _iter_records(value: Iterable[Any]) -> Iterable[Any]:
    if isinstance(value, (str, bytes, bytearray, Mapping)):
        return ()
    return value


__all__ = [
    "ADVANCED_ML_EVENT_TYPES",
    "StoredMLScoreLookup",
    "get_score_source_for_range",
    "get_stored_score_at",
]
