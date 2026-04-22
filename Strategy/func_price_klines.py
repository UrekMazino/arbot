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


def _int_env(name, default):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return int(default)
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return int(default)


def _is_disconnect_error(err):
    text = str(err).lower()
    patterns = (
        "server disconnected",
        "connection reset",
        "connection aborted",
        "connection refused",
        "connection error",
        "connectionterminated",
        "remoteprotocolerror",
        "stream reset",
        "timed out",
        "timeout",
    )
    return any(pat in text for pat in patterns)


def _is_rate_limit_error(err):
    text = str(err).lower()
    patterns = (
        "too many requests",
        "rate limit",
        "ratelimit",
        "429",
        "50011",
    )
    return any(pat in text for pat in patterns)


def _is_rate_limit_response(response):
    if not isinstance(response, dict):
        return False
    code = str(response.get("code") or response.get("sCode") or "").strip()
    msg = str(response.get("msg") or response.get("sMsg") or "")
    return code in {"429", "50011"} or _is_rate_limit_error(msg)


class RateLimiter:
    def __init__(self, max_requests_per_second=2.0, max_burst=1.0):
        try:
            self.max_requests = float(max_requests_per_second)
        except (TypeError, ValueError):
            self.max_requests = 0.0
        if self.max_requests < 0:
            self.max_requests = 0.0
        try:
            self.max_burst = float(max_burst)
        except (TypeError, ValueError):
            self.max_burst = 1.0
        if self.max_burst < 1:
            self.max_burst = 1.0
        self.tokens = min(self.max_requests, self.max_burst)
        self.lock = threading.Lock()
        self.last_update = time.time()

    def acquire(self):
        if self.max_requests <= 0:
            return
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.max_burst, self.tokens + elapsed * self.max_requests)
            self.last_update = now

            if self.tokens < 1:
                sleep_time = (1 - self.tokens) / self.max_requests
                if sleep_time > 0:
                    time.sleep(sleep_time)
                self.tokens = 1

            self.tokens -= 1


_KLINE_RATE_LIMITER = RateLimiter(
    max_requests_per_second=_float_env("STATBOT_STRATEGY_INTERNAL_KLINE_RPS", 2.0),
    max_burst=_float_env("STATBOT_STRATEGY_INTERNAL_KLINE_BURST", 1.0),
)
_KLINE_API_RETRIES = max(1, _int_env("STATBOT_STRATEGY_INTERNAL_KLINE_API_RETRIES", 5))
_KLINE_API_RETRY_BASE_DELAY = max(0.0, _float_env("STATBOT_STRATEGY_INTERNAL_KLINE_API_RETRY_BASE_DELAY", 0.5))
_KLINE_API_RETRY_MAX_DELAY = max(_KLINE_API_RETRY_BASE_DELAY, _float_env("STATBOT_STRATEGY_INTERNAL_KLINE_API_RETRY_MAX_DELAY", 4.0))
_KLINE_RATE_LIMIT_RETRIES = max(_KLINE_API_RETRIES, _int_env("STATBOT_STRATEGY_INTERNAL_KLINE_RATE_LIMIT_RETRIES", 8))
_KLINE_RATE_LIMIT_BASE_DELAY = max(0.0, _float_env("STATBOT_STRATEGY_INTERNAL_KLINE_RATE_LIMIT_BASE_DELAY", 2.0))
_KLINE_RATE_LIMIT_MAX_DELAY = max(_KLINE_RATE_LIMIT_BASE_DELAY, _float_env("STATBOT_STRATEGY_INTERNAL_KLINE_RATE_LIMIT_MAX_DELAY", 20.0))
_DISCONNECT_LOG_COOLDOWN = max(1.0, _float_env("STATBOT_STRATEGY_INTERNAL_KLINE_DISCONNECT_LOG_COOLDOWN", 60.0))
_RATE_LIMIT_LOG_COOLDOWN = max(1.0, _float_env("STATBOT_STRATEGY_INTERNAL_KLINE_RATE_LIMIT_LOG_COOLDOWN", 30.0))
_LAST_LOG_TS = {}


def _should_log(key, cooldown_seconds):
    now = time.time()
    last = _LAST_LOG_TS.get(key, 0.0)
    if now - last >= cooldown_seconds:
        _LAST_LOG_TS[key] = now
        return True
    return False


def _log_disconnect_once(logger, key, message):
    if _should_log(key, _DISCONNECT_LOG_COOLDOWN):
        logger.warning("%s (cooldown %.0fs)", message, _DISCONNECT_LOG_COOLDOWN)


def _call_with_retries(func, *, logger, request_label, log_key):
    delay = _KLINE_API_RETRY_BASE_DELAY
    rate_limit_delay = _KLINE_RATE_LIMIT_BASE_DELAY
    last_exc = None

    max_attempts = max(_KLINE_API_RETRIES, _KLINE_RATE_LIMIT_RETRIES)
    for attempt in range(1, max_attempts + 1):
        try:
            response = func()
            if _is_rate_limit_response(response):
                if attempt >= _KLINE_RATE_LIMIT_RETRIES:
                    return response
                if _should_log(f"{log_key}:rate_limit", _RATE_LIMIT_LOG_COOLDOWN):
                    logger.warning(
                        "OKX candlestick rate limit during %s; backing off %.1fs (attempt %d/%d)",
                        request_label,
                        rate_limit_delay,
                        attempt,
                        _KLINE_RATE_LIMIT_RETRIES,
                    )
                if rate_limit_delay > 0:
                    time.sleep(rate_limit_delay)
                rate_limit_delay = min(
                    _KLINE_RATE_LIMIT_MAX_DELAY,
                    max(_KLINE_RATE_LIMIT_BASE_DELAY, rate_limit_delay * 2 if rate_limit_delay > 0 else 0),
                )
                continue
            return response
        except Exception as exc:
            last_exc = exc
            if not _is_disconnect_error(exc):
                raise
            if attempt >= _KLINE_API_RETRIES:
                break
            _log_disconnect_once(
                logger,
                log_key,
                f"Transient OKX candlestick disconnect during {request_label}; retrying",
            )
            if delay > 0:
                time.sleep(delay)
            delay = min(_KLINE_API_RETRY_MAX_DELAY, max(_KLINE_API_RETRY_BASE_DELAY, delay * 2 if delay > 0 else 0))

    if last_exc:
        raise last_exc
    return None


def _fetch_candlesticks(params, *, inst_id, logger, context):
    request_label = f"{context}:{inst_id}"
    try:
        return _call_with_retries(
            lambda: (_KLINE_RATE_LIMITER.acquire(), market_session.get_candlesticks(**params))[1],
            logger=logger,
            request_label=request_label,
            log_key=f"{context}:retry",
        )
    except Exception as exc:
        if _is_disconnect_error(exc):
            _log_disconnect_once(
                logger,
                f"{context}:disconnect",
                f"OKX candlestick fetch exhausted retries for {inst_id}; returning no data",
            )
            return {"code": "1", "msg": str(exc), "data": []}
        raise


def _fetch_history_candlesticks(params, *, inst_id, logger, context):
    request_label = f"{context}:{inst_id}"
    try:
        return _call_with_retries(
            lambda: (_KLINE_RATE_LIMITER.acquire(), market_session.get_history_candlesticks(**params))[1],
            logger=logger,
            request_label=request_label,
            log_key=f"{context}:retry",
        )
    except Exception as exc:
        if _is_disconnect_error(exc):
            _log_disconnect_once(
                logger,
                f"{context}:disconnect",
                f"OKX historical candlestick fetch exhausted retries for {inst_id}; returning no data",
            )
            return {"code": "1", "msg": str(exc), "data": []}
        raise


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
    use_history_endpoint = False

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

            if use_history_endpoint:
                prices = _fetch_history_candlesticks(
                    params,
                    inst_id=inst_id,
                    logger=logger,
                    context="history_archive",
                )
            else:
                prices = _fetch_candlesticks(params, inst_id=inst_id, logger=logger, context="history")

            if prices.get('code') != '0':
                msg = prices.get('msg', 'Unknown error')
                if _is_rate_limit_response(prices) and collected:
                    if _should_log("history:rate_limit_partial", _RATE_LIMIT_LOG_COOLDOWN):
                        logger.warning(
                            "Klines rate limited for %s after %d candles; keeping partial history for this scan",
                            inst_id,
                            len(collected),
                        )
                    break
                if not _is_disconnect_error(msg):
                    logger.warning("Klines error for %s: %s", inst_id, msg)
                if collected and use_history_endpoint:
                    break
                return prices

            data = prices.get('data') or []
            if not data:
                if not use_history_endpoint and collected:
                    use_history_endpoint = True
                    logger.info(
                        "Recent klines exhausted for %s after %d candles; continuing with historical endpoint",
                        inst_id,
                        len(collected),
                    )
                    continue
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
                if not use_history_endpoint and collected:
                    use_history_endpoint = True
                    logger.info(
                        "Recent klines duplicated for %s after %d candles; continuing with historical endpoint",
                        inst_id,
                        len(collected),
                    )
                    continue
                break

            oldest_ts = data[-1][0]
            if last_oldest == oldest_ts:
                if not use_history_endpoint and collected:
                    use_history_endpoint = True
                    logger.info(
                        "Recent klines stalled for %s after %d candles; continuing with historical endpoint",
                        inst_id,
                        len(collected),
                    )
                    continue
                break
            last_oldest = oldest_ts
            after = oldest_ts

            if len(data) < batch_limit:
                if not use_history_endpoint and collected:
                    use_history_endpoint = True
                    logger.info(
                        "Recent klines short page for %s after %d candles; continuing with historical endpoint",
                        inst_id,
                        len(collected),
                    )
                    continue
                break

            time.sleep(0.05)

        if collected:
            return {'code': '0', 'msg': '', 'data': collected[:target]}

        logger.warning("Klines error for %s: no data returned", inst_id)
        return {'code': '1', 'msg': 'Insufficient data', 'data': []}

    except Exception as e:
        if _is_disconnect_error(e):
            logger.warning("Klines fetch failed for %s after retries: %s", inst_id, e)
        else:
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
        prices = _fetch_candlesticks(
            {
                "instId": inst_id,
                "bar": time_frame,
                "limit": str(limit),
            },
            inst_id=inst_id,
            logger=logger,
            context="latest",
        )
        if prices.get("code") != "0":
            msg = prices.get("msg")
            if not _is_disconnect_error(msg):
                logger.warning("Latest klines error for %s: %s", inst_id, msg)
        return prices
    except Exception as exc:
        if _is_disconnect_error(exc):
            logger.warning("Latest klines fetch failed for %s after retries: %s", inst_id, exc)
        else:
            logger.exception("Latest klines exception for %s: %s", inst_id, exc)
        return {"code": "1", "msg": str(exc), "data": []}
