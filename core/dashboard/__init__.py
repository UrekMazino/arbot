"""Shared read-only dashboard contracts."""

from core.dashboard.contracts import (
    AnalyticsSummary,
    CounterfactualSummary,
    DashboardCacheMeta,
    DashboardTag,
    DecisionScoreSummary,
    HedgeRatioSummary,
    PairPerformanceSummary,
    PairSummary,
    PortfolioSummary,
    ReplaySignalSummary,
    RiskEventSummary,
    TradeSummary,
    SUPPORTED_DASHBOARD_TAGS,
)

__all__ = [
    "AnalyticsSummary",
    "CounterfactualSummary",
    "DashboardCacheMeta",
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
