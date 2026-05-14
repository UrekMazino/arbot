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
    full_tp_guard_multiplier: float = 1.0
    partial_tp_guard_multiplier: float = 1.0
    trailing_stop_guard_multiplier: float = 1.0

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
    base_min_profit_usdt: float = 0.0
    effective_min_profit_usdt: float = 0.0
    guard_multiplier: float = 1.0
    current_pnl_usdt: float | None = None


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
            blocked_candidate = self._net_profit_guard_block(candidate, net_profit_guard)
            if blocked_candidate is not None:
                blocked.append(blocked_candidate)
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

    def _net_profit_guard_block(
        self,
        candidate: ExitCandidate,
        guard: NetProfitGuardContext | None,
    ) -> BlockedExitCandidate | None:
        if guard is None or not guard.enabled:
            return None
        if candidate.category == ExitCandidateCategory.HARD:
            return None
        if not candidate.net_profit_guard_applies:
            return None
        if candidate.action not in (ExitAction.PARTIAL_EXIT, ExitAction.FULL_EXIT):
            return None

        current_pnl = _finite_float(guard.current_pnl_usdt, None)
        base_required, effective_required, multiplier = _candidate_guard_threshold(candidate, guard)
        if current_pnl is None:
            if guard.block_when_pnl_unknown:
                return BlockedExitCandidate(
                    candidate=candidate,
                    reason=f"net profit unknown; required >= {effective_required:.4f} USDT",
                    base_min_profit_usdt=base_required,
                    effective_min_profit_usdt=effective_required,
                    guard_multiplier=multiplier,
                    current_pnl_usdt=current_pnl,
                )
            return None
        if current_pnl < effective_required:
            return BlockedExitCandidate(
                candidate=candidate,
                reason=(
                    f"net profit {current_pnl:.4f} < required {effective_required:.4f} USDT "
                    f"(base={base_required:.4f}, multiplier={multiplier:.3f})"
                ),
                base_min_profit_usdt=base_required,
                effective_min_profit_usdt=effective_required,
                guard_multiplier=multiplier,
                current_pnl_usdt=current_pnl,
            )
        return None


def _finite_float(value: Any, default: float | None) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _candidate_guard_threshold(
    candidate: ExitCandidate,
    guard: NetProfitGuardContext,
) -> tuple[float, float, float]:
    metadata = candidate.metadata if isinstance(candidate.metadata, dict) else {}
    base_required = _finite_float(metadata.get("base_min_profit_usdt"), None)
    if base_required is None:
        base_required = guard.required_profit_usdt
    base_required = max(base_required, 0.0)

    metadata_multiplier = _finite_float(metadata.get("guard_multiplier"), None)
    if metadata_multiplier is None or metadata_multiplier < 0:
        metadata_multiplier = _candidate_guard_multiplier(candidate, guard)

    metadata_effective = _finite_float(metadata.get("effective_min_profit_usdt"), None)
    if metadata_effective is None:
        metadata_effective = base_required * metadata_multiplier
    metadata_effective = max(metadata_effective, 0.0)
    return base_required, metadata_effective, metadata_multiplier


def _candidate_guard_multiplier(candidate: ExitCandidate, guard: NetProfitGuardContext) -> float:
    reason_code = ""
    if isinstance(candidate.metadata, dict):
        reason_code = str(candidate.metadata.get("reason_code") or "").strip().lower()
    name = str(candidate.name or "").strip().lower()
    if reason_code == "take_profit" or name in {"trade_manager_take_profit", "take_profit"}:
        return _positive_multiplier(guard.full_tp_guard_multiplier)
    if reason_code == "partial_profit" or name in {"trade_manager_partial_profit", "partial_profit"}:
        return _positive_multiplier(guard.partial_tp_guard_multiplier)
    if reason_code == "trailing_stop" or name in {"trade_manager_trailing_stop", "trailing_stop"}:
        return _positive_multiplier(guard.trailing_stop_guard_multiplier)
    return 1.0


def _positive_multiplier(value: Any) -> float:
    parsed = _finite_float(value, 1.0)
    if parsed is None or parsed < 0:
        return 1.0
    return parsed


__all__ = [
    "BlockedExitCandidate",
    "ExitCandidate",
    "ExitCandidateCategory",
    "ExitOrchestrator",
    "NetProfitGuardContext",
    "OrchestratedExitDecision",
]
