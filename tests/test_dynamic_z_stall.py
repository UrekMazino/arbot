import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

def _install_okx_stub():
    okx_mod = types.ModuleType("okx")
    public_mod = types.ModuleType("okx.PublicData")
    account_mod = types.ModuleType("okx.Account")
    trade_mod = types.ModuleType("okx.Trade")
    market_mod = types.ModuleType("okx.MarketData")

    class _StubAPI:
        def __init__(self, *args, **kwargs):
            pass

        def __getattr__(self, _name):
            def _noop(*_args, **_kwargs):
                return {"code": "0", "data": []}
            return _noop

    public_mod.PublicAPI = _StubAPI
    account_mod.AccountAPI = _StubAPI
    trade_mod.TradeAPI = _StubAPI
    market_mod.MarketAPI = _StubAPI

    okx_mod.PublicData = public_mod
    okx_mod.Account = account_mod
    okx_mod.Trade = trade_mod
    okx_mod.MarketData = market_mod

    sys.modules["okx"] = okx_mod
    sys.modules["okx.PublicData"] = public_mod
    sys.modules["okx.Account"] = account_mod
    sys.modules["okx.Trade"] = trade_mod
    sys.modules["okx.MarketData"] = market_mod

os.environ["STATBOT_SKIP_INSTRUMENT_FETCH"] = "1"
os.environ["STATBOT_LOG_PATH"] = os.path.join(tempfile.gettempdir(), "okxstatbot-test-dynamic-z.log")
_install_okx_stub()

TEST_DIR = os.path.dirname(__file__)
EXEC_DIR = os.path.abspath(os.path.join(TEST_DIR, "..", "Execution"))
if EXEC_DIR not in sys.path:
    sys.path.append(EXEC_DIR)

import func_trade_management as ftm


def _build_z_history(start_ts, end_ts, points, z_start, z_end):
    if points < 2:
        return [{"ts": start_ts, "z": z_start}]
    step = (end_ts - start_ts) / (points - 1)
    z_step = (z_end - z_start) / (points - 1)
    history = []
    for idx in range(points):
        history.append({
            "ts": start_ts + step * idx,
            "z": z_start + z_step * idx,
        })
    return history


class TestDynamicZStall(unittest.TestCase):
    def _run_monitor_exit(self, now_ts, entry_z, entry_time, current_z, z_history):
        ftm._close_trade_manager()
        zscore_results = ([current_z], False, {"coint_flag": 1})
        with patch("func_pair_state.get_entry_z_score", return_value=entry_z), \
            patch("func_pair_state.get_entry_time", return_value=entry_time), \
            patch("func_pair_state.get_last_health_score", return_value=100), \
            patch("func_pair_state.get_z_history", return_value=z_history), \
            patch("func_pair_state.add_to_z_history", return_value=None), \
            patch("func_position_calls.get_account_state", return_value={"positions": []}), \
            patch("func_trade_management.time.time", return_value=now_ts):
            return ftm.monitor_exit(1, False, zscore_results)

    def test_stall_triggers_after_window(self):
        now_ts = 1_700_000_000
        entry_z = -2.3
        current_z = -2.2
        entry_time = now_ts - 1900
        z_history = _build_z_history(
            start_ts=now_ts - 2000,
            end_ts=now_ts,
            points=20,
            z_start=-2.25,
            z_end=current_z,
        )

        result = self._run_monitor_exit(now_ts, entry_z, entry_time, current_z, z_history)
        self.assertEqual(result, 2)

    def test_stall_grace_period_blocks_exit(self):
        now_ts = 1_700_000_000
        entry_z = -2.3
        current_z = -2.2
        entry_time = now_ts - 1200
        z_history = _build_z_history(
            start_ts=now_ts - 1800,
            end_ts=now_ts,
            points=20,
            z_start=-2.25,
            z_end=current_z,
        )

        result = self._run_monitor_exit(now_ts, entry_z, entry_time, current_z, z_history)
        self.assertEqual(result, 1)

    def test_small_orphan_leg_auto_closes_without_waiting_for_mean_reversion(self):
        close_calls = []

        def _close_stub(kill_switch, tickers=None, **_kwargs):
            close_calls.append({"kill_switch": kill_switch, "tickers": tickers})
            return {"ok": True, "kill_switch": 0}

        account_state = {
            "ok": True,
            "errors": [],
            "orders": [],
            "positions": [
                {
                    "instId": "SHIB-USDT-SWAP",
                    "posSide": "long",
                    "pos": "5.5",
                    "notionalUsd": "35.08",
                    "upl": "-0.055",
                }
            ],
        }
        zscore_results = ([1.33], False, {"coint_flag": 1})

        with patch.dict(
            os.environ,
            {
                "STATBOT_ORPHAN_LEG_AUTO_CLOSE": "1",
                "STATBOT_ORPHAN_LEG_SMALL_NOTIONAL_USDT": "100",
                "STATBOT_ORPHAN_LEG_MAX_LOSS_USDT": "2",
                "STATBOT_ORPHAN_LEG_MAX_LOSS_PCT": "1",
                "STATBOT_ORPHAN_LEG_MAX_AGE_SECONDS": "300",
            },
            clear=False,
        ), patch.object(ftm, "ticker_1", "1INCH-USDT-SWAP"), \
            patch.object(ftm, "ticker_2", "SHIB-USDT-SWAP"), \
            patch("func_pair_state.add_to_z_history", return_value=None), \
            patch("func_pair_state.get_entry_equity", return_value=None), \
            patch("func_pair_state.get_entry_notional", return_value=None), \
            patch("func_pair_state.get_entry_strategy", return_value=None), \
            patch("func_pair_state.get_entry_time", return_value=None), \
            patch("func_pair_state.get_entry_z_score", return_value=None), \
            patch("func_pair_state.clear_coint_lost_since_ts", return_value=None), \
            patch("func_pair_state.clear_coint_lost_confirm_count", return_value=None), \
            patch("func_position_calls.get_account_state", return_value=account_state), \
            patch("func_trade_management.close_all_positions_and_confirm", side_effect=_close_stub), \
            patch("func_trade_management.set_last_switch_reason") as set_reason, \
            patch("func_trade_management.set_last_health_score"), \
            patch("func_trade_management.emit_event"):
            result = ftm.monitor_exit(1, False, zscore_results)

        self.assertEqual(result, 0)
        self.assertEqual(close_calls, [{"kill_switch": 1, "tickers": ["SHIB-USDT-SWAP"]}])
        set_reason.assert_called_once_with("orphan_leg")

    def test_large_orphan_leg_does_not_use_pair_mean_reversion_exit(self):
        account_state = {
            "ok": True,
            "errors": [],
            "orders": [],
            "positions": [
                {
                    "instId": "SHIB-USDT-SWAP",
                    "posSide": "long",
                    "pos": "150",
                    "notionalUsd": "1000",
                    "upl": "0",
                }
            ],
        }
        zscore_results = ([0.10], False, {"coint_flag": 1})

        with patch.dict(
            os.environ,
            {
                "STATBOT_ORPHAN_LEG_AUTO_CLOSE": "1",
                "STATBOT_ORPHAN_LEG_SMALL_NOTIONAL_USDT": "100",
                "STATBOT_ORPHAN_LEG_MAX_LOSS_USDT": "2",
                "STATBOT_ORPHAN_LEG_MAX_LOSS_PCT": "1",
                "STATBOT_ORPHAN_LEG_MAX_AGE_SECONDS": "300",
            },
            clear=False,
        ), patch.object(ftm, "ticker_1", "1INCH-USDT-SWAP"), \
            patch.object(ftm, "ticker_2", "SHIB-USDT-SWAP"), \
            patch("func_pair_state.add_to_z_history", return_value=None), \
            patch("func_pair_state.get_entry_equity", return_value=None), \
            patch("func_pair_state.get_entry_notional", return_value=None), \
            patch("func_pair_state.get_entry_strategy", return_value=None), \
            patch("func_pair_state.get_entry_time", return_value=None), \
            patch("func_pair_state.get_entry_z_score", return_value=None), \
            patch("func_pair_state.clear_coint_lost_since_ts", return_value=None), \
            patch("func_pair_state.clear_coint_lost_confirm_count", return_value=None), \
            patch("func_position_calls.get_account_state", return_value=account_state), \
            patch("func_trade_management.close_all_positions_and_confirm") as close_mock, \
            patch("func_trade_management.emit_event"):
            result = ftm.monitor_exit(1, False, zscore_results)

        self.assertEqual(result, 1)
        close_mock.assert_not_called()

    def test_orphan_leg_auto_closes_even_without_valid_zscore(self):
        close_calls = []

        def _close_stub(kill_switch, tickers=None, **_kwargs):
            close_calls.append({"kill_switch": kill_switch, "tickers": tickers})
            return {"ok": True, "kill_switch": 0}

        account_state = {
            "ok": True,
            "errors": [],
            "orders": [],
            "positions": [
                {
                    "instId": "SHIB-USDT-SWAP",
                    "posSide": "long",
                    "pos": "5.5",
                    "notionalUsd": "35.08",
                    "upl": "-0.055",
                }
            ],
        }
        zscore_results = ([float("nan")], False, {"coint_flag": 0})

        with patch.dict(
            os.environ,
            {
                "STATBOT_ORPHAN_LEG_AUTO_CLOSE": "1",
                "STATBOT_ORPHAN_LEG_SMALL_NOTIONAL_USDT": "100",
                "STATBOT_ORPHAN_LEG_MAX_LOSS_USDT": "2",
                "STATBOT_ORPHAN_LEG_MAX_LOSS_PCT": "1",
                "STATBOT_ORPHAN_LEG_MAX_AGE_SECONDS": "300",
            },
            clear=False,
        ), patch.object(ftm, "ticker_1", "1INCH-USDT-SWAP"), \
            patch.object(ftm, "ticker_2", "SHIB-USDT-SWAP"), \
            patch("func_position_calls.get_account_state", return_value=account_state), \
            patch("func_trade_management.close_all_positions_and_confirm", side_effect=_close_stub), \
            patch("func_trade_management.set_last_switch_reason") as set_reason, \
            patch("func_trade_management.set_last_health_score"), \
            patch("func_trade_management.emit_event"):
            result = ftm.monitor_exit(1, False, zscore_results)

        self.assertEqual(result, 0)
        self.assertEqual(close_calls, [{"kill_switch": 1, "tickers": ["SHIB-USDT-SWAP"]}])
        set_reason.assert_called_once_with("orphan_leg")

    def test_entry_setup_failure_closes_already_placed_leg(self):
        result_long = {
            "ok": False,
            "entry_id": "3543602138750865408",
            "entry": {
                "code": "0",
                "data": [{"ordId": "3543602138750865408", "sCode": "0"}],
            },
            "stop": {"code": "51000", "msg": "Parameter slTriggerPx error"},
        }

        with patch(
            "func_trade_management.close_all_positions_and_confirm",
            return_value={"ok": True, "kill_switch": 0},
        ) as close_mock, patch("func_trade_management.set_last_switch_reason") as set_reason, \
            patch("func_trade_management.set_last_health_score"), \
            patch("func_trade_management.emit_event"):
            handled, kill_switch = ftm._close_placed_entry_after_setup_failure(
                "Long",
                "SHIB-USDT-SWAP",
                result_long,
                "long_entry_setup_failed",
                0,
            )

        self.assertTrue(handled)
        self.assertEqual(kill_switch, 0)
        close_mock.assert_called_once_with(0, tickers=["SHIB-USDT-SWAP"])
        set_reason.assert_called_once_with("entry_setup_failed")

    def test_entry_setup_failure_does_not_close_when_entry_was_rejected(self):
        rejected_entry = {
            "ok": False,
            "entry": {
                "code": "1",
                "data": [{"sCode": "51155", "sMsg": "instrument restricted"}],
            },
        }

        with patch("func_trade_management.close_all_positions_and_confirm") as close_mock:
            handled, kill_switch = ftm._close_placed_entry_after_setup_failure(
                "Long",
                "SHIB-USDT-SWAP",
                rejected_entry,
                "long_entry_failed",
                0,
            )

        self.assertFalse(handled)
        self.assertEqual(kill_switch, 0)
        close_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
