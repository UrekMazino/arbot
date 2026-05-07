"""Marker contracts for the chart decision audit dashboard.

These are data contracts only. They do not infer chart signals, run replay, or
change live trading behavior.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Any, TypeAlias


class MarkerCategory(str, Enum):
    STATISTICAL = "statistical"
    REPLAY = "replay"
    ACTUAL = "actual"


class StatisticalMarkerType(str, Enum):
    HISTORICAL_MEAN_CROSSING = "historical_mean_crossing"
    ZERO_CROSSING = "zero_crossing"
    EXTREME_Z_PEAK = "extreme_z_peak"


class ReplayMarkerType(str, Enum):
    REPLAY_ENTRY_CANDIDATE = "replay_entry_candidate"
    REPLAY_EXIT_CANDIDATE = "replay_exit_candidate"
    REPLAY_BLOCKED_SIGNAL = "replay_blocked_signal"


class ActualMarkerType(str, Enum):
    ACTUAL_ENTRY = "actual_entry"
    ACTUAL_EXIT = "actual_exit"
    ACTUAL_PARTIAL_EXIT = "actual_partial_exit"
    ACTUAL_BLOCKED_SIGNAL = "actual_blocked_signal"
    ACTUAL_REGIME_EXIT = "actual_regime_exit"
    ACTUAL_MANUAL_EXIT = "actual_manual_exit"
    ACTUAL_ADVANCED_ML_SHADOW_RECOMMENDATION = "actual_advanced_ml_shadow_recommendation"


class CuratorState(str, Enum):
    TRADABLE = "tradable"
    ANALYSIS_ONLY = "analysis_only"
    EXCLUDED = "excluded"
    HOSPITAL = "hospital"
    GRAVEYARD = "graveyard"
    STALE_DATA = "stale_data"
    INSUFFICIENT_HISTORY = "insufficient_history"
    LOW_LIQUIDITY = "low_liquidity"


class BlockReason(str, Enum):
    CURATOR_NOT_TRADABLE = "curator_not_tradable"
    ANALYSIS_ONLY = "analysis_only"
    PAIR_EXCLUDED = "pair_excluded"
    PAIR_IN_HOSPITAL = "pair_in_hospital"
    PAIR_IN_GRAVEYARD = "pair_in_graveyard"
    STALE_DATA = "stale_data"
    INSUFFICIENT_HISTORY = "insufficient_history"
    COINTEGRATION_INVALID = "cointegration_invalid"
    ADF_FAILED = "adf_failed"
    ZERO_CROSSINGS_TOO_LOW = "zero_crossings_too_low"
    HEDGE_RATIO_UNSTABLE = "hedge_ratio_unstable"
    LIQUIDITY_FAILED = "liquidity_failed"
    ORDER_CAPACITY_FAILED = "order_capacity_failed"
    QUALITY_GATE_FAILED = "quality_gate_failed"
    POSITION_ALREADY_OPEN = "position_already_open"
    ORDERBOOK_STALE = "orderbook_stale"
    REGIME_BREAK_RISK_HIGH = "regime_break_risk_high"
    Z_PERSISTENCE_FAILED = "z_persistence_failed"
    CONFIG_UNAVAILABLE = "config_unavailable"
    CURATOR_STATE_UNAVAILABLE = "curator_state_unavailable"
    CURATOR_LOW_LIQUIDITY = "curator_low_liquidity"


def build_actual_entry_id(trade_id: str) -> str:
    trade_id_text = str(trade_id or "").strip()
    if not trade_id_text:
        raise ValueError("actual entry_id requires a non-empty trade_id")
    return f"actual_{trade_id_text}"


def build_replay_entry_id(pair_key: str, timestamp: int | float | str, side: str) -> str:
    pair_key_text = str(pair_key or "").strip()
    timestamp_text = str(timestamp or "").strip()
    side_text = str(side or "").strip()
    if not pair_key_text:
        raise ValueError("replay entry_id requires a non-empty pair_key")
    if not timestamp_text:
        raise ValueError("replay entry_id requires a non-empty timestamp")
    if not side_text:
        raise ValueError("replay entry_id requires a non-empty side")
    return f"replay_{pair_key_text}_{timestamp_text}_{side_text}"


@dataclass(frozen=True)
class ActualMarkerBase:
    timestamp: int | float
    original_event_timestamp: int | float | None = None
    side: str | None = None
    z_score: float | None = None
    spread: float | None = None
    trade_id: str | None = None
    reason: str | None = None
    pnl_usdt: float | None = None
    fees_usdt: float | None = None
    slippage_usdt: float | None = None
    timestamp_alignment: str = "exact"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    marker_category: MarkerCategory = field(default=MarkerCategory.ACTUAL, init=False)
    marker_type: ActualMarkerType = field(init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            item.name: _to_json_value(getattr(self, item.name))
            for item in fields(self)
        }


@dataclass(frozen=True)
class ActualEntryMarker(ActualMarkerBase):
    entry_id: str | None = None
    marker_type: ActualMarkerType = field(default=ActualMarkerType.ACTUAL_ENTRY, init=False)

    def __post_init__(self) -> None:
        if not str(self.trade_id or "").strip():
            raise ValueError("ActualEntryMarker requires trade_id")
        if self.entry_id is None:
            object.__setattr__(self, "entry_id", build_actual_entry_id(str(self.trade_id)))


@dataclass(frozen=True)
class ActualExitMarker(ActualMarkerBase):
    marker_type: ActualMarkerType = field(default=ActualMarkerType.ACTUAL_EXIT, init=False)


@dataclass(frozen=True)
class ActualPartialExitMarker(ActualMarkerBase):
    exit_percentage: float | None = None
    marker_type: ActualMarkerType = field(default=ActualMarkerType.ACTUAL_PARTIAL_EXIT, init=False)


@dataclass(frozen=True)
class ActualBlockedSignalMarker(ActualMarkerBase):
    block_reasons: tuple[BlockReason, ...] = ()
    marker_type: ActualMarkerType = field(default=ActualMarkerType.ACTUAL_BLOCKED_SIGNAL, init=False)


@dataclass(frozen=True)
class ActualRegimeExitMarker(ActualExitMarker):
    marker_type: ActualMarkerType = field(default=ActualMarkerType.ACTUAL_REGIME_EXIT, init=False)


@dataclass(frozen=True)
class ActualManualExitMarker(ActualExitMarker):
    marker_type: ActualMarkerType = field(default=ActualMarkerType.ACTUAL_MANUAL_EXIT, init=False)


@dataclass(frozen=True)
class ActualAdvancedMLShadowRecommendationMarker(ActualMarkerBase):
    shadow_action: str | None = None
    executed: bool = False
    exit_score: float | None = None
    ev_hold_value_usdt: float | None = None
    regime: str | None = None
    marker_type: ActualMarkerType = field(
        default=ActualMarkerType.ACTUAL_ADVANCED_ML_SHADOW_RECOMMENDATION,
        init=False,
    )


ActualMarker: TypeAlias = (
    ActualEntryMarker
    | ActualExitMarker
    | ActualPartialExitMarker
    | ActualBlockedSignalMarker
    | ActualRegimeExitMarker
    | ActualManualExitMarker
    | ActualAdvancedMLShadowRecommendationMarker
)


def _to_json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_to_json_value(item) for item in value]
    if isinstance(value, list):
        return [_to_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    return value


__all__ = [
    "ActualAdvancedMLShadowRecommendationMarker",
    "ActualBlockedSignalMarker",
    "ActualEntryMarker",
    "ActualExitMarker",
    "ActualManualExitMarker",
    "ActualMarker",
    "ActualMarkerBase",
    "ActualMarkerType",
    "ActualPartialExitMarker",
    "ActualRegimeExitMarker",
    "BlockReason",
    "CuratorState",
    "MarkerCategory",
    "ReplayMarkerType",
    "StatisticalMarkerType",
    "build_actual_entry_id",
    "build_replay_entry_id",
]
