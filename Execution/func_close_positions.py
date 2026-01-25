import logging

from config_execution_api import account_session, trade_session, inst_type, ticker_1, ticker_2, td_mode

logger = logging.getLogger(__name__)


def get_position_info(ticker, session=None):
    """
    Fetch current position size and side for a given instrument.

    Returns:
        tuple: (size, side) where side is "Buy" (Long) or "Sell" (Short); (0.0, "") if no open position.
    """
    active_session = session or account_session

    try:
        response = active_session.get_positions(instType=inst_type, instId=ticker)
    except Exception as exc:
        logger.error(f"Failed to fetch positions for {ticker}: {exc}")
        return 0.0, ""

    if response.get("code") != "0":
        logger.error(f"OKX position query failed for {ticker}: {response.get('msg')}")
        return 0.0, ""

    positions = response.get("data", [])
    if not positions:
        return 0.0, ""

    # Note: If in Hedge mode, OKX might return two positions (Long and Short).
    # This function currently returns the first non-zero position found.
    for position in positions:
        pos_str = position.get("pos", "0")
        try:
            size = float(pos_str)
        except (TypeError, ValueError):
            continue

        if size == 0:
            continue

        pos_side = str(position.get("posSide", "")).lower()
        
        # Explicit mapping based on OKX posSide field
        if pos_side == "long":
            return abs(size), "Buy"
        if pos_side == "short":
            return abs(size), "Sell"

        # Fallback to net position side if posSide is net or missing
        if size > 0:
            return size, "Buy"
        
        return abs(size), "Sell"

    return 0.0, ""

# Place market close order
def place_market_close_order(ticker, size, side):
    """
    Close a position using a market order.
    
    Args:
        ticker (str): Instrument ID.
        size (float): Quantity to close.
        side (str): Current position side ("Buy" or "Sell").
    """
    try:
        # Determine the order side to close the position
        # If we are "Buy" (Long), we must "sell" to close.
        # If we are "Sell" (Short), we must "buy" to close.
        order_side = "sell" if side == "Buy" else "buy"
        
        # Determine the posSide for Hedge Mode (long/short)
        # OKX needs this to know which side to reduce.
        pos_side = "long" if side == "Buy" else "short"

        response = trade_session.place_order(
            instId=ticker,
            tdMode=td_mode,
            side=order_side,
            posSide=pos_side,
            ordType="market",
            sz=str(size),
            reduceOnly=True
        )

        # OKX returns code "0" for successful request handling.
        # For certainty, we check if 'data' contains an 'ordId'.
        code = response.get("code")
        msg = response.get("msg")
        data_list = response.get("data", [])
        order_data = data_list[0] if data_list else {}
        ord_id = order_data.get("ordId")

        if code == "0" and ord_id:
            logger.info(f"Successfully placed market close order for {ticker}: {size} {order_side}. Order ID: {ord_id}")
            return response
        
        # Detailed error extraction
        s_code = order_data.get("sCode")
        s_msg = order_data.get("sMsg")
        
        final_msg = s_msg if s_msg else msg
        final_code = s_code if s_code else code
        
        logger.error(f"Market close order failed for {ticker} (Code: {final_code}): {final_msg}")
        return response

    except Exception as exc:
        logger.error(f"Error placing market close order for {ticker}: {exc}")
        return None


# Close all positions for both tickers
def close_all_positions(kill_switch):
    """
    Cancel all open orders and close all positions for ticker_1 and ticker_2.
    """
    # Cancel all active orders for both tickers
    for ticker in [ticker_1, ticker_2]:
        try:
            # Fetch open orders (incomplete orders)
            response = trade_session.get_order_list(instId=ticker)
            if response.get("code") == "0":
                orders = response.get("data", [])
                if orders:
                    # Prepare batch cancellation list
                    cancel_reqs = [{"instId": ticker, "ordId": o["ordId"]} for o in orders]
                    
                    # OKX cancel_multiple_orders allows up to 20 per request
                    for i in range(0, len(cancel_reqs), 20):
                        batch = cancel_reqs[i:i+20]
                        trade_session.cancel_multiple_orders(batch)
                        logger.info(f"Cancelled {len(batch)} orders for {ticker}")
                else:
                    logger.debug(f"No open orders to cancel for {ticker}.")
            else:
                logger.error(f"Failed to fetch open orders for {ticker}: {response.get('msg')}")
        except Exception as exc:
            logger.error(f"Error cancelling orders for {ticker}: {exc}")

    # Get position information
    size_1, side_1 = get_position_info(ticker_1)
    size_2, side_2 = get_position_info(ticker_2)

    if size_1 > 0:
        logger.info(f"Closing position for {ticker_1}: {size_1} {side_1}")
        place_market_close_order(ticker_1, size_1, side_1)

    if size_2 > 0:
        logger.info(f"Closing position for {ticker_2}: {size_2} {side_2}")
        place_market_close_order(ticker_2, size_2, side_2)

    # Output result
    kill_switch = 0
    return kill_switch
