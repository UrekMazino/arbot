"""
    OKX EXECUTION CONFIGURATION
    API Documentation: https://www.okx.com/docs-v5/en/#public-data-rest-api-get-instruments
"""

import os
import json
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
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


# CONFIG VARIABLES
mode = "demo"  # "demo" or "live"

# Default tickers
default_ticker_1 = "ETH-USD-SWAP"
default_ticker_2 = "ZETA-USDT-SWAP"

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
inst_type = "SWAP"
depth = 5  # 5 uses books5, any other value uses books
td_mode = "cross"  # "cross" or "isolated" - CROSS is more capital efficient for pairs trading
pos_mode = "long_short"  # "net" or "long_short" (hedged)
dry_run = False  # When True, execution calls will not place or cancel live orders.
use_fresh_orderbook = False  # True fetches a new snapshot right before order placement.
max_snapshot_age_seconds = 15  # Reuse snapshot only if it is this fresh or newer.
stop_loss_fail_safe = 0.03  # 3% stop loss (reduced from 15% for proper arbitrage risk management)
default_leverage = 1  # Default leverage for set_leverage calls.
max_cycles = 0  # 0 = run indefinitely; set to 1 for a single cycle.
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

z_score_window = 21  # Z-score calculation window (21 x 1m candles = ~21 minutes)
                     # 21 bars is valid for 1m high-frequency data when:
                     # - Used only for entry timing (not sole cointegration validation)
                     # - Cointegration validated separately on sufficient window
                     # - Regime filter or other validation exists
limit_order_basis = True  # Place entries with limit orders when True.
tradeable_capital_usdt = 2000  # Total tradeable capital to split across pairs.

# PERMANENT BLACKLIST - Tickers that should NEVER be traded
# No cooldown, completely excluded from pair discovery and trading
PERMANENT_BLACKLIST = {
    # Compliance restricted (regional or regulatory issues)
    'BIO-USDT-SWAP': 'Code 51155 - regional restriction',

    # Liquidity failures (dead orderbooks, no bids/asks)
    'MUBARAK-USDT-SWAP': '0 bids in orderbook, illiquid',

    # Consistently poor performers (multiple failed pairs, large losses)
    'ZETA-USDT-SWAP': 'Trap token, 5+ failed pairs, -2.22 USDT total',
    'IMX-USDT-SWAP': '-2.13 USDT single loss, high fees',
    'MAGIC-USDT-SWAP': '-0.30 USDT across 2 trades, unreliable',
}

def is_permanently_blacklisted(ticker):
    """Check if a ticker is permanently blacklisted"""
    return ticker in PERMANENT_BLACKLIST

def get_blacklist_reason(ticker):
    """Get the reason why a ticker is blacklisted"""
    return PERMANENT_BLACKLIST.get(ticker, None)

# SIGNAL GENERATION (Issue #11 fix: robust entry/exit logic with persistence requirement)
ENTRY_Z = 2.0  # Require Z-score to reach ±2.0 (2 standard deviations) for entry

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
MAX_CONSECUTIVE_LOSSES = 2  # Move pair to graveyard after 2 consecutive losses
                            # Prevents repeated losses on deteriorating pairs

# PAIR HEALTH & MONITORING (conintegration_pair_switching.txt recommendations)
HEALTH_CHECK_INTERVAL = 3600  # Check health every 1 hour (3600 seconds)
STATUS_UPDATE_INTERVAL = 60   # Trading status update every 1 minute (60 seconds)
P_VALUE_CRITICAL = 0.15        # More realistic statistical threshold for switching
ZERO_CROSSINGS_MIN = 15       # Minimum zero crossings to consider a pair healthy
CORRELATION_MIN = 0.60        # Minimum price correlation
TREND_CRITICAL = 0.002        # Maximum allowed spread trend
Z_SCORE_CRITICAL = 6.0        # Maximum allowed Z-score before switching

max_drawdown_pct = 0.05  # Circuit breaker: exit if cumulative loss exceeds 5% of capital

# ENVIRONMENT SETTINGS
flag = "1" if mode == "demo" else "0"  # "1" = demo, "0" = live
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

# Added 10s timeout to prevent hanging on network issues
# Since the SDK constructor doesn't accept requests_options/timeout, 
# we set it directly on the session objects (which are httpx.Client subclasses).
for session in [public_session, market_session, account_session, trade_session]:
    session.timeout = 10.0

skip_instrument_fetch = os.getenv("STATBOT_SKIP_INSTRUMENT_FETCH") == "1"

# DYNAMIC ROUNDING FETCH
if not skip_instrument_fetch:
    try:
        # Update rounding_ticker_1
        res1 = public_session.get_instruments(instType=inst_type, instId=ticker_1)
        if res1.get("code") == "0" and res1.get("data"):
            inst1 = res1["data"][0]
            tick_sz = inst1.get("tickSz", "0.01")
            rounding_ticker_1 = len(tick_sz.split(".")[-1]) if "." in tick_sz else 0
            lot_sz = inst1.get("lotSz", "1")
            quantity_rounding_ticker_1 = len(lot_sz.split(".")[-1]) if "." in lot_sz else 0

        # Update rounding_ticker_2
        res2 = public_session.get_instruments(instType=inst_type, instId=ticker_2)
        if res2.get("code") == "0" and res2.get("data"):
            inst2 = res2["data"][0]
            tick_sz = inst2.get("tickSz", "0.01")
            rounding_ticker_2 = len(tick_sz.split(".")[-1]) if "." in tick_sz else 0
            lot_sz = inst2.get("lotSz", "1")
            quantity_rounding_ticker_2 = len(lot_sz.split(".")[-1]) if "." in lot_sz else 0
    except Exception as e:
        print(f"Warning: Could not fetch dynamic rounding info: {e}")
