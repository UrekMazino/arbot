import json
import os
import time
from pathlib import Path

_STATE_DIR = Path(__file__).resolve().parent / "state"
STATE_FILE = _STATE_DIR / "strategy_state.json"
DEFAULT_SCORE_WINDOW_TRADES = 20
VALID_STRATEGIES = ("STATARB_MR", "TREND_SPREAD", "DEFENSIVE", "UNKNOWN")


def _env_int(name, default):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default


def _score_window_trades():
    value = _env_int("STATBOT_STRATEGY_SCORE_WINDOW_TRADES", DEFAULT_SCORE_WINDOW_TRADES)
    if value < 1:
        value = DEFAULT_SCORE_WINDOW_TRADES
    return min(value, 500)


def _normalize_strategy_name(name):
    strategy = str(name or "UNKNOWN").strip().upper()
    if strategy in VALID_STRATEGIES:
        return strategy
    return "UNKNOWN"


def _safe_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _default_strategy_stats():
    return {
        "trades_total": 0,
        "wins_total": 0,
        "losses_total": 0,
        "pnl_total_usdt": 0.0,
        "avg_pnl_usdt": None,
        "hold_minutes_total": 0.0,
        "hold_samples": 0,
        "avg_hold_minutes": None,
        "rolling_trades": [],
        "rolling_count": 0,
        "rolling_wins": 0,
        "rolling_win_rate_pct": None,
        "rolling_pnl_usdt": 0.0,
        "last_trade_ts": 0.0,
        "last_regime": "",
        "last_exit_reason": "",
    }


def _default_strategy_performance():
    return {
        "window_trades": _score_window_trades(),
        "stats": {},
    }


def _coerce_strategy_stats(raw_stats, window):
    stats = _default_strategy_stats()
    if isinstance(raw_stats, dict):
        stats.update(raw_stats)
    try:
        stats["trades_total"] = int(stats.get("trades_total", 0) or 0)
    except (TypeError, ValueError):
        stats["trades_total"] = 0
    try:
        stats["wins_total"] = int(stats.get("wins_total", 0) or 0)
    except (TypeError, ValueError):
        stats["wins_total"] = 0
    try:
        stats["losses_total"] = int(stats.get("losses_total", 0) or 0)
    except (TypeError, ValueError):
        stats["losses_total"] = 0
    stats["pnl_total_usdt"] = _safe_float(stats.get("pnl_total_usdt"), 0.0)
    stats["hold_minutes_total"] = _safe_float(stats.get("hold_minutes_total"), 0.0)
    try:
        stats["hold_samples"] = int(stats.get("hold_samples", 0) or 0)
    except (TypeError, ValueError):
        stats["hold_samples"] = 0
    stats["last_trade_ts"] = _safe_float(stats.get("last_trade_ts"), 0.0)
    stats["last_regime"] = str(stats.get("last_regime") or "").strip().upper()
    stats["last_exit_reason"] = str(stats.get("last_exit_reason") or "").strip().lower()
    if not isinstance(stats.get("rolling_trades"), list):
        stats["rolling_trades"] = []
    sanitized = []
    for item in stats["rolling_trades"][-max(int(window), 1):]:
        if not isinstance(item, dict):
            continue
        pnl_usdt = _safe_float(item.get("pnl_usdt"))
        ts_val = _safe_float(item.get("ts"))
        if pnl_usdt is None or ts_val is None:
            continue
        hold_val = _safe_float(item.get("hold_minutes"))
        sanitized.append(
            {
                "ts": ts_val,
                "pnl_usdt": pnl_usdt,
                "win": 1 if int(_safe_float(item.get("win"), 0) or 0) == 1 else 0,
                "regime": str(item.get("regime") or "").strip().upper(),
                "hold_minutes": hold_val,
                "exit_reason": str(item.get("exit_reason") or "").strip().lower(),
            }
        )
    stats["rolling_trades"] = sanitized
    rolling_count = len(sanitized)
    rolling_wins = sum(int(item.get("win", 0)) for item in sanitized)
    rolling_pnl = sum(float(item.get("pnl_usdt", 0.0) or 0.0) for item in sanitized)
    stats["rolling_count"] = rolling_count
    stats["rolling_wins"] = rolling_wins
    stats["rolling_pnl_usdt"] = round(rolling_pnl, 4)
    stats["rolling_win_rate_pct"] = round((rolling_wins / rolling_count) * 100, 2) if rolling_count > 0 else None
    stats["avg_pnl_usdt"] = (
        round(stats["pnl_total_usdt"] / stats["trades_total"], 4) if stats["trades_total"] > 0 else None
    )
    stats["avg_hold_minutes"] = (
        round(stats["hold_minutes_total"] / stats["hold_samples"], 2) if stats["hold_samples"] > 0 else None
    )
    return stats


def _coerce_strategy_performance(raw_perf):
    perf = _default_strategy_performance()
    if isinstance(raw_perf, dict):
        perf.update(raw_perf)
    window = _safe_float(perf.get("window_trades"))
    if window is None:
        window = _score_window_trades()
    window = int(max(min(window, 500), 1))
    perf["window_trades"] = window
    stats_in = perf.get("stats")
    if not isinstance(stats_in, dict):
        stats_in = {}
    stats_out = {}
    for key, value in stats_in.items():
        strategy = _normalize_strategy_name(key)
        stats_out[strategy] = _coerce_strategy_stats(value, window)
    perf["stats"] = stats_out
    return perf


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
        "strategy_performance": _default_strategy_performance(),
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
    base["strategy_performance"] = _coerce_strategy_performance(base.get("strategy_performance"))

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


def record_strategy_trade_result(
    strategy_name,
    pnl_usdt,
    regime_name="",
    hold_minutes=None,
    exit_reason="",
    trade_ts=None,
):
    """
    Persist per-strategy realized trade stats with a rolling window.

    This is observability state only and does not drive entry/exit behavior.
    """
    state = load_strategy_state()
    perf = _coerce_strategy_performance(state.get("strategy_performance"))
    window = int(perf.get("window_trades", _score_window_trades()) or _score_window_trades())
    strategy = _normalize_strategy_name(strategy_name)
    regime = str(regime_name or "").strip().upper()
    reason = str(exit_reason or "").strip().lower()
    pnl_val = _safe_float(pnl_usdt, 0.0)
    hold_val = _safe_float(hold_minutes, None)
    ts_val = _safe_float(trade_ts, None)
    if ts_val is None:
        ts_val = time.time()

    stats_map = perf.get("stats")
    if not isinstance(stats_map, dict):
        stats_map = {}
        perf["stats"] = stats_map
    stats = _coerce_strategy_stats(stats_map.get(strategy), window)

    stats["trades_total"] += 1
    if pnl_val > 0:
        stats["wins_total"] += 1
    else:
        stats["losses_total"] += 1
    stats["pnl_total_usdt"] = float(stats.get("pnl_total_usdt", 0.0) or 0.0) + pnl_val
    stats["avg_pnl_usdt"] = round(stats["pnl_total_usdt"] / stats["trades_total"], 4)
    if hold_val is not None and hold_val >= 0:
        stats["hold_minutes_total"] = float(stats.get("hold_minutes_total", 0.0) or 0.0) + hold_val
        stats["hold_samples"] = int(stats.get("hold_samples", 0) or 0) + 1
    stats["avg_hold_minutes"] = (
        round(stats["hold_minutes_total"] / stats["hold_samples"], 2) if stats["hold_samples"] > 0 else None
    )
    stats["last_trade_ts"] = float(ts_val)
    stats["last_regime"] = regime
    stats["last_exit_reason"] = reason

    rolling = list(stats.get("rolling_trades") or [])
    rolling.append(
        {
            "ts": float(ts_val),
            "pnl_usdt": float(pnl_val),
            "win": 1 if pnl_val > 0 else 0,
            "regime": regime,
            "hold_minutes": hold_val,
            "exit_reason": reason,
        }
    )
    if len(rolling) > window:
        rolling = rolling[-window:]
    stats["rolling_trades"] = rolling
    stats["rolling_count"] = len(rolling)
    stats["rolling_wins"] = sum(int(item.get("win", 0)) for item in rolling)
    stats["rolling_pnl_usdt"] = round(sum(float(item.get("pnl_usdt", 0.0) or 0.0) for item in rolling), 4)
    stats["rolling_win_rate_pct"] = (
        round((stats["rolling_wins"] / stats["rolling_count"]) * 100, 2)
        if stats["rolling_count"] > 0
        else None
    )

    stats_map[strategy] = stats
    perf["stats"] = stats_map
    state["strategy_performance"] = perf
    save_strategy_state(state)
    return dict(stats)


def get_strategy_performance():
    """Read-only accessor for strategy performance state."""
    state = load_strategy_state()
    perf = state.get("strategy_performance")
    if not isinstance(perf, dict):
        return _default_strategy_performance()
    return _coerce_strategy_performance(perf)
