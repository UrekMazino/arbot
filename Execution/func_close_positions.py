import logging
import math
import os
import time

from config_execution_api import account_session, trade_session, inst_type, ticker_1, ticker_2, td_mode
from func_fill_logging import log_order_fills
from func_position_calls import get_account_state

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

        if pos_side == "long":
            return abs(size), "Buy"
        if pos_side == "short":
            return abs(size), "Sell"

        if size > 0:
            return size, "Buy"

        return abs(size), "Sell"

    return 0.0, ""


def place_market_close_order(ticker, size, side):
    """
    Close a position using a market order.
    """
    try:
        order_side = "sell" if side == "Buy" else "buy"
        pos_side = "long" if side == "Buy" else "short"

        response = trade_session.place_order(
            instId=ticker,
            tdMode=td_mode,
            side=order_side,
            posSide=pos_side,
            ordType="market",
            sz=str(size),
            reduceOnly=True,
        )

        code = response.get("code")
        msg = response.get("msg")
        data_list = response.get("data", [])
        order_data = data_list[0] if data_list else {}
        ord_id = order_data.get("ordId")

        if code == "0" and ord_id:
            logger.info(f"Successfully placed market close order for {ticker}: {size} {order_side}. Order ID: {ord_id}")
            log_order_fills(ord_id, ticker)
            return response

        s_code = order_data.get("sCode")
        s_msg = order_data.get("sMsg")
        final_msg = s_msg if s_msg else msg
        final_code = s_code if s_code else code

        logger.error(f"Market close order failed for {ticker} (Code: {final_code}): {final_msg}")
        return response

    except Exception as exc:
        logger.error(f"Error placing market close order for {ticker}: {exc}")
        return None


def _safe_float(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _position_side(pos_side, pos_val):
    side_norm = str(pos_side or "").lower()
    if side_norm == "long":
        return "Buy"
    if side_norm == "short":
        return "Sell"
    return "Buy" if pos_val > 0 else "Sell"


def close_non_active_positions(active_tickers, state=None, include_orders=True):
    active_set = set(active_tickers or [])

    if state is None:
        state = get_account_state()
    if not isinstance(state, dict) or not bool(state.get("ok", True)):
        logger.warning(
            "Skipping non-active position cleanup because account state is untrusted: %s",
            "; ".join(state.get("errors", [])) if isinstance(state, dict) else "invalid state",
        )
        return 0

    if include_orders:
        try:
            orders = state.get("orders", [])
            cancel_reqs = []
            for order in orders:
                if not isinstance(order, dict):
                    continue
                inst_id = order.get("instId")
                ord_id = order.get("ordId")
                if not inst_id or not ord_id:
                    continue
                if inst_id in active_set:
                    continue
                cancel_reqs.append({"instId": inst_id, "ordId": ord_id})

            if cancel_reqs:
                for i in range(0, len(cancel_reqs), 20):
                    batch = cancel_reqs[i:i + 20]
                    trade_session.cancel_multiple_orders(batch)
                logger.warning("Cancelled %d open orders for non-active instruments.", len(cancel_reqs))
        except Exception as exc:
            logger.error("Error cancelling non-active orders: %s", exc)

    closed = 0
    for pos in state.get("positions", []):
        if not isinstance(pos, dict):
            continue
        inst_id = pos.get("instId")
        if not inst_id or inst_id in active_set:
            continue
        pos_val = _safe_float(pos.get("pos") or pos.get("position") or pos.get("size"))
        if pos_val is None or abs(pos_val) == 0:
            continue
        side = _position_side(pos.get("posSide"), pos_val)
        size = abs(pos_val)
        logger.warning("Closing non-active position for %s: %.6f %s", inst_id, size, side)
        place_market_close_order(inst_id, size, side)
        closed += 1

    return closed


def _env_int(name, default, minimum=None):
    raw = os.getenv(name)
    try:
        value = int(float(raw)) if raw not in (None, "") else int(default)
    except (TypeError, ValueError):
        value = int(default)
    if minimum is not None and value < minimum:
        value = minimum
    return value


def _active_tickers(tickers=None):
    source = tickers if tickers is not None else [ticker_1, ticker_2]
    result = []
    for ticker in source:
        text = str(ticker or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _flat_blockers_from_state(state, tickers):
    if not isinstance(state, dict) or not bool(state.get("ok", True)):
        errors = state.get("errors", []) if isinstance(state, dict) else []
        detail = "; ".join(str(item) for item in errors if str(item).strip())
        return [detail or "account state could not be confirmed"]

    blockers = []
    active_set = set(tickers or [])
    for pos in state.get("positions", []):
        if not isinstance(pos, dict):
            continue
        inst_id = pos.get("instId")
        if inst_id not in active_set:
            continue
        pos_val = _safe_float(pos.get("pos") or pos.get("position") or pos.get("size"))
        if pos_val is not None and abs(pos_val) > 0:
            blockers.append(f"open position remains for {inst_id}: {abs(pos_val):.8f}")

    for order in state.get("orders", []):
        if not isinstance(order, dict):
            continue
        inst_id = order.get("instId")
        if inst_id in active_set:
            blockers.append(f"open order remains for {inst_id}: {order.get('ordId') or 'unknown order'}")

    return blockers


def account_tickers_are_flat(tickers=None, state=None):
    active = _active_tickers(tickers)
    check_state = state if state is not None else get_account_state()
    blockers = _flat_blockers_from_state(check_state, active)
    return not blockers, blockers


def close_all_positions(kill_switch, tickers=None, return_result=False):
    """
    Cancel open orders and close positions for the active pair.

    By default this preserves the historical integer return. Call with
    return_result=True for structured close/cancel diagnostics.
    """
    active = _active_tickers(tickers)
    result = {
        "ok": True,
        "kill_switch": 0,
        "tickers": active,
        "cancelled_orders": 0,
        "close_orders": 0,
        "errors": [],
    }

    for ticker in active:
        try:
            response = trade_session.get_order_list(instId=ticker)
            if isinstance(response, dict) and response.get("code") == "0":
                orders = response.get("data", [])
                if orders:
                    cancel_reqs = [{"instId": ticker, "ordId": o["ordId"]} for o in orders]
                    for i in range(0, len(cancel_reqs), 20):
                        batch = cancel_reqs[i:i + 20]
                        cancel_response = trade_session.cancel_multiple_orders(batch)
                        if isinstance(cancel_response, dict) and cancel_response.get("code") not in (None, "0"):
                            msg = f"Failed to cancel orders for {ticker}: {cancel_response.get('msg') or cancel_response.get('code')}"
                            logger.error(msg)
                            result["errors"].append(msg)
                        else:
                            result["cancelled_orders"] += len(batch)
                            logger.info(f"Cancelled {len(batch)} orders for {ticker}")
                else:
                    logger.debug(f"No open orders to cancel for {ticker}.")
            else:
                msg = f"Failed to fetch open orders for {ticker}: {response.get('msg') if isinstance(response, dict) else 'invalid response'}"
                logger.error(msg)
                result["errors"].append(msg)
        except Exception as exc:
            msg = f"Error cancelling orders for {ticker}: {exc}"
            logger.error(msg)
            result["errors"].append(msg)

    for ticker in active:
        size, side = get_position_info(ticker)
        if size > 0:
            logger.info(f"Closing position for {ticker}: {size} {side}")
            close_response = place_market_close_order(ticker, size, side)
            if isinstance(close_response, dict) and close_response.get("code") == "0":
                result["close_orders"] += 1
            else:
                msg = f"Failed to place close order for {ticker}: {close_response}"
                logger.error(msg)
                result["errors"].append(msg)

    from func_pair_state import clear_entry_tracking
    clear_entry_tracking()
    logger.info("Entry Z-score tracking cleared")

    if result["errors"]:
        result["ok"] = False
    return result if return_result else 0


def close_all_positions_and_confirm(kill_switch=0, tickers=None, timeout_seconds=None, poll_seconds=None):
    active = _active_tickers(tickers)
    timeout = timeout_seconds if timeout_seconds is not None else _env_int(
        "STATBOT_CLOSE_CONFIRM_TIMEOUT_SECONDS",
        30,
        minimum=5,
    )
    poll = poll_seconds if poll_seconds is not None else _env_int(
        "STATBOT_CLOSE_CONFIRM_POLL_SECONDS",
        2,
        minimum=1,
    )
    result = close_all_positions(kill_switch, tickers=active, return_result=True)
    deadline = time.time() + timeout
    last_blockers = []

    while True:
        flat, blockers = account_tickers_are_flat(active)
        if flat:
            result["ok"] = True
            result["confirmed_flat"] = True
            result["blockers"] = []
            result["kill_switch"] = 0
            return result

        last_blockers = blockers
        if time.time() >= deadline:
            break
        time.sleep(poll)

    result["ok"] = False
    result["confirmed_flat"] = False
    result["blockers"] = last_blockers
    result["errors"] = list(dict.fromkeys([*result.get("errors", []), *last_blockers]))
    result["kill_switch"] = kill_switch
    logger.error(
        "Close confirmation failed for %s within %ss: %s",
        "/".join(active),
        timeout,
        "; ".join(last_blockers),
    )
    return result
