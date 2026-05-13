from __future__ import annotations

import inspect
import json

import pytest

from core.dashboard import pair_detail_service as service
from core.dashboard.pair_detail_service import PairDetailDataBundle


BASE_TS = 1_715_000_000
PAIR_A = "AAA-USDT-SWAP/BBB-USDT-SWAP"
PAIR_B = "CCC-USDT-SWAP/DDD-USDT-SWAP"


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    service.clear_pair_detail_cache()


def _trade(pair: str, ts: int, pnl: float | None, **extra):
    payload = {
        "id": extra.pop("id", f"{pair}:{ts}:{pnl}"),
        "pair_key": pair,
        "entry_ts": ts - 60,
        "exit_ts": ts,
        "pnl_usdt": pnl,
        "hold_minutes": extra.pop("hold_minutes", 5),
        "entry_z": extra.pop("entry_z", -2.1),
        "exit_z": extra.pop("exit_z", -0.3),
        **extra,
    }
    return payload


def _event(pair: str, ts: int, event_type: str = "replay_blocked_signal", **payload):
    return {
        "event_id": f"{pair}:{event_type}:{ts}",
        "event_type": event_type,
        "ts": ts,
        "payload_json": {
            "pair": pair,
            **payload,
        },
    }


def _patch_loader(monkeypatch: pytest.MonkeyPatch, bundle: PairDetailDataBundle):
    calls: list[tuple[str, str, int | None, int | None]] = []

    def fake_loader(pair: str, timeframe: str, start_ts: int | None, end_ts: int | None) -> PairDetailDataBundle:
        calls.append((pair, timeframe, start_ts, end_ts))
        return bundle

    monkeypatch.setattr(service, "_load_pair_detail_data", fake_loader)
    return calls


def test_missing_data_returns_null_safe_response(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_loader(monkeypatch, PairDetailDataBundle())

    payload = service.get_pair_detail_summary(PAIR_A, refresh=True)

    assert payload["pair"] == PAIR_A
    assert payload["timeframe"] == "1m"
    assert payload["status"] is None
    assert payload["summary"] == {
        "total_pnl_usdt": None,
        "total_trades": None,
        "win_rate": None,
        "profit_factor": None,
        "avg_reversion_time_seconds": None,
        "avg_hedge_ratio": None,
        "current_hedge_ratio": None,
        "avg_hedge_drift_pct": None,
        "current_regime": None,
        "current_bayesian_posterior": None,
        "current_final_rank_score": None,
    }
    assert payload["best_trade"] is None
    assert payload["worst_trade"] is None
    assert payload["latest_trade"] is None
    assert payload["block_reason_counts"] == {}
    assert payload["counterfactual_summary"] == {
        "best_exit_policy": None,
        "avg_missed_profit_usdt": None,
        "avg_avoided_loss_usdt": None,
        "actual_exit_efficiency": None,
    }
    assert payload["hedge_summary"] == {
        "avg_entry_hedge_ratio": None,
        "avg_exit_hedge_ratio": None,
        "avg_hedge_drift_pct": None,
        "equal_notional_total_pnl": None,
        "hedge_ratio_sized_total_pnl": None,
        "sizing_pnl_delta_usdt": None,
    }
    assert payload["cache"]["cache_hit"] is False
    assert payload["cache"]["ttl_seconds"] == 300
    assert payload["cache"]["refresh_supported"] is True
    json.dumps(payload)


def test_pair_summary_aggregation_calculates_trade_pnl_win_rate_and_profit_factor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = PairDetailDataBundle(
        trades=(
            _trade(PAIR_A, BASE_TS + 60, 10.0),
            _trade(PAIR_A, BASE_TS + 120, -4.0),
            _trade(PAIR_A, BASE_TS + 180, 6.0),
            _trade(PAIR_B, BASE_TS + 240, 100.0),
        ),
        current_hedge_ratio=1.25,
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_pair_detail_summary(PAIR_A, refresh=True)
    summary = payload["summary"]

    assert summary["total_trades"] == 3
    assert summary["total_pnl_usdt"] == 12.0
    assert summary["win_rate"] == pytest.approx(2 / 3)
    assert summary["profit_factor"] == pytest.approx(4.0)
    assert summary["avg_reversion_time_seconds"] == 300.0
    assert summary["current_hedge_ratio"] == 1.25


def test_best_worst_and_latest_trade_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = PairDetailDataBundle(
        trades=(
            _trade(PAIR_A, BASE_TS + 120, 1.0),
            _trade(PAIR_A, BASE_TS + 60, 12.0, side="BUY_SPREAD"),
            _trade(PAIR_A, BASE_TS + 180, -5.0, exit_reason="stop"),
        ),
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_pair_detail_summary(PAIR_A, refresh=True)

    assert payload["best_trade"]["pnl_usdt"] == 12.0
    assert payload["best_trade"]["side"] == "BUY_SPREAD"
    assert payload["worst_trade"]["pnl_usdt"] == -5.0
    assert payload["worst_trade"]["exit_reason"] == "stop"
    assert payload["latest_trade"]["pnl_usdt"] == -5.0


def test_date_filtering_works(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = PairDetailDataBundle(
        trades=(
            _trade(PAIR_A, BASE_TS - 60, 10.0),
            _trade(PAIR_A, BASE_TS + 60, 3.0),
            _trade(PAIR_A, BASE_TS + 120, 7.0),
        ),
    )
    calls = _patch_loader(monkeypatch, bundle)

    payload = service.get_pair_detail_summary(PAIR_A, start_ts=BASE_TS, end_ts=BASE_TS + 90, refresh=True)

    assert calls == [(PAIR_A, "1m", BASE_TS, BASE_TS + 90)]
    assert payload["summary"]["total_trades"] == 1
    assert payload["summary"]["total_pnl_usdt"] == 3.0


def test_current_status_is_loaded_from_pair_health_state(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = PairDetailDataBundle(
        trades=(_trade(PAIR_A, BASE_TS + 60, 1.0),),
        pair_state={"hospital": {PAIR_A: {"reason": "test"}}, "graveyard": {}},
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_pair_detail_summary(PAIR_A, refresh=True)

    assert payload["status"] == "hospital"


def test_hedge_summary_calculates_average_entry_exit_and_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = PairDetailDataBundle(
        trades=(
            _trade(PAIR_A, BASE_TS + 60, 1.0, entry_hedge_ratio=1.2, exit_hedge_ratio=1.1, hedge_ratio_drift_pct=0.1),
            _trade(PAIR_A, BASE_TS + 120, 2.0, entry_hedge_ratio=0.8, exit_hedge_ratio=0.9, hedge_ratio_drift_pct=0.3),
        ),
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_pair_detail_summary(PAIR_A, refresh=True)

    assert payload["summary"]["avg_hedge_ratio"] == pytest.approx(1.0)
    hedge = payload["hedge_summary"]
    assert hedge["avg_entry_hedge_ratio"] == pytest.approx(1.0)
    assert hedge["avg_exit_hedge_ratio"] == pytest.approx(1.0)
    assert hedge["avg_hedge_drift_pct"] == pytest.approx(0.2)


def test_hedge_sizing_comparison_fields_remain_null_without_stored_counterfactuals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = PairDetailDataBundle(
        trades=(_trade(PAIR_A, BASE_TS + 60, 1.0, entry_hedge_ratio=1.2),),
    )
    _patch_loader(monkeypatch, bundle)

    hedge = service.get_pair_detail_summary(PAIR_A, refresh=True)["hedge_summary"]

    assert hedge["equal_notional_total_pnl"] is None
    assert hedge["hedge_ratio_sized_total_pnl"] is None
    assert hedge["sizing_pnl_delta_usdt"] is None


def test_counterfactual_summary_remains_null_safe_when_no_stored_counterfactuals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_loader(monkeypatch, PairDetailDataBundle(trades=(_trade(PAIR_A, BASE_TS + 60, 1.0),)))

    counterfactual = service.get_pair_detail_summary(PAIR_A, refresh=True)["counterfactual_summary"]

    assert counterfactual["best_exit_policy"] is None
    assert counterfactual["avg_missed_profit_usdt"] is None
    assert counterfactual["avg_avoided_loss_usdt"] is None
    assert counterfactual["actual_exit_efficiency"] is None


def test_stored_ml_fields_remain_null_when_no_score_history(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_loader(monkeypatch, PairDetailDataBundle(trades=(_trade(PAIR_A, BASE_TS + 60, 1.0),)))

    summary = service.get_pair_detail_summary(PAIR_A, refresh=True)["summary"]

    assert summary["current_regime"] is None
    assert summary["current_bayesian_posterior"] is None
    assert summary["current_final_rank_score"] is None


def test_block_reason_counts_from_events(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = PairDetailDataBundle(
        trades=(_trade(PAIR_A, BASE_TS + 60, 1.0),),
        run_events=(
            _event(PAIR_A, BASE_TS + 60, block_reasons=["pair_in_hospital", "liquidity_failed"]),
            _event(PAIR_A, BASE_TS + 90, block_reason="pair_in_hospital"),
        ),
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_pair_detail_summary(PAIR_A, refresh=True)

    assert payload["block_reason_counts"] == {
        "pair_in_hospital": 2,
        "liquidity_failed": 1,
    }


def test_cache_hit_and_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_loader(monkeypatch, PairDetailDataBundle(trades=(_trade(PAIR_A, BASE_TS + 60, 1.0),)))

    first = service.get_pair_detail_summary(PAIR_A)
    second = service.get_pair_detail_summary(PAIR_A)

    assert len(calls) == 1
    assert first["cache"]["cache_hit"] is False
    assert second["cache"]["cache_hit"] is True


def test_refresh_true_bypasses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    values = [1.0, 2.0]
    calls: list[tuple[str, str, int | None, int | None]] = []

    def fake_loader(pair: str, timeframe: str, start_ts: int | None, end_ts: int | None) -> PairDetailDataBundle:
        calls.append((pair, timeframe, start_ts, end_ts))
        return PairDetailDataBundle(trades=(_trade(PAIR_A, BASE_TS + len(calls), values[len(calls) - 1]),))

    monkeypatch.setattr(service, "_load_pair_detail_data", fake_loader)

    first = service.get_pair_detail_summary(PAIR_A)
    refreshed = service.get_pair_detail_summary(PAIR_A, refresh=True)

    assert len(calls) == 2
    assert first["summary"]["total_pnl_usdt"] == 1.0
    assert refreshed["summary"]["total_pnl_usdt"] == 2.0
    assert refreshed["cache"]["cache_hit"] is False


def test_response_is_json_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = PairDetailDataBundle(
        trades=(_trade(PAIR_A, BASE_TS + 60, 0.0),),
        run_events=(_event(PAIR_A, BASE_TS + 60, block_reasons=["insufficient_history"]),),
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_pair_detail_summary(PAIR_A, refresh=True)

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
    ):
        assert forbidden not in source
