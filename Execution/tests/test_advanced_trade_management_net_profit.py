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
        self.assertEqual(result["base_min_profit_usdt"], 0.20)
        self.assertEqual(result["effective_min_profit_usdt"], 0.20)
        self.assertEqual(result["guard_multiplier"], 1.0)
        self.assertEqual(result["current_z"], 0.20)
        self.assertEqual(result["take_profit_z"], 0.35)

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

    def test_full_take_profit_guard_multiplier_changes_only_full_take_profit_floor(self):
        full_manager = self._manager(full_tp_guard_multiplier=0.5, partial_exit_enabled=False)
        full_manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)

        full_result = full_manager.update(0.20, floating_pnl_usdt=0.15, min_profit_usdt=0.20)

        self.assertEqual(full_result["action"], "EXIT")
        self.assertEqual(full_result["reason"], "take_profit")

        partial_manager = self._manager(full_tp_guard_multiplier=0.5)
        partial_manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)

        partial_result = partial_manager.update(0.90, floating_pnl_usdt=0.15, min_profit_usdt=0.20)

        self.assertEqual(partial_result["action"], "HOLD")
        self.assertEqual(partial_result["blocked_exit_reason"], "partial_profit")
        self.assertEqual(partial_result["effective_min_profit_usdt"], 0.20)

    def test_partial_take_profit_guard_multiplier_changes_only_partial_floor(self):
        partial_manager = self._manager(partial_tp_guard_multiplier=0.5)
        partial_manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)

        partial_result = partial_manager.update(0.90, floating_pnl_usdt=0.15, min_profit_usdt=0.20)

        self.assertEqual(partial_result["action"], "PARTIAL_EXIT")
        self.assertEqual(partial_result["reason"], "partial_profit")

        full_manager = self._manager(partial_tp_guard_multiplier=0.5)
        full_manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)

        full_result = full_manager.update(0.20, floating_pnl_usdt=0.15, min_profit_usdt=0.20)

        self.assertEqual(full_result["action"], "HOLD")
        self.assertEqual(full_result["blocked_exit_reason"], "take_profit")
        self.assertEqual(full_result["effective_min_profit_usdt"], 0.20)

    def test_trailing_stop_guard_multiplier_changes_only_trailing_floor(self):
        trailing_manager = self._manager(
            trailing_stop_enabled=True,
            trailing_stop_min_hold_seconds=0,
            trailing_stop_guard_multiplier=0.5,
        )
        trailing_manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)
        trailing_manager.trade_state.best_z = 0.0
        trailing_manager.trade_state.trailing_stop_active = True
        trailing_manager.trade_state.trailing_stop_level = 0.5

        trailing_result = trailing_manager.update(0.60, floating_pnl_usdt=0.15, min_profit_usdt=0.20)

        self.assertEqual(trailing_result["action"], "EXIT")
        self.assertEqual(trailing_result["reason"], "trailing_stop")

        full_manager = self._manager(
            trailing_stop_enabled=False,
            trailing_stop_guard_multiplier=0.5,
            partial_exit_enabled=False,
        )
        full_manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)

        full_result = full_manager.update(0.20, floating_pnl_usdt=0.15, min_profit_usdt=0.20)

        self.assertEqual(full_result["action"], "HOLD")
        self.assertEqual(full_result["blocked_exit_reason"], "take_profit")
        self.assertEqual(full_result["effective_min_profit_usdt"], 0.20)

    def test_guard_blocked_result_includes_effective_threshold_diagnostics(self):
        manager = self._manager(full_tp_guard_multiplier=0.5, partial_exit_enabled=False)
        manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)

        result = manager.update(0.20, floating_pnl_usdt=0.05, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "HOLD")
        self.assertEqual(result["blocked_exit_reason"], "take_profit")
        self.assertEqual(result["floating_pnl_usdt"], 0.05)
        self.assertEqual(result["base_min_profit_usdt"], 0.20)
        self.assertEqual(result["effective_min_profit_usdt"], 0.10)
        self.assertEqual(result["guard_multiplier"], 0.5)
        self.assertEqual(result["current_z"], 0.20)
        self.assertEqual(result["take_profit_z"], 0.35)

    def test_mean_reversion_escape_is_disabled_by_default(self):
        manager = self._manager(partial_exit_enabled=False)
        manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)
        manager.trade_state.best_z = 0.10

        result = manager.update(0.20, floating_pnl_usdt=0.05, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "HOLD")
        self.assertEqual(result["blocked_exit_reason"], "take_profit")

    def test_mean_reversion_escape_exits_when_enabled_and_risk_condition_passes(self):
        manager = self._manager(
            partial_exit_enabled=False,
            mean_reversion_escape_enabled=True,
            mean_reversion_escape_z=0.25,
            mean_reversion_escape_min_pnl_usdt=0.0,
            mean_reversion_escape_requires_risk_rising=True,
        )
        manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)
        manager.trade_state.best_z = 0.10

        result = manager.update(0.20, floating_pnl_usdt=0.05, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "EXIT")
        self.assertEqual(result["reason"], "mean_reversion_escape")

    def test_mean_reversion_escape_requires_configured_conditions(self):
        manager = self._manager(
            partial_exit_enabled=False,
            mean_reversion_escape_enabled=True,
            mean_reversion_escape_z=0.25,
            mean_reversion_escape_min_pnl_usdt=0.10,
            mean_reversion_escape_requires_risk_rising=True,
        )
        manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)
        manager.trade_state.best_z = 0.10

        result = manager.update(0.20, floating_pnl_usdt=0.05, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "HOLD")
        self.assertEqual(result["blocked_exit_reason"], "take_profit")

    def test_mean_reversion_escape_does_not_bypass_hard_safety_exit(self):
        manager = self._manager(
            max_hold_hours=6,
            max_hold_warning_hours=4,
            partial_exit_enabled=False,
            mean_reversion_escape_enabled=True,
            mean_reversion_escape_z=0.25,
            mean_reversion_escape_min_pnl_usdt=0.0,
            mean_reversion_escape_requires_risk_rising=False,
        )
        manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - (7 * 3600))

        result = manager.update(0.20, floating_pnl_usdt=0.05, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "EXIT")
        self.assertEqual(result["reason"], "max_hold_time")

    def test_pnl_profit_lock_disabled_by_default_preserves_hold_behavior(self):
        manager = self._manager(partial_exit_enabled=False, trailing_stop_enabled=False)
        manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)
        manager.trade_state.max_favorable_pnl_usdt = 1.00

        result = manager.update(0.90, floating_pnl_usdt=0.10, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "HOLD")
        self.assertNotEqual(result.get("reason"), "pnl_profit_lock")

    def test_pnl_profit_lock_does_not_activate_before_mfe_clears_floor_plus_buffer(self):
        manager = self._manager(
            partial_exit_enabled=False,
            trailing_stop_enabled=False,
            pnl_profit_lock_enabled=True,
            pnl_profit_lock_activation_buffer_usdt=0.05,
        )
        manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)
        manager.trade_state.max_favorable_pnl_usdt = 0.22

        result = manager.update(0.90, floating_pnl_usdt=0.10, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "HOLD")
        self.assertFalse(manager.trade_state.pnl_profit_lock_active)

    def test_pnl_profit_lock_exits_when_current_pnl_falls_below_lock_floor(self):
        manager = self._manager(
            partial_exit_enabled=False,
            trailing_stop_enabled=False,
            pnl_profit_lock_enabled=True,
            pnl_profit_lock_giveback_pct=0.50,
        )
        manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)
        manager.trade_state.max_favorable_pnl_usdt = 1.00

        result = manager.update(0.90, floating_pnl_usdt=0.49, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "EXIT")
        self.assertEqual(result["reason"], "pnl_profit_lock")
        self.assertAlmostEqual(result["pnl_profit_lock_floor"], 0.50)
        self.assertAlmostEqual(result["max_favorable_pnl_usdt"], 1.00)

    def test_pnl_profit_lock_uses_effective_guard_floor_for_activation(self):
        manager = self._manager(
            partial_exit_enabled=False,
            trailing_stop_enabled=False,
            full_tp_guard_multiplier=0.5,
            pnl_profit_lock_enabled=True,
            pnl_profit_lock_activation_buffer_usdt=0.05,
            pnl_profit_lock_giveback_pct=0.50,
        )
        manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)
        manager.trade_state.max_favorable_pnl_usdt = 0.16

        result = manager.update(0.90, floating_pnl_usdt=0.09, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "EXIT")
        self.assertEqual(result["reason"], "pnl_profit_lock")
        self.assertAlmostEqual(result["effective_min_profit_usdt"], 0.10)
        self.assertAlmostEqual(result["guard_multiplier"], 0.5)

    def test_full_take_profit_still_outranks_pnl_profit_lock(self):
        manager = self._manager(
            partial_exit_enabled=True,
            trailing_stop_enabled=False,
            pnl_profit_lock_enabled=True,
            pnl_profit_lock_giveback_pct=0.50,
        )
        manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)
        manager.trade_state.max_favorable_pnl_usdt = 1.00

        result = manager.update(0.20, floating_pnl_usdt=0.49, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "EXIT")
        self.assertEqual(result["reason"], "take_profit")

    def test_partial_profit_does_not_outrank_active_pnl_profit_lock(self):
        manager = self._manager(
            partial_exit_enabled=True,
            trailing_stop_enabled=False,
            pnl_profit_lock_enabled=True,
            pnl_profit_lock_giveback_pct=0.50,
        )
        manager.open_position(entry_z=2.2, position_size=1000, entry_time=time.time() - 300)
        manager.trade_state.max_favorable_pnl_usdt = 1.00

        result = manager.update(0.90, floating_pnl_usdt=0.49, min_profit_usdt=0.20)

        self.assertEqual(result["action"], "EXIT")
        self.assertEqual(result["reason"], "pnl_profit_lock")
        self.assertNotEqual(result["action"], "PARTIAL_EXIT")


if __name__ == "__main__":
    unittest.main()
