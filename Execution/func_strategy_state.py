import json
import time
from pathlib import Path

_STATE_DIR = Path(__file__).resolve().parent / "state"
STATE_FILE = _STATE_DIR / "strategy_state.json"


def _default_state():
    return {
        "version": 1,
        "mode": "off",
        "active_strategy": "STATARB_MR",
        "desired_strategy": "STATARB_MR",
        "pending_strategy": "",
        "pending_count": 0,
        "since_ts": 0.0,
        "last_eval_ts": 0.0,
        "strategy_switch_count": 0,
        "reason_codes": [],
        "diagnostics": {},
        "updated_ts": 0.0,
    }


def _coerce_state(state):
    base = _default_state()
    if not isinstance(state, dict):
        return base
    base.update(state)
    base["mode"] = str(base.get("mode", "off") or "off").strip().lower()
    base["active_strategy"] = str(base.get("active_strategy", "STATARB_MR") or "STATARB_MR").strip().upper()
    base["desired_strategy"] = str(base.get("desired_strategy", "STATARB_MR") or "STATARB_MR").strip().upper()
    base["pending_strategy"] = str(base.get("pending_strategy", "") or "").strip().upper()
    if not isinstance(base.get("reason_codes"), list):
        base["reason_codes"] = []
    if not isinstance(base.get("diagnostics"), dict):
        base["diagnostics"] = {}

    try:
        base["pending_count"] = int(base.get("pending_count", 0) or 0)
    except (TypeError, ValueError):
        base["pending_count"] = 0

    try:
        base["since_ts"] = float(base.get("since_ts", 0.0) or 0.0)
    except (TypeError, ValueError):
        base["since_ts"] = 0.0

    try:
        base["last_eval_ts"] = float(base.get("last_eval_ts", 0.0) or 0.0)
    except (TypeError, ValueError):
        base["last_eval_ts"] = 0.0

    try:
        base["strategy_switch_count"] = int(base.get("strategy_switch_count", 0) or 0)
    except (TypeError, ValueError):
        base["strategy_switch_count"] = 0

    try:
        base["updated_ts"] = float(base.get("updated_ts", 0.0) or 0.0)
    except (TypeError, ValueError):
        base["updated_ts"] = 0.0

    return base


def load_strategy_state():
    if not STATE_FILE.exists():
        return _default_state()
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return _default_state()
    return _coerce_state(data)


def save_strategy_state(state):
    payload = _coerce_state(state)
    payload["updated_ts"] = time.time()
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        with STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        return False
    return True


def update_strategy_state(decision, inputs=None):
    state = load_strategy_state()

    if isinstance(decision, dict):
        get_value = decision.get
    else:
        get_value = lambda k, default=None: getattr(decision, k, default)

    state["mode"] = str(get_value("mode", state.get("mode", "off")) or "off").strip().lower()
    state["active_strategy"] = str(
        get_value("active_strategy", state.get("active_strategy", "STATARB_MR")) or "STATARB_MR"
    ).strip().upper()
    state["desired_strategy"] = str(
        get_value("desired_strategy", state.get("desired_strategy", "STATARB_MR")) or "STATARB_MR"
    ).strip().upper()
    state["pending_strategy"] = str(
        get_value("pending_strategy", state.get("pending_strategy", "")) or ""
    ).strip().upper()
    state["reason_codes"] = list(get_value("reason_codes", []) or [])
    state["diagnostics"] = dict(get_value("diagnostics", {}) or {})

    pending_count = get_value("pending_count", state.get("pending_count", 0))
    try:
        state["pending_count"] = int(pending_count or 0)
    except (TypeError, ValueError):
        pass

    if inputs is not None:
        if isinstance(inputs, dict):
            ts_value = inputs.get("ts")
        else:
            ts_value = getattr(inputs, "ts", None)
        if ts_value is not None:
            try:
                state["last_eval_ts"] = float(ts_value)
            except (TypeError, ValueError):
                pass

    if get_value("changed", False):
        state["since_ts"] = state.get("last_eval_ts") or time.time()
        state["strategy_switch_count"] = int(state.get("strategy_switch_count", 0) or 0) + 1

    save_strategy_state(state)
    return state

