import os
import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from trade_quality_gate import TradeQualitySettings, evaluate_trade_quality  # noqa: E402


class TestTradeQualityGate(unittest.TestCase):
    ENV_KEYS = [
        "STATBOT_TRADE_QUALITY_GATE",
        "STATBOT_TRADE_QUALITY_GATE_MODE",
        "STATBOT_TQG_MIN_SCORE",
    ]

    def setUp(self):
        self.prev_env = {key: os.environ.get(key) for key in self.ENV_KEYS}
        for key in self.ENV_KEYS:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self.prev_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _settings(self, mode="active", min_score=72.0):
        return TradeQualitySettings(
            mode=mode,
            min_score=min_score,
            preferred_max_p_value=0.05,
            hard_max_p_value=0.15,
            hard_min_zero_crossings=3,
            min_zero_crossings=15,
            target_zero_crossings=30,
            min_correlation=0.60,
            max_spread_trend=0.002,
            hard_max_spread_trend=0.010,
            min_edge_z=1.20,
            min_pair_trades=4,
            min_pair_win_rate=0.45,
            max_pair_consecutive_losses=2,
            require_pair_profit=True,
        )

    def _metrics(self, **overrides):
        metrics = {
            "coint_flag": 1,
            "coint_health": "healthy",
            "p_value": 0.01,
            "adf_stat": -4.2,
            "critical_value": -3.4,
            "zero_crossings": 30,
            "correlation": 0.90,
            "returns_correlation": 0.60,
            "spread_trend": 0.0,
            "latest_zscore": 2.30,
        }
        metrics.update(overrides)
        return metrics

    def _pair_stats(self, **overrides):
        stats = {
            "trades": 6,
            "wins": 5,
            "losses": 1,
            "win_rate": 5 / 6,
            "win_usdt": 15.0,
            "loss_usdt": 3.0,
            "consecutive_losses": 0,
        }
        stats.update(overrides)
        return stats

    def _decision(self, **overrides):
        params = {
            "signal": "SELL_SPREAD",
            "metrics": self._metrics(),
            "zscores": [2.05, 2.20, 2.25, 2.30],
            "pair_stats": self._pair_stats(),
            "entry_z": 2.0,
            "entry_z_max": 3.0,
            "entry_z_tolerance": 0.05,
            "exit_z": 0.35,
            "ratio_long": 4.0,
            "ratio_short": 3.5,
            "min_liquidity_ratio": 1.5,
            "target_usdt": 1000.0,
            "liquidity_long_usdt": 4000.0,
            "liquidity_short_usdt": 3500.0,
            "settings": self._settings(),
        }
        params.update(overrides)
        return evaluate_trade_quality(**params)

    def test_high_quality_signal_passes(self):
        decision = self._decision(zscores=[2.40, 2.35, 2.32, 2.30])

        self.assertTrue(decision.passed)
        self.assertTrue(decision.allow)
        self.assertGreaterEqual(decision.score, decision.min_score)
        self.assertEqual(decision.reason, "quality_passed")

    def test_p_value_above_hard_limit_blocks(self):
        decision = self._decision(metrics=self._metrics(p_value=0.20))

        self.assertFalse(decision.passed)
        self.assertFalse(decision.allow)
        self.assertIn("p_value_above_hard_limit", decision.hard_reasons)

    def test_score_below_threshold_blocks_without_hard_failure(self):
        decision = self._decision(
            metrics=self._metrics(
                p_value=0.08,
                zero_crossings=5,
                correlation=0.45,
                returns_correlation=0.05,
                spread_trend=0.0018,
            ),
            pair_stats=self._pair_stats(
                trades=8,
                wins=2,
                losses=6,
                win_rate=0.25,
                win_usdt=3.0,
                loss_usdt=12.0,
                consecutive_losses=1,
            ),
            zscores=[2.0, 2.1, 2.25, 2.42],
            ratio_long=1.6,
            ratio_short=1.55,
        )

        self.assertFalse(decision.passed)
        self.assertFalse(decision.allow)
        self.assertEqual(decision.reason, "score_below_threshold")
        self.assertIn("zero_crossings_below_quality_target", decision.reasons)

    def test_shadow_mode_reports_failure_but_allows_execution(self):
        decision = self._decision(
            metrics=self._metrics(p_value=0.20),
            settings=self._settings(mode="shadow"),
        )

        self.assertFalse(decision.passed)
        self.assertTrue(decision.allow)
        self.assertEqual(decision.mode, "shadow")

    def test_pair_consecutive_losses_are_soft_score_penalty_only(self):
        decision = self._decision(
            zscores=[2.40, 2.35, 2.32, 2.30],
            pair_stats=self._pair_stats(
                trades=8,
                wins=6,
                losses=2,
                win_rate=0.75,
                win_usdt=30.0,
                loss_usdt=6.0,
                consecutive_losses=2,
            ),
        )

        self.assertTrue(decision.passed)
        self.assertTrue(decision.allow)
        self.assertNotIn("pair_consecutive_losses_at_limit", decision.hard_reasons)
        self.assertIn("pair_consecutive_losses_at_limit", decision.reasons)
        self.assertLessEqual(decision.components["pair_history"], 1.4)


if __name__ == "__main__":
    unittest.main()
