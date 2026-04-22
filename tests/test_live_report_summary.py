from __future__ import annotations

import json
import os
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
from Platform.api.app.services import bot_control, live_report
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
        bot_instance_id="bot-live-1",
        ts=ts,
        event_type=event_type,
        severity="info",
        payload_json=payload,
    )


def _create_run(db, *, run_key: str, start_ts: datetime) -> Run:
    bot = BotInstance(id="bot-live-1", name="default", environment="demo", is_active=True)
    run = Run(
        id=f"{run_key}-id",
        bot_instance_id=bot.id,
        run_key=run_key,
        status="running",
        start_ts=start_ts,
        start_equity=1000.0,
    )
    db.add_all([bot, run])
    db.flush()
    return run


def _materialize(db, run: Run, *events: RunEvent) -> None:
    db.add_all(events)
    db.flush()
    for event in events:
        materialize_run_entities_for_event(db, run, event)
    db.commit()


def _read_summary(root: Path, run_key: str) -> dict:
    return json.loads((root / run_key / "summary.json").read_text(encoding="utf-8"))


def test_live_report_counts_open_trade_as_trade_total(monkeypatch, tmp_path):
    reports_root = tmp_path / "Reports" / "v1"
    monkeypatch.setattr(live_report, "REPORTS_ROOT", reports_root)

    engine, session_factory = _build_session_factory()
    db = session_factory()
    try:
        start_ts = datetime(2026, 4, 22, 3, 0, 0, tzinfo=timezone.utc)
        run = _create_run(db, run_key="run_live_open", start_ts=start_ts)
        open_event = _event(
            run.id,
            "evt-open-1",
            start_ts + timedelta(minutes=2),
            "trade_open",
            {
                "pair": "ETH-USDT-SWAP/SOL-USDT-SWAP",
                "side": "long_spread",
                "entry_ts": (start_ts + timedelta(minutes=2)).isoformat(),
                "entry_z": -2.1,
                "strategy": "STATARB_MR",
                "regime": "RANGE",
            },
        )
        _materialize(db, run, open_event)

        result = live_report.materialize_live_run_report(db, run)
        summary = _read_summary(reports_root, run.run_key)
        manifest = json.loads((reports_root / run.run_key / "report_manifest.json").read_text(encoding="utf-8"))

        assert result["saved"] is True
        assert summary["trades_total"] == 1
        assert summary["trade_opens_total"] == 1
        assert summary["open_trades_total"] == 1
        assert summary["closed_trades_total"] == 0
        assert summary["wins"] == 0
        assert summary["losses"] == 0
        assert summary["win_rate_pct"] is None
        assert summary["win_rate_basis"] == "closed_trades"
        assert (reports_root / run.run_key / "open_trades.csv").exists()
        assert any(entry["name"] == "open_trades.csv" for entry in manifest["files"])
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_live_report_splits_open_and_closed_trade_counts(monkeypatch, tmp_path):
    reports_root = tmp_path / "Reports" / "v1"
    monkeypatch.setattr(live_report, "REPORTS_ROOT", reports_root)

    engine, session_factory = _build_session_factory()
    db = session_factory()
    try:
        start_ts = datetime(2026, 4, 22, 4, 0, 0, tzinfo=timezone.utc)
        run = _create_run(db, run_key="run_live_mixed", start_ts=start_ts)
        first_entry_ts = start_ts + timedelta(minutes=1)
        first_open = _event(
            run.id,
            "evt-open-1",
            first_entry_ts,
            "trade_open",
            {
                "pair": "ETH-USDT-SWAP/SOL-USDT-SWAP",
                "side": "long_spread",
                "entry_ts": first_entry_ts.isoformat(),
                "entry_z": -2.0,
                "strategy": "STATARB_MR",
                "regime": "RANGE",
            },
        )
        first_close = _event(
            run.id,
            "evt-close-1",
            first_entry_ts + timedelta(minutes=12),
            "trade_close",
            {
                "pair": "ETH-USDT-SWAP/SOL-USDT-SWAP",
                "side": "long_spread",
                "entry_ts": first_entry_ts.isoformat(),
                "entry_z": -2.0,
                "exit_z": -0.2,
                "pnl_usdt": 1.5,
                "hold_minutes": 12,
                "strategy": "STATARB_MR",
                "regime": "RANGE",
            },
        )
        second_entry_ts = start_ts + timedelta(minutes=20)
        second_open = _event(
            run.id,
            "evt-open-2",
            second_entry_ts,
            "trade_open",
            {
                "pair": "BTC-USDT-SWAP/ETH-USDT-SWAP",
                "side": "short_spread",
                "entry_ts": second_entry_ts.isoformat(),
                "entry_z": 2.4,
                "strategy": "STATARB_MR",
                "regime": "RANGE",
            },
        )
        _materialize(db, run, first_open, first_close, second_open)

        live_report.materialize_live_run_report(db, run)
        summary = _read_summary(reports_root, run.run_key)

        assert summary["trades_total"] == 2
        assert summary["trade_opens_total"] == 2
        assert summary["open_trades_total"] == 1
        assert summary["closed_trades_total"] == 1
        assert summary["wins"] == 1
        assert summary["losses"] == 0
        assert summary["win_rate_pct"] == 100.0
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_report_summary_refreshes_stopped_run_when_db_events_are_newer(monkeypatch, tmp_path):
    reports_root = tmp_path / "Reports" / "v1"
    monkeypatch.setattr(live_report, "REPORTS_ROOT", reports_root)
    monkeypatch.setattr(bot_control, "REPORTS_ROOT", reports_root)

    engine, session_factory = _build_session_factory()
    db = session_factory()
    try:
        start_ts = datetime(2026, 4, 22, 5, 0, 0, tzinfo=timezone.utc)
        run = _create_run(db, run_key="run_live_refresh", start_ts=start_ts)
        first_open = _event(
            run.id,
            "evt-open-1",
            start_ts + timedelta(minutes=1),
            "trade_open",
            {
                "pair": "ETH-USDT-SWAP/SOL-USDT-SWAP",
                "entry_ts": (start_ts + timedelta(minutes=1)).isoformat(),
                "strategy": "STATARB_MR",
            },
        )
        _materialize(db, run, first_open)
        live_report.materialize_live_run_report(db, run)

        run.status = "stopped"
        run.end_ts = start_ts + timedelta(minutes=5)
        second_open = _event(
            run.id,
            "evt-open-2",
            start_ts + timedelta(minutes=6),
            "trade_open",
            {
                "pair": "BTC-USDT-SWAP/ETH-USDT-SWAP",
                "entry_ts": (start_ts + timedelta(minutes=6)).isoformat(),
                "strategy": "STATARB_MR",
            },
        )
        _materialize(db, run, second_open)

        summary_path = reports_root / run.run_key / "summary.json"
        os.utime(summary_path, (1, 1))

        response = bot_control.get_report_run_summary(db, run.run_key)

        assert response["refreshed"] is True
        assert response["summary"]["trades_total"] == 2
        assert response["summary"]["open_trades_total"] == 2
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
