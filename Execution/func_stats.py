import sys
from pathlib import Path

from config_execution_api import COINT_ZERO_CROSS_THRESHOLD_RATIO, P_VALUE_CRITICAL, z_score_window

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared_cointegration_validator import calculate_zscore_series, evaluate_cointegration


def calculate_zscore(spread):
    return calculate_zscore_series(spread, window=z_score_window)


def calculate_spread(series_1_log, series_2_log, hedge_ratio):
    return series_1_log - (hedge_ratio * series_2_log)


def calculate_metrics(series_1, series_2):
    """
    Returns:
        tuple: (coint_flag, zscore_list)
    """
    metrics = evaluate_cointegration(
        series_1,
        series_2,
        window=z_score_window,
        pvalue_threshold=P_VALUE_CRITICAL,
        zero_cross_threshold_ratio=COINT_ZERO_CROSS_THRESHOLD_RATIO,
        already_logged=False,
    )
    zscores = metrics.get("zscore_values")
    if hasattr(zscores, "tolist"):
        zscores = zscores.tolist()
    return int(metrics.get("coint_flag", 0) or 0), list(zscores or [])
