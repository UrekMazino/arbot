from config_strategy_api import (
    z_score_window,
    shared_coint_pvalue_threshold,
    cointegration_zero_cross_threshold_ratio,
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
    min_orderbook_depth_usdt,
    min_orderbook_levels,
    fast_path_enabled,
    corr_min_filter,
    corr_lookback,
    market_session,
)
import time
from pathlib import Path
import json
import sys
import pandas as pd
import numpy as np
import math
from decimal import Decimal, ROUND_UP
from itertools import combinations
from func_strategy_log import get_strategy_logger

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared_cointegration_validator import (
    calculate_zscore_series,
    count_spread_zero_crossings,
    evaluate_cointegration,
)


def _read_json_object(path):
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _load_restricted_tickers():
    restricted = set()
    state_path = Path(__file__).resolve().parents[1] / "Execution" / "state" / "pair_strategy_state.json"
    data = _read_json_object(state_path)
    graveyard = data.get("graveyard", {})
    if isinstance(graveyard, dict):
        for key in graveyard.keys():
            key_text = str(key or "")
            if key_text.startswith("ticker::"):
                ticker = key_text[len("ticker::"):]
                if ticker:
                    restricted.add(ticker)

    state_restricted = data.get("restricted_tickers", {})
    if isinstance(state_restricted, dict):
        restricted.update(str(key) for key in state_restricted.keys() if key)
    elif isinstance(state_restricted, list):
        restricted.update(str(item) for item in state_restricted if item)

    seeded_path = Path(__file__).resolve().parents[1] / "Execution" / "state" / "graveyard_tickers.json"
    seeded_restricted = _read_json_object(seeded_path)
    restricted.update(str(key) for key in seeded_restricted.keys() if key)
    return restricted


# Calculate Z-score
def calculate_zscore(spread):
    return calculate_zscore_series(spread, window=z_score_window)


# Count zero crossings
def count_zero_crossings(spread, threshold=None):
    return count_spread_zero_crossings(
        spread,
        threshold=threshold,
        threshold_ratio=cointegration_zero_cross_threshold_ratio,
    )


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
    metrics = evaluate_cointegration(
        series_1,
        series_2,
        window=z_score_window,
        pvalue_threshold=shared_coint_pvalue_threshold,
        zero_cross_threshold_ratio=cointegration_zero_cross_threshold_ratio,
        already_logged=False,
    )
    if not metrics.get("critical_value"):
        return 0, None, None, None, None, 0
    return (
        int(metrics.get("coint_flag", 0) or 0),
        float(metrics.get("p_value", 1.0)),
        float(metrics.get("adf_stat", 0.0)),
        float(metrics.get("critical_value", 0.0)),
        float(metrics.get("hedge_ratio", 0.0)),
        int(metrics.get("zero_crossings", 0) or 0),
    )


def calculate_cointegration_from_log(series_1_log, series_2_log):
    """
    Calculate cointegration using precomputed log prices.

    Args:
        series_1_log: Log-transformed prices for series 1
        series_2_log: Log-transformed prices for series 2

    Returns:
        tuple: (coint_flag, p_value, adf_stat, crit_val, hedge_ratio, zero_crossings)
    """
    metrics = evaluate_cointegration(
        series_1_log,
        series_2_log,
        window=z_score_window,
        pvalue_threshold=shared_coint_pvalue_threshold,
        zero_cross_threshold_ratio=cointegration_zero_cross_threshold_ratio,
        already_logged=True,
    )
    if not metrics.get("critical_value"):
        return 0, None, None, None, None, 0
    return (
        int(metrics.get("coint_flag", 0) or 0),
        float(metrics.get("p_value", 1.0)),
        float(metrics.get("adf_stat", 0.0)),
        float(metrics.get("critical_value", 0.0)),
        float(metrics.get("hedge_ratio", 0.0)),
        int(metrics.get("zero_crossings", 0) or 0),
    )


def _corrcoef_fast(series_a, series_b):
    if series_a.size < 2 or series_b.size < 2:
        return None
    a = series_a.astype(float)
    b = series_b.astype(float)
    min_len = min(a.size, b.size)
    if min_len < 2:
        return None
    if a.size != b.size:
        a = a[-min_len:]
        b = b[-min_len:]
    a_mean = a.mean()
    b_mean = b.mean()
    a = a - a_mean
    b = b - b_mean
    denom = math.sqrt(float((a * a).sum()) * float((b * b).sum()))
    if denom <= 0:
        return None
    return float((a * b).sum() / denom)


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


def _parse_quote_ccy(inst_id):
    if not inst_id:
        return ""
    parts = str(inst_id).split("-")
    if len(parts) >= 2:
        return parts[1].upper()
    return ""


def _resolve_contract_value_quote(last_price, instrument_info=None, inst_id=""):
    if not isinstance(instrument_info, dict):
        return 0.0

    ct_val = _safe_float(instrument_info.get("ctVal"))
    ct_mult = _safe_float(instrument_info.get("ctMult"))
    if ct_mult in (None, 0):
        ct_mult = 1.0
    if ct_val is None or ct_val <= 0 or last_price is None or last_price <= 0:
        return 0.0

    ct_val_ccy = str(instrument_info.get("ctValCcy") or "").upper()
    inst_ref = inst_id or instrument_info.get("instId") or instrument_info.get("symbol") or ""
    quote_ccy = _parse_quote_ccy(inst_ref)
    contract_units = ct_val * ct_mult
    if ct_val_ccy and quote_ccy and ct_val_ccy == quote_ccy:
        return float(contract_units)
    return float(last_price) * float(contract_units)


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


def _calculate_min_capital(last_price, min_sz, lot_sz, instrument_info=None, inst_id=""):
    if last_price is None or last_price <= 0:
        return 0.0, 0.0
    min_qty = _get_min_order_qty(min_sz, lot_sz)
    if min_qty <= 0:
        return 0.0, 0.0
    contract_value_quote = _resolve_contract_value_quote(last_price, instrument_info, inst_id=inst_id)
    if contract_value_quote > 0:
        return min_qty, float(min_qty) * contract_value_quote
    return min_qty, float(min_qty) * float(last_price)


def _calculate_orderbook_depth_usdt(levels, instrument_info=None, inst_id="", fallback_price=None):
    total = 0.0
    for level in levels or []:
        try:
            price = _safe_float(level[0] if len(level) > 0 else None)
            size = _safe_float(level[1] if len(level) > 1 else None)
        except (TypeError, ValueError, IndexError):
            continue
        if price is None or price <= 0 or size is None or size <= 0:
            continue

        contract_value_quote = _resolve_contract_value_quote(price, instrument_info, inst_id=inst_id)
        if contract_value_quote > 0:
            total += size * contract_value_quote
            continue

        ref_price = price if price > 0 else fallback_price
        if ref_price is None or ref_price <= 0:
            continue
        total += ref_price * size
    return float(total)


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
def get_cointegrated_pairs(
    json_symbols,
    liquidity_pct_override=None,
    min_avg_quote_volume_override=None,
    corr_min_override=None,
    min_p_value_override=None,
    max_p_value_override=None,
    min_zero_crossings_override=None,
    min_capital_per_leg_override=None,
    min_equity_filter_override=None,
):
    """
    Find all cointegrated pairs from symbol data
    """
    logger = get_strategy_logger()
    coint_pair_list = []
    total_comparisons = 0
    pairs_with_crossings = 0
    restricted_tickers = _load_restricted_tickers()
    restricted_removed = 0

    series_by_symbol = {}
    log_series_by_symbol = {}
    returns_by_symbol = {}
    symbol_meta = {}
    for sym, data in json_symbols.items():
        series = extract_close_prices(data['klines'])
        if not series:
            continue
        series = np.array(series, dtype=float)
        if np.any(np.isnan(series)) or np.any(series <= 0):
            continue
        log_series = np.log(series)
        if np.std(log_series) == 0:
            continue

        series_by_symbol[sym] = series
        log_series_by_symbol[sym] = log_series
        returns = np.diff(log_series)
        if corr_lookback and corr_lookback > 0 and returns.size > corr_lookback:
            returns = returns[-corr_lookback:]
        returns_by_symbol[sym] = returns

        info = data.get('symbol_info', {}) if isinstance(data, dict) else {}
        klines = data.get('klines', []) if isinstance(data, dict) else []
        min_sz = info.get('min_sz') if isinstance(info, dict) else None
        lot_sz = info.get('lot_sz') if isinstance(info, dict) else None
        if min_sz is None and isinstance(info, dict):
            min_sz = info.get('minSz')
        if lot_sz is None and isinstance(info, dict):
            lot_sz = info.get('lotSz')
        last_close = series[-1] if series.size else None
        contract_value_quote = _resolve_contract_value_quote(last_close, info, inst_id=sym)
        min_qty, min_capital = _calculate_min_capital(last_close, min_sz, lot_sz, info, inst_id=sym)
        avg_quote_volume = _average_quote_volume(klines, liquidity_window)
        symbol_meta[sym] = {
            "min_qty": min_qty,
            "min_capital": min_capital,
            "last_close": last_close,
            "avg_quote_volume": avg_quote_volume,
            "contract_value_quote": contract_value_quote,
            "instrument_info": info,
        }

    symbols = list(series_by_symbol.keys())
    if restricted_tickers:
        before = len(symbols)
        symbols = [sym for sym in symbols if sym not in restricted_tickers]
        restricted_removed = before - len(symbols)

    if corr_min_override is not None:
        try:
            corr_min = float(corr_min_override)
        except (TypeError, ValueError):
            corr_min = 0.0
    else:
        corr_min = corr_min_filter if fast_path_enabled else 0.0

    # Load graveyard to exclude failed pairs
    graveyard_pairs = set()
    try:
        execution_state_path = Path(__file__).resolve().parent.parent / "Execution" / "state" / "pair_strategy_state.json"
        if execution_state_path.exists():
            with open(execution_state_path, 'r') as f:
                exec_state = json.load(f)
                graveyard = exec_state.get("graveyard", {})
                for pair_key in graveyard.keys():
                    graveyard_pairs.add(pair_key)
                    # Also add reverse
                    parts = pair_key.split('/')
                    if len(parts) == 2:
                        graveyard_pairs.add(f"{parts[1]}/{parts[0]}")
                logger.info(f"Loaded {len(graveyard)} pairs from graveyard (will exclude from discovery)")

                # Expired hospital entries are already eligible again, but stale state may still contain them.
                hospital = exec_state.get("hospital", {})
                now = time.time()
                expired_hospital_count = 0
                for pair_key, entry in hospital.items():
                    if not isinstance(entry, dict):
                        continue
                    ts = entry.get("ts", 0)
                    cooldown = entry.get("cooldown", 3600)
                    elapsed = now - ts
                    if elapsed >= cooldown:
                        expired_hospital_count += 1
                if expired_hospital_count:
                    logger.info(
                        "Found %d expired hospital entries in state (already eligible for discovery).",
                        expired_hospital_count,
                    )
    except Exception as e:
        logger.warning(f"Could not load graveyard/hospital: {e}")

    filtered_breakdown = {}
    orderbook_cache = {}

    def _get_orderbook_liquidity_status(ticker):
        cached = orderbook_cache.get(ticker)
        if cached is not None:
            return cached

        meta = symbol_meta.get(ticker, {})
        instrument_info = meta.get("instrument_info") or {}
        last_close = meta.get("last_close")

        try:
            orderbook_res = market_session.get_orderbook(instId=ticker, sz=50)
            if orderbook_res.get("code") != "0":
                result = {
                    "ok": False,
                    "reason": "orderbook_fetch_error",
                    "detail": orderbook_res.get("msg") or "unknown_error",
                }
                logger.warning("Failed to fetch orderbook for %s: %s", ticker, result["detail"])
                orderbook_cache[ticker] = result
                return result

            data = orderbook_res.get("data", [])
            if not data:
                result = {
                    "ok": False,
                    "reason": "orderbook_fetch_error",
                    "detail": "empty_data",
                }
                logger.warning("Failed to fetch orderbook for %s: empty response data", ticker)
                orderbook_cache[ticker] = result
                return result

            bids = data[0].get("bids", [])
            asks = data[0].get("asks", [])
            if len(bids) < min_orderbook_levels or len(asks) < min_orderbook_levels:
                result = {
                    "ok": False,
                    "reason": "orderbook_levels",
                    "bid_levels": len(bids),
                    "ask_levels": len(asks),
                }
                logger.info(
                    "Skipping thin orderbook: %s (bids=%d, asks=%d levels)",
                    ticker,
                    len(bids),
                    len(asks),
                )
                orderbook_cache[ticker] = result
                return result

            try:
                bid_depth_usdt = _calculate_orderbook_depth_usdt(
                    bids,
                    instrument_info=instrument_info,
                    inst_id=ticker,
                    fallback_price=last_close,
                )
                ask_depth_usdt = _calculate_orderbook_depth_usdt(
                    asks,
                    instrument_info=instrument_info,
                    inst_id=ticker,
                    fallback_price=last_close,
                )
            except (ValueError, TypeError, IndexError) as exc:
                result = {
                    "ok": False,
                    "reason": "orderbook_calc_error",
                    "detail": str(exc),
                }
                logger.warning("Error calculating orderbook depth for %s: %s", ticker, exc)
                orderbook_cache[ticker] = result
                return result

            result = {
                "ok": bid_depth_usdt >= min_orderbook_depth_usdt and ask_depth_usdt >= min_orderbook_depth_usdt,
                "reason": "orderbook_depth",
                "bid_depth_usdt": bid_depth_usdt,
                "ask_depth_usdt": ask_depth_usdt,
            }
            if not result["ok"]:
                logger.info(
                    "Skipping low liquidity: %s (bid_depth=%.0f USDT, ask_depth=%.0f USDT, min=%.0f USDT)",
                    ticker,
                    bid_depth_usdt,
                    ask_depth_usdt,
                    min_orderbook_depth_usdt,
                )
            else:
                logger.debug(
                    "%s liquidity OK: bids=%.0f USDT, asks=%.0f USDT",
                    ticker,
                    bid_depth_usdt,
                    ask_depth_usdt,
                )
            orderbook_cache[ticker] = result
            return result
        except Exception as exc:
            result = {
                "ok": False,
                "reason": "orderbook_fetch_error",
                "detail": str(exc),
            }
            logger.warning("Error checking orderbook depth for %s: %s", ticker, exc)
            orderbook_cache[ticker] = result
            return result

    for sym_1, sym_2 in combinations(symbols, 2):
        series_1_log = log_series_by_symbol[sym_1]
        series_2_log = log_series_by_symbol[sym_2]

        total_comparisons += 1

        # Skip graveyard pairs
        pair_key = f"{sym_1}/{sym_2}"
        if pair_key in graveyard_pairs:
            filtered_breakdown["graveyard"] = filtered_breakdown.get("graveyard", 0) + 1
            continue

        if corr_min and corr_min > 0:
            ret_1 = returns_by_symbol.get(sym_1)
            ret_2 = returns_by_symbol.get(sym_2)
            if ret_1 is None or ret_2 is None:
                continue
            corr_value = _corrcoef_fast(ret_1, ret_2)
            if corr_value is None or not np.isfinite(corr_value):
                filtered_breakdown["corr"] = filtered_breakdown.get("corr", 0) + 1
                continue
            if abs(corr_value) < corr_min:
                filtered_breakdown["corr"] = filtered_breakdown.get("corr", 0) + 1
                continue

        # Check for cointegration using precomputed logs
        coint_flag, p_value, adf_statistic, critical_values, hedge_ratio, zero_crossings = (
            calculate_cointegration_from_log(series_1_log, series_2_log)
        )

        if coint_flag == 1:
            if zero_crossings > 0:
                pairs_with_crossings += 1

            # Orderbook depth check - ensure sufficient USDT liquidity
            orderbook_check_passed = True

            for ticker in [sym_1, sym_2]:
                orderbook_status = _get_orderbook_liquidity_status(ticker)
                if not orderbook_status.get("ok"):
                    reason = orderbook_status.get("reason") or "orderbook_fetch_error"
                    filtered_breakdown[reason] = filtered_breakdown.get(reason, 0) + 1
                    orderbook_check_passed = False
                    break

            if not orderbook_check_passed:
                continue  # Skip this pair

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

    # Only sort if DataFrame is not empty
    if not df_coint.empty and 'zero_crossing' in df_coint.columns:
        df_coint = df_coint.sort_values(by=['zero_crossing'], ascending=[False])
    filtered_count = 0
    liquidity_pct_cutoff = None
    active_liquidity_pct = (
        liquidity_pct_override if liquidity_pct_override is not None else liquidity_pct
    )
    active_min_avg_quote_volume = (
        min_avg_quote_volume_override if min_avg_quote_volume_override is not None else min_avg_quote_volume
    )

    active_min_p_value = min_p_value_filter
    active_max_p_value = max_p_value_filter
    if min_p_value_override is not None:
        try:
            active_min_p_value = float(min_p_value_override)
        except (TypeError, ValueError):
            pass
    if max_p_value_override is not None:
        try:
            active_max_p_value = float(max_p_value_override)
        except (TypeError, ValueError):
            pass

    active_zero_crossings = min_zero_crossings
    if min_zero_crossings_override is not None:
        try:
            active_zero_crossings = int(float(min_zero_crossings_override))
        except (TypeError, ValueError):
            pass

    active_min_capital_per_leg = min_capital_per_leg
    if min_capital_per_leg_override is not None:
        try:
            active_min_capital_per_leg = float(min_capital_per_leg_override)
        except (TypeError, ValueError):
            pass

    active_min_equity_filter = min_equity_filter_usdt
    if min_equity_filter_override is not None:
        try:
            active_min_equity_filter = float(min_equity_filter_override)
        except (TypeError, ValueError):
            pass

    if not df_coint.empty:
        if active_min_p_value is not None and active_max_p_value is not None:
            if active_min_p_value > 0 and active_max_p_value > 0 and active_min_p_value < active_max_p_value:
                before = len(df_coint)
                df_coint = df_coint[
                    (df_coint["p_value"] >= active_min_p_value) &
                    (df_coint["p_value"] <= active_max_p_value)
                ].copy()
                filtered_breakdown["p_value"] = before - len(df_coint)

        if active_zero_crossings and active_zero_crossings > 0:
            before = len(df_coint)
            df_coint = df_coint[df_coint["zero_crossing"] >= active_zero_crossings].copy()
            filtered_breakdown["zero_crossing"] = before - len(df_coint)

        if min_hedge_ratio is not None and max_hedge_ratio is not None:
            if min_hedge_ratio >= 0 and max_hedge_ratio > 0 and min_hedge_ratio <= max_hedge_ratio:
                before = len(df_coint)
                hr_abs = df_coint["hedge_ratio"].abs()
                df_coint = df_coint[(hr_abs >= min_hedge_ratio) & (hr_abs <= max_hedge_ratio)].copy()
                filtered_breakdown["hedge_ratio"] = before - len(df_coint)

        if active_min_capital_per_leg is not None and active_min_capital_per_leg > 0:
            if "min_capital_per_leg" in df_coint.columns:
                before = len(df_coint)
                cap_vals = pd.to_numeric(df_coint["min_capital_per_leg"], errors="coerce")
                df_coint = df_coint[cap_vals >= active_min_capital_per_leg].copy()
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
        active_min_equity_filter
        and active_min_equity_filter > 0
        and not df_coint.empty
        and "min_equity_recommended" in df_coint.columns
    ):
        before = len(df_coint)
        mask = df_coint["min_equity_recommended"].isna() | (
            df_coint["min_equity_recommended"] <= active_min_equity_filter
        )
        df_coint = df_coint[mask].copy()
        filtered_count = before - len(df_coint)
        filtered_breakdown["min_equity"] = filtered_count
    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "2_cointegrated_pairs.csv"
    df_coint.to_csv(output_path, index=False)
    summary = {
        "total_pairs": total_comparisons,
        "cointegrated_pairs": len(coint_pair_list),
        "pairs_with_crossings": pairs_with_crossings,
        "pairs_without_crossings": len(coint_pair_list) - pairs_with_crossings,
        "filtered_breakdown": filtered_breakdown,
        "corr_min": corr_min,
        "corr_lookback": corr_lookback,
        "corr_filtered": filtered_breakdown.get("corr", 0),
        "p_value_min": active_min_p_value,
        "p_value_max": active_max_p_value,
        "zero_crossing_min": active_zero_crossings,
        "min_capital_per_leg": active_min_capital_per_leg,
        "min_equity_filter_usdt": active_min_equity_filter,
        "liquidity_pct": active_liquidity_pct,
        "liquidity_pct_cutoff": liquidity_pct_cutoff,
        "min_equity_filtered": filtered_count,
        "restricted_removed": restricted_removed,
        "pairs_kept": len(df_coint),
    }

    if len(df_coint) > 0 and "zero_crossing" in df_coint.columns:
        summary["zero_crossing"] = {
            "min": float(df_coint["zero_crossing"].min()),
            "max": float(df_coint["zero_crossing"].max()),
            "mean": float(df_coint["zero_crossing"].mean()),
            "median": float(df_coint["zero_crossing"].median()),
        }
    if "min_capital_per_leg" in df_coint.columns:
        min_caps = df_coint["min_capital_per_leg"].dropna().astype(float).tolist()
        if min_caps:
            max_per_leg = max(min_caps)
            summary["min_capital"] = {
                "max_per_leg": float(max_per_leg),
                "recommended_equity": float(max_per_leg * 2),
            }

    logger.info("Cointegration summary: %s", summary)

    return df_coint, summary
