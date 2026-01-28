"""
    OKX API CONFIGURATION
    API Documentation: https://www.okx.com/docs-v5/en/

    Install SDK: pip install python-okx
"""

import os
from dotenv import load_dotenv
import okx.Account as Account
import okx.MarketData as MarketData
import okx.Trade as Trade
import okx.PublicData as PublicData

# Load environment variables
load_dotenv()

# CONFIG
mode = "demo"  # "demo" or "live"
time_frame = "1m"  # Timeframe for klines (1m, 5m, 15m, 1H, 1D, etc.)
z_score_window = 21  # Z-score calculation window
def _env_float(name, default):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return float(default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def _env_int(name, default):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return int(default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return int(default)


def _env_list(name, default=""):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        raw = default
    items = [part.strip().upper() for part in str(raw).split(",") if part.strip()]
    if not items or "ALL" in items:
        return []
    return items

kline_limit = _env_int("STATBOT_STRATEGY_KLINE_LIMIT", 1440)
min_equity_filter_usdt = _env_float("STATBOT_STRATEGY_MIN_EQUITY", 0.0)
settle_ccy_filter = _env_list("STATBOT_STRATEGY_SETTLE_CCY", "USDT")
max_pairs_per_ticker = _env_int("STATBOT_STRATEGY_MAX_PAIRS_PER_TICKER", 5)
min_p_value_filter = _env_float("STATBOT_STRATEGY_MIN_P_VALUE", 1e-8)
max_p_value_filter = _env_float("STATBOT_STRATEGY_MAX_P_VALUE", 0.02)
min_zero_crossings = _env_int("STATBOT_STRATEGY_MIN_ZERO_CROSSINGS", 1)
min_hedge_ratio = _env_float("STATBOT_STRATEGY_MIN_HEDGE_RATIO", 0.3)
max_hedge_ratio = _env_float("STATBOT_STRATEGY_MAX_HEDGE_RATIO", 3.0)
min_capital_per_leg = _env_float("STATBOT_STRATEGY_MIN_CAPITAL_PER_LEG", 1.0)

# API CREDENTIALS from .env
api_key = os.getenv("OKX_API_KEY", "")
api_secret = os.getenv("OKX_API_SECRET", "")
passphrase = os.getenv("OKX_PASSPHRASE", "")
flag = os.getenv("OKX_FLAG", "1")  # "0" = live, "1" = demo

# Determine if using demo/simulated trading
is_demo = (flag == "1" or mode == "demo")

# SESSION ACTIVATION
# Public endpoints (no auth required)
public_session = PublicData.PublicAPI(
    flag=flag,
    debug=False
)

market_session = MarketData.MarketAPI(
    flag=flag,
    debug=False
)

# Private endpoints (require authentication)
account_session = Account.AccountAPI(
    api_key=api_key,
    api_secret_key=api_secret,
    passphrase=passphrase,
    flag=flag,
    debug=False
)

trade_session = Trade.TradeAPI(
    api_key=api_key,
    api_secret_key=api_secret,
    passphrase=passphrase,
    flag=flag,
    debug=False
)

# Display configuration
print(f"{'='*60}")
print(f"OKX API Configuration")
print(f"{'='*60}")
print(f"Mode: {'DEMO/Simulated Trading' if is_demo else 'LIVE Trading'}")
print(f"Timeframe: {time_frame}")
print(f"Kline Limit: {kline_limit}")
print(f"Z-Score Window: {z_score_window}")
if min_equity_filter_usdt > 0:
    print(f"Min Equity Filter: {min_equity_filter_usdt:.2f} USDT")
if settle_ccy_filter:
    print(f"Settle CCY Filter: {', '.join(settle_ccy_filter)}")
print(
    "Pair Filters: max_per_ticker={0}, p_value=[{1}, {2}], "
    "min_zero_crossings={3}, hedge_ratio=[{4}, {5}], min_capital_per_leg={6}".format(
        max_pairs_per_ticker,
        min_p_value_filter,
        max_p_value_filter,
        min_zero_crossings,
        min_hedge_ratio,
        max_hedge_ratio,
        min_capital_per_leg,
    )
)
print(f"{'='*60}\n")
