"""Emergency script to blacklist current pair and force switch."""
import json
import time
from pathlib import Path

STATE_FILE = Path(__file__).parent / "state" / "pair_strategy_state.json"
ACTIVE_PAIR_FILE = Path(__file__).parent / "state" / "active_pair.json"

def blacklist_pair():
    # Read current active pair
    try:
        with open(ACTIVE_PAIR_FILE, 'r') as f:
            active = json.load(f)
        ticker_1 = active['ticker_1']
        ticker_2 = active['ticker_2']
        print(f"Current active pair: {ticker_1}/{ticker_2}")
    except Exception as e:
        print(f"Error reading active pair: {e}")
        return False

    # Load state
    try:
        with open(STATE_FILE, 'r') as f:
            state = json.load(f)
    except Exception as e:
        print(f"Error reading state: {e}")
        return False

    # Add to graveyard
    pair_key = f"{ticker_1}/{ticker_2}"
    if "graveyard" not in state:
        state["graveyard"] = {}

    state["graveyard"][pair_key] = {
        "ts": time.time(),
        "reason": "zero_liquidity_dead_orderbook",
        "ttl_days": None  # Permanent blacklist
    }

    print(f"Adding {pair_key} to graveyard (permanent)...")

    # Save state
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)
        print("State saved successfully")
    except Exception as e:
        print(f"Error saving state: {e}")
        return False

    # Force cooldown bypass by resetting last_switch_time
    state["last_switch_time"] = time.time() - (25 * 3600)  # 25 hours ago
    state["last_switch_reason"] = "zero_liquidity"

    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)
        print("Cooldown bypassed - pair switch will trigger on next cycle")
    except Exception as e:
        print(f"Error bypassing cooldown: {e}")
        return False

    print("\nDone! The bot will switch pairs on the next health check cycle.")
    print("If needed, restart the bot to force immediate switch.")
    return True

if __name__ == "__main__":
    blacklist_pair()
