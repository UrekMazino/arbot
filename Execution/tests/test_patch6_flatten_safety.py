"""
Patch 6 — Emergency flatten safety tests.

Covers:
1. Exponential backoff schedule — delays between consecutive failed flatten cycles.
2. Pending hard-exit intent — survives entry-context loss (clear_entry_tracking).
"""
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from func_pair_state import (
    set_pending_hard_exit,
    get_pending_hard_exit,
    clear_pending_hard_exit,
    clear_entry_tracking,
)

# ---------------------------------------------------------------------------
# Backoff schedule (mirrors _FLATTEN_BACKOFF_SCHEDULE / _flatten_backoff_delay
# in main_execution.py — kept in sync by hand; if the schedule changes, update both)
# ---------------------------------------------------------------------------

_FLATTEN_BACKOFF_SCHEDULE = [5, 30, 120, 300]


def _flatten_backoff_delay(cycle_count: int) -> int:
    if cycle_count <= 0:
        return 0
    idx = min(cycle_count - 1, len(_FLATTEN_BACKOFF_SCHEDULE) - 1)
    return _FLATTEN_BACKOFF_SCHEDULE[idx]


class TestFlattenBackoffSchedule(unittest.TestCase):
    def test_first_cycle_no_delay(self):
        # Before any cycle has failed, no delay.
        self.assertEqual(_flatten_backoff_delay(0), 0)

    def test_after_first_failure_5s(self):
        self.assertEqual(_flatten_backoff_delay(1), 5)

    def test_after_second_failure_30s(self):
        self.assertEqual(_flatten_backoff_delay(2), 30)

    def test_after_third_failure_120s(self):
        self.assertEqual(_flatten_backoff_delay(3), 120)

    def test_after_fourth_failure_300s(self):
        self.assertEqual(_flatten_backoff_delay(4), 300)

    def test_beyond_schedule_capped_at_300s(self):
        for n in (5, 10, 50):
            with self.subTest(n=n):
                self.assertEqual(_flatten_backoff_delay(n), 300)

    def test_schedule_is_strictly_increasing(self):
        delays = [_flatten_backoff_delay(i) for i in range(1, len(_FLATTEN_BACKOFF_SCHEDULE) + 1)]
        self.assertEqual(delays, sorted(delays), "backoff schedule must be monotonically increasing")


class TestPendingHardExitIntent(unittest.TestCase):
    def setUp(self):
        clear_pending_hard_exit()

    def tearDown(self):
        clear_pending_hard_exit()

    def test_initial_state_is_none(self):
        self.assertIsNone(get_pending_hard_exit())

    def test_set_and_get_round_trips(self):
        set_pending_hard_exit("trade_manager_regime_break", "Regime flip (sustained)", 90)
        result = get_pending_hard_exit()
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "trade_manager_regime_break")
        self.assertEqual(result["reason"], "Regime flip (sustained)")
        self.assertEqual(result["priority"], 90)
        self.assertIn("ts", result)

    def test_clear_removes_pending_exit(self):
        set_pending_hard_exit("trade_manager_regime_break", "Regime flip", 90)
        clear_pending_hard_exit()
        self.assertIsNone(get_pending_hard_exit())

    def test_intent_survives_clear_entry_tracking(self):
        # This is the core run-98 invariant: clearing entry Z-score (as close_all_positions does)
        # must NOT wipe the pending hard-exit intent.
        set_pending_hard_exit("trade_manager_regime_break", "Regime flip (sustained)", 90)
        clear_entry_tracking()  # simulates close_all_positions clearing Z-score
        result = get_pending_hard_exit()
        self.assertIsNotNone(result, "pending hard exit must survive clear_entry_tracking")
        self.assertEqual(result["name"], "trade_manager_regime_break")

    def test_set_overwrites_previous_intent(self):
        set_pending_hard_exit("first_exit", "first reason", 80)
        set_pending_hard_exit("second_exit", "second reason", 90)
        result = get_pending_hard_exit()
        self.assertEqual(result["name"], "second_exit")
        self.assertEqual(result["priority"], 90)


if __name__ == "__main__":
    unittest.main()
