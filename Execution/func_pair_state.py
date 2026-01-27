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
            "last_health_score": None
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
            return state
    except Exception:
        return {"last_switch_time": 0, "graveyard": {}, "consecutive_losses": 0, "last_health_score": None}

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
