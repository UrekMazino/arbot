from __future__ import annotations

import inspect
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from Platform.api.app.routers import admin


def _analytics_route():
    return next(
        route
        for route in admin.router.routes
        if getattr(route, "path", None) == "/admin/dashboard/analytics"
    )


def _client_with_permission_override() -> TestClient:
    app = FastAPI()
    app.include_router(admin.router)
    route = _analytics_route()
    for dependency in route.dependant.dependencies:
        app.dependency_overrides[dependency.call] = lambda: object()
    return TestClient(app)


def _fake_response() -> dict[str, Any]:
    return {
        "performance": {"total_pnl_usdt": 1.0},
        "pnl_timeseries": {"daily_pnl": [], "equity_curve": [], "drawdown_curve": []},
        "pair_leaderboards": {
            "top_pairs_by_pnl": [],
            "bottom_pairs_by_pnl": [],
            "top_pairs_by_win_rate": [],
            "worst_pairs_by_drawdown": [],
            "pairs_with_high_hedge_drift": [],
            "pairs_with_frequent_blocks": [],
        },
        "exit_analysis": {
            "best_counterfactual_exit_policy": None,
            "actual_exit_efficiency": None,
            "avg_missed_profit_usdt": None,
            "avg_avoided_loss_usdt": None,
            "exit_policy_distribution": {},
        },
        "ml_analysis": {
            "pnl_by_regime": [],
            "win_rate_by_regime": [],
            "bayesian_posterior_vs_outcome": [],
            "final_rank_score_vs_outcome": [],
            "break_risk_before_losses": None,
            "microstructure_risk_vs_slippage": [],
        },
        "hedge_analysis": {
            "equal_notional_total_pnl": None,
            "hedge_ratio_sized_total_pnl": None,
            "sizing_pnl_delta_usdt": None,
            "high_drift_trade_count": None,
        },
        "cache": {
            "cache_hit": False,
            "generated_at": 1_715_000_000,
            "ttl_seconds": 900,
            "refresh_supported": True,
        },
    }


def test_analytics_endpoint_returns_standard_sections(monkeypatch):
    monkeypatch.setattr(admin, "_get_analytics_dashboard_service", lambda: lambda **_: _fake_response())
    client = _client_with_permission_override()

    response = client.get("/admin/dashboard/analytics")

    assert response.status_code == 200
    assert set(response.json()) == {
        "performance",
        "pnl_timeseries",
        "pair_leaderboards",
        "exit_analysis",
        "ml_analysis",
        "hedge_analysis",
        "cache",
    }


def test_analytics_query_params_are_passed_to_service(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_service(**kwargs):
        captured.update(kwargs)
        return _fake_response()

    monkeypatch.setattr(admin, "_get_analytics_dashboard_service", lambda: fake_service)
    client = _client_with_permission_override()

    response = client.get(
        "/admin/dashboard/analytics",
        params={"start_ts": 1, "end_ts": 2, "refresh": "true"},
    )

    assert response.status_code == 200
    assert captured == {"start_ts": 1.0, "end_ts": 2.0, "refresh": True}


def test_analytics_permission_dependency_is_applied() -> None:
    route = _analytics_route()
    assert route.methods == {"GET"}
    assert route.dependant.dependencies
    dependency = route.dependant.dependencies[0].call
    closure_values = [cell.cell_contents for cell in dependency.__closure__ or ()]

    assert {"view_analytics", "view_dashboard"} in closure_values


def test_analytics_endpoint_is_read_only_and_avoids_order_execution() -> None:
    source = inspect.getsource(admin.admin_analytics_dashboard) + inspect.getsource(admin._get_analytics_dashboard_service)

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


def test_analytics_endpoint_does_not_call_live_current_ml_runtime() -> None:
    source = inspect.getsource(admin.admin_analytics_dashboard) + inspect.getsource(admin._get_analytics_dashboard_service)

    for forbidden in (
        "advanced_ml_runtime",
        "Execution.advanced_ml_runtime",
        "get_live_ml",
        "current_model_memory",
    ):
        assert forbidden not in source
