from __future__ import annotations

from pathlib import Path


PAIR_DETAIL_PAGE = Path("Platform/web/app/admin/dashboard/pair-detail/page.tsx")
ADMIN_ACCESS = Path("Platform/web/lib/admin-access.ts")


def test_pair_detail_route_file_exists() -> None:
    assert PAIR_DETAIL_PAGE.exists()


def test_pair_detail_page_uses_query_param_route_not_dynamic_pair_path() -> None:
    source = PAIR_DETAIL_PAGE.read_text(encoding="utf-8")

    assert "URLSearchParams(window.location.search)" in source
    assert 'params.get("pair")' in source
    assert "decodePairQueryValue" in source
    assert "app/admin/dashboard/pairs/[pair]" not in source


def test_pair_detail_page_calls_summary_and_chart_audit_clients() -> None:
    source = PAIR_DETAIL_PAGE.read_text(encoding="utf-8")

    assert "getPairDetailSummary" in source
    assert "getPairDecisionAuditChart" in source
    assert "getCounterfactualExitStudy" in source
    assert "PairZScoreChart" in source


def test_pair_detail_page_handles_missing_pair_state() -> None:
    source = PAIR_DETAIL_PAGE.read_text(encoding="utf-8")

    assert "Pair is required" in source
    assert "Back to Pair History" in source


def test_pair_detail_page_has_required_tabs() -> None:
    source = PAIR_DETAIL_PAGE.read_text(encoding="utf-8")

    for label in (
        "Overview",
        "Trades",
        "Replay Audit",
        "Counterfactual Exits",
        "Hedge Ratio",
        "ML Scores",
        "Orderbook / Liquidity",
        "Logs",
    ):
        assert label in source


def test_pair_detail_route_access_exists() -> None:
    source = ADMIN_ACCESS.read_text(encoding="utf-8")

    assert 'href: "/admin/dashboard/pair-detail"' in source
    assert 'requiredPermissions: ["view_pair_universe", "view_dashboard"]' in source
