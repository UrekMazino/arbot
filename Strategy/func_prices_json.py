"""
    Store price history for all available trading pairs
    Fetches candlestick data and saves to JSON file
"""

from func_price_klines import get_price_klines, get_latest_klines
from func_strategy_log import get_strategy_logger
from config_strategy_api import time_frame, kline_limit
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
import time
import sys


def _int_env(name, default):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default


def _bool_env(name, default=False):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return bool(default)
    return str(raw).strip().lower() in ("1", "true", "yes", "y", "on")


def _float_env(name, default):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return float(default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def _timeframe_to_ms(tf):
    text = str(tf or "").strip()
    if not text or len(text) < 2:
        return 0
    unit = text[-1]
    try:
        value = float(text[:-1])
    except (TypeError, ValueError):
        return 0
    if unit == "m":
        seconds = value * 60
    elif unit in ("h", "H"):
        seconds = value * 3600
    elif unit in ("d", "D"):
        seconds = value * 86400
    elif unit in ("w", "W"):
        seconds = value * 604800
    elif unit == "M":
        seconds = value * 2592000
    else:
        return 0
    return int(seconds * 1000)


def _state_dir():
    base_dir = Path(__file__).resolve().parent
    state_dir = base_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def _load_no_data_blacklist(path, ttl_hours):
    if not path.exists():
        return set(), {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set(), {}

    symbols = payload.get("symbols", {}) if isinstance(payload, dict) else {}
    if not isinstance(symbols, dict):
        return set(), {}

    now = datetime.now(timezone.utc)
    keep = {}
    ttl_seconds = None
    if ttl_hours and ttl_hours > 0:
        ttl_seconds = float(ttl_hours) * 3600

    for sym, ts in symbols.items():
        if not sym:
            continue
        if not ts or ttl_seconds is None:
            keep[sym] = ts
            continue
        try:
            parsed = datetime.fromisoformat(ts)
        except (TypeError, ValueError):
            keep[sym] = ts
            continue
        age = (now - parsed).total_seconds()
        if age <= ttl_seconds:
            keep[sym] = ts

    return set(keep.keys()), keep


def _save_no_data_blacklist(path, symbols_map):
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "symbols": symbols_map,
    }
    temp_path = path.with_name(f".{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _normalize_klines(price_history):
    if not price_history or price_history.get("code") != "0" or not price_history.get("data"):
        return []
    klines = []
    for kline in reversed(price_history["data"]):
        kline_data = {
            "timestamp": kline[0],
            "open": float(kline[1]),
            "high": float(kline[2]),
            "low": float(kline[3]),
            "close": float(kline[4]),
            "volume": float(kline[5]) if len(kline) > 5 else 0,
            "volume_ccy": float(kline[6]) if len(kline) > 6 else 0,
        }
        klines.append(kline_data)
    return klines


def _merge_klines(existing, new):
    merged = {}
    for row in existing or []:
        ts = row.get("timestamp")
        if ts is not None:
            merged[str(ts)] = row
    for row in new or []:
        ts = row.get("timestamp")
        if ts is not None:
            merged[str(ts)] = row
    def _ts_key(item):
        try:
            return int(item.get("timestamp"))
        except (TypeError, ValueError):
            return 0
    return sorted(merged.values(), key=_ts_key)


def _target_kline_limit():
    try:
        return max(1, int(kline_limit))
    except (TypeError, ValueError):
        return 1


def _cache_needs_backfill(cached_klines, target_limit):
    return bool(cached_klines) and len(cached_klines) < target_limit


def store_price_history(symbols):
    """
    Fetch and store price history for all symbols

    Args:
        symbols: List of symbol dictionaries with 'symbol' key

    Returns:
        None (saves to output/1_price_list.json)
    """
    # Get prices and store in dictionary
    count = 0
    price_history_dict = {}

    logger = get_strategy_logger()
    print(f"Price history: fetching {len(symbols)} symbols...")
    logger.info("Price history fetch start: symbols=%d", len(symbols))

    total_symbols = len(symbols)
    bar_len = 24
    cache_enabled = _bool_env("STATBOT_STRATEGY_INTERNAL_CACHE_KLINES", True)
    max_gap_bars = _int_env("STATBOT_STRATEGY_INTERNAL_CACHE_MAX_GAP_BARS", 120)
    refresh_bars = _int_env("STATBOT_STRATEGY_INTERNAL_CACHE_REFRESH_BARS", 100)
    cache_sleep = _float_env("STATBOT_STRATEGY_INTERNAL_CACHE_SLEEP", 0.05)
    request_sleep = _float_env("STATBOT_STRATEGY_INTERNAL_KLINE_SLEEP", 0.0)
    max_workers = _int_env("STATBOT_STRATEGY_INTERNAL_KLINE_WORKERS", 2)
    retry_count = _int_env("STATBOT_STRATEGY_INTERNAL_KLINE_RETRIES", 2)
    retry_sleep = _float_env("STATBOT_STRATEGY_INTERNAL_KLINE_RETRY_SLEEP", 0.25)
    max_stale_bars = _int_env("STATBOT_STRATEGY_INTERNAL_CACHE_MAX_STALE_BARS", 2)
    target_limit = _target_kline_limit()
    if max_stale_bars < 0:
        max_stale_bars = 0
    if max_workers < 1:
        max_workers = 1
    no_data_ttl = _float_env("STATBOT_STRATEGY_NO_DATA_TTL_HOURS", 24)
    bar_ms = _timeframe_to_ms(time_frame)

    cached_data = {}
    base_dir = Path(__file__).resolve().parent
    output_dir = base_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "1_price_list.json"
    state_dir = _state_dir()
    no_data_path = state_dir / "no_data_symbols.json"
    no_data_symbols, no_data_map = _load_no_data_blacklist(no_data_path, no_data_ttl)
    no_data_changed = False

    if no_data_symbols:
        before = len(symbols)
        symbols = [sym for sym in symbols if sym.get("symbol") not in no_data_symbols]
        removed = before - len(symbols)
        if removed > 0:
            logger.warning("Price history: skipping %d no-data symbols from blacklist.", removed)
            total_symbols = len(symbols)

    if cache_enabled and output_path.exists():
        try:
            cached_data = json.loads(output_path.read_text(encoding="utf-8"))
            logger.info("Price history cache loaded: symbols=%d", len(cached_data))
        except Exception as exc:
            logger.warning("Price history cache load failed: %s", exc)
            cached_data = {}

    def _render_progress(idx, symbol_name, status="", stored=None):
        filled = int(bar_len * idx / max(1, total_symbols))
        bar = "#" * filled + "-" * (bar_len - filled)
        suffix = f" | {status}" if status else ""
        if stored is not None:
            suffix = f"{suffix} | stored {stored}/{total_symbols}"
        sys.stdout.write(f"\r[{bar}] {idx}/{total_symbols} {symbol_name}{suffix}")
        sys.stdout.flush()
        if idx >= total_symbols:
            sys.stdout.write("\n")

    cache_hits = 0
    cache_refreshed = 0
    cache_stale_used = 0
    cache_stale_skipped = 0
    cache_backfill_skipped = 0
    stale_symbols = 0
    stale_gap_total = 0

    def _fetch_symbol_data(symbol):
        symbol_name = symbol.get("symbol")
        klines = []
        status = ""
        no_data = False
        cache_used = False
        cache_refreshed_local = False
        stale_used = False
        stale_skipped = False
        needs_backfill = False
        gap_bars = None

        try:
            cached_entry = cached_data.get(symbol_name) if cache_enabled else None
            cached_klines = cached_entry.get("klines") if isinstance(cached_entry, dict) else None
            use_cache = bool(cache_enabled and cached_klines)
            needs_backfill = _cache_needs_backfill(cached_klines, target_limit)

            if needs_backfill:
                status = f"BACKFILL {len(cached_klines)}/{target_limit} candles"
            elif use_cache and bar_ms > 0:
                try:
                    last_ts = int(cached_klines[-1].get("timestamp"))
                except (TypeError, ValueError, AttributeError):
                    last_ts = 0
                now_ms = int(time.time() * 1000)
                gap_bars = int(max(0, (now_ms - last_ts) // bar_ms))
                if gap_bars <= max_gap_bars:
                    fetch_limit = max(refresh_bars, gap_bars + 5)
                    fetch_limit = max(1, min(int(fetch_limit), 100))
                    try:
                        latest = get_latest_klines(symbol_name, limit=fetch_limit)
                        if request_sleep > 0:
                            time.sleep(request_sleep)
                        if cache_sleep > 0:
                            time.sleep(cache_sleep)
                        latest_klines = _normalize_klines(latest)
                        if latest_klines:
                            klines = _merge_klines(cached_klines, latest_klines)
                            cache_used = True
                            cache_refreshed_local = True
                        elif gap_bars <= max_stale_bars:
                            klines = list(cached_klines)
                            cache_used = True
                            stale_used = gap_bars > 0
                        else:
                            stale_skipped = True
                    except Exception:
                        if gap_bars is not None and gap_bars <= max_stale_bars:
                            klines = list(cached_klines)
                            cache_used = True
                            stale_used = gap_bars > 0
                        else:
                            stale_skipped = True
                else:
                    stale_skipped = True

                if klines:
                    if len(klines) > target_limit:
                        klines = klines[-target_limit:]
                    status = f"CACHE {len(klines)} candles"

            if not klines:
                attempts = max(retry_count, 0) + 1
                last_error = None
                for attempt in range(attempts):
                    try:
                        price_history = get_price_klines(symbol_name)
                        if request_sleep > 0:
                            time.sleep(request_sleep)
                    except Exception as exc:
                        last_error = exc
                        if attempt < attempts - 1 and retry_sleep > 0:
                            time.sleep(retry_sleep * (attempt + 1))
                        continue

                    klines = _normalize_klines(price_history)
                    if klines:
                        status = f"OK {len(klines)} candles"
                        break
                    status = "ERR no data"
                    msg = str(price_history.get("msg") or "").lower() if isinstance(price_history, dict) else ""
                    if "insufficient data" in msg or "no data" in msg:
                        no_data = True
                    break

                if not klines and not status:
                    status = "ERR fetch failed"
                    if last_error:
                        logger.warning("Price history fetch failed: %s", symbol_name)
        except Exception:
            status = "ERR fetch failed"

        return {
            "symbol": symbol,
            "symbol_name": symbol_name,
            "klines": klines,
            "status": status,
            "no_data": no_data,
            "cache_used": cache_used,
            "cache_refreshed": cache_refreshed_local,
            "stale_used": stale_used,
            "stale_skipped": stale_skipped,
            "cache_backfill": needs_backfill,
            "gap_bars": gap_bars,
        }

    def _handle_result(idx, result):
        nonlocal count, no_data_changed, cache_hits, cache_refreshed, cache_stale_used, cache_stale_skipped
        nonlocal cache_backfill_skipped
        nonlocal stale_symbols, stale_gap_total

        symbol_name = result.get("symbol_name")
        klines = result.get("klines") or []
        status = result.get("status") or ""
        gap_bars = result.get("gap_bars")

        if gap_bars is not None and gap_bars > 0:
            stale_symbols += 1
            stale_gap_total += gap_bars

        if result.get("cache_used"):
            cache_hits += 1
            if result.get("cache_refreshed"):
                cache_refreshed += 1
            if result.get("stale_used"):
                cache_stale_used += 1
        if result.get("stale_skipped"):
            cache_stale_skipped += 1
        if result.get("cache_backfill"):
            cache_backfill_skipped += 1

        symbol = result.get("symbol") or {}
        symbol["total_klines"] = len(klines)

        if len(klines) > 0:
            price_history_dict[symbol_name] = {
                "symbol_info": symbol,
                "klines": klines,
            }
            count += 1
        else:
            if not status or status.startswith("CACHE"):
                status = "SKIP no klines"
            if result.get("no_data") and symbol_name:
                no_data_map[symbol_name] = datetime.now(timezone.utc).isoformat()
                no_data_changed = True
                logger.warning("Price history: no data for %s; added to blacklist.", symbol_name)

        _render_progress(idx, symbol_name, status=status, stored=count)

    if max_workers == 1:
        for idx, symbol in enumerate(symbols, 1):
            result = _fetch_symbol_data(symbol)
            _handle_result(idx, result)
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_fetch_symbol_data, symbol) for symbol in symbols]
            for idx, future in enumerate(as_completed(futures), 1):
                result = future.result()
                _handle_result(idx, result)
    if no_data_changed:
        _save_no_data_blacklist(no_data_path, no_data_map)
    if total_symbols > 0:
        stale_rate = round((stale_symbols / total_symbols) * 100, 2)
    else:
        stale_rate = 0.0
    avg_gap_bars = round((stale_gap_total / stale_symbols), 2) if stale_symbols else 0.0
    logger.info(
        "Price history cache: hits=%d refreshed=%d stale_used=%d stale_skipped=%d backfill=%d",
        cache_hits,
        cache_refreshed,
        cache_stale_used,
        cache_stale_skipped,
        cache_backfill_skipped,
    )
    logger.info(
        "Price history staleness: symbols=%d rate=%.2f%% avg_gap_bars=%.2f",
        stale_symbols,
        stale_rate,
        avg_gap_bars,
    )
    # Output prices to JSON
    if len(price_history_dict) > 0:
        try:
            rel_path = output_path.relative_to(base_dir)
        except ValueError:
            rel_path = output_path
        print(f"Price history saved: {rel_path} (symbols {len(price_history_dict)})")
        temp_path = output_path.with_name(f".{output_path.name}.tmp")
        with temp_path.open("w", encoding="utf-8") as fp:
            json.dump(price_history_dict, fp, indent=4)
        temp_path.replace(output_path)
        logger.info("Price history saved: %s symbols=%d", rel_path, len(price_history_dict))
    else:
        print("Price history: no data to save.")
        logger.warning("Price history empty: no data to save")

    return
