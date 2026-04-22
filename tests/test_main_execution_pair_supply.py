from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXECUTION_DIR = ROOT / "Execution"
if str(EXECUTION_DIR) not in sys.path:
    sys.path.insert(0, str(EXECUTION_DIR))

import main_execution as me


def _write_supply_state(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_pair_supply_scan_progress_reads_active_price_history(monkeypatch, tmp_path):
    log_path = tmp_path / "pair_supply_scheduler.log"
    log_path.write_text(
        "\n".join(
            [
                "2026-04-22T01:22:49.227768+00:00 pair_supply scan_start",
                "[###---------------------] 16/122 ACT-USDT-SWAP | OK 10080 candles | stored 16/122",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(me, "PAIR_SUPPLY_LOG_FILE", log_path)

    progress = me._read_pair_supply_scan_progress({"log_file": str(log_path)})

    assert progress["known"] is True
    assert progress["active"] is True
    assert progress["current"] == 16
    assert progress["total"] == 122
    assert progress["phase"] == "fetching price history"


def test_pair_supply_scan_progress_ignores_timestamp_glued_to_stored_total(monkeypatch, tmp_path):
    log_path = tmp_path / "pair_supply_scheduler.log"
    log_path.write_text(
        "\n".join(
            [
                "2026-04-22T01:22:49.227768+00:00 pair_supply scan_start",
                "[##########--------------] 54/122 HBAR-USDT-SWAP | OK 10080 candles | stored 54/1222026-04-22 09:46:52,746 INFO next log",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(me, "PAIR_SUPPLY_LOG_FILE", log_path)

    progress = me._read_pair_supply_scan_progress({"log_file": str(log_path)})

    assert progress["current"] == 54
    assert progress["total"] == 122


def test_pair_supply_scan_progress_detects_watched_completion_with_next_scan_active(monkeypatch, tmp_path):
    log_path = tmp_path / "pair_supply_scheduler.log"
    watched_start = "2026-04-22T01:00:00.000000+00:00"
    log_path.write_text(
        "\n".join(
            [
                f"{watched_start} pair_supply scan_start",
                "[########################] 122/122 HOOD-USDT-SWAP | OK 10080 candles | stored 122/122",
                "2026-04-22T02:00:00.000000+00:00 pair_supply scan_end exit_code=0 elapsed_seconds=3600.0",
                "2026-04-22T02:00:00.100000+00:00 pair_supply scan_start",
                "[------------------------] 1/122 SOL-USDT-SWAP | OK 10080 candles | stored 1/122",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(me, "PAIR_SUPPLY_LOG_FILE", log_path)

    progress = me._read_pair_supply_scan_progress(
        {"log_file": str(log_path)},
        watch_started_at=watched_start,
    )

    assert progress["active"] is True
    assert progress["watched_completed"] is True
    assert progress["latest_start_at"] == "2026-04-22T02:00:00.100000+00:00"
    assert progress["current"] == 1
    assert progress["total"] == 122


def test_execution_defers_to_fresh_pair_supply_start_request(monkeypatch, tmp_path):
    state_path = tmp_path / "pair_supply_control.json"
    now = datetime.now(timezone.utc).isoformat()
    _write_supply_state(
        state_path,
        {
            "running": False,
            "desired_running": True,
            "detail": "start_requested",
            "process_mode": "runner",
            "process_owner": "pair-supply-runner",
            "request_updated_at": now,
        },
    )

    monkeypatch.setattr(me, "PAIR_SUPPLY_STATE_FILE", state_path)
    monkeypatch.setattr(me.subprocess, "call", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()))

    status = me._get_pair_supply_runtime_status()

    assert status["running"] is False
    assert status["desired_running"] is True
    assert status["defer_to_supply"] is True
    assert me._run_strategy_refresh() is False


def test_execution_trusts_fresh_remote_pair_supply_state_without_local_pid(monkeypatch, tmp_path):
    state_path = tmp_path / "pair_supply_control.json"
    now = datetime.now(timezone.utc).isoformat()
    _write_supply_state(
        state_path,
        {
            "running": True,
            "desired_running": True,
            "pid": 12345,
            "detail": "started",
            "process_owner": "pair-supply-runner",
            "updated_at": now,
        },
    )

    monkeypatch.setenv("STATBOT_PROCESS_OWNER", "bot-runner")
    monkeypatch.setattr(me, "PAIR_SUPPLY_STATE_FILE", state_path)
    monkeypatch.setattr(me, "_pid_matches_pair_supply", lambda _pid: False)

    status = me._get_pair_supply_runtime_status()

    assert status["running"] is True
    assert status["defer_to_supply"] is True


def test_execution_does_not_defer_to_stale_pair_supply_request(monkeypatch, tmp_path):
    state_path = tmp_path / "pair_supply_control.json"
    old = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
    _write_supply_state(
        state_path,
        {
            "running": False,
            "desired_running": True,
            "detail": "start_requested",
            "process_mode": "runner",
            "process_owner": "pair-supply-runner",
            "request_updated_at": old,
            "runner_heartbeat_at": old,
            "updated_at": old,
        },
    )

    monkeypatch.setattr(me, "PAIR_SUPPLY_STATE_FILE", state_path)

    status = me._get_pair_supply_runtime_status()

    assert status["running"] is False
    assert status["defer_to_supply"] is False
