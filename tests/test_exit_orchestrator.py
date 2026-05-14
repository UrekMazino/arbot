from __future__ import annotations

import pytest

from core.ev.hold_exit_ev import ExitAction
from core.trade_management.exit_orchestrator import (
    ExitCandidate,
    ExitCandidateCategory,
    ExitOrchestrator,
    NetProfitGuardContext,
)


def _candidate(
    name: str,
    category: ExitCandidateCategory,
    *,
    action: ExitAction = ExitAction.FULL_EXIT,
    priority: int = 0,
    guard: bool = False,
    metadata: dict | None = None,
) -> ExitCandidate:
    return ExitCandidate(
        name=name,
        category=category,
        action=action,
        priority=priority,
        reason=name,
        net_profit_guard_applies=guard,
        metadata=metadata or {},
    )


def test_hard_exit_overrides_quality_profit_and_advanced_candidates() -> None:
    decision = ExitOrchestrator().decide(
        [
            _candidate("take_profit", ExitCandidateCategory.PROFIT_RISK, priority=100),
            _candidate("coint_lost", ExitCandidateCategory.QUALITY, priority=10),
            _candidate("advanced_soft_exit", ExitCandidateCategory.ADVANCED_ML, priority=100),
            _candidate("orphan_desync", ExitCandidateCategory.HARD, priority=1),
        ],
        net_profit_guard=NetProfitGuardContext(
            enabled=True,
            current_pnl_usdt=-5.0,
            min_profit_usdt=1.0,
        ),
    )

    assert decision.action == ExitAction.FULL_EXIT
    assert decision.selected_candidate is not None
    assert decision.selected_candidate.name == "orphan_desync"
    assert decision.hard_exit is True
    assert decision.blocked_by_net_profit_guard is False


def test_quality_exit_beats_profit_and_advanced_soft_exits() -> None:
    decision = ExitOrchestrator().decide(
        [
            _candidate("adaptive_profit_target", ExitCandidateCategory.PROFIT_RISK, priority=100),
            _candidate("bayesian_exit", ExitCandidateCategory.ADVANCED_ML, priority=1000),
            _candidate("pair_health_failure", ExitCandidateCategory.QUALITY, priority=1),
        ]
    )

    assert decision.selected_candidate is not None
    assert decision.selected_candidate.name == "pair_health_failure"


def test_net_profit_guard_blocks_only_marked_soft_profit_exits() -> None:
    decision = ExitOrchestrator().decide(
        [
            _candidate(
                "mean_reversion_target",
                ExitCandidateCategory.PROFIT_RISK,
                priority=100,
                guard=True,
            ),
            _candidate("stall_exit", ExitCandidateCategory.PROFIT_RISK, priority=10),
        ],
        net_profit_guard=NetProfitGuardContext(
            enabled=True,
            current_pnl_usdt=0.10,
            min_profit_usdt=0.75,
        ),
    )

    assert decision.selected_candidate is not None
    assert decision.selected_candidate.name == "stall_exit"
    assert decision.blocked_by_net_profit_guard is True
    assert decision.blocked_candidates[0].candidate.name == "mean_reversion_target"


def test_net_profit_guard_does_not_block_catastrophic_exit() -> None:
    decision = ExitOrchestrator().decide(
        [
            _candidate(
                "session_drawdown",
                ExitCandidateCategory.HARD,
                priority=100,
                guard=True,
            )
        ],
        net_profit_guard=NetProfitGuardContext(
            enabled=True,
            current_pnl_usdt=-100.0,
            min_profit_usdt=10.0,
        ),
    )

    assert decision.selected_candidate is not None
    assert decision.selected_candidate.name == "session_drawdown"
    assert decision.action == ExitAction.FULL_EXIT
    assert decision.blocked_candidates == ()


def test_all_blocked_soft_candidates_hold() -> None:
    decision = ExitOrchestrator().decide(
        [
            _candidate(
                "partial_profit",
                ExitCandidateCategory.PROFIT_RISK,
                action=ExitAction.PARTIAL_EXIT,
                guard=True,
            )
        ],
        net_profit_guard=NetProfitGuardContext(
            enabled=True,
            current_pnl_usdt=None,
            min_profit_usdt=0.50,
        ),
    )

    assert decision.action == ExitAction.HOLD
    assert decision.selected_candidate is None
    assert decision.blocked_by_net_profit_guard is True
    assert decision.reason == "net profit guard blocked all soft exit candidates"


def test_full_take_profit_multiplier_allows_orchestrator_at_effective_floor() -> None:
    decision = ExitOrchestrator().decide(
        [
            _candidate(
                "trade_manager_take_profit",
                ExitCandidateCategory.PROFIT_RISK,
                priority=100,
                guard=True,
                metadata={
                    "reason_code": "take_profit",
                    "base_min_profit_usdt": 1.0,
                    "effective_min_profit_usdt": 0.75,
                    "guard_multiplier": 0.75,
                },
            )
        ],
        net_profit_guard=NetProfitGuardContext(
            enabled=True,
            current_pnl_usdt=0.75,
            min_profit_usdt=1.0,
        ),
    )

    assert decision.selected_candidate is not None
    assert decision.selected_candidate.name == "trade_manager_take_profit"
    assert decision.blocked_candidates == ()


def test_full_take_profit_multiplier_blocks_below_effective_floor() -> None:
    decision = ExitOrchestrator().decide(
        [
            _candidate(
                "trade_manager_take_profit",
                ExitCandidateCategory.PROFIT_RISK,
                priority=100,
                guard=True,
                metadata={
                    "reason_code": "take_profit",
                    "base_min_profit_usdt": 1.0,
                    "effective_min_profit_usdt": 0.75,
                    "guard_multiplier": 0.75,
                },
            )
        ],
        net_profit_guard=NetProfitGuardContext(
            enabled=True,
            current_pnl_usdt=0.74,
            min_profit_usdt=1.0,
        ),
    )

    assert decision.action == ExitAction.HOLD
    assert decision.blocked_by_net_profit_guard is True
    blocked = decision.blocked_candidates[0]
    assert blocked.candidate.name == "trade_manager_take_profit"
    assert blocked.base_min_profit_usdt == pytest.approx(1.0)
    assert blocked.effective_min_profit_usdt == pytest.approx(0.75)
    assert blocked.guard_multiplier == pytest.approx(0.75)


def test_full_take_profit_default_multiplier_preserves_existing_orchestrator_floor() -> None:
    decision = ExitOrchestrator().decide(
        [
            _candidate(
                "trade_manager_take_profit",
                ExitCandidateCategory.PROFIT_RISK,
                priority=100,
                guard=True,
                metadata={"reason_code": "take_profit"},
            )
        ],
        net_profit_guard=NetProfitGuardContext(
            enabled=True,
            current_pnl_usdt=0.99,
            min_profit_usdt=1.0,
        ),
    )

    assert decision.action == ExitAction.HOLD
    blocked = decision.blocked_candidates[0]
    assert blocked.effective_min_profit_usdt == pytest.approx(1.0)
    assert blocked.guard_multiplier == pytest.approx(1.0)


def test_partial_profit_uses_partial_multiplier_not_full_multiplier() -> None:
    decision = ExitOrchestrator().decide(
        [
            _candidate(
                "trade_manager_partial_profit",
                ExitCandidateCategory.PROFIT_RISK,
                action=ExitAction.PARTIAL_EXIT,
                guard=True,
                metadata={"reason_code": "partial_profit"},
            )
        ],
        net_profit_guard=NetProfitGuardContext(
            enabled=True,
            current_pnl_usdt=0.60,
            min_profit_usdt=1.0,
            full_tp_guard_multiplier=0.50,
            partial_tp_guard_multiplier=0.75,
        ),
    )

    assert decision.action == ExitAction.HOLD
    blocked = decision.blocked_candidates[0]
    assert blocked.effective_min_profit_usdt == pytest.approx(0.75)
    assert blocked.guard_multiplier == pytest.approx(0.75)


def test_trailing_stop_uses_trailing_multiplier() -> None:
    decision = ExitOrchestrator().decide(
        [
            _candidate(
                "trade_manager_trailing_stop",
                ExitCandidateCategory.PROFIT_RISK,
                guard=True,
                metadata={"reason_code": "trailing_stop"},
            )
        ],
        net_profit_guard=NetProfitGuardContext(
            enabled=True,
            current_pnl_usdt=0.60,
            min_profit_usdt=1.0,
            full_tp_guard_multiplier=0.50,
            partial_tp_guard_multiplier=0.75,
            trailing_stop_guard_multiplier=0.90,
        ),
    )

    assert decision.action == ExitAction.HOLD
    blocked = decision.blocked_candidates[0]
    assert blocked.effective_min_profit_usdt == pytest.approx(0.90)
    assert blocked.guard_multiplier == pytest.approx(0.90)
