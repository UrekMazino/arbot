import os
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from func_trade_management import _evaluate_directional_filter


class TestTrendQualityControls(unittest.TestCase):
    ENV_KEYS = [
        "STATBOT_STRATEGY_TREND_DIRECTIONAL_FILTER_MODE",
        "STATBOT_STRATEGY_TREND_DIRECTIONAL_FILTER_STRENGTH",
    ]

    def setUp(self):
        self.prev_env = {k: os.environ.get(k) for k in self.ENV_KEYS}
        os.environ["STATBOT_STRATEGY_TREND_DIRECTIONAL_FILTER_STRENGTH"] = "1.0"

    def tearDown(self):
        for key, value in self.prev_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_directional_filter_shadow_flags_without_enforcement(self):
        os.environ["STATBOT_STRATEGY_TREND_DIRECTIONAL_FILTER_MODE"] = "shadow"
        allow_new, reason, mode = _evaluate_directional_filter(
            "SELL_SPREAD",
            {},
            [0.1, 0.4, 0.8, 1.2, 1.7],
        )
        self.assertFalse(allow_new)
        self.assertEqual(reason, "trend_continuation_against_reversion")
        self.assertEqual(mode, "shadow")

    def test_directional_filter_active_blocks(self):
        os.environ["STATBOT_STRATEGY_TREND_DIRECTIONAL_FILTER_MODE"] = "active"
        allow_new, reason, mode = _evaluate_directional_filter(
            "BUY_SPREAD",
            {},
            [-0.2, -0.5, -0.9, -1.4, -1.8],
        )
        self.assertFalse(allow_new)
        self.assertEqual(reason, "trend_continuation_against_reversion")
        self.assertEqual(mode, "active")

    def test_directional_filter_off_always_allows(self):
        os.environ["STATBOT_STRATEGY_TREND_DIRECTIONAL_FILTER_MODE"] = "off"
        allow_new, reason, mode = _evaluate_directional_filter(
            "SELL_SPREAD",
            {},
            [0.1, 0.4, 0.8, 1.2, 1.7],
        )
        self.assertTrue(allow_new)
        self.assertEqual(mode, "off")


if __name__ == "__main__":
    unittest.main()
