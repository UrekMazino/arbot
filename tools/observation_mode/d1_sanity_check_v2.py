#!/usr/bin/env python3
"""
D1 sanity check v2 — work item §1.3-bis, RE-SPECCED differenced-quantity gate.

ONE re-spec only (strategist bind). The original §1.3 gate (level + velocity
reconstruction of the bot's z) failed 0/15 — the bot's internal basis is not
reconstructable from public klines (third converging diagnostic; see
docs/audits/d1_sanity_check_infeasible_2026-05-31.md). This gate tests the
quantity the pre-test ACTUALLY uses: windowed position-PnL CHANGES, where the
structural basis offset cancels in differences.

THE GATE (pre-committed before run):
  On the in-trade overlap windows, mean abs(kline-derived position-PnL change
  - logged upl change) over matched 5-15 minute intervals <= $0.03 at $200
  notional, passing on >= 13/15 trades.

Kline-derived PnL change over interval (a, b):
  delta_kline = eff_qty_long * (close_L(b) - close_L(a))
              - eff_qty_short * (close_S(b) - close_S(a))
where eff_qty_leg = capital_leg / preview_price_leg. Capitals come from the
BETA_SIZING log line nearest before STRATEGY_TRADE_OPEN (verified exact to
the cent 15/15 in the experiment); prices from the Entry preview line at the
same moment. This sidesteps the OKX contract-multiplier convention entirely
(preview qty is in CONTRACTS with per-instrument ctVal — e.g. BNB 0.01,
ARB 10 — which broke the naive qty*price=capital assumption on 7/15 trades;
caught by the gross-plausibility guard on the first run, fixed as an
implementation bug, NOT a gate change). Same formula as the §5 fidelity
validator sidecar: cap * (P(b)-P(a))/P_entry. The preview price enters only
as the capital-to-coins conversion; bps-level basis error in it is
second-order on a windowed change.

Logged PnL change: upl(b) - upl(a) from position_snapshots.csv.

Matched intervals: all snapshot pairs (i, j) within a trade's hold with
5 min <= t_j - t_i <= 15 min.

HANDLING:
- T7 and T10 have 1 snapshot each -> zero intervals -> INSUFFICIENT-INTERVALS,
  counted as NON-passing (strictest consistent reading of >=13/15: the 13
  evaluable trades must all pass).
- Missing kline bars: interval skipped, not imputed; skips counted.
- Timestamp hard-verification (strategist implementation note c): metadata
  entry/exit UTC must match trade_closes.csv entry_ts/exit_ts within 5 s
  for every trade BEFORE any window extraction. Mismatch = STOP.

BIND (verbatim consequence): if this gate fails, INFEASIBLE-INSTRUMENT is
DEFINITIVE. No second re-spec. The D1 pre-test closes; the kline cache and
tooling remain as reusable assets; the pivot decision returns to the operator
with "the premise couldn't be cheaply tested" as its honest status.

Usage:
    python tools/observation_mode/d1_sanity_check_v2.py
"""

from __future__ import annotations

import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).parent / "output"
CACHE_DIR = OUTPUT_DIR / "kline_cache"
REPORTS_DIR = PROJECT_ROOT / "Reports" / "v1"
LOGS_DIR = PROJECT_ROOT / "Logs" / "v1"
METADATA_CSV = OUTPUT_DIR / "d1_trade_metadata.csv"

GATE_TOLERANCE_USD = 0.03      # mean abs(delta_kline - delta_logged) per trade
MIN_PASS_TRADES = 13           # of 15
INTERVAL_MIN_MIN = 5.0         # matched interval lower bound (minutes)
INTERVAL_MAX_MIN = 15.0        # matched interval upper bound (minutes)
TS_VERIFY_TOLERANCE_S = 5.0    # metadata vs trade_closes timestamp agreement

ENTRY_PREVIEW_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+INFO\s+Entry preview:\s+"
    r"long=(?P<long_inst>\S+)\s+price=(?P<long_price>[\d.]+)\s+qty=(?P<long_qty>[\d.]+)\s+\|\s+"
    r"short=(?P<short_inst>\S+)\s+price=(?P<short_price>[\d.]+)\s+qty=(?P<short_qty>[\d.]+)"
)
BETA_SIZING_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+INFO\s+BETA_SIZING:\s+"
    r"beta=(?P<beta>[\d.]+)\s+gross=(?P<gross>[\d.]+)\s+"
    r"capital_long=(?P<cap_long>[\d.]+)\s+capital_short=(?P<cap_short>[\d.]+)"
)
TRADE_OPEN_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+\s+INFO\s+STRATEGY_TRADE_OPEN:"
)


def floor_minute_ms(ts_ms: int) -> int:
    return (ts_ms // 60_000) * 60_000


def load_klines(inst_id: str) -> dict[int, float]:
    path = CACHE_DIR / f"{inst_id}.csv"
    if not path.exists():
        raise FileNotFoundError(f"No kline cache for {inst_id}: {path}")
    out: dict[int, float] = {}
    with path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                out[int(row["ts_ms"])] = float(row["close"])
            except (KeyError, ValueError):
                continue
    return out


def load_metadata() -> list[dict]:
    with METADATA_CSV.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def find_report_dir(run_name: str) -> Path | None:
    d = REPORTS_DIR / run_name
    return d if d.exists() else None


def find_log(run_name: str) -> Path | None:
    d = LOGS_DIR / run_name
    if not d.exists():
        return None
    logs = list(d.glob("log_*.log"))
    return logs[0] if logs else None


def verify_timestamps(meta: dict, report_dir: Path) -> tuple[bool, str]:
    """Implementation note (c): hard-verify metadata UTC timestamps against
    trade_closes.csv before any window extraction."""
    tc = report_dir / "trade_closes.csv"
    if not tc.exists():
        return False, "trade_closes.csv missing"
    with tc.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return False, "trade_closes.csv empty"
    row = rows[0]  # one trade per run in this window
    try:
        tc_entry = datetime.fromisoformat(row["entry_ts"])
        tc_exit = datetime.fromisoformat(row["exit_ts"])
        md_entry = datetime.fromisoformat(meta["entry_ts_utc"])
        md_exit = datetime.fromisoformat(meta["exit_ts_utc"])
    except (KeyError, ValueError) as exc:
        return False, f"timestamp parse failure: {exc}"
    d_entry = abs((tc_entry - md_entry).total_seconds())
    d_exit = abs((tc_exit - md_exit).total_seconds())
    if d_entry > TS_VERIFY_TOLERANCE_S or d_exit > TS_VERIFY_TOLERANCE_S:
        return False, f"mismatch: entry delta={d_entry:.1f}s exit delta={d_exit:.1f}s"
    return True, f"OK (entry delta={d_entry:.1f}s, exit delta={d_exit:.1f}s)"


def extract_entry_legs(log_path: Path) -> dict | None:
    """Entry preview + BETA_SIZING lines nearest BEFORE the STRATEGY_TRADE_OPEN
    line. Effective coin quantities = logged leg capital / preview price —
    sidesteps the contract-multiplier (ctVal) convention in the preview's qty.
    Returns {long_inst, eff_qty_long, short_inst, eff_qty_short, ...} or None."""
    last_preview: dict | None = None
    last_sizing: dict | None = None
    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = ENTRY_PREVIEW_RE.match(line)
            if m:
                last_preview = {
                    "long_inst": m.group("long_inst"),
                    "long_price": float(m.group("long_price")),
                    "short_inst": m.group("short_inst"),
                    "short_price": float(m.group("short_price")),
                }
                continue
            s = BETA_SIZING_RE.match(line)
            if s:
                last_sizing = {
                    "cap_long": float(s.group("cap_long")),
                    "cap_short": float(s.group("cap_short")),
                    "gross": float(s.group("gross")),
                }
                continue
            if TRADE_OPEN_RE.match(line) and last_preview is not None and last_sizing is not None:
                return {
                    "long_inst": last_preview["long_inst"],
                    "short_inst": last_preview["short_inst"],
                    "long_price": last_preview["long_price"],
                    "short_price": last_preview["short_price"],
                    "cap_long": last_sizing["cap_long"],
                    "cap_short": last_sizing["cap_short"],
                    "gross": last_sizing["gross"],
                    "eff_qty_long": last_sizing["cap_long"] / last_preview["long_price"],
                    "eff_qty_short": last_sizing["cap_short"] / last_preview["short_price"],
                }
    return None


def load_snapshots(report_dir: Path) -> list[tuple[int, float]]:
    """(ts_ms, upl) per snapshot."""
    path = report_dir / "position_snapshots.csv"
    rows: list[tuple[int, float]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                ts = datetime.fromisoformat(row["timestamp"])
                rows.append((int(ts.timestamp() * 1000), float(row["unrealized_pnl_usdt"])))
            except (KeyError, ValueError):
                continue
    rows.sort(key=lambda r: r[0])
    return rows


def main() -> int:
    print("=" * 100)
    print("D1 sanity check v2 — §1.3-bis RE-SPECCED differenced-quantity gate (ONE re-spec only)")
    print("=" * 100)
    print()

    meta_rows = load_metadata()

    # ---- Step 0: timestamp hard verification (implementation note c) ----
    print("Step 0 — timestamp hard-verification (metadata vs trade_closes.csv UTC):")
    ts_failures = []
    for meta in meta_rows:
        report_dir = find_report_dir(meta["run"])
        if report_dir is None:
            ts_failures.append((meta["trade_id"], "report dir missing"))
            continue
        ok, msg = verify_timestamps(meta, report_dir)
        status = "OK " if ok else "FAIL"
        print(f"  {meta['trade_id']:<5} {status} {msg}")
        if not ok:
            ts_failures.append((meta["trade_id"], msg))
    if ts_failures:
        print()
        print("STOP: timestamp verification failed — window extraction would be corrupted.")
        for tid, msg in ts_failures:
            print(f"  {tid}: {msg}")
        return 1
    print("  All 15 trades verified. Proceeding.")
    print()

    # ---- Per-trade gate ----
    per_trade_rows = []
    results = []  # (trade_id, status, mean_err, max_err, n_intervals, n_skipped)

    for meta in meta_rows:
        tid = meta["trade_id"]
        run = meta["run"]
        report_dir = find_report_dir(run)
        log_path = find_log(run)
        if report_dir is None or log_path is None:
            results.append((tid, "DATA-MISSING", None, None, 0, 0))
            continue

        legs = extract_entry_legs(log_path)
        if legs is None:
            results.append((tid, "NO-ENTRY-PREVIEW", None, None, 0, 0))
            continue

        # Sanity: BETA_SIZING gross must be plausible for a $200 trade.
        if not (140.0 <= legs["gross"] <= 260.0):
            results.append((tid, f"GROSS-IMPLAUSIBLE ({legs['gross']:.0f})", None, None, 0, 0))
            continue

        snaps = load_snapshots(report_dir)
        if len(snaps) < 2:
            results.append((tid, "INSUFFICIENT-INTERVALS", None, None, 0, 0))
            continue

        kl_long = load_klines(legs["long_inst"])
        kl_short = load_klines(legs["short_inst"])

        errs = []
        n_skipped = 0
        lo_ms = INTERVAL_MIN_MIN * 60_000
        hi_ms = INTERVAL_MAX_MIN * 60_000
        for i in range(len(snaps)):
            for j in range(i + 1, len(snaps)):
                dt_ms = snaps[j][0] - snaps[i][0]
                if dt_ms < lo_ms:
                    continue
                if dt_ms > hi_ms:
                    break
                la = kl_long.get(floor_minute_ms(snaps[i][0]))
                lb = kl_long.get(floor_minute_ms(snaps[j][0]))
                sa = kl_short.get(floor_minute_ms(snaps[i][0]))
                sb = kl_short.get(floor_minute_ms(snaps[j][0]))
                if None in (la, lb, sa, sb):
                    n_skipped += 1
                    continue
                delta_kline = legs["eff_qty_long"] * (lb - la) - legs["eff_qty_short"] * (sb - sa)
                delta_logged = snaps[j][1] - snaps[i][1]
                err = abs(delta_kline - delta_logged)
                errs.append(err)
                per_trade_rows.append({
                    "trade_id": tid,
                    "t_i_ms": snaps[i][0], "t_j_ms": snaps[j][0],
                    "interval_min": dt_ms / 60_000.0,
                    "delta_kline": delta_kline,
                    "delta_logged": delta_logged,
                    "abs_err": err,
                })

        if not errs:
            results.append((tid, "NO-EVALUABLE-INTERVALS", None, None, 0, n_skipped))
            continue

        mean_err = sum(errs) / len(errs)
        max_err = max(errs)
        status = "PASS" if mean_err <= GATE_TOLERANCE_USD else "FAIL"
        results.append((tid, status, mean_err, max_err, len(errs), n_skipped))

    # ---- Report ----
    print("Per-trade results (gate: mean |delta_kline - delta_logged| <= $0.03 on matched 5-15 min intervals):")
    print(f"  {'trade':<6} {'status':<24} {'mean_err':>9} {'max_err':>9} {'n_int':>6} {'skipped':>8}")
    n_pass = 0
    for tid, status, mean_err, max_err, n_int, n_skip in results:
        me = f"{mean_err:.4f}" if mean_err is not None else "—"
        mx = f"{max_err:.4f}" if max_err is not None else "—"
        print(f"  {tid:<6} {status:<24} {me:>9} {mx:>9} {n_int:>6} {n_skip:>8}")
        if status == "PASS":
            n_pass += 1
    print()
    print(f"Passing trades: {n_pass}/15 (gate requires >= {MIN_PASS_TRADES})")
    print()

    # Persist per-interval data
    out_csv = OUTPUT_DIR / "d1_sanity_check_v2_per_interval.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["trade_id", "t_i_ms", "t_j_ms", "interval_min",
                    "delta_kline", "delta_logged", "abs_err"])
        for row in per_trade_rows:
            w.writerow([row["trade_id"], row["t_i_ms"], row["t_j_ms"],
                        f"{row['interval_min']:.2f}",
                        f"{row['delta_kline']:+.4f}",
                        f"{row['delta_logged']:+.4f}",
                        f"{row['abs_err']:.4f}"])
    print(f"Per-interval data: {out_csv.relative_to(PROJECT_ROOT)}")
    print()

    # ---- Verdict ----
    print("=" * 100)
    print("VERDICT (per §1.3-bis pre-commit; ONE re-spec only — this result is final either way)")
    print("=" * 100)
    if n_pass >= MIN_PASS_TRADES:
        print("GATE PASS")
        print(f"  {n_pass}/15 trades within $0.03 mean error on differenced quantities.")
        print("  The windowed-PnL-change instrument is validated against logged upl ground")
        print("  truth. The pre-test proceeds on honest instruments: the bot's logged broken")
        print("  flag + the kline-velocity detector (both deployable). Next: trigger")
        print("  extraction (work item §2) and the simulation loop (§3).")
        verdict = "GATE-PASS"
    else:
        print("INFEASIBLE-INSTRUMENT — DEFINITIVE")
        print(f"  Only {n_pass}/15 trades within $0.03 mean error (need >= {MIN_PASS_TRADES}).")
        print("  Even in differenced quantities, the basis offset is not stable enough for")
        print("  kline-derived outcomes to track logged ground truth. Per the strategist's")
        print("  bind: NO second re-spec. The D1 pre-test CLOSES on INFEASIBLE-INSTRUMENT.")
        print("  The kline cache and tooling remain as reusable assets. The pivot decision")
        print("  returns to the operator with 'the premise couldn't be cheaply tested' as")
        print("  its honest status — which itself weighs toward D3 or stop.")
        verdict = "INFEASIBLE-INSTRUMENT-DEFINITIVE"
    print()
    print(f"Verdict: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
