from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# In-memory session state — resets automatically on each new process (run).
# In "session" mode the circuit breaker uses these counters; in "persistent"
# mode it reads from pair_strategy_state.json via get_consecutive_losses().
# ──────────────────────────────────────────────────────────────────────────────

_session_run_id: str = str(uuid.uuid4())
_session_consecutive_losses: int = 0
_session_realized_pnl_usdt: float = 0.0


def reset_session_circuit_breaker_state() -> None:
    """Reset all session-local counters and issue a new run ID.

    Called automatically on process start (module load gives zero state).
    Exposed for tests — do not call from production trade logic.
    """
    global _session_run_id, _session_consecutive_losses, _session_realized_pnl_usdt
    _session_run_id = str(uuid.uuid4())
    _session_consecutive_losses = 0
    _session_realized_pnl_usdt = 0.0


def record_session_trade_result(is_win: bool, pnl_usdt: float = 0.0) -> None:
    """Record a closed trade in session-local state.

    Call this alongside record_trade_result() in func_pair_state so both
    the persistent pair-blacklist counter and the session circuit breaker
    counter stay in sync.
    """
    global _session_consecutive_losses, _session_realized_pnl_usdt
    if is_win:
        _session_consecutive_losses = 0
    else:
        _session_consecutive_losses += 1
    _session_realized_pnl_usdt += float(pnl_usdt)


def get_session_consecutive_losses() -> int:
    return _session_consecutive_losses


def get_session_realized_pnl() -> float:
    return _session_realized_pnl_usdt


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
    # "session"    — counters reset on each process start (new run); default.
    # "persistent" — counters accumulate across restarts via pair_strategy_state.json.
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
    # In-memory consecutive-loss counter — resets to 0 on process start.
    session_consecutive_losses: int | None = None
    # Persistent counter from pair_strategy_state.json — survives restarts.
    persistent_consecutive_losses: int | None = None
    # Equity-based drawdown for the drawdown rule (can be None if equity untrusted).
    current_drawdown_usdt: float | None = None
    equity_trusted: bool = True
    # Run UUID assigned at process start; included in breach payloads.
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
    # In "session" mode use the in-memory counter (resets with each new run).
    # In "persistent" mode use the counter read from pair_strategy_state.json.
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
