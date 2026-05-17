from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXECUTION = ROOT / "Execution"
if str(EXECUTION) not in sys.path:
    sys.path.insert(0, str(EXECUTION))

from session_risk_circuit_breaker import (  # noqa: E402
    RiskCircuitBreakerConfig,
    RiskCircuitBreakerState,
    evaluate_risk_circuit_breaker,
)


def test_disabled_config_preserves_current_entry_behavior():
    decision = evaluate_risk_circuit_breaker(
        RiskCircuitBreakerState(
            session_realized_pnl_usdt=-100.0,
            session_consecutive_losses=99,
            current_drawdown_usdt=-100.0,
        ),
        RiskCircuitBreakerConfig(),
    )

    assert decision.active is False
    assert decision.block_new_entries is False
    assert decision.breaches == ()


def test_session_loss_limit_blocks_new_entry_and_emits_risk_payload():
    decision = evaluate_risk_circuit_breaker(
        RiskCircuitBreakerState(session_realized_pnl_usdt=-5.01),
        RiskCircuitBreakerConfig(session_max_loss_usdt=5.0),
    )

    assert decision.block_new_entries is True
    assert decision.reasons == ("session_loss_limit_hit",)
    assert decision.entry_block_reasons == ("entries_blocked_by_session_loss",)
    payload = decision.risk_event_payloads(pair="AAA/BBB")[0]
    assert payload["alert_type"] == "session_loss_limit_hit"
    assert payload["action"] == "block_new_entries"
    assert payload["session_realized_pnl_usdt"] == -5.01


def test_consecutive_loss_limit_blocks_new_entry():
    decision = evaluate_risk_circuit_breaker(
        RiskCircuitBreakerState(session_consecutive_losses=3),
        RiskCircuitBreakerConfig(max_consecutive_losses=3),
    )

    assert decision.block_new_entries is True
    assert decision.reasons == ("consecutive_loss_limit_hit",)
    assert decision.entry_block_reasons == ("entries_blocked_by_consecutive_losses",)


def test_drawdown_limit_blocks_new_entry():
    decision = evaluate_risk_circuit_breaker(
        RiskCircuitBreakerState(current_drawdown_usdt=-10.5),
        RiskCircuitBreakerConfig(max_drawdown_usdt=10.0),
    )

    assert decision.block_new_entries is True
    assert decision.reasons == ("drawdown_limit_hit",)
    assert decision.entry_block_reasons == ("entries_blocked_by_drawdown",)


def test_disable_entries_flag_can_observe_without_blocking_or_closing():
    decision = evaluate_risk_circuit_breaker(
        RiskCircuitBreakerState(
            session_realized_pnl_usdt=-6.0,
            session_consecutive_losses=4,
            current_drawdown_usdt=-12.0,
        ),
        RiskCircuitBreakerConfig(
            session_max_loss_usdt=5.0,
            max_consecutive_losses=3,
            max_drawdown_usdt=10.0,
            disable_entries_after_risk_stop=False,
        ),
    )

    assert decision.active is True
    assert decision.block_new_entries is False
    assert {payload["action"] for payload in decision.risk_event_payloads()} == {"observe_only"}


def test_config_from_env_uses_disabled_defaults_and_parses_limits(monkeypatch):
    keys = [
        "STATBOT_SESSION_MAX_LOSS_USDT",
        "STATBOT_MAX_CONSECUTIVE_LOSSES",
        "STATBOT_MAX_DRAWDOWN_USDT",
        "STATBOT_DISABLE_ENTRIES_AFTER_RISK_STOP",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)

    config = RiskCircuitBreakerConfig.from_env()
    assert config.session_max_loss_usdt is None
    assert config.max_consecutive_losses is None
    assert config.max_drawdown_usdt is None
    assert config.disable_entries_after_risk_stop is True

    monkeypatch.setenv("STATBOT_SESSION_MAX_LOSS_USDT", "5")
    monkeypatch.setenv("STATBOT_MAX_CONSECUTIVE_LOSSES", "3")
    monkeypatch.setenv("STATBOT_MAX_DRAWDOWN_USDT", "10")
    monkeypatch.setenv("STATBOT_DISABLE_ENTRIES_AFTER_RISK_STOP", "false")

    config = RiskCircuitBreakerConfig.from_env()
    assert config.session_max_loss_usdt == 5.0
    assert config.max_consecutive_losses == 3
    assert config.max_drawdown_usdt == 10.0
    assert config.disable_entries_after_risk_stop is False


def test_existing_open_trade_management_remains_separate_from_entry_block():
    source = (ROOT / "Execution" / "main_execution.py").read_text(encoding="utf-8")

    assert "blocked_by_risk = risk_circuit_decision.block_new_entries" in source
    assert "if not is_manage_new_trades or kill_switch == 1:" in source
    assert "monitor_exit(" in source
    assert "Risk circuit breaker active; skipping new entries." in source


def test_risk_circuit_breaker_does_not_import_order_execution_modules():
    source = (ROOT / "Execution" / "session_risk_circuit_breaker.py").read_text(encoding="utf-8")

    forbidden_terms = [
        "func_execution_calls",
        "func_close_positions",
        "initialise_order_execution",
        "close_account_positions",
        "close_all_positions",
        "place_order",
    ]
    for term in forbidden_terms:
        assert term not in source
