"""
Tests for tick-distance-aware stop-loss validation and emergency-flatten
final-state guarantees.

Coverage:
  1.  SHIB-like tiny price / tickSz=0.000001 → fails when distance < 2 ticks
  2.  Normal-priced instrument → passes at 2-tick minimum
  3.  Long direction (sell stop): distance measured below entry
  4.  Short direction (buy stop): distance measured above entry
  5.  Rounded stop that collapses to ≤ 1 tick is rejected before entry
  6.  Post-fill validation catches fill-price / tick issue via place_entry_with_stop
  7.  Emergency flatten emits EMERGENCY_FLATTEN_FLAT on full close
  8.  Emergency flatten emits EMERGENCY_FLATTEN_NOT_FLAT when qty persists
  9.  Entry is blocked before order placement when stop tick-distance fails
 10.  No order-execution behavior change when distance is safely above minimum
"""
from __future__ import annotations

import sys
from pathlib import Path
import logging

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import func_close_positions
import func_execution_calls
import func_calculation

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

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

ETH_INFO = {
    "instId": "ETH-USDT-SWAP",
    "ctVal": "0.01",
    "ctMult": "1",
    "ctValCcy": "ETH",
    "lotSz": "1",
    "minSz": "1",
    "maxMktSz": "5000",
    "maxLmtSz": "5000",
    "maxStopSz": "5000",
    "tickSz": "0.01",
}

SHIB_ORDERBOOK = {
    "arg": {"channel": "books", "instId": "SHIB-USDT-SWAP"},
    "data": [{
        "bids": [["0.00000626", "100000"]],
        "asks": [["0.00000627", "100000"]],
    }],
}

ETH_ORDERBOOK = {
    "arg": {"channel": "books", "instId": "ETH-USDT-SWAP"},
    "data": [{
        "bids": [["2000.00", "50"]],
        "asks": [["2001.00", "50"]],
    }],
}


def _patch_shib(monkeypatch):
    monkeypatch.setattr(func_calculation, "ticker_1", "SHIB-USDT-SWAP")
    monkeypatch.setattr(func_calculation, "rounding_ticker_1", 8)
    monkeypatch.setattr(func_calculation, "quantity_rounding_ticker_1", 1)


def _patch_eth(monkeypatch):
    monkeypatch.setattr(func_calculation, "ticker_1", "ETH-USDT-SWAP")
    monkeypatch.setattr(func_calculation, "rounding_ticker_1", 2)
    monkeypatch.setattr(func_calculation, "quantity_rounding_ticker_1", 0)


# ---------------------------------------------------------------------------
# Test 1: SHIB tiny-price fails when distance < 2 ticks
# ---------------------------------------------------------------------------

def test_shib_stop_too_close_fails_distance_check():
    # SHIB entry ~6.264e-6, stop at 3% below rounds to 6.0e-6 → 0.26 ticks
    result = func_execution_calls.validate_stop_tick_distance(
        "SHIB-USDT-SWAP",
        "sell",
        entry_price=0.000006264382,
        stop_price="0.000006",           # already-rounded stop (1 tick below entry)
        instrument_info=SHIB_INFO,
        min_ticks=2,
    )
    assert result["valid"] is False
    assert result["reason"] == "stop_too_close_in_ticks"
    assert result["distance_ticks"] is not None
    assert result["distance_ticks"] < 2.0
    assert result["min_required_ticks"] == 2


# ---------------------------------------------------------------------------
# Test 2: Normal-priced instrument passes at 2-tick minimum
# ---------------------------------------------------------------------------

def test_normal_price_stop_distance_passes():
    # ETH at $2000, stop at $1940 → distance=$60, tickSz=$0.01 → 6000 ticks
    result = func_execution_calls.validate_stop_tick_distance(
        "ETH-USDT-SWAP",
        "sell",
        entry_price=2000.0,
        stop_price=1940.0,
        instrument_info=ETH_INFO,
        min_ticks=2,
    )
    assert result["valid"] is True
    assert result["distance_ticks"] is not None
    assert result["distance_ticks"] >= 2.0


# ---------------------------------------------------------------------------
# Test 3: Long direction — stop below entry is measured correctly
# ---------------------------------------------------------------------------

def test_long_direction_sell_stop_below_entry():
    # entry=1.000000, stop=0.999998, tickSz=0.000001 → 2 ticks → passes
    result = func_execution_calls.validate_stop_tick_distance(
        "INST-USDT-SWAP",
        "sell",
        entry_price=1.000000,
        stop_price=0.999998,
        instrument_info={"instId": "INST-USDT-SWAP", "tickSz": "0.000001"},
        min_ticks=2,
    )
    assert result["valid"] is True
    assert abs(result["distance_ticks"] - 2.0) < 1e-9


def test_long_direction_sell_stop_only_one_tick_fails():
    # entry=1.000000, stop=0.999999, tickSz=0.000001 → 1 tick → fails
    result = func_execution_calls.validate_stop_tick_distance(
        "INST-USDT-SWAP",
        "sell",
        entry_price=1.000000,
        stop_price=0.999999,
        instrument_info={"instId": "INST-USDT-SWAP", "tickSz": "0.000001"},
        min_ticks=2,
    )
    assert result["valid"] is False
    assert result["reason"] == "stop_too_close_in_ticks"
    assert abs(result["distance_ticks"] - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Test 4: Short direction — stop above entry is measured correctly
# ---------------------------------------------------------------------------

def test_short_direction_buy_stop_above_entry():
    # entry=1.000000, stop=1.000002, tickSz=0.000001 → 2 ticks → passes
    result = func_execution_calls.validate_stop_tick_distance(
        "INST-USDT-SWAP",
        "buy",
        entry_price=1.000000,
        stop_price=1.000002,
        instrument_info={"instId": "INST-USDT-SWAP", "tickSz": "0.000001"},
        min_ticks=2,
    )
    assert result["valid"] is True
    assert abs(result["distance_ticks"] - 2.0) < 1e-9


def test_short_direction_buy_stop_only_one_tick_fails():
    result = func_execution_calls.validate_stop_tick_distance(
        "INST-USDT-SWAP",
        "buy",
        entry_price=1.000000,
        stop_price=1.000001,
        instrument_info={"instId": "INST-USDT-SWAP", "tickSz": "0.000001"},
        min_ticks=2,
    )
    assert result["valid"] is False
    assert result["reason"] == "stop_too_close_in_ticks"


# ---------------------------------------------------------------------------
# Test 5: Rounded stop that collapses to ≤ 1 tick is rejected before entry
# ---------------------------------------------------------------------------

def test_rounded_stop_too_close_blocks_entry(monkeypatch):
    _patch_shib(monkeypatch)
    # Force STATBOT_BLOCK_ENTRY_IF_STOP_INVALID=true (default)
    monkeypatch.delenv("STATBOT_BLOCK_ENTRY_IF_STOP_INVALID", raising=False)
    monkeypatch.setenv("STATBOT_MIN_STOP_DISTANCE_TICKS", "2")

    placed_orders = []

    def fake_market_order(*args, **kwargs):
        placed_orders.append(args)
        raise AssertionError("entry order must not be placed when stop tick-distance fails")

    monkeypatch.setattr(func_execution_calls, "place_market_order", fake_market_order)

    result = func_execution_calls.initialise_order_execution(
        ticker="SHIB-USDT-SWAP",
        direction="long",
        capital=750.0,
        orderbook_payload=SHIB_ORDERBOOK,
        dry_run_override=True,
        instrument_info=SHIB_INFO,
    )

    assert result is not None
    assert result["ok"] is False
    assert result["entry"] is None
    assert result["error_type"] == "stop_loss_tick_distance_failed"
    assert "stop_too_close_in_ticks" in result["error"]
    assert placed_orders == [], "entry order must not be placed"


# ---------------------------------------------------------------------------
# Test 6: Post-fill validation catches fill-price / tick issue
# ---------------------------------------------------------------------------

def test_post_fill_tick_distance_blocks_on_close_fill_price(monkeypatch):
    _patch_shib(monkeypatch)
    monkeypatch.delenv("STATBOT_BLOCK_ENTRY_IF_STOP_INVALID", raising=False)
    monkeypatch.setenv("STATBOT_MIN_STOP_DISTANCE_TICKS", "2")

    call_count = {"n": 0}

    def fake_validate(inst_id, side, ref, trigger, instrument_info=None):
        call_count["n"] += 1
        return {"valid": True, "rounded_trigger_px": "0.000006", "reason": None, "metadata": {}}

    monkeypatch.setattr(func_execution_calls, "validate_stop_trigger_price", fake_validate)

    def fake_tick_dist(inst_id, side, entry_price, stop_price,
                       instrument_info=None, min_ticks=None):
        # preflight (before entry): pass; post-fill: fail
        if call_count["n"] <= 1:
            return {"valid": True, "reason": None, "distance_ticks": 5.0,
                    "min_required_ticks": min_ticks or 2, "tick_size": "0.000001", "metadata": {}}
        return {"valid": False, "reason": "stop_too_close_in_ticks",
                "distance_ticks": 0.26, "min_required_ticks": min_ticks or 2,
                "tick_size": "0.000001", "metadata": {}}

    monkeypatch.setattr(func_execution_calls, "validate_stop_tick_distance", fake_tick_dist)
    monkeypatch.setattr(
        func_execution_calls,
        "place_market_order",
        lambda *a, **kw: {"code": "0", "data": [{"ordId": "ENTRY1", "sCode": "0",
                                                   "avgPx": "0.000006264382"}]},
    )
    stop_placed = []
    monkeypatch.setattr(
        func_execution_calls,
        "place_stop_loss_order",
        lambda *a, **kw: stop_placed.append(1) or {"code": "0"},
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
    assert result["error_type"] == "stop_loss_post_fill_validation_failed"
    assert stop_placed == [], "stop order must not be placed"


# ---------------------------------------------------------------------------
# Test 7: Emergency flatten emits EMERGENCY_FLATTEN_FLAT
# ---------------------------------------------------------------------------

def test_emergency_flatten_emits_flat_log(monkeypatch, caplog):
    monkeypatch.setattr(func_close_positions, "emergency_flatten_verify_enabled", True)
    monkeypatch.setattr(func_close_positions, "emergency_flatten_max_retries", 3)
    monkeypatch.setattr(func_close_positions, "emergency_flatten_poll_seconds", 0.0)
    monkeypatch.setattr(func_close_positions, "emergency_flatten_dust_contracts", 0.0)
    monkeypatch.setattr(
        func_close_positions,
        "close_all_positions",
        lambda *a, **kw: {
            "ok": True, "kill_switch": 0, "tickers": ["SHIB-USDT-SWAP"],
            "cancelled_orders": 0, "close_orders": 1, "errors": [],
        },
    )
    monkeypatch.setattr(
        func_close_positions,
        "get_account_state",
        lambda: {"ok": True, "positions": [], "orders": []},
    )

    with caplog.at_level(logging.INFO, logger="func_close_positions"):
        result = func_close_positions.close_all_positions_and_confirm(
            tickers=["SHIB-USDT-SWAP"]
        )

    assert result["final_flatten_status"] == "flat"
    assert result["confirmed_flat"] is True
    flat_logs = [r for r in caplog.records if "EMERGENCY_FLATTEN_FLAT" in r.message]
    assert flat_logs, "EMERGENCY_FLATTEN_FLAT must be logged"
    assert "retry_count" in flat_logs[0].message
    assert "requested_qty" in flat_logs[0].message
    assert "remaining_qty" in flat_logs[0].message


# ---------------------------------------------------------------------------
# Test 8: Emergency flatten emits EMERGENCY_FLATTEN_NOT_FLAT when qty persists
# ---------------------------------------------------------------------------

def test_emergency_flatten_emits_not_flat_log(monkeypatch, caplog):
    monkeypatch.setattr(func_close_positions, "emergency_flatten_verify_enabled", True)
    monkeypatch.setattr(func_close_positions, "emergency_flatten_max_retries", 1)
    monkeypatch.setattr(func_close_positions, "emergency_flatten_poll_seconds", 0.0)
    monkeypatch.setattr(func_close_positions, "emergency_flatten_dust_contracts", 0.0)
    monkeypatch.setattr(
        func_close_positions,
        "close_all_positions",
        lambda *a, **kw: {
            "ok": True, "kill_switch": 0, "tickers": ["SHIB-USDT-SWAP"],
            "cancelled_orders": 0, "close_orders": 1, "errors": [],
            "close_attempts": [{"ticker": "SHIB-USDT-SWAP",
                                "requested_qty": 119.7, "filled_qty": 71.0}],
        },
    )
    # Position always remains open (flatten never works in this test)
    monkeypatch.setattr(
        func_close_positions,
        "get_account_state",
        lambda: {"ok": True,
                 "positions": [{"instId": "SHIB-USDT-SWAP", "pos": "48.7", "posSide": "long"}],
                 "orders": []},
    )
    monkeypatch.setattr(
        func_close_positions,
        "place_market_close_order",
        lambda ticker, size, side: {"code": "0", "data": [{"ordId": "RETRY1"}]},
    )

    with caplog.at_level(logging.CRITICAL, logger="func_close_positions"):
        result = func_close_positions.close_all_positions_and_confirm(
            tickers=["SHIB-USDT-SWAP"]
        )

    assert result["final_flatten_status"] == "not_flat"
    assert result["confirmed_flat"] is False
    not_flat_logs = [r for r in caplog.records if "EMERGENCY_FLATTEN_NOT_FLAT" in r.message]
    assert not_flat_logs, "EMERGENCY_FLATTEN_NOT_FLAT must be logged"
    msg = not_flat_logs[0].message
    assert "requested_qty" in msg
    assert "remaining_qty" in msg
    assert "final_position_qty" in msg
    assert "open_orders" in msg


# ---------------------------------------------------------------------------
# Test 9: Entry is blocked before placement when stop tick-distance fails
# (end-to-end: no market or stop order placed)
# ---------------------------------------------------------------------------

def test_entry_blocked_before_placement_no_orders_sent(monkeypatch):
    _patch_shib(monkeypatch)
    monkeypatch.setenv("STATBOT_MIN_STOP_DISTANCE_TICKS", "2")
    monkeypatch.delenv("STATBOT_BLOCK_ENTRY_IF_STOP_INVALID", raising=False)

    market_calls = []
    stop_calls = []

    monkeypatch.setattr(
        func_execution_calls, "place_market_order",
        lambda *a, **kw: market_calls.append(kw) or {"code": "0", "data": [{"ordId": "X"}]},
    )
    monkeypatch.setattr(
        func_execution_calls, "place_stop_loss_order",
        lambda *a, **kw: stop_calls.append(kw) or {"code": "0"},
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
    assert result["error_type"] == "stop_loss_tick_distance_failed"
    assert market_calls == [], "entry market order must not be placed"
    assert stop_calls == [], "stop-loss order must not be placed"


# ---------------------------------------------------------------------------
# Test 10: No behavior change for instruments with safe tick distance
# ---------------------------------------------------------------------------

def test_safe_instrument_entry_proceeds_normally(monkeypatch):
    _patch_eth(monkeypatch)
    monkeypatch.setenv("STATBOT_MIN_STOP_DISTANCE_TICKS", "2")
    monkeypatch.delenv("STATBOT_BLOCK_ENTRY_IF_STOP_INVALID", raising=False)

    market_calls = []

    def fake_market(inst_id, side, size, **kw):
        market_calls.append({"inst_id": inst_id, "side": side, "size": size})
        return {"code": "0", "data": [{"ordId": "ENTRY_ETH", "sCode": "0"}]}

    stop_calls = []

    def fake_stop(inst_id, side, size, trigger_price, **kw):
        stop_calls.append({"inst_id": inst_id, "trigger": trigger_price})
        return {"code": "0", "data": [{"algoId": "STOP_ETH"}]}

    monkeypatch.setattr(func_execution_calls, "place_market_order", fake_market)
    monkeypatch.setattr(func_execution_calls, "place_stop_loss_order", fake_stop)

    result = func_execution_calls.initialise_order_execution(
        ticker="ETH-USDT-SWAP",
        direction="long",
        capital=500.0,
        orderbook_payload=ETH_ORDERBOOK,
        dry_run_override=False,
        instrument_info=ETH_INFO,
    )

    assert result["ok"] is True, f"expected ok=True, got error={result.get('error')}"
    assert len(market_calls) == 1
    assert market_calls[0]["inst_id"] == "ETH-USDT-SWAP"
    assert len(stop_calls) == 1
    assert stop_calls[0]["inst_id"] == "ETH-USDT-SWAP"


# ---------------------------------------------------------------------------
# Test 11: validate_stop_tick_distance edge cases
# ---------------------------------------------------------------------------

def test_tick_distance_zero_min_ticks_always_passes():
    result = func_execution_calls.validate_stop_tick_distance(
        "SHIB-USDT-SWAP", "sell",
        entry_price=0.000006264382, stop_price="0.000006",
        instrument_info=SHIB_INFO,
        min_ticks=0,
    )
    assert result["valid"] is True


def test_tick_distance_no_tick_size_always_passes():
    result = func_execution_calls.validate_stop_tick_distance(
        "NOTICK", "sell",
        entry_price=100.0, stop_price=97.0,
        instrument_info={"instId": "NOTICK", "tickSz": "0"},
        min_ticks=2,
    )
    assert result["valid"] is True
    assert result["distance_ticks"] is None


def test_tick_distance_stop_wrong_side_fails():
    # stop above entry for a sell stop (long position) is wrong direction
    result = func_execution_calls.validate_stop_tick_distance(
        "ETH-USDT-SWAP", "sell",
        entry_price=2000.0, stop_price=2050.0,  # above entry!
        instrument_info=ETH_INFO,
        min_ticks=2,
    )
    assert result["valid"] is False
    assert result["reason"] == "stop_wrong_side_of_entry"


def test_tick_distance_env_default_applies(monkeypatch):
    monkeypatch.setenv("STATBOT_MIN_STOP_DISTANCE_TICKS", "5")
    # 3 ticks distance < 5 required → should fail
    result = func_execution_calls.validate_stop_tick_distance(
        "INST", "sell",
        entry_price=1.000003, stop_price=1.000000,
        instrument_info={"instId": "INST", "tickSz": "0.000001"},
        min_ticks=None,   # reads from env
    )
    assert result["valid"] is False
    assert result["min_required_ticks"] == 5
    assert abs(result["distance_ticks"] - 3.0) < 1e-9
