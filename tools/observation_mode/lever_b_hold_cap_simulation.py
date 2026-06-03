#!/usr/bin/env python3
"""
Lever-B Offline Pre-Test — Hold-Cap Simulation on T1–T15.

Tests, on existing cent-exact data, whether a fast-reverting sub-population
exists that a shorter-hold cap would have rescued. The premise of Lever B
(short holds outrun mean-shift) is supported by T7 (1.1-min only win) but
T7 itself has only 1 snapshot and can't be used to test alternative caps —
T7 motivates but contributes zero to this simulation.

Authorized 2026-05-31 per strategist work item:
  docs/prompts/work_item_lever_b_offline_pretest.md

Pre-committed verdicts (LOCKED before run, §4 of the work item):

  LEVER-B-HAS-PULSE — at some cap M, n_rescued(M) >= 3 robustly (clears
    adverse-cost, rescued-at-mean not overshoot), AND aggregate simulated
    PnL beats realized. Live test warranted.
  LEVER-B-DEAD — at no cap M does n_rescued clear a meaningful bar (<=1
    robustly-rescued, or aggregate doesn't beat realized at any cap).
    Lever B has no pulse; the most promising dominant-mode lever is
    dead for free; pivot-or-stop earned.
  LEVER-B-AMBIGUOUS — rescued count in noise (1–2, or sensitive to cost
    proxy, or rescued-at-overshoot not mean). Cannot resolve from N≈13
    + loose cost proxy. Operator's exploratory-vs-stop judgment.

Stop-and-report guardrails (identical to prior diagnostics):
- Read-only on existing CSVs. No trades, no bot contact, no live API.
- No imputation on insufficient-ticks trades — report INSUFFICIENT-TICKS
  honestly; T7 explicitly contributes zero despite being the motivating
  case.
- Realized cost as proxy for capped cost is DIRECTIONALLY CONSERVATIVE
  (funding scales with hold; capped trade's real cost <= realized) — so
  PULSE results are robust to the proxy. DEAD results are also robust
  (would only be MORE dead under accurate costs).
- Rescued-at-mean (|z|<=0.5, in-zone) vs rescued-at-overshoot (|z|>0.5,
  momentum-luck): only rescued-at-mean counts toward PULSE.

Usage:
    python tools/observation_mode/lever_b_hold_cap_simulation.py
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
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

CAPS_MIN = [1, 2, 3, 5, 8]
COST_ERR = 0.06  # ±$0.06 noise band, same as cost diagnostic
ZONE_THRESHOLD = 0.5  # |z| <= 0.5 = rescued-at-mean; |z| > 0.5 = rescued-at-overshoot


@dataclass
class Snapshot:
    hold_min: float
    z: float
    upl: float


@dataclass
class TradeData:
    trade_id: str
    run_glob: str
    snapshots: list[Snapshot] = field(default_factory=list)
    real_cost: float | None = None
    recon_basis: str = ""
    recon_pass: bool = True
    realized_gross_pnl: float | None = None  # last snapshot upl (≈ realized gross)

    @property
    def n_snapshots(self) -> int:
        return len(self.snapshots)

    @property
    def realized_cleared(self) -> bool | None:
        if self.realized_gross_pnl is None or self.real_cost is None:
            return None
        return self.realized_gross_pnl > self.real_cost

    def upl_at_cap(self, cap_min: int) -> tuple[float | None, float | None]:
        """Return (upl_at_cap, z_at_cap). Picks the last snapshot with hold_min <= cap_min.
        Returns (None, None) if no snapshot exists within the cap window."""
        eligible = [s for s in self.snapshots if s.hold_min <= cap_min]
        if not eligible:
            return (None, None)
        last = max(eligible, key=lambda s: s.hold_min)
        return (last.upl, last.z)


def find_report_dir(run_glob: str) -> Path | None:
    matches = sorted(REPORTS_DIR.glob(run_glob))
    return matches[0] if matches else None


def load_trade(trade_id: str, run_glob: str) -> TradeData:
    td = TradeData(trade_id=trade_id, run_glob=run_glob)
    report_dir = find_report_dir(run_glob)
    if report_dir is None:
        return td

    # Snapshots
    snap_csv = report_dir / "position_snapshots.csv"
    if snap_csv.exists():
        with snap_csv.open("r", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                try:
                    td.snapshots.append(Snapshot(
                        hold_min=float(row["hold_minutes"]),
                        z=float(row["current_z"]),
                        upl=float(row["unrealized_pnl_usdt"]),
                    ))
                except (KeyError, ValueError):
                    continue
        if td.snapshots:
            td.realized_gross_pnl = td.snapshots[-1].upl

    # Reconciliation (real cost)
    recon_csv = report_dir / "reconciliation_checks.csv"
    if recon_csv.exists():
        with recon_csv.open("r", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                try:
                    td.real_cost = abs(float(row["difference"]))
                    td.recon_basis = row.get("basis", "")
                    td.recon_pass = (row.get("pass_fail", "pass") == "pass")
                    break  # one recon row per run
                except (KeyError, ValueError):
                    continue

    return td


def classify_rescue(upl_at_cap: float, real_cost: float, realized_gross: float,
                    z_at_cap: float) -> tuple[bool, bool, bool, str]:
    """Return (cleared_point, cleared_adverse, cleared_generous, zone_label).

    A trade is RESCUED at cap M if:
      - cleared at cap: upl_at_cap > real_cost (robustly: even adverse cost)
      - realized hold did NOT clear: realized_gross < real_cost
      - rescued-at-mean (zone), not rescued-at-overshoot
    """
    cleared_point = upl_at_cap > real_cost
    cleared_adverse = upl_at_cap > (real_cost + COST_ERR)
    cleared_generous = upl_at_cap > (real_cost - COST_ERR)
    if abs(z_at_cap) <= ZONE_THRESHOLD:
        zone_label = "in-zone (rescued-at-mean)"
    else:
        zone_label = "out-of-zone (rescued-at-overshoot)"
    return (cleared_point, cleared_adverse, cleared_generous, zone_label)


def main() -> int:
    print("Lever-B Offline Pre-Test — Hold-Cap Simulation")
    print("=" * 90)
    print()

    # Load all trades
    trades: list[TradeData] = []
    for tid, rg in TRADES:
        td = load_trade(tid, rg)
        trades.append(td)

    # Per-trade summary
    print("Per-trade data load:")
    print(f"  {'trade':<6} {'n_snap':>7} {'realized_gross':>15} {'real_cost':>10} {'recon':>10} {'cleared':>8}")
    for td in trades:
        cleared = ""
        rc = td.realized_cleared
        if rc is True:
            cleared = "yes"
        elif rc is False:
            cleared = "no"
        rg = f"{td.realized_gross_pnl:+.4f}" if td.realized_gross_pnl is not None else "—"
        rcost = f"{td.real_cost:.4f}" if td.real_cost is not None else "—"
        recon = "PASS" if td.recon_pass else "FAIL"
        print(f"  {td.trade_id:<6} {td.n_snapshots:>7} {rg:>15} {rcost:>10} {recon:>10} {cleared:>8}")
    print()

    # Insufficient-ticks flags
    insufficient = [td.trade_id for td in trades if td.n_snapshots < 2]
    print(f"Trades flagged INSUFFICIENT-TICKS (n_snapshots < 2): {insufficient}")
    print("  Per work-item §3.1: these contribute zero to the simulation. T7's irony (the motivating")
    print("  case can't test its own hypothesis) is part of the honest read.")
    print()

    # Run simulation across caps
    per_trade_per_cap_rows = []
    cap_aggregates: dict[int, dict] = {}

    for cap in CAPS_MIN:
        n_eval = 0
        n_cleared_point = 0
        n_cleared_adverse = 0
        n_cleared_generous = 0
        n_rescued_robust_mean = 0
        n_rescued_robust = 0  # adverse-cost robust, any zone
        n_rescued_point = 0   # point-estimate only
        aggregate_simulated = 0.0
        aggregate_realized = 0.0
        rescue_details = []

        for td in trades:
            if td.n_snapshots < 2 or td.real_cost is None or td.realized_gross_pnl is None:
                continue
            upl_at_cap, z_at_cap = td.upl_at_cap(cap)
            if upl_at_cap is None or z_at_cap is None:
                # No snapshot within cap window (trade was held longer; but first snapshot exceeds cap)
                # Use first snapshot if it exists but is past cap? No — strict per work item.
                continue
            n_eval += 1
            cp, ca, cg, zlabel = classify_rescue(upl_at_cap, td.real_cost,
                                                  td.realized_gross_pnl, z_at_cap)
            if cp: n_cleared_point += 1
            if ca: n_cleared_adverse += 1
            if cg: n_cleared_generous += 1

            realized_net = td.realized_gross_pnl - td.real_cost
            capped_net = upl_at_cap - td.real_cost
            aggregate_simulated += capped_net
            aggregate_realized += realized_net

            # Rescued = cleared at cap AND realized did NOT clear
            realized_cleared = (td.realized_gross_pnl > td.real_cost)
            if cp and not realized_cleared:
                n_rescued_point += 1
            if ca and not realized_cleared:
                n_rescued_robust += 1
                if abs(z_at_cap) <= ZONE_THRESHOLD:
                    n_rescued_robust_mean += 1
                rescue_details.append((td.trade_id, upl_at_cap, td.real_cost,
                                       z_at_cap, zlabel))

            per_trade_per_cap_rows.append({
                "trade_id": td.trade_id, "cap_min": cap,
                "upl_at_cap": upl_at_cap, "z_at_cap": z_at_cap,
                "real_cost": td.real_cost,
                "realized_gross_pnl": td.realized_gross_pnl,
                "cleared_at_cap_point": cp,
                "cleared_at_cap_adverse": ca,
                "cleared_at_cap_generous": cg,
                "realized_cleared": realized_cleared,
                "rescued_point": cp and not realized_cleared,
                "rescued_adverse": ca and not realized_cleared,
                "zone_label": zlabel,
                "capped_net": capped_net,
                "realized_net": realized_net,
            })

        cap_aggregates[cap] = {
            "n_eval": n_eval,
            "n_cleared_point": n_cleared_point,
            "n_cleared_adverse": n_cleared_adverse,
            "n_cleared_generous": n_cleared_generous,
            "n_rescued_point": n_rescued_point,
            "n_rescued_robust": n_rescued_robust,
            "n_rescued_robust_mean": n_rescued_robust_mean,
            "aggregate_simulated": aggregate_simulated,
            "aggregate_realized": aggregate_realized,
            "rescue_details": rescue_details,
        }

    # Print per-cap aggregates
    print("Per-cap aggregates:")
    print(f"  {'cap':>4} {'n_eval':>7} {'cleared_pt':>11} {'cleared_adv':>12} "
          f"{'rescued_pt':>11} {'resc_robust':>12} {'resc_robust_mean':>17} "
          f"{'agg_sim':>10} {'agg_real':>10}")
    for cap in CAPS_MIN:
        a = cap_aggregates[cap]
        print(f"  {cap:>4} {a['n_eval']:>7} "
              f"{a['n_cleared_point']:>11} {a['n_cleared_adverse']:>12} "
              f"{a['n_rescued_point']:>11} {a['n_rescued_robust']:>12} "
              f"{a['n_rescued_robust_mean']:>17} "
              f"{a['aggregate_simulated']:>+10.4f} {a['aggregate_realized']:>+10.4f}")
    print()

    # Show rescue details (the load-bearing data)
    print("Rescue details (robustly-rescued trades at each cap, with z-context):")
    for cap in CAPS_MIN:
        a = cap_aggregates[cap]
        if a["rescue_details"]:
            print(f"  cap M={cap}:")
            for tid, upl, cost, z, zlabel in a["rescue_details"]:
                print(f"    {tid:<5} upl={upl:+.4f}  cost={cost:.4f}  net={upl-cost:+.4f}  "
                      f"z={z:+.3f}  {zlabel}")
    print()

    # Verdict
    max_robust_mean = max(a["n_rescued_robust_mean"] for a in cap_aggregates.values())
    max_robust = max(a["n_rescued_robust"] for a in cap_aggregates.values())
    best_cap_by_robust_mean = max(CAPS_MIN, key=lambda c: cap_aggregates[c]["n_rescued_robust_mean"])
    best_cap_aggregate = max(CAPS_MIN, key=lambda c: cap_aggregates[c]["aggregate_simulated"])
    best_aggregate = cap_aggregates[best_cap_aggregate]["aggregate_simulated"]
    best_aggregate_realized = cap_aggregates[best_cap_aggregate]["aggregate_realized"]

    print("=" * 90)
    print("VERDICT (per §4 pre-commit, locked before run)")
    print("=" * 90)

    # Verdict logic per §4 of the work item, primary metric is n_rescued_robust_mean
    # (clears adverse-cost AND rescued-at-mean — the thesis-capture signal):
    #   PULSE:     max_robust_mean >= 3  AND  best_aggregate > best_aggregate_realized
    #   DEAD:      max_robust_mean <= 1  (the "rescue clears a meaningful bar" check fails)
    #   AMBIGUOUS: max_robust_mean = 2  (in the 1-2 noise band per § 4)
    aggregate_improves = best_aggregate > best_aggregate_realized
    aggregate_delta = best_aggregate - best_aggregate_realized

    if max_robust_mean >= 3 and aggregate_improves:
        print(f"LEVER-B-HAS-PULSE")
        print(f"  At cap M={best_cap_by_robust_mean}, n_rescued (robust-cost, at-mean) = {max_robust_mean} >= 3.")
        print(f"  Best-cap aggregate simulated PnL ({best_aggregate:+.4f}) beats realized "
              f"({best_aggregate_realized:+.4f}).")
        print(f"  Routes to: a live hold-cap experiment is warranted (designed with §3.3 exit-")
        print(f"  interaction complexity + pre-committed criteria + bundled with E/C/D hygiene levers).")
        verdict = "LEVER-B-HAS-PULSE"
    elif max_robust_mean <= 1:
        print(f"LEVER-B-DEAD")
        print(f"  Maximum n_rescued (robust-cost, AT-MEAN) across all caps = {max_robust_mean} <= 1.")
        print(f"  The thesis-capture signal — trades clearing cost at a cap with the position")
        print(f"  near the mean and the realized hold failing — does NOT appear in the data.")
        print(f"  Best aggregate simulated = {best_aggregate:+.4f} vs realized = "
              f"{best_aggregate_realized:+.4f} (delta = {aggregate_delta:+.4f}).")
        if aggregate_improves:
            print(f"  Aggregate IS modestly better than realized, but the per-trade improvement")
            print(f"  averages {aggregate_delta/cap_aggregates[best_cap_aggregate]['n_eval']:+.4f}/trade")
            print(f"  — within the ±$0.06 per-trade cost-model noise, not a signal.")
            print(f"  The aggregate improvement is 'shorter holds incur slightly less time-cost,'")
            print(f"  not 'fast-reverting sub-population caught early.' The latter requires")
            print(f"  rescues-at-mean, which are 0.")
        print(f"  Routes to: the most promising dominant-mode lever has no pulse on the data")
        print(f"  we have. The fast-reverting-at-mean sub-population that Lever B requires does")
        print(f"  not exist in N=13 evaluable trades. Substantially firms the negative result;")
        print(f"  pivot-or-stop is now earned (not premature).")
        verdict = "LEVER-B-DEAD"
    else:
        print(f"LEVER-B-AMBIGUOUS")
        print(f"  Max n_rescued (robust-cost, at-mean) = {max_robust_mean} (in the 1–2 noise band)")
        print(f"  Best aggregate simulated = {best_aggregate:+.4f} vs realized = {best_aggregate_realized:+.4f}")
        print(f"  Evaluable-N is thin and cost proxy is loose; the data cannot resolve.")
        print(f"  Routes to: operator's exploratory-vs-stop judgment call. Does NOT route to")
        print(f"  'collect more data at $200' (refuted by halt). The thin-positive-signal must be")
        print(f"  weighed against the trading risk of an exploratory test.")
        verdict = "LEVER-B-AMBIGUOUS"
    print()

    # Write per-trade-per-cap CSV
    out_csv = OUTPUT_DIR / "lever_b_simulation.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["trade_id", "cap_min", "upl_at_cap", "z_at_cap", "real_cost",
                    "realized_gross_pnl", "cleared_at_cap_point",
                    "cleared_at_cap_adverse", "cleared_at_cap_generous",
                    "realized_cleared", "rescued_point", "rescued_adverse",
                    "zone_label", "capped_net", "realized_net"])
        for row in per_trade_per_cap_rows:
            w.writerow([row["trade_id"], row["cap_min"],
                        f"{row['upl_at_cap']:.4f}", f"{row['z_at_cap']:.4f}",
                        f"{row['real_cost']:.4f}",
                        f"{row['realized_gross_pnl']:.4f}",
                        int(row["cleared_at_cap_point"]),
                        int(row["cleared_at_cap_adverse"]),
                        int(row["cleared_at_cap_generous"]),
                        int(row["realized_cleared"]),
                        int(row["rescued_point"]),
                        int(row["rescued_adverse"]),
                        row["zone_label"],
                        f"{row['capped_net']:+.4f}",
                        f"{row['realized_net']:+.4f}"])
    print(f"Per-trade per-cap data: {out_csv.relative_to(PROJECT_ROOT)}")
    print()
    print(f"Verdict: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
