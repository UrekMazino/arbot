from config_strategy_api import z_score_window
from statsmodels.tsa.stattools import coint
import statsmodels.api as sm
import pandas as pd
import numpy as np
import math
import warnings
from itertools import combinations


# Calculate Z-score
def calculate_zscore(spread):
    series = pd.Series(spread, dtype=float)
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=RuntimeWarning)
        mean = series.rolling(window=z_score_window).mean()
        std = series.rolling(window=z_score_window).std()
        zscore = (series - mean) / std
    return zscore.astype(float).values


# Count zero crossings
def count_zero_crossings(spread, threshold=None):
    spread = pd.Series(spread).dropna()

    if len(spread) < 2:
        return 0

    if threshold is None:
        threshold = 0.1 * spread.std()  # noise filter

    prev = spread.shift(1)

    crossings = (
            ((prev > threshold) & (spread < -threshold)) |
            ((prev < -threshold) & (spread > threshold))
    )

    return int(crossings.sum())


# Calculate spread (input should already be logged)
def calculate_spread(series_1_log, series_2_log, hedge_ratio):
    """
    Calculate spread from LOG prices (do NOT log again!)

    Args:
        series_1_log: Already log-transformed prices
        series_2_log: Already log-transformed prices
        hedge_ratio: Hedge ratio from regression

    Returns:
        numpy array: The spread
    """
    spread = series_1_log - (hedge_ratio * series_2_log)
    return spread


# Calculate co-integration
def calculate_cointegration(series_1, series_2):
    """
    Calculate cointegration between two price series

    Args:
        series_1: Raw price series (will be log-transformed)
        series_2: Raw price series (will be log-transformed)

    Returns:
        tuple: (coint_flag, p_value, adf_stat, crit_val, hedge_ratio, zero_crossings)
    """
    coint_flag = 0

    # Convert to numpy arrays first
    series_1 = np.array(series_1, dtype=float)
    series_2 = np.array(series_2, dtype=float)

    min_len = min(len(series_1), len(series_2))
    if min_len < 2:
        return 0, None, None, None, None, 0

    if len(series_1) != len(series_2):
        series_1 = series_1[-min_len:]
        series_2 = series_2[-min_len:]

    # Safety: skip if any NaN or zero/negative prices
    if np.any(np.isnan(series_1)) or np.any(np.isnan(series_2)):
        return 0, None, None, None, None, 0
    if np.any(series_1 <= 0) or np.any(series_2 <= 0):
        return 0, None, None, None, None, 0

    # Log transform once (this is correct)
    series_1_log = np.log(series_1)
    series_2_log = np.log(series_2)

    # Check for constant series (zero variance)
    if np.std(series_1_log) == 0 or np.std(series_2_log) == 0:
        return 0, None, None, None, None, 0

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

        # Count zero crossings
        zero_crossings = count_zero_crossings(spread)

        # Set cointegration flag
        if np.isfinite(p_value) and p_value < 0.05 and adf_statistic < critical_values[1]:
            coint_flag = 1

        return (
            coint_flag,
            p_value,
            adf_statistic,
            critical_values[1],
            hedge_ratio,
            zero_crossings
        )

    except (ValueError, np.linalg.LinAlgError) as e:
        # Skip pairs with numerical issues
        return 0, None, None, None, None, 0


# Put close prices into a list
def extract_close_prices(klines):
    close_prices = []
    for price_values in klines:
        if math.isnan(price_values["close"]):
            return []
        close_prices.append(price_values["close"])

    # Filter out symbols with zero variance
    if len(set(close_prices)) == 1:
        return []

    return close_prices


# Get co-integrated pairs
def get_cointegrated_pairs(json_symbols):
    """
    Find all cointegrated pairs from symbol data
    """
    coint_pair_list = []
    total_comparisons = 0
    pairs_with_crossings = 0

    series_by_symbol = {}
    for sym, data in json_symbols.items():
        series = extract_close_prices(data['klines'])
        if series:
            series_by_symbol[sym] = np.array(series, dtype=float)

    symbols = list(series_by_symbol.keys())

    for sym_1, sym_2 in combinations(symbols, 2):
        series_1 = series_by_symbol[sym_1]
        series_2 = series_by_symbol[sym_2]

        # Check for cointegration
        coint_flag, p_value, adf_statistic, critical_values, hedge_ratio, zero_crossings = calculate_cointegration(
            series_1, series_2)

        total_comparisons += 1

        if coint_flag == 1:
            if zero_crossings > 0:
                pairs_with_crossings += 1

            coint_pair_list.append({
                "sym_1": sym_1,
                "sym_2": sym_2,
                "p_value": p_value,
                "adf_stat": adf_statistic,
                "c_value": critical_values,
                "hedge_ratio": hedge_ratio,
                "zero_crossing": zero_crossings,
            })

    # Output results
    df_coint = pd.DataFrame(coint_pair_list)
    df_coint = df_coint.sort_values(by=['zero_crossing'], ascending=[False])
    df_coint.to_csv('2_cointegrated_pairs.csv', index=False)

    # Print statistics
    print(f"\n{'=' * 60}")
    print(f"COINTEGRATION ANALYSIS RESULTS")
    print(f"{'=' * 60}")
    print(f"Total pairs analyzed:        {total_comparisons:,}")
    print(f"Cointegrated pairs found:    {len(coint_pair_list):,}")
    print(f"Pairs with crossings (>0):   {pairs_with_crossings:,}")
    print(f"Pairs without crossings:     {len(coint_pair_list) - pairs_with_crossings:,}")

    if len(df_coint) > 0:
        print(f"\nZero Crossings Statistics:")
        print(f"  Min:     {df_coint['zero_crossing'].min()}")
        print(f"  Max:     {df_coint['zero_crossing'].max()}")
        print(f"  Mean:    {df_coint['zero_crossing'].mean():.2f}")
        print(f"  Median:  {df_coint['zero_crossing'].median():.0f}")
    print(f"{'=' * 60}\n")

    return df_coint
