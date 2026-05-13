import sys
import time
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from advanced_trade_management import AdvancedTradeManager  # noqa: E402


class TestAdvancedTradeManagementNetProfitGuard(unittest.TestCase):
    def _manager(self, **config):
        base_config = {
            "take_profit_z": 0.35,
            "partial_exit_enabled": True,
            "partial_exit_z_threshold": 1.0,
            "trailing_stop_enabled": False,
        }
        base_config.update(config)
        return AdvancedTradeManager(config=base_config)

    def test_net_profit_guard_blocks_take_profit_exit_below_cost_floor(self):
        manager = self._manager(partial_exit_enabled=False)
        manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)

        result = manager.update(0.20, floating_pnl_usdt=0.05, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "HOLD")
        self.assertEqual(result["blocked_exit_reason"], "take_profit")

    def test_net_profit_guard_allows_take_profit_above_cost_floor(self):
        manager = self._manager(partial_exit_enabled=False)
        manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)

        result = manager.update(0.20, floating_pnl_usdt=0.25, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "EXIT")
        self.assertEqual(result["reason"], "take_profit")

    def test_net_profit_guard_blocks_partial_exit_below_cost_floor(self):
        manager = self._manager()
        manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)

        result = manager.update(0.90, floating_pnl_usdt=0.05, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "HOLD")
        self.assertEqual(result["blocked_exit_reason"], "partial_profit")

    def test_full_take_profit_wins_over_partial_when_both_eligible(self):
        manager = self._manager()
        manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)

        result = manager.update(0.20, floating_pnl_usdt=0.25, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "EXIT")
        self.assertEqual(result["reason"], "take_profit")
        self.assertNotEqual(result["reason"], "partial_profit")

    def test_partial_take_profit_still_works_when_full_take_profit_not_eligible(self):
        manager = self._manager()
        manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)

        result = manager.update(0.90, floating_pnl_usdt=0.25, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "PARTIAL_EXIT")
        self.assertEqual(result["reason"], "partial_profit")

    def test_max_hold_still_outranks_take_profit(self):
        manager = self._manager(max_hold_hours=6, max_hold_warning_hours=4)
        manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - (7 * 3600))

        result = manager.update(0.20, floating_pnl_usdt=0.25, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "EXIT")
        self.assertEqual(result["reason"], "max_hold_time")

    def test_btc_xlm_missed_profit_shape_selects_full_take_profit(self):
        manager = self._manager(take_profit_z=0.35)
        manager.open_position(entry_z=-2.2, position_size=1000, entry_time=time.time() - 300)

        result = manager.update(-0.23, floating_pnl_usdt=0.25, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "EXIT")
        self.assertEqual(result["reason"], "take_profit")
        self.assertNotEqual(result["reason"], "partial_profit")

    def test_crossing_from_partial_zone_into_full_take_profit_zone_selects_full_exit(self):
        manager = self._manager()
        manager.open_position(entry_z=-2.2, position_size=1000, entry_time=time.time() - 300)

        partial_result = manager.update(-0.90, floating_pnl_usdt=0.25, min_profit_usdt=0.20)
        full_result = manager.update(-0.23, floating_pnl_usdt=0.25, min_profit_usdt=0.20)

        self.assertEqual(partial_result["action"], "PARTIAL_EXIT")
        self.assertEqual(partial_result["reason"], "partial_profit")
        self.assertEqual(full_result["action"], "EXIT")
        self.assertEqual(full_result["reason"], "take_profit")
        self.assertNotEqual(full_result["reason"], "partial_profit")


if __name__ == "__main__":
    unittest.main()
