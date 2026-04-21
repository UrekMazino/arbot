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


if __name__ == "__main__":
    unittest.main()
