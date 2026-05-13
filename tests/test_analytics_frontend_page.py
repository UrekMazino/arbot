from __future__ import annotations

from pathlib import Path


ANALYTICS_PAGE = Path("Platform/web/app/admin/dashboard/analytics/page.tsx")
ADMIN_ACCESS = Path("Platform/web/lib/admin-access.ts")


def test_existing_analytics_page_route_exists() -> None:
    assert ANALYTICS_PAGE.exists()


def test_analytics_page_calls_standardized_api() -> None:
    source = ANALYTICS_PAGE.read_text(encoding="utf-8")

    assert "getAnalyticsDashboard" in source
    assert "getPerformanceHistory" not in source
    assert "getRunAdvancedMLAnalytics" not in source


def test_analytics_page_renders_major_sections() -> None:
    source = ANALYTICS_PAGE.read_text(encoding="utf-8")

    for label in (
        "Total PnL",
        "Pair Leaderboards",
        "Exit Policy Analysis",
        "ML Analysis",
        "Hedge-Ratio Analysis",
    ):
        assert label in source


def test_analytics_page_handles_null_and_unavailable_metrics() -> None:
    source = ANALYTICS_PAGE.read_text(encoding="utf-8")

    assert "n/a" in source
    assert "No data available yet." in source
    assert "No exit orchestrator data available yet." in source


def test_analytics_page_has_refresh_behavior() -> None:
    source = ANALYTICS_PAGE.read_text(encoding="utf-8")

    assert "Refresh" in source
    assert "refresh: forceRefresh" in source


def test_analytics_route_access_remains_configured() -> None:
    source = ADMIN_ACCESS.read_text(encoding="utf-8")

    assert 'href: "/admin/dashboard/analytics"' in source
    assert 'requiredPermissions: ["view_analytics", "view_dashboard"]' in source
