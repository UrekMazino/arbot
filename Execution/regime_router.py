import math
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from func_regime_state import load_regime_state, save_regime_state


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


def _clip(value, low, high):
    if value < low:
        return low
    if value > high:
        return high
    return value


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _ema(values, span):
    if not values:
        return 0.0
    alpha = 2.0 / (float(span) + 1.0)
    ema_val = float(values[0])
    for value in values[1:]:
        ema_val = (alpha * float(value)) + ((1.0 - alpha) * ema_val)
    return ema_val


def _rolling_mean(values, period):
    out = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    running = 0.0
    for idx, value in enumerate(values):
        running += value
        if idx >= period:
            running -= values[idx - period]
        if idx >= period - 1:
            out[idx] = running / period
    return out


@dataclass
class RegimeInput:
    ts: float
    ticker_1: str
    ticker_2: str
    latest_zscore: Optional[float]
    z_metrics: Dict
    market_candles: List[Dict]
    liq_long: Dict
    liq_short: Dict
    per_leg_target_usdt: float
    pnl_fallback_active: bool
    session_drawdown_pct: float


@dataclass
class RegimeDecision:
    mode: str
    regime: str
    candidate_regime: str
    confidence: float
    changed: bool
    allow_new_entries: bool
    entry_z: float
    entry_z_max: float
    min_persist_bars: int
    min_liquidity_ratio: float
    size_multiplier: float
    reason_codes: List[str]
    diagnostics: Dict
    pending_candidate: str = ""
    pending_count: int = 0


class RegimeRouter:
    VALID_REGIMES = {"RANGE", "TREND", "RISK_OFF"}
    VALID_MODES = {"off", "shadow", "active"}
    HARD_RISK_REASONS = {"orderbook_dead", "cointegration_lost", "vol_shock"}

    def __init__(self, state_store=None, config=None):
        self._state_store = state_store
        self.state = self._load_state()
        self.mode = _env_str("STATBOT_REGIME_ROUTER_MODE", "off").lower()
        if self.mode not in self.VALID_MODES:
            self.mode = "off"

        self.config = {
            "min_hold_seconds": _env_int("STATBOT_REGIME_MIN_HOLD_SECONDS", 1200),
            "confirm_count": _env_int("STATBOT_REGIME_CONFIRM_COUNT", 2),
            "trend_threshold": _env_float("STATBOT_REGIME_TREND_THRESHOLD", 1.2),
            "vol_shock_pct": _env_float("STATBOT_REGIME_VOL_SHOCK_PCT", 0.95),
            "vol_expansion": _env_float("STATBOT_REGIME_VOL_EXPANSION", 0.5),
            "thin_depth_ratio": _env_float("STATBOT_REGIME_THIN_DEPTH_RATIO", 1.2),
            "riskoff_drawdown_pct": _env_float("STATBOT_REGIME_RISKOFF_DRAWDOWN_PCT", 1.5),
        }
        if isinstance(config, dict):
            self.config.update(config)

        # Guardrails on config values.
        if self.config["min_hold_seconds"] < 0:
            self.config["min_hold_seconds"] = 0
        if self.config["confirm_count"] < 1:
            self.config["confirm_count"] = 1
        if self.config["trend_threshold"] <= 0:
            self.config["trend_threshold"] = 1.2
        if self.config["thin_depth_ratio"] <= 0:
            self.config["thin_depth_ratio"] = 1.2

    def _load_state(self):
        if self._state_store and hasattr(self._state_store, "load"):
            try:
                loaded = self._state_store.load()
                if isinstance(loaded, dict):
                    return loaded
            except Exception:
                pass
        return load_regime_state()

    def _save_state(self, state):
        if self._state_store and hasattr(self._state_store, "save"):
            try:
                self._state_store.save(state)
                return
            except Exception:
                pass
        save_regime_state(state)

    def evaluate(self, inputs: RegimeInput) -> RegimeDecision:
        features = self._compute_features(inputs)
        candidate, reason_codes, hard_risk = self._classify_candidate(features, inputs)
        confidence = self._compute_confidence(candidate, features, reason_codes)
        regime, changed, hold_seconds, pending_candidate, pending_count = self._apply_hysteresis(
            candidate=candidate,
            confidence=confidence,
            reason_codes=reason_codes,
            hard_risk=hard_risk,
            ts=inputs.ts,
        )

        policy = self._build_policy(regime)
        diagnostics = dict(features)
        diagnostics["hold_seconds"] = hold_seconds

        decision = RegimeDecision(
            mode=self.mode,
            regime=regime,
            candidate_regime=candidate,
            confidence=confidence,
            changed=changed,
            allow_new_entries=policy["allow_new_entries"],
            entry_z=policy["entry_z"],
            entry_z_max=policy["entry_z_max"],
            min_persist_bars=policy["min_persist_bars"],
            min_liquidity_ratio=policy["min_liquidity_ratio"],
            size_multiplier=policy["size_multiplier"],
            reason_codes=reason_codes,
            diagnostics=diagnostics,
            pending_candidate=pending_candidate,
            pending_count=pending_count,
        )

        self._persist_state(decision, inputs.ts)
        return decision

    def _persist_state(self, decision: RegimeDecision, ts: float):
        state = dict(self.state or {})
        previous_regime = str(state.get("current_regime", "RANGE") or "RANGE")
        if previous_regime not in self.VALID_REGIMES:
            previous_regime = "RANGE"

        state["mode"] = self.mode
        state["candidate_regime"] = decision.candidate_regime
        state["current_regime"] = decision.regime
        state["confidence"] = decision.confidence
        state["reason_codes"] = list(decision.reason_codes)
        state["diagnostics"] = dict(decision.diagnostics)
        state["last_eval_ts"] = float(ts)
        state["pending_candidate"] = decision.pending_candidate
        state["pending_count"] = int(decision.pending_count)
        if decision.changed or previous_regime != decision.regime:
            state["since_ts"] = float(ts)
        else:
            try:
                state["since_ts"] = float(state.get("since_ts", ts) or ts)
            except (TypeError, ValueError):
                state["since_ts"] = float(ts)

        self.state = state
        self._save_state(state)

    def _compute_features(self, inputs: RegimeInput):
        trend_features = self._compute_trend_vol_features(inputs.market_candles)
        liquidity_features = self._compute_liquidity_features(
            inputs.liq_long,
            inputs.liq_short,
            inputs.per_leg_target_usdt,
        )
        features = {}
        features.update(trend_features)
        features.update(liquidity_features)
        features["coint_flag"] = int(_safe_float(inputs.z_metrics.get("coint_flag", 0), 0))
        features["orderbook_dead"] = bool(inputs.z_metrics.get("orderbook_dead", False))
        features["pnl_fallback_active"] = bool(inputs.pnl_fallback_active)
        features["session_drawdown_pct"] = _safe_float(inputs.session_drawdown_pct, 0.0)
        return features

    def _compute_trend_vol_features(self, candles):
        closes = []
        highs = []
        lows = []
        for candle in candles or []:
            if not isinstance(candle, dict):
                continue
            close_val = _safe_float(candle.get("close"), None)
            high_val = _safe_float(candle.get("high"), None)
            low_val = _safe_float(candle.get("low"), None)
            if close_val is None or high_val is None or low_val is None:
                continue
            if close_val <= 0 or high_val <= 0 or low_val <= 0:
                continue
            closes.append(close_val)
            highs.append(high_val)
            lows.append(low_val)

        sample_count = len(closes)
        if sample_count < 20:
            return {
                "market_samples": sample_count,
                "trend_raw": 0.0,
                "trend_strength": 0.0,
                "trend_direction": 0,
                "atr14": 0.0,
                "norm_atr": 0.0,
                "vol_percentile": 0.0,
                "vol_expansion": 0.0,
                "vol_shock": False,
            }

        tr_values = []
        prev_close = closes[0]
        for idx, close_val in enumerate(closes):
            high_val = highs[idx]
            low_val = lows[idx]
            tr = max(high_val - low_val, abs(high_val - prev_close), abs(low_val - prev_close))
            tr_values.append(max(tr, 0.0))
            prev_close = close_val

        atr_series = _rolling_mean(tr_values, 14)
        atr14 = 0.0
        for value in reversed(atr_series):
            if value is not None:
                atr14 = float(value)
                break

        ema20 = _ema(closes, 20)
        ema60 = _ema(closes, 60)
        trend_raw = 0.0
        if atr14 > 0:
            trend_raw = (ema20 - ema60) / atr14
        trend_strength = abs(trend_raw)
        trend_direction = 1 if trend_raw > 0 else -1 if trend_raw < 0 else 0

        norm_atr_series = []
        for idx, atr_val in enumerate(atr_series):
            if atr_val is None:
                continue
            close_val = closes[idx]
            if close_val <= 0:
                continue
            norm_atr_series.append(float(atr_val) / close_val)

        norm_atr = norm_atr_series[-1] if norm_atr_series else 0.0
        vol_lookback = norm_atr_series[-120:] if norm_atr_series else []
        vol_percentile = 0.0
        if vol_lookback:
            current = vol_lookback[-1]
            rank = sum(1 for value in vol_lookback if value <= current)
            vol_percentile = rank / float(len(vol_lookback))

        vol_expansion = 0.0
        if len(norm_atr_series) >= 61:
            prior = norm_atr_series[-61]
            current = norm_atr_series[-1]
            if prior > 0:
                vol_expansion = (current / prior) - 1.0

        vol_shock = (
            vol_percentile >= self.config["vol_shock_pct"]
            and vol_expansion >= self.config["vol_expansion"]
        )

        return {
            "market_samples": sample_count,
            "trend_raw": trend_raw,
            "trend_strength": trend_strength,
            "trend_direction": trend_direction,
            "atr14": atr14,
            "norm_atr": norm_atr,
            "vol_percentile": vol_percentile,
            "vol_expansion": vol_expansion,
            "vol_shock": bool(vol_shock),
        }

    def _compute_liquidity_features(self, liq_long, liq_short, per_leg_target_usdt):
        long_label = str((liq_long or {}).get("label", "unknown") or "unknown").lower()
        short_label = str((liq_short or {}).get("label", "unknown") or "unknown").lower()
        long_depth = _safe_float((liq_long or {}).get("orderbook_depth_notional"), 0.0)
        short_depth = _safe_float((liq_short or {}).get("orderbook_depth_notional"), 0.0)

        target = _safe_float(per_leg_target_usdt, 0.0)
        if target <= 0:
            depth_ratio_long = 0.0
            depth_ratio_short = 0.0
            depth_ratio_min = 0.0
        else:
            depth_ratio_long = long_depth / target
            depth_ratio_short = short_depth / target
            depth_ratio_min = min(depth_ratio_long, depth_ratio_short)

        low_label_count = int(long_label == "low") + int(short_label == "low")
        depth_threshold = self.config["thin_depth_ratio"]
        label_pressure = low_label_count > 0 and depth_ratio_min < (depth_threshold * 2.0)
        liq_thin = depth_ratio_min < depth_threshold

        return {
            "liq_label_long": long_label,
            "liq_label_short": short_label,
            "liq_depth_long": long_depth,
            "liq_depth_short": short_depth,
            "liq_depth_ratio_long": depth_ratio_long,
            "liq_depth_ratio_short": depth_ratio_short,
            "liq_depth_ratio_min": depth_ratio_min,
            "liq_low_label_count": low_label_count,
            "liq_label_pressure": bool(label_pressure),
            "liq_thin": bool(liq_thin),
        }

    def _classify_candidate(self, features, inputs):
        reasons = []
        hard_risk = False

        if features.get("orderbook_dead"):
            reasons.append("orderbook_dead")
            hard_risk = True
        if features.get("coint_flag", 0) != 1:
            reasons.append("cointegration_lost")
            hard_risk = True
        if features.get("vol_shock"):
            reasons.append("vol_shock")
            hard_risk = True
        if features.get("liq_thin"):
            reasons.append("thin_liquidity")
        if features.get("pnl_fallback_active"):
            reasons.append("pnl_fallback")

        dd_limit = -abs(self.config["riskoff_drawdown_pct"])
        if features.get("session_drawdown_pct", 0.0) <= dd_limit:
            reasons.append("session_drawdown")

        if reasons:
            return "RISK_OFF", reasons, hard_risk

        trend_strength = _safe_float(features.get("trend_strength"), 0.0)
        if trend_strength >= self.config["trend_threshold"]:
            return "TREND", ["strong_trend"], False

        return "RANGE", ["ranging"], False

    def _compute_confidence(self, candidate, features, reason_codes):
        sample_count = int(features.get("market_samples", 0) or 0)
        trend_strength = _safe_float(features.get("trend_strength"), 0.0)
        trend_threshold = max(_safe_float(self.config["trend_threshold"], 1.2), 0.01)

        if candidate == "RISK_OFF":
            confidence = 0.7 + min(0.25, max(len(reason_codes) - 1, 0) * 0.08)
            if "vol_shock" in reason_codes or "orderbook_dead" in reason_codes:
                confidence = max(confidence, 0.9)
        elif candidate == "TREND":
            ratio = trend_strength / trend_threshold
            confidence = 0.55 + min(0.4, max(ratio - 1.0, 0.0) * 0.25)
            confidence += min(0.1, ratio * 0.05)
        else:
            ratio = min(trend_strength / trend_threshold, 1.0)
            confidence = 0.9 - (ratio * 0.35)

        if sample_count < 80:
            confidence = min(confidence, 0.65)
        elif sample_count < 120:
            confidence = min(confidence, 0.8)

        return _clip(confidence, 0.0, 1.0)

    def _apply_hysteresis(
        self,
        candidate: str,
        confidence: float,
        reason_codes: List[str],
        hard_risk: bool,
        ts: float,
    ) -> Tuple[str, bool, float, str, int]:
        state = self.state or {}
        current = str(state.get("current_regime", "RANGE") or "RANGE")
        if current not in self.VALID_REGIMES:
            current = "RANGE"

        try:
            since_ts = float(state.get("since_ts", ts) or ts)
        except (TypeError, ValueError):
            since_ts = float(ts)
        if since_ts <= 0:
            since_ts = float(ts)

        elapsed = max(float(ts) - since_ts, 0.0)
        pending_candidate = str(state.get("pending_candidate", "") or "")
        pending_count = int(_safe_float(state.get("pending_count", 0), 0))

        if candidate == current:
            return current, False, elapsed, "", 0

        if candidate == "RISK_OFF" and hard_risk:
            return candidate, True, elapsed, "", 0

        if pending_candidate == candidate:
            pending_count += 1
        else:
            pending_candidate = candidate
            pending_count = 1

        meets_hold = elapsed >= float(self.config["min_hold_seconds"])
        meets_confirm = pending_count >= int(self.config["confirm_count"])
        if meets_hold and meets_confirm:
            return candidate, True, elapsed, "", 0

        return current, False, elapsed, pending_candidate, pending_count

    def _build_policy(self, regime):
        base_liq_ratio = 0.0
        raw_ratio = os.getenv("STATBOT_MIN_LIQUIDITY_RATIO")
        if raw_ratio is None or str(raw_ratio).strip() == "":
            raw_ratio = os.getenv("STATBOT_LIQUIDITY_MIN_RATIO", "0")
        try:
            base_liq_ratio = float(raw_ratio)
        except (TypeError, ValueError):
            base_liq_ratio = 0.0

        if regime == "TREND":
            return {
                "allow_new_entries": True,
                "entry_z": 2.6,
                "entry_z_max": 3.6,
                "min_persist_bars": 5,
                "min_liquidity_ratio": max(base_liq_ratio, 2.5),
                "size_multiplier": 0.5,
            }
        if regime == "RISK_OFF":
            return {
                "allow_new_entries": False,
                "entry_z": 999.0,
                "entry_z_max": 999.0,
                "min_persist_bars": 6,
                "min_liquidity_ratio": max(base_liq_ratio, 3.0),
                "size_multiplier": 0.0,
            }
        return {
            "allow_new_entries": True,
            "entry_z": 2.0,
            "entry_z_max": 3.0,
            "min_persist_bars": 4,
            "min_liquidity_ratio": max(base_liq_ratio, 1.5),
            "size_multiplier": 1.0,
        }


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


def _decision_get(decision, key, default=None):
    if isinstance(decision, dict):
        return decision.get(key, default)
    return getattr(decision, key, default)


def resolve_regime_policy_overrides(mode, decision):
    """
    Return normalized policy overrides for active mode.

    Off/shadow modes always return None overrides to preserve baseline behavior.
    """
    overrides = {
        "active": False,
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
