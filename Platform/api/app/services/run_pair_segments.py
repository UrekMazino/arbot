from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Run, RunEvent, RunPairSegment

_STOP_STATUSES = {"manual_stop", "run_end"}
_SWITCH_STATUS_SWITCHED = "switched"
_SYNTHETIC_SWITCH_REASON = "event_backfill"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_pair_text(value: object) -> str | None:
    text = str(value or "").strip()
    if not text or "/" not in text:
        return None
    left, right = text.split("/", 1)
    left = left.strip().upper()
    right = right.strip().upper()
    if not left or not right:
        return None
    return f"{left}/{right}"


def _segment_duration_seconds(segment: RunPairSegment, reference_time: datetime) -> float:
    started_at = _as_utc(segment.started_at)
    end_time = _as_utc(segment.ended_at) or _as_utc(reference_time)
    if started_at is None or end_time is None:
        return 0.0
    if end_time < started_at:
        end_time = started_at
    return max((end_time - started_at).total_seconds(), 0.0)


def _latest_segment(db: Session, run_id: str) -> RunPairSegment | None:
    return db.execute(
        select(RunPairSegment)
        .where(RunPairSegment.run_id == run_id)
        .order_by(RunPairSegment.sequence_no.desc())
        .limit(1)
    ).scalar_one_or_none()


def _next_sequence_no(db: Session, run_id: str) -> int:
    latest = _latest_segment(db, run_id)
    if latest is None:
        return 1
    return int(latest.sequence_no or 0) + 1


def _create_segment(
    db: Session,
    *,
    run_id: str,
    pair_key: str,
    started_at: datetime,
    sequence_no: int,
    start_event_id: str | None,
    switch_reason: str | None,
) -> RunPairSegment:
    segment = RunPairSegment(
        run_id=run_id,
        pair_key=pair_key,
        started_at=started_at,
        sequence_no=sequence_no,
        start_event_id=start_event_id,
        switch_reason=switch_reason,
    )
    db.add(segment)
    db.flush()
    return segment


def _close_segment(
    segment: RunPairSegment,
    *,
    ended_at: datetime,
    end_event_id: str | None,
) -> RunPairSegment:
    started_at = _as_utc(segment.started_at)
    ended_at = _as_utc(ended_at)
    if started_at is not None and ended_at is not None and ended_at < started_at:
        ended_at = started_at
    segment.ended_at = ended_at
    if end_event_id:
        segment.end_event_id = end_event_id
    return segment


def _observe_current_pair(
    db: Session,
    *,
    run: Run,
    pair_key: str,
    observed_at: datetime,
    event_id: str | None,
    switch_reason: str | None,
    start_override: datetime | None = None,
) -> RunPairSegment:
    latest = _latest_segment(db, run.id)
    if latest and latest.ended_at is None:
        if latest.pair_key == pair_key:
            return latest
        _close_segment(latest, ended_at=observed_at, end_event_id=event_id)
        return _create_segment(
            db,
            run_id=run.id,
            pair_key=pair_key,
            started_at=observed_at,
            sequence_no=int(latest.sequence_no) + 1,
            start_event_id=event_id,
            switch_reason=switch_reason,
        )

    return _create_segment(
        db,
        run_id=run.id,
        pair_key=pair_key,
        started_at=start_override or observed_at,
        sequence_no=_next_sequence_no(db, run.id),
        start_event_id=event_id,
        switch_reason=switch_reason,
    )


def _apply_pair_switch(
    db: Session,
    *,
    run: Run,
    event: RunEvent,
    from_pair: str | None,
    to_pair: str | None,
    switch_reason: str | None,
) -> RunPairSegment | None:
    latest = _latest_segment(db, run.id)
    if latest and latest.ended_at is None:
        if from_pair and latest.pair_key != from_pair:
            _close_segment(latest, ended_at=event.ts, end_event_id=event.event_id)
            latest = None
        else:
            _close_segment(latest, ended_at=event.ts, end_event_id=event.event_id)
    elif from_pair:
        synthetic_start = run.start_ts if run.start_ts and run.start_ts <= event.ts else event.ts
        synthetic = _create_segment(
            db,
            run_id=run.id,
            pair_key=from_pair,
            started_at=synthetic_start,
            sequence_no=_next_sequence_no(db, run.id),
            start_event_id=None,
            switch_reason=_SYNTHETIC_SWITCH_REASON,
        )
        _close_segment(synthetic, ended_at=event.ts, end_event_id=event.event_id)

    if not to_pair:
        return None

    latest = _latest_segment(db, run.id)
    if latest and latest.ended_at is None and latest.pair_key == to_pair:
        return latest

    return _create_segment(
        db,
        run_id=run.id,
        pair_key=to_pair,
        started_at=event.ts,
        sequence_no=_next_sequence_no(db, run.id),
        start_event_id=event.event_id,
        switch_reason=switch_reason,
    )


def sync_run_pair_segments_for_event(db: Session, run: Run, event: RunEvent) -> None:
    payload = event.payload_json if isinstance(event.payload_json, dict) else {}
    event_type = str(event.event_type or "").strip().lower()

    if event_type == "status_update":
        status_text = str(payload.get("status") or "").strip().lower()
        if status_text == "startup_complete":
            pair_key = _normalize_pair_text(payload.get("pair") or payload.get("current_pair"))
            if pair_key:
                _observe_current_pair(
                    db,
                    run=run,
                    pair_key=pair_key,
                    observed_at=event.ts,
                    event_id=event.event_id,
                    switch_reason="startup_complete",
                    start_override=event.ts,
                )
            return

        if status_text in _STOP_STATUSES:
            latest = _latest_segment(db, run.id)
            if latest and latest.ended_at is None:
                _close_segment(latest, ended_at=event.ts, end_event_id=event.event_id)
            return

    if event_type == "heartbeat":
        pair_key = _normalize_pair_text(payload.get("current_pair") or payload.get("pair"))
        if pair_key:
            _observe_current_pair(
                db,
                run=run,
                pair_key=pair_key,
                observed_at=event.ts,
                event_id=event.event_id,
                switch_reason="heartbeat_observed",
            )
        return

    if event_type != "pair_switch":
        return

    status_text = str(payload.get("status") or "").strip().lower()
    if status_text != _SWITCH_STATUS_SWITCHED:
        return

    from_pair = _normalize_pair_text(payload.get("from_pair"))
    to_pair = _normalize_pair_text(payload.get("to_pair"))
    _apply_pair_switch(
        db,
        run=run,
        event=event,
        from_pair=from_pair,
        to_pair=to_pair,
        switch_reason=str(payload.get("reason") or "").strip() or None,
    )


def rebuild_run_pair_segments_from_events(db: Session, run: Run, *, overwrite: bool = False) -> list[RunPairSegment]:
    if overwrite:
        db.execute(delete(RunPairSegment).where(RunPairSegment.run_id == run.id))
        db.flush()
    else:
        existing = db.execute(
            select(RunPairSegment.id)
            .where(RunPairSegment.run_id == run.id)
            .limit(1)
        ).scalar_one_or_none()
        if existing:
            return list_run_pair_segments(db, run.id)

    events = db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run.id)
        .order_by(RunEvent.ts.asc(), RunEvent.created_at.asc(), RunEvent.id.asc())
    ).scalars().all()

    for row in events:
        sync_run_pair_segments_for_event(db, run, row)

    return list_run_pair_segments(db, run.id)


def ensure_run_pair_segments(db: Session, run: Run) -> list[RunPairSegment]:
    segments = list_run_pair_segments(db, run.id)
    if segments:
        return segments
    return rebuild_run_pair_segments_from_events(db, run, overwrite=False)


def list_run_pair_segments(db: Session, run_id: str) -> list[RunPairSegment]:
    return list(
        db.execute(
            select(RunPairSegment)
            .where(RunPairSegment.run_id == run_id)
            .order_by(RunPairSegment.sequence_no.asc(), RunPairSegment.started_at.asc())
        ).scalars().all()
    )


def list_run_pair_history_rows(
    db: Session,
    run: Run,
    *,
    reference_time: datetime | None = None,
    ensure_backfilled: bool = True,
) -> list[dict]:
    if ensure_backfilled:
        segments = list_run_pair_segments(db, run.id)
        if not segments:
            segments = rebuild_run_pair_segments_from_events(db, run, overwrite=False)
            db.commit()
    else:
        segments = list_run_pair_segments(db, run.id)
    ref_time = _as_utc(reference_time) or _as_utc(run.end_ts) or _utcnow()

    rows: list[dict] = []
    for segment in segments:
        started_at = _as_utc(segment.started_at)
        ended_at = _as_utc(segment.ended_at)
        rows.append(
            {
                "id": segment.id,
                "pair": segment.pair_key,
                "sequence_no": segment.sequence_no,
                "started_at": started_at.isoformat() if started_at else None,
                "ended_at": ended_at.isoformat() if ended_at else None,
                "switch_reason": segment.switch_reason,
                "duration_seconds": _segment_duration_seconds(segment, ref_time),
            }
        )
    return rows


def list_run_pair_history_rows_by_run_key(
    db: Session,
    run_key: str,
    *,
    reference_time: datetime | None = None,
    ensure_backfilled: bool = True,
) -> list[dict]:
    run = db.execute(select(Run).where(Run.run_key == run_key)).scalar_one_or_none()
    if not run:
        return []
    return list_run_pair_history_rows(
        db,
        run,
        reference_time=reference_time,
        ensure_backfilled=ensure_backfilled,
    )
