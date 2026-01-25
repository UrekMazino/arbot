from scipy.stats import false_discovery_control

from config_execution_api import account_session
from config_execution_api import signal_positive_ticker
from config_execution_api import signal_negative_ticker
from config_execution_api import signal_trigger_thresh
from config_execution_api import tradeable_capital_usdt
from config_execution_api import limit_order_basis
from func_price_calls import get_ticker_trade_liquidity
from func_get_zscore import get_latest_zscore
from func_execution_calls import initialise_order_execution
from func_order_review import check_order
import time
import math

# Manage new trade assessment and order placing
def manage_new_trades(kill_switch):

    # Set variables
    order_long_id = ""
    order_short_id = ""
    signal_side = ""
    hot = False

    # Get and save the latest z-score
    zscore, signal_sign_positive = get_latest_zscore()

    # Filter out NaN values and get the latest valid z-score
    valid_zscores = [z for z in zscore if not math.isnan(z)]
    latest_zscore = valid_zscores[-1]
    # Switch to how if meets signal threshold
    # Note: you can add in coint-flag check too if you want extra vigilence
    if abs(latest_zscore) >= signal_trigger_thresh:

        # Activate hot trigger
        hot = True
        print(f"Hot trigger activated: {signal_sign_positive} @ {latest_zscore:.4f}")
        print("Placing and monitoring existing orders...")

    # Place and manage trades
    if hot and kill_switch == 0:

        # Get the trade history for liquidity
        avg_liquidity_ticker_p, last_price_p = get_ticker_trade_liquidity(signal_positive_ticker)
        avg_liquidity_ticker_n, last_price_n = get_ticker_trade_liquidity(signal_negative_ticker)
        print(f"avg_liquidity_ticker_p: {avg_liquidity_ticker_p:.4f}, avg_liquidity_ticker_n: {avg_liquidity_ticker_n}")

    if valid_zscores:

        print(f"Latest Z-Score: {latest_zscore:.4f}, Signal Positive: {signal_sign_positive}")
    else:
        print("No valid z-scores yet (insufficient data for rolling window calculation)")
        return kill_switch