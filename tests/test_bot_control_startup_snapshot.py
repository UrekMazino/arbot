from __future__ import annotations

import json
import signal
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Platform.api.app.database import Base
from Platform.api.app.models import BotInstance, EquitySnapshot, Run, RunEvent, Trade
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


def _build_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine, sessionmaker(bind=engine, autocommit=False, autoflush=False)


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
    monkeypatch.setattr(bot_control, "_is_managed_bot_process", lambda _pid: True)
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


def test_normalize_status_rejects_reused_non_bot_pid(monkeypatch):
    monkeypatch.setattr(bot_control, "_pid_exists", lambda _pid: True)
    monkeypatch.setattr(bot_control, "_read_process_cmdline", lambda _pid: ["python", "-m", "uvicorn", "app.main:app"])
    monkeypatch.setattr(bot_control, "_latest_run_log_file", lambda: (None, None))
    monkeypatch.setattr(bot_control.os, "name", "posix", raising=False)

    result = bot_control._normalize_status({"running": True, "pid": 13, "detail": "started"})

    assert result["running"] is False
    assert result["detail"] == "stale_pid_reused"


def test_normalize_status_trusts_remote_runner_state(monkeypatch):
    monkeypatch.setenv("STATBOT_PROCESS_OWNER", "api")
    monkeypatch.setattr(bot_control, "_pid_exists", lambda _pid: False)
    monkeypatch.setattr(bot_control, "_latest_run_log_file", lambda: (None, None))

    result = bot_control._normalize_status(
        {
            "running": True,
            "pid": 13,
            "detail": "started",
            "process_mode": "runner",
            "process_owner": "bot-runner",
            "runner_heartbeat_at": bot_control._utc_iso_now(),
        }
    )

    assert result["running"] is True
    assert result["detail"] == "started"


def test_bot_child_env_uses_internal_api_port_inside_docker(monkeypatch):
    monkeypatch.setattr(bot_control.os, "name", "posix", raising=False)
    monkeypatch.setattr(bot_control.Path, "exists", lambda self: str(self) == "/workspace")

    env = bot_control._normalize_bot_child_env(
        {"STATBOT_EVENT_API_BASE": "http://127.0.0.1:8082/api/v2"}
    )

    assert env["STATBOT_EVENT_API_BASE"] == "http://127.0.0.1:8080/api/v2"


def test_stop_bot_does_not_signal_reused_non_bot_pid(monkeypatch):
    writes = []
    signal_calls = []

    monkeypatch.setattr(
        bot_control,
        "get_bot_status",
        lambda: {"running": True, "pid": 13, "requested_by": "", "detail": "started"},
    )
    monkeypatch.setattr(bot_control, "_pid_exists", lambda _pid: True)
    monkeypatch.setattr(bot_control, "_is_managed_bot_process", lambda _pid: False)
    monkeypatch.setattr(bot_control, "_normalize_status", lambda state: state)
    monkeypatch.setattr(bot_control, "_write_state", lambda state: writes.append(dict(state)))
    monkeypatch.setattr(bot_control.os, "killpg", lambda pgid, sig: signal_calls.append((pgid, sig)), raising=False)

    result = bot_control.stop_bot(requested_by="tester@example.com", timeout_seconds=1.0)

    assert signal_calls == []
    assert result["running"] is False
    assert result["detail"] == "stale_pid_reused"
    assert writes[-1]["requested_by"] == "tester@example.com"


def test_start_bot_runner_mode_records_start_request(monkeypatch):
    writes = []

    monkeypatch.setenv("STATBOT_BOT_PROCESS_MODE", "runner")
    monkeypatch.setattr(bot_control, "get_bot_status", lambda: {"running": False, "pid": 0})
    monkeypatch.setattr(bot_control, "_write_state", lambda state: writes.append(dict(state)))
    monkeypatch.setattr(bot_control, "_normalize_status", lambda state: state)

    result = bot_control.start_bot(requested_by="tester@example.com")

    assert result["desired_running"] is True
    assert result["detail"] == "start_requested"
    assert writes[-1]["process_mode"] == "runner"
    assert writes[-1]["requested_by"] == "tester@example.com"


def test_stop_bot_runner_mode_records_stop_request(monkeypatch):
    writes = []

    monkeypatch.setenv("STATBOT_BOT_PROCESS_MODE", "runner")
    monkeypatch.setattr(bot_control, "get_bot_status", lambda: {"running": True, "pid": 123, "detail": "started"})
    monkeypatch.setattr(bot_control, "_write_state", lambda state: writes.append(dict(state)))
    monkeypatch.setattr(bot_control, "_normalize_status", lambda state: state)

    result = bot_control.stop_bot(requested_by="tester@example.com")

    assert result["desired_running"] is False
    assert result["detail"] == "stop_requested"
    assert writes[-1]["process_mode"] == "runner"
    assert writes[-1]["requested_by"] == "tester@example.com"


def test_manual_switch_stopped_bot_sets_active_pair(tmp_path, monkeypatch):
    active_pair_file = tmp_path / "Execution" / "state" / "active_pair.json"
    manual_switch_file = tmp_path / "Execution" / "state" / "manual_pair_switch.json"
    control_log = tmp_path / "Logs" / "v1" / "superadmin_bot_control.log"
    fake_session = _FakeSession()

    monkeypatch.setattr(bot_control, "ACTIVE_PAIR_FILE", active_pair_file)
    monkeypatch.setattr(bot_control, "MANUAL_PAIR_SWITCH_FILE", manual_switch_file)
    monkeypatch.setattr(bot_control, "CONTROL_LOG_FILE", control_log)
    monkeypatch.setattr(bot_control, "SessionLocal", lambda: fake_session)
    monkeypatch.setattr(bot_control, "get_bot_status", lambda: {"running": False, "pid": 0})
    monkeypatch.setattr(bot_control, "_latest_run_for_manual_switch", lambda _db, _status: None)
    monkeypatch.setattr(bot_control, "_manual_switch_blockers", lambda _db, _run, bot_running=False: [])
    monkeypatch.setattr(bot_control, "_manual_switch_target_in_pair_universe", lambda _t1, _t2: True)

    result = bot_control.manual_switch_active_pair(
        "aaa-usdt-swap",
        "bbb-usdt-swap",
        requested_by="tester@example.com",
    )
    active = json.loads(active_pair_file.read_text(encoding="utf-8"))

    assert result["status"] == "applied"
    assert result["running"] is False
    assert active["ticker_1"] == "AAA-USDT-SWAP"
    assert active["ticker_2"] == "BBB-USDT-SWAP"
    assert not manual_switch_file.exists()
    assert "Manual active pair set" in control_log.read_text(encoding="utf-8")


def test_manual_switch_running_bot_writes_request_file(tmp_path, monkeypatch):
    active_pair_file = tmp_path / "Execution" / "state" / "active_pair.json"
    manual_switch_file = tmp_path / "Execution" / "state" / "manual_pair_switch.json"
    control_log = tmp_path / "Logs" / "v1" / "superadmin_bot_control.log"
    active_pair_file.parent.mkdir(parents=True)
    active_pair_file.write_text(
        json.dumps({"ticker_1": "OLD1-USDT-SWAP", "ticker_2": "OLD2-USDT-SWAP"}),
        encoding="utf-8",
    )
    fake_session = _FakeSession()

    monkeypatch.setattr(bot_control, "ACTIVE_PAIR_FILE", active_pair_file)
    monkeypatch.setattr(bot_control, "MANUAL_PAIR_SWITCH_FILE", manual_switch_file)
    monkeypatch.setattr(bot_control, "CONTROL_LOG_FILE", control_log)
    monkeypatch.setattr(bot_control, "SessionLocal", lambda: fake_session)
    monkeypatch.setattr(bot_control, "get_bot_status", lambda: {"running": True, "pid": 123, "run_key": "run_01"})
    monkeypatch.setattr(bot_control, "_latest_run_for_manual_switch", lambda _db, _status: None)
    monkeypatch.setattr(bot_control, "_manual_switch_blockers", lambda _db, _run, bot_running=False: [])
    monkeypatch.setattr(bot_control, "_manual_switch_target_in_pair_universe", lambda _t1, _t2: True)

    result = bot_control.manual_switch_active_pair(
        "AAA-USDT-SWAP",
        "BBB-USDT-SWAP",
        requested_by="tester@example.com",
    )
    request = json.loads(manual_switch_file.read_text(encoding="utf-8"))

    assert result["status"] == "requested"
    assert result["pending"] is True
    assert request["status"] == "requested"
    assert request["ticker_1"] == "AAA-USDT-SWAP"
    assert request["ticker_2"] == "BBB-USDT-SWAP"
    assert request["from_pair"] == "OLD1-USDT-SWAP/OLD2-USDT-SWAP"


def test_manual_switch_blocked_when_runtime_reports_position(tmp_path, monkeypatch):
    manual_switch_file = tmp_path / "Execution" / "state" / "manual_pair_switch.json"
    control_log = tmp_path / "Logs" / "v1" / "superadmin_bot_control.log"
    fake_session = _FakeSession()

    monkeypatch.setattr(bot_control, "MANUAL_PAIR_SWITCH_FILE", manual_switch_file)
    monkeypatch.setattr(bot_control, "CONTROL_LOG_FILE", control_log)
    monkeypatch.setattr(bot_control, "SessionLocal", lambda: fake_session)
    monkeypatch.setattr(bot_control, "get_bot_status", lambda: {"running": True, "pid": 123, "run_key": "run_01"})
    monkeypatch.setattr(bot_control, "_latest_run_for_manual_switch", lambda _db, _status: None)
    monkeypatch.setattr(
        bot_control,
        "_manual_switch_blockers",
        lambda _db, _run, bot_running=False: ["Latest heartbeat reports the bot is still in position/orders."],
    )
    monkeypatch.setattr(bot_control, "_manual_switch_target_in_pair_universe", lambda _t1, _t2: True)

    with pytest.raises(bot_control.ManualPairSwitchBlocked) as exc_info:
        bot_control.manual_switch_active_pair(
            "AAA-USDT-SWAP",
            "BBB-USDT-SWAP",
            requested_by="tester@example.com",
        )

    assert exc_info.value.result["status"] == "blocked"
    assert "position/orders" in exc_info.value.result["detail"]
    assert not manual_switch_file.exists()
    assert "Manual pair switch blocked" in control_log.read_text(encoding="utf-8")


def test_manual_switch_blockers_ignore_stale_open_trade_after_trade_close_event():
    engine, session_factory = _build_session_factory()
    db = session_factory()
    try:
        pair_key = "XRP-USDT-SWAP/SUI-USDT-SWAP"
        start_ts = datetime(2026, 4, 23, 8, 0, tzinfo=timezone.utc)
        close_ts = start_ts + timedelta(minutes=4)
        bot = BotInstance(id="bot-1", name="default", environment="demo", is_active=True)
        run = Run(id="run-1", bot_instance_id=bot.id, run_key="run_01_20260423_080000", status="running", start_ts=start_ts)
        db.add_all(
            [
                bot,
                run,
                Trade(run_id=run.id, pair_key=pair_key, entry_ts=start_ts + timedelta(minutes=1)),
                RunEvent(
                    event_id="evt-close-1",
                    run_id=run.id,
                    bot_instance_id=bot.id,
                    ts=close_ts,
                    event_type="trade_close",
                    severity="info",
                    payload_json={"pair": pair_key, "in_position": False},
                ),
            ]
        )
        db.commit()

        blockers = bot_control._manual_switch_blockers(db, run, bot_running=True)

        assert blockers == []
    finally:
        db.close()
        engine.dispose()


def test_manual_switch_blockers_ignore_stale_open_trade_after_flat_equity_snapshot():
    engine, session_factory = _build_session_factory()
    db = session_factory()
    try:
        pair_key = "XRP-USDT-SWAP/SUI-USDT-SWAP"
        start_ts = datetime(2026, 4, 23, 9, 0, tzinfo=timezone.utc)
        flat_ts = start_ts + timedelta(minutes=6)
        bot = BotInstance(id="bot-2", name="default-2", environment="demo", is_active=True)
        run = Run(id="run-2", bot_instance_id=bot.id, run_key="run_02_20260423_090000", status="running", start_ts=start_ts)
        db.add_all(
            [
                bot,
                run,
                Trade(run_id=run.id, pair_key=pair_key, entry_ts=start_ts + timedelta(minutes=1)),
                EquitySnapshot(
                    run_id=run.id,
                    ts=flat_ts,
                    equity_usdt=1000,
                    current_pair=pair_key,
                    in_position=False,
                    source="heartbeat",
                    source_event_id="eq-flat-1",
                ),
            ]
        )
        db.commit()

        blockers = bot_control._manual_switch_blockers(db, run, bot_running=True)

        assert blockers == []
    finally:
        db.close()
        engine.dispose()


def test_manual_switch_blockers_keep_open_trade_without_flat_runtime_evidence():
    engine, session_factory = _build_session_factory()
    db = session_factory()
    try:
        pair_key = "XRP-USDT-SWAP/SUI-USDT-SWAP"
        start_ts = datetime(2026, 4, 23, 10, 0, tzinfo=timezone.utc)
        bot = BotInstance(id="bot-3", name="default-3", environment="demo", is_active=True)
        run = Run(id="run-3", bot_instance_id=bot.id, run_key="run_03_20260423_100000", status="running", start_ts=start_ts)
        db.add_all(
            [
                bot,
                run,
                Trade(run_id=run.id, pair_key=pair_key, entry_ts=start_ts + timedelta(minutes=1)),
            ]
        )
        db.commit()

        blockers = bot_control._manual_switch_blockers(db, run, bot_running=True)

        assert blockers == [f"Open trade record exists for {pair_key}; wait for it to close before switching."]
    finally:
        db.close()
        engine.dispose()


def test_remove_pair_from_graveyard_removes_normalized_pair_only(tmp_path, monkeypatch):
    state_file = tmp_path / "Execution" / "state" / "pair_strategy_state.json"
    ticker_graveyard_file = tmp_path / "Execution" / "state" / "graveyard_tickers.json"
    control_log = tmp_path / "Logs" / "v1" / "superadmin_bot_control.log"
    state_file.parent.mkdir(parents=True)
    state_file.write_text(
        json.dumps(
            {
                "graveyard": {
                    "AAA-USDT-SWAP/BBB-USDT-SWAP": {
                        "ts": 123.0,
                        "reason": "manual",
                        "ttl_days": None,
                    },
                    "ticker::DOGE-USDT-SWAP": {
                        "ticker": "DOGE-USDT-SWAP",
                        "reason": "manual_ticker",
                        "source": "runtime",
                    },
                },
                "hospital": {},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(bot_control, "PAIR_STRATEGY_STATE_FILE", state_file)
    monkeypatch.setattr(bot_control, "GRAVEYARD_TICKERS_FILE", ticker_graveyard_file)
    monkeypatch.setattr(bot_control, "CONTROL_LOG_FILE", control_log)
    monkeypatch.setattr(bot_control, "ENV_FILE", tmp_path / "Execution" / ".env")

    result = bot_control.remove_pair_from_graveyard(
        pair="BBB-USDT-SWAP/AAA-USDT-SWAP",
        requested_by="tester@example.com",
    )

    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert result["removed"] is True
    assert result["pair_key"] == "AAA-USDT-SWAP/BBB-USDT-SWAP"
    assert "AAA-USDT-SWAP/BBB-USDT-SWAP" not in data["graveyard"]
    assert "ticker::DOGE-USDT-SWAP" in data["graveyard"]
    assert result["health"]["graveyard"] == []
    assert data["graveyard_last_removed_pair"] == "AAA-USDT-SWAP/BBB-USDT-SWAP"


def test_remove_pair_from_graveyard_returns_not_found_without_creating_state(tmp_path, monkeypatch):
    state_file = tmp_path / "Execution" / "state" / "pair_strategy_state.json"
    ticker_graveyard_file = tmp_path / "Execution" / "state" / "graveyard_tickers.json"
    monkeypatch.setattr(bot_control, "PAIR_STRATEGY_STATE_FILE", state_file)
    monkeypatch.setattr(bot_control, "GRAVEYARD_TICKERS_FILE", ticker_graveyard_file)

    result = bot_control.remove_pair_from_graveyard(
        sym_1="AAA-USDT-SWAP",
        sym_2="BBB-USDT-SWAP",
        requested_by="tester@example.com",
    )

    assert result["removed"] is False
    assert result["status"] == "not_found"
    assert result["pair_key"] == "AAA-USDT-SWAP/BBB-USDT-SWAP"
    assert not state_file.exists()
