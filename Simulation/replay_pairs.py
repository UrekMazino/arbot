from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PRICE_JSON = ROOT_DIR / "Strategy" / "output" / "1_price_list.json"
DEFAULT_PAIRS_CSV = ROOT_DIR / "Strategy" / "output" / "2_cointegrated_pairs.csv"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "Simulation" / "output"


@dataclass(frozen=True)
class ReplayProfile:
    entry_z: float
    exit_z: float
    z_window: int
    min_persist_bars: int
    entry_z_max: float
    max_hold_bars: int
    stop_loss_pct: float
    notional_usdt: float
    fee_bps: float
    slippage_bps: float


@dataclass
class ReplayTrade:
    pair: str
    profile: str
    side: str
    entry_idx: int
    exit_idx: int
    entry_ts: str
    exit_ts: str
    entry_z: float
    exit_z: float
    hold_bars: int
    pnl_usdt: float
    pnl_pct: float
    gross_pnl_usdt: float
    cost_usdt: float
    exit_reason: str
    split: str


@dataclass
class ReplaySummary:
    pair: str
    sym_1: str
    sym_2: str
    hedge_ratio: float
    profile: str
    entry_z: float
    exit_z: float
    z_window: int
    min_persist_bars: int
    trades: int
    wins: int
    losses: int
    win_rate_pct: float | None
    net_pnl_usdt: float
    gross_pnl_usdt: float
    costs_usdt: float
    avg_pnl_usdt: float | None
    max_drawdown_usdt: float
    train_trades: int
    train_pnl_usdt: float
    validation_trades: int
    validation_pnl_usdt: float
    validation_win_rate_pct: float | None
    score: float


def _parse_float_list(raw: str) -> list[float]:
    values: list[float] = []
    for part in str(raw or "").split(","):
        text = part.strip()
        if not text:
            continue
        values.append(float(text))
    return values


def _parse_int_list(raw: str) -> list[int]:
    values: list[int] = []
    for part in str(raw or "").split(","):
        text = part.strip()
        if not text:
            continue
        values.append(int(float(text)))
    return values


def _safe_float(value, default: float | None = None) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(result):
        return default
    return result


def _load_price_data(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"price JSON must be an object: {path}")
    return data


def _load_candidate_pairs(path: Path, limit: int | None = None) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            sym_1 = str(row.get("sym_1") or "").strip()
            sym_2 = str(row.get("sym_2") or "").strip()
            if not sym_1 or not sym_2:
                continue
            rows.append(row)
            if limit is not None and len(rows) >= limit:
                break
    return rows


def _extract_series(symbol_payload: dict) -> tuple[list[float], list[int]]:
    prices: list[float] = []
    timestamps: list[int] = []
    for row in symbol_payload.get("klines") or []:
        if not isinstance(row, dict):
            continue
        close = _safe_float(row.get("close"))
        if close is None or close <= 0:
            continue
        ts = _safe_float(row.get("timestamp"))
        if ts is None:
            ts = float(len(timestamps))
        timestamps.append(int(ts))
        prices.append(float(close))
    return prices, timestamps


def _align_series(
    prices_1: list[float],
    ts_1: list[int],
    prices_2: list[float],
    ts_2: list[int],
) -> tuple[list[float], list[float], list[int]]:
    by_ts_1 = {ts: price for ts, price in zip(ts_1, prices_1)}
    by_ts_2 = {ts: price for ts, price in zip(ts_2, prices_2)}
    common = sorted(set(by_ts_1).intersection(by_ts_2))
    if common:
        return [by_ts_1[ts] for ts in common], [by_ts_2[ts] for ts in common], common

    min_len = min(len(prices_1), len(prices_2))
    if min_len <= 0:
        return [], [], []
    return prices_1[-min_len:], prices_2[-min_len:], ts_1[-min_len:]


def _rolling_zscore(values: list[float], window: int) -> list[float | None]:
    zscores: list[float | None] = [None] * len(values)
    if window < 2:
        window = 2
    for idx in range(window - 1, len(values)):
        sample = values[idx - window + 1 : idx + 1]
        avg = sum(sample) / len(sample)
        variance = sum((item - avg) ** 2 for item in sample) / len(sample)
        std = math.sqrt(variance)
        if std <= 0:
            continue
        zscores[idx] = (values[idx] - avg) / std
    return zscores


def _format_timestamp(raw_ts: int) -> str:
    try:
        ts = float(raw_ts)
        if ts > 10_000_000_000:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except Exception:
        return str(raw_ts)


def _profile_label(profile: ReplayProfile) -> str:
    return (
        f"ez{profile.entry_z:g}_xz{profile.exit_z:g}_w{profile.z_window}"
        f"_p{profile.min_persist_bars}_h{profile.max_hold_bars}"
    )


def _entry_signal(
    zscores: list[float | None],
    idx: int,
    entry_z: float,
    entry_z_max: float,
    min_persist_bars: int,
) -> str | None:
    start = idx - max(min_persist_bars, 1) + 1
    if start < 0:
        return None
    window = zscores[start : idx + 1]
    if any(value is None for value in window):
        return None

    values = [float(value) for value in window if value is not None]
    latest = values[-1]
    if latest >= entry_z and latest <= entry_z_max and all(entry_z <= value <= entry_z_max for value in values):
        return "short_spread"
    if latest <= -entry_z and latest >= -entry_z_max and all(-entry_z_max <= value <= -entry_z for value in values):
        return "long_spread"
    return None


def _trade_pnl(
    side: str,
    entry_p1: float,
    exit_p1: float,
    entry_p2: float,
    exit_p2: float,
    hedge_ratio: float,
    profile: ReplayProfile,
) -> tuple[float, float, float, float]:
    hedge_abs = abs(hedge_ratio)
    leg_1_notional = profile.notional_usdt / (1.0 + hedge_abs)
    leg_2_notional = profile.notional_usdt - leg_1_notional
    ret_1 = math.log(exit_p1 / entry_p1)
    ret_2 = math.log(exit_p2 / entry_p2)

    if side == "long_spread":
        gross_pnl = leg_1_notional * ret_1 - leg_2_notional * ret_2
    else:
        gross_pnl = -leg_1_notional * ret_1 + leg_2_notional * ret_2

    cost_rate = max(profile.fee_bps, 0.0) / 10_000.0 + max(profile.slippage_bps, 0.0) / 10_000.0
    cost = profile.notional_usdt * 2.0 * cost_rate
    net_pnl = gross_pnl - cost
    pnl_pct = (net_pnl / profile.notional_usdt) * 100.0 if profile.notional_usdt > 0 else 0.0
    return net_pnl, pnl_pct, gross_pnl, cost


def replay_pair(
    sym_1: str,
    sym_2: str,
    hedge_ratio: float,
    price_data: dict,
    profile: ReplayProfile,
    train_ratio: float,
) -> list[ReplayTrade]:
    payload_1 = price_data.get(sym_1)
    payload_2 = price_data.get(sym_2)
    if not isinstance(payload_1, dict) or not isinstance(payload_2, dict):
        return []

    prices_1_raw, ts_1 = _extract_series(payload_1)
    prices_2_raw, ts_2 = _extract_series(payload_2)
    prices_1, prices_2, timestamps = _align_series(prices_1_raw, ts_1, prices_2_raw, ts_2)
    if len(prices_1) < max(profile.z_window + profile.min_persist_bars + 2, 10):
        return []

    spread = [math.log(p1) - hedge_ratio * math.log(p2) for p1, p2 in zip(prices_1, prices_2)]
    zscores = _rolling_zscore(spread, profile.z_window)
    split_idx = int(len(prices_1) * min(max(train_ratio, 0.05), 0.95))

    trades: list[ReplayTrade] = []
    idx = 0
    pair = f"{sym_1}/{sym_2}"
    profile_label = _profile_label(profile)
    while idx < len(prices_1):
        side = _entry_signal(
            zscores,
            idx,
            profile.entry_z,
            profile.entry_z_max,
            profile.min_persist_bars,
        )
        if side is None:
            idx += 1
            continue

        entry_idx = idx
        exit_idx = None
        exit_reason = "end_of_data"
        for cursor in range(entry_idx + 1, len(prices_1)):
            net_pnl, pnl_pct, _gross_pnl, _cost = _trade_pnl(
                side,
                prices_1[entry_idx],
                prices_1[cursor],
                prices_2[entry_idx],
                prices_2[cursor],
                hedge_ratio,
                profile,
            )
            z_val = zscores[cursor]
            hold_bars = cursor - entry_idx
            if profile.stop_loss_pct > 0 and pnl_pct <= -abs(profile.stop_loss_pct):
                exit_idx = cursor
                exit_reason = "stop_loss"
                break
            if z_val is not None and abs(float(z_val)) <= profile.exit_z:
                exit_idx = cursor
                exit_reason = "mean_reversion"
                break
            if profile.max_hold_bars > 0 and hold_bars >= profile.max_hold_bars:
                exit_idx = cursor
                exit_reason = "max_hold"
                break

        if exit_idx is None:
            exit_idx = len(prices_1) - 1

        net_pnl, pnl_pct, gross_pnl, cost = _trade_pnl(
            side,
            prices_1[entry_idx],
            prices_1[exit_idx],
            prices_2[entry_idx],
            prices_2[exit_idx],
            hedge_ratio,
            profile,
        )
        entry_z = float(zscores[entry_idx] or 0.0)
        exit_z = float(zscores[exit_idx] or 0.0)
        trades.append(
            ReplayTrade(
                pair=pair,
                profile=profile_label,
                side=side,
                entry_idx=entry_idx,
                exit_idx=exit_idx,
                entry_ts=_format_timestamp(timestamps[entry_idx]),
                exit_ts=_format_timestamp(timestamps[exit_idx]),
                entry_z=round(entry_z, 6),
                exit_z=round(exit_z, 6),
                hold_bars=exit_idx - entry_idx,
                pnl_usdt=round(net_pnl, 8),
                pnl_pct=round(pnl_pct, 8),
                gross_pnl_usdt=round(gross_pnl, 8),
                cost_usdt=round(cost, 8),
                exit_reason=exit_reason,
                split="train" if entry_idx < split_idx else "validation",
            )
        )
        idx = max(exit_idx + 1, idx + 1)
    return trades


def _max_drawdown(pnls: Iterable[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in pnls:
        equity += float(pnl)
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def _win_rate(trades: list[ReplayTrade]) -> float | None:
    if not trades:
        return None
    wins = sum(1 for trade in trades if trade.pnl_usdt > 0)
    return (wins / len(trades)) * 100.0


def summarize_trades(sym_1: str, sym_2: str, hedge_ratio: float, profile: ReplayProfile, trades: list[ReplayTrade]) -> ReplaySummary:
    wins = sum(1 for trade in trades if trade.pnl_usdt > 0)
    losses = sum(1 for trade in trades if trade.pnl_usdt < 0)
    net_pnl = sum(trade.pnl_usdt for trade in trades)
    gross_pnl = sum(trade.gross_pnl_usdt for trade in trades)
    costs = sum(trade.cost_usdt for trade in trades)
    train = [trade for trade in trades if trade.split == "train"]
    validation = [trade for trade in trades if trade.split == "validation"]
    validation_pnl = sum(trade.pnl_usdt for trade in validation)
    train_pnl = sum(trade.pnl_usdt for trade in train)
    drawdown = _max_drawdown(trade.pnl_usdt for trade in trades)
    validation_win_rate = _win_rate(validation)

    # Prefer profiles that make money in validation, but penalize overfit profiles
    # that only work in-sample or have very few validation trades.
    validation_trade_bonus = min(len(validation), 10) * 0.10
    train_penalty = min(train_pnl, 0.0) * 0.25
    drawdown_penalty = abs(drawdown) * 0.05
    score = validation_pnl + train_penalty - drawdown_penalty + validation_trade_bonus

    return ReplaySummary(
        pair=f"{sym_1}/{sym_2}",
        sym_1=sym_1,
        sym_2=sym_2,
        hedge_ratio=round(hedge_ratio, 8),
        profile=_profile_label(profile),
        entry_z=profile.entry_z,
        exit_z=profile.exit_z,
        z_window=profile.z_window,
        min_persist_bars=profile.min_persist_bars,
        trades=len(trades),
        wins=wins,
        losses=losses,
        win_rate_pct=round((wins / len(trades)) * 100.0, 2) if trades else None,
        net_pnl_usdt=round(net_pnl, 8),
        gross_pnl_usdt=round(gross_pnl, 8),
        costs_usdt=round(costs, 8),
        avg_pnl_usdt=round(mean([trade.pnl_usdt for trade in trades]), 8) if trades else None,
        max_drawdown_usdt=round(drawdown, 8),
        train_trades=len(train),
        train_pnl_usdt=round(train_pnl, 8),
        validation_trades=len(validation),
        validation_pnl_usdt=round(validation_pnl, 8),
        validation_win_rate_pct=round(validation_win_rate, 2) if validation_win_rate is not None else None,
        score=round(score, 8),
    )


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_profiles(args: argparse.Namespace) -> list[ReplayProfile]:
    profiles: list[ReplayProfile] = []
    for entry_z in _parse_float_list(args.entry_z):
        for exit_z in _parse_float_list(args.exit_z):
            for z_window in _parse_int_list(args.z_window):
                for min_persist in _parse_int_list(args.min_persist_bars):
                    if exit_z >= entry_z:
                        continue
                    profiles.append(
                        ReplayProfile(
                            entry_z=entry_z,
                            exit_z=exit_z,
                            z_window=max(z_window, 2),
                            min_persist_bars=max(min_persist, 1),
                            entry_z_max=float(args.entry_z_max),
                            max_hold_bars=max(int(args.max_hold_bars), 0),
                            stop_loss_pct=max(float(args.stop_loss_pct), 0.0),
                            notional_usdt=max(float(args.notional_usdt), 1.0),
                            fee_bps=max(float(args.fee_bps), 0.0),
                            slippage_bps=max(float(args.slippage_bps), 0.0),
                        )
                    )
    return profiles


def run_replay(args: argparse.Namespace) -> dict:
    price_path = Path(args.price_json)
    pairs_path = Path(args.pairs_csv)
    output_dir = Path(args.output_dir)
    price_data = _load_price_data(price_path)
    pairs = _load_candidate_pairs(pairs_path, limit=args.limit_pairs)
    profiles = build_profiles(args)

    summaries: list[ReplaySummary] = []
    all_trades: list[ReplayTrade] = []
    skipped_pairs: list[dict] = []

    for row in pairs:
        sym_1 = str(row.get("sym_1") or "").strip()
        sym_2 = str(row.get("sym_2") or "").strip()
        hedge_ratio = _safe_float(row.get("hedge_ratio"), 1.0) or 1.0
        if sym_1 not in price_data or sym_2 not in price_data:
            skipped_pairs.append({"sym_1": sym_1, "sym_2": sym_2, "reason": "missing_price_data"})
            continue
        for profile in profiles:
            trades = replay_pair(sym_1, sym_2, hedge_ratio, price_data, profile, args.train_ratio)
            if len(trades) < args.min_trades:
                continue
            summaries.append(summarize_trades(sym_1, sym_2, hedge_ratio, profile, trades))
            all_trades.extend(trades)

    summaries.sort(
        key=lambda item: (
            item.score,
            item.validation_pnl_usdt,
            item.net_pnl_usdt,
            item.validation_trades,
        ),
        reverse=True,
    )
    top_summaries = summaries[: args.top]
    top_keys = {(summary.pair, summary.profile) for summary in top_summaries}
    top_trades = [trade for trade in all_trades if (trade.pair, trade.profile) in top_keys]

    summary_rows = [asdict(summary) for summary in summaries]
    trade_rows = [asdict(trade) for trade in top_trades]
    skipped_rows = skipped_pairs
    _write_csv(output_dir / "simulation_summary.csv", summary_rows)
    _write_csv(output_dir / "simulation_top_trades.csv", trade_rows)
    _write_csv(output_dir / "simulation_skipped_pairs.csv", skipped_rows)

    best = asdict(top_summaries[0]) if top_summaries else None
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "price_json": str(price_path),
        "pairs_csv": str(pairs_path),
        "candidate_pairs": len(pairs),
        "profiles": len(profiles),
        "summaries": len(summaries),
        "trades_in_top_profiles": len(top_trades),
        "skipped_pairs": len(skipped_pairs),
        "best": best,
        "outputs": {
            "summary_csv": str(output_dir / "simulation_summary.csv"),
            "top_trades_csv": str(output_dir / "simulation_top_trades.csv"),
            "skipped_pairs_csv": str(output_dir / "simulation_skipped_pairs.csv"),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "simulation_best.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Offline replay simulator for Strategy cointegrated-pair candidates.",
    )
    parser.add_argument("--price-json", default=str(DEFAULT_PRICE_JSON))
    parser.add_argument("--pairs-csv", default=str(DEFAULT_PAIRS_CSV))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--entry-z", default="1.8,2.0,2.2")
    parser.add_argument("--exit-z", default="0.25,0.35,0.5")
    parser.add_argument("--z-window", default="60,120")
    parser.add_argument("--min-persist-bars", default="1,4")
    parser.add_argument("--entry-z-max", type=float, default=3.0)
    parser.add_argument("--max-hold-bars", type=int, default=360)
    parser.add_argument("--stop-loss-pct", type=float, default=3.0)
    parser.add_argument("--notional-usdt", type=float, default=2000.0)
    parser.add_argument("--fee-bps", type=float, default=5.0, help="Per-side fee in basis points.")
    parser.add_argument("--slippage-bps", type=float, default=2.0, help="Per-side slippage in basis points.")
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--min-trades", type=int, default=1)
    parser.add_argument("--limit-pairs", type=int, default=None)
    parser.add_argument("--top", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    metadata = run_replay(args)
    best = metadata.get("best")
    print(f"Replay complete: summaries={metadata['summaries']} skipped_pairs={metadata['skipped_pairs']}")
    print(f"Summary CSV: {metadata['outputs']['summary_csv']}")
    if best:
        print(
            "Best profile: "
            f"{best['pair']} {best['profile']} "
            f"validation_pnl={best['validation_pnl_usdt']:.4f} "
            f"net_pnl={best['net_pnl_usdt']:.4f} "
            f"trades={best['trades']}"
        )
    else:
        print("No replay profiles produced trades. Refresh Strategy outputs or relax entry filters.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
