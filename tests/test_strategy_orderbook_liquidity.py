from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_ROOT = ROOT / "Strategy"
if str(STRATEGY_ROOT) not in sys.path:
    sys.path.insert(0, str(STRATEGY_ROOT))

import func_cointegration as fc


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
