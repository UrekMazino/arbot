"""Phase 2 chart decision audit service.

This service assembles read-only chart audit data. Phase 2 returns historical
chart series, actual bot markers, and point-in-time replay markers.
Counterfactuals and decision score timelines are intentionally left empty here.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.chart_audit.actual_event_overlay import actual_markers_from_records
from core.chart_audit.config_snapshot_source import config_at
from core.chart_audit.curator_state_source import curator_state_at
from core.chart_audit.marker_types import MarkerCategory, StatisticalMarkerType
from core.chart_audit.replay_snapshot_factory import ReplaySnapshotFactory
from core.chart_audit.timestamp_alignment import align_actual_marker_timestamps

logger = logging.getLogger(__name__)


def get_pair_decision_audit_chart(
    pair: str,
    timeframe: str,
    start_ts: int | float | datetime | str | None,
    end_ts: int | float | datetime | str | None,
) -> dict[str, Any]:
    """Return the Phase 1 decision-audit chart payload for one pair."""

    pair_key = _normalize_pair_key_text(pair)
    start_value = _coerce_timestamp(start_ts)
    end_value = _coerce_timestamp(end_ts)

    chart_detail = _load_existing_pair_chart_detail(pair_key, timeframe, start_value, end_value)
    chart_points = _chart_points(chart_detail)
    zscore_series = _zscore_series_from_points(chart_points, start_value, end_value)
    statistical_markers = _statistical_markers_from_points(chart_points, start_value, end_value)

    actual_records = _load_actual_records(pair_key, start_value, end_value)
    actual_markers = actual_markers_from_records(
        actual_records,
        pair=None,
        start_ts=start_value,
        end_ts=end_value,
    )
    actual_markers = align_actual_marker_timestamps(
        actual_markers,
        chart_supports_exact_timestamp=True,
    )
    replay_markers = _replay_markers_from_points(
        pair_key=pair_key,
        timeframe=timeframe,
        chart_points=chart_points,
        actual_records=actual_records,
        start_ts=start_value,
        end_ts=end_value,
    )

    return {
        "pair": pair_key,
        "timeframe": str(timeframe or "").strip() or None,
        "start_ts": start_value,
        "end_ts": end_value,
        "zscore_series": zscore_series,
        "statistical_markers": statistical_markers,
        "replay_markers": replay_markers,
        "actual_markers": [marker.to_dict() for marker in actual_markers],
        "counterfactual_exit_studies": [],
        "counterfactuals_lazy_load": True,
        "decision_score_timeline": [],
    }


def _load_existing_pair_chart_detail(
    pair_key: str,
    timeframe: str,
    start_ts: float | None,
    end_ts: float | None,
) -> dict[str, Any] | None:
    symbols = _split_pair_key(pair_key)
    if symbols is None:
        return None

    service = _import_cointegrated_pairs_service()
    if service is None or not hasattr(service, "get_cointegrated_pair_detail"):
        return None

    limit = _chart_limit_from_range(timeframe, start_ts, end_ts)
    try:
        detail = service.get_cointegrated_pair_detail(symbols[0], symbols[1], limit=limit, db=None)
    except Exception as exc:
        logger.debug("chart audit zscore source unavailable for %s: %s", pair_key, exc)
        return None
    return detail if isinstance(detail, dict) else None


def _load_actual_records(
    pair_key: str,
    start_ts: float | None,
    end_ts: float | None,
) -> list[Any]:
    db_bundle = _import_database_bundle()
    if db_bundle is None:
        return []
    SessionLocal, RunEvent, Trade, select, or_ = db_bundle

    start_dt = _timestamp_to_datetime(start_ts)
    end_dt = _timestamp_to_datetime(end_ts)
    db = SessionLocal()
    try:
        records: list[Any] = []
        event_stmt = select(RunEvent)
        trade_stmt = select(Trade)
        if start_dt is not None and end_dt is not None:
            event_stmt = event_stmt.where(RunEvent.ts.between(start_dt, end_dt))
            trade_stmt = trade_stmt.where(
                or_(
                    Trade.entry_ts.between(start_dt, end_dt),
                    Trade.exit_ts.between(start_dt, end_dt),
                )
            )
        elif start_dt is not None:
            event_stmt = event_stmt.where(RunEvent.ts >= start_dt)
            trade_stmt = trade_stmt.where(
                or_(Trade.entry_ts >= start_dt, Trade.exit_ts >= start_dt)
            )
        elif end_dt is not None:
            event_stmt = event_stmt.where(RunEvent.ts <= end_dt)
            trade_stmt = trade_stmt.where(
                or_(Trade.entry_ts <= end_dt, Trade.exit_ts <= end_dt)
            )

        trade_stmt = trade_stmt.where(Trade.pair_key.in_(_pair_key_variants(pair_key)))
        event_types = (
            "trade_open",
            "trade_close",
            "entry_reject",
            "gate_enforced",
            "trade_quality_gate",
            "partial_exit",
            "trade_partial_exit",
            "manual_exit",
            "trade_manual_exit",
            "advanced_ml_exit_shadow",
        )
        event_stmt = event_stmt.where(RunEvent.event_type.in_(event_types))

        records.extend(db.execute(trade_stmt).scalars().all())
        records.extend(
            record
            for record in db.execute(event_stmt).scalars().all()
            if _record_matches_pair(record, pair_key)
        )
        return records
    except Exception as exc:
        logger.debug("chart audit actual record source unavailable for %s: %s", pair_key, exc)
        return []
    finally:
        try:
            db.close()
        except Exception:
            pass


def _zscore_series_from_points(
    points: list[dict[str, Any]],
    start_ts: float | None,
    end_ts: float | None,
) -> list[dict[str, Any]]:
    series: list[dict[str, Any]] = []
    for point in points:
        timestamp = _coerce_timestamp(point.get("timestamp") or point.get("ts"))
        if timestamp is None or not _timestamp_in_range(timestamp, start_ts, end_ts):
            continue
        series.append(
            _compact(
                {
                    "timestamp": timestamp,
                    "zscore": _safe_float(point.get("zscore")),
                    "spread": _safe_float(point.get("spread")),
                    "spread_mean": _safe_float(point.get("spread_mean")),
                    "price_1_norm": _safe_float(point.get("price_1_norm")),
                    "price_2_norm": _safe_float(point.get("price_2_norm")),
                }
            )
        )
    return series


def _statistical_markers_from_points(
    points: list[dict[str, Any]],
    start_ts: float | None,
    end_ts: float | None,
) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    for point in points:
        crossing_spread = _safe_float(point.get("crossing_spread"))
        if crossing_spread is None:
            continue
        timestamp = _coerce_timestamp(point.get("timestamp") or point.get("ts"))
        if timestamp is None or not _timestamp_in_range(timestamp, start_ts, end_ts):
            continue
        markers.append(
            _compact(
                {
                    "timestamp": timestamp,
                    "marker_category": MarkerCategory.STATISTICAL.value,
                    "marker_type": StatisticalMarkerType.HISTORICAL_MEAN_CROSSING.value,
                    "spread": crossing_spread,
                    "zscore": _safe_float(point.get("zscore")),
                    "label": point.get("crossing_label"),
                    "metadata": {"source": "existing_chart_data"},
                }
            )
        )
    return markers


def _replay_markers_from_points(
    *,
    pair_key: str,
    timeframe: str,
    chart_points: list[dict[str, Any]],
    actual_records: list[Any],
    start_ts: float | None,
    end_ts: float | None,
) -> list[dict[str, Any]]:
    candles = _replay_candles_from_points(chart_points, start_ts, end_ts)
    if not candles:
        return []

    try:
        factory = ReplaySnapshotFactory(
            pair=pair_key,
            timeframe=str(timeframe or "").strip() or "",
            candles=candles,
            curator_state_at=lambda timestamp: curator_state_at(pair_key, timestamp),
            config_at=config_at,
            actual_events=actual_records,
        )
        return [marker.to_dict() for marker in factory.replay()]
    except Exception as exc:
        logger.debug("chart audit replay unavailable for %s: %s", pair_key, exc)
        return []


def _replay_candles_from_points(
    points: list[dict[str, Any]],
    start_ts: float | None,
    end_ts: float | None,
) -> list[dict[str, Any]]:
    candles: list[dict[str, Any]] = []
    for point in points:
        timestamp = _coerce_timestamp(point.get("timestamp") or point.get("ts"))
        if timestamp is None or not _timestamp_in_range(timestamp, start_ts, end_ts):
            continue

        spread = _safe_float(point.get("spread"))
        price_1 = _safe_float(point.get("price_1"))
        price_2 = _safe_float(point.get("price_2"))
        if spread is None and (price_1 is None or price_2 is None):
            continue

        candle = _compact(
            {
                "timestamp": timestamp,
                "spread": spread,
                "close_1": price_1,
                "close_2": price_2,
            }
        )
        candles.append(candle)
    return candles


def _chart_points(chart_detail: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(chart_detail, dict):
        return []
    points = chart_detail.get("points")
    if not isinstance(points, list):
        return []
    return [point for point in points if isinstance(point, dict)]


def _import_cointegrated_pairs_service() -> Any | None:
    _ensure_platform_api_path()
    for module_name in (
        "app.services.cointegrated_pairs",
        "Platform.api.app.services.cointegrated_pairs",
    ):
        try:
            module = __import__(module_name, fromlist=["get_cointegrated_pair_detail"])
        except Exception:
            continue
        return module
    return None


def _import_database_bundle() -> tuple[Any, Any, Any, Any, Any] | None:
    _ensure_platform_api_path()
    for models_module_name, database_module_name in (
        ("app.models", "app.database"),
        ("Platform.api.app.models", "Platform.api.app.database"),
    ):
        try:
            models_module = __import__(models_module_name, fromlist=["RunEvent", "Trade"])
            database_module = __import__(database_module_name, fromlist=["SessionLocal"])
            sqlalchemy_module = __import__("sqlalchemy", fromlist=["or_", "select"])
            return (
                database_module.SessionLocal,
                models_module.RunEvent,
                models_module.Trade,
                sqlalchemy_module.select,
                sqlalchemy_module.or_,
            )
        except Exception:
            continue
    return None


def _ensure_platform_api_path() -> None:
    api_root = Path(__file__).resolve().parents[2] / "Platform" / "api"
    if api_root.exists() and str(api_root) not in sys.path:
        sys.path.insert(0, str(api_root))


def _chart_limit_from_range(timeframe: str, start_ts: float | None, end_ts: float | None) -> int:
    if start_ts is None or end_ts is None or end_ts <= start_ts:
        return 720
    seconds = _timeframe_seconds(timeframe) or 60
    bars = int((end_ts - start_ts) / seconds) + 5
    return max(50, min(bars, 2000))


def _timeframe_seconds(timeframe: str) -> int | None:
    text = str(timeframe or "").strip().lower()
    if len(text) < 2:
        return None
    try:
        value = int(text[:-1])
    except ValueError:
        return None
    unit = text[-1]
    if unit == "m":
        return value * 60
    if unit == "h":
        return value * 3600
    if unit == "d":
        return value * 86400
    return None


def _split_pair_key(pair_key: str) -> tuple[str, str] | None:
    if "/" not in pair_key:
        return None
    left, right = pair_key.split("/", 1)
    left = left.strip()
    right = right.strip()
    if not left or not right:
        return None
    return left, right


def _pair_key_variants(pair_key: str) -> list[str]:
    variants = [pair_key]
    symbols = _split_pair_key(pair_key)
    if symbols is not None:
        reversed_key = f"{symbols[1]}/{symbols[0]}"
        if reversed_key not in variants:
            variants.append(reversed_key)
    return variants


def _record_matches_pair(record: Any, pair_key: str) -> bool:
    record_pair = _record_pair_key(record)
    if not record_pair:
        return False
    return _same_pair(record_pair, pair_key)


def _record_pair_key(record: Any) -> str:
    pair_value = _get_any(record, "pair_key", "pair")
    if pair_value:
        return _normalize_pair_key_text(pair_value)

    payload = _get_any(record, "payload_json", "payload")
    if isinstance(payload, dict):
        payload_pair = payload.get("pair_key") or payload.get("pair")
        if payload_pair:
            return _normalize_pair_key_text(payload_pair)
        long_ticker = payload.get("long_ticker")
        short_ticker = payload.get("short_ticker")
        if long_ticker and short_ticker:
            return _normalize_pair_key_text((long_ticker, short_ticker))
        sym_1 = payload.get("sym_1") or payload.get("ticker_1")
        sym_2 = payload.get("sym_2") or payload.get("ticker_2")
        if sym_1 and sym_2:
            return _normalize_pair_key_text((sym_1, sym_2))
    return ""


def _same_pair(left: str, right: str) -> bool:
    left_symbols = _split_pair_key(_normalize_pair_key_text(left))
    right_symbols = _split_pair_key(_normalize_pair_key_text(right))
    if left_symbols is None or right_symbols is None:
        return _normalize_pair_key_text(left) == _normalize_pair_key_text(right)
    return set(left_symbols) == set(right_symbols)


def _normalize_pair_key_text(pair: Any) -> str:
    if isinstance(pair, (tuple, list)) and len(pair) >= 2:
        return f"{str(pair[0]).strip()}/{str(pair[1]).strip()}"
    text = str(pair or "").strip()
    if "/" in text:
        left, right = text.split("/", 1)
        return f"{left.strip()}/{right.strip()}"
    if "__" in text:
        left, right = text.split("__", 1)
        return f"{left.strip()}/{right.strip()}"
    return text


def _get_any(record: Any, *keys: str) -> Any:
    for key in keys:
        if isinstance(record, dict) and key in record:
            return record[key]
        if not isinstance(record, dict) and hasattr(record, key):
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


def _timestamp_to_datetime(value: float | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _timestamp_in_range(timestamp: int | float, start_ts: float | None, end_ts: float | None) -> bool:
    value = float(timestamp)
    if start_ts is not None and value < start_ts:
        return False
    if end_ts is not None and value > end_ts:
        return False
    return True


def _safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result or result in {float("inf"), float("-inf")}:
        return None
    return result


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


__all__ = ["get_pair_decision_audit_chart"]
