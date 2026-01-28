"""
    Get historical klines/candlesticks for OKX instruments
    OKX API: https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-candlesticks

    Bar intervals: 1m, 3m, 5m, 15m, 30m, 1H, 2H, 4H, 6H, 12H, 1D, 1W, 1M
    Limit: max 100 candles per request; paginated to reach kline_limit.
"""

import time

from config_strategy_api import market_session, time_frame, kline_limit


def get_price_klines(inst_id):
    """
    Get historical candlestick data for an instrument

    Args:
        inst_id: Instrument ID (e.g., 'BTC-USDT-SWAP')

    Returns:
        dict: {'code': '0', 'msg': '', 'data': [[timestamp, open, high, low, close, vol, volCcy], ...]}
    """
    try:
        target = int(kline_limit)
    except (TypeError, ValueError):
        target = 0

    if target <= 0:
        return {'code': '1', 'msg': 'Invalid kline_limit', 'data': []}

    collected = []
    seen_ts = set()
    after = None
    last_oldest = None

    try:
        while len(collected) < target:
            batch_limit = min(100, target - len(collected))
            params = {
                "instId": inst_id,
                "bar": time_frame,
                "limit": str(batch_limit),
            }
            if after is not None:
                params["after"] = str(after)

            prices = market_session.get_candlesticks(**params)

            if prices.get('code') != '0':
                print(f"  Error getting klines: {prices.get('msg', 'Unknown error')}")
                return prices

            data = prices.get('data') or []
            if not data:
                break

            added = 0
            for row in data:
                if not row:
                    continue
                ts = row[0]
                if ts in seen_ts:
                    continue
                seen_ts.add(ts)
                collected.append(row)
                added += 1

            if added == 0:
                break

            oldest_ts = data[-1][0]
            if last_oldest == oldest_ts:
                break
            last_oldest = oldest_ts
            after = oldest_ts

            if len(data) < batch_limit:
                break

            time.sleep(0.05)

        if collected:
            prices['data'] = collected[:target]
            return prices

        print("  Error getting klines: no data returned")
        return {'code': '1', 'msg': 'Insufficient data', 'data': []}

    except Exception as e:
        print(f"  Exception getting klines: {e}")
        return {'code': '1', 'msg': str(e), 'data': []}
