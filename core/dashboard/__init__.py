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
from core.dashboard.portfolio_service import (
    PortfolioDataBundle,
    clear_portfolio_dashboard_cache,
    get_portfolio_dashboard,
)
from core.dashboard.pair_history_service import (
    PairHistoryDataBundle,
    clear_pair_history_cache,
    get_pair_history_summary,
)

__all__ = [
    "AnalyticsSummary",
    "CounterfactualSummary",
    "DashboardCacheMeta",
    "DashboardTag",
    "DecisionScoreSummary",
    "HedgeRatioSummary",
    "PairPerformanceSummary",
    "PairHistoryDataBundle",
    "PairSummary",
    "PortfolioDataBundle",
    "PortfolioSummary",
    "ReplaySignalSummary",
    "RiskEventSummary",
    "SUPPORTED_DASHBOARD_TAGS",
    "TradeSummary",
    "clear_portfolio_dashboard_cache",
    "clear_pair_history_cache",
    "get_pair_history_summary",
    "get_portfolio_dashboard",
]
