from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_ROOT = ROOT / "Strategy"
if str(STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(STRATEGY_ROOT))

import pair_supply_daemon as daemon


def test_pair_supply_daemon_interval_allows_zero(monkeypatch):
    monkeypatch.setenv("STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS", "0")

    assert daemon._pair_supply_interval_seconds() == 0


def test_pair_supply_daemon_loads_interval_from_execution_env(monkeypatch, tmp_path):
    strategy_file = tmp_path / "Strategy" / "pair_supply_daemon.py"
    env_file = tmp_path / "Execution" / ".env"
    strategy_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS=0\n", encoding="utf-8")

    monkeypatch.setattr(daemon, "__file__", str(strategy_file))
    monkeypatch.delenv("STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS", raising=False)

    daemon._load_execution_env()

    assert daemon._pair_supply_interval_seconds() == 0


def test_pair_supply_daemon_execution_env_interval_overrides_process_default(monkeypatch, tmp_path):
    strategy_file = tmp_path / "Strategy" / "pair_supply_daemon.py"
    env_file = tmp_path / "Execution" / ".env"
    strategy_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS=0\n", encoding="utf-8")

    monkeypatch.setattr(daemon, "__file__", str(strategy_file))
    monkeypatch.setenv("STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS", "900")

    daemon._load_execution_env()

    assert daemon._pair_supply_interval_seconds() == 0
