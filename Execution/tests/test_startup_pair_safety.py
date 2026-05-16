"""
Tests for startup active-pair safety: check_startup_pair_block in func_pair_state.

check_startup_pair_block(t1, t2) returns (reason, message) or (None, None).
Tests verify:
  - valid pair is unchanged (None, None)
  - restricted ticker is rejected
  - graveyard pair is rejected
  - hospital pair returns startup_pair_in_hospital
  - hospital state is not mutated by the check
  - graveyard state is not mutated by the check
  - restricted ticker in t2 position is also caught
"""

import json
import shutil
import sys
import time
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import func_pair_state as fps


T1 = "AAA-USDT-SWAP"
T2 = "BBB-USDT-SWAP"
T3 = "CCC-USDT-SWAP"


class TestCheckStartupPairBlock:
    def setup_method(self):
        self.tmp_dir = ROOT_DIR / ".tmp" / "startup_safety" / uuid.uuid4().hex
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.prev_state_file = fps.STATE_FILE
        self.prev_graveyard_file = fps.GRAVEYARD_TICKERS_FILE
        fps.STATE_FILE = self.tmp_dir / "pair_strategy_state.json"
        fps.GRAVEYARD_TICKERS_FILE = self.tmp_dir / "graveyard_tickers.json"
        fps.STATE_FILE.write_text(
            json.dumps({"hospital": {}, "graveyard": {}, "pair_history": {}}),
            encoding="utf-8",
        )
        fps.GRAVEYARD_TICKERS_FILE.write_text(json.dumps({}), encoding="utf-8")

    def teardown_method(self):
        fps.STATE_FILE = self.prev_state_file
        fps.GRAVEYARD_TICKERS_FILE = self.prev_graveyard_file
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # ── Test 1: valid startup pair is unchanged ───────────────────────────────

    def test_valid_pair_returns_none(self):
        reason, message = fps.check_startup_pair_block(T1, T2)
        assert reason is None
        assert message is None

    # ── Test 2: restricted ticker in t1 is rejected ───────────────────────────

    def test_restricted_ticker_t1_blocked(self):
        fps.add_restricted_ticker(T1, code="", msg="test restriction")
        reason, message = fps.check_startup_pair_block(T1, T2)
        assert reason == "restricted_ticker"
        assert T1 in message

    # ── Test 3: restricted ticker in t2 is rejected ───────────────────────────

    def test_restricted_ticker_t2_blocked(self):
        fps.add_restricted_ticker(T2, code="", msg="test restriction")
        reason, message = fps.check_startup_pair_block(T1, T2)
        assert reason == "restricted_ticker"
        assert T2 in message

    # ── Test 4: graveyard pair is blocked ─────────────────────────────────────

    def test_graveyard_pair_blocked(self):
        fps.add_to_graveyard(T1, T2, reason="manual")
        reason, message = fps.check_startup_pair_block(T1, T2)
        assert reason == "startup_invalid_pair"
        assert T1 in message or T2 in message

    # ── Test 5: hospital pair blocked with cooldown remaining ─────────────────

    def test_hospital_pair_blocked(self):
        fps.add_to_hospital(T1, T2, reason="test_hospital", cooldown_seconds=3600)
        reason, message = fps.check_startup_pair_block(T1, T2)
        assert reason == "startup_pair_in_hospital"
        assert "hospital" in message.lower()
        assert T1 in message or T2 in message

    # ── Test 6: hospital pair with expired cooldown is NOT blocked ────────────

    def test_hospital_expired_not_blocked(self):
        state = fps.load_pair_state()
        pair_key = fps.normalize_pair_key(T1, T2)
        # Write a hospital entry with a timestamp far in the past
        state["hospital"][pair_key] = {
            "ts": time.time() - 7200,
            "cooldown": 3600,
            "reason": "expired_test",
            "visits": 1,
        }
        fps.save_pair_state(state)
        reason, message = fps.check_startup_pair_block(T1, T2)
        assert reason is None
        assert message is None

    # ── Test 7: hospital state not mutated by block check ─────────────────────

    def test_hospital_state_not_deleted_by_check(self):
        fps.add_to_hospital(T1, T2, reason="test_hospital", cooldown_seconds=86400)
        state_before = fps.load_pair_state()
        pair_key = fps.normalize_pair_key(T1, T2)
        assert pair_key in state_before["hospital"]

        fps.check_startup_pair_block(T1, T2)

        state_after = fps.load_pair_state()
        assert pair_key in state_after["hospital"], (
            "check_startup_pair_block must not remove hospital entries"
        )

    # ── Test 8: graveyard state not mutated by block check ────────────────────

    def test_graveyard_state_not_deleted_by_check(self):
        fps.add_to_graveyard(T1, T2, reason="manual")
        pair_key = fps.normalize_pair_key(T1, T2)
        state_before = fps.load_pair_state()
        assert pair_key in state_before["graveyard"]

        fps.check_startup_pair_block(T1, T2)

        state_after = fps.load_pair_state()
        assert pair_key in state_after["graveyard"], (
            "check_startup_pair_block must not remove graveyard entries"
        )

    # ── Test 9: hospital checked before graveyard (restriction first) ─────────

    def test_restricted_ticker_takes_priority_over_hospital(self):
        fps.add_restricted_ticker(T1, code="", msg="restricted")
        fps.add_to_hospital(T1, T2, reason="also_hospital", cooldown_seconds=3600)
        reason, _message = fps.check_startup_pair_block(T1, T2)
        assert reason == "restricted_ticker"

    # ── Test 10: different pair unaffected by hospital of other pair ──────────

    def test_unrelated_hospital_pair_does_not_block(self):
        fps.add_to_hospital(T1, T3, reason="unrelated", cooldown_seconds=3600)
        reason, message = fps.check_startup_pair_block(T1, T2)
        assert reason is None

    # ── Test 11: message contains cooldown info for hospital ──────────────────

    def test_hospital_message_includes_cooldown_seconds(self):
        fps.add_to_hospital(T1, T2, reason="test", cooldown_seconds=3600)
        _reason, message = fps.check_startup_pair_block(T1, T2)
        # remaining should be close to 3600 — just verify it's a number in the message
        assert "s remaining" in message
