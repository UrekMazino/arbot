"""
    OKX EXECUTION CONFIGURATION
    API Documentation: https://www.okx.com/docs-v5/en/#public-data-rest-api-get-instruments
"""

import os
import json
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

ENV_PATH = Path(__file__).resolve().parent / ".env"
if load_dotenv:
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)
    else:
        load_dotenv()

from okx.PublicData import PublicAPI
from okx.Account import AccountAPI
from okx.Trade import TradeAPI
from okx.MarketData import MarketAPI


def _env_flag(name, default=False):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    value = str(raw).strip().lower()
    if value in ("1", "true", "yes", "y", "on"):
        return True
    if value in ("0", "false", "no", "n", "off"):
        return False
    return default


def _env_list(name, default=""):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        raw = default
    items = [part.strip().upper() for part in str(raw).split(",") if part.strip()]
    if not items or "ALL" in items:
        return []
    return items


def _env_str(name, default=""):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return str(default)
    return str(raw).strip()


def _env_int(name, default=0, minimum=None):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        value = int(default)
    else:
        try:
            value = int(float(raw))
        except (TypeError, ValueError):
            value = int(default)
    if minimum is not None and value < minimum:
        value = minimum
    return value


def _env_float(name, default=0.0, minimum=None):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        value = float(default)
    else:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = float(default)
    if minimum is not None and value < minimum:
        value = minimum
    return value

def save_active_pair(t1, t2):
    """Save the current active pair to active_pair.json."""
    data = {"ticker_1": t1, "ticker_2": t2}
    try:
        active_pair_path = Path(active_pair_file)
        active_pair_path.parent.mkdir(parents=True, exist_ok=True)
        with active_pair_path.open("w") as f:
            json.dump(data, f)
        return True
    except Exception as e:
        print(f"Error saving active pair: {e}")
        return False


def _load_rounding_for_ticker(inst_id):
    price_rounding = 2
    quantity_rounding = 0
    if skip_instrument_fetch or not inst_id:
        return price_rounding, quantity_rounding

    try:
        response = public_session.get_instruments(instType=inst_type, instId=inst_id)
        if response.get("code") == "0" and response.get("data"):
            instrument = response["data"][0]
            tick_sz = instrument.get("tickSz", "0.01")
            price_rounding = len(tick_sz.split(".")[-1]) if "." in tick_sz else 0
            lot_sz = instrument.get("lotSz", "1")
            quantity_rounding = len(lot_sz.split(".")[-1]) if "." in lot_sz else 0
    except Exception as exc:
        print(f"Warning: Could not fetch dynamic rounding for {inst_id}: {exc}")
    return price_rounding, quantity_rounding


def refresh_dynamic_rounding(inst_id_1=None, inst_id_2=None):
    """Refresh price and quantity roundings for the active pair."""
    global rounding_ticker_1, rounding_ticker_2
    global quantity_rounding_ticker_1, quantity_rounding_ticker_2

    target_t1 = str(inst_id_1 or ticker_1 or "").strip().upper()
    target_t2 = str(inst_id_2 or ticker_2 or "").strip().upper()
    if not target_t1 or not target_t2:
        return False

    rounding_ticker_1, quantity_rounding_ticker_1 = _load_rounding_for_ticker(target_t1)
    rounding_ticker_2, quantity_rounding_ticker_2 = _load_rounding_for_ticker(target_t2)
    return True


def _sync_runtime_pair_to_modules():
    """Push the current active pair into modules that imported config values by value."""
    module_names = (
        "__main__",
        "main_execution",
        "func_get_zscore",
        "func_price_calls",
        "func_close_positions",
        "func_trade_management",
        "func_calculation",
        "config_ws_connect",
        "check_balance",
    )
    for module_name in module_names:
        module = sys.modules.get(module_name)
        if module is None:
            continue
        if hasattr(module, "ticker_1"):
            setattr(module, "ticker_1", ticker_1)
        if hasattr(module, "ticker_2"):
            setattr(module, "ticker_2", ticker_2)
        if hasattr(module, "signal_positive_ticker"):
            setattr(module, "signal_positive_ticker", signal_positive_ticker)
        if hasattr(module, "signal_negative_ticker"):
            setattr(module, "signal_negative_ticker", signal_negative_ticker)
        if hasattr(module, "rounding_ticker_1"):
            setattr(module, "rounding_ticker_1", rounding_ticker_1)
        if hasattr(module, "rounding_ticker_2"):
            setattr(module, "rounding_ticker_2", rounding_ticker_2)
        if hasattr(module, "quantity_rounding_ticker_1"):
            setattr(module, "quantity_rounding_ticker_1", quantity_rounding_ticker_1)
        if hasattr(module, "quantity_rounding_ticker_2"):
            setattr(module, "quantity_rounding_ticker_2", quantity_rounding_ticker_2)


def set_runtime_active_pair(t1, t2, persist=True):
    """
    Update the active pair for the running process and optionally persist it.

    This keeps the in-memory execution modules in sync after a live pair switch.
    """
    global ticker_1, ticker_2, signal_positive_ticker, signal_negative_ticker

    next_t1 = str(t1 or "").strip().upper()
    next_t2 = str(t2 or "").strip().upper()
    if not next_t1 or not next_t2 or next_t1 == next_t2:
        return False

    if persist and not save_active_pair(next_t1, next_t2):
        return False

    ticker_1 = next_t1
    ticker_2 = next_t2
    signal_positive_ticker = ticker_2
    signal_negative_ticker = ticker_1
    refresh_dynamic_rounding(next_t1, next_t2)
    _sync_runtime_pair_to_modules()
    return True


# CONFIG VARIABLES
flag = "1" if _env_flag("OKX_FLAG", True) else "0"  # "1" = demo, "0" = live
mode = "demo" if flag == "1" else "live"  # "demo" or "live"

# Default tickers
default_ticker_1 = _env_str("STATBOT_DEFAULT_TICKER_1", "ETH-USDT-SWAP").upper()
default_ticker_2 = _env_str("STATBOT_DEFAULT_TICKER_2", "SOL-USDT-SWAP").upper()

ticker_1 = default_ticker_1
ticker_2 = default_ticker_2
lock_on_pair = _env_flag("STATBOT_LOCK_ON_PAIR", False)
allowed_settle_ccy = _env_list("STATBOT_EXECUTION_SETTLE_CCY", "USDT")

# Try to load active pair from JSON if it exists (unless locked in env)
active_pair_file = str(Path(__file__).resolve().parent / "state" / "active_pair.json")
lock_pair_raw = os.getenv("STATBOT_LOCK_PAIR", "").strip()
lock_pair_active = False
if lock_on_pair and lock_pair_raw:
    try:
        lock_pair = json.loads(lock_pair_raw)
        lock_t1 = str(lock_pair.get("ticker_1") or "").strip()
        lock_t2 = str(lock_pair.get("ticker_2") or "").strip()
        if lock_t1 and lock_t2:
            ticker_1 = lock_t1
            ticker_2 = lock_t2
            lock_pair_active = True
            if os.getenv("STATBOT_MANAGED") == "1":
                print(f"Lock pair override enabled: {ticker_1}/{ticker_2}")
        else:
            print("Warning: STATBOT_LOCK_PAIR missing ticker_1 or ticker_2; ignoring.")
    except Exception as exc:
        print(f"Warning: Failed to parse STATBOT_LOCK_PAIR ({exc}); ignoring.")
elif lock_pair_raw and not lock_on_pair:
    pass

if not lock_pair_active and os.path.exists(active_pair_file):
    try:
        with open(active_pair_file, "r") as f:
            active_data = json.load(f)
            ticker_1 = active_data.get("ticker_1", default_ticker_1)
            ticker_2 = active_data.get("ticker_2", default_ticker_2)
    except Exception:
        ticker_1 = default_ticker_1
        ticker_2 = default_ticker_2

signal_positive_ticker = ticker_2
signal_negative_ticker = ticker_1
inst_type = _env_str("STATBOT_INST_TYPE", "SWAP").upper()
depth = _env_int("STATBOT_DEPTH", 5, minimum=1)  # 5 uses books5, any other value uses books
td_mode = _env_str("STATBOT_TD_MODE", "cross").lower()  # "cross" or "isolated"
if td_mode not in ("cross", "isolated"):
    td_mode = "cross"
pos_mode = _env_str("STATBOT_POS_MODE", "long_short").lower()  # "net" or "long_short" (hedged)
if pos_mode not in ("net", "long_short"):
    pos_mode = "long_short"
dry_run = _env_flag("STATBOT_DRY_RUN", False)  # When True, execution calls will not place or cancel live orders.
use_fresh_orderbook = _env_flag("STATBOT_USE_FRESH_ORDERBOOK", False)  # Reserved for fresh snapshot enforcement.
max_snapshot_age_seconds = _env_int("STATBOT_MAX_SNAPSHOT_AGE_SECONDS", 15, minimum=0)
stop_loss_fail_safe = _env_float("STATBOT_STOP_LOSS_FAIL_SAFE", 0.03, minimum=0.0)
default_leverage = _env_int("STATBOT_DEFAULT_LEVERAGE", 1, minimum=1)
max_cycles = _env_int("STATBOT_MAX_CYCLES", 0, minimum=0)
# Default roundings (will be updated if possible)
rounding_ticker_1 = 1
rounding_ticker_2 = 2
quantity_rounding_ticker_1 = 4
quantity_rounding_ticker_2 = 3

# Fetch dynamic rounding info from OKX
try:
    # Note: public_session is already initialized below, so we move this check after session init
    pass 
except Exception:
    pass

z_score_window = _env_int("STATBOT_Z_SCORE_WINDOW", 21, minimum=2)
                     # 21 bars is valid for 1m high-frequency data when:
                     # - Used only for entry timing (not sole cointegration validation)
                     # - Cointegration validated separately on sufficient window
                     # - Regime filter or other validation exists
limit_order_basis = _env_flag("STATBOT_LIMIT_ORDER_BASIS", True)  # Place entries with limit orders when True.
tradeable_capital_usdt = _env_float("STATBOT_TRADEABLE_CAPITAL_USDT", 2000.0, minimum=0.0)

# SIGNAL GENERATION (Issue #11 fix: robust entry/exit logic with persistence requirement)
ENTRY_Z = 2.0  # Require Z-score to reach ±2.0 (2 standard deviations) for entry
ENTRY_Z_MAX = 3.0  # Maximum threshold - don't enter if too extreme (regime break)
ENTRY_Z = _env_float("STATBOT_ENTRY_Z", ENTRY_Z, minimum=0.0)
ENTRY_Z_MAX = _env_float("STATBOT_ENTRY_Z_MAX", ENTRY_Z_MAX, minimum=0.0)
if ENTRY_Z_MAX < ENTRY_Z:
    ENTRY_Z_MAX = ENTRY_Z

# Fee-adjusted exit calculation
# OKX fees: taker ~0.05%, slippage ~0.02% = 0.07% round-trip per leg
# With hedge ratio ~1.0, total cost ~0.14% of notional
# EXIT_Z must ensure reversion covers fees + profit margin
def calculate_fee_adjusted_exit_z(hedge_ratio=1.0, entry_z=2.0, fees_pct=0.0007, profit_margin=1.2):
    """
    Calculate minimum Z-score reversion needed for profitable exit after fees.

    Args:
        hedge_ratio: Hedge ratio from cointegration (default 1.0)
        entry_z: Entry Z-score threshold (default 2.0)
        fees_pct: Round-trip fees as decimal (0.07% = 0.0007)
        profit_margin: Multiplier for profit target (1.2 = 20% buffer)

    Returns:
        float: Minimum exit Z-score
    """
    # Fee cost in Z-score units (approximate)
    # Each leg incurs fees, so multiply by hedge ratio
    fee_in_zscore = fees_pct * (1 + abs(hedge_ratio)) * entry_z

    # Exit must revert past fees to be profitable
    # Add profit margin buffer
    exit_z = fee_in_zscore * profit_margin

    # Ensure minimum meaningful reversion
    return max(exit_z, 0.3)

EXIT_Z = 0.35  # Fee-adjusted exit (increased from 0.5 to ensure profitability after 0.14% costs)
               # This ensures ~0.21% profit margin after fees with 1.0 hedge ratio
MIN_PERSIST_BARS = 4  # Require signal to persist for 4 bars before entering (4 minutes @ 1m)
                      # Increased from 3 to reduce false entries and improve conviction
ENTRY_Z_TOLERANCE = 0.05  # Treat tiny near-threshold misses (for example 1.98 vs 2.00) as valid.
ENTRY_MIN_QUALIFIED_BARS = 0  # 0 = adaptive default of MIN_PERSIST_BARS - 1.
ENTRY_EXTREME_CLEAN_BARS = 2  # Clean in-band checks required after returning from ENTRY_Z_MAX breach.
MAX_CONSECUTIVE_LOSSES = 2  # Move pair to graveyard after 2 consecutive losses
                            # Prevents repeated losses on deteriorating pairs
EXIT_Z = _env_float("STATBOT_EXIT_Z", EXIT_Z, minimum=0.0)
MIN_PERSIST_BARS = _env_int("STATBOT_MIN_PERSIST_BARS", MIN_PERSIST_BARS, minimum=1)
ENTRY_Z_TOLERANCE = _env_float("STATBOT_ENTRY_Z_TOLERANCE", ENTRY_Z_TOLERANCE, minimum=0.0)
ENTRY_MIN_QUALIFIED_BARS = _env_int("STATBOT_ENTRY_MIN_QUALIFIED_BARS", ENTRY_MIN_QUALIFIED_BARS, minimum=0)
ENTRY_EXTREME_CLEAN_BARS = _env_int("STATBOT_ENTRY_EXTREME_CLEAN_BARS", ENTRY_EXTREME_CLEAN_BARS, minimum=0)
MAX_CONSECUTIVE_LOSSES = _env_int("STATBOT_MAX_CONSECUTIVE_LOSSES", MAX_CONSECUTIVE_LOSSES, minimum=1)

# PAIR HEALTH & MONITORING (conintegration_pair_switching.txt recommendations)
HEALTH_CHECK_INTERVAL = 3600  # Check health every 1 hour (3600 seconds)
STATUS_UPDATE_INTERVAL = 60   # Trading status update every 1 minute (60 seconds)
P_VALUE_CRITICAL = 0.15        # More realistic statistical threshold for switching
ZERO_CROSSINGS_MIN = 15       # Minimum zero crossings to consider a pair healthy
CORRELATION_MIN = 0.60        # Minimum price correlation
TREND_CRITICAL = 0.002        # Maximum allowed spread trend
Z_SCORE_CRITICAL = 6.0        # Maximum allowed Z-score before switching

max_drawdown_pct = 0.05  # Circuit breaker: exit if cumulative loss exceeds 5% of capital
HEALTH_CHECK_INTERVAL = _env_int("STATBOT_HEALTH_CHECK_INTERVAL", HEALTH_CHECK_INTERVAL, minimum=1)
STATUS_UPDATE_INTERVAL = _env_int("STATBOT_STATUS_UPDATE_INTERVAL", STATUS_UPDATE_INTERVAL, minimum=1)
P_VALUE_CRITICAL = _env_float("STATBOT_P_VALUE_CRITICAL", P_VALUE_CRITICAL, minimum=0.0)
if P_VALUE_CRITICAL > 1.0:
    P_VALUE_CRITICAL = 1.0
ZERO_CROSSINGS_MIN = _env_int("STATBOT_ZERO_CROSSINGS_MIN", ZERO_CROSSINGS_MIN, minimum=0)
COINT_ZERO_CROSS_THRESHOLD_RATIO = _env_float("STATBOT_COINT_ZERO_CROSS_THRESHOLD_RATIO", 0.1, minimum=0.0)
CORRELATION_MIN = _env_float("STATBOT_CORRELATION_MIN", CORRELATION_MIN, minimum=0.0)
if CORRELATION_MIN > 1.0:
    CORRELATION_MIN = 1.0
TREND_CRITICAL = _env_float("STATBOT_TREND_CRITICAL", TREND_CRITICAL, minimum=0.0)
Z_SCORE_CRITICAL = _env_float("STATBOT_Z_SCORE_CRITICAL", Z_SCORE_CRITICAL, minimum=0.0)
max_drawdown_pct = _env_float("STATBOT_MAX_DRAWDOWN_PCT", max_drawdown_pct, minimum=0.0)
if max_drawdown_pct > 1.0:
    max_drawdown_pct = 1.0

# ENVIRONMENT SETTINGS
ws_url = "wss://wspap.okx.com:8443/ws/v5/public" if mode == "demo" else "wss://ws.okx.com:8443/ws/v5/public"

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
    debug=False
)

trade_session = TradeAPI(
    api_key=api_key,
    api_secret_key=api_secret,
    passphrase=passphrase,
    flag=flag,
    debug=False
)

# Added env-backed timeout to prevent hanging on network issues
# Since the SDK constructor doesn't accept requests_options/timeout, 
# we set it directly on the session objects (which are httpx.Client subclasses).
session_timeout_seconds = _env_float("STATBOT_OKX_SESSION_TIMEOUT_SECONDS", 10.0, minimum=0.1)
for session in [public_session, market_session, account_session, trade_session]:
    session.timeout = session_timeout_seconds

skip_instrument_fetch = _env_flag("STATBOT_SKIP_INSTRUMENT_FETCH", False)

# DYNAMIC ROUNDING FETCH
refresh_dynamic_rounding()
