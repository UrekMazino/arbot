import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import func_trade_management as ftm


class TestManageNewTradesHealthSwitch(unittest.TestCase):
    ENV_KEYS = [
        "STATBOT_HEALTH_FAILS_REQUIRED",
        "STATBOT_HEALTH_SWITCH_GRACE_SECONDS",
        "STATBOT_POST_SWITCH_ENTRY_WARMUP_SECONDS",
    ]

    def setUp(self):
        self.prev_env = {key: os.environ.get(key) for key in self.ENV_KEYS}
        os.environ["STATBOT_HEALTH_FAILS_REQUIRED"] = "1"
        os.environ["STATBOT_HEALTH_SWITCH_GRACE_SECONDS"] = "0"
        os.environ["STATBOT_POST_SWITCH_ENTRY_WARMUP_SECONDS"] = "0"

    def tearDown(self):
        for key, value in self.prev_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_coint_zero_health_switch_uses_metrics_health_state(self):
        set_reason_calls = []
        metrics = {
            "coint_flag": 0,
            "coint_health": "watch",
            "p_value": 0.20,
            "adf_stat": -3.2,
            "critical_value": -3.4,
            "zero_crossings": 10,
            "correlation": 0.8,
            "spread_trend": 0.0,
        }

        with (
            patch.object(ftm, "check_pair_health", return_value=(True, 10, "STOP_AND_SWITCH")),
            patch.object(ftm, "record_health_failure", return_value=1),
            patch.object(ftm, "get_last_switch_time", return_value=0.0),
            patch.object(ftm, "set_last_switch_reason", side_effect=set_reason_calls.append),
        ):
            kill_switch, signal_seen, trade_placed = ftm.manage_new_trades(
                0,
                zscore_results=([0.1, 0.2, 0.3], True, metrics),
            )

        self.assertEqual(kill_switch, 3)
        self.assertFalse(signal_seen)
        self.assertFalse(trade_placed)
        self.assertEqual(set_reason_calls, ["health"])

    def test_coint_zero_health_switch_falls_back_to_classifier(self):
        set_reason_calls = []
        metrics = {
            "coint_flag": 0,
            "p_value": 0.9,
            "adf_stat": 0.0,
            "critical_value": -3.4,
            "zero_crossings": 0,
            "correlation": 0.1,
            "spread_trend": 0.0,
        }

        with (
            patch.object(ftm, "check_pair_health", return_value=(True, 10, "STOP_AND_SWITCH")),
            patch.object(ftm, "record_health_failure", return_value=1),
            patch.object(ftm, "get_last_switch_time", return_value=0.0),
            patch.object(ftm, "set_last_switch_reason", side_effect=set_reason_calls.append),
        ):
            kill_switch, signal_seen, trade_placed = ftm.manage_new_trades(
                0,
                zscore_results=([0.1, 0.2, 0.3], True, metrics),
            )

        self.assertEqual(kill_switch, 3)
        self.assertFalse(signal_seen)
        self.assertFalse(trade_placed)
        self.assertEqual(set_reason_calls, ["cointegration_lost"])


if __name__ == "__main__":
    unittest.main()
