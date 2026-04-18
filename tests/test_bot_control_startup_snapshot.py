from __future__ import annotations

import json
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Platform.api.app.routers import events
from Platform.api.app.services import bot_control


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, run=None):
        self.run = run
        self.commit_count = 0
        self.added = []

    def get(self, *_args, **_kwargs):
        return None

    def execute(self, _stmt):
        return _FakeResult(self.run)

    def add(self, value):
        self.added.append(value)

    def flush(self):
        return None

    def commit(self):
        self.commit_count += 1

    def close(self):
        return None


def test_tail_run_log_reads_and_persists_starting_equity_from_log_header(tmp_path, monkeypatch):
    logs_root = tmp_path / "Logs" / "v1"
    run_key = "run_01_20260418_120000"
    run_dir = logs_root / run_key
    run_dir.mkdir(parents=True)
    log_file = run_dir / "log_20260418_120000.log"
    log_file.write_text(
        "\n".join(
            [
                "2026-04-18 12:00:00 INFO Starting equity: 100.50 USDT",
                "2026-04-18 12:00:01 INFO Boot complete",
                "2026-04-18 12:10:00 INFO heartbeat",
                "2026-04-18 12:20:00 INFO PnL: 4.20 USDT (4.18%) | Equity: 104.70 USDT | Session: 4.20 USDT (4.18%)",
            ]
        ),
        encoding="utf-8",
    )

    state_file = tmp_path / "state" / "ui_bot_control.json"
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({"run_key": run_key}), encoding="utf-8")

    fake_run = SimpleNamespace(id="run-db-1", run_key=run_key, start_equity=None, start_ts=None)
    fake_session = _FakeSession(run=fake_run)

    monkeypatch.setattr(bot_control, "LOGS_ROOT", logs_root)
    monkeypatch.setattr(bot_control, "CONTROL_LOG_FILE", logs_root / "superadmin_bot_control.log")
    monkeypatch.setattr(bot_control, "STATE_FILE", state_file)
    monkeypatch.setattr(bot_control, "SessionLocal", lambda: fake_session)

    tail = bot_control.tail_run_log(run_key=run_key, lines=1)

    assert tail["run_key"] == run_key
    assert tail["line_count"] == 1
    assert tail["starting_equity"] == 100.5
    assert tail["equity"] == 104.7
    assert tail["session_pnl"] == 4.2
    assert tail["run_start_time"] == datetime(2026, 4, 18, 12, 0, 0).timestamp()
    assert fake_run.start_equity == 100.5
    assert fake_run.start_ts == datetime.fromtimestamp(
        datetime(2026, 4, 18, 12, 0, 0).timestamp(),
        tz=timezone.utc,
    )
    assert fake_session.commit_count == 1

    state_data = json.loads(state_file.read_text(encoding="utf-8"))
    assert state_data["starting_equity"] == 100.5
    assert state_data["run_start_time"] == datetime(2026, 4, 18, 12, 0, 0).timestamp()


def test_tail_run_log_falls_back_to_control_log_for_active_run_snapshot(tmp_path, monkeypatch):
    logs_root = tmp_path / "Logs" / "v1"
    run_key = "run_03_20260418_123000"
    run_dir = logs_root / run_key
    run_dir.mkdir(parents=True)
    log_file = run_dir / "log_20260418_123000.log"
    log_file.write_text(
        "\n".join(
            [
                "2026-04-18 12:30:05 INFO Boot phase",
                "2026-04-18 12:30:06 INFO Still starting",
            ]
        ),
        encoding="utf-8",
    )

    control_log = logs_root / "superadmin_bot_control.log"
    control_log.write_text(
        "\n".join(
            [
                "2026-04-18 12:29:50 INFO Previous run noise",
                "2026-04-18 12:30:01 INFO Starting equity: 321.09 USDT",
                "2026-04-18 12:30:01 INFO Balance snapshot (USDT): availBal=320.00 | availEq=321.09 | td_mode=cross | pos_mode=long_short",
            ]
        ),
        encoding="utf-8",
    )

    state_file = tmp_path / "state" / "ui_bot_control.json"
    state_file.parent.mkdir(parents=True)
    state_file.write_text(
        json.dumps(
            {
                "run_key": run_key,
                "started_at": "2026-04-18T12:30:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    fake_run = SimpleNamespace(id="run-db-2", run_key=run_key, start_equity=None, start_ts=None)
    fake_session = _FakeSession(run=fake_run)

    monkeypatch.setattr(bot_control, "LOGS_ROOT", logs_root)
    monkeypatch.setattr(bot_control, "CONTROL_LOG_FILE", control_log)
    monkeypatch.setattr(bot_control, "STATE_FILE", state_file)
    monkeypatch.setattr(bot_control, "SessionLocal", lambda: fake_session)

    tail = bot_control.tail_run_log(run_key=run_key, lines=10)

    assert tail["starting_equity"] == 321.09
    assert fake_run.start_equity == 321.09


def test_tail_run_log_infers_pair_history_from_startup_ticker_configuration(tmp_path, monkeypatch):
    logs_root = tmp_path / "Logs" / "v1"
    run_key = "run_04_20260418_124500"
    run_dir = logs_root / run_key
    run_dir.mkdir(parents=True)
    log_file = run_dir / "log_20260418_124500.log"
    log_file.write_text(
        "\n".join(
            [
                "2026-04-18 12:45:00 INFO Starting equity: 999.00 USDT",
                "2026-04-18 12:45:01 INFO Ticker configuration validated: ticker_1=CRV-USDT-SWAP, ticker_2=ETHW-USDT-SWAP, signal_positive=ETHW-USDT-SWAP, signal_negative=CRV-USDT-SWAP",
                "2026-04-18 12:47:00 INFO Heartbeat",
            ]
        ),
        encoding="utf-8",
    )

    state_file = tmp_path / "state" / "ui_bot_control.json"
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({"run_key": run_key}), encoding="utf-8")

    fake_run = SimpleNamespace(id="run-db-3", run_key=run_key, start_equity=None, start_ts=None)
    fake_session = _FakeSession(run=fake_run)

    monkeypatch.setattr(bot_control, "LOGS_ROOT", logs_root)
    monkeypatch.setattr(bot_control, "CONTROL_LOG_FILE", logs_root / "superadmin_bot_control.log")
    monkeypatch.setattr(bot_control, "STATE_FILE", state_file)
    monkeypatch.setattr(bot_control, "SessionLocal", lambda: fake_session)

    tail = bot_control.tail_run_log(run_key=run_key, lines=50)

    assert tail["pair_count"] == 1
    assert tail["pair_history"] == [
        {
            "pair": "CRV-USDT-SWAP/ETHW-USDT-SWAP",
            "duration_seconds": 119.0,
        }
    ]


def test_tail_run_log_keeps_pair_history_when_switch_markers_scroll_out_of_display_tail(tmp_path, monkeypatch):
    logs_root = tmp_path / "Logs" / "v1"
    run_key = "run_05_20260418_130000"
    run_dir = logs_root / run_key
    run_dir.mkdir(parents=True)
    log_file = run_dir / "log_20260418_130000.log"

    lines = [
        "2026-04-18 13:00:00 INFO Starting equity: 1500.00 USDT",
        "2026-04-18 13:00:01 INFO Ticker configuration validated: ticker_1=CRV-USDT-SWAP, ticker_2=ETHW-USDT-SWAP, signal_positive=ETHW-USDT-SWAP, signal_negative=CRV-USDT-SWAP",
        "2026-04-18 13:05:00 INFO Current pair: CRV-USDT-SWAP/ETHW-USDT-SWAP",
        "2026-04-18 13:05:10 INFO Switching from CRV-USDT-SWAP/ETHW-USDT-SWAP to BAND-USDT-SWAP/CHZ-USDT-SWAP",
    ]
    for idx in range(200):
        minute = 5 + ((11 + idx) // 60)
        second = (11 + idx) % 60
        lines.append(f"2026-04-18 13:{minute:02d}:{second:02d} INFO Heartbeat {idx}")
    log_file.write_text("\n".join(lines), encoding="utf-8")

    state_file = tmp_path / "state" / "ui_bot_control.json"
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({"run_key": run_key}), encoding="utf-8")

    fake_run = SimpleNamespace(id="run-db-5", run_key=run_key, start_equity=None, start_ts=None)
    fake_session = _FakeSession(run=fake_run)

    monkeypatch.setattr(bot_control, "LOGS_ROOT", logs_root)
    monkeypatch.setattr(bot_control, "CONTROL_LOG_FILE", logs_root / "superadmin_bot_control.log")
    monkeypatch.setattr(bot_control, "STATE_FILE", state_file)
    monkeypatch.setattr(bot_control, "SessionLocal", lambda: fake_session)

    tail = bot_control.tail_run_log(run_key=run_key, lines=50)

    assert tail["line_count"] == 50
    assert tail["pair_count"] == 2
    assert tail["pair_history"] == [
        {
            "pair": "CRV-USDT-SWAP/ETHW-USDT-SWAP",
            "duration_seconds": 309.0,
        },
        {
            "pair": "BAND-USDT-SWAP/CHZ-USDT-SWAP",
            "duration_seconds": 200.0,
        },
    ]


def test_ensure_run_prefers_existing_run_key_record():
    existing_run = SimpleNamespace(id="db-run-123", run_key="run_02_20260418_121500")
    fake_session = _FakeSession(run=existing_run)

    resolved = events._ensure_run(fake_session, "run_02_20260418_121500", "bot-1")

    assert resolved is existing_run
    assert fake_session.added == []


def test_apply_run_metrics_from_event_updates_start_and_live_equity():
    run = SimpleNamespace(
        start_equity=None,
        end_equity=None,
        session_pnl=None,
        status="pending",
        end_ts=None,
    )

    startup_event = SimpleNamespace(
        event_type="status_update",
        payload={"status": "startup_complete", "starting_equity_usdt": "250.75"},
        ts=datetime(2026, 4, 18, 12, 0, 0, tzinfo=timezone.utc).timestamp(),
    )
    heartbeat_event = SimpleNamespace(
        event_type="heartbeat",
        payload={"equity_usdt": "255.10", "session_pnl_usdt": "4.35"},
        ts=datetime(2026, 4, 18, 12, 5, 0, tzinfo=timezone.utc).timestamp(),
    )
    stop_event = SimpleNamespace(
        event_type="status_update",
        payload={"status": "run_end"},
        ts=datetime(2026, 4, 18, 12, 30, 0, tzinfo=timezone.utc).timestamp(),
    )

    events._apply_run_metrics_from_event(run, startup_event)
    events._apply_run_metrics_from_event(run, heartbeat_event)
    events._apply_run_metrics_from_event(run, stop_event)

    assert run.start_equity == 250.75
    assert run.end_equity == 255.10
    assert run.session_pnl == 4.35
    assert run.status == "stopped"
    assert run.end_ts == datetime(2026, 4, 18, 12, 30, 0, tzinfo=timezone.utc)


def test_stop_bot_prefers_interrupt_for_graceful_shutdown(monkeypatch):
    writes = []
    signal_calls = []

    monkeypatch.setattr(
        bot_control,
        "get_bot_status",
        lambda: {"running": True, "pid": 123, "requested_by": "", "detail": "started"},
    )
    monkeypatch.setattr(bot_control, "_normalize_status", lambda state: state)
    monkeypatch.setattr(bot_control, "_write_state", lambda state: writes.append(dict(state)))
    monkeypatch.setattr(bot_control, "_pid_exists", lambda _pid: False)
    monkeypatch.setattr(bot_control.os, "name", "posix", raising=False)
    monkeypatch.setattr(bot_control.os, "getpgid", lambda pid: pid, raising=False)
    monkeypatch.setattr(bot_control.os, "killpg", lambda pgid, sig: signal_calls.append((pgid, sig)), raising=False)

    result = bot_control.stop_bot(requested_by="tester@example.com", timeout_seconds=1.0)

    assert signal_calls == [(123, signal.SIGINT)]
    assert result["running"] is False
    assert result["detail"] == "stopped"
    assert writes[-1]["requested_by"] == "tester@example.com"
