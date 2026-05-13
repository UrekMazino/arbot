from __future__ import annotations

import inspect
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from Platform.api.app.routers import admin


def _pair_detail_route():
    return next(
        route
        for route in admin.router.routes
        if getattr(route, "path", None) == "/admin/pairs/detail-summary"
    )


def _client_with_permission_override() -> TestClient:
    app = FastAPI()
    app.include_router(admin.router)
    route = _pair_detail_route()
    for dependency in route.dependant.dependencies:
        app.dependency_overrides[dependency.call] = lambda: object()
    return TestClient(app)


def _fake_response() -> dict[str, Any]:
    return {
        "pair": "AAA-USDT-SWAP/BBB-USDT-SWAP",
        "timeframe": "1m",
        "status": "stable",
        "summary": {
            "total_pnl_usdt": 1.0,
            "total_trades": 1,
            "win_rate": 1.0,
            "profit_factor": None,
            "avg_reversion_time_seconds": None,
            "avg_hedge_ratio": None,
            "current_hedge_ratio": None,
            "avg_hedge_drift_pct": None,
            "current_regime": None,
            "current_bayesian_posterior": None,
            "current_final_rank_score": None,
        },
        "best_trade": None,
        "worst_trade": None,
        "latest_trade": None,
        "block_reason_counts": {},
        "counterfactual_summary": {
            "best_exit_policy": None,
            "avg_missed_profit_usdt": None,
            "avg_avoided_loss_usdt": None,
            "actual_exit_efficiency": None,
        },
        "hedge_summary": {
            "avg_entry_hedge_ratio": None,
            "avg_exit_hedge_ratio": None,
            "avg_hedge_drift_pct": None,
            "equal_notional_total_pnl": None,
            "hedge_ratio_sized_total_pnl": None,
            "sizing_pnl_delta_usdt": None,
        },
        "cache": {
            "cache_hit": False,
            "generated_at": 1_715_000_000,
            "ttl_seconds": 300,
            "refresh_supported": True,
        },
    }


def test_pair_detail_endpoint_returns_expected_shape(monkeypatch):
    monkeypatch.setattr(admin, "_get_pair_detail_summary_service", lambda: lambda **_: _fake_response())
    client = _client_with_permission_override()

    response = client.get("/admin/pairs/detail-summary?pair=AAA-USDT-SWAP%2FBBB-USDT-SWAP")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "pair",
        "timeframe",
        "status",
        "summary",
        "best_trade",
        "worst_trade",
        "latest_trade",
        "block_reason_counts",
        "counterfactual_summary",
        "hedge_summary",
        "cache",
    }
    assert payload["summary"]["total_pnl_usdt"] == 1.0


def test_pair_detail_required_pair_param_is_enforced(monkeypatch):
    monkeypatch.setattr(admin, "_get_pair_detail_summary_service", lambda: lambda **_: _fake_response())
    client = _client_with_permission_override()

    response = client.get("/admin/pairs/detail-summary")

    assert response.status_code == 422


def test_pair_detail_timeframe_default_is_one_minute(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_service(**kwargs):
        captured.update(kwargs)
        return _fake_response()

    monkeypatch.setattr(admin, "_get_pair_detail_summary_service", lambda: fake_service)
    client = _client_with_permission_override()

    response = client.get("/admin/pairs/detail-summary?pair=AAA/BBB")

    assert response.status_code == 200
    assert captured["timeframe"] == "1m"


def test_pair_detail_query_params_are_passed_to_service(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_service(**kwargs):
        captured.update(kwargs)
        return _fake_response()

    monkeypatch.setattr(admin, "_get_pair_detail_summary_service", lambda: fake_service)
    client = _client_with_permission_override()

    response = client.get(
        "/admin/pairs/detail-summary",
        params={
            "pair": "AAA/BBB",
            "timeframe": "5m",
            "start_ts": 1,
            "end_ts": 2,
            "refresh": "true",
        },
    )

    assert response.status_code == 200
    assert captured == {
        "pair": "AAA/BBB",
        "timeframe": "5m",
        "start_ts": 1.0,
        "end_ts": 2.0,
        "refresh": True,
    }


def test_pair_detail_permission_dependency_is_applied() -> None:
    route = _pair_detail_route()
    assert route.methods == {"GET"}
    assert route.dependant.dependencies
    dependency = route.dependant.dependencies[0].call
    closure_values = [cell.cell_contents for cell in dependency.__closure__ or ()]

    assert {"view_pair_universe", "view_dashboard"} in closure_values


def test_pair_detail_endpoint_is_read_only_and_avoids_order_execution() -> None:
    source = inspect.getsource(admin.admin_pair_detail_summary) + inspect.getsource(admin._get_pair_detail_summary_service)

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
