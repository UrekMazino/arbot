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


# ── Shadow candidate evaluation ───────────────────────────────────────────────

_SHADOW_Z_ZONES = {
    "inside_z_1_50": 1.50,
    "inside_z_1_25": 1.25,
    "inside_z_1_00": 1.00,
    "inside_z_0_75": 0.75,
    "inside_z_0_50": 0.50,
    "inside_z_0_35": 0.35,
}

_SHADOW_GUARD_KEYS = {
    "inside_z_1_50": "z_1_50_guard_passed",
    "inside_z_1_25": "z_1_25_guard_passed",
    "inside_z_1_00": "z_1_00_guard_passed",
    "inside_z_0_75": "z_0_75_guard_passed",
    "inside_z_0_50": "z_0_50_guard_passed",
    "inside_z_0_35": "z_0_35_guard_passed",
}


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
    # ── Opportunity diagnostics context (all optional for backward compat) ──
    run_id: str | None = None,
    entry_strategy: str | None = None,
    entry_regime: str | None = None,
    current_regime: str | None = None,
    pair_state_mfe_usdt: float | None = None,
    position_snapshot_unrealized_pnl_usdt: float | None = None,
    floating_pnl_source: str | None = None,
    current_break_risk: float | None = None,
    coint_flag: int | None = None,
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

    # ── Part A: Z-improvement and source fields ───────────────────────────────
    entry_z_val = _finite_float(_mapping_get(trade_state, "entry_z"))
    abs_entry_z = abs(entry_z_val) if entry_z_val is not None else None
    abs_current_z = abs(z) if z is not None else None
    z_improvement_pct: float | None = None
    if abs_entry_z is not None and abs_current_z is not None and abs_entry_z > 0:
        z_improvement_pct = round((abs_entry_z - abs_current_z) / abs_entry_z * 100.0, 4)

    atm_mfe_usdt = max_favorable_pnl  # AdvancedTradeManager MFE (same source, alias)
    ps_mfe_usdt = _finite_float(pair_state_mfe_usdt)

    # ── Part A: Profit-lock should-have analysis ──────────────────────────────
    activation_buffer = _finite_float(config.get("pnl_profit_lock_activation_buffer_usdt"), 0.05) or 0.05
    min_lock_usdt = _finite_float(config.get("pnl_profit_lock_min_lock_usdt"), 0.0) or 0.0
    pnl_lock_activation_floor = full_tp_effective_min + activation_buffer

    pnl_profit_lock_should_have_activated = bool(
        pnl_profit_lock_enabled
        and max_favorable_pnl is not None
        and pnl is not None
        and max_favorable_pnl >= pnl_lock_activation_floor
    )

    pnl_profit_lock_shadow_floor: float | None = None
    if pnl_profit_lock_should_have_activated and max_favorable_pnl is not None:
        gvb = pnl_profit_lock_giveback_pct if pnl_profit_lock_giveback_pct is not None else 0.50
        pnl_profit_lock_shadow_floor = max(
            full_tp_effective_min,
            min_lock_usdt,
            max_favorable_pnl * (1.0 - gvb),
        )

    pnl_profit_lock_should_have_selected = bool(
        pnl_profit_lock_should_have_activated
        and pnl is not None
        and pnl_profit_lock_shadow_floor is not None
        and pnl <= pnl_profit_lock_shadow_floor
    )

    if not pnl_profit_lock_enabled:
        pnl_profit_lock_activation_reason = "disabled"
    elif max_favorable_pnl is None or pnl is None:
        pnl_profit_lock_activation_reason = "pnl_unavailable"
    elif max_favorable_pnl >= pnl_lock_activation_floor:
        pnl_profit_lock_activation_reason = (
            f"mfe={max_favorable_pnl:.4f}_ge_floor={pnl_lock_activation_floor:.4f}"
        )
    else:
        pnl_profit_lock_activation_reason = (
            f"mfe={max_favorable_pnl:.4f}_lt_floor={pnl_lock_activation_floor:.4f}"
        )

    pnl_profit_lock_miss_reason = ""
    if pnl_profit_lock_should_have_activated and not pnl_profit_lock_active:
        pnl_profit_lock_miss_reason = "active_flag_not_set_in_trade_state"
    elif pnl_profit_lock_should_have_selected and not pnl_profit_lock_selected:
        _sf = pnl_profit_lock_shadow_floor
        _sfstr = f"{_sf:.4f}" if _sf is not None else "?"
        _pstr = f"{pnl:.4f}" if pnl is not None else "?"
        pnl_profit_lock_miss_reason = f"should_select_pnl={_pstr}_le_floor={_sfstr}_but_not_selected"

    # ── Part A: Z-zone booleans and per-zone guard-pass ───────────────────────
    _shadow_guard_floor = max(full_tp_effective_min, 0.0)
    z_zone_results: dict[str, bool] = {}
    z_guard_results: dict[str, bool] = {}
    for zone_key, threshold in _SHADOW_Z_ZONES.items():
        inside = bool(z is not None and abs(z) <= threshold)
        guard_ok = bool(inside and pnl is not None and pnl >= _shadow_guard_floor)
        z_zone_results[zone_key] = inside
        guard_key = _SHADOW_GUARD_KEYS[zone_key]
        z_guard_results[guard_key] = guard_ok

    # ── Part B: Shadow exit candidates (diagnostic only, never executed) ──────
    shadow_exit_z_1_50_would_trigger = bool(
        z is not None and pnl is not None and abs(z) <= 1.50 and pnl >= _shadow_guard_floor
    )
    shadow_exit_z_1_00_would_trigger = bool(
        z is not None and pnl is not None and abs(z) <= 1.00 and pnl >= _shadow_guard_floor
    )

    # shadow_early_net_profit_capture: profit above floor + z improved 30% + at least one quality signal
    _z_improved_30 = z_improvement_pct is not None and z_improvement_pct >= 30.0
    _pnl_above_guard = pnl is not None and pnl >= _shadow_guard_floor
    _coint_weakening = coint_flag is not None and int(coint_flag) == 0
    _mfe_giveback = (
        max_favorable_pnl is not None
        and pnl is not None
        and max_favorable_pnl > 0.0
        and pnl < max_favorable_pnl * 0.70
    )
    _break_risk_elevated = current_break_risk is not None and _finite_float(current_break_risk, 0.0) > 0.10
    _regime_adverse = str(current_regime or "").strip().upper() in ("TREND", "RISK_OFF")
    _any_quality_signal = _coint_weakening or _mfe_giveback or _break_risk_elevated or _regime_adverse
    shadow_early_net_profit_capture_would_trigger = bool(
        _z_improved_30 and _pnl_above_guard and _any_quality_signal
    )
    _early_parts: list[str] = []
    if _coint_weakening:
        _early_parts.append("coint_lost")
    if _mfe_giveback:
        _early_parts.append("mfe_giveback")
    if _break_risk_elevated:
        _early_parts.append("break_risk_high")
    if _regime_adverse:
        _early_parts.append(f"regime_{str(current_regime or '').strip().upper()}")
    shadow_early_net_profit_capture_reason = "+".join(_early_parts) if _early_parts else ""

    # shadow_profit_lock_exit: lock should be active but isn't — and PnL would have triggered it
    shadow_profit_lock_exit_would_trigger = bool(
        pnl_profit_lock_should_have_activated
        and pnl_profit_lock_shadow_floor is not None
        and pnl is not None
        and pnl <= pnl_profit_lock_shadow_floor
        and not pnl_profit_lock_active
    )

    # shadow_trend_mr_block: STATARB_MR entered in TREND/RISK_OFF (entry would have been blocked)
    _strategy_upper = str(entry_strategy or "").strip().upper()
    _entry_regime_upper = str(entry_regime or "").strip().upper()
    _in_trend = _entry_regime_upper == "TREND"
    _in_risk_off = _entry_regime_upper == "RISK_OFF"
    shadow_trend_mr_block_would_trigger = bool(_strategy_upper == "STATARB_MR" and (_in_trend or _in_risk_off))
    shadow_trend_mr_block_reason = (
        f"STATARB_MR_in_{_entry_regime_upper}" if shadow_trend_mr_block_would_trigger else ""
    )

    # ── Part D: PnL source consistency audit ──────────────────────────────────
    atm_mfe_vs_pair_state_mfe_delta: float | None = None
    pnl_source_mismatch = False
    pnl_source_mismatch_description = ""
    if atm_mfe_usdt is not None and ps_mfe_usdt is not None:
        atm_mfe_vs_pair_state_mfe_delta = round(atm_mfe_usdt - ps_mfe_usdt, 6)
        if abs(atm_mfe_vs_pair_state_mfe_delta) > 0.001:
            pnl_source_mismatch = True
            pnl_source_mismatch_description = (
                f"ATM_MFE={atm_mfe_usdt:.4f} pair_state_MFE={ps_mfe_usdt:.4f} "
                f"delta={atm_mfe_vs_pair_state_mfe_delta:.4f}"
            )

    pos_snap_pnl = _finite_float(position_snapshot_unrealized_pnl_usdt)
    if not pnl_source_mismatch and pnl is not None and pos_snap_pnl is not None:
        _snap_delta = abs(pnl - pos_snap_pnl)
        if _snap_delta > 0.01:
            pnl_source_mismatch = True
            pnl_source_mismatch_description = (
                f"floating_pnl={pnl:.4f} position_snapshot={pos_snap_pnl:.4f} "
                f"delta={pnl - pos_snap_pnl:.4f}"
            )

    # ── Part E: TREND/RISK_OFF MR shadow block ────────────────────────────────
    statarb_mr_in_trend_regime = bool(_strategy_upper == "STATARB_MR" and _entry_regime_upper == "TREND")
    statarb_mr_in_risk_off_regime = bool(_strategy_upper == "STATARB_MR" and _entry_regime_upper == "RISK_OFF")
    trend_or_riskoff_block_would_have_blocked = shadow_trend_mr_block_would_trigger

    return {
        # ── Existing fields (unchanged) ───────────────────────────────────────
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
        # ── Part A: new opportunity-trace fields ──────────────────────────────
        "run_id": str(run_id or "").strip(),
        "entry_strategy": str(entry_strategy or "").strip(),
        "entry_regime": _entry_regime_upper,
        "current_regime": str(current_regime or "").strip().upper(),
        "abs_entry_z": abs_entry_z,
        "abs_current_z": abs_current_z,
        "z_improvement_pct": z_improvement_pct,
        "floating_pnl_source": str(floating_pnl_source or "").strip(),
        "pair_state_mfe_usdt": ps_mfe_usdt,
        "advanced_trade_manager_mfe_usdt": atm_mfe_usdt,
        "position_snapshot_unrealized_pnl_usdt": pos_snap_pnl,
        "effective_full_tp_floor_usdt": full_tp_effective_min,
        "pnl_profit_lock_activation_buffer_usdt": activation_buffer,
        "pnl_profit_lock_activation_floor": pnl_lock_activation_floor,
        "pnl_profit_lock_should_have_activated": pnl_profit_lock_should_have_activated,
        "pnl_profit_lock_should_have_selected": pnl_profit_lock_should_have_selected,
        "pnl_profit_lock_shadow_floor": pnl_profit_lock_shadow_floor,
        "pnl_profit_lock_activation_reason": pnl_profit_lock_activation_reason,
        "pnl_profit_lock_miss_reason": pnl_profit_lock_miss_reason,
        "exit_candidate_selected": selected_candidate,
        # ── Part A: Z-zone booleans ───────────────────────────────────────────
        **z_zone_results,
        **z_guard_results,
        # ── Part B: shadow exit candidates ───────────────────────────────────
        "shadow_exit_z_1_50_would_trigger": shadow_exit_z_1_50_would_trigger,
        "shadow_exit_z_1_00_would_trigger": shadow_exit_z_1_00_would_trigger,
        "shadow_early_net_profit_capture_would_trigger": shadow_early_net_profit_capture_would_trigger,
        "shadow_early_net_profit_capture_reason": shadow_early_net_profit_capture_reason,
        "shadow_profit_lock_exit_would_trigger": shadow_profit_lock_exit_would_trigger,
        "shadow_trend_mr_block_would_trigger": shadow_trend_mr_block_would_trigger,
        "shadow_trend_mr_block_reason": shadow_trend_mr_block_reason,
        # ── Part D: PnL source audit ──────────────────────────────────────────
        "pnl_source_mismatch": pnl_source_mismatch,
        "pnl_source_mismatch_description": pnl_source_mismatch_description,
        "atm_mfe_vs_pair_state_mfe_delta": atm_mfe_vs_pair_state_mfe_delta,
        # ── Part E: TREND/RISK_OFF MR shadow block ────────────────────────────
        "statarb_mr_in_trend_regime": statarb_mr_in_trend_regime,
        "statarb_mr_in_risk_off_regime": statarb_mr_in_risk_off_regime,
        "trend_or_riskoff_block_would_have_blocked": trend_or_riskoff_block_would_have_blocked,
        "trend_or_riskoff_block_reason": shadow_trend_mr_block_reason,
    }


__all__ = ["build_exit_decision_trace_payload"]
