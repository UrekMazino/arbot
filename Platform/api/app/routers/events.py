from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..deps import get_db_session, get_event_ingest_principal
from ..models import Alert, BotInstance, Run, RunEvent
from ..realtime import publish_bot_event
from ..schemas import EventBatchIn, EventIngestResultOut
from ..services.live_report import materialize_live_run_report
from ..services.run_pair_segments import sync_run_pair_segments_for_event

router = APIRouter(prefix="/bots", tags=["events"])
logger = logging.getLogger("platform.events")


def _coerce_ts(ts_value: float) -> datetime:
    return datetime.fromtimestamp(float(ts_value), tz=timezone.utc)


def _ensure_bot_instance(db: Session, bot_instance_id: str) -> BotInstance:
    bot = db.get(BotInstance, bot_instance_id)
    if bot:
        return bot
    bot = BotInstance(id=bot_instance_id, name=f"bot-{bot_instance_id[:8]}", environment="demo", is_active=True)
    db.add(bot)
    db.flush()
    return bot


def _ensure_run(db: Session, run_id: str, bot_instance_id: str) -> Run:
    run = db.get(Run, run_id)
    if run:
        return run
    run = db.execute(select(Run).where(Run.run_key == run_id)).scalar_one_or_none()
    if run:
        return run
    run = Run(
        id=run_id,
        bot_instance_id=bot_instance_id,
        run_key=run_id if str(run_id).startswith("run_") else f"ingest-{run_id[:8]}",
        status="running",
        start_ts=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()
    return run


def _coerce_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _apply_run_metrics_from_event(run: Run, event) -> None:
    payload = event.payload or {}

    if event.event_type == "status_update":
        status_text = str(payload.get("status") or "").strip().lower()
        if status_text == "startup_complete":
            start_equity = _coerce_float(payload.get("starting_equity_usdt"))
            if start_equity is not None:
                run.start_equity = start_equity
            run.status = "running"
        elif status_text in {"manual_stop", "run_end"}:
            run.status = "stopped"
            run.end_ts = _coerce_ts(event.ts)

    if event.event_type == "heartbeat":
        end_equity = _coerce_float(payload.get("equity_usdt"))
        session_pnl = _coerce_float(payload.get("session_pnl_usdt"))
        if end_equity is not None:
            run.end_equity = end_equity
        if session_pnl is not None:
            run.session_pnl = session_pnl


@router.post("/{bot_instance_id}/events/batch", response_model=EventIngestResultOut)
def ingest_events_batch(
    bot_instance_id: str,
    body: EventBatchIn,
    _: object = Depends(get_event_ingest_principal),
    db: Session = Depends(get_db_session),
):
    if len(body.events) > settings.event_batch_max:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"events max is {settings.event_batch_max}",
        )

    accepted = 0
    duplicate = 0
    rejected = 0

    _ensure_bot_instance(db, bot_instance_id)
    db.commit()

    for event in body.events:
        try:
            run = _ensure_run(db, event.run_id, bot_instance_id)
            row = RunEvent(
                event_id=event.event_id,
                run_id=run.id,
                bot_instance_id=bot_instance_id,
                ts=_coerce_ts(event.ts),
                event_type=event.event_type,
                severity=event.severity.lower(),
                payload_json=event.payload or {},
            )
            db.add(row)
            db.flush()
            _apply_run_metrics_from_event(run, event)
            sync_run_pair_segments_for_event(db, run, row)
            accepted += 1

            if row.severity in {"warn", "error", "critical"}:
                alert = Alert(
                    run_id=run.id,
                    event_id=event.event_id,
                    severity=row.severity,
                    alert_type=event.event_type,
                    message=str((event.payload or {}).get("message") or event.event_type),
                )
                db.add(alert)
                db.flush()
            db.commit()
            try:
                materialize_live_run_report(db, run)
            except Exception as report_exc:
                logger.warning(
                    "Live report materialization failed: bot=%s run=%s type=%s err=%s",
                    bot_instance_id,
                    event.run_id,
                    event.event_type,
                    report_exc,
                )

            publish_bot_event(
                bot_instance_id,
                {
                    "event_id": row.event_id,
                    "run_id": row.run_id,
                    "bot_instance_id": row.bot_instance_id,
                    "ts": row.ts.timestamp(),
                    "event_type": row.event_type,
                    "severity": row.severity,
                    "payload": row.payload_json or {},
                },
            )
        except IntegrityError:
            db.rollback()
            duplicate += 1
        except Exception as exc:
            db.rollback()
            rejected += 1
            logger.warning("Event ingest rejected: bot=%s run=%s type=%s err=%s", bot_instance_id, event.run_id, event.event_type, exc)

    return EventIngestResultOut(accepted=accepted, duplicate=duplicate, rejected=rejected)


@router.post("/{bot_instance_id}/heartbeat", response_model=EventIngestResultOut)
def heartbeat(
    bot_instance_id: str,
    body: EventBatchIn,
    principal: object = Depends(get_event_ingest_principal),
    db: Session = Depends(get_db_session),
):
    return ingest_events_batch(bot_instance_id, body, principal, db)
