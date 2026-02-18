from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db_session
from ..models import Alert, RegimeMetric, Run, RunEvent, StrategyMetric, Trade
from ..schemas import RunEventOut, RunOut, TradeOut

router = APIRouter(prefix="/runs", tags=["runs"])


def _coerce_float(value):
    if value is None:
        return None
    return float(value)


def _status_rank(status_text: str) -> int:
    if status_text == "fail":
        return 3
    if status_text == "warn":
        return 2
    if status_text == "unknown":
        return 1
    return 0


def _get_run_or_404(db: Session, run_id: str) -> Run:
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.get("", response_model=list[RunOut])
def list_runs(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    stmt = select(Run).order_by(Run.start_ts.desc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


@router.get("/{run_id}", response_model=RunOut)
def get_run(
    run_id: str,
    _: object = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    return _get_run_or_404(db, run_id)


@router.get("/{run_id}/events", response_model=list[RunEventOut])
def list_run_events(
    run_id: str,
    limit: int = Query(default=500, ge=1, le=2000),
    _: object = Depends(get_current_user),
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


@router.get("/{run_id}/trades", response_model=list[TradeOut])
def list_run_trades(
    run_id: str,
    limit: int = Query(default=1000, ge=1, le=5000),
    _: object = Depends(get_current_user),
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
    _: object = Depends(get_current_user),
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
    _: object = Depends(get_current_user),
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
    _: object = Depends(get_current_user),
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
    _: object = Depends(get_current_user),
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
    _: object = Depends(get_current_user),
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
    _: object = Depends(get_current_user),
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
