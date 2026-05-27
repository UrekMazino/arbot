"""
retroactive_beta.py — Compute OLS hedge ratio (β) for T5–T14 entry timestamps.

Step 1 of the counterfactual study for exp_coint_stability_v1.

Window parameters match live execution exactly:
  - 200 bars of 1-minute klines ending at entry_ts (STATBOT_EXECUTION_KLINE_LIMIT=200)
  - OLS regression on the full 200-bar series (window=21 used for z-score only, not OLS)
  - Same evaluate_cointegration() call as func_get_zscore.py

Also computes counterfactual PnL:
  - equal_notional: $100 per leg (live production mode, 2× gross = $200)
  - gross_normalized_beta: gross=$200 split as $200/(1+β) leg1, $200β/(1+β) leg2

Run from project root:
    python core/chart_audit/retroactive_beta.py
"""

from __future__ import annotations

import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXEC_DIR = ROOT / "Execution"
sys.path.insert(0, str(EXEC_DIR))
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(EXEC_DIR / "Execution.env")

import numpy as np

from func_price_calls import get_candlesticks
from config_execution_api import market_session
from shared_cointegration_validator import evaluate_cointegration

def _get_candlesticks_auto(inst_id: str, bar: str, limit: int, after: int) -> dict:
    """
    Use market/history-candles endpoint (covers all historical timestamps including recent).
    The live market/candles endpoint only returns the last ~200 recent bars.
    """
    kwargs = {"instId": inst_id, "bar": bar, "limit": str(limit), "after": str(after)}
    try:
        return market_session.get_history_candlesticks(**kwargs)
    except Exception as exc:
        return {"code": "1", "msg": str(exc), "data": []}


LIMIT = 200   # STATBOT_EXECUTION_KLINE_LIMIT
BAR = "1m"    # STATBOT_EXECUTION_TIMEFRAME
WINDOW = 21   # STATBOT_Z_SCORE_WINDOW (z-score only; OLS uses full series)
GROSS = 200.0 # gross pair notional, confirmed from trade_closes.csv entry_notional_usdt=200.0
              # equal-notional: each leg = $100; gross-normalized-beta: leg1+leg2 = $200

TRADES = [
    # (id, inst_1, inst_2, side, entry_ts_iso, exit_ts_iso, actual_pnl_usdt)
    # side: "L1S2" = long inst_1 short inst_2; "S1L2" = short inst_1 long inst_2
    # For "long_negative_short_positive" (entry_z < 0): L1S2
    # For "long_positive_short_negative" (entry_z > 0): S1L2
    ("T5",  "FIL-USDT-SWAP",   "FLOKI-USDT-SWAP", "S1L2",
     "2026-05-24T06:07:46.331878+00:00", "2026-05-24T06:13:01.544073+00:00", -0.555291),
    ("T6",  "DOGE-USDT-SWAP",  "SUI-USDT-SWAP",   "L1S2",
     "2026-05-26T04:22:46.654734+00:00", "2026-05-26T04:31:17.226644+00:00", -0.786421),
    ("T7",  "BTC-USDT-SWAP",   "HBAR-USDT-SWAP",  "L1S2",
     "2026-05-26T07:46:14.692864+00:00", "2026-05-26T08:01:06.122356+00:00", -0.106568),
    ("T8",  "SOL-USDT-SWAP",   "AVAX-USDT-SWAP",  "L1S2",
     "2026-05-26T11:38:40.049344+00:00", "2026-05-26T13:06:59.165548+00:00", -0.064731),
    ("T9",  "LINEA-USDT-SWAP", "ZRO-USDT-SWAP",   "L1S2",
     "2026-05-26T19:09:10.056576+00:00", "2026-05-26T19:14:24.800691+00:00", -0.072956),
    ("T10", "FIL-USDT-SWAP",   "ICP-USDT-SWAP",   "S1L2",
     "2026-05-27T01:37:13.575520+00:00", "2026-05-27T01:54:22.142965+00:00", -0.120461),
    ("T11", "CRV-USDT-SWAP",   "IOTA-USDT-SWAP",  "S1L2",
     "2026-05-27T05:44:25.036098+00:00", "2026-05-27T07:45:02.927115+00:00", -0.499409),
    ("T12", "SOL-USDT-SWAP",   "BTC-USDT-SWAP",   "S1L2",
     "2026-05-27T08:05:46.062102+00:00", "2026-05-27T08:50:19.914103+00:00", +0.026363),
    ("T13", "BNB-USDT-SWAP",   "COMP-USDT-SWAP",  "S1L2",
     "2026-05-27T13:01:17.932464+00:00", "2026-05-27T13:42:20.534678+00:00", -0.508409),
    ("T14", "SOL-USDT-SWAP",   "ALGO-USDT-SWAP",  "S1L2",
     "2026-05-27T14:03:21.163255+00:00", "2026-05-27T14:23:37.165448+00:00", -0.603932),
]


def _ts_to_ms(iso_str: str) -> int:
    dt = datetime.fromisoformat(iso_str)
    return int(dt.timestamp() * 1000)


def _floor_to_minute_ms(ts_ms: int) -> int:
    return (ts_ms // 60_000) * 60_000


def fetch_klines_before(inst_id: str, entry_ts_ms: int, limit: int = LIMIT, bar: str = BAR) -> list[float]:
    """
    Fetch 'limit' 1m klines ending at the bar containing entry_ts_ms.

    OKX pagination: after=ts returns bars with open_time < ts (older-than cursor).
    First page: after = floor(entry_ts_ms to minute) + 60_000
               → bars with open_time < (entry minute + 1 minute)
               → includes the entry bar ✓

    Returns close prices sorted oldest-to-newest.
    """
    bar_open_ms = _floor_to_minute_ms(entry_ts_ms)
    after_cursor = bar_open_ms + 60_000

    all_rows: list[list] = []
    seen: set = set()

    while len(all_rows) < limit:
        page_size = min(100, limit - len(all_rows))
        resp = _get_candlesticks_auto(inst_id=inst_id, bar=bar, limit=page_size, after=after_cursor)
        if resp.get("code") != "0":
            print(f"    API error for {inst_id}: {resp.get('msg')}")
            break
        page = resp.get("data", [])
        if not page:
            break
        for row in page:
            ts_val = row[0]
            if ts_val not in seen:
                seen.add(ts_val)
                all_rows.append(row)
        oldest_ts = int(float(page[-1][0]))
        after_cursor = oldest_ts
        if len(page) < page_size:
            break
        time.sleep(0.15)

    all_rows.sort(key=lambda r: int(float(r[0])))
    tail = all_rows[-limit:] if len(all_rows) >= limit else all_rows
    return [float(r[4]) for r in tail]


def fetch_single_close(inst_id: str, ts_ms: int, bar: str = BAR) -> float | None:
    """
    Fetch the close price of the 1m bar that was open at ts_ms.
    Uses after = floor(ts_ms to minute) + 60_000, limit=1.
    """
    bar_open_ms = _floor_to_minute_ms(ts_ms)
    after_cursor = bar_open_ms + 60_000
    resp = _get_candlesticks_auto(inst_id=inst_id, bar=bar, limit=1, after=after_cursor)
    if resp.get("code") != "0":
        return None
    page = resp.get("data", [])
    if not page:
        return None
    return float(page[0][4])


def compute_beta(series_1: list[float], series_2: list[float]) -> float | None:
    """OLS β from evaluate_cointegration() on the full aligned series."""
    s1 = np.array(series_1, dtype=float)
    s2 = np.array(series_2, dtype=float)
    try:
        metrics = evaluate_cointegration(s1, s2, window=WINDOW)
        beta = metrics.get("hedge_ratio")
        return float(beta) if beta is not None else None
    except Exception as e:
        print(f"    evaluate_cointegration failed: {e}")
        return None


def compute_counterfactual(
    *,
    side: str,
    beta: float,
    p1_entry: float,
    p2_entry: float,
    p1_exit: float,
    p2_exit: float,
    gross: float = GROSS,
) -> dict:
    """
    Compute equal-notional and gross-normalized-beta PnL for a trade.

    side:
      'L1S2' = long inst_1, short inst_2 (entry_z < 0, long_negative_short_positive)
      'S1L2' = short inst_1, long inst_2 (entry_z > 0, long_positive_short_negative)

    equal_notional: each leg = gross/2
    gross_normalized_beta: leg1 = gross/(1+β), leg2 = gross*β/(1+β)
    """
    r1 = (p1_exit - p1_entry) / p1_entry
    r2 = (p2_exit - p2_entry) / p2_entry

    leg_equal = gross / 2.0
    leg1_beta = gross / (1.0 + beta)
    leg2_beta = gross * beta / (1.0 + beta)

    if side == "L1S2":
        # long inst_1, short inst_2
        pnl_equal = leg_equal * r1 - leg_equal * r2
        pnl_beta = leg1_beta * r1 - leg2_beta * r2
    else:
        # S1L2: short inst_1, long inst_2
        pnl_equal = -leg_equal * r1 + leg_equal * r2
        pnl_beta = -leg1_beta * r1 + leg2_beta * r2

    delta = pnl_beta - pnl_equal
    delta_pct = delta / abs(pnl_equal) * 100 if pnl_equal != 0 else float("nan")

    return {
        "r1": r1,
        "r2": r2,
        "leg1_equal": leg_equal,
        "leg2_equal": leg_equal,
        "leg1_beta": leg1_beta,
        "leg2_beta": leg2_beta,
        "pnl_equal": pnl_equal,
        "pnl_beta": pnl_beta,
        "delta": delta,
        "delta_pct": delta_pct,
        "sign_flip": (pnl_equal * pnl_beta < 0),
    }


def main() -> None:
    print("=" * 70)
    print("Retroactive β computation — exp_coint_stability_v1 T5–T14")
    print(f"Window: {LIMIT} bars × {BAR} | OLS on full series | z-window={WINDOW}")
    print(f"Gross notional per trade: ${GROSS:.0f} (${GROSS/2:.0f}/leg equal-notional)")
    print("=" * 70)
    print()

    results = []

    for trade_id, inst_1, inst_2, side, entry_iso, exit_iso, actual_pnl in TRADES:
        entry_ts_ms = _ts_to_ms(entry_iso)
        exit_ts_ms = _ts_to_ms(exit_iso)
        pair = f"{inst_1.replace('-USDT-SWAP','')}/{inst_2.replace('-USDT-SWAP','')}"
        entry_fmt = datetime.fromisoformat(entry_iso).strftime("%m-%d %H:%M UTC")

        print(f"--- {trade_id}: {pair}  ({entry_fmt}, side={side}) ---")

        s1 = fetch_klines_before(inst_1, entry_ts_ms)
        time.sleep(0.2)
        s2 = fetch_klines_before(inst_2, entry_ts_ms)
        time.sleep(0.2)

        print(f"  Klines: {len(s1)} for {inst_1.split('-')[0]}, {len(s2)} for {inst_2.split('-')[0]}")

        if len(s1) < 10 or len(s2) < 10:
            print(f"  SKIP: insufficient kline data")
            results.append({
                "id": trade_id, "pair": pair, "beta": None,
                "pnl_equal": None, "pnl_beta": None, "delta": None,
                "sign_flip": None, "actual_pnl": actual_pnl, "error": "insufficient_data",
            })
            print()
            continue

        min_len = min(len(s1), len(s2))
        s1_aligned = s1[-min_len:]
        s2_aligned = s2[-min_len:]

        beta = compute_beta(s1_aligned, s2_aligned)
        if beta is None:
            print(f"  SKIP: OLS failed")
            results.append({
                "id": trade_id, "pair": pair, "beta": None,
                "pnl_equal": None, "pnl_beta": None, "delta": None,
                "sign_flip": None, "actual_pnl": actual_pnl, "error": "ols_failed",
            })
            print()
            continue

        print(f"  β = {beta:.4f}")

        # Fetch entry and exit prices
        p1_entry = s1_aligned[-1] if s1_aligned else None
        p2_entry = s2_aligned[-1] if s2_aligned else None

        p1_exit = fetch_single_close(inst_1, exit_ts_ms)
        time.sleep(0.15)
        p2_exit = fetch_single_close(inst_2, exit_ts_ms)
        time.sleep(0.15)

        if any(p is None for p in [p1_entry, p2_entry, p1_exit, p2_exit]):
            print(f"  SKIP: could not fetch price data (entry={p1_entry},{p2_entry} exit={p1_exit},{p2_exit})")
            results.append({
                "id": trade_id, "pair": pair, "beta": beta,
                "pnl_equal": None, "pnl_beta": None, "delta": None,
                "sign_flip": None, "actual_pnl": actual_pnl, "error": "price_fetch_failed",
            })
            print()
            continue

        cf = compute_counterfactual(
            side=side, beta=beta,
            p1_entry=p1_entry, p2_entry=p2_entry,
            p1_exit=p1_exit, p2_exit=p2_exit,
        )

        print(f"  Entry prices: {inst_1.split('-')[0]}=${p1_entry:.4f}, {inst_2.split('-')[0]}=${p2_entry:.4f}")
        print(f"  Exit prices:  {inst_1.split('-')[0]}=${p1_exit:.4f}, {inst_2.split('-')[0]}=${p2_exit:.4f}")
        print(f"  Returns: r1={cf['r1']*100:.3f}%, r2={cf['r2']*100:.3f}%")
        print(f"  Leg sizing — equal: ${cf['leg1_equal']:.0f}/${cf['leg2_equal']:.0f} | β-sized: ${cf['leg1_beta']:.1f}/${cf['leg2_beta']:.1f}")
        print(f"  PnL equal-notional:  ${cf['pnl_equal']:+.4f}  (actual: ${actual_pnl:+.4f})")
        print(f"  PnL β-sized:         ${cf['pnl_beta']:+.4f}")
        print(f"  Δ (β−equal):         ${cf['delta']:+.4f}  ({cf['delta_pct']:+.1f}%)")
        if cf["sign_flip"]:
            print(f"  *** SIGN FLIP: equal-notional and β-sized have opposite PnL signs ***")
        print()

        results.append({
            "id": trade_id, "pair": pair, "beta": beta, "side": side,
            "pnl_equal": cf["pnl_equal"], "pnl_beta": cf["pnl_beta"],
            "delta": cf["delta"], "sign_flip": cf["sign_flip"],
            "actual_pnl": actual_pnl, "error": None,
            "r1": cf["r1"], "r2": cf["r2"],
        })

    # Summary table
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"{'ID':<4} {'Pair':<14} {'β':>6} {'PnL_equal':>11} {'PnL_β':>11} {'Δ':>9} {'Flip':<5} {'Error'}")
    print("-" * 70)
    cum_delta = 0.0
    sign_flips = []
    for r in results:
        beta_s = f"{r['beta']:.3f}" if r["beta"] is not None else "—"
        pnl_eq_s = f"${r['pnl_equal']:+.3f}" if r["pnl_equal"] is not None else "—"
        pnl_bt_s = f"${r['pnl_beta']:+.3f}" if r["pnl_beta"] is not None else "—"
        delta_s = f"${r['delta']:+.3f}" if r["delta"] is not None else "—"
        flip_s = "YES" if r.get("sign_flip") else ("—" if r["delta"] is None else "no")
        err_s = r.get("error") or ""
        print(f"{r['id']:<4} {r['pair']:<14} {beta_s:>6} {pnl_eq_s:>11} {pnl_bt_s:>11} {delta_s:>9} {flip_s:<5} {err_s}")
        if r["delta"] is not None:
            cum_delta += r["delta"]
        if r.get("sign_flip"):
            sign_flips.append(r["id"])

    valid = [r for r in results if r["delta"] is not None]
    print("-" * 70)
    print(f"{'TOTAL':<4} {'':14} {'':>6} {'':>11} {'':>11} ${cum_delta:+.3f}")
    print()
    print(f"Cumulative δ (β−equal): ${cum_delta:+.3f}")
    print(f"Sign flips: {len(sign_flips)} — {sign_flips if sign_flips else 'none'}")
    print()

    # Decision rule evaluation
    print("DECISION RULE:")
    print(f"  Criterion: cumul δ > $0.30 AND ≥2 flips AND T13/T14 among flips")
    t13_t14_flips = [f for f in sign_flips if f in ("T13", "T14")]
    criterion_met = (
        abs(cum_delta) > 0.30
        and len(sign_flips) >= 2
        and len(t13_t14_flips) >= 1
    )
    print(f"  |cumul δ| > $0.30: {abs(cum_delta):.3f} > 0.30 → {'YES' if abs(cum_delta) > 0.30 else 'NO'}")
    print(f"  ≥2 sign flips: {len(sign_flips)} → {'YES' if len(sign_flips) >= 2 else 'NO'}")
    print(f"  T13/T14 among flips: {t13_t14_flips} → {'YES' if t13_t14_flips else 'NO'}")
    print()
    if criterion_met:
        print("  → OPTION C JUSTIFIED (gross-normalized-beta sizing)")
    else:
        betas = [r["beta"] for r in valid if r["beta"] is not None]
        if betas:
            beta_min, beta_max = min(betas), max(betas)
            tight = (beta_max - beta_min) < 0.30 and all(0.85 <= b <= 1.15 for b in betas)
            print(f"  β range: [{beta_min:.3f}, {beta_max:.3f}] — {'TIGHT near 1' if tight else 'WIDE or far from 1'}")
            if tight and abs(cum_delta) < 0.30:
                print("  → OPTION A preferred (β-range gating) or pivot to Item 14/12")
            elif not tight:
                print("  → OPTION C worth pursuing despite criterion not fully met (wide β spread)")
            else:
                print("  → AMBIGUOUS — re-examine with forward data")


if __name__ == "__main__":
    main()
