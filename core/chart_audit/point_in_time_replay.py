"""MVP curator-aware point-in-time replay engine.

This module evaluates one ReplaySnapshot at a time. It does not fetch live
state, execute trades, compute counterfactuals, or alter live trading behavior.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Any, TypeAlias

from core.chart_audit.marker_types import (
    BlockReason,
    CuratorState,
    MarkerCategory,
    ReplayMarkerType,
    build_replay_entry_id,
)
from core.chart_audit.point_in_time_indicators import (
    BasicHardValidationPointInTimeResult,
    STATUS_BLOCKED_CANDIDATE,
    STATUS_INSUFFICIENT_DATA,
    STATUS_VALID_CANDIDATE,
    compute_basic_hard_validation_point_in_time,
)
from core.chart_audit.replay_snapshot import ReplaySnapshot


BUY_SPREAD = "BUY_SPREAD"
SELL_SPREAD = "SELL_SPREAD"


class ReplayPositionState(str, Enum):
    NO_POSITION = "no_position"
    OPEN_BUY_SPREAD = "open_buy_spread"
    OPEN_SELL_SPREAD = "open_sell_spread"
    CLOSED = "closed"


@dataclass(frozen=True)
class ReplayMarkerBase:
    timestamp: int | float
    side: str | None
    z_score: float | None
    spread: float | None
    status: str
    curator_state: CuratorState
    curator_state_source: str
    config_source: str
    passed: bool
    reason: str
    block_reasons: tuple[BlockReason, ...] = ()
    entry_id: str | None = None
    hold_seconds: float | None = None
    position_state: ReplayPositionState = ReplayPositionState.NO_POSITION
    metadata: Mapping[str, Any] = field(default_factory=dict)
    marker_category: MarkerCategory = field(default=MarkerCategory.REPLAY, init=False)
    marker_type: ReplayMarkerType = field(init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            item.name: _json_value(getattr(self, item.name))
            for item in fields(self)
        }


@dataclass(frozen=True)
class ReplayEntryCandidateMarker(ReplayMarkerBase):
    marker_type: ReplayMarkerType = field(default=ReplayMarkerType.REPLAY_ENTRY_CANDIDATE, init=False)


@dataclass(frozen=True)
class ReplayExitCandidateMarker(ReplayMarkerBase):
    marker_type: ReplayMarkerType = field(default=ReplayMarkerType.REPLAY_EXIT_CANDIDATE, init=False)


@dataclass(frozen=True)
class ReplayBlockedSignalMarker(ReplayMarkerBase):
    marker_type: ReplayMarkerType = field(default=ReplayMarkerType.REPLAY_BLOCKED_SIGNAL, init=False)


ReplayMarker: TypeAlias = ReplayEntryCandidateMarker | ReplayExitCandidateMarker | ReplayBlockedSignalMarker


@dataclass
class _ReplayPosition:
    side: str
    entry_id: str
    entry_timestamp: int
    entry_z_score: float | None
    entry_spread: float | None


class PointInTimeReplayEngine:
    """Sequential MVP replay state machine."""

    def __init__(self) -> None:
        self.position_state = ReplayPositionState.NO_POSITION
        self._position: _ReplayPosition | None = None

    def reset(self) -> None:
        self.position_state = ReplayPositionState.NO_POSITION
        self._position = None

    def evaluate(self, snapshot: ReplaySnapshot) -> list[ReplayMarker]:
        """Evaluate one point-in-time snapshot and return replay markers."""

        if not isinstance(snapshot, ReplaySnapshot):
            raise TypeError("PointInTimeReplayEngine.evaluate requires a ReplaySnapshot")

        if self.position_state == ReplayPositionState.CLOSED:
            self.position_state = ReplayPositionState.NO_POSITION

        latest_z = _latest_finite(snapshot.zscore_until_t)
        latest_spread = _latest_finite(snapshot.spread_until_t)
        if latest_z is None:
            return []

        if self._position is not None:
            exit_marker = self._maybe_exit(snapshot, latest_z, latest_spread)
            if exit_marker is not None:
                return [exit_marker]

            side = _entry_side(latest_z, snapshot.config_snapshot.entry_z_threshold)
            if side is not None:
                return [
                    self._blocked_marker(
                        snapshot,
                        side=side,
                        z_score=latest_z,
                        spread=latest_spread,
                        block_reasons=(BlockReason.POSITION_ALREADY_OPEN,),
                        status=STATUS_BLOCKED_CANDIDATE,
                        reason="entry threshold reached but replay position is already open",
                        hard_validation=None,
                    )
                ]
            return []

        side = _entry_side(latest_z, snapshot.config_snapshot.entry_z_threshold)
        if side is None:
            return []

        hard_validation = compute_basic_hard_validation_point_in_time(snapshot)
        block_reasons = list(hard_validation.block_reasons)
        if not _persistence_passed(snapshot.zscore_until_t, side, snapshot.config_snapshot.entry_z_threshold, snapshot.config_snapshot.persistence_candles):
            block_reasons.append(BlockReason.Z_PERSISTENCE_FAILED)

        unique_reasons = _unique_reasons(block_reasons)
        if hard_validation.passed and not unique_reasons:
            marker = self._entry_marker(snapshot, side=side, z_score=latest_z, spread=latest_spread, hard_validation=hard_validation)
            self._position = _ReplayPosition(
                side=side,
                entry_id=str(marker.entry_id),
                entry_timestamp=int(snapshot.timestamp),
                entry_z_score=latest_z,
                entry_spread=latest_spread,
            )
            self.position_state = _open_state_for_side(side)
            return [marker]

        status = STATUS_INSUFFICIENT_DATA if hard_validation.status == STATUS_INSUFFICIENT_DATA else STATUS_BLOCKED_CANDIDATE
        return [
            self._blocked_marker(
                snapshot,
                side=side,
                z_score=latest_z,
                spread=latest_spread,
                block_reasons=unique_reasons,
                status=status,
                reason=_blocked_reason(status, unique_reasons),
                hard_validation=hard_validation,
            )
        ]

    def _entry_marker(
        self,
        snapshot: ReplaySnapshot,
        *,
        side: str,
        z_score: float,
        spread: float | None,
        hard_validation: BasicHardValidationPointInTimeResult,
    ) -> ReplayEntryCandidateMarker:
        entry_id = build_replay_entry_id(snapshot.pair, snapshot.timestamp, side)
        return ReplayEntryCandidateMarker(
            timestamp=snapshot.timestamp,
            side=side,
            z_score=z_score,
            spread=spread,
            status=STATUS_VALID_CANDIDATE,
            curator_state=snapshot.curator_state,
            curator_state_source=snapshot.curator_state_source,
            config_source=snapshot.config_snapshot.config_source,
            passed=True,
            reason="z threshold, persistence, curator, and hard validation passed",
            entry_id=entry_id,
            position_state=_open_state_for_side(side),
            metadata={
                "entry_z_threshold": float(snapshot.config_snapshot.entry_z_threshold),
                "persistence_candles": int(snapshot.config_snapshot.persistence_candles),
                "config_version": snapshot.config_snapshot.config_version,
                "hard_validation": hard_validation.to_dict(),
            },
        )

    def _blocked_marker(
        self,
        snapshot: ReplaySnapshot,
        *,
        side: str,
        z_score: float,
        spread: float | None,
        block_reasons: Sequence[BlockReason],
        status: str,
        reason: str,
        hard_validation: BasicHardValidationPointInTimeResult | None,
    ) -> ReplayBlockedSignalMarker:
        return ReplayBlockedSignalMarker(
            timestamp=snapshot.timestamp,
            side=side,
            z_score=z_score,
            spread=spread,
            status=status,
            curator_state=snapshot.curator_state,
            curator_state_source=snapshot.curator_state_source,
            config_source=snapshot.config_snapshot.config_source,
            passed=False,
            reason=reason,
            block_reasons=_unique_reasons(block_reasons),
            entry_id=build_replay_entry_id(snapshot.pair, snapshot.timestamp, side),
            position_state=self.position_state,
            metadata={
                "entry_z_threshold": float(snapshot.config_snapshot.entry_z_threshold),
                "persistence_candles": int(snapshot.config_snapshot.persistence_candles),
                "config_version": snapshot.config_snapshot.config_version,
                "hard_validation": hard_validation.to_dict() if hard_validation is not None else None,
            },
        )

    def _maybe_exit(
        self,
        snapshot: ReplaySnapshot,
        latest_z: float,
        latest_spread: float | None,
    ) -> ReplayExitCandidateMarker | None:
        position = self._position
        if position is None:
            return None

        exit_reasons: list[str] = []
        block_reasons: list[BlockReason] = []
        hold_seconds = max(float(snapshot.timestamp - position.entry_timestamp), 0.0)
        if abs(latest_z) <= float(snapshot.config_snapshot.exit_z_threshold):
            exit_reasons.append("z_reverted_to_exit_threshold")
        if hold_seconds >= float(snapshot.config_snapshot.max_hold_seconds):
            exit_reasons.append("max_hold_reached")
        if snapshot.curator_state != CuratorState.TRADABLE:
            exit_reasons.append("curator_state_no_longer_tradable")
            block_reasons.extend(_curator_exit_block_reasons(snapshot.curator_state))

        if not exit_reasons:
            return None

        marker = ReplayExitCandidateMarker(
            timestamp=snapshot.timestamp,
            side=position.side,
            z_score=latest_z,
            spread=latest_spread,
            status=STATUS_VALID_CANDIDATE,
            curator_state=snapshot.curator_state,
            curator_state_source=snapshot.curator_state_source,
            config_source=snapshot.config_snapshot.config_source,
            passed=True,
            reason=", ".join(exit_reasons),
            block_reasons=_unique_reasons(block_reasons),
            entry_id=position.entry_id,
            hold_seconds=hold_seconds,
            position_state=ReplayPositionState.CLOSED,
            metadata={
                "exit_reasons": exit_reasons,
                "exit_z_threshold": float(snapshot.config_snapshot.exit_z_threshold),
                "max_hold_seconds": float(snapshot.config_snapshot.max_hold_seconds),
                "entry_timestamp": position.entry_timestamp,
                "entry_z_score": position.entry_z_score,
                "entry_spread": position.entry_spread,
                "config_version": snapshot.config_snapshot.config_version,
            },
        )
        self._position = None
        self.position_state = ReplayPositionState.CLOSED
        return marker


def generate_replay_markers(snapshots: Iterable[ReplaySnapshot]) -> list[ReplayMarker]:
    """Run the MVP replay engine over snapshots in caller-provided order."""

    engine = PointInTimeReplayEngine()
    markers: list[ReplayMarker] = []
    for snapshot in snapshots:
        markers.extend(engine.evaluate(snapshot))
    return markers


def _entry_side(z_score: float, threshold: float) -> str | None:
    threshold_value = abs(float(threshold))
    if z_score <= -threshold_value:
        return BUY_SPREAD
    if z_score >= threshold_value:
        return SELL_SPREAD
    return None


def _persistence_passed(
    zscore_until_t: Sequence[Any],
    side: str,
    threshold: float,
    persistence_candles: int,
) -> bool:
    required = max(int(persistence_candles or 1), 1)
    values = _finite_values(zscore_until_t)
    if len(values) < required:
        return False
    recent = values[-required:]
    threshold_value = abs(float(threshold))
    if side == BUY_SPREAD:
        return all(value <= -threshold_value for value in recent)
    if side == SELL_SPREAD:
        return all(value >= threshold_value for value in recent)
    return False


def _open_state_for_side(side: str) -> ReplayPositionState:
    if side == BUY_SPREAD:
        return ReplayPositionState.OPEN_BUY_SPREAD
    if side == SELL_SPREAD:
        return ReplayPositionState.OPEN_SELL_SPREAD
    return ReplayPositionState.NO_POSITION


def _curator_exit_block_reasons(curator_state: CuratorState) -> tuple[BlockReason, ...]:
    mapping = {
        CuratorState.ANALYSIS_ONLY: BlockReason.ANALYSIS_ONLY,
        CuratorState.EXCLUDED: BlockReason.PAIR_EXCLUDED,
        CuratorState.HOSPITAL: BlockReason.PAIR_IN_HOSPITAL,
        CuratorState.GRAVEYARD: BlockReason.PAIR_IN_GRAVEYARD,
        CuratorState.STALE_DATA: BlockReason.STALE_DATA,
        CuratorState.INSUFFICIENT_HISTORY: BlockReason.INSUFFICIENT_HISTORY,
        CuratorState.LOW_LIQUIDITY: BlockReason.CURATOR_LOW_LIQUIDITY,
    }
    reason = mapping.get(curator_state, BlockReason.CURATOR_NOT_TRADABLE)
    return (reason,)


def _blocked_reason(status: str, block_reasons: Sequence[BlockReason]) -> str:
    if status == STATUS_INSUFFICIENT_DATA:
        return "entry threshold reached but point-in-time replay data is insufficient"
    if not block_reasons:
        return "entry threshold reached but replay gate failed"
    return "entry threshold reached but blocked by " + ", ".join(reason.value for reason in block_reasons)


def _unique_reasons(reasons: Sequence[BlockReason]) -> tuple[BlockReason, ...]:
    seen: set[BlockReason] = set()
    ordered: list[BlockReason] = []
    for reason in reasons:
        if reason in seen:
            continue
        seen.add(reason)
        ordered.append(reason)
    return tuple(ordered)


def _latest_finite(values: Sequence[Any]) -> float | None:
    finite = _finite_values(values)
    return finite[-1] if finite else None


def _finite_values(values: Sequence[Any]) -> list[float]:
    output: list[float] = []
    for value in values:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(parsed):
            output.append(parsed)
    return output


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


__all__ = [
    "BUY_SPREAD",
    "SELL_SPREAD",
    "PointInTimeReplayEngine",
    "ReplayBlockedSignalMarker",
    "ReplayEntryCandidateMarker",
    "ReplayExitCandidateMarker",
    "ReplayMarker",
    "ReplayMarkerBase",
    "ReplayPositionState",
    "generate_replay_markers",
]
