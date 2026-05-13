from __future__ import annotations

from pathlib import Path


def test_frontend_dashboard_type_exports_exist() -> None:
    api_types = Path("Platform/web/lib/api.ts").read_text(encoding="utf-8")

    for exported_type in (
        "DashboardTag",
        "DashboardCacheMeta",
        "TradeSummary",
        "PairSummary",
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
