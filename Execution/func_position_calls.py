import math

from config_execution_api import account_session, inst_type, trade_session

# Check for open positions
def open_position_confirmation(inst_id="", inst_type_override=None, session=None):
    """
    Return True if there is any open position (safe default True on errors).
    """
    active_session = session or account_session
    inst_type_value = inst_type_override or inst_type

    try:
        response = active_session.get_positions(instType=inst_type_value, instId=inst_id)
    except Exception as exc:
        print(f"ERROR: Failed to fetch positions: {exc}")
        return True

    if not isinstance(response, dict):
        print("ERROR: Positions response invalid.")
        return True

    if response.get("code") != "0":
        print(f"ERROR: OKX positions failed: {response.get('msg')}")
        return True

    data = response.get("data", [])
    if not isinstance(data, list):
        return True

    for item in data:
        if not isinstance(item, dict):
            continue
        pos_raw = item.get("pos") or item.get("position") or item.get("size")
        try:
            pos_val = float(pos_raw)
        except (TypeError, ValueError):
            continue
        if abs(pos_val) > 0:
            return True

    return False


def _normalize_direction(direction):
    return str(direction).strip().lower() if direction else ""


def _matches_direction(pos_side, pos_value, direction):
    direction_norm = _normalize_direction(direction)
    if not direction_norm:
        return True

    pos_side_norm = str(pos_side or "").lower()
    if pos_side_norm:
        if direction_norm in ("long", "buy"):
            return pos_side_norm in ("long", "buy")
        if direction_norm in ("short", "sell"):
            return pos_side_norm in ("short", "sell")

    if direction_norm in ("long", "buy"):
        return pos_value > 0
    if direction_norm in ("short", "sell"):
        return pos_value < 0
    return True


def _safe_float(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _first_positive(*values):
    for value in values:
        parsed = _safe_float(value)
        if parsed is not None and parsed > 0:
            return parsed
    return None


def _recommend_order_size_focus(order):
    order_size = _safe_float(order.get("sz"))
    filled_size = _safe_float(order.get("accFillSz") or order.get("fillSz"))
    state = str(
        order.get("state")
        or order.get("orderStatus")
        or order.get("status")
        or order.get("order_status")
        or ""
    ).lower()

    if order_size is None and filled_size is None:
        return {
            "focus": "unknown",
            "basis": None,
            "reason": "size fields missing",
        }

    if filled_size is None:
        filled_size = 0.0

    if order_size is None or order_size <= 0:
        return {
            "focus": "filled",
            "basis": "accFillSz",
            "order_size": order_size,
            "filled_size": filled_size,
            "remaining_size": None,
            "fill_ratio": None,
            "state": state,
            "reason": "order size missing; use filled size",
        }

    fill_ratio = filled_size / order_size if order_size else None
    remaining = max(order_size - filled_size, 0.0)

    if state == "filled":
        focus = "filled"
        basis = "accFillSz"
        reason = "order filled"
    elif state in ("canceled", "cancelled"):
        if filled_size > 0:
            focus = "filled"
            basis = "accFillSz"
            reason = "order canceled with fills"
        else:
            focus = "original"
            basis = "sz"
            reason = "order canceled without fills"
    elif filled_size == 0:
        focus = "original"
        basis = "sz"
        reason = "no fills yet"
    elif filled_size >= order_size:
        focus = "filled"
        basis = "accFillSz"
        reason = "filled size >= order size"
    else:
        focus = "both"
        basis = "accFillSz"
        reason = "partial fill; use accFillSz for exposure, sz for intent"

    return {
        "focus": focus,
        "basis": basis,
        "order_size": order_size,
        "filled_size": filled_size,
        "remaining_size": remaining,
        "fill_ratio": fill_ratio,
        "state": state,
        "reason": reason,
    }


def get_open_positions(inst_id="", direction="Long", inst_type_override=None, session=None):
    """
    Return (entry_price, size) for the matching open position.
    """
    active_session = session or account_session
    inst_type_value = inst_type_override or inst_type

    try:
        response = active_session.get_positions(instType=inst_type_value, instId=inst_id)
    except Exception as exc:
        print(f"ERROR: Failed to fetch positions: {exc}")
        return None, None

    if not isinstance(response, dict):
        print("ERROR: Positions response invalid.")
        return None, None

    if response.get("code") != "0":
        print(f"ERROR: OKX positions failed: {response.get('msg')}")
        return None, None

    data = response.get("data", [])
    if not isinstance(data, list) or not data:
        return None, None

    for item in data:
        if not isinstance(item, dict):
            continue

        pos_val = _safe_float(item.get("pos") or item.get("position") or item.get("size"))
        if pos_val is None or pos_val == 0:
            continue

        if not _matches_direction(item.get("posSide"), pos_val, direction):
            continue

        price_val = _safe_float(item.get("avgPx") or item.get("entryPx") or item.get("avgPx"))
        if price_val is None or price_val <= 0:
            return None, None

        return price_val, abs(pos_val)

    return None, None


# Check for active orders
def get_active_positions(inst_id="", order_id=None, inst_type_override=None, session=None):
    """
    Return (order_price, order_size) for the first active order (or a matching order_id).
    """
    active_session = session or trade_session
    inst_type_value = inst_type_override or inst_type

    try:
        response = active_session.get_order_list(instType=inst_type_value, instId=inst_id)
    except Exception as exc:
        print(f"ERROR: Failed to fetch open orders: {exc}")
        return None, None

    if not isinstance(response, dict):
        print("ERROR: Open orders response invalid.")
        return None, None

    if response.get("code") != "0":
        print(f"ERROR: OKX open orders failed: {response.get('msg')}")
        return None, None

    data = response.get("data", [])
    if not isinstance(data, list) or not data:
        return None, None

    order = None
    if order_id:
        for item in data:
            if not isinstance(item, dict):
                continue
            if item.get("ordId") == order_id or item.get("clOrdId") == order_id:
                order = item
                break
    else:
        order = data[0] if isinstance(data[0], dict) else None

    if not order:
        return None, None

    price_val = _safe_float(order.get("px") or order.get("avgPx") or order.get("fillPx"))
    size_val = _safe_float(order.get("sz") or order.get("accFillSz") or order.get("fillSz"))
    if price_val is None or size_val is None:
        return None, None

    return price_val, size_val


# Check for active orders
def active_position_confirmation(inst_id="", inst_type_override=None, session=None):
    """
    Return True if there are any open orders (safe default True on errors).
    """
    active_session = session or trade_session
    inst_type_value = inst_type_override or inst_type

    try:
        response = active_session.get_order_list(instType=inst_type_value, instId=inst_id)
    except Exception as exc:
        print(f"ERROR: Failed to fetch open orders: {exc}")
        return True

    if not isinstance(response, dict):
        print("ERROR: Open orders response invalid.")
        return True

    if response.get("code") != "0":
        print(f"ERROR: OKX open orders failed: {response.get('msg')}")
        return True

    data = response.get("data", [])
    if not isinstance(data, list):
        return True

    return bool(data)


# Query existing order
def query_existing_order(order_id, inst_id="", direction=None, inst_type_override=None, session=None,
                         include_recommendation=False):
    """
    Return (order_price, order_qty, order_status) for a specific order.
    """
    active_session = session or trade_session
    inst_type_value = inst_type_override or inst_type

    if not order_id:
        return None, None, None

    order = None

    if inst_id:
        try:
            response = active_session.get_order(instId=inst_id, ordId=order_id)
        except Exception as exc:
            print(f"ERROR: Failed to fetch order {order_id}: {exc}")
            return None, None, None

        if not isinstance(response, dict):
            print("ERROR: Order response invalid.")
            return None, None, None

        if response.get("code") != "0":
            print(f"ERROR: OKX order lookup failed: {response.get('msg')}")
            return None, None, None

        data = response.get("data", [])
        order = data[0] if isinstance(data, list) and data else None
    else:
        try:
            response = active_session.get_order_list(instType=inst_type_value, limit="100")
        except Exception as exc:
            print(f"ERROR: Failed to fetch open orders: {exc}")
            return None, None, None

        if not isinstance(response, dict):
            print("ERROR: Open orders response invalid.")
            return None, None, None

        if response.get("code") != "0":
            print(f"ERROR: OKX open orders failed: {response.get('msg')}")
            return None, None, None

        data = response.get("data", [])
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                if item.get("ordId") == order_id or item.get("clOrdId") == order_id:
                    order = item
                    break

    if not isinstance(order, dict):
        return None, None, None

    side = order.get("side")
    side_norm = str(side or "").lower()
    if direction and side_norm:
        pos_value = 1 if side_norm == "buy" else -1 if side_norm == "sell" else 0
        if not _matches_direction(side_norm, pos_value, direction):
            return None, None, None

    order_price = _first_positive(order.get("px"), order.get("avgPx"), order.get("fillPx"))
    order_qty = _safe_float(order.get("sz"))
    if order_qty is None or order_qty == 0:
        order_qty = _safe_float(order.get("accFillSz") or order.get("fillSz"))
    order_status = order.get("state") or order.get("orderStatus") or order.get("status") or order.get("order_status")
    if order_price is None or order_qty is None:
        return None, None, None

    if include_recommendation:
        recommendation = _recommend_order_size_focus(order)
        return order_price, order_qty, order_status, recommendation

    return order_price, order_qty, order_status
