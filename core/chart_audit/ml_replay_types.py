"""Advanced ML replay score contracts for chart audit.

These DTOs are read-only audit contracts. They do not call model runtimes,
submit orders, or mutate bot state.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from core.chart_audit.marker_types import BlockReason


class MLScoreSource(str, Enum):
    STORED_LIVE = "stored_live"
    RECOMPUTED_POINT_IN_TIME = "recomputed_point_in_time"
    CURRENT_APPROXIMATE = "current_approximate"
    UNAVAILABLE = "unavailable"


ML_REPLAY_MARKER_METADATA_FIELDS = (
    "score_source",
    "hard_validation_valid",
    "regime_name",
    "regime_confidence",
    "break_risk",
    "bayesian_posterior",
    "bayesian_quality_grade",
    "final_rank_score",
    "microstructure_risk",
    "liquidity_score",
    "ev_hold_value_usdt",
    "exit_score",
    "quality_gate_passed",
)


@dataclass(frozen=True)
class ReplayMLGateConfig:
    enabled: bool = True
    min_bayesian_posterior: float = 0.55
    min_final_rank_score: float = 0.50
    max_break_risk: float = 0.65
    max_microstructure_risk: float = 0.70
    min_liquidity_score: float | None = None
    require_hard_validation: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", _coerce_bool(self.enabled))
        object.__setattr__(self, "min_bayesian_posterior", float(self.min_bayesian_posterior))
        object.__setattr__(self, "min_final_rank_score", float(self.min_final_rank_score))
        object.__setattr__(self, "max_break_risk", float(self.max_break_risk))
        object.__setattr__(self, "max_microstructure_risk", float(self.max_microstructure_risk))
        object.__setattr__(self, "min_liquidity_score", _optional_float(self.min_liquidity_score))
        object.__setattr__(self, "require_hard_validation", _coerce_bool(self.require_hard_validation))


@dataclass(frozen=True)
class ReplayMLScoreSnapshot:
    pair: str | None = None
    timestamp: int | float | None = None
    score_source: MLScoreSource | str = MLScoreSource.UNAVAILABLE

    hard_validation_valid: bool | None = None
    regime_name: str | None = None
    regime_confidence: float | None = None
    break_risk: float | None = None
    bayesian_posterior: float | None = None
    bayesian_quality_grade: str | None = None
    final_rank_score: float | None = None
    microstructure_risk: float | None = None
    liquidity_score: float | None = None
    ev_hold_value_usdt: float | None = None
    exit_score: float | None = None
    quality_gate_passed: bool | None = None

    block_reasons: tuple[BlockReason, ...] = ()
    warning: str | None = None
    metadata: Mapping[str, Any] | tuple[tuple[str, object], ...] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "pair", _normalize_text(self.pair))
        object.__setattr__(self, "timestamp", _optional_int_timestamp(self.timestamp))
        object.__setattr__(self, "score_source", _coerce_score_source(self.score_source))
        object.__setattr__(self, "hard_validation_valid", _optional_bool(self.hard_validation_valid))
        object.__setattr__(self, "regime_name", _normalize_text(self.regime_name))
        object.__setattr__(self, "regime_confidence", _optional_float(self.regime_confidence))
        object.__setattr__(self, "break_risk", _optional_float(self.break_risk))
        object.__setattr__(self, "bayesian_posterior", _optional_float(self.bayesian_posterior))
        object.__setattr__(self, "bayesian_quality_grade", _normalize_text(self.bayesian_quality_grade))
        object.__setattr__(self, "final_rank_score", _optional_float(self.final_rank_score))
        object.__setattr__(self, "microstructure_risk", _optional_float(self.microstructure_risk))
        object.__setattr__(self, "liquidity_score", _optional_float(self.liquidity_score))
        object.__setattr__(self, "ev_hold_value_usdt", _optional_float(self.ev_hold_value_usdt))
        object.__setattr__(self, "exit_score", _optional_float(self.exit_score))
        object.__setattr__(self, "quality_gate_passed", _optional_bool(self.quality_gate_passed))
        object.__setattr__(self, "block_reasons", _block_reason_tuple(self.block_reasons))
        object.__setattr__(self, "warning", _normalize_text(self.warning))
        object.__setattr__(self, "metadata", _metadata_tuple(self.metadata))

    @property
    def available(self) -> bool:
        return self.score_source != MLScoreSource.UNAVAILABLE

    def to_marker_metadata(self) -> dict[str, Any]:
        payload = {
            "score_source": self.score_source.value,
            "hard_validation_valid": self.hard_validation_valid,
            "regime_name": self.regime_name,
            "regime_confidence": self.regime_confidence,
            "break_risk": self.break_risk,
            "bayesian_posterior": self.bayesian_posterior,
            "bayesian_quality_grade": self.bayesian_quality_grade,
            "final_rank_score": self.final_rank_score,
            "microstructure_risk": self.microstructure_risk,
            "liquidity_score": self.liquidity_score,
            "ev_hold_value_usdt": self.ev_hold_value_usdt,
            "exit_score": self.exit_score,
            "quality_gate_passed": self.quality_gate_passed,
        }
        if self.timestamp is not None:
            payload["ml_score_timestamp"] = self.timestamp
        if self.block_reasons:
            payload["ml_block_reasons"] = [reason.value for reason in self.block_reasons]
        if self.warning:
            payload["ml_score_warning"] = self.warning
        return payload

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "timestamp": self.timestamp,
            "score_source": self.score_source.value,
            "hard_validation_valid": self.hard_validation_valid,
            "regime_name": self.regime_name,
            "regime_confidence": self.regime_confidence,
            "break_risk": self.break_risk,
            "bayesian_posterior": self.bayesian_posterior,
            "bayesian_quality_grade": self.bayesian_quality_grade,
            "final_rank_score": self.final_rank_score,
            "microstructure_risk": self.microstructure_risk,
            "liquidity_score": self.liquidity_score,
            "ev_hold_value_usdt": self.ev_hold_value_usdt,
            "exit_score": self.exit_score,
            "quality_gate_passed": self.quality_gate_passed,
            "block_reasons": [reason.value for reason in self.block_reasons],
            "warning": self.warning,
            "metadata": {key: _json_value(value) for key, value in self.metadata},
        }


def freeze_ml_gate_config(value: ReplayMLGateConfig | Mapping[str, Any] | None) -> ReplayMLGateConfig:
    if isinstance(value, ReplayMLGateConfig):
        return value
    if isinstance(value, Mapping):
        return ReplayMLGateConfig(
            enabled=value.get("enabled", True),
            min_bayesian_posterior=value.get("min_bayesian_posterior", 0.55),
            min_final_rank_score=value.get("min_final_rank_score", 0.50),
            max_break_risk=value.get("max_break_risk", 0.65),
            max_microstructure_risk=value.get("max_microstructure_risk", 0.70),
            min_liquidity_score=value.get("min_liquidity_score"),
            require_hard_validation=value.get("require_hard_validation", True),
        )
    return ReplayMLGateConfig()


def unavailable_ml_score(
    pair: str | None,
    timestamp: int | float | datetime | str | None,
    *,
    warning: str | None = None,
) -> ReplayMLScoreSnapshot:
    return ReplayMLScoreSnapshot(
        pair=pair,
        timestamp=timestamp,
        score_source=MLScoreSource.UNAVAILABLE,
        warning=warning,
    )


def _coerce_score_source(value: MLScoreSource | str) -> MLScoreSource:
    if isinstance(value, MLScoreSource):
        return value
    try:
        return MLScoreSource(str(value))
    except ValueError:
        return MLScoreSource.UNAVAILABLE


def _block_reason_tuple(value: Any) -> tuple[BlockReason, ...]:
    if value is None:
        return ()
    if isinstance(value, BlockReason):
        return (value,)
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        values = tuple(value)
    else:
        values = (value,)

    reasons: list[BlockReason] = []
    seen: set[BlockReason] = set()
    for item in values:
        if isinstance(item, BlockReason):
            reason = item
        else:
            try:
                reason = BlockReason(str(item))
            except ValueError:
                continue
        if reason in seen:
            continue
        seen.add(reason)
        reasons.append(reason)
    return tuple(reasons)


def _metadata_tuple(value: Any) -> tuple[tuple[str, object], ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping):
        return tuple(
            (str(key), _freeze_metadata_value(item))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    if isinstance(value, tuple):
        output: list[tuple[str, object]] = []
        for item in value:
            if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)) and len(item) == 2:
                output.append((str(item[0]), _freeze_metadata_value(item[1])))
        return tuple(output)
    return (("value", _freeze_metadata_value(value)),)


def _freeze_metadata_value(value: Any) -> object:
    if isinstance(value, Mapping):
        return tuple(
            (str(key), _freeze_metadata_value(item))
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        )
    if isinstance(value, list):
        return tuple(_freeze_metadata_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_metadata_value(item) for item in value)
    if isinstance(value, Enum):
        return value.value
    return value


def _json_value(value: Any) -> Any:
    if isinstance(value, tuple):
        if all(isinstance(item, tuple) and len(item) == 2 for item in value):
            return {str(key): _json_value(item) for key, item in value}
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return _coerce_bool(value)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on", "enabled"}


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int_timestamp(value: Any) -> int | None:
    timestamp = _coerce_timestamp(value)
    return int(timestamp) if timestamp is not None else None


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


__all__ = [
    "MLScoreSource",
    "ML_REPLAY_MARKER_METADATA_FIELDS",
    "ReplayMLGateConfig",
    "ReplayMLScoreSnapshot",
    "freeze_ml_gate_config",
    "unavailable_ml_score",
]
