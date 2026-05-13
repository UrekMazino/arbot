import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

import func_calculation
import func_close_positions
import func_execution_calls
import func_trade_management


SHIB_INFO = {
    "instId": "SHIB-USDT-SWAP",
    "ctVal": "1000000",
    "ctMult": "1",
    "ctValCcy": "SHIB",
    "lotSz": "0.1",
    "minSz": "0.1",
    "maxMktSz": "35000.5",
    "maxLmtSz": "35000.5",
    "maxStopSz": "35000.5",
    "tickSz": "0.000001",
}

SHIB_ORDERBOOK = {
    "arg": {"channel": "books", "instId": "SHIB-USDT-SWAP"},
    "data": [{
        "bids": [["0.00000626", "100000"]],
        "asks": [["0.00000627", "100000"]],
    }],
}


def _patch_shib_rounding(monkeypatch):
    monkeypatch.setattr(func_calculation, "ticker_1", "SHIB-USDT-SWAP")
    monkeypatch.setattr(func_calculation, "rounding_ticker_1", 8)
    monkeypatch.setattr(func_calculation, "quantity_rounding_ticker_1", 1)


def test_small_price_stop_trigger_rounds_to_tick_and_remains_valid():
    result = func_execution_calls.validate_stop_trigger_price(
        "SHIB-USDT-SWAP",
        "sell",
        0.000006264382,
        0.00000608,
        instrument_info=SHIB_INFO,
    )

    assert result["valid"] is True
    assert result["rounded_trigger_px"] == "0.000006"
    assert float(result["rounded_trigger_px"]) > 0


def test_invalid_stop_trigger_blocks_entry_preflight(monkeypatch):
    _patch_shib_rounding(monkeypatch)
    info = dict(SHIB_INFO, tickSz="0.00001")

    def fail_if_called(*args, **kwargs):
        raise AssertionError("entry order should not be placed after stop preflight failure")

    monkeypatch.setattr(func_execution_calls, "place_market_order", fail_if_called)
    result = func_execution_calls.initialise_order_execution(
        ticker="SHIB-USDT-SWAP",
        direction="long",
        capital=750.0,
        orderbook_payload=SHIB_ORDERBOOK,
        dry_run_override=True,
        instrument_info=info,
    )

    assert result is not None
    assert result["ok"] is False
    assert result["entry"] is None
    assert result["error_type"] == "stop_loss_preflight_failed"
    assert "rounded_trigger_not_positive" in result["error"]


def test_post_fill_stop_validation_failure_triggers_emergency_close(monkeypatch):
    _patch_shib_rounding(monkeypatch)
    calls = {"validation": 0, "emergency": 0}

    def fake_validate(*args, **kwargs):
        calls["validation"] += 1
        if calls["validation"] == 1:
            return {"valid": True, "rounded_trigger_px": "0.000006", "reason": None, "metadata": {}}
        return {"valid": False, "rounded_trigger_px": None, "reason": "invalid_after_fill", "metadata": {}}

    monkeypatch.setattr(func_execution_calls, "validate_stop_trigger_price", fake_validate)
    monkeypatch.setattr(
        func_execution_calls,
        "place_market_order",
        lambda *args, **kwargs: {"code": "0", "data": [{"ordId": "ENTRY1", "sCode": "0"}]},
    )
    monkeypatch.setattr(
        func_execution_calls,
        "place_stop_loss_order",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("stop order should not be submitted")),
    )

    result = func_execution_calls.initialise_order_execution(
        ticker="SHIB-USDT-SWAP",
        direction="long",
        capital=750.0,
        orderbook_payload=SHIB_ORDERBOOK,
        dry_run_override=True,
        instrument_info=SHIB_INFO,
    )

    assert result["ok"] is False
    assert result["entry_id"] == "ENTRY1"
    assert result["error_type"] == "stop_loss_post_fill_validation_failed"

    monkeypatch.setattr(func_trade_management, "_emergency_close_tickers", lambda *args, **kwargs: calls.__setitem__("emergency", calls["emergency"] + 1) or 0)
    handled, kill_switch = func_trade_management._close_placed_entry_after_setup_failure(
        "Long",
        "SHIB-USDT-SWAP",
        result,
        "long_entry_setup_failed",
        0,
    )

    assert handled is True
    assert kill_switch == 0
    assert calls["emergency"] == 1


def test_emergency_close_partial_fill_does_not_assume_flat(monkeypatch):
    monkeypatch.setattr(func_close_positions, "emergency_flatten_verify_enabled", True)
    monkeypatch.setattr(func_close_positions, "emergency_flatten_max_retries", 1)
    monkeypatch.setattr(func_close_positions, "emergency_flatten_poll_seconds", 0.0)
    monkeypatch.setattr(func_close_positions, "emergency_flatten_dust_contracts", 0.0)
    monkeypatch.setattr(
        func_close_positions,
        "close_all_positions",
        lambda *args, **kwargs: {
            "ok": True,
            "kill_switch": 0,
            "tickers": ["SHIB-USDT-SWAP"],
            "cancelled_orders": 0,
            "close_orders": 1,
            "errors": [],
            "close_attempts": [{
                "ticker": "SHIB-USDT-SWAP",
                "requested_qty": 119.7,
                "filled_qty": 71.0,
            }],
        },
    )
    states = [
        {"ok": True, "positions": [{"instId": "SHIB-USDT-SWAP", "pos": "48.7", "posSide": "long"}], "orders": []},
        {"ok": True, "positions": [], "orders": []},
    ]
    monkeypatch.setattr(func_close_positions, "get_account_state", lambda: states.pop(0))
    retry_attempts = []

    def fake_close(ticker, size, side):
        retry_attempts.append((ticker, size, side))
        return {"code": "0", "data": [{"ordId": "RETRY1"}], "fill_summary": {"qty": size}}

    monkeypatch.setattr(func_close_positions, "place_market_close_order", fake_close)

    result = func_close_positions.close_all_positions_and_confirm(tickers=["SHIB-USDT-SWAP"])

    assert result["ok"] is True
    assert result["final_flatten_status"] == "flat"
    assert retry_attempts == [("SHIB-USDT-SWAP", 48.7, "Buy")]


def test_emergency_close_verifies_flat_without_orphan_alert(monkeypatch):
    monkeypatch.setattr(func_close_positions, "emergency_flatten_verify_enabled", True)
    monkeypatch.setattr(func_close_positions, "emergency_flatten_max_retries", 3)
    monkeypatch.setattr(
        func_close_positions,
        "close_all_positions",
        lambda *args, **kwargs: {
            "ok": True,
            "kill_switch": 0,
            "tickers": ["SHIB-USDT-SWAP"],
            "cancelled_orders": 0,
            "close_orders": 1,
            "errors": [],
        },
    )
    monkeypatch.setattr(func_close_positions, "get_account_state", lambda: {"ok": True, "positions": [], "orders": []})

    result = func_close_positions.close_all_positions_and_confirm(tickers=["SHIB-USDT-SWAP"])

    assert result["ok"] is True
    assert result["confirmed_flat"] is True
    assert result["final_flatten_status"] == "flat"
    assert result["blockers"] == []
