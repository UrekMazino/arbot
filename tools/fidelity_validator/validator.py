#!/usr/bin/env python3
"""
Section-5 Path-1 Fidelity-Gate Validator (read-only sidecar).

Subscribes to OKX public WS mark-price for the currently-open trade's
instruments, computes virtual_pnl from beta-sized leg capitals + live marks,
and compares to the live monitoring loop's recorded unrealized_pnl_usdt in
position_snapshots.csv.

Per the query-3 spec v1.2 section 5 (Path 1):
- Pass criterion: >= 99% of compared ticks within $0.01, over >= 3 live
  trades' full snapshot series, with the <=1% out-of-tolerance bucket
  randomly distributed (not clustered).

Path A (chosen by operator): parses the bot log for entry info. Zero code
change to live; depends on stable BETA_SIZING + "Placed long/short entry"
log line formats.

Stop-and-report guardrails:
- This script does NOT write to bot-owned files.
- It does NOT invoke any trade-permissioned credentials.
- It does NOT call any bot code or modify bot state.
- If the implementation surfaces a need to build harness components,
  STOP and report (do not extend into the harness).

Usage:
  Start AFTER a live run begins (i.e., once Reports/v1/run_N/position_snapshots.csv
  exists for the active run). Run as a separate process:
      python tools/fidelity_validator/validator.py
  Output: tools/fidelity_validator/logs/fidelity_<run_name>.csv

  If a new run starts, kill the validator (Ctrl+C) and restart it.
"""

import asyncio
import csv
import glob
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import websockets
except ImportError:
    print("ERR: websockets library not installed. Run: pip install websockets", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------- config

OKX_WS_PUBLIC = "wss://ws.okx.com:8443/ws/v5/public"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = PROJECT_ROOT / "Logs" / "v1"
REPORTS_DIR = PROJECT_ROOT / "Reports" / "v1"
OUTPUT_DIR = Path(__file__).parent / "logs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CENT = 0.01

# ---------------------------------------------------------------- log parsing

BETA_SIZING_RE = re.compile(
    r"BETA_SIZING:\s*beta=([\d.]+)\s+gross=([\d.]+)\s+"
    r"capital_long=([\d.]+)\s+capital_short=([\d.]+)\s+side=(\w+)"
)
PLACED_LONG_RE = re.compile(
    r"Placed long entry:\s*ticker=(\S+)\s+id=\S+\s+entry_price=([\d.]+)\s+capital=([\d.]+)"
)
PLACED_SHORT_RE = re.compile(
    r"Placed short entry:\s*ticker=(\S+)\s+id=\S+\s+entry_price=([\d.]+)\s+capital=([\d.]+)"
)
RUN_END_RE = re.compile(r"RUN_END:")
TRADE_OPEN_RE = re.compile(r"STRATEGY_TRADE_OPEN")
TRADE_CLOSE_RE = re.compile(r"STRATEGY_TRADE_CLOSE")


# ---------------------------------------------------------------- state

class State:
    def __init__(self):
        self.current_trade = None  # dict or None
        self.latest_marks = {}     # instId -> latest mark price (float)
        self.run_dir = None
        self.snapshots_seen = set()
        self.output_csv = None
        self.lock = asyncio.Lock()


def _run_number(path_str):
    """Extract integer run number from a 'run_<N>_<YYYYMMDD>_<HHMMSS>' path."""
    name = Path(path_str).name
    m = re.match(r"run_(\d+)_", name)
    return int(m.group(1)) if m else -1


def find_latest_run_dir():
    """Sort by numeric run number, then by mtime as tiebreaker (highest = latest)."""
    runs = glob.glob(str(LOGS_DIR / "run_*"))
    if not runs:
        return None
    runs.sort(key=lambda p: (_run_number(p), os.path.getmtime(p)))
    return Path(runs[-1])


def find_latest_log(run_dir):
    logs = sorted(Path(run_dir).glob("log_*.log"))
    return logs[-1] if logs else None


def find_snapshot_csv(run_dir):
    snaps = REPORTS_DIR / Path(run_dir).name / "position_snapshots.csv"
    return snaps if snaps.exists() else None


# ---------------------------------------------------------------- tasks

def _initial_scan_for_open_trade(log_path):
    """At startup, scan the log from beginning to find the most-recent OPEN trade
    (a complete BETA_SIZING + Placed long + Placed short trio not followed by
    a STRATEGY_TRADE_CLOSE or RUN_END). Returns the trade dict or None.
    """
    pending = {}
    last_open_trade = None
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = BETA_SIZING_RE.search(line)
            if m:
                pending = {
                    "beta": float(m.group(1)), "gross": float(m.group(2)),
                    "capital_long": float(m.group(3)), "capital_short": float(m.group(4)),
                    "side": m.group(5),
                }
                continue
            m = PLACED_LONG_RE.search(line)
            if m:
                pending["long_inst"] = m.group(1); pending["long_entry"] = float(m.group(2))
                continue
            m = PLACED_SHORT_RE.search(line)
            if m:
                pending["short_inst"] = m.group(1); pending["short_entry"] = float(m.group(2))
                required = {"long_inst","long_entry","short_inst","short_entry","capital_long","capital_short"}
                if required.issubset(pending.keys()):
                    last_open_trade = dict(pending)
                    pending = {}
                continue
            if TRADE_CLOSE_RE.search(line) or RUN_END_RE.search(line):
                last_open_trade = None  # trade closed; current state has no open trade
                pending = {}
    return last_open_trade


async def tail_log(state, log_path, stop):
    """Initial backward scan for any currently-open trade, then tail from EOF."""
    initial = _initial_scan_for_open_trade(log_path)
    if initial:
        async with state.lock:
            state.current_trade = initial
        print(f"[validator] initial scan found OPEN trade: "
              f"{initial['long_inst']}(L) {initial['short_inst']}(S) "
              f"L_cap={initial['capital_long']:.2f} S_cap={initial['capital_short']:.2f}")
    else:
        print("[validator] initial scan: no open trade found in log so far")
    pending = {}
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        f.seek(0, 2)  # EOF (tail from here for new lines)
        while not stop.is_set():
            line = f.readline()
            if not line:
                await asyncio.sleep(1.0)
                continue
            m = BETA_SIZING_RE.search(line)
            if m:
                pending["beta"] = float(m.group(1))
                pending["gross"] = float(m.group(2))
                pending["capital_long"] = float(m.group(3))
                pending["capital_short"] = float(m.group(4))
                pending["side"] = m.group(5)
                continue
            m = PLACED_LONG_RE.search(line)
            if m:
                pending["long_inst"] = m.group(1)
                pending["long_entry"] = float(m.group(2))
                continue
            m = PLACED_SHORT_RE.search(line)
            if m:
                pending["short_inst"] = m.group(1)
                pending["short_entry"] = float(m.group(2))
                required = {
                    "long_inst", "long_entry", "short_inst", "short_entry",
                    "capital_long", "capital_short",
                }
                if required.issubset(pending.keys()):
                    async with state.lock:
                        state.current_trade = dict(pending)
                    print(f"[validator] open trade: {pending['long_inst']}(L) "
                          f"{pending['short_inst']}(S) "
                          f"L_cap={pending['capital_long']:.2f} "
                          f"S_cap={pending['capital_short']:.2f}")
                    pending = {}
                continue
            if TRADE_CLOSE_RE.search(line) or RUN_END_RE.search(line):
                async with state.lock:
                    if state.current_trade is not None:
                        print("[validator] trade closed / run ended; clearing trade.")
                    state.current_trade = None
                pending = {}
                if RUN_END_RE.search(line):
                    print("[validator] RUN_END detected. Validator continues; "
                          "restart it manually for the next run.")


async def ws_subscribe(state, stop):
    """Subscribe to OKX public mark-price WS for current trade's instruments."""
    subscribed = set()
    while not stop.is_set():
        try:
            async with websockets.connect(OKX_WS_PUBLIC, ping_interval=20) as ws:
                print(f"[validator] WS connected: {OKX_WS_PUBLIC}")
                while not stop.is_set():
                    async with state.lock:
                        trade = dict(state.current_trade) if state.current_trade else None
                    target = set()
                    if trade:
                        target = {trade["long_inst"], trade["short_inst"]}
                    new_subs = target - subscribed
                    for inst in new_subs:
                        msg = {
                            "op": "subscribe",
                            "args": [{"channel": "mark-price", "instId": inst}],
                        }
                        await ws.send(json.dumps(msg))
                        subscribed.add(inst)
                        print(f"[validator] subscribed mark-price: {inst}")
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    except asyncio.TimeoutError:
                        continue
                    try:
                        data = json.loads(raw)
                    except Exception:
                        continue
                    if "data" in data and data.get("arg", {}).get("channel") == "mark-price":
                        for row in data["data"]:
                            inst = row.get("instId")
                            mp = row.get("markPx")
                            if inst and mp:
                                state.latest_marks[inst] = float(mp)
        except Exception as e:
            print(f"[validator] WS error: {e}; reconnecting in 5s")
            try:
                await asyncio.wait_for(stop.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass


async def compare_snapshots(state, snapshot_path, stop):
    """Tail position_snapshots.csv; compute virtual_pnl per new row; log diff."""
    print(f"[validator] watching snapshots: {snapshot_path}")
    while not Path(snapshot_path).exists() and not stop.is_set():
        await asyncio.sleep(2.0)
    last_pos = 0
    headers = None
    while not stop.is_set():
        try:
            with open(snapshot_path, "r", encoding="utf-8") as f:
                f.seek(last_pos)
                if headers is None:
                    header_line = f.readline()
                    if not header_line:
                        await asyncio.sleep(1.0)
                        continue
                    headers = [h.strip() for h in header_line.split(",")]
                    last_pos = f.tell()
                while True:
                    pos_before = f.tell()
                    line = f.readline()
                    if not line:
                        last_pos = pos_before
                        break
                    if not line.strip():
                        continue
                    cols = [c.strip() for c in line.split(",")]
                    if len(cols) < len(headers):
                        f.seek(pos_before)
                        last_pos = pos_before
                        break
                    row = dict(zip(headers, cols))
                    ts = row.get("timestamp")
                    if not ts or ts in state.snapshots_seen:
                        continue
                    state.snapshots_seen.add(ts)
                    async with state.lock:
                        trade = dict(state.current_trade) if state.current_trade else None
                    if not trade:
                        print(f"[validator] snap {ts} - no current trade context; skip")
                        continue
                    L_inst = trade["long_inst"]
                    S_inst = trade["short_inst"]
                    L_mark = state.latest_marks.get(L_inst)
                    S_mark = state.latest_marks.get(S_inst)
                    if L_mark is None or S_mark is None:
                        print(f"[validator] snap {ts} - mark not yet available "
                              f"({L_inst}={L_mark}, {S_inst}={S_mark}); skip")
                        continue
                    L_entry = trade["long_entry"]
                    S_entry = trade["short_entry"]
                    L_cap = trade["capital_long"]
                    S_cap = trade["capital_short"]
                    virtual = (
                        L_cap * (L_mark / L_entry - 1)
                        - S_cap * (S_mark / S_entry - 1)
                    )
                    try:
                        recorded = float(row.get("unrealized_pnl_usdt", 0))
                    except ValueError:
                        recorded = 0.0
                    diff = virtual - recorded
                    write_header = not state.output_csv.exists()
                    with open(state.output_csv, "a", newline="", encoding="utf-8") as out:
                        w = csv.writer(out)
                        if write_header:
                            w.writerow([
                                "timestamp", "pair", "long_inst", "short_inst",
                                "L_entry", "S_entry", "L_cap", "S_cap",
                                "L_mark", "S_mark",
                                "recorded_pnl", "virtual_pnl", "diff", "abs_diff",
                                "within_cent",
                            ])
                        w.writerow([
                            ts, row.get("pair", ""), L_inst, S_inst,
                            f"{L_entry:.6f}", f"{S_entry:.6f}",
                            f"{L_cap:.4f}", f"{S_cap:.4f}",
                            f"{L_mark:.6f}", f"{S_mark:.6f}",
                            f"{recorded:.6f}", f"{virtual:.6f}",
                            f"{diff:+.6f}", f"{abs(diff):.6f}",
                            "yes" if abs(diff) <= CENT else "no",
                        ])
                    flag = "OK" if abs(diff) <= CENT else "OUTSIDE"
                    print(f"[validator] {ts}  rec={recorded:+.4f}  "
                          f"virt={virtual:+.4f}  diff={diff:+.4f}  [{flag}]")
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[validator] snapshot compare error: {e}")
        await asyncio.sleep(2.0)


# ---------------------------------------------------------------- main

async def run():
    run_dir = find_latest_run_dir()
    if not run_dir:
        print("ERR: no run dirs found in Logs/v1/")
        return
    log_path = find_latest_log(run_dir)
    if not log_path:
        print(f"ERR: no log file in {run_dir}")
        return
    snapshot_path = REPORTS_DIR / run_dir.name / "position_snapshots.csv"

    state = State()
    state.run_dir = run_dir
    state.output_csv = OUTPUT_DIR / f"fidelity_{run_dir.name}.csv"

    print(f"[validator] active run: {run_dir.name}")
    print(f"[validator] log:    {log_path}")
    print(f"[validator] snaps:  {snapshot_path}")
    print(f"[validator] output: {state.output_csv}")
    print("[validator] starting; Ctrl+C to stop.")

    stop = asyncio.Event()
    tasks = [
        asyncio.create_task(tail_log(state, log_path, stop)),
        asyncio.create_task(ws_subscribe(state, stop)),
        asyncio.create_task(compare_snapshots(state, snapshot_path, stop)),
    ]
    try:
        await asyncio.gather(*tasks)
    except (KeyboardInterrupt, asyncio.CancelledError):
        stop.set()
        for t in tasks:
            t.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n[validator] stopped.")
