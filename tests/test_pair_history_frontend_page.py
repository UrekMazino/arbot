from __future__ import annotations

from pathlib import Path


PAIR_HISTORY_PAGE = Path("Platform/web/app/admin/dashboard/pairs/history/page.tsx")
ADMIN_ACCESS = Path("Platform/web/lib/admin-access.ts")


def test_pair_history_page_uses_pair_history_api_and_existing_shell() -> None:
    source = PAIR_HISTORY_PAGE.read_text(encoding="utf-8")

    assert "getPairHistory" in source
    assert "DashboardShell" in source
    assert "MetricCard" in source
    assert "TableFrame" in source
    assert "StatusPill" in source


def test_pair_history_pair_detail_navigation_is_query_encoded() -> None:
    source = PAIR_HISTORY_PAGE.read_text(encoding="utf-8")

    assert "/admin/dashboard/pair-detail?pair=" in source
    assert "encodeURIComponent(pair)" in source
    assert "&timeframe=1m" in source


def test_pair_history_page_has_null_safe_empty_and_error_states() -> None:
    source = PAIR_HISTORY_PAGE.read_text(encoding="utf-8")

    assert "n/a" in source
    assert "No pairs found for the selected filters." in source
    assert "Unable to load pair history" in source
    assert "Loading pair history..." in source


def test_pair_history_route_is_admin_guarded() -> None:
    source = ADMIN_ACCESS.read_text(encoding="utf-8")

    assert 'href: "/admin/dashboard/pairs/history"' in source
    assert 'requiredPermissions: ["view_pair_universe", "view_dashboard"]' in source
