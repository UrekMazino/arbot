from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models import Run, RunEvent
from .run_pair_segments import list_run_pair_history_rows

_STARTUP_STATUS = "startup_complete"
_STOP_STATUSES = {"manual_stop", "run_end"}


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    normalized = _as_utc(value)
    return normalized.isoformat() if normalized else None


def _coerce_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_iso(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return _as_utc(parsed)


def _payload_text(payload: dict, *keys: str) -> str | None:
    for key in keys:
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return None


def _resolve_run(db: Session, run_key: str | None) -> Run | None:
    selected = str(run_key or "").strip()
    if not selected or selected.lower() == "latest":
        return db.execute(
            select(Run)
            .order_by(desc(Run.start_ts), desc(Run.id))
            .limit(1)
        ).scalar_one_or_none()
    return db.execute(select(Run).where(Run.run_key == selected)).scalar_one_or_none()


def _latest_event(db: Session, run_id: str, event_type: str) -> RunEvent | None:
    return db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run_id, RunEvent.event_type == event_type)
        .order_by(desc(RunEvent.ts), desc(RunEvent.created_at), desc(RunEvent.id))
        .limit(1)
    ).scalar_one_or_none()


def _latest_status_event(db: Session, run_id: str, allowed_statuses: set[str]) -> RunEvent | None:
    rows = db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run_id, RunEvent.event_type == "status_update")
        .order_by(desc(RunEvent.ts), desc(RunEvent.created_at), desc(RunEvent.id))
        .limit(25)
    ).scalars().all()
    for row in rows:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        status_text = str(payload.get("status") or "").strip().lower()
        if status_text in allowed_statuses:
            return row
    return None


def _latest_runtime_event(db: Session, run_id: str) -> RunEvent | None:
    return db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run_id)
        .order_by(desc(RunEvent.ts), desc(RunEvent.created_at), desc(RunEvent.id))
        .limit(1)
    ).scalar_one_or_none()


def get_run_runtime_snapshot(
    db: Session,
    run_key: str | None = None,
    *,
    include_pair_history: bool = True,
) -> dict:
    run = _resolve_run(db, run_key)
    if run is None:
        return {
            "run_id": None,
            "run_key": None,
            "status": "not_found",
            "running": False,
            "detail": "run_not_found",
            "started_at": None,
            "stopped_at": None,
            "updated_at": None,
            "duration_seconds": 0.0,
            "starting_equity": None,
            "equity": None,
            "session_pnl": None,
            "session_pnl_pct": None,
            "run_start_time": None,
            "pair_history": [],
            "pair_count": 0,
            "current_pair": None,
            "latest_regime": None,
            "latest_strategy": None,
            "source": "events_db",
        }

    latest_heartbeat = _latest_event(db, run.id, "heartbeat")
    startup_event = _latest_status_event(db, run.id, {_STARTUP_STATUS})
    stop_event = _latest_status_event(db, run.id, _STOP_STATUSES)
    latest_regime = _latest_event(db, run.id, "regime_update")
    latest_strategy = _latest_event(db, run.id, "strategy_update")
    latest_event = _latest_runtime_event(db, run.id)

    heartbeat_payload = latest_heartbeat.payload_json if latest_heartbeat and isinstance(latest_heartbeat.payload_json, dict) else {}
    startup_payload = startup_event.payload_json if startup_event and isinstance(startup_event.payload_json, dict) else {}
    regime_payload = latest_regime.payload_json if latest_regime and isinstance(latest_regime.payload_json, dict) else {}
    strategy_payload = latest_strategy.payload_json if latest_strategy and isinstance(latest_strategy.payload_json, dict) else {}

    started_at = _as_utc(run.start_ts)
    uptime_seconds = _coerce_float(heartbeat_payload.get("uptime_seconds"))
    if latest_heartbeat is not None and uptime_seconds is not None and uptime_seconds >= 0:
        started_at = _as_utc(latest_heartbeat.ts) - timedelta(seconds=uptime_seconds)
    elif startup_event is not None:
        started_at = _as_utc(startup_event.ts)

    stopped_at = _as_utc(run.end_ts)
    if stopped_at is None and stop_event is not None:
        stopped_at = _as_utc(stop_event.ts)

    running = str(run.status or "").strip().lower() == "running" and stopped_at is None

    try:
        from .bot_control import get_bot_status

        bot_status = get_bot_status()
    except Exception:
        bot_status = {}

    state_run_key = str(bot_status.get("run_key") or bot_status.get("latest_run_key") or "").strip()
    if state_run_key and state_run_key == str(run.run_key or "").strip():
        state_started_at = _parse_iso(bot_status.get("started_at"))
        state_stopped_at = _parse_iso(bot_status.get("stopped_at"))
        if started_at is None and state_started_at is not None:
            started_at = state_started_at
        if not bool(bot_status.get("running")):
            running = False
            if state_stopped_at is not None:
                stopped_at = state_stopped_at

    updated_at = None
    if latest_heartbeat is not None:
        updated_at = _as_utc(latest_heartbeat.ts)
    elif latest_event is not None:
        updated_at = _as_utc(latest_event.ts)
    elif stopped_at is not None:
        updated_at = stopped_at
    else:
        updated_at = started_at

    reference_time = updated_at or stopped_at or started_at or datetime.now(timezone.utc)
    if not running and stopped_at is not None and reference_time < stopped_at:
        reference_time = stopped_at
    duration_seconds = 0.0
    if started_at is not None and reference_time is not None:
        duration_seconds = max((reference_time - started_at).total_seconds(), 0.0)

    starting_equity = _coerce_float(run.start_equity)
    if starting_equity is None:
        starting_equity = _coerce_float(startup_payload.get("starting_equity_usdt"))

    equity = _coerce_float(run.end_equity)
    heartbeat_equity = _coerce_float(heartbeat_payload.get("equity_usdt"))
    if heartbeat_equity is not None:
        equity = heartbeat_equity
    elif equity is None:
        equity = starting_equity

    session_pnl = _coerce_float(run.session_pnl)
    heartbeat_session_pnl = _coerce_float(heartbeat_payload.get("session_pnl_usdt"))
    if heartbeat_session_pnl is not None:
        session_pnl = heartbeat_session_pnl

    session_pnl_pct = _coerce_float(heartbeat_payload.get("session_pnl_pct"))
    if session_pnl_pct is None and session_pnl is not None and starting_equity and starting_equity > 0:
        session_pnl_pct = (session_pnl / starting_equity) * 100.0

    pair_history: list[dict] = []
    if include_pair_history:
        pair_history = list_run_pair_history_rows(
            db,
            run,
            reference_time=reference_time,
            ensure_backfilled=True,
        )

    current_pair = None
    if pair_history:
        current_pair = str(pair_history[-1].get("pair") or "").strip() or None
    if current_pair is None:
        current_pair = _payload_text(heartbeat_payload, "current_pair", "pair")
    if current_pair is None:
        current_pair = _payload_text(startup_payload, "current_pair", "pair")

    return {
        "run_id": run.id,
        "run_key": run.run_key,
        "status": ("running" if running else "stopped") if str(run.status or "").strip().lower() in {"running", "stopped"} else (str(run.status or "").strip() or "unknown"),
        "running": running,
        "detail": "events_db",
        "started_at": _iso(started_at),
        "stopped_at": _iso(stopped_at),
        "updated_at": _iso(reference_time),
        "duration_seconds": duration_seconds,
        "starting_equity": starting_equity,
        "equity": equity,
        "session_pnl": session_pnl,
        "session_pnl_pct": session_pnl_pct,
        "run_start_time": started_at.timestamp() if started_at else None,
        "pair_history": pair_history,
        "pair_count": len(pair_history),
        "current_pair": current_pair,
        "latest_regime": _payload_text(regime_payload, "regime"),
        "latest_strategy": _payload_text(strategy_payload, "strategy"),
        "source": "events_db",
    }
