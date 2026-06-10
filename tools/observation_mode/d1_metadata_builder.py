#!/usr/bin/env python3
"""
D1 metadata builder — extracts per-trade metadata for T1-T15 needed by the
unified continuation pre-test (work item v1.1).

For each of the 15 trades, produces a row with:
  - pair (inst_1, inst_2), side ("L1S2" or "S1L2"), entry_ts, exit_ts
  - entry beta (logged at BETA_SIZING line at entry)
  - entry_z, exit_z, hold_min, exit_reason

Output: tools/observation_mode/output/d1_trade_metadata.csv

Read-only on existing CSVs + log files. No live API, no bot code paths.
"""

from __future__ import annotations

import csv
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOGS_DIR = PROJECT_ROOT / "Logs" / "v1"
REPORTS_DIR = PROJECT_ROOT / "Reports" / "v1"
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Trade -> run mapping (matches prior diagnostics).
TRADES = [
    ("T1",  "run_125_*"),
    ("T2",  "run_126_*"),
    ("T3",  "run_129_*"),
    ("T4",  "run_130_*"),
    ("T5",  "run_131_*"),
    ("T6",  "run_132_*"),
    ("T7",  "run_134_*"),
    ("T8",  "run_135_*"),
    ("T9",  "run_136_*"),
    ("T10", "run_137_*"),
    ("T11", "run_138_*"),
    ("T12", "run_139_*"),
    ("T13", "run_140_*"),
    ("T14", "run_141_*"),
    ("T15", "run_142_*"),
]

BETA_SIZING_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+INFO\s+BETA_SIZING:\s+"
    r"beta=(?P<beta>[\d.]+)\s+gross=(?P<gross>[\d.]+)\s+"
    r"capital_long=(?P<cap_long>[\d.]+)\s+capital_short=(?P<cap_short>[\d.]+)\s+"
    r"side=(?P<side>\w+)"
)
TRADE_OPEN_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+INFO\s+STRATEGY_TRADE_OPEN:"
)


def find_run_dirs(run_glob: str) -> tuple[Path, Path]:
    """Return (report_dir, log_dir) for first matching run."""
    rep = sorted(REPORTS_DIR.glob(run_glob))
    log = sorted(LOGS_DIR.glob(run_glob))
    return (rep[0] if rep else None, log[0] if log else None)


def parse_local_to_utc(ts_str: str, utc_offset_hours: int = -8) -> datetime:
    """Bot logs use local time (observed to be UTC+8 in earlier audits — i.e., logs
    are 8h AHEAD of UTC). Convert local timestamp -> UTC.

    NOTE: This needs verification against the matched STRATEGY_TRADE_OPEN UTC
    timestamp from trade_closes.csv. We'll cross-check during extraction.
    """
    dt_local = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    # Naive parse — offset applied at comparison time
    return dt_local.replace(tzinfo=timezone(timedelta(hours=utc_offset_hours)))


def extract_entry_beta(log_path: Path, entry_ts_utc: datetime, search_window_sec: int = 60) -> tuple[float | None, str | None, str | None]:
    """Find the BETA_SIZING line nearest in time to entry_ts_utc (within window).

    Returns (beta, side_marker, raw_log_ts).
    Side marker is 'positive_z' or 'negative_z' from the log line.
    """
    best = None
    best_delta = None
    # Try both UTC+0 and UTC+8 interpretations of log timestamps
    log_offsets = [timedelta(hours=0), timedelta(hours=8)]

    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            # Look for STRATEGY_TRADE_OPEN line and the BETA_SIZING right before it
            m = BETA_SIZING_RE.search(line)
            if not m:
                continue
            log_ts_naive = datetime.strptime(m.group("ts"), "%Y-%m-%d %H:%M:%S")
            for offset in log_offsets:
                log_ts = log_ts_naive.replace(tzinfo=timezone.utc) - offset
                delta = abs((log_ts - entry_ts_utc).total_seconds())
                if delta <= search_window_sec:
                    if best is None or delta < best_delta:
                        best = (float(m.group("beta")), m.group("side"), m.group("ts"))
                        best_delta = delta
    return best if best else (None, None, None)


def build_metadata():
    rows = []
    for trade_id, run_glob in TRADES:
        report_dir, log_dir = find_run_dirs(run_glob)
        if report_dir is None:
            print(f"  WARN: no report dir for {trade_id} ({run_glob})", file=sys.stderr)
            continue
        # Load trade_closes
        trade_csv = report_dir / "trade_closes.csv"
        if not trade_csv.exists():
            print(f"  WARN: no trade_closes.csv for {trade_id}", file=sys.stderr)
            continue
        with trade_csv.open("r", encoding="utf-8") as f:
            r = csv.DictReader(f)
            trade_rows = list(r)
        if not trade_rows:
            print(f"  WARN: empty trade_closes.csv for {trade_id}", file=sys.stderr)
            continue
        tr = trade_rows[0]
        entry_ts = datetime.fromisoformat(tr["entry_ts"])
        exit_ts = datetime.fromisoformat(tr["exit_ts"])
        pair = tr["pair"]  # e.g. "ETH-USDT-SWAP/AVAX-USDT-SWAP" — inst_1/inst_2
        side = tr["side"]  # long_positive_short_negative or long_negative_short_positive
        entry_z = float(tr["entry_z"])
        exit_z = float(tr["exit_z"])
        hold_min = float(tr["hold_minutes"])
        exit_reason = tr["exit_reason"]
        notional = float(tr["entry_notional_usdt"])

        # Extract beta from log (matches the BETA_SIZING line near entry)
        log_file = None
        if log_dir:
            log_files = list(log_dir.glob("log_*.log"))
            log_file = log_files[0] if log_files else None
        beta, side_marker, raw_log_ts = (None, None, None)
        if log_file:
            beta, side_marker, raw_log_ts = extract_entry_beta(log_file, entry_ts)

        # Side -> direction
        # long_positive_short_negative = long signal_positive, short signal_negative = S1L2 in retroactive_beta convention
        # long_negative_short_positive = L1S2
        if side == "long_positive_short_negative":
            side_code = "S1L2"
        elif side == "long_negative_short_positive":
            side_code = "L1S2"
        else:
            side_code = "UNKNOWN"

        inst_1, inst_2 = pair.split("/")
        rows.append({
            "trade_id": trade_id,
            "run": report_dir.name,
            "pair": pair,
            "inst_1": inst_1,
            "inst_2": inst_2,
            "side": side,
            "side_code": side_code,
            "entry_ts_utc": entry_ts.isoformat(),
            "exit_ts_utc": exit_ts.isoformat(),
            "hold_min": f"{hold_min:.4f}",
            "entry_z": f"{entry_z:.6f}",
            "exit_z": f"{exit_z:.6f}",
            "notional_usdt": f"{notional:.2f}",
            "beta": f"{beta:.6f}" if beta is not None else "",
            "beta_log_side": side_marker or "",
            "beta_log_ts": raw_log_ts or "",
            "exit_reason": exit_reason,
        })

    out_path = OUTPUT_DIR / "d1_trade_metadata.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {out_path.relative_to(PROJECT_ROOT)}")

    # Summary
    print()
    print(f"  {'id':<5} {'pair':<35} {'side':<6} {'beta':>8} {'entry_z':>8}")
    for row in rows:
        print(f"  {row['trade_id']:<5} {row['pair']:<35} {row['side_code']:<6} "
              f"{row['beta'] or '-':>8} {row['entry_z']:>8}")

    # Distinct instruments
    instruments = set()
    for row in rows:
        instruments.add(row["inst_1"])
        instruments.add(row["inst_2"])
    print(f"\nDistinct instruments across T1-T15: {len(instruments)}")
    print(f"  {sorted(instruments)}")


if __name__ == "__main__":
    build_metadata()
