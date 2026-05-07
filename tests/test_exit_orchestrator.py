from __future__ import annotations

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
) -> ExitCandidate:
    return ExitCandidate(
        name=name,
        category=category,
        action=action,
        priority=priority,
        reason=name,
        net_profit_guard_applies=guard,
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
