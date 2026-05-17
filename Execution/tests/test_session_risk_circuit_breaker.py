import shutil
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import session_risk_circuit_breaker as scb  # noqa: E402
from session_risk_circuit_breaker import (  # noqa: E402
    RiskCircuitBreakerConfig,
    RiskCircuitBreakerState,
    evaluate_risk_circuit_breaker,
    get_session_consecutive_losses,
    get_session_realized_pnl,
    get_session_run_id,
    record_session_trade_result,
    reset_session_circuit_breaker_state,
)

# ── module-level state-file isolation ─────────────────────────────────────────
# Redirect SESSION_RISK_STATE_FILE to a temp directory for the entire module so
# tests never read from or write to the production state file.

_orig_state_file = scb.SESSION_RISK_STATE_FILE
_tmp_module_dir: Path | None = None


def setup_module(_mod=None):
    global _tmp_module_dir
    _tmp_module_dir = Path(tempfile.mkdtemp())
    scb.SESSION_RISK_STATE_FILE = _tmp_module_dir / "session_risk_state.json"


def teardown_module(_mod=None):
    scb.SESSION_RISK_STATE_FILE = _orig_state_file
    if _tmp_module_dir and _tmp_module_dir.exists():
        shutil.rmtree(_tmp_module_dir, ignore_errors=True)


# ── helpers ───────────────────────────────────────────────────────────────────

def _cfg(**overrides) -> RiskCircuitBreakerConfig:
    defaults = dict(
        session_max_loss_usdt=5.0,
        max_consecutive_losses=3,
        max_drawdown_usdt=10.0,
        disable_entries_after_risk_stop=True,
        state_mode="session",
    )
    defaults.update(overrides)
    return RiskCircuitBreakerConfig(**defaults)


def _state(**overrides) -> RiskCircuitBreakerState:
    defaults = dict(
        session_realized_pnl_usdt=get_session_realized_pnl(),
        session_consecutive_losses=get_session_consecutive_losses(),
        persistent_consecutive_losses=0,
        current_drawdown_usdt=None,
        equity_trusted=True,
        run_id=get_session_run_id(),
    )
    defaults.update(overrides)
    return RiskCircuitBreakerState(**defaults)


def setup_function():
    reset_session_circuit_breaker_state()


# ── Test 1: New run starts with zero session consecutive losses ───────────────

def test_new_run_resets_session_consecutive_losses():
    # reset_session_circuit_breaker_state() is called in setup_function.
    assert get_session_consecutive_losses() == 0
    assert get_session_realized_pnl() == 0.0


# ── Test 2: Persistent mode reads the persistent counter, not session ─────────

def test_persistent_mode_uses_persistent_counter():
    # Session counter is 0 (fresh). Persistent counter is injected at 3 (the limit).
    cfg = _cfg(state_mode="persistent", max_consecutive_losses=3)
    state = _state(
        session_consecutive_losses=0,
        persistent_consecutive_losses=3,
    )
    decision = evaluate_risk_circuit_breaker(state, cfg)

    assert decision.active, "persistent counter=3 at limit should trigger"
    assert "consecutive_loss_limit_hit" in decision.reasons
    # Metadata must expose both counters and the source.
    breach = next(b for b in decision.breaches if b.reason == "consecutive_loss_limit_hit")
    assert breach.metadata["state_mode"] == "persistent"
    assert breach.metadata["persistent_consecutive_losses"] == 3
    assert breach.metadata["session_consecutive_losses"] == 0


# ── Test 3: session_realized_pnl_usdt accumulates correctly ──────────────────

def test_session_realized_pnl_updates_after_trades():
    record_session_trade_result(is_win=False, pnl_usdt=-0.18)
    record_session_trade_result(is_win=False, pnl_usdt=-0.25)
    record_session_trade_result(is_win=True,  pnl_usdt=+0.10)

    assert abs(get_session_realized_pnl() - (-0.33)) < 1e-9
    # A win resets the consecutive-loss streak but does NOT reset the realized PnL.
    assert get_session_consecutive_losses() == 0


# ── Test 4: Session mode fires on session counter, ignores persistent ─────────

def test_session_mode_uses_session_counter_not_persistent():
    record_session_trade_result(False, -0.1)
    record_session_trade_result(False, -0.1)
    record_session_trade_result(False, -0.1)  # session count = 3

    cfg = _cfg(state_mode="session", max_consecutive_losses=3)
    state = _state(
        session_consecutive_losses=get_session_consecutive_losses(),
        persistent_consecutive_losses=0,  # persistent=0 — must NOT trigger alone
    )
    decision = evaluate_risk_circuit_breaker(state, cfg)

    assert decision.active
    assert "consecutive_loss_limit_hit" in decision.reasons
    breach = next(b for b in decision.breaches if b.reason == "consecutive_loss_limit_hit")
    assert breach.metadata["state_mode"] == "session"


# ── Test 5: Alert payload contains run_id, state_mode, both counters ─────────

def test_breach_payload_contains_run_and_mode_fields():
    run_id = get_session_run_id()
    cfg = _cfg(state_mode="session", max_consecutive_losses=3)
    state = RiskCircuitBreakerState(
        session_consecutive_losses=3,
        persistent_consecutive_losses=0,
        session_realized_pnl_usdt=-0.3,
        current_drawdown_usdt=None,
        equity_trusted=True,
        run_id=run_id,
    )
    decision = evaluate_risk_circuit_breaker(state, cfg)
    assert decision.active

    payloads = decision.risk_event_payloads(pair="AAA/BBB")
    breach_pl = next(p for p in payloads if p["alert_type"] == "consecutive_loss_limit_hit")

    assert breach_pl["run_id"] == run_id
    assert breach_pl["state_mode"] == "session"
    assert breach_pl["session_consecutive_losses"] == 3
    assert breach_pl["persistent_consecutive_losses"] == 0
    # Back-compat field must reflect the active counter.
    assert breach_pl["consecutive_losses"] == 3


# ── Test 6: No limits configured → always passes ─────────────────────────────

def test_disabled_config_never_triggers():
    for _ in range(20):
        record_session_trade_result(False, -5.0)  # huge session losses

    cfg = RiskCircuitBreakerConfig(
        session_max_loss_usdt=None,
        max_consecutive_losses=None,
        max_drawdown_usdt=None,
        disable_entries_after_risk_stop=True,
        state_mode="session",
    )
    state = _state(
        session_consecutive_losses=get_session_consecutive_losses(),
        persistent_consecutive_losses=100,
        current_drawdown_usdt=-500.0,
        session_realized_pnl_usdt=get_session_realized_pnl(),
    )
    decision = evaluate_risk_circuit_breaker(state, cfg)
    assert not decision.active
    assert not decision.block_new_entries


# ── Test 7: Session mode ignores a large persistent counter ───────────────────

def test_session_mode_ignores_large_persistent_counter():
    # No losses in this session — persistent counter is 10 (from prior runs).
    cfg = _cfg(state_mode="session", max_consecutive_losses=3)
    state = _state(
        session_consecutive_losses=0,
        persistent_consecutive_losses=10,
    )
    decision = evaluate_risk_circuit_breaker(state, cfg)
    assert not decision.active, (
        "session mode must NOT trigger when session counter=0, "
        "even if persistent counter is well above the limit"
    )
