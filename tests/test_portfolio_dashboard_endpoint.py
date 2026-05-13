from __future__ import annotations

from Platform.api.app.routers import admin


def test_admin_portfolio_dashboard_route_is_read_only_get() -> None:
    route = next(
        route
        for route in admin.router.routes
        if getattr(route, "path", None) == "/admin/dashboard/portfolio"
    )

    assert route.methods == {"GET"}
