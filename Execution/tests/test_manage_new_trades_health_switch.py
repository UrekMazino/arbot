import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
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
        "STATBOT_DISABLE_OPEN_ORDERS",
        "STATBOT_TRADE_QUALITY_GATE",
        "STATBOT_TRADE_QUALITY_GATE_MODE",
        "STATBOT_TQG_MIN_SCORE",
    ]

    def setUp(self):
        self.prev_env = {key: os.environ.get(key) for key in self.ENV_KEYS}
        os.environ["STATBOT_HEALTH_FAILS_REQUIRED"] = "1"
        os.environ["STATBOT_HEALTH_SWITCH_GRACE_SECONDS"] = "0"
        os.environ["STATBOT_POST_SWITCH_ENTRY_WARMUP_SECONDS"] = "0"
        os.environ.pop("STATBOT_DISABLE_OPEN_ORDERS", None)
        os.environ["STATBOT_TRADE_QUALITY_GATE"] = "1"
        os.environ["STATBOT_TRADE_QUALITY_GATE_MODE"] = "active"
        os.environ["STATBOT_TQG_MIN_SCORE"] = "72"
        self.env_file_patch = patch.object(ftm, "_env_file_flag", return_value=None)
        self.env_file_patch.start()

    def tearDown(self):
        self.env_file_patch.stop()
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

    def test_disable_open_orders_blocks_entry_execution_after_signal(self):
        os.environ["STATBOT_DISABLE_OPEN_ORDERS"] = "1"
        metrics = {
            "coint_flag": 1,
            "p_value": 0.01,
            "adf_stat": -4.0,
            "critical_value": -3.4,
            "zero_crossings": 20,
            "correlation": 0.9,
            "spread_trend": 0.0,
        }

        with (
            patch.object(ftm, "_resolve_entry_signal", return_value=("BUY_SPREAD", "test signal", "STATARB_MR")),
            patch.object(ftm, "get_last_switch_time", return_value=0.0),
            patch.object(ftm, "initialise_order_execution", side_effect=AssertionError("entry order placed")),
            patch.object(ftm, "get_ticker_trade_liquidity", side_effect=AssertionError("liquidity fetched")),
        ):
            kill_switch, signal_seen, trade_placed = ftm.manage_new_trades(
                0,
                zscore_results=([0.1, -2.2], False, metrics),
            )

        self.assertEqual(kill_switch, 0)
        self.assertTrue(signal_seen)
        self.assertFalse(trade_placed)

    def test_trade_quality_gate_blocks_entry_before_preflight(self):
        metrics = {
            "coint_flag": 1,
            "coint_health": "healthy",
            "p_value": 0.20,
            "adf_stat": -4.0,
            "critical_value": -3.4,
            "zero_crossings": 20,
            "correlation": 0.9,
            "returns_correlation": 0.6,
            "spread_trend": 0.0,
            "latest_zscore": -2.2,
        }
        account_stub = SimpleNamespace(
            get_account_balance=lambda: {
                "code": "0",
                "data": [{"details": [{"ccy": "USDT", "availBal": "10000", "availEq": "10000"}]}],
            }
        )

        with (
            patch.object(ftm, "_resolve_entry_signal", return_value=("BUY_SPREAD", "test signal", "STATARB_MR")),
            patch.object(ftm, "get_last_switch_time", return_value=0.0),
            patch.object(ftm, "account_session", account_stub),
            patch.object(ftm, "get_ticker_trade_liquidity", return_value=(10000.0, 100.0)),
            patch.object(
                ftm,
                "get_min_capital_requirements",
                return_value={"ok": True, "min_capital": 1.0, "instrument_info": {}, "orderbook_payload": None},
            ),
            patch.object(ftm, "get_contract_value_quote", return_value=1.0),
            patch.object(ftm, "get_pair_history_stats", return_value={"trades": 0, "win_rate": 0.0}),
            patch.object(ftm, "emit_event", return_value=True),
            patch.object(ftm, "preview_entry_details", side_effect=AssertionError("preflight should not run")),
            patch.object(ftm, "initialise_order_execution", side_effect=AssertionError("entry order placed")),
        ):
            kill_switch, signal_seen, trade_placed = ftm.manage_new_trades(
                0,
                zscore_results=([0.1, -2.0, -2.1, -2.2], False, metrics),
            )

        self.assertEqual(kill_switch, 0)
        self.assertTrue(signal_seen)
        self.assertFalse(trade_placed)


if __name__ == "__main__":
    unittest.main()
