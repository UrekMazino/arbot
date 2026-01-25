from config_execution_api import z_score_window
from statsmodels.tsa.stattools import coint
import statsmodels.api as sm
import pandas as pd
import numpy as np
import warnings


# Calculate Z-score
def calculate_zscore(spread):
    series = pd.Series(spread, dtype=float)
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=RuntimeWarning)
        mean = series.rolling(window=z_score_window).mean()
        std = series.rolling(window=z_score_window).std()
        zscore = (series - mean) / std
    return zscore.astype(float).values


# Calculate spread (input should already be logged)
def calculate_spread(series_1_log, series_2_log, hedge_ratio):
    spread = series_1_log - (hedge_ratio * series_2_log)
    return spread


# Calculate metrics
def calculate_metrics(series_1, series_2):
    """
    Returns:
        tuple: (coint_flag, zscore_list)
    """
    coint_flag = 0

    # Convert to numpy arrays first
    series_1 = np.array(series_1, dtype=float)
    series_2 = np.array(series_2, dtype=float)

    min_len = min(len(series_1), len(series_2))
    if min_len < 2:
        return 0, []

    if len(series_1) != len(series_2):
        series_1 = series_1[-min_len:]
        series_2 = series_2[-min_len:]

    # Safety: skip if any NaN or zero/negative prices
    if np.any(np.isnan(series_1)) or np.any(np.isnan(series_2)):
        return 0, []
    if np.any(series_1 <= 0) or np.any(series_2 <= 0):
        return 0, []

    # Log transform once (this is correct)
    series_1_log = np.log(series_1)
    series_2_log = np.log(series_2)

    # Check for constant series (zero variance)
    if np.std(series_1_log) == 0 or np.std(series_2_log) == 0:
        return 0, []

    try:
        # Cointegration test on log prices
        adf_statistic, p_value, critical_values = coint(series_1_log, series_2_log)

        # OLS regression on log prices
        series_2_const = sm.add_constant(series_2_log)
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=RuntimeWarning)
            models = sm.OLS(series_1_log, series_2_const).fit()

        # Get hedge ratio
        hedge_ratio = float(models.params[1] if len(models.params) > 1 else models.params[0])

        # Pass already-logged prices (do not log again)
        spread = calculate_spread(series_1_log, series_2_log, hedge_ratio)
        spread = pd.Series(spread)

        # Compute z-score series
        zscore_list = calculate_zscore(spread)

        # Set cointegration flag
        if np.isfinite(p_value) and p_value < 0.05 and adf_statistic < critical_values[1]:
            coint_flag = 1

        return (
            coint_flag,
            zscore_list.tolist(),
        )

    except (ValueError, np.linalg.LinAlgError):
        # Skip pairs with numerical issues
        return 0, []
