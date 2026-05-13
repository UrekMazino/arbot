from __future__ import annotations

import pytest

from core.chart_audit.hedge_ratio_drift_audit import (
    HEDGE_RATIO_DRIFT_SOURCE,
    compute_hedge_ratio_drift_pct,
    hedge_ratio_drift_exit_candidate,
)
from core.chart_audit.replay_snapshot import ReplayConfigSnapshot
from core.ev.hold_exit_ev import ExitAction
from core.trade_management.exit_orchestrator import ExitCandidateCategory, ExitOrchestrator


def _config() -> ReplayConfigSnapshot:
    return ReplayConfigSnapshot(
        config_version="test",
        config_source="historical",
        entry_z_threshold=2.0,
        exit_z_threshold=0.35,
        persistence_candles=1,
        max_hold_seconds=3600.0,
        min_zero_crossings=0,
        min_cointegration_window=1,
        max_hedge_ratio_drift_pct=0.20,
        severe_hedge_ratio_drift_pct=0.35,
    )


def test_hedge_ratio_drift_pct_formula() -> None:
    assert compute_hedge_ratio_drift_pct(entry_hedge_ratio=1.8, current_hedge_ratio=1.26) == pytest.approx(0.3)


def test_no_exit_candidate_when_drift_below_threshold() -> None:
    assert hedge_ratio_drift_exit_candidate(
        entry_hedge_ratio=1.8,
        current_hedge_ratio=1.55,
        config=_config(),
    ) is None


def test_drift_monitor_emits_quality_tighten_stop_candidate() -> None:
    candidate = hedge_ratio_drift_exit_candidate(
        entry_hedge_ratio=1.8,
        current_hedge_ratio=1.28,
        config=_config(),
        entry_id="entry-1",
    )

    assert candidate is not None
    assert candidate.name == HEDGE_RATIO_DRIFT_SOURCE
    assert candidate.category == ExitCandidateCategory.QUALITY
    assert candidate.action == ExitAction.TIGHTEN_STOP
    assert candidate.net_profit_guard_applies is False
    assert candidate.metadata["source"] == HEDGE_RATIO_DRIFT_SOURCE
    assert candidate.metadata["blockable_by_net_profit_guard"] is False
    assert candidate.severity == pytest.approx(candidate.metadata["hedge_ratio_drift_pct"] / 0.35)


def test_severe_drift_candidate_uses_full_exit() -> None:
    candidate = hedge_ratio_drift_exit_candidate(
        entry_hedge_ratio=1.8,
        current_hedge_ratio=1.0,
        config=_config(),
    )

    assert candidate is not None
    assert candidate.action == ExitAction.FULL_EXIT
    assert candidate.exit_percentage == 1.0


def test_drift_monitor_returns_candidate_not_direct_close() -> None:
    candidate = hedge_ratio_drift_exit_candidate(
        entry_hedge_ratio=1.8,
        current_hedge_ratio=1.28,
        config=_config(),
    )
    decision = ExitOrchestrator().decide([candidate] if candidate is not None else [])

    assert candidate is not None
    assert candidate.action == ExitAction.TIGHTEN_STOP
    assert decision.action == ExitAction.TIGHTEN_STOP
    assert decision.should_exit is False
