import json
import os
import time
from pathlib import Path

STATE_FILE = Path(__file__).resolve().parent / "pair_strategy_state.json"

def load_pair_state():
    if not STATE_FILE.exists():
        return {
            "last_switch_time": 0,
            "graveyard": {}, # { "ticker_1/ticker_2": fail_timestamp }
            "consecutive_losses": 0,
            "last_health_score": None,
            "price_fetch_failures": 0,
            "entry_z_score": None,
            "entry_time": None
        }
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
            # Ensure consecutive_losses exists
            if "consecutive_losses" not in state:
                state["consecutive_losses"] = 0
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
            return state
    except Exception:
        return {"last_switch_time": 0, "graveyard": {}, "consecutive_losses": 0, "last_health_score": None, "price_fetch_failures": 0, "entry_z_score": None, "entry_time": None}

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

def add_to_graveyard(t1, t2):
    state = load_pair_state()
    pair_key = f"{t1}/{t2}"
    state["graveyard"][pair_key] = time.time()
    state["consecutive_losses"] = 0 # Reset losses when switching
    save_pair_state(state)

def is_in_graveyard(t1, t2, lookback_days=7):
    state = load_pair_state()
    pair_key = f"{t1}/{t2}"
    alt_pair_key = f"{t2}/{t1}"
    
    fail_time = state["graveyard"].get(pair_key) or state["graveyard"].get(alt_pair_key)
    if not fail_time:
        return False
    
    # Check if 7 days have passed
    if time.time() - fail_time < (lookback_days * 24 * 60 * 60):
        return True
    return False

def get_last_switch_time():
    state = load_pair_state()
    return state.get("last_switch_time", 0)

def set_last_switch_time(timestamp=None):
    if timestamp is None:
        timestamp = time.time()
    state = load_pair_state()
    state["last_switch_time"] = timestamp
    save_pair_state(state)

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

def clear_entry_tracking():
    """Clear entry tracking when position is closed."""
    state = load_pair_state()
    state["entry_z_score"] = None
    state["entry_time"] = None
    state["last_exit_time"] = time.time()  # Track when we exited
    state["z_history"] = []  # Clear stall detection history
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
    """Add current z-score to monitoring history (last 10 cycles for stall detection)."""
    state = load_pair_state()
    if "z_history" not in state:
        state["z_history"] = []

    state["z_history"].append(z_score)
    # Keep only last 10 cycles
    if len(state["z_history"]) > 10:
        state["z_history"] = state["z_history"][-10:]

    save_pair_state(state)

def get_z_history():
    """Get Z-score history for stall detection."""
    state = load_pair_state()
    return state.get("z_history", [])

def get_persistence_history():
    """Get persistence history."""
    state = load_pair_state()
    return state.get("persistence_history", [])

def clear_persistence_history():
    """Clear persistence history (on position open or pair switch)."""
    state = load_pair_state()
    state["persistence_history"] = []
    save_pair_state(state)

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
