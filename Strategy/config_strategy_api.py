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
from func_strategy_log import get_strategy_logger

# Load environment variables
load_dotenv()

# CONFIG
mode = "demo"  # "demo" or "live"
time_frame = "1m"  # Timeframe for klines (1m, 5m, 15m, 1H, 1D, etc.)
z_score_window = 60  # Z-score calculation window (increased from 21 for stability)
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


def _env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return bool(default)
    return str(raw).strip().lower() in ("1", "true", "yes", "y", "on")

kline_limit = _env_int("STATBOT_STRATEGY_KLINE_LIMIT", 10080)  # 7 days @ 1m bars (increased from 1440 for statistical validity)
min_equity_filter_usdt = _env_float("STATBOT_STRATEGY_MIN_EQUITY", 0)
settle_ccy_filter = _env_list("STATBOT_STRATEGY_SETTLE_CCY", "USDT")
max_pairs_per_ticker = _env_int("STATBOT_STRATEGY_MAX_PAIRS_PER_TICKER", 10)
min_p_value_filter = _env_float("STATBOT_STRATEGY_MIN_P_VALUE", 1e-8)
max_p_value_filter = _env_float("STATBOT_STRATEGY_MAX_P_VALUE", 0.01)  # Tightened from 0.02 - only top 1% statistical strength
min_zero_crossings = _env_int("STATBOT_STRATEGY_MIN_ZERO_CROSSINGS", 20)  # Increased from 1 - need frequent reversions
min_hedge_ratio = _env_float("STATBOT_STRATEGY_MIN_HEDGE_RATIO", 0.3)
max_hedge_ratio = _env_float("STATBOT_STRATEGY_MAX_HEDGE_RATIO", 3.0)
min_capital_per_leg = _env_float("STATBOT_STRATEGY_MIN_CAPITAL_PER_LEG", 1.0)
liquidity_window = _env_int("STATBOT_STRATEGY_LIQUIDITY_WINDOW", 60)
min_avg_quote_volume = _env_float("STATBOT_STRATEGY_MIN_AVG_QUOTE_VOL", 0)
liquidity_pct = _env_float("STATBOT_STRATEGY_LIQUIDITY_PCT", 0)
if liquidity_pct < 0:
    liquidity_pct = 0.0
if liquidity_pct > 1:
    liquidity_pct = 1.0
fast_path_enabled = _env_bool("STATBOT_STRATEGY_FAST_PATH", True)
corr_min_filter = _env_float("STATBOT_STRATEGY_CORR_MIN", 0.60 if fast_path_enabled else 0.0)  # Increased from 0.2 - need strong correlation
corr_lookback = _env_int("STATBOT_STRATEGY_CORR_LOOKBACK", 0)

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

def log_strategy_config(logger=None, to_console=False):
    logger = logger or get_strategy_logger()
    lines = [
        "OKX Strategy Configuration",
        f"Mode: {'DEMO' if is_demo else 'LIVE'}",
        f"Timeframe: {time_frame}",
        f"Kline limit: {kline_limit}",
        f"Z-score window: {z_score_window}",
    ]
    if min_equity_filter_usdt > 0:
        lines.append(f"Min equity filter: {min_equity_filter_usdt:.2f} USDT")
    if settle_ccy_filter:
        lines.append(f"Settle CCY filter: {', '.join(settle_ccy_filter)}")
    lines.append(
        "Pair filters: max_per_ticker={0}, p_value=[{1}, {2}], "
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
    if min_avg_quote_volume > 0 or liquidity_pct > 0:
        lines.append(
            "Liquidity filter: window={0} bars, min_avg_quote_vol={1}, percentile={2}".format(
                liquidity_window,
                min_avg_quote_volume,
                liquidity_pct,
            )
        )
    if fast_path_enabled or corr_min_filter > 0:
        lines.append(
            "Fast path: enabled={0}, corr_min={1}, corr_lookback={2}".format(
                fast_path_enabled,
                corr_min_filter,
                corr_lookback,
            )
        )
    logger.info(" | ".join(lines))
    if to_console:
        print("Strategy config logged.")
