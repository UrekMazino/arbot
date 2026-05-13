from __future__ import annotations

import inspect
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from Platform.api.app.routers import admin


def _pair_history_route():
    return next(
        route
        for route in admin.router.routes
        if getattr(route, "path", None) == "/admin/pairs/history"
    )


def _client_with_permission_override() -> TestClient:
    app = FastAPI()
    app.include_router(admin.router)
    route = _pair_history_route()
    for dependency in route.dependant.dependencies:
        app.dependency_overrides[dependency.call] = lambda: object()
    return TestClient(app)


def _fake_response() -> dict[str, Any]:
    return {
        "rows": [{"pair": "AAA-USDT-SWAP/BBB-USDT-SWAP", "total_trades": 1}],
        "meta": {
            "page": 1,
            "page_size": 50,
            "total_rows": 1,
            "total_pages": 1,
            "sort_by": "net_pnl_usdt",
            "sort_dir": "desc",
        },
        "kpis": {
            "total_pairs": 1,
            "tradable_pairs": 1,
            "profitable_pairs": 1,
            "losing_pairs": 0,
            "hospital_pairs": 0,
            "graveyard_pairs": 0,
        },
        "cache": {
            "cache_hit": False,
            "generated_at": 1_715_000_000,
            "ttl_seconds": 300,
            "refresh_supported": True,
        },
    }


def test_pair_history_endpoint_returns_rows_meta_kpis_cache_shape(monkeypatch):
    monkeypatch.setattr(admin, "_get_pair_history_summary_service", lambda: lambda **_: _fake_response())
    client = _client_with_permission_override()

    response = client.get("/admin/pairs/history")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"rows", "meta", "kpis", "cache"}
    assert payload["rows"][0]["pair"] == "AAA-USDT-SWAP/BBB-USDT-SWAP"
    assert payload["cache"]["ttl_seconds"] == 300


def test_pair_history_query_params_are_passed_to_service(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_service(**kwargs):
        captured.update(kwargs)
        return _fake_response()

    monkeypatch.setattr(admin, "_get_pair_history_summary_service", lambda: fake_service)
    client = _client_with_permission_override()

    response = client.get(
        "/admin/pairs/history",
        params={
            "start_ts": 1,
            "end_ts": 2,
            "status": "hospital",
            "pnl_filter": "winners",
            "min_trade_count": 3,
            "min_win_rate": 0.4,
            "max_win_rate": 0.9,
            "regime": "mean_reverting",
            "hedge_drift_filter": "high_drift",
            "significant_only": "true",
            "search": "AAA",
            "sort_by": "win_rate",
            "sort_dir": "asc",
            "page": 2,
            "page_size": 25,
            "refresh": "true",
        },
    )

    assert response.status_code == 200
    assert captured == {
        "start_ts": 1.0,
        "end_ts": 2.0,
        "status": "hospital",
        "pnl_filter": "winners",
        "min_trade_count": 3,
        "min_win_rate": 0.4,
        "max_win_rate": 0.9,
        "regime": "mean_reverting",
        "hedge_drift_filter": "high_drift",
        "significant_only": True,
        "search": "AAA",
        "sort_by": "win_rate",
        "sort_dir": "asc",
        "page": 2,
        "page_size": 25,
        "refresh": True,
    }


def test_pair_history_page_and_page_size_defaults(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_service(**kwargs):
        captured.update(kwargs)
        return _fake_response()

    monkeypatch.setattr(admin, "_get_pair_history_summary_service", lambda: fake_service)
    client = _client_with_permission_override()

    response = client.get("/admin/pairs/history")

    assert response.status_code == 200
    assert captured["page"] == 1
    assert captured["page_size"] == 50


def test_pair_history_page_size_cap_is_validated(monkeypatch):
    monkeypatch.setattr(admin, "_get_pair_history_summary_service", lambda: lambda **_: _fake_response())
    client = _client_with_permission_override()

    response = client.get("/admin/pairs/history?page_size=201")

    assert response.status_code == 422


def test_pair_history_significant_only_param(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_service(**kwargs):
        captured.update(kwargs)
        return _fake_response()

    monkeypatch.setattr(admin, "_get_pair_history_summary_service", lambda: fake_service)
    client = _client_with_permission_override()

    response = client.get("/admin/pairs/history?significant_only=true")

    assert response.status_code == 200
    assert captured["significant_only"] is True


def test_pair_history_refresh_true_is_passed_to_service(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_service(**kwargs):
        captured.update(kwargs)
        response = _fake_response()
        response["cache"]["cache_hit"] = False
        return response

    monkeypatch.setattr(admin, "_get_pair_history_summary_service", lambda: fake_service)
    client = _client_with_permission_override()

    response = client.get("/admin/pairs/history?refresh=true")

    assert response.status_code == 200
    assert captured["refresh"] is True
    assert response.json()["cache"]["cache_hit"] is False


def test_pair_history_permission_dependency_is_applied() -> None:
    route = _pair_history_route()
    assert route.methods == {"GET"}
    assert route.dependant.dependencies
    dependency = route.dependant.dependencies[0].call
    closure_values = [cell.cell_contents for cell in dependency.__closure__ or ()]

    assert {"view_pair_universe", "view_dashboard"} in closure_values


def test_pair_history_endpoint_is_read_only_and_avoids_order_execution() -> None:
    source = inspect.getsource(admin.admin_pair_history) + inspect.getsource(admin._get_pair_history_summary_service)

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
