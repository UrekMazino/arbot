# Check order items
from func_position_calls import query_existing_order, get_open_positions, get_active_positions
from func_fill_logging import log_order_fills


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_status(value):
    return str(value).strip().lower() if value is not None else ""


def check_order(ticker, order_id, remaining_capital, direction="Long", remaining_unit="quote"):
    # Get existing order
    order_price, order_quantity, order_status = query_existing_order(
        order_id,
        inst_id=ticker,
        direction=direction,
    )
    if order_status is None and direction is None:
        order_price, order_quantity, order_status = query_existing_order(
            order_id,
            inst_id=ticker,
        )

    # Get an open position
    position_price, position_quantity = get_open_positions(ticker, direction=direction)

    # Get active orders (fallback if status missing)
    _active_order_price, active_order_quantity = get_active_positions(ticker, order_id=order_id)

    # Determine action - trade complete - stop placing orders
    position_qty_val = _safe_float(position_quantity)
    remaining_val = _safe_float(remaining_capital)
    position_price_val = _safe_float(position_price)
    remaining_unit_norm = _normalize_status(remaining_unit)
    if remaining_val is not None and position_qty_val is not None:
        if remaining_unit_norm in ("base", "qty", "quantity"):
            if position_qty_val >= remaining_val and position_qty_val > 0:
                log_order_fills(order_id, ticker)
                return "Trade Complete"
        elif remaining_unit_norm in ("quote", "notional", "usdt", "usd"):
            if position_price_val is not None:
                if position_qty_val * position_price_val >= remaining_val and position_qty_val > 0:
                    log_order_fills(order_id, ticker)
                    return "Trade Complete"

    # Normalize status for OKX values
    status_norm = _normalize_status(order_status)

    # Determine action - position filled - buy more
    if status_norm == "filled":
        log_order_fills(order_id, ticker)
        return "Position Filled"

    # Determine action - order active - do nothing
    active_items = {"live", "created", "new"}
    if status_norm in active_items:
        return "Order Active"

    # Determine action - partial filled order - do nothing
    if status_norm == "partially_filled":
        return "Partial Fill"

    # Determine action - order failed - try place order again
    cancel_items = {"canceled", "cancelled", "rejected", "pending_cancel", "order_failed", "failed"}
    if status_norm in cancel_items:
        return "Try Again"

    # Fallback on active order data
    if active_order_quantity is not None:
        return "Order Active"

    return "Try Again"
