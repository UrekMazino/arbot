from __future__ import annotations

import inspect
import json

import pytest

from core.dashboard import portfolio_service as service
from core.dashboard.portfolio_service import PortfolioDataBundle


BASE_TS = 1_715_000_000
PAIR_A = "AAA-USDT-SWAP/BBB-USDT-SWAP"
PAIR_B = "CCC-USDT-SWAP/DDD-USDT-SWAP"


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    service.clear_portfolio_dashboard_cache()


def _patch_loader(monkeypatch: pytest.MonkeyPatch, bundle: PortfolioDataBundle):
    calls: list[tuple[int | None, int | None]] = []

    def fake_loader(start_ts: int | None, end_ts: int | None) -> PortfolioDataBundle:
        calls.append((start_ts, end_ts))
        return bundle

    monkeypatch.setattr(service, "_load_portfolio_data", fake_loader)
    return calls


def test_missing_data_returns_null_scalars_and_empty_charts(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_loader(monkeypatch, PortfolioDataBundle())

    payload = service.get_portfolio_dashboard(refresh=True)

    summary = payload["summary"]
    assert summary == {
        "total_equity_usdt": None,
        "session_pnl_usdt": None,
        "realized_pnl_usdt": None,
        "unrealized_pnl_usdt": None,
        "win_rate": None,
        "profit_factor": None,
        "max_drawdown_usdt": None,
        "open_positions": None,
        "active_pair": None,
        "bot_status": None,
        "open_exposure_usdt": None,
    }
    assert payload["charts"] == {
        "equity_curve": [],
        "daily_pnl": [],
        "drawdown_curve": [],
        "open_exposure": [],
    }
    assert payload["highlights"] == {
        "best_performing_pair": None,
        "worst_performing_pair": None,
        "most_traded_pair": None,
        "highest_drawdown_pair": None,
        "current_regime_state": None,
        "current_risk_level": None,
    }
    assert payload["cache"]["cache_hit"] is False
    assert payload["cache"]["ttl_seconds"] == 60
    assert payload["cache"]["refresh_supported"] is True
    json.dumps(payload)


def test_summary_aggregation_calculates_pnl_win_rate_and_profit_factor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trades = (
        {"pair_key": PAIR_A, "exit_ts": BASE_TS + 60, "pnl_usdt": 10.0},
        {"pair_key": PAIR_A, "exit_ts": BASE_TS + 120, "pnl_usdt": -4.0},
        {"pair_key": PAIR_B, "exit_ts": BASE_TS + 180, "pnl_usdt": 6.0},
        {"pair_key": PAIR_B, "entry_ts": BASE_TS + 240, "pnl_usdt": 100.0},
    )
    bundle = PortfolioDataBundle(
        trades=trades,
        equity_snapshots=({"ts": BASE_TS + 180, "equity_usdt": 1_012.0},),
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_portfolio_dashboard(refresh=True)

    summary = payload["summary"]
    assert summary["realized_pnl_usdt"] == 12.0
    assert summary["win_rate"] == pytest.approx(2 / 3)
    assert summary["profit_factor"] == pytest.approx(4.0)
    assert summary["total_equity_usdt"] == 1_012.0


def test_equity_curve_returns_ordered_time_series(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = PortfolioDataBundle(
        equity_snapshots=(
            {"ts": BASE_TS + 120, "equity_usdt": 105.0},
            {"ts": BASE_TS, "equity_usdt": 100.0},
            {"ts": BASE_TS + 60, "equity_usdt": 110.0},
        )
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_portfolio_dashboard(refresh=True)

    timestamps = [point["timestamp"] for point in payload["charts"]["equity_curve"]]
    assert timestamps == [BASE_TS, BASE_TS + 60, BASE_TS + 120]
    assert payload["summary"]["total_equity_usdt"] == 105.0


def test_drawdown_curve_is_computed_from_equity_curve(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = PortfolioDataBundle(
        equity_snapshots=(
            {"ts": BASE_TS, "equity_usdt": 100.0},
            {"ts": BASE_TS + 60, "equity_usdt": 110.0},
            {"ts": BASE_TS + 120, "equity_usdt": 105.0},
            {"ts": BASE_TS + 180, "equity_usdt": 120.0},
            {"ts": BASE_TS + 240, "equity_usdt": 90.0},
        )
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_portfolio_dashboard(refresh=True)

    drawdowns = payload["charts"]["drawdown_curve"]
    assert [row["drawdown_usdt"] for row in drawdowns] == [0.0, 0.0, -5.0, 0.0, -30.0]
    assert payload["summary"]["max_drawdown_usdt"] == -30.0


def test_pair_highlights_select_best_worst_and_most_traded(monkeypatch: pytest.MonkeyPatch) -> None:
    trades = (
        {"pair_key": PAIR_A, "exit_ts": BASE_TS + 60, "pnl_usdt": 8.0},
        {"pair_key": PAIR_A, "exit_ts": BASE_TS + 120, "pnl_usdt": -2.0},
        {"pair_key": PAIR_B, "exit_ts": BASE_TS + 180, "pnl_usdt": -3.0},
    )
    _patch_loader(monkeypatch, PortfolioDataBundle(trades=trades))

    payload = service.get_portfolio_dashboard(refresh=True)

    highlights = payload["highlights"]
    assert highlights["best_performing_pair"] == PAIR_A
    assert highlights["worst_performing_pair"] == PAIR_B
    assert highlights["most_traded_pair"] == PAIR_A


def test_cache_hit_returns_cached_result(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_loader(
        monkeypatch,
        PortfolioDataBundle(equity_snapshots=({"ts": BASE_TS, "equity_usdt": 100.0},)),
    )

    first = service.get_portfolio_dashboard()
    second = service.get_portfolio_dashboard()

    assert len(calls) == 1
    assert first["cache"]["cache_hit"] is False
    assert second["cache"]["cache_hit"] is True
    assert second["summary"]["total_equity_usdt"] == 100.0


def test_refresh_true_bypasses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    values = [100.0, 125.0]
    calls: list[tuple[int | None, int | None]] = []

    def fake_loader(start_ts: int | None, end_ts: int | None) -> PortfolioDataBundle:
        calls.append((start_ts, end_ts))
        equity = values[len(calls) - 1]
        return PortfolioDataBundle(equity_snapshots=({"ts": BASE_TS, "equity_usdt": equity},))

    monkeypatch.setattr(service, "_load_portfolio_data", fake_loader)

    first = service.get_portfolio_dashboard()
    refreshed = service.get_portfolio_dashboard(refresh=True)

    assert len(calls) == 2
    assert first["summary"]["total_equity_usdt"] == 100.0
    assert refreshed["cache"]["cache_hit"] is False
    assert refreshed["summary"]["total_equity_usdt"] == 125.0


def test_cache_key_respects_start_and_end_timestamps(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_loader(monkeypatch, PortfolioDataBundle())

    service.get_portfolio_dashboard(start_ts=BASE_TS, end_ts=BASE_TS + 60)
    service.get_portfolio_dashboard(start_ts=BASE_TS + 1, end_ts=BASE_TS + 60)
    cached = service.get_portfolio_dashboard(start_ts=BASE_TS, end_ts=BASE_TS + 60)

    assert calls == [(BASE_TS, BASE_TS + 60), (BASE_TS + 1, BASE_TS + 60)]
    assert cached["cache"]["cache_hit"] is True


def test_service_does_not_import_order_execution_modules() -> None:
    source = inspect.getsource(service)

    for forbidden in (
        "submit_order",
        "place_order",
        "execute_order",
        "order_execution",
        "ExecutionManager",
        "bot_control",
        "func_trade",
    ):
        assert forbidden not in source


def test_response_is_json_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = PortfolioDataBundle(
        trades=({"pair_key": PAIR_A, "exit_ts": BASE_TS + 60, "pnl_usdt": 0.0},),
        equity_snapshots=(
            {
                "ts": BASE_TS,
                "equity_usdt": 100.0,
                "session_pnl_usdt": 0.0,
                "current_pair": PAIR_A,
                "regime": "mean_reverting",
            },
        ),
        position_snapshots=(
            {
                "ts": BASE_TS,
                "pair_key": PAIR_A,
                "notional_usdt": 50.0,
                "unrealized_pnl_usdt": 0.0,
            },
        ),
        heartbeat_events=({"ts": BASE_TS, "payload_json": {"status": "running"}},),
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_portfolio_dashboard(refresh=True)

    assert payload["summary"]["open_positions"] == [
        {
            "pair": PAIR_A,
            "timestamp": BASE_TS,
            "notional_usdt": 50.0,
            "unrealized_pnl_usdt": 0.0,
        }
    ]
    assert payload["summary"]["session_pnl_usdt"] == 0.0
    assert payload["summary"]["unrealized_pnl_usdt"] == 0.0
    json.dumps(payload)
