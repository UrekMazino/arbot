"""Point-in-time replay snapshot contracts.

Replay snapshots are interface-level no-lookahead guards. They expose only data
available at or before one candle timestamp and keep historical sequences as
immutable tuples.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core.chart_audit.marker_types import CuratorState


@dataclass(frozen=True)
class ReplayConfigSnapshot:
    config_version: str
    config_source: str

    entry_z_threshold: float
    exit_z_threshold: float
    persistence_candles: int
    max_hold_seconds: float
    min_zero_crossings: int

    min_liquidity_score: float | None = None
    max_orderbook_age_ms: float | None = None
    max_spread_bps: float | None = None
    max_slippage_bps: float | None = None

    warning: str | None = None

    def __post_init__(self) -> None:
        if self.config_source not in {"historical", "current_approximate"}:
            raise ValueError("ReplayConfigSnapshot.config_source must be historical or current_approximate")
        if self.config_source == "current_approximate" and not self.warning:
            object.__setattr__(
                self,
                "warning",
                "Historical config unavailable; current config used for replay.",
            )


@dataclass(frozen=True)
class ReplaySnapshot:
    pair: str
    timeframe: str
    timestamp: int

    candles_until_t: tuple[Any, ...]
    zscore_until_t: tuple[float, ...]
    spread_until_t: tuple[float, ...]

    rolling_mean_until_t: float | None
    rolling_std_until_t: float | None
    hedge_ratio_until_t: float | None
    cointegration_result_until_t: dict[str, Any] | None
    zero_crossing_count_until_t: int | None

    curator_state: CuratorState
    curator_state_source: str
    pair_health_state: str | None
    orderbook_snapshot: Any | None
    config_snapshot: ReplayConfigSnapshot
    config_source: str

    actual_events_at_t: tuple[Any, ...]

    def __post_init__(self) -> None:
        timestamp_value = _coerce_timestamp(self.timestamp)
        if timestamp_value is None:
            raise ValueError("ReplaySnapshot.timestamp is missing or invalid")
        object.__setattr__(self, "timestamp", int(timestamp_value))
        object.__setattr__(self, "candles_until_t", _as_tuple(self.candles_until_t, "candles_until_t"))
        object.__setattr__(self, "zscore_until_t", _float_tuple(self.zscore_until_t, "zscore_until_t"))
        object.__setattr__(self, "spread_until_t", _float_tuple(self.spread_until_t, "spread_until_t"))
        object.__setattr__(self, "actual_events_at_t", _as_tuple(self.actual_events_at_t, "actual_events_at_t"))
        if self.cointegration_result_until_t is not None:
            object.__setattr__(
                self,
                "cointegration_result_until_t",
                _freeze_lists_in_mapping(self.cointegration_result_until_t),
            )
        if not isinstance(self.curator_state, CuratorState):
            object.__setattr__(self, "curator_state", CuratorState(str(self.curator_state)))
        if self.config_source != self.config_snapshot.config_source:
            raise ValueError("ReplaySnapshot.config_source must match config_snapshot.config_source")
        validate_snapshot_timestamp_matches_last_candle(self)


def validate_snapshot_timestamp_matches_last_candle(snapshot: ReplaySnapshot) -> None:
    """Validate that snapshot.timestamp is the last included candle timestamp."""

    if not snapshot.candles_until_t:
        raise ValueError("ReplaySnapshot requires at least one candle")
    last_candle_timestamp = candle_timestamp(snapshot.candles_until_t[-1])
    if last_candle_timestamp is None:
        raise ValueError("Last candle timestamp is missing or invalid")
    if int(last_candle_timestamp) != int(snapshot.timestamp):
        raise ValueError(
            "ReplaySnapshot.timestamp must match the last candle timestamp "
            f"({snapshot.timestamp!r} != {last_candle_timestamp!r})"
        )
    for candle in snapshot.candles_until_t:
        item_timestamp = candle_timestamp(candle)
        if item_timestamp is None:
            raise ValueError("ReplaySnapshot candle timestamp is missing or invalid")
        if int(item_timestamp) > int(snapshot.timestamp):
            raise ValueError("ReplaySnapshot cannot contain candles after timestamp")


def candle_timestamp(candle: Any) -> int | None:
    """Extract a normalized seconds timestamp from a candle-like object."""

    raw_timestamp = _get_any(candle, "timestamp", "ts", "time", "close_time", "close_ts")
    value = _coerce_timestamp(raw_timestamp)
    return int(value) if value is not None else None


def _as_tuple(value: Sequence[Any] | tuple[Any, ...], field_name: str) -> tuple[Any, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    raise TypeError(f"ReplaySnapshot.{field_name} must be a tuple or finite sequence")


def _float_tuple(value: Sequence[Any] | tuple[Any, ...], field_name: str) -> tuple[float, ...]:
    return tuple(float(item) for item in _as_tuple(value, field_name))


def _freeze_lists_in_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _freeze_lists(item) for key, item in value.items()}


def _freeze_lists(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_freeze_lists(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_lists(item) for item in value)
    if isinstance(value, Mapping):
        return {str(key): _freeze_lists(item) for key, item in value.items()}
    return value


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


__all__ = [
    "ReplayConfigSnapshot",
    "ReplaySnapshot",
    "candle_timestamp",
    "validate_snapshot_timestamp_matches_last_candle",
]
