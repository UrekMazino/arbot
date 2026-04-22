from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_ROOT = ROOT / "Strategy"
if str(STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(STRATEGY_ROOT))

import func_cointegration as fc


@pytest.fixture(autouse=True)
def isolate_strategy_output(monkeypatch, tmp_path):
    strategy_file = tmp_path / "Strategy" / "func_cointegration.py"
    strategy_file.parent.mkdir(parents=True, exist_ok=True)
    strategy_file.write_text("# isolated test module path\n", encoding="utf-8")
    monkeypatch.setattr(fc, "__file__", str(strategy_file))


def _build_symbol(inst_id: str, closes: list[float], *, ct_val: float) -> dict:
    klines = []
    for idx, close in enumerate(closes):
        klines.append(
            {
                "timestamp": str(idx),
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 100.0,
                "volume_ccy": 100.0,
            }
        )
    return {
        "symbol_info": {
            "symbol": inst_id,
            "instId": inst_id,
            "min_sz": 1.0,
            "lot_sz": 1.0,
            "ctVal": ct_val,
            "ctMult": 1.0,
            "ctValCcy": inst_id.split("-")[0],
            "maxMktSz": 100000.0,
            "maxStopSz": 100000.0,
        },
        "klines": klines,
    }


def test_orderbook_depth_uses_contract_value_quote():
    instrument_info = {
        "symbol": "HOME-USDT-SWAP",
        "instId": "HOME-USDT-SWAP",
        "ctVal": 100.0,
        "ctMult": 1.0,
        "ctValCcy": "HOME",
    }
    levels = [
        ["0.015", "300"],
        ["0.014", "200"],
    ]

    depth = fc._calculate_orderbook_depth_usdt(levels, instrument_info, inst_id="HOME-USDT-SWAP")

    assert depth == 730.0


def test_get_cointegrated_pairs_caches_orderbook_by_ticker(monkeypatch):
    calls: list[str] = []

    def fake_get_orderbook(instId: str, sz: int = 50):
        calls.append(instId)
        levels = [["10", "5", "0", "1"]] * 10
        return {"code": "0", "data": [{"bids": levels, "asks": levels}]}

    json_symbols = {
        "AAA-USDT-SWAP": _build_symbol("AAA-USDT-SWAP", [10.0, 10.1, 10.2, 10.3], ct_val=100.0),
        "BBB-USDT-SWAP": _build_symbol("BBB-USDT-SWAP", [11.0, 11.1, 11.2, 11.3], ct_val=100.0),
        "CCC-USDT-SWAP": _build_symbol("CCC-USDT-SWAP", [12.0, 12.1, 12.2, 12.3], ct_val=100.0),
    }

    monkeypatch.setattr(
        fc,
        "calculate_cointegration_from_log",
        lambda *_args, **_kwargs: (1, 0.001, -4.0, -3.0, 1.0, 5),
    )
    monkeypatch.setattr(fc, "_load_restricted_tickers", lambda: set())
    monkeypatch.setattr(fc, "market_session", SimpleNamespace(get_orderbook=fake_get_orderbook))
    monkeypatch.setattr(fc, "min_orderbook_levels", 10)
    monkeypatch.setattr(fc, "min_orderbook_depth_usdt", 1000.0)

    df, summary = fc.get_cointegrated_pairs(
        json_symbols,
        corr_min_override=0.0,
        min_p_value_override=0.0,
        max_p_value_override=0.01,
        min_zero_crossings_override=1,
    )

    assert len(df) == 3
    assert summary["pairs_kept"] == 3
    assert calls.count("AAA-USDT-SWAP") == 1
    assert calls.count("BBB-USDT-SWAP") == 1
    assert calls.count("CCC-USDT-SWAP") == 1


def test_pair_supply_caps_canonical_pairs_at_configured_max(monkeypatch, tmp_path):
    def fake_get_orderbook(instId: str, sz: int = 50):
        levels = [["100", "100", "0", "1"]] * 10
        return {"code": "0", "data": [{"bids": levels, "asks": levels}]}

    json_symbols = {
        f"SYM{idx}-USDT-SWAP": _build_symbol(
            f"SYM{idx}-USDT-SWAP",
            [10.0 + idx, 10.1 + idx, 10.2 + idx, 10.3 + idx],
            ct_val=1.0,
        )
        for idx in range(6)
    }

    monkeypatch.setattr(
        fc,
        "calculate_cointegration_from_log",
        lambda *_args, **_kwargs: (1, 0.001, -4.0, -3.0, 1.0, 5),
    )
    monkeypatch.setattr(fc, "_load_restricted_tickers", lambda: set())
    monkeypatch.setattr(fc, "market_session", SimpleNamespace(get_orderbook=fake_get_orderbook))
    monkeypatch.setattr(fc, "min_orderbook_levels", 7)
    monkeypatch.setattr(fc, "min_orderbook_depth_usdt", 1000.0)
    monkeypatch.setattr(fc, "max_supply_pairs", 10)

    df, summary = fc.get_cointegrated_pairs(
        json_symbols,
        corr_min_override=0.0,
        min_p_value_override=0.0,
        max_p_value_override=0.01,
        min_zero_crossings_override=1,
    )
    output_path = Path(fc.__file__).resolve().parent / "output" / "2_cointegrated_pairs.csv"
    canonical = pd.read_csv(output_path)

    assert len(df) == 10
    assert len(canonical) == 10
    assert summary["pairs_kept"] == 10
    assert summary["max_supply_pairs"] == 10
    assert summary["filtered_breakdown"]["supply_cap"] == 5
    assert summary["pre_filter_pairs_with_crossings"] == 15
    assert summary["usable_pairs_with_crossings"] == 10
    assert summary["crossing_candidates_filtered_later"] == 5

    status_path = Path(fc.__file__).resolve().parent / "output" / "2_cointegrated_pairs_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["pre_filter_pairs_with_crossings"] == 15
    assert status["usable_pairs_with_crossings"] == 10
    assert status["scan_summary"]["usable_pairs_with_crossings"] == 10


def test_orderbook_soft_pass_accepts_slightly_low_balanced_depth(monkeypatch):
    calls: list[str] = []

    def fake_get_orderbook(instId: str, sz: int = 50):
        calls.append(instId)
        levels = [["100", "10", "0", "1"]] * 7  # 7,000 USDT per side with ctVal=1.
        return {"code": "0", "data": [{"bids": levels, "asks": levels}]}

    json_symbols = {
        "AAA-USDT-SWAP": _build_symbol("AAA-USDT-SWAP", [10.0, 10.1, 10.2, 10.3], ct_val=1.0),
        "BBB-USDT-SWAP": _build_symbol("BBB-USDT-SWAP", [11.0, 11.1, 11.2, 11.3], ct_val=1.0),
    }

    monkeypatch.setattr(
        fc,
        "calculate_cointegration_from_log",
        lambda *_args, **_kwargs: (1, 0.001, -4.0, -3.0, 1.0, 5),
    )
    monkeypatch.setattr(fc, "_load_restricted_tickers", lambda: set())
    monkeypatch.setattr(fc, "market_session", SimpleNamespace(get_orderbook=fake_get_orderbook))
    monkeypatch.setattr(fc, "min_orderbook_levels", 7)
    monkeypatch.setattr(fc, "min_orderbook_depth_usdt", 8000.0)
    monkeypatch.setattr(fc, "soft_orderbook_depth_usdt", 6000.0)
    monkeypatch.setattr(fc, "max_orderbook_imbalance", 12.0)

    df, summary = fc.get_cointegrated_pairs(
        json_symbols,
        corr_min_override=0.0,
        min_p_value_override=0.0,
        max_p_value_override=0.01,
        min_zero_crossings_override=1,
    )

    assert len(df) == 1
    assert summary["pairs_kept"] == 1
    assert summary["orderbook_soft_pass_tickers"] == 2
    assert calls.count("AAA-USDT-SWAP") == 1
    assert calls.count("BBB-USDT-SWAP") == 1


def test_orderbook_soft_pass_rejects_excessive_imbalance(monkeypatch):
    def fake_get_orderbook(instId: str, sz: int = 50):
        bids = [["100", "100", "0", "1"]] * 7  # 70,000 USDT
        asks = [["100", "10", "0", "1"]] * 7   # 7,000 USDT
        return {"code": "0", "data": [{"bids": bids, "asks": asks}]}

    json_symbols = {
        "AAA-USDT-SWAP": _build_symbol("AAA-USDT-SWAP", [10.0, 10.1, 10.2, 10.3], ct_val=1.0),
        "BBB-USDT-SWAP": _build_symbol("BBB-USDT-SWAP", [11.0, 11.1, 11.2, 11.3], ct_val=1.0),
    }

    monkeypatch.setattr(
        fc,
        "calculate_cointegration_from_log",
        lambda *_args, **_kwargs: (1, 0.001, -4.0, -3.0, 1.0, 5),
    )
    monkeypatch.setattr(fc, "_load_restricted_tickers", lambda: set())
    monkeypatch.setattr(fc, "market_session", SimpleNamespace(get_orderbook=fake_get_orderbook))
    monkeypatch.setattr(fc, "min_orderbook_levels", 7)
    monkeypatch.setattr(fc, "min_orderbook_depth_usdt", 8000.0)
    monkeypatch.setattr(fc, "soft_orderbook_depth_usdt", 6000.0)
    monkeypatch.setattr(fc, "max_orderbook_imbalance", 8.0)

    df, summary = fc.get_cointegrated_pairs(
        json_symbols,
        corr_min_override=0.0,
        min_p_value_override=0.0,
        max_p_value_override=0.01,
        min_zero_crossings_override=1,
    )

    assert len(df) == 0
    assert summary["pairs_kept"] == 0
    assert summary["filtered_breakdown"]["orderbook_depth"] == 1


def test_order_capacity_filter_rejects_tiny_okx_max_order_symbols(monkeypatch):
    def fake_get_orderbook(instId: str, sz: int = 50):
        levels = [["100", "100", "0", "1"]] * 7
        return {"code": "0", "data": [{"bids": levels, "asks": levels}]}

    tiny = _build_symbol("TINY-USDT-SWAP", [0.026, 0.027, 0.0265, 0.0272], ct_val=1.0)
    tiny["symbol_info"]["maxMktSz"] = 100.0
    tiny["symbol_info"]["maxStopSz"] = 100.0
    json_symbols = {
        "TINY-USDT-SWAP": tiny,
        "AAA-USDT-SWAP": _build_symbol("AAA-USDT-SWAP", [10.0, 10.1, 10.2, 10.3], ct_val=1.0),
    }

    monkeypatch.setattr(
        fc,
        "calculate_cointegration_from_log",
        lambda *_args, **_kwargs: (1, 0.001, -4.0, -3.0, 1.0, 5),
    )
    monkeypatch.setattr(fc, "_load_restricted_tickers", lambda: set())
    monkeypatch.setattr(fc, "market_session", SimpleNamespace(get_orderbook=fake_get_orderbook))
    monkeypatch.setattr(fc, "min_order_capacity_usdt", 50.0)
    monkeypatch.setattr(fc, "min_orderbook_levels", 7)
    monkeypatch.setattr(fc, "min_orderbook_depth_usdt", 1000.0)

    df, summary = fc.get_cointegrated_pairs(
        json_symbols,
        corr_min_override=0.0,
        min_p_value_override=0.0,
        max_p_value_override=0.01,
        min_zero_crossings_override=1,
    )

    assert len(df) == 0
    assert summary["pairs_kept"] == 0
    assert summary["filtered_breakdown"]["order_capacity"] == 1


def test_cointegrated_pairs_writer_preserves_last_good_csv_on_empty_scan(tmp_path):
    output_path = tmp_path / "2_cointegrated_pairs.csv"
    previous = pd.DataFrame([{"sym_1": "AAA-USDT-SWAP", "sym_2": "BBB-USDT-SWAP", "zero_crossing": 9}])
    previous.to_csv(output_path, index=False)

    empty_attempt = pd.DataFrame(columns=["sym_1", "sym_2", "zero_crossing"])
    status = fc._write_cointegrated_pairs_csv(empty_attempt, output_path)
    preserved = pd.read_csv(output_path)
    latest_attempt = pd.read_csv(tmp_path / "2_cointegrated_pairs_latest_attempt.csv")

    assert status["canonical_updated"] is False
    assert status["preserved_existing"] is True
    assert len(preserved) == 1
    assert preserved.iloc[0]["sym_1"] == "AAA-USDT-SWAP"
    assert latest_attempt.empty


def test_cointegrated_pairs_writer_accumulates_non_empty_scans(tmp_path):
    output_path = tmp_path / "2_cointegrated_pairs.csv"
    previous = pd.DataFrame(
        [
            {"sym_1": "AAA-USDT-SWAP", "sym_2": "BBB-USDT-SWAP", "p_value": 0.01, "zero_crossing": 9},
            {"sym_1": "CCC-USDT-SWAP", "sym_2": "DDD-USDT-SWAP", "p_value": 0.02, "zero_crossing": 3},
        ]
    )
    previous.to_csv(output_path, index=False)
    latest = pd.DataFrame(
        [
            {"sym_1": "DDD-USDT-SWAP", "sym_2": "CCC-USDT-SWAP", "p_value": 0.003, "zero_crossing": 10},
            {"sym_1": "EEE-USDT-SWAP", "sym_2": "FFF-USDT-SWAP", "p_value": 0.004, "zero_crossing": 8},
        ]
    )

    status = fc._write_cointegrated_pairs_csv(latest, output_path, max_rows=3)
    canonical = pd.read_csv(output_path)
    latest_attempt = pd.read_csv(tmp_path / "2_cointegrated_pairs_latest_attempt.csv")

    assert len(latest_attempt) == 2
    assert len(canonical) == 3
    assert canonical.iloc[0]["sym_1"] == "DDD-USDT-SWAP"
    assert canonical.iloc[0]["sym_2"] == "CCC-USDT-SWAP"
    assert canonical.iloc[0]["zero_crossing"] == 10
    assert set(canonical["sym_1"]) == {"AAA-USDT-SWAP", "DDD-USDT-SWAP", "EEE-USDT-SWAP"}
    assert status["canonical_updated"] is True
    assert status["accumulated_supply"] is True
    assert status["previous_canonical_rows"] == 2
    assert status["latest_attempt_rows"] == 2
    assert status["latest_attempt_valid_rows"] == 2
    assert status["accumulated_pairs_added"] == 1
    assert status["accumulated_pairs_refreshed"] == 1
    assert status["accumulated_pairs_retained"] == 1
    assert status["accumulation_cap_filtered"] == 0


def test_cointegrated_pairs_writer_caps_accumulated_supply(tmp_path):
    output_path = tmp_path / "2_cointegrated_pairs.csv"
    previous = pd.DataFrame(
        [
            {"sym_1": "AAA-USDT-SWAP", "sym_2": "BBB-USDT-SWAP", "p_value": 0.01, "zero_crossing": 9},
            {"sym_1": "CCC-USDT-SWAP", "sym_2": "DDD-USDT-SWAP", "p_value": 0.02, "zero_crossing": 3},
        ]
    )
    previous.to_csv(output_path, index=False)
    latest = pd.DataFrame(
        [{"sym_1": "EEE-USDT-SWAP", "sym_2": "FFF-USDT-SWAP", "p_value": 0.004, "zero_crossing": 8}]
    )

    status = fc._write_cointegrated_pairs_csv(latest, output_path, max_rows=2)
    canonical = pd.read_csv(output_path)

    assert len(canonical) == 2
    assert list(canonical["sym_1"]) == ["AAA-USDT-SWAP", "EEE-USDT-SWAP"]
    assert status["accumulation_cap_filtered"] == 1
