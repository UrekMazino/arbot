from __future__ import annotations

import re
from pathlib import Path


ADMIN_ACCESS = Path("Platform/web/lib/admin-access.ts")
APP_SIDEBAR = Path("Platform/web/components/layout/app-sidebar.tsx")
DASHBOARD_REDIRECT = Path("Platform/web/app/admin/dashboard/page.tsx")


def _source() -> str:
    return ADMIN_ACCESS.read_text(encoding="utf-8")


def _sidebar_source() -> str:
    return APP_SIDEBAR.read_text(encoding="utf-8")


def test_portfolio_nav_item_exists_with_correct_route_and_permissions() -> None:
    source = _source()

    assert 'href: "/admin/dashboard/portfolio"' in source
    assert 'label: "Portfolio"' in source
    assert 'requiredPermissions: ["view_portfolio", "view_dashboard"]' in source


def test_analytics_nav_item_exists_with_correct_route_and_permissions() -> None:
    source = _source()

    assert 'href: "/admin/dashboard/analytics"' in source
    assert 'label: "Analytics"' in source
    assert 'requiredPermissions: ["view_analytics", "view_dashboard"]' in source


def test_risk_health_nav_item_exists_with_correct_route_and_permissions() -> None:
    source = _source()

    assert 'href: "/admin/dashboard/risk-health"' in source
    assert 'label: "Risk & Health"' in source
    assert 'requiredPermissions: ["view_dashboard"]' in source


def test_pair_history_nav_item_exists_with_correct_route_and_permissions() -> None:
    source = _source()

    assert 'href: "/admin/dashboard/pairs/history"' in source
    assert 'label: "Pair History"' in source
    assert 'requiredPermissions: ["view_pair_universe", "view_dashboard"]' in source


def test_pair_detail_route_access_exists_but_is_hidden_from_sidebar() -> None:
    source = _source()
    sidebar = _sidebar_source()

    assert 'href: "/admin/dashboard/pair-detail"' in source
    assert 'label: "Pair Detail"' in source
    assert "hiddenFromSidebar: true" in source
    assert "visibleChildren = item.children?.filter((child) => !child.hiddenFromSidebar)" in sidebar


def test_chart_decision_audit_route_is_preserved() -> None:
    source = _source()

    assert 'href: "/admin/dashboard/cointegrated-pair"' in source
    assert 'label: "Chart Decision Audit"' in source
    assert 'requiredPermissions: ["view_pair_universe", "view_dashboard"]' in source


def test_console_logs_settings_and_access_entries_are_preserved() -> None:
    source = _source()

    for href, label in (
        ("/admin/console", "Console"),
        ("/admin/console/logs", "Logs"),
        ("/admin/settings", "Settings"),
        ("/admin/access", "Access"),
    ):
        assert f'href: "{href}"' in source
        assert f'label: "{label}"' in source
    assert 'requiredPermissions: ["view_logs", "manage_bot"]' in source
    assert 'requiredPermissions: ["view_logs"]' in source
    assert 'requiredPermissions: ["edit_settings", "manage_api"]' in source
    assert 'requiredPermissions: ["manage_users", "manage_roles"]' in source


def test_permission_helpers_still_drive_route_visibility_and_access() -> None:
    source = _source()

    assert "hasAnyPermission(user, item.requiredPermissions)" in source
    assert "hasAnyPermission(user, child.requiredPermissions)" in source
    assert "return hasAnyPermission(user, navItem.requiredPermissions)" in source
    assert "normalizeAdminPath(href)" in source


def test_active_route_matching_handles_dashboard_routes_and_pair_detail_query() -> None:
    source = _source()
    sidebar = _sidebar_source()

    for route in (
        "/admin/dashboard/portfolio",
        "/admin/dashboard/analytics",
        "/admin/dashboard/risk-health",
        "/admin/dashboard/pairs/history",
        "/admin/dashboard/pair-detail",
    ):
        assert route in source
    assert "split(/[?#]/)" in source
    assert "split(/[?#]/)" in sidebar
    assert "normalizeHref(child.href) === normalizedActiveHref" in sidebar


def test_no_duplicate_nav_hrefs() -> None:
    hrefs = re.findall(r'href:\s*"([^"]+)"', _source())
    duplicates = sorted({href for href in hrefs if hrefs.count(href) > 1})

    assert duplicates == []


def test_dashboard_redirect_is_preserved() -> None:
    source = DASHBOARD_REDIRECT.read_text(encoding="utf-8")

    assert 'redirect("/admin/dashboard/analytics")' in source
