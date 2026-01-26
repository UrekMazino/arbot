import math
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import coint

from config_execution_api import depth, market_session, ticker_1, ticker_2, z_score_window
from func_price_calls import get_latest_klines


def _compute_zscore(spread, window):
    series = pd.Series(spread, dtype=float)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        mean = series.rolling(window=window).mean()
        std = series.rolling(window=window).std()
        zscore = (series - mean) / std
    return zscore.astype(float).values


def _fetch_mid_price(inst_id, depth_levels=depth, session=None):
    if not inst_id:
        return None

    active_session = session or market_session
    try:
        level_count = int(depth_levels)
    except (TypeError, ValueError):
        level_count = depth
    if level_count <= 0:
        level_count = depth

    try:
        response = active_session.get_orderbook(instId=inst_id, sz=str(level_count))
    except Exception as exc:
        print(f"ERROR: Failed to fetch orderbook for {inst_id}: {exc}")
        return None

    if response.get("code") != "0":
        print(f"ERROR: OKX orderbook failed for {inst_id}: {response.get('msg')}")
        return None

    data = response.get("data", [])
    book = data[0] if isinstance(data, list) and data else {}
    bids = book.get("bids") or book.get("b") or []
    asks = book.get("asks") or book.get("a") or []

    if not bids or not asks:
        return None

    try:
        best_bid = max(float(level[0]) for level in bids if level)
        best_ask = min(float(level[0]) for level in asks if level)
    except (TypeError, ValueError):
        return None

    if best_bid <= 0 or best_ask <= 0:
        return None

    return (best_bid + best_ask) / 2.0


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
    
    coint_flag: 1 if p_value < 0.05 (cointegrated), 0 otherwise
    """
    inst_1 = inst_id_1 or ticker_1
    inst_2 = inst_id_2 or ticker_2
    if not inst_1 or not inst_2:
        return [], False, 0

    window_val = z_score_window if window is None else window
    try:
        window_val = int(window_val)
    except (TypeError, ValueError):
        window_val = z_score_window
    if window_val <= 1:
        return [], False, 0

    series_1, series_2 = get_latest_klines(
        inst_id_1=inst_1,
        inst_id_2=inst_2,
        bar=bar,
        limit=limit,
        session=session,
        ascending=True,
    )
    if not series_1 or not series_2:
        return [], False, 0

    if use_orderbook:
        mid_1 = _fetch_mid_price(inst_1, depth_levels=depth_levels, session=session)
        mid_2 = _fetch_mid_price(inst_2, depth_levels=depth_levels, session=session)
        if mid_1 is not None and mid_2 is not None:
            series_1 = _replace_last(series_1, mid_1)
            series_2 = _replace_last(series_2, mid_2)

    min_len = min(len(series_1), len(series_2))
    if min_len < 2:
        return [], False, 0

    series_1 = np.array(series_1[-min_len:], dtype=float)
    series_2 = np.array(series_2[-min_len:], dtype=float)
    if not np.all(np.isfinite(series_1)) or not np.all(np.isfinite(series_2)):
        return [], False, 0
    if np.any(series_1 <= 0) or np.any(series_2 <= 0):
        return [], False, 0

    series_1_log = np.log(series_1)
    series_2_log = np.log(series_2)
    if np.std(series_1_log) == 0 or np.std(series_2_log) == 0:
        return [], False, 0

    try:
        series_2_const = sm.add_constant(series_2_log)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            model = sm.OLS(series_1_log, series_2_const).fit()
            
            # Perform cointegration test
            adf_statistic, p_value, critical_values = sm.tsa.stattools.coint(series_1_log, series_2_log)
            coint_flag = 1 if (p_value < 0.05 and adf_statistic < critical_values[1]) else 0
    except (ValueError, np.linalg.LinAlgError) as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"OLS/cointegration calculation failed ({inst_1} vs {inst_2}): {e}")
        return [], False, 0
    except (AttributeError, IndexError, TypeError) as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Cointegration test error ({inst_1} vs {inst_2}): {e}")
        return [], False, 0

    hedge_ratio = float(model.params[1] if len(model.params) > 1 else model.params[0])
    spread = series_1_log - (hedge_ratio * series_2_log)
    zscore_values = _compute_zscore(spread, window_val)
    zscore_list = zscore_values.tolist()
    latest = _latest_finite(zscore_list)
    if latest is None:
        return [], False, 0
    return zscore_list, latest > 0, coint_flag
