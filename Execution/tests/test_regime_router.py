import os
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from regime_router import RegimeInput, RegimeRouter, should_block_new_entries


class _MemoryStateStore:
    def __init__(self):
        self.state = {
            "current_regime": "RANGE",
            "candidate_regime": "RANGE",
            "confidence": 0.0,
            "since_ts": 0.0,
            "pending_candidate": "",
            "pending_count": 0,
            "reason_codes": [],
            "diagnostics": {},
            "last_eval_ts": 0.0,
            "updated_ts": 0.0,
        }

    def load(self):
        return dict(self.state)

    def save(self, state):
        self.state = dict(state)


def _build_candles(count=180, base=100.0, drift=0.25):
    candles = []
    close_val = base
    for idx in range(count):
        close_val = close_val + drift + (0.05 if idx % 7 == 0 else -0.02)
        high_val = close_val * 1.002
        low_val = close_val * 0.998
        open_val = (high_val + low_val) * 0.5
        candles.append(
            {
                "timestamp": idx,
                "open": open_val,
                "high": high_val,
                "low": low_val,
                "close": close_val,
            }
        )
    return candles


def _input(
    ts=2000.0,
    coint_flag=1,
    liq_label="high",
    depth=20000.0,
    liq_label_long=None,
    liq_label_short=None,
    depth_long=None,
    depth_short=None,
    candles=None,
):
    if candles is None:
        candles = _build_candles()
    if liq_label_long is None:
        liq_label_long = liq_label
    if liq_label_short is None:
        liq_label_short = liq_label
    if depth_long is None:
        depth_long = depth
    if depth_short is None:
        depth_short = depth
    return RegimeInput(
        ts=ts,
        ticker_1="ETH-USDT-SWAP",
        ticker_2="LINK-USDT-SWAP",
        latest_zscore=2.4,
        z_metrics={"coint_flag": coint_flag, "orderbook_dead": False},
        market_candles=candles,
        liq_long={"label": liq_label_long, "orderbook_depth_notional": depth_long},
        liq_short={"label": liq_label_short, "orderbook_depth_notional": depth_short},
        per_leg_target_usdt=2000.0,
        pnl_fallback_active=False,
        session_drawdown_pct=0.0,
    )


class TestRegimeRouter(unittest.TestCase):
    def setUp(self):
        self.prev_mode = os.environ.get("STATBOT_REGIME_ROUTER_MODE")
        os.environ["STATBOT_REGIME_ROUTER_MODE"] = "shadow"

    def tearDown(self):
        if self.prev_mode is None:
            os.environ.pop("STATBOT_REGIME_ROUTER_MODE", None)
        else:
            os.environ["STATBOT_REGIME_ROUTER_MODE"] = self.prev_mode

    def test_cointegration_loss_forces_risk_off(self):
        store = _MemoryStateStore()
        router = RegimeRouter(
            state_store=store,
            config={"min_hold_seconds": 1200, "confirm_count": 2},
        )
        decision = router.evaluate(_input(coint_flag=0))
        self.assertEqual(decision.regime, "RISK_OFF")
        self.assertIn("cointegration_lost", decision.reason_codes)

    def test_strong_trend_classifies_trend(self):
        store = _MemoryStateStore()
        router = RegimeRouter(
            state_store=store,
            config={"min_hold_seconds": 0, "confirm_count": 1, "trend_threshold": 0.8},
        )
        decision = router.evaluate(_input(coint_flag=1))
        self.assertEqual(decision.candidate_regime, "TREND")
        self.assertEqual(decision.regime, "TREND")
        self.assertIn("strong_trend", decision.reason_codes)

    def test_thin_liquidity_forces_risk_off(self):
        store = _MemoryStateStore()
        router = RegimeRouter(
            state_store=store,
            config={"min_hold_seconds": 0, "confirm_count": 1},
        )
        decision = router.evaluate(_input(liq_label="low", depth=400.0))
        self.assertEqual(decision.regime, "RISK_OFF")
        self.assertIn("thin_liquidity", decision.reason_codes)

    def test_low_label_with_deep_orderbook_not_risk_off(self):
        store = _MemoryStateStore()
        router = RegimeRouter(
            state_store=store,
            config={"min_hold_seconds": 0, "confirm_count": 1, "trend_threshold": 0.8},
        )
        decision = router.evaluate(
            _input(
                liq_label_long="low",
                liq_label_short="high",
                depth_long=250000.0,
                depth_short=400000.0,
            )
        )
        self.assertNotEqual(decision.regime, "RISK_OFF")
        self.assertNotIn("thin_liquidity", decision.reason_codes)
        self.assertFalse(bool(decision.diagnostics.get("liq_thin")))
        self.assertFalse(bool(decision.diagnostics.get("liq_label_pressure")))

    def test_hysteresis_blocks_fast_range_to_trend_switch(self):
        store = _MemoryStateStore()
        store.state["current_regime"] = "RANGE"
        store.state["since_ts"] = 1000.0

        router = RegimeRouter(
            state_store=store,
            config={"min_hold_seconds": 600, "confirm_count": 2, "trend_threshold": 0.8},
        )

        first = router.evaluate(_input(ts=1100.0))
        self.assertEqual(first.candidate_regime, "TREND")
        self.assertEqual(first.regime, "RANGE")
        self.assertEqual(first.pending_candidate, "TREND")
        self.assertEqual(first.pending_count, 1)

        second = router.evaluate(_input(ts=1200.0))
        self.assertEqual(second.regime, "RANGE")
        self.assertEqual(second.pending_count, 2)

        third = router.evaluate(_input(ts=1705.0))
        self.assertEqual(third.regime, "TREND")
        self.assertTrue(third.changed)

    def test_gate_helper_blocks_only_active_mode(self):
        decision = {"allow_new_entries": False}
        self.assertFalse(should_block_new_entries("off", decision))
        self.assertFalse(should_block_new_entries("shadow", decision))
        self.assertTrue(should_block_new_entries("active", decision))
        self.assertFalse(should_block_new_entries("active", {"allow_new_entries": True}))
        self.assertFalse(should_block_new_entries("active", None))


if __name__ == "__main__":
    unittest.main()
