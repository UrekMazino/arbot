from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Simulation import replay_pairs


def _kline(ts: int, close: float) -> dict:
    return {
        "timestamp": str(ts),
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1.0,
        "volume_ccy": 1.0,
    }


def test_replay_simulator_finds_profitable_mean_reversion(tmp_path):
    price_path = tmp_path / "1_price_list.json"
    pairs_path = tmp_path / "2_cointegrated_pairs.csv"
    output_dir = tmp_path / "sim"

    spreads = [0.0] * 20 + [0.40, 0.35, 0.30, 0.20, 0.10, 0.00] + [0.0] * 20
    base_price = 100.0
    timestamps = [1_800_000_000_000 + idx * 60_000 for idx in range(len(spreads))]
    price_data = {
        "AAA-USDT-SWAP": {
            "klines": [_kline(ts, base_price * math.exp(spread)) for ts, spread in zip(timestamps, spreads)]
        },
        "BBB-USDT-SWAP": {
            "klines": [_kline(ts, base_price) for ts in timestamps]
        },
    }
    price_path.write_text(json.dumps(price_data), encoding="utf-8")

    with pairs_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sym_1", "sym_2", "hedge_ratio"])
        writer.writeheader()
        writer.writerow({"sym_1": "AAA-USDT-SWAP", "sym_2": "BBB-USDT-SWAP", "hedge_ratio": "1.0"})

    args = replay_pairs.build_arg_parser().parse_args(
        [
            "--price-json",
            str(price_path),
            "--pairs-csv",
            str(pairs_path),
            "--output-dir",
            str(output_dir),
            "--entry-z",
            "1.0",
            "--exit-z",
            "0.2",
            "--z-window",
            "10",
            "--min-persist-bars",
            "1",
            "--fee-bps",
            "0",
            "--slippage-bps",
            "0",
            "--top",
            "5",
        ]
    )

    metadata = replay_pairs.run_replay(args)

    assert metadata["summaries"] >= 1
    assert metadata["best"] is not None
    assert metadata["best"]["net_pnl_usdt"] > 0
    assert metadata["best"]["trades"] >= 1
    assert (output_dir / "simulation_summary.csv").exists()
    assert (output_dir / "simulation_top_trades.csv").exists()
