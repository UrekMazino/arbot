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
