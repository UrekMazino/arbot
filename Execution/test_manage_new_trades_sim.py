#!/usr/bin/env python3
import sys
import os
import time

# Ensure Execution dir is first on path when running from repo root
sys.path.insert(0, os.getcwd())

import func_trade_management as ftm


# --- Monkeypatch dependencies to simulate a HOT signal ---
def fake_get_latest_zscore(*args, **kwargs):
    # Return a z-score list with latest value well above threshold
    z = [0.0] * 20 + [2.5]
    return z, True


def fake_get_ticker_trade_liquidity(ticker, limit=50, session=None):
    # avg trade size, last price
    return 5.0, 100.0


def fake_initialise_order_execution(ticker, side, capital):
    print(f"Simulated initialise_order_execution: {side} {ticker} for {capital:.2f} USDT")
    return (f"SIM-{ticker}-{side}-ID", "placed")


def fake_check_order(order_id):
    print(f"Simulated check_order for {order_id}")
    return "filled"


# Apply monkeypatches
ftm.get_latest_zscore = fake_get_latest_zscore
ftm.get_ticker_trade_liquidity = fake_get_ticker_trade_liquidity
ftm.initialise_order_execution = fake_initialise_order_execution
ftm.check_order = fake_check_order


if __name__ == "__main__":
    print("Starting simulated manage_new_trades run (will be killed after 5s by the runner if needed)")
    try:
        res = ftm.manage_new_trades(0)
        print("manage_new_trades returned:", res)
    except Exception as exc:
        print("manage_new_trades raised:", type(exc).__name__, exc)
