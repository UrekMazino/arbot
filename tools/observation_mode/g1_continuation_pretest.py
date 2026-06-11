#!/usr/bin/env python3
"""
Pivot G — G1 Daily Spread-Continuation Pre-Test.

Per work item docs/prompts/work_item_g_pivot_scoping.md (v1.0, verdicts,
grid, and taint mitigations LOCKED at commit d0f5529 BEFORE the extended
data pull or any simulation).

Thesis (from the program's unified finding, measured 3x): extension of a
discovered cointegrated spread is more often the onset of breakdown than
a reversion opportunity. G1 bets WITH the extension.

LOCKED spec (d0f5529):
- Data: ~800 daily bars (kline_cache_1d_ext/ — early half never touched
  by any prior analysis; in-sample-taint mitigation)
- Discovery-gated: 120-bar EG p <= 0.05, folds every 20 bars
- Entry: |z| CROSSES >= z_entry at day-t close (prev day below) ->
  enter at t+1 close WITH the extension. One position per pair.
  beta-aware $200 gross.
- Exits (first-of, evaluated daily, executed next close):
    trailing stop: z retraces >= trail sigma from peak favorable
    reversion stop: z back through (z_entry - 0.5) toward mean
    max hold: 20 days
    (NO coint-watch — breakdown is the thesis)
- Grid (LOCKED): z_entry {1.5, 2.0, 2.5} x trail {0.75, 1.25} = 6 cells
- Costs: BASE $0.14 + $0.104*(hold/10); STRESS $0.28 + $0.470*(hold/10)
- Qualify: net>0 at BOTH costs, n>=30, >=10 pairs, max pair share <=40%
- Ridge: >=2 adjacent qualifying cells
- PLUS per-half sign-stability: ridge cells' pooled net at BASE must be
  positive in EACH half (early/late by global midpoint) taken alone

LOCKED verdicts: G1-VIABLE / G1-DEAD (incl. HALF-SPLIT-as-taint route) /
G1-AMBIGUOUS (STRESS-DEATH / UNDERPOWERED / CONCENTRATION / HALF-SPLIT /
GRAY). Borderline resolves DOWN.

Usage:
    python tools/observation_mode/g1_continuation_pretest.py [--fetch-only]
"""

from __future__ import annotations

import csv
import sys
import time
import warnings
from collections import defaultdict
from pathlib import Path

import certifi
import numpy as np

try:
    import requests
    from statsmodels.tsa.stattools import coint
except ImportError as e:
    print(f"ERR: missing dependency: {e}", file=sys.stderr)
    sys.exit(1)

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).parent / "output"
CACHE_EXT = OUTPUT_DIR / "kline_cache_1d_ext"
CACHE_EXT.mkdir(parents=True, exist_ok=True)

OKX_BASE = "https://www.okx.com"
HISTORY_CANDLES = "/api/v5/market/history-candles"

# ---- locked parameters (d0f5529) ----
MAX_BARS = 800
MIN_INST_BARS = 140
DISCOVERY_WINDOW = 120
DISCOVERY_P = 0.05
FOLD_STEP = 20
Z_ENTRIES = [1.5, 2.0, 2.5]
TRAILS = [0.75, 1.25]
REV_STOP_BUFFER = 0.5
MAX_HOLD = 20
GROSS = 200.0
BASE_EE, BASE_F10 = 0.14, 0.104
STRESS_EE, STRESS_F10 = 0.28, 0.470
MIN_TRADES, MIN_PAIRS, MAX_SHARE = 30, 10, 0.40


def fetch_1d_ext(inst: str) -> int:
    path = CACHE_EXT / f"{inst}.csv"
    if path.exists():
        with path.open(encoding="utf-8") as f:
            return sum(1 for _ in f) - 1
    rows: list[tuple[int, float]] = []
    after = ""
    while len(rows) < MAX_BARS:
        params = {"instId": inst, "bar": "1D", "limit": "100"}
        if after:
            params["after"] = after
        try:
            r = requests.get(OKX_BASE + HISTORY_CANDLES, params=params, timeout=20,
                             verify=certifi.where())
            data = r.json()
        except Exception as e:
            print(f"    {inst}: fetch error {type(e).__name__}", file=sys.stderr)
            break
        if data.get("code") != "0" or not data.get("data"):
            break
        page = data["data"]
        for row in page:
            if row[8] == "1":
                rows.append((int(row[0]), float(row[4])))
        after = page[-1][0]
        if len(page) < 100:
            break
        time.sleep(0.12)
    rows.sort()
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ts_ms", "close"])
        for ts, c in rows:
            w.writerow([ts, c])
    return len(rows)


def load_ext(inst: str) -> dict[int, float]:
    path = CACHE_EXT / f"{inst}.csv"
    if not path.exists():
        return {}
    return {int(r["ts_ms"]): float(r["close"])
            for r in csv.DictReader(path.open(encoding="utf-8"))}


def ols_beta_c(y: np.ndarray, x: np.ndarray) -> tuple[float, float]:
    A = np.column_stack([x, np.ones_like(x)])
    sol, *_ = np.linalg.lstsq(A, y, rcond=None)
    return float(sol[0]), float(sol[1])


def cost(hold: int, ee: float, f10: float) -> float:
    return ee + f10 * (hold / 10.0)


def main() -> int:
    # instrument list = the 46 from B1 (same source as prior tools)
    import glob as _glob
    insts = sorted({leg for f in _glob.glob(str(OUTPUT_DIR / "run_*__samples.csv"))
                    for r in csv.DictReader(open(f, encoding="utf-8"))
                    for leg in r.get("pair", "").split("/") if leg.endswith("-USDT-SWAP")})
    print(f"Universe: {len(insts)} instruments")

    print("Fetching extended 1D history (800 bars, cache-aware)...")
    counts = {i: fetch_1d_ext(i) for i in insts}
    qual = [i for i in insts if counts[i] >= MIN_INST_BARS]
    print(f"Qualified (>= {MIN_INST_BARS} bars): {len(qual)}; "
          f"dropped: {[(i, c) for i, c in counts.items() if c < MIN_INST_BARS]}")
    if "--fetch-only" in sys.argv:
        return 0

    series = {i: load_ext(i) for i in qual}
    all_ts = sorted({t for s in series.values() for t in s})
    mid_ts = all_ts[len(all_ts) // 2]
    print(f"Global span: {len(all_ts)} days; half boundary index {len(all_ts)//2}")

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

            folds = []
            for E in range(DISCOVERY_WINDOW, n, FOLD_STEP):
                y, x = la[E - DISCOVERY_WINDOW:E], lb[E - DISCOVERY_WINDOW:E]
                try:
                    _, pval, _ = coint(y, x)
                except Exception:
                    continue
                if pval > DISCOVERY_P:
                    continue
                beta, c = ols_beta_c(y, x)
                sigma = float(np.std(y - beta * x - c))
                if sigma <= 0:
                    continue
                folds.append((E, beta, c, sigma))

            for ze in Z_ENTRIES:
                for tr in TRAILS:
                    busy_until = -1
                    for E, beta, c, sigma in folds:
                        z_arr = (la - beta * lb - c) / sigma  # full-series z under fold params
                        for t in range(E, min(E + FOLD_STEP, n - 1)):
                            if t <= busy_until:
                                continue
                            z_t, z_prev = z_arr[t], z_arr[t - 1]
                            crossed = abs(z_t) >= ze and abs(z_prev) < ze
                            if not crossed:
                                continue
                            e_idx = t + 1
                            sign = 1.0 if z_t > 0 else -1.0   # WITH the extension
                            n1 = GROSS / (1 + abs(beta)) if beta != 0 else GROSS / 2
                            peak = abs(z_t)
                            exit_idx, reason = None, ""
                            for h in range(e_idx + 1, n):
                                z_h = z_arr[h] * sign          # favorable = positive
                                peak = max(peak, z_h)
                                if z_h <= peak - tr:
                                    exit_idx, reason = min(h + 1, n - 1), "trail"
                                elif z_h < (ze - REV_STOP_BUFFER):
                                    exit_idx, reason = min(h + 1, n - 1), "rev_stop"
                                elif h - e_idx >= MAX_HOLD:
                                    exit_idx, reason = min(h + 1, n - 1), "max_hold"
                                if exit_idx is not None:
                                    break
                            if exit_idx is None:
                                exit_idx, reason = n - 1, "data_end"
                            d_spread = (la[exit_idx] - beta * lb[exit_idx]) - (la[e_idx] - beta * lb[e_idx])
                            pnl = sign * n1 * d_spread
                            hold = exit_idx - e_idx
                            trades[(ze, tr)].append({
                                "pair": f"{a}/{b}", "entry_ts": common[e_idx],
                                "half": "early" if common[e_idx] < mid_ts else "late",
                                "z_sig": round(z_arr[t], 3), "hold": hold, "reason": reason,
                                "gross": round(pnl, 4),
                                "net_base": round(pnl - cost(hold, BASE_EE, BASE_F10), 4),
                                "net_stress": round(pnl - cost(hold, STRESS_EE, STRESS_F10), 4),
                            })
                            busy_until = exit_idx

    print(f"Pairs simulated: {n_pairs_run}\n")

    # ---- per-cell aggregation ----
    print(f"{'cell':<16} {'n':>5} {'pairs':>6} {'win%':>6} {'hold':>5} "
          f"{'net_BASE':>10} {'net_STRESS':>11} {'early':>9} {'late':>9} {'maxsh':>6} {'qual':>5}")
    stats: dict[tuple[float, float], dict] = {}
    for ze in Z_ENTRIES:
        for tr in TRAILS:
            T = trades[(ze, tr)]
            if not T:
                stats[(ze, tr)] = {"n": 0, "q": False}
                continue
            nb = sum(t["net_base"] for t in T)
            ns = sum(t["net_stress"] for t in T)
            eb = sum(t["net_base"] for t in T if t["half"] == "early")
            lb_ = sum(t["net_base"] for t in T if t["half"] == "late")
            pairs_c = {t["pair"] for t in T}
            wins = sum(1 for t in T if t["net_base"] > 0)
            by_pair = defaultdict(float)
            for t in T:
                by_pair[t["pair"]] += t["net_base"]
            share = (max(by_pair.values()) / nb) if nb > 0 else float("inf")
            q = (nb > 0 and ns > 0 and len(T) >= MIN_TRADES
                 and len(pairs_c) >= MIN_PAIRS and share <= MAX_SHARE)
            stats[(ze, tr)] = {"n": len(T), "pairs": len(pairs_c), "net_base": nb,
                               "net_stress": ns, "early": eb, "late": lb_,
                               "share": share, "q": q}
            print(f"ze={ze} tr={tr:<7} {len(T):>5} {len(pairs_c):>6} {wins/len(T):>6.1%} "
                  f"{np.mean([t['hold'] for t in T]):>5.1f} {nb:>+10.2f} {ns:>+11.2f} "
                  f"{eb:>+9.2f} {lb_:>+9.2f} {share:>6.2f} {'YES' if q else 'no':>5}")

    pooled = [t for T in trades.values() for t in T]
    reasons = defaultdict(int)
    for t in pooled:
        reasons[t["reason"]] += 1
    print(f"\nexit reasons (pooled): {dict(reasons)}")

    # ---- ridge + halves ----
    def adjacent(c1, c2):
        (a1, t1), (a2, t2) = c1, c2
        if t1 == t2:
            return abs(Z_ENTRIES.index(a1) - Z_ENTRIES.index(a2)) == 1
        return a1 == a2

    qc = [c for c, s in stats.items() if s.get("q")]
    ridge_pairs = [(c1, c2) for i, c1 in enumerate(qc) for c2 in qc[i+1:] if adjacent(c1, c2)]
    ridge = bool(ridge_pairs)
    halves_ok = False
    if ridge:
        ridge_cells = sorted({c for pr in ridge_pairs for c in pr})
        e_sum = sum(stats[c]["early"] for c in ridge_cells)
        l_sum = sum(stats[c]["late"] for c in ridge_cells)
        halves_ok = e_sum > 0 and l_sum > 0
        print(f"\nridge cells: {ridge_cells}  early-half net ${e_sum:+.2f}  late-half net ${l_sum:+.2f}")

    # persist
    out_csv = OUTPUT_DIR / "g1_continuation_trades.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ze", "trail", "pair", "entry_ts", "half", "z_sig", "hold",
                    "reason", "gross", "net_base", "net_stress"])
        for (ze, tr), T in trades.items():
            for t in T:
                w.writerow([ze, tr, t["pair"], t["entry_ts"], t["half"], t["z_sig"],
                            t["hold"], t["reason"], t["gross"], t["net_base"], t["net_stress"]])
    print(f"per-trade data: {out_csv.relative_to(PROJECT_ROOT)}")

    # ---- verdict (locked) ----
    print("\n" + "=" * 100)
    print("VERDICT (per work item v1.0, locked at d0f5529)")
    print("=" * 100)
    any_base_pos = any(s.get("net_base", 0) > 0 and s.get("n", 0) > 0 for s in stats.values())
    underpowered = all(s.get("n", 0) < MIN_TRADES or s.get("pairs", 0) < MIN_PAIRS
                       for s in stats.values())

    def q_base(c):
        s = stats[c]
        return (s.get("n", 0) >= MIN_TRADES and s.get("pairs", 0) >= MIN_PAIRS
                and s.get("net_base", 0) > 0 and s.get("share", 9) <= MAX_SHARE)
    qb = [c for c in stats if q_base(c)]
    ridge_b = any(adjacent(c1, c2) for i, c1 in enumerate(qb) for c2 in qb[i+1:])

    if ridge and halves_ok:
        print("G1-VIABLE (pending the §5 skeptical audit before acceptance)")
        verdict = "G1-VIABLE-PENDING-AUDIT"
    elif ridge and not halves_ok:
        print("G1-AMBIGUOUS (sub-cause: HALF-SPLIT)")
        print("  Pooled ridge passes but the halves disagree in sign — taint-suspect.")
        print("  Routes toward stop-or-longer-paper, never toward grid tuning.")
        verdict = "AMBIGUOUS-HALF-SPLIT"
    elif underpowered:
        print("G1-AMBIGUOUS (sub-cause: UNDERPOWERED)")
        print("  Continuation signals too rare to test at the locked guards.")
        verdict = "AMBIGUOUS-UNDERPOWERED"
    elif ridge_b and not ridge:
        print("G1-AMBIGUOUS (sub-cause: STRESS-DEATH)")
        print("  BASE-qualifying ridge dies at STRESS costs.")
        verdict = "AMBIGUOUS-STRESS-DEATH"
    elif not any_base_pos:
        print("G1-DEAD")
        print("  No cell net-positive at BASE. The continuation thesis does not convert")
        print("  to capture with this rule family. The last program-evidence-backed")
        print("  direction closes. Per the locked clause: stop becomes the strong default;")
        print("  G3 remains as an explicitly evidence-free fresh bet.")
        verdict = "G1-DEAD"
    else:
        if len(qb) == 1:
            print("G1-DEAD (spike-only positivity)")
            print(f"  Single qualifying cell {qb} — pre-named noise.")
            verdict = "G1-DEAD-SPIKE-ONLY"
        else:
            conc = [c for c in stats if stats[c].get("net_base", 0) > 0
                    and stats[c].get("share", 0) > MAX_SHARE]
            if conc and not qb:
                print("G1-AMBIGUOUS (sub-cause: CONCENTRATION)")
                verdict = "AMBIGUOUS-CONCENTRATION"
            else:
                print("G1-AMBIGUOUS (sub-cause: GRAY)")
                print("  Mixed cells, no ridge. Borderline resolves DOWN.")
                verdict = "AMBIGUOUS-GRAY"

    print(f"\nVerdict: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
