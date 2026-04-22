from config_strategy_api import (
    z_score_window,
    shared_coint_pvalue_threshold,
    cointegration_zero_cross_threshold_ratio,
    min_equity_filter_usdt,
    max_supply_pairs,
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
    soft_orderbook_depth_usdt,
    max_orderbook_imbalance,
    min_orderbook_levels,
    min_order_capacity_usdt,
    fast_path_enabled,
    corr_min_filter,
    corr_lookback,
    market_session,
)
import time
import os
from pathlib import Path
import json
import sys
from datetime import datetime, timezone
import pandas as pd
import numpy as np
import math
from decimal import Decimal, ROUND_UP
from itertools import combinations
from func_strategy_log import get_strategy_logger

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
PAIR_STATE_PATH = ROOT_DIR / "Execution" / "state" / "pair_strategy_state.json"

from shared_cointegration_validator import (
    calculate_zscore_series,
    count_spread_zero_crossings,
    evaluate_cointegration,
)


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
        return minimum
    return value


def _env_float(name, default, minimum=None):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        value = float(default)
    else:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = float(default)
    if minimum is not None and value < minimum:
        return minimum
    return value


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
    data = _read_json_object(PAIR_STATE_PATH)
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


def _calculate_max_order_notional(last_price, max_sz, instrument_info=None, inst_id=""):
    max_qty = _safe_float(max_sz)
    if max_qty is None or max_qty <= 0 or last_price is None or last_price <= 0:
        return None
    contract_value_quote = _resolve_contract_value_quote(last_price, instrument_info, inst_id=inst_id)
    if contract_value_quote > 0:
        return float(max_qty) * contract_value_quote
    return float(max_qty) * float(last_price)


def _count_csv_rows(path):
    if not path.exists():
        return 0
    try:
        return int(len(pd.read_csv(path)))
    except Exception:
        return 0


def _canonical_pair_key(row):
    sym_1 = str(row.get("sym_1") or "").strip().upper()
    sym_2 = str(row.get("sym_2") or "").strip().upper()
    if not sym_1 or not sym_2:
        return ""
    return "/".join(sorted((sym_1, sym_2)))


def _normalize_pair_key_text(pair_key):
    parts = str(pair_key or "").strip().upper().split("/")
    if len(parts) != 2:
        return ""
    left = parts[0].strip()
    right = parts[1].strip()
    if not left or not right:
        return ""
    return "/".join(sorted((left, right)))


def _load_pair_exclusion_reasons(now_ts=None):
    now_value = time.time() if now_ts is None else float(now_ts)
    data = _read_json_object(PAIR_STATE_PATH)
    exclusions = {}
    counts = {"graveyard": 0, "hospital": 0, "expired_hospital": 0}

    graveyard = data.get("graveyard", {})
    if isinstance(graveyard, dict):
        for raw_key in graveyard.keys():
            key_text = str(raw_key or "")
            if key_text.startswith("ticker::"):
                continue
            pair_key = _normalize_pair_key_text(key_text)
            if not pair_key:
                continue
            exclusions[pair_key] = "graveyard"
            counts["graveyard"] += 1

    hospital = data.get("hospital", {})
    if isinstance(hospital, dict):
        for raw_key, entry in hospital.items():
            pair_key = _normalize_pair_key_text(raw_key)
            if not pair_key or not isinstance(entry, dict):
                continue
            try:
                ts = float(entry.get("ts") or 0)
                cooldown = float(entry.get("cooldown") or 0)
            except (TypeError, ValueError):
                continue
            if ts > 0 and cooldown > 0 and now_value - ts < cooldown:
                exclusions.setdefault(pair_key, "hospital")
                counts["hospital"] += 1
            else:
                counts["expired_hospital"] += 1

    return exclusions, counts


def _filter_excluded_pair_rows(df):
    exclusions, _counts = _load_pair_exclusion_reasons()
    if df.empty or not exclusions:
        return df.copy(), 0
    output = df.copy()
    output["_pair_key"] = output.apply(_canonical_pair_key, axis=1)
    before = len(output)
    output = output[~output["_pair_key"].isin(exclusions.keys())].copy()
    return output.drop(columns=["_pair_key"], errors="ignore"), int(before - len(output))


def _filter_unusable_liquidity_pair_rows(df):
    required_columns = ("avg_quote_volume_1", "avg_quote_volume_2", "pair_liquidity_min")
    if df.empty or not all(column in df.columns for column in required_columns):
        return df.copy(), 0
    output = df.copy()
    vol_1 = pd.to_numeric(output["avg_quote_volume_1"], errors="coerce")
    vol_2 = pd.to_numeric(output["avg_quote_volume_2"], errors="coerce")
    pair_liq = pd.to_numeric(output["pair_liquidity_min"], errors="coerce")
    usable = (vol_1 > 0) & (vol_2 > 0) & (pair_liq > 0)
    before = len(output)
    return output[usable].copy(), int(before - int(usable.sum()))


def _sort_cointegrated_pair_frame(df):
    if df.empty:
        return df.copy()

    output = df.copy()
    sort_columns = []
    ascending = []
    if "zero_crossing" in output.columns:
        output["_sort_zero_crossing"] = pd.to_numeric(output["zero_crossing"], errors="coerce").fillna(-1)
        sort_columns.append("_sort_zero_crossing")
        ascending.append(False)
    if "p_value" in output.columns:
        output["_sort_p_value"] = pd.to_numeric(output["p_value"], errors="coerce").fillna(float("inf"))
        sort_columns.append("_sort_p_value")
        ascending.append(True)
    if sort_columns:
        output = output.sort_values(by=sort_columns, ascending=ascending, kind="stable")
    return output.drop(columns=[col for col in ("_sort_zero_crossing", "_sort_p_value") if col in output.columns])


def _accumulate_cointegrated_pair_supply(previous_df, latest_df, max_rows=None):
    previous = previous_df.copy() if previous_df is not None else pd.DataFrame()
    latest = latest_df.copy() if latest_df is not None else pd.DataFrame()
    previous["_pair_key"] = previous.apply(_canonical_pair_key, axis=1) if not previous.empty else []
    latest["_pair_key"] = latest.apply(_canonical_pair_key, axis=1) if not latest.empty else []
    previous = previous[previous["_pair_key"] != ""].copy() if "_pair_key" in previous.columns else previous
    latest = latest[latest["_pair_key"] != ""].copy() if "_pair_key" in latest.columns else latest

    previous_keys = set(previous["_pair_key"].tolist()) if "_pair_key" in previous.columns else set()
    latest_keys = set(latest["_pair_key"].tolist()) if "_pair_key" in latest.columns else set()

    if previous.empty:
        combined = latest.copy()
    elif latest.empty:
        combined = previous.copy()
    else:
        # Latest rows go first so a pair found again gets fresh metrics.
        combined = pd.concat([latest, previous], ignore_index=True, sort=False)
        combined = combined.drop_duplicates(subset=["_pair_key"], keep="first")

    combined = _sort_cointegrated_pair_frame(combined)
    before_cap = len(combined)
    if max_rows is not None:
        try:
            max_rows_int = max(int(max_rows), 1)
        except (TypeError, ValueError):
            max_rows_int = 1
        combined = combined.head(max_rows_int).copy()

    final_keys = set(combined["_pair_key"].tolist()) if "_pair_key" in combined.columns else set()
    output = combined.drop(columns=["_pair_key"], errors="ignore")
    return output, {
        "previous_canonical_rows": int(len(previous)),
        "latest_attempt_valid_rows": int(len(latest)),
        "accumulated_from_previous": bool(previous_keys and latest_keys),
        "accumulated_pairs_added": int(len(latest_keys - previous_keys)),
        "accumulated_pairs_refreshed": int(len(latest_keys & previous_keys)),
        "accumulated_pairs_retained": int(len((previous_keys - latest_keys) & final_keys)),
        "accumulation_cap_filtered": int(max(before_cap - len(output), 0)),
    }


def _write_cointegrated_pairs_csv(df_coint, output_path, logger=None, max_rows=None):
    """
    Keep 2_cointegrated_pairs.csv as the accumulated last-good pair supply.

    Strategy fallback attempts can legitimately produce zero rows. Those empty
    attempts should be visible for diagnostics, but they should not erase the
    canonical CSV that execution uses for pair switching. Non-empty attempts
    are merged into the previous canonical supply and capped after sorting.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    latest_attempt_path = output_path.with_name(f"{output_path.stem}_latest_attempt{output_path.suffix}")
    status_path = output_path.with_name(f"{output_path.stem}_status.json")
    temp_path = output_path.with_name(f".{output_path.stem}.tmp{output_path.suffix}")

    attempt_rows = int(len(df_coint))
    df_canonical_attempt, latest_excluded_rows = _filter_excluded_pair_rows(df_coint)
    df_coint.to_csv(latest_attempt_path, index=False)
    canonical_updated = False
    preserved_existing = False
    accumulation_status = {
        "previous_canonical_rows": _count_csv_rows(output_path),
        "latest_attempt_valid_rows": int(len(df_canonical_attempt)),
        "accumulated_from_previous": False,
        "accumulated_pairs_added": 0,
        "accumulated_pairs_refreshed": 0,
        "accumulated_pairs_retained": 0,
        "accumulation_cap_filtered": 0,
        "excluded_pairs_filtered": int(latest_excluded_rows),
        "unusable_liquidity_pairs_filtered": 0,
    }

    df_canonical_attempt, latest_unusable_liquidity_rows = _filter_unusable_liquidity_pair_rows(
        df_canonical_attempt
    )
    accumulation_status["latest_attempt_valid_rows"] = int(len(df_canonical_attempt))
    accumulation_status["unusable_liquidity_pairs_filtered"] = int(latest_unusable_liquidity_rows)

    if len(df_canonical_attempt) > 0:
        previous_df = pd.DataFrame()
        previous_excluded_rows = 0
        previous_unusable_liquidity_rows = 0
        if output_path.exists() and output_path.stat().st_size > 0:
            try:
                previous_df = pd.read_csv(output_path)
            except Exception:
                previous_df = pd.DataFrame()
            previous_df, previous_excluded_rows = _filter_excluded_pair_rows(previous_df)
            previous_df, previous_unusable_liquidity_rows = _filter_unusable_liquidity_pair_rows(previous_df)
        canonical_df, accumulation_status = _accumulate_cointegrated_pair_supply(
            previous_df,
            df_canonical_attempt,
            max_rows=max_rows,
        )
        accumulation_status["excluded_pairs_filtered"] = int(latest_excluded_rows + previous_excluded_rows)
        accumulation_status["unusable_liquidity_pairs_filtered"] = int(
            latest_unusable_liquidity_rows + previous_unusable_liquidity_rows
        )
        canonical_df.to_csv(temp_path, index=False)
        temp_path.replace(output_path)
        canonical_updated = True
    elif output_path.exists() and output_path.stat().st_size > 0:
        previous_df = pd.DataFrame()
        try:
            previous_df = pd.read_csv(output_path)
        except Exception:
            previous_df = pd.DataFrame()
        canonical_df, previous_excluded_rows = _filter_excluded_pair_rows(previous_df)
        canonical_df, previous_unusable_liquidity_rows = _filter_unusable_liquidity_pair_rows(canonical_df)
        accumulation_status["excluded_pairs_filtered"] = int(latest_excluded_rows + previous_excluded_rows)
        accumulation_status["unusable_liquidity_pairs_filtered"] = int(
            latest_unusable_liquidity_rows + previous_unusable_liquidity_rows
        )
        if previous_excluded_rows or previous_unusable_liquidity_rows:
            canonical_df.to_csv(temp_path, index=False)
            temp_path.replace(output_path)
            canonical_updated = True
            if logger:
                logger.info(
                    "Removed %d hospital/graveyard and %d unusable-liquidity pairs from canonical pair CSV at %s.",
                    previous_excluded_rows,
                    previous_unusable_liquidity_rows,
                    output_path,
                )
        else:
            preserved_existing = True
            if logger:
                logger.warning(
                    "No pairs found in latest Strategy attempt; preserving existing canonical pair CSV at %s.",
                    output_path,
                )
    else:
        df_canonical_attempt.to_csv(output_path, index=False)
        canonical_updated = True

    status = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "canonical_path": str(output_path),
        "latest_attempt_path": str(latest_attempt_path),
        "latest_attempt_rows": attempt_rows,
        "canonical_rows": _count_csv_rows(output_path),
        "canonical_updated": canonical_updated,
        "preserved_existing": preserved_existing,
        "accumulated_supply": True,
        **accumulation_status,
    }
    try:
        status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    except Exception as exc:
        if logger:
            logger.warning("Failed to write cointegrated pair status metadata: %s", exc)
    return status


def _write_cointegration_status_summary(output_path, summary, logger=None):
    status_path = output_path.with_name(f"{output_path.stem}_status.json")
    status = {}
    if status_path.exists():
        try:
            loaded = json.loads(status_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                status = loaded
        except Exception:
            status = {}

    summary_keys = [
        "total_pairs",
        "cointegrated_pairs",
        "pre_filter_pairs_with_crossings",
        "pre_filter_pairs_without_crossings",
        "usable_pairs_with_crossings",
        "usable_pairs_without_crossings",
        "crossing_candidates_filtered_later",
        "raw_pairs_with_crossings",
        "crossing_rejected_by_orderbook",
        "pairs_kept",
        "latest_attempt_rows",
        "latest_attempt_valid_rows",
        "canonical_pairs_rows",
        "accumulated_supply",
        "previous_canonical_rows",
        "accumulated_pairs_added",
        "accumulated_pairs_refreshed",
        "accumulated_pairs_retained",
        "accumulation_cap_filtered",
        "excluded_pairs_filtered",
        "unusable_liquidity_pairs_filtered",
        "zero_crossing_min",
        "filtered_breakdown",
        "zero_crossing",
    ]
    scan_summary = {key: summary.get(key) for key in summary_keys if key in summary}
    status.update(scan_summary)
    status["scan_summary"] = scan_summary
    try:
        status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    except Exception as exc:
        if logger:
            logger.warning("Failed to merge cointegrated pair scan summary into status metadata: %s", exc)


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
    raw_pairs_with_crossings = 0
    crossing_reject_examples = []
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
        max_market_notional = _calculate_max_order_notional(
            last_close,
            info.get("maxMktSz") if isinstance(info, dict) else None,
            info,
            inst_id=sym,
        )
        max_stop_notional = _calculate_max_order_notional(
            last_close,
            info.get("maxStopSz") if isinstance(info, dict) else None,
            info,
            inst_id=sym,
        )
        capacity_values = [
            value
            for value in (max_market_notional, max_stop_notional)
            if value is not None and value > 0
        ]
        order_capacity_usdt = min(capacity_values) if capacity_values else None
        avg_quote_volume = _average_quote_volume(klines, liquidity_window)
        symbol_meta[sym] = {
            "min_qty": min_qty,
            "min_capital": min_capital,
            "last_close": last_close,
            "avg_quote_volume": avg_quote_volume,
            "contract_value_quote": contract_value_quote,
            "max_market_notional": max_market_notional,
            "max_stop_notional": max_stop_notional,
            "order_capacity_usdt": order_capacity_usdt,
            "instrument_info": info,
        }

    symbols = list(series_by_symbol.keys())
    if restricted_tickers:
        before = len(symbols)
        symbols = [sym for sym in symbols if sym not in restricted_tickers]
        restricted_removed = before - len(symbols)
    total_expected_comparisons = len(symbols) * (len(symbols) - 1) // 2
    progress_interval = _env_int("STATBOT_STRATEGY_INTERNAL_COINT_PROGRESS_INTERVAL", 250, minimum=0)
    progress_percent_step = _env_float("STATBOT_STRATEGY_INTERNAL_COINT_PROGRESS_PERCENT_STEP", 5.0)
    if progress_percent_step <= 0:
        progress_percent_step = 5.0
    next_progress_percent = progress_percent_step

    def _emit_coint_progress(force=False):
        nonlocal next_progress_percent
        if total_expected_comparisons <= 0:
            return
        if progress_interval <= 0 and not force:
            return
        pct_done = (total_comparisons / total_expected_comparisons) * 100.0
        should_emit = bool(force)
        if not should_emit and progress_interval > 0 and total_comparisons % progress_interval == 0:
            should_emit = True
        if not should_emit and pct_done >= next_progress_percent:
            should_emit = True
        if not should_emit:
            return
        while next_progress_percent <= pct_done:
            next_progress_percent += progress_percent_step
        filled = int((min(100.0, pct_done) / 100.0) * 24)
        bar = "#" * filled + "-" * (24 - filled)
        message = (
            f"Cointegration progress: [{bar}] "
            f"{total_comparisons}/{total_expected_comparisons} pairs "
            f"{pct_done:.0f}% | pre_filter_candidates={len(coint_pair_list)} "
            f"pre_filter_crossings={pairs_with_crossings}"
        )
        logger.info(message)

    if corr_min_override is not None:
        try:
            corr_min = float(corr_min_override)
        except (TypeError, ValueError):
            corr_min = 0.0
    else:
        corr_min = corr_min_filter if fast_path_enabled else 0.0

    # Load pair exclusions so hospital/graveyard pairs do not stay in supply.
    excluded_pair_reasons = {}
    try:
        excluded_pair_reasons, exclusion_counts = _load_pair_exclusion_reasons()
        if exclusion_counts.get("graveyard"):
            logger.info(
                "Loaded %d pairs from graveyard (will exclude from discovery)",
                exclusion_counts["graveyard"],
            )
        if exclusion_counts.get("hospital"):
            logger.info(
                "Loaded %d active hospital pairs (will exclude from discovery until cooldown expires)",
                exclusion_counts["hospital"],
            )
        if exclusion_counts.get("expired_hospital"):
            logger.info(
                "Found %d expired hospital entries in state (already eligible for discovery).",
                exclusion_counts["expired_hospital"],
            )
    except Exception as e:
        logger.warning(f"Could not load graveyard/hospital: {e}")

    filtered_breakdown = {}
    orderbook_cache = {}
    orderbook_soft_pass_tickers = set()
    order_capacity_logged = set()

    def _order_capacity_passes(ticker):
        if not min_order_capacity_usdt or min_order_capacity_usdt <= 0:
            return True
        capacity = symbol_meta.get(ticker, {}).get("order_capacity_usdt")
        if capacity is None:
            return True
        if capacity >= min_order_capacity_usdt:
            return True
        if ticker not in order_capacity_logged:
            logger.info(
                "Skipping low OKX order capacity: %s (capacity=%.2f USDT, min=%.2f USDT)",
                ticker,
                capacity,
                min_order_capacity_usdt,
            )
            order_capacity_logged.add(ticker)
        return False

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

            weak_depth_usdt = min(bid_depth_usdt, ask_depth_usdt)
            strong_depth_usdt = max(bid_depth_usdt, ask_depth_usdt)
            imbalance = (
                strong_depth_usdt / weak_depth_usdt
                if weak_depth_usdt > 0
                else float("inf")
            )
            hard_ok = bid_depth_usdt >= min_orderbook_depth_usdt and ask_depth_usdt >= min_orderbook_depth_usdt
            soft_ok = (
                not hard_ok
                and soft_orderbook_depth_usdt > 0
                and weak_depth_usdt >= soft_orderbook_depth_usdt
                and (
                    max_orderbook_imbalance <= 0
                    or imbalance <= max_orderbook_imbalance
                )
            )
            pass_mode = "strict" if hard_ok else ("soft" if soft_ok else "fail")
            result = {
                "ok": hard_ok or soft_ok,
                "reason": "orderbook_depth",
                "bid_depth_usdt": bid_depth_usdt,
                "ask_depth_usdt": ask_depth_usdt,
                "weak_depth_usdt": weak_depth_usdt,
                "orderbook_imbalance": imbalance,
                "pass_mode": pass_mode,
            }
            if not result["ok"]:
                logger.info(
                    "Skipping low liquidity: %s (bid_depth=%.0f USDT, ask_depth=%.0f USDT, min=%.0f USDT, soft_min=%.0f USDT, imbalance=%.2fx, max_imbalance=%.2fx)",
                    ticker,
                    bid_depth_usdt,
                    ask_depth_usdt,
                    min_orderbook_depth_usdt,
                    soft_orderbook_depth_usdt,
                    imbalance,
                    max_orderbook_imbalance,
                )
            elif soft_ok:
                orderbook_soft_pass_tickers.add(ticker)
                logger.info(
                    "Liquidity soft-pass: %s (bid_depth=%.0f USDT, ask_depth=%.0f USDT, hard_min=%.0f USDT, soft_min=%.0f USDT, imbalance=%.2fx)",
                    ticker,
                    bid_depth_usdt,
                    ask_depth_usdt,
                    min_orderbook_depth_usdt,
                    soft_orderbook_depth_usdt,
                    imbalance,
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
        _emit_coint_progress()

        # Skip hospital/graveyard pairs
        pair_key = f"{sym_1}/{sym_2}"
        pair_state_key = _normalize_pair_key_text(pair_key)
        exclusion_reason = excluded_pair_reasons.get(pair_state_key)
        if exclusion_reason:
            filtered_breakdown[exclusion_reason] = filtered_breakdown.get(exclusion_reason, 0) + 1
            continue

        if not _order_capacity_passes(sym_1) or not _order_capacity_passes(sym_2):
            filtered_breakdown["order_capacity"] = filtered_breakdown.get("order_capacity", 0) + 1
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
                raw_pairs_with_crossings += 1

            # Orderbook depth check - ensure sufficient USDT liquidity
            orderbook_check_passed = True
            orderbook_reject_reason = None

            for ticker in [sym_1, sym_2]:
                orderbook_status = _get_orderbook_liquidity_status(ticker)
                if not orderbook_status.get("ok"):
                    reason = orderbook_status.get("reason") or "orderbook_fetch_error"
                    filtered_breakdown[reason] = filtered_breakdown.get(reason, 0) + 1
                    orderbook_reject_reason = reason
                    orderbook_check_passed = False
                    break

            if not orderbook_check_passed:
                if zero_crossings > 0 and len(crossing_reject_examples) < 5:
                    crossing_reject_examples.append(
                        {
                            "pair": pair_key,
                            "reason": orderbook_reject_reason or "orderbook",
                            "zero_crossing": int(zero_crossings),
                            "p_value": float(p_value),
                        }
                    )
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
            max_market_1 = symbol_meta.get(sym_1, {}).get("max_market_notional")
            max_market_2 = symbol_meta.get(sym_2, {}).get("max_market_notional")
            max_stop_1 = symbol_meta.get(sym_1, {}).get("max_stop_notional")
            max_stop_2 = symbol_meta.get(sym_2, {}).get("max_stop_notional")
            order_capacity_1 = symbol_meta.get(sym_1, {}).get("order_capacity_usdt")
            order_capacity_2 = symbol_meta.get(sym_2, {}).get("order_capacity_usdt")
            pair_order_capacity = None
            if order_capacity_1 is not None and order_capacity_2 is not None:
                pair_order_capacity = min(order_capacity_1, order_capacity_2)

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
                "min_capital_1": min_cap_1 if min_cap_1 > 0 else None,
                "min_capital_2": min_cap_2 if min_cap_2 > 0 else None,
                "min_capital_per_leg": required_floor,
                "min_equity_recommended": min_equity,
                "avg_quote_volume_1": avg_vol_1,
                "avg_quote_volume_2": avg_vol_2,
                "pair_liquidity_min": pair_liquidity,
                "max_market_notional_1": max_market_1,
                "max_market_notional_2": max_market_2,
                "max_stop_notional_1": max_stop_1,
                "max_stop_notional_2": max_stop_2,
                "order_capacity_usdt_1": order_capacity_1,
                "order_capacity_usdt_2": order_capacity_2,
                "pair_order_capacity_usdt": pair_order_capacity,
            })

    _emit_coint_progress(force=True)

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

    active_max_supply_pairs = max(int(max_supply_pairs or 10), 1)
    if not df_coint.empty and len(df_coint) > active_max_supply_pairs:
        before = len(df_coint)
        sort_columns = [col for col in ("zero_crossing", "p_value") if col in df_coint.columns]
        if sort_columns:
            ascending = [False if col == "zero_crossing" else True for col in sort_columns]
            df_coint = df_coint.sort_values(by=sort_columns, ascending=ascending)
        df_coint = df_coint.head(active_max_supply_pairs).copy()
        filtered_breakdown["supply_cap"] = before - len(df_coint)

    usable_pairs_with_crossings = 0
    if not df_coint.empty and "zero_crossing" in df_coint.columns:
        usable_zero_crossings = pd.to_numeric(df_coint["zero_crossing"], errors="coerce").fillna(0)
        usable_pairs_with_crossings = int((usable_zero_crossings > 0).sum())
    usable_pairs_without_crossings = int(len(df_coint) - usable_pairs_with_crossings)
    crossing_candidates_filtered_later = max(int(pairs_with_crossings) - usable_pairs_with_crossings, 0)

    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "2_cointegrated_pairs.csv"
    output_status = _write_cointegrated_pairs_csv(
        df_coint,
        output_path,
        logger=logger,
        max_rows=active_max_supply_pairs,
    )
    accumulation_cap_filtered = int(output_status.get("accumulation_cap_filtered") or 0)
    if accumulation_cap_filtered:
        filtered_breakdown["accumulation_cap"] = accumulation_cap_filtered
    summary = {
        "total_pairs": total_comparisons,
        "cointegrated_pairs": len(coint_pair_list),
        "pairs_with_crossings": pairs_with_crossings,
        "pairs_without_crossings": len(coint_pair_list) - pairs_with_crossings,
        "pre_filter_pairs_with_crossings": pairs_with_crossings,
        "pre_filter_pairs_without_crossings": len(coint_pair_list) - pairs_with_crossings,
        "usable_pairs_with_crossings": usable_pairs_with_crossings,
        "usable_pairs_without_crossings": usable_pairs_without_crossings,
        "crossing_candidates_filtered_later": crossing_candidates_filtered_later,
        "raw_pairs_with_crossings": raw_pairs_with_crossings,
        "crossing_rejected_by_orderbook": max(raw_pairs_with_crossings - pairs_with_crossings, 0),
        "crossing_reject_examples": crossing_reject_examples,
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
        "orderbook_depth_hard_min_usdt": min_orderbook_depth_usdt,
        "orderbook_depth_soft_min_usdt": soft_orderbook_depth_usdt,
        "orderbook_max_imbalance": max_orderbook_imbalance,
        "orderbook_soft_pass_tickers": len(orderbook_soft_pass_tickers),
        "order_capacity_min_usdt": min_order_capacity_usdt,
        "order_capacity_filtered": filtered_breakdown.get("order_capacity", 0),
        "max_supply_pairs": active_max_supply_pairs,
        "canonical_pairs_rows": output_status.get("canonical_rows"),
        "canonical_pairs_updated": output_status.get("canonical_updated"),
        "latest_attempt_rows": output_status.get("latest_attempt_rows"),
        "latest_attempt_valid_rows": output_status.get("latest_attempt_valid_rows"),
        "preserved_existing_pairs_csv": output_status.get("preserved_existing"),
        "accumulated_supply": output_status.get("accumulated_supply"),
        "previous_canonical_rows": output_status.get("previous_canonical_rows"),
        "accumulated_pairs_added": output_status.get("accumulated_pairs_added"),
        "accumulated_pairs_refreshed": output_status.get("accumulated_pairs_refreshed"),
        "accumulated_pairs_retained": output_status.get("accumulated_pairs_retained"),
        "accumulation_cap_filtered": accumulation_cap_filtered,
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

    _write_cointegration_status_summary(output_path, summary, logger=logger)
    logger.info("Cointegration summary: %s", summary)

    return df_coint, summary
