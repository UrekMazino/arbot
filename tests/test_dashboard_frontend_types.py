from __future__ import annotations

from pathlib import Path


def test_frontend_dashboard_type_exports_exist() -> None:
    api_types = Path("Platform/web/lib/api.ts").read_text(encoding="utf-8")

    for exported_type in (
        "DashboardTag",
        "DashboardCacheMeta",
        "TradeSummary",
        "PairSummary",
        "PairHistoryResponse",
        "PairPerformanceSummary",
        "ReplaySignalSummary",
        "CounterfactualSummary",
        "DecisionScoreSummary",
        "HedgeRatioSummary",
        "RiskEventSummary",
        "PortfolioSummary",
        "PortfolioDashboardResponse",
        "AnalyticsSummary",
    ):
        assert f"export type {exported_type}" in api_types

    assert "export async function getPortfolioDashboard" in api_types
    assert "export async function getPairHistory" in api_types
    for query_param in (
        "start_ts",
        "end_ts",
        "pnl_filter",
        "min_trade_count",
        "min_win_rate",
        "max_win_rate",
        "hedge_drift_filter",
        "significant_only",
        "sort_by",
        "sort_dir",
        "page_size",
    ):
        assert f'"{query_param}"' in api_types
