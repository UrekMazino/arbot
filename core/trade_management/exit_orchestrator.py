"""Unified ranked exit decision layer.

The orchestrator is intentionally small: existing systems produce candidates,
then this layer decides which one is allowed to drive execution. Catastrophic
exits stay above every soft/quality decision, and the net-profit guard only
blocks candidates explicitly marked as soft profit exits.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from core.ev.hold_exit_ev import ExitAction


class ExitCandidateCategory(str, Enum):
    HARD = "hard"
    QUALITY = "quality"
    PROFIT_RISK = "profit_risk"
    ADVANCED_ML = "advanced_ml"


_CATEGORY_RANK = {
    ExitCandidateCategory.HARD: 4000,
    ExitCandidateCategory.QUALITY: 3000,
    ExitCandidateCategory.PROFIT_RISK: 2000,
    ExitCandidateCategory.ADVANCED_ML: 1000,
}


@dataclass(frozen=True)
class ExitCandidate:
    name: str
    category: ExitCandidateCategory
    action: ExitAction
    reason: str
    priority: int = 0
    exit_percentage: float = 1.0
    severity: float = 0.0
    net_profit_guard_applies: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def rank(self) -> tuple[int, int, float, str]:
        return (
            _CATEGORY_RANK[self.category],
            int(self.priority),
            _finite_float(self.severity, 0.0),
            str(self.name),
        )


@dataclass(frozen=True)
class NetProfitGuardContext:
    enabled: bool
    current_pnl_usdt: float | None
    min_profit_usdt: float = 0.0
    estimated_exit_cost_usdt: float = 0.0
    block_when_pnl_unknown: bool = True

    @property
    def required_profit_usdt(self) -> float:
        return max(
            _finite_float(self.min_profit_usdt, 0.0),
            _finite_float(self.estimated_exit_cost_usdt, 0.0),
            0.0,
        )


@dataclass(frozen=True)
class BlockedExitCandidate:
    candidate: ExitCandidate
    reason: str


@dataclass(frozen=True)
class OrchestratedExitDecision:
    action: ExitAction
    reason: str
    selected_candidate: ExitCandidate | None
    exit_percentage: float
    hard_exit: bool
    blocked_by_net_profit_guard: bool
    candidates: tuple[ExitCandidate, ...]
    blocked_candidates: tuple[BlockedExitCandidate, ...]

    @property
    def should_exit(self) -> bool:
        return self.action in (ExitAction.PARTIAL_EXIT, ExitAction.FULL_EXIT)


class ExitOrchestrator:
    """Rank exit candidates and return one final execution decision."""

    def decide(
        self,
        candidates: Iterable[ExitCandidate],
        *,
        net_profit_guard: NetProfitGuardContext | None = None,
    ) -> OrchestratedExitDecision:
        sorted_candidates = tuple(
            sorted(
                (candidate for candidate in candidates if candidate.action != ExitAction.HOLD),
                key=lambda candidate: candidate.rank,
                reverse=True,
            )
        )
        blocked: list[BlockedExitCandidate] = []
        for candidate in sorted_candidates:
            block_reason = self._net_profit_guard_block_reason(candidate, net_profit_guard)
            if block_reason:
                blocked.append(BlockedExitCandidate(candidate=candidate, reason=block_reason))
                continue
            return OrchestratedExitDecision(
                action=candidate.action,
                reason=candidate.reason,
                selected_candidate=candidate,
                exit_percentage=max(0.0, min(float(candidate.exit_percentage), 1.0)),
                hard_exit=candidate.category == ExitCandidateCategory.HARD,
                blocked_by_net_profit_guard=bool(blocked),
                candidates=sorted_candidates,
                blocked_candidates=tuple(blocked),
            )

        reason = (
            "net profit guard blocked all soft exit candidates"
            if blocked and len(blocked) == len(sorted_candidates)
            else "no exit candidates"
        )
        return OrchestratedExitDecision(
            action=ExitAction.HOLD,
            reason=reason,
            selected_candidate=None,
            exit_percentage=0.0,
            hard_exit=False,
            blocked_by_net_profit_guard=bool(blocked),
            candidates=sorted_candidates,
            blocked_candidates=tuple(blocked),
        )

    def _net_profit_guard_block_reason(
        self,
        candidate: ExitCandidate,
        guard: NetProfitGuardContext | None,
    ) -> str | None:
        if guard is None or not guard.enabled:
            return None
        if candidate.category == ExitCandidateCategory.HARD:
            return None
        if not candidate.net_profit_guard_applies:
            return None
        if candidate.action not in (ExitAction.PARTIAL_EXIT, ExitAction.FULL_EXIT):
            return None

        current_pnl = _finite_float(guard.current_pnl_usdt, None)
        required = guard.required_profit_usdt
        if current_pnl is None:
            if guard.block_when_pnl_unknown:
                return f"net profit unknown; required >= {required:.4f} USDT"
            return None
        if current_pnl < required:
            return f"net profit {current_pnl:.4f} < required {required:.4f} USDT"
        return None


def _finite_float(value: Any, default: float | None) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


__all__ = [
    "BlockedExitCandidate",
    "ExitCandidate",
    "ExitCandidateCategory",
    "ExitOrchestrator",
    "NetProfitGuardContext",
    "OrchestratedExitDecision",
]
