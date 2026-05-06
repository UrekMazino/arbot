from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_ROOT = ROOT / "Strategy"
if str(STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(STRATEGY_ROOT))

import pair_supply_daemon as daemon


def test_pair_supply_daemon_interval_enforces_minimum(monkeypatch):
    monkeypatch.setenv("STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS", "0")

    assert daemon._pair_supply_interval_seconds() == 5


def test_pair_supply_daemon_fast_interval_prefers_new_env(monkeypatch):
    monkeypatch.setenv("STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS", "30")
    monkeypatch.setenv("STATBOT_PAIR_SUPPLY_FAST_INTERVAL_SECONDS", "12")

    assert daemon._pair_supply_fast_interval_seconds() == 12


def test_pair_supply_daemon_loads_interval_from_execution_env(monkeypatch, tmp_path):
    strategy_file = tmp_path / "Strategy" / "pair_supply_daemon.py"
    env_file = tmp_path / "Execution" / ".env"
    strategy_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS=0\n", encoding="utf-8")

    monkeypatch.setattr(daemon, "__file__", str(strategy_file))
    monkeypatch.delenv("STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS", raising=False)

    daemon._load_execution_env()

    assert daemon._pair_supply_interval_seconds() == 5


def test_pair_supply_daemon_execution_env_interval_overrides_process_default(monkeypatch, tmp_path):
    strategy_file = tmp_path / "Strategy" / "pair_supply_daemon.py"
    env_file = tmp_path / "Execution" / ".env"
    strategy_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS=0\n", encoding="utf-8")

    monkeypatch.setattr(daemon, "__file__", str(strategy_file))
    monkeypatch.setenv("STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS", "900")

    daemon._load_execution_env()

    assert daemon._pair_supply_interval_seconds() == 5


def test_pair_supply_daemon_rotates_scheduler_log(monkeypatch, tmp_path):
    log_path = tmp_path / "pair_supply_scheduler.log"
    log_path.write_text("x" * (1024 * 1024 + 1), encoding="utf-8")

    monkeypatch.setenv("STATBOT_PAIR_SUPPLY_LOG_PATH", str(log_path))
    monkeypatch.setenv("STATBOT_LOG_MAX_MB", "1")
    monkeypatch.setenv("STATBOT_LOG_BACKUPS", "1")

    daemon._write_log_line("new line")

    assert log_path.read_text(encoding="utf-8") == "new line\n"
    assert (tmp_path / "pair_supply_scheduler.log.1").exists()


def test_pair_supply_scheduler_uses_health_refresh_for_fresh_existing_supply(tmp_path):
    csv_path = tmp_path / "2_cointegrated_pairs.csv"
    price_path = tmp_path / "1_price_list.json"
    csv_path.write_text(
        "sym_1,sym_2\n"
        "AAA-USDT-SWAP,BBB-USDT-SWAP\n"
        "CCC-USDT-SWAP,DDD-USDT-SWAP\n"
        "EEE-USDT-SWAP,FFF-USDT-SWAP\n",
        encoding="utf-8",
    )
    price_path.write_text("{}", encoding="utf-8")
    now = datetime.now(timezone.utc)

    should_run, reason = daemon._should_run_full_discovery(
        status={
            "canonical_rows": 3,
            "curator_active_pair_count": 3,
            "curator_status_counts": {"healthy": 3},
            "pair_universe_generation": now.isoformat(),
        },
        state={},
        csv_path=csv_path,
        price_path=price_path,
        first_run=True,
        run_immediately=True,
        full_interval_seconds=900,
        min_active_pairs=3,
        now=now + timedelta(seconds=30),
    )

    assert should_run is False
    assert reason == "health_refresh"


def test_pair_supply_scheduler_runs_full_discovery_when_due(tmp_path):
    csv_path = tmp_path / "2_cointegrated_pairs.csv"
    price_path = tmp_path / "1_price_list.json"
    csv_path.write_text(
        "sym_1,sym_2\n"
        "AAA-USDT-SWAP,BBB-USDT-SWAP\n"
        "CCC-USDT-SWAP,DDD-USDT-SWAP\n"
        "EEE-USDT-SWAP,FFF-USDT-SWAP\n",
        encoding="utf-8",
    )
    price_path.write_text("{}", encoding="utf-8")
    last_full = datetime.now(timezone.utc)

    should_run, reason = daemon._should_run_full_discovery(
        status={
            "canonical_rows": 3,
            "curator_active_pair_count": 3,
            "curator_status_counts": {"healthy": 3},
            "pair_universe_generation": last_full.isoformat(),
        },
        state={},
        csv_path=csv_path,
        price_path=price_path,
        first_run=False,
        run_immediately=True,
        full_interval_seconds=900,
        min_active_pairs=3,
        now=last_full + timedelta(seconds=901),
    )

    assert should_run is True
    assert reason == "scheduled"


def test_pair_supply_scheduler_runs_full_discovery_without_healthy_curator_pairs(tmp_path):
    csv_path = tmp_path / "2_cointegrated_pairs.csv"
    price_path = tmp_path / "1_price_list.json"
    csv_path.write_text(
        "sym_1,sym_2\n"
        "AAA-USDT-SWAP,BBB-USDT-SWAP\n"
        "CCC-USDT-SWAP,DDD-USDT-SWAP\n"
        "EEE-USDT-SWAP,FFF-USDT-SWAP\n",
        encoding="utf-8",
    )
    price_path.write_text("{}", encoding="utf-8")
    now = datetime.now(timezone.utc)

    should_run, reason = daemon._should_run_full_discovery(
        status={
            "canonical_rows": 3,
            "curator_active_pair_count": 3,
            "curator_status_counts": {"watch": 3},
            "pair_universe_generation": now.isoformat(),
        },
        state={},
        csv_path=csv_path,
        price_path=price_path,
        first_run=False,
        run_immediately=True,
        full_interval_seconds=900,
        min_active_pairs=3,
        now=now + timedelta(seconds=30),
    )

    assert should_run is True
    assert reason == "no_healthy_curator_pairs"
