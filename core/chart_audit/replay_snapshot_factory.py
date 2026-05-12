"""ReplaySnapshot factory and sequential replay loop.

The factory is the boundary that makes the no-lookahead contract operational:
each yielded ReplaySnapshot contains only candles and indicators available at
that candle timestamp.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TypeAlias

from core.chart_audit.config_snapshot_source import config_at as _default_config_at
from core.chart_audit.curator_state_source import (
    CURATOR_SOURCE_UNAVAILABLE,
    CuratorStateAtResult,
    curator_state_at as _default_curator_state_at,
    normalize_curator_state,
)
from core.chart_audit.marker_types import CuratorState
from core.chart_audit.point_in_time_indicators import (
    compute_zero_crossings_point_in_time,
    compute_zscore_point_in_time,
)
from core.chart_audit.point_in_time_replay import PointInTimeReplayEngine, ReplayMarker
from core.chart_audit.replay_snapshot import ReplayConfigSnapshot, ReplaySnapshot, candle_timestamp


CuratorStateProvider: TypeAlias = Callable[
    [int],
    CuratorStateAtResult | CuratorState | str | Mapping[str, Any] | None,
]
ConfigProvider: TypeAlias = Callable[[int], ReplayConfigSnapshot]
TimestampLookup: TypeAlias = (
    Callable[[int], Any | None]
    | Mapping[Any, Any]
    | Iterable[Any]
    | None
)
ActualEventsSource: TypeAlias = (
    Callable[[int], Iterable[Any] | Any | None]
    | Mapping[Any, Iterable[Any] | Any]
    | Iterable[Any]
    | None
)


@dataclass
class ReplaySnapshotFactory:
    """Build ReplaySnapshot objects one candle at a time."""

    pair: str
    timeframe: str
    candles: Iterable[Any]
    curator_state_at: CuratorStateProvider | None = None
    config_at: ConfigProvider | None = None
    orderbook_snapshots: TimestampLookup = None
    actual_events: ActualEventsSource = None
    pair_health_state_at: TimestampLookup | str = None

    def __post_init__(self) -> None:
        self.candles = tuple(self.candles)
        if (
            self.orderbook_snapshots is not None
            and not callable(self.orderbook_snapshots)
            and not isinstance(self.orderbook_snapshots, Mapping)
        ):
            self.orderbook_snapshots = tuple(_iter_records(self.orderbook_snapshots))
        if (
            self.actual_events is not None
            and not callable(self.actual_events)
            and not isinstance(self.actual_events, Mapping)
        ):
            self.actual_events = tuple(_iter_records(self.actual_events))
        if (
            self.pair_health_state_at is not None
            and not callable(self.pair_health_state_at)
            and not isinstance(self.pair_health_state_at, (Mapping, str))
        ):
            self.pair_health_state_at = tuple(_iter_records(self.pair_health_state_at))

    def iter_snapshots(self) -> Iterator[ReplaySnapshot]:
        """Yield immutable point-in-time snapshots in candle order."""

        candles_until_t: list[Any] = []
        for candle in self.candles:
            timestamp = candle_timestamp(candle)
            if timestamp is None:
                raise ValueError("ReplaySnapshotFactory candle timestamp is missing or invalid")

            candles_until_t.append(candle)
            prefix = tuple(candles_until_t)
            config_snapshot = self._config_at(timestamp)
            zscore_result = compute_zscore_point_in_time(prefix, config_snapshot)
            spread_until_t = tuple(zscore_result.spread_until_t)
            zero_crossings = compute_zero_crossings_point_in_time(spread_until_t)
            curator_result = self._curator_state_at(timestamp)

            yield ReplaySnapshot(
                pair=self.pair,
                timeframe=self.timeframe,
                timestamp=timestamp,
                candles_until_t=prefix,
                zscore_until_t=tuple(zscore_result.zscore_until_t),
                spread_until_t=spread_until_t,
                rolling_mean_until_t=zscore_result.rolling_mean,
                rolling_std_until_t=zscore_result.rolling_std,
                hedge_ratio_until_t=zscore_result.hedge_ratio,
                cointegration_result_until_t=(
                    dict(zscore_result.cointegration_result)
                    if isinstance(zscore_result.cointegration_result, Mapping)
                    else None
                ),
                zero_crossing_count_until_t=(
                    zero_crossings.zero_crossings
                    if zero_crossings.status != "insufficient_data"
                    else None
                ),
                curator_state=curator_result.curator_state,
                curator_state_source=curator_result.curator_state_source,
                pair_health_state=self._pair_health_state_at(timestamp),
                orderbook_snapshot=self._orderbook_at(timestamp),
                config_snapshot=config_snapshot,
                config_source=config_snapshot.config_source,
                actual_events_at_t=tuple(_as_event_tuple(self._actual_events_at(timestamp))),
            )

    def build_snapshots(self) -> tuple[ReplaySnapshot, ...]:
        """Materialize all snapshots for callers that need a reusable tuple."""

        return tuple(self.iter_snapshots())

    def replay(self, engine: PointInTimeReplayEngine | Any | None = None) -> list[ReplayMarker]:
        """Evaluate snapshots sequentially without exposing future candles."""

        replay_engine = engine or PointInTimeReplayEngine()
        markers: list[ReplayMarker] = []
        for snapshot in self.iter_snapshots():
            markers.extend(replay_engine.evaluate(snapshot))
        return markers

    def _curator_state_at(self, timestamp: int) -> CuratorStateAtResult:
        provider = self.curator_state_at
        raw_result = (
            provider(timestamp)
            if provider is not None
            else _default_curator_state_at(self.pair, timestamp)
        )
        return _coerce_curator_result(raw_result)

    def _config_at(self, timestamp: int) -> ReplayConfigSnapshot:
        provider = self.config_at
        return provider(timestamp) if provider is not None else _default_config_at(timestamp)

    def _orderbook_at(self, timestamp: int) -> Any | None:
        return _lookup_latest_at_or_before(self.orderbook_snapshots, timestamp)

    def _actual_events_at(self, timestamp: int) -> tuple[Any, ...]:
        source = self.actual_events
        if source is None:
            return ()
        if callable(source):
            return _as_event_tuple(source(timestamp))
        if isinstance(source, Mapping):
            return _events_from_mapping(source, timestamp)
        return tuple(
            event
            for event in _iter_records(source)
            if _record_timestamp(event) is not None and int(_record_timestamp(event) or 0) == int(timestamp)
        )

    def _pair_health_state_at(self, timestamp: int) -> str | None:
        source = self.pair_health_state_at
        if source is None:
            return None
        if isinstance(source, str):
            return source
        value = _lookup_latest_at_or_before(source, timestamp)
        if value is None:
            return None
        if isinstance(value, Mapping):
            return _normalize_text(_get_any(value, "pair_health_state", "health_state", "state", "status"))
        return _normalize_text(value)


def build_replay_snapshots(
    pair: str,
    timeframe: str,
    candles: Iterable[Any],
    **kwargs: Any,
) -> tuple[ReplaySnapshot, ...]:
    """Convenience wrapper for building ReplaySnapshot tuples."""

    return ReplaySnapshotFactory(
        pair=pair,
        timeframe=timeframe,
        candles=candles,
        **kwargs,
    ).build_snapshots()


def replay_candles(
    pair: str,
    timeframe: str,
    candles: Iterable[Any],
    *,
    engine: PointInTimeReplayEngine | Any | None = None,
    **kwargs: Any,
) -> list[ReplayMarker]:
    """Build snapshots and run the replay engine in one sequential pass."""

    return ReplaySnapshotFactory(
        pair=pair,
        timeframe=timeframe,
        candles=candles,
        **kwargs,
    ).replay(engine=engine)


def _coerce_curator_result(
    value: CuratorStateAtResult | CuratorState | str | Mapping[str, Any] | None,
) -> CuratorStateAtResult:
    if isinstance(value, CuratorStateAtResult):
        return value
    if value is None:
        return CuratorStateAtResult(
            curator_state=CuratorState.INSUFFICIENT_HISTORY,
            curator_state_source=CURATOR_SOURCE_UNAVAILABLE,
            reason="curator_state_at returned no state; insufficient_data.",
        )
    if isinstance(value, Mapping):
        return CuratorStateAtResult(
            curator_state=normalize_curator_state(
                value.get("curator_state") or value.get("state") or value.get("new_state")
            ),
            curator_state_source=str(
                value.get("curator_state_source") or value.get("source") or "provided"
            ),
            transition_timestamp=_optional_int_timestamp(
                value.get("transition_timestamp") or value.get("timestamp") or value.get("ts")
            ),
            reason=_normalize_text(value.get("reason")),
            warning=_normalize_text(value.get("warning")),
            metadata=value.get("metadata") if isinstance(value.get("metadata"), Mapping) else {},
        )
    return CuratorStateAtResult(
        curator_state=normalize_curator_state(value),
        curator_state_source="provided",
    )


def _lookup_latest_at_or_before(source: TimestampLookup | str, timestamp: int) -> Any | None:
    if source is None or isinstance(source, str):
        return None
    if callable(source):
        return source(timestamp)
    if isinstance(source, Mapping):
        return _lookup_mapping_latest_at_or_before(source, timestamp)
    return _latest_record_at_or_before(source, timestamp)


def _lookup_mapping_latest_at_or_before(source: Mapping[Any, Any], timestamp: int) -> Any | None:
    latest_key: int | None = None
    latest_value: Any | None = None
    for key, value in source.items():
        key_timestamp = _coerce_timestamp(key)
        if key_timestamp is None:
            continue
        normalized_key = int(key_timestamp)
        if normalized_key <= int(timestamp) and (latest_key is None or normalized_key > latest_key):
            latest_key = normalized_key
            latest_value = value
    return latest_value


def _latest_record_at_or_before(source: Iterable[Any], timestamp: int) -> Any | None:
    latest_timestamp: int | None = None
    latest_record: Any | None = None
    for record in _iter_records(source):
        record_timestamp = _record_timestamp(record)
        if record_timestamp is None:
            continue
        normalized_timestamp = int(record_timestamp)
        if normalized_timestamp <= int(timestamp) and (
            latest_timestamp is None or normalized_timestamp > latest_timestamp
        ):
            latest_timestamp = normalized_timestamp
            latest_record = record
    return latest_record


def _events_from_mapping(source: Mapping[Any, Iterable[Any] | Any], timestamp: int) -> tuple[Any, ...]:
    events: list[Any] = []
    for key, value in source.items():
        key_timestamp = _coerce_timestamp(key)
        if key_timestamp is not None and int(key_timestamp) == int(timestamp):
            events.extend(_as_event_tuple(value))
    return tuple(events)


def _as_event_tuple(value: Iterable[Any] | Any | None) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray, Mapping)):
        return tuple(value)
    return (value,)


def _iter_records(value: Iterable[Any]) -> Iterator[Any]:
    if isinstance(value, (str, bytes, bytearray, Mapping)):
        return iter(())
    return iter(value)


def _record_timestamp(record: Any) -> int | None:
    return _optional_int_timestamp(
        _get_any(
            record,
            "timestamp",
            "ts",
            "event_timestamp",
            "original_event_timestamp",
            "entry_ts",
            "exit_ts",
            "created_at",
            "updated_at",
        )
    )


def _optional_int_timestamp(value: Any) -> int | None:
    timestamp = _coerce_timestamp(value)
    return int(timestamp) if timestamp is not None else None


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


def _get_any(record: Any, *keys: str) -> Any:
    for key in keys:
        if isinstance(record, Mapping) and key in record:
            return record[key]
        if not isinstance(record, Mapping) and hasattr(record, key):
            return getattr(record, key)
    return None


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "ActualEventsSource",
    "ConfigProvider",
    "CuratorStateProvider",
    "ReplaySnapshotFactory",
    "TimestampLookup",
    "build_replay_snapshots",
    "replay_candles",
]
