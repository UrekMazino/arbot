from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from Strategy import pair_universe_curator as curator
from Platform.api.app.services import cointegrated_pairs as cp


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


def _write_sample_inputs(tmp_path: Path) -> tuple[Path, Path]:
    pairs_path = tmp_path / "2_cointegrated_pairs.csv"
    price_path = tmp_path / "1_price_list.json"

    pd.DataFrame(
        [
            {
                "sym_1": "AAA-USDT-SWAP",
                "sym_2": "BBB-USDT-SWAP",
                "p_value": 0.01,
                "adf_stat": -4.1,
                "hedge_ratio": 1.0,
                "zero_crossing": 12,
                "pair_liquidity_min": 2500.0,
                "pair_order_capacity_usdt": 15000.0,
            },
            {
                "sym_1": "CCC-USDT-SWAP",
                "sym_2": "DDD-USDT-SWAP",
                "p_value": 0.08,
                "adf_stat": -3.4,
                "hedge_ratio": 1.0,
                "zero_crossing": 4,
                "pair_liquidity_min": 800.0,
                "pair_order_capacity_usdt": 5000.0,
            },
        ]
    ).to_csv(pairs_path, index=False)

    rows_a = []
    rows_b = []
    rows_c = []
    rows_d = []
    base_ts = 1_800_000_000_000
    for idx in range(140):
        ts = base_ts + idx * 60_000
        base = 100.0 + idx * 0.03
        spread = math.sin(idx / 5.0) * 0.01
        rows_a.append(_kline(ts, base * math.exp(spread)))
        rows_b.append(_kline(ts, base))
        rows_c.append(_kline(ts, 50.0 + idx * 0.02))
        rows_d.append(_kline(ts, 80.0 + idx * 0.5))
    price_path.write_text(
        json.dumps(
            {
                "AAA-USDT-SWAP": {"klines": rows_a},
                "BBB-USDT-SWAP": {"klines": rows_b},
                "CCC-USDT-SWAP": {"klines": rows_c},
                "DDD-USDT-SWAP": {"klines": rows_d},
            }
        ),
        encoding="utf-8",
    )
    return pairs_path, price_path


def test_pair_universe_curator_writes_ranked_advisory_report(monkeypatch, tmp_path):
    pairs_path, price_path = _write_sample_inputs(tmp_path)
    report_path = tmp_path / "pair_universe_curator.json"
    state_path = tmp_path / "pair_universe_curator_control.json"

    monkeypatch.setattr(curator, "COINT_CSV", pairs_path)
    monkeypatch.setattr(curator, "PRICE_JSON", price_path)
    monkeypatch.setattr(curator, "CURATOR_REPORT_JSON", report_path)
    monkeypatch.setattr(curator, "CURATOR_STATE_JSON", state_path)
    monkeypatch.setattr(curator, "EXECUTION_ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(curator, "EXECUTION_STATE_ROOT", tmp_path)
    monkeypatch.setenv("STATBOT_PAIR_CURATOR_STALE_SECONDS", "999999")
    monkeypatch.setenv("STATBOT_PAIR_CURATOR_KLINE_LIMIT", "120")
    monkeypatch.setenv("STATBOT_STRATEGY_Z_SCORE_WINDOW", "20")

    report = curator.run_curator_once()

    assert report["pair_count"] == 2
    assert report_path.exists()
    assert state_path.exists()
    assert report["top_pairs"][0]["score"] >= report["top_pairs"][-1]["score"]
    assert report["top_pairs"][0]["status"] in {"healthy", "watch", "degraded", "hospital_candidate"}
    assert report["top_pairs"][0]["reasons"]


def test_pair_universe_api_uses_curator_priority(monkeypatch, tmp_path):
    pairs_path, price_path = _write_sample_inputs(tmp_path)
    report_path = tmp_path / "pair_universe_curator.json"
    report_path.write_text(
        json.dumps(
            {
                "updated_at": "2026-04-23T00:00:00+00:00",
                "pair_count": 2,
                "status_counts": {"healthy": 1, "watch": 1},
                "pairs": {
                    "AAA-USDT-SWAP/BBB-USDT-SWAP": {
                        "score": 40.0,
                        "status": "watch",
                        "recommendation": "watch",
                        "reasons": ["low_crossing_frequency"],
                        "priority_rank": 2,
                        "checked_at": "2026-04-23T00:00:00+00:00",
                    },
                    "CCC-USDT-SWAP/DDD-USDT-SWAP": {
                        "score": 90.0,
                        "status": "healthy",
                        "recommendation": "promote",
                        "reasons": ["cointegration_confirmed"],
                        "priority_rank": 1,
                        "checked_at": "2026-04-23T00:00:00+00:00",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cp, "COINT_CSV", pairs_path)
    monkeypatch.setattr(cp, "PRICE_JSON", price_path)
    monkeypatch.setattr(cp, "STATUS_JSON", tmp_path / "status.json")
    monkeypatch.setattr(cp, "PAIR_STRATEGY_STATE", tmp_path / "pair_strategy_state.json")
    monkeypatch.setattr(cp, "PAIR_CURATOR_REPORT", report_path)
    monkeypatch.setattr(cp, "PAIR_CURATOR_STATE", tmp_path / "pair_curator_state.json")
    cp.set_pair_curator_enabled(True, requested_by="test")

    payload = cp.list_cointegrated_pairs()

    assert payload["curator_updated_at"] == "2026-04-23T00:00:00+00:00"
    assert payload["curator"]["enabled"] is True
    assert payload["pairs"][0]["pair"] == "CCC-USDT-SWAP/DDD-USDT-SWAP"
    assert payload["pairs"][0]["curator_score"] == 90.0
    assert payload["pairs"][0]["curator_status"] == "healthy"


def test_pair_universe_api_disables_curator_priority(monkeypatch, tmp_path):
    pairs_path, price_path = _write_sample_inputs(tmp_path)
    report_path = tmp_path / "pair_universe_curator.json"
    state_path = tmp_path / "pair_curator_state.json"
    report_path.write_text(
        json.dumps(
            {
                "updated_at": "2026-04-23T00:00:00+00:00",
                "pair_count": 2,
                "status_counts": {"healthy": 1},
                "pairs": {
                    "CCC-USDT-SWAP/DDD-USDT-SWAP": {
                        "score": 90.0,
                        "status": "healthy",
                        "recommendation": "promote",
                        "reasons": ["cointegration_confirmed"],
                        "priority_rank": 1,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(cp, "COINT_CSV", pairs_path)
    monkeypatch.setattr(cp, "PRICE_JSON", price_path)
    monkeypatch.setattr(cp, "STATUS_JSON", tmp_path / "status.json")
    monkeypatch.setattr(cp, "PAIR_STRATEGY_STATE", tmp_path / "pair_strategy_state.json")
    monkeypatch.setattr(cp, "PAIR_CURATOR_REPORT", report_path)
    monkeypatch.setattr(cp, "PAIR_CURATOR_STATE", state_path)

    status = cp.set_pair_curator_enabled(False, requested_by="test")
    payload = cp.list_cointegrated_pairs()

    assert status["enabled"] is False
    assert payload["curator"]["enabled"] is False
    assert payload["curator_updated_at"] is None
    assert payload["pairs"][0]["pair"] == "AAA-USDT-SWAP/BBB-USDT-SWAP"
    assert payload["pairs"][0]["curator_score"] is None
