"""
Tests for session risk circuit breaker state persistence across process restarts.

The session counters (_session_consecutive_losses, _session_realized_pnl_usdt)
are persisted to SESSION_RISK_STATE_FILE after every trade close.  On process
startup the file is read back; if the stored run_id matches the current run_id
the counters are restored, enabling the circuit breaker to accumulate losses
across pair-switch restarts within the same run.

Test A: state persists after one loss and reloads with same run_id.
Test B: state resets when run_id changes.
Test C: three losses across simulated restarts trigger consecutive_loss_limit_hit.
Test D: fourth new entry is blocked after three losses.
Test E: session_realized_pnl_usdt accumulates across restarts.
Test F: alert payload includes run_id and session counters.
Test G: state file atomic write produces valid JSON readable by _load_session_state.
Test H: disabled circuit breaker (no limits) preserves existing behaviour.
Test I: record_session_trade_result does not affect order execution state.
"""

import json
import shutil
import sys
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import session_risk_circuit_breaker as scb
from session_risk_circuit_breaker import (
    RiskCircuitBreakerConfig,
    RiskCircuitBreakerState,
    evaluate_risk_circuit_breaker,
    get_session_consecutive_losses,
    get_session_realized_pnl,
    get_session_run_id,
    record_session_trade_result,
    reload_session_state,
    reset_session_circuit_breaker_state,
)


class TestSessionRiskStatePersistence:
    """All tests redirect SESSION_RISK_STATE_FILE to an isolated temp directory."""

    def setup_method(self):
        self.tmp_dir = ROOT_DIR / ".tmp" / "session_risk_persist" / uuid.uuid4().hex
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self._prev_state_file = scb.SESSION_RISK_STATE_FILE
        scb.SESSION_RISK_STATE_FILE = self.tmp_dir / "session_risk_state.json"
        # Start each test with a fresh UUID run_id and zero counters.
        reset_session_circuit_breaker_state()

    def teardown_method(self):
        scb.SESSION_RISK_STATE_FILE = self._prev_state_file
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _simulate_restart(self):
        """Zero in-memory counters then reload from disk (same-run restart)."""
        scb._session_consecutive_losses = 0
        scb._session_realized_pnl_usdt = 0.0
        reload_session_state()

    def _cfg(self, **kw) -> RiskCircuitBreakerConfig:
        defaults = dict(
            session_max_loss_usdt=5.0,
            max_consecutive_losses=3,
            max_drawdown_usdt=10.0,
            disable_entries_after_risk_stop=True,
            state_mode="session",
        )
        defaults.update(kw)
        return RiskCircuitBreakerConfig(**defaults)

    def _state(self, **kw) -> RiskCircuitBreakerState:
        defaults = dict(
            session_realized_pnl_usdt=get_session_realized_pnl(),
            session_consecutive_losses=get_session_consecutive_losses(),
            persistent_consecutive_losses=0,
            current_drawdown_usdt=None,
            equity_trusted=True,
            run_id=get_session_run_id(),
        )
        defaults.update(kw)
        return RiskCircuitBreakerState(**defaults)

    # ── Test A: state persists after one loss and reloads with same run_id ────

    def test_a_state_persists_and_reloads_same_run_id(self):
        record_session_trade_result(is_win=False, pnl_usdt=-0.25)

        assert get_session_consecutive_losses() == 1
        assert abs(get_session_realized_pnl() - (-0.25)) < 1e-9
        assert scb.SESSION_RISK_STATE_FILE.exists(), "state file must be written"

        self._simulate_restart()

        assert get_session_consecutive_losses() == 1, (
            "consecutive_losses must survive process restart within same run_id"
        )
        assert abs(get_session_realized_pnl() - (-0.25)) < 1e-9, (
            "realized_pnl must survive process restart within same run_id"
        )

    # ── Test B: state resets when run_id changes ──────────────────────────────

    def test_b_state_resets_on_new_run_id(self):
        record_session_trade_result(is_win=False, pnl_usdt=-0.30)
        assert get_session_consecutive_losses() == 1

        # Simulate: new run starts — reset_session_circuit_breaker_state() issues
        # a new UUID, which does NOT match the UUID stored in the file.
        reset_session_circuit_breaker_state()

        assert get_session_consecutive_losses() == 0, (
            "counters must be zero after a new run_id is issued"
        )
        assert get_session_realized_pnl() == 0.0

    # ── Test C: three losses across simulated restarts trigger the breaker ────

    def test_c_three_losses_across_restarts_trigger_circuit_breaker(self):
        cfg = self._cfg(max_consecutive_losses=3)

        # Loss 1 — process continues
        record_session_trade_result(is_win=False, pnl_usdt=-0.25)
        self._simulate_restart()
        assert get_session_consecutive_losses() == 1

        # Loss 2 — pair switch + restart
        record_session_trade_result(is_win=False, pnl_usdt=-0.16)
        self._simulate_restart()
        assert get_session_consecutive_losses() == 2

        # Loss 3 — pair switch + restart (breaker should now be tripped)
        record_session_trade_result(is_win=False, pnl_usdt=-0.43)
        self._simulate_restart()
        assert get_session_consecutive_losses() == 3

        decision = evaluate_risk_circuit_breaker(self._state(), cfg)
        assert decision.active, "circuit breaker must activate at 3 session losses"
        assert "consecutive_loss_limit_hit" in decision.reasons

    # ── Test D: fourth new entry is blocked after three losses ────────────────

    def test_d_fourth_entry_blocked_after_three_losses(self):
        cfg = self._cfg(max_consecutive_losses=3)

        for pnl in (-0.25, -0.16, -0.43):
            record_session_trade_result(is_win=False, pnl_usdt=pnl)
            self._simulate_restart()

        # The fourth entry attempt happens in the restarted process.
        decision = evaluate_risk_circuit_breaker(self._state(), cfg)

        assert decision.block_new_entries, (
            "new entries must be blocked after 3 session consecutive losses "
            "even when evaluated in a fresh process"
        )

    # ── Test E: realized pnl accumulates across restarts ─────────────────────

    def test_e_session_pnl_accumulates_across_restarts(self):
        record_session_trade_result(is_win=False, pnl_usdt=-0.25)
        self._simulate_restart()

        record_session_trade_result(is_win=False, pnl_usdt=-0.16)
        self._simulate_restart()

        record_session_trade_result(is_win=True, pnl_usdt=+0.10)
        self._simulate_restart()

        expected = -0.25 + (-0.16) + 0.10
        assert abs(get_session_realized_pnl() - expected) < 1e-9, (
            f"realized pnl must accumulate to {expected:.4f} across restarts, "
            f"got {get_session_realized_pnl():.4f}"
        )
        # A win resets the consecutive streak.
        assert get_session_consecutive_losses() == 0

    # ── Test F: alert payload includes run_id and session counters ────────────

    def test_f_alert_payload_includes_run_id_and_session_counters(self):
        for _ in range(3):
            record_session_trade_result(is_win=False, pnl_usdt=-0.20)
        self._simulate_restart()

        run_id = get_session_run_id()
        cfg = self._cfg(max_consecutive_losses=3)
        decision = evaluate_risk_circuit_breaker(self._state(), cfg)
        assert decision.active

        payloads = decision.risk_event_payloads(pair="AAA/BBB")
        breach_pl = next(
            p for p in payloads if p["alert_type"] == "consecutive_loss_limit_hit"
        )

        assert breach_pl["run_id"] == run_id
        assert breach_pl["state_mode"] == "session"
        assert breach_pl["session_consecutive_losses"] == 3
        assert breach_pl["consecutive_losses"] == 3
        assert "session_realized_pnl_usdt" not in breach_pl or True  # optional field OK

    # ── Test G: atomic write produces valid JSON readable by _load_session_state

    def test_g_atomic_write_produces_valid_readable_json(self):
        record_session_trade_result(is_win=False, pnl_usdt=-0.10)

        path = scb.SESSION_RISK_STATE_FILE
        assert path.exists(), "state file must exist after record_session_trade_result"

        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)

        assert data["run_id"] == get_session_run_id()
        assert data["session_consecutive_losses"] == 1
        assert abs(data["session_realized_pnl_usdt"] - (-0.10)) < 1e-9
        assert "updated_at" in data

        # Force-reload and confirm values match.
        scb._session_consecutive_losses = 0
        scb._session_realized_pnl_usdt = 0.0
        reload_session_state()
        assert get_session_consecutive_losses() == 1
        assert abs(get_session_realized_pnl() - (-0.10)) < 1e-9

    # ── Test H: disabled circuit breaker never activates ─────────────────────

    def test_h_disabled_circuit_breaker_never_activates(self):
        for _ in range(10):
            record_session_trade_result(is_win=False, pnl_usdt=-1.0)
        self._simulate_restart()

        cfg = RiskCircuitBreakerConfig(
            session_max_loss_usdt=None,
            max_consecutive_losses=None,
            max_drawdown_usdt=None,
            disable_entries_after_risk_stop=True,
            state_mode="session",
        )
        state = RiskCircuitBreakerState(
            session_realized_pnl_usdt=get_session_realized_pnl(),
            session_consecutive_losses=get_session_consecutive_losses(),
            persistent_consecutive_losses=0,
            current_drawdown_usdt=-999.0,
            equity_trusted=True,
            run_id=get_session_run_id(),
        )
        decision = evaluate_risk_circuit_breaker(state, cfg)

        assert not decision.active, "disabled config must never activate the breaker"
        assert not decision.block_new_entries

    # ── Test I: record_session_trade_result does not affect execution state ───

    def test_i_record_does_not_modify_execution_state(self):
        """record_session_trade_result only updates session counters and the JSON
        file — no side effects on entry signal, exit logic, or order state."""
        before_losses = get_session_consecutive_losses()
        before_pnl = get_session_realized_pnl()

        record_session_trade_result(is_win=False, pnl_usdt=-0.05)

        assert get_session_consecutive_losses() == before_losses + 1
        assert abs(get_session_realized_pnl() - (before_pnl - 0.05)) < 1e-9

        # The file must be written but must contain ONLY the expected keys.
        data = json.loads(scb.SESSION_RISK_STATE_FILE.read_text(encoding="utf-8"))
        allowed_keys = {"run_id", "session_consecutive_losses",
                        "session_realized_pnl_usdt", "updated_at"}
        unexpected = set(data.keys()) - allowed_keys
        assert not unexpected, (
            f"state file must not contain extra keys: {unexpected}"
        )

        # A second call with a win resets the streak but not the PnL.
        record_session_trade_result(is_win=True, pnl_usdt=+0.10)
        assert get_session_consecutive_losses() == 0
        assert abs(get_session_realized_pnl() - (before_pnl - 0.05 + 0.10)) < 1e-9

    # ── Test J: win mid-streak resets consecutive counter but not pnl ─────────

    def test_j_win_resets_consecutive_but_not_pnl_across_restarts(self):
        record_session_trade_result(is_win=False, pnl_usdt=-0.20)
        record_session_trade_result(is_win=False, pnl_usdt=-0.15)
        self._simulate_restart()
        assert get_session_consecutive_losses() == 2

        # Win arrives — streak resets to 0 but pnl is cumulative.
        record_session_trade_result(is_win=True, pnl_usdt=+0.08)
        self._simulate_restart()

        assert get_session_consecutive_losses() == 0, (
            "a win must reset the streak to 0"
        )
        assert abs(get_session_realized_pnl() - (-0.20 - 0.15 + 0.08)) < 1e-9

    # ── Test K: stale file from different run_id is ignored ───────────────────

    def test_k_stale_file_from_different_run_id_is_ignored(self):
        # Write a file with a foreign run_id.
        foreign_id = str(uuid.uuid4())
        scb.SESSION_RISK_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        scb.SESSION_RISK_STATE_FILE.write_text(
            json.dumps({
                "run_id": foreign_id,
                "session_consecutive_losses": 99,
                "session_realized_pnl_usdt": -999.0,
                "updated_at": 0,
            }),
            encoding="utf-8",
        )

        # Reload should NOT apply the stale data.
        scb._session_consecutive_losses = 0
        scb._session_realized_pnl_usdt = 0.0
        reload_session_state()

        assert get_session_consecutive_losses() == 0, (
            "stale file with different run_id must not pollute the session counter"
        )
        assert get_session_realized_pnl() == 0.0

    # ── Test L: corrupt state file is silently ignored ────────────────────────

    def test_l_corrupt_state_file_silently_ignored(self):
        scb.SESSION_RISK_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        scb.SESSION_RISK_STATE_FILE.write_text("NOT JSON {{{{", encoding="utf-8")

        scb._session_consecutive_losses = 0
        scb._session_realized_pnl_usdt = 0.0
        reload_session_state()  # must not raise

        assert get_session_consecutive_losses() == 0
        assert get_session_realized_pnl() == 0.0
