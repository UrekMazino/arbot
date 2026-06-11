#!/usr/bin/env python3
"""
D3 Daily-Bar Cointegration Pre-Test.

Per work item docs/prompts/work_item_d3_daily_coint_pretest.md (v1.0,
verdicts LOCKED at commit 77b3dee BEFORE any 1D bar was pulled).

Question: do daily-bar cointegrating relationships on the exp_beta
instrument universe survive multi-day hold horizons (frozen-beta) at a
strategy-supporting rate, with 2-sigma reversion edges clearing the
multi-day cost stack?

Design (locked):
- Universe: 46 instruments from B1 per-run samples; all C(46,2) pairs
- Discovery: 120-bar window, Engle-Granger coint p <= 0.05
- GATED: frozen-beta survival at +5/+10/+20 days — plain ADF p <= 0.20
  on the spread held at discovery beta/intercept (a held position's
  hedge is frozen; this is the daily-scale mean-shift exposure)
- Walk-forward folds every 20 days; pooled (pair, fold) observations
- N-guards: >=30 observations at +10d AND >=8 distinct pairs
- Part B: median 2*sigma_s*$200 edge of survivors >= $2.22
  (3x the $0.74 middle-funding 10-day stack)

Verdicts (locked): SUPPORTED (>=70% @+10d AND >=50% @+20d AND guards
AND edge) / DEAD (<=40% @+10d with guards) / AMBIGUOUS with named
sub-cause (GRAY-ZONE / UNDERPOWERED / EDGE-FAILS-COSTS /
UNIVERSE-COVERAGE). Borderline resolves DOWN.

Read-only: public history-candles endpoint, no auth, no bot contact.

Usage:
    python tools/observation_mode/d3_daily_coint_pretest.py
"""

from __future__ import annotations

import csv
import glob
import math
import sys
import time
import warnings
from pathlib import Path

import certifi
import numpy as np

try:
    import requests
except ImportError:
    print("ERR: requests not installed", file=sys.stderr)
    sys.exit(1)

try:
    from statsmodels.tsa.stattools import adfuller, coint
except ImportError:
    print("ERR: statsmodels not installed", file=sys.stderr)
    sys.exit(1)

warnings.filterwarnings("ignore")  # statsmodels emits convergence chatter on short windows

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).parent / "output"
CACHE_1D = OUTPUT_DIR / "kline_cache_1d"
CACHE_1D.mkdir(parents=True, exist_ok=True)

OKX_BASE = "https://www.okx.com"
HISTORY_CANDLES = "/api/v5/market/history-candles"

# ---- locked parameters (work item v1.0, commit 77b3dee) ----
MAX_BARS = 400
MIN_INST_BARS = 140
DISCOVERY_WINDOW = 120
DISCOVERY_P = 0.05
SURVIVAL_P = 0.20
HORIZONS = [5, 10, 20]
FOLD_STEP = 20
GATE_HORIZON = 10
N_GUARD_OBS = 30
N_GUARD_PAIRS = 8
SUPPORTED_10D = 0.70
SUPPORTED_20D = 0.50
DEAD_10D = 0.40
GROSS = 200.0
COST_STACKS = {"low(0.005%/8h)": 0.44, "mid(0.01%/8h)": 0.74, "high(0.03%/8h)": 1.94}
EDGE_GATE = 3 * 0.74  # $2.22 vs mid stack
MIN_UNIVERSE = 10


def universe_from_b1() -> list[str]:
    insts: set[str] = set()
    for f in glob.glob(str(OUTPUT_DIR / "run_*__samples.csv")):
        with open(f, encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                p = row.get("pair", "")
                if "/" in p:
                    a, b = p.split("/", 1)
                    insts.add(a.strip())
                    insts.add(b.strip())
    return sorted(i for i in insts if i.endswith("-USDT-SWAP"))


def fetch_1d(inst: str) -> int:
    """Fetch up to MAX_BARS confirmed 1D bars; cache. Returns bar count."""
    path = CACHE_1D / f"{inst}.csv"
    if path.exists():
        with path.open(encoding="utf-8") as f:
            n = sum(1 for _ in f) - 1
        if n >= MIN_INST_BARS or n >= 0:  # cache exists; trust it (full refetch = delete cache)
            return n
    rows: list[tuple[int, float]] = []
    after = ""  # newest first
    while len(rows) < MAX_BARS:
        params = {"instId": inst, "bar": "1D", "limit": "100"}
        if after:
            params["after"] = after
        try:
            r = requests.get(OKX_BASE + HISTORY_CANDLES, params=params, timeout=20,
                             verify=certifi.where())
            data = r.json()
        except Exception as e:
            print(f"    {inst}: fetch error {type(e).__name__}: {e}", file=sys.stderr)
            break
        if data.get("code") != "0" or not data.get("data"):
            break
        page = data["data"]
        for row in page:
            ts, close, confirm = int(row[0]), float(row[4]), row[8]
            if confirm == "1":
                rows.append((ts, close))
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


def load_1d(inst: str) -> dict[int, float]:
    path = CACHE_1D / f"{inst}.csv"
    out: dict[int, float] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[int(row["ts_ms"])] = float(row["close"])
    return out


def ols_beta_c(y: np.ndarray, x: np.ndarray) -> tuple[float, float]:
    """y = beta*x + c."""
    A = np.column_stack([x, np.ones_like(x)])
    sol, *_ = np.linalg.lstsq(A, y, rcond=None)
    return float(sol[0]), float(sol[1])


def main() -> int:
    insts = universe_from_b1()
    print(f"Universe: {len(insts)} instruments from B1 monitored pairs")

    # ---- fetch ----
    print("Fetching 1D bars (cache-aware)...")
    bar_counts: dict[str, int] = {}
    for inst in insts:
        n = fetch_1d(inst)
        bar_counts[inst] = n
    qualified = [i for i in insts if bar_counts[i] >= MIN_INST_BARS]
    dropped = [(i, bar_counts[i]) for i in insts if bar_counts[i] < MIN_INST_BARS]
    print(f"Qualified instruments (>= {MIN_INST_BARS} bars): {len(qualified)}")
    if dropped:
        print(f"Dropped (insufficient 1D history): {dropped}")

    if len(qualified) < MIN_UNIVERSE:
        print("\nVERDICT: D3-PREMISE-AMBIGUOUS (sub-cause: UNIVERSE-COVERAGE)")
        print(f"  Only {len(qualified)} instruments qualify (< {MIN_UNIVERSE}).")
        return 0

    series = {i: load_1d(i) for i in qualified}

    # ---- walk-forward ----
    pair_fold_rows: list[dict] = []
    n_pairs_tested = 0
    for ai in range(len(qualified)):
        for bi in range(ai + 1, len(qualified)):
            a, b = qualified[ai], qualified[bi]
            common = sorted(set(series[a]) & set(series[b]))
            if len(common) < DISCOVERY_WINDOW + FOLD_STEP:
                continue
            n_pairs_tested += 1
            la = np.log(np.array([series[a][t] for t in common]))
            lb = np.log(np.array([series[b][t] for t in common]))
            n = len(common)
            for E in range(DISCOVERY_WINDOW, n - max(HORIZONS) + 1, FOLD_STEP):
                y = la[E - DISCOVERY_WINDOW:E]
                x = lb[E - DISCOVERY_WINDOW:E]
                try:
                    _, pval, _ = coint(y, x)
                except Exception:
                    continue
                if pval > DISCOVERY_P:
                    continue
                beta, c = ols_beta_c(y, x)
                resid = y - beta * x - c
                sigma_s = float(np.std(resid))
                edge_usd = 2.0 * sigma_s * GROSS
                row = {"pair": f"{a}/{b}", "fold_end_idx": E,
                       "discovery_p": round(pval, 5), "beta": round(beta, 5),
                       "sigma_s": round(sigma_s, 6), "edge_usd": round(edge_usd, 3)}
                for H in HORIZONS:
                    s, e = E - DISCOVERY_WINDOW + H, E + H
                    if e > n:
                        row[f"surv_{H}d"] = ""
                        continue
                    spread_h = la[s:e] - beta * lb[s:e] - c
                    try:
                        p_h = adfuller(spread_h, regression="c")[1]
                    except Exception:
                        row[f"surv_{H}d"] = ""
                        continue
                    row[f"p_{H}d"] = round(float(p_h), 5)
                    row[f"surv_{H}d"] = int(p_h <= SURVIVAL_P)
                    if H == GATE_HORIZON:
                        b2, c2 = ols_beta_c(la[s:e], lb[s:e])
                        row["beta_drift_10d"] = round(abs(b2 - beta) / abs(beta), 4) if beta else ""
                        try:
                            _, p_refit, _ = coint(la[s:e], lb[s:e])
                            row["refit_surv_10d"] = int(p_refit <= SURVIVAL_P)
                        except Exception:
                            row["refit_surv_10d"] = ""
                pair_fold_rows.append(row)

    print(f"\nPairs with sufficient overlap: {n_pairs_tested}")
    print(f"Discovery-passing (pair, fold) observations: {len(pair_fold_rows)}")

    # ---- pooled aggregates ----
    def pool(H: int) -> tuple[int, int, float]:
        obs = [r for r in pair_fold_rows if r.get(f"surv_{H}d") != ""]
        surv = sum(r[f"surv_{H}d"] for r in obs)
        return len(obs), surv, (surv / len(obs) if obs else float("nan"))

    print(f"\n{'horizon':>8} {'n_obs':>6} {'n_surv':>7} {'rate':>7}")
    rates = {}
    for H in HORIZONS:
        n_o, n_s, rate = pool(H)
        rates[H] = (n_o, n_s, rate)
        print(f"{H:>7}d {n_o:>6} {n_s:>7} {rate:>7.3f}" if n_o else f"{H:>7}d {n_o:>6} {'—':>7} {'—':>7}")

    distinct_pairs = len({r["pair"] for r in pair_fold_rows
                          if r.get(f"surv_{GATE_HORIZON}d") != ""})
    print(f"distinct pairs contributing at +{GATE_HORIZON}d: {distinct_pairs}")

    # refit-survival + beta drift context
    refit_obs = [r for r in pair_fold_rows if r.get("refit_surv_10d") not in ("", None)]
    if refit_obs:
        rr = sum(r["refit_surv_10d"] for r in refit_obs) / len(refit_obs)
        print(f"refit-beta survival @+10d (context, not gated): {rr:.3f} (n={len(refit_obs)})")
    drifts = [r["beta_drift_10d"] for r in pair_fold_rows
              if isinstance(r.get("beta_drift_10d"), float)]
    if drifts:
        print(f"median |beta drift| @+10d: {np.median(drifts):.4f}")

    # ---- Part B ----
    survivors_10 = [r for r in pair_fold_rows if r.get(f"surv_{GATE_HORIZON}d") == 1]
    median_edge = float(np.median([r["edge_usd"] for r in survivors_10])) if survivors_10 else float("nan")
    print(f"\nPart B — median 2-sigma dollar edge of +{GATE_HORIZON}d survivors: "
          f"${median_edge:.2f}" if survivors_10 else "\nPart B — no survivors to measure")
    for name, stack in COST_STACKS.items():
        if survivors_10:
            print(f"  vs stack {name} = ${stack:.2f}: edge/stack = {median_edge/stack:.1f}x")
    print(f"  GATE (locked): median edge >= ${EDGE_GATE:.2f} (3x mid stack)")

    # ---- persist per-observation data ----
    out_csv = OUTPUT_DIR / "d3_pair_fold_results.csv"
    if pair_fold_rows:
        keys = ["pair", "fold_end_idx", "discovery_p", "beta", "sigma_s", "edge_usd",
                "p_5d", "surv_5d", "p_10d", "surv_10d", "refit_surv_10d",
                "beta_drift_10d", "p_20d", "surv_20d"]
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            w.writeheader()
            w.writerows(pair_fold_rows)
        print(f"\nper-observation data: {out_csv.relative_to(PROJECT_ROOT)}")

    # ---- verdict (locked rules; borderline resolves DOWN) ----
    n10, s10, r10 = rates[10]
    n20, s20, r20 = rates[20]
    print("\n" + "=" * 90)
    print("VERDICT (per work item v1.0, locked at commit 77b3dee)")
    print("=" * 90)

    guards_met = (n10 >= N_GUARD_OBS) and (distinct_pairs >= N_GUARD_PAIRS)
    if not guards_met:
        print("D3-PREMISE-AMBIGUOUS (sub-cause: UNDERPOWERED)")
        print(f"  n_obs@+10d = {n10} (need >= {N_GUARD_OBS}); distinct pairs = {distinct_pairs} "
              f"(need >= {N_GUARD_PAIRS}).")
        print("  Few daily-scale cointegrations exist to even test — itself informative")
        print("  about the universe. Routes to operator with sub-cause named.")
        verdict = "AMBIGUOUS-UNDERPOWERED"
    elif r10 <= DEAD_10D:
        print("D3-PREMISE-DEAD")
        print(f"  Frozen-beta survival @+10d = {r10:.1%} <= 40% (the minute-scale analogue")
        print("  that killed MR). Daily-scale relationships on this universe are no more")
        print("  stable over a hold than minute-scale ones were. The timescale hypothesis")
        print("  is falsified. D3 closes; remaining options: G (class pivot) or stop.")
        verdict = "DEAD"
    elif r10 >= SUPPORTED_10D and r20 >= SUPPORTED_20D:
        if survivors_10 and median_edge >= EDGE_GATE:
            print("D3-PREMISE-SUPPORTED")
            print(f"  Survival @+10d = {r10:.1%} (>= 70%), @+20d = {r20:.1%} (>= 50%);")
            print(f"  guards met (n={n10}, pairs={distinct_pairs}); median edge ${median_edge:.2f} >= ${EDGE_GATE:.2f}.")
            print("  CAVEATS (mandatory): funding assumption-based; survival != profitability;")
            print("  premise-support, not a backtest. Routes to: D3 experiment design scoping.")
            verdict = "SUPPORTED"
        else:
            print("D3-PREMISE-AMBIGUOUS (sub-cause: EDGE-FAILS-COSTS)")
            print(f"  Survival passes ({r10:.1%} / {r20:.1%}) but median edge "
                  f"${median_edge:.2f} < ${EDGE_GATE:.2f}.")
            print("  Relationships hold; the captured move doesn't clear the multi-day stack")
            print("  at $200 gross. Routes to operator (notional/cost question, not stability).")
            verdict = "AMBIGUOUS-EDGE-FAILS-COSTS"
    else:
        print("D3-PREMISE-AMBIGUOUS (sub-cause: GRAY-ZONE)")
        print(f"  Survival @+10d = {r10:.1%} (between 40% and 70%) "
              f"{'and/or @+20d = ' + format(r20, '.1%') + ' < 50%' if r20 < SUPPORTED_20D else ''}.")
        print("  Neither supported nor refuted at this universe/window. Borderline resolves")
        print("  DOWN per the lock. Routes to operator with the gray-zone numbers.")
        verdict = "AMBIGUOUS-GRAY-ZONE"

    print(f"\nVerdict: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
