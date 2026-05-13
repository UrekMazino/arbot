from __future__ import annotations

import inspect
import json

import pytest

from core.dashboard import risk_health_service as service
from core.dashboard.risk_health_service import RiskHealthDataBundle


BASE_TS = 1_715_000_000
PAIR_A = "AAA-USDT-SWAP/BBB-USDT-SWAP"
PAIR_B = "CCC-USDT-SWAP/DDD-USDT-SWAP"
PAIR_C = "EEE-USDT-SWAP/FFF-USDT-SWAP"


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    service.clear_risk_health_cache()


def _event(ts: int, event_type: str, **payload):
    return {
        "event_id": f"{event_type}:{ts}",
        "event_type": event_type,
        "ts": ts,
        "payload_json": payload,
    }


def _trade(pair: str, ts: int, pnl: float | None, **extra):
    return {
        "id": f"{pair}:{ts}:{pnl}",
        "pair_key": pair,
        "entry_ts": ts - 60,
        "exit_ts": ts,
        "pnl_usdt": pnl,
        **extra,
    }


def _patch_loader(monkeypatch: pytest.MonkeyPatch, bundle: RiskHealthDataBundle):
    calls: list[tuple[int | None, int | None]] = []

    def fake_loader(start_ts: int | None, end_ts: int | None) -> RiskHealthDataBundle:
        calls.append((start_ts, end_ts))
        return bundle

    monkeypatch.setattr(service, "_load_risk_health_data", fake_loader)
    return calls


def _alerts_by_type(payload: dict) -> dict[str, list[dict]]:
    alerts: dict[str, list[dict]] = {}
    for alert in payload["alerts"]:
        alerts.setdefault(alert["type"], []).append(alert)
    return alerts


def test_missing_data_returns_null_empty_sections_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_loader(monkeypatch, RiskHealthDataBundle())

    payload = service.get_risk_health_dashboard(refresh=True)

    assert payload["bot_status"] == {}
    assert payload["risk_kpis"] == {
        "current_drawdown_usdt": None,
        "daily_loss_limit_usage_pct": None,
        "open_exposure_usdt": None,
        "open_positions": None,
        "orphan_desync_status": None,
        "api_latency_ms": None,
        "order_failure_count": None,
        "orderbook_stale_count": None,
    }
    assert payload["pair_health"] == {
        "hospital_pairs": [],
        "graveyard_pairs": [],
        "high_break_risk_pairs": [],
        "high_hedge_drift_positions": [],
        "liquidity_stress_pairs": [],
    }
    assert payload["alerts"] == []
    assert payload["cache"]["cache_hit"] is False
    assert payload["cache"]["ttl_seconds"] == 30
    assert payload["cache"]["refresh_supported"] is True
    json.dumps(payload)


def test_hospital_pairs_load_from_pair_state(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = RiskHealthDataBundle(pair_state={"hospital": {PAIR_A: {"reason": "watch", "ts": BASE_TS}}})
    _patch_loader(monkeypatch, bundle)

    payload = service.get_risk_health_dashboard(refresh=True)

    assert payload["pair_health"]["hospital_pairs"] == [PAIR_A]
    alert = _alerts_by_type(payload)["pair_moved_to_hospital"][0]
    assert alert["pair"] == PAIR_A
    assert alert["latest_timestamp"] == BASE_TS
    assert alert["severity"] == "warning"


def test_graveyard_pairs_load_from_pair_state_and_ticker_source(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = RiskHealthDataBundle(
        pair_state={"graveyard": {PAIR_B: {"reason": "bad_history", "ts": BASE_TS}}},
        graveyard_tickers=frozenset({"ZZZ-USDT-SWAP"}),
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_risk_health_dashboard(refresh=True)

    assert payload["pair_health"]["graveyard_pairs"] == [PAIR_B, "ZZZ-USDT-SWAP"]
    graveyard_alerts = _alerts_by_type(payload)["pair_moved_to_graveyard"]
    assert {alert["pair"] for alert in graveyard_alerts} == {PAIR_B, "ZZZ-USDT-SWAP"}


def test_alert_generation_for_hedge_ratio_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = RiskHealthDataBundle(
        position_snapshots=(
            {
                "ts": BASE_TS,
                "pair_key": PAIR_A,
                "notional_usdt": 100.0,
                "hedge_ratio_drift_pct": 0.32,
            },
        )
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_risk_health_dashboard(refresh=True)

    health_rows = payload["pair_health"]["high_hedge_drift_positions"]
    assert health_rows == [
        {
            "pair": PAIR_A,
            "hedge_ratio_drift_pct": 0.32,
            "latest_timestamp": BASE_TS,
            "notional_usdt": 100.0,
        }
    ]
    alert = _alerts_by_type(payload)["hedge_ratio_drift_exceeded"][0]
    assert alert["pair"] == PAIR_A
    assert alert["metadata"]["hedge_ratio_drift_pct"] == 0.32


def test_alert_generation_for_orderbook_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = RiskHealthDataBundle(
        run_events=(
            _event(BASE_TS, "orderbook_stale", pair=PAIR_A, stale_age_ms=8000),
            _event(BASE_TS + 60, "heartbeat", pair=PAIR_A, api_latency_ms=120.0),
        )
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_risk_health_dashboard(refresh=True)

    assert payload["risk_kpis"]["orderbook_stale_count"] == 1
    assert payload["risk_kpis"]["api_latency_ms"] == 120.0
    alert = _alerts_by_type(payload)["orderbook_stale"][0]
    assert alert["pair"] == PAIR_A
    assert alert["severity"] == "warning"


def test_alert_generation_for_high_break_risk_from_stored_score(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = RiskHealthDataBundle(
        run_events=(
            _event(BASE_TS, "advanced_ml_regime_shadow", pair=PAIR_B, break_risk=0.72, score_source="stored_live"),
            _event(BASE_TS + 60, "advanced_ml_regime_shadow", pair=PAIR_C, break_risk=0.40, score_source="stored_live"),
        )
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_risk_health_dashboard(refresh=True)

    assert payload["pair_health"]["high_break_risk_pairs"] == [
        {
            "pair": PAIR_B,
            "break_risk": 0.72,
            "latest_timestamp": BASE_TS,
            "score_source": "stored_live",
        }
    ]
    alert = _alerts_by_type(payload)["regime_break_risk_high"][0]
    assert alert["pair"] == PAIR_B
    assert alert["metadata"]["break_risk"] == 0.72


def test_alert_deduplication_groups_by_type_and_pair_within_window() -> None:
    alerts = [
        {
            "severity": "warning",
            "type": "orderbook_stale",
            "message": "older",
            "pair": PAIR_A,
            "latest_timestamp": BASE_TS,
            "occurrence_count": 1,
            "metadata": {"first": True},
        },
        {
            "severity": "error",
            "type": "orderbook_stale",
            "message": "newer",
            "pair": PAIR_A,
            "latest_timestamp": BASE_TS + 60,
            "occurrence_count": 1,
            "metadata": {"second": True},
        },
    ]

    deduped = service.deduplicate_alerts(alerts)

    assert len(deduped) == 1
    assert deduped[0]["message"] == "newer"
    assert deduped[0]["severity"] == "error"
    assert deduped[0]["latest_timestamp"] == BASE_TS + 60
    assert deduped[0]["occurrence_count"] == 2
    assert deduped[0]["metadata"] == {"first": True, "second": True}


def test_alert_deduplication_uses_global_key_when_pair_missing() -> None:
    alerts = [
        {
            "severity": "warning",
            "type": "API_error_spike",
            "message": "older",
            "pair": None,
            "latest_timestamp": BASE_TS,
            "occurrence_count": 1,
            "metadata": {},
        },
        {
            "severity": "warning",
            "type": "API_error_spike",
            "message": "newer",
            "pair": None,
            "latest_timestamp": BASE_TS + 30,
            "occurrence_count": 1,
            "metadata": {"event_count": 3},
        },
    ]

    deduped = service.deduplicate_alerts(alerts)

    assert len(deduped) == 1
    assert deduped[0]["pair"] is None
    assert deduped[0]["occurrence_count"] == 2
    assert deduped[0]["metadata"]["event_count"] == 3


def test_cache_hit_and_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_loader(monkeypatch, RiskHealthDataBundle(run_events=(_event(BASE_TS, "heartbeat", status="running"),)))

    first = service.get_risk_health_dashboard()
    second = service.get_risk_health_dashboard()

    assert len(calls) == 1
    assert first["cache"]["cache_hit"] is False
    assert second["cache"]["cache_hit"] is True


def test_refresh_true_bypasses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int | None, int | None]] = []

    def fake_loader(start_ts: int | None, end_ts: int | None) -> RiskHealthDataBundle:
        calls.append((start_ts, end_ts))
        status = "running" if len(calls) == 1 else "paused"
        return RiskHealthDataBundle(run_events=(_event(BASE_TS + len(calls), "heartbeat", status=status),))

    monkeypatch.setattr(service, "_load_risk_health_data", fake_loader)

    first = service.get_risk_health_dashboard()
    refreshed = service.get_risk_health_dashboard(refresh=True)

    assert len(calls) == 2
    assert first["bot_status"]["status"] == "running"
    assert refreshed["bot_status"]["status"] == "paused"
    assert refreshed["cache"]["cache_hit"] is False


def test_cache_key_respects_start_and_end_timestamps(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_loader(monkeypatch, RiskHealthDataBundle())

    service.get_risk_health_dashboard(start_ts=BASE_TS, end_ts=BASE_TS + 60)
    service.get_risk_health_dashboard(start_ts=BASE_TS + 1, end_ts=BASE_TS + 60)
    cached = service.get_risk_health_dashboard(start_ts=BASE_TS, end_ts=BASE_TS + 60)

    assert calls == [(BASE_TS, BASE_TS + 60), (BASE_TS + 1, BASE_TS + 60)]
    assert cached["cache"]["cache_hit"] is True


def test_missing_or_broken_state_loader_is_handled_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken_state_loader():
        raise ValueError("corrupt json")

    def missing_database():
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(service, "_load_pair_state_data", broken_state_loader)
    monkeypatch.setattr(service, "_platform_database_bundle", missing_database)

    payload = service.get_risk_health_dashboard(refresh=True)

    assert payload["pair_health"]["hospital_pairs"] == []
    assert payload["pair_health"]["graveyard_pairs"] == []
    assert payload["alerts"] == []
    json.dumps(payload)


def test_response_is_json_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = RiskHealthDataBundle(
        trades=(
            _trade(PAIR_A, BASE_TS, -1.0),
            _trade(PAIR_A, BASE_TS + 60, -2.0),
            _trade(PAIR_A, BASE_TS + 120, -3.0),
        ),
        equity_snapshots=(
            {"ts": BASE_TS, "equity_usdt": 100.0},
            {"ts": BASE_TS + 60, "equity_usdt": 95.0},
        ),
        run_events=(
            _event(BASE_TS + 120, "api_error", error="timeout"),
            _event(BASE_TS + 121, "api_error", error="timeout"),
            _event(BASE_TS + 122, "api_error", error="timeout"),
        ),
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_risk_health_dashboard(refresh=True)

    assert payload["risk_kpis"]["current_drawdown_usdt"] == -5.0
    assert "consecutive_losses" in _alerts_by_type(payload)
    assert "API_error_spike" in _alerts_by_type(payload)
    json.dumps(payload)


def test_service_does_not_import_or_call_order_execution_modules() -> None:
    source = inspect.getsource(service)

    for forbidden in (
        "submit_order",
        "place_order",
        "execute_order",
        "order_execution",
        "ExecutionManager",
        "bot_control",
        "func_trade",
        "func_close_positions",
    ):
        assert forbidden not in source


def test_service_does_not_call_live_current_ml_runtime() -> None:
    source = inspect.getsource(service)

    for forbidden in (
        "advanced_ml_runtime",
        "Execution.advanced_ml_runtime",
        "get_live_ml",
        "current_model_memory",
        "submit_ml_order",
    ):
        assert forbidden not in source
