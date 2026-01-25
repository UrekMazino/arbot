from config_execution_api import (
    ticker_1,
    dry_run,
    rounding_ticker_1,
    market_session,
)
from func_execution_calls import place_limit_order, cancel_order, get_open_orders, get_order_history


def _get_last_price(inst_id):
    try:
        response = market_session.get_ticker(instId=inst_id)
    except Exception as exc:
        print(f"ERROR: Failed to fetch ticker: {exc}")
        return None

    if response.get("code") != "0":
        print(f"ERROR: OKX ticker failed: {response.get('msg')}")
        return None

    data = response.get("data", [])
    if not data:
        return None

    last = data[0].get("last")
    try:
        return float(last)
    except (TypeError, ValueError):
        return None


def test_demo_order_flow():
    print("OKX demo order flow")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE/DEMO ORDERS'}")

    last_price = _get_last_price(ticker_1)
    if last_price is None:
        if dry_run:
            last_price = 100.0
            print("WARNING: Using fallback price for dry-run.")
        else:
            print("ERROR: Unable to fetch last price; aborting order flow.")
            return

    limit_price = round(last_price * 0.98, rounding_ticker_1)
    print(f"Using limit price: {limit_price} (last={last_price})")

    order_res = place_limit_order(
        ticker_1,
        side="buy",
        size=1,
        price=limit_price,
    )

    if not order_res:
        print("ERROR: No response from place_limit_order.")
        return

    if order_res.get("dry_run"):
        print("Dry-run response received; no order placed.")
        return

    order_id = order_res.get("data", [{}])[0].get("ordId", "")
    if not order_id:
        print("ERROR: No order ID returned.")
        return

    open_orders = get_open_orders(ticker_1)
    open_count = len(open_orders) if isinstance(open_orders, list) else 0
    print(f"Open orders: {open_count}")

    cancel_order(ticker_1, ord_id=order_id)

    history = get_order_history(ticker_1, limit=5)
    if isinstance(history, list):
        print(f"Order history (last 5): {history}")
    else:
        print("Order history not available.")


if __name__ == "__main__":
    test_demo_order_flow()
