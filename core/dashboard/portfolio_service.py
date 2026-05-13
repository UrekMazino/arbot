"""Read-only Portfolio Dashboard service.

The service aggregates stored database/event data into dashboard DTO-shaped
payloads. It never calls order execution, mutating bot controls, strategy
logic, or live ML runtimes.
"""

from __future__ import annotations

import copy
import math
import sys
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from core.dashboard.contracts import DashboardCacheMeta, PortfolioSummary


PORTFOLIO_CACHE_TTL_SECONDS = 60


@dataclass(frozen=True)
class PortfolioDataBundle:
    trades: tuple[Any, ...] = ()
    runs: tuple[Any, ...] = ()
    equity_snapshots: tuple[Any, ...] = ()
    position_snapshots: tuple[Any, ...] = ()
    heartbeat_events: tuple[Any, ...] = ()


_CACHE: dict[tuple[int | None, int | None], tuple[float, dict[str, Any]]] = {}


def get_portfolio_dashboard(
    start_ts: int | float | datetime | str | None = None,
    end_ts: int | float | datetime | str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Return a JSON-safe Portfolio Dashboard payload."""

    return get_cached_or_compute(start_ts=start_ts, end_ts=end_ts, refresh=refresh)


def get_cached_or_compute(
    *,
    start_ts: int | float | datetime | str | None = None,
    end_ts: int | float | datetime | str | None = None,
    refresh: bool = False,
    ttl_seconds: int = PORTFOLIO_CACHE_TTL_SECONDS,
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

    payload = _compute_portfolio_dashboard(
        start_ts=start_value,
        end_ts=end_value,
        generated_at=now,
        ttl_seconds=ttl_seconds,
    )
    _CACHE[cache_key] = (now + max(int(ttl_seconds), 30), copy.deepcopy(payload))
    return payload


def compute_portfolio_summary(
    *,
    trades: Sequence[Any] = (),
    runs: Sequence[Any] = (),
    equity_snapshots: Sequence[Any] = (),
    position_snapshots: Sequence[Any] = (),
    heartbeat_events: Sequence[Any] = (),
    equity_curve: Sequence[Mapping[str, Any]] = (),
    drawdown_curve: Sequence[Mapping[str, Any]] = (),
    cache: DashboardCacheMeta | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    closed_trades = [
        trade
        for trade in trades
        if _coerce_timestamp(_get_any(trade, "exit_ts", "exit_time", "exit_timestamp")) is not None
    ]
    pnl_values = [_finite_float(_get_any(trade, "pnl_usdt", "pnl")) for trade in closed_trades]
    pnl_values = [value for value in pnl_values if value is not None]
    wins = sum(1 for value in pnl_values if value > 0)
    losses = sum(1 for value in pnl_values if value < 0)
    gross_profit = sum(value for value in pnl_values if value > 0)
    gross_loss = abs(sum(value for value in pnl_values if value < 0))

    latest_equity_point = equity_curve[-1] if equity_curve else None
    latest_snapshot = _latest_by_timestamp(equity_snapshots, "ts", "timestamp")
    latest_run = _latest_by_timestamp(runs, "end_ts", "updated_at", "start_ts")
    latest_heartbeat = _latest_by_timestamp(heartbeat_events, "ts", "timestamp")
    latest_heartbeat_payload = _payload(latest_heartbeat)

    open_positions = _open_positions(position_snapshots)
    open_exposure = _sum_optional(
        _finite_float(position.get("notional_usdt"))
        for position in (open_positions or ())
    )
    unrealized_pnl = _latest_unrealized_pnl(
        position_snapshots=position_snapshots,
        latest_snapshot=latest_snapshot,
        latest_heartbeat_payload=latest_heartbeat_payload,
    )
    session_pnl = _first_not_none(
        _finite_float(_get_any(latest_snapshot, "session_pnl_usdt", "session_pnl")),
        _finite_float(_get_any(latest_run, "session_pnl", "session_pnl_usdt")),
        _finite_float(latest_heartbeat_payload.get("session_pnl_usdt")),
    )
    active_pair = (
        _normalize_text(_get_any(latest_snapshot, "current_pair", "active_pair"))
        or _normalize_text(latest_heartbeat_payload.get("current_pair") or latest_heartbeat_payload.get("pair"))
    )
    bot_status = _normalize_text(_get_any(latest_run, "status")) or _normalize_text(latest_heartbeat_payload.get("status"))
    drawdowns = [_finite_float(point.get("drawdown_usdt")) for point in drawdown_curve]
    drawdowns = [value for value in drawdowns if value is not None]

    summary = PortfolioSummary(
        total_equity_usdt=_finite_float(latest_equity_point.get("equity_usdt")) if latest_equity_point else None,
        session_pnl_usdt=session_pnl,
        realized_pnl_usdt=sum(pnl_values) if pnl_values else None,
        unrealized_pnl_usdt=unrealized_pnl,
        win_rate=(wins / len(pnl_values)) if pnl_values else None,
        profit_factor=(gross_profit / gross_loss) if gross_loss > 0 else None,
        max_drawdown_usdt=min(drawdowns) if drawdowns else None,
        open_positions=open_positions,
        active_pair=active_pair,
        bot_status=bot_status,
        open_exposure_usdt=open_exposure,
        cache=cache or DashboardCacheMeta(ttl_seconds=PORTFOLIO_CACHE_TTL_SECONDS),
    )
    payload = summary.to_dict()
    payload.pop("cache", None)
    return payload


def build_equity_curve(equity_snapshots: Sequence[Any] = ()) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for snapshot in equity_snapshots:
        timestamp = _coerce_timestamp(_get_any(snapshot, "ts", "timestamp"))
        equity = _finite_float(_get_any(snapshot, "equity_usdt", "equity"))
        if timestamp is None or equity is None:
            continue
        points.append(
            _compact(
                {
                    "timestamp": timestamp,
                    "equity_usdt": equity,
                    "session_pnl_usdt": _finite_float(_get_any(snapshot, "session_pnl_usdt", "session_pnl")),
                    "source": _normalize_text(_get_any(snapshot, "source")),
                    "run_id": _normalize_text(_get_any(snapshot, "run_id")),
                    "current_pair": _normalize_text(_get_any(snapshot, "current_pair")),
                }
            )
        )
    return sorted(points, key=lambda point: float(point["timestamp"]))


def build_daily_pnl(trades: Sequence[Any] = ()) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {"date": "", "pnl_usdt": 0.0, "trade_count": 0})
    for trade in trades:
        exit_timestamp = _coerce_timestamp(_get_any(trade, "exit_ts", "exit_time", "exit_timestamp"))
        pnl = _finite_float(_get_any(trade, "pnl_usdt", "pnl"))
        if exit_timestamp is None or pnl is None:
            continue
        day = datetime.fromtimestamp(exit_timestamp, timezone.utc).date().isoformat()
        buckets[day]["date"] = day
        buckets[day]["pnl_usdt"] += pnl
        buckets[day]["trade_count"] += 1
    return [buckets[key] for key in sorted(buckets)]


def build_drawdown_curve(equity_curve: Sequence[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    peak: float | None = None
    rows: list[dict[str, Any]] = []
    for point in equity_curve:
        timestamp = _coerce_timestamp(point.get("timestamp"))
        equity = _finite_float(point.get("equity_usdt"))
        if timestamp is None or equity is None:
            continue
        peak = equity if peak is None else max(peak, equity)
        drawdown = equity - peak
        rows.append(
            {
                "timestamp": timestamp,
                "equity_usdt": equity,
                "peak_equity_usdt": peak,
                "drawdown_usdt": drawdown,
                "drawdown_pct": (drawdown / peak) if peak else None,
            }
        )
    return rows


def build_open_exposure(position_snapshots: Sequence[Any] = ()) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for snapshot in position_snapshots:
        timestamp = _coerce_timestamp(_get_any(snapshot, "ts", "timestamp"))
        notional = _finite_float(_get_any(snapshot, "notional_usdt", "open_exposure_usdt"))
        if timestamp is None or notional is None:
            continue
        rows.append(
            _compact(
                {
                    "timestamp": timestamp,
                    "pair": _normalize_text(_get_any(snapshot, "pair_key", "pair")),
                    "open_exposure_usdt": notional,
                    "unrealized_pnl_usdt": _finite_float(_get_any(snapshot, "unrealized_pnl_usdt")),
                }
            )
        )
    return sorted(rows, key=lambda row: float(row["timestamp"]))


def find_pair_highlights(
    *,
    trades: Sequence[Any] = (),
    equity_snapshots: Sequence[Any] = (),
    heartbeat_events: Sequence[Any] = (),
) -> dict[str, Any]:
    pnl_by_pair: dict[str, float] = defaultdict(float)
    trades_by_pair: dict[str, int] = defaultdict(int)
    for trade in trades:
        pair = _normalize_text(_get_any(trade, "pair_key", "pair"))
        pnl = _finite_float(_get_any(trade, "pnl_usdt", "pnl"))
        if not pair:
            continue
        trades_by_pair[pair] += 1
        if pnl is not None:
            pnl_by_pair[pair] += pnl

    latest_snapshot = _latest_by_timestamp(equity_snapshots, "ts", "timestamp")
    latest_heartbeat = _latest_by_timestamp(heartbeat_events, "ts", "timestamp")
    latest_heartbeat_payload = _payload(latest_heartbeat)
    regime = (
        _normalize_text(_get_any(latest_snapshot, "regime"))
        or _normalize_text(latest_heartbeat_payload.get("regime"))
    )

    return {
        "best_performing_pair": max(pnl_by_pair, key=pnl_by_pair.get) if pnl_by_pair else None,
        "worst_performing_pair": min(pnl_by_pair, key=pnl_by_pair.get) if pnl_by_pair else None,
        "most_traded_pair": max(trades_by_pair, key=trades_by_pair.get) if trades_by_pair else None,
        "highest_drawdown_pair": None,
        "current_regime_state": regime,
        "current_risk_level": None,
    }


def clear_portfolio_dashboard_cache() -> None:
    _CACHE.clear()


def _compute_portfolio_dashboard(
    *,
    start_ts: int | None,
    end_ts: int | None,
    generated_at: float,
    ttl_seconds: int,
) -> dict[str, Any]:
    bundle = _load_portfolio_data(start_ts=start_ts, end_ts=end_ts)
    equity_curve = build_equity_curve(bundle.equity_snapshots)
    drawdown_curve = build_drawdown_curve(equity_curve)
    cache = DashboardCacheMeta(
        cache_hit=False,
        generated_at=generated_at,
        ttl_seconds=ttl_seconds,
        refresh_supported=True,
    )
    return {
        "summary": compute_portfolio_summary(
            trades=bundle.trades,
            runs=bundle.runs,
            equity_snapshots=bundle.equity_snapshots,
            position_snapshots=bundle.position_snapshots,
            heartbeat_events=bundle.heartbeat_events,
            equity_curve=equity_curve,
            drawdown_curve=drawdown_curve,
            cache=cache,
        ),
        "charts": {
            "equity_curve": equity_curve,
            "daily_pnl": build_daily_pnl(bundle.trades),
            "drawdown_curve": drawdown_curve,
            "open_exposure": build_open_exposure(bundle.position_snapshots),
        },
        "highlights": find_pair_highlights(
            trades=bundle.trades,
            equity_snapshots=bundle.equity_snapshots,
            heartbeat_events=bundle.heartbeat_events,
        ),
        "cache": cache.to_dict(),
    }


def _load_portfolio_data(start_ts: int | None, end_ts: int | None) -> PortfolioDataBundle:
    """Load read-only Platform database rows when available."""

    try:
        SessionLocal, models, select, or_ = _platform_database_bundle()
    except Exception:
        return PortfolioDataBundle()

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
            trade_stmt = trade_stmt.where(
                or_(
                    Trade.entry_ts.between(start_dt, end_dt),
                    Trade.exit_ts.between(start_dt, end_dt),
                )
            )
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
        heartbeat_stmt = select(RunEvent).where(RunEvent.event_type == "heartbeat")
        if start_dt is not None:
            equity_stmt = equity_stmt.where(EquitySnapshot.ts >= start_dt)
            position_stmt = position_stmt.where(PositionSnapshot.ts >= start_dt)
            heartbeat_stmt = heartbeat_stmt.where(RunEvent.ts >= start_dt)
        if end_dt is not None:
            equity_stmt = equity_stmt.where(EquitySnapshot.ts <= end_dt)
            position_stmt = position_stmt.where(PositionSnapshot.ts <= end_dt)
            heartbeat_stmt = heartbeat_stmt.where(RunEvent.ts <= end_dt)

        return PortfolioDataBundle(
            trades=tuple(db.execute(trade_stmt).scalars().all()),
            runs=tuple(db.execute(run_stmt).scalars().all()),
            equity_snapshots=tuple(db.execute(equity_stmt).scalars().all()),
            position_snapshots=tuple(db.execute(position_stmt).scalars().all()),
            heartbeat_events=tuple(db.execute(heartbeat_stmt).scalars().all()),
        )
    except Exception:
        return PortfolioDataBundle()
    finally:
        try:
            db.close()
        except Exception:
            pass


def _platform_database_bundle() -> tuple[Any, Any, Any, Any]:
    repo_root = Path(__file__).resolve().parents[2]
    platform_root = repo_root / "Platform" / "api"
    if str(platform_root) not in sys.path:
        sys.path.append(str(platform_root))
    from sqlalchemy import or_, select

    from app import models
    from app.database import SessionLocal

    return SessionLocal, models, select, or_


def _open_positions(position_snapshots: Sequence[Any]) -> list[dict[str, Any]] | None:
    latest_by_pair: dict[str, Any] = {}
    for snapshot in position_snapshots:
        pair = _normalize_text(_get_any(snapshot, "pair_key", "pair"))
        timestamp = _coerce_timestamp(_get_any(snapshot, "ts", "timestamp"))
        notional = _finite_float(_get_any(snapshot, "notional_usdt", "open_exposure_usdt"))
        if not pair or timestamp is None or notional is None or notional <= 0:
            continue
        existing = latest_by_pair.get(pair)
        existing_ts = _coerce_timestamp(_get_any(existing, "ts", "timestamp")) if existing is not None else None
        if existing_ts is None or timestamp >= existing_ts:
            latest_by_pair[pair] = snapshot

    rows = []
    for pair, snapshot in sorted(latest_by_pair.items()):
        rows.append(
            _compact(
                {
                    "pair": pair,
                    "timestamp": _coerce_timestamp(_get_any(snapshot, "ts", "timestamp")),
                    "notional_usdt": _finite_float(_get_any(snapshot, "notional_usdt", "open_exposure_usdt")),
                    "unrealized_pnl_usdt": _finite_float(_get_any(snapshot, "unrealized_pnl_usdt")),
                    "entry_z": _finite_float(_get_any(snapshot, "entry_z")),
                    "current_z": _finite_float(_get_any(snapshot, "current_z")),
                    "hold_minutes": _finite_float(_get_any(snapshot, "hold_minutes")),
                }
            )
        )
    return rows or None


def _latest_unrealized_pnl(
    *,
    position_snapshots: Sequence[Any],
    latest_snapshot: Any,
    latest_heartbeat_payload: Mapping[str, Any],
) -> float | None:
    open_positions = _open_positions(position_snapshots)
    position_sum = _sum_optional(
        _finite_float(position.get("unrealized_pnl_usdt"))
        for position in (open_positions or ())
    )
    if position_sum is not None:
        return position_sum
    return _first_not_none(
        _finite_float(_get_any(latest_snapshot, "unrealized_pnl_usdt")),
        _finite_float(latest_heartbeat_payload.get("unrealized_pnl_usdt")),
    )


def _latest_by_timestamp(records: Sequence[Any], *timestamp_keys: str) -> Any | None:
    best_record = None
    best_ts = None
    for record in records:
        timestamp = _coerce_timestamp(_get_any(record, *timestamp_keys))
        if timestamp is None:
            continue
        if best_ts is None or timestamp >= best_ts:
            best_ts = timestamp
            best_record = record
    return best_record


def _payload(record: Any) -> Mapping[str, Any]:
    payload = _get_any(record, "payload_json", "payload")
    return payload if isinstance(payload, Mapping) else {}


def _sum_optional(values: Iterable[float | None]) -> float | None:
    total = 0.0
    count = 0
    for value in values:
        if value is None:
            continue
        total += value
        count += 1
    return total if count else None


def _first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _compact(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _get_any(record: Any, *keys: str) -> Any:
    if record is None:
        return None
    for key in keys:
        if isinstance(record, Mapping) and key in record:
            value = record[key]
            if value is not None:
                return value
        if not isinstance(record, Mapping) and hasattr(record, key):
            value = getattr(record, key)
            if value is not None:
                return value
    return None


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _normalize_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _coerce_timestamp(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    if isinstance(value, date):
        return int(datetime(value.year, value.month, value.day, tzinfo=timezone.utc).timestamp())
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    if not math.isfinite(numeric):
        return None
    if numeric > 10_000_000_000:
        numeric /= 1000.0
    return int(numeric)


def _timestamp_to_datetime(value: int | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, timezone.utc)


__all__ = [
    "PORTFOLIO_CACHE_TTL_SECONDS",
    "PortfolioDataBundle",
    "build_daily_pnl",
    "build_drawdown_curve",
    "build_equity_curve",
    "build_open_exposure",
    "clear_portfolio_dashboard_cache",
    "compute_portfolio_summary",
    "find_pair_highlights",
    "get_cached_or_compute",
    "get_portfolio_dashboard",
]
