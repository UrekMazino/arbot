import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
EXECUTION_DIR = ROOT / "Execution"
if str(EXECUTION_DIR) not in sys.path:
    sys.path.insert(0, str(EXECUTION_DIR))

from exit_decision_trace import build_exit_decision_trace_payload  # noqa: E402


def _state(**overrides):
    base = {
        "entry_time": 123.0,
        "entry_z": -2.2,
        "partial_exits": [],
        "trailing_stop_active": False,
        "trailing_stop_level": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _decision(**overrides):
    base = {
        "action": SimpleNamespace(value="hold"),
        "reason": "no exit candidates",
        "selected_candidate": None,
        "blocked_candidates": (),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _config(**overrides):
    base = {
        "take_profit_z": 0.35,
        "net_profit_guard_enabled": True,
        "net_profit_guard_require_pnl": True,
        "full_tp_guard_multiplier": 0.75,
        "partial_tp_guard_multiplier": 1.0,
        "trailing_stop_guard_multiplier": 1.0,
        "partial_exit_enabled": True,
        "partial_exit_z_threshold": 1.0,
        "pnl_profit_lock_enabled": False,
        "pnl_profit_lock_giveback_pct": 0.50,
    }
    base.update(overrides)
    return base


def test_trace_row_records_full_tp_zone_when_reached():
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="BTC-USDT-SWAP/XLM-USDT-SWAP",
        current_z=-0.23,
        floating_pnl_usdt=0.10,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(),
        trade_state=_state(),
        trade_manager_result={"action": "HOLD", "blocked_exit_reason": "take_profit"},
        exit_decision=_decision(),
    )

    assert payload["full_tp_zone_hit"] is True
    assert payload["take_profit_z"] == 0.35
    assert payload["current_z"] == -0.23


def test_trace_records_guard_block_and_effective_floor():
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="BTC/XLM",
        current_z=-0.23,
        floating_pnl_usdt=0.10,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(),
        trade_state=_state(),
        trade_manager_result={"action": "HOLD", "blocked_exit_reason": "take_profit"},
        exit_decision=_decision(),
    )

    assert payload["base_min_profit_usdt"] == 0.20
    assert payload["effective_min_profit_usdt"] == pytest.approx(0.15)
    assert payload["full_tp_guard_multiplier"] == 0.75
    assert payload["full_tp_guard_passed"] is False
    assert payload["trade_manager_guard_passed"] is False
    assert payload["full_tp_candidate_created"] is False
    assert payload["full_tp_candidate_blocked"] is False
    assert payload["full_tp_blocked_reason"] == "net_profit_guard"
    assert payload["why_full_tp_not_selected"] == "trade_manager_net_profit_guard_blocked"


def test_trace_records_guard_pass_and_selected_exit_reason():
    selected = SimpleNamespace(name="trade_manager_take_profit")
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="BTC/XLM",
        current_z=-0.23,
        floating_pnl_usdt=0.20,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(),
        trade_state=_state(),
        trade_manager_result={"action": "EXIT", "reason": "take_profit"},
        exit_decision=_decision(
            action=SimpleNamespace(value="full_exit"),
            reason="Mean-reversion target hit",
            selected_candidate=selected,
        ),
    )

    assert payload["full_tp_guard_passed"] is True
    assert payload["selected_exit_reason"] == "Mean-reversion target hit"
    assert payload["selected_exit_action"] == "full_exit"
    assert payload["selected_candidate_name"] == "trade_manager_take_profit"
    assert payload["trade_manager_guard_passed"] is True
    assert payload["full_tp_candidate_created"] is True
    assert payload["full_tp_candidate_blocked"] is False
    assert payload["why_full_tp_not_selected"] == ""


def test_trace_records_pnl_profit_lock_diagnostics():
    selected = SimpleNamespace(name="trade_manager_pnl_profit_lock")
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="BTC/XLM",
        current_z=0.90,
        floating_pnl_usdt=0.49,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(pnl_profit_lock_enabled=True),
        trade_state=_state(
            max_favorable_pnl_usdt=1.00,
            pnl_profit_lock_active=True,
            pnl_profit_lock_floor=0.50,
        ),
        trade_manager_result={"action": "EXIT", "reason": "pnl_profit_lock"},
        exit_decision=_decision(
            action=SimpleNamespace(value="full_exit"),
            reason="PnL profit lock",
            selected_candidate=selected,
        ),
    )

    assert payload["pnl_profit_lock_enabled"] is True
    assert payload["pnl_profit_lock_active"] is True
    assert payload["max_favorable_pnl_usdt"] == pytest.approx(1.00)
    assert payload["pnl_profit_lock_floor"] == pytest.approx(0.50)
    assert payload["pnl_profit_lock_giveback_pct"] == pytest.approx(0.50)
    assert payload["pnl_profit_lock_selected"] is True


def test_trace_explains_preemption_after_full_tp_guard_passes():
    selected = SimpleNamespace(name="cointegration_lost_losing")
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="BTC/XLM",
        current_z=-0.23,
        floating_pnl_usdt=0.20,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(),
        trade_state=_state(),
        trade_manager_result={"action": "EXIT", "reason": "take_profit"},
        exit_decision=_decision(
            action=SimpleNamespace(value="full_exit"),
            reason="cointegration quality exit",
            selected_candidate=selected,
        ),
    )

    assert payload["full_tp_guard_passed"] is True
    assert payload["full_tp_candidate_created"] is True
    assert payload["why_full_tp_not_selected"] == "higher_priority_exit_selected:cointegration_lost_losing"


def test_trace_explains_orchestrator_guard_block_after_manager_guard_passes():
    blocked = SimpleNamespace(
        candidate=SimpleNamespace(name="trade_manager_take_profit"),
        base_min_profit_usdt=0.20,
        effective_min_profit_usdt=0.15,
        guard_multiplier=0.75,
    )
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="BTC/XLM",
        current_z=-0.23,
        floating_pnl_usdt=0.16,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(),
        trade_state=_state(),
        trade_manager_result={"action": "EXIT", "reason": "take_profit"},
        exit_decision=_decision(
            action=SimpleNamespace(value="hold"),
            reason="net profit guard blocked all soft exit candidates",
            blocked_candidates=(blocked,),
        ),
    )

    assert payload["full_tp_guard_passed"] is True
    assert payload["orchestrator_base_min_profit_usdt"] == pytest.approx(0.20)
    assert payload["orchestrator_effective_min_profit_usdt"] == pytest.approx(0.15)
    assert payload["orchestrator_guard_multiplier"] == pytest.approx(0.75)
    assert payload["orchestrator_guard_passed"] is False
    assert payload["blocked_candidate_names"] == "trade_manager_take_profit"
    assert payload["full_tp_candidate_created"] is True
    assert payload["full_tp_candidate_blocked"] is True
    assert payload["why_full_tp_not_selected"] == "orchestrator_net_profit_guard_blocked"


def test_trace_detects_selected_full_tp_outside_zone_inconsistency():
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="BTC/XLM",
        current_z=0.90,
        floating_pnl_usdt=0.20,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(),
        trade_state=_state(),
        trade_manager_result={"action": "EXIT", "reason": "take_profit"},
        exit_decision=_decision(
            action=SimpleNamespace(value="full_exit"),
            reason="Mean-reversion target hit",
            selected_candidate=SimpleNamespace(name="trade_manager_take_profit"),
        ),
    )

    assert payload["full_tp_selected"] is True
    assert payload["full_tp_zone_hit"] is False
    assert payload["why_full_tp_not_selected"] == "trace_inconsistent:selected_but_outside_full_tp_zone"


def test_trace_detects_selected_full_tp_guard_failed_inconsistency():
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="BTC/XLM",
        current_z=0.20,
        floating_pnl_usdt=0.10,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(),
        trade_state=_state(),
        trade_manager_result={"action": "EXIT", "reason": "take_profit"},
        exit_decision=_decision(
            action=SimpleNamespace(value="full_exit"),
            reason="Mean-reversion target hit",
            selected_candidate=SimpleNamespace(name="trade_manager_take_profit"),
        ),
    )

    assert payload["full_tp_zone_hit"] is True
    assert payload["trade_manager_guard_passed"] is False
    assert payload["why_full_tp_not_selected"] == "trace_inconsistent:selected_but_trade_manager_guard_failed"


def test_trace_does_not_mutate_trade_state():
    trade_state = _state(partial_exits=[])
    before = dict(trade_state.__dict__)

    build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="BTC/XLM",
        current_z=0.90,
        floating_pnl_usdt=0.30,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(),
        trade_state=trade_state,
        trade_manager_result={"action": "PARTIAL_EXIT", "reason": "partial_profit"},
        exit_decision=_decision(
            action=SimpleNamespace(value="partial_exit"),
            reason="partial profit",
            selected_candidate=SimpleNamespace(name="trade_manager_partial_profit"),
        ),
    )

    assert trade_state.__dict__ == before


def test_trace_module_has_no_order_execution_imports():
    source = (EXECUTION_DIR / "exit_decision_trace.py").read_text(encoding="utf-8")

    assert "func_execution_calls" not in source
    assert "initialise_order_execution" not in source
    assert "place_market_close_order" not in source


# ── Part F: Exit opportunity diagnostics tests ────────────────────────────────

def test_exit_opportunity_trace_emits_rows_without_changing_exit_decisions():
    """Calling the payload builder must not mutate trade_state or change exit decision."""
    ts = _state(max_favorable_pnl_usdt=0.20, pnl_profit_lock_active=False)
    before = dict(ts.__dict__)
    decision_before = _decision()

    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="OP-USDT-SWAP/XLM-USDT-SWAP",
        current_z=0.80,
        floating_pnl_usdt=0.10,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(),
        trade_state=ts,
        trade_manager_result={"action": "HOLD", "reason": "monitoring"},
        exit_decision=decision_before,
    )

    # Trade state must not be mutated
    assert ts.__dict__ == before
    # Payload must be a dict (not None or exception)
    assert isinstance(payload, dict)
    assert payload["selected_exit_action"] == "hold"


def test_z_zone_booleans_are_set_correctly():
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="AAA/BBB",
        current_z=0.90,
        floating_pnl_usdt=0.05,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(),
        trade_state=_state(),
        trade_manager_result={"action": "HOLD"},
        exit_decision=_decision(),
    )

    assert payload["inside_z_1_50"] is True   # |0.90| <= 1.50
    assert payload["inside_z_1_25"] is True   # |0.90| <= 1.25
    assert payload["inside_z_1_00"] is True   # |0.90| <= 1.00
    assert payload["inside_z_0_75"] is False  # |0.90| > 0.75
    assert payload["inside_z_0_50"] is False
    assert payload["inside_z_0_35"] is False


def test_shadow_exit_z_1_50_recorded_not_executed():
    """shadow_exit_z_1_50_would_trigger is True when conditions met; no exit occurs."""
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="AAA/BBB",
        current_z=1.20,
        floating_pnl_usdt=0.20,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(full_tp_guard_multiplier=0.75),
        trade_state=_state(),
        trade_manager_result={"action": "HOLD"},
        exit_decision=_decision(),
    )

    # pnl=0.20 >= effective_guard (0.20*0.75=0.15), abs(z)=1.20 <= 1.50 → triggers
    assert payload["shadow_exit_z_1_50_would_trigger"] is True
    # But the exit_decision is still HOLD — nothing executed
    assert payload["selected_exit_action"] == "hold"
    assert payload["shadow_exit_z_1_00_would_trigger"] is False  # |1.20| > 1.00


def test_shadow_exit_z_1_00_recorded_not_executed():
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="AAA/BBB",
        current_z=0.80,
        floating_pnl_usdt=0.20,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(full_tp_guard_multiplier=0.75),
        trade_state=_state(),
        trade_manager_result={"action": "HOLD"},
        exit_decision=_decision(),
    )

    assert payload["shadow_exit_z_1_00_would_trigger"] is True
    assert payload["shadow_exit_z_1_50_would_trigger"] is True
    assert payload["selected_exit_action"] == "hold"


def test_shadow_early_net_profit_capture_recorded_not_executed():
    """shadow_early triggers when pnl >= guard, z improved 30%+, and a quality signal fires."""
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="AAA/BBB",
        current_z=1.00,      # abs=1.00; entry_z=-2.00 → improvement=50%
        floating_pnl_usdt=0.20,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(full_tp_guard_multiplier=0.75),
        trade_state=_state(entry_z=-2.00),
        trade_manager_result={"action": "HOLD"},
        exit_decision=_decision(),
        coint_flag=0,         # cointegration lost → quality signal
    )

    assert payload["shadow_early_net_profit_capture_would_trigger"] is True
    assert "coint_lost" in payload["shadow_early_net_profit_capture_reason"]
    assert payload["selected_exit_action"] == "hold"


def test_shadow_early_net_profit_capture_does_not_trigger_without_quality_signal():
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="AAA/BBB",
        current_z=1.00,
        floating_pnl_usdt=0.20,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(full_tp_guard_multiplier=0.75),
        trade_state=_state(entry_z=-2.00),
        trade_manager_result={"action": "HOLD"},
        exit_decision=_decision(),
        coint_flag=1,           # coint is healthy — no quality signal
        current_break_risk=0.05,  # below 0.10 threshold
    )

    assert payload["shadow_early_net_profit_capture_would_trigger"] is False


def test_pnl_profit_lock_should_activate_true_when_mfe_above_activation_floor():
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="AAA/BBB",
        current_z=1.20,
        floating_pnl_usdt=0.10,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(
            pnl_profit_lock_enabled=True,
            full_tp_guard_multiplier=0.75,  # effective=0.15, buffer=0.05 → floor=0.20
        ),
        trade_state=_state(
            max_favorable_pnl_usdt=0.25,   # 0.25 >= 0.20 → should activate
            pnl_profit_lock_active=False,   # but active flag not set
        ),
        trade_manager_result={"action": "HOLD"},
        exit_decision=_decision(),
    )

    assert payload["pnl_profit_lock_should_have_activated"] is True
    assert payload["pnl_profit_lock_active"] is False
    assert payload["pnl_profit_lock_miss_reason"] == "active_flag_not_set_in_trade_state"


def test_pnl_profit_lock_miss_reason_recorded_when_should_activate_but_not_active():
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="AAA/BBB",
        current_z=1.50,
        floating_pnl_usdt=0.05,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(
            pnl_profit_lock_enabled=True,
            full_tp_guard_multiplier=0.75,
        ),
        trade_state=_state(
            max_favorable_pnl_usdt=0.30,  # well above activation floor (0.20)
            pnl_profit_lock_active=False,  # bug: should be active but isn't
        ),
        trade_manager_result={"action": "HOLD"},
        exit_decision=_decision(),
    )

    assert payload["pnl_profit_lock_should_have_activated"] is True
    assert "active_flag_not_set" in payload["pnl_profit_lock_miss_reason"]


def test_shadow_profit_lock_exit_triggers_when_lock_should_be_active_but_is_not():
    """If the lock should be active and PnL <= shadow floor, shadow_profit_lock_exit fires."""
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="AAA/BBB",
        current_z=1.50,
        floating_pnl_usdt=0.04,    # below shadow giveback floor
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(
            pnl_profit_lock_enabled=True,
            full_tp_guard_multiplier=0.75,
            pnl_profit_lock_giveback_pct=0.50,
        ),
        trade_state=_state(
            max_favorable_pnl_usdt=0.30,   # activation_floor=0.15+0.05=0.20 < 0.30
            pnl_profit_lock_active=False,
        ),
        trade_manager_result={"action": "HOLD"},
        exit_decision=_decision(),
    )

    # shadow_floor = max(0.15, 0, 0.30*0.50) = max(0.15, 0.15) = 0.15
    # pnl=0.04 <= 0.15 → shadow_profit_lock_exit triggers
    assert payload["shadow_profit_lock_exit_would_trigger"] is True
    assert payload["selected_exit_action"] == "hold"


def test_trend_risk_off_mr_shadow_block_recorded_not_executed():
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="SOL-USDT-SWAP/ADA-USDT-SWAP",
        current_z=1.80,
        floating_pnl_usdt=-0.10,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(),
        trade_state=_state(),
        trade_manager_result={"action": "HOLD"},
        exit_decision=_decision(),
        entry_strategy="STATARB_MR",
        entry_regime="TREND",
    )

    assert payload["statarb_mr_in_trend_regime"] is True
    assert payload["statarb_mr_in_risk_off_regime"] is False
    assert payload["trend_or_riskoff_block_would_have_blocked"] is True
    assert payload["shadow_trend_mr_block_would_trigger"] is True
    # No entry was actually blocked — this is shadow-only
    assert payload["selected_exit_action"] == "hold"


def test_risk_off_mr_shadow_block_recorded():
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="SOL-USDT-SWAP/ADA-USDT-SWAP",
        current_z=2.10,
        floating_pnl_usdt=-0.20,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(),
        trade_state=_state(),
        trade_manager_result={"action": "HOLD"},
        exit_decision=_decision(),
        entry_strategy="STATARB_MR",
        entry_regime="RISK_OFF",
    )

    assert payload["statarb_mr_in_risk_off_regime"] is True
    assert payload["statarb_mr_in_trend_regime"] is False
    assert payload["trend_or_riskoff_block_would_have_blocked"] is True


def test_non_mr_strategy_not_flagged_for_trend_block():
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="SOL-USDT-SWAP/ADA-USDT-SWAP",
        current_z=2.10,
        floating_pnl_usdt=-0.20,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(),
        trade_state=_state(),
        trade_manager_result={"action": "HOLD"},
        exit_decision=_decision(),
        entry_strategy="STATARB_TREND",
        entry_regime="TREND",
    )

    assert payload["statarb_mr_in_trend_regime"] is False
    assert payload["trend_or_riskoff_block_would_have_blocked"] is False


def test_pnl_source_mismatch_detected_when_atm_and_pair_state_mfe_differ():
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="AAA/BBB",
        current_z=1.00,
        floating_pnl_usdt=0.10,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(),
        trade_state=_state(max_favorable_pnl_usdt=0.30),   # ATM MFE = 0.30
        trade_manager_result={"action": "HOLD"},
        exit_decision=_decision(),
        pair_state_mfe_usdt=0.18,  # pair_state MFE = 0.18 → delta=0.12 > 0.001
    )

    assert payload["pnl_source_mismatch"] is True
    assert "ATM_MFE" in payload["pnl_source_mismatch_description"]
    assert payload["atm_mfe_vs_pair_state_mfe_delta"] == pytest.approx(0.12, abs=1e-6)


def test_no_pnl_source_mismatch_when_values_agree():
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="AAA/BBB",
        current_z=1.00,
        floating_pnl_usdt=0.10,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(),
        trade_state=_state(max_favorable_pnl_usdt=0.30),
        trade_manager_result={"action": "HOLD"},
        exit_decision=_decision(),
        pair_state_mfe_usdt=0.30005,  # within 0.001 tolerance
    )

    assert payload["pnl_source_mismatch"] is False


def test_z_improvement_pct_computed_correctly():
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="AAA/BBB",
        current_z=1.00,   # abs=1.00
        floating_pnl_usdt=0.10,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(),
        trade_state=_state(entry_z=-2.00),  # abs=2.00
        trade_manager_result={"action": "HOLD"},
        exit_decision=_decision(),
    )

    # (2.00 - 1.00) / 2.00 * 100 = 50%
    assert payload["z_improvement_pct"] == pytest.approx(50.0)
    assert payload["abs_entry_z"] == pytest.approx(2.00)
    assert payload["abs_current_z"] == pytest.approx(1.00)


def test_existing_exit_behavior_unchanged_after_new_fields():
    """All existing exit trace fields work as before; new fields are additive."""
    selected = SimpleNamespace(name="trade_manager_take_profit")
    payload = build_exit_decision_trace_payload(
        timestamp=1.0,
        pair="BTC/XLM",
        current_z=-0.23,
        floating_pnl_usdt=0.20,
        base_min_profit_usdt=0.20,
        trade_manager_config=_config(),
        trade_state=_state(),
        trade_manager_result={"action": "EXIT", "reason": "take_profit"},
        exit_decision=_decision(
            action=SimpleNamespace(value="full_exit"),
            reason="Mean-reversion target hit",
            selected_candidate=selected,
        ),
    )

    # Existing fields preserved
    assert payload["full_tp_guard_passed"] is True
    assert payload["selected_exit_reason"] == "Mean-reversion target hit"
    assert payload["selected_exit_action"] == "full_exit"
    assert payload["selected_candidate_name"] == "trade_manager_take_profit"
    assert payload["why_full_tp_not_selected"] == ""
    # New fields present and sensible
    assert "shadow_exit_z_1_50_would_trigger" in payload
    assert "pnl_profit_lock_should_have_activated" in payload
    assert "statarb_mr_in_trend_regime" in payload


def test_no_order_execution_imports_after_extension():
    source = (EXECUTION_DIR / "exit_decision_trace.py").read_text(encoding="utf-8")

    assert "func_execution_calls" not in source
    assert "initialise_order_execution" not in source
    assert "place_market_close_order" not in source
    assert "place_limit_close" not in source
