from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from Platform.api.app.services import cointegrated_pairs as cp


def test_pair_supply_interval_enforces_minimum(monkeypatch):
    monkeypatch.setenv("STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS", "0")

    assert cp._pair_supply_interval_seconds() == 5


def test_pair_supply_interval_reads_execution_env(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS=0\n", encoding="utf-8")

    monkeypatch.setattr(cp, "EXECUTION_ENV_FILE", env_file)
    monkeypatch.delenv("STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS", raising=False)

    assert cp._pair_supply_interval_seconds() == 5


def test_healthiest_pair_from_curator_requires_healthy_or_promote(monkeypatch, tmp_path):
    report_path = tmp_path / "pair_universe_curator.json"
    coint_csv = tmp_path / "2_cointegrated_pairs.csv"
    pd.DataFrame(
        [
            {"sym_1": "AAA-USDT-SWAP", "sym_2": "BBB-USDT-SWAP"},
            {"sym_1": "CCC-USDT-SWAP", "sym_2": "DDD-USDT-SWAP"},
            {"sym_1": "EEE-USDT-SWAP", "sym_2": "FFF-USDT-SWAP"},
        ]
    ).to_csv(coint_csv, index=False)
    report_path.write_text(
        json.dumps(
            {
                "pairs": {
                    "AAA-USDT-SWAP/BBB-USDT-SWAP": {
                        "sym_1": "AAA-USDT-SWAP",
                        "sym_2": "BBB-USDT-SWAP",
                        "pair": "AAA-USDT-SWAP/BBB-USDT-SWAP",
                        "priority_rank": 1,
                        "score": 99,
                        "status": "watch",
                        "recommendation": "hold",
                    },
                    "CCC-USDT-SWAP/DDD-USDT-SWAP": {
                        "sym_1": "CCC-USDT-SWAP",
                        "sym_2": "DDD-USDT-SWAP",
                        "pair": "CCC-USDT-SWAP/DDD-USDT-SWAP",
                        "priority_rank": 2,
                        "score": 10,
                        "status": "watch",
                        "recommendation": "promote",
                    },
                    "EEE-USDT-SWAP/FFF-USDT-SWAP": {
                        "sym_1": "EEE-USDT-SWAP",
                        "sym_2": "FFF-USDT-SWAP",
                        "pair": "EEE-USDT-SWAP/FFF-USDT-SWAP",
                        "priority_rank": 3,
                        "score": 20,
                        "status": "healthy",
                        "recommendation": "hold",
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cp, "PAIR_CURATOR_REPORT", report_path)
    monkeypatch.setattr(cp, "COINT_CSV", coint_csv)

    assert cp.get_healthiest_pair_from_curator()["pair"] == "CCC-USDT-SWAP/DDD-USDT-SWAP"


def test_healthiest_pair_from_curator_returns_none_without_selectable_pair(monkeypatch, tmp_path):
    report_path = tmp_path / "pair_universe_curator.json"
    coint_csv = tmp_path / "2_cointegrated_pairs.csv"
    pd.DataFrame([{"sym_1": "AAA-USDT-SWAP", "sym_2": "BBB-USDT-SWAP"}]).to_csv(coint_csv, index=False)
    report_path.write_text(
        json.dumps(
            {
                "pairs": {
                    "AAA-USDT-SWAP/BBB-USDT-SWAP": {
                        "sym_1": "AAA-USDT-SWAP",
                        "sym_2": "BBB-USDT-SWAP",
                        "priority_rank": 1,
                        "score": 99,
                        "status": "watch",
                        "recommendation": "hold",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cp, "PAIR_CURATOR_REPORT", report_path)
    monkeypatch.setattr(cp, "COINT_CSV", coint_csv)

    assert cp.get_healthiest_pair_from_curator() is None


def test_healthiest_pair_from_curator_ignores_pairs_removed_from_universe(monkeypatch, tmp_path):
    report_path = tmp_path / "pair_universe_curator.json"
    coint_csv = tmp_path / "2_cointegrated_pairs.csv"
    pd.DataFrame([{"sym_1": "CCC-USDT-SWAP", "sym_2": "DDD-USDT-SWAP"}]).to_csv(coint_csv, index=False)
    report_path.write_text(
        json.dumps(
            {
                "pairs": {
                    "AAA-USDT-SWAP/BBB-USDT-SWAP": {
                        "sym_1": "AAA-USDT-SWAP",
                        "sym_2": "BBB-USDT-SWAP",
                        "pair": "AAA-USDT-SWAP/BBB-USDT-SWAP",
                        "priority_rank": 1,
                        "score": 99,
                        "status": "healthy",
                        "recommendation": "promote",
                    },
                    "CCC-USDT-SWAP/DDD-USDT-SWAP": {
                        "sym_1": "CCC-USDT-SWAP",
                        "sym_2": "DDD-USDT-SWAP",
                        "pair": "CCC-USDT-SWAP/DDD-USDT-SWAP",
                        "priority_rank": 2,
                        "score": 90,
                        "status": "healthy",
                        "recommendation": "promote",
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cp, "PAIR_CURATOR_REPORT", report_path)
    monkeypatch.setattr(cp, "COINT_CSV", coint_csv)

    assert cp.get_healthiest_pair_from_curator()["pair"] == "CCC-USDT-SWAP/DDD-USDT-SWAP"


def test_pair_doctor_ui_refresh_seconds_defaults_to_twenty(monkeypatch):
    monkeypatch.delenv("STATBOT_PAIR_DOCTOR_UI_REFRESH_SECONDS", raising=False)
    monkeypatch.setattr(cp, "EXECUTION_ENV_FILE", Path("missing-test.env"))

    assert cp._pair_doctor_ui_refresh_seconds() == 20


def test_pair_doctor_ui_refresh_seconds_reads_execution_env(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("STATBOT_PAIR_DOCTOR_UI_REFRESH_SECONDS=33\n", encoding="utf-8")

    monkeypatch.setattr(cp, "EXECUTION_ENV_FILE", env_file)
    monkeypatch.delenv("STATBOT_PAIR_DOCTOR_UI_REFRESH_SECONDS", raising=False)

    assert cp._pair_doctor_ui_refresh_seconds() == 33


def test_pair_supply_child_env_includes_execution_env(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS=0\n", encoding="utf-8")

    monkeypatch.setattr(cp, "EXECUTION_ENV_FILE", env_file)
    monkeypatch.delenv("STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS", raising=False)

    assert cp._merged_child_env()["STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS"] == "0"


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
    monkeypatch.setattr(cp, "PAIR_STRATEGY_STATE", tmp_path / "pair_strategy_state.json")
    monkeypatch.setattr(cp, "EXECUTION_ENV_FILE", tmp_path / "missing.env")
    monkeypatch.delenv("STATBOT_PAIR_DOCTOR_UI_REFRESH_SECONDS", raising=False)
    monkeypatch.setenv("STATBOT_STRATEGY_Z_SCORE_WINDOW", "3")
    monkeypatch.setenv("STATBOT_COINT_ZERO_CROSS_THRESHOLD_RATIO", "0.1")

    catalog = cp.list_cointegrated_pairs()
    detail = cp.get_cointegrated_pair_detail("AAA-USDT-SWAP", "BBB-USDT-SWAP", limit=50)

    assert catalog["pair_count"] == 1
    assert catalog["pair_doctor_ui_refresh_seconds"] == 20
    assert catalog["status"]["preserved_existing"] is True
    assert catalog["pairs"][0]["pair"] == "AAA-USDT-SWAP/BBB-USDT-SWAP"
    assert detail["pair"]["zero_crossing"] == 7
    assert len(detail["points"]) == 4
    assert detail["points"][0]["zscore"] is None
    assert detail["points"][-1]["zscore"] is not None
    crossing_points = [point for point in detail["points"] if point["crossing_spread"] is not None]
    assert detail["stats"]["zero_crossing_window"] == len(crossing_points)
    assert crossing_points[0]["crossing_label"] == "#1"
    assert detail["stats"]["zscore_window"] == 3
    assert detail["stats"]["zscore_current"] is not None


def test_cointegrated_pair_catalog_filters_hospital_and_graveyard(monkeypatch, tmp_path):
    coint_csv = tmp_path / "2_cointegrated_pairs.csv"
    status_json = tmp_path / "2_cointegrated_pairs_status.json"
    pair_state = tmp_path / "pair_strategy_state.json"
    pd.DataFrame(
        [
            {"sym_1": "AAA-USDT-SWAP", "sym_2": "BBB-USDT-SWAP", "zero_crossing": 9},
            {"sym_1": "CCC-USDT-SWAP", "sym_2": "DDD-USDT-SWAP", "zero_crossing": 8},
            {"sym_1": "EEE-USDT-SWAP", "sym_2": "FFF-USDT-SWAP", "zero_crossing": 7},
        ]
    ).to_csv(coint_csv, index=False)
    status_json.write_text("{}", encoding="utf-8")
    now = cp._unix_now()
    pair_state.write_text(
        json.dumps(
            {
                "hospital": {
                    "AAA-USDT-SWAP/BBB-USDT-SWAP": {
                        "ts": now,
                        "cooldown": 3600,
                        "reason": "test",
                    }
                },
                "graveyard": {
                    "CCC-USDT-SWAP/DDD-USDT-SWAP": {
                        "ts": now,
                        "reason": "manual",
                        "ttl_days": 7,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cp, "COINT_CSV", coint_csv)
    monkeypatch.setattr(cp, "STATUS_JSON", status_json)
    monkeypatch.setattr(cp, "PAIR_STRATEGY_STATE", pair_state)

    catalog = cp.list_cointegrated_pairs()

    assert catalog["excluded_pair_count"] == 2
    assert catalog["pair_count"] == 1
    assert catalog["pairs"][0]["pair"] == "EEE-USDT-SWAP/FFF-USDT-SWAP"


def test_cointegrated_pair_catalog_filters_missing_liquidity_rows(monkeypatch, tmp_path):
    coint_csv = tmp_path / "2_cointegrated_pairs.csv"
    status_json = tmp_path / "2_cointegrated_pairs_status.json"
    pair_state = tmp_path / "pair_strategy_state.json"
    pd.DataFrame(
        [
            {
                "sym_1": "AAA-USDT-SWAP",
                "sym_2": "BBB-USDT-SWAP",
                "zero_crossing": 99,
                "avg_quote_volume_1": 1000,
                "avg_quote_volume_2": None,
                "pair_liquidity_min": None,
            },
            {
                "sym_1": "CCC-USDT-SWAP",
                "sym_2": "DDD-USDT-SWAP",
                "zero_crossing": 8,
                "avg_quote_volume_1": 1000,
                "avg_quote_volume_2": 900,
                "pair_liquidity_min": 900,
            },
        ]
    ).to_csv(coint_csv, index=False)
    status_json.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(cp, "COINT_CSV", coint_csv)
    monkeypatch.setattr(cp, "STATUS_JSON", status_json)
    monkeypatch.setattr(cp, "PAIR_STRATEGY_STATE", pair_state)

    catalog = cp.list_cointegrated_pairs()

    assert catalog["unusable_liquidity_pair_count"] == 1
    assert catalog["pair_count"] == 1
    assert catalog["pairs"][0]["pair"] == "CCC-USDT-SWAP/DDD-USDT-SWAP"


def test_remove_cointegrated_pair_only_removes_pair_from_universe(monkeypatch, tmp_path):
    coint_csv = tmp_path / "2_cointegrated_pairs.csv"
    status_json = tmp_path / "2_cointegrated_pairs_status.json"
    pair_state = tmp_path / "pair_strategy_state.json"
    supply_state = tmp_path / "pair_supply_control.json"
    report_path = tmp_path / "pair_universe_curator.json"
    pd.DataFrame(
        [
            {"sym_1": "AAA-USDT-SWAP", "sym_2": "BBB-USDT-SWAP", "zero_crossing": 9},
            {"sym_1": "CCC-USDT-SWAP", "sym_2": "DDD-USDT-SWAP", "zero_crossing": 8},
        ]
    ).to_csv(coint_csv, index=False)
    status_json.write_text(json.dumps({"canonical_rows": 2}), encoding="utf-8")
    supply_state.write_text(json.dumps({"status": {"canonical_rows": 2}}), encoding="utf-8")
    report_path.write_text(
        json.dumps(
            {
                "pair_count": 2,
                "pairs": {
                    "AAA-USDT-SWAP/BBB-USDT-SWAP": {
                        "pair_key": "AAA-USDT-SWAP/BBB-USDT-SWAP",
                        "status": "healthy",
                    },
                    "CCC-USDT-SWAP/DDD-USDT-SWAP": {
                        "pair_key": "CCC-USDT-SWAP/DDD-USDT-SWAP",
                        "status": "healthy",
                    },
                },
                "top_pairs": [
                    {"pair_key": "AAA-USDT-SWAP/BBB-USDT-SWAP", "status": "healthy"},
                    {"pair_key": "CCC-USDT-SWAP/DDD-USDT-SWAP", "status": "healthy"},
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cp, "COINT_CSV", coint_csv)
    monkeypatch.setattr(cp, "STATUS_JSON", status_json)
    monkeypatch.setattr(cp, "PAIR_STRATEGY_STATE", pair_state)
    monkeypatch.setattr(cp, "PAIR_SUPPLY_STATE", supply_state)
    monkeypatch.setattr(cp, "PAIR_CURATOR_REPORT", report_path)

    result = cp.remove_cointegrated_pair("BBB-USDT-SWAP", "AAA-USDT-SWAP", requested_by="tester@example.com")
    canonical = pd.read_csv(coint_csv)
    status = json.loads(status_json.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert result["removed"] is True
    assert result["removed_rows"] == 1
    assert result["pair_key"] == "AAA-USDT-SWAP/BBB-USDT-SWAP"
    assert result["status"] == "removed"
    assert list(canonical["sym_1"]) == ["CCC-USDT-SWAP"]
    assert not pair_state.exists()
    assert status["canonical_rows"] == 1
    assert "AAA-USDT-SWAP/BBB-USDT-SWAP" not in report["pairs"]
    assert report["pair_count"] == 1


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
