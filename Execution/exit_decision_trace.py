from __future__ import annotations

import math
from typing import Any, Mapping


def _finite_float(value: Any, default: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _enum_value(value: Any) -> str:
    if value is None:
        return ""
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        return str(enum_value)
    return str(value)


def _mapping_get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _profit_guard_passed(
    *,
    net_profit_guard_enabled: bool,
    net_profit_guard_require_pnl: bool,
    floating_pnl_usdt: float | None,
    effective_min_profit_usdt: float,
) -> bool:
    if not net_profit_guard_enabled:
        return True
    if floating_pnl_usdt is None:
        return not net_profit_guard_require_pnl
    return floating_pnl_usdt >= max(float(effective_min_profit_usdt or 0.0), 0.0)


def _guard_threshold(config: Mapping[str, Any], min_profit_usdt: float | None, multiplier_key: str) -> tuple[float, float]:
    base = max(_finite_float(min_profit_usdt, 0.0) or 0.0, 0.0)
    multiplier = _finite_float(config.get(multiplier_key), 1.0)
    if multiplier is None or multiplier < 0:
        multiplier = 1.0
    return base * multiplier, multiplier


def _selected_candidate_name(exit_decision: Any) -> str:
    candidate = _mapping_get(exit_decision, "selected_candidate")
    return str(_mapping_get(candidate, "name", "") or "").strip()


def _find_blocked_candidate(exit_decision: Any, candidate_name: str) -> Any | None:
    for block in (_mapping_get(exit_decision, "blocked_candidates", ()) or ()):
        candidate = _mapping_get(block, "candidate")
        if str(_mapping_get(candidate, "name", "") or "").strip() == candidate_name:
            return block
    return None


def _candidate_metadata(candidate: Any) -> Mapping[str, Any]:
    metadata = _mapping_get(candidate, "metadata", {}) or {}
    return metadata if isinstance(metadata, Mapping) else {}


def build_exit_decision_trace_payload(
    *,
    timestamp: float,
    pair: str,
    current_z: float | None,
    floating_pnl_usdt: float | None,
    base_min_profit_usdt: float | None,
    trade_manager_config: Mapping[str, Any],
    trade_state: Any,
    trade_manager_result: Mapping[str, Any] | None,
    exit_decision: Any,
) -> dict[str, Any]:
    """Build read-only exit diagnostics without mutating trade-manager state."""

    config = trade_manager_config or {}
    tm_result = trade_manager_result if isinstance(trade_manager_result, Mapping) else {}
    z = _finite_float(current_z)
    pnl = _finite_float(floating_pnl_usdt)
    take_profit_z = _finite_float(config.get("take_profit_z"), 0.0) or 0.0
    full_tp_effective_min, full_tp_multiplier = _guard_threshold(
        config,
        base_min_profit_usdt,
        "full_tp_guard_multiplier",
    )
    partial_tp_effective_min, _partial_multiplier = _guard_threshold(
        config,
        base_min_profit_usdt,
        "partial_tp_guard_multiplier",
    )
    trailing_effective_min, _trailing_multiplier = _guard_threshold(
        config,
        base_min_profit_usdt,
        "trailing_stop_guard_multiplier",
    )
    max_favorable_pnl = _finite_float(_mapping_get(trade_state, "max_favorable_pnl_usdt"))
    pnl_profit_lock_enabled = bool(config.get("pnl_profit_lock_enabled", False))
    pnl_profit_lock_active = bool(_mapping_get(trade_state, "pnl_profit_lock_active", False))
    pnl_profit_lock_floor = _finite_float(_mapping_get(trade_state, "pnl_profit_lock_floor"))
    pnl_profit_lock_giveback_pct = _finite_float(config.get("pnl_profit_lock_giveback_pct"), 0.50)

    net_guard_enabled = bool(config.get("net_profit_guard_enabled", True))
    net_guard_require_pnl = bool(config.get("net_profit_guard_require_pnl", True))
    full_tp_zone_hit = bool(z is not None and take_profit_z >= 0 and abs(z) <= take_profit_z)
    full_tp_guard_passed = bool(
        full_tp_zone_hit
        and _profit_guard_passed(
            net_profit_guard_enabled=net_guard_enabled,
            net_profit_guard_require_pnl=net_guard_require_pnl,
            floating_pnl_usdt=pnl,
            effective_min_profit_usdt=full_tp_effective_min,
        )
    )
    full_tp_blocked_reason = ""
    if full_tp_zone_hit and not full_tp_guard_passed:
        full_tp_blocked_reason = "net_profit_guard"

    partial_threshold = _finite_float(config.get("partial_exit_z_threshold"), 1.0) or 1.0
    partial_enabled = bool(config.get("partial_exit_enabled", True))
    partial_exits = _mapping_get(trade_state, "partial_exits", []) or []
    partial_zone = bool(
        partial_enabled
        and z is not None
        and abs(z) < partial_threshold
        and not partial_exits
        and not full_tp_guard_passed
    )
    partial_tp_eligible = bool(
        partial_zone
        and _profit_guard_passed(
            net_profit_guard_enabled=net_guard_enabled,
            net_profit_guard_require_pnl=net_guard_require_pnl,
            floating_pnl_usdt=pnl,
            effective_min_profit_usdt=partial_tp_effective_min,
        )
    )

    trailing_stop_active = bool(_mapping_get(trade_state, "trailing_stop_active", False))
    trailing_stop_level = _finite_float(_mapping_get(trade_state, "trailing_stop_level"))
    trailing_stop_eligible = bool(
        trailing_stop_active
        and trailing_stop_level is not None
        and z is not None
        and abs(z) > trailing_stop_level
        and _profit_guard_passed(
            net_profit_guard_enabled=net_guard_enabled,
            net_profit_guard_require_pnl=net_guard_require_pnl,
            floating_pnl_usdt=pnl,
            effective_min_profit_usdt=trailing_effective_min,
        )
    )

    tm_action = str(tm_result.get("action") or "").strip()
    tm_reason = str(tm_result.get("reason") or tm_result.get("blocked_exit_reason") or "").strip()
    tm_reason_code = tm_reason.lower()
    selected_candidate_obj = _mapping_get(exit_decision, "selected_candidate")
    selected_candidate = _selected_candidate_name(exit_decision)
    selected_exit_action = _enum_value(_mapping_get(exit_decision, "action"))
    selected_exit_reason = str(_mapping_get(exit_decision, "reason", "") or "").strip()
    blocked_names = {
        str(_mapping_get(_mapping_get(block, "candidate"), "name", "") or "").strip()
        for block in (_mapping_get(exit_decision, "blocked_candidates", ()) or ())
        if _mapping_get(block, "candidate") is not None
    }
    blocked_names.discard("")
    blocked_candidate_names = ",".join(sorted(blocked_names))
    full_tp_block = _find_blocked_candidate(exit_decision, "trade_manager_take_profit")
    if full_tp_block is not None:
        orchestrator_base_min = _finite_float(_mapping_get(full_tp_block, "base_min_profit_usdt"))
        orchestrator_effective_min = _finite_float(_mapping_get(full_tp_block, "effective_min_profit_usdt"))
        orchestrator_multiplier = _finite_float(_mapping_get(full_tp_block, "guard_multiplier"))
        orchestrator_guard_passed = False
    elif selected_candidate == "trade_manager_take_profit":
        selected_metadata = _candidate_metadata(selected_candidate_obj)
        orchestrator_base_min = _finite_float(selected_metadata.get("base_min_profit_usdt"), full_tp_effective_min)
        orchestrator_effective_min = _finite_float(
            selected_metadata.get("effective_min_profit_usdt"),
            full_tp_effective_min,
        )
        orchestrator_multiplier = _finite_float(selected_metadata.get("guard_multiplier"), full_tp_multiplier)
        orchestrator_guard_passed = True
    else:
        orchestrator_base_min = None
        orchestrator_effective_min = None
        orchestrator_multiplier = None
        orchestrator_guard_passed = None

    full_tp_selected = selected_candidate == "trade_manager_take_profit" or (
        tm_action.upper() == "EXIT"
        and tm_reason_code == "take_profit"
        and selected_candidate == "trade_manager_take_profit"
    )
    full_tp_candidate_blocked = "trade_manager_take_profit" in blocked_names
    full_tp_candidate_created = bool(
        (tm_action.upper() == "EXIT" and tm_reason_code == "take_profit")
        or selected_candidate == "trade_manager_take_profit"
        or full_tp_candidate_blocked
    )
    pnl_profit_lock_selected = selected_candidate == "trade_manager_pnl_profit_lock" or (
        tm_action.upper() == "EXIT"
        and tm_reason_code == "pnl_profit_lock"
        and selected_candidate == "trade_manager_pnl_profit_lock"
    )
    regime_break_eligible = bool(
        (tm_action.upper() == "EXIT" and tm_reason_code in {"regime_break", "diverging"})
        or selected_candidate in {"trade_manager_regime_break", "trade_manager_diverging"}
    )
    stall_exit_eligible = bool(
        (tm_action.upper() == "EXIT" and tm_reason_code == "stall")
        or selected_candidate == "trade_manager_stall"
    )

    trade_manager_guard_passed = full_tp_guard_passed
    if full_tp_selected and not full_tp_zone_hit:
        why_full_tp_not_selected = "trace_inconsistent:selected_but_outside_full_tp_zone"
    elif full_tp_selected and not trade_manager_guard_passed:
        why_full_tp_not_selected = "trace_inconsistent:selected_but_trade_manager_guard_failed"
    elif full_tp_selected and full_tp_candidate_blocked:
        why_full_tp_not_selected = "trace_inconsistent:selected_but_candidate_blocked"
    elif full_tp_selected:
        why_full_tp_not_selected = ""
    elif not full_tp_zone_hit:
        why_full_tp_not_selected = "outside_full_tp_zone"
    elif not trade_manager_guard_passed:
        why_full_tp_not_selected = "trade_manager_net_profit_guard_blocked"
    elif full_tp_candidate_blocked:
        why_full_tp_not_selected = "orchestrator_net_profit_guard_blocked"
    elif selected_candidate:
        why_full_tp_not_selected = f"higher_priority_exit_selected:{selected_candidate}"
    elif selected_exit_action and selected_exit_action.lower() != "hold":
        why_full_tp_not_selected = f"higher_priority_action_selected:{selected_exit_action}"
    else:
        why_full_tp_not_selected = "no_exit_selected"

    return {
        "timestamp": timestamp,
        "pair": str(pair or "").strip(),
        "entry_ts": _mapping_get(trade_state, "entry_time"),
        "entry_z": _mapping_get(trade_state, "entry_z"),
        "current_z": z,
        "floating_pnl_usdt": pnl,
        "base_min_profit_usdt": max(_finite_float(base_min_profit_usdt, 0.0) or 0.0, 0.0),
        "effective_min_profit_usdt": full_tp_effective_min,
        "full_tp_guard_multiplier": full_tp_multiplier,
        "take_profit_z": take_profit_z,
        "full_tp_zone_hit": full_tp_zone_hit,
        "trade_manager_guard_passed": trade_manager_guard_passed,
        "full_tp_guard_passed": full_tp_guard_passed,
        "full_tp_candidate_created": full_tp_candidate_created,
        "full_tp_candidate_blocked": full_tp_candidate_blocked,
        "full_tp_selected": full_tp_selected,
        "full_tp_blocked_reason": full_tp_blocked_reason,
        "orchestrator_base_min_profit_usdt": orchestrator_base_min,
        "orchestrator_effective_min_profit_usdt": orchestrator_effective_min,
        "orchestrator_guard_multiplier": orchestrator_multiplier,
        "orchestrator_guard_passed": orchestrator_guard_passed,
        "pnl_profit_lock_enabled": pnl_profit_lock_enabled,
        "pnl_profit_lock_active": pnl_profit_lock_active,
        "max_favorable_pnl_usdt": max_favorable_pnl,
        "pnl_profit_lock_floor": pnl_profit_lock_floor,
        "pnl_profit_lock_giveback_pct": pnl_profit_lock_giveback_pct,
        "pnl_profit_lock_selected": pnl_profit_lock_selected,
        "partial_tp_eligible": partial_tp_eligible,
        "trailing_stop_eligible": trailing_stop_eligible,
        "regime_break_eligible": regime_break_eligible,
        "stall_exit_eligible": stall_exit_eligible,
        "selected_exit_reason": selected_exit_reason,
        "selected_exit_action": selected_exit_action,
        "selected_candidate_name": selected_candidate,
        "blocked_candidate_names": blocked_candidate_names,
        "trade_manager_action": tm_action,
        "trade_manager_reason": tm_reason,
        "why_full_tp_not_selected": why_full_tp_not_selected,
    }


__all__ = ["build_exit_decision_trace_payload"]
