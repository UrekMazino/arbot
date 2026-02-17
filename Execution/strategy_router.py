import math
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from func_strategy_state import load_strategy_state, save_strategy_state


def _env_str(name, default):
    raw = os.getenv(name)
    if raw is None:
        return default
    value = str(raw).strip()
    return value if value else default


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


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _decision_get(decision, key, default=None):
    if isinstance(decision, dict):
        return decision.get(key, default)
    return getattr(decision, key, default)


def _normalize_regime(value):
    regime = str(value or "RANGE").strip().upper()
    if regime not in ("RANGE", "TREND", "RISK_OFF"):
        return "RANGE"
    return regime


def _normalize_strategy(value):
    strategy = str(value or "STATARB_MR").strip().upper()
    if strategy not in ("STATARB_MR", "TREND_SPREAD", "DEFENSIVE"):
        return "STATARB_MR"
    return strategy


def _tail_stats(series, window):
    if window <= 1 or not series or len(series) < window:
        return None, None
    tail = [float(v) for v in series[-window:]]
    mean_val = sum(tail) / float(len(tail))
    variance = sum((v - mean_val) ** 2 for v in tail) / float(len(tail))
    return mean_val, math.sqrt(max(variance, 0.0))


@dataclass
class StrategyInput:
    ts: float
    regime_decision: Optional[object]
    in_position: bool
    coint_flag: int
    zscore_history: List[float]
    spread_history: Optional[List[float]] = None


@dataclass
class StrategyDecision:
    mode: str
    active_strategy: str
    desired_strategy: str
    pending_strategy: str
    changed: bool
    allow_new_entries: bool
    size_multiplier: float
    entry_z: float
    entry_z_max: float
    min_persist_bars: int
    min_liquidity_ratio: float
    reason_codes: List[str]
    diagnostics: Dict
    pending_count: int = 0


class StrategyRouter:
    VALID_MODES = {"off", "shadow", "active"}

    def __init__(self, state_store=None, config=None):
        self._state_store = state_store
        self.state = self._load_state()

        self.mode = _env_str("STATBOT_STRATEGY_ROUTER_MODE", "off").strip().lower()
        if self.mode not in self.VALID_MODES:
            self.mode = "off"

        self.config = {
            "min_hold_seconds": max(_env_int("STATBOT_STRATEGY_MIN_HOLD_SECONDS", 900), 0),
            "confirm_count": max(_env_int("STATBOT_STRATEGY_CONFIRM_COUNT", 2), 1),
            "allow_switch_in_position": _env_flag("STATBOT_STRATEGY_ALLOW_SWITCH_IN_POSITION", False),
            "mr_entry_z": 2.0,
            "mr_entry_z_max": 3.0,
            "mr_min_persist": 4,
            "mr_size_mult": 1.0,
            "mr_min_liq_ratio": 1.5,
            "trend_entry_z": max(_env_float("STATBOT_STRATEGY_TREND_ENTRY_Z", 2.8), 0.1),
            "trend_entry_z_max": max(_env_float("STATBOT_STRATEGY_TREND_ENTRY_Z_MAX", 5.0), 0.1),
            "trend_min_persist": max(_env_int("STATBOT_STRATEGY_TREND_MIN_PERSIST", 4), 1),
            "trend_size_mult": max(_env_float("STATBOT_STRATEGY_TREND_SIZE_MULT", 0.35), 0.0),
            "trend_min_liq_ratio": max(_env_float("STATBOT_STRATEGY_TREND_MIN_LIQ_RATIO", 2.0), 0.0),
            "enable_mean_shift_gate": _env_flag("STATBOT_STRATEGY_TREND_ENABLE_MEAN_SHIFT_GATE", True),
            "mean_short_window": max(_env_int("STATBOT_STRATEGY_TREND_MEAN_SHORT_WINDOW", 21), 2),
            "mean_long_window": max(_env_int("STATBOT_STRATEGY_TREND_MEAN_LONG_WINDOW", 200), 5),
            "mean_shift_z_threshold": max(_env_float("STATBOT_STRATEGY_TREND_MEAN_SHIFT_Z_THRESHOLD", 1.0), 0.1),
        }
        if isinstance(config, dict):
            self.config.update(config)

    def _load_state(self):
        if self._state_store and hasattr(self._state_store, "load"):
            try:
                loaded = self._state_store.load()
                if isinstance(loaded, dict):
                    return loaded
            except Exception:
                pass
        return load_strategy_state()

    def _save_state(self, state):
        if self._state_store and hasattr(self._state_store, "save"):
            try:
                self._state_store.save(state)
                return
            except Exception:
                pass
        save_strategy_state(state)

    def _extract_regime(self, regime_decision):
        if regime_decision is None:
            return "RANGE", 0.0
        regime = _normalize_regime(_decision_get(regime_decision, "regime", "RANGE"))
        confidence = _safe_float(_decision_get(regime_decision, "confidence", 0.0), 0.0)
        return regime, confidence

    @staticmethod
    def _map_strategy(regime):
        if regime == "TREND":
            return "TREND_SPREAD"
        if regime == "RISK_OFF":
            return "DEFENSIVE"
        return "STATARB_MR"

    def _profile(self, strategy):
        if strategy == "TREND_SPREAD":
            entry_z = self.config["trend_entry_z"]
            entry_z_max = self.config["trend_entry_z_max"]
            if entry_z_max < entry_z:
                entry_z_max = entry_z
            return {
                "allow_new_entries": True,
                "entry_z": entry_z,
                "entry_z_max": entry_z_max,
                "min_persist_bars": self.config["trend_min_persist"],
                "min_liquidity_ratio": self.config["trend_min_liq_ratio"],
                "size_multiplier": self.config["trend_size_mult"],
            }
        if strategy == "DEFENSIVE":
            return {
                "allow_new_entries": False,
                "entry_z": 999.0,
                "entry_z_max": 999.0,
                "min_persist_bars": 6,
                "min_liquidity_ratio": 3.0,
                "size_multiplier": 0.0,
            }
        return {
            "allow_new_entries": True,
            "entry_z": self.config["mr_entry_z"],
            "entry_z_max": self.config["mr_entry_z_max"],
            "min_persist_bars": self.config["mr_min_persist"],
            "min_liquidity_ratio": self.config["mr_min_liq_ratio"],
            "size_multiplier": self.config["mr_size_mult"],
        }

    def _compute_mean_shift_gate(self, inputs: StrategyInput):
        if not self.config["enable_mean_shift_gate"]:
            return False, 0.0, "disabled"

        short_w = int(self.config["mean_short_window"])
        long_w = int(self.config["mean_long_window"])
        if long_w < short_w:
            long_w = short_w

        spread_series = []
        for value in inputs.spread_history or []:
            try:
                spread_series.append(float(value))
            except (TypeError, ValueError):
                continue

        basis = "spread"
        if len(spread_series) < long_w:
            basis = "zscore"
            spread_series = []
            for value in inputs.zscore_history or []:
                try:
                    spread_series.append(float(value))
                except (TypeError, ValueError):
                    continue

        if len(spread_series) < long_w:
            return False, 0.0, basis

        mu_short, sigma_short = _tail_stats(spread_series, short_w)
        mu_long, _ = _tail_stats(spread_series, long_w)
        if mu_short is None or mu_long is None:
            return False, 0.0, basis

        sigma_val = max(float(sigma_short or 0.0), 1e-9)
        shift_z = abs(mu_short - mu_long) / sigma_val
        threshold = float(self.config["mean_shift_z_threshold"])
        return bool(shift_z > threshold), float(shift_z), basis

    def evaluate(self, inputs: StrategyInput) -> StrategyDecision:
        state = dict(self.state or {})
        ts = _safe_float(inputs.ts, 0.0)
        regime, regime_confidence = self._extract_regime(inputs.regime_decision)

        active_strategy = _normalize_strategy(state.get("active_strategy", "STATARB_MR"))
        desired_strategy = self._map_strategy(regime)
        pending_strategy = _normalize_strategy(state.get("pending_strategy", "")) if state.get("pending_strategy") else ""
        pending_count = int(_safe_float(state.get("pending_count", 0), 0))
        changed = False

        since_ts = _safe_float(state.get("since_ts", ts), ts)
        if since_ts <= 0:
            since_ts = ts
        hold_seconds = max(ts - since_ts, 0.0)

        if self.mode == "off":
            active_strategy = "STATARB_MR"
            desired_strategy = "STATARB_MR"
            pending_strategy = ""
            pending_count = 0
        else:
            if desired_strategy == active_strategy:
                pending_strategy = ""
                pending_count = 0
            else:
                if pending_strategy == desired_strategy:
                    pending_count += 1
                else:
                    pending_strategy = desired_strategy
                    pending_count = 1

                meets_hold = hold_seconds >= float(self.config["min_hold_seconds"])
                meets_confirm = pending_count >= int(self.config["confirm_count"])
                can_switch_now = (not bool(inputs.in_position)) or bool(self.config["allow_switch_in_position"])
                if meets_hold and meets_confirm and can_switch_now:
                    active_strategy = desired_strategy
                    pending_strategy = ""
                    pending_count = 0
                    changed = True
                    since_ts = ts

        profile = self._profile(active_strategy)
        allow_new_entries = bool(profile["allow_new_entries"])
        reason_codes = []
        diagnostics = {
            "regime": regime,
            "regime_confidence": regime_confidence,
            "hold_seconds": hold_seconds,
            "in_position": bool(inputs.in_position),
            "coint_flag": int(_safe_float(inputs.coint_flag, 0)),
        }

        if regime == "RISK_OFF":
            allow_new_entries = False
            reason_codes.append("risk_off_policy")

        coint_flag = int(_safe_float(inputs.coint_flag, 0))
        if coint_flag != 1:
            allow_new_entries = False
            reason_codes.append("coint_gate")

        if active_strategy == "TREND_SPREAD":
            mean_shift_gate, shift_z, shift_basis = self._compute_mean_shift_gate(inputs)
            diagnostics["mean_shift_gate"] = bool(mean_shift_gate)
            diagnostics["mean_shift_z"] = float(shift_z)
            diagnostics["mean_shift_basis"] = shift_basis
            diagnostics["mean_shift_threshold"] = float(self.config["mean_shift_z_threshold"])
            if mean_shift_gate:
                allow_new_entries = False
                reason_codes.append("mean_shift_gate")

        if active_strategy == "DEFENSIVE":
            allow_new_entries = False
            if "defensive_strategy" not in reason_codes:
                reason_codes.append("defensive_strategy")

        decision = StrategyDecision(
            mode=self.mode,
            active_strategy=active_strategy,
            desired_strategy=desired_strategy,
            pending_strategy=pending_strategy,
            pending_count=pending_count,
            changed=changed,
            allow_new_entries=allow_new_entries,
            size_multiplier=float(profile["size_multiplier"]),
            entry_z=float(profile["entry_z"]),
            entry_z_max=float(profile["entry_z_max"]),
            min_persist_bars=int(profile["min_persist_bars"]),
            min_liquidity_ratio=float(profile["min_liquidity_ratio"]),
            reason_codes=reason_codes,
            diagnostics=diagnostics,
        )

        self._persist_state(decision, ts, since_ts)
        return decision

    def _persist_state(self, decision: StrategyDecision, ts: float, since_ts: float):
        # Reload latest state before writing to avoid overwriting
        # out-of-band updates like strategy_performance trade counters.
        latest_state = self._load_state()
        state = {}
        if isinstance(latest_state, dict):
            state.update(latest_state)
        if isinstance(self.state, dict):
            for key, value in self.state.items():
                state.setdefault(key, value)
        previous_active = _normalize_strategy(state.get("active_strategy", "STATARB_MR"))

        state["mode"] = self.mode
        state["active_strategy"] = decision.active_strategy
        state["desired_strategy"] = decision.desired_strategy
        state["pending_strategy"] = decision.pending_strategy
        state["pending_count"] = int(decision.pending_count)
        state["last_eval_ts"] = float(ts)
        state["reason_codes"] = list(decision.reason_codes)
        state["diagnostics"] = dict(decision.diagnostics)

        if decision.changed or previous_active != decision.active_strategy:
            state["since_ts"] = float(ts)
            state["strategy_switch_count"] = int(state.get("strategy_switch_count", 0) or 0) + 1
        else:
            state["since_ts"] = float(since_ts or ts)

        self.state = state
        self._save_state(state)


def should_block_new_entries(mode, decision) -> bool:
    """Return True only for active-mode decisions that disallow entries."""
    if str(mode or "").strip().lower() != "active":
        return False
    if decision is None:
        return False
    if isinstance(decision, dict):
        allow_new = decision.get("allow_new_entries", True)
    else:
        allow_new = getattr(decision, "allow_new_entries", True)
    return not bool(allow_new)


def resolve_strategy_policy_overrides(mode, decision):
    """
    Return normalized policy overrides for active strategy-router mode.

    Off/shadow modes return inert overrides to preserve baseline behavior.
    """
    overrides = {
        "active": False,
        "strategy_name": "STATARB_MR",
        "allow_new_entries": True,
        "entry_z": None,
        "entry_z_max": None,
        "min_persist_bars": None,
        "min_liquidity_ratio": None,
        "size_multiplier": None,
    }

    if str(mode or "").strip().lower() != "active" or decision is None:
        return overrides

    overrides["active"] = True
    overrides["strategy_name"] = _normalize_strategy(_decision_get(decision, "active_strategy", "STATARB_MR"))
    overrides["allow_new_entries"] = bool(_decision_get(decision, "allow_new_entries", True))

    entry_z = _safe_float(_decision_get(decision, "entry_z", None), None)
    if entry_z is not None and entry_z > 0:
        overrides["entry_z"] = entry_z

    entry_z_max = _safe_float(_decision_get(decision, "entry_z_max", None), None)
    if entry_z_max is not None and entry_z_max > 0:
        if overrides["entry_z"] is not None and entry_z_max < overrides["entry_z"]:
            entry_z_max = overrides["entry_z"]
        overrides["entry_z_max"] = entry_z_max

    min_persist_raw = _safe_float(_decision_get(decision, "min_persist_bars", None), None)
    if min_persist_raw is not None:
        min_persist = int(min_persist_raw)
        if min_persist >= 1:
            overrides["min_persist_bars"] = min_persist

    min_liq = _safe_float(_decision_get(decision, "min_liquidity_ratio", None), None)
    if min_liq is not None:
        overrides["min_liquidity_ratio"] = max(min_liq, 0.0)

    size_mult = _safe_float(_decision_get(decision, "size_multiplier", None), None)
    if size_mult is not None:
        overrides["size_multiplier"] = max(size_mult, 0.0)

    return overrides
