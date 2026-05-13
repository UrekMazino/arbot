from __future__ import annotations

import inspect
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from Platform.api.app.routers import admin


def _risk_health_route():
    return next(
        route
        for route in admin.router.routes
        if getattr(route, "path", None) == "/admin/dashboard/risk-health"
    )


def _client_with_permission_override() -> TestClient:
    app = FastAPI()
    app.include_router(admin.router)
    route = _risk_health_route()
    for dependency in route.dependant.dependencies:
        app.dependency_overrides[dependency.call] = lambda: object()
    return TestClient(app)


def _fake_response() -> dict[str, Any]:
    return {
        "bot_status": {},
        "risk_kpis": {
            "current_drawdown_usdt": None,
            "daily_loss_limit_usage_pct": None,
            "open_exposure_usdt": None,
            "open_positions": None,
            "orphan_desync_status": None,
            "api_latency_ms": None,
            "order_failure_count": None,
            "orderbook_stale_count": None,
        },
        "pair_health": {
            "hospital_pairs": [],
            "graveyard_pairs": [],
            "high_break_risk_pairs": [],
            "high_hedge_drift_positions": [],
            "liquidity_stress_pairs": [],
        },
        "alerts": [],
        "cache": {
            "cache_hit": False,
            "generated_at": 1_715_000_000,
            "ttl_seconds": 30,
            "refresh_supported": True,
        },
    }


def test_risk_health_endpoint_returns_standard_sections(monkeypatch):
    monkeypatch.setattr(admin, "_get_risk_health_dashboard_service", lambda: lambda **_: _fake_response())
    client = _client_with_permission_override()

    response = client.get("/admin/dashboard/risk-health")

    assert response.status_code == 200
    assert set(response.json()) == {"bot_status", "risk_kpis", "pair_health", "alerts", "cache"}


def test_risk_health_query_params_are_passed_to_service(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_service(**kwargs):
        captured.update(kwargs)
        return _fake_response()

    monkeypatch.setattr(admin, "_get_risk_health_dashboard_service", lambda: fake_service)
    client = _client_with_permission_override()

    response = client.get(
        "/admin/dashboard/risk-health",
        params={"start_ts": 1, "end_ts": 2, "refresh": "true"},
    )

    assert response.status_code == 200
    assert captured == {"start_ts": 1.0, "end_ts": 2.0, "refresh": True}


def test_risk_health_permission_dependency_is_applied() -> None:
    route = _risk_health_route()
    assert route.methods == {"GET"}
    assert route.dependant.dependencies
    dependency = route.dependant.dependencies[0].call
    closure_values = [cell.cell_contents for cell in dependency.__closure__ or ()]

    assert {"view_dashboard"} in closure_values


def test_risk_health_endpoint_is_read_only_and_avoids_order_execution() -> None:
    source = inspect.getsource(admin.admin_risk_health_dashboard) + inspect.getsource(admin._get_risk_health_dashboard_service)

    for forbidden in (
        "submit_order",
        "place_order",
        "execute_order",
        "order_execution",
        "ExecutionManager",
        "func_trade",
        "func_close_positions",
    ):
        assert forbidden not in source


def test_risk_health_endpoint_does_not_call_live_current_ml_runtime() -> None:
    source = inspect.getsource(admin.admin_risk_health_dashboard) + inspect.getsource(admin._get_risk_health_dashboard_service)

    for forbidden in (
        "advanced_ml_runtime",
        "Execution.advanced_ml_runtime",
        "get_live_ml",
        "current_model_memory",
    ):
        assert forbidden not in source
