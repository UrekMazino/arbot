import math
import os
import threading
import time
import sys
from pathlib import Path

import numpy as np

from config_execution_api import (
    COINT_ZERO_CROSS_THRESHOLD_RATIO,
    P_VALUE_CRITICAL,
    depth,
    market_session,
    ticker_1,
    ticker_2,
    z_score_window,
)
from func_price_calls import get_latest_klines
from func_log_setup import get_logger

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared_cointegration_validator import calculate_zscore_series, evaluate_cointegration
from cointegration_health import classify_cointegration_health

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


def _env_int(name, default, minimum=None):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        value = int(default)
    else:
        try:
            value = int(float(raw))
        except (TypeError, ValueError):
            value = int(default)
    if minimum is not None and value < minimum:
        value = int(minimum)
    return value


def _env_flag(name, default=False):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return bool(default)
    value = str(raw).strip().lower()
    if value in ("1", "true", "yes", "y", "on"):
        return True
    if value in ("0", "false", "no", "n", "off"):
        return False
    return bool(default)


_ORDERBOOK_BACKOFF_UNTIL = {}
_ORDERBOOK_BACKOFF_SECONDS = _env_float("STATBOT_ORDERBOOK_BACKOFF_SECONDS", 45.0)
_ORDERBOOK_BACKOFF_RETRIES = int(_env_float("STATBOT_ORDERBOOK_BACKOFF_RETRIES", 2))
_ORDERBOOK_BACKOFF_RETRY_SLEEP = _env_float("STATBOT_ORDERBOOK_BACKOFF_RETRY_SLEEP", 0.25)


def _get_live_coint_limit():
    default_limit = _env_int("STATBOT_SWITCH_PRECHECK_LIMIT", 300, minimum=60)
    return _env_int("STATBOT_LIVE_COINT_LIMIT", default_limit, minimum=60)


def _get_live_coint_window():
    default_window = _env_int("STATBOT_SWITCH_PRECHECK_WINDOW", 60, minimum=20)
    return _env_int("STATBOT_LIVE_COINT_WINDOW", default_window, minimum=20)


def _use_stable_coint_metrics():
    return _env_flag("STATBOT_LIVE_COINT_USE_KLINE_ONLY", True)


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
    return calculate_zscore_series(spread, window=window)


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


def _safe_float(value, default=0.0):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not math.isfinite(parsed):
        return float(default)
    return parsed


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _prepare_series_pair(series_1, series_2, sample_limit=None):
    min_len = min(len(series_1 or []), len(series_2 or []))
    if sample_limit is not None:
        try:
            sample_len = min(min_len, int(sample_limit))
        except (TypeError, ValueError):
            sample_len = min_len
    else:
        sample_len = min_len

    if sample_len < 2:
        return None, None

    arr_1 = np.array(list(series_1)[-sample_len:], dtype=float)
    arr_2 = np.array(list(series_2)[-sample_len:], dtype=float)
    if not np.all(np.isfinite(arr_1)) or not np.all(np.isfinite(arr_2)):
        return None, None
    if np.any(arr_1 <= 0) or np.any(arr_2 <= 0):
        return None, None
    return arr_1, arr_2


def _normalize_coint_metrics(coint_metrics):
    coint_metrics = coint_metrics or {}
    return {
        "coint_flag": _safe_int(coint_metrics.get("coint_flag", 0), 0),
        "p_value": _safe_float(coint_metrics.get("p_value", 1.0), 1.0),
        "adf_stat": _safe_float(coint_metrics.get("adf_stat", 0.0), 0.0),
        "critical_value": _safe_float(coint_metrics.get("critical_value", 0.0), 0.0),
        "zero_crossings": _safe_int(coint_metrics.get("zero_crossings", 0), 0),
        "spread_trend": _safe_float(coint_metrics.get("spread_trend", 0.0), 0.0),
        "correlation": _safe_float(coint_metrics.get("correlation", 0.0), 0.0),
        "returns_correlation": _safe_float(coint_metrics.get("returns_correlation", 0.0), 0.0),
        "hedge_ratio": _safe_float(coint_metrics.get("hedge_ratio", 0.0), 0.0),
    }


def _classify_metrics(coint_metrics):
    normalized = _normalize_coint_metrics(coint_metrics)
    coint_health = classify_cointegration_health(normalized, strict_pvalue=P_VALUE_CRITICAL)
    normalized.update(
        {
            "coint_health": coint_health["state"],
            "coint_health_reason": coint_health["reason"],
            "coint_watch": bool(coint_health["is_watch"]),
            "coint_broken": bool(coint_health["is_broken"]),
            "coint_adf_gap": float(coint_health["adf_gap"]),
            "coint_adf_margin": float(coint_health["adf_margin"]),
            "coint_watch_p_value": float(coint_health["watch_pvalue"]),
            "coint_fail_p_value": float(coint_health["fail_pvalue"]),
        }
    )
    return normalized


def _entry_coint_diagnostics(metrics):
    return {
        "entry_coint_flag": int(metrics.get("coint_flag", 0) or 0),
        "entry_p_value": float(metrics.get("p_value", 1.0) or 1.0),
        "entry_adf_gap": float(metrics.get("coint_adf_gap", 0.0) or 0.0),
        "entry_coint_health": str(metrics.get("coint_health") or ""),
        "entry_coint_health_reason": str(metrics.get("coint_health_reason") or ""),
    }


def _evaluate_cointegration_safe(series_1, series_2, window_val, inst_1, inst_2, basis_label):
    try:
        return evaluate_cointegration(
            series_1,
            series_2,
            window=window_val,
            pvalue_threshold=P_VALUE_CRITICAL,
            zero_cross_threshold_ratio=COINT_ZERO_CROSS_THRESHOLD_RATIO,
            already_logged=False,
        )
    except Exception as e:
        logger.warning(
            "Cointegration evaluation failed (%s vs %s, basis=%s): %s",
            inst_1,
            inst_2,
            basis_label,
            e,
        )
        return None


def _get_latest_zscore_legacy(
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

    try:
        coint_metrics = evaluate_cointegration(
            series_1,
            series_2,
            window=window_val,
            pvalue_threshold=P_VALUE_CRITICAL,
            zero_cross_threshold_ratio=COINT_ZERO_CROSS_THRESHOLD_RATIO,
            already_logged=False,
        )
    except Exception as e:
        logger.warning(f"Cointegration evaluation failed ({inst_1} vs {inst_2}): {e}")
        return [], False, metrics

    metrics.update(
        {
            "coint_flag": int(coint_metrics.get("coint_flag", 0) or 0),
            "p_value": float(coint_metrics.get("p_value", 1.0) or 1.0),
            "adf_stat": float(coint_metrics.get("adf_stat", 0.0) or 0.0),
            "critical_value": float(coint_metrics.get("critical_value", 0.0) or 0.0),
            "zero_crossings": int(coint_metrics.get("zero_crossings", 0) or 0),
            "spread_trend": float(coint_metrics.get("spread_trend", 0.0) or 0.0),
            "correlation": float(coint_metrics.get("correlation", 0.0) or 0.0),
            "returns_correlation": float(coint_metrics.get("returns_correlation", 0.0) or 0.0),
            "hedge_ratio": float(coint_metrics.get("hedge_ratio", 0.0) or 0.0),
        }
    )
    coint_health = classify_cointegration_health(metrics, strict_pvalue=P_VALUE_CRITICAL)
    metrics.update(
        {
            "coint_health": coint_health["state"],
            "coint_health_reason": coint_health["reason"],
            "coint_watch": bool(coint_health["is_watch"]),
            "coint_broken": bool(coint_health["is_broken"]),
            "coint_adf_gap": float(coint_health["adf_gap"]),
            "coint_adf_margin": float(coint_health["adf_margin"]),
            "coint_watch_p_value": float(coint_health["watch_pvalue"]),
            "coint_fail_p_value": float(coint_health["fail_pvalue"]),
        }
    )

    zscore_values = coint_metrics.get("zscore_values")
    if isinstance(zscore_values, np.ndarray):
        zscore_list = zscore_values.tolist()
    else:
        zscore_list = list(zscore_values or [])

    latest = coint_metrics.get("latest_zscore")
    if latest is None:
        latest = _latest_finite(zscore_list)
    if latest is None:
        return [], False, metrics
    return zscore_list, latest > 0, metrics


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
    Return entry z-scores plus live cointegration diagnostics.

    Entry z-score and latest prices can use orderbook mids. Live cointegration
    health defaults to a separate kline-only pass so the entry feed cannot
    briefly invalidate an otherwise healthy Pair Doctor / switch-precheck pair.
    """
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
        "orderbook_dead": False,
        "entry_basis": "kline",
        "entry_window": 0,
        "entry_sample_size": 0,
        "coint_basis": "kline_only",
        "coint_window": 0,
        "coint_config_limit": 0,
        "coint_sample_size": 0,
    }

    inst_1 = inst_id_1 or ticker_1
    inst_2 = inst_id_2 or ticker_2
    if not inst_1 or not inst_2:
        return [], False, metrics

    window_val = z_score_window if window is None else window
    try:
        window_val = int(window_val)
    except (TypeError, ValueError):
        window_val = z_score_window
    if window_val <= 1:
        return [], False, metrics

    logger.debug("get_latest_zscore: fetching klines for %s and %s", inst_1, inst_2)
    base_series_1, base_series_2 = get_latest_klines(
        inst_id_1=inst_1,
        inst_id_2=inst_2,
        bar=bar,
        limit=limit,
        session=session,
        ascending=True,
    )
    if not base_series_1 or not base_series_2:
        logger.warning("get_latest_zscore: failed to fetch klines")
        return [], False, metrics

    entry_series_1 = list(base_series_1)
    entry_series_2 = list(base_series_2)
    entry_basis = "kline"
    if use_orderbook:
        logger.debug("get_latest_zscore: fetching mid prices for %s and %s", inst_1, inst_2)
        mid_1 = _fetch_mid_price(inst_1, depth_levels=depth_levels, session=session)
        mid_2 = _fetch_mid_price(inst_2, depth_levels=depth_levels, session=session)
        if mid_1 is not None and mid_2 is not None:
            entry_series_1 = _replace_last(entry_series_1, mid_1)
            entry_series_2 = _replace_last(entry_series_2, mid_2)
            entry_basis = "orderbook_mid"
            from func_pair_state import reset_price_fetch_failures
            reset_price_fetch_failures()
        else:
            entry_basis = "kline_last_close"
            if _backoff_active(inst_1) or _backoff_active(inst_2):
                logger.info("get_latest_zscore: orderbook backoff active, using last kline prices")
            else:
                logger.warning("get_latest_zscore: failed to fetch mid prices")
                from func_pair_state import increment_price_fetch_failures
                failures = increment_price_fetch_failures()
                if failures >= 5:
                    logger.error("Price fetch failed %d times - tickers may be delisted/illiquid", failures)
                    metrics["orderbook_dead"] = True

    entry_arr_1, entry_arr_2 = _prepare_series_pair(entry_series_1, entry_series_2)
    if entry_arr_1 is None or entry_arr_2 is None:
        return [], False, metrics

    metrics["price_1"] = float(entry_arr_1[-1])
    metrics["price_2"] = float(entry_arr_2[-1])
    metrics["entry_basis"] = entry_basis
    metrics["entry_window"] = int(window_val)
    metrics["entry_sample_size"] = int(len(entry_arr_1))

    entry_coint_metrics = _evaluate_cointegration_safe(
        entry_arr_1,
        entry_arr_2,
        window_val,
        inst_1,
        inst_2,
        entry_basis,
    )
    if entry_coint_metrics is None:
        return [], False, metrics

    entry_classified = _classify_metrics(entry_coint_metrics)
    metrics.update(entry_classified)
    metrics.update(_entry_coint_diagnostics(entry_classified))
    metrics.update(
        {
            "coint_basis": "kline_only" if entry_basis == "kline" else entry_basis,
            "coint_window": int(window_val),
            "coint_config_limit": _safe_int(limit, len(entry_arr_1)) or int(len(entry_arr_1)),
            "coint_sample_size": int(len(entry_arr_1)),
        }
    )

    if use_orderbook and _use_stable_coint_metrics():
        stable_limit = _get_live_coint_limit()
        stable_window = _get_live_coint_window()
        stable_series_1 = base_series_1
        stable_series_2 = base_series_2
        base_sample_size = min(len(base_series_1 or []), len(base_series_2 or []))
        if base_sample_size < stable_limit:
            fetched_1, fetched_2 = get_latest_klines(
                inst_id_1=inst_1,
                inst_id_2=inst_2,
                bar=bar,
                limit=stable_limit,
                session=session,
                ascending=True,
            )
            if fetched_1 and fetched_2:
                stable_series_1 = fetched_1
                stable_series_2 = fetched_2
            else:
                logger.warning(
                    "get_latest_zscore: stable kline-only cointegration fetch failed; using existing kline sample"
                )

        stable_arr_1, stable_arr_2 = _prepare_series_pair(
            stable_series_1,
            stable_series_2,
            sample_limit=stable_limit,
        )
        if stable_arr_1 is not None and stable_arr_2 is not None:
            stable_coint_metrics = _evaluate_cointegration_safe(
                stable_arr_1,
                stable_arr_2,
                stable_window,
                inst_1,
                inst_2,
                "kline_only",
            )
            if stable_coint_metrics is not None:
                metrics.update(_classify_metrics(stable_coint_metrics))
                metrics.update(
                    {
                        "coint_basis": "kline_only",
                        "coint_window": int(stable_window),
                        "coint_config_limit": int(stable_limit),
                        "coint_sample_size": int(len(stable_arr_1)),
                    }
                )
        else:
            logger.warning("get_latest_zscore: stable kline-only cointegration sample is invalid")

    zscore_values = entry_coint_metrics.get("zscore_values")
    if isinstance(zscore_values, np.ndarray):
        zscore_list = zscore_values.tolist()
    else:
        zscore_list = list(zscore_values or [])

    latest = entry_coint_metrics.get("latest_zscore")
    if latest is None:
        latest = _latest_finite(zscore_list)
    if latest is None:
        return [], False, metrics
    metrics["latest_zscore"] = float(latest)
    return zscore_list, latest > 0, metrics
