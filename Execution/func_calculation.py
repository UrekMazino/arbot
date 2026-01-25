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


def get_trade_details(orderbook_data, direction="Long", capital=0.0):
    """
    Calculate trade details from OKX orderbook data.

    Args:
        orderbook_data (dict): OKX WS payload or dict with bids/asks.
        direction (str): "Long" or "Short".
        capital (float): USDT amount to trade.

    Returns:
        tuple: (entry_price, quantity, stop_loss)
    """
    entry_price = 0.0
    quantity = 0.0
    stop_loss = 0.0

    bids, asks = _extract_sides(orderbook_data)
    if not bids or not asks:
        logger.warning("No bids or asks found in orderbook data.")
        return entry_price, quantity, stop_loss

    symbol = _extract_symbol(orderbook_data)
    
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
        logger.warning(f"Could not extract prices for {symbol}.")
        return entry_price, quantity, stop_loss

    # Maker strategy: Buy at bid, Sell at ask
    best_bid = max(bid_prices)
    best_ask = min(ask_prices)

    if direction.lower() == "long":
        entry_price = best_bid
        stop_loss = round(entry_price * (1 - stop_loss_fail_safe), price_roundings)
    else:
        entry_price = best_ask
        stop_loss = round(entry_price * (1 + stop_loss_fail_safe), price_roundings)

    if entry_price > 0:
        # Note: For OKX SWAP, sz is usually number of contracts. 
        # If capital is in USDT, quantity should be: capital / (entry_price * contract_value)
        # This implementation assumes capital / entry_price is the desired unit.
        raw_quantity = capital / entry_price
        quantity = round(raw_quantity, quantity_roundings)
        
        # Best Practice: For Swaps, quantity must often be an integer.
        # If quantity_roundings is 0, it will be an integer.
        if quantity_roundings == 0:
            quantity = int(quantity)

    return entry_price, quantity, stop_loss
