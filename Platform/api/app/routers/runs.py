from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from ..deps import get_db_session, require_permissions
from ..models import Alert, BotConfig, EquitySnapshot, RegimeMetric, Report, ReportFile, Run, RunEvent, StrategyMetric, Trade
from ..schemas import RunEventOut, RunOut, RunPairSegmentOut, TradeOut
from ..services.run_pair_segments import list_run_pair_history_rows

router = APIRouter(prefix="/runs", tags=["runs"])

PORTFOLIO_RANGE_WINDOWS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}
PORTFOLIO_BUCKETS = {"auto", "raw", "hour", "day", "week"}


def _coerce_float(value):
    if value is None:
        return None
    return float(value)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_portfolio_range(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in PORTFOLIO_RANGE_WINDOWS or normalized == "all":
        return normalized
    return "7d"


def _normalize_portfolio_bucket(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in PORTFOLIO_BUCKETS:
        return normalized
    return "auto"


def _auto_portfolio_bucket(range_key: str, points: list[dict]) -> str:
    if range_key == "24h":
        return "raw"
    if range_key == "7d":
        return "hour"
    if range_key in {"30d", "90d"}:
        return "day"
    if len(points) < 2:
        return "day"
    first_ts = points[0]["ts"]
    last_ts = points[-1]["ts"]
    span_days = max((last_ts - first_ts).total_seconds() / 86400.0, 0.0)
    return "week" if span_days > 120 else "day"


def _bucket_start(value: datetime, bucket: str) -> datetime:
    value = _as_utc(value) or datetime.now(timezone.utc)
    if bucket == "hour":
        return value.replace(minute=0, second=0, microsecond=0)
    if bucket == "day":
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    if bucket == "week":
        day_start = value.replace(hour=0, minute=0, second=0, microsecond=0)
        return day_start - timedelta(days=day_start.weekday())
    return value


def _finish_portfolio_points(points: list[dict], *, baseline: float | None = None) -> list[dict]:
    if not points:
        return []
    baseline_equity = points[0]["equity"] if baseline is None else baseline
    peak = points[0]["equity"]
    output = []
    for point in points:
        equity = point["equity"]
        drawdown_peak = _coerce_float(point.get("_drawdown_peak"))
        peak = max(peak, equity, drawdown_peak if drawdown_peak is not None else equity)
        pnl_usdt = equity - baseline_equity
        drawdown = equity - peak
        output.append(
            {
                "ts": point["ts"].isoformat(),
                "equity": equity,
                "pnl_usdt": pnl_usdt,
                "pnl_pct": (pnl_usdt / baseline_equity * 100.0) if baseline_equity else None,
                "drawdown": drawdown,
                "drawdown_pct": (drawdown / peak * 100.0) if peak else None,
                "run_id": point.get("run_id"),
                "run_key": point.get("run_key"),
                "source": point.get("source"),
                "samples": int(point.get("samples") or 1),
            }
        )
    return output


def _status_rank(status_text: str) -> int:
    if status_text == "fail":
        return 3
    if status_text == "warn":
        return 2
    if status_text == "unknown":
        return 1
    return 0


def _safe_file_info(path_text: str) -> tuple[Path | None, str | None]:
    if not path_text:
        return None, "path missing"
    try:
        path_obj = Path(path_text)
        resolved = path_obj.resolve()
    except Exception:
        return None, "invalid path"
    allowed_root = Path("/workspace").resolve()
    if not str(resolved).startswith(str(allowed_root)):
        return None, "path outside allowed root"
    if not resolved.exists() or not resolved.is_file():
        return None, "file missing"
    return resolved, None


def _get_run_or_404(db: Session, run_id: str) -> Run:
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.get("", response_model=list[RunOut])
def list_runs(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: object = Depends(require_permissions("view_dashboard")),
    db: Session = Depends(get_db_session),
):
    stmt = select(Run).order_by(Run.start_ts.desc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


@router.get("/portfolio/equity-curve")
def portfolio_equity_curve(
    range_key: str = Query(default="7d", alias="range"),
    bucket_key: str = Query(default="auto", alias="bucket"),
    max_points: int = Query(default=2000, ge=100, le=10000),
    _: object = Depends(require_permissions("view_portfolio")),
    db: Session = Depends(get_db_session),
):
    normalized_range = _normalize_portfolio_range(range_key)
    requested_bucket = _normalize_portfolio_bucket(bucket_key)
    now = datetime.now(timezone.utc)
    since = None
    if normalized_range != "all":
        since = now - PORTFOLIO_RANGE_WINDOWS[normalized_range]

    raw_points: list[dict] = []
    runs_stmt = select(Run)
    if since is not None:
        runs_stmt = runs_stmt.where(
            or_(
                Run.start_ts >= since,
                Run.end_ts >= since,
                Run.status == "running",
            )
        )
    runs_by_id = {row.id: row for row in db.execute(runs_stmt).scalars().all()}

    snapshot_stmt = (
        select(EquitySnapshot, Run.run_key)
        .join(Run, EquitySnapshot.run_id == Run.id)
        .order_by(EquitySnapshot.ts.asc(), EquitySnapshot.created_at.asc(), EquitySnapshot.id.asc())
    )
    if since is not None:
        snapshot_stmt = snapshot_stmt.where(EquitySnapshot.ts >= since)
    equity_snapshot_rows = db.execute(snapshot_stmt).all()
    snapshot_run_ids: set[str] = set()
    for snapshot_row, run_key in equity_snapshot_rows:
        equity = _coerce_float(snapshot_row.equity_usdt)
        ts_value = _as_utc(snapshot_row.ts)
        if equity is None or ts_value is None:
            continue
        snapshot_run_ids.add(snapshot_row.run_id)
        raw_points.append(
            {
                "ts": ts_value,
                "equity": equity,
                "run_id": snapshot_row.run_id,
                "run_key": run_key,
                "source": snapshot_row.source,
                "samples": 1,
            }
        )

    if equity_snapshot_rows:
        for run in runs_by_id.values():
            if run.id in snapshot_run_ids:
                continue
            start_ts = _as_utc(run.start_ts)
            start_equity = _coerce_float(run.start_equity)
            if start_ts is not None and start_equity is not None and (since is None or start_ts >= since):
                raw_points.append(
                    {
                        "ts": start_ts,
                        "equity": start_equity,
                        "run_id": run.id,
                        "run_key": run.run_key,
                        "source": "run_start_fallback",
                        "samples": 1,
                    }
                )

            end_ts = _as_utc(run.end_ts)
            end_equity = _coerce_float(run.end_equity)
            if end_ts is not None and end_equity is not None and (since is None or end_ts >= since):
                raw_points.append(
                    {
                        "ts": end_ts,
                        "equity": end_equity,
                        "run_id": run.id,
                        "run_key": run.run_key,
                        "source": "run_end_fallback",
                        "samples": 1,
                    }
                )

    if not equity_snapshot_rows:
        for run in runs_by_id.values():
            start_ts = _as_utc(run.start_ts)
            start_equity = _coerce_float(run.start_equity)
            if start_ts is not None and start_equity is not None and (since is None or start_ts >= since):
                raw_points.append(
                    {
                        "ts": start_ts,
                        "equity": start_equity,
                        "run_id": run.id,
                        "run_key": run.run_key,
                        "source": "run_start_fallback",
                        "samples": 1,
                    }
                )

            end_ts = _as_utc(run.end_ts)
            end_equity = _coerce_float(run.end_equity)
            if end_ts is not None and end_equity is not None and (since is None or end_ts >= since):
                raw_points.append(
                    {
                        "ts": end_ts,
                        "equity": end_equity,
                        "run_id": run.id,
                        "run_key": run.run_key,
                        "source": "run_end_fallback",
                        "samples": 1,
                    }
                )

        heartbeat_stmt = (
            select(RunEvent, Run.run_key)
            .join(Run, RunEvent.run_id == Run.id)
            .where(RunEvent.event_type == "heartbeat")
            .order_by(RunEvent.ts.asc(), RunEvent.created_at.asc(), RunEvent.id.asc())
        )
        if since is not None:
            heartbeat_stmt = heartbeat_stmt.where(RunEvent.ts >= since)
        heartbeat_rows = db.execute(heartbeat_stmt).all()
        for event_row, run_key in heartbeat_rows:
            payload = event_row.payload_json if isinstance(event_row.payload_json, dict) else {}
            equity = _coerce_float(payload.get("equity_usdt"))
            ts_value = _as_utc(event_row.ts)
            if equity is None or ts_value is None:
                continue
            raw_points.append(
                {
                    "ts": ts_value,
                    "equity": equity,
                    "run_id": event_row.run_id,
                    "run_key": run_key,
                    "source": "heartbeat_fallback",
                    "samples": 1,
                }
            )

    raw_points.sort(key=lambda point: (point["ts"], str(point.get("run_key") or ""), str(point.get("source") or "")))
    raw_run_keys = {
        str(point.get("run_key") or "").strip()
        for point in raw_points
        if str(point.get("run_key") or "").strip()
    }
    actual_bucket = _auto_portfolio_bucket(normalized_range, raw_points) if requested_bucket == "auto" else requested_bucket

    if actual_bucket == "raw":
        chart_points = raw_points[-max_points:] if len(raw_points) > max_points else raw_points
    else:
        buckets: dict[datetime, dict] = {}
        for point in raw_points:
            bucket_ts = _bucket_start(point["ts"], actual_bucket)
            existing = buckets.get(bucket_ts)
            if existing is None:
                buckets[bucket_ts] = {**point, "ts": bucket_ts, "samples": int(point.get("samples") or 1)}
                continue
            existing["samples"] = int(existing.get("samples") or 0) + int(point.get("samples") or 1)
            if point["ts"] >= existing.get("_last_sample_ts", existing["ts"]):
                existing.update({**point, "ts": bucket_ts, "samples": existing["samples"], "_last_sample_ts": point["ts"]})
        chart_points = sorted(buckets.values(), key=lambda point: point["ts"])
        if len(chart_points) > max_points:
            chart_points = chart_points[-max_points:]
        for point in chart_points:
            point.pop("_last_sample_ts", None)
        running_peak = None
        peak_by_bucket: dict[datetime, float] = {}
        for point in raw_points:
            equity = point["equity"]
            running_peak = equity if running_peak is None else max(running_peak, equity)
            peak_by_bucket[_bucket_start(point["ts"], actual_bucket)] = running_peak
        for point in chart_points:
            bucket_peak = peak_by_bucket.get(point["ts"])
            if bucket_peak is not None:
                point["_drawdown_peak"] = bucket_peak

    raw_finished_points = _finish_portfolio_points(raw_points)
    raw_start_equity = raw_points[0]["equity"] if raw_points else None
    points = _finish_portfolio_points(chart_points, baseline=raw_start_equity)
    raw_equities = [point["equity"] for point in raw_finished_points]
    raw_pnl_values = [point["pnl_usdt"] for point in raw_finished_points]
    raw_drawdowns = [point["drawdown"] for point in raw_finished_points]
    raw_drawdown_pcts = [
        point["drawdown_pct"]
        for point in raw_finished_points
        if point["drawdown_pct"] is not None
    ]
    start_equity = raw_equities[0] if raw_equities else None
    end_equity = raw_equities[-1] if raw_equities else None
    change_usdt = (end_equity - start_equity) if start_equity is not None and end_equity is not None else None
    start_ts = raw_finished_points[0]["ts"] if raw_finished_points else None
    end_ts = raw_finished_points[-1]["ts"] if raw_finished_points else None

    return {
        "range": normalized_range,
        "bucket": actual_bucket,
        "requested_bucket": requested_bucket,
        "source": "equity_snapshots" if equity_snapshot_rows else "event_fallback",
        "generated_at": now.isoformat(),
        "points": points,
        "stats": {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "start_equity": start_equity,
            "end_equity": end_equity,
            "change_usdt": change_usdt,
            "change_pct": (change_usdt / start_equity * 100.0) if change_usdt is not None and start_equity else None,
            "min_equity": min(raw_equities) if raw_equities else None,
            "max_equity": max(raw_equities) if raw_equities else None,
            "max_drawdown": min(raw_drawdowns) if raw_drawdowns else None,
            "max_drawdown_pct": min(raw_drawdown_pcts) if raw_drawdown_pcts else None,
            "point_count": len(points),
            "raw_point_count": len(raw_points),
            "run_count": len(raw_run_keys),
            "latest_pnl_usdt": raw_pnl_values[-1] if raw_pnl_values else None,
        },
    }


@router.get("/{run_id}", response_model=RunOut)
def get_run(
    run_id: str,
    _: object = Depends(require_permissions("view_dashboard")),
    db: Session = Depends(get_db_session),
):
    return _get_run_or_404(db, run_id)


@router.get("/{run_id}/events", response_model=list[RunEventOut])
def list_run_events(
    run_id: str,
    limit: int = Query(default=500, ge=1, le=2000),
    _: object = Depends(require_permissions("view_dashboard")),
    db: Session = Depends(get_db_session),
):
    _get_run_or_404(db, run_id)
    stmt = (
        select(RunEvent)
        .where(RunEvent.run_id == run_id)
        .order_by(RunEvent.ts.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


@router.get("/{run_id}/pair-segments", response_model=list[RunPairSegmentOut])
def list_run_pair_segments(
    run_id: str,
    _: object = Depends(require_permissions("view_dashboard")),
    db: Session = Depends(get_db_session),
):
    run = _get_run_or_404(db, run_id)
    return list_run_pair_history_rows(db, run, ensure_backfilled=True)


@router.get("/{run_id}/trades", response_model=list[TradeOut])
def list_run_trades(
    run_id: str,
    limit: int = Query(default=1000, ge=1, le=5000),
    _: object = Depends(require_permissions("view_dashboard")),
    db: Session = Depends(get_db_session),
):
    _get_run_or_404(db, run_id)
    stmt = (
        select(Trade)
        .where(Trade.run_id == run_id)
        .order_by(Trade.exit_ts.desc().nullslast())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


@router.get("/{run_id}/metrics/strategy")
def strategy_metrics(
    run_id: str,
    _: object = Depends(require_permissions("view_dashboard")),
    db: Session = Depends(get_db_session),
):
    _get_run_or_404(db, run_id)
    stmt = select(StrategyMetric).where(StrategyMetric.run_id == run_id).order_by(StrategyMetric.strategy.asc())
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "strategy": row.strategy,
            "trades": row.trades,
            "wins": row.wins,
            "losses": row.losses,
            "win_rate_pct": row.win_rate_pct,
            "pnl_usdt": float(row.pnl_usdt) if row.pnl_usdt is not None else None,
            "avg_hold_minutes": row.avg_hold_minutes,
        }
        for row in rows
    ]


@router.get("/{run_id}/metrics/regime")
def regime_metrics(
    run_id: str,
    _: object = Depends(require_permissions("view_dashboard")),
    db: Session = Depends(get_db_session),
):
    _get_run_or_404(db, run_id)
    stmt = select(RegimeMetric).where(RegimeMetric.run_id == run_id).order_by(RegimeMetric.regime.asc())
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "regime": row.regime,
            "time_pct": row.time_pct,
            "switches": row.switches,
            "gate_blocks": row.gate_blocks,
        }
        for row in rows
    ]


@router.get("/{run_id}/analytics/scorecard")
def analytics_scorecard(
    run_id: str,
    _: object = Depends(require_permissions("view_dashboard")),
    db: Session = Depends(get_db_session),
):
    _get_run_or_404(db, run_id)
    stmt = (
        select(
            Trade.entry_strategy,
            Trade.entry_regime,
            func.count(Trade.id).label("trades"),
            func.sum(case((Trade.pnl_usdt > 0, 1), else_=0)).label("wins"),
            func.avg(Trade.pnl_usdt).label("avg_pnl"),
            func.sum(Trade.pnl_usdt).label("sum_pnl"),
        )
        .where(Trade.run_id == run_id)
        .group_by(Trade.entry_strategy, Trade.entry_regime)
        .order_by(Trade.entry_strategy.asc(), Trade.entry_regime.asc())
    )
    rows = db.execute(stmt).all()
    result = []
    for row in rows:
        trades = int(row.trades or 0)
        wins = int(row.wins or 0)
        win_rate = (wins / trades * 100.0) if trades > 0 else None
        result.append(
            {
                "entry_strategy": row.entry_strategy,
                "entry_regime": row.entry_regime,
                "trades": trades,
                "wins": wins,
                "win_rate_pct": round(win_rate, 2) if win_rate is not None else None,
                "avg_pnl_usdt": float(row.avg_pnl) if row.avg_pnl is not None else None,
                "sum_pnl_usdt": float(row.sum_pnl) if row.sum_pnl is not None else None,
            }
        )
    return result


@router.get("/{run_id}/analytics/walk-forward")
def analytics_walk_forward(
    run_id: str,
    _: object = Depends(require_permissions("view_dashboard")),
    db: Session = Depends(get_db_session),
):
    _get_run_or_404(db, run_id)
    # Placeholder: return segmented trade chronology for frontend visualization.
    stmt = (
        select(Trade.exit_ts, Trade.pnl_usdt)
        .where(Trade.run_id == run_id, Trade.exit_ts.is_not(None))
        .order_by(Trade.exit_ts.asc())
    )
    rows = db.execute(stmt).all()
    return [{"exit_ts": row.exit_ts.isoformat(), "pnl_usdt": float(row.pnl_usdt or 0.0)} for row in rows]


@router.get("/{run_id}/analytics/parameter-stability")
def analytics_parameter_stability(
    run_id: str,
    _: object = Depends(require_permissions("view_dashboard")),
    db: Session = Depends(get_db_session),
):
    _get_run_or_404(db, run_id)
    # Placeholder: returns observed parameter distribution from trade records.
    stmt = (
        select(
            Trade.entry_z_threshold_used,
            Trade.size_multiplier_used,
            func.count(Trade.id).label("trades"),
            func.avg(Trade.pnl_usdt).label("avg_pnl"),
        )
        .where(Trade.run_id == run_id)
        .group_by(Trade.entry_z_threshold_used, Trade.size_multiplier_used)
        .order_by(func.count(Trade.id).desc())
    )
    rows = db.execute(stmt).all()
    return [
        {
            "entry_z_threshold_used": row.entry_z_threshold_used,
            "size_multiplier_used": row.size_multiplier_used,
            "trades": int(row.trades or 0),
            "avg_pnl_usdt": float(row.avg_pnl) if row.avg_pnl is not None else None,
        }
        for row in rows
    ]


@router.get("/{run_id}/analytics/data-quality")
def analytics_data_quality(
    run_id: str,
    _: object = Depends(require_permissions("view_dashboard")),
    db: Session = Depends(get_db_session),
):
    run = _get_run_or_404(db, run_id)

    event_counts_stmt = select(
        func.count(RunEvent.id).label("total"),
        func.sum(case((RunEvent.severity == "warn", 1), else_=0)).label("warn"),
        func.sum(case((RunEvent.severity == "error", 1), else_=0)).label("error"),
        func.sum(case((RunEvent.severity == "critical", 1), else_=0)).label("critical"),
    ).where(RunEvent.run_id == run_id)
    event_counts = db.execute(event_counts_stmt).one()

    typed_counts_stmt = (
        select(RunEvent.event_type, func.count(RunEvent.id).label("count"))
        .where(
            RunEvent.run_id == run_id,
            RunEvent.event_type.in_(
                [
                    "data_quality_warning",
                    "reconciliation_warning",
                    "risk_alert",
                    "entry_reject",
                    "gate_enforced",
                ]
            ),
        )
        .group_by(RunEvent.event_type)
        .order_by(func.count(RunEvent.id).desc())
    )
    typed_counts_rows = db.execute(typed_counts_stmt).all()
    typed_counts = {str(row.event_type): int(row.count or 0) for row in typed_counts_rows}

    alerts_top_stmt = (
        select(
            Alert.alert_type,
            func.count(Alert.id).label("count"),
            func.max(Alert.created_at).label("last_seen"),
        )
        .where(Alert.run_id == run_id)
        .group_by(Alert.alert_type)
        .order_by(func.count(Alert.id).desc(), func.max(Alert.created_at).desc())
        .limit(12)
    )
    alerts_top_rows = db.execute(alerts_top_stmt).all()

    trade_integrity_stmt = select(
        func.count(Trade.id).label("total"),
        func.sum(case((Trade.exit_ts.is_not(None), 1), else_=0)).label("closed"),
        func.sum(
            case(
                (and_(Trade.exit_ts.is_not(None), Trade.pnl_usdt.is_(None)), 1),
                else_=0,
            )
        ).label("closed_missing_pnl"),
        func.sum(
            case(
                (and_(Trade.exit_ts.is_not(None), Trade.exit_reason.is_(None)), 1),
                else_=0,
            )
        ).label("closed_missing_exit_reason"),
        func.sum(case((Trade.exit_ts.is_(None), 1), else_=0)).label("open_rows"),
    ).where(Trade.run_id == run_id)
    trade_integrity = db.execute(trade_integrity_stmt).one()

    trade_pnl_sum_stmt = select(func.coalesce(func.sum(Trade.pnl_usdt), 0.0)).where(
        Trade.run_id == run_id,
        Trade.exit_ts.is_not(None),
    )
    trade_pnl_sum = float(db.execute(trade_pnl_sum_stmt).scalar() or 0.0)

    run_session_pnl = _coerce_float(run.session_pnl)
    delta_usdt = (run_session_pnl - trade_pnl_sum) if run_session_pnl is not None else None
    abs_delta_usdt = abs(delta_usdt) if delta_usdt is not None else None
    delta_pct = (
        abs(delta_usdt) / max(abs(run_session_pnl), 1.0) * 100.0
        if delta_usdt is not None and run_session_pnl is not None
        else None
    )

    if abs_delta_usdt is None:
        reconciliation_status = "unknown"
    elif abs_delta_usdt <= 1.0:
        reconciliation_status = "pass"
    elif abs_delta_usdt <= 5.0:
        reconciliation_status = "warn"
    else:
        reconciliation_status = "fail"

    if delta_pct is not None and delta_pct >= 25.0 and reconciliation_status == "warn":
        reconciliation_status = "fail"

    closed_missing_pnl = int(trade_integrity.closed_missing_pnl or 0)
    closed_missing_exit_reason = int(trade_integrity.closed_missing_exit_reason or 0)
    if closed_missing_pnl > 0:
        trade_integrity_status = "fail"
    elif closed_missing_exit_reason > 0:
        trade_integrity_status = "warn"
    else:
        trade_integrity_status = "pass"

    issues_stmt = (
        select(RunEvent)
        .where(
            RunEvent.run_id == run_id,
            or_(
                RunEvent.severity.in_(["warn", "error", "critical"]),
                RunEvent.event_type.in_(
                    [
                        "data_quality_warning",
                        "reconciliation_warning",
                        "risk_alert",
                        "entry_reject",
                        "gate_enforced",
                    ]
                ),
                RunEvent.event_type.ilike("%warning%"),
            ),
        )
        .order_by(RunEvent.ts.desc())
        .limit(40)
    )
    issues_rows = db.execute(issues_stmt).scalars().all()

    recent_issues = []
    for row in issues_rows:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        message = str(payload.get("message") or payload.get("reason") or payload.get("reason_code") or "")
        if not message:
            message = row.event_type
        recent_issues.append(
            {
                "event_id": row.event_id,
                "ts": row.ts.isoformat(),
                "event_type": row.event_type,
                "severity": row.severity,
                "message": message,
            }
        )

    alert_top = [
        {
            "alert_type": str(row.alert_type),
            "count": int(row.count or 0),
            "last_seen": row.last_seen.isoformat() if row.last_seen else None,
        }
        for row in alerts_top_rows
    ]

    health_statuses = [reconciliation_status, trade_integrity_status]
    event_warn_total = int(event_counts.warn or 0) + int(event_counts.error or 0) + int(event_counts.critical or 0)
    if event_warn_total > 0 and "pass" in health_statuses:
        health_statuses.append("warn")
    overall_status = "pass"
    for status_text in health_statuses:
        if _status_rank(status_text) > _status_rank(overall_status):
            overall_status = status_text

    return {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall_status,
        "event_health": {
            "total": int(event_counts.total or 0),
            "warn": int(event_counts.warn or 0),
            "error": int(event_counts.error or 0),
            "critical": int(event_counts.critical or 0),
            "typed_warning_events": typed_counts,
        },
        "trade_integrity": {
            "status": trade_integrity_status,
            "total_rows": int(trade_integrity.total or 0),
            "closed_rows": int(trade_integrity.closed or 0),
            "open_rows": int(trade_integrity.open_rows or 0),
            "closed_missing_pnl": closed_missing_pnl,
            "closed_missing_exit_reason": closed_missing_exit_reason,
        },
        "reconciliation": {
            "status": reconciliation_status,
            "run_session_pnl_usdt": run_session_pnl,
            "trade_pnl_sum_usdt": trade_pnl_sum,
            "delta_usdt": delta_usdt,
            "delta_pct_of_session": delta_pct,
            "threshold_pass_usdt": 1.0,
            "threshold_warn_usdt": 5.0,
        },
        "top_alerts": alert_top,
        "recent_issues": recent_issues,
    }


@router.get("/{run_id}/config-snapshot")
def get_run_config_snapshot(
    run_id: str,
    _: object = Depends(require_permissions("view_dashboard")),
    db: Session = Depends(get_db_session),
):
    _get_run_or_404(db, run_id)

    cfg_stmt = (
        select(BotConfig)
        .where(BotConfig.run_id == run_id)
        .order_by(BotConfig.created_at.desc())
        .limit(1)
    )
    bot_cfg = db.execute(cfg_stmt).scalar_one_or_none()
    if bot_cfg is not None:
        payload = bot_cfg.config_snapshot_json if isinstance(bot_cfg.config_snapshot_json, dict) else {}
        return {
            "run_id": run_id,
            "source": "bot_configs",
            "created_at": bot_cfg.created_at.isoformat() if bot_cfg.created_at else None,
            "report_id": None,
            "file_id": None,
            "path": None,
            "config_snapshot": payload,
        }

    fallback_stmt = (
        select(ReportFile, Report)
        .join(Report, ReportFile.report_id == Report.id)
        .where(
            Report.run_id == run_id,
            func.lower(ReportFile.name) == "config_snapshot.json",
        )
        .order_by(Report.requested_at.desc(), ReportFile.created_at.desc())
        .limit(1)
    )
    fallback_row = db.execute(fallback_stmt).first()
    if fallback_row is None:
        return {
            "run_id": run_id,
            "source": "none",
            "created_at": None,
            "report_id": None,
            "file_id": None,
            "path": None,
            "config_snapshot": None,
        }

    report_file = fallback_row[0]
    report = fallback_row[1]
    resolved_path, error_text = _safe_file_info(str(report_file.path or ""))
    if resolved_path is None:
        return {
            "run_id": run_id,
            "source": "report_file_unavailable",
            "created_at": report_file.created_at.isoformat() if report_file.created_at else None,
            "report_id": report.id,
            "file_id": report_file.id,
            "path": report_file.path,
            "config_snapshot": None,
            "error": error_text,
        }

    try:
        text = resolved_path.read_text(encoding="utf-8")
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            parsed = {"_raw": parsed}
    except Exception as exc:
        return {
            "run_id": run_id,
            "source": "report_file_invalid",
            "created_at": report_file.created_at.isoformat() if report_file.created_at else None,
            "report_id": report.id,
            "file_id": report_file.id,
            "path": str(resolved_path),
            "config_snapshot": None,
            "error": str(exc),
        }

    return {
        "run_id": run_id,
        "source": "report_file",
        "created_at": report_file.created_at.isoformat() if report_file.created_at else None,
        "report_id": report.id,
        "file_id": report_file.id,
        "path": str(resolved_path),
        "config_snapshot": parsed,
    }


@router.get("/{run_id}/report-artifacts")
def list_run_report_artifacts(
    run_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    _: object = Depends(require_permissions("view_reports")),
    db: Session = Depends(get_db_session),
):
    _get_run_or_404(db, run_id)

    report_rows = db.execute(
        select(Report)
        .where(Report.run_id == run_id)
        .order_by(Report.requested_at.desc())
        .limit(limit)
    ).scalars().all()

    if not report_rows:
        return []

    report_ids = [row.id for row in report_rows]
    file_rows = db.execute(
        select(ReportFile)
        .where(ReportFile.report_id.in_(report_ids))
        .order_by(ReportFile.created_at.asc())
    ).scalars().all()

    files_by_report: dict[str, list[dict]] = {}
    for row in file_rows:
        files_by_report.setdefault(row.report_id, []).append(
            {
                "id": row.id,
                "name": row.name,
                "path": row.path,
                "mime_type": row.mime_type,
                "size_bytes": row.size_bytes,
                "checksum": row.checksum,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "download_url": f"/api/v2/reports/{row.report_id}/files/{row.id}/download",
            }
        )

    return [
        {
            "id": row.id,
            "run_id": row.run_id,
            "status": row.status,
            "requested_by": row.requested_by,
            "requested_at": row.requested_at.isoformat() if row.requested_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "error_text": row.error_text,
            "files": files_by_report.get(row.id, []),
        }
        for row in report_rows
    ]
