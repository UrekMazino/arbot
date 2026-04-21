from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Platform.api.app.database import Base
from Platform.api.app.models import BotInstance, Report, ReportFile, Run
from Platform.api.app.services import bot_control


def _build_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _touch_dir(path: Path, ts: float) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.utime(path, (ts, ts))


def _touch_file(path: Path, content: str, ts: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    os.utime(path, (ts, ts))


def test_clear_logs_and_reports_removes_old_runs_indexes_and_report_rows(tmp_path, monkeypatch):
    engine, session_factory = _build_session_factory()
    db = session_factory()
    try:
        logs_root = tmp_path / "Logs" / "v1"
        reports_root = tmp_path / "Reports" / "v1"

        old_log_run = logs_root / "run_01_20260418_120000"
        latest_log_run = logs_root / "run_02_20260418_130000"
        _touch_dir(old_log_run, 100)
        _touch_dir(latest_log_run, 200)
        _touch_file(old_log_run / "log_20260418_120000.log", "old log", 100)
        _touch_file(latest_log_run / "log_20260418_130000.log", "latest log", 200)
        _touch_file(logs_root / "index.csv", "stale log index", 150)
        _touch_file(logs_root / "index.json", "{}", 150)
        control_log = logs_root / "superadmin_bot_control.log"
        _touch_file(control_log, "control log", 150)
        os.utime(old_log_run, (100, 100))
        os.utime(latest_log_run, (200, 200))

        old_report_run = reports_root / "run_01_20260418_120000"
        latest_report_run = reports_root / "run_02_20260418_130000"
        _touch_dir(old_report_run, 100)
        _touch_dir(latest_report_run, 200)
        _touch_file(old_report_run / "summary.json", "{}", 100)
        _touch_file(old_report_run / "nested" / "artifact.txt", "nested artifact", 100)
        _touch_file(latest_report_run / "summary.json", "{}", 200)
        _touch_file(reports_root / "index.csv", "stale report index", 150)
        _touch_file(reports_root / "index.json", "{}", 150)
        os.utime(old_report_run, (100, 100))
        os.utime(latest_report_run, (200, 200))

        bot = BotInstance(id="bot-1", name="default", environment="demo", is_active=True)
        old_run = Run(
            id="run-db-1",
            bot_instance_id=bot.id,
            run_key=old_report_run.name,
            status="stopped",
            start_ts=datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc),
        )
        latest_run = Run(
            id="run-db-2",
            bot_instance_id=bot.id,
            run_key=latest_report_run.name,
            status="stopped",
            start_ts=datetime(2026, 4, 18, 13, 0, 0, tzinfo=timezone.utc),
        )
        old_report = Report(id="report-old", run_id=old_run.id, status="done")
        latest_report = Report(id="report-latest", run_id=latest_run.id, status="done")
        old_report_file = ReportFile(
            id="report-file-old",
            report_id=old_report.id,
            name="summary.json",
            path=str(old_report_run / "summary.json"),
        )
        latest_report_file = ReportFile(
            id="report-file-latest",
            report_id=latest_report.id,
            name="summary.json",
            path=str(latest_report_run / "summary.json"),
        )

        db.add_all([bot, old_run, latest_run, old_report, latest_report, old_report_file, latest_report_file])
        db.commit()

        monkeypatch.setattr(bot_control, "LOGS_ROOT", logs_root)
        monkeypatch.setattr(bot_control, "REPORTS_ROOT", reports_root)
        monkeypatch.setattr(bot_control, "CONTROL_LOG_FILE", control_log)
        monkeypatch.setattr(bot_control, "SessionLocal", session_factory)

        result = bot_control.clear_logs_and_reports(keep_latest=True)

        expected = {
            "deleted_logs": 1,
            "deleted_reports": 1,
            "deleted_log_files": 1,
            "deleted_report_rows": 1,
            "deleted_report_files": 1,
            "deleted_indexes": 4,
            "kept_latest": True,
            "errors": [],
        }
        for key, value in expected.items():
            assert result[key] == value
        assert result["deleted_equity_snapshots"] == 0

        assert not old_log_run.exists()
        assert latest_log_run.exists()
        assert not old_report_run.exists()
        assert latest_report_run.exists()
        assert not (logs_root / "index.csv").exists()
        assert not (logs_root / "index.json").exists()
        assert not (reports_root / "index.csv").exists()
        assert not (reports_root / "index.json").exists()
        assert not control_log.exists()

        verify_db = session_factory()
        try:
            remaining_reports = verify_db.execute(select(Report).order_by(Report.id.asc())).scalars().all()
            remaining_report_files = verify_db.execute(select(ReportFile).order_by(ReportFile.id.asc())).scalars().all()
            assert [row.id for row in remaining_reports] == ["report-latest"]
            assert [row.id for row in remaining_report_files] == ["report-file-latest"]
        finally:
            verify_db.close()
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
