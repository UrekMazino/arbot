from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Session state persistence
#
# The subprocess manager sets STATBOT_RUN_ID before launching the bot and
# preserves it across pair-switch restarts (sys.exit(3)).  We use that env var
# as the persistence key so that a restarted process can detect it is the same
# run and reload the session counters from disk instead of starting from zero.
#
# Tests redirect SESSION_RISK_STATE_FILE to a temp path via setup_module /
# setup_method before any getter or setter is called.
# ──────────────────────────────────────────────────────────────────────────────

SESSION_RISK_STATE_FILE: Path = (
    Path(__file__).resolve().parent / "state" / "session_risk_state.json"
)


def _stable_run_id() -> str:
    """Return a run_id that is stable across pair-switch process restarts.

    Uses STATBOT_RUN_ID set by the subprocess manager.  Falls back to a fresh
    UUID when the env var is absent (local dev, tests).
    """
    env = os.getenv("STATBOT_RUN_ID", "").strip()
    return env if env else str(uuid.uuid4())


# ──────────────────────────────────────────────────────────────────────────────
# In-memory session state.
# Values are initialised to zero and then potentially overwritten by
# _load_session_state() immediately below.
# ──────────────────────────────────────────────────────────────────────────────

_session_run_id: str = _stable_run_id()
_session_consecutive_losses: int = 0
_session_realized_pnl_usdt: float = 0.0
_session_trades_count: int = 0


# ──────────────────────────────────────────────────────────────────────────────
# Disk I/O helpers
# ──────────────────────────────────────────────────────────────────────────────

def _load_session_state() -> None:
    """Read persisted counters from SESSION_RISK_STATE_FILE if run_id matches.

    Called automatically at module import and via reload_session_state() in
    tests.  All errors are silently swallowed — a missing or corrupt file just
    means we start from zero, which is always safe.
    """
    global _session_consecutive_losses, _session_realized_pnl_usdt, _session_trades_count
    try:
        path = SESSION_RISK_STATE_FILE
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("run_id") != _session_run_id:
            _log.warning(
                "session_risk_state_reset run_id_changed old=%s new=%s",
                data.get("run_id"),
                _session_run_id,
            )
            return  # different run → do not inherit state
        _session_consecutive_losses = int(data.get("session_consecutive_losses", 0))
        _session_realized_pnl_usdt = float(data.get("session_realized_pnl_usdt", 0.0))
        _session_trades_count = int(data.get("session_trades_count", 0))
        _log.info(
            "session_risk_state_loaded run_id=%s session_consecutive_losses=%d session_realized_pnl_usdt=%.4f session_trades_count=%d",
            _session_run_id,
            _session_consecutive_losses,
            _session_realized_pnl_usdt,
            _session_trades_count,
        )
    except Exception:  # noqa: BLE001
        pass


def _save_session_state() -> None:
    """Persist current counters to SESSION_RISK_STATE_FILE atomically.

    Uses write-to-tmp-then-rename so a crash mid-write never leaves a corrupt
    file.  Errors are swallowed: the circuit breaker always functions from its
    in-memory state even if the disk write fails.
    """
    path = SESSION_RISK_STATE_FILE
    payload = json.dumps(
        {
            "run_id": _session_run_id,
            "session_consecutive_losses": _session_consecutive_losses,
            "session_realized_pnl_usdt": _session_realized_pnl_usdt,
            "session_trades_count": _session_trades_count,
            "updated_at": time.time(),
        }
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=".scb_tmp_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp_path, str(path))
        except Exception:  # noqa: BLE001
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception:  # noqa: BLE001
        pass  # best-effort; in-memory state is still authoritative


# Load persisted state immediately when the module is first imported.
# In production the process start triggers this, restoring counters from the
# previous pair-switch restart if the run_id matches.
_load_session_state()


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def reset_session_circuit_breaker_state() -> None:
    """Reset all session-local counters and issue a new run ID.

    Generates a fresh UUID run_id so the new session does not inherit any
    persisted state from a prior run.  Removes the state file at the current
    SESSION_RISK_STATE_FILE path so that a subsequent reload does not restore
    stale values.

    Exposed for tests — do not call from production trade logic.
    """
    global _session_run_id, _session_consecutive_losses, _session_realized_pnl_usdt, _session_trades_count
    _session_run_id = str(uuid.uuid4())
    _session_consecutive_losses = 0
    _session_realized_pnl_usdt = 0.0
    _session_trades_count = 0
    try:
        if SESSION_RISK_STATE_FILE.exists():
            SESSION_RISK_STATE_FILE.unlink()
    except OSError:
        pass


def reload_session_state() -> None:
    """Re-read persisted state from SESSION_RISK_STATE_FILE.

    Exposed for tests to simulate a pair-switch process restart: after zeroing
    the in-memory counters, calling this function restores them from disk the
    same way a fresh module import would.
    """
    _load_session_state()


def record_session_trade_result(is_win: bool, pnl_usdt: float = 0.0) -> None:
    """Record a closed trade result in session state and persist to disk.

    Call this alongside record_trade_result() in func_pair_state so both the
    persistent pair-blacklist counter and the session circuit breaker counter
    stay in sync.  The disk write is atomic so a concurrent restart cannot read
    a half-written file.
    """
    global _session_consecutive_losses, _session_realized_pnl_usdt, _session_trades_count
    if is_win:
        _session_consecutive_losses = 0
    else:
        _session_consecutive_losses += 1
    _session_realized_pnl_usdt += float(pnl_usdt)
    _session_trades_count += 1
    _save_session_state()


def get_session_consecutive_losses() -> int:
    return _session_consecutive_losses


def get_session_realized_pnl() -> float:
    return _session_realized_pnl_usdt


def get_session_trades_count() -> int:
    return _session_trades_count


def get_session_run_id() -> str:
    return _session_run_id


# ──────────────────────────────────────────────────────────────────────────────
# Env helpers
# ──────────────────────────────────────────────────────────────────────────────

def _env_float_limit(name: str) -> float | None:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = abs(float(raw))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _env_int_limit(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RiskCircuitBreakerConfig:
    session_max_loss_usdt: float | None = None
    max_consecutive_losses: int | None = None
    max_drawdown_usdt: float | None = None
    disable_entries_after_risk_stop: bool = True
    # "session"    — counters persist across pair-switch restarts within the
    #                same run_id; reset at the start of a new run.
    # "persistent" — counters accumulate across runs via pair_strategy_state.json.
    state_mode: str = "session"

    @classmethod
    def from_env(cls) -> "RiskCircuitBreakerConfig":
        mode_raw = (
            os.getenv("STATBOT_RISK_CIRCUIT_BREAKER_STATE_MODE") or "session"
        ).strip().lower()
        state_mode = mode_raw if mode_raw in {"session", "persistent"} else "session"
        return cls(
            session_max_loss_usdt=_env_float_limit("STATBOT_SESSION_MAX_LOSS_USDT"),
            max_consecutive_losses=_env_int_limit("STATBOT_MAX_CONSECUTIVE_LOSSES"),
            max_drawdown_usdt=_env_float_limit("STATBOT_MAX_DRAWDOWN_USDT"),
            disable_entries_after_risk_stop=_env_flag(
                "STATBOT_DISABLE_ENTRIES_AFTER_RISK_STOP",
                True,
            ),
            state_mode=state_mode,
        )

    def any_limit_enabled(self) -> bool:
        return (
            self.session_max_loss_usdt is not None
            or self.max_consecutive_losses is not None
            or self.max_drawdown_usdt is not None
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_max_loss_usdt": self.session_max_loss_usdt,
            "max_consecutive_losses": self.max_consecutive_losses,
            "max_drawdown_usdt": self.max_drawdown_usdt,
            "disable_entries_after_risk_stop": self.disable_entries_after_risk_stop,
            "state_mode": self.state_mode,
        }


# ──────────────────────────────────────────────────────────────────────────────
# State
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RiskCircuitBreakerState:
    # Realized PnL accumulated from closed trades this session (in-memory sum).
    session_realized_pnl_usdt: float | None = None
    # In-memory consecutive-loss counter — persisted across pair-switch restarts
    # but resets to 0 when a new run_id is issued.
    session_consecutive_losses: int | None = None
    # Persistent counter from pair_strategy_state.json — survives across runs.
    persistent_consecutive_losses: int | None = None
    # Equity-based drawdown for the drawdown rule (can be None if equity untrusted).
    current_drawdown_usdt: float | None = None
    equity_trusted: bool = True
    # Run UUID included in breach payloads.
    run_id: str | None = None


# ──────────────────────────────────────────────────────────────────────────────
# Breach / Decision
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RiskCircuitBreakerBreach:
    reason: str
    entry_block_reason: str
    message: str
    severity: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class RiskCircuitBreakerDecision:
    active: bool
    block_new_entries: bool
    breaches: tuple[RiskCircuitBreakerBreach, ...] = ()

    @property
    def reasons(self) -> tuple[str, ...]:
        return tuple(breach.reason for breach in self.breaches)

    @property
    def entry_block_reasons(self) -> tuple[str, ...]:
        return tuple(breach.entry_block_reason for breach in self.breaches)

    def risk_event_payloads(self, pair: str | None = None) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for breach in self.breaches:
            payloads.append(
                {
                    "alert_type": breach.reason,
                    "entry_block_reason": breach.entry_block_reason,
                    "message": breach.message,
                    "pair": pair,
                    "action": "block_new_entries" if self.block_new_entries else "observe_only",
                    "block_new_entries": self.block_new_entries,
                    "severity": breach.severity,
                    **breach.metadata,
                }
            )
        return payloads


# ──────────────────────────────────────────────────────────────────────────────
# Evaluator
# ──────────────────────────────────────────────────────────────────────────────

def evaluate_risk_circuit_breaker(
    state: RiskCircuitBreakerState,
    config: RiskCircuitBreakerConfig,
) -> RiskCircuitBreakerDecision:
    breaches: list[RiskCircuitBreakerBreach] = []

    # --- Session loss limit ---
    session_pnl = _float_or_none(state.session_realized_pnl_usdt)
    if config.session_max_loss_usdt is not None and session_pnl is not None:
        limit = abs(float(config.session_max_loss_usdt))
        if session_pnl <= -limit:
            breaches.append(
                RiskCircuitBreakerBreach(
                    reason="session_loss_limit_hit",
                    entry_block_reason="entries_blocked_by_session_loss",
                    message=(
                        f"Session realized PnL {session_pnl:.2f} USDT reached "
                        f"loss limit {-limit:.2f} USDT."
                    ),
                    severity="critical",
                    metadata={
                        "state_mode": config.state_mode,
                        "session_realized_pnl_usdt": session_pnl,
                        "session_max_loss_usdt": limit,
                        "run_id": state.run_id,
                    },
                )
            )

    # --- Consecutive losses ---
    # In "session" mode use the persisted-then-reloaded session counter.
    # In "persistent" mode use the counter from pair_strategy_state.json.
    if config.state_mode == "persistent":
        effective_losses = _int_or_none(state.persistent_consecutive_losses)
        losses_source = "persistent"
    else:
        effective_losses = _int_or_none(state.session_consecutive_losses)
        losses_source = "session"

    if config.max_consecutive_losses is not None and effective_losses is not None:
        limit = int(config.max_consecutive_losses)
        if effective_losses >= limit:
            breaches.append(
                RiskCircuitBreakerBreach(
                    reason="consecutive_loss_limit_hit",
                    entry_block_reason="entries_blocked_by_consecutive_losses",
                    message=(
                        f"Consecutive losses {effective_losses} reached "
                        f"limit {limit} ({losses_source} counter)."
                    ),
                    severity="error",
                    metadata={
                        "state_mode": losses_source,
                        "session_consecutive_losses": _int_or_none(
                            state.session_consecutive_losses
                        ),
                        "persistent_consecutive_losses": _int_or_none(
                            state.persistent_consecutive_losses
                        ),
                        # "consecutive_losses" is the active counter for backward-compat readers.
                        "consecutive_losses": effective_losses,
                        "max_consecutive_losses": limit,
                        "run_id": state.run_id,
                    },
                )
            )

    # --- Drawdown ---
    drawdown = _float_or_none(state.current_drawdown_usdt)
    if config.max_drawdown_usdt is not None and drawdown is not None:
        limit = abs(float(config.max_drawdown_usdt))
        if drawdown <= -limit:
            breaches.append(
                RiskCircuitBreakerBreach(
                    reason="drawdown_limit_hit",
                    entry_block_reason="entries_blocked_by_drawdown",
                    message=(
                        f"Current drawdown {drawdown:.2f} USDT reached "
                        f"drawdown limit {-limit:.2f} USDT."
                    ),
                    severity="critical",
                    metadata={
                        "state_mode": config.state_mode,
                        "current_drawdown_usdt": drawdown,
                        "max_drawdown_usdt": limit,
                        "run_id": state.run_id,
                    },
                )
            )

    active = bool(breaches)
    return RiskCircuitBreakerDecision(
        active=active,
        block_new_entries=active and bool(config.disable_entries_after_risk_stop),
        breaches=tuple(breaches),
    )
