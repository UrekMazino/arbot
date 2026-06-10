#!/usr/bin/env python3
"""
D1 kline fetcher — pulls 1-minute klines from OKX history-candles public
endpoint for the 18 instruments involved in T1-T15. Caches per-instrument
CSVs in tools/observation_mode/output/kline_cache/.

Read-only public endpoint, no auth, no bot dependencies. Same posture as
the validator sidecar and the coint-fragility sampler.

For the D1 sanity check (work item §1.3), we need klines covering each
trade's hold window + 21-bar lookback for z computation. To keep this
simple and robust, we pull the full experiment window for all 18
instruments: 2026-05-28 00:00 UTC -> 2026-05-31 03:00 UTC (~3300 bars
each, 18 instruments, ~33 paginated requests per instrument).

Usage:
    python tools/observation_mode/d1_kline_fetcher.py
"""

from __future__ import annotations

import certifi
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERR: requests library not installed. Run: pip install requests certifi", file=sys.stderr)
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = Path(__file__).parent / "output" / "kline_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

OKX_BASE = "https://www.okx.com"
HISTORY_CANDLES_PATH = "/api/v5/market/history-candles"

# Experiment window: 2026-05-28 00:00 UTC through 2026-05-31 03:00 UTC.
# Buffer 60 min on each side for velocity computation and post-event windows.
WINDOW_START_UTC = datetime(2026, 5, 27, 23, 0, tzinfo=timezone.utc)
WINDOW_END_UTC = datetime(2026, 5, 31, 4, 0, tzinfo=timezone.utc)

# 18 instruments from T1-T15 metadata
INSTRUMENTS = [
    "AAVE-USDT-SWAP", "ARB-USDT-SWAP", "AVAX-USDT-SWAP", "BCH-USDT-SWAP",
    "BNB-USDT-SWAP", "BTC-USDT-SWAP", "CRV-USDT-SWAP", "DOGE-USDT-SWAP",
    "DOT-USDT-SWAP", "ETC-USDT-SWAP", "ETH-USDT-SWAP", "JUP-USDT-SWAP",
    "KSM-USDT-SWAP", "LINK-USDT-SWAP", "LTC-USDT-SWAP", "OP-USDT-SWAP",
    "SOL-USDT-SWAP", "YGG-USDT-SWAP",
]

# OKX kline row: [ts_ms, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
KLINE_COLS = ["ts_ms", "open", "high", "low", "close", "vol", "vol_ccy", "vol_ccy_quote", "confirm"]


def fetch_page(inst_id: str, after_ms: int, limit: int = 100) -> list:
    """Fetch up to `limit` 1m klines older than after_ms. Returns rows
    newest-to-oldest."""
    url = f"{OKX_BASE}{HISTORY_CANDLES_PATH}"
    params = {"instId": inst_id, "bar": "1m", "limit": str(limit), "after": str(after_ms)}
    r = requests.get(url, params=params, timeout=20, verify=certifi.where())
    data = r.json()
    if data.get("code") != "0":
        return []
    return data.get("data", [])


def fetch_range(inst_id: str, start_ms: int, end_ms: int, sleep_sec: float = 0.18) -> list:
    """Fetch all 1m klines in [start_ms, end_ms] via reverse pagination.
    Returns rows sorted oldest-to-newest."""
    collected = {}
    after_cursor = end_ms + 60_000
    while True:
        page = fetch_page(inst_id, after_cursor, limit=100)
        if not page:
            break
        for row in page:
            ts = int(row[0])
            if ts < start_ms:
                continue
            collected[ts] = row
        oldest_ts = int(page[-1][0])
        if oldest_ts < start_ms:
            break
        after_cursor = oldest_ts
        time.sleep(sleep_sec)
    return sorted(collected.values(), key=lambda r: int(r[0]))


def cache_path(inst_id: str) -> Path:
    return CACHE_DIR / f"{inst_id}.csv"


def already_cached(inst_id: str, start_ms: int, end_ms: int, min_coverage: float = 0.95) -> bool:
    """Check if cache covers [start_ms, end_ms] with at least min_coverage."""
    path = cache_path(inst_id)
    if not path.exists():
        return False
    expected_bars = (end_ms - start_ms) // 60_000
    actual_bars = 0
    earliest = None
    latest = None
    with path.open("r", encoding="utf-8") as f:
        r = csv.reader(f)
        next(r, None)  # header
        for row in r:
            if not row:
                continue
            try:
                ts = int(row[0])
            except (ValueError, IndexError):
                continue
            if start_ms <= ts <= end_ms:
                actual_bars += 1
                if earliest is None or ts < earliest:
                    earliest = ts
                if latest is None or ts > latest:
                    latest = ts
    coverage = actual_bars / expected_bars if expected_bars else 0.0
    return coverage >= min_coverage


def write_cache(inst_id: str, rows: list):
    path = cache_path(inst_id)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(KLINE_COLS)
        for row in rows:
            w.writerow(row)


def main():
    start_ms = int(WINDOW_START_UTC.timestamp() * 1000)
    end_ms = int(WINDOW_END_UTC.timestamp() * 1000)
    expected_bars_per_inst = (end_ms - start_ms) // 60_000
    print(f"Fetch window: {WINDOW_START_UTC.isoformat()} -> {WINDOW_END_UTC.isoformat()} UTC")
    print(f"Expected bars per instrument: ~{expected_bars_per_inst}")
    print(f"Instruments: {len(INSTRUMENTS)}")
    print()

    for i, inst in enumerate(INSTRUMENTS, 1):
        if already_cached(inst, start_ms, end_ms):
            print(f"  [{i:>2}/{len(INSTRUMENTS)}] {inst:<20} cached -> skip")
            continue
        print(f"  [{i:>2}/{len(INSTRUMENTS)}] {inst:<20} fetching ...", end="", flush=True)
        t0 = time.time()
        rows = fetch_range(inst, start_ms, end_ms)
        elapsed = time.time() - t0
        write_cache(inst, rows)
        coverage_pct = 100.0 * len(rows) / expected_bars_per_inst if expected_bars_per_inst else 0.0
        print(f" got {len(rows):>4} bars ({coverage_pct:5.1f}%) in {elapsed:5.1f}s")

    print("\nKline cache populated.")


if __name__ == "__main__":
    main()
