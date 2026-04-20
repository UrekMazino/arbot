import math
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import coint

try:
    from statsmodels.tools.sm_exceptions import CollinearityWarning
except Exception:  # pragma: no cover - fallback for older statsmodels versions
    CollinearityWarning = Warning


def _safe_corrcoef(series_a, series_b):
    if len(series_a) < 2 or len(series_b) < 2:
        return 0.0
    try:
        corr = float(np.corrcoef(series_a, series_b)[0, 1])
    except Exception:
        return 0.0
    if not math.isfinite(corr):
        return 0.0
    return corr


def latest_finite(values):
    for value in reversed(values):
        if isinstance(value, (int, float)) and math.isfinite(value):
            return float(value)
    return None


def calculate_zscore_series(spread, window):
    window_val = int(window)
    if window_val <= 1:
        return np.array([], dtype=float)
    series = pd.Series(spread, dtype=float)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        mean = series.rolling(window=window_val).mean()
        std = series.rolling(window=window_val).std()
        zscore = (series - mean) / std
    return zscore.astype(float).values


def count_spread_zero_crossings(spread, threshold=None, threshold_ratio=0.1):
    spread_series = pd.Series(spread, dtype=float).dropna()
    if len(spread_series) < 2:
        return 0

    if threshold is None:
        try:
            threshold = abs(float(threshold_ratio)) * float(spread_series.std())
        except (TypeError, ValueError):
            threshold = 0.0

    prev = spread_series.shift(1)
    crossings = (
        ((prev > threshold) & (spread_series < -threshold))
        | ((prev < -threshold) & (spread_series > threshold))
    )
    return int(crossings.sum())


def evaluate_cointegration(
    series_1,
    series_2,
    *,
    window,
    pvalue_threshold=0.05,
    zero_cross_threshold_ratio=0.1,
    already_logged=False,
):
    metrics = {
        "coint_flag": 0,
        "p_value": 1.0,
        "adf_stat": 0.0,
        "critical_value": 0.0,
        "zero_crossings": 0,
        "hedge_ratio": 0.0,
        "spread_trend": 0.0,
        "correlation": 0.0,
        "returns_correlation": 0.0,
        "latest_zscore": None,
        "zscore_values": np.array([], dtype=float),
    }

    try:
        arr_1 = np.array(series_1, dtype=float)
        arr_2 = np.array(series_2, dtype=float)
    except (TypeError, ValueError):
        return metrics

    min_len = min(len(arr_1), len(arr_2))
    if min_len < 2:
        return metrics

    if len(arr_1) != len(arr_2):
        arr_1 = arr_1[-min_len:]
        arr_2 = arr_2[-min_len:]

    if not np.all(np.isfinite(arr_1)) or not np.all(np.isfinite(arr_2)):
        return metrics

    if already_logged:
        series_1_log = arr_1
        series_2_log = arr_2
    else:
        if np.any(arr_1 <= 0) or np.any(arr_2 <= 0):
            return metrics
        series_1_log = np.log(arr_1)
        series_2_log = np.log(arr_2)

    if np.std(series_1_log) == 0 or np.std(series_2_log) == 0:
        return metrics

    try:
        series_2_const = sm.add_constant(series_2_log)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            warnings.filterwarnings("ignore", category=CollinearityWarning)
            model = sm.OLS(series_1_log, series_2_const).fit()
            adf_statistic, p_value, critical_values = coint(series_1_log, series_2_log)
    except (ValueError, np.linalg.LinAlgError, AttributeError, IndexError, TypeError):
        return metrics

    hedge_ratio = float(model.params[1] if len(model.params) > 1 else model.params[0])
    spread = series_1_log - (hedge_ratio * series_2_log)
    zscore_values = calculate_zscore_series(spread, window=window)
    zero_crossings = count_spread_zero_crossings(spread, threshold_ratio=zero_cross_threshold_ratio)
    critical_value = float(critical_values[1]) if len(critical_values) > 1 else float(critical_values[0])
    coint_flag = int(
        bool(
            math.isfinite(float(p_value))
            and float(p_value) < float(pvalue_threshold)
            and float(adf_statistic) < critical_value
        )
    )

    try:
        x = np.arange(len(spread), dtype=float)
        spread_trend = float(np.polyfit(x, spread, 1)[0])
    except Exception:
        spread_trend = 0.0

    returns_1 = np.diff(series_1_log)
    returns_2 = np.diff(series_2_log)

    metrics.update(
        {
            "coint_flag": coint_flag,
            "p_value": float(p_value),
            "adf_stat": float(adf_statistic),
            "critical_value": critical_value,
            "zero_crossings": zero_crossings,
            "hedge_ratio": hedge_ratio,
            "spread_trend": spread_trend,
            "correlation": _safe_corrcoef(series_1_log, series_2_log),
            "returns_correlation": _safe_corrcoef(returns_1, returns_2),
            "latest_zscore": latest_finite(zscore_values.tolist()),
            "zscore_values": zscore_values,
        }
    )
    return metrics
