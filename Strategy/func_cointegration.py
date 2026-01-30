from config_strategy_api import (
    z_score_window,
    min_equity_filter_usdt,
    max_pairs_per_ticker,
    min_p_value_filter,
    max_p_value_filter,
    min_zero_crossings,
    min_hedge_ratio,
    max_hedge_ratio,
    min_capital_per_leg,
    liquidity_window,
    min_avg_quote_volume,
    liquidity_pct,
)
from pathlib import Path
import json
from statsmodels.tsa.stattools import coint
import statsmodels.api as sm
import pandas as pd
import numpy as np
import math
import warnings
from decimal import Decimal, ROUND_UP
from itertools import combinations

def _load_restricted_tickers():
    state_path = Path(__file__).resolve().parents[1] / "Execution" / "pair_strategy_state.json"
    if not state_path.exists():
        return set()
    try:
        with state_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return set()
    restricted = data.get("restricted_tickers", {})
    if isinstance(restricted, dict):
        return {str(key) for key in restricted.keys() if key}
    if isinstance(restricted, list):
        return {str(item) for item in restricted if item}
    return set()


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


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_min_order_qty(min_sz, lot_sz):
    try:
        min_sz_dec = Decimal(str(min_sz)) if min_sz is not None else Decimal("0")
    except (TypeError, ValueError):
        min_sz_dec = Decimal("0")
    try:
        lot_sz_dec = Decimal(str(lot_sz)) if lot_sz is not None else Decimal("0")
    except (TypeError, ValueError):
        lot_sz_dec = Decimal("0")

    if min_sz_dec <= 0 and lot_sz_dec <= 0:
        return 0.0
    if lot_sz_dec <= 0:
        return float(min_sz_dec)
    if min_sz_dec <= 0:
        return float(lot_sz_dec)

    steps = (min_sz_dec / lot_sz_dec).to_integral_value(rounding=ROUND_UP)
    return float(steps * lot_sz_dec)


def _calculate_min_capital(last_price, min_sz, lot_sz):
    if last_price is None or last_price <= 0:
        return 0.0, 0.0
    min_qty = _get_min_order_qty(min_sz, lot_sz)
    if min_qty <= 0:
        return 0.0, 0.0
    return min_qty, float(min_qty) * float(last_price)


def _average_quote_volume(klines, window):
    if not klines:
        return None
    if window and window > 0 and len(klines) > window:
        data = klines[-window:]
    else:
        data = klines

    total = 0.0
    count = 0
    for row in data:
        if not isinstance(row, dict):
            continue
        close = _safe_float(row.get("close"))
        if close is None or close <= 0:
            continue
        base_vol = _safe_float(row.get("volume_ccy"))
        if base_vol is None or base_vol <= 0:
            base_vol = _safe_float(row.get("volume"))
        if base_vol is None or base_vol <= 0:
            continue
        total += base_vol * close
        count += 1
    if count == 0:
        return None
    return total / count


# Get co-integrated pairs
def get_cointegrated_pairs(json_symbols, liquidity_pct_override=None, min_avg_quote_volume_override=None):
    """
    Find all cointegrated pairs from symbol data
    """
    coint_pair_list = []
    total_comparisons = 0
    pairs_with_crossings = 0
    restricted_tickers = _load_restricted_tickers()
    restricted_removed = 0

    series_by_symbol = {}
    symbol_meta = {}
    for sym, data in json_symbols.items():
        series = extract_close_prices(data['klines'])
        if series:
            series_by_symbol[sym] = np.array(series, dtype=float)
        info = data.get('symbol_info', {}) if isinstance(data, dict) else {}
        klines = data.get('klines', []) if isinstance(data, dict) else []
        min_sz = info.get('min_sz') if isinstance(info, dict) else None
        lot_sz = info.get('lot_sz') if isinstance(info, dict) else None
        if min_sz is None and isinstance(info, dict):
            min_sz = info.get('minSz')
        if lot_sz is None and isinstance(info, dict):
            lot_sz = info.get('lotSz')
        last_close = series[-1] if series else None
        min_qty, min_capital = _calculate_min_capital(last_close, min_sz, lot_sz)
        avg_quote_volume = _average_quote_volume(klines, liquidity_window)
        symbol_meta[sym] = {
            "min_qty": min_qty,
            "min_capital": min_capital,
            "last_close": last_close,
            "avg_quote_volume": avg_quote_volume,
        }

    symbols = list(series_by_symbol.keys())
    if restricted_tickers:
        before = len(symbols)
        symbols = [sym for sym in symbols if sym not in restricted_tickers]
        restricted_removed = before - len(symbols)

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

            min_cap_1 = symbol_meta.get(sym_1, {}).get("min_capital", 0.0) or 0.0
            min_cap_2 = symbol_meta.get(sym_2, {}).get("min_capital", 0.0) or 0.0
            required_floor = max(min_cap_1, min_cap_2) if min_cap_1 > 0 and min_cap_2 > 0 else None
            min_equity = required_floor * 2 if required_floor else None
            avg_vol_1 = symbol_meta.get(sym_1, {}).get("avg_quote_volume")
            avg_vol_2 = symbol_meta.get(sym_2, {}).get("avg_quote_volume")
            pair_liquidity = None
            if avg_vol_1 is not None and avg_vol_2 is not None:
                pair_liquidity = min(avg_vol_1, avg_vol_2)

            coint_pair_list.append({
                "sym_1": sym_1,
                "sym_2": sym_2,
                "p_value": p_value,
                "adf_stat": adf_statistic,
                "c_value": critical_values,
                "hedge_ratio": hedge_ratio,
                "zero_crossing": zero_crossings,
                "min_capital_1": min_cap_1 if min_cap_1 > 0 else None,
                "min_capital_2": min_cap_2 if min_cap_2 > 0 else None,
                "min_capital_per_leg": required_floor,
                "min_equity_recommended": min_equity,
                "avg_quote_volume_1": avg_vol_1,
                "avg_quote_volume_2": avg_vol_2,
                "pair_liquidity_min": pair_liquidity,
            })

    # Output results
    df_coint = pd.DataFrame(coint_pair_list)
    df_coint = df_coint.sort_values(by=['zero_crossing'], ascending=[False])
    filtered_count = 0
    filtered_breakdown = {}
    liquidity_pct_cutoff = None
    active_liquidity_pct = (
        liquidity_pct_override if liquidity_pct_override is not None else liquidity_pct
    )
    active_min_avg_quote_volume = (
        min_avg_quote_volume_override if min_avg_quote_volume_override is not None else min_avg_quote_volume
    )

    if not df_coint.empty:
        if min_p_value_filter is not None and max_p_value_filter is not None:
            if min_p_value_filter > 0 and max_p_value_filter > 0 and min_p_value_filter < max_p_value_filter:
                before = len(df_coint)
                df_coint = df_coint[
                    (df_coint["p_value"] >= min_p_value_filter) &
                    (df_coint["p_value"] <= max_p_value_filter)
                ].copy()
                filtered_breakdown["p_value"] = before - len(df_coint)

        if min_zero_crossings and min_zero_crossings > 0:
            before = len(df_coint)
            df_coint = df_coint[df_coint["zero_crossing"] >= min_zero_crossings].copy()
            filtered_breakdown["zero_crossing"] = before - len(df_coint)

        if min_hedge_ratio is not None and max_hedge_ratio is not None:
            if min_hedge_ratio >= 0 and max_hedge_ratio > 0 and min_hedge_ratio <= max_hedge_ratio:
                before = len(df_coint)
                hr_abs = df_coint["hedge_ratio"].abs()
                df_coint = df_coint[(hr_abs >= min_hedge_ratio) & (hr_abs <= max_hedge_ratio)].copy()
                filtered_breakdown["hedge_ratio"] = before - len(df_coint)

        if min_capital_per_leg is not None and min_capital_per_leg > 0:
            if "min_capital_per_leg" in df_coint.columns:
                before = len(df_coint)
                cap_vals = pd.to_numeric(df_coint["min_capital_per_leg"], errors="coerce")
                df_coint = df_coint[cap_vals >= min_capital_per_leg].copy()
                filtered_breakdown["min_capital"] = before - len(df_coint)

        if active_min_avg_quote_volume and active_min_avg_quote_volume > 0:
            if "avg_quote_volume_1" in df_coint.columns and "avg_quote_volume_2" in df_coint.columns:
                before = len(df_coint)
                vol_1 = pd.to_numeric(df_coint["avg_quote_volume_1"], errors="coerce").fillna(0)
                vol_2 = pd.to_numeric(df_coint["avg_quote_volume_2"], errors="coerce").fillna(0)
                df_coint = df_coint[
                    (vol_1 >= active_min_avg_quote_volume) & (vol_2 >= active_min_avg_quote_volume)
                ].copy()
                filtered_breakdown["liquidity_min"] = before - len(df_coint)

        if active_liquidity_pct and active_liquidity_pct > 0 and not df_coint.empty:
            if "pair_liquidity_min" in df_coint.columns:
                before = len(df_coint)
                pair_liq = pd.to_numeric(df_coint["pair_liquidity_min"], errors="coerce")
                if not pair_liq.dropna().empty:
                    liquidity_pct_cutoff = pair_liq.quantile(active_liquidity_pct)
                    df_coint = df_coint[pair_liq >= liquidity_pct_cutoff].copy()
                    filtered_breakdown["liquidity_pct"] = before - len(df_coint)

        if max_pairs_per_ticker and max_pairs_per_ticker > 0 and not df_coint.empty:
            before = len(df_coint)
            counts = pd.concat([df_coint["sym_1"], df_coint["sym_2"]]).value_counts()
            df_coint = df_coint[
                (df_coint["sym_1"].map(counts) <= max_pairs_per_ticker) &
                (df_coint["sym_2"].map(counts) <= max_pairs_per_ticker)
            ].copy()
            filtered_breakdown["ticker_diversity"] = before - len(df_coint)
    if (
        min_equity_filter_usdt
        and min_equity_filter_usdt > 0
        and not df_coint.empty
        and "min_equity_recommended" in df_coint.columns
    ):
        before = len(df_coint)
        mask = df_coint["min_equity_recommended"].isna() | (
            df_coint["min_equity_recommended"] <= min_equity_filter_usdt
        )
        df_coint = df_coint[mask].copy()
        filtered_count = before - len(df_coint)
        filtered_breakdown["min_equity"] = filtered_count
    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "2_cointegrated_pairs.csv"
    df_coint.to_csv(output_path, index=False)

    # Print statistics
    print(f"\n{'=' * 60}")
    print(f"COINTEGRATION ANALYSIS RESULTS")
    print(f"{'=' * 60}")
    print(f"Total pairs analyzed:        {total_comparisons:,}")
    print(f"Cointegrated pairs found:    {len(coint_pair_list):,}")
    print(f"Pairs with crossings (>0):   {pairs_with_crossings:,}")
    print(f"Pairs without crossings:     {len(coint_pair_list) - pairs_with_crossings:,}")
    if filtered_breakdown:
        for key, count in filtered_breakdown.items():
            if count:
                print(f"Pairs filtered by {key}: {count:,}")
    if liquidity_pct_cutoff is not None:
        print(
            "Liquidity percentile cutoff: {0:.4f} (pct={1})".format(
                liquidity_pct_cutoff,
                active_liquidity_pct,
            )
        )
    if filtered_count:
        print(f"Pairs filtered by min equity: {filtered_count:,} (threshold: {min_equity_filter_usdt:.2f} USDT)")
    if restricted_removed:
        print(f"Symbols filtered by compliance restrictions: {restricted_removed:,}")

    if len(df_coint) > 0:
        print(f"\nZero Crossings Statistics:")
        print(f"  Min:     {df_coint['zero_crossing'].min()}")
        print(f"  Max:     {df_coint['zero_crossing'].max()}")
        print(f"  Mean:    {df_coint['zero_crossing'].mean():.2f}")
        print(f"  Median:  {df_coint['zero_crossing'].median():.0f}")

        if "min_capital_per_leg" in df_coint.columns:
            min_caps = df_coint["min_capital_per_leg"].dropna().astype(float).tolist()
            if min_caps:
                max_per_leg = max(min_caps)
                print("\nMin Capital Summary:")
                print(f"  Max per-leg min capital: {max_per_leg:.4f} USDT")
                print(f"  Recommended starting equity: {max_per_leg * 2:.4f} USDT")
    print(f"{'=' * 60}\n")

    return df_coint
