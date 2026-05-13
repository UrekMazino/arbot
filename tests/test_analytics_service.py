from __future__ import annotations

import inspect
import json

import pytest

from core.dashboard import analytics_service as service
from core.dashboard.analytics_service import AnalyticsDataBundle


BASE_TS = 1_715_000_000
PAIR_A = "AAA-USDT-SWAP/BBB-USDT-SWAP"
PAIR_B = "CCC-USDT-SWAP/DDD-USDT-SWAP"
PAIR_C = "EEE-USDT-SWAP/FFF-USDT-SWAP"


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    service.clear_analytics_cache()


def _trade(pair: str, ts: int, pnl: float | None, **extra):
    return {
        "id": f"{pair}:{ts}:{pnl}",
        "pair_key": pair,
        "entry_ts": ts - 60,
        "exit_ts": ts,
        "pnl_usdt": pnl,
        "hold_minutes": extra.pop("hold_minutes", 5),
        **extra,
    }


def _event(ts: int, event_type: str, **payload):
    return {
        "event_id": f"{event_type}:{ts}",
        "event_type": event_type,
        "ts": ts,
        "payload_json": payload,
    }


def _patch_loader(monkeypatch: pytest.MonkeyPatch, bundle: AnalyticsDataBundle):
    calls: list[tuple[int | None, int | None]] = []

    def fake_loader(start_ts: int | None, end_ts: int | None) -> AnalyticsDataBundle:
        calls.append((start_ts, end_ts))
        return bundle

    monkeypatch.setattr(service, "_load_analytics_data", fake_loader)
    return calls


def test_missing_data_returns_null_empty_sections_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_loader(monkeypatch, AnalyticsDataBundle())

    payload = service.get_analytics_dashboard(refresh=True)

    assert payload["performance"] == {
        "total_pnl_usdt": None,
        "realized_pnl_usdt": None,
        "unrealized_pnl_usdt": None,
        "win_rate": None,
        "profit_factor": None,
        "average_win_usdt": None,
        "average_loss_usdt": None,
        "max_drawdown_usdt": None,
        "trade_count": None,
        "avg_hold_seconds": None,
    }
    assert payload["pnl_timeseries"] == {
        "daily_pnl": [],
        "equity_curve": [],
        "drawdown_curve": [],
    }
    assert payload["pair_leaderboards"] == {
        "top_pairs_by_pnl": [],
        "bottom_pairs_by_pnl": [],
        "top_pairs_by_win_rate": [],
        "worst_pairs_by_drawdown": [],
        "pairs_with_high_hedge_drift": [],
        "pairs_with_frequent_blocks": [],
    }
    assert payload["exit_analysis"] == {
        "best_counterfactual_exit_policy": None,
        "actual_exit_efficiency": None,
        "avg_missed_profit_usdt": None,
        "avg_avoided_loss_usdt": None,
        "exit_policy_distribution": {},
    }
    assert payload["ml_analysis"]["pnl_by_regime"] == []
    assert payload["ml_analysis"]["break_risk_before_losses"] is None
    assert payload["hedge_analysis"] == {
        "equal_notional_total_pnl": None,
        "hedge_ratio_sized_total_pnl": None,
        "sizing_pnl_delta_usdt": None,
        "high_drift_trade_count": None,
    }
    assert payload["cache"]["cache_hit"] is False
    assert payload["cache"]["ttl_seconds"] == 900
    assert payload["cache"]["refresh_supported"] is True
    json.dumps(payload)


def test_performance_aggregation_calculates_pnl_win_loss_and_profit_factor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = AnalyticsDataBundle(
        trades=(
            _trade(PAIR_A, BASE_TS + 60, 10.0, hold_minutes=2),
            _trade(PAIR_A, BASE_TS + 120, -4.0, hold_minutes=4),
            _trade(PAIR_B, BASE_TS + 180, 6.0, hold_minutes=6),
        )
    )
    _patch_loader(monkeypatch, bundle)

    performance = service.get_analytics_dashboard(refresh=True)["performance"]

    assert performance["total_pnl_usdt"] == 12.0
    assert performance["realized_pnl_usdt"] == 12.0
    assert performance["win_rate"] == pytest.approx(2 / 3)
    assert performance["average_win_usdt"] == pytest.approx(8.0)
    assert performance["average_loss_usdt"] == pytest.approx(-4.0)
    assert performance["profit_factor"] == pytest.approx(4.0)
    assert performance["trade_count"] == 3
    assert performance["avg_hold_seconds"] == pytest.approx(240.0)


def test_daily_pnl_timeseries_aggregates_by_date(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = AnalyticsDataBundle(
        trades=(
            _trade(PAIR_A, BASE_TS, 1.0),
            _trade(PAIR_A, BASE_TS + 60, 2.0),
            _trade(PAIR_A, BASE_TS + 90_000, -1.0),
        )
    )
    _patch_loader(monkeypatch, bundle)

    daily = service.get_analytics_dashboard(refresh=True)["pnl_timeseries"]["daily_pnl"]

    assert len(daily) == 2
    assert daily[0]["pnl_usdt"] == 3.0
    assert daily[0]["trade_count"] == 2
    assert daily[1]["pnl_usdt"] == -1.0


def test_drawdown_curve_is_computed_from_equity_curve(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = AnalyticsDataBundle(
        equity_snapshots=(
            {"ts": BASE_TS, "equity_usdt": 100.0},
            {"ts": BASE_TS + 60, "equity_usdt": 110.0},
            {"ts": BASE_TS + 120, "equity_usdt": 90.0},
        )
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_analytics_dashboard(refresh=True)

    drawdowns = payload["pnl_timeseries"]["drawdown_curve"]
    assert [row["drawdown_usdt"] for row in drawdowns] == [0.0, 0.0, -20.0]
    assert payload["performance"]["max_drawdown_usdt"] == -20.0


def test_pair_leaderboards_use_pair_history_data(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = (
        {
            "pair": PAIR_A,
            "net_pnl_usdt": 12.0,
            "win_rate": 0.75,
            "max_drawdown_usdt": -1.0,
            "avg_hedge_drift_pct": 0.1,
            "block_reason_counts": {},
        },
        {
            "pair": PAIR_B,
            "net_pnl_usdt": -8.0,
            "win_rate": 0.2,
            "max_drawdown_usdt": -8.0,
            "avg_hedge_drift_pct": 0.3,
            "block_reason_counts": {"liquidity_failed": 3},
        },
        {
            "pair": PAIR_C,
            "net_pnl_usdt": 5.0,
            "win_rate": 0.9,
            "max_drawdown_usdt": -0.5,
            "avg_hedge_drift_pct": 0.05,
            "block_reason_counts": {},
        },
    )
    _patch_loader(monkeypatch, AnalyticsDataBundle(pair_history_rows=rows))

    leaderboards = service.get_analytics_dashboard(refresh=True)["pair_leaderboards"]

    assert leaderboards["top_pairs_by_pnl"][0]["pair"] == PAIR_A
    assert leaderboards["bottom_pairs_by_pnl"][0]["pair"] == PAIR_B
    assert leaderboards["top_pairs_by_win_rate"][0]["pair"] == PAIR_C
    assert leaderboards["worst_pairs_by_drawdown"][0]["pair"] == PAIR_B
    assert leaderboards["pairs_with_high_hedge_drift"][0]["pair"] == PAIR_B
    assert leaderboards["pairs_with_frequent_blocks"][0]["pair"] == PAIR_B


def test_exit_analysis_null_when_exit_orchestrator_logs_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_loader(monkeypatch, AnalyticsDataBundle(trades=(_trade(PAIR_A, BASE_TS, 1.0),)))

    exit_analysis = service.get_analytics_dashboard(refresh=True)["exit_analysis"]

    assert exit_analysis["best_counterfactual_exit_policy"] is None
    assert exit_analysis["actual_exit_efficiency"] is None
    assert exit_analysis["avg_missed_profit_usdt"] is None
    assert exit_analysis["avg_avoided_loss_usdt"] is None
    assert exit_analysis["exit_policy_distribution"] == {}


def test_counterfactual_metrics_remain_null_without_stored_counterfactuals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = AnalyticsDataBundle(exit_orchestrator_events=(_event(BASE_TS, "exit_orchestrator_candidate", policy="quality"),))
    _patch_loader(monkeypatch, bundle)

    exit_analysis = service.get_analytics_dashboard(refresh=True)["exit_analysis"]

    assert exit_analysis["exit_policy_distribution"] == {"quality": 1}
    assert exit_analysis["best_counterfactual_exit_policy"] is None
    assert exit_analysis["actual_exit_efficiency"] is None


def test_ml_analysis_empty_when_stored_scores_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_loader(monkeypatch, AnalyticsDataBundle(trades=(_trade(PAIR_A, BASE_TS, -1.0, regime="trend"),)))

    ml = service.get_analytics_dashboard(refresh=True)["ml_analysis"]

    assert ml["pnl_by_regime"] == []
    assert ml["win_rate_by_regime"] == []
    assert ml["bayesian_posterior_vs_outcome"] == []
    assert ml["final_rank_score_vs_outcome"] == []
    assert ml["break_risk_before_losses"] is None
    assert ml["microstructure_risk_vs_slippage"] == []


def test_hedge_analysis_null_when_sizing_comparison_data_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_loader(monkeypatch, AnalyticsDataBundle(trades=(_trade(PAIR_A, BASE_TS, 1.0),)))

    hedge = service.get_analytics_dashboard(refresh=True)["hedge_analysis"]

    assert hedge["equal_notional_total_pnl"] is None
    assert hedge["hedge_ratio_sized_total_pnl"] is None
    assert hedge["sizing_pnl_delta_usdt"] is None
    assert hedge["high_drift_trade_count"] is None


def test_cache_hit_and_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_loader(monkeypatch, AnalyticsDataBundle(trades=(_trade(PAIR_A, BASE_TS, 1.0),)))

    first = service.get_analytics_dashboard()
    second = service.get_analytics_dashboard()

    assert len(calls) == 1
    assert first["cache"]["cache_hit"] is False
    assert second["cache"]["cache_hit"] is True


def test_refresh_true_bypasses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    values = [1.0, 2.0]
    calls: list[tuple[int | None, int | None]] = []

    def fake_loader(start_ts: int | None, end_ts: int | None) -> AnalyticsDataBundle:
        calls.append((start_ts, end_ts))
        return AnalyticsDataBundle(trades=(_trade(PAIR_A, BASE_TS + len(calls), values[len(calls) - 1]),))

    monkeypatch.setattr(service, "_load_analytics_data", fake_loader)

    first = service.get_analytics_dashboard()
    refreshed = service.get_analytics_dashboard(refresh=True)

    assert len(calls) == 2
    assert first["performance"]["total_pnl_usdt"] == 1.0
    assert refreshed["performance"]["total_pnl_usdt"] == 2.0
    assert refreshed["cache"]["cache_hit"] is False


def test_cache_key_respects_start_and_end_timestamps(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_loader(monkeypatch, AnalyticsDataBundle())

    service.get_analytics_dashboard(start_ts=BASE_TS, end_ts=BASE_TS + 60)
    service.get_analytics_dashboard(start_ts=BASE_TS + 1, end_ts=BASE_TS + 60)
    cached = service.get_analytics_dashboard(start_ts=BASE_TS, end_ts=BASE_TS + 60)

    assert calls == [(BASE_TS, BASE_TS + 60), (BASE_TS + 1, BASE_TS + 60)]
    assert cached["cache"]["cache_hit"] is True


def test_response_is_json_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = AnalyticsDataBundle(
        trades=(_trade(PAIR_A, BASE_TS, 0.0),),
        equity_snapshots=({"ts": BASE_TS, "equity_usdt": 100.0},),
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_analytics_dashboard(refresh=True)

    json.dumps(payload)


def test_service_does_not_import_or_call_order_execution_modules() -> None:
    source = inspect.getsource(service)

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
