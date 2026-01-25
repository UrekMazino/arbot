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
kline_limit = 200  # Number of candles to fetch
z_score_window = 21  # Z-score calculation window

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
print(f"{'='*60}\n")
