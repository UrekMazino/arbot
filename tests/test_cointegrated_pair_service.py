from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from Platform.api.app.services import cointegrated_pairs as cp


def _write_price_json(path: Path) -> None:
    rows_a = []
    rows_b = []
    for idx, (a, b) in enumerate([(10.0, 20.0), (10.2, 20.1), (10.1, 20.2), (10.4, 20.0)]):
        ts = str(1_776_700_000_000 + idx * 60_000)
        rows_a.append({"timestamp": ts, "close": a})
        rows_b.append({"timestamp": ts, "close": b})
    path.write_text(
        json.dumps(
            {
                "AAA-USDT-SWAP": {"klines": rows_a},
                "BBB-USDT-SWAP": {"klines": rows_b},
            }
        ),
        encoding="utf-8",
    )


def test_cointegrated_pair_catalog_and_detail(monkeypatch, tmp_path):
    coint_csv = tmp_path / "2_cointegrated_pairs.csv"
    price_json = tmp_path / "1_price_list.json"
    status_json = tmp_path / "2_cointegrated_pairs_status.json"
    pd.DataFrame(
        [
            {
                "sym_1": "AAA-USDT-SWAP",
                "sym_2": "BBB-USDT-SWAP",
                "p_value": 0.001,
                "adf_stat": -4.5,
                "hedge_ratio": 0.8,
                "zero_crossing": 7,
                "pair_liquidity_min": 1234.5,
                "pair_order_capacity_usdt": 6789.0,
            }
        ]
    ).to_csv(coint_csv, index=False)
    _write_price_json(price_json)
    status_json.write_text(
        json.dumps({"latest_attempt_rows": 0, "canonical_rows": 1, "preserved_existing": True}),
        encoding="utf-8",
    )

    monkeypatch.setattr(cp, "COINT_CSV", coint_csv)
    monkeypatch.setattr(cp, "PRICE_JSON", price_json)
    monkeypatch.setattr(cp, "STATUS_JSON", status_json)

    catalog = cp.list_cointegrated_pairs()
    detail = cp.get_cointegrated_pair_detail("AAA-USDT-SWAP", "BBB-USDT-SWAP", limit=50)

    assert catalog["pair_count"] == 1
    assert catalog["status"]["preserved_existing"] is True
    assert catalog["pairs"][0]["pair"] == "AAA-USDT-SWAP/BBB-USDT-SWAP"
    assert detail["pair"]["zero_crossing"] == 7
    assert len(detail["points"]) == 4
    assert detail["stats"]["zscore_current"] is not None


def test_pair_supply_status_marks_zombie_or_reaped_pid_stopped(monkeypatch, tmp_path):
    state_path = tmp_path / "pair_supply_control.json"
    log_path = tmp_path / "pair_supply_scheduler.log"
    status_json = tmp_path / "2_cointegrated_pairs_status.json"
    state_path.write_text(
        json.dumps(
            {
                "running": True,
                "pid": 12345,
                "started_at": "2026-04-21T00:00:00+00:00",
                "stopped_at": None,
                "detail": "started",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cp, "PAIR_SUPPLY_STATE", state_path)
    monkeypatch.setattr(cp, "PAIR_SUPPLY_LOG", log_path)
    monkeypatch.setattr(cp, "STATUS_JSON", status_json)
    monkeypatch.setattr(cp, "_pid_exists", lambda _pid: False)

    status = cp.get_pair_supply_status()
    persisted = json.loads(state_path.read_text(encoding="utf-8"))

    assert status["running"] is False
    assert status["detail"] == "process_exited"
    assert status["stopped_at"]
    assert persisted["running"] is False
    assert persisted["detail"] == "process_exited"
    assert status["updated_at"] == persisted["updated_at"]


def test_pair_supply_status_trusts_remote_runner_state(monkeypatch, tmp_path):
    state_path = tmp_path / "pair_supply_control.json"
    log_path = tmp_path / "pair_supply_scheduler.log"
    status_json = tmp_path / "2_cointegrated_pairs_status.json"
    state_path.write_text(
        json.dumps(
            {
                "running": True,
                "pid": 12345,
                "started_at": "2026-04-21T00:00:00+00:00",
                "stopped_at": None,
                "detail": "started",
                "process_mode": "runner",
                "process_owner": "pair-supply-runner",
                "runner_heartbeat_at": cp._utc_iso_now(),
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("STATBOT_PROCESS_OWNER", "api")
    monkeypatch.setattr(cp, "PAIR_SUPPLY_STATE", state_path)
    monkeypatch.setattr(cp, "PAIR_SUPPLY_LOG", log_path)
    monkeypatch.setattr(cp, "STATUS_JSON", status_json)
    monkeypatch.setattr(cp, "_pid_exists", lambda _pid: False)

    status = cp.get_pair_supply_status()
    persisted = json.loads(state_path.read_text(encoding="utf-8"))

    assert status["running"] is True
    assert status["detail"] == "started"
    assert persisted["running"] is True
    assert "updated_at" not in persisted


def test_pair_supply_status_rejects_reused_non_daemon_pid(monkeypatch, tmp_path):
    state_path = tmp_path / "pair_supply_control.json"
    log_path = tmp_path / "pair_supply_scheduler.log"
    status_json = tmp_path / "2_cointegrated_pairs_status.json"
    state_path.write_text(
        json.dumps({"running": True, "pid": 12345, "detail": "started"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(cp, "PAIR_SUPPLY_STATE", state_path)
    monkeypatch.setattr(cp, "PAIR_SUPPLY_LOG", log_path)
    monkeypatch.setattr(cp, "STATUS_JSON", status_json)
    monkeypatch.setattr(cp.os, "name", "posix", raising=False)
    monkeypatch.setattr(cp, "_pid_exists", lambda _pid: True)
    monkeypatch.setattr(cp, "_read_process_cmdline", lambda _pid: ["python", "-m", "uvicorn", "app.main:app"])

    status = cp.get_pair_supply_status()

    assert status["running"] is False
    assert status["detail"] == "process_exited"


def test_pid_exists_treats_reaped_child_as_stopped(monkeypatch):
    monkeypatch.setattr(cp.os, "name", "posix", raising=False)
    monkeypatch.setattr(cp.os, "waitpid", lambda pid, _flags: (pid, 0))

    killed = []

    def fake_kill(pid, signal_number):
        killed.append((pid, signal_number))

    monkeypatch.setattr(cp.os, "kill", fake_kill)

    assert cp._pid_exists(12345) is False
    assert killed == []


def test_pair_supply_runner_mode_records_start_request(monkeypatch, tmp_path):
    state_path = tmp_path / "pair_supply_control.json"
    log_path = tmp_path / "pair_supply_scheduler.log"
    status_json = tmp_path / "2_cointegrated_pairs_status.json"

    monkeypatch.setenv("STATBOT_PAIR_SUPPLY_PROCESS_MODE", "runner")
    monkeypatch.setattr(cp, "PAIR_SUPPLY_STATE", state_path)
    monkeypatch.setattr(cp, "PAIR_SUPPLY_LOG", log_path)
    monkeypatch.setattr(cp, "STATUS_JSON", status_json)

    result = cp.start_pair_supply(requested_by="tester@example.com")
    persisted = json.loads(state_path.read_text(encoding="utf-8"))

    assert result["desired_running"] is True
    assert persisted["detail"] == "start_requested"
    assert persisted["process_mode"] == "runner"
    assert persisted["requested_by"] == "tester@example.com"


def test_pair_supply_runner_mode_records_stop_request(monkeypatch, tmp_path):
    state_path = tmp_path / "pair_supply_control.json"
    log_path = tmp_path / "pair_supply_scheduler.log"
    status_json = tmp_path / "2_cointegrated_pairs_status.json"
    state_path.write_text(
        json.dumps({"running": True, "pid": 12345, "detail": "started"}),
        encoding="utf-8",
    )

    monkeypatch.setenv("STATBOT_PAIR_SUPPLY_PROCESS_MODE", "runner")
    monkeypatch.setattr(cp, "PAIR_SUPPLY_STATE", state_path)
    monkeypatch.setattr(cp, "PAIR_SUPPLY_LOG", log_path)
    monkeypatch.setattr(cp, "STATUS_JSON", status_json)
    monkeypatch.setattr(cp, "_is_managed_pair_supply_process", lambda _pid: True)

    result = cp.stop_pair_supply(requested_by="tester@example.com")
    persisted = json.loads(state_path.read_text(encoding="utf-8"))

    assert result["desired_running"] is False
    assert persisted["detail"] == "stop_requested"
    assert persisted["process_mode"] == "runner"
    assert persisted["requested_by"] == "tester@example.com"
