import datetime
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from config_execution_api import ticker_1
from func_price_calls import (
    get_ticker_liquidity_analysis,
    get_timestamps,
    normalize_candlesticks,
    extract_close_prices,
    get_candlesticks,
    get_close_prices,
    get_price_klines,
    get_latest_klines,
)


def _print_result(label, ok, details=""):
    status = "PASS" if ok else "FAIL"
    print(f"{label}: {status}")
    if details:
        print(f"  {details}")
    return ok


def test_timestamp_window():
    print("\n[1] Timestamp window")
    now = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    start_ms, now_ms, end_ms = get_timestamps(bar="1m", limit=10, now=now)
    expected_now = int(now.timestamp() * 1000)
    expected_start = expected_now - (10 * 60 * 1000)
    expected_end = expected_now + (60 * 1000)
    ok = (start_ms, now_ms, end_ms) == (expected_start, expected_now, expected_end)
    details = f"start={start_ms} now={now_ms} end={end_ms}"
    return _print_result("Timestamp window", ok, details)


def test_normalize_and_extract():
    print("\n[2] Normalize + close extraction (mock)")
    raw = [
        ["1700000000000", "1", "2", "0.5", "1.5", "10", "20", "30", "1"],
        ["1699999940000", "1.1", "2.1", "0.6", "1.6", "11", "21", "31", "1"],
    ]
    candles = normalize_candlesticks(raw, ascending=True)
    closes = extract_close_prices(candles)
    ok = len(candles) == 2 and closes == [1.6, 1.5]
    details = f"closes={closes}"
    return _print_result("Normalize + close extraction", ok, details)


class _StubSession:
    def __init__(self, response):
        self._response = response

    def get_candlesticks(self, **_kwargs):
        return self._response


class _PagingSession:
    def get_candlesticks(self, **kwargs):
        limit = int(kwargs.get("limit", 100))
        before = kwargs.get("before")
        start = int(before) if before is not None else 200
        data = []
        for idx in range(limit):
            ts = start - idx
            if ts <= 0:
                break
            data.append([str(ts), "1", "2", "0.5", "1.5", "10", "20", "30", "1"])
        return {"code": "0", "msg": "", "data": data}


def test_trade_liquidity_live():
    print("\n[3] Trade liquidity (live OKX demo)")
    analysis = get_ticker_liquidity_analysis(ticker_1)
    avg = analysis.get("avg_trade_size", 0)
    price = analysis.get("last_price", 0)
    label = analysis.get("label", "unknown")
    basis = analysis.get("label_basis", "none")
    ok = avg > 0 and price > 0
    details = f"avg={avg} price={price} label={label} basis={basis}"
    return _print_result("Trade liquidity (live OKX demo)", ok, details)


def test_live_candles():
    print("\n[4] Live OKX candlesticks")
    response = get_candlesticks(ticker_1, bar="1m", limit=5)
    if response.get("code") != "0":
        details = f"code={response.get('code')} msg={response.get('msg')}"
        return _print_result("Live OKX candlesticks", False, details)

    candles = normalize_candlesticks(response.get("data", []), ascending=True)
    closes = extract_close_prices(candles)
    stub = _StubSession(response)
    helper_closes = get_close_prices(ticker_1, bar="1m", limit=5, session=stub)
    ok = bool(closes) and bool(helper_closes)
    details = f"candles={len(candles)} closes={len(closes)} helper={len(helper_closes)}"
    return _print_result("Live OKX candlesticks", ok, details)


def test_get_price_klines_paged():
    print("\n[5] Paged get_price_klines (mock)")
    data = get_price_klines("TEST", bar="1m", limit=150, session=_PagingSession(), use_start_time=False)
    ok = len(data) == 150 and data[0][0] == "200" and data[-1][0] == "51"
    details = f"rows={len(data)} first={data[0][0]} last={data[-1][0]}"
    return _print_result("Paged get_price_klines", ok, details)


def test_get_latest_klines_mock():
    print("\n[6] Latest klines (mock)")
    series_1, series_2 = get_latest_klines("TEST1", "TEST2", bar="1m", limit=120,
                                           session=_PagingSession(), ascending=False)
    ok = len(series_1) == 120 and len(series_2) == 120
    details = f"series_1={len(series_1)} series_2={len(series_2)}"
    return _print_result("Latest klines (mock)", ok, details)


def test_get_price_klines():
    print("\n[7] Live OKX get_price_klines")
    data = get_price_klines(ticker_1, bar="1m", limit=5)
    ok = isinstance(data, list) and len(data) > 0
    details = f"rows={len(data)}"
    return _print_result("Live OKX get_price_klines", ok, details)


def main():
    passed = 0
    total = 7

    if test_timestamp_window():
        passed += 1
    if test_normalize_and_extract():
        passed += 1
    if test_trade_liquidity_live():
        passed += 1
    if test_live_candles():
        passed += 1
    if test_get_price_klines_paged():
        passed += 1
    if test_get_latest_klines_mock():
        passed += 1
    if test_get_price_klines():
        passed += 1

    print(f"\nResult: {passed}/{total} tests passed")


if __name__ == "__main__":
    main()
