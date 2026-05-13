"""Read-only Risk & Health Dashboard service."""

from __future__ import annotations

import copy
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.dashboard.contracts import DashboardCacheMeta, RiskEventSummary
from core.dashboard.pair_history_service import (
    HIGH_HEDGE_DRIFT_THRESHOLD,
    _coerce_timestamp,
    _finite_float,
    _first_not_none,
    _get_any,
    _load_pair_state_data,
    _normalize_pair,
    _payload,
    _platform_database_bundle,
    _timestamp_to_datetime,
    _trade_metadata_float,
    _trade_timestamp,
)
from core.dashboard.portfolio_service import build_drawdown_curve, build_equity_curve, build_open_exposure


RISK_HEALTH_CACHE_TTL_SECONDS = 30
DEFAULT_ALERT_DEDUP_WINDOW_MINUTES = 30
HIGH_BREAK_RISK_THRESHOLD = 0.65
LIQUIDITY_STRESS_SCORE_THRESHOLD = 0.30
API_ERROR_SPIKE_COUNT_THRESHOLD = 3
CONSECUTIVE_LOSS_ALERT_THRESHOLD = 3


@dataclass(frozen=True)
class RiskHealthDataBundle:
    bot_status: Mapping[str, Any] | None = None
    trades: tuple[Any, ...] = ()
    runs: tuple[Any, ...] = ()
    equity_snapshots: tuple[Any, ...] = ()
    position_snapshots: tuple[Any, ...] = ()
    run_events: tuple[Any, ...] = ()
    pair_state: Mapping[str, Any] | None = None
    graveyard_tickers: frozenset[str] = frozenset()


_CACHE: dict[tuple[int | None, int | None], tuple[float, dict[str, Any]]] = {}


def get_risk_health_dashboard(
    start_ts: int | float | datetime | str | None = None,
    end_ts: int | float | datetime | str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Return a JSON-safe Risk & Health dashboard payload."""

    return get_cached_or_compute(start_ts=start_ts, end_ts=end_ts, refresh=refresh)


def get_cached_or_compute(
    *,
    start_ts: int | float | datetime | str | None = None,
    end_ts: int | float | datetime | str | None = None,
    refresh: bool = False,
    ttl_seconds: int = RISK_HEALTH_CACHE_TTL_SECONDS,
) -> dict[str, Any]:
    start_value = _coerce_timestamp(start_ts)
    end_value = _coerce_timestamp(end_ts)
    cache_key = (start_value, end_value)
    now = time.time()

    if not refresh:
        cached = _CACHE.get(cache_key)
        if cached is not None:
            expires_at, payload = cached
            if now < expires_at:
                result = copy.deepcopy(payload)
                result["cache"]["cache_hit"] = True
                return result

    payload = _compute_risk_health_dashboard(
        start_ts=start_value,
        end_ts=end_value,
        generated_at=now,
        ttl_seconds=ttl_seconds,
    )
    _CACHE[cache_key] = (now + max(int(ttl_seconds), 15), copy.deepcopy(payload))
    return payload


def clear_risk_health_cache() -> None:
    _CACHE.clear()


def build_risk_kpis(
    *,
    equity_curve: Sequence[Mapping[str, Any]] = (),
    drawdown_curve: Sequence[Mapping[str, Any]] = (),
    position_snapshots: Sequence[Any] = (),
    run_events: Sequence[Any] = (),
) -> dict[str, Any]:
    open_exposure_rows = build_open_exposure(position_snapshots)
    open_exposure_values = [_finite_float(row.get("open_exposure_usdt")) for row in open_exposure_rows]
    latest_drawdown = drawdown_curve[-1] if drawdown_curve else None
    has_event_source = bool(run_events)

    order_failure_count = sum(1 for event in run_events if _is_order_failure_record(event))
    orderbook_stale_count = sum(1 for event in run_events if _is_orderbook_stale_record(event))

    return {
        "current_drawdown_usdt": _finite_float(latest_drawdown.get("drawdown_usdt")) if latest_drawdown else None,
        "daily_loss_limit_usage_pct": _latest_record_float(run_events, "daily_loss_limit_usage_pct"),
        "open_exposure_usdt": _sum_optional(open_exposure_values),
        "open_positions": len(open_exposure_rows) if open_exposure_rows else None,
        "orphan_desync_status": _latest_orphan_desync_status(run_events),
        "api_latency_ms": _latest_record_float(run_events, "api_latency_ms", "latency_ms", "okx_latency_ms"),
        "order_failure_count": order_failure_count if has_event_source else None,
        "orderbook_stale_count": orderbook_stale_count if has_event_source else None,
    }


def build_pair_health(
    *,
    pair_state: Mapping[str, Any] | None = None,
    graveyard_tickers: frozenset[str] = frozenset(),
    trades: Sequence[Any] = (),
    position_snapshots: Sequence[Any] = (),
    run_events: Sequence[Any] = (),
) -> dict[str, list[Any]]:
    hospital_pairs = _state_pairs(pair_state, "hospital")
    graveyard_pairs = _state_pairs(pair_state, "graveyard")
    graveyard_pairs.extend(sorted(str(ticker) for ticker in graveyard_tickers if str(ticker).strip()))
    graveyard_pairs = _dedupe_texts(graveyard_pairs)

    return {
        "hospital_pairs": hospital_pairs,
        "graveyard_pairs": graveyard_pairs,
        "high_break_risk_pairs": _high_break_risk_pairs(run_events),
        "high_hedge_drift_positions": _high_hedge_drift_positions(
            records=tuple(position_snapshots) + tuple(trades),
        ),
        "liquidity_stress_pairs": _liquidity_stress_pairs(run_events),
    }


def build_alerts(
    *,
    pair_state: Mapping[str, Any] | None = None,
    graveyard_tickers: frozenset[str] = frozenset(),
    trades: Sequence[Any] = (),
    position_snapshots: Sequence[Any] = (),
    run_events: Sequence[Any] = (),
    default_alert_dedup_window_minutes: int = DEFAULT_ALERT_DEDUP_WINDOW_MINUTES,
) -> list[dict[str, Any]]:
    pair_health = build_pair_health(
        pair_state=pair_state,
        graveyard_tickers=graveyard_tickers,
        trades=trades,
        position_snapshots=position_snapshots,
        run_events=run_events,
    )
    raw_alerts: list[RiskEventSummary] = []

    for pair in pair_health["hospital_pairs"]:
        raw_alerts.append(
            _risk_event(
                severity="warning",
                alert_type="pair_moved_to_hospital",
                message=f"Pair is currently in hospital: {pair}",
                pair=pair,
                timestamp=_state_entry_timestamp(pair_state, "hospital", pair),
                metadata=_state_entry_metadata(pair_state, "hospital", pair),
            )
        )

    for pair in pair_health["graveyard_pairs"]:
        raw_alerts.append(
            _risk_event(
                severity="error",
                alert_type="pair_moved_to_graveyard",
                message=f"Pair is currently in graveyard: {pair}",
                pair=pair,
                timestamp=_state_entry_timestamp(pair_state, "graveyard", pair),
                metadata=_state_entry_metadata(pair_state, "graveyard", pair),
            )
        )

    for row in pair_health["high_hedge_drift_positions"]:
        pair = _normalize_pair(row.get("pair"))
        drift = _finite_float(row.get("hedge_ratio_drift_pct"))
        raw_alerts.append(
            _risk_event(
                severity="warning",
                alert_type="hedge_ratio_drift_exceeded",
                message=f"Hedge ratio drift exceeded threshold for {pair or 'global'}",
                pair=pair,
                timestamp=_coerce_timestamp(row.get("latest_timestamp")),
                metadata={"hedge_ratio_drift_pct": drift, "threshold": HIGH_HEDGE_DRIFT_THRESHOLD},
            )
        )

    for row in pair_health["high_break_risk_pairs"]:
        pair = _normalize_pair(row.get("pair"))
        break_risk = _finite_float(row.get("break_risk"))
        raw_alerts.append(
            _risk_event(
                severity="warning",
                alert_type="regime_break_risk_high",
                message=f"Regime break risk is high for {pair or 'global'}",
                pair=pair,
                timestamp=_coerce_timestamp(row.get("latest_timestamp")),
                metadata={"break_risk": break_risk, "threshold": HIGH_BREAK_RISK_THRESHOLD},
            )
        )

    for row in pair_health["liquidity_stress_pairs"]:
        pair = _normalize_pair(row.get("pair"))
        raw_alerts.append(
            _risk_event(
                severity="error",
                alert_type="liquidity_stress",
                message=f"Liquidity stress detected for {pair or 'global'}",
                pair=pair,
                timestamp=_coerce_timestamp(row.get("latest_timestamp")),
                metadata=dict(row.get("metadata") or {}),
            )
        )

    for event in run_events:
        pair = _record_pair(event)
        timestamp = _record_timestamp(event)
        if _is_orderbook_stale_record(event):
            raw_alerts.append(
                _risk_event(
                    severity="warning",
                    alert_type="orderbook_stale",
                    message=f"Orderbook stale for {pair or 'global'}",
                    pair=pair,
                    timestamp=timestamp,
                    metadata=_payload(event),
                )
            )
        if _is_orphan_position_record(event):
            raw_alerts.append(
                _risk_event(
                    severity="critical",
                    alert_type="orphan_position",
                    message=f"Orphan position detected for {pair or 'global'}",
                    pair=pair,
                    timestamp=timestamp,
                    metadata=_payload(event),
                )
            )
        if _is_leg_desync_record(event):
            raw_alerts.append(
                _risk_event(
                    severity="critical",
                    alert_type="leg_desync",
                    message=f"Leg desync detected for {pair or 'global'}",
                    pair=pair,
                    timestamp=timestamp,
                    metadata=_payload(event),
                )
            )
        if _is_drawdown_threshold_record(event):
            raw_alerts.append(
                _risk_event(
                    severity="warning",
                    alert_type="drawdown_threshold_near",
                    message="Drawdown threshold is near",
                    pair=pair,
                    timestamp=timestamp,
                    metadata=_payload(event),
                )
            )

    api_failures = [event for event in run_events if _is_api_failure_record(event)]
    explicit_api_spikes = [event for event in run_events if "api_error_spike" in _event_type(event)]
    if explicit_api_spikes or len(api_failures) >= API_ERROR_SPIKE_COUNT_THRESHOLD:
        latest_api = _latest_by_timestamp(tuple(explicit_api_spikes) or tuple(api_failures))
        raw_alerts.append(
            _risk_event(
                severity="error",
                alert_type="API_error_spike",
                message="API error spike detected",
                pair=None,
                timestamp=_record_timestamp(latest_api),
                metadata={"event_count": len(api_failures) or len(explicit_api_spikes)},
            )
        )

    loss_streak = _consecutive_losses(trades)
    if loss_streak["count"] >= CONSECUTIVE_LOSS_ALERT_THRESHOLD:
        raw_alerts.append(
            _risk_event(
                severity="warning",
                alert_type="consecutive_losses",
                message=f"{loss_streak['count']} consecutive losses detected",
                pair=None,
                timestamp=loss_streak["latest_timestamp"],
                metadata={"loss_count": loss_streak["count"]},
            )
        )

    return deduplicate_alerts(
        raw_alerts,
        default_alert_dedup_window_minutes=default_alert_dedup_window_minutes,
    )


def deduplicate_alerts(
    alerts: Sequence[RiskEventSummary | Mapping[str, Any]],
    *,
    default_alert_dedup_window_minutes: int = DEFAULT_ALERT_DEDUP_WINDOW_MINUTES,
) -> list[dict[str, Any]]:
    window_seconds = max(int(default_alert_dedup_window_minutes), 1) * 60
    sorted_alerts = sorted(alerts, key=lambda alert: _alert_timestamp(alert) or 0)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for alert in sorted_alerts:
        payload = _alert_to_dict(alert)
        alert_type = str(payload.get("type") or "").strip()
        if not alert_type:
            continue
        key = (alert_type, _dedup_pair_key(payload.get("pair")))
        timestamp = _coerce_timestamp(payload.get("latest_timestamp"))
        target_group = None
        for group in groups[key]:
            group_ts = _coerce_timestamp(group.get("latest_timestamp"))
            if timestamp is None or group_ts is None or abs(timestamp - group_ts) <= window_seconds:
                target_group = group
                break
        if target_group is None:
            groups[key].append(payload)
            continue
        _merge_alert_payload(target_group, payload)

    rows = [item for grouped in groups.values() for item in grouped]
    rows.sort(key=lambda alert: _coerce_timestamp(alert.get("latest_timestamp")) or 0, reverse=True)
    return rows


def _compute_risk_health_dashboard(
    *,
    start_ts: int | None,
    end_ts: int | None,
    generated_at: float,
    ttl_seconds: int,
) -> dict[str, Any]:
    bundle = _load_risk_health_data(start_ts=start_ts, end_ts=end_ts)
    equity_curve = build_equity_curve(bundle.equity_snapshots)
    drawdown_curve = build_drawdown_curve(equity_curve)
    cache = DashboardCacheMeta(
        cache_hit=False,
        generated_at=generated_at,
        ttl_seconds=ttl_seconds,
        refresh_supported=True,
    )
    return {
        "bot_status": build_bot_status(
            bot_status=bundle.bot_status,
            runs=bundle.runs,
            run_events=bundle.run_events,
            equity_snapshots=bundle.equity_snapshots,
        ),
        "risk_kpis": build_risk_kpis(
            equity_curve=equity_curve,
            drawdown_curve=drawdown_curve,
            position_snapshots=bundle.position_snapshots,
            run_events=bundle.run_events,
        ),
        "pair_health": build_pair_health(
            pair_state=bundle.pair_state,
            graveyard_tickers=bundle.graveyard_tickers,
            trades=bundle.trades,
            position_snapshots=bundle.position_snapshots,
            run_events=bundle.run_events,
        ),
        "alerts": build_alerts(
            pair_state=bundle.pair_state,
            graveyard_tickers=bundle.graveyard_tickers,
            trades=bundle.trades,
            position_snapshots=bundle.position_snapshots,
            run_events=bundle.run_events,
        ),
        "cache": cache.to_dict(),
    }


def build_bot_status(
    *,
    bot_status: Mapping[str, Any] | None = None,
    runs: Sequence[Any] = (),
    run_events: Sequence[Any] = (),
    equity_snapshots: Sequence[Any] = (),
) -> dict[str, Any]:
    if bot_status:
        return _compact(dict(bot_status))

    latest_run = _latest_by_timestamp(runs, "end_ts", "updated_at", "start_ts")
    latest_event = _latest_by_timestamp(run_events, "ts", "timestamp")
    latest_equity = _latest_by_timestamp(equity_snapshots, "ts", "timestamp")
    event_payload = _payload(latest_event)

    return _compact(
        {
            "status": _normalize_text(_first_not_none(_get_any(latest_run, "status"), event_payload.get("status"))),
            "active_pair": _normalize_pair(
                _first_not_none(
                    event_payload.get("active_pair"),
                    event_payload.get("current_pair"),
                    event_payload.get("pair"),
                    _get_any(latest_equity, "current_pair"),
                )
            ),
            "latest_event_type": _event_type(latest_event) or None,
            "latest_event_timestamp": _record_timestamp(latest_event),
        }
    )


def _load_risk_health_data(start_ts: int | None, end_ts: int | None) -> RiskHealthDataBundle:
    pair_state, graveyard_tickers = _safe_load_pair_state_data()
    try:
        SessionLocal, models, select, or_ = _platform_database_bundle()
    except Exception:
        return RiskHealthDataBundle(pair_state=pair_state, graveyard_tickers=graveyard_tickers)

    db = SessionLocal()
    try:
        Trade = models.Trade
        Run = models.Run
        EquitySnapshot = models.EquitySnapshot
        PositionSnapshot = models.PositionSnapshot
        RunEvent = models.RunEvent
        start_dt = _timestamp_to_datetime(start_ts)
        end_dt = _timestamp_to_datetime(end_ts)

        trade_stmt = select(Trade)
        if start_dt is not None and end_dt is not None:
            trade_stmt = trade_stmt.where(or_(Trade.entry_ts.between(start_dt, end_dt), Trade.exit_ts.between(start_dt, end_dt)))
        elif start_dt is not None:
            trade_stmt = trade_stmt.where(or_(Trade.entry_ts >= start_dt, Trade.exit_ts >= start_dt))
        elif end_dt is not None:
            trade_stmt = trade_stmt.where(or_(Trade.entry_ts <= end_dt, Trade.exit_ts <= end_dt))

        run_stmt = select(Run)
        if start_dt is not None and end_dt is not None:
            run_stmt = run_stmt.where(or_(Run.start_ts.between(start_dt, end_dt), Run.end_ts.between(start_dt, end_dt)))
        elif start_dt is not None:
            run_stmt = run_stmt.where(or_(Run.start_ts >= start_dt, Run.end_ts >= start_dt))
        elif end_dt is not None:
            run_stmt = run_stmt.where(or_(Run.start_ts <= end_dt, Run.end_ts <= end_dt))

        equity_stmt = select(EquitySnapshot)
        position_stmt = select(PositionSnapshot)
        event_stmt = select(RunEvent)
        if start_dt is not None:
            equity_stmt = equity_stmt.where(EquitySnapshot.ts >= start_dt)
            position_stmt = position_stmt.where(PositionSnapshot.ts >= start_dt)
            event_stmt = event_stmt.where(RunEvent.ts >= start_dt)
        if end_dt is not None:
            equity_stmt = equity_stmt.where(EquitySnapshot.ts <= end_dt)
            position_stmt = position_stmt.where(PositionSnapshot.ts <= end_dt)
            event_stmt = event_stmt.where(RunEvent.ts <= end_dt)

        return RiskHealthDataBundle(
            trades=tuple(db.execute(trade_stmt).scalars().all()),
            runs=tuple(db.execute(run_stmt).scalars().all()),
            equity_snapshots=tuple(db.execute(equity_stmt).scalars().all()),
            position_snapshots=tuple(db.execute(position_stmt).scalars().all()),
            run_events=tuple(db.execute(event_stmt).scalars().all()),
            pair_state=pair_state,
            graveyard_tickers=graveyard_tickers,
        )
    except Exception:
        return RiskHealthDataBundle(pair_state=pair_state, graveyard_tickers=graveyard_tickers)
    finally:
        try:
            db.close()
        except Exception:
            pass


def _safe_load_pair_state_data() -> tuple[Mapping[str, Any] | None, frozenset[str]]:
    try:
        return _load_pair_state_data()
    except Exception:
        return None, frozenset()


def _state_pairs(pair_state: Mapping[str, Any] | None, key: str) -> list[str]:
    if not isinstance(pair_state, Mapping):
        return []
    section = pair_state.get(key)
    if not isinstance(section, Mapping):
        return []
    return _dedupe_texts(str(pair).strip() for pair in section if str(pair).strip())


def _state_entry_metadata(pair_state: Mapping[str, Any] | None, key: str, pair: Any) -> dict[str, Any]:
    if not isinstance(pair_state, Mapping):
        return {}
    section = pair_state.get(key)
    if not isinstance(section, Mapping):
        return {}
    entry = section.get(pair)
    return dict(entry) if isinstance(entry, Mapping) else {}


def _state_entry_timestamp(pair_state: Mapping[str, Any] | None, key: str, pair: Any) -> int | None:
    entry = _state_entry_metadata(pair_state, key, pair)
    return _first_not_none(
        _coerce_timestamp(entry.get("ts")),
        _coerce_timestamp(entry.get("timestamp")),
        _coerce_timestamp(entry.get("created_at")),
        _coerce_timestamp(entry.get("updated_at")),
    )


def _high_break_risk_pairs(records: Sequence[Any]) -> list[dict[str, Any]]:
    latest_by_pair: dict[str, dict[str, Any]] = {}
    for record in records:
        break_risk = _record_float(record, "break_risk")
        if break_risk is None or break_risk < HIGH_BREAK_RISK_THRESHOLD:
            continue
        pair = _record_pair(record)
        pair_key = pair or "global"
        timestamp = _record_timestamp(record)
        existing = latest_by_pair.get(pair_key)
        if existing is None or (timestamp or 0) >= (existing.get("latest_timestamp") or 0):
            latest_by_pair[pair_key] = _compact(
                {
                    "pair": pair,
                    "break_risk": break_risk,
                    "latest_timestamp": timestamp,
                    "score_source": _normalize_text(_first_not_none(_payload(record).get("score_source"), _get_any(record, "score_source"))),
                }
            )
    return sorted(latest_by_pair.values(), key=lambda row: (row.get("pair") or ""))


def _high_hedge_drift_positions(records: Sequence[Any]) -> list[dict[str, Any]]:
    latest_by_pair: dict[str, dict[str, Any]] = {}
    for record in records:
        drift = _first_not_none(
            _record_float(record, "hedge_ratio_drift_pct"),
            _trade_metadata_float(record, "hedge_ratio_drift_pct"),
        )
        if drift is None or drift < HIGH_HEDGE_DRIFT_THRESHOLD:
            continue
        pair = _record_pair(record)
        pair_key = pair or "global"
        timestamp = _record_timestamp(record)
        existing = latest_by_pair.get(pair_key)
        if existing is None or (timestamp or 0) >= (existing.get("latest_timestamp") or 0):
            latest_by_pair[pair_key] = _compact(
                {
                    "pair": pair,
                    "hedge_ratio_drift_pct": drift,
                    "latest_timestamp": timestamp,
                    "notional_usdt": _record_float(record, "notional_usdt", "open_exposure_usdt"),
                }
            )
    return sorted(latest_by_pair.values(), key=lambda row: (row.get("pair") or ""))


def _liquidity_stress_pairs(records: Sequence[Any]) -> list[dict[str, Any]]:
    latest_by_pair: dict[str, dict[str, Any]] = {}
    for record in records:
        if not _is_liquidity_stress_record(record):
            continue
        pair = _record_pair(record)
        pair_key = pair or "global"
        timestamp = _record_timestamp(record)
        payload = _payload(record)
        existing = latest_by_pair.get(pair_key)
        if existing is None or (timestamp or 0) >= (existing.get("latest_timestamp") or 0):
            latest_by_pair[pair_key] = _compact(
                {
                    "pair": pair,
                    "latest_timestamp": timestamp,
                    "liquidity_score": _record_float(record, "liquidity_score"),
                    "microstructure_risk": _record_float(record, "microstructure_risk"),
                    "metadata": dict(payload),
                }
            )
    return sorted(latest_by_pair.values(), key=lambda row: (row.get("pair") or ""))


def _risk_event(
    *,
    severity: str,
    alert_type: str,
    message: str,
    pair: str | None,
    timestamp: int | None,
    metadata: Mapping[str, Any] | None = None,
) -> RiskEventSummary:
    return RiskEventSummary(
        severity=_normalize_severity(severity),
        type=alert_type,
        message=message,
        pair=pair,
        latest_timestamp=timestamp,
        occurrence_count=1,
        metadata=dict(metadata or {}),
    )


def _merge_alert_payload(target: dict[str, Any], incoming: Mapping[str, Any]) -> None:
    target_count = int(target.get("occurrence_count") or 1)
    incoming_count = int(incoming.get("occurrence_count") or 1)
    target["occurrence_count"] = target_count + incoming_count

    incoming_ts = _coerce_timestamp(incoming.get("latest_timestamp"))
    target_ts = _coerce_timestamp(target.get("latest_timestamp"))
    if target_ts is None or (incoming_ts is not None and incoming_ts >= target_ts):
        target["latest_timestamp"] = incoming.get("latest_timestamp")
        target["message"] = incoming.get("message")
        target["severity"] = _max_severity(target.get("severity"), incoming.get("severity"))
        target["metadata"] = _merge_metadata(target.get("metadata"), incoming.get("metadata"))
    else:
        target["severity"] = _max_severity(target.get("severity"), incoming.get("severity"))
        target["metadata"] = _merge_metadata(incoming.get("metadata"), target.get("metadata"))


def _alert_to_dict(alert: RiskEventSummary | Mapping[str, Any]) -> dict[str, Any]:
    if hasattr(alert, "to_dict") and callable(alert.to_dict):
        payload = alert.to_dict()
    else:
        payload = dict(alert)
    payload["severity"] = _normalize_severity(payload.get("severity"))
    payload["pair"] = _normalize_pair(payload.get("pair"))
    payload["occurrence_count"] = int(payload.get("occurrence_count") or 1)
    payload["metadata"] = dict(payload.get("metadata") or {})
    return payload


def _alert_timestamp(alert: RiskEventSummary | Mapping[str, Any]) -> int | None:
    if hasattr(alert, "latest_timestamp"):
        return _coerce_timestamp(getattr(alert, "latest_timestamp"))
    return _coerce_timestamp(alert.get("latest_timestamp")) if isinstance(alert, Mapping) else None


def _dedup_pair_key(pair: Any) -> str:
    return _normalize_pair(pair) or "global"


def _merge_metadata(first: Any, second: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(first, Mapping):
        merged.update(first)
    if isinstance(second, Mapping):
        merged.update(second)
    return merged


def _normalize_severity(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text == "warn":
        text = "warning"
    return text if text in {"info", "warning", "error", "critical"} else "info"


def _max_severity(first: Any, second: Any) -> str:
    rank = {"info": 0, "warning": 1, "error": 2, "critical": 3}
    first_text = _normalize_severity(first)
    second_text = _normalize_severity(second)
    return first_text if rank[first_text] >= rank[second_text] else second_text


def _latest_record_float(records: Sequence[Any], *keys: str) -> float | None:
    latest_record = None
    latest_ts = None
    latest_value = None
    for record in records:
        value = _record_float(record, *keys)
        timestamp = _record_timestamp(record)
        if value is None:
            continue
        if latest_ts is None or (timestamp or 0) >= latest_ts:
            latest_record = record
            latest_ts = timestamp or 0
            latest_value = value
    return latest_value if latest_record is not None else None


def _latest_orphan_desync_status(records: Sequence[Any]) -> str | None:
    latest_record = _latest_by_timestamp(
        tuple(record for record in records if _is_orphan_position_record(record) or _is_leg_desync_record(record)),
        "ts",
        "timestamp",
    )
    if latest_record is None:
        return None
    payload = _payload(latest_record)
    return _normalize_text(
        _first_not_none(
            payload.get("orphan_desync_status"),
            payload.get("status"),
            payload.get("reason"),
            _event_type(latest_record),
        )
    )


def _record_float(record: Any, *keys: str) -> float | None:
    payload = _payload(record)
    metadata = _get_any(record, "metadata")
    for key in keys:
        value = _finite_float(_get_any(record, key))
        if value is not None:
            return value
        value = _finite_float(payload.get(key))
        if value is not None:
            return value
        if isinstance(metadata, Mapping):
            value = _finite_float(metadata.get(key))
            if value is not None:
                return value
    return None


def _record_pair(record: Any) -> str | None:
    payload = _payload(record)
    return _normalize_pair(
        _first_not_none(
            _get_any(record, "pair_key", "pair"),
            payload.get("pair"),
            payload.get("pair_key"),
            payload.get("current_pair"),
            payload.get("active_pair"),
        )
    )


def _record_timestamp(record: Any) -> int | None:
    payload = _payload(record)
    return _first_not_none(
        _coerce_timestamp(_get_any(record, "timestamp", "ts", "created_at")),
        _trade_timestamp(record),
        _coerce_timestamp(payload.get("timestamp") or payload.get("ts") or payload.get("created_at")),
    )


def _latest_by_timestamp(records: Sequence[Any], *timestamp_keys: str) -> Any | None:
    keys = timestamp_keys or ("timestamp", "ts", "created_at")
    best_record = None
    best_ts = None
    for record in records:
        timestamp = _coerce_timestamp(_get_any(record, *keys)) or _record_timestamp(record)
        if timestamp is None:
            continue
        if best_ts is None or timestamp >= best_ts:
            best_ts = timestamp
            best_record = record
    return best_record


def _event_type(record: Any) -> str:
    return str(_first_not_none(_get_any(record, "event_type", "type"), _payload(record).get("event_type")) or "").strip().lower()


def _is_order_failure_record(record: Any) -> bool:
    event_type = _event_type(record)
    payload = _payload(record)
    return any(token in event_type for token in ("order_failure", "order_error", "order_reject")) or bool(
        payload.get("order_failure") or payload.get("order_error") or payload.get("recent_order_failures")
    )


def _is_api_failure_record(record: Any) -> bool:
    event_type = _event_type(record)
    payload = _payload(record)
    return any(token in event_type for token in ("api_error", "api_failure", "api_timeout")) or bool(
        payload.get("api_error") or payload.get("api_failure") or payload.get("api_timeout")
    )


def _is_orderbook_stale_record(record: Any) -> bool:
    event_type = _event_type(record)
    payload = _payload(record)
    return "orderbook_stale" in event_type or bool(
        payload.get("orderbook_stale") or payload.get("stale_orderbook") or payload.get("is_orderbook_stale")
    )


def _is_liquidity_stress_record(record: Any) -> bool:
    event_type = _event_type(record)
    payload = _payload(record)
    liquidity_score = _record_float(record, "liquidity_score")
    return (
        "liquidity_stress" in event_type
        or bool(payload.get("liquidity_stress"))
        or (liquidity_score is not None and liquidity_score <= LIQUIDITY_STRESS_SCORE_THRESHOLD and bool(payload.get("liquidity_score_is_stress")))
    )


def _is_orphan_position_record(record: Any) -> bool:
    event_type = _event_type(record)
    payload = _payload(record)
    return "orphan_position" in event_type or bool(payload.get("orphan_position") or payload.get("orphan_leg"))


def _is_leg_desync_record(record: Any) -> bool:
    event_type = _event_type(record)
    payload = _payload(record)
    return "leg_desync" in event_type or "position_desync" in event_type or bool(payload.get("leg_desync") or payload.get("position_desync"))


def _is_drawdown_threshold_record(record: Any) -> bool:
    event_type = _event_type(record)
    payload = _payload(record)
    return "drawdown_threshold" in event_type or bool(payload.get("drawdown_threshold_near"))


def _consecutive_losses(trades: Sequence[Any]) -> dict[str, Any]:
    ordered = sorted(trades, key=lambda trade: _trade_timestamp(trade) or 0)
    count = 0
    latest_timestamp = None
    for trade in reversed(ordered):
        pnl = _finite_float(_get_any(trade, "pnl_usdt", "pnl"))
        if pnl is None:
            continue
        if pnl < 0:
            count += 1
            latest_timestamp = latest_timestamp or _trade_timestamp(trade)
            continue
        break
    return {"count": count, "latest_timestamp": latest_timestamp}


def _sum_optional(values: Sequence[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _dedupe_texts(values: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        rows.append(text)
    return sorted(rows)


def _compact(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _normalize_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


__all__ = [
    "DEFAULT_ALERT_DEDUP_WINDOW_MINUTES",
    "HIGH_BREAK_RISK_THRESHOLD",
    "RISK_HEALTH_CACHE_TTL_SECONDS",
    "RiskHealthDataBundle",
    "build_alerts",
    "build_bot_status",
    "build_pair_health",
    "build_risk_kpis",
    "clear_risk_health_cache",
    "deduplicate_alerts",
    "get_cached_or_compute",
    "get_risk_health_dashboard",
]
