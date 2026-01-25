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

    result = initialise_order_execution(
        ticker=ticker_1,
        direction="long",
        capital=1000,
        orderbook_payload=mock_payload,
        dry_run_override=True,
        place_stop=True,
        enforce_lot_size=False,
    )
    return _print_result("Deterministic dry-run", result)


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
    return _print_result("Live-data dry-run", result)


def test_demo_execution():
    print("\n[3] Demo execution (real orders)")
    if dry_run:
        print("Demo execution skipped: dry_run=True. Set dry_run=False to enable.")
        return False

    result = initialise_order_execution(
        ticker=ticker_1,
        direction="long",
        capital=100,
        place_stop=True,
    )
    return _print_result("Demo execution", result)


def main():
    passed = 0
    total = 3

    if test_deterministic_dry_run():
        passed += 1
    if test_live_data_dry_run():
        passed += 1
    if test_demo_execution():
        passed += 1

    print(f"\nResult: {passed}/{total} tests passed")


if __name__ == "__main__":
    main()
