import sys
import time
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from advanced_trade_management import AdvancedTradeManager  # noqa: E402


class TestAdvancedTradeManagementNetProfitGuard(unittest.TestCase):
    def test_net_profit_guard_blocks_take_profit_exit_below_cost_floor(self):
        manager = AdvancedTradeManager(
            config={
                "take_profit_z": 0.35,
                "partial_exit_enabled": False,
                "trailing_stop_enabled": False,
            }
        )
        manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)

        result = manager.update(0.20, floating_pnl_usdt=0.05, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "HOLD")
        self.assertEqual(result["blocked_exit_reason"], "take_profit")

    def test_net_profit_guard_allows_take_profit_above_cost_floor(self):
        manager = AdvancedTradeManager(
            config={
                "take_profit_z": 0.35,
                "partial_exit_enabled": False,
                "trailing_stop_enabled": False,
            }
        )
        manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)

        result = manager.update(0.20, floating_pnl_usdt=0.25, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "EXIT")
        self.assertEqual(result["reason"], "take_profit")

    def test_net_profit_guard_blocks_partial_exit_below_cost_floor(self):
        manager = AdvancedTradeManager(
            config={
                "take_profit_z": 0.35,
                "partial_exit_enabled": True,
                "trailing_stop_enabled": False,
                "partial_exit_z_threshold": 1.0,
            }
        )
        manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)

        result = manager.update(0.90, floating_pnl_usdt=0.05, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "HOLD")
        self.assertEqual(result["blocked_exit_reason"], "partial_profit")


if __name__ == "__main__":
    unittest.main()
