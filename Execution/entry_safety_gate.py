from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
import time
from typing import Any


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return bool(default)
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _env_float(name: str, default: float, minimum: float | None = None) -> float:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        value = float(default)
    else:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = float(default)
    if not math.isfinite(value):
        value = float(default)
    if minimum is not None and value < minimum:
        value = minimum
    return float(value)


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _safe_int(value: Any, default: int = 0) -> int:
    parsed = _safe_float(value, None)
    if parsed is None:
        return default
    return int(parsed)


def _decision_get(decision: Any, key: str, default: Any = None) -> Any:
    if decision is None:
        return default
    if isinstance(decision, dict):
        return decision.get(key, default)
    return getattr(decision, key, default)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_pair(pair: Any) -> str:
    return str(pair or "").strip().upper()


@dataclass(frozen=True)
class EntrySafetyGateConfig:
    enabled: bool = True
    min_cointegration_component: float = 20.0
    min_correlation_component: float = 7.0
    block_liquidity_floor: bool = True
    block_risk_off_thin_liquidity: bool = True
    block_risk_off_vol_shock: bool = True
    block_trending_ml: bool = True
    block_statarb_mr_in_trend: bool = True
    max_break_risk: float = 0.12
    cointegration_watch_cooldown_seconds: float = 1800.0
    cointegration_lost_cooldown_seconds: float = 3600.0
    cointegration_broken_cooldown_seconds: float = 7200.0
    watch_timeout_cooldown_seconds: float = 3600.0
    coint_stability_enabled: bool = True
    coint_stability_window: int = 5
    coint_stability_slope_max: float = 0.020
    coint_stability_min_sample_interval_seconds: float = 60.0

    @classmethod
    def from_env(cls) -> "EntrySafetyGateConfig":
        return cls(
            # Default false preserves baseline behavior unless the managed
            # runtime explicitly enables this safety gate.
            enabled=_env_flag("STATBOT_ENTRY_SAFETY_GATE_ENABLED", True),
            min_cointegration_component=_env_float(
                "STATBOT_ENTRY_GATE_MIN_COINTEGRATION_COMPONENT",
                20.0,
                minimum=0.0,
            ),
            min_correlation_component=_env_float(
                "STATBOT_ENTRY_GATE_MIN_CORRELATION_COMPONENT",
                7.0,
                minimum=0.0,
            ),
            block_liquidity_floor=_env_flag("STATBOT_ENTRY_GATE_BLOCK_LIQUIDITY_FLOOR", True),
            block_risk_off_thin_liquidity=_env_flag(
                "STATBOT_ENTRY_GATE_BLOCK_RISK_OFF_THIN_LIQUIDITY",
                True,
            ),
            block_risk_off_vol_shock=_env_flag(
                "STATBOT_ENTRY_GATE_BLOCK_RISK_OFF_VOL_SHOCK",
                True,
            ),
            block_trending_ml=_env_flag("STATBOT_ENTRY_GATE_BLOCK_TRENDING_ML", True),
            block_statarb_mr_in_trend=_env_flag("STATBOT_ENTRY_GATE_BLOCK_STATARB_MR_IN_TREND", True),
            max_break_risk=_env_float("STATBOT_ENTRY_GATE_MAX_BREAK_RISK", 0.12, minimum=0.0),
            cointegration_watch_cooldown_seconds=_env_float(
                "STATBOT_ENTRY_GATE_COINTEGRATION_WATCH_COOLDOWN_SECONDS",
                1800.0,
                minimum=0.0,
            ),
            cointegration_lost_cooldown_seconds=_env_float(
                "STATBOT_ENTRY_GATE_COINTEGRATION_LOST_COOLDOWN_SECONDS",
                3600.0,
                minimum=0.0,
            ),
            cointegration_broken_cooldown_seconds=_env_float(
                "STATBOT_ENTRY_GATE_COINTEGRATION_BROKEN_COOLDOWN_SECONDS",
                7200.0,
                minimum=0.0,
            ),
            watch_timeout_cooldown_seconds=_env_float(
                "STATBOT_ENTRY_GATE_COOLDOWN_AFTER_WATCH_TIMEOUT_SECONDS",
                3600.0,
                minimum=0.0,
            ),
            coint_stability_enabled=_env_flag("STATBOT_ENTRY_COINT_STABILITY_ENABLED", True),
            coint_stability_window=max(2, int(_env_float("STATBOT_ENTRY_COINT_STABILITY_WINDOW", 5.0, minimum=2.0))),
            coint_stability_slope_max=_env_float("STATBOT_ENTRY_COINT_STABILITY_SLOPE_MAX", 0.020),
            coint_stability_min_sample_interval_seconds=_env_float(
                "STATBOT_ENTRY_COINT_STABILITY_MIN_SAMPLE_INTERVAL_SECONDS", 60.0, minimum=1.0
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "min_cointegration_component": float(self.min_cointegration_component),
            "min_correlation_component": float(self.min_correlation_component),
            "block_liquidity_floor": bool(self.block_liquidity_floor),
            "block_risk_off_thin_liquidity": bool(self.block_risk_off_thin_liquidity),
            "block_risk_off_vol_shock": bool(self.block_risk_off_vol_shock),
            "block_trending_ml": bool(self.block_trending_ml),
            "block_statarb_mr_in_trend": bool(self.block_statarb_mr_in_trend),
            "max_break_risk": float(self.max_break_risk),
            "cointegration_watch_cooldown_seconds": float(self.cointegration_watch_cooldown_seconds),
            "cointegration_lost_cooldown_seconds": float(self.cointegration_lost_cooldown_seconds),
            "cointegration_broken_cooldown_seconds": float(self.cointegration_broken_cooldown_seconds),
            "watch_timeout_cooldown_seconds": float(self.watch_timeout_cooldown_seconds),
            "coint_stability_enabled": bool(self.coint_stability_enabled),
            "coint_stability_window": int(self.coint_stability_window),
            "coint_stability_slope_max": float(self.coint_stability_slope_max),
            "coint_stability_min_sample_interval_seconds": float(self.coint_stability_min_sample_interval_seconds),
        }


@dataclass(frozen=True)
class EntrySafetyGateDecision:
    passed: bool
    reason: str
    reasons: tuple[str, ...] = ()
    cooldown_remaining_seconds: float | None = None
    component_scores: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "entry_gate_passed": bool(self.passed),
            "entry_gate_block_reason": "" if self.passed else self.reason,
            "entry_gate_reasons": list(self.reasons),
            "entry_gate_component_scores": dict(self.component_scores),
            "entry_gate_cooldown_remaining": self.cooldown_remaining_seconds,
        }
        payload.update(dict(self.metadata))
        return payload


_PAIR_COOLDOWNS: dict[str, dict[str, Any]] = {}
_PAIR_COINT_PVALUE_HISTORY: dict[str, list[tuple[float, float]]] = {}


def clear_entry_safety_gate_state() -> None:
    _PAIR_COOLDOWNS.clear()
    _PAIR_COINT_PVALUE_HISTORY.clear()


def _ols_slope(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den else 0.0


def _cooldown_seconds_for_reason(reason: str, config: EntrySafetyGateConfig) -> float:
    reason_text = _normalize_text(reason)
    if reason_text in {"cointegration_watch", "coint_watch", "watch"}:
        return float(config.cointegration_watch_cooldown_seconds)
    if reason_text in {"cointegration_watch_timeout", "watch_timeout"}:
        return float(config.watch_timeout_cooldown_seconds)
    if reason_text in {"cointegration_broken", "coint_broken", "broken"}:
        return float(config.cointegration_broken_cooldown_seconds)
    if reason_text in {"cointegration_lost", "coint_lost", "lost"}:
        return float(config.cointegration_lost_cooldown_seconds)
    return 0.0


def record_entry_safety_pair_event(
    pair: str,
    reason: str,
    *,
    now: float | None = None,
    config: EntrySafetyGateConfig | None = None,
) -> dict[str, Any] | None:
    config = config or EntrySafetyGateConfig.from_env()
    pair_key = _normalize_pair(pair)
    if not pair_key:
        return None
    seconds = _cooldown_seconds_for_reason(reason, config)
    if seconds <= 0:
        return None
    now_ts = time.time() if now is None else float(now)
    entry = {
        "reason": _normalize_text(reason) or "unknown",
        "ts": now_ts,
        "until_ts": now_ts + float(seconds),
    }
    _PAIR_COOLDOWNS[pair_key] = entry
    return dict(entry)


def _cooldown_decision(pair: str, now: float) -> tuple[str | None, float | None]:
    entry = _PAIR_COOLDOWNS.get(_normalize_pair(pair))
    if not isinstance(entry, dict):
        return None, None
    until_ts = _safe_float(entry.get("until_ts"), 0.0) or 0.0
    if until_ts <= now:
        _PAIR_COOLDOWNS.pop(_normalize_pair(pair), None)
        return None, None
    return _normalize_text(entry.get("reason")) or "recent_pair_quality_event", max(until_ts - now, 0.0)


def _quality_components(quality_decision: Any) -> dict[str, float]:
    raw = _decision_get(quality_decision, "components", {}) or {}
    if not isinstance(raw, dict):
        return {}
    components: dict[str, float] = {}
    for key, value in raw.items():
        parsed = _safe_float(value, None)
        if parsed is not None:
            components[str(key)] = float(parsed)
    return components


def _router_state(regime_decision: Any, strategy_decision: Any) -> dict[str, Any]:
    regime_name = str(_decision_get(regime_decision, "regime", "") or "").strip().upper()
    regime_candidate = str(_decision_get(regime_decision, "candidate_regime", "") or "").strip().upper()
    regime_reasons = list(_decision_get(regime_decision, "reason_codes", []) or [])
    strategy_name = str(_decision_get(strategy_decision, "active_strategy", "") or "").strip().upper()
    strategy_desired = str(_decision_get(strategy_decision, "desired_strategy", "") or "").strip().upper()
    strategy_reasons = list(_decision_get(strategy_decision, "reason_codes", []) or [])
    return {
        "regime": regime_name,
        "candidate_regime": regime_candidate,
        "regime_reasons": regime_reasons,
        "strategy": strategy_name,
        "desired_strategy": strategy_desired,
        "strategy_reasons": strategy_reasons,
    }


def _advanced_ml_state(advanced_regime_result: Any) -> dict[str, Any]:
    regime_obj = _decision_get(advanced_regime_result, "regime", None)
    regime_name = getattr(regime_obj, "value", regime_obj)
    return {
        "advanced_regime": str(regime_name or "").strip().lower(),
        "break_risk": _safe_float(_decision_get(advanced_regime_result, "break_risk", None), None),
        "confidence": _safe_float(_decision_get(advanced_regime_result, "confidence", None), None),
        "reasons": list(_decision_get(advanced_regime_result, "reasons", []) or []),
    }


def _coint_state_from_metrics(metrics: dict[str, Any] | None) -> str:
    metrics = metrics or {}
    coint_health = _normalize_text(metrics.get("coint_health"))
    if coint_health:
        return coint_health
    coint_flag = _safe_int(metrics.get("coint_flag"), 0)
    if coint_flag == 1:
        return "valid"
    return "broken"


def evaluate_entry_safety_gate(
    *,
    pair: str,
    metrics: dict[str, Any] | None,
    quality_decision: Any | None = None,
    ratio_long: float | None = None,
    ratio_short: float | None = None,
    min_liquidity_ratio: float | None = None,
    regime_decision: Any | None = None,
    strategy_decision: Any | None = None,
    advanced_regime_result: Any | None = None,
    now: float | None = None,
    config: EntrySafetyGateConfig | None = None,
    entry_strategy_name: str | None = None,
) -> EntrySafetyGateDecision:
    config = config or EntrySafetyGateConfig.from_env()
    now_ts = time.time() if now is None else float(now)
    metrics = metrics or {}
    components = _quality_components(quality_decision)
    coint_state = _coint_state_from_metrics(metrics)
    router = _router_state(regime_decision, strategy_decision)
    advanced = _advanced_ml_state(advanced_regime_result)
    reasons: list[str] = []
    cooldown_remaining: float | None = None

    metadata: dict[str, Any] = {
        "pair": pair,
        "coint_state": coint_state,
        "coint_flag": _safe_int(metrics.get("coint_flag"), 0),
        "router_shadow_state": router,
        "ml_shadow_state": advanced,
        "break_risk": advanced.get("break_risk"),
        "config_thresholds": config.to_dict(),
        "ratio_long": ratio_long,
        "ratio_short": ratio_short,
        "min_ratio": min_liquidity_ratio,
    }

    if not config.enabled:
        return EntrySafetyGateDecision(
            passed=True,
            reason="entry_safety_gate_disabled",
            reasons=(),
            component_scores=components,
            metadata=metadata,
        )

    cooldown_reason, cooldown_seconds = _cooldown_decision(pair, now_ts)
    if cooldown_reason:
        reasons.append(f"recent_{cooldown_reason}_cooldown")
        cooldown_remaining = cooldown_seconds

    coint_flag = _safe_int(metrics.get("coint_flag"), 0)
    if coint_flag == 0 or coint_state in {"watch", "broken", "degraded", "failed", "fail", "critical"}:
        if coint_state == "watch":
            reasons.append("cointegration_watch")
            record_entry_safety_pair_event(pair, "cointegration_watch", now=now_ts, config=config)
        elif coint_state in {"lost", "cointegration_lost"}:
            reasons.append("cointegration_lost")
            record_entry_safety_pair_event(pair, "cointegration_lost", now=now_ts, config=config)
        else:
            reasons.append("cointegration_broken")
            record_entry_safety_pair_event(pair, "cointegration_broken", now=now_ts, config=config)

    _coint_eval = 0
    _coint_blocked = 0
    _coint_insuff = 0
    _coint_slope_val: float | None = None

    if config.coint_stability_enabled:
        _pair_key = _normalize_pair(pair)
        _current_p = _safe_float(metrics.get("p_value"), None)
        if _current_p is not None:
            _history = _PAIR_COINT_PVALUE_HISTORY.setdefault(_pair_key, [])
            _should_append = (
                not _history
                or now_ts - _history[-1][0] >= float(config.coint_stability_min_sample_interval_seconds)
            )
            if _should_append:
                _history.append((now_ts, _current_p))
                _max_keep = config.coint_stability_window * 2
                if len(_history) > _max_keep:
                    del _history[:-_max_keep]
            _p_values = [p for _, p in _history]
            if len(_p_values) >= config.coint_stability_window:
                _recent = _p_values[-config.coint_stability_window:]
                _slope = _ols_slope(_recent)
                _coint_slope_val = _slope
                _coint_eval = 1
                if _slope > float(config.coint_stability_slope_max):
                    reasons.append("coint_stability_slope_high")
                    _coint_blocked = 1
                    metadata["coint_stability_slope"] = _slope
            else:
                _coint_insuff = 1

    cointegration_component = components.get("cointegration")
    if (
        cointegration_component is not None
        and cointegration_component < float(config.min_cointegration_component)
    ):
        reasons.append("cointegration_component_below_threshold")

    correlation_component = components.get("correlation")
    if (
        correlation_component is not None
        and correlation_component < float(config.min_correlation_component)
    ):
        reasons.append("correlation_component_below_threshold")

    liquidity_component = components.get("liquidity")
    if config.block_liquidity_floor and min_liquidity_ratio and min_liquidity_ratio > 0:
        ratio_values = [
            parsed
            for parsed in (_safe_float(ratio_long, None), _safe_float(ratio_short, None))
            if parsed is not None
        ]
        if ratio_values and min(ratio_values) <= float(min_liquidity_ratio) * 1.001:
            reasons.append("liquidity_at_floor")
        elif liquidity_component is not None and liquidity_component <= 10.0:
            reasons.append("liquidity_component_at_floor")

    regime_name = router.get("regime") or router.get("candidate_regime")
    regime_reasons = {_normalize_text(item) for item in router.get("regime_reasons") or []}
    strategy_name = router.get("strategy") or router.get("desired_strategy")
    if regime_name == "RISK_OFF":
        if config.block_risk_off_thin_liquidity and "thin_liquidity" in regime_reasons:
            reasons.append("risk_off_thin_liquidity")
        if config.block_risk_off_vol_shock and "vol_shock" in regime_reasons:
            reasons.append("risk_off_vol_shock")
    if strategy_name == "TREND_SPREAD" and (
        (correlation_component is not None and correlation_component < float(config.min_correlation_component))
        or (
            cointegration_component is not None
            and cointegration_component < float(config.min_cointegration_component)
        )
    ):
        reasons.append("trend_candidate_with_weak_quality")

    _exec_strategy = str(entry_strategy_name).strip().upper() if entry_strategy_name else strategy_name
    if config.block_statarb_mr_in_trend and _exec_strategy == "STATARB_MR" and regime_name == "TREND":
        reasons.append("statarb_mr_trend_regime_block")
        metadata["statarb_mr_trend_blocked"] = True
        metadata["blocked_regime"] = regime_name

    advanced_regime = _normalize_text(advanced.get("advanced_regime"))
    break_risk = advanced.get("break_risk")
    if config.block_trending_ml:
        if advanced_regime in {"trend", "trending", "breakout", "momentum"}:
            reasons.append("advanced_ml_trending")
        if break_risk is not None and float(break_risk) >= float(config.max_break_risk):
            reasons.append("advanced_ml_break_risk_high")

    if config.coint_stability_enabled:
        components["coint_stability_check_evaluated_count"] = float(_coint_eval)
        components["coint_stability_check_blocked_count"] = float(_coint_blocked)
        components["coint_stability_insufficient_history_count"] = float(_coint_insuff)
        if _coint_slope_val is not None:
            components["coint_stability_slope"] = float(_coint_slope_val)

    unique_reasons = tuple(sorted(set(reason for reason in reasons if reason)))
    passed = not unique_reasons
    return EntrySafetyGateDecision(
        passed=passed,
        reason="entry_safety_gate_passed" if passed else unique_reasons[0],
        reasons=unique_reasons,
        cooldown_remaining_seconds=cooldown_remaining,
        component_scores=components,
        metadata=metadata,
    )


__all__ = [
    "EntrySafetyGateConfig",
    "EntrySafetyGateDecision",
    "clear_entry_safety_gate_state",
    "evaluate_entry_safety_gate",
    "record_entry_safety_pair_event",
]
