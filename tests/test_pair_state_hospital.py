from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Execution import func_pair_state as fps


def test_drain_ready_hospital_pairs_removes_expired_entries_and_returns_valid_ready_pairs(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)
    state_file = state_dir / "pair_strategy_state.json"
    now = 1_800_000_000.0

    state_file.write_text(
        json.dumps(
            {
                "hospital": {
                    "AAA-USDT-SWAP/BBB-USDT-SWAP": {
                        "ts": now - 7200,
                        "cooldown": 3600,
                        "reason": "cointegration_lost",
                    },
                    "CCC-USDT-SWAP/DDD-USDT-SWAP": {
                        "ts": now - 7200,
                        "cooldown": 3600,
                        "reason": "idle_timeout",
                    },
                    "EEE-USDT-SWAP/FFF-USDT-SWAP": {
                        "ts": now - 1200,
                        "cooldown": 3600,
                        "reason": "cointegration_lost",
                    },
                    "BROKEN-USDT-SWAP/GARBAGE-USDT-SWAP": "bad-entry",
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(fps, "_STATE_DIR", state_dir)
    monkeypatch.setattr(fps, "STATE_FILE", state_file)
    monkeypatch.setattr(fps.time, "time", lambda: now)

    ready_pairs, removed = fps.drain_ready_hospital_pairs(
        {"AAA-USDT-SWAP/BBB-USDT-SWAP"}
    )

    assert ready_pairs == [("AAA-USDT-SWAP/BBB-USDT-SWAP", now - 7200)]
    assert removed == 3

    saved_state = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved_state["hospital"] == {
        "EEE-USDT-SWAP/FFF-USDT-SWAP": {
            "ts": now - 1200,
            "cooldown": 3600,
            "reason": "cointegration_lost",
        }
    }


def test_pair_blacklist_uses_pair_specific_consecutive_losses(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)
    state_file = state_dir / "pair_strategy_state.json"

    monkeypatch.setattr(fps, "_STATE_DIR", state_dir)
    monkeypatch.setattr(fps, "STATE_FILE", state_file)
    monkeypatch.setattr(fps, "BLACKLIST_ENABLED", True)
    monkeypatch.setattr(fps, "BLACKLIST_MIN_TRADES", 10)
    monkeypatch.setattr(fps, "BLACKLIST_MAX_LOSS_RATE", 0.75)
    monkeypatch.setattr(fps, "BLACKLIST_REQUIRE_LOSS_DOMINANCE", True)
    monkeypatch.setattr(fps, "BLACKLIST_MAX_CONSECUTIVE_LOSSES", 2)

    fps.record_pair_trade_result("AAA-USDT-SWAP", "BBB-USDT-SWAP", -1.0)
    fps.record_trade_result(False)
    fps.record_trade_result(False)

    first_stats = fps.get_pair_history_stats("AAA-USDT-SWAP", "BBB-USDT-SWAP")
    assert first_stats["consecutive_losses"] == 1
    assert fps.should_blacklist_pair("AAA-USDT-SWAP", "BBB-USDT-SWAP") is False

    fps.record_pair_trade_result("CCC-USDT-SWAP", "DDD-USDT-SWAP", -1.0)
    fps.record_pair_trade_result("CCC-USDT-SWAP", "DDD-USDT-SWAP", -1.0)

    second_stats = fps.get_pair_history_stats("CCC-USDT-SWAP", "DDD-USDT-SWAP")
    assert second_stats["consecutive_losses"] == 2
    assert fps.should_blacklist_pair("CCC-USDT-SWAP", "DDD-USDT-SWAP") is True

    fps.record_pair_trade_result("CCC-USDT-SWAP", "DDD-USDT-SWAP", 0.5)
    reset_stats = fps.get_pair_history_stats("CCC-USDT-SWAP", "DDD-USDT-SWAP")
    assert reset_stats["consecutive_losses"] == 0


def test_pair_history_tracks_breakevens_without_extending_loss_streak(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)
    state_file = state_dir / "pair_strategy_state.json"

    monkeypatch.setattr(fps, "_STATE_DIR", state_dir)
    monkeypatch.setattr(fps, "STATE_FILE", state_file)
    monkeypatch.setattr(fps, "PAIR_HISTORY_BREAKEVEN_EPSILON_USDT", 0.01)

    fps.record_pair_trade_result("BBB-USDT-SWAP", "AAA-USDT-SWAP", -1.0)
    fps.record_pair_trade_result("BBB-USDT-SWAP", "AAA-USDT-SWAP", -0.005)

    stats = fps.get_pair_history_stats("AAA-USDT-SWAP", "BBB-USDT-SWAP")
    assert stats["trades"] == 2
    assert stats["losses"] == 1
    assert stats["breakevens"] == 1
    assert stats["consecutive_losses"] == 0


def test_add_to_graveyard_stores_normalized_pair_key(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)
    state_file = state_dir / "pair_strategy_state.json"

    monkeypatch.setattr(fps, "_STATE_DIR", state_dir)
    monkeypatch.setattr(fps, "STATE_FILE", state_file)

    fps.add_to_graveyard("BBB-USDT-SWAP", "AAA-USDT-SWAP", reason="bad_history")

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert "AAA-USDT-SWAP/BBB-USDT-SWAP" in state["graveyard"]
    assert "BBB-USDT-SWAP/AAA-USDT-SWAP" not in state["graveyard"]


def test_startup_invalid_pair_preserves_existing_graveyard_reason(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)
    state_file = state_dir / "pair_strategy_state.json"

    monkeypatch.setattr(fps, "_STATE_DIR", state_dir)
    monkeypatch.setattr(fps, "STATE_FILE", state_file)
    monkeypatch.setattr(fps.time, "time", lambda: 1000.0)

    assert fps.add_to_graveyard("AAA-USDT-SWAP", "BBB-USDT-SWAP", reason="bad_history") is True

    monkeypatch.setattr(fps.time, "time", lambda: 2000.0)
    assert fps.add_to_graveyard("BBB-USDT-SWAP", "AAA-USDT-SWAP", reason="startup_invalid_pair") is False

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["graveyard"]["AAA-USDT-SWAP/BBB-USDT-SWAP"] == {
        "ts": 1000.0,
        "reason": "bad_history",
        "ttl_days": 7,
    }
