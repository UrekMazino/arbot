#!/usr/bin/env python3
"""
D3 Design Phase A — Funding Reality (measurement, no verdict surface).

Per work item docs/prompts/work_item_d3_design_phase.md (v1.0, commit
d9efdcc). Replaces the pre-test's assumed funding stacks
({$0.44, $0.74, $1.94} for a 10-day hold, both legs charged as paying)
with the MEASURED pair-level funding differential: a pairs position is
one long + one short, so net funding per event is
(r_long - r_short) x leg notional — rates on correlated perps may
largely cancel, or diverge on one leg.

Method:
- Pull funding-rate history (public endpoint, no auth) for the 44
  qualified instruments over the cached window; cache to
  output/funding_cache/<INST>.csv.
- For each of the 672 pairs that contributed to the pre-test's +10d
  population, sample 10-day windows stepping every 5 days over the
  common funding history; net_usd = sum over events of
  (r_1 - r_2) x $100 (central beta case: ~$100/leg at $200 gross).
- Report distribution of |net_usd| (funding cost/risk magnitude):
  p50 / p90 / p99. These feed Phase B's two cost levels.

Read-only. Public endpoint. No bot contact.

Usage:
    python tools/observation_mode/d3_funding_reality.py
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

import certifi
import numpy as np
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).parent / "output"
FUNDING_CACHE = OUTPUT_DIR / "funding_cache"
FUNDING_CACHE.mkdir(parents=True, exist_ok=True)

OKX_BASE = "https://www.okx.com"
FUNDING_PATH = "/api/v5/public/funding-rate-history"

LEG_NOTIONAL = 100.0       # central beta case at $200 gross
WINDOW_DAYS = 10
STEP_DAYS = 5
MAX_RECORDS = 1300         # ~400 days x 3/day + slack


def fetch_funding(inst: str) -> int:
    path = FUNDING_CACHE / f"{inst}.csv"
    if path.exists():
        with path.open(encoding="utf-8") as f:
            return sum(1 for _ in f) - 1
    rows: list[tuple[int, float]] = []
    after = ""
    while len(rows) < MAX_RECORDS:
        params = {"instId": inst, "limit": "100"}
        if after:
            params["after"] = after
        try:
            r = requests.get(OKX_BASE + FUNDING_PATH, params=params, timeout=20,
                             verify=certifi.where())
            data = r.json()
        except Exception as e:
            print(f"    {inst}: fetch error {type(e).__name__}", file=sys.stderr)
            break
        if data.get("code") != "0" or not data.get("data"):
            break
        page = data["data"]
        for rec in page:
            try:
                rows.append((int(rec["fundingTime"]), float(rec["fundingRate"])))
            except (KeyError, ValueError):
                continue
        after = page[-1]["fundingTime"]
        if len(page) < 100:
            break
        time.sleep(0.12)
    rows.sort()
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["funding_time_ms", "rate"])
        for ts, rate in rows:
            w.writerow([ts, rate])
    return len(rows)


def load_funding(inst: str) -> dict[int, float]:
    path = FUNDING_CACHE / f"{inst}.csv"
    if not path.exists():
        return {}
    out = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[int(row["funding_time_ms"])] = float(row["rate"])
    return out


def main() -> int:
    # Pair population: the pre-test's contributing pairs
    results_csv = OUTPUT_DIR / "d3_pair_fold_results.csv"
    if not results_csv.exists():
        print("ERR: run d3_daily_coint_pretest.py first")
        return 1
    pairs = sorted({r["pair"] for r in csv.DictReader(results_csv.open(encoding="utf-8"))})
    insts = sorted({leg for p in pairs for leg in p.split("/")})
    print(f"Pairs from pre-test population: {len(pairs)}; instruments: {len(insts)}")

    print("Fetching funding-rate history (cache-aware)...")
    counts = {}
    for inst in insts:
        counts[inst] = fetch_funding(inst)
    have = [i for i in insts if counts[i] >= 60]   # >= ~20 days of history
    missing = [(i, counts[i]) for i in insts if counts[i] < 60]
    print(f"Instruments with usable funding history: {len(have)}")
    if missing:
        print(f"Insufficient funding history (skipped): {missing}")

    funding = {i: load_funding(i) for i in have}

    # Per-instrument context
    all_rates = [r for i in have for r in funding[i].values()]
    print(f"\nPer-event funding rate (all instruments, n={len(all_rates)}):")
    print(f"  median {np.median(all_rates):+.5%}   p10 {np.percentile(all_rates, 10):+.5%}   "
          f"p90 {np.percentile(all_rates, 90):+.5%}")

    # Pair-level 10-day |net| distribution
    window_ms = WINDOW_DAYS * 86_400_000
    step_ms = STEP_DAYS * 86_400_000
    nets: list[float] = []
    per_pair_p90: dict[str, float] = {}
    for p in pairs:
        a, b = p.split("/")
        if a not in funding or b not in funding:
            continue
        common = sorted(set(funding[a]) & set(funding[b]))
        if len(common) < 30:
            continue
        t0, t1 = common[0], common[-1]
        pair_nets = []
        t = t0
        while t + window_ms <= t1:
            evs = [ts for ts in common if t <= ts < t + window_ms]
            if len(evs) >= 24:  # >= 8 days' worth of events present
                net = sum(funding[a][ts] - funding[b][ts] for ts in evs) * LEG_NOTIONAL
                pair_nets.append(abs(net))
            t += step_ms
        if pair_nets:
            nets.extend(pair_nets)
            per_pair_p90[p] = float(np.percentile(pair_nets, 90))

    nets_arr = np.array(nets)
    print(f"\nPair-level |net funding| per 10-day hold at $200 gross "
          f"(n={len(nets_arr)} windows across {len(per_pair_p90)} pairs):")
    p50, p90, p99 = (float(np.percentile(nets_arr, q)) for q in (50, 90, 99))
    print(f"  p50 = ${p50:.3f}   p90 = ${p90:.3f}   p99 = ${p99:.3f}   max = ${nets_arr.max():.3f}")

    print(f"\nComparison vs the pre-test's ASSUMED stacks (both legs charged as paying):")
    print(f"  assumed low/mid/high funding component: $0.30 / $0.60 / $1.80")
    print(f"  MEASURED pair-differential funding:     p50 ${p50:.2f} / p90 ${p90:.2f} / p99 ${p99:.2f}")

    print(f"\nPhase B cost levels (per work item: $0.14 entry/exit + measured funding):")
    print(f"  BASE  = $0.14 + p50 = ${0.14 + p50:.3f}")
    print(f"  STRESS = $0.28 (2x slippage) + p90 = ${0.28 + p90:.3f}")

    # Persist summary
    out = OUTPUT_DIR / "d3_funding_summary.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value_usd"])
        w.writerow(["pair_10d_net_p50", round(p50, 4)])
        w.writerow(["pair_10d_net_p90", round(p90, 4)])
        w.writerow(["pair_10d_net_p99", round(p99, 4)])
        w.writerow(["phase_b_base_cost", round(0.14 + p50, 4)])
        w.writerow(["phase_b_stress_cost", round(0.28 + p90, 4)])
    print(f"\nsummary: {out.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
