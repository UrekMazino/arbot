import json
import os
import time
from pathlib import Path

_STATE_DIR = Path(__file__).resolve().parent / "state"
STATE_FILE = _STATE_DIR / "pair_strategy_state.json"
GRAVEYARD_TICKERS_FILE = _STATE_DIR / "graveyard_tickers.json"
TICKER_GRAVEYARD_PREFIX = "ticker::"

# Pair history/hospital defaults
DEFAULT_HISTORY_MIN_TRADES = 1
DEFAULT_HISTORY_MIN_WIN_RATE = 0.50
DEFAULT_HISTORY_REQUIRE_PROFIT = True
DEFAULT_HOSPITAL_COOLDOWN_SECONDS = 3600
DEFAULT_BLACKLIST_MIN_TRADES = 10
DEFAULT_BLACKLIST_MAX_LOSS_RATE = 0.75
DEFAULT_BLACKLIST_REQUIRE_LOSS_DOMINANCE = True

# Min-capital cooldown defaults (seconds)
MIN_CAPITAL_COOLDOWN_SHORT = 180
MIN_CAPITAL_COOLDOWN_MEDIUM = 300
MIN_CAPITAL_COOLDOWN_LONG = 600
MIN_CAPITAL_SHORTAGE_MEDIUM = 0.20
MIN_CAPITAL_SHORTAGE_HIGH = 0.50
Z_HISTORY_MAX_AGE_SECONDS = 14400
Z_HISTORY_MAX_LEN = 5000
SWITCH_RATE_WINDOW_SECONDS = 3600
DEFAULT_MAX_SWITCHES = 5
DEFAULT_SWITCH_COOLDOWN_SECONDS = 600
GRAVEYARD_DEFAULT_DAYS = 7
GRAVEYARD_REASON_DAYS = {
    "cointegration_lost": 7,  # Changed from 5min to 7 days
    "cointegration_lost_bad_history": 7,
    "cointegration_lost_unproven": 7,  # Added for consistency
    "orderbook_dead": 30,
    "compliance_restricted": None,  # Permanent ticker-level restriction
    "manual": 7,  # Changed from 3 to 7 days
    "health": 7,  # Changed from 5min to 7 days
    "health_bad_history": 7,
    "settle_ccy_filter": 30,
    "bad_history": 7,
    "idle_timeout": 7,  # Changed from 3 to 7 days
    "idle_timeout_bad_history": 7,  # Added for consistency
    "pair_loss_limit": 7,  # New reason from per-pair loss limit
    "restricted_ticker": 7,
}


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


def _env_int(name, default):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default


def _env_float(name, default):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


PAIR_HISTORY_MIN_TRADES = _env_int("STATBOT_HISTORY_MIN_TRADES", DEFAULT_HISTORY_MIN_TRADES)
PAIR_HISTORY_MIN_WIN_RATE = _env_float("STATBOT_HISTORY_MIN_WIN_RATE", DEFAULT_HISTORY_MIN_WIN_RATE)
PAIR_HISTORY_REQUIRE_PROFIT = _env_flag("STATBOT_HISTORY_REQUIRE_PROFIT", DEFAULT_HISTORY_REQUIRE_PROFIT)
HOSPITAL_DEFAULT_COOLDOWN_SECONDS = _env_int(
    "STATBOT_HOSPITAL_COOLDOWN_SECONDS",
    DEFAULT_HOSPITAL_COOLDOWN_SECONDS,
)
BLACKLIST_ENABLED = _env_flag("STATBOT_BLACKLIST_ENABLED", True)
BLACKLIST_MIN_TRADES = _env_int("STATBOT_BLACKLIST_MIN_TRADES", DEFAULT_BLACKLIST_MIN_TRADES)
BLACKLIST_MAX_LOSS_RATE = _env_float("STATBOT_BLACKLIST_MAX_LOSS_RATE", DEFAULT_BLACKLIST_MAX_LOSS_RATE)
BLACKLIST_REQUIRE_LOSS_DOMINANCE = _env_flag(
    "STATBOT_BLACKLIST_REQUIRE_LOSS_DOMINANCE",
    DEFAULT_BLACKLIST_REQUIRE_LOSS_DOMINANCE,
)


def _read_json_object(path):
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _normalize_ttl_days(value):
    if value is None or value == "":
        return None
    try:
        ttl_days = float(value)
    except (TypeError, ValueError):
        return None
    if ttl_days <= 0:
        return None
    return ttl_days


def _normalize_restricted_entry(entry, default_source="runtime", fallback_ts=None):
    if fallback_ts is None:
        fallback_ts = time.time()
    try:
        fallback_ts = float(fallback_ts)
    except (TypeError, ValueError):
        fallback_ts = time.time()

    if isinstance(entry, dict):
        ts_raw = entry.get("ts", fallback_ts)
        try:
            ts = float(ts_raw)
        except (TypeError, ValueError):
            ts = fallback_ts
        code = str(entry.get("code") or "").strip()
        msg = str(entry.get("msg") or "").strip()
        reason = str(entry.get("reason") or "").strip()
        source = str(entry.get("source") or default_source).strip() or default_source
        ttl_days = _normalize_ttl_days(entry.get("ttl_days"))
        if not msg and reason:
            msg = reason
        if not reason and msg:
            reason = msg
        return {
            "ts": ts,
            "code": code,
            "msg": msg,
            "reason": reason,
            "ttl_days": ttl_days,
            "source": source,
        }

    text = str(entry or "").strip()
    if not text:
        return None
    return {
        "ts": fallback_ts,
        "code": "",
        "msg": text,
        "reason": text,
        "ttl_days": None,
        "source": default_source,
    }


def _load_seed_ticker_graveyard():
    data = _read_json_object(GRAVEYARD_TICKERS_FILE)
    normalized = {}
    for ticker, entry in data.items():
        ticker_text = str(ticker or "").strip()
        if not ticker_text:
            continue
        normalized_entry = _normalize_restricted_entry(entry, default_source="seed", fallback_ts=0.0)
        if not normalized_entry:
            continue
        normalized[ticker_text] = normalized_entry
    return normalized


def _ticker_graveyard_key(ticker):
    ticker_text = str(ticker or "").strip()
    if not ticker_text:
        return ""
    return f"{TICKER_GRAVEYARD_PREFIX}{ticker_text}"


def _is_ticker_graveyard_key(key):
    return str(key or "").startswith(TICKER_GRAVEYARD_PREFIX)


def _ticker_from_graveyard_key(key):
    key_text = str(key or "").strip()
    if not _is_ticker_graveyard_key(key_text):
        return ""
    return key_text[len(TICKER_GRAVEYARD_PREFIX):]


def _merge_restricted_entry(existing_entry, next_entry):
    if not next_entry:
        return existing_entry, False
    if not existing_entry:
        return dict(next_entry), True

    merged = dict(existing_entry)
    updated = False
    for key in ("code", "msg", "reason", "ttl_days", "source"):
        next_value = next_entry.get(key)
        if key == "ttl_days" and next_value is None:
            continue
        if next_value and merged.get(key) != next_value:
            merged[key] = next_value
            updated = True
    if not merged.get("ts"):
        merged["ts"] = next_entry.get("ts") or time.time()
        updated = True
    return merged, updated


def _extract_runtime_ticker_graveyard(state):
    graveyard = state.get("graveyard", {})
    if not isinstance(graveyard, dict):
        graveyard = {}
    runtime_restricted = {}
    dirty = False

    for key, entry in list(graveyard.items()):
        if not _is_ticker_graveyard_key(key):
            continue
        ticker = _ticker_from_graveyard_key(key)
        if not ticker:
            graveyard.pop(key, None)
            dirty = True
            continue
        normalized_entry = _normalize_restricted_entry(entry, default_source="runtime")
        if not normalized_entry:
            graveyard.pop(key, None)
            dirty = True
            continue
        runtime_restricted[ticker] = normalized_entry

    return runtime_restricted, graveyard, dirty

def load_pair_state():
    if not STATE_FILE.exists():
        return {
            "last_switch_time": 0,
            "switch_events": [],
            "switch_rate_limit_until_ts": 0.0,
            "graveyard": {}, # { "ticker_1/ticker_2": fail_timestamp }
            "hospital": {}, # { "ticker_1/ticker_2": {"ts": float, "cooldown": int, "reason": str} }
            "pair_history": {}, # { "ticker_1/ticker_2": {wins, losses, win_usdt, loss_usdt, trades} }
            "restricted_tickers": {}, # Legacy field kept for migration; ticker exclusions now live in graveyard.
            "consecutive_losses": 0,
            "last_health_score": None,
            "price_fetch_failures": 0,
            "entry_z_score": None,
            "entry_time": None,
            "coint_lost_since_ts": None,
            "coint_lost_confirm_count": 0,
            "entry_equity": None,
            "entry_notional": None,
            "entry_strategy": None,
            "entry_regime": None,
            "entry_policy_snapshot": {},
            "entry_ts": None,
            "last_switch_reason": "",
            "min_capital_cooldowns": {},
            "stall_warning_marks": [],
            "health_failures": {},
        }
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
            dirty = False
            # Ensure consecutive_losses exists
            if "consecutive_losses" not in state:
                state["consecutive_losses"] = 0
                dirty = True
            if "switch_events" not in state:
                state["switch_events"] = []
                dirty = True
            if "switch_rate_limit_until_ts" not in state:
                state["switch_rate_limit_until_ts"] = 0.0
                dirty = True
            if "graveyard" not in state or not isinstance(state.get("graveyard"), dict):
                state["graveyard"] = {}
                dirty = True
            if "restricted_tickers" not in state:
                state["restricted_tickers"] = {}
                dirty = True
            if "hospital" not in state:
                state["hospital"] = {}
                dirty = True
            if "pair_history" not in state:
                state["pair_history"] = {}
                dirty = True
            if "health_failures" not in state:
                state["health_failures"] = {}
                dirty = True
            # Ensure last_health_score exists
            if "last_health_score" not in state:
                state["last_health_score"] = None
                dirty = True
            # Ensure price_fetch_failures exists
            if "price_fetch_failures" not in state:
                state["price_fetch_failures"] = 0
                dirty = True
            # Ensure entry tracking exists
            if "entry_z_score" not in state:
                state["entry_z_score"] = None
                dirty = True
            if "entry_time" not in state:
                state["entry_time"] = None
                dirty = True
            if "coint_lost_since_ts" not in state:
                state["coint_lost_since_ts"] = None
                dirty = True
            if "coint_lost_confirm_count" not in state:
                state["coint_lost_confirm_count"] = 0
                dirty = True
            if "entry_equity" not in state:
                state["entry_equity"] = None
                dirty = True
            if "entry_notional" not in state:
                state["entry_notional"] = None
                dirty = True
            if "entry_strategy" not in state:
                state["entry_strategy"] = None
                dirty = True
            if "entry_regime" not in state:
                state["entry_regime"] = None
                dirty = True
            if "entry_policy_snapshot" not in state or not isinstance(state.get("entry_policy_snapshot"), dict):
                state["entry_policy_snapshot"] = {}
                dirty = True
            if "entry_ts" not in state:
                state["entry_ts"] = None
                dirty = True
            if "last_switch_reason" not in state:
                state["last_switch_reason"] = ""
                dirty = True
            if "min_capital_cooldowns" not in state:
                state["min_capital_cooldowns"] = {}
                dirty = True
            if "stall_warning_marks" not in state:
                state["stall_warning_marks"] = []
                dirty = True

            restricted = state.get("restricted_tickers", {})
            if isinstance(restricted, dict) and restricted:
                graveyard = state.get("graveyard", {})
                for ticker, entry in restricted.items():
                    ticker_text = str(ticker or "").strip()
                    if not ticker_text:
                        continue
                    normalized_entry = _normalize_restricted_entry(entry, default_source="runtime")
                    merged_key = _ticker_graveyard_key(ticker_text)
                    existing_entry = _normalize_restricted_entry(graveyard.get(merged_key), default_source="runtime")
                    merged_entry, updated = _merge_restricted_entry(existing_entry, normalized_entry)
                    if updated or merged_key not in graveyard:
                        graveyard[merged_key] = merged_entry
                        dirty = True
                state["graveyard"] = graveyard
                state["restricted_tickers"] = {}
                dirty = True

            runtime_restricted, normalized_graveyard, graveyard_dirty = _extract_runtime_ticker_graveyard(state)
            if graveyard_dirty:
                state["graveyard"] = normalized_graveyard
                dirty = True
            if runtime_restricted and state.get("restricted_tickers"):
                state["restricted_tickers"] = {}
                dirty = True

            if dirty:
                save_pair_state(state)
            return state
    except Exception:
        return {"last_switch_time": 0, "switch_events": [], "switch_rate_limit_until_ts": 0.0, "graveyard": {}, "hospital": {}, "pair_history": {}, "restricted_tickers": {}, "consecutive_losses": 0, "last_health_score": None, "price_fetch_failures": 0, "entry_z_score": None, "entry_time": None, "coint_lost_since_ts": None, "coint_lost_confirm_count": 0, "entry_equity": None, "entry_notional": None, "entry_strategy": None, "entry_regime": None, "entry_policy_snapshot": {}, "entry_ts": None, "last_switch_reason": "", "min_capital_cooldowns": {}, "stall_warning_marks": [], "health_failures": {}}

def save_pair_state(state):
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        print(f"Error saving pair state: {e}")


def _switch_limit_settings():
    max_switches = _env_int("STATBOT_MAX_SWITCHES", DEFAULT_MAX_SWITCHES)
    cooldown_seconds = _env_int("STATBOT_SWITCH_COOLDOWN_SECONDS", DEFAULT_SWITCH_COOLDOWN_SECONDS)
    if max_switches < 0:
        max_switches = 0
    if cooldown_seconds < 0:
        cooldown_seconds = 0
    return max_switches, cooldown_seconds


def _prune_switch_events(events, now_ts, window_seconds=SWITCH_RATE_WINDOW_SECONDS):
    pruned = []
    if not isinstance(events, list):
        return pruned
    cutoff = now_ts - max(float(window_seconds), 0.0)
    for ts in events:
        try:
            value = float(ts)
        except (TypeError, ValueError):
            continue
        if value >= cutoff:
            pruned.append(value)
    return pruned

def normalize_pair_key(t1, t2):
    if not t1 or not t2:
        return ""
    return "/".join(sorted([str(t1), str(t2)]))

def _get_pair_history_entry(history, key):
    entry = history.get(key)
    if not isinstance(entry, dict):
        entry = {}
    return {
        "wins": int(entry.get("wins", 0) or 0),
        "losses": int(entry.get("losses", 0) or 0),
        "win_usdt": float(entry.get("win_usdt", 0.0) or 0.0),
        "loss_usdt": float(entry.get("loss_usdt", 0.0) or 0.0),
        "trades": int(entry.get("trades", 0) or 0),
        "last_trade_ts": float(entry.get("last_trade_ts", 0.0) or 0.0),
    }

def record_pair_trade_result(t1, t2, pnl_usdt):
    key = normalize_pair_key(t1, t2)
    if not key:
        return False
    try:
        pnl_val = float(pnl_usdt)
    except (TypeError, ValueError):
        return False

    state = load_pair_state()
    history = state.get("pair_history", {})
    entry = _get_pair_history_entry(history, key)

    entry["trades"] += 1
    if pnl_val > 0:
        entry["wins"] += 1
        entry["win_usdt"] += pnl_val
    else:
        entry["losses"] += 1
        entry["loss_usdt"] += abs(pnl_val)
    entry["last_trade_ts"] = time.time()

    history[key] = entry
    state["pair_history"] = history
    save_pair_state(state)
    return True

def get_pair_history_stats(t1, t2):
    key = normalize_pair_key(t1, t2)
    if not key:
        return None
    state = load_pair_state()
    history = state.get("pair_history", {})
    entry = _get_pair_history_entry(history, key)
    trades = entry["trades"]
    win_rate = (entry["wins"] / trades) if trades > 0 else 0.0
    entry["win_rate"] = win_rate
    entry["pair_key"] = key
    return entry

def is_good_pair_history(
    t1,
    t2,
    min_trades=None,
    min_win_rate=None,
    require_profit=None,
):
    stats = get_pair_history_stats(t1, t2)
    if not stats:
        return False
    if min_trades is None:
        min_trades = PAIR_HISTORY_MIN_TRADES
    if min_win_rate is None:
        min_win_rate = PAIR_HISTORY_MIN_WIN_RATE
    if require_profit is None:
        require_profit = PAIR_HISTORY_REQUIRE_PROFIT

    if stats["trades"] < min_trades:
        return False
    if stats["win_rate"] <= min_win_rate:
        return False
    if require_profit and stats["win_usdt"] <= stats["loss_usdt"]:
        return False
    return True


def should_blacklist_pair(
    t1,
    t2,
    min_trades=None,
    max_loss_rate=None,
    require_loss_dominance=None,
):
    if not BLACKLIST_ENABLED:
        return False
    stats = get_pair_history_stats(t1, t2)
    if not stats:
        return False
    if min_trades is None:
        min_trades = BLACKLIST_MIN_TRADES
    if max_loss_rate is None:
        max_loss_rate = BLACKLIST_MAX_LOSS_RATE
    if require_loss_dominance is None:
        require_loss_dominance = BLACKLIST_REQUIRE_LOSS_DOMINANCE

    # Check consecutive losses first (immediate blacklist)
    from config_execution_api import MAX_CONSECUTIVE_LOSSES
    consecutive_losses = get_consecutive_losses()
    if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        return True  # Blacklist after MAX_CONSECUTIVE_LOSSES consecutive losses

    # Original logic for overall performance
    trades = stats.get("trades", 0) or 0
    if trades < min_trades:
        return False
    losses = stats.get("losses", 0) or 0
    loss_rate = (losses / trades) if trades > 0 else 0.0
    if loss_rate < max_loss_rate:
        return False
    if require_loss_dominance and stats.get("loss_usdt", 0.0) <= stats.get("win_usdt", 0.0):
        return False
    return True

def add_to_hospital(t1, t2, reason="", cooldown_seconds=None):
    key = normalize_pair_key(t1, t2)
    if not key:
        return False
    if cooldown_seconds is None:
        cooldown_seconds = HOSPITAL_DEFAULT_COOLDOWN_SECONDS
    try:
        cooldown_seconds = int(float(cooldown_seconds))
    except (TypeError, ValueError):
        cooldown_seconds = HOSPITAL_DEFAULT_COOLDOWN_SECONDS

    state = load_pair_state()
    hospital = state.get("hospital", {})
    entry = hospital.get(key)
    visits = 0
    if isinstance(entry, dict):
        visits = int(entry.get("visits", 0) or 0)
    hospital[key] = {
        "ts": time.time(),
        "cooldown": cooldown_seconds,
        "reason": str(reason or ""),
        "visits": visits + 1,
    }
    state["hospital"] = hospital
    save_pair_state(state)
    return True

def remove_from_hospital(t1, t2):
    key = normalize_pair_key(t1, t2)
    if not key:
        return False
    state = load_pair_state()
    hospital = state.get("hospital", {})
    if key in hospital:
        hospital.pop(key, None)
        state["hospital"] = hospital
        save_pair_state(state)
        return True
    return False

def get_hospital_entries():
    state = load_pair_state()
    entries = state.get("hospital", {})
    if not isinstance(entries, dict):
        return {}
    return entries

def drain_ready_hospital_pairs(valid_pair_keys=None):
    state = load_pair_state()
    hospital = state.get("hospital", {})
    if not isinstance(hospital, dict):
        return [], 0

    valid_keys = None
    if valid_pair_keys is not None:
        valid_keys = {str(key) for key in valid_pair_keys if key}

    now = time.time()
    ready_pairs = []
    removed = 0

    for pair_key in list(hospital.keys()):
        entry = hospital.get(pair_key)
        if not isinstance(entry, dict):
            hospital.pop(pair_key, None)
            removed += 1
            continue

        ts = entry.get("ts") or 0
        cooldown = entry.get("cooldown") or HOSPITAL_DEFAULT_COOLDOWN_SECONDS
        try:
            ts = float(ts)
        except (TypeError, ValueError):
            ts = 0.0
        try:
            cooldown = float(cooldown)
        except (TypeError, ValueError):
            cooldown = float(HOSPITAL_DEFAULT_COOLDOWN_SECONDS)

        if not ts or (now - ts) < max(cooldown, 0.0):
            continue

        hospital.pop(pair_key, None)
        removed += 1
        if valid_keys is None or pair_key in valid_keys:
            ready_pairs.append((pair_key, ts))

    if removed:
        state["hospital"] = hospital
        save_pair_state(state)

    ready_pairs.sort(key=lambda item: item[1])
    return ready_pairs, removed

def get_hospital_remaining(t1, t2):
    key = normalize_pair_key(t1, t2)
    if not key:
        return 0.0
    state = load_pair_state()
    hospital = state.get("hospital", {})
    entry = hospital.get(key)
    if not isinstance(entry, dict):
        return 0.0
    ts = entry.get("ts") or 0
    cooldown = entry.get("cooldown") or HOSPITAL_DEFAULT_COOLDOWN_SECONDS
    if not ts or cooldown <= 0:
        return 0.0
    elapsed = time.time() - ts
    remaining = cooldown - elapsed
    if remaining <= 0:
        return 0.0
    return float(remaining)

def is_in_hospital(t1, t2):
    key = normalize_pair_key(t1, t2)
    if not key:
        return False
    state = load_pair_state()
    hospital = state.get("hospital", {})
    return key in hospital

def is_hospital_ready(t1, t2):
    return get_hospital_remaining(t1, t2) <= 0.0

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


def record_health_failure(t1, t2, is_failure):
    key = normalize_pair_key(t1, t2)
    if not key:
        return 0
    state = load_pair_state()
    failures = state.get("health_failures", {})
    if not isinstance(failures, dict):
        failures = {}
    if is_failure:
        count = int(failures.get(key, 0) or 0) + 1
    else:
        count = 0
    failures[key] = count
    state["health_failures"] = failures
    save_pair_state(state)
    return count


def get_health_failure_count(t1, t2):
    key = normalize_pair_key(t1, t2)
    if not key:
        return 0
    state = load_pair_state()
    failures = state.get("health_failures", {})
    if not isinstance(failures, dict):
        return 0
    return int(failures.get(key, 0) or 0)


def reset_health_failure(t1, t2):
    return record_health_failure(t1, t2, False)

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
    hospital = state.get("hospital", {})
    hospital_key = normalize_pair_key(t1, t2)
    if hospital_key in hospital:
        hospital.pop(hospital_key, None)
        state["hospital"] = hospital
    state["consecutive_losses"] = 0 # Reset losses when switching
    save_pair_state(state)

def add_restricted_ticker(ticker, code="", msg=""):
    if not ticker:
        return False
    state = load_pair_state()
    ticker = str(ticker).strip()
    if not ticker:
        return False

    next_entry = _normalize_restricted_entry(
        {
            "ts": time.time(),
            "code": str(code or ""),
            "msg": str(msg or ""),
            "reason": "compliance_restricted" if str(code or "").strip() else "",
            "ttl_days": None,
            "source": "runtime",
        },
        default_source="runtime",
    )
    if not next_entry:
        return False

    graveyard = state.get("graveyard", {})
    if not isinstance(graveyard, dict):
        graveyard = {}
    ticker_key = _ticker_graveyard_key(ticker)
    existing_entry = _normalize_restricted_entry(graveyard.get(ticker_key), default_source="runtime")
    merged_entry, updated = _merge_restricted_entry(existing_entry, next_entry)
    if not updated and ticker_key in graveyard:
        return False
    graveyard[ticker_key] = merged_entry
    state["graveyard"] = graveyard
    state["restricted_tickers"] = {}
    save_pair_state(state)
    return True


def get_restricted_tickers():
    state = load_pair_state()
    runtime_restricted, normalized_graveyard, dirty = _extract_runtime_ticker_graveyard(state)
    if dirty:
        state["graveyard"] = normalized_graveyard
        save_pair_state(state)

    merged = _load_seed_ticker_graveyard()
    merged.update(runtime_restricted)
    return merged


def get_restricted_ticker_entry(ticker):
    if not ticker:
        return None
    restricted = get_restricted_tickers()
    entry = restricted.get(str(ticker).strip())
    if not isinstance(entry, dict):
        return None
    return dict(entry)


def get_restricted_ticker_reason(ticker):
    entry = get_restricted_ticker_entry(ticker)
    if not entry:
        return None
    msg = str(entry.get("msg") or "").strip()
    code = str(entry.get("code") or "").strip()
    reason = str(entry.get("reason") or "").strip()
    if msg and code and code not in msg:
        return f"{msg} (code={code})"
    if msg:
        return msg
    if code:
        return f"code={code}"
    if reason:
        return reason
    return None


def is_restricted_ticker(ticker, lookback_days=365):
    _ = lookback_days
    return get_restricted_ticker_entry(ticker) is not None

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
    ts_value = float(timestamp)
    state["last_switch_time"] = ts_value
    events = _prune_switch_events(state.get("switch_events", []), ts_value)
    events.append(ts_value)
    state["switch_events"] = events
    save_pair_state(state)

def set_last_switch_reason(reason):
    state = load_pair_state()
    state["last_switch_reason"] = str(reason or "")
    save_pair_state(state)

def get_last_switch_reason():
    state = load_pair_state()
    return state.get("last_switch_reason", "")


def get_switch_rate_limit_remaining():
    state = load_pair_state()
    now = time.time()
    try:
        until_ts = float(state.get("switch_rate_limit_until_ts", 0.0) or 0.0)
    except (TypeError, ValueError):
        until_ts = 0.0

    remaining = until_ts - now
    if remaining <= 0:
        if until_ts > 0:
            state["switch_rate_limit_until_ts"] = 0.0
            save_pair_state(state)
        return 0.0
    return float(remaining)

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
    state["entry_ts"] = state["entry_time"]
    state["coint_lost_since_ts"] = None
    state["coint_lost_confirm_count"] = 0
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


def get_coint_lost_since_ts():
    """Get cointegration-lost timer start timestamp."""
    state = load_pair_state()
    value = state.get("coint_lost_since_ts")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def set_coint_lost_since_ts(timestamp=None):
    """Set cointegration-lost timer start timestamp."""
    state = load_pair_state()
    if timestamp is None:
        timestamp = time.time()
    try:
        state["coint_lost_since_ts"] = float(timestamp)
    except (TypeError, ValueError):
        state["coint_lost_since_ts"] = time.time()
    save_pair_state(state)


def clear_coint_lost_since_ts():
    """Clear cointegration-lost timer start timestamp."""
    state = load_pair_state()
    if state.get("coint_lost_since_ts") is not None:
        state["coint_lost_since_ts"] = None
        save_pair_state(state)


def get_coint_lost_confirm_count():
    """Get consecutive monitor cycles with coint_flag == 0."""
    state = load_pair_state()
    try:
        value = int(state.get("coint_lost_confirm_count", 0) or 0)
    except (TypeError, ValueError):
        value = 0
    return max(value, 0)


def set_coint_lost_confirm_count(count):
    """Set consecutive monitor cycles with coint_flag == 0."""
    state = load_pair_state()
    try:
        value = int(count)
    except (TypeError, ValueError):
        value = 0
    if value < 0:
        value = 0
    state["coint_lost_confirm_count"] = value
    save_pair_state(state)


def clear_coint_lost_confirm_count():
    """Reset coint lost confirmation counter."""
    state = load_pair_state()
    if int(state.get("coint_lost_confirm_count", 0) or 0) != 0:
        state["coint_lost_confirm_count"] = 0
        save_pair_state(state)

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

def set_entry_trade_context(strategy_name=None, regime_name=None, policy_snapshot=None, entry_ts=None):
    """Persist entry strategy/regime context for close-time attribution."""
    state = load_pair_state()
    strategy = str(strategy_name or "").strip().upper()
    regime = str(regime_name or "").strip().upper()
    state["entry_strategy"] = strategy or None
    state["entry_regime"] = regime or None
    if isinstance(policy_snapshot, dict):
        state["entry_policy_snapshot"] = dict(policy_snapshot)
    elif not isinstance(state.get("entry_policy_snapshot"), dict):
        state["entry_policy_snapshot"] = {}
    try:
        if entry_ts is None:
            entry_ts = state.get("entry_time")
        state["entry_ts"] = float(entry_ts) if entry_ts is not None else None
    except (TypeError, ValueError):
        state["entry_ts"] = None
    save_pair_state(state)

def get_entry_strategy():
    """Get persisted strategy context for the open trade."""
    state = load_pair_state()
    return state.get("entry_strategy")

def get_entry_regime():
    """Get persisted regime context for the open trade."""
    state = load_pair_state()
    return state.get("entry_regime")

def get_entry_policy_snapshot():
    """Get entry policy snapshot persisted at open."""
    state = load_pair_state()
    snapshot = state.get("entry_policy_snapshot")
    if isinstance(snapshot, dict):
        return dict(snapshot)
    return {}

def get_entry_ts():
    """Get persisted entry timestamp used for strategy attribution."""
    state = load_pair_state()
    try:
        value = state.get("entry_ts")
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

def clear_entry_tracking():
    """Clear entry tracking when position is closed."""
    state = load_pair_state()
    state["entry_z_score"] = None
    state["entry_time"] = None
    state["coint_lost_since_ts"] = None
    state["coint_lost_confirm_count"] = 0
    state["entry_equity"] = None
    state["entry_notional"] = None
    state["entry_strategy"] = None
    state["entry_regime"] = None
    state["entry_policy_snapshot"] = {}
    state["entry_ts"] = None
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

def can_switch(
    cooldown_hours=24,
    health_score=None,
    emergency_threshold=25,
    bypass_rate_limit=False,
    bypass_cooldown=False,
):
    """
    Check if pair switching is allowed.

    Args:
        cooldown_hours: Normal cooldown period in hours (default: 24)
        health_score: Current pair health score (0-100). If provided and below emergency_threshold, overrides cooldown
        emergency_threshold: Health score threshold for emergency override (default: 25)
        bypass_rate_limit: When True, ignore sliding-window/rate-limit blocks.
        bypass_cooldown: When True, ignore elapsed-time cooldown checks.

    Returns:
        bool: True if switching is allowed, False otherwise
    """
    state = load_pair_state()
    now_ts = time.time()

    if not bypass_rate_limit:
        # 1) Hard block while switch rate-limit cooldown is active.
        try:
            until_ts = float(state.get("switch_rate_limit_until_ts", 0.0) or 0.0)
        except (TypeError, ValueError):
            until_ts = 0.0
        if until_ts > now_ts:
            return False

        # 2) Sliding-window rate limiter.
        max_switches, switch_cooldown_seconds = _switch_limit_settings()
        events = _prune_switch_events(state.get("switch_events", []), now_ts)
        if max_switches > 0 and len(events) >= max_switches:
            if switch_cooldown_seconds > 0:
                state["switch_rate_limit_until_ts"] = now_ts + switch_cooldown_seconds
            else:
                state["switch_rate_limit_until_ts"] = 0.0
            state["switch_events"] = events
            save_pair_state(state)
            return False
        if events != state.get("switch_events", []):
            state["switch_events"] = events
            save_pair_state(state)

    last_switch = get_last_switch_time()
    time_since_switch = now_ts - last_switch
    cooldown_seconds = cooldown_hours * 60 * 60

    if bypass_cooldown:
        return True

    # Emergency override: health is critically bad, ignore cooldown
    if health_score is not None and health_score < emergency_threshold:
        return True

    # Normal cooldown check
    if time_since_switch < cooldown_seconds:
        return False
    return True
