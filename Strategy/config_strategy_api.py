"""
    OKX API CONFIGURATION
    API Documentation: https://www.okx.com/docs-v5/en/

    Install SDK: pip install python-okx
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import okx.Account as Account
import okx.MarketData as MarketData
import okx.Trade as Trade
import okx.PublicData as PublicData
from func_strategy_log import get_strategy_logger

# Load environment variables
ENV_PATH = Path(__file__).resolve().parents[1] / "Execution" / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    load_dotenv()

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
        return int(float(raw))
    except (TypeError, ValueError):
        return int(default)


def _env_str(name, default=""):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return str(default)
    return str(raw).strip()


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


# CONFIG
flag = _env_str("OKX_FLAG", "1")  # "0" = live, "1" = demo
mode = "demo" if flag == "1" else "live"
time_frame = _env_str("STATBOT_STRATEGY_TIMEFRAME", "1m")
z_score_window = max(2, _env_int("STATBOT_STRATEGY_Z_SCORE_WINDOW", 60))
shared_coint_pvalue_threshold = _env_float("STATBOT_P_VALUE_CRITICAL", 0.15)
if shared_coint_pvalue_threshold < 0:
    shared_coint_pvalue_threshold = 0.0
if shared_coint_pvalue_threshold > 1:
    shared_coint_pvalue_threshold = 1.0
cointegration_zero_cross_threshold_ratio = _env_float("STATBOT_COINT_ZERO_CROSS_THRESHOLD_RATIO", 0.1)
if cointegration_zero_cross_threshold_ratio < 0:
    cointegration_zero_cross_threshold_ratio = 0.0

kline_limit = _env_int("STATBOT_STRATEGY_KLINE_LIMIT", 1440)  # 1 day @ 1m bars; avoid short-window zero-crossing starvation
min_equity_filter_usdt = _env_float("STATBOT_STRATEGY_MIN_EQUITY", 0)
settle_ccy_filter = _env_list("STATBOT_STRATEGY_SETTLE_CCY", "USDT")
max_pairs_per_ticker = _env_int("STATBOT_STRATEGY_MAX_PAIRS_PER_TICKER", 10)
min_p_value_filter = _env_float("STATBOT_STRATEGY_MIN_P_VALUE", 1e-8)
max_p_value_filter = _env_float("STATBOT_STRATEGY_MAX_P_VALUE", 0.01)  # Tightened from 0.02 - only top 1% statistical strength
min_zero_crossings = _env_int("STATBOT_STRATEGY_MIN_ZERO_CROSSINGS", 3)  # Require frequent mean reversions
min_hedge_ratio = _env_float("STATBOT_STRATEGY_MIN_HEDGE_RATIO", 0.3)
max_hedge_ratio = _env_float("STATBOT_STRATEGY_MAX_HEDGE_RATIO", 3.0)
min_capital_per_leg = _env_float("STATBOT_STRATEGY_MIN_CAPITAL_PER_LEG", 0)
liquidity_window = _env_int("STATBOT_STRATEGY_LIQUIDITY_WINDOW", 60)
min_avg_quote_volume = _env_float("STATBOT_STRATEGY_MIN_AVG_QUOTE_VOL", 0)
liquidity_pct = _env_float("STATBOT_STRATEGY_LIQUIDITY_PCT", 0)
if liquidity_pct < 0:
    liquidity_pct = 0.0
if liquidity_pct > 1:
    liquidity_pct = 1.0
min_orderbook_depth_usdt = _env_float("STATBOT_STRATEGY_MIN_ORDERBOOK_DEPTH", 5000.0)
soft_orderbook_depth_usdt = _env_float(
    "STATBOT_STRATEGY_SOFT_ORDERBOOK_DEPTH",
    min_orderbook_depth_usdt * 0.75,
)
if soft_orderbook_depth_usdt < 0:
    soft_orderbook_depth_usdt = 0.0
if soft_orderbook_depth_usdt >= min_orderbook_depth_usdt:
    soft_orderbook_depth_usdt = min_orderbook_depth_usdt * 0.75
max_orderbook_imbalance = _env_float("STATBOT_STRATEGY_MAX_ORDERBOOK_IMBALANCE", 12.0)
if max_orderbook_imbalance < 0:
    max_orderbook_imbalance = 0.0
min_orderbook_levels = _env_int("STATBOT_STRATEGY_MIN_ORDERBOOK_LEVELS", 7)
fast_path_enabled = _env_bool("STATBOT_STRATEGY_FAST_PATH", True)
corr_min_filter = _env_float("STATBOT_STRATEGY_CORR_MIN", 0.60 if fast_path_enabled else 0.0)  # Increased from 0.2 - need strong correlation
corr_lookback = _env_int("STATBOT_STRATEGY_CORR_LOOKBACK", 0)

# API CREDENTIALS from .env
api_key = os.getenv("OKX_API_KEY", "")
api_secret = os.getenv("OKX_API_SECRET", "")
passphrase = os.getenv("OKX_PASSPHRASE", "")

# Determine if using demo/simulated trading
is_demo = flag == "1"

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
        f"Coint threshold: {shared_coint_pvalue_threshold}",
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
