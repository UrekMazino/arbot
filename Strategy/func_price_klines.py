"""
    Get historical klines/candlesticks for OKX instruments
    OKX API: https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-candlesticks

    Bar intervals: 1m, 3m, 5m, 15m, 30m, 1H, 2H, 4H, 6H, 12H, 1D, 1W, 1M
    Limit: max 100 candles per request; paginated to reach kline_limit.
"""

import time

from func_strategy_log import get_strategy_logger

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

    logger = get_strategy_logger()
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
                logger.warning("Klines error for %s: %s", inst_id, prices.get('msg', 'Unknown error'))
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

        logger.warning("Klines error for %s: no data returned", inst_id)
        return {'code': '1', 'msg': 'Insufficient data', 'data': []}

    except Exception as e:
        logger.exception("Klines exception for %s: %s", inst_id, e)
        return {'code': '1', 'msg': str(e), 'data': []}


def get_latest_klines(inst_id, limit=100):
    """
    Get latest candlesticks without pagination (fast path).

    Args:
        inst_id: Instrument ID (e.g., 'BTC-USDT-SWAP')
        limit: Number of candles to fetch (max 100)

    Returns:
        dict: OKX response payload
    """
    logger = get_strategy_logger()
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 100
    if limit <= 0:
        limit = 1
    if limit > 100:
        limit = 100

    try:
        prices = market_session.get_candlesticks(
            instId=inst_id,
            bar=time_frame,
            limit=str(limit),
        )
        if prices.get("code") != "0":
            logger.warning("Latest klines error for %s: %s", inst_id, prices.get("msg"))
        return prices
    except Exception as exc:
        logger.exception("Latest klines exception for %s: %s", inst_id, exc)
        return {"code": "1", "msg": str(exc), "data": []}
