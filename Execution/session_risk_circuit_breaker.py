from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


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


@dataclass(frozen=True)
class RiskCircuitBreakerConfig:
    session_max_loss_usdt: float | None = None
    max_consecutive_losses: int | None = None
    max_drawdown_usdt: float | None = None
    disable_entries_after_risk_stop: bool = True

    @classmethod
    def from_env(cls) -> "RiskCircuitBreakerConfig":
        return cls(
            session_max_loss_usdt=_env_float_limit("STATBOT_SESSION_MAX_LOSS_USDT"),
            max_consecutive_losses=_env_int_limit("STATBOT_MAX_CONSECUTIVE_LOSSES"),
            max_drawdown_usdt=_env_float_limit("STATBOT_MAX_DRAWDOWN_USDT"),
            disable_entries_after_risk_stop=_env_flag(
                "STATBOT_DISABLE_ENTRIES_AFTER_RISK_STOP",
                True,
            ),
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
        }


@dataclass(frozen=True)
class RiskCircuitBreakerState:
    session_realized_pnl_usdt: float | None = None
    consecutive_losses: int | None = None
    current_drawdown_usdt: float | None = None
    equity_trusted: bool = True


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


def evaluate_risk_circuit_breaker(
    state: RiskCircuitBreakerState,
    config: RiskCircuitBreakerConfig,
) -> RiskCircuitBreakerDecision:
    breaches: list[RiskCircuitBreakerBreach] = []

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
                        "session_realized_pnl_usdt": session_pnl,
                        "session_max_loss_usdt": limit,
                    },
                )
            )

    consecutive_losses = _int_or_none(state.consecutive_losses)
    if config.max_consecutive_losses is not None and consecutive_losses is not None:
        limit = int(config.max_consecutive_losses)
        if consecutive_losses >= limit:
            breaches.append(
                RiskCircuitBreakerBreach(
                    reason="consecutive_loss_limit_hit",
                    entry_block_reason="entries_blocked_by_consecutive_losses",
                    message=(
                        f"Consecutive losses {consecutive_losses} reached "
                        f"limit {limit}."
                    ),
                    severity="error",
                    metadata={
                        "consecutive_losses": consecutive_losses,
                        "max_consecutive_losses": limit,
                    },
                )
            )

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
                        "current_drawdown_usdt": drawdown,
                        "max_drawdown_usdt": limit,
                    },
                )
            )

    active = bool(breaches)
    return RiskCircuitBreakerDecision(
        active=active,
        block_new_entries=active and bool(config.disable_entries_after_risk_stop),
        breaches=tuple(breaches),
    )
