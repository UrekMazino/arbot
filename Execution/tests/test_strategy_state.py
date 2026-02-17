import os
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import func_strategy_state as strategy_state


class TestStrategyState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.prev_state_dir = strategy_state._STATE_DIR
        self.prev_state_file = strategy_state.STATE_FILE
        self.prev_window = os.environ.get("STATBOT_STRATEGY_SCORE_WINDOW_TRADES")
        strategy_state._STATE_DIR = Path(self.tmp.name)
        strategy_state.STATE_FILE = strategy_state._STATE_DIR / "strategy_state.json"
        os.environ["STATBOT_STRATEGY_SCORE_WINDOW_TRADES"] = "3"

    def tearDown(self):
        strategy_state._STATE_DIR = self.prev_state_dir
        strategy_state.STATE_FILE = self.prev_state_file
        if self.prev_window is None:
            os.environ.pop("STATBOT_STRATEGY_SCORE_WINDOW_TRADES", None)
        else:
            os.environ["STATBOT_STRATEGY_SCORE_WINDOW_TRADES"] = self.prev_window
        self.tmp.cleanup()

    def test_load_legacy_state_adds_strategy_performance(self):
        legacy = {
            "version": 1,
            "mode": "active",
            "active_strategy": "TREND_SPREAD",
        }
        strategy_state._STATE_DIR.mkdir(parents=True, exist_ok=True)
        strategy_state.STATE_FILE.write_text(json.dumps(legacy), encoding="utf-8")

        loaded = strategy_state.load_strategy_state()
        self.assertIn("strategy_performance", loaded)
        perf = loaded["strategy_performance"]
        self.assertEqual(perf.get("window_trades"), 3)
        self.assertIsInstance(perf.get("stats"), dict)

    def test_record_strategy_trade_result_rolling_window(self):
        strategy_state.record_strategy_trade_result(
            "STATARB_MR",
            1.0,
            regime_name="RANGE",
            hold_minutes=10.0,
            exit_reason="normal",
            trade_ts=1000.0,
        )
        strategy_state.record_strategy_trade_result(
            "STATARB_MR",
            -0.5,
            regime_name="RANGE",
            hold_minutes=5.0,
            exit_reason="exit_tier_1_stop_loss",
            trade_ts=1010.0,
        )
        strategy_state.record_strategy_trade_result(
            "STATARB_MR",
            0.3,
            regime_name="TREND",
            hold_minutes=7.5,
            exit_reason="normal",
            trade_ts=1020.0,
        )
        stats = strategy_state.record_strategy_trade_result(
            "STATARB_MR",
            0.2,
            regime_name="RANGE",
            hold_minutes=4.0,
            exit_reason="normal",
            trade_ts=1030.0,
        )

        self.assertEqual(stats.get("trades_total"), 4)
        self.assertEqual(stats.get("wins_total"), 3)
        self.assertEqual(stats.get("losses_total"), 1)
        self.assertEqual(stats.get("rolling_count"), 3)
        self.assertAlmostEqual(float(stats.get("rolling_pnl_usdt")), 0.0, places=6)
        self.assertAlmostEqual(float(stats.get("rolling_win_rate_pct")), 66.67, places=2)
        self.assertEqual(len(stats.get("rolling_trades", [])), 3)


if __name__ == "__main__":
    unittest.main()
