from __future__ import annotations

from pathlib import Path


RISK_HEALTH_PAGE = Path("Platform/web/app/admin/dashboard/risk-health/page.tsx")
ADMIN_ACCESS = Path("Platform/web/lib/admin-access.ts")


def test_risk_health_page_route_file_exists() -> None:
    assert RISK_HEALTH_PAGE.exists()


def test_risk_health_page_calls_standardized_api() -> None:
    source = RISK_HEALTH_PAGE.read_text(encoding="utf-8")

    assert "getRiskHealthDashboard" in source
    assert "getAdminBotStatus" not in source
    assert "startAdminBot" not in source
    assert "stopAdminBot" not in source


def test_risk_health_page_renders_major_sections() -> None:
    source = RISK_HEALTH_PAGE.read_text(encoding="utf-8")

    for label in (
        "Current Drawdown",
        "Active Alerts",
        "Pair Health",
        "Execution Health",
        "Risk Trend",
    ):
        assert label in source


def test_risk_health_page_handles_null_and_unavailable_metrics() -> None:
    source = RISK_HEALTH_PAGE.read_text(encoding="utf-8")

    assert "n/a" in source
    assert "No active risk alerts." in source
    assert "No pairs in this category." in source
    assert "Risk trend data unavailable." in source


def test_risk_health_page_has_refresh_behavior() -> None:
    source = RISK_HEALTH_PAGE.read_text(encoding="utf-8")

    assert "Refresh" in source
    assert "refresh: forceRefresh" in source


def test_risk_health_route_access_exists() -> None:
    source = ADMIN_ACCESS.read_text(encoding="utf-8")

    assert 'href: "/admin/dashboard/risk-health"' in source
    assert 'requiredPermissions: ["view_dashboard"]' in source


def test_risk_health_page_renders_alert_occurrence_count() -> None:
    source = RISK_HEALTH_PAGE.read_text(encoding="utf-8")

    assert "Occurrence Count" in source
    assert "occurrence_count" in source
