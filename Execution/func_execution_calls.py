import os

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
from func_calculation import get_trade_details, get_contract_value_quote
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_UP


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


def _get_orderbook_payload(inst_id):
    try:
        res = market_session.get_orderbook(instId=inst_id, sz=str(depth))
    except Exception as exc:
        return None, f"Failed to fetch orderbook: {exc}"

    if res.get("code") != "0":
        return None, f"Orderbook fetch failed: {res.get('msg')}"

    payload = {"arg": {"channel": "books", "instId": inst_id}, "data": res.get("data", [])}
    return payload, None


def _adjust_quantity_to_lot_size(inst_id, quantity, instrument_info=None):
    if quantity <= 0:
        return quantity

    info = instrument_info or _fetch_instrument_info(inst_id)
    if not info:
        return quantity

    lot_sz_raw = info.get("lotSz")
    try:
        lot_sz = Decimal(str(lot_sz_raw))
    except (TypeError, ValueError, InvalidOperation):
        return quantity

    if lot_sz <= 0:
        return quantity

    min_sz_raw = info.get("minSz")
    try:
        min_sz = Decimal(str(min_sz_raw)) if min_sz_raw else Decimal("0")
    except (TypeError, ValueError, InvalidOperation):
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


def _get_min_order_qty(instrument_info):
    if not instrument_info:
        return Decimal("0")

    lot_sz_raw = instrument_info.get("lotSz")
    min_sz_raw = instrument_info.get("minSz")
    try:
        lot_sz = Decimal(str(lot_sz_raw)) if lot_sz_raw is not None else Decimal("0")
    except (TypeError, ValueError, InvalidOperation):
        lot_sz = Decimal("0")
    try:
        min_sz = Decimal(str(min_sz_raw)) if min_sz_raw is not None else Decimal("0")
    except (TypeError, ValueError, InvalidOperation):
        min_sz = Decimal("0")

    if lot_sz <= 0 and min_sz <= 0:
        return Decimal("0")
    if lot_sz <= 0:
        return min_sz
    if min_sz <= 0:
        return lot_sz

    steps = (min_sz / lot_sz).to_integral_value(rounding=ROUND_UP)
    return steps * lot_sz


def _calculate_min_capital(entry_price, instrument_info):
    if entry_price <= 0:
        return 0.0, 0.0
    min_qty = _get_min_order_qty(instrument_info)
    if min_qty <= 0:
        return 0.0, 0.0
    inst_id = instrument_info.get("instId") if instrument_info else ""
    contract_value_quote = get_contract_value_quote(entry_price, instrument_info, inst_id=inst_id)
    if contract_value_quote <= 0:
        min_capital = float(min_qty) * entry_price
    else:
        min_capital = float(min_qty) * contract_value_quote
    return float(min_qty), min_capital


def _decimal_from_info(instrument_info, key):
    if not instrument_info:
        return Decimal("0")
    raw = instrument_info.get(key)
    try:
        value = Decimal(str(raw)) if raw not in (None, "") else Decimal("0")
    except (TypeError, ValueError, InvalidOperation):
        return Decimal("0")
    return value if value > 0 else Decimal("0")


def _format_qty(value):
    try:
        return f"{float(value):.8f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def _format_decimal(value):
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _decimal_from_value(value):
    try:
        parsed = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return None
    if not parsed.is_finite():
        return None
    return parsed


def validate_stop_trigger_price(
    inst_id,
    side,
    reference_price,
    computed_trigger_price,
    instrument_info=None,
):
    """
    Validate and round an OKX stop-loss trigger before order submission.

    `side` is the stop order side: a sell stop closes a long and must trigger
    below the reference price; a buy stop closes a short and must trigger above
    it. OKX requires slTriggerPx to respect tickSz, which matters for tiny-price
    swaps such as SHIB-USDT-SWAP.
    """
    side_norm = _normalize_value(side)
    tick_size = _decimal_from_info(instrument_info, "tickSz")
    ref_dec = _decimal_from_value(reference_price)
    raw_dec = _decimal_from_value(computed_trigger_price)
    metadata = {
        "inst_id": inst_id,
        "side": side_norm,
        "reference_price": reference_price,
        "raw_trigger_px": computed_trigger_price,
        "tick_size": _format_decimal(tick_size) if tick_size > 0 else None,
    }

    if side_norm not in ("buy", "sell"):
        return {"valid": False, "rounded_trigger_px": None, "reason": "invalid_stop_side", "metadata": metadata}
    if ref_dec is None or ref_dec <= 0:
        return {"valid": False, "rounded_trigger_px": None, "reason": "invalid_reference_price", "metadata": metadata}
    if raw_dec is None or raw_dec <= 0:
        return {"valid": False, "rounded_trigger_px": None, "reason": "invalid_trigger_price", "metadata": metadata}

    rounded = raw_dec
    if tick_size > 0:
        rounding_mode = ROUND_DOWN if side_norm == "sell" else ROUND_UP
        steps = (raw_dec / tick_size).to_integral_value(rounding=rounding_mode)
        rounded = steps * tick_size

    rounded_text = _format_decimal(rounded)
    metadata["rounded_trigger_px"] = rounded_text

    if rounded <= 0:
        return {"valid": False, "rounded_trigger_px": rounded_text, "reason": "rounded_trigger_not_positive", "metadata": metadata}
    if side_norm == "sell" and rounded >= ref_dec:
        return {
            "valid": False,
            "rounded_trigger_px": rounded_text,
            "reason": "sell_stop_trigger_not_below_reference",
            "metadata": metadata,
        }
    if side_norm == "buy" and rounded <= ref_dec:
        return {
            "valid": False,
            "rounded_trigger_px": rounded_text,
            "reason": "buy_stop_trigger_not_above_reference",
            "metadata": metadata,
        }

    return {"valid": True, "rounded_trigger_px": rounded_text, "reason": None, "metadata": metadata}


def validate_stop_tick_distance(
    inst_id,
    side,
    entry_price,
    stop_price,
    instrument_info=None,
    min_ticks=None,
):
    """
    Verify that the stop price is at least `min_ticks` tick-sizes away from the
    entry price.  For a sell stop (closing a long) the stop must be below entry
    by at least `tickSz * min_ticks`; for a buy stop (closing a short) it must
    be above entry by the same margin.

    Instruments like SHIB-USDT-SWAP have tickSz=0.000001, so a 3% stop placed
    at entry_price * 0.97 rounds to the floor tick and ends up only 0.26 ticks
    away—OKX then rejects the algo order at placement time.  This check catches
    that failure *before* the entry order is placed.

    Returns a dict with keys:
        valid (bool)
        reason (str | None)
        distance_ticks (float | None)
        min_required_ticks (int)
        tick_size (str | None)
        metadata (dict)
    """
    side_norm = _normalize_value(side)
    tick_size = _decimal_from_info(instrument_info, "tickSz")
    entry_dec = _decimal_from_value(entry_price)
    stop_dec = _decimal_from_value(stop_price)

    if min_ticks is None:
        raw = os.getenv("STATBOT_MIN_STOP_DISTANCE_TICKS", "2")
        try:
            min_ticks = max(int(float(raw)), 0)
        except (TypeError, ValueError):
            min_ticks = 2

    tick_str = _format_decimal(tick_size) if tick_size > 0 else None
    metadata = {
        "inst_id": inst_id,
        "side": side_norm,
        "entry_price": entry_price,
        "stop_price": stop_price,
        "tick_size": tick_str,
        "min_required_ticks": min_ticks,
    }

    if tick_size <= 0 or min_ticks <= 0:
        metadata["distance_ticks"] = None
        return {"valid": True, "reason": None, "distance_ticks": None,
                "min_required_ticks": min_ticks, "tick_size": tick_str, "metadata": metadata}

    if entry_dec is None or entry_dec <= 0 or stop_dec is None or stop_dec <= 0:
        metadata["distance_ticks"] = None
        return {"valid": False, "reason": "invalid_price_for_tick_distance_check",
                "distance_ticks": None, "min_required_ticks": min_ticks,
                "tick_size": tick_str, "metadata": metadata}

    if side_norm == "sell":
        raw_distance = entry_dec - stop_dec
    elif side_norm == "buy":
        raw_distance = stop_dec - entry_dec
    else:
        metadata["distance_ticks"] = None
        return {"valid": False, "reason": "invalid_side_for_tick_distance_check",
                "distance_ticks": None, "min_required_ticks": min_ticks,
                "tick_size": tick_str, "metadata": metadata}

    if raw_distance <= 0:
        metadata["distance_ticks"] = 0.0
        return {"valid": False, "reason": "stop_wrong_side_of_entry",
                "distance_ticks": 0.0, "min_required_ticks": min_ticks,
                "tick_size": tick_str, "metadata": {**metadata, "distance_ticks": 0.0}}

    distance_ticks = float(raw_distance / tick_size)
    metadata["distance_ticks"] = distance_ticks

    if distance_ticks < min_ticks:
        return {
            "valid": False,
            "reason": "stop_too_close_in_ticks",
            "distance_ticks": distance_ticks,
            "min_required_ticks": min_ticks,
            "tick_size": tick_str,
            "metadata": metadata,
        }

    return {
        "valid": True,
        "reason": None,
        "distance_ticks": distance_ticks,
        "min_required_ticks": min_ticks,
        "tick_size": tick_str,
        "metadata": metadata,
    }


def _block_entry_if_stop_invalid():
    raw = os.getenv("STATBOT_BLOCK_ENTRY_IF_STOP_INVALID", "true").strip().lower()
    return raw not in ("0", "false", "no", "n", "off")


def _get_min_stop_distance_ticks():
    raw = os.getenv("STATBOT_MIN_STOP_DISTANCE_TICKS", "2")
    try:
        return max(int(float(raw)), 0)
    except (TypeError, ValueError):
        return 2


def _get_max_order_qty(instrument_info, order_type):
    order_type = _normalize_value(order_type) or "market"
    if order_type == "limit":
        return _decimal_from_info(instrument_info, "maxLmtSz"), "maxLmtSz"
    return _decimal_from_info(instrument_info, "maxMktSz"), "maxMktSz"


def _validate_order_size_limits(
    inst_id,
    quantity,
    entry_price,
    instrument_info,
    order_type="market",
    place_stop=True,
):
    """
    Validate OKX max order-size fields before placing either leg.

    OKX derivative `sz` is contract count, so maxMktSz/maxLmtSz/maxStopSz must
    be checked against the rounded contract quantity, not only USDT notional.
    """
    result = {
        "ok": True,
        "order_type": _normalize_value(order_type) or "market",
        "max_order_size": None,
        "max_order_size_field": "",
        "max_stop_size": None,
        "max_order_notional_usdt": None,
        "max_stop_notional_usdt": None,
        "error": "",
    }
    if not instrument_info:
        return result

    try:
        qty_dec = Decimal(str(quantity))
    except (TypeError, ValueError):
        result["ok"] = False
        result["error"] = f"invalid quantity for max-size check: {quantity}"
        return result

    contract_value_quote = get_contract_value_quote(entry_price, instrument_info, inst_id=inst_id)
    order_max, order_field = _get_max_order_qty(instrument_info, result["order_type"])
    stop_max = _decimal_from_info(instrument_info, "maxStopSz")
    failures = []

    if order_max > 0:
        result["max_order_size"] = float(order_max)
        result["max_order_size_field"] = order_field
        if contract_value_quote > 0:
            result["max_order_notional_usdt"] = float(order_max) * contract_value_quote
        if qty_dec > order_max:
            max_notional = result["max_order_notional_usdt"]
            notional_text = f", max_notional={max_notional:.2f} USDT" if max_notional else ""
            failures.append(
                f"{inst_id} {result['order_type']} quantity {_format_qty(qty_dec)} "
                f"exceeds {order_field} {_format_qty(order_max)}{notional_text}"
            )

    if place_stop and stop_max > 0:
        result["max_stop_size"] = float(stop_max)
        if contract_value_quote > 0:
            result["max_stop_notional_usdt"] = float(stop_max) * contract_value_quote
        if qty_dec > stop_max:
            max_notional = result["max_stop_notional_usdt"]
            notional_text = f", max_notional={max_notional:.2f} USDT" if max_notional else ""
            failures.append(
                f"{inst_id} stop quantity {_format_qty(qty_dec)} "
                f"exceeds maxStopSz {_format_qty(stop_max)}{notional_text}"
            )

    if failures:
        result["ok"] = False
        result["error"] = "; ".join(failures)
    return result


def get_min_capital_requirements(inst_id, orderbook_payload=None, instrument_info=None):
    info = instrument_info or _fetch_instrument_info(inst_id)
    if not info:
        return {"ok": False, "error": "instrument info unavailable"}

    if orderbook_payload is None:
        orderbook_payload, err = _get_orderbook_payload(inst_id)
        if not orderbook_payload:
            return {"ok": False, "error": err}

    entry_long, _, _ = get_trade_details(
        orderbook_payload,
        direction="long",
        capital=1.0,
        instrument_info=info,
    )
    entry_short, _, _ = get_trade_details(
        orderbook_payload,
        direction="short",
        capital=1.0,
        instrument_info=info,
    )

    min_qty_long, min_cap_long = _calculate_min_capital(entry_long, info)
    min_qty_short, min_cap_short = _calculate_min_capital(entry_short, info)

    min_capital = max(min_cap_long, min_cap_short)
    min_qty = max(min_qty_long, min_qty_short)

    return {
        "ok": min_capital > 0,
        "min_capital": min_capital,
        "min_qty": min_qty,
        "entry_long": entry_long,
        "entry_short": entry_short,
        "orderbook_payload": orderbook_payload,
        "instrument_info": info,
    }


def preview_entry_details(inst_id, direction, capital, orderbook_payload=None,
                          enforce_lot_size=True, instrument_info=None,
                          order_type="market", place_stop=True):
    entry_side = _resolve_entry_side(direction)
    if not entry_side:
        return {"ok": False, "error": "direction must be long/short or buy/sell."}

    if orderbook_payload is None:
        orderbook_payload, err = _get_orderbook_payload(inst_id)
        if not orderbook_payload:
            return {"ok": False, "error": err}

    info = instrument_info
    if info is None:
        info = _fetch_instrument_info(inst_id)

    entry_price, quantity, stop_price = get_trade_details(
        orderbook_payload,
        direction="long" if entry_side == "buy" else "short",
        capital=capital,
        instrument_info=info,
    )

    if enforce_lot_size and info:
        quantity = _adjust_quantity_to_lot_size(inst_id, quantity, instrument_info=info)

    ok = entry_price > 0 and quantity > 0 and stop_price > 0
    error = ""
    if not ok:
        error = f"entry={entry_price} qty={quantity} stop={stop_price} capital={capital}"

    min_qty, min_capital = _calculate_min_capital(entry_price, info)
    contract_value_quote = get_contract_value_quote(entry_price, info, inst_id=inst_id)
    notional_usdt = 0.0
    if contract_value_quote > 0 and quantity > 0:
        notional_usdt = float(quantity) * contract_value_quote
    size_limits = _validate_order_size_limits(
        inst_id,
        quantity,
        entry_price,
        info,
        order_type=order_type,
        place_stop=place_stop,
    )
    if ok and not size_limits.get("ok", True):
        ok = False
        error = size_limits.get("error", "")
    stop_validation = None
    tick_dist_check = None
    if ok and place_stop:
        stop_side = "sell" if entry_side == "buy" else "buy"
        stop_validation = validate_stop_trigger_price(
            inst_id,
            stop_side,
            entry_price,
            stop_price,
            instrument_info=info,
        )
        if not stop_validation.get("valid"):
            ok = False
            error = f"stop_loss_preflight_failed: {stop_validation.get('reason')}"
        else:
            stop_price = stop_validation.get("rounded_trigger_px")
            if _block_entry_if_stop_invalid():
                tick_dist_check = validate_stop_tick_distance(
                    inst_id, stop_side, entry_price, stop_price,
                    instrument_info=info, min_ticks=_get_min_stop_distance_ticks(),
                )
                if not tick_dist_check["valid"]:
                    ok = False
                    error = f"stop_loss_tick_distance_failed: {tick_dist_check.get('reason')}"

    return {
        "ok": ok,
        "inst_id": inst_id,
        "direction": direction,
        "entry_side": entry_side,
        "entry_price": entry_price,
        "quantity": quantity,
        "stop_price": stop_price,
        "min_qty": min_qty,
        "min_capital": min_capital,
        "contract_value_quote": contract_value_quote,
        "notional_usdt": notional_usdt,
        "size_limit_ok": size_limits.get("ok", True),
        "max_order_size": size_limits.get("max_order_size"),
        "max_order_size_field": size_limits.get("max_order_size_field"),
        "max_stop_size": size_limits.get("max_stop_size"),
        "max_order_notional_usdt": size_limits.get("max_order_notional_usdt"),
        "max_stop_notional_usdt": size_limits.get("max_stop_notional_usdt"),
        "stop_trigger_validation": stop_validation,
        "stop_tick_distance_validation": tick_dist_check,
        "orderbook_payload": orderbook_payload,
        "instrument_info": info,
        "error": error,
    }


def place_stop_loss_order(inst_id, side, size, trigger_price, td_mode_override=None, pos_side="",
                          session=None, dry_run_override=None, reference_price=None,
                          instrument_info=None, validate_trigger=True):
    """
    Place a stop-loss order using OKX algo orders.
    """
    active_session = session or trade_session
    td_mode_value = _normalize_value(td_mode_override or td_mode)
    side = _normalize_value(side)
    pos_side = _resolve_pos_side(side, True, _normalize_value(pos_side))
    trigger_price_to_send = trigger_price

    if validate_trigger and reference_price is not None:
        validation = validate_stop_trigger_price(
            inst_id,
            side,
            reference_price,
            trigger_price,
            instrument_info=instrument_info,
        )
        if not validation.get("valid"):
            print(
                "ERROR: stop_loss_validation_failed "
                f"{inst_id} side={side} trigger={trigger_price} reason={validation.get('reason')}"
            )
            return {
                "code": "STOP_TRIGGER_INVALID",
                "msg": validation.get("reason") or "invalid stop trigger",
                "data": [],
                "validation": validation,
            }
        trigger_price_to_send = validation.get("rounded_trigger_px")

    if _should_dry_run(dry_run_override):
        pos_info = f", posSide={pos_side}" if pos_side else ""
        print(f"DRY RUN: stop loss {side} {inst_id}, size={size}, trigger={trigger_price_to_send}{pos_info}")
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
            slTriggerPx=str(trigger_price_to_send),
            slOrdPx="-1",
        )
    except Exception as exc:
        print(f"ERROR: Failed to place stop loss order: {exc}")
        return None

    if not _ensure_ok(response, "OKX stop loss order"):
        return response

    algo_id = response.get("data", [{}])[0].get("algoId", "")
    pos_info = f", posSide={pos_side}" if pos_side else ""
    print(f"OK: Stop loss placed ({side} {inst_id}, size={size}, trigger={trigger_price_to_send}{pos_info}) id={algo_id}")
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
        orderbook_payload, err = _get_orderbook_payload(inst_id)
        if not orderbook_payload:
            print(f"ERROR: {err}")
            return None

    info = instrument_info
    if info is None:
        info = _fetch_instrument_info(inst_id)

    entry_price, quantity, stop_price = get_trade_details(
        orderbook_payload,
        direction="long" if entry_side == "buy" else "short",
        capital=capital,
        instrument_info=info,
    )

    if size_override is not None:
        try:
            quantity = float(size_override)
        except (TypeError, ValueError):
            pass

    if enforce_lot_size:
        quantity = _adjust_quantity_to_lot_size(inst_id, quantity, instrument_info=info)

    if entry_price <= 0 or quantity <= 0 or stop_price <= 0:
        print(f"ERROR: Invalid trade details (entry={entry_price}, quantity={quantity}, stop={stop_price}).")
        return None

    order_type = "limit" if limit_offset and limit_offset != 0 else "market"
    size_limits = _validate_order_size_limits(
        inst_id,
        quantity,
        entry_price,
        info,
        order_type=order_type,
        place_stop=place_stop,
    )
    details = {
        "inst_id": inst_id,
        "direction": direction,
        "entry_side": entry_side,
        "entry_price": entry_price,
        "quantity": quantity,
        "stop_price": stop_price,
        "size_limit_ok": size_limits.get("ok", True),
        "max_order_size": size_limits.get("max_order_size"),
        "max_order_size_field": size_limits.get("max_order_size_field"),
        "max_stop_size": size_limits.get("max_stop_size"),
        "max_order_notional_usdt": size_limits.get("max_order_notional_usdt"),
        "max_stop_notional_usdt": size_limits.get("max_stop_notional_usdt"),
    }

    if not size_limits.get("ok", True):
        error = size_limits.get("error") or "order size exceeds OKX instrument limit"
        print(f"ERROR: {error}")
        return {"entry": None, "stop": None, "details": details, "ok": False, "error": error}

    stop_side = "sell" if entry_side == "buy" else "buy"
    stop_validation = None
    if place_stop:
        stop_validation = validate_stop_trigger_price(
            inst_id,
            stop_side,
            entry_price,
            stop_price,
            instrument_info=info,
        )
        details["stop_trigger_validation"] = stop_validation
        if not stop_validation.get("valid"):
            error = f"stop_loss_preflight_failed: {stop_validation.get('reason')}"
            print(f"ERROR: {error} details={stop_validation.get('metadata')}")
            return {
                "entry": None,
                "stop": None,
                "details": details,
                "ok": False,
                "error": error,
                "error_type": "stop_loss_preflight_failed",
            }
        stop_price = stop_validation.get("rounded_trigger_px")
        details["stop_price"] = stop_price

        if _block_entry_if_stop_invalid():
            min_ticks = _get_min_stop_distance_ticks()
            tick_dist = validate_stop_tick_distance(
                inst_id, stop_side, entry_price, stop_price,
                instrument_info=info, min_ticks=min_ticks,
            )
            details["stop_tick_distance_preflight"] = tick_dist
            if not tick_dist["valid"]:
                error = (
                    f"stop_loss_tick_distance_failed: {tick_dist.get('reason')} "
                    f"distance={tick_dist.get('distance_ticks'):.4f} ticks "
                    f"min={tick_dist.get('min_required_ticks')} "
                    f"tickSz={tick_dist.get('tick_size')}"
                    if tick_dist.get("distance_ticks") is not None
                    else f"stop_loss_tick_distance_failed: {tick_dist.get('reason')}"
                )
                print(f"ERROR: {error} inst_id={inst_id}")
                return {
                    "entry": None,
                    "stop": None,
                    "details": details,
                    "ok": False,
                    "error": error,
                    "error_type": "stop_loss_tick_distance_failed",
                }

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

    result = {"entry": entry_res, "stop": None, "details": details, "ok": _is_ok_response(entry_res)}
    if not result["ok"]:
        print("ERROR: Entry order failed; stop order not placed.")
        return result

    if not place_stop:
        return result

    post_entry_reference_price = _extract_order_response_price(entry_res)
    post_entry_reference_source = "entry_response_fill_price" if post_entry_reference_price else "planned_entry_price"
    post_fill_validation = validate_stop_trigger_price(
        inst_id,
        stop_side,
        post_entry_reference_price or entry_price,
        stop_price,
        instrument_info=info,
    )
    details["post_fill_stop_trigger_validation"] = post_fill_validation
    details["post_fill_reference_price_source"] = post_entry_reference_source
    if not post_fill_validation.get("valid"):
        error = f"stop_loss_post_fill_validation_failed: {post_fill_validation.get('reason')}"
        print(f"ERROR: {error} details={post_fill_validation.get('metadata')}")
        result["ok"] = False
        result["error"] = error
        result["error_type"] = "stop_loss_post_fill_validation_failed"
        return result

    if _block_entry_if_stop_invalid():
        min_ticks = _get_min_stop_distance_ticks()
        fill_ref = post_entry_reference_price or entry_price
        post_fill_tick_dist = validate_stop_tick_distance(
            inst_id, stop_side, fill_ref, stop_price,
            instrument_info=info, min_ticks=min_ticks,
        )
        details["post_fill_tick_distance_validation"] = post_fill_tick_dist
        if not post_fill_tick_dist["valid"]:
            error = (
                f"stop_loss_post_fill_tick_distance_failed: {post_fill_tick_dist.get('reason')} "
                f"distance={post_fill_tick_dist.get('distance_ticks'):.4f} ticks "
                f"min={post_fill_tick_dist.get('min_required_ticks')} "
                f"tickSz={post_fill_tick_dist.get('tick_size')} "
                f"fill_price={fill_ref} stop={stop_price}"
                if post_fill_tick_dist.get("distance_ticks") is not None
                else f"stop_loss_post_fill_tick_distance_failed: {post_fill_tick_dist.get('reason')}"
            )
            print(f"ERROR: {error} inst_id={inst_id}")
            result["ok"] = False
            result["error"] = error
            result["error_type"] = "stop_loss_post_fill_validation_failed"
            return result

    stop_res = place_stop_loss_order(
        inst_id,
        side=stop_side,
        size=quantity,
        trigger_price=stop_price,
        td_mode_override=td_mode_override,
        dry_run_override=dry_run_override,
        reference_price=post_entry_reference_price or entry_price,
        instrument_info=info,
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


def _extract_order_response_price(response):
    if not isinstance(response, dict):
        return None
    data_list = response.get("data", [])
    order_data = data_list[0] if data_list else {}
    for key in ("avgPx", "fillPx", "px"):
        parsed = _decimal_from_value(order_data.get(key))
        if parsed is not None and parsed > 0:
            return float(parsed)
    return None


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
        orderbook_payload, err = _get_orderbook_payload(ticker)
        if not orderbook_payload:
            print(f"ERROR: {err}")
            return None

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
