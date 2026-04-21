import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from func_execution_calls import initialise_order_execution, preview_entry_details


SPK_INFO = {
    "instId": "SPK-USDT-SWAP",
    "ctVal": "1",
    "ctMult": "1",
    "ctValCcy": "SPK",
    "lotSz": "1",
    "minSz": "1",
    "maxMktSz": "100",
    "maxLmtSz": "100000",
    "maxStopSz": "100",
}

SPK_ORDERBOOK = {
    "arg": {"channel": "books", "instId": "SPK-USDT-SWAP"},
    "data": [{
        "bids": [["0.02675", "1000"]],
        "asks": [["0.02675", "1000"]],
    }],
}


def test_preview_rejects_quantity_above_market_and_stop_max_size():
    result = preview_entry_details(
        "SPK-USDT-SWAP",
        "sell",
        210.0,
        orderbook_payload=SPK_ORDERBOOK,
        instrument_info=SPK_INFO,
    )

    assert result["ok"] is False
    assert result["size_limit_ok"] is False
    assert result["max_order_size"] == 100.0
    assert result["max_stop_size"] == 100.0
    assert "maxMktSz" in result["error"]
    assert "maxStopSz" in result["error"]


def test_preview_accepts_quantity_within_market_and_stop_max_size():
    result = preview_entry_details(
        "SPK-USDT-SWAP",
        "sell",
        2.0,
        orderbook_payload=SPK_ORDERBOOK,
        instrument_info=SPK_INFO,
    )

    assert result["ok"] is True
    assert result["size_limit_ok"] is True
    assert result["quantity"] <= 100.0


def test_initialise_order_execution_rejects_before_dry_run_order_when_size_too_large():
    result = initialise_order_execution(
        ticker="SPK-USDT-SWAP",
        direction="sell",
        capital=210.0,
        orderbook_payload=SPK_ORDERBOOK,
        dry_run_override=True,
        instrument_info=SPK_INFO,
    )

    assert result is not None
    assert result["ok"] is False
    assert result["entry"] is None
    assert result["entry_id"] == ""
    assert "maxMktSz" in result["error"]
