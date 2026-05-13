"""Decision score timeline assembly for chart audit.

The timeline is read-only audit data. It uses stored point-in-time score rows
or explicit unavailable rows, and never calls live/current ML runtime state.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from core.chart_audit.hedge_ratio_drift_audit import compute_hedge_ratio_drift_pct
from core.chart_audit.ml_replay_types import MLScoreSource, ReplayMLScoreSnapshot
from core.chart_audit.replay_snapshot import ReplayConfigSnapshot, ReplaySnapshot
from core.chart_audit.replay_snapshot_factory import ReplaySnapshotFactory


DownsampleMethod = Literal["last", "mean", "none"]

NUMERIC_TIMELINE_FIELDS = (
    "regime_confidence",
    "break_risk",
    "bayesian_posterior",
    "final_rank_score",
    "linucb_score",
    "trade_quality_score",
    "liquidity_score",
    "microstructure_risk",
    "ev_hold_value_usdt",
    "exit_score",
    "hedge_ratio_at_t",
    "hedge_ratio_drift_pct",
)

CATEGORICAL_TIMELINE_FIELDS = (
    "score_source",
    "curator_state",
    "curator_state_source",
    "regime",
    "bayesian_quality_grade",
    "quality_gate_passed",
    "config_source",
    "warning",
)

ENTRY_MARKER_TYPES = {"actual_entry", "replay_entry_candidate"}
EXIT_MARKER_TYPES = {
    "actual_exit",
    "actual_partial_exit",
    "actual_regime_exit",
    "actual_manual_exit",
    "replay_exit_candidate",
}


@dataclass(frozen=True)
class DecisionScoreTimelineConfig:
    include_decision_timeline: bool = False
    max_timeline_points: int = 1440
    downsample_method: DownsampleMethod | str = "last"
    resolution: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "include_decision_timeline", _coerce_bool(self.include_decision_timeline))
        object.__setattr__(self, "max_timeline_points", max(int(self.max_timeline_points or 1440), 1))
        method = str(self.downsample_method or "last").strip().lower()
        if method not in {"last", "mean", "none"}:
            method = "last"
        object.__setattr__(self, "downsample_method", method)
        object.__setattr__(self, "resolution", _normalize_text(self.resolution))


@dataclass(frozen=True)
class DecisionScoreTimelinePoint:
    timestamp: int
    score_source: str
    curator_state: str | None = None
    curator_state_source: str | None = None
    regime: str | None = None
    regime_confidence: float | None = None
    break_risk: float | None = None
    bayesian_posterior: float | None = None
    bayesian_quality_grade: str | None = None
    final_rank_score: float | None = None
    linucb_score: float | None = None
    trade_quality_score: float | None = None
    liquidity_score: float | None = None
    microstructure_risk: float | None = None
    ev_hold_value_usdt: float | None = None
    exit_score: float | None = None
    quality_gate_passed: bool | None = None
    hedge_ratio_at_t: float | None = None
    hedge_ratio_drift_pct: float | None = None
    config_source: str | None = None
    warning: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {item.name: _json_value(getattr(self, item.name)) for item in fields(self)}


@dataclass(frozen=True)
class DecisionScoreTimelineMeta:
    timeline_resolution: str | None
    timeline_downsample_method: str
    timeline_original_points: int
    timeline_returned_points: int
    score_source_summary: Mapping[str, int]
    unavailable_count: int = 0
    stored_live_count: int = 0
    recomputed_point_in_time_count: int = 0
    current_approximate_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeline_resolution": self.timeline_resolution,
            "timeline_downsample_method": self.timeline_downsample_method,
            "timeline_original_points": self.timeline_original_points,
            "timeline_returned_points": self.timeline_returned_points,
            "score_source_summary": dict(self.score_source_summary),
            "unavailable_count": self.unavailable_count,
            "stored_live_count": self.stored_live_count,
            "recomputed_point_in_time_count": self.recomputed_point_in_time_count,
            "current_approximate_count": self.current_approximate_count,
        }


@dataclass(frozen=True)
class DecisionScoreTimeline:
    points: tuple[DecisionScoreTimelinePoint, ...]
    meta: DecisionScoreTimelineMeta

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_score_timeline": [point.to_dict() for point in self.points],
            "decision_timeline_meta": self.meta.to_dict(),
        }


def empty_decision_score_timeline(
    config: DecisionScoreTimelineConfig | Mapping[str, Any] | None = None,
) -> DecisionScoreTimeline:
    cfg = _coerce_config(config)
    return DecisionScoreTimeline(points=(), meta=_meta((), 0, cfg))


def build_decision_score_timeline(
    *,
    pair: str,
    timeframe: str,
    candles: Iterable[Any],
    stored_scores: Iterable[ReplayMLScoreSnapshot | Mapping[str, Any]] = (),
    config: DecisionScoreTimelineConfig | Mapping[str, Any] | None = None,
    curator_state_at: Callable[[int], Any] | None = None,
    config_at: Callable[[int], ReplayConfigSnapshot] | None = None,
    entry_markers: Sequence[Mapping[str, Any]] = (),
) -> DecisionScoreTimeline:
    """Build a point-in-time decision timeline from chart candles and stored scores."""

    cfg = _coerce_config(config)
    if not cfg.include_decision_timeline:
        return empty_decision_score_timeline(cfg)

    snapshots = _snapshots(
        pair=pair,
        timeframe=timeframe,
        candles=candles,
        curator_state_at=curator_state_at,
        config_at=config_at,
    )
    score_stream = _score_stream(stored_scores)
    entry_contexts = _entry_contexts(entry_markers)
    raw_points = _aligned_points(snapshots, score_stream, entry_contexts)
    returned_points = _downsample(raw_points, cfg)
    return DecisionScoreTimeline(
        points=tuple(returned_points),
        meta=_meta(returned_points, len(raw_points), cfg),
    )


def _snapshots(
    *,
    pair: str,
    timeframe: str,
    candles: Iterable[Any],
    curator_state_at: Callable[[int], Any] | None,
    config_at: Callable[[int], ReplayConfigSnapshot] | None,
) -> tuple[ReplaySnapshot, ...]:
    factory = ReplaySnapshotFactory(
        pair=pair,
        timeframe=timeframe,
        candles=candles,
        curator_state_at=curator_state_at,
        config_at=config_at,
    )
    return factory.build_snapshots()


def _aligned_points(
    snapshots: tuple[ReplaySnapshot, ...],
    score_stream: tuple[ReplayMLScoreSnapshot, ...],
    entry_contexts: tuple[Mapping[str, Any], ...],
) -> tuple[DecisionScoreTimelinePoint, ...]:
    points: list[DecisionScoreTimelinePoint] = []
    pointer = -1
    latest_score: ReplayMLScoreSnapshot | None = None
    for snapshot in sorted(snapshots, key=lambda item: int(item.timestamp)):
        timestamp = int(snapshot.timestamp)
        while pointer + 1 < len(score_stream) and int(score_stream[pointer + 1].timestamp or 0) <= timestamp:
            pointer += 1
            latest_score = score_stream[pointer]
        active_entry = _active_entry_context(entry_contexts, timestamp)
        points.append(_point_from_snapshot(snapshot, latest_score, active_entry))
    return tuple(points)


def _point_from_snapshot(
    snapshot: ReplaySnapshot,
    score: ReplayMLScoreSnapshot | None,
    active_entry: Mapping[str, Any] | None,
) -> DecisionScoreTimelinePoint:
    score_source = MLScoreSource.UNAVAILABLE.value if score is None else score.score_source.value
    metadata: dict[str, Any] = {}
    warning = None
    if score is not None:
        if score.timestamp is not None:
            metadata["score_timestamp"] = int(score.timestamp)
        if score.warning:
            warning = score.warning
    drift = _hedge_ratio_drift(active_entry, snapshot.hedge_ratio_until_t)
    if active_entry is not None:
        metadata["active_entry_id"] = active_entry.get("entry_id")
        metadata["active_entry_marker_type"] = active_entry.get("marker_type")
    return DecisionScoreTimelinePoint(
        timestamp=int(snapshot.timestamp),
        score_source=score_source,
        curator_state=_enum_value(snapshot.curator_state),
        curator_state_source=snapshot.curator_state_source,
        regime=score.regime_name if score is not None else None,
        regime_confidence=score.regime_confidence if score is not None else None,
        break_risk=score.break_risk if score is not None else None,
        bayesian_posterior=score.bayesian_posterior if score is not None else None,
        bayesian_quality_grade=score.bayesian_quality_grade if score is not None else None,
        final_rank_score=score.final_rank_score if score is not None else None,
        linucb_score=_score_metadata_float(score, "linucb_score"),
        trade_quality_score=_score_metadata_float(score, "trade_quality_score"),
        liquidity_score=score.liquidity_score if score is not None else None,
        microstructure_risk=score.microstructure_risk if score is not None else None,
        ev_hold_value_usdt=score.ev_hold_value_usdt if score is not None else None,
        exit_score=score.exit_score if score is not None else None,
        quality_gate_passed=score.quality_gate_passed if score is not None else None,
        hedge_ratio_at_t=snapshot.hedge_ratio_until_t,
        hedge_ratio_drift_pct=drift,
        config_source=snapshot.config_source,
        warning=warning,
        metadata=metadata,
    )


def _score_stream(
    stored_scores: Iterable[ReplayMLScoreSnapshot | Mapping[str, Any]],
) -> tuple[ReplayMLScoreSnapshot, ...]:
    rows: list[ReplayMLScoreSnapshot] = []
    for row in stored_scores:
        score = _coerce_score(row)
        if score is None or score.timestamp is None:
            continue
        rows.append(score)
    return tuple(sorted(rows, key=lambda item: int(item.timestamp or 0)))


def _coerce_score(row: ReplayMLScoreSnapshot | Mapping[str, Any]) -> ReplayMLScoreSnapshot | None:
    if isinstance(row, ReplayMLScoreSnapshot):
        return row
    if not isinstance(row, Mapping):
        return None
    try:
        return ReplayMLScoreSnapshot(
            pair=row.get("pair"),
            timestamp=row.get("timestamp"),
            score_source=row.get("score_source") or MLScoreSource.STORED_LIVE,
            hard_validation_valid=row.get("hard_validation_valid"),
            regime_name=row.get("regime_name") or row.get("regime"),
            regime_confidence=row.get("regime_confidence"),
            break_risk=row.get("break_risk"),
            bayesian_posterior=row.get("bayesian_posterior"),
            bayesian_quality_grade=row.get("bayesian_quality_grade"),
            final_rank_score=row.get("final_rank_score"),
            microstructure_risk=row.get("microstructure_risk"),
            liquidity_score=row.get("liquidity_score"),
            ev_hold_value_usdt=row.get("ev_hold_value_usdt"),
            exit_score=row.get("exit_score"),
            quality_gate_passed=row.get("quality_gate_passed"),
            metadata={
                "linucb_score": row.get("linucb_score"),
                "trade_quality_score": row.get("trade_quality_score"),
            },
        )
    except (TypeError, ValueError):
        return None


def _entry_contexts(markers: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    entries: list[dict[str, Any]] = []
    exits: list[Mapping[str, Any]] = []
    for marker in markers:
        marker_type = str(marker.get("marker_type") or "")
        if marker_type in ENTRY_MARKER_TYPES:
            timestamp = _coerce_timestamp(marker.get("original_event_timestamp") or marker.get("timestamp"))
            if timestamp is None:
                continue
            metadata = marker.get("metadata")
            entries.append(
                {
                    "entry_id": marker.get("entry_id"),
                    "trade_id": marker.get("trade_id"),
                    "marker_type": marker_type,
                    "start_ts": int(timestamp),
                    "entry_hedge_ratio": _metadata_float(
                        metadata if isinstance(metadata, Mapping) else {},
                        "entry_hedge_ratio",
                        "hedge_ratio_at_t",
                        "hedge_ratio",
                    ),
                    "end_ts": None,
                }
            )
        elif marker_type in EXIT_MARKER_TYPES:
            exits.append(marker)

    for entry in entries:
        end_ts = _matching_exit_timestamp(entry, exits)
        if end_ts is not None:
            entry["end_ts"] = int(end_ts)
    return tuple(sorted(entries, key=lambda item: int(item["start_ts"])))


def _matching_exit_timestamp(entry: Mapping[str, Any], exits: Sequence[Mapping[str, Any]]) -> int | None:
    candidates: list[int] = []
    entry_id = _normalize_text(entry.get("entry_id"))
    trade_id = _normalize_text(entry.get("trade_id"))
    for marker in exits:
        marker_type = str(marker.get("marker_type") or "")
        if marker_type == "replay_exit_candidate" and entry_id and marker.get("entry_id") != entry_id:
            continue
        if marker_type != "replay_exit_candidate" and trade_id and marker.get("trade_id") != trade_id:
            continue
        timestamp = _coerce_timestamp(marker.get("original_event_timestamp") or marker.get("timestamp"))
        if timestamp is None or int(timestamp) < int(entry["start_ts"]):
            continue
        candidates.append(int(timestamp))
    return min(candidates) if candidates else None


def _active_entry_context(
    contexts: tuple[Mapping[str, Any], ...],
    timestamp: int,
) -> Mapping[str, Any] | None:
    active = [
        context
        for context in contexts
        if int(context["start_ts"]) <= timestamp
        and (context.get("end_ts") is None or timestamp <= int(context["end_ts"]))
    ]
    if not active:
        return None
    return max(active, key=lambda item: int(item["start_ts"]))


def _hedge_ratio_drift(active_entry: Mapping[str, Any] | None, current_hedge_ratio: float | None) -> float | None:
    if active_entry is None or current_hedge_ratio is None:
        return None
    entry_hedge_ratio = _optional_float(active_entry.get("entry_hedge_ratio"))
    if entry_hedge_ratio is None:
        return None
    try:
        return compute_hedge_ratio_drift_pct(
            entry_hedge_ratio=entry_hedge_ratio,
            current_hedge_ratio=float(current_hedge_ratio),
        )
    except ValueError:
        return None


def _downsample(
    points: tuple[DecisionScoreTimelinePoint, ...],
    config: DecisionScoreTimelineConfig,
) -> tuple[DecisionScoreTimelinePoint, ...]:
    if config.downsample_method == "none" or not points:
        return points

    bucketed = _resolution_downsample(points, config) if config.resolution else points
    if len(bucketed) <= config.max_timeline_points:
        return tuple(bucketed)

    chunk_size = max(math.ceil(len(bucketed) / config.max_timeline_points), 1)
    buckets = [
        tuple(bucketed[index : index + chunk_size])
        for index in range(0, len(bucketed), chunk_size)
    ]
    sampled = tuple(_collapse_bucket(bucket, config.downsample_method) for bucket in buckets if bucket)
    return sampled[: config.max_timeline_points]


def _resolution_downsample(
    points: tuple[DecisionScoreTimelinePoint, ...],
    config: DecisionScoreTimelineConfig,
) -> tuple[DecisionScoreTimelinePoint, ...]:
    seconds = _resolution_seconds(config.resolution)
    if seconds is None:
        return points
    buckets: dict[int, list[DecisionScoreTimelinePoint]] = {}
    for point in points:
        bucket_key = int(point.timestamp // seconds)
        buckets.setdefault(bucket_key, []).append(point)
    return tuple(
        _collapse_bucket(tuple(bucket), config.downsample_method)
        for _, bucket in sorted(buckets.items(), key=lambda item: item[0])
    )


def _collapse_bucket(
    bucket: tuple[DecisionScoreTimelinePoint, ...],
    method: str,
) -> DecisionScoreTimelinePoint:
    if method == "last" or len(bucket) == 1:
        return bucket[-1]
    latest = bucket[-1].to_dict()
    for field_name in NUMERIC_TIMELINE_FIELDS:
        latest[field_name] = _mean_optional(getattr(item, field_name) for item in bucket)
    latest["metadata"] = {
        **(latest.get("metadata") if isinstance(latest.get("metadata"), dict) else {}),
        "downsampled_bucket_size": len(bucket),
        "bucket_start_timestamp": bucket[0].timestamp,
        "bucket_end_timestamp": bucket[-1].timestamp,
    }
    return DecisionScoreTimelinePoint(**latest)


def _meta(
    points: Sequence[DecisionScoreTimelinePoint],
    original_points: int,
    config: DecisionScoreTimelineConfig,
) -> DecisionScoreTimelineMeta:
    source_counts = Counter(point.score_source for point in points)
    return DecisionScoreTimelineMeta(
        timeline_resolution=config.resolution,
        timeline_downsample_method=str(config.downsample_method),
        timeline_original_points=int(original_points),
        timeline_returned_points=len(points),
        score_source_summary=dict(source_counts),
        unavailable_count=int(source_counts.get(MLScoreSource.UNAVAILABLE.value, 0)),
        stored_live_count=int(source_counts.get(MLScoreSource.STORED_LIVE.value, 0)),
        recomputed_point_in_time_count=int(source_counts.get(MLScoreSource.RECOMPUTED_POINT_IN_TIME.value, 0)),
        current_approximate_count=int(source_counts.get(MLScoreSource.CURRENT_APPROXIMATE.value, 0)),
    )


def _coerce_config(config: DecisionScoreTimelineConfig | Mapping[str, Any] | None) -> DecisionScoreTimelineConfig:
    if isinstance(config, DecisionScoreTimelineConfig):
        return config
    if isinstance(config, Mapping):
        return DecisionScoreTimelineConfig(
            include_decision_timeline=config.get("include_decision_timeline", False),
            max_timeline_points=config.get("max_timeline_points", 1440),
            downsample_method=config.get("downsample_method", "last"),
            resolution=config.get("resolution"),
        )
    return DecisionScoreTimelineConfig()


def _resolution_seconds(value: str | None) -> int | None:
    text = _normalize_text(value)
    if text is None:
        return None
    unit = text[-1].lower()
    amount = _optional_float(text[:-1] if unit in {"m", "h", "d", "s"} else text)
    if amount is None or amount <= 0:
        return None
    if unit == "s":
        return max(int(amount), 1)
    if unit == "m":
        return max(int(amount * 60), 1)
    if unit == "h":
        return max(int(amount * 3600), 1)
    if unit == "d":
        return max(int(amount * 86400), 1)
    return max(int(amount), 1)


def _score_metadata_float(score: ReplayMLScoreSnapshot | None, key: str) -> float | None:
    if score is None:
        return None
    metadata = score.metadata
    if isinstance(metadata, Mapping):
        return _optional_float(metadata.get(key))
    if isinstance(metadata, tuple):
        return _optional_float(dict(metadata).get(key))
    return None


def _metadata_float(metadata: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _optional_float(metadata.get(key))
        if value is not None:
            return value
    return None


def _mean_optional(values: Iterable[Any]) -> float | None:
    parsed = [_optional_float(value) for value in values]
    finite = [value for value in parsed if value is not None]
    if not finite:
        return None
    return sum(finite) / len(finite)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _coerce_timestamp(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt_value = value
        if dt_value.tzinfo is None:
            dt_value = dt_value.replace(tzinfo=timezone.utc)
        return float(dt_value.timestamp())
    if isinstance(value, (int, float)):
        parsed = float(value)
        if not math.isfinite(parsed):
            return None
        if parsed > 10_000_000_000:
            parsed /= 1000.0
        return parsed
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        try:
            parsed_dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return _coerce_timestamp(parsed_dt)
    if not math.isfinite(parsed):
        return None
    if parsed > 10_000_000_000:
        parsed /= 1000.0
    return parsed


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _enum_value(value: Any) -> str | None:
    if isinstance(value, Enum):
        return str(value.value)
    return _normalize_text(value)


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


__all__ = [
    "DecisionScoreTimeline",
    "DecisionScoreTimelineConfig",
    "DecisionScoreTimelineMeta",
    "DecisionScoreTimelinePoint",
    "build_decision_score_timeline",
    "empty_decision_score_timeline",
]
