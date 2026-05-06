"""Runtime bridge for the advanced ML stack.

The core advanced modules deliberately avoid importing the existing bot. This
module is the thin adapter layer that translates current execution state into
their protocol-shaped inputs while keeping legacy execution authoritative unless
advanced live mode is explicitly enabled.
"""

from __future__ import annotations

import json
import logging
import math
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.adapters.bot_adapter_types import PairState  # noqa: E402
from core.config.advanced_ml_config import AdvancedMLConfig, load_advanced_ml_config_from_env  # noqa: E402
from core.ev.hold_exit_ev import ExitAction  # noqa: E402
from core.regime.heuristic_regime_detector import HeuristicRegimeDetector  # noqa: E402
from core.regime.regime_types import RegimeDetectionResult, RegimeName  # noqa: E402
from core.trade_management.probabilistic_exit_manager import (  # noqa: E402
    ExitDecision,
    ProbabilisticExitManager,
)


logger = logging.getLogger(__name__)

STATE_DIR = Path(__file__).resolve().parent / "state"
SHADOW_REPORT_PATH = STATE_DIR / "advanced_ml_shadow_reports.json"

_CONFIG: AdvancedMLConfig | None = None
_EXIT_MANAGER: ProbabilisticExitManager | None = None
_EXIT_MANAGER_MODE: tuple[bool, bool] | None = None
_REGIME_DETECTOR: HeuristicRegimeDetector | None = None
_REGIME_MEMORY: dict[str, dict[str, Any]] = {}
_LAST_REGIME_LOG_SIGNATURE: tuple[Any, ...] | None = None
_LAST_REGIME_LOG_TS = 0.0
_LAST_EXIT_LOG_SIGNATURE: tuple[Any, ...] | None = None
_LAST_EXIT_LOG_TS = 0.0


@dataclass(frozen=True)
class RuntimePair:
    key: str
    sym_1: str
    sym_2: str


class RuntimeExistingBotAdapter:
    """Protocol adapter used by ProbabilisticExitManager.

    submit_exit_order intentionally records an intent only. The existing
    monitor_exit flow remains responsible for actual order placement.
    """

    def __init__(self) -> None:
        self.submitted_intents: list[dict[str, Any]] = []

    def get_pair_state(self, pair: Any) -> PairState:
        del pair
        return PairState.STABLE

    def get_orderbook_snapshot(self, symbol: str) -> dict[str, Any] | None:
        del symbol
        return None

    def get_current_position(self, pair: Any) -> dict[str, Any] | None:
        del pair
        return None

    def get_trade_lifecycle_event(self) -> dict[str, Any] | None:
        return None

    def read_existing_trade_state(self) -> dict[str, Any] | None:
        return {"action": "hold", "reason": "legacy monitor_exit"}

    def submit_exit_order(
        self,
        pair: Any,
        exit_percentage: float,
        order_style: str,
        reason: str,
    ) -> dict[str, Any]:
        intent = {
            "pair": _pair_key(pair),
            "exit_percentage": float(exit_percentage),
            "order_style": str(order_style),
            "reason": str(reason),
            "timestamp": time.time(),
        }
        self.submitted_intents.append(intent)
        return intent


def get_advanced_ml_config() -> AdvancedMLConfig:
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = load_advanced_ml_config_from_env()
    return _CONFIG


def reset_advanced_ml_runtime_cache() -> None:
    """Test helper: force env/config to be re-read."""

    global _CONFIG, _EXIT_MANAGER, _EXIT_MANAGER_MODE, _REGIME_DETECTOR
    global _LAST_REGIME_LOG_SIGNATURE, _LAST_REGIME_LOG_TS
    global _LAST_EXIT_LOG_SIGNATURE, _LAST_EXIT_LOG_TS
    _CONFIG = None
    _EXIT_MANAGER = None
    _EXIT_MANAGER_MODE = None
    _REGIME_DETECTOR = None
    _REGIME_MEMORY.clear()
    _LAST_REGIME_LOG_SIGNATURE = None
    _LAST_REGIME_LOG_TS = 0.0
    _LAST_EXIT_LOG_SIGNATURE = None
    _LAST_EXIT_LOG_TS = 0.0


def advanced_ml_config_snapshot(config: AdvancedMLConfig | None = None) -> dict[str, Any]:
    cfg = config or get_advanced_ml_config()
    mode = advanced_ml_runtime_mode(cfg)
    return {
        "mode": mode,
        "enabled": bool(cfg.pipeline.enabled),
        "shadow_mode": bool(cfg.pipeline.shadow_mode),
        "shadow_eval_window": int(cfg.pipeline.shadow_eval_window),
        "max_shadow_disagreement_rate": float(cfg.pipeline.max_shadow_disagreement_rate),
        "min_shadow_policy_delta_usdt": float(cfg.pipeline.min_shadow_policy_delta_usdt),
        "model_state_path": str(cfg.persistence.model_state_path),
        "max_book_age_ms": float(cfg.microstructure.max_book_age_ms),
        "fast_adverse_threshold": float(cfg.microstructure.fast_adverse_threshold),
        "wide_spread_bps": float(cfg.microstructure.wide_spread_bps),
        "max_drawdown_usdt": float(cfg.exit.max_drawdown_usdt),
    }


def advanced_ml_runtime_mode(config: AdvancedMLConfig | None = None) -> str:
    cfg = config or get_advanced_ml_config()
    if cfg.pipeline.enabled and not cfg.pipeline.shadow_mode:
        return "live"
    if cfg.pipeline.shadow_mode:
        return "shadow"
    return "off"


def log_advanced_ml_startup_status(log: logging.Logger | None = None) -> dict[str, Any]:
    target = log or logger
    snapshot = advanced_ml_config_snapshot()
    mode = snapshot["mode"]
    if mode == "live":
        target.warning(
            "Advanced ML runtime LIVE: Bayes/LinUCB/ranker/exit decisions may affect execution by config."
        )
    elif mode == "shadow":
        target.info(
            "Advanced ML runtime SHADOW: regime, ranking, and exit systems evaluate beside legacy logic only."
        )
    else:
        target.info("Advanced ML runtime disabled.")
    target.info("Advanced ML config snapshot: %s", snapshot)
    return snapshot


def evaluate_advanced_regime(
    *,
    pair: tuple[str, str] | RuntimePair | str,
    zscore_series: list[Any] | tuple[Any, ...],
    metrics: dict[str, Any] | None,
    legacy_decision: Any | None = None,
    log: logging.Logger | None = None,
) -> RegimeDetectionResult | None:
    cfg = get_advanced_ml_config()
    mode = advanced_ml_runtime_mode(cfg)
    if mode == "off":
        return None

    pair_obj = _coerce_pair(pair)
    z_values = _finite_tail(zscore_series, max(cfg.regime.regime_window, 2))
    if len(z_values) < 2:
        return None

    detector = _get_regime_detector(cfg)
    pair_memory = _REGIME_MEMORY.get(pair_obj.key, {})
    metrics = metrics or {}
    corr_value = _finite_float(metrics.get("correlation"), 0.0)
    hedge_value = _finite_float(metrics.get("hedge_ratio"), 1.0)
    now = time.time()

    try:
        result = detector.detect(
            pair=pair_obj,
            z_history=[(now - (len(z_values) - idx) * 60.0, z) for idx, z in enumerate(z_values)],
            spread_history=z_values,
            corr_history=[corr_value],
            hedge_ratio_history=[hedge_value],
            spread_bps=_finite_float(metrics.get("spread_bps"), 0.0),
            depth_imbalance=_finite_float(metrics.get("depth_imbalance"), 0.0),
            top_depth_usdt=_finite_float(metrics.get("top_depth_usdt"), cfg.regime.min_top_depth_usdt),
            slippage_estimate_bps=_finite_float(metrics.get("slippage_estimate_bps"), 0.0),
            book_freshness_ms=_finite_float(metrics.get("book_freshness_ms"), 0.0),
            previous_regime=pair_memory.get("regime"),
            previous_regime_confidence=_finite_float(pair_memory.get("confidence"), 0.0),
            ticks_in_proposed_regime=int(pair_memory.get("ticks", 0) or 0),
            seconds_since_last_regime_switch=max(now - float(pair_memory.get("last_switch_ts", 0.0) or 0.0), 0.0),
            timestamp=now,
        )
    except Exception as exc:
        (log or logger).warning("ADVANCED_REGIME_%s failed: pair=%s error=%s", mode.upper(), pair_obj.key, exc)
        return None

    previous_regime = pair_memory.get("regime")
    if previous_regime == result.regime:
        ticks = int(pair_memory.get("ticks", 0) or 0) + 1
        last_switch_ts = float(pair_memory.get("last_switch_ts", now) or now)
    else:
        ticks = 1
        last_switch_ts = now
    _REGIME_MEMORY[pair_obj.key] = {
        "regime": result.regime,
        "confidence": result.confidence,
        "ticks": ticks,
        "last_switch_ts": last_switch_ts,
    }

    _log_advanced_regime_result(result, legacy_decision=legacy_decision, log=log or logger, mode=mode)
    return result


def evaluate_probabilistic_exit(
    *,
    pair: tuple[str, str] | RuntimePair | str,
    zscore_series: list[Any] | tuple[Any, ...],
    metrics: dict[str, Any] | None,
    latest_zscore: float,
    entry_z: float | None,
    entry_time: float | None,
    entry_notional: float | None,
    floating_pnl_usdt: float | None,
    pnl_pct: float | None,
    regime_decision: Any | None = None,
    strategy_decision: Any | None = None,
    old_action: str = "hold",
    old_reason: str = "legacy hold",
    log: logging.Logger | None = None,
) -> ExitDecision | None:
    cfg = get_advanced_ml_config()
    mode = advanced_ml_runtime_mode(cfg)
    if mode == "off":
        return None

    pair_obj = _coerce_pair(pair)
    manager = _get_exit_manager(cfg)
    features = build_exit_features(
        pair=pair_obj,
        zscore_series=zscore_series,
        metrics=metrics or {},
        latest_zscore=latest_zscore,
        entry_z=entry_z,
        entry_time=entry_time,
        entry_notional=entry_notional,
        floating_pnl_usdt=floating_pnl_usdt,
        pnl_pct=pnl_pct,
        regime_decision=regime_decision,
        strategy_decision=strategy_decision,
    )
    try:
        decision = manager.evaluate_exit(
            pair_obj,
            features,
            old_action=old_action,
            old_reason=old_reason,
        )
    except Exception as exc:
        (log or logger).warning("ADVANCED_EXIT_%s failed: pair=%s error=%s", mode.upper(), pair_obj.key, exc)
        return None

    _log_advanced_exit_decision(decision, old_action=old_action, old_reason=old_reason, log=log or logger)
    return decision


def build_exit_features(
    *,
    pair: RuntimePair,
    zscore_series: list[Any] | tuple[Any, ...],
    metrics: dict[str, Any],
    latest_zscore: float,
    entry_z: float | None,
    entry_time: float | None,
    entry_notional: float | None,
    floating_pnl_usdt: float | None,
    pnl_pct: float | None,
    regime_decision: Any | None,
    strategy_decision: Any | None,
) -> dict[str, Any]:
    del strategy_decision
    cfg = get_advanced_ml_config()
    z_values = _finite_tail(zscore_series, max(cfg.ev.recent_z_vol_window, 3))
    if not z_values or z_values[-1] != float(latest_zscore):
        z_values.append(float(latest_zscore))
    previous_z = z_values[-2] if len(z_values) >= 2 else float(latest_zscore)
    abs_current = abs(float(latest_zscore))
    abs_previous = abs(float(previous_z))
    abs_entry = abs(float(entry_z)) if entry_z is not None else abs_current
    time_in_trade_seconds = max(time.time() - float(entry_time), 0.0) if entry_time else 0.0
    notional = max(_finite_float(entry_notional, 0.0), 0.0)
    pnl = _finite_float(floating_pnl_usdt, 0.0)
    coint_flag = int(_finite_float(metrics.get("coint_flag"), 0.0))
    break_risk = _break_risk_from_inputs(metrics, regime_decision)
    liquidity_score = _liquidity_score(metrics)
    trend_score = _trend_score(z_values, regime_decision)
    adverse_z_velocity_score = _adverse_z_velocity_score(abs_previous, abs_current)
    z_velocity_toward_mean_score = _z_velocity_toward_mean_score(abs_previous, abs_current)
    mean_reversion_score = _mean_reversion_score(abs_entry, abs_current)
    spread_vol_spike = _normalized_spread_vol_spike(z_values)
    regime_name = _advanced_regime_from_legacy(regime_decision, metrics)
    current_drawdown_usdt = max(-pnl, 0.0)
    capacity = _finite_float(metrics.get("pair_order_capacity_usdt"), notional if notional > 0 else 1.0)

    return {
        "pair_key": pair.key,
        "trade_id": f"{pair.key}:{entry_time if entry_time is not None else 'unknown'}",
        "entry_z": float(entry_z) if entry_z is not None else float(latest_zscore),
        "current_z": float(latest_zscore),
        "previous_z": float(previous_z),
        "catastrophic_divergence_sigma": 2.0,
        "time_in_trade_seconds": time_in_trade_seconds,
        "estimated_half_life_seconds": cfg.exit.default_half_life_seconds,
        "position_notional_usdt": notional,
        "exit_notional_usdt": notional,
        "desired_exit_notional_usdt": notional,
        "order_capacity_usdt": capacity,
        "z_history_values": z_values,
        "bayesian_posterior": _finite_float(metrics.get("advanced_bayes_probability"), 0.5),
        "regime": regime_name,
        "regime_confidence": _legacy_confidence(regime_decision),
        "regime_mean_reversion_confidence": _mean_reversion_confidence(regime_decision, metrics),
        "mean_reversion_score": mean_reversion_score,
        "z_velocity_toward_mean_score": z_velocity_toward_mean_score,
        "break_risk": break_risk,
        "regime_break_score": break_risk,
        "adverse_z_velocity_score": adverse_z_velocity_score,
        "trend_score": trend_score,
        "normalized_spread_vol_spike": spread_vol_spike,
        "liquidity_score": liquidity_score,
        "liquidity_risk_score": 1.0 - liquidity_score,
        "slippage_estimate_bps": _finite_float(metrics.get("slippage_estimate_bps"), 0.0),
        "spread_bps": _finite_float(metrics.get("spread_bps"), 0.0),
        "update_age_ms": _finite_float(metrics.get("update_age_ms"), _finite_float(metrics.get("book_freshness_ms"), 0.0)),
        "book_freshness_ms": _finite_float(metrics.get("book_freshness_ms"), 0.0),
        "freshness_ms": _finite_float(metrics.get("freshness_ms"), _finite_float(metrics.get("book_freshness_ms"), 0.0)),
        "bid_depth": _finite_float(metrics.get("bid_depth"), cfg.regime.min_top_depth_usdt * liquidity_score),
        "ask_depth": _finite_float(metrics.get("ask_depth"), cfg.regime.min_top_depth_usdt * liquidity_score),
        "expected_taker_fee_bps": _finite_float(metrics.get("expected_taker_fee_bps"), cfg.ev.exit_fee_rate * 10000.0),
        "recent_maker_fill_probability": _finite_float(metrics.get("recent_maker_fill_probability"), 0.75),
        "api_latency_ms": _finite_float(metrics.get("api_latency_ms"), 0.0),
        "recent_order_failures": _finite_float(metrics.get("recent_order_failures"), 0.0),
        "unrealized_pnl_usdt": pnl,
        "current_drawdown_usdt": current_drawdown_usdt,
        "pnl_pct": _finite_float(pnl_pct, 0.0),
        "take_profit_score": _take_profit_score(pnl, notional),
        "trailing_stop_pressure": 0.0,
        "net_profit_guard_enabled": True,
        "coint_flag": coint_flag,
        "position_desync": False,
    }


def should_apply_live_advanced_exit(decision: ExitDecision | None) -> bool:
    if decision is None:
        return False
    cfg = get_advanced_ml_config()
    if advanced_ml_runtime_mode(cfg) != "live":
        return False
    return decision.action in (ExitAction.PARTIAL_EXIT, ExitAction.FULL_EXIT)


def generate_post_trade_shadow_report(
    *,
    pair: tuple[str, str] | RuntimePair | str,
    trade_id: str,
    actual_pnl_usdt: float,
    actual_exit_timestamp: float | None = None,
    log: logging.Logger | None = None,
) -> dict[str, Any] | None:
    cfg = get_advanced_ml_config()
    if advanced_ml_runtime_mode(cfg) == "off":
        return None
    manager = _get_exit_manager(cfg)
    pair_obj = _coerce_pair(pair)
    try:
        report = manager.generate_post_trade_shadow_report(
            pair_obj,
            trade_id=str(trade_id),
            actual_exit_timestamp=float(actual_exit_timestamp or time.time()),
            actual_pnl_usdt=float(actual_pnl_usdt),
        )
    except Exception as exc:
        (log or logger).warning("ADVANCED_EXIT_POST_TRADE_SHADOW failed: pair=%s error=%s", pair_obj.key, exc)
        return None
    payload = report.to_dict()
    _append_shadow_report(payload)
    (log or logger).info(
        "ADVANCED_EXIT_POST_TRADE_SHADOW: pair=%s trade_id=%s agreement=%.3f disagreement=%.3f net_delta=%+.2f reports_window=%s",
        pair_obj.key,
        trade_id,
        report.agreement_rate,
        report.disagreement_rate,
        report.net_policy_delta_usdt,
        manager.shadow_circuit_breaker_status(),
    )
    return payload


def _get_exit_manager(config: AdvancedMLConfig) -> ProbabilisticExitManager:
    global _EXIT_MANAGER, _EXIT_MANAGER_MODE
    mode_key = (bool(config.pipeline.enabled), bool(config.pipeline.shadow_mode))
    if _EXIT_MANAGER is None or _EXIT_MANAGER_MODE != mode_key:
        _EXIT_MANAGER = ProbabilisticExitManager(
            RuntimeExistingBotAdapter(),
            config,
            shadow_mode=(advanced_ml_runtime_mode(config) != "live"),
        )
        _EXIT_MANAGER_MODE = mode_key
    return _EXIT_MANAGER


def _get_regime_detector(config: AdvancedMLConfig) -> HeuristicRegimeDetector:
    global _REGIME_DETECTOR
    if _REGIME_DETECTOR is None:
        _REGIME_DETECTOR = HeuristicRegimeDetector(config)
    return _REGIME_DETECTOR


def _log_advanced_regime_result(
    result: RegimeDetectionResult,
    *,
    legacy_decision: Any | None,
    log: logging.Logger,
    mode: str,
) -> None:
    global _LAST_REGIME_LOG_SIGNATURE, _LAST_REGIME_LOG_TS
    legacy_regime = str(_read_attr(legacy_decision, "regime", "unknown") or "unknown").lower()
    signature = (
        _pair_key(result.pair),
        str(result.regime.value),
        round(float(result.confidence), 2),
        round(float(result.break_risk), 2),
        legacy_regime,
    )
    now = time.time()
    if signature == _LAST_REGIME_LOG_SIGNATURE and now - _LAST_REGIME_LOG_TS < 60:
        return
    _LAST_REGIME_LOG_SIGNATURE = signature
    _LAST_REGIME_LOG_TS = now
    log.info(
        "ADVANCED_REGIME_%s: pair=%s legacy=%s advanced=%s conf=%.3f break_risk=%.3f trend=%.3f liquidity=%s reasons=%s",
        str(mode or "shadow").upper(),
        _pair_key(result.pair),
        legacy_regime,
        result.regime.value,
        result.confidence,
        result.break_risk,
        result.trend_score,
        result.liquidity_state,
        "|".join(result.reasons or []) or "none",
    )


def _log_advanced_exit_decision(
    decision: ExitDecision,
    *,
    old_action: str,
    old_reason: str,
    log: logging.Logger,
) -> None:
    global _LAST_EXIT_LOG_SIGNATURE, _LAST_EXIT_LOG_TS
    mode = advanced_ml_runtime_mode()
    pair_key = _pair_key(decision.metadata.get("pair", "unknown"))
    signature = (
        pair_key,
        mode,
        str(old_action),
        decision.action.value,
        round(float(decision.scores.total_exit_score), 2),
        round(float(decision.ev.expected_hold_value_usdt), 2),
    )
    now = time.time()
    if signature == _LAST_EXIT_LOG_SIGNATURE and now - _LAST_EXIT_LOG_TS < 30:
        return
    _LAST_EXIT_LOG_SIGNATURE = signature
    _LAST_EXIT_LOG_TS = now
    log.info(
        "ADVANCED_EXIT_%s: pair=%s old=%s new=%s pct=%.2f score=%.3f ev=%+.4f micro=%.3f hard=%d guard=%d old_reason=%s new_reason=%s",
        mode.upper(),
        pair_key,
        old_action,
        decision.action.value,
        decision.exit_percentage,
        decision.scores.total_exit_score,
        decision.ev.expected_hold_value_usdt,
        decision.microstructure.book_stress_score,
        1 if decision.hard_kill_triggered else 0,
        1 if decision.blocked_by_net_profit_guard else 0,
        old_reason,
        decision.reason,
    )


def _append_shadow_report(payload: dict[str, Any]) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if SHADOW_REPORT_PATH.exists():
            existing = json.loads(SHADOW_REPORT_PATH.read_text(encoding="utf-8"))
            reports = existing if isinstance(existing, list) else []
        else:
            reports = []
        reports.append(_json_safe(payload))
        reports = reports[-500:]
        temp = SHADOW_REPORT_PATH.with_name(f".{SHADOW_REPORT_PATH.name}.tmp")
        temp.write_text(json.dumps(reports, indent=2), encoding="utf-8")
        temp.replace(SHADOW_REPORT_PATH)
    except Exception as exc:
        logger.warning("Failed to persist advanced ML shadow report: %s", exc)


def _json_safe(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "to_dict"):
        return _json_safe(value.to_dict())
    if hasattr(value, "__dataclass_fields__"):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _coerce_pair(pair: tuple[str, str] | RuntimePair | str) -> RuntimePair:
    if isinstance(pair, RuntimePair):
        return pair
    if isinstance(pair, tuple) and len(pair) == 2:
        sym_1 = str(pair[0]).strip().upper()
        sym_2 = str(pair[1]).strip().upper()
        key = "/".join(sorted((sym_1, sym_2)))
        return RuntimePair(key=key, sym_1=sym_1, sym_2=sym_2)
    text = str(pair or "").strip().upper()
    parts = [part for part in text.replace("|", "/").split("/") if part]
    if len(parts) >= 2:
        sym_1, sym_2 = parts[0], parts[1]
        return RuntimePair(key="/".join(sorted((sym_1, sym_2))), sym_1=sym_1, sym_2=sym_2)
    return RuntimePair(key=text or "UNKNOWN", sym_1=text or "UNKNOWN", sym_2="")


def _finite_tail(values: list[Any] | tuple[Any, ...], limit: int) -> list[float]:
    output: list[float] = []
    for value in values or []:
        number = _finite_float(value, None)
        if number is not None:
            output.append(float(number))
    return output[-max(int(limit), 1):]


def _finite_float(value: Any, default: float | None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _pair_key(pair: Any) -> str:
    key = getattr(pair, "key", None)
    return str(key if key is not None else pair)


def _read_attr(source: Any, name: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _break_risk_from_inputs(metrics: dict[str, Any], regime_decision: Any | None) -> float:
    if int(_finite_float(metrics.get("coint_flag"), 0.0) or 0) == 0:
        base = 0.65
    else:
        base = 0.0
    if bool(metrics.get("coint_broken", False)):
        base = max(base, 0.85)
    regime = str(_read_attr(regime_decision, "regime", "") or "").strip().upper()
    if regime == "RISK_OFF":
        base = max(base, 0.70)
    diagnostics = _read_attr(regime_decision, "diagnostics", {}) or {}
    fallback = bool(diagnostics.get("pnl_fallback_active", False)) if isinstance(diagnostics, dict) else False
    if fallback:
        base = max(base, 0.50)
    return _clamp01(base)


def _liquidity_score(metrics: dict[str, Any]) -> float:
    if "liquidity_score" in metrics:
        return _clamp01(_finite_float(metrics.get("liquidity_score"), 1.0) or 1.0)
    liquidity = _finite_float(metrics.get("pair_liquidity_min"), None)
    if liquidity is None:
        return 1.0
    return _clamp01(math.log10(max(liquidity, 1.0)) / 5.0)


def _trend_score(z_values: list[float], regime_decision: Any | None) -> float:
    diagnostics = _read_attr(regime_decision, "diagnostics", {}) or {}
    if isinstance(diagnostics, dict) and "trend_strength" in diagnostics:
        return _clamp01(_finite_float(diagnostics.get("trend_strength"), 0.0) or 0.0)
    if len(z_values) < 4:
        return 0.0
    first = abs(z_values[-4])
    last = abs(z_values[-1])
    return _clamp01((last - first) / max(first, 1e-9))


def _adverse_z_velocity_score(abs_previous: float, abs_current: float) -> float:
    return _clamp01((abs_current - abs_previous) / max(abs_previous, 1e-9))


def _z_velocity_toward_mean_score(abs_previous: float, abs_current: float) -> float:
    return _clamp01((abs_previous - abs_current) / max(abs_previous, 1e-9))


def _mean_reversion_score(abs_entry: float, abs_current: float) -> float:
    if abs_entry <= 0:
        return 0.0
    return _clamp01((abs_entry - abs_current) / abs_entry)


def _normalized_spread_vol_spike(z_values: list[float]) -> float:
    if len(z_values) < 6:
        return 0.0
    tail = z_values[-5:]
    base = z_values[:-5] or z_values
    tail_std = _std(tail)
    base_std = max(_std(base), 1e-9)
    return _clamp01((tail_std / base_std - 1.0) / 2.0)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _advanced_regime_from_legacy(regime_decision: Any | None, metrics: dict[str, Any]) -> RegimeName:
    if bool(metrics.get("coint_broken", False)):
        return RegimeName.CORRELATION_BREAKDOWN
    legacy = str(_read_attr(regime_decision, "regime", "") or "").strip().upper()
    if legacy == "RANGE":
        return RegimeName.MEAN_REVERTING
    if legacy == "TREND":
        return RegimeName.TRENDING
    if legacy == "RISK_OFF":
        return RegimeName.LIQUIDITY_STRESS
    return RegimeName.UNKNOWN


def _legacy_confidence(regime_decision: Any | None) -> float:
    return _clamp01(_finite_float(_read_attr(regime_decision, "confidence", 0.0), 0.0) or 0.0)


def _mean_reversion_confidence(regime_decision: Any | None, metrics: dict[str, Any]) -> float:
    if _advanced_regime_from_legacy(regime_decision, metrics) == RegimeName.MEAN_REVERTING:
        return max(_legacy_confidence(regime_decision), 0.65)
    return 0.0


def _take_profit_score(pnl: float, notional: float) -> float:
    if pnl <= 0:
        return 0.0
    target = max(notional * 0.0025, 1.0)
    return _clamp01(pnl / target)


def _clamp01(value: float | None) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    if not math.isfinite(number):
        number = 0.0
    return max(0.0, min(1.0, number))


__all__ = [
    "RuntimePair",
    "advanced_ml_config_snapshot",
    "advanced_ml_runtime_mode",
    "build_exit_features",
    "evaluate_advanced_regime",
    "evaluate_probabilistic_exit",
    "generate_post_trade_shadow_report",
    "get_advanced_ml_config",
    "log_advanced_ml_startup_status",
    "reset_advanced_ml_runtime_cache",
    "should_apply_live_advanced_exit",
]
