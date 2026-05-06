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
    time_frame,
    market_session,
)
import time
import os
from pathlib import Path
import json
import hashlib
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
    count_mean_reversion_crossings,
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


def _env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return bool(default)
    return str(raw).strip().lower() in ("1", "true", "yes", "y", "on")


def _coerce_float_or_default(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int_or_default(value, default):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


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
    return count_mean_reversion_crossings(
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


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


_EPOCH_MS_MIN = 1_000_000_000_000


def _parse_timeframe_ms(value):
    text = str(value or "").strip()
    if not text:
        return None
    idx = 0
    while idx < len(text) and text[idx].isdigit():
        idx += 1
    if idx == 0:
        return None
    try:
        amount = int(text[:idx])
    except ValueError:
        return None
    if amount <= 0:
        return None
    unit = text[idx:]
    if unit == "m":
        return amount * 60_000
    if unit in ("H", "h"):
        return amount * 60 * 60_000
    if unit in ("D", "d"):
        return amount * 24 * 60 * 60_000
    if unit in ("W", "w"):
        return amount * 7 * 24 * 60 * 60_000
    return None


def _coerce_timestamp_ms(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _empty_quality_result(tier, reasons, **extra):
    result = {
        "tier": tier,
        "reason_codes": list(reasons),
        "close_prices": [],
        "timestamps": [],
        "raw_timestamps": [],
        "dropped_forming_candles": 0,
        "missing_bars": 0,
        "duplicate_timestamps": 0,
        "epoch_timestamps": False,
    }
    result.update(extra)
    return result


def validate_kline_series(
    klines,
    *,
    bar_ms=None,
    now_ms=None,
    closed_candle_only=None,
    max_missing_bars=None,
    max_stale_bars=None,
):
    """
    Validate one symbol's candle series for discovery.

    Tier 1 is tradable. Tier 2 is clean enough for analysis-only diagnostics
    but excluded from tradable pair generation. Tier 3 is excluded.
    """
    if closed_candle_only is None:
        closed_candle_only = _env_bool("STATBOT_STRATEGY_CLOSED_CANDLE_ONLY", True)
    if max_missing_bars is None:
        max_missing_bars = _env_int("STATBOT_STRATEGY_DATA_MAX_MISSING_BARS_ANALYSIS", 2, minimum=0)
    if max_stale_bars is None:
        max_stale_bars = _env_int("STATBOT_STRATEGY_DATA_MAX_STALE_BARS", 5, minimum=0)
    close_grace_ms = _env_int("STATBOT_STRATEGY_CANDLE_CLOSE_GRACE_MS", 0, minimum=0)
    if now_ms is None:
        now_ms = int(time.time() * 1000)

    if not klines:
        return _empty_quality_result("tier_3", ["no_klines"])

    rows = []
    reasons = []
    invalid_close_count = 0
    missing_timestamp_count = 0
    invalid_row_count = 0
    for idx, row in enumerate(klines):
        if not isinstance(row, dict):
            invalid_row_count += 1
            continue

        close = _safe_float(row.get("close"))
        if close is None or not np.isfinite(close) or close <= 0:
            invalid_close_count += 1
            continue

        timestamp = _coerce_timestamp_ms(row.get("timestamp"))
        if timestamp is None:
            missing_timestamp_count += 1

        rows.append(
            {
                "index": idx,
                "timestamp": timestamp,
                "close": close,
            }
        )

    if invalid_row_count:
        reasons.append("invalid_row")
    if invalid_close_count:
        reasons.append("invalid_close")
    if missing_timestamp_count:
        reasons.append("missing_timestamp")
    if invalid_row_count or invalid_close_count or missing_timestamp_count:
        return _empty_quality_result(
            "tier_3",
            reasons,
            invalid_rows=invalid_row_count,
            invalid_closes=invalid_close_count,
            missing_timestamps=missing_timestamp_count,
        )
    if len(rows) < 2:
        return _empty_quality_result("tier_3", ["too_few_candles"])

    original_timestamps = [row["timestamp"] for row in rows]
    timestamp_set = set(original_timestamps)
    duplicate_count = len(original_timestamps) - len(timestamp_set)
    if duplicate_count:
        return _empty_quality_result(
            "tier_3",
            ["duplicate_timestamp"],
            duplicate_timestamps=duplicate_count,
        )

    rows = sorted(rows, key=lambda item: item["timestamp"])
    if [row["timestamp"] for row in rows] != original_timestamps:
        reasons.append("sorted_timestamps")

    raw_timestamps = [row["timestamp"] for row in rows]
    epoch_timestamps = bool(raw_timestamps and max(raw_timestamps) >= _EPOCH_MS_MIN)
    dropped_forming = 0
    if closed_candle_only and epoch_timestamps and bar_ms and bar_ms > 0:
        closed_cutoff = int(now_ms) - int(bar_ms) - close_grace_ms
        closed_rows = [row for row in rows if row["timestamp"] <= closed_cutoff]
        dropped_forming = len(rows) - len(closed_rows)
        if dropped_forming:
            reasons.append("forming_candle_dropped")
        rows = closed_rows
        if len(rows) < 2:
            return _empty_quality_result(
                "tier_3",
                ["no_closed_candles"],
                dropped_forming_candles=dropped_forming,
                epoch_timestamps=epoch_timestamps,
            )

    raw_timestamps = [row["timestamp"] for row in rows]
    alignment_timestamps = [
        timestamp + int(bar_ms)
        if epoch_timestamps and bar_ms and bar_ms > 0
        else timestamp
        for timestamp in raw_timestamps
    ]

    missing_bars = 0
    bad_gap = False
    if epoch_timestamps and bar_ms and bar_ms > 0:
        for prev_ts, next_ts in zip(raw_timestamps, raw_timestamps[1:]):
            gap = next_ts - prev_ts
            if gap <= 0:
                bad_gap = True
                continue
            if gap == bar_ms:
                continue
            if gap % bar_ms != 0:
                bad_gap = True
                continue
            missing_bars += max((gap // bar_ms) - 1, 0)
        if bad_gap:
            reasons.append("bad_alignment")
        if missing_bars:
            reasons.append("missing_bars")

        if max_stale_bars and max_stale_bars > 0:
            last_close_ts = raw_timestamps[-1] + int(bar_ms)
            stale_cutoff = int(max_stale_bars) * int(bar_ms)
            if int(now_ms) - last_close_ts > stale_cutoff:
                reasons.append("stale")

    close_prices = [row["close"] for row in rows]
    if len(set(close_prices)) == 1:
        reasons.append("zero_variance")

    tier = "tier_1"
    if any(reason in reasons for reason in ("bad_alignment", "stale", "zero_variance")):
        tier = "tier_3"
    elif missing_bars:
        tier = "tier_2" if missing_bars <= max_missing_bars else "tier_3"

    if tier == "tier_3":
        close_prices = []
        alignment_timestamps = []
        raw_timestamps = []

    return {
        "tier": tier,
        "reason_codes": reasons,
        "close_prices": close_prices,
        "timestamps": alignment_timestamps,
        "raw_timestamps": raw_timestamps,
        "dropped_forming_candles": dropped_forming,
        "missing_bars": int(missing_bars),
        "duplicate_timestamps": 0,
        "epoch_timestamps": epoch_timestamps,
    }


# Put close prices into a list
def extract_close_prices(klines):
    quality = validate_kline_series(
        klines,
        closed_candle_only=False,
        max_stale_bars=0,
    )
    if quality.get("tier") == "tier_3":
        return []
    return quality.get("close_prices") or []


_PAIR_METRIC_CACHE_VERSION = 1
_ORDERBOOK_LIQUIDITY_CACHE_VERSION = 1


def _stable_float_array(values):
    return np.ascontiguousarray(values, dtype="<f8")


def _stable_int_array(values):
    source = [] if values is None else values
    return np.ascontiguousarray(list(source), dtype="<i8")


def _series_content_signature(log_series, timestamps):
    log_values = _stable_float_array(log_series)
    timestamp_values = _stable_int_array(timestamps)
    hasher = hashlib.blake2b(digest_size=20)
    hasher.update(b"series-v1")
    hasher.update(timestamp_values.tobytes())
    hasher.update(log_values.tobytes())
    return {
        "hash": hasher.hexdigest(),
        "length": int(log_values.size),
        "first_ts": int(timestamp_values[0]) if timestamp_values.size else None,
        "last_ts": int(timestamp_values[-1]) if timestamp_values.size else None,
    }


def _metric_config_signature():
    payload = {
        "version": _PAIR_METRIC_CACHE_VERSION,
        "z_score_window": int(z_score_window),
        "pvalue_threshold": float(shared_coint_pvalue_threshold),
        "zero_cross_threshold_ratio": float(cointegration_zero_cross_threshold_ratio),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.blake2b(encoded, digest_size=16).hexdigest(), payload


def _pair_metric_cache_key(sym_1, signature_1, sym_2, signature_2, config_hash):
    payload = {
        "sym_1": str(sym_1),
        "sig_1": signature_1.get("hash"),
        "sym_2": str(sym_2),
        "sig_2": signature_2.get("hash"),
        "config": config_hash,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.blake2b(encoded, digest_size=24).hexdigest()


def _metric_value_or_none(value):
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(result):
        return None
    return result


def _decode_pair_metric_result(entry):
    if not isinstance(entry, dict):
        return None
    result = entry.get("result")
    if not isinstance(result, list) or len(result) != 6:
        return None
    try:
        return (
            int(result[0] or 0),
            _metric_value_or_none(result[1]),
            _metric_value_or_none(result[2]),
            _metric_value_or_none(result[3]),
            _metric_value_or_none(result[4]),
            int(result[5] or 0),
        )
    except (TypeError, ValueError):
        return None


def _encode_pair_metric_result(metrics):
    coint_flag, p_value, adf_statistic, critical_values, hedge_ratio, zero_crossings = metrics
    return [
        int(coint_flag or 0),
        _metric_value_or_none(p_value),
        _metric_value_or_none(adf_statistic),
        _metric_value_or_none(critical_values),
        _metric_value_or_none(hedge_ratio),
        int(zero_crossings or 0),
    ]


def _load_pair_metric_cache(path, logger=None):
    data = _read_json_object(path)
    if data.get("version") != _PAIR_METRIC_CACHE_VERSION:
        return {}, 0
    entries = data.get("entries")
    if not isinstance(entries, dict):
        return {}, 0
    return entries, len(entries)


def _write_pair_metric_cache(path, entries, *, max_entries=None, logger=None):
    if not isinstance(entries, dict):
        entries = {}
    pruned = 0
    if max_entries is not None and max_entries >= 0 and len(entries) > max_entries:
        def _entry_used_at(item):
            entry = item[1] if isinstance(item[1], dict) else {}
            return float(entry.get("used_at") or entry.get("updated_at_unix") or 0)

        sorted_entries = sorted(
            entries.items(),
            key=_entry_used_at,
            reverse=True,
        )
        pruned = len(entries) - max_entries
        entries = dict(sorted_entries[:max_entries])

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": _PAIR_METRIC_CACHE_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "entries": entries,
    }
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        temp_path.replace(path)
    except Exception as exc:
        if logger:
            logger.warning("Failed to write pair metric cache: %s", exc)
        return {"entries": len(entries), "pruned": pruned, "write_error": str(exc)}
    return {"entries": len(entries), "pruned": pruned, "write_error": None}


def _load_orderbook_liquidity_cache(path):
    data = _read_json_object(path)
    if data.get("version") != _ORDERBOOK_LIQUIDITY_CACHE_VERSION:
        return {}, 0
    entries = data.get("entries")
    if not isinstance(entries, dict):
        return {}, 0
    return entries, len(entries)


def _write_orderbook_liquidity_cache(path, entries, *, max_entries=None, logger=None):
    if not isinstance(entries, dict):
        entries = {}
    pruned = 0
    if max_entries is not None and max_entries >= 0 and len(entries) > max_entries:
        def _entry_used_at(item):
            entry = item[1] if isinstance(item[1], dict) else {}
            return float(entry.get("used_at") or entry.get("fetched_at_unix") or 0)

        sorted_entries = sorted(entries.items(), key=_entry_used_at, reverse=True)
        pruned = len(entries) - max_entries
        entries = dict(sorted_entries[:max_entries])

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": _ORDERBOOK_LIQUIDITY_CACHE_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "entries": entries,
    }
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        temp_path.replace(path)
    except Exception as exc:
        if logger:
            logger.warning("Failed to write orderbook liquidity cache: %s", exc)
        return {"entries": len(entries), "pruned": pruned, "write_error": str(exc)}
    return {"entries": len(entries), "pruned": pruned, "write_error": None}


def _orderbook_spread_bps(bids, asks):
    best_bid = _safe_float(bids[0][0]) if bids and len(bids[0]) > 0 else None
    best_ask = _safe_float(asks[0][0]) if asks and len(asks[0]) > 0 else None
    if best_bid is None or best_ask is None or best_bid <= 0 or best_ask <= 0:
        return None
    mid = (best_bid + best_ask) / 2.0
    if mid <= 0 or best_ask < best_bid:
        return None
    return ((best_ask - best_bid) / mid) * 10_000.0


def _orderbook_quality_score(weak_depth_usdt, hard_depth_usdt, imbalance, max_imbalance, age_seconds, ttl_seconds):
    depth_score = 1.0
    if hard_depth_usdt and hard_depth_usdt > 0:
        depth_score = max(0.0, min(float(weak_depth_usdt or 0.0) / float(hard_depth_usdt), 1.0))

    imbalance_score = 1.0
    if imbalance is None or not np.isfinite(imbalance):
        imbalance_score = 0.0
    elif max_imbalance and max_imbalance > 1:
        imbalance_score = max(0.0, min((float(max_imbalance) - float(imbalance)) / (float(max_imbalance) - 1.0), 1.0))

    freshness_score = 1.0
    if ttl_seconds and ttl_seconds > 0:
        freshness_score = max(0.0, min(1.0 - (float(age_seconds or 0.0) / float(ttl_seconds)), 1.0))

    return round((0.55 * depth_score) + (0.30 * imbalance_score) + (0.15 * freshness_score), 4)


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
    previous_status = _read_json_object(status_path)

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

    now_iso = datetime.now(timezone.utc).isoformat()
    previous_generation = str(previous_status.get("pair_universe_generation") or "").strip()
    pair_universe_generation = now_iso if canonical_updated or not previous_generation else previous_generation
    curator_ready = bool(previous_status.get("curator_ready")) if not canonical_updated else False
    previous_curator_generation = str(previous_status.get("curator_generation") or "").strip()
    curator_generation = previous_curator_generation if curator_ready else None
    if curator_generation and curator_generation != pair_universe_generation:
        curator_ready = False
        curator_generation = None

    status = {
        "updated_at": now_iso,
        "canonical_path": str(output_path),
        "latest_attempt_path": str(latest_attempt_path),
        "pair_universe_generation": pair_universe_generation,
        "curator_ready": curator_ready,
        "curator_generation": curator_generation,
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
        "data_quality",
        "timestamp_alignment_filtered",
        "pair_metric_cache",
        "orderbook_cache",
        "validation_tiers",
        "accuracy_budget",
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
    max_supply_pairs_override=None,
    write_output=True,
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

    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    metric_cache_path = output_dir / "pair_metric_cache.json"
    metric_cache_enabled = _env_bool("STATBOT_STRATEGY_PAIR_METRIC_CACHE", True)
    metric_cache_max_entries = _env_int("STATBOT_STRATEGY_PAIR_METRIC_CACHE_MAX_ENTRIES", 50000, minimum=0)
    metric_cache_entries = {}
    metric_cache_loaded_entries = 0
    if metric_cache_enabled:
        metric_cache_entries, metric_cache_loaded_entries = _load_pair_metric_cache(
            metric_cache_path,
            logger=logger,
        )
    metric_config_hash, metric_config = _metric_config_signature()
    metric_cache_stats = {
        "enabled": bool(metric_cache_enabled),
        "persisted": bool(metric_cache_enabled and write_output),
        "path": str(metric_cache_path),
        "loaded_entries": metric_cache_loaded_entries,
        "hits": 0,
        "misses": 0,
        "writes": 0,
        "entries": metric_cache_loaded_entries,
        "pruned": 0,
        "write_error": None,
        "max_entries": metric_cache_max_entries,
        "config": metric_config,
    }
    metric_cache_dirty = False
    scan_time = time.time()
    scan_unix = int(scan_time)

    orderbook_cache_path = output_dir / "orderbook_liquidity_cache.json"
    orderbook_cache_ttl_seconds = _env_float(
        "STATBOT_STRATEGY_ORDERBOOK_CACHE_TTL_SECONDS",
        15.0,
        minimum=0.0,
    )
    orderbook_persistent_cache_enabled = _env_bool(
        "STATBOT_STRATEGY_ORDERBOOK_CACHE",
        True,
    ) and orderbook_cache_ttl_seconds > 0
    orderbook_cache_max_entries = _env_int(
        "STATBOT_STRATEGY_ORDERBOOK_CACHE_MAX_ENTRIES",
        5000,
        minimum=0,
    )
    orderbook_persistent_entries = {}
    orderbook_cache_loaded_entries = 0
    if orderbook_persistent_cache_enabled:
        orderbook_persistent_entries, orderbook_cache_loaded_entries = _load_orderbook_liquidity_cache(
            orderbook_cache_path
        )
    orderbook_cache_dirty = False
    orderbook_quality_samples = []
    orderbook_cache_stats = {
        "enabled": bool(orderbook_persistent_cache_enabled),
        "persisted": bool(orderbook_persistent_cache_enabled and write_output),
        "path": str(orderbook_cache_path),
        "ttl_seconds": orderbook_cache_ttl_seconds,
        "loaded_entries": orderbook_cache_loaded_entries,
        "hits": 0,
        "misses": 0,
        "stale_entries": 0,
        "live_fetches": 0,
        "writes": 0,
        "recheck_needed": 0,
        "entries": orderbook_cache_loaded_entries,
        "pruned": 0,
        "write_error": None,
        "source_counts": {},
        "pass_modes": {},
        "quality_score_min": None,
        "quality_score_avg": None,
    }

    bar_ms = _parse_timeframe_ms(time_frame)
    closed_candle_only = _env_bool("STATBOT_STRATEGY_CLOSED_CANDLE_ONLY", True)
    max_missing_bars = _env_int("STATBOT_STRATEGY_DATA_MAX_MISSING_BARS_ANALYSIS", 2, minimum=0)
    max_stale_bars = _env_int("STATBOT_STRATEGY_DATA_MAX_STALE_BARS", 5, minimum=0)
    now_ms = int(scan_time * 1000)
    data_quality = {
        "total_symbols": len(json_symbols),
        "tradable_symbols": 0,
        "analysis_only_symbols": 0,
        "excluded_symbols": 0,
        "tier_counts": {"tier_1": 0, "tier_2": 0, "tier_3": 0},
        "reason_counts": {},
        "closed_candle_only": bool(closed_candle_only),
        "timeframe": time_frame,
        "bar_ms": bar_ms,
        "max_missing_bars_analysis_only": max_missing_bars,
        "max_stale_bars": max_stale_bars,
    }

    def _record_quality(quality):
        tier = str(quality.get("tier") or "tier_3")
        if tier not in data_quality["tier_counts"]:
            data_quality["tier_counts"][tier] = 0
        data_quality["tier_counts"][tier] += 1
        if tier == "tier_1":
            data_quality["tradable_symbols"] += 1
        elif tier == "tier_2":
            data_quality["analysis_only_symbols"] += 1
        else:
            data_quality["excluded_symbols"] += 1
        for reason in quality.get("reason_codes") or ["unknown"]:
            reason_text = str(reason or "unknown")
            data_quality["reason_counts"][reason_text] = (
                data_quality["reason_counts"].get(reason_text, 0) + 1
            )

    series_by_symbol = {}
    log_series_by_symbol = {}
    returns_by_symbol = {}
    timestamps_by_symbol = {}
    symbol_signatures = {}
    symbol_meta = {}
    for sym, data in json_symbols.items():
        klines = data.get('klines', []) if isinstance(data, dict) else []
        quality = validate_kline_series(
            klines,
            bar_ms=bar_ms,
            now_ms=now_ms,
            closed_candle_only=closed_candle_only,
            max_missing_bars=max_missing_bars,
            max_stale_bars=max_stale_bars,
        )
        _record_quality(quality)
        if quality.get("tier") != "tier_1":
            continue

        series = quality.get("close_prices") or []
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
        timestamp_tuple = tuple(quality.get("timestamps") or ())
        timestamps_by_symbol[sym] = timestamp_tuple
        symbol_signatures[sym] = _series_content_signature(log_series, timestamp_tuple)
        returns = np.diff(log_series)
        if corr_lookback and corr_lookback > 0 and returns.size > corr_lookback:
            returns = returns[-corr_lookback:]
        returns_by_symbol[sym] = returns
        return_std = float(np.std(returns)) if returns.size >= 2 else None

        info = data.get('symbol_info', {}) if isinstance(data, dict) else {}
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
            "return_std": return_std,
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

    active_liquidity_pct = liquidity_pct
    if liquidity_pct_override is not None:
        active_liquidity_pct = _coerce_float_or_default(liquidity_pct_override, active_liquidity_pct)
    active_min_avg_quote_volume = min_avg_quote_volume
    if min_avg_quote_volume_override is not None:
        active_min_avg_quote_volume = _coerce_float_or_default(
            min_avg_quote_volume_override,
            active_min_avg_quote_volume,
        )

    active_min_p_value = min_p_value_filter
    if min_p_value_override is not None:
        active_min_p_value = _coerce_float_or_default(min_p_value_override, active_min_p_value)
    active_max_p_value = max_p_value_filter
    if max_p_value_override is not None:
        active_max_p_value = _coerce_float_or_default(max_p_value_override, active_max_p_value)

    active_zero_crossings = min_zero_crossings
    if min_zero_crossings_override is not None:
        active_zero_crossings = _coerce_int_or_default(min_zero_crossings_override, active_zero_crossings)

    active_min_capital_per_leg = min_capital_per_leg
    if min_capital_per_leg_override is not None:
        active_min_capital_per_leg = _coerce_float_or_default(
            min_capital_per_leg_override,
            active_min_capital_per_leg,
        )

    active_min_equity_filter = min_equity_filter_usdt
    if min_equity_filter_override is not None:
        active_min_equity_filter = _coerce_float_or_default(
            min_equity_filter_override,
            active_min_equity_filter,
        )

    prefilter_vol_ratio_max = _env_float(
        "STATBOT_STRATEGY_PREFILTER_VOL_RATIO_MAX",
        0.0,
        minimum=0.0,
    )
    prefilter_vol_ratio_enabled = bool(prefilter_vol_ratio_max and prefilter_vol_ratio_max > 0)
    reject_sample_pct = _env_float("STATBOT_STRATEGY_REJECT_SAMPLE_PCT", 0.01, minimum=0.0)
    if reject_sample_pct > 1.0:
        reject_sample_pct = 1.0
    reject_sample_max = _env_int("STATBOT_STRATEGY_REJECT_SAMPLE_MAX", 500, minimum=0)
    reject_sample_reasons_raw = os.getenv(
        "STATBOT_STRATEGY_REJECT_SAMPLE_REASONS",
        "corr,tier0_liquidity_min,tier0_min_capital,tier0_min_equity,tier0_vol_ratio",
    )
    reject_sample_reasons = {
        item.strip()
        for item in str(reject_sample_reasons_raw).split(",")
        if item.strip()
    }
    reject_sample_seed = os.getenv("STATBOT_STRATEGY_REJECT_SAMPLE_SEED", "accuracy-budget-v1")

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
    validation_tiers = {
        "tier_0": {
            "checked_pairs": 0,
            "passed_pairs": 0,
            "filtered_pairs": 0,
            "filtered_breakdown": {},
            "settings": {
                "corr_min": corr_min,
                "min_avg_quote_volume": active_min_avg_quote_volume,
                "min_capital_per_leg": active_min_capital_per_leg,
                "min_equity_filter_usdt": active_min_equity_filter,
                "order_capacity_min_usdt": min_order_capacity_usdt,
                "vol_ratio_max": prefilter_vol_ratio_max if prefilter_vol_ratio_enabled else None,
            },
        },
        "tier_2": {
            "checked_pairs": 0,
            "computed_pairs": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        },
    }
    accuracy_budget = {
        "enabled": bool(reject_sample_pct > 0 and reject_sample_max != 0 and reject_sample_reasons),
        "sample_pct": reject_sample_pct,
        "max_samples": reject_sample_max,
        "eligible_reasons": sorted(reject_sample_reasons),
        "eligible_rejects": 0,
        "sampled_rejects": 0,
        "shadow_computed": 0,
        "shadow_cache_hits": 0,
        "shadow_cache_misses": 0,
        "missed_cointegrated": 0,
        "missed_with_crossings": 0,
        "missed_stat_candidates": 0,
        "reason_breakdown": {},
        "examples": [],
    }

    def _record_tier0_filter(reason):
        filtered_breakdown[reason] = filtered_breakdown.get(reason, 0) + 1
        tier0 = validation_tiers["tier_0"]
        tier0["filtered_pairs"] += 1
        tier0["filtered_breakdown"][reason] = tier0["filtered_breakdown"].get(reason, 0) + 1

    def _accuracy_reason_stats(reason):
        reason_text = str(reason or "unknown")
        breakdown = accuracy_budget["reason_breakdown"]
        if reason_text not in breakdown:
            breakdown[reason_text] = {
                "eligible_rejects": 0,
                "sampled_rejects": 0,
                "missed_cointegrated": 0,
                "missed_with_crossings": 0,
                "missed_stat_candidates": 0,
            }
        return breakdown[reason_text]

    def _reject_sample_score(pair_key, reason):
        payload = f"{reject_sample_seed}|{reason}|{pair_key}".encode("utf-8")
        digest = hashlib.blake2b(payload, digest_size=8).digest()
        return int.from_bytes(digest, "big") / float(2**64)

    def _should_shadow_sample_reject(pair_key, reason):
        if not accuracy_budget["enabled"] or reason not in reject_sample_reasons:
            return False
        stats = _accuracy_reason_stats(reason)
        stats["eligible_rejects"] += 1
        accuracy_budget["eligible_rejects"] += 1
        if reject_sample_max and accuracy_budget["sampled_rejects"] >= reject_sample_max:
            return False
        if _reject_sample_score(pair_key, reason) >= reject_sample_pct:
            return False
        stats["sampled_rejects"] += 1
        accuracy_budget["sampled_rejects"] += 1
        return True

    def _metrics_pass_final_stat_filters(metrics):
        coint_flag, p_value, _adf_statistic, _critical_values, hedge_ratio, zero_crossings = metrics
        if int(coint_flag or 0) != 1:
            return False
        if active_min_p_value is not None and active_max_p_value is not None:
            if active_min_p_value > 0 and active_max_p_value > 0 and active_min_p_value < active_max_p_value:
                if p_value is None or p_value < active_min_p_value or p_value > active_max_p_value:
                    return False
        if active_zero_crossings and active_zero_crossings > 0:
            if int(zero_crossings or 0) < active_zero_crossings:
                return False
        if min_hedge_ratio is not None and max_hedge_ratio is not None:
            if min_hedge_ratio >= 0 and max_hedge_ratio > 0 and min_hedge_ratio <= max_hedge_ratio:
                if hedge_ratio is None:
                    return False
                hedge_abs = abs(float(hedge_ratio))
                if hedge_abs < min_hedge_ratio or hedge_abs > max_hedge_ratio:
                    return False
        return True

    def _pair_capital_profile(sym_1, sym_2):
        min_cap_1 = symbol_meta.get(sym_1, {}).get("min_capital", 0.0) or 0.0
        min_cap_2 = symbol_meta.get(sym_2, {}).get("min_capital", 0.0) or 0.0
        required_floor = max(min_cap_1, min_cap_2) if min_cap_1 > 0 and min_cap_2 > 0 else None
        min_equity = required_floor * 2 if required_floor else None
        return min_cap_1, min_cap_2, required_floor, min_equity

    def _pair_liquidity_profile(sym_1, sym_2):
        avg_vol_1 = symbol_meta.get(sym_1, {}).get("avg_quote_volume")
        avg_vol_2 = symbol_meta.get(sym_2, {}).get("avg_quote_volume")
        pair_liquidity = None
        if avg_vol_1 is not None and avg_vol_2 is not None:
            pair_liquidity = min(avg_vol_1, avg_vol_2)
        return avg_vol_1, avg_vol_2, pair_liquidity

    def _tier0_prefilter_pair(sym_1, sym_2):
        if active_min_avg_quote_volume and active_min_avg_quote_volume > 0:
            avg_vol_1, avg_vol_2, _pair_liquidity = _pair_liquidity_profile(sym_1, sym_2)
            if (
                avg_vol_1 is None
                or avg_vol_2 is None
                or avg_vol_1 < active_min_avg_quote_volume
                or avg_vol_2 < active_min_avg_quote_volume
            ):
                return "tier0_liquidity_min"

        if active_min_capital_per_leg is not None and active_min_capital_per_leg > 0:
            _min_cap_1, _min_cap_2, required_floor, _min_equity = _pair_capital_profile(sym_1, sym_2)
            if required_floor is None or required_floor < active_min_capital_per_leg:
                return "tier0_min_capital"

        if active_min_equity_filter and active_min_equity_filter > 0:
            _min_cap_1, _min_cap_2, _required_floor, min_equity = _pair_capital_profile(sym_1, sym_2)
            if min_equity is not None and min_equity > active_min_equity_filter:
                return "tier0_min_equity"

        if prefilter_vol_ratio_enabled:
            vol_1 = symbol_meta.get(sym_1, {}).get("return_std")
            vol_2 = symbol_meta.get(sym_2, {}).get("return_std")
            if vol_1 is None or vol_2 is None or vol_1 <= 0 or vol_2 <= 0:
                return "tier0_vol_ratio"
            vol_ratio = max(vol_1, vol_2) / min(vol_1, vol_2)
            if vol_ratio > prefilter_vol_ratio_max:
                return "tier0_vol_ratio"

        return None

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

    def _record_orderbook_status(status):
        source = str(status.get("source") or "unknown")
        orderbook_cache_stats["source_counts"][source] = (
            orderbook_cache_stats["source_counts"].get(source, 0) + 1
        )
        pass_mode = str(status.get("pass_mode") or "unknown")
        orderbook_cache_stats["pass_modes"][pass_mode] = (
            orderbook_cache_stats["pass_modes"].get(pass_mode, 0) + 1
        )
        quality_score = _metric_value_or_none(status.get("quality_score"))
        if quality_score is not None:
            orderbook_quality_samples.append(quality_score)

    def _cached_orderbook_status(entry, now_unix, *, source):
        if not isinstance(entry, dict):
            return None, None
        fetched_at = _metric_value_or_none(entry.get("fetched_at_unix"))
        if fetched_at is None:
            return None, None
        age_seconds = max(float(now_unix) - fetched_at, 0.0)
        if orderbook_cache_ttl_seconds > 0 and age_seconds > orderbook_cache_ttl_seconds:
            return None, age_seconds
        status = dict(entry)
        status["source"] = source
        status["age_seconds"] = age_seconds
        status["fresh"] = True
        status["cache_ttl_seconds"] = orderbook_cache_ttl_seconds
        status["quality_score"] = _orderbook_quality_score(
            status.get("weak_depth_usdt"),
            min_orderbook_depth_usdt,
            status.get("orderbook_imbalance"),
            max_orderbook_imbalance,
            age_seconds,
            orderbook_cache_ttl_seconds,
        )
        status["used_at"] = int(now_unix)
        return status, age_seconds

    def _persist_orderbook_status(ticker, status):
        nonlocal orderbook_cache_dirty
        orderbook_cache[ticker] = status
        if not orderbook_persistent_cache_enabled or not status.get("cacheable"):
            return
        numeric_keys = {
            "bid_depth_usdt",
            "ask_depth_usdt",
            "weak_depth_usdt",
            "orderbook_imbalance",
            "spread_bps",
            "quality_score",
            "fetched_at_unix",
            "cache_ttl_seconds",
        }
        entry = {}
        for key in (
            "ok",
            "reason",
            "detail",
            "bid_levels",
            "ask_levels",
            "bid_depth_usdt",
            "ask_depth_usdt",
            "weak_depth_usdt",
            "orderbook_imbalance",
            "pass_mode",
            "spread_bps",
            "quality_score",
            "fetched_at_unix",
            "cache_ttl_seconds",
            "fresh",
        ):
            if key not in status:
                continue
            entry[key] = _metric_value_or_none(status.get(key)) if key in numeric_keys else status.get(key)
        entry["used_at"] = int(time.time())
        orderbook_persistent_entries[ticker] = entry
        orderbook_cache_stats["writes"] += 1
        orderbook_cache_dirty = True

    def _get_orderbook_liquidity_status(ticker):
        now_unix = time.time()
        cached = orderbook_cache.get(ticker)
        if cached is not None:
            cached_status, _age = _cached_orderbook_status(cached, now_unix, source=cached.get("source") or "scan_cache")
            if cached_status is not None:
                _record_orderbook_status(cached_status)
                return cached_status
            orderbook_cache_stats["stale_entries"] += 1

        stale_cache_age = None
        if orderbook_persistent_cache_enabled:
            persistent_status, stale_cache_age = _cached_orderbook_status(
                orderbook_persistent_entries.get(ticker),
                now_unix,
                source="persistent_cache",
            )
            if persistent_status is not None:
                orderbook_cache_stats["hits"] += 1
                orderbook_cache[ticker] = persistent_status
                orderbook_persistent_entries[ticker]["used_at"] = int(now_unix)
                _record_orderbook_status(persistent_status)
                return persistent_status
            if stale_cache_age is not None:
                orderbook_cache_stats["stale_entries"] += 1

        orderbook_cache_stats["misses"] += 1
        orderbook_cache_stats["live_fetches"] += 1

        meta = symbol_meta.get(ticker, {})
        instrument_info = meta.get("instrument_info") or {}
        last_close = meta.get("last_close")

        try:
            orderbook_res = market_session.get_orderbook(instId=ticker, sz=50)
            if orderbook_res.get("code") != "0":
                if stale_cache_age is not None:
                    result = {
                        "ok": False,
                        "reason": "orderbook_needs_recheck",
                        "detail": orderbook_res.get("msg") or "stale_cache_refetch_failed",
                        "stale_age_seconds": stale_cache_age,
                        "source": "stale_cache_refetch_failed",
                        "fresh": False,
                        "cache_ttl_seconds": orderbook_cache_ttl_seconds,
                    }
                    orderbook_cache_stats["recheck_needed"] += 1
                    orderbook_cache[ticker] = result
                    _record_orderbook_status(result)
                    return result
                result = {
                    "ok": False,
                    "reason": "orderbook_fetch_error",
                    "detail": orderbook_res.get("msg") or "unknown_error",
                    "source": "live",
                    "fresh": True,
                    "fetched_at_unix": now_unix,
                }
                logger.warning("Failed to fetch orderbook for %s: %s", ticker, result["detail"])
                orderbook_cache[ticker] = result
                _record_orderbook_status(result)
                return result

            data = orderbook_res.get("data", [])
            if not data:
                if stale_cache_age is not None:
                    result = {
                        "ok": False,
                        "reason": "orderbook_needs_recheck",
                        "detail": "empty_data_after_stale_cache",
                        "stale_age_seconds": stale_cache_age,
                        "source": "stale_cache_refetch_failed",
                        "fresh": False,
                        "cache_ttl_seconds": orderbook_cache_ttl_seconds,
                    }
                    orderbook_cache_stats["recheck_needed"] += 1
                    orderbook_cache[ticker] = result
                    _record_orderbook_status(result)
                    return result
                result = {
                    "ok": False,
                    "reason": "orderbook_fetch_error",
                    "detail": "empty_data",
                    "source": "live",
                    "fresh": True,
                    "fetched_at_unix": now_unix,
                }
                logger.warning("Failed to fetch orderbook for %s: empty response data", ticker)
                orderbook_cache[ticker] = result
                _record_orderbook_status(result)
                return result

            bids = data[0].get("bids", [])
            asks = data[0].get("asks", [])
            if len(bids) < min_orderbook_levels or len(asks) < min_orderbook_levels:
                result = {
                    "ok": False,
                    "reason": "orderbook_levels",
                    "bid_levels": len(bids),
                    "ask_levels": len(asks),
                    "source": "live",
                    "fresh": True,
                    "cacheable": True,
                    "fetched_at_unix": now_unix,
                    "cache_ttl_seconds": orderbook_cache_ttl_seconds,
                    "pass_mode": "fail",
                }
                logger.info(
                    "Skipping thin orderbook: %s (bids=%d, asks=%d levels)",
                    ticker,
                    len(bids),
                    len(asks),
                )
                _persist_orderbook_status(ticker, result)
                _record_orderbook_status(result)
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
                    "source": "live",
                    "fresh": True,
                    "fetched_at_unix": now_unix,
                }
                logger.warning("Error calculating orderbook depth for %s: %s", ticker, exc)
                orderbook_cache[ticker] = result
                _record_orderbook_status(result)
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
            spread_bps = _orderbook_spread_bps(bids, asks)
            quality_score = _orderbook_quality_score(
                weak_depth_usdt,
                min_orderbook_depth_usdt,
                imbalance,
                max_orderbook_imbalance,
                0.0,
                orderbook_cache_ttl_seconds,
            )
            result = {
                "ok": hard_ok or soft_ok,
                "reason": "orderbook_depth",
                "bid_depth_usdt": bid_depth_usdt,
                "ask_depth_usdt": ask_depth_usdt,
                "weak_depth_usdt": weak_depth_usdt,
                "orderbook_imbalance": imbalance,
                "pass_mode": pass_mode,
                "spread_bps": spread_bps,
                "quality_score": quality_score,
                "source": "live",
                "fresh": True,
                "cacheable": True,
                "fetched_at_unix": now_unix,
                "age_seconds": 0.0,
                "cache_ttl_seconds": orderbook_cache_ttl_seconds,
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
            _persist_orderbook_status(ticker, result)
            _record_orderbook_status(result)
            return result
        except Exception as exc:
            if stale_cache_age is not None:
                result = {
                    "ok": False,
                    "reason": "orderbook_needs_recheck",
                    "detail": str(exc),
                    "stale_age_seconds": stale_cache_age,
                    "source": "stale_cache_refetch_failed",
                    "fresh": False,
                    "cache_ttl_seconds": orderbook_cache_ttl_seconds,
                }
                orderbook_cache_stats["recheck_needed"] += 1
                orderbook_cache[ticker] = result
                _record_orderbook_status(result)
                return result
            result = {
                "ok": False,
                "reason": "orderbook_fetch_error",
                "detail": str(exc),
                "source": "live",
                "fresh": True,
                "fetched_at_unix": now_unix,
            }
            logger.warning("Error checking orderbook depth for %s: %s", ticker, exc)
            orderbook_cache[ticker] = result
            _record_orderbook_status(result)
            return result

    def _get_pair_metrics(sym_1, sym_2, *, purpose):
        nonlocal metric_cache_dirty
        series_1_log = log_series_by_symbol[sym_1]
        series_2_log = log_series_by_symbol[sym_2]
        cache_key = None
        cached_metrics = None
        if metric_cache_enabled:
            signature_1 = symbol_signatures.get(sym_1)
            signature_2 = symbol_signatures.get(sym_2)
            if signature_1 and signature_2:
                cache_key = _pair_metric_cache_key(
                    sym_1,
                    signature_1,
                    sym_2,
                    signature_2,
                    metric_config_hash,
                )
                cached_metrics = _decode_pair_metric_result(metric_cache_entries.get(cache_key))

        if cached_metrics is not None:
            metric_cache_stats["hits"] += 1
            metric_cache_entries[cache_key]["used_at"] = scan_unix
            metric_cache_dirty = True
            if purpose == "validation":
                validation_tiers["tier_2"]["cache_hits"] += 1
            elif purpose == "accuracy_budget":
                accuracy_budget["shadow_cache_hits"] += 1
            return cached_metrics

        if purpose == "validation":
            validation_tiers["tier_2"]["computed_pairs"] += 1
        elif purpose == "accuracy_budget":
            accuracy_budget["shadow_computed"] += 1

        if metric_cache_enabled:
            metric_cache_stats["misses"] += 1
            if purpose == "validation":
                validation_tiers["tier_2"]["cache_misses"] += 1
            elif purpose == "accuracy_budget":
                accuracy_budget["shadow_cache_misses"] += 1

        metrics = calculate_cointegration_from_log(series_1_log, series_2_log)
        if metric_cache_enabled and cache_key:
            metric_cache_entries[cache_key] = {
                "sym_1": sym_1,
                "sym_2": sym_2,
                "series_1_hash": symbol_signatures[sym_1]["hash"],
                "series_2_hash": symbol_signatures[sym_2]["hash"],
                "config_hash": metric_config_hash,
                "result": _encode_pair_metric_result(metrics),
                "updated_at_unix": scan_unix,
                "used_at": scan_unix,
            }
            metric_cache_stats["writes"] += 1
            metric_cache_dirty = True
        return metrics

    def _maybe_shadow_validate_reject(sym_1, sym_2, pair_key, reason):
        if not _should_shadow_sample_reject(pair_key, reason):
            return
        metrics = _get_pair_metrics(sym_1, sym_2, purpose="accuracy_budget")
        coint_flag, p_value, _adf_statistic, _critical_values, hedge_ratio, zero_crossings = metrics
        stats = _accuracy_reason_stats(reason)
        if int(coint_flag or 0) == 1:
            stats["missed_cointegrated"] += 1
            accuracy_budget["missed_cointegrated"] += 1
            if int(zero_crossings or 0) > 0:
                stats["missed_with_crossings"] += 1
                accuracy_budget["missed_with_crossings"] += 1
            if _metrics_pass_final_stat_filters(metrics):
                stats["missed_stat_candidates"] += 1
                accuracy_budget["missed_stat_candidates"] += 1
            if len(accuracy_budget["examples"]) < 5:
                accuracy_budget["examples"].append(
                    {
                        "pair": pair_key,
                        "reason": reason,
                        "p_value": _metric_value_or_none(p_value),
                        "hedge_ratio": _metric_value_or_none(hedge_ratio),
                        "zero_crossing": int(zero_crossings or 0),
                        "final_stat_pass": bool(_metrics_pass_final_stat_filters(metrics)),
                    }
                )

    def _handle_tier0_reject(sym_1, sym_2, pair_key, reason):
        _record_tier0_filter(reason)
        _maybe_shadow_validate_reject(sym_1, sym_2, pair_key, reason)

    for sym_1, sym_2 in combinations(symbols, 2):
        total_comparisons += 1
        validation_tiers["tier_0"]["checked_pairs"] += 1
        _emit_coint_progress()

        # Skip hospital/graveyard pairs
        pair_key = f"{sym_1}/{sym_2}"
        pair_state_key = _normalize_pair_key_text(pair_key)
        exclusion_reason = excluded_pair_reasons.get(pair_state_key)
        if exclusion_reason:
            _handle_tier0_reject(sym_1, sym_2, pair_key, exclusion_reason)
            continue

        if timestamps_by_symbol.get(sym_1) != timestamps_by_symbol.get(sym_2):
            _handle_tier0_reject(sym_1, sym_2, pair_key, "timestamp_alignment")
            continue

        if not _order_capacity_passes(sym_1) or not _order_capacity_passes(sym_2):
            _handle_tier0_reject(sym_1, sym_2, pair_key, "order_capacity")
            continue

        ret_1 = returns_by_symbol.get(sym_1)
        ret_2 = returns_by_symbol.get(sym_2)
        corr_value = None
        if ret_1 is not None and ret_2 is not None:
            corr_value = _corrcoef_fast(ret_1, ret_2)

        if corr_min and corr_min > 0:
            if corr_value is None or not np.isfinite(corr_value):
                _handle_tier0_reject(sym_1, sym_2, pair_key, "corr")
                continue
            if abs(corr_value) < corr_min:
                _handle_tier0_reject(sym_1, sym_2, pair_key, "corr")
                continue

        tier0_reason = _tier0_prefilter_pair(sym_1, sym_2)
        if tier0_reason:
            _handle_tier0_reject(sym_1, sym_2, pair_key, tier0_reason)
            continue

        validation_tiers["tier_0"]["passed_pairs"] += 1
        validation_tiers["tier_2"]["checked_pairs"] += 1
        coint_flag, p_value, adf_statistic, critical_values, hedge_ratio, zero_crossings = (
            _get_pair_metrics(sym_1, sym_2, purpose="validation")
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

            min_cap_1, min_cap_2, required_floor, min_equity = _pair_capital_profile(sym_1, sym_2)
            avg_vol_1, avg_vol_2, pair_liquidity = _pair_liquidity_profile(sym_1, sym_2)
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
                "correlation": corr_value,
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

    if max_supply_pairs_override is None:
        active_max_supply_pairs = max(int(max_supply_pairs or 10), 1)
    else:
        try:
            active_max_supply_pairs = int(max_supply_pairs_override)
        except (TypeError, ValueError):
            active_max_supply_pairs = max(int(max_supply_pairs or 10), 1)
        if active_max_supply_pairs <= 0:
            active_max_supply_pairs = None
    if active_max_supply_pairs and not df_coint.empty and len(df_coint) > active_max_supply_pairs:
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

    output_path = output_dir / "2_cointegrated_pairs.csv"
    if write_output:
        output_status = _write_cointegrated_pairs_csv(
            df_coint,
            output_path,
            logger=logger,
            max_rows=active_max_supply_pairs,
        )
    else:
        output_status = {
            "canonical_rows": None,
            "canonical_updated": False,
            "latest_attempt_rows": len(df_coint),
            "latest_attempt_valid_rows": len(df_coint),
            "preserved_existing": False,
            "accumulated_supply": False,
            "previous_canonical_rows": _count_csv_rows(output_path),
            "accumulated_pairs_added": 0,
            "accumulated_pairs_refreshed": 0,
            "accumulated_pairs_retained": 0,
            "accumulation_cap_filtered": 0,
        }
    accumulation_cap_filtered = int(output_status.get("accumulation_cap_filtered") or 0)
    if accumulation_cap_filtered:
        filtered_breakdown["accumulation_cap"] = accumulation_cap_filtered
    if metric_cache_enabled and metric_cache_dirty and write_output:
        metric_cache_stats.update(
            _write_pair_metric_cache(
                metric_cache_path,
                metric_cache_entries,
                max_entries=metric_cache_max_entries,
                logger=logger,
            )
        )
    else:
        metric_cache_stats["entries"] = len(metric_cache_entries)
    if orderbook_quality_samples:
        orderbook_cache_stats["quality_score_min"] = float(min(orderbook_quality_samples))
        orderbook_cache_stats["quality_score_avg"] = float(sum(orderbook_quality_samples) / len(orderbook_quality_samples))
    if orderbook_persistent_cache_enabled and orderbook_cache_dirty and write_output:
        orderbook_cache_stats.update(
            _write_orderbook_liquidity_cache(
                orderbook_cache_path,
                orderbook_persistent_entries,
                max_entries=orderbook_cache_max_entries,
                logger=logger,
            )
        )
    else:
        orderbook_cache_stats["entries"] = len(orderbook_persistent_entries)
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
        "data_quality": data_quality,
        "pair_metric_cache": metric_cache_stats,
        "orderbook_cache": orderbook_cache_stats,
        "validation_tiers": validation_tiers,
        "accuracy_budget": accuracy_budget,
        "corr_min": corr_min,
        "corr_lookback": corr_lookback,
        "corr_filtered": filtered_breakdown.get("corr", 0),
        "timestamp_alignment_filtered": filtered_breakdown.get("timestamp_alignment", 0),
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

    if write_output:
        _write_cointegration_status_summary(output_path, summary, logger=logger)
    logger.info("Cointegration summary: %s", summary)

    return df_coint, summary


def save_cointegrated_pairs_result(df_coint, summary=None, logger=None, max_rows=None):
    """Persist a selected in-memory fallback result as the canonical pair universe."""
    logger = logger or get_strategy_logger()
    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "2_cointegrated_pairs.csv"
    summary = dict(summary or {})
    output_status = _write_cointegrated_pairs_csv(
        df_coint,
        output_path,
        logger=logger,
        max_rows=max_rows,
    )
    accumulation_cap_filtered = int(output_status.get("accumulation_cap_filtered") or 0)
    filtered_breakdown = summary.get("filtered_breakdown")
    if not isinstance(filtered_breakdown, dict):
        filtered_breakdown = {}
    if accumulation_cap_filtered:
        filtered_breakdown["accumulation_cap"] = accumulation_cap_filtered
    summary.update(
        {
            "filtered_breakdown": filtered_breakdown,
            "max_supply_pairs": max_rows,
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
            "pairs_kept": int(len(df_coint)),
        }
    )
    if len(df_coint) > 0 and "zero_crossing" in df_coint.columns:
        zc = pd.to_numeric(df_coint["zero_crossing"], errors="coerce").dropna()
        if not zc.empty:
            summary["zero_crossing"] = {
                "min": float(zc.min()),
                "max": float(zc.max()),
                "mean": float(zc.mean()),
                "median": float(zc.median()),
            }
    if "min_capital_per_leg" in df_coint.columns:
        min_caps = pd.to_numeric(df_coint["min_capital_per_leg"], errors="coerce").dropna().tolist()
        if min_caps:
            max_per_leg = max(min_caps)
            summary["min_capital"] = {
                "max_per_leg": float(max_per_leg),
                "recommended_equity": float(max_per_leg * 2),
            }
    _write_cointegration_status_summary(output_path, summary, logger=logger)
    logger.info("Cointegration summary: %s", summary)
    return output_status, summary
