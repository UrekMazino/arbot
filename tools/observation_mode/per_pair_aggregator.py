#!/usr/bin/env python3
"""
B1 v1.1 — Cross-run per-pair aggregation.

Reads all per-run sample CSVs produced by coint_fragility_sampler.py and
aggregates broken_rate by pair across the entire exp_beta_aware_sizing_v1
window. Answers the deferred mechanism question from B1 v1's RISK_OFF
finding: is the elevation (RISK_OFF 23.1% vs RANGE 16.5%) regime-causal
(some pairs become more fragile under RISK_OFF) or pair-selection-driven
(the bot selects different, worse pairs under RISK_OFF)?

The decisive cut: for pairs that appear under BOTH regimes, does their
broken_rate differ between regimes?
- If yes -> regime-causal (the same pair is more fragile under RISK_OFF)
- If no  -> pair-selection-driven (RISK_OFF just selects worse pairs)

Note: per the structural review v1.2 FINAL closure, this is now
informational rather than decision-gating. The Branch A decision is
made. This aggregation is for any future configuration choice.

Stop-and-report guardrails: read-only, no bot contact, no live API.

Usage:
    python tools/observation_mode/per_pair_aggregator.py
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).parent / "output"


def main() -> int:
    sample_csvs = sorted(OUTPUT_DIR.glob("run_*__samples.csv"))
    if not sample_csvs:
        print("ERR: no per-run sample CSVs found. Run coint_fragility_sampler.py first.")
        return 1

    # pair -> regime -> {valid, watch, broken}
    pair_regime: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"valid": 0, "watch": 0, "broken": 0}))
    pair_runs: dict[str, set[str]] = defaultdict(set)

    for csv_path in sample_csvs:
        run_name = csv_path.stem.replace("__samples", "")
        with csv_path.open("r", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                pair = row.get("pair", "unknown")
                regime = row.get("regime", "unknown")
                health = row.get("health", "unknown")
                if pair == "unknown" or health not in ("valid", "watch", "broken"):
                    continue
                pair_regime[pair][regime][health] = pair_regime[pair][regime].get(health, 0) + 1
                pair_runs[pair].add(run_name)

    # Compute per-pair totals + regime split
    rows = []
    for pair, by_regime in pair_regime.items():
        total = 0
        broken = 0
        for reg_d in by_regime.values():
            for k, v in reg_d.items():
                total += v
                if k == "broken":
                    broken += v
        if total == 0:
            continue

        # Per-regime breakdown
        def rate(reg: str) -> tuple[int, int, float | None]:
            d = by_regime.get(reg, {})
            n = sum(d.values())
            br = d.get("broken", 0)
            return (n, br, (br / n) if n else None)

        n_range, br_range, r_range = rate("RANGE")
        n_off, br_off, r_off = rate("RISK_OFF")
        n_trend, br_trend, r_trend = rate("TREND")

        rows.append({
            "pair": pair,
            "n_runs": len(pair_runs[pair]),
            "n_total": total,
            "broken_total": broken,
            "broken_rate_overall": broken / total,
            "n_RANGE": n_range, "br_RANGE": br_range, "rate_RANGE": r_range,
            "n_RISK_OFF": n_off, "br_RISK_OFF": br_off, "rate_RISK_OFF": r_off,
            "n_TREND": n_trend, "br_TREND": br_trend, "rate_TREND": r_trend,
        })

    rows.sort(key=lambda r: r["n_total"], reverse=True)

    # Write per-pair CSV
    out_path = OUTPUT_DIR / "per_pair_summary.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["pair", "n_runs", "n_total", "broken_total", "broken_rate_overall",
                    "n_RANGE", "br_RANGE", "rate_RANGE",
                    "n_RISK_OFF", "br_RISK_OFF", "rate_RISK_OFF",
                    "n_TREND", "br_TREND", "rate_TREND",
                    "delta_RISK_OFF_vs_RANGE"])
        for row in rows:
            delta = ""
            if row["rate_RISK_OFF"] is not None and row["rate_RANGE"] is not None:
                delta = f"{row['rate_RISK_OFF'] - row['rate_RANGE']:+.4f}"
            w.writerow([
                row["pair"], row["n_runs"], row["n_total"], row["broken_total"],
                f"{row['broken_rate_overall']:.4f}",
                row["n_RANGE"], row["br_RANGE"],
                f"{row['rate_RANGE']:.4f}" if row["rate_RANGE"] is not None else "",
                row["n_RISK_OFF"], row["br_RISK_OFF"],
                f"{row['rate_RISK_OFF']:.4f}" if row["rate_RISK_OFF"] is not None else "",
                row["n_TREND"], row["br_TREND"],
                f"{row['rate_TREND']:.4f}" if row["rate_TREND"] is not None else "",
                delta,
            ])

    print(f"Per-pair summary: {out_path.relative_to(PROJECT_ROOT)}")
    print()

    # Stdout report
    print(f"Total distinct pairs observed: {len(rows)}")
    print()
    print("Top pairs by total monitor samples (n_total):")
    print(f"  {'pair':<48} {'n_total':>7} {'broken_rate':>11} {'n_runs':>6}")
    for row in rows[:15]:
        print(f"  {row['pair']:<48} {row['n_total']:>7} {row['broken_rate_overall']:>11.4f} {row['n_runs']:>6}")
    print()

    # Pairs that appear under BOTH RANGE and RISK_OFF (the decisive cut)
    paired_data = [r for r in rows
                   if r["rate_RANGE"] is not None and r["rate_RISK_OFF"] is not None
                   and r["n_RANGE"] >= 5 and r["n_RISK_OFF"] >= 5]
    paired_data.sort(key=lambda r: r["n_total"], reverse=True)

    print(f"Pairs appearing under BOTH RANGE and RISK_OFF (n>=5 each, the decisive cut):")
    print(f"  n={len(paired_data)} pairs")
    print()
    if paired_data:
        print(f"  {'pair':<48} {'rate_RNG':>9} {'rate_ROF':>9} {'delta':>8} {'n_RNG':>5} {'n_ROF':>5}")
        n_higher_off = 0
        n_higher_rng = 0
        sum_delta_weighted = 0.0
        sum_n = 0
        for row in paired_data:
            d = row["rate_RISK_OFF"] - row["rate_RANGE"]
            if d > 0:
                n_higher_off += 1
            elif d < 0:
                n_higher_rng += 1
            n = row["n_RANGE"] + row["n_RISK_OFF"]
            sum_delta_weighted += d * n
            sum_n += n
            print(f"  {row['pair']:<48} {row['rate_RANGE']:>9.4f} {row['rate_RISK_OFF']:>9.4f} "
                  f"{d:>+8.4f} {row['n_RANGE']:>5} {row['n_RISK_OFF']:>5}")
        avg_delta = sum_delta_weighted / sum_n if sum_n else 0.0
        print()
        print(f"  Pairs with higher rate under RISK_OFF: {n_higher_off}/{len(paired_data)}")
        print(f"  Pairs with higher rate under RANGE:    {n_higher_rng}/{len(paired_data)}")
        print(f"  Sample-weighted mean delta (RISK_OFF - RANGE): {avg_delta:+.4f}")
        print()

        # Read the mechanism
        if n_higher_off >= 2 * n_higher_rng and avg_delta > 0.03:
            print("  READ: REGIME-CAUSAL — same pairs are more fragile under RISK_OFF.")
            print("        The RISK_OFF elevation (B1 v1: 23.1% vs 16.5% RANGE aggregate)")
            print("        is a regime property, not pair-selection. Surviving lever:")
            print("        regime-gated entry would address the elevation directly.")
        elif n_higher_off <= n_higher_rng and abs(avg_delta) < 0.03:
            print("  READ: PAIR-SELECTION-DRIVEN — same pairs are NOT systematically more")
            print("        fragile under RISK_OFF. The aggregate elevation comes from the")
            print("        bot selecting a different (worse) pair set under RISK_OFF.")
            print("        Surviving lever: universe restriction, not regime-gating.")
        else:
            print("  READ: MIXED / INSUFFICIENT — small N or noisy split. Either lever is")
            print("        consistent with the data; mechanism not isolated at this N.")
    else:
        print("  No pairs appear under both regimes with n>=5 each — cut is not")
        print("  populated enough to discriminate at this N. Aggregate-only finding")
        print("  (B1 v1: RISK_OFF 23.1% vs RANGE 16.5%) cannot be decomposed by pair.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
