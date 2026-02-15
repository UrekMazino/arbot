import json
import time
from pathlib import Path

_STATE_DIR = Path(__file__).resolve().parent / "state"
STATE_FILE = _STATE_DIR / "regime_state.json"


def _default_state():
    return {
        "version": 1,
        "mode": "off",
        "current_regime": "RANGE",
        "candidate_regime": "RANGE",
        "confidence": 0.0,
        "since_ts": 0.0,
        "pending_candidate": "",
        "pending_count": 0,
        "reason_codes": [],
        "diagnostics": {},
        "last_eval_ts": 0.0,
        "updated_ts": 0.0,
    }


def _coerce_state(state):
    base = _default_state()
    if not isinstance(state, dict):
        return base
    base.update(state)
    if not isinstance(base.get("reason_codes"), list):
        base["reason_codes"] = []
    if not isinstance(base.get("diagnostics"), dict):
        base["diagnostics"] = {}
    try:
        base["confidence"] = float(base.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        base["confidence"] = 0.0
    try:
        base["since_ts"] = float(base.get("since_ts", 0.0) or 0.0)
    except (TypeError, ValueError):
        base["since_ts"] = 0.0
    try:
        base["last_eval_ts"] = float(base.get("last_eval_ts", 0.0) or 0.0)
    except (TypeError, ValueError):
        base["last_eval_ts"] = 0.0
    try:
        base["updated_ts"] = float(base.get("updated_ts", 0.0) or 0.0)
    except (TypeError, ValueError):
        base["updated_ts"] = 0.0
    try:
        base["pending_count"] = int(base.get("pending_count", 0) or 0)
    except (TypeError, ValueError):
        base["pending_count"] = 0
    return base


def load_regime_state():
    if not STATE_FILE.exists():
        return _default_state()
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return _default_state()
    return _coerce_state(data)


def save_regime_state(state):
    payload = _coerce_state(state)
    payload["updated_ts"] = time.time()
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        with STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception:
        return False
    return True


def update_regime_state(decision, inputs=None):
    state = load_regime_state()

    if isinstance(decision, dict):
        get_value = decision.get
    else:
        get_value = lambda k, default=None: getattr(decision, k, default)

    state["mode"] = str(get_value("mode", state.get("mode", "off")) or "off")
    state["current_regime"] = str(get_value("regime", state.get("current_regime", "RANGE")) or "RANGE")
    state["candidate_regime"] = str(get_value("candidate_regime", state.get("candidate_regime", "RANGE")) or "RANGE")
    state["confidence"] = float(get_value("confidence", state.get("confidence", 0.0)) or 0.0)
    state["reason_codes"] = list(get_value("reason_codes", []) or [])
    state["diagnostics"] = dict(get_value("diagnostics", {}) or {})

    diagnostics = state["diagnostics"]
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
            diagnostics["input_ts"] = state["last_eval_ts"]

    if get_value("changed", False):
        state["since_ts"] = state.get("last_eval_ts") or time.time()
        state["pending_candidate"] = ""
        state["pending_count"] = 0
    else:
        pending_candidate = get_value("pending_candidate", None)
        pending_count = get_value("pending_count", None)
        if pending_candidate is not None:
            state["pending_candidate"] = str(pending_candidate or "")
        if pending_count is not None:
            try:
                state["pending_count"] = int(pending_count)
            except (TypeError, ValueError):
                pass

    save_regime_state(state)
    return state


def reset_regime_state(reason="pair_switch", mode=None, regime="RANGE"):
    previous = load_regime_state()
    fresh = _default_state()

    if mode is None:
        mode = previous.get("mode", "off")
    mode_value = str(mode or "off").strip().lower()
    if mode_value not in ("off", "shadow", "active"):
        mode_value = "off"

    regime_value = str(regime or "RANGE").strip().upper()
    if regime_value not in ("RANGE", "TREND", "RISK_OFF"):
        regime_value = "RANGE"

    now = time.time()
    fresh["mode"] = mode_value
    fresh["current_regime"] = regime_value
    fresh["candidate_regime"] = regime_value
    fresh["since_ts"] = now
    fresh["diagnostics"] = {
        "reset_reason": str(reason or "pair_switch"),
        "reset_ts": now,
    }
    save_regime_state(fresh)
    return fresh
