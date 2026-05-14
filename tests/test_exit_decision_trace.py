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
