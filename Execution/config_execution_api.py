"""
    OKX EXECUTION CONFIGURATION
    API Documentation: https://www.okx.com/docs-v5/en/#public-data-rest-api-get-instruments
"""

import os

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from okx.PublicData import PublicAPI
from okx.Account import AccountAPI
from okx.Trade import TradeAPI
from okx.MarketData import MarketAPI

# CONFIG VARIABLES
mode = "demo"  # "demo" or "live"
ticker_1 = "ASTER-USDT-SWAP"
ticker_2 = "ETHFI-USDT-SWAP"
signal_positive_ticker = ticker_2
signal_negative_ticker = ticker_1
inst_type = "SWAP"
depth = 5  # 5 uses books5, any other value uses books
td_mode = "isolated"  # "cross" or "isolated"
pos_mode = "long_short"  # "net" or "long_short" (hedged)
dry_run = False  # When True, execution calls will not place or cancel live orders.
use_fresh_orderbook = False  # True fetches a new snapshot right before order placement.
max_snapshot_age_seconds = 15  # Reuse snapshot only if it is this fresh or newer.
stop_loss_fail_safe = 0.15
default_leverage = 1  # Default leverage for set_leverage calls.
max_cycles = 0  # 0 = run indefinitely; set to 1 for a single cycle.
rounding_ticker_1 = 2
rounding_ticker_2 = 2
quantity_rounding_ticker_1 = 3
quantity_rounding_ticker_2 = 3
z_score_window = 21  # Z-score calculation window
limit_order_basis = True  # Place entries with limit orders when True.
tradeable_capital_usdt = 2000  # Total tradeable capital to split across pairs.
signal_trigger_thresh = 1  # Z-score threshold for triggering signals.

# ENVIRONMENT SETTINGS
flag = "1" if mode == "demo" else "0"  # "1" = demo, "0" = live
ws_url = "wss://wspap.okx.com:8443/ws/v5/public" if mode == "demo" else "wss://ws.okx.com:8443/ws/v5/public"

# Load credentials
if load_dotenv:
    load_dotenv()

api_key = os.getenv("OKX_API_KEY", "")
api_secret = os.getenv("OKX_API_SECRET", "")
passphrase = os.getenv("OKX_PASSPHRASE", "")

# SESSION ACTIVATION (public endpoints only)
public_session = PublicAPI(flag=flag, debug=False)
market_session = MarketAPI(flag=flag, debug=False)
account_session = AccountAPI(
    api_key=api_key,
    api_secret_key=api_secret,
    passphrase=passphrase,
    flag=flag,
    debug=False,
)

trade_session = TradeAPI(
    api_key=api_key,
    api_secret_key=api_secret,
    passphrase=passphrase,
    flag=flag,
    debug=False,
)
