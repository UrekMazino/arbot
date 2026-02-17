from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..deps import get_db_session, get_event_ingest_principal
from ..models import Alert, BotInstance, Run, RunEvent
from ..realtime import publish_bot_event
from ..schemas import EventBatchIn, EventIngestResultOut

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
    run = Run(
        id=run_id,
        bot_instance_id=bot_instance_id,
        run_key=f"ingest-{run_id[:8]}",
        status="running",
        start_ts=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()
    return run


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
            _ensure_run(db, event.run_id, bot_instance_id)
            row = RunEvent(
                event_id=event.event_id,
                run_id=event.run_id,
                bot_instance_id=bot_instance_id,
                ts=_coerce_ts(event.ts),
                event_type=event.event_type,
                severity=event.severity.lower(),
                payload_json=event.payload or {},
            )
            db.add(row)
            db.flush()
            accepted += 1

            if row.severity in {"warn", "error", "critical"}:
                alert = Alert(
                    run_id=event.run_id,
                    event_id=event.event_id,
                    severity=row.severity,
                    alert_type=event.event_type,
                    message=str((event.payload or {}).get("message") or event.event_type),
                )
                db.add(alert)
                db.flush()
            db.commit()

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
