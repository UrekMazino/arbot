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
class FrozenCointegrationResult:
    p_value: float | None = None
    adf_stat: float | None = None
    hedge_ratio: float | None = None
    zero_crossings: int | None = None
    is_valid: bool = False
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "p_value", _optional_float(self.p_value))
        object.__setattr__(self, "adf_stat", _optional_float(self.adf_stat))
        object.__setattr__(self, "hedge_ratio", _optional_float(self.hedge_ratio))
        object.__setattr__(self, "zero_crossings", _optional_int(self.zero_crossings))
        object.__setattr__(self, "is_valid", bool(self.is_valid))
        object.__setattr__(self, "reasons", _reason_tuple(self.reasons))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "FrozenCointegrationResult":
        status = str(_get_any(value, "status") or "").strip().lower()
        coint_flag = _optional_int(_get_any(value, "coint_flag", "cointegration_flag", "is_cointegrated"))
        explicit_valid = _get_any(value, "is_valid", "valid")
        if explicit_valid is not None:
            is_valid = _coerce_bool(explicit_valid)
        elif coint_flag is not None:
            is_valid = coint_flag == 1
        else:
            is_valid = status == "ok"

        reasons = _reason_tuple(_get_any(value, "reasons", "reason", "message"))
        if status == "insufficient_data" and "insufficient_history" not in reasons:
            reasons = (*reasons, "insufficient_history")
        if coint_flag is not None and coint_flag != 1 and "cointegration_invalid" not in reasons:
            reasons = (*reasons, "cointegration_invalid")

        return cls(
            p_value=_get_any(value, "p_value", "pvalue", "adf_p_value", "cointegration_p_value"),
            adf_stat=_get_any(value, "adf_stat", "adf_statistic", "test_statistic"),
            hedge_ratio=_get_any(value, "hedge_ratio", "beta"),
            zero_crossings=_get_any(value, "zero_crossings", "zero_crossing_count"),
            is_valid=is_valid,
            reasons=reasons,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "p_value": self.p_value,
            "adf_stat": self.adf_stat,
            "hedge_ratio": self.hedge_ratio,
            "zero_crossings": self.zero_crossings,
            "is_valid": self.is_valid,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class FrozenOrderBookSnapshot:
    timestamp: int | float
    bid_depth_usdt: float | None = None
    ask_depth_usdt: float | None = None
    spread_bps: float | None = None
    slippage_bps: float | None = None
    liquidity_score: float | None = None
    is_fresh: bool = True
    source: str | None = None
    age_ms: float | None = None

    def __post_init__(self) -> None:
        timestamp_value = _coerce_timestamp(self.timestamp)
        if timestamp_value is None:
            raise ValueError("FrozenOrderBookSnapshot.timestamp is missing or invalid")
        object.__setattr__(self, "timestamp", int(timestamp_value))
        object.__setattr__(self, "bid_depth_usdt", _optional_float(self.bid_depth_usdt))
        object.__setattr__(self, "ask_depth_usdt", _optional_float(self.ask_depth_usdt))
        object.__setattr__(self, "spread_bps", _optional_float(self.spread_bps))
        object.__setattr__(self, "slippage_bps", _optional_float(self.slippage_bps))
        object.__setattr__(self, "liquidity_score", _optional_float(self.liquidity_score))
        object.__setattr__(self, "is_fresh", _coerce_bool(self.is_fresh))
        object.__setattr__(self, "source", _normalize_text(self.source))
        object.__setattr__(self, "age_ms", _optional_float(self.age_ms))

    @classmethod
    def from_raw(cls, value: Any, *, timestamp: int | float | None = None) -> "FrozenOrderBookSnapshot":
        if isinstance(value, FrozenOrderBookSnapshot):
            return value
        snapshot_timestamp = (
            _get_any(value, "timestamp", "ts", "event_timestamp", "updated_at")
            if value is not None
            else None
        )
        if snapshot_timestamp is None:
            snapshot_timestamp = timestamp
        if snapshot_timestamp is None:
            snapshot_timestamp = 0
        stale_value = _get_any(value, "stale", "is_stale")
        explicit_fresh = _get_any(value, "is_fresh", "fresh")
        is_fresh = (
            not _coerce_bool(stale_value)
            if stale_value is not None
            else (_coerce_bool(explicit_fresh) if explicit_fresh is not None else True)
        )
        return cls(
            timestamp=snapshot_timestamp,
            bid_depth_usdt=_get_any(value, "bid_depth_usdt", "bid_depth", "book_bid_depth_usdt"),
            ask_depth_usdt=_get_any(value, "ask_depth_usdt", "ask_depth", "book_ask_depth_usdt"),
            spread_bps=_get_any(value, "spread_bps", "book_spread_bps"),
            slippage_bps=_get_any(value, "slippage_bps", "estimated_slippage_bps", "slippage_estimate_bps"),
            liquidity_score=_get_any(value, "liquidity_score"),
            is_fresh=is_fresh,
            source=_get_any(value, "source"),
            age_ms=_get_any(value, "book_freshness_ms", "freshness_ms", "update_age_ms", "age_ms"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "bid_depth_usdt": self.bid_depth_usdt,
            "ask_depth_usdt": self.ask_depth_usdt,
            "spread_bps": self.spread_bps,
            "slippage_bps": self.slippage_bps,
            "liquidity_score": self.liquidity_score,
            "is_fresh": self.is_fresh,
            "source": self.source,
            "age_ms": self.age_ms,
        }


@dataclass(frozen=True)
class ActualBotEvent:
    event_id: str
    event_type: str
    pair: str
    timestamp: float

    side: str | None = None
    trade_id: str | None = None
    z_score: float | None = None
    spread: float | None = None
    reason: str | None = None

    pnl_usdt: float | None = None
    fees_usdt: float | None = None
    slippage_usdt: float | None = None

    metadata: tuple[tuple[str, object], ...] = ()

    def __post_init__(self) -> None:
        timestamp_value = _coerce_timestamp(self.timestamp)
        if timestamp_value is None:
            raise ValueError("ActualBotEvent.timestamp is missing or invalid")
        object.__setattr__(self, "event_id", str(self.event_id or "").strip())
        object.__setattr__(self, "event_type", str(self.event_type or "").strip())
        object.__setattr__(self, "pair", str(self.pair or "").strip())
        object.__setattr__(self, "timestamp", float(timestamp_value))
        object.__setattr__(self, "side", _normalize_text(self.side))
        object.__setattr__(self, "trade_id", _normalize_text(self.trade_id))
        object.__setattr__(self, "z_score", _optional_float(self.z_score))
        object.__setattr__(self, "spread", _optional_float(self.spread))
        object.__setattr__(self, "reason", _normalize_text(self.reason))
        object.__setattr__(self, "pnl_usdt", _optional_float(self.pnl_usdt))
        object.__setattr__(self, "fees_usdt", _optional_float(self.fees_usdt))
        object.__setattr__(self, "slippage_usdt", _optional_float(self.slippage_usdt))
        object.__setattr__(self, "metadata", _metadata_tuple(self.metadata))
        if not self.event_id:
            raise ValueError("ActualBotEvent.event_id is required")
        if not self.event_type:
            raise ValueError("ActualBotEvent.event_type is required")
        if not self.pair:
            raise ValueError("ActualBotEvent.pair is required")

    @classmethod
    def from_raw(
        cls,
        value: Any,
        *,
        pair: str | None = None,
        timestamp: int | float | None = None,
    ) -> "ActualBotEvent":
        if isinstance(value, ActualBotEvent):
            return value
        payload = _get_any(value, "payload")
        if not isinstance(payload, Mapping):
            payload = {}
        event_type = _get_any(value, "event_type", "type", "action") or _get_any(payload, "event_type", "type", "action")
        event_timestamp = (
            _get_any(value, "timestamp", "ts", "event_timestamp", "original_event_timestamp", "created_at")
            or _get_any(payload, "timestamp", "ts", "event_timestamp", "created_at")
            or timestamp
        )
        event_id = (
            _get_any(value, "event_id", "id", "uuid")
            or _get_any(payload, "event_id", "id", "uuid")
            or _get_any(value, "trade_id")
            or _get_any(payload, "trade_id")
            or f"{event_type or 'event'}_{event_timestamp or timestamp or 0}"
        )
        source_metadata = _get_any(value, "metadata")
        if not isinstance(source_metadata, Mapping):
            source_metadata = payload if isinstance(payload, Mapping) else {}
        return cls(
            event_id=str(event_id),
            event_type=str(event_type or "unknown"),
            pair=str(_get_any(value, "pair") or _get_any(payload, "pair") or pair or "unknown"),
            timestamp=float(_coerce_timestamp(event_timestamp) or 0.0),
            side=_get_any(value, "side") or _get_any(payload, "side"),
            trade_id=_get_any(value, "trade_id") or _get_any(payload, "trade_id"),
            z_score=_get_any(value, "z_score", "zscore") or _get_any(payload, "z_score", "zscore"),
            spread=_get_any(value, "spread") or _get_any(payload, "spread"),
            reason=_get_any(value, "reason") or _get_any(payload, "reason"),
            pnl_usdt=_get_any(value, "pnl_usdt") or _get_any(payload, "pnl_usdt"),
            fees_usdt=_get_any(value, "fees_usdt") or _get_any(payload, "fees_usdt"),
            slippage_usdt=_get_any(value, "slippage_usdt") or _get_any(payload, "slippage_usdt"),
            metadata=_metadata_tuple(source_metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "pair": self.pair,
            "timestamp": self.timestamp,
            "side": self.side,
            "trade_id": self.trade_id,
            "z_score": self.z_score,
            "spread": self.spread,
            "reason": self.reason,
            "pnl_usdt": self.pnl_usdt,
            "fees_usdt": self.fees_usdt,
            "slippage_usdt": self.slippage_usdt,
            "metadata": {key: value for key, value in self.metadata},
        }


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

    hedge_ratio_sizing_enabled: bool = False
    hedge_sizing_mode: str = "equal_notional"
    min_hedge_ratio: float = 0.20
    max_hedge_ratio: float = 5.00
    reject_negative_hedge_ratio: bool = True
    max_hedge_sizing_error_pct: float = 0.10
    max_hedge_ratio_drift_pct: float = 0.20
    severe_hedge_ratio_drift_pct: float = 0.35
    min_cointegration_window: int = 120

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
        object.__setattr__(self, "hedge_ratio_sizing_enabled", _coerce_bool(self.hedge_ratio_sizing_enabled))
        object.__setattr__(self, "hedge_sizing_mode", str(self.hedge_sizing_mode or "equal_notional"))
        object.__setattr__(self, "min_hedge_ratio", float(self.min_hedge_ratio))
        object.__setattr__(self, "max_hedge_ratio", float(self.max_hedge_ratio))
        object.__setattr__(self, "reject_negative_hedge_ratio", _coerce_bool(self.reject_negative_hedge_ratio))
        object.__setattr__(self, "max_hedge_sizing_error_pct", float(self.max_hedge_sizing_error_pct))
        object.__setattr__(self, "max_hedge_ratio_drift_pct", float(self.max_hedge_ratio_drift_pct))
        object.__setattr__(self, "severe_hedge_ratio_drift_pct", float(self.severe_hedge_ratio_drift_pct))
        object.__setattr__(self, "min_cointegration_window", max(int(self.min_cointegration_window), 1))


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
    cointegration_result_until_t: FrozenCointegrationResult | None
    zero_crossing_count_until_t: int | None

    curator_state: CuratorState
    curator_state_source: str
    pair_health_state: str | None
    orderbook_snapshot: FrozenOrderBookSnapshot | None
    config_snapshot: ReplayConfigSnapshot
    config_source: str

    actual_events_at_t: tuple[ActualBotEvent, ...]

    def __post_init__(self) -> None:
        timestamp_value = _coerce_timestamp(self.timestamp)
        if timestamp_value is None:
            raise ValueError("ReplaySnapshot.timestamp is missing or invalid")
        object.__setattr__(self, "timestamp", int(timestamp_value))
        object.__setattr__(self, "candles_until_t", _as_tuple(self.candles_until_t, "candles_until_t"))
        object.__setattr__(self, "zscore_until_t", _float_tuple(self.zscore_until_t, "zscore_until_t"))
        object.__setattr__(self, "spread_until_t", _float_tuple(self.spread_until_t, "spread_until_t"))
        object.__setattr__(
            self,
            "actual_events_at_t",
            tuple(
                freeze_actual_bot_event(event, pair=self.pair, timestamp=timestamp_value)
                for event in _as_tuple(self.actual_events_at_t, "actual_events_at_t")
            ),
        )
        if self.cointegration_result_until_t is not None:
            object.__setattr__(
                self,
                "cointegration_result_until_t",
                freeze_cointegration_result(self.cointegration_result_until_t),
            )
        if self.orderbook_snapshot is not None:
            object.__setattr__(
                self,
                "orderbook_snapshot",
                freeze_orderbook_snapshot(self.orderbook_snapshot, timestamp=timestamp_value),
            )
        if len(self.candles_until_t) < int(self.config_snapshot.min_cointegration_window):
            object.__setattr__(self, "hedge_ratio_until_t", None)
            object.__setattr__(self, "cointegration_result_until_t", None)
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


def freeze_cointegration_result(value: FrozenCointegrationResult | Mapping[str, Any]) -> FrozenCointegrationResult | None:
    if isinstance(value, FrozenCointegrationResult):
        return value
    if isinstance(value, Mapping):
        if str(value.get("status") or "").strip().lower() == "insufficient_data":
            return None
        return FrozenCointegrationResult.from_mapping(value)
    raise TypeError("cointegration_result_until_t must be FrozenCointegrationResult, mapping, or None")


def freeze_orderbook_snapshot(
    value: FrozenOrderBookSnapshot | Any,
    *,
    timestamp: int | float | None = None,
) -> FrozenOrderBookSnapshot:
    return FrozenOrderBookSnapshot.from_raw(value, timestamp=timestamp)


def freeze_actual_bot_event(
    value: ActualBotEvent | Any,
    *,
    pair: str | None = None,
    timestamp: int | float | None = None,
) -> ActualBotEvent:
    return ActualBotEvent.from_raw(value, pair=pair, timestamp=timestamp)


def _get_any(record: Any, *keys: str) -> Any:
    for key in keys:
        if isinstance(record, Mapping) and key in record:
            return record[key]
        if not isinstance(record, Mapping) and hasattr(record, key):
            return getattr(record, key)
    return None


def _optional_int(value: Any) -> int | None:
    parsed = _optional_float(value)
    return int(parsed) if parsed is not None else None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in {float("inf"), float("-inf")}:
        return None
    return parsed


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on", "enabled"}


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _reason_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return tuple(str(item) for item in value if str(item).strip())
    return (str(value),)


def _metadata_tuple(value: Any) -> tuple[tuple[str, object], ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        return tuple(
            (str(key), _freeze_metadata_value(item))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    if isinstance(value, tuple):
        output: list[tuple[str, object]] = []
        for item in value:
            if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)) and len(item) == 2:
                output.append((str(item[0]), _freeze_metadata_value(item[1])))
        return tuple(output)
    return (("value", _freeze_metadata_value(value)),)


def _freeze_metadata_value(value: Any) -> object:
    if isinstance(value, Mapping):
        return tuple(
            (str(key), _freeze_metadata_value(item))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    if isinstance(value, list):
        return tuple(_freeze_metadata_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_metadata_value(item) for item in value)
    return value


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
    "ActualBotEvent",
    "FrozenCointegrationResult",
    "FrozenOrderBookSnapshot",
    "ReplayConfigSnapshot",
    "ReplaySnapshot",
    "candle_timestamp",
    "freeze_actual_bot_event",
    "freeze_cointegration_result",
    "freeze_orderbook_snapshot",
    "validate_snapshot_timestamp_matches_last_candle",
]
