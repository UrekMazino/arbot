#!/usr/bin/env python3
"""
D3 Design Phase B — Capture-Realism Walk-Forward.

Per work item docs/prompts/work_item_d3_design_phase.md (v1.0, verdicts
and grid LOCKED at commit d9efdcc, BEFORE this file existed).

Question: does a locked entry/exit rule family, walked forward on the
native daily basis with measured costs, convert the pre-test's survival
(82.4% @+10d) and edge (median $24.17) into positive net capture?

LOCKED spec (d9efdcc):
- Discovery: 120-bar window, EG p <= 0.05, refreshed every 20 bars
  (fold boundaries identical to the pre-test)
- Signal: z = frozen-beta spread residual / discovery-window sigma_s
- Entry: |z| >= z_entry at day-t close -> open at day t+1 close
  (one-day lag; no lookahead). One open position per pair; re-entry
  allowed after exit. beta-aware sizing per H1 at $200 gross.
- Exit (first-of, evaluated daily, executed at next close):
    |z| <= z_exit            (reversion target)
    |z| >= 4.0               (divergence stop, fixed)
    frozen-beta ADF p > 0.20 (daily coint-watch, fixed)
    hold >= 20 days          (max hold, fixed)
- Grid (LOCKED, 6 cells): z_entry {1.5, 2.0, 2.5} x z_exit {0.0, 0.5}
- Costs per trade (Phase A measured):
    BASE   = $0.14 + $0.104 x (hold_days/10)
    STRESS = $0.28 + $0.470 x (hold_days/10)
- Cell qualifies: net > 0 at BOTH cost levels AND n >= 30 trades AND
  >= 10 distinct pairs AND no pair > 40% of cell net
- Ridge: >= 2 adjacent qualifying cells (z_entry neighbors at same
  z_exit, or the two z_exit at same z_entry)

LOCKED verdicts: DESIGN-VIABLE (ridge) / DESIGN-DEAD (no cell positive
at BASE, or spike-only, or concentration-only) / DESIGN-AMBIGUOUS with
named sub-cause (RIDGE-DIES-UNDER-STRESS / UNDERPOWERED /
CONCENTRATION / GRAY). Borderline resolves DOWN.

Read-only; cached public data only; no bot contact.

Usage:
    python tools/observation_mode/d3_capture_realism.py
"""

from __future__ import annotations

import csv
import sys
import warnings
from collections import defaultdict
from pathlib import Path

import numpy as np

try:
    from statsmodels.tsa.stattools import adfuller, coint
except ImportError:
    print("ERR: statsmodels not installed", file=sys.stderr)
    sys.exit(1)

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).parent / "output"
CACHE_1D = OUTPUT_DIR / "kline_cache_1d"

# ---- locked parameters (d9efdcc) ----
DISCOVERY_WINDOW = 120
DISCOVERY_P = 0.05
FOLD_STEP = 20
Z_ENTRIES = [1.5, 2.0, 2.5]
Z_EXITS = [0.0, 0.5]
Z_STOP = 4.0
COINT_WATCH_P = 0.20
MAX_HOLD = 20
GROSS = 200.0
BASE_EE, BASE_FUND10 = 0.14, 0.104     # entry/exit + funding per 10d (Phase A p50)
STRESS_EE, STRESS_FUND10 = 0.28, 0.470  # 2x slippage + funding p90
MIN_TRADES = 30
MIN_PAIRS = 10
MAX_PAIR_SHARE = 0.40
K_CONCURRENT = 5
MIN_INST_BARS = 140


def load_1d(inst: str) -> dict[int, float]:
    path = CACHE_1D / f"{inst}.csv"
    if not path.exists():
        return {}
    return {int(r["ts_ms"]): float(r["close"])
            for r in csv.DictReader(path.open(encoding="utf-8"))}


def ols_beta_c(y: np.ndarray, x: np.ndarray) -> tuple[float, float]:
    A = np.column_stack([x, np.ones_like(x)])
    sol, *_ = np.linalg.lstsq(A, y, rcond=None)
    return float(sol[0]), float(sol[1])


def cost(hold_days: int, ee: float, fund10: float) -> float:
    return ee + fund10 * (hold_days / 10.0)


def main() -> int:
    insts = sorted(p.stem for p in CACHE_1D.glob("*.csv"))
    series = {i: load_1d(i) for i in insts}
    qual = [i for i in insts if len(series[i]) >= MIN_INST_BARS]
    print(f"Instruments: {len(qual)} qualified")

    # ---- simulate per cell ----
    # trades[(ze, zx)] = list of trade dicts
    trades: dict[tuple[float, float], list[dict]] = defaultdict(list)

    n_pairs_run = 0
    for ai in range(len(qual)):
        for bi in range(ai + 1, len(qual)):
            a, b = qual[ai], qual[bi]
            common = sorted(set(series[a]) & set(series[b]))
            n = len(common)
            if n < DISCOVERY_WINDOW + FOLD_STEP:
                continue
            n_pairs_run += 1
            la = np.log(np.array([series[a][t] for t in common]))
            lb = np.log(np.array([series[b][t] for t in common]))

            # Discovery state per fold (computed once, shared across cells)
            folds = []  # (E, beta, c, sigma_s) for discovered folds
            for E in range(DISCOVERY_WINDOW, n, FOLD_STEP):
                y, x = la[E - DISCOVERY_WINDOW:E], lb[E - DISCOVERY_WINDOW:E]
                try:
                    _, pval, _ = coint(y, x)
                except Exception:
                    continue
                if pval > DISCOVERY_P:
                    continue
                beta, c = ols_beta_c(y, x)
                resid = y - beta * x - c
                sigma = float(np.std(resid))
                if sigma <= 0:
                    continue
                folds.append((E, beta, c, sigma))
            if not folds:
                continue
            fold_state = {E: (beta, c, sigma) for E, beta, c, sigma in folds}

            for ze in Z_ENTRIES:
                for zx in Z_EXITS:
                    open_pos = None  # one position per pair
                    for E, beta, c, sigma in folds:
                        # live window for this fold's signal: [E, E+FOLD_STEP)
                        for t in range(E, min(E + FOLD_STEP, n - 1)):
                            if open_pos is not None:
                                continue  # exits handled in inner loop below at open time
                            z_t = (la[t] - beta * lb[t] - c) / sigma
                            if abs(z_t) < ze:
                                continue
                            # ---- entry at t+1 close ----
                            e_idx = t + 1
                            direction = -1 if z_t > 0 else 1  # short spread if rich
                            n1 = GROSS / (1 + abs(beta)) if beta != 0 else GROSS / 2
                            # hold loop: evaluate exits daily from e_idx forward
                            exit_idx = None
                            exit_reason = ""
                            for h in range(e_idx + 1, n):
                                z_h = (la[h] - beta * lb[h] - c) / sigma
                                days_held = h - e_idx
                                if abs(z_h) <= zx:
                                    exit_idx, exit_reason = min(h + 1, n - 1), "reversion"
                                elif abs(z_h) >= Z_STOP:
                                    exit_idx, exit_reason = min(h + 1, n - 1), "stop"
                                elif days_held >= MAX_HOLD:
                                    exit_idx, exit_reason = min(h + 1, n - 1), "max_hold"
                                else:
                                    # daily coint-watch (frozen-beta ADF on rolling window)
                                    if h >= DISCOVERY_WINDOW:
                                        spread_w = la[h - DISCOVERY_WINDOW:h] - beta * lb[h - DISCOVERY_WINDOW:h] - c
                                        try:
                                            p_w = adfuller(spread_w, regression="c")[1]
                                        except Exception:
                                            p_w = 0.0
                                        if p_w > COINT_WATCH_P:
                                            exit_idx, exit_reason = min(h + 1, n - 1), "coint_watch"
                                if exit_idx is not None:
                                    break
                            if exit_idx is None:
                                # data ran out mid-hold: close at last bar (flagged)
                                exit_idx, exit_reason = n - 1, "data_end"
                            d_spread = (la[exit_idx] - beta * lb[exit_idx]) - (la[e_idx] - beta * lb[e_idx])
                            pnl = direction * n1 * d_spread
                            hold = exit_idx - e_idx
                            trades[(ze, zx)].append({
                                "pair": f"{a}/{b}", "entry_idx": e_idx,
                                "entry_ts": common[e_idx], "exit_ts": common[exit_idx],
                                "direction": direction, "beta": round(beta, 5),
                                "z_at_signal": round(z_t, 3), "hold_days": hold,
                                "exit_reason": exit_reason, "gross_pnl": round(pnl, 4),
                                "net_base": round(pnl - cost(hold, BASE_EE, BASE_FUND10), 4),
                                "net_stress": round(pnl - cost(hold, STRESS_EE, STRESS_FUND10), 4),
                            })
                            open_pos = (e_idx, exit_idx)
                            # mark busy until exit (handled below)
                        # release positions that exited before next fold window
                        if open_pos is not None and open_pos[1] < min(E + FOLD_STEP, n - 1):
                            open_pos = None
                    # end folds

    print(f"Pairs simulated: {n_pairs_run}")

    # ---- per-cell aggregation + qualification ----
    print(f"\n{'cell':<18} {'n':>5} {'pairs':>6} {'win%':>6} {'avg_hold':>8} "
          f"{'net_BASE':>10} {'net_STRESS':>11} {'maxshare':>9} {'qualifies':>10}")
    cell_q: dict[tuple[float, float], bool] = {}
    cell_stats: dict[tuple[float, float], dict] = {}
    for ze in Z_ENTRIES:
        for zx in Z_EXITS:
            T = trades[(ze, zx)]
            n_t = len(T)
            if n_t == 0:
                cell_q[(ze, zx)] = False
                cell_stats[(ze, zx)] = {"n": 0}
                print(f"ze={ze} zx={zx:<10} {0:>5}")
                continue
            net_b = sum(t["net_base"] for t in T)
            net_s = sum(t["net_stress"] for t in T)
            pairs_c = {t["pair"] for t in T}
            wins = sum(1 for t in T if t["net_base"] > 0)
            avg_hold = np.mean([t["hold_days"] for t in T])
            # concentration: max single-pair share of positive cell net
            by_pair = defaultdict(float)
            for t in T:
                by_pair[t["pair"]] += t["net_base"]
            max_share = (max(by_pair.values()) / net_b) if net_b > 0 else float("inf")
            q = (net_b > 0 and net_s > 0 and n_t >= MIN_TRADES
                 and len(pairs_c) >= MIN_PAIRS and max_share <= MAX_PAIR_SHARE)
            cell_q[(ze, zx)] = q
            cell_stats[(ze, zx)] = {"n": n_t, "pairs": len(pairs_c), "win": wins / n_t,
                                    "avg_hold": avg_hold, "net_base": net_b,
                                    "net_stress": net_s, "max_share": max_share}
            print(f"ze={ze} zx={zx:<10} {n_t:>5} {len(pairs_c):>6} {wins/n_t:>6.1%} "
                  f"{avg_hold:>8.1f} {net_b:>+10.2f} {net_s:>+11.2f} "
                  f"{max_share:>9.2f} {'YES' if q else 'no':>10}")

    # exit-reason breakdown (pooled)
    all_trades = [t for T in trades.values() for t in T]
    reasons = defaultdict(int)
    for t in all_trades:
        reasons[t["exit_reason"]] += 1
    print(f"\nexit reasons (pooled all cells): {dict(reasons)}")

    # ---- ridge detection ----
    def adjacent(c1, c2):
        (a1, x1), (a2, x2) = c1, c2
        if x1 == x2:
            i, j = Z_ENTRIES.index(a1), Z_ENTRIES.index(a2)
            return abs(i - j) == 1
        if a1 == a2:
            return x1 != x2
        return False

    qcells = [c for c, q in cell_q.items() if q]
    ridge = any(adjacent(c1, c2) for i, c1 in enumerate(qcells) for c2 in qcells[i+1:])

    # base-only qualification (for RIDGE-DIES-UNDER-STRESS)
    def q_base_only(c):
        s = cell_stats[c]
        return (s.get("n", 0) >= MIN_TRADES and s.get("pairs", 0) >= MIN_PAIRS
                and s.get("net_base", 0) > 0 and s.get("max_share", 9) <= MAX_PAIR_SHARE)
    qcells_base = [c for c in cell_q if q_base_only(c)]
    ridge_base = any(adjacent(c1, c2) for i, c1 in enumerate(qcells_base) for c2 in qcells_base[i+1:])

    # persist per-trade data
    out_csv = OUTPUT_DIR / "d3_capture_trades.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        keys = ["cell_ze", "cell_zx", "pair", "entry_ts", "exit_ts", "direction", "beta",
                "z_at_signal", "hold_days", "exit_reason", "gross_pnl", "net_base", "net_stress"]
        w = csv.writer(f)
        w.writerow(keys)
        for (ze, zx), T in trades.items():
            for t in T:
                w.writerow([ze, zx, t["pair"], t["entry_ts"], t["exit_ts"], t["direction"],
                            t["beta"], t["z_at_signal"], t["hold_days"], t["exit_reason"],
                            t["gross_pnl"], t["net_base"], t["net_stress"]])
    print(f"per-trade data: {out_csv.relative_to(PROJECT_ROOT)}")

    # ---- verdict (locked rules) ----
    print("\n" + "=" * 95)
    print("VERDICT (per work item v1.0, locked at d9efdcc)")
    print("=" * 95)
    any_base_positive = any(cell_stats[c].get("net_base", 0) > 0 and cell_stats[c].get("n", 0) > 0
                            for c in cell_q)
    underpowered = all(cell_stats[c].get("n", 0) < MIN_TRADES or cell_stats[c].get("pairs", 0) < MIN_PAIRS
                       for c in cell_q)

    if ridge:
        print("DESIGN-VIABLE")
        print(f"  Qualifying cells: {sorted(qcells)}")
        print("  Ridge present; all guards met at BOTH cost levels.")
        print("  Routes to: experiment spec — PAPER-FIRST pre-committed (>=8 weeks or")
        print("  >=10 paper trades, whichever later). Caveats: backtest != forward;")
        print("  daily closes are fill proxies.")
        verdict = "DESIGN-VIABLE"
    elif underpowered:
        print("DESIGN-AMBIGUOUS (sub-cause: UNDERPOWERED)")
        print("  No cell reaches n>=30 trades with >=10 pairs. The signal fires too")
        print("  rarely — itself informative about sample-accumulation timeline.")
        verdict = "AMBIGUOUS-UNDERPOWERED"
    elif ridge_base and not ridge:
        print("DESIGN-AMBIGUOUS (sub-cause: RIDGE-DIES-UNDER-STRESS)")
        print(f"  Base-qualifying ridge {sorted(qcells_base)} fails at STRESS costs.")
        print("  Cost-tail question routes to operator.")
        verdict = "AMBIGUOUS-RIDGE-DIES-UNDER-STRESS"
    elif not any_base_positive:
        print("DESIGN-DEAD")
        print("  No cell is net-positive even at BASE costs. The premise survives but")
        print("  capture does not reach it at $200 gross with this rule family.")
        print("  Routes to: D3 closes at design level; G (class pivot) or stop.")
        verdict = "DESIGN-DEAD"
    else:
        # some positivity but no ridge: spike or concentration or gray
        spikes = [c for c in qcells_base]
        conc = [c for c in cell_q if cell_stats[c].get("net_base", 0) > 0
                and cell_stats[c].get("max_share", 0) > MAX_PAIR_SHARE]
        if spikes and len(spikes) == 1:
            print("DESIGN-DEAD (spike-only positivity)")
            print(f"  Single qualifying cell {spikes} with no adjacent partner — pre-named noise.")
            verdict = "DESIGN-DEAD-SPIKE-ONLY"
        elif conc and not spikes:
            print("DESIGN-AMBIGUOUS (sub-cause: CONCENTRATION)")
            print(f"  Positivity exists but rests on concentrated pairs in {conc}.")
            verdict = "AMBIGUOUS-CONCENTRATION"
        else:
            print("DESIGN-AMBIGUOUS (sub-cause: GRAY)")
            print("  Mixed cells, no ridge. Borderline resolves DOWN per the lock.")
            verdict = "AMBIGUOUS-GRAY"

    print(f"\nVerdict: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
