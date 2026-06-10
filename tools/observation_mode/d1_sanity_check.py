#!/usr/bin/env python3
"""
D1 sanity check — work item §1.3, two-stage reconstruction validation.

For each of T1-T15, reconstruct the live monitor's z(t) trajectory from
cached klines using the logged β, and compare to the logged z(t) from
position_snapshots.csv. Two stages:

  Stage 1 — LEVELS: mean abs(reconstructed z - logged z) <= 0.10sigma
  Stage 2 — VELOCITIES: mean abs(reconstructed dz - logged dz) <= 0.15sigma/min

Pass criterion: >=13/15 trades clear both stages. Otherwise STOP-AND-REPORT
with verdict INFEASIBLE-INSTRUMENT.

Formula (from Strategy/func_cointegration.py:193 and
Execution/config_execution_api.py:271):
    spread(t) = log(price_1(t)) - β · log(price_2(t))
    z(t)     = (spread(t) - μ_21(spread)) / sigma_21(spread)

Where window=21 (STATBOT_Z_SCORE_WINDOW), inst_1 is the first ticker in the
pair string, inst_2 is the second. Klines used: 1m close.

Known reconstruction error source (flagged for honesty):
- The live monitor may use orderbook-mid as the proxy for the current
  in-flight minute (vs the kline close we use here). This introduces
  small per-snapshot error (~0.01-0.1% on liquid pairs) absorbed by the
  0.10sigma tolerance.
"""

from __future__ import annotations

import csv
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).parent / "output"
CACHE_DIR = OUTPUT_DIR / "kline_cache"
REPORTS_DIR = PROJECT_ROOT / "Reports" / "v1"

Z_WINDOW = 21  # STATBOT_Z_SCORE_WINDOW
LEVEL_TOLERANCE_PER_TRADE = 0.10  # mean abs(z_recon - z_logged) <= 0.10sigma
VELOCITY_TOLERANCE_PER_TRADE = 0.15  # mean abs(dz_recon - dz_logged) <= 0.15sigma/min
MIN_PASS_TRADES = 13  # of 15
EXTREME_LEVEL_TICK_TOLERANCE = 0.5  # any single tick > 0.5sigma off = fail


def load_klines(inst_id: str) -> dict[int, float]:
    """Load cached 1m close prices keyed by ts_ms. Returns ts_ms -> close."""
    path = CACHE_DIR / f"{inst_id}.csv"
    if not path.exists():
        raise FileNotFoundError(f"No kline cache for {inst_id}: {path}")
    out: dict[int, float] = {}
    with path.open("r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                out[int(row["ts_ms"])] = float(row["close"])
            except (KeyError, ValueError):
                continue
    return out


def floor_minute_ms(ts_ms: int) -> int:
    return (ts_ms // 60_000) * 60_000


def get_close_for_ts(klines: dict[int, float], ts_ms: int) -> float | None:
    """Return the close of the 1m bar containing ts_ms."""
    return klines.get(floor_minute_ms(ts_ms))


def load_snapshots(report_dir: Path) -> list[tuple[int, float, float]]:
    """Load (ts_ms, current_z, unrealized_pnl) per snapshot from
    position_snapshots.csv."""
    path = report_dir / "position_snapshots.csv"
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                ts = datetime.fromisoformat(row["timestamp"])
                ts_ms = int(ts.timestamp() * 1000)
                z = float(row["current_z"])
                upl = float(row["unrealized_pnl_usdt"])
                rows.append((ts_ms, z, upl))
            except (KeyError, ValueError):
                continue
    return rows


def reconstruct_z(klines_1: dict[int, float], klines_2: dict[int, float],
                   beta: float, target_ts_ms: int, window: int) -> float | None:
    """Reconstruct z at target_ts_ms using rolling-window log-spread.

    Returns None if insufficient kline data (less than `window` bars
    ending at the target minute).
    """
    target_bar = floor_minute_ms(target_ts_ms)
    # Build log-spread series ending at target_bar, going back `window` bars
    spreads = []
    for i in range(window):
        bar_ms = target_bar - (window - 1 - i) * 60_000
        p1 = klines_1.get(bar_ms)
        p2 = klines_2.get(bar_ms)
        if p1 is None or p2 is None or p1 <= 0 or p2 <= 0:
            return None
        spreads.append(math.log(p1) - beta * math.log(p2))
    mean = sum(spreads) / window
    var = sum((s - mean) ** 2 for s in spreads) / window
    std = math.sqrt(var)
    if std <= 0:
        return None
    current_spread = spreads[-1]
    return (current_spread - mean) / std


def analyze_trade(trade_id: str, run_dir_name: str, inst_1: str, inst_2: str,
                  beta: float, klines_cache: dict[str, dict[int, float]]) -> dict:
    """Reconstruct z trajectory for one trade; compare to logged.
    Returns per-trade stats including stage 1 (levels) and stage 2 (velocities).
    """
    report_dir = REPORTS_DIR / run_dir_name
    snapshots = load_snapshots(report_dir)
    if not snapshots:
        return {"trade_id": trade_id, "n_snapshots": 0, "status": "no_snapshots"}

    k1 = klines_cache[inst_1]
    k2 = klines_cache[inst_2]

    rows = []  # (ts_ms, z_logged, z_recon, level_diff, dz_logged, dz_recon, vel_diff)
    prev_z_logged = None
    prev_z_recon = None
    for ts_ms, z_logged, _upl in snapshots:
        z_recon = reconstruct_z(k1, k2, beta, ts_ms, Z_WINDOW)
        level_diff = (z_recon - z_logged) if z_recon is not None else None
        dz_logged = (z_logged - prev_z_logged) if prev_z_logged is not None else None
        dz_recon = (z_recon - prev_z_recon) if (z_recon is not None and prev_z_recon is not None) else None
        vel_diff = (dz_recon - dz_logged) if (dz_recon is not None and dz_logged is not None) else None
        rows.append((ts_ms, z_logged, z_recon, level_diff, dz_logged, dz_recon, vel_diff))
        prev_z_logged = z_logged
        prev_z_recon = z_recon

    level_diffs = [abs(r[3]) for r in rows if r[3] is not None]
    vel_diffs = [abs(r[6]) for r in rows if r[6] is not None]

    mean_abs_level = sum(level_diffs) / len(level_diffs) if level_diffs else None
    max_abs_level = max(level_diffs) if level_diffs else None
    mean_abs_vel = sum(vel_diffs) / len(vel_diffs) if vel_diffs else None
    max_abs_vel = max(vel_diffs) if vel_diffs else None

    return {
        "trade_id": trade_id,
        "n_snapshots": len(snapshots),
        "n_recon": sum(1 for r in rows if r[2] is not None),
        "mean_abs_level": mean_abs_level,
        "max_abs_level": max_abs_level,
        "mean_abs_vel": mean_abs_vel,
        "max_abs_vel": max_abs_vel,
        "rows": rows,
    }


def main():
    meta_path = OUTPUT_DIR / "d1_trade_metadata.csv"
    if not meta_path.exists():
        print(f"ERR: metadata not found. Run d1_metadata_builder.py first.", file=sys.stderr)
        return 1

    with meta_path.open("r", encoding="utf-8") as f:
        metadata = list(csv.DictReader(f))

    # Pre-load all kline caches
    instruments = set()
    for row in metadata:
        instruments.add(row["inst_1"])
        instruments.add(row["inst_2"])
    klines_cache = {}
    print("Loading kline caches...")
    for inst in sorted(instruments):
        klines_cache[inst] = load_klines(inst)
        print(f"  {inst:<20} {len(klines_cache[inst])} bars")
    print()

    # Run sanity check per trade
    print("=" * 96)
    print("D1 sanity check — work item §1.3 two-stage reconstruction validation")
    print("=" * 96)
    print()
    print(f"  {'trade':<6} {'n_snap':>7} {'n_recon':>8} {'mean|dz|':>10} {'max|dz|':>9} "
          f"{'mean|ddz|':>11} {'max|ddz|':>10} {'stage1':>8} {'stage2':>8}")

    per_trade_stats = []
    stage1_pass = 0
    stage2_pass = 0
    extreme_level_fail = 0
    for row in metadata:
        beta = float(row["beta"]) if row["beta"] else None
        if beta is None:
            print(f"  {row['trade_id']:<6} SKIP — no beta")
            continue
        result = analyze_trade(
            row["trade_id"], row["run"], row["inst_1"], row["inst_2"],
            beta, klines_cache,
        )
        per_trade_stats.append(result)

        if result.get("status") == "no_snapshots":
            print(f"  {result['trade_id']:<6} (no snapshots)")
            continue

        mean_abs_level = result.get("mean_abs_level")
        max_abs_level = result.get("max_abs_level")
        mean_abs_vel = result.get("mean_abs_vel")
        max_abs_vel = result.get("max_abs_vel")

        s1_pass = (mean_abs_level is not None and
                   mean_abs_level <= LEVEL_TOLERANCE_PER_TRADE and
                   (max_abs_level or 0) <= EXTREME_LEVEL_TICK_TOLERANCE)
        s2_pass = (mean_abs_vel is not None and mean_abs_vel <= VELOCITY_TOLERANCE_PER_TRADE)
        if s1_pass:
            stage1_pass += 1
        if s2_pass:
            stage2_pass += 1
        if max_abs_level is not None and max_abs_level > EXTREME_LEVEL_TICK_TOLERANCE:
            extreme_level_fail += 1

        def fmt(v, w=10):
            return f"{v:>{w}.4f}" if v is not None else " " * (w - 1) + "—"

        print(f"  {result['trade_id']:<6} {result['n_snapshots']:>7} {result['n_recon']:>8} "
              f"{fmt(mean_abs_level)} {fmt(max_abs_level, 9)} "
              f"{fmt(mean_abs_vel, 11)} {fmt(max_abs_vel, 10)} "
              f"{('PASS' if s1_pass else 'FAIL'):>8} "
              f"{('PASS' if s2_pass else 'FAIL'):>8}")

    print()
    print(f"Stage 1 (levels):    {stage1_pass}/{len(per_trade_stats)} trades pass "
          f"(threshold: mean|dz| <= {LEVEL_TOLERANCE_PER_TRADE}sigma, max|dz| <= "
          f"{EXTREME_LEVEL_TICK_TOLERANCE}sigma)")
    print(f"Stage 2 (velocities):{stage2_pass}/{len(per_trade_stats)} trades pass "
          f"(threshold: mean|ddz| <= {VELOCITY_TOLERANCE_PER_TRADE}sigma/min)")
    print(f"Extreme single-tick level failures (>0.5sigma): {extreme_level_fail} trades")
    print()

    # Write per-tick CSV
    out = OUTPUT_DIR / "d1_sanity_check_per_tick.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["trade_id", "ts_ms", "z_logged", "z_recon", "level_diff",
                    "dz_logged", "dz_recon", "vel_diff"])
        for stat in per_trade_stats:
            if not stat.get("rows"):
                continue
            for ts_ms, z_l, z_r, ld, dzl, dzr, vd in stat["rows"]:
                def f(v):
                    return f"{v:.6f}" if v is not None else ""
                w.writerow([stat["trade_id"], ts_ms, f(z_l), f(z_r), f(ld),
                            f(dzl), f(dzr), f(vd)])
    print(f"Per-tick data: {out.relative_to(PROJECT_ROOT)}")

    # Verdict
    print()
    print("=" * 96)
    print("VERDICT")
    print("=" * 96)
    if stage1_pass >= MIN_PASS_TRADES and stage2_pass >= MIN_PASS_TRADES and extreme_level_fail == 0:
        print(f"PASS — Kline-based z reconstruction is trustworthy.")
        print(f"  Both stages clear >={MIN_PASS_TRADES}/15 trades; no extreme single-tick failures.")
        print(f"  Proceed to §2 (trigger extraction).")
        return 0
    else:
        print(f"INFEASIBLE-INSTRUMENT")
        print(f"  Stage 1: {stage1_pass}/{len(per_trade_stats)} pass (need >={MIN_PASS_TRADES})")
        print(f"  Stage 2: {stage2_pass}/{len(per_trade_stats)} pass (need >={MIN_PASS_TRADES})")
        print(f"  Extreme tick failures: {extreme_level_fail} (need 0)")
        print(f"  The kline-based reconstruction does not support the unconditioned-event")
        print(f"  analysis. Per work item §1.3: report as INFEASIBLE-INSTRUMENT — distinct")
        print(f"  from CONTINUATION-DEAD. The data layer beneath the simulation logic is")
        print(f"  itself the failure point. Strategist decides whether to commission a")
        print(f"  finer-grained data source or close the pre-test.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
