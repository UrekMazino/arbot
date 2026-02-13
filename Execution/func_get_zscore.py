import math
import os
import warnings
import threading
import time
import logging

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import coint

from config_execution_api import depth, market_session, ticker_1, ticker_2, z_score_window, P_VALUE_CRITICAL
from func_price_calls import get_latest_klines
from func_log_setup import get_logger

# Setup logging
logger = get_logger("func_get_zscore")


def _env_float(name, default):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


_ORDERBOOK_BACKOFF_UNTIL = {}
_ORDERBOOK_BACKOFF_SECONDS = _env_float("STATBOT_ORDERBOOK_BACKOFF_SECONDS", 45.0)
_ORDERBOOK_BACKOFF_RETRIES = int(_env_float("STATBOT_ORDERBOOK_BACKOFF_RETRIES", 2))
_ORDERBOOK_BACKOFF_RETRY_SLEEP = _env_float("STATBOT_ORDERBOOK_BACKOFF_RETRY_SLEEP", 0.25)


def _backoff_active(inst_id):
    if not inst_id:
        return False
    until = _ORDERBOOK_BACKOFF_UNTIL.get(inst_id, 0)
    return until > time.time()


def _set_backoff(inst_id, seconds, reason):
    if not inst_id or seconds <= 0:
        return
    until = time.time() + seconds
    current = _ORDERBOOK_BACKOFF_UNTIL.get(inst_id, 0)
    if until > current:
        _ORDERBOOK_BACKOFF_UNTIL[inst_id] = until
        logger.warning(
            "Orderbook backoff for %s: %s (%.0fs)",
            inst_id,
            reason,
            seconds,
        )


def _compute_zscore(spread, window):
    series = pd.Series(spread, dtype=float)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        mean = series.rolling(window=window).mean()
        std = series.rolling(window=window).std()
        zscore = (series - mean) / std
    return zscore.astype(float).values


# Issue #14 Fix: API timeout protection
def _get_orderbook_with_timeout(session, inst_id, level_count, timeout=5):
    """
    Fetch orderbook with timeout protection to prevent indefinite hangs.
    
    Args:
        session: OKX market session
        inst_id: Instrument ID
        level_count: Number of orderbook levels
        timeout: Timeout in seconds (default 5)
    
    Returns:
        dict: Orderbook response or None if timeout/error
    """
    result = [None]  # Use list to store result from thread
    
    def fetch():
        try:
            result[0] = session.get_orderbook(instId=inst_id, sz=str(level_count))
        except Exception as e:
            result[0] = None
    
    thread = threading.Thread(target=fetch, daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    
    if thread.is_alive():
        # Timeout occurred
        return None
    
    return result[0]


def _fetch_mid_price(inst_id, depth_levels=depth, session=None):
    if not inst_id:
        logger.error(f"_fetch_mid_price called with empty inst_id")
        return None
    if _backoff_active(inst_id):
        return None

    active_session = session or market_session
    try:
        level_count = int(depth_levels)
    except (TypeError, ValueError):
        level_count = depth
    if level_count <= 0:
        level_count = depth

    # Issue #14 Fix: Use timeout-protected API call (5 second timeout)
    logger.debug(f"Fetching orderbook for {inst_id} (depth={level_count})")
    response = None
    attempts = max(_ORDERBOOK_BACKOFF_RETRIES, 0)
    while True:
        response = _get_orderbook_with_timeout(active_session, inst_id, level_count, timeout=5)
        if response is None:
            break
        response_code = response.get("code")
        if response_code != "50026" or attempts <= 0:
            break
        sleep_seconds = max(_ORDERBOOK_BACKOFF_RETRY_SLEEP * attempts, 0)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        attempts -= 1
    
    if response is None:
        logger.error(f"❌ Orderbook fetch failed for {inst_id}: timeout or connection error")
        return None

    response_code = response.get("code")
    if response_code != "0":
        error_msg = response.get("msg", "unknown error")
        logger.error(f"❌ OKX API error for {inst_id}: code={response_code}, msg={error_msg}")
        
        # Specific error handling
        if "Instrument ID does not exist" in error_msg or response_code == "51001":
            logger.error(f"🚨 TICKER DELISTED OR INVALID: {inst_id}")
        elif response_code == "50026":
            _set_backoff(inst_id, _ORDERBOOK_BACKOFF_SECONDS, "system error 50026")
        elif "rate limit" in error_msg.lower():
            logger.error(f"⚠️ Rate limit exceeded for {inst_id}")
        
        return None

    data = response.get("data", [])
    if not data:
        logger.error(f"❌ Empty orderbook data for {inst_id}")
        return None
        
    book = data[0] if isinstance(data, list) and data else {}
    bids = book.get("bids") or book.get("b") or []
    asks = book.get("asks") or book.get("a") or []

    if not bids or not asks:
        logger.error(f"❌ No bids/asks in orderbook for {inst_id}: bids={len(bids)}, asks={len(asks)}")
        return None

    try:
        best_bid = max(float(level[0]) for level in bids if level)
        best_ask = min(float(level[0]) for level in asks if level)
    except (TypeError, ValueError) as e:
        logger.error(f"❌ Invalid bid/ask format for {inst_id}: {e}")
        return None

    if best_bid <= 0 or best_ask <= 0:
        logger.error(f"❌ Invalid prices for {inst_id}: bid={best_bid}, ask={best_ask}")
        return None

    mid_price = (best_bid + best_ask) / 2.0
    logger.debug(f"✅ Mid price for {inst_id}: {mid_price:.6f}")
    return mid_price


def _latest_finite(values):
    for value in reversed(values):
        if isinstance(value, (int, float)) and math.isfinite(value):
            return float(value)
    return None


def _replace_last(values, new_value):
    if not values:
        return []

    if new_value is None or not isinstance(new_value, (int, float)):
        return list(values)

    if not math.isfinite(new_value) or new_value <= 0:
        return list(values)

    updated = list(values)
    updated[-1] = float(new_value)
    return updated


def get_latest_zscore(
    inst_id_1=None,
    inst_id_2=None,
    bar=None,
    limit=None,
    window=None,
    use_orderbook=True,
    depth_levels=depth,
    session=None,
):
    """
    Return (zscore_list, signal_sign_positive, coint_flag) for the configured instrument pair.
    
    coint_flag: 1 if p_value < P_VALUE_CRITICAL (cointegrated), 0 otherwise
    """
    import logging
    logger = logging.getLogger(__name__)

    metrics = {
        "coint_flag": 0,
        "p_value": 1.0,
        "adf_stat": 0.0,
        "critical_value": 0.0,
        "zero_crossings": 0,
        "spread_trend": 0.0,
        "correlation": 0.0,
        "price_1": 0.0,
        "price_2": 0.0,
        "orderbook_dead": False
    }
    
    inst_1 = inst_id_1 or ticker_1
    inst_2 = inst_id_2 or ticker_2
    if not inst_1 or not inst_2:
        return [], False, metrics

    logger.debug(f"get_latest_zscore: fetching klines for {inst_1} and {inst_2}")
    window_val = z_score_window if window is None else window
    try:
        window_val = int(window_val)
    except (TypeError, ValueError):
        window_val = z_score_window
    if window_val <= 1:
        return [], False, metrics

    series_1, series_2 = get_latest_klines(
        inst_id_1=inst_1,
        inst_id_2=inst_2,
        bar=bar,
        limit=limit,
        session=session,
        ascending=True,
    )
    if not series_1 or not series_2:
        logger.warning("get_latest_zscore: failed to fetch klines")
        return [], False, metrics

    if use_orderbook:
        logger.debug(f"get_latest_zscore: fetching mid prices for {inst_1} and {inst_2}")
        mid_1 = _fetch_mid_price(inst_1, depth_levels=depth_levels, session=session)
        mid_2 = _fetch_mid_price(inst_2, depth_levels=depth_levels, session=session)
        if mid_1 is not None and mid_2 is not None:
            series_1 = _replace_last(series_1, mid_1)
            series_2 = _replace_last(series_2, mid_2)
            # Reset failure counter on success
            from func_pair_state import reset_price_fetch_failures
            reset_price_fetch_failures()
        else:
            backoff_active = _backoff_active(inst_1) or _backoff_active(inst_2)
            if backoff_active:
                logger.info("get_latest_zscore: orderbook backoff active, using last kline prices")
            else:
                logger.warning("get_latest_zscore: failed to fetch mid prices")
                # Track consecutive failures - indicates delisted/illiquid tickers
                from func_pair_state import increment_price_fetch_failures
                failures = increment_price_fetch_failures()
                if failures >= 5:
                    logger.error(f"⚠️ Price fetch failed {failures} times - tickers may be delisted/illiquid")
                    metrics["orderbook_dead"] = True

    min_len = min(len(series_1), len(series_2))
    if min_len < 2:
        return [], False, metrics

    # Save latest prices used for calculation
    metrics["price_1"] = series_1[-1]
    metrics["price_2"] = series_2[-1]

    series_1 = np.array(series_1[-min_len:], dtype=float)
    series_2 = np.array(series_2[-min_len:], dtype=float)
    if not np.all(np.isfinite(series_1)) or not np.all(np.isfinite(series_2)):
        return [], False, metrics
    if np.any(series_1 <= 0) or np.any(series_2 <= 0):
        return [], False, metrics

    series_1_log = np.log(series_1)
    series_2_log = np.log(series_2)
    if np.std(series_1_log) == 0 or np.std(series_2_log) == 0:
        return [], False, metrics

    coint_flag = 0

    try:
        series_2_const = sm.add_constant(series_2_log)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            from statsmodels.tools.sm_exceptions import CollinearityWarning
            warnings.filterwarnings("ignore", category=CollinearityWarning)
            model = sm.OLS(series_1_log, series_2_const).fit()

            # Perform cointegration test
            adf_statistic, p_value, critical_values = sm.tsa.stattools.coint(series_1_log, series_2_log)
            coint_flag = 1 if (p_value < P_VALUE_CRITICAL and adf_statistic < critical_values[1]) else 0
            
            # Calculate correlation
            correlation = np.corrcoef(series_1_log, series_2_log)[0, 1]
            
            metrics.update({
                "coint_flag": coint_flag,
                "p_value": float(p_value),
                "adf_stat": float(adf_statistic),
                "critical_value": float(critical_values[1]),
                "correlation": float(correlation)
            })
    except (ValueError, np.linalg.LinAlgError) as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"OLS/cointegration calculation failed ({inst_1} vs {inst_2}): {e}")
        return [], False, metrics
    except (AttributeError, IndexError, TypeError) as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Cointegration test error ({inst_1} vs {inst_2}): {e}")
        return [], False, metrics

    hedge_ratio = float(model.params[1] if len(model.params) > 1 else model.params[0])
    spread = series_1_log - (hedge_ratio * series_2_log)
    
    # Calculate spread trend
    try:
        x = np.arange(len(spread))
        coeffs = np.polyfit(x, spread, 1)
        metrics["spread_trend"] = float(coeffs[0])
    except Exception:
        metrics["spread_trend"] = 0.0

    zscore_values = _compute_zscore(spread, window_val)
    zscore_list = zscore_values.tolist()
    
    # Calculate zero crossings
    try:
        z_series = pd.Series(zscore_list).dropna()
        metrics["zero_crossings"] = int(((z_series.shift(1) * z_series) < 0).sum())
    except Exception:
        metrics["zero_crossings"] = 0

    latest = _latest_finite(zscore_list)
    if latest is None:
        return [], False, metrics
    return zscore_list, latest > 0, metrics
