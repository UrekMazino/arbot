"""Replay-safe Advanced ML scoring bridge.

Phase 2.5 intentionally prefers stored point-in-time score snapshots. The
recompute path is not enabled here because the live ML runtime uses mutable
runtime state and wall-clock time.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from core.chart_audit.marker_types import BlockReason
from core.chart_audit.ml_replay_types import (
    MLScoreSource,
    ReplayMLGateConfig,
    ReplayMLScoreSnapshot,
    unavailable_ml_score,
)
from core.chart_audit.replay_snapshot import ReplaySnapshot


ScoreLookup = Callable[[str, int], ReplayMLScoreSnapshot | None]


@dataclass(frozen=True)
class ReplayMLGateResult:
    passed: bool
    block_reasons: tuple[BlockReason, ...] = ()


class ReplayMLScoringBridge:
    """Return Advanced ML score metadata for a ReplaySnapshot."""

    def __init__(self, score_lookup: ScoreLookup | None = None) -> None:
        self._score_lookup = score_lookup

    def score(self, snapshot: ReplaySnapshot) -> ReplayMLScoreSnapshot:
        if not isinstance(snapshot, ReplaySnapshot):
            raise TypeError("ReplayMLScoringBridge.score requires a ReplaySnapshot")
        if self._score_lookup is None:
            return unavailable_ml_score(snapshot.pair, snapshot.timestamp)

        score = self._score_lookup(snapshot.pair, snapshot.timestamp)
        if score is None:
            return unavailable_ml_score(snapshot.pair, snapshot.timestamp)
        if not isinstance(score, ReplayMLScoreSnapshot):
            raise TypeError("ML score lookup must return ReplayMLScoreSnapshot or None")
        return score


def get_replay_ml_score(
    snapshot: ReplaySnapshot,
    *,
    score_lookup: ScoreLookup | None = None,
) -> ReplayMLScoreSnapshot:
    return ReplayMLScoringBridge(score_lookup=score_lookup).score(snapshot)


def evaluate_replay_ml_gate(
    score: ReplayMLScoreSnapshot,
    config: ReplayMLGateConfig,
) -> ReplayMLGateResult:
    if not isinstance(score, ReplayMLScoreSnapshot):
        raise TypeError("evaluate_replay_ml_gate requires ReplayMLScoreSnapshot")
    if not config.enabled:
        return ReplayMLGateResult(passed=True)
    if score.score_source == MLScoreSource.UNAVAILABLE:
        return ReplayMLGateResult(passed=True)

    block_reasons: list[BlockReason] = []
    if config.require_hard_validation and score.hard_validation_valid is False:
        block_reasons.extend(score.block_reasons or (BlockReason.QUALITY_GATE_FAILED,))
    if score.break_risk is not None and score.break_risk >= config.max_break_risk:
        block_reasons.append(BlockReason.REGIME_BREAK_RISK_HIGH)
    if score.final_rank_score is not None and score.final_rank_score < config.min_final_rank_score:
        block_reasons.append(BlockReason.QUALITY_GATE_FAILED)
    if score.bayesian_posterior is not None and score.bayesian_posterior < config.min_bayesian_posterior:
        block_reasons.append(BlockReason.QUALITY_GATE_FAILED)
    if score.microstructure_risk is not None and score.microstructure_risk >= config.max_microstructure_risk:
        block_reasons.append(BlockReason.LIQUIDITY_FAILED)
    if (
        config.min_liquidity_score is not None
        and score.liquidity_score is not None
        and score.liquidity_score < config.min_liquidity_score
    ):
        block_reasons.append(BlockReason.LIQUIDITY_FAILED)

    unique = _unique_block_reasons(block_reasons)
    return ReplayMLGateResult(passed=not unique, block_reasons=unique)


def ml_score_marker_metadata(score: ReplayMLScoreSnapshot) -> dict[str, Any]:
    if not isinstance(score, ReplayMLScoreSnapshot):
        raise TypeError("ml_score_marker_metadata requires ReplayMLScoreSnapshot")
    return score.to_marker_metadata()


def _unique_block_reasons(reasons: list[BlockReason] | tuple[BlockReason, ...]) -> tuple[BlockReason, ...]:
    seen: set[BlockReason] = set()
    output: list[BlockReason] = []
    for reason in reasons:
        if reason in seen:
            continue
        seen.add(reason)
        output.append(reason)
    return tuple(output)


__all__ = [
    "ReplayMLGateResult",
    "ReplayMLScoringBridge",
    "ScoreLookup",
    "evaluate_replay_ml_gate",
    "get_replay_ml_score",
    "ml_score_marker_metadata",
]
