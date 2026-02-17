from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db_session
from ..models import RegimeMetric, Run, RunEvent, StrategyMetric, Trade
from ..schemas import RunEventOut, RunOut, TradeOut

router = APIRouter(prefix="/runs", tags=["runs"])


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
