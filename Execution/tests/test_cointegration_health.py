import os
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cointegration_health import (  # noqa: E402
    COINT_HEALTH_BROKEN,
    COINT_HEALTH_VALID,
    COINT_HEALTH_WATCH,
    classify_cointegration_health,
    get_cointegration_health_settings,
)


class TestCointegrationHealth(unittest.TestCase):
    def setUp(self):
        self._prev_env = {
            name: os.environ.get(name)
            for name in (
                "STATBOT_COINT_WATCH_P_VALUE",
                "STATBOT_COINT_FAIL_P_VALUE",
                "STATBOT_COINT_ADF_MARGIN_PCT",
            )
        }
        for name in self._prev_env:
            os.environ.pop(name, None)

    def tearDown(self):
        for name, value in self._prev_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_strict_pass_is_valid(self):
        result = classify_cointegration_health(
            {
                "coint_flag": 1,
                "p_value": 0.08,
                "adf_stat": -3.8,
                "critical_value": -3.4,
            },
            strict_pvalue=0.15,
        )

        self.assertEqual(result["state"], COINT_HEALTH_VALID)
        self.assertTrue(result["is_valid"])

    def test_soft_p_value_enters_watch_band(self):
        result = classify_cointegration_health(
            {
                "coint_flag": 0,
                "p_value": 0.20,
                "adf_stat": -2.8,
                "critical_value": -3.4,
            },
            strict_pvalue=0.15,
        )

        self.assertEqual(result["state"], COINT_HEALTH_WATCH)
        self.assertEqual(result["reason"], "p_value_watch_band")

    def test_adf_near_margin_extends_watch_band_until_fail_pvalue(self):
        watch_result = classify_cointegration_health(
            {
                "coint_flag": 0,
                "p_value": 0.30,
                "adf_stat": -3.15,
                "critical_value": -3.4,
            },
            strict_pvalue=0.15,
        )
        broken_result = classify_cointegration_health(
            {
                "coint_flag": 0,
                "p_value": 0.36,
                "adf_stat": -3.35,
                "critical_value": -3.4,
            },
            strict_pvalue=0.15,
        )

        self.assertEqual(watch_result["state"], COINT_HEALTH_WATCH)
        self.assertEqual(watch_result["reason"], "adf_near_watch_band")
        self.assertEqual(broken_result["state"], COINT_HEALTH_BROKEN)

    def test_settings_clamp_watch_above_strict_and_fail_above_watch(self):
        os.environ["STATBOT_COINT_WATCH_P_VALUE"] = "0.05"
        os.environ["STATBOT_COINT_FAIL_P_VALUE"] = "0.08"

        settings = get_cointegration_health_settings(strict_pvalue=0.15)

        self.assertEqual(settings["watch_pvalue"], 0.15)
        self.assertEqual(settings["fail_pvalue"], 0.15)


if __name__ == "__main__":
    unittest.main()
