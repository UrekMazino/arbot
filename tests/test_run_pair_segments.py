from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Platform.api.app.database import Base
from Platform.api.app.models import BotInstance, Run, RunEvent
from Platform.api.app.services import bot_control
from Platform.api.app.services.run_pair_segments import (
    list_run_pair_history_rows,
    rebuild_run_pair_segments_from_events,
    sync_run_pair_segments_for_event,
)


def _build_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _event(run_id: str, event_id: str, ts: datetime, event_type: str, payload: dict) -> RunEvent:
    return RunEvent(
        event_id=event_id,
        run_id=run_id,
        bot_instance_id="bot-1",
        ts=ts,
        event_type=event_type,
        severity="info",
        payload_json=payload,
    )


def test_rebuild_run_pair_segments_from_events_normalizes_history():
    engine, session_factory = _build_session_factory()
    db = session_factory()
    try:
        bot = BotInstance(id="bot-1", name="default", environment="demo", is_active=True)
        start_ts = datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc)
        run = Run(id="run-db-1", bot_instance_id=bot.id, run_key="run_01_20260418_120000", status="stopped", start_ts=start_ts)
        db.add_all([bot, run])
        db.flush()

        rows = [
            _event(
                run.id,
                "evt-1",
                start_ts,
                "status_update",
                {"status": "startup_complete", "pair": "CRV-USDT-SWAP/ETHW-USDT-SWAP"},
            ),
            _event(
                run.id,
                "evt-2",
                start_ts + timedelta(minutes=10),
                "heartbeat",
                {"current_pair": "CRV-USDT-SWAP/ETHW-USDT-SWAP"},
            ),
            _event(
                run.id,
                "evt-3",
                start_ts + timedelta(minutes=15),
                "pair_switch",
                {
                    "status": "switched",
                    "from_pair": "CRV-USDT-SWAP/ETHW-USDT-SWAP",
                    "to_pair": "BAND-USDT-SWAP/CHZ-USDT-SWAP",
                    "reason": "cointegration_lost",
                },
            ),
            _event(
                run.id,
                "evt-4",
                start_ts + timedelta(minutes=30),
                "status_update",
                {"status": "run_end"},
            ),
        ]
        db.add_all(rows)
        db.commit()

        rebuild_run_pair_segments_from_events(db, run, overwrite=True)
        db.commit()

        history = list_run_pair_history_rows(db, run, reference_time=start_ts + timedelta(minutes=30))

        assert history == [
            {
                "id": history[0]["id"],
                "pair": "CRV-USDT-SWAP/ETHW-USDT-SWAP",
                "sequence_no": 1,
                "started_at": start_ts.isoformat(),
                "ended_at": (start_ts + timedelta(minutes=15)).isoformat(),
                "switch_reason": "startup_complete",
                "duration_seconds": 900.0,
            },
            {
                "id": history[1]["id"],
                "pair": "BAND-USDT-SWAP/CHZ-USDT-SWAP",
                "sequence_no": 2,
                "started_at": (start_ts + timedelta(minutes=15)).isoformat(),
                "ended_at": (start_ts + timedelta(minutes=30)).isoformat(),
                "switch_reason": "cointegration_lost",
                "duration_seconds": 900.0,
            },
        ]
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_sync_run_pair_segments_for_event_ignores_blocked_switches():
    engine, session_factory = _build_session_factory()
    db = session_factory()
    try:
        bot = BotInstance(id="bot-1", name="default", environment="demo", is_active=True)
        start_ts = datetime(2026, 4, 18, 13, 0, 0, tzinfo=timezone.utc)
        run = Run(id="run-db-2", bot_instance_id=bot.id, run_key="run_02_20260418_130000", status="running", start_ts=start_ts)
        db.add_all([bot, run])
        db.flush()

        startup = _event(
            run.id,
            "evt-10",
            start_ts,
            "status_update",
            {"status": "startup_complete", "pair": "HOME-USDT-SWAP/1INCH-USDT-SWAP"},
        )
        blocked = _event(
            run.id,
            "evt-11",
            start_ts + timedelta(minutes=5),
            "pair_switch",
            {
                "status": "blocked",
                "from_pair": "HOME-USDT-SWAP/1INCH-USDT-SWAP",
                "to_pair": "BAND-USDT-SWAP/CHZ-USDT-SWAP",
                "reason": "cooldown_active",
            },
        )
        db.add_all([startup, blocked])
        db.flush()

        sync_run_pair_segments_for_event(db, run, startup)
        sync_run_pair_segments_for_event(db, run, blocked)
        db.commit()

        history = list_run_pair_history_rows(db, run, reference_time=start_ts + timedelta(minutes=5), ensure_backfilled=False)

        assert len(history) == 1
        assert history[0]["pair"] == "HOME-USDT-SWAP/1INCH-USDT-SWAP"
        assert history[0]["duration_seconds"] == 300.0
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_tail_run_log_prefers_database_pair_history(tmp_path, monkeypatch):
    engine, session_factory = _build_session_factory()
    db = session_factory()
    try:
        logs_root = tmp_path / "Logs" / "v1"
        run_key = "run_03_20260418_140000"
        run_dir = logs_root / run_key
        run_dir.mkdir(parents=True)
        log_file = run_dir / "log_20260418_140000.log"
        log_file.write_text(
            "\n".join(
                [
                    "2026-04-18 14:00:00 INFO Starting equity: 1000.00 USDT",
                    "2026-04-18 14:20:00 INFO Heartbeat",
                ]
            ),
            encoding="utf-8",
        )

        state_file = tmp_path / "state" / "ui_bot_control.json"
        state_file.parent.mkdir(parents=True)
        state_file.write_text(json.dumps({"run_key": run_key}), encoding="utf-8")

        bot = BotInstance(id="bot-1", name="default", environment="demo", is_active=True)
        start_ts = datetime.fromtimestamp(
            datetime(2026, 4, 18, 14, 0, 0).timestamp(),
            tz=timezone.utc,
        )
        run = Run(id="run-db-3", bot_instance_id=bot.id, run_key=run_key, status="running", start_ts=start_ts)
        db.add_all([bot, run])
        db.flush()

        startup = _event(
            run.id,
            "evt-20",
            start_ts,
            "status_update",
            {"status": "startup_complete", "pair": "CRV-USDT-SWAP/ETHW-USDT-SWAP"},
        )
        switch = _event(
            run.id,
            "evt-21",
            start_ts + timedelta(minutes=12),
            "pair_switch",
            {
                "status": "switched",
                "from_pair": "CRV-USDT-SWAP/ETHW-USDT-SWAP",
                "to_pair": "BAND-USDT-SWAP/CHZ-USDT-SWAP",
                "reason": "health",
            },
        )
        heartbeat = _event(
            run.id,
            "evt-22",
            start_ts + timedelta(minutes=20),
            "heartbeat",
            {"current_pair": "BAND-USDT-SWAP/CHZ-USDT-SWAP"},
        )
        db.add_all([startup, switch, heartbeat])
        db.commit()

        rebuild_run_pair_segments_from_events(db, run, overwrite=True)
        db.commit()

        monkeypatch.setattr(bot_control, "LOGS_ROOT", logs_root)
        monkeypatch.setattr(bot_control, "CONTROL_LOG_FILE", logs_root / "superadmin_bot_control.log")
        monkeypatch.setattr(bot_control, "STATE_FILE", state_file)
        monkeypatch.setattr(bot_control, "SessionLocal", session_factory)

        tail = bot_control.tail_run_log(run_key=run_key, lines=50)

        assert tail["pair_count"] == 2
        assert tail["pair_history"][0]["pair"] == "CRV-USDT-SWAP/ETHW-USDT-SWAP"
        assert tail["pair_history"][0]["duration_seconds"] == 720.0
        assert tail["pair_history"][1]["pair"] == "BAND-USDT-SWAP/CHZ-USDT-SWAP"
        assert tail["pair_history"][1]["duration_seconds"] == 480.0
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
