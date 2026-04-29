import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from func_close_positions import account_is_flat, exposure_tickers_from_state  # noqa: E402


class TestAccountFlatHelpers(unittest.TestCase):
    def test_account_is_flat_checks_all_positions_and_orders(self):
        state = {
            "ok": True,
            "positions": [{"instId": "SOL-USDT-SWAP", "pos": "1.25"}],
            "orders": [{"instId": "ADA-USDT-SWAP", "ordId": "abc"}],
        }

        flat, blockers = account_is_flat(state=state)

        self.assertFalse(flat)
        self.assertTrue(any("SOL-USDT-SWAP" in item for item in blockers))
        self.assertTrue(any("ADA-USDT-SWAP" in item for item in blockers))

    def test_exposure_tickers_from_state_includes_positions_and_orders_once(self):
        state = {
            "ok": True,
            "positions": [{"instId": "SOL-USDT-SWAP", "pos": "1.25"}],
            "orders": [
                {"instId": "SOL-USDT-SWAP", "ordId": "abc"},
                {"instId": "ADA-USDT-SWAP", "ordId": "def"},
            ],
        }

        self.assertEqual(
            exposure_tickers_from_state(state),
            ["SOL-USDT-SWAP", "ADA-USDT-SWAP"],
        )


if __name__ == "__main__":
    unittest.main()
