"""Read-only dashboard DTOs.

These contracts describe analytics/visualization payloads only. They do not
query live trading state, submit orders, modify strategy logic, or compute new
ML signals.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any


class DashboardTag(str, Enum):
    ELITE = "elite"
    STABLE = "stable"
    WARNING = "warning"
    HOSPITAL = "hospital"
    GRAVEYARD = "graveyard"
    HIGH_DRIFT = "high_drift"
    HIGH_SLIPPAGE = "high_slippage"
    GOOD_REVERTER = "good_reverter"
    BAD_EXECUTOR = "bad_executor"
    HIGH_BREAK_RISK = "high_break_risk"
    PROFITABLE = "profitable"
    LOSING = "losing"


SUPPORTED_DASHBOARD_TAGS: tuple[str, ...] = tuple(tag.value for tag in DashboardTag)


@dataclass
class DashboardDTO:
    """Mixin for JSON-safe dashboard payloads."""

    def to_dict(self) -> dict[str, Any]:
        return {
            item.name: _json_value(getattr(self, item.name))
            for item in fields(self)
        }


@dataclass
class DashboardCacheMeta(DashboardDTO):
    cache_hit: bool = False
    generated_at: int | float | None = None
    ttl_seconds: int | None = None
    refresh_supported: bool = True


@dataclass
class TradeSummary(DashboardDTO):
    trade_id: str
    pair: str
    side: str | None = None
    entry_time: int | float | None = None
    exit_time: int | float | None = None
    entry_z: float | None = None
    exit_z: float | None = None
    hold_seconds: float | None = None
    pnl_usdt: float | None = None
    fees_usdt: float | None = None
    slippage_usdt: float | None = None
    exit_reason: str | None = None
    entry_hedge_ratio: float | None = None
    exit_hedge_ratio: float | None = None
    hedge_ratio_drift_pct: float | None = None
    regime_at_entry: str | None = None
    final_rank_score_at_entry: float | None = None
    bayesian_posterior_at_entry: float | None = None


@dataclass
class PairSummary(DashboardDTO):
    pair: str
    status: str | None = None
    total_trades: int | None = None
    net_pnl_usdt: float | None = None
    realized_pnl_usdt: float | None = None
    unrealized_pnl_usdt: float | None = None
    win_rate: float | None = None
    profit_factor: float | None = None
    max_drawdown_usdt: float | None = None
    avg_hold_seconds: float | None = None
    avg_entry_z: float | None = None
    avg_exit_z: float | None = None
    avg_hedge_ratio: float | None = None
    avg_hedge_drift_pct: float | None = None
    hospital_count: int | None = None
    graveyard_count: int | None = None
    block_reason_counts: Mapping[str, int] = field(default_factory=dict)
    best_trade: TradeSummary | Mapping[str, Any] | None = None
    worst_trade: TradeSummary | Mapping[str, Any] | None = None
    last_traded_at: int | float | None = None
    tags: Sequence[str | DashboardTag] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.block_reason_counts = _int_count_mapping(self.block_reason_counts)
        self.tags = list(_normalize_tags(self.tags))


@dataclass
class PairPerformanceSummary(DashboardDTO):
    pair: str | None = None
    total_trades: int | None = None
    net_pnl_usdt: float | None = None
    win_rate: float | None = None
    profit_factor: float | None = None
    max_drawdown_usdt: float | None = None
    avg_hold_seconds: float | None = None
    best_trade: TradeSummary | Mapping[str, Any] | None = None
    worst_trade: TradeSummary | Mapping[str, Any] | None = None
    tags: Sequence[str | DashboardTag] = field(default_factory=list)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.tags = list(_normalize_tags(self.tags))
        self.metadata = dict(self.metadata or {})


@dataclass
class ReplaySignalSummary(DashboardDTO):
    pair: str | None = None
    total_markers: int | None = None
    entry_candidates: int | None = None
    exit_candidates: int | None = None
    blocked_signals: int | None = None
    valid_candidates: int | None = None
    blocked_candidates: int | None = None
    candidate_to_actual_conversion_rate: float | None = None
    block_reason_counts: Mapping[str, int] = field(default_factory=dict)
    latest_signal_at: int | float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.block_reason_counts = _int_count_mapping(self.block_reason_counts)
        self.metadata = dict(self.metadata or {})


@dataclass
class CounterfactualSummary(DashboardDTO):
    best_exit_policy: str | None = None
    avg_missed_profit_usdt: float | None = None
    avg_avoided_loss_usdt: float | None = None
    studies_count: int | None = None
    policy_win_counts: Mapping[str, int] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.policy_win_counts = _int_count_mapping(self.policy_win_counts)
        self.metadata = dict(self.metadata or {})


@dataclass
class DecisionScoreSummary(DashboardDTO):
    score_source: str | None = None
    avg_regime_confidence: float | None = None
    avg_break_risk: float | None = None
    avg_bayesian_posterior: float | None = None
    avg_final_rank_score: float | None = None
    avg_liquidity_score: float | None = None
    avg_microstructure_risk: float | None = None
    avg_ev_hold_value_usdt: float | None = None
    avg_exit_score: float | None = None
    quality_gate_pass_rate: float | None = None
    unavailable_count: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.metadata = dict(self.metadata or {})


@dataclass
class HedgeRatioSummary(DashboardDTO):
    avg_hedge_ratio: float | None = None
    avg_hedge_drift_pct: float | None = None
    max_hedge_drift_pct: float | None = None
    high_drift_count: int | None = None
    sizing_pnl_delta_usdt: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.metadata = dict(self.metadata or {})


@dataclass
class RiskEventSummary(DashboardDTO):
    severity: str | None = None
    type: str | None = None
    message: str | None = None
    pair: str | None = None
    latest_timestamp: int | float | None = None
    occurrence_count: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.metadata = dict(self.metadata or {})


@dataclass
class PortfolioSummary(DashboardDTO):
    total_equity_usdt: float | None = None
    session_pnl_usdt: float | None = None
    realized_pnl_usdt: float | None = None
    unrealized_pnl_usdt: float | None = None
    win_rate: float | None = None
    profit_factor: float | None = None
    max_drawdown_usdt: float | None = None
    open_positions: Sequence[Mapping[str, Any]] | None = None
    active_pair: str | None = None
    bot_status: str | None = None
    open_exposure_usdt: float | None = None
    cache: DashboardCacheMeta | Mapping[str, Any] = field(default_factory=DashboardCacheMeta)

    def __post_init__(self) -> None:
        if self.open_positions is not None:
            self.open_positions = list(self.open_positions)


@dataclass
class AnalyticsSummary(DashboardDTO):
    performance: Mapping[str, Any] = field(default_factory=dict)
    pnl_timeseries: Sequence[Mapping[str, Any]] = field(default_factory=list)
    pair_leaderboards: Sequence[PairPerformanceSummary | Mapping[str, Any]] = field(default_factory=list)
    exit_analysis: CounterfactualSummary | Mapping[str, Any] | None = None
    ml_analysis: DecisionScoreSummary | Mapping[str, Any] | None = None
    hedge_analysis: HedgeRatioSummary | Mapping[str, Any] | None = None
    cache: DashboardCacheMeta | Mapping[str, Any] = field(default_factory=DashboardCacheMeta)

    def __post_init__(self) -> None:
        self.performance = dict(self.performance or {})
        self.pnl_timeseries = list(self.pnl_timeseries or [])
        self.pair_leaderboards = list(self.pair_leaderboards or [])


def _normalize_tags(tags: Sequence[str | DashboardTag] | None) -> tuple[str, ...]:
    if not tags:
        return ()
    normalized: list[str] = []
    seen: set[str] = set()
    for item in tags:
        value = item.value if isinstance(item, DashboardTag) else str(item or "").strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return tuple(normalized)


def _int_count_mapping(value: Mapping[str, Any] | None) -> dict[str, int]:
    if not value:
        return {}
    result: dict[str, int] = {}
    for key, raw_count in value.items():
        text = str(key or "").strip()
        if not text:
            continue
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            continue
        result[text] = count
    return result


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if is_dataclass(value):
        return {
            item.name: _json_value(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    return value


__all__ = [
    "AnalyticsSummary",
    "CounterfactualSummary",
    "DashboardCacheMeta",
    "DashboardDTO",
    "DashboardTag",
    "DecisionScoreSummary",
    "HedgeRatioSummary",
    "PairPerformanceSummary",
    "PairSummary",
    "PortfolioSummary",
    "ReplaySignalSummary",
    "RiskEventSummary",
    "SUPPORTED_DASHBOARD_TAGS",
    "TradeSummary",
]
