import json
import os
import time
from pathlib import Path

STATE_FILE = Path(__file__).resolve().parent / "pair_strategy_state.json"

# Min-capital cooldown defaults (seconds)
MIN_CAPITAL_COOLDOWN_SHORT = 180
MIN_CAPITAL_COOLDOWN_MEDIUM = 300
MIN_CAPITAL_COOLDOWN_LONG = 600
MIN_CAPITAL_SHORTAGE_MEDIUM = 0.20
MIN_CAPITAL_SHORTAGE_HIGH = 0.50
Z_HISTORY_MAX_AGE_SECONDS = 14400
Z_HISTORY_MAX_LEN = 5000
GRAVEYARD_DEFAULT_DAYS = 7
GRAVEYARD_REASON_DAYS = {
    "cointegration_lost": 5 / (24 * 60),
    "orderbook_dead": 30,
    "compliance_restricted": None,
    "manual": 3,
    "health": 5 / (24 * 60),
    "settle_ccy_filter": 30,
}

def load_pair_state():
    if not STATE_FILE.exists():
        return {
            "last_switch_time": 0,
            "graveyard": {}, # { "ticker_1/ticker_2": fail_timestamp }
            "restricted_tickers": {}, # { "TICKER": {"ts": float, "code": str, "msg": str} }
            "consecutive_losses": 0,
            "last_health_score": None,
            "price_fetch_failures": 0,
            "entry_z_score": None,
            "entry_time": None,
            "entry_equity": None,
            "entry_notional": None,
            "last_switch_reason": "",
            "min_capital_cooldowns": {},
            "stall_warning_marks": []
        }
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
            # Ensure consecutive_losses exists
            if "consecutive_losses" not in state:
                state["consecutive_losses"] = 0
            if "restricted_tickers" not in state:
                state["restricted_tickers"] = {}
            # Ensure last_health_score exists
            if "last_health_score" not in state:
                state["last_health_score"] = None
            # Ensure price_fetch_failures exists
            if "price_fetch_failures" not in state:
                state["price_fetch_failures"] = 0
            # Ensure entry tracking exists
            if "entry_z_score" not in state:
                state["entry_z_score"] = None
            if "entry_time" not in state:
                state["entry_time"] = None
            if "entry_equity" not in state:
                state["entry_equity"] = None
            if "entry_notional" not in state:
                state["entry_notional"] = None
            if "last_switch_reason" not in state:
                state["last_switch_reason"] = ""
            if "min_capital_cooldowns" not in state:
                state["min_capital_cooldowns"] = {}
            if "stall_warning_marks" not in state:
                state["stall_warning_marks"] = []
            return state
    except Exception:
        return {"last_switch_time": 0, "graveyard": {}, "restricted_tickers": {}, "consecutive_losses": 0, "last_health_score": None, "price_fetch_failures": 0, "entry_z_score": None, "entry_time": None, "entry_equity": None, "entry_notional": None, "last_switch_reason": "", "min_capital_cooldowns": {}, "stall_warning_marks": []}

def save_pair_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        print(f"Error saving pair state: {e}")

def record_trade_result(is_win):
    state = load_pair_state()
    if is_win:
        state["consecutive_losses"] = 0
    else:
        state["consecutive_losses"] += 1
    save_pair_state(state)

def get_consecutive_losses():
    state = load_pair_state()
    return state.get("consecutive_losses", 0)

def _graveyard_days_for_reason(reason):
    if not reason:
        return GRAVEYARD_DEFAULT_DAYS
    reason_key = str(reason).strip().lower()
    if reason_key in GRAVEYARD_REASON_DAYS:
        return GRAVEYARD_REASON_DAYS[reason_key]
    return GRAVEYARD_DEFAULT_DAYS

def add_to_graveyard(t1, t2, reason=""):
    state = load_pair_state()
    pair_key = f"{t1}/{t2}"
    ttl_days = _graveyard_days_for_reason(reason)
    state["graveyard"][pair_key] = {
        "ts": time.time(),
        "reason": str(reason or ""),
        "ttl_days": ttl_days,
    }
    state["consecutive_losses"] = 0 # Reset losses when switching
    save_pair_state(state)

def add_restricted_ticker(ticker, code="", msg=""):
    if not ticker:
        return False
    state = load_pair_state()
    restricted = state.get("restricted_tickers", {})
    if ticker in restricted:
        return False
    restricted[ticker] = {
        "ts": time.time(),
        "code": str(code or ""),
        "msg": str(msg or ""),
    }
    state["restricted_tickers"] = restricted
    save_pair_state(state)
    return True

def is_restricted_ticker(ticker, lookback_days=365):
    if not ticker:
        return False
    state = load_pair_state()
    restricted = state.get("restricted_tickers", {})
    entry = restricted.get(ticker)
    if not entry:
        return False
    ts = entry.get("ts") or 0
    if lookback_days and ts > 0:
        if time.time() - ts > (lookback_days * 24 * 60 * 60):
            restricted.pop(ticker, None)
            state["restricted_tickers"] = restricted
            save_pair_state(state)
            return False
    return True

def is_in_graveyard(t1, t2, lookback_days=7):
    state = load_pair_state()
    pair_key = f"{t1}/{t2}"
    alt_pair_key = f"{t2}/{t1}"

    entry = state["graveyard"].get(pair_key)
    entry_key = pair_key
    if not entry:
        entry = state["graveyard"].get(alt_pair_key)
        entry_key = alt_pair_key
    if not entry:
        return False

    if isinstance(entry, dict):
        fail_time = entry.get("ts") or 0
        ttl_days = entry.get("ttl_days")
        reason = entry.get("reason") or ""
        if ttl_days is None:
            return True
        if ttl_days <= 0:
            ttl_days = _graveyard_days_for_reason(reason)
    else:
        fail_time = entry
        ttl_days = lookback_days

    if fail_time and time.time() - fail_time < (ttl_days * 24 * 60 * 60):
        return True

    state["graveyard"].pop(entry_key, None)
    save_pair_state(state)
    return False


def cleanup_expired_graveyard(lookback_days=7):
    state = load_pair_state()
    graveyard = state.get("graveyard", {})
    now = time.time()
    removed = 0

    for pair_key in list(graveyard.keys()):
        entry = graveyard.get(pair_key)
        if isinstance(entry, dict):
            fail_time = entry.get("ts") or 0
            ttl_days = entry.get("ttl_days")
            if ttl_days is None:
                continue
            if ttl_days <= 0:
                ttl_days = _graveyard_days_for_reason(entry.get("reason") or "")
        else:
            fail_time = entry
            ttl_days = lookback_days

        if not fail_time:
            graveyard.pop(pair_key, None)
            removed += 1
            continue

        if now - fail_time >= (ttl_days * 24 * 60 * 60):
            graveyard.pop(pair_key, None)
            removed += 1

    if removed:
        state["graveyard"] = graveyard
        save_pair_state(state)
    return removed

def get_last_switch_time():
    state = load_pair_state()
    return state.get("last_switch_time", 0)

def set_last_switch_time(timestamp=None):
    if timestamp is None:
        timestamp = time.time()
    state = load_pair_state()
    state["last_switch_time"] = timestamp
    save_pair_state(state)

def set_last_switch_reason(reason):
    state = load_pair_state()
    state["last_switch_reason"] = str(reason or "")
    save_pair_state(state)

def get_last_switch_reason():
    state = load_pair_state()
    return state.get("last_switch_reason", "")

def calculate_min_capital_cooldown(required, allocated):
    try:
        required_val = float(required)
        allocated_val = float(allocated)
    except (TypeError, ValueError):
        return MIN_CAPITAL_COOLDOWN_MEDIUM

    if required_val <= 0 or allocated_val <= 0:
        return MIN_CAPITAL_COOLDOWN_MEDIUM

    shortage_pct = (required_val - allocated_val) / required_val
    if shortage_pct > MIN_CAPITAL_SHORTAGE_HIGH:
        return MIN_CAPITAL_COOLDOWN_LONG
    if shortage_pct > MIN_CAPITAL_SHORTAGE_MEDIUM:
        return MIN_CAPITAL_COOLDOWN_MEDIUM
    return MIN_CAPITAL_COOLDOWN_SHORT

def _min_capital_key(t1, t2):
    return "/".join(sorted([str(t1), str(t2)]))

def set_min_capital_cooldown(t1, t2, required, allocated):
    cooldown = calculate_min_capital_cooldown(required, allocated)
    state = load_pair_state()
    cooldowns = state.get("min_capital_cooldowns", {})
    key = _min_capital_key(t1, t2)
    cooldowns[key] = {
        "ts": time.time(),
        "cooldown": cooldown,
        "required": float(required),
        "allocated": float(allocated),
    }
    state["min_capital_cooldowns"] = cooldowns
    save_pair_state(state)
    return cooldown

def get_min_capital_cooldown(t1, t2):
    state = load_pair_state()
    cooldowns = state.get("min_capital_cooldowns", {})
    key = _min_capital_key(t1, t2)
    entry = cooldowns.get(key)
    if not entry:
        return 0.0

    ts = entry.get("ts") or 0
    cooldown = entry.get("cooldown") or 0
    if ts <= 0 or cooldown <= 0:
        return 0.0

    elapsed = time.time() - ts
    if elapsed >= cooldown:
        cooldowns.pop(key, None)
        state["min_capital_cooldowns"] = cooldowns
        save_pair_state(state)
        return 0.0
    return float(cooldown - elapsed)

def set_last_health_score(score):
    """Store the last health score for emergency override checks."""
    state = load_pair_state()
    state["last_health_score"] = score
    save_pair_state(state)

def get_last_health_score():
    """Retrieve the last health score."""
    state = load_pair_state()
    return state.get("last_health_score")

def increment_price_fetch_failures():
    """Increment and return the count of consecutive price fetch failures."""
    state = load_pair_state()
    state["price_fetch_failures"] = state.get("price_fetch_failures", 0) + 1
    save_pair_state(state)
    return state["price_fetch_failures"]

def reset_price_fetch_failures():
    """Reset price fetch failure counter."""
    state = load_pair_state()
    state["price_fetch_failures"] = 0
    save_pair_state(state)

def get_price_fetch_failures():
    """Get current count of price fetch failures."""
    state = load_pair_state()
    return state.get("price_fetch_failures", 0)

def set_entry_z_score(z_score):
    """Record the Z-score at position entry."""
    import logging
    logger = logging.getLogger(__name__)

    state = load_pair_state()
    state["entry_z_score"] = float(z_score)
    state["entry_time"] = time.time()
    save_pair_state(state)

    # Verify write was successful
    verify_state = load_pair_state()
    if verify_state.get("entry_z_score") != float(z_score):
        logger.error(f"⚠️  CRITICAL: Entry Z-score failed to persist! Expected {z_score}, got {verify_state.get('entry_z_score')}")
    else:
        logger.debug(f"✅ Entry Z-score persisted: {z_score}")

def get_entry_z_score():
    """Get the Z-score at position entry."""
    state = load_pair_state()
    return state.get("entry_z_score")

def get_entry_time():
    """Get the timestamp of position entry."""
    state = load_pair_state()
    return state.get("entry_time")

def set_entry_equity(equity_usdt):
    """Record equity at the time of position entry."""
    state = load_pair_state()
    state["entry_equity"] = float(equity_usdt)
    save_pair_state(state)

def get_entry_equity():
    """Get recorded equity at position entry."""
    state = load_pair_state()
    return state.get("entry_equity")

def set_entry_notional(notional_usdt):
    """Record estimated notional size at entry (USDT)."""
    state = load_pair_state()
    state["entry_notional"] = float(notional_usdt)
    save_pair_state(state)

def get_entry_notional():
    """Get estimated notional size at entry (USDT)."""
    state = load_pair_state()
    return state.get("entry_notional")

def clear_entry_tracking():
    """Clear entry tracking when position is closed."""
    state = load_pair_state()
    state["entry_z_score"] = None
    state["entry_time"] = None
    state["entry_equity"] = None
    state["entry_notional"] = None
    state["last_exit_time"] = time.time()  # Track when we exited
    state["z_history"] = []  # Clear stall detection history
    state["stall_warning_marks"] = []
    save_pair_state(state)

def can_reenter(cooldown_minutes=5):
    """Check if enough time has passed since last exit to prevent clustering."""
    state = load_pair_state()
    last_exit = state.get("last_exit_time", 0)

    if last_exit == 0:
        return True  # No previous exit

    time_since_exit = (time.time() - last_exit) / 60  # minutes
    return time_since_exit >= cooldown_minutes

def add_to_persistence_history(z_score):
    """Add current z-score to persistence history (last 5 values)."""
    state = load_pair_state()
    if "persistence_history" not in state:
        state["persistence_history"] = []

    state["persistence_history"].append(z_score)
    # Keep only last 5 values
    if len(state["persistence_history"]) > 5:
        state["persistence_history"] = state["persistence_history"][-5:]

    save_pair_state(state)

def add_to_z_history(z_score):
    """Add current z-score to monitoring history (time-based stall detection)."""
    state = load_pair_state()
    history = state.get("z_history", [])
    if not isinstance(history, list):
        history = []

    if history and any(
        not isinstance(entry, dict) or "z" not in entry or "ts" not in entry
        for entry in history
    ):
        history = []

    try:
        z_val = float(z_score)
    except (TypeError, ValueError):
        return

    now = time.time()
    history.append({"ts": now, "z": z_val})

    cutoff = now - Z_HISTORY_MAX_AGE_SECONDS
    history = [
        entry for entry in history
        if isinstance(entry, dict) and entry.get("ts", 0) >= cutoff
    ]

    if len(history) > Z_HISTORY_MAX_LEN:
        history = history[-Z_HISTORY_MAX_LEN:]

    state["z_history"] = history
    save_pair_state(state)

def get_z_history():
    """Get Z-score history for stall detection."""
    state = load_pair_state()
    history = state.get("z_history", [])
    if not isinstance(history, list):
        return []
    if history and any(
        not isinstance(entry, dict) or "z" not in entry or "ts" not in entry
        for entry in history
    ):
        return []
    return history

def get_persistence_history():
    """Get persistence history."""
    state = load_pair_state()
    return state.get("persistence_history", [])

def clear_persistence_history():
    """Clear persistence history (on position open or pair switch)."""
    state = load_pair_state()
    state["persistence_history"] = []
    save_pair_state(state)

def get_stall_warning_marks():
    state = load_pair_state()
    marks = state.get("stall_warning_marks", [])
    if not isinstance(marks, list):
        return []
    return marks

def add_stall_warning_mark(mark):
    try:
        mark_val = int(mark)
    except (TypeError, ValueError):
        return False
    state = load_pair_state()
    marks = state.get("stall_warning_marks", [])
    if not isinstance(marks, list):
        marks = []
    if mark_val in marks:
        return False
    marks.append(mark_val)
    state["stall_warning_marks"] = marks
    save_pair_state(state)
    return True

def can_switch(cooldown_hours=24, health_score=None, emergency_threshold=25):
    """
    Check if pair switching is allowed.

    Args:
        cooldown_hours: Normal cooldown period in hours (default: 24)
        health_score: Current pair health score (0-100). If provided and below emergency_threshold, overrides cooldown
        emergency_threshold: Health score threshold for emergency override (default: 25)

    Returns:
        bool: True if switching is allowed, False otherwise
    """
    last_switch = get_last_switch_time()
    time_since_switch = time.time() - last_switch
    cooldown_seconds = cooldown_hours * 60 * 60

    # Emergency override: health is critically bad, ignore cooldown
    if health_score is not None and health_score < emergency_threshold:
        return True

    # Normal cooldown check
    if time_since_switch < cooldown_seconds:
        return False
    return True
