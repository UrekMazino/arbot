import os
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from strategy_router import (
    StrategyInput,
    StrategyRouter,
    resolve_strategy_policy_overrides,
    should_block_new_entries,
)


class _MemoryStateStore:
    def __init__(self):
        self.state = {
            "mode": "off",
            "active_strategy": "STATARB_MR",
            "desired_strategy": "STATARB_MR",
            "pending_strategy": "",
            "pending_count": 0,
            "since_ts": 0.0,
            "last_eval_ts": 0.0,
            "strategy_switch_count": 0,
            "reason_codes": [],
            "diagnostics": {},
            "updated_ts": 0.0,
        }

    def load(self):
        return dict(self.state)

    def save(self, state):
        self.state = dict(state)


def _input(
    ts=2000.0,
    regime="RANGE",
    confidence=0.8,
    in_position=False,
    coint_flag=1,
    zscores=None,
):
    if zscores is None:
        zscores = [0.1, -0.2, 0.4, -0.1, 0.2, -0.3, 0.1, -0.2]
    regime_decision = {
        "regime": regime,
        "confidence": confidence,
    }
    return StrategyInput(
        ts=ts,
        regime_decision=regime_decision,
        in_position=in_position,
        coint_flag=coint_flag,
        zscore_history=zscores,
        spread_history=None,
    )


class TestStrategyRouter(unittest.TestCase):
    ENV_KEYS = [
        "STATBOT_STRATEGY_ROUTER_MODE",
        "STATBOT_STRATEGY_MIN_HOLD_SECONDS",
        "STATBOT_STRATEGY_CONFIRM_COUNT",
        "STATBOT_STRATEGY_ALLOW_SWITCH_IN_POSITION",
        "STATBOT_STRATEGY_TREND_ENABLE_MEAN_SHIFT_GATE",
        "STATBOT_STRATEGY_TREND_MEAN_SHORT_WINDOW",
        "STATBOT_STRATEGY_TREND_MEAN_LONG_WINDOW",
        "STATBOT_STRATEGY_TREND_MEAN_SHIFT_Z_THRESHOLD",
        "STATBOT_STRATEGY_SCORE_MIN_TRADES",
        "STATBOT_STRATEGY_SCORE_MIN_WIN_RATE",
        "STATBOT_STRATEGY_SCORE_MAX_ROLLING_LOSS_USDT",
        "STATBOT_STRATEGY_COOLDOWN_SECONDS",
    ]

    def setUp(self):
        self.prev_env = {k: os.environ.get(k) for k in self.ENV_KEYS}
        os.environ["STATBOT_STRATEGY_ROUTER_MODE"] = "active"
        os.environ["STATBOT_STRATEGY_MIN_HOLD_SECONDS"] = "0"
        os.environ["STATBOT_STRATEGY_CONFIRM_COUNT"] = "1"
        os.environ["STATBOT_STRATEGY_ALLOW_SWITCH_IN_POSITION"] = "0"
        os.environ["STATBOT_STRATEGY_TREND_ENABLE_MEAN_SHIFT_GATE"] = "0"
        os.environ["STATBOT_STRATEGY_SCORE_MIN_TRADES"] = "8"
        os.environ["STATBOT_STRATEGY_SCORE_MIN_WIN_RATE"] = "0.35"
        os.environ["STATBOT_STRATEGY_SCORE_MAX_ROLLING_LOSS_USDT"] = "20"
        os.environ["STATBOT_STRATEGY_COOLDOWN_SECONDS"] = "3600"

    def tearDown(self):
        for key, value in self.prev_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_regime_mapping_to_strategy(self):
        store = _MemoryStateStore()
        router = StrategyRouter(state_store=store)

        decision_range = router.evaluate(_input(ts=1000.0, regime="RANGE"))
        self.assertEqual(decision_range.active_strategy, "STATARB_MR")

        decision_trend = router.evaluate(_input(ts=1005.0, regime="TREND"))
        self.assertEqual(decision_trend.active_strategy, "TREND_SPREAD")
        self.assertTrue(decision_trend.changed)

        decision_risk = router.evaluate(_input(ts=1010.0, regime="RISK_OFF"))
        self.assertEqual(decision_risk.active_strategy, "DEFENSIVE")
        self.assertFalse(decision_risk.allow_new_entries)

    def test_pending_switch_while_in_position(self):
        store = _MemoryStateStore()
        store.state["active_strategy"] = "STATARB_MR"
        store.state["since_ts"] = 1000.0
        router = StrategyRouter(
            state_store=store,
            config={"min_hold_seconds": 0, "confirm_count": 1, "allow_switch_in_position": False},
        )

        first = router.evaluate(_input(ts=1100.0, regime="TREND", in_position=True))
        self.assertEqual(first.active_strategy, "STATARB_MR")
        self.assertEqual(first.pending_strategy, "TREND_SPREAD")
        self.assertEqual(first.pending_count, 1)
        self.assertFalse(first.changed)

        second = router.evaluate(_input(ts=1110.0, regime="TREND", in_position=False))
        self.assertEqual(second.active_strategy, "TREND_SPREAD")
        self.assertEqual(second.pending_strategy, "")
        self.assertTrue(second.changed)

    def test_cointegration_gate_blocks_entries_without_switch(self):
        store = _MemoryStateStore()
        store.state["active_strategy"] = "TREND_SPREAD"
        store.state["since_ts"] = 1000.0
        router = StrategyRouter(
            state_store=store,
            config={"min_hold_seconds": 0, "confirm_count": 1},
        )

        decision = router.evaluate(_input(ts=1200.0, regime="TREND", coint_flag=0))
        self.assertEqual(decision.active_strategy, "TREND_SPREAD")
        self.assertFalse(decision.allow_new_entries)
        self.assertIn("coint_gate", decision.reason_codes)
        self.assertFalse(decision.changed)

    def test_mean_shift_gate_on_trend_strategy(self):
        os.environ["STATBOT_STRATEGY_TREND_ENABLE_MEAN_SHIFT_GATE"] = "1"
        os.environ["STATBOT_STRATEGY_TREND_MEAN_SHORT_WINDOW"] = "5"
        os.environ["STATBOT_STRATEGY_TREND_MEAN_LONG_WINDOW"] = "20"
        os.environ["STATBOT_STRATEGY_TREND_MEAN_SHIFT_Z_THRESHOLD"] = "0.5"

        store = _MemoryStateStore()
        store.state["active_strategy"] = "TREND_SPREAD"
        store.state["since_ts"] = 1000.0
        router = StrategyRouter(
            state_store=store,
            config={"min_hold_seconds": 0, "confirm_count": 1},
        )

        zscores = [0.0] * 15 + [2.0, 2.2, 2.4, 2.6, 2.8]
        decision = router.evaluate(_input(ts=1300.0, regime="TREND", zscores=zscores))
        self.assertFalse(decision.allow_new_entries)
        self.assertIn("mean_shift_gate", decision.reason_codes)
        self.assertGreater(float(decision.diagnostics.get("mean_shift_z", 0.0)), 0.5)

    def test_helpers_block_only_active_mode(self):
        decision = {"allow_new_entries": False}
        self.assertFalse(should_block_new_entries("off", decision))
        self.assertFalse(should_block_new_entries("shadow", decision))
        self.assertTrue(should_block_new_entries("active", decision))

    def test_policy_overrides_apply_only_active_mode(self):
        decision = {
            "active_strategy": "TREND_SPREAD",
            "allow_new_entries": True,
            "entry_z": 2.8,
            "entry_z_max": 5.0,
            "min_persist_bars": 4,
            "min_liquidity_ratio": 2.0,
            "size_multiplier": 0.35,
        }

        shadow = resolve_strategy_policy_overrides("shadow", decision)
        self.assertFalse(shadow["active"])
        self.assertIsNone(shadow["entry_z"])

        active = resolve_strategy_policy_overrides("active", decision)
        self.assertTrue(active["active"])
        self.assertEqual(active["strategy_name"], "TREND_SPREAD")
        self.assertEqual(active["entry_z"], 2.8)
        self.assertEqual(active["entry_z_max"], 5.0)
        self.assertEqual(active["min_persist_bars"], 4)
        self.assertEqual(active["min_liquidity_ratio"], 2.0)
        self.assertEqual(active["size_multiplier"], 0.35)

    def test_strategy_cooldown_triggers_from_rolling_stats(self):
        os.environ["STATBOT_STRATEGY_SCORE_MIN_TRADES"] = "3"
        os.environ["STATBOT_STRATEGY_SCORE_MIN_WIN_RATE"] = "0.60"
        os.environ["STATBOT_STRATEGY_SCORE_MAX_ROLLING_LOSS_USDT"] = "1.0"
        os.environ["STATBOT_STRATEGY_COOLDOWN_SECONDS"] = "900"

        store = _MemoryStateStore()
        store.state["active_strategy"] = "TREND_SPREAD"
        store.state["since_ts"] = 1000.0
        store.state["strategy_performance"] = {
            "window_trades": 20,
            "stats": {
                "TREND_SPREAD": {
                    "rolling_count": 4,
                    "rolling_win_rate_pct": 25.0,
                    "rolling_pnl_usdt": -2.5,
                }
            },
        }
        router = StrategyRouter(
            state_store=store,
            config={"min_hold_seconds": 0, "confirm_count": 1},
        )

        decision = router.evaluate(_input(ts=1500.0, regime="TREND", coint_flag=1))
        self.assertFalse(decision.allow_new_entries)
        self.assertIn("strategy_cooldown", decision.reason_codes)
        self.assertTrue(bool(decision.diagnostics.get("cooldown_triggered")))
        self.assertTrue(bool(decision.diagnostics.get("cooldown_active")))
        self.assertGreater(float(decision.diagnostics.get("cooldown_until_ts", 0.0)), 1500.0)

    def test_strategy_cooldown_clears_after_expiry(self):
        os.environ["STATBOT_STRATEGY_SCORE_MIN_TRADES"] = "10"
        os.environ["STATBOT_STRATEGY_COOLDOWN_SECONDS"] = "900"

        store = _MemoryStateStore()
        store.state["active_strategy"] = "TREND_SPREAD"
        store.state["since_ts"] = 1000.0
        store.state["strategy_cooldowns"] = {
            "TREND_SPREAD": {
                "until_ts": 1200.0,
                "reason": "rolling_loss",
            }
        }
        store.state["strategy_performance"] = {"window_trades": 20, "stats": {}}
        router = StrategyRouter(
            state_store=store,
            config={"min_hold_seconds": 0, "confirm_count": 1},
        )

        decision = router.evaluate(_input(ts=1500.0, regime="TREND", coint_flag=1))
        self.assertTrue(bool(decision.diagnostics.get("cooldown_cleared")))
        self.assertFalse(bool(decision.diagnostics.get("cooldown_active")))
        self.assertNotIn("strategy_cooldown", decision.reason_codes)

    def test_strategy_cooldown_clears_when_current_settings_no_longer_qualify(self):
        os.environ["STATBOT_STRATEGY_SCORE_MIN_TRADES"] = "20"
        os.environ["STATBOT_STRATEGY_SCORE_MIN_WIN_RATE"] = "0.30"
        os.environ["STATBOT_STRATEGY_COOLDOWN_SECONDS"] = "10"

        store = _MemoryStateStore()
        store.state["active_strategy"] = "STATARB_MR"
        store.state["since_ts"] = 1000.0
        store.state["strategy_cooldowns"] = {
            "STATARB_MR": {
                "until_ts": 2000.0,
                "reason": "low_win_rate",
            }
        }
        store.state["strategy_performance"] = {
            "window_trades": 20,
            "stats": {
                "STATARB_MR": {
                    "rolling_count": 9,
                    "rolling_win_rate_pct": 33.33,
                    "rolling_pnl_usdt": -0.85,
                }
            },
        }
        router = StrategyRouter(
            state_store=store,
            config={"min_hold_seconds": 0, "confirm_count": 1},
        )

        decision = router.evaluate(_input(ts=1500.0, regime="RANGE", coint_flag=1))
        self.assertTrue(bool(decision.diagnostics.get("cooldown_cleared")))
        self.assertFalse(bool(decision.diagnostics.get("cooldown_active")))
        self.assertNotIn("strategy_cooldown", decision.reason_codes)
        self.assertNotIn("STATARB_MR", store.state.get("strategy_cooldowns", {}))


if __name__ == "__main__":
    unittest.main()
