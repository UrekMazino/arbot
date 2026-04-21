from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Platform.api.app.database import Base
from Platform.api.app.models import BotInstance, EquitySnapshot, Run, RunEvent
from Platform.api.app.services.event_materializer import materialize_run_entities_for_event


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


def test_materializer_creates_equity_snapshots_and_run_summary():
    engine, session_factory = _build_session_factory()
    db = session_factory()
    try:
        bot = BotInstance(id="bot-1", name="default", environment="demo", is_active=True)
        start_ts = datetime(2026, 4, 21, 4, 0, 0, tzinfo=timezone.utc)
        run = Run(
            id="run-db-1",
            bot_instance_id=bot.id,
            run_key="run_01_20260421_120000",
            status="running",
            start_ts=start_ts,
            start_equity=1000.0,
        )
        db.add_all([bot, run])
        db.flush()

        startup = _event(
            run.id,
            "evt-start",
            start_ts,
            "status_update",
            {"status": "startup_complete", "starting_equity_usdt": 1000.0},
        )
        heartbeat = _event(
            run.id,
            "evt-heartbeat",
            start_ts + timedelta(minutes=1),
            "heartbeat",
            {
                "equity_usdt": 995.0,
                "current_pair": "ETH-USDT-SWAP/SOL-USDT-SWAP",
                "strategy": "STATARB_MR",
                "regime": "RANGE",
            },
        )
        db.add_all([startup, heartbeat])
        db.flush()

        materialize_run_entities_for_event(db, run, startup)
        materialize_run_entities_for_event(db, run, heartbeat)
        db.commit()

        snapshots = db.execute(
            select(EquitySnapshot).order_by(EquitySnapshot.ts.asc())
        ).scalars().all()

        assert len(snapshots) == 2
        assert snapshots[0].source == "startup"
        assert float(snapshots[0].equity_usdt) == 1000.0
        assert snapshots[1].source == "heartbeat"
        assert float(snapshots[1].equity_usdt) == 995.0
        assert float(snapshots[1].session_pnl_usdt) == -5.0
        assert snapshots[1].current_pair == "ETH-USDT-SWAP/SOL-USDT-SWAP"

        db.refresh(run)
        assert float(run.end_equity) == 995.0
        assert float(run.session_pnl) == -5.0
        assert float(run.max_drawdown) == -5.0
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
