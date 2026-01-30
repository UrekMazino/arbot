import logging
import time

from config_execution_api import trade_session, inst_type

logger = logging.getLogger(__name__)

_logged_order_ids = set()


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def log_order_fills(order_id, inst_id, max_wait_seconds=2.0, poll_interval=0.5):
    if not order_id or not inst_id:
        return None
    if order_id in _logged_order_ids:
        return None

    deadline = time.time() + max_wait_seconds
    fills = []
    while time.time() < deadline:
        try:
            response = trade_session.get_fills(
                instType=inst_type,
                instId=inst_id,
                ordId=order_id,
                limit=100,
            )
        except Exception as exc:
            logger.warning("Fill lookup failed for %s ordId=%s: %s", inst_id, order_id, exc)
            return None

        if response.get("code") == "0":
            fills = response.get("data", [])
            if fills:
                break
        time.sleep(poll_interval)

    if not fills:
        logger.debug("No fills returned yet for %s ordId=%s", inst_id, order_id)
        return None

    total_qty = sum(_safe_float(fill.get("fillSz")) for fill in fills)
    total_notional = sum(
        _safe_float(fill.get("fillSz")) * _safe_float(fill.get("fillPx"))
        for fill in fills
    )
    avg_px = total_notional / total_qty if total_qty > 0 else 0.0
    total_fee = sum(abs(_safe_float(fill.get("fee"))) for fill in fills)
    total_pnl = sum(_safe_float(fill.get("pnl")) for fill in fills)

    logger.info(
        "Fills for %s ordId=%s: count=%d qty=%.6f avg_px=%.6f fee=%.6f pnl=%.6f",
        inst_id,
        order_id,
        len(fills),
        total_qty,
        avg_px,
        total_fee,
        total_pnl,
    )

    for fill in fills:
        logger.debug(
            "Fill detail: instId=%s ordId=%s tradeId=%s side=%s posSide=%s px=%s sz=%s fee=%s feeCcy=%s pnl=%s",
            fill.get("instId"),
            fill.get("ordId"),
            fill.get("tradeId"),
            fill.get("side"),
            fill.get("posSide"),
            fill.get("fillPx"),
            fill.get("fillSz"),
            fill.get("fee"),
            fill.get("feeCcy"),
            fill.get("pnl"),
        )

    _logged_order_ids.add(order_id)
    return {
        "inst_id": inst_id,
        "order_id": order_id,
        "count": len(fills),
        "qty": total_qty,
        "avg_px": avg_px,
        "fee": total_fee,
        "pnl": total_pnl,
    }
