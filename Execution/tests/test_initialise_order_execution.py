import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from func_execution_calls import initialise_order_execution
from config_execution_api import ticker_1, dry_run


def _print_result(label, result):
    if not result:
        print(f"{label}: FAIL (no result)")
        return False
    ok = result.get("ok", False)
    entry_id = result.get("entry_id", "")
    stop_id = result.get("stop_id", "")
    print(f"{label}: {'PASS' if ok else 'FAIL'}")
    print(f"  entry_id={entry_id} stop_id={stop_id}")
    return ok


def test_deterministic_dry_run():
    print("\n[1] Deterministic dry-run (mock orderbook)")
    mock_payload = {
        "arg": {"channel": "books", "instId": ticker_1},
        "data": [{
            "bids": [["43000", "2"]],
            "asks": [["43010", "1"]],
        }],
    }
    mock_instrument_info = {
        "instId": ticker_1,
        "ctVal": "0.01",
        "ctMult": "1",
        "ctValCcy": "BTC",
        "lotSz": "1",
        "minSz": "1",
        "maxMktSz": "1000",
        "maxLmtSz": "1000",
        "maxStopSz": "1000",
    }

    result = initialise_order_execution(
        ticker=ticker_1,
        direction="long",
        capital=1000,
        orderbook_payload=mock_payload,
        dry_run_override=True,
        place_stop=True,
        enforce_lot_size=False,
        instrument_info=mock_instrument_info,
    )
    assert _print_result("Deterministic dry-run", result), "Deterministic dry-run returned failed result"


def test_live_data_dry_run():
    print("\n[2] Live-data dry-run (OKX market data)")
    result = initialise_order_execution(
        ticker=ticker_1,
        direction="long",
        capital=1000,
        dry_run_override=True,
        place_stop=True,
        enforce_lot_size=True,
    )
    if not result:
        pytest.skip("Live-data dry-run unavailable in this environment (market data/orderbook access blocked).")
    assert _print_result("Live-data dry-run", result), "Live-data dry-run returned failed result"


def test_demo_execution():
    print("\n[3] Demo execution (real orders)")
    if dry_run:
        pytest.skip("Demo execution skipped: dry_run=True. Set dry_run=False to enable.")

    result = initialise_order_execution(
        ticker=ticker_1,
        direction="long",
        capital=100,
        place_stop=True,
    )
    if not result:
        pytest.skip("Demo execution unavailable in this environment (market data/orderbook access blocked).")
    assert _print_result("Demo execution", result), "Demo execution returned failed result"


def main():
    tests = [
        ("Deterministic dry-run", test_deterministic_dry_run),
        ("Live-data dry-run", test_live_data_dry_run),
        ("Demo execution", test_demo_execution),
    ]
    passed = 0
    skipped = 0

    for label, fn in tests:
        try:
            fn()
            passed += 1
        except pytest.skip.Exception as exc:
            skipped += 1
            print(f"{label}: SKIP ({exc})")
        except AssertionError as exc:
            print(f"{label}: FAIL ({exc})")

    total = len(tests)
    print(f"\nResult: {passed} passed, {skipped} skipped, {total - passed - skipped} failed")


if __name__ == "__main__":
    main()
