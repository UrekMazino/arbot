"""
    Get historical klines/candlesticks for OKX instruments
    OKX API: https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-candlesticks

    Bar intervals: 1m, 3m, 5m, 15m, 30m, 1H, 2H, 4H, 6H, 12H, 1D, 1W, 1M
    Limit: max 100 candles per request; paginated to reach kline_limit.
"""

import time
import os
import threading

from func_strategy_log import get_strategy_logger

from config_strategy_api import market_session, time_frame, kline_limit


def _float_env(name, default):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return float(default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


class RateLimiter:
    def __init__(self, max_requests_per_second=5.0):
        try:
            self.max_requests = float(max_requests_per_second)
        except (TypeError, ValueError):
            self.max_requests = 0.0
        if self.max_requests < 0:
            self.max_requests = 0.0
        self.tokens = self.max_requests
        self.lock = threading.Lock()
        self.last_update = time.time()

    def acquire(self):
        if self.max_requests <= 0:
            return
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.max_requests, self.tokens + elapsed * self.max_requests)
            self.last_update = now

            if self.tokens < 1:
                sleep_time = (1 - self.tokens) / self.max_requests
                if sleep_time > 0:
                    time.sleep(sleep_time)
                self.tokens = 1

            self.tokens -= 1


_KLINE_RATE_LIMITER = RateLimiter(max_requests_per_second=_float_env("STATBOT_STRATEGY_INTERNAL_KLINE_RPS", 5.0))


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

            _KLINE_RATE_LIMITER.acquire()
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
        _KLINE_RATE_LIMITER.acquire()
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
