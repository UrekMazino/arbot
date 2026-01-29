import logging
from config_execution_api import (
    stop_loss_fail_safe,
    ticker_1,
    ticker_2,
    rounding_ticker_1,
    rounding_ticker_2,
    quantity_rounding_ticker_1,
    quantity_rounding_ticker_2,
)

logger = logging.getLogger(__name__)

# Fee/slippage buffer: OKX taker ~0.05% + slippage ~0.02% = 0.07% round-trip
FEE_SLIPPAGE_BUFFER_PCT = 0.0007


def _extract_symbol(orderbook_data):
    """Extract instrument ID from orderbook payload."""
    if not orderbook_data or not isinstance(orderbook_data, dict):
        return ""

    arg = orderbook_data.get("arg")
    if isinstance(arg, dict):
        inst_id = arg.get("instId")
        if inst_id:
            return inst_id

    return orderbook_data.get("instId") or orderbook_data.get("s", "")


def _extract_sides(orderbook_data):
    """Extract bids and asks from orderbook payload."""
    if not orderbook_data or not isinstance(orderbook_data, dict):
        return [], []

    data = orderbook_data.get("data")
    book = data[0] if isinstance(data, list) and data else orderbook_data

    bids = book.get("bids") or book.get("b") or []
    asks = book.get("asks") or book.get("a") or []
    return bids, asks


def _extract_prices(levels):
    """Extract price values from orderbook levels."""
    prices = []
    for level in levels:
        if not level:
            continue
        price = level[0] if isinstance(level, (list, tuple)) else level
        try:
            prices.append(float(price))
        except (TypeError, ValueError):
            continue
    return prices


def _parse_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_quote_ccy(inst_id):
    if not inst_id:
        return ""
    parts = str(inst_id).split("-")
    if len(parts) >= 2:
        return parts[1].upper()
    return ""


def _resolve_contract_value_quote(entry_price, instrument_info=None, inst_id=""):
    if not instrument_info:
        return 0.0
    ct_val = _parse_float(instrument_info.get("ctVal"), 0.0)
    ct_mult = _parse_float(instrument_info.get("ctMult"), 1.0)
    if ct_mult == 0:
        ct_mult = 1.0
    if ct_val <= 0 or entry_price <= 0:
        return 0.0
    ct_val_ccy = str(instrument_info.get("ctValCcy") or "").upper()
    quote_ccy = _parse_quote_ccy(inst_id or instrument_info.get("instId", ""))
    contract_units = ct_val * ct_mult
    if ct_val_ccy and quote_ccy and ct_val_ccy == quote_ccy:
        return contract_units
    return entry_price * contract_units


def get_contract_value_quote(entry_price, instrument_info=None, inst_id=""):
    return _resolve_contract_value_quote(entry_price, instrument_info, inst_id)


def get_trade_details(orderbook_data, direction="Long", capital=0.0, instrument_info=None):
    """
    Calculate trade details from OKX orderbook data.

    Args:
        orderbook_data (dict): OKX WS payload or dict with bids/asks.
        direction (str): "Long" or "Short".
        capital (float): USDT amount to trade.
        instrument_info (dict): OKX instrument details for contract sizing.

    Returns:
        tuple: (entry_price, quantity, stop_loss)
    """
    entry_price = 0.0
    quantity = 0.0
    stop_loss = 0.0

    bids, asks = _extract_sides(orderbook_data)
    if not bids or not asks:
        # Issue #12 Fix: Add symbol, direction, and capital context for better debugging
        symbol = _extract_symbol(orderbook_data)
        logger.warning(f"❌ No bids or asks in orderbook: symbol={symbol}, direction={direction}, capital={capital:.2f} USDT")
        return entry_price, quantity, stop_loss

    symbol = _extract_symbol(orderbook_data)
    if instrument_info and not symbol:
        symbol = instrument_info.get("instId") or ""
    
    # Logic: determine rounding parameters
    if symbol == ticker_1:
        price_roundings = rounding_ticker_1
        quantity_roundings = quantity_rounding_ticker_1
    elif symbol == ticker_2:
        price_roundings = rounding_ticker_2
        quantity_roundings = quantity_rounding_ticker_2
    else:
        # Default fallback or handle as error
        logger.debug(f"Symbol {symbol} not matched in config; using default (2).")
        price_roundings = 2
        quantity_roundings = 2

    bid_prices = _extract_prices(bids)
    ask_prices = _extract_prices(asks)
    
    if not bid_prices or not ask_prices:
        # Issue #12 Fix: Add direction and capital context to price extraction error
        logger.warning(f"❌ Could not extract prices: symbol={symbol}, direction={direction}, capital={capital:.2f} USDT, bid_count={len(bid_prices)}, ask_count={len(ask_prices)}")
        return entry_price, quantity, stop_loss

    # Maker strategy: Buy at bid, Sell at ask
    best_bid = max(bid_prices)
    best_ask = min(ask_prices)

    if direction.lower() == "long":
        # For LONG: add fee buffer to entry price (worse entry, better safety)
        # This accounts for taker fee (0.05%) + slippage (0.02%) = 0.07%
        entry_price = best_bid * (1 + FEE_SLIPPAGE_BUFFER_PCT)
        stop_loss = round(entry_price * (1 - stop_loss_fail_safe), price_roundings)
        logger.debug(
            "Long entry fee buffer applied: %.2f -> %.2f (+%.3f%%)",
            best_bid,
            entry_price,
            FEE_SLIPPAGE_BUFFER_PCT * 100,
        )
    else:
        # For SHORT: subtract fee buffer from entry price (worse entry, better safety)
        entry_price = best_ask * (1 - FEE_SLIPPAGE_BUFFER_PCT)
        stop_loss = round(entry_price * (1 + stop_loss_fail_safe), price_roundings)
        logger.debug(
            "Short entry fee buffer applied: %.2f -> %.2f (-%.3f%%)",
            best_ask,
            entry_price,
            FEE_SLIPPAGE_BUFFER_PCT * 100,
        )

    if entry_price > 0:
        contract_value_quote = _resolve_contract_value_quote(entry_price, instrument_info, symbol)
        if contract_value_quote > 0:
            raw_quantity = capital / contract_value_quote
        else:
            if instrument_info:
                logger.warning(
                    "Contract value unavailable for sizing: symbol=%s entry_price=%.6f",
                    symbol,
                    entry_price,
                )
            raw_quantity = capital / entry_price
        quantity = round(raw_quantity, quantity_roundings)
        
        # Best Practice: For Swaps, quantity must often be an integer.
        # If quantity_roundings is 0, it will be an integer.
        if quantity_roundings == 0:
            quantity = int(quantity)

    return entry_price, quantity, stop_loss
