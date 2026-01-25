from config_execution_api import (
    account_session,
    trade_session,
    market_session,
    public_session,
    inst_type,
    td_mode,
    pos_mode,
    dry_run,
    depth,
)
from func_calculation import get_trade_details
from decimal import Decimal, ROUND_DOWN


def _bool_str(value):
    return "true" if value else "false"


def _normalize_value(value):
    return str(value).strip().lower() if value else ""


def _is_hedged_mode(mode_value):
    normalized = _normalize_value(mode_value)
    return normalized in ("long_short", "long_short_mode", "hedge", "hedged")


def _resolve_pos_side(side, reduce_only, pos_side):
    if pos_side:
        return pos_side

    if not _is_hedged_mode(pos_mode):
        return ""

    if side == "buy":
        return "short" if reduce_only else "long"
    if side == "sell":
        return "long" if reduce_only else "short"
    return ""


def _extract_order_error(response):
    data_list = response.get("data", []) if isinstance(response, dict) else []
    order_data = data_list[0] if data_list else {}
    return order_data.get("sCode"), order_data.get("sMsg")


def _is_ok_response(response):
    if not isinstance(response, dict):
        return False
    if response.get("dry_run"):
        return True
    if response.get("code") != "0":
        return False
    s_code, _ = _extract_order_error(response)
    if s_code and s_code != "0":
        return False
    return True


def _should_dry_run(dry_run_override):
    if dry_run_override is None:
        return dry_run
    return dry_run_override


def _ensure_ok(response, context):
    if not isinstance(response, dict):
        print(f"ERROR: {context} failed: invalid response")
        return False

    if response.get("code") != "0":
        s_code, s_msg = _extract_order_error(response)
        detail = f"sCode={s_code}, sMsg={s_msg}" if s_code or s_msg else response.get("msg")
        print(f"ERROR: {context} failed: {detail}")
        return False

    s_code, s_msg = _extract_order_error(response)
    if s_code and s_code != "0":
        print(f"ERROR: {context} failed: sCode={s_code}, sMsg={s_msg}")
        return False

    return True


def _resolve_entry_side(direction):
    normalized = _normalize_value(direction)
    if normalized in ("long", "buy"):
        return "buy"
    if normalized in ("short", "sell"):
        return "sell"
    return ""


def _fetch_instrument_info(inst_id):
    try:
        response = public_session.get_instruments(instType=inst_type, instId=inst_id)
    except Exception as exc:
        print(f"WARNING: Failed to fetch instrument info: {exc}")
        return None

    if response.get("code") != "0":
        print(f"WARNING: Instrument lookup failed: {response.get('msg')}")
        return None

    data = response.get("data", [])
    return data[0] if data else None


def _adjust_quantity_to_lot_size(inst_id, quantity, instrument_info=None):
    if quantity <= 0:
        return quantity

    info = instrument_info or _fetch_instrument_info(inst_id)
    if not info:
        return quantity

    lot_sz_raw = info.get("lotSz")
    try:
        lot_sz = Decimal(str(lot_sz_raw))
    except (TypeError, ValueError):
        return quantity

    if lot_sz <= 0:
        return quantity

    min_sz_raw = info.get("minSz")
    try:
        min_sz = Decimal(str(min_sz_raw)) if min_sz_raw else Decimal("0")
    except (TypeError, ValueError):
        min_sz = Decimal("0")

    size_dec = Decimal(str(quantity))
    steps = (size_dec / lot_sz).to_integral_value(rounding=ROUND_DOWN)
    adjusted = steps * lot_sz

    if adjusted < min_sz:
        print(f"ERROR: Quantity {quantity} below minSz {min_sz} after lot size adjustment.")
        return 0.0

    if adjusted != size_dec:
        print(f"Adjusted quantity to lot size: {quantity} -> {adjusted}")

    return float(adjusted)


def place_stop_loss_order(inst_id, side, size, trigger_price, td_mode_override=None, pos_side="",
                          session=None, dry_run_override=None):
    """
    Place a stop-loss order using OKX algo orders.
    """
    active_session = session or trade_session
    td_mode_value = _normalize_value(td_mode_override or td_mode)
    side = _normalize_value(side)
    pos_side = _resolve_pos_side(side, True, _normalize_value(pos_side))

    if _should_dry_run(dry_run_override):
        pos_info = f", posSide={pos_side}" if pos_side else ""
        print(f"DRY RUN: stop loss {side} {inst_id}, size={size}, trigger={trigger_price}{pos_info}")
        return {"code": "0", "msg": "", "data": [{"algoId": "DRYRUN"}], "dry_run": True}

    try:
        response = active_session.place_algo_order(
            instId=inst_id,
            tdMode=td_mode_value,
            side=side,
            ordType="conditional",
            sz=str(size),
            posSide=pos_side,
            reduceOnly=_bool_str(True),
            slTriggerPx=str(trigger_price),
            slOrdPx="-1",
        )
    except Exception as exc:
        print(f"ERROR: Failed to place stop loss order: {exc}")
        return None

    if not _ensure_ok(response, "OKX stop loss order"):
        return response

    algo_id = response.get("data", [{}])[0].get("algoId", "")
    pos_info = f", posSide={pos_side}" if pos_side else ""
    print(f"OK: Stop loss placed ({side} {inst_id}, size={size}, trigger={trigger_price}{pos_info}) id={algo_id}")
    return response


def place_entry_with_stop(inst_id, direction, capital, orderbook_payload=None, size_override=None,
                          limit_offset=0.0, td_mode_override=None, dry_run_override=None,
                          place_stop=True, enforce_lot_size=True, instrument_info=None):
    """
    Place an entry order plus a stop-loss order based on live orderbook data.
    """
    entry_side = _resolve_entry_side(direction)
    if not entry_side:
        print("ERROR: direction must be long/short or buy/sell.")
        return None

    if orderbook_payload is None:
        try:
            res = market_session.get_orderbook(instId=inst_id, sz=str(depth))
        except Exception as exc:
            print(f"ERROR: Failed to fetch orderbook: {exc}")
            return None

        if res.get("code") != "0":
            print(f"ERROR: Orderbook fetch failed: {res.get('msg')}")
            return None

        orderbook_payload = {"arg": {"channel": "books", "instId": inst_id}, "data": res.get("data", [])}

    entry_price, quantity, stop_price = get_trade_details(
        orderbook_payload,
        direction="long" if entry_side == "buy" else "short",
        capital=capital,
    )

    if size_override is not None:
        try:
            quantity = float(size_override)
        except (TypeError, ValueError):
            pass

    if enforce_lot_size:
        quantity = _adjust_quantity_to_lot_size(inst_id, quantity, instrument_info=instrument_info)

    if entry_price <= 0 or quantity <= 0 or stop_price <= 0:
        print("ERROR: Invalid trade details (entry, quantity, stop).")
        return None

    if limit_offset and limit_offset != 0:
        offset = abs(float(limit_offset))
        if entry_side == "buy":
            limit_price = entry_price * (1 - offset)
        else:
            limit_price = entry_price * (1 + offset)
        entry_res = place_limit_order(
            inst_id,
            side=entry_side,
            size=quantity,
            price=limit_price,
            td_mode_override=td_mode_override,
            dry_run_override=dry_run_override,
        )
    else:
        entry_res = place_market_order(
            inst_id,
            side=entry_side,
            size=quantity,
            td_mode_override=td_mode_override,
            dry_run_override=dry_run_override,
        )

    details = {
        "inst_id": inst_id,
        "direction": direction,
        "entry_side": entry_side,
        "entry_price": entry_price,
        "quantity": quantity,
        "stop_price": stop_price,
    }

    result = {"entry": entry_res, "stop": None, "details": details, "ok": _is_ok_response(entry_res)}
    if not result["ok"]:
        print("ERROR: Entry order failed; stop order not placed.")
        return result

    if not place_stop:
        return result

    stop_side = "sell" if entry_side == "buy" else "buy"
    stop_res = place_stop_loss_order(
        inst_id,
        side=stop_side,
        size=quantity,
        trigger_price=stop_price,
        td_mode_override=td_mode_override,
        dry_run_override=dry_run_override,
    )
    result["stop"] = stop_res
    result["ok"] = result["ok"] and _is_ok_response(stop_res)
    return result


def set_leverage(inst_id, leverage, mgn_mode=None, pos_side="", session=None, dry_run_override=None):
    """
    Set leverage for a given instrument.
    """
    active_session = session or account_session
    mgn_mode = _normalize_value(mgn_mode or td_mode)
    pos_side = _normalize_value(pos_side)

    if _should_dry_run(dry_run_override):
        print(f"DRY RUN: set_leverage {inst_id} to {leverage}x ({mgn_mode})")
        return {"code": "0", "msg": "", "data": [{"instId": inst_id}], "dry_run": True}

    try:
        response = active_session.set_leverage(
            lever=str(leverage),
            mgnMode=mgn_mode,
            instId=inst_id,
            posSide=pos_side,
        )
    except Exception as exc:
        print(f"ERROR: Failed to set leverage: {exc}")
        return None

    if response.get("code") != "0":
        print(f"ERROR: OKX set_leverage failed: {response.get('msg')}")
        return response

    print(f"OK: Leverage set for {inst_id} to {leverage}x ({mgn_mode})")
    return response


def place_market_order(inst_id, side, size, reduce_only=False, td_mode_override=None, pos_side="",
                       session=None, dry_run_override=None):
    """
    Place a market order.
    """
    active_session = session or trade_session
    td_mode_value = _normalize_value(td_mode_override or td_mode)
    side = _normalize_value(side)
    pos_side = _resolve_pos_side(side, reduce_only, _normalize_value(pos_side))

    if _should_dry_run(dry_run_override):
        pos_info = f", posSide={pos_side}" if pos_side else ""
        print(f"DRY RUN: market order {side} {inst_id}, size={size}{pos_info}")
        return {"code": "0", "msg": "", "data": [{"ordId": "DRYRUN"}], "dry_run": True}

    try:
        response = active_session.place_order(
            instId=inst_id,
            tdMode=td_mode_value,
            side=side,
            ordType="market",
            sz=str(size),
            posSide=pos_side,
            reduceOnly=_bool_str(reduce_only),
        )
    except Exception as exc:
        print(f"ERROR: Failed to place market order: {exc}")
        return None

    if not _ensure_ok(response, "OKX market order"):
        return response

    order_id = response.get("data", [{}])[0].get("ordId", "")
    pos_info = f", posSide={pos_side}" if pos_side else ""
    print(f"OK: Market order placed ({side} {inst_id}, size={size}{pos_info}) id={order_id}")
    return response


def place_limit_order(inst_id, side, size, price, reduce_only=False, td_mode_override=None, pos_side="",
                      session=None, dry_run_override=None):
    """
    Place a limit order.
    """
    active_session = session or trade_session
    td_mode_value = _normalize_value(td_mode_override or td_mode)
    side = _normalize_value(side)
    pos_side = _resolve_pos_side(side, reduce_only, _normalize_value(pos_side))

    if _should_dry_run(dry_run_override):
        pos_info = f", posSide={pos_side}" if pos_side else ""
        print(f"DRY RUN: limit order {side} {inst_id}, size={size}, px={price}{pos_info}")
        return {"code": "0", "msg": "", "data": [{"ordId": "DRYRUN"}], "dry_run": True}

    try:
        response = active_session.place_order(
            instId=inst_id,
            tdMode=td_mode_value,
            side=side,
            ordType="limit",
            sz=str(size),
            px=str(price),
            posSide=pos_side,
            reduceOnly=_bool_str(reduce_only),
        )
    except Exception as exc:
        print(f"ERROR: Failed to place limit order: {exc}")
        return None

    if not _ensure_ok(response, "OKX limit order"):
        return response

    order_id = response.get("data", [{}])[0].get("ordId", "")
    pos_info = f", posSide={pos_side}" if pos_side else ""
    print(f"OK: Limit order placed ({side} {inst_id}, size={size}, px={price}{pos_info}) id={order_id}")
    return response


def cancel_order(inst_id, ord_id="", cl_ord_id="", session=None, dry_run_override=None):
    """
    Cancel an order by order ID or client order ID.
    """
    active_session = session or trade_session

    if not ord_id and not cl_ord_id:
        print("ERROR: ord_id or cl_ord_id is required to cancel an order")
        return None

    if _should_dry_run(dry_run_override):
        print(f"DRY RUN: cancel order {inst_id}, ord_id={ord_id or cl_ord_id}")
        return {"code": "0", "msg": "", "data": [{"ordId": ord_id}], "dry_run": True}

    try:
        response = active_session.cancel_order(instId=inst_id, ordId=ord_id, clOrdId=cl_ord_id)
    except Exception as exc:
        print(f"ERROR: Failed to cancel order: {exc}")
        return None

    if not _ensure_ok(response, "OKX cancel order"):
        return response

    print(f"OK: Cancel request submitted for {inst_id}")
    return response


def get_open_orders(inst_id="", session=None):
    """
    Get open orders for the instrument or for the configured instType.
    """
    active_session = session or trade_session

    try:
        response = active_session.get_order_list(instType=inst_type, instId=inst_id)
    except Exception as exc:
        print(f"ERROR: Failed to fetch open orders: {exc}")
        return None

    if response.get("code") != "0":
        print(f"ERROR: OKX open orders failed: {response.get('msg')}")
        return response

    return response.get("data", [])


def _extract_order_id(response):
    if not isinstance(response, dict):
        return ""
    data_list = response.get("data", [])
    order_data = data_list[0] if data_list else {}
    return order_data.get("ordId", "")


def _extract_algo_id(response):
    if not isinstance(response, dict):
        return ""
    data_list = response.get("data", [])
    order_data = data_list[0] if data_list else {}
    return order_data.get("algoId", "")


def get_order_history(inst_id="", limit=50, session=None):
    """
    Get recent order history (last 7 days).
    """
    active_session = session or trade_session

    try:
        response = active_session.get_orders_history(instType=inst_type, instId=inst_id, limit=str(limit))
    except Exception as exc:
        print(f"ERROR: Failed to fetch order history: {exc}")
        return None

    if response.get("code") != "0":
        print(f"ERROR: OKX order history failed: {response.get('msg')}")
        return response

    return response.get("data", [])



# Initialize execution
def initialise_order_execution(
    ticker,
    direction,
    capital,
    orderbook_payload=None,
    size_override=None,
    limit_offset=0.0,
    td_mode_override=None,
    dry_run_override=None,
    place_stop=True,
    enforce_lot_size=True,
    instrument_info=None,
):
    """
    Place an entry order (market or limit) and optional stop-loss using OKX.
    Returns a dict with entry/stop responses and extracted IDs, or None on failure.
    """
    if orderbook_payload is None:
        try:
            res = market_session.get_orderbook(instId=ticker, sz=str(depth))
        except Exception as exc:
            print(f"ERROR: Failed to fetch orderbook: {exc}")
            return None

        if res.get("code") != "0":
            print(f"ERROR: Orderbook fetch failed: {res.get('msg')}")
            return None

        orderbook_payload = {"arg": {"channel": "books", "instId": ticker}, "data": res.get("data", [])}

    result = place_entry_with_stop(
        inst_id=ticker,
        direction=direction,
        capital=capital,
        orderbook_payload=orderbook_payload,
        size_override=size_override,
        limit_offset=limit_offset,
        td_mode_override=td_mode_override,
        dry_run_override=dry_run_override,
        place_stop=place_stop,
        enforce_lot_size=enforce_lot_size,
        instrument_info=instrument_info,
    )

    if not result:
        return None

    result["entry_id"] = _extract_order_id(result.get("entry"))
    result["stop_id"] = _extract_algo_id(result.get("stop"))
    return result
