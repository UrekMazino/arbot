import datetime
import math
from bisect import bisect_left
from collections import deque

from config_execution_api import depth, market_session, ticker_1, ticker_2
from func_api_retry import call_with_retries, is_disconnect_error, log_disconnect_once

DEFAULT_BAR = "1m"
DEFAULT_LIMIT = 200
MAX_OKX_CANDLE_LIMIT = 100
_LIQUIDITY_HISTORY = {}

# Get trade liquidity for ticker
def get_ticker_trade_liquidity(ticker, limit=50, session=None):
    """
    Return (average trade size, latest trade price).
    """
    if not ticker:
        return 0.0, 0.0

    active_session = session or market_session
    try:
        limit_val = int(limit)
    except (TypeError, ValueError):
        limit_val = 50
    if limit_val <= 0:
        limit_val = 50

    try:
        if hasattr(active_session, "get_trades"):
            response = active_session.get_trades(instId=ticker, limit=str(limit_val))
        else:
            response = active_session.get_trade(instId=ticker, limit=str(limit_val))
    except TypeError:
        try:
            response = active_session.get_trade(inst_id=ticker, limit=limit_val)
        except Exception as exc:
            print(f"ERROR: Failed to get trades: {exc}")
            return 0.0, 0.0
    except Exception as exc:
        print(f"ERROR: Failed to get trades: {exc}")
        return 0.0, 0.0

    if not isinstance(response, dict):
        print("ERROR: Trade response invalid.")
        return 0.0, 0.0

    if response.get("code") not in (None, "0"):
        print(f"ERROR: Trade fetch failed: {response.get('msg')}")
        return 0.0, 0.0

    trade_rows = response.get("data") or response.get("result") or []
    if not isinstance(trade_rows, list):
        return 0.0, 0.0

    total_size = 0.0
    count = 0
    last_price = 0.0

    for trade in trade_rows:
        if not isinstance(trade, dict):
            continue

        if last_price == 0.0:
            price_raw = trade.get("px") or trade.get("price")
            try:
                price_val = float(price_raw)
            except (TypeError, ValueError):
                price_val = None
            if price_val is not None and math.isfinite(price_val) and price_val > 0:
                last_price = price_val

        size_raw = trade.get("sz") or trade.get("qty") or trade.get("size")
        try:
            size_val = float(size_raw)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(size_val) or size_val <= 0:
            continue

        total_size += size_val
        count += 1

    if count > 0:
        return total_size / count, last_price

    return 0.0, 0.0


def _ensure_history_bucket(history_store, ticker, maxlen):
    bucket = history_store.get(ticker)
    if isinstance(bucket, deque):
        if bucket.maxlen != maxlen:
            bucket = deque(bucket, maxlen=maxlen)
            history_store[ticker] = bucket
        return bucket

    if bucket:
        try:
            bucket = deque(bucket, maxlen=maxlen)
        except TypeError:
            bucket = deque(maxlen=maxlen)
    else:
        bucket = deque(maxlen=maxlen)
    history_store[ticker] = bucket
    return bucket


def _percentile_from_sorted(values, pct):
    if not values:
        return None
    if pct <= 0:
        return values[0]
    if pct >= 1:
        return values[-1]

    pos = (len(values) - 1) * pct
    low = int(math.floor(pos))
    high = int(math.ceil(pos))
    if low == high:
        return values[low]

    low_val = values[low]
    high_val = values[high]
    return low_val + (high_val - low_val) * (pos - low)


def _classify_liquidity_by_history(avg_size, history, low_pct, high_pct, min_samples):
    if avg_size <= 0 or not math.isfinite(avg_size):
        return "unknown", None, None, None
    if len(history) < min_samples:
        return "insufficient_history", None, None, None

    sorted_vals = sorted(history)
    low_cutoff = _percentile_from_sorted(sorted_vals, low_pct)
    high_cutoff = _percentile_from_sorted(sorted_vals, high_pct)
    if low_cutoff is None or high_cutoff is None:
        return "insufficient_history", None, None, None

    if avg_size <= low_cutoff:
        label = "low"
    elif avg_size >= high_cutoff:
        label = "high"
    else:
        label = "medium"

    rank = bisect_left(sorted_vals, avg_size)
    percentile = rank / len(sorted_vals)
    return label, low_cutoff, high_cutoff, percentile


def _classify_liquidity_by_depth(avg_size, depth_size, high_ratio, medium_ratio):
    if avg_size <= 0 or depth_size <= 0:
        return "unknown", None
    ratio = avg_size / depth_size
    if ratio <= high_ratio:
        return "high", ratio
    if ratio <= medium_ratio:
        return "medium", ratio
    return "low", ratio


def get_orderbook_depth(inst_id, levels=depth, session=None):
    """
    Return (total_size, total_notional) from the top N bid+ask levels.
    """
    if not inst_id:
        return 0.0, 0.0

    active_session = session or market_session
    if not hasattr(active_session, "get_orderbook"):
        return 0.0, 0.0

    try:
        level_count = int(levels)
    except (TypeError, ValueError):
        level_count = depth
    if level_count <= 0:
        level_count = depth

    try:
        response = active_session.get_orderbook(instId=inst_id, sz=str(level_count))
    except Exception as exc:
        print(f"ERROR: Failed to fetch orderbook: {exc}")
        return 0.0, 0.0

    if response.get("code") != "0":
        print(f"ERROR: OKX orderbook failed: {response.get('msg')}")
        return 0.0, 0.0

    data = response.get("data", [])
    book = data[0] if isinstance(data, list) and data else {}
    bids = book.get("bids", []) or []
    asks = book.get("asks", []) or []

    def _sum_levels(levels_list):
        total_size = 0.0
        total_notional = 0.0
        for level in levels_list[:level_count]:
            if not isinstance(level, (list, tuple)) or len(level) < 2:
                continue
            try:
                price = float(level[0])
                size = float(level[1])
            except (TypeError, ValueError):
                continue
            if not (math.isfinite(price) and math.isfinite(size)) or price <= 0 or size <= 0:
                continue
            total_size += size
            total_notional += price * size
        return total_size, total_notional

    bid_size, bid_notional = _sum_levels(bids)
    ask_size, ask_notional = _sum_levels(asks)
    return bid_size + ask_size, bid_notional + ask_notional


def get_ticker_liquidity_analysis(
    ticker,
    trade_limit=50,
    history_window=200,
    min_samples=20,
    low_pct=0.2,
    high_pct=0.8,
    depth_levels=depth,
    depth_high_ratio=0.01,
    depth_medium_ratio=0.05,
    session=None,
    history_store=None,
):
    """
    Analyze liquidity using trade-size history, with orderbook fallback.
    """
    avg_size, last_price = get_ticker_trade_liquidity(ticker, limit=trade_limit, session=session)
    depth_size, depth_notional = get_orderbook_depth(ticker, levels=depth_levels, session=session)

    store = history_store if history_store is not None else _LIQUIDITY_HISTORY
    history = _ensure_history_bucket(store, ticker, history_window)
    if avg_size > 0 and math.isfinite(avg_size):
        history.append(avg_size)

    history_label, low_cutoff, high_cutoff, percentile = _classify_liquidity_by_history(
        avg_size,
        history,
        low_pct,
        high_pct,
        min_samples,
    )
    depth_label, depth_ratio = _classify_liquidity_by_depth(
        avg_size,
        depth_size,
        depth_high_ratio,
        depth_medium_ratio,
    )

    if history_label in ("low", "medium", "high"):
        label = history_label
        label_basis = "history"
    elif depth_label in ("low", "medium", "high"):
        label = depth_label
        label_basis = "orderbook"
    else:
        label = "unknown"
        label_basis = "none"

    return {
        "ticker": ticker,
        "avg_trade_size": avg_size,
        "last_price": last_price,
        "label": label,
        "label_basis": label_basis,
        "history_label": history_label,
        "history_samples": len(history),
        "history_low_cutoff": low_cutoff,
        "history_high_cutoff": high_cutoff,
        "history_percentile": percentile,
        "orderbook_label": depth_label,
        "orderbook_depth_size": depth_size,
        "orderbook_depth_notional": depth_notional,
        "orderbook_ratio": depth_ratio,
    }


def _normalize_bar(bar):
    if bar is None:
        return DEFAULT_BAR

    if isinstance(bar, (int, float)) and bar > 0:
        minutes = int(bar)
        if minutes >= 60 and minutes % 60 == 0:
            return f"{minutes // 60}H"
        return f"{minutes}m"

    bar_str = str(bar).strip()
    if not bar_str:
        return DEFAULT_BAR

    if bar_str.isdigit():
        return _normalize_bar(int(bar_str))

    if bar_str.upper() == "D":
        return "1D"

    suffix = bar_str[-1]
    if suffix.isalpha() and bar_str[:-1].isdigit():
        number = bar_str[:-1]
        if suffix in ("m", "M"):
            return f"{number}m" if suffix == "m" else f"{number}M"
        if suffix in ("h", "H"):
            return f"{number}H"
        if suffix in ("d", "D"):
            return f"{number}D"
        if suffix in ("w", "W"):
            return f"{number}W"

    return bar_str


def _bar_to_seconds(bar):
    bar_norm = _normalize_bar(bar)
    if len(bar_norm) < 2 or not bar_norm[:-1].isdigit():
        return None

    value = int(bar_norm[:-1])
    suffix = bar_norm[-1]
    if suffix == "m":
        return value * 60
    if suffix == "H":
        return value * 60 * 60
    if suffix == "D":
        return value * 24 * 60 * 60
    if suffix == "W":
        return value * 7 * 24 * 60 * 60
    if suffix == "M":
        return value * 30 * 24 * 60 * 60
    return None


def _normalize_now(now):
    if now is None:
        return datetime.datetime.now(datetime.timezone.utc)
    if isinstance(now, (int, float)):
        return datetime.datetime.fromtimestamp(float(now), datetime.timezone.utc)
    if isinstance(now, datetime.datetime):
        if now.tzinfo is None:
            return now.replace(tzinfo=datetime.timezone.utc)
        return now.astimezone(datetime.timezone.utc)
    raise TypeError("now must be datetime, int/float timestamp, or None")


def get_timestamps(bar=DEFAULT_BAR, limit=DEFAULT_LIMIT, now=None):
    """
    Return (start_ms, now_ms, end_ms) for a candle window.
    end_ms is now_ms + one bar, which is useful for OKX before/after windows.
    """
    bar_seconds = _bar_to_seconds(bar)
    if not bar_seconds:
        return None, None, None

    try:
        limit_val = int(limit)
    except (TypeError, ValueError):
        limit_val = DEFAULT_LIMIT

    if limit_val <= 0:
        return None, None, None

    now_dt = _normalize_now(now)
    now_ms = int(now_dt.timestamp() * 1000)
    start_ms = now_ms - (bar_seconds * 1000 * limit_val)
    end_ms = now_ms + (bar_seconds * 1000)
    return int(start_ms), int(now_ms), int(end_ms)


def get_candlesticks(inst_id, bar=DEFAULT_BAR, limit=DEFAULT_LIMIT, before=None, after=None, session=None):
    """
    Fetch candlesticks from OKX MarketData.
    """
    active_session = session or market_session
    bar = _normalize_bar(bar)

    try:
        limit_val = int(limit)
    except (TypeError, ValueError):
        limit_val = DEFAULT_LIMIT

    kwargs = {
        "instId": inst_id,
        "bar": bar,
        "limit": str(limit_val),
    }
    if before is not None:
        kwargs["before"] = str(int(before))
    if after is not None:
        kwargs["after"] = str(int(after))

    try:
        response = call_with_retries(lambda: active_session.get_candlesticks(**kwargs))
    except Exception as exc:
        msg = f"ERROR: Failed to get candlesticks: {exc}"
        if is_disconnect_error(exc):
            log_disconnect_once("candlesticks", msg)
        else:
            print(msg)
        return {"code": "1", "msg": str(exc), "data": []}

    if response.get("code") != "0":
        err_msg = response.get("msg")
        msg = f"ERROR: OKX candlesticks failed: {err_msg}"
        if is_disconnect_error(err_msg):
            log_disconnect_once("candlesticks", msg)
        else:
            print(msg)
    return response


def normalize_candlesticks(raw_data, ascending=True):
    """
    Convert OKX candlestick lists into dicts with numeric values.
    """
    if not raw_data:
        return []

    candles = []
    for kline in raw_data:
        if not isinstance(kline, (list, tuple)) or len(kline) < 5:
            continue
        try:
            ts = int(float(kline[0]))
            open_px = float(kline[1])
            high_px = float(kline[2])
            low_px = float(kline[3])
            close_px = float(kline[4])
        except (TypeError, ValueError):
            continue

        volume = float(kline[5]) if len(kline) > 5 else 0.0
        volume_ccy = float(kline[6]) if len(kline) > 6 else 0.0
        volume_ccy_quote = float(kline[7]) if len(kline) > 7 else 0.0
        confirm = kline[8] if len(kline) > 8 else None

        candles.append({
            "timestamp": ts,
            "open": open_px,
            "high": high_px,
            "low": low_px,
            "close": close_px,
            "volume": volume,
            "volume_ccy": volume_ccy,
            "volume_ccy_quote": volume_ccy_quote,
            "confirm": confirm,
        })

    if ascending:
        candles.reverse()
    return candles


def extract_close_prices(candles, require_variance=False):
    """
    Extract close prices from normalized candles or raw OKX lists.
    """
    close_prices = []
    for item in candles or []:
        if isinstance(item, dict):
            close_val = item.get("close")
        elif isinstance(item, (list, tuple)) and len(item) > 4:
            close_val = item[4]
        else:
            continue

        try:
            close_num = float(close_val)
        except (TypeError, ValueError):
            return []
        if not math.isfinite(close_num):
            return []
        close_prices.append(close_num)

    if not close_prices:
        return []
    if require_variance and len(set(close_prices)) == 1:
        return []
    return close_prices


def get_close_prices(inst_id, bar=DEFAULT_BAR, limit=DEFAULT_LIMIT, session=None, ascending=True,
                     require_variance=False):
    """
    Fetch candlesticks and return close prices.
    """
    response = get_candlesticks(inst_id, bar=bar, limit=limit, session=session)
    if response.get("code") != "0":
        return []
    candles = normalize_candlesticks(response.get("data", []), ascending=ascending)
    return extract_close_prices(candles, require_variance=require_variance)


def get_price_klines(ticker, bar=DEFAULT_BAR, limit=DEFAULT_LIMIT, session=None, use_start_time=True,
                     ascending=False):
    """
    Fetch historical candlesticks for a ticker using OKX MarketData.
    Returns the raw OKX list-of-lists data (newest first) or [] on failure.
    """
    try:
        limit_val = int(limit)
    except (TypeError, ValueError):
        limit_val = DEFAULT_LIMIT

    if limit_val <= 0:
        return []

    start_ms = None
    if use_start_time:
        start_ms, _, _ = get_timestamps(bar=bar, limit=limit_val)

    remaining = limit_val
    before = None
    after = start_ms
    data_all = []
    seen_ts = set()

    while remaining > 0:
        page_limit = min(remaining, MAX_OKX_CANDLE_LIMIT)
        response = get_candlesticks(
            inst_id=ticker,
            bar=bar,
            limit=page_limit,
            before=before,
            after=after,
            session=session,
        )
        after = None

        if response.get("code") != "0":
            return []

        page = response.get("data", [])
        if not page:
            break

        new_rows = []
        for row in page:
            if not row:
                continue
            ts = row[0]
            if ts in seen_ts:
                continue
            seen_ts.add(ts)
            new_rows.append(row)

        if not new_rows:
            break

        data_all.extend(new_rows)
        if len(data_all) >= limit_val:
            break

        oldest_ts = None
        try:
            oldest_ts = int(float(new_rows[-1][0]))
        except (TypeError, ValueError, IndexError):
            oldest_ts = None

        if oldest_ts is None:
            break

        before = oldest_ts - 1
        remaining = limit_val - len(data_all)

        if len(page) < page_limit:
            break

    if len(data_all) < limit_val:
        print(f"Warning: Got {len(data_all)} candles, expected {limit_val}")

    data_all = data_all[:limit_val]
    if ascending:
        data_all.reverse()
    return data_all


def get_latest_klines(inst_id_1=None, inst_id_2=None, bar=DEFAULT_BAR, limit=DEFAULT_LIMIT, session=None,
                      ascending=True, debug=False):
    """
    Fetch the latest close-price series for two instruments.
    """
    inst_1 = inst_id_1 or ticker_1
    inst_2 = inst_id_2 or ticker_2
    series_1 = []
    series_2 = []

    if not inst_1 or not inst_2:
        return series_1, series_2

    prices_1 = get_price_klines(inst_1, bar=bar, limit=limit, session=session, ascending=ascending)
    prices_2 = get_price_klines(inst_2, bar=bar, limit=limit, session=session, ascending=ascending)

    if prices_1:
        series_1 = extract_close_prices(prices_1)
    if prices_2:
        series_2 = extract_close_prices(prices_2)

    if debug:
        print(f"{inst_1} closes: {len(series_1)}")
        print(f"{inst_2} closes: {len(series_2)}")

    return series_1, series_2
