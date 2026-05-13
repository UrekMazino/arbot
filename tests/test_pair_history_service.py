from __future__ import annotations

import inspect
import json

import pytest

from core.dashboard import pair_history_service as service
from core.dashboard.pair_history_service import PairHistoryDataBundle


BASE_TS = 1_715_000_000
PAIR_A = "AAA-USDT-SWAP/BBB-USDT-SWAP"
PAIR_B = "CCC-USDT-SWAP/DDD-USDT-SWAP"
PAIR_C = "EEE-USDT-SWAP/FFF-USDT-SWAP"
PAIR_D = "GGG-USDT-SWAP/HHH-USDT-SWAP"
PAIR_E = "III-USDT-SWAP/JJJ-USDT-SWAP"
PAIR_F = "KKK-USDT-SWAP/LLL-USDT-SWAP"
PAIR_G = "MMM-USDT-SWAP/NNN-USDT-SWAP"


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    service.clear_pair_history_cache()


def _trade(pair: str, ts: int, pnl: float | None, **extra):
    payload = {
        "id": f"{pair}:{ts}:{pnl}",
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


def _patch_loader(monkeypatch: pytest.MonkeyPatch, bundle: PairHistoryDataBundle):
    calls: list[tuple[int | None, int | None]] = []

    def fake_loader(start_ts: int | None, end_ts: int | None) -> PairHistoryDataBundle:
        calls.append((start_ts, end_ts))
        return bundle

    monkeypatch.setattr(service, "_load_pair_history_data", fake_loader)
    return calls


def _rows(payload: dict) -> dict[str, dict]:
    return {row["pair"]: row for row in payload["rows"]}


def test_missing_data_returns_empty_rows_zero_kpis_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_loader(monkeypatch, PairHistoryDataBundle())

    payload = service.get_pair_history_summary(refresh=True)

    assert payload["rows"] == []
    assert payload["meta"] == {
        "page": 1,
        "page_size": 50,
        "total_rows": 0,
        "total_pages": 0,
        "sort_by": "net_pnl_usdt",
        "sort_dir": "desc",
    }
    assert payload["kpis"] == {
        "total_pairs": 0,
        "tradable_pairs": 0,
        "profitable_pairs": 0,
        "losing_pairs": 0,
        "hospital_pairs": 0,
        "graveyard_pairs": 0,
    }
    assert payload["cache"]["cache_hit"] is False
    assert payload["cache"]["ttl_seconds"] == 300
    assert payload["cache"]["refresh_supported"] is True
    json.dumps(payload)


def test_pair_aggregation_calculates_total_trades_and_net_pnl(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = PairHistoryDataBundle(
        trades=(
            _trade(PAIR_A, BASE_TS + 60, 10.0),
            _trade(PAIR_A, BASE_TS + 120, -4.0),
            _trade(PAIR_B, BASE_TS + 180, 3.0),
        ),
        pair_state={"hospital": {}, "graveyard": {}},
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_pair_history_summary(refresh=True, sort_by="pair")
    rows = _rows(payload)

    assert rows[PAIR_A]["total_trades"] == 2
    assert rows[PAIR_A]["net_pnl_usdt"] == 6.0
    assert rows[PAIR_A]["realized_pnl_usdt"] == 6.0
    assert rows[PAIR_A]["status"] == "stable"
    assert rows[PAIR_B]["total_trades"] == 1
    assert payload["kpis"]["total_pairs"] == 2
    assert payload["kpis"]["tradable_pairs"] == 2


def test_win_rate_and_profit_factor_calculate_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = PairHistoryDataBundle(
        trades=(
            _trade(PAIR_A, BASE_TS + 60, 10.0),
            _trade(PAIR_A, BASE_TS + 120, -4.0),
            _trade(PAIR_A, BASE_TS + 180, 6.0),
        ),
    )
    _patch_loader(monkeypatch, bundle)

    row = service.get_pair_history_summary(refresh=True)["rows"][0]

    assert row["win_rate"] == pytest.approx(2 / 3)
    assert row["profit_factor"] == pytest.approx(4.0)


def test_best_and_worst_trade_selected_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = PairHistoryDataBundle(
        trades=(
            _trade(PAIR_A, BASE_TS + 60, 1.0),
            _trade(PAIR_A, BASE_TS + 120, 12.0, side="BUY_SPREAD"),
            _trade(PAIR_A, BASE_TS + 180, -5.0, exit_reason="stop"),
        ),
    )
    _patch_loader(monkeypatch, bundle)

    row = service.get_pair_history_summary(refresh=True)["rows"][0]

    assert row["best_trade"]["pnl_usdt"] == 12.0
    assert row["best_trade"]["side"] == "BUY_SPREAD"
    assert row["worst_trade"]["pnl_usdt"] == -5.0
    assert row["worst_trade"]["exit_reason"] == "stop"


def test_date_filtering_uses_trade_timestamps(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = PairHistoryDataBundle(
        trades=(
            _trade(PAIR_A, BASE_TS - 60, 10.0),
            _trade(PAIR_A, BASE_TS + 60, 3.0),
            _trade(PAIR_B, BASE_TS + 120, 2.0),
        ),
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_pair_history_summary(start_ts=BASE_TS, end_ts=BASE_TS + 90, refresh=True)

    assert [row["pair"] for row in payload["rows"]] == [PAIR_A]
    assert payload["rows"][0]["net_pnl_usdt"] == 3.0


def test_status_filtering_uses_pair_state(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = PairHistoryDataBundle(
        trades=(_trade(PAIR_A, BASE_TS + 60, 1.0), _trade(PAIR_B, BASE_TS + 60, 1.0)),
        pair_state={"hospital": {PAIR_A: {"reason": "test"}}, "graveyard": {PAIR_B: {"reason": "manual"}}},
    )
    _patch_loader(monkeypatch, bundle)

    hospital = service.get_pair_history_summary(status="hospital", refresh=True)
    graveyard = service.get_pair_history_summary(status="graveyard", refresh=True)

    assert [row["pair"] for row in hospital["rows"]] == [PAIR_A]
    assert [row["pair"] for row in graveyard["rows"]] == [PAIR_B]
    assert hospital["kpis"]["hospital_pairs"] == 1
    assert graveyard["kpis"]["graveyard_pairs"] == 1


def test_pnl_filter_winners_and_losers(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = PairHistoryDataBundle(
        trades=(_trade(PAIR_A, BASE_TS + 60, 5.0), _trade(PAIR_B, BASE_TS + 60, -2.0)),
    )
    _patch_loader(monkeypatch, bundle)

    winners = service.get_pair_history_summary(pnl_filter="winners", refresh=True)
    losers = service.get_pair_history_summary(pnl_filter="losers", refresh=True)

    assert [row["pair"] for row in winners["rows"]] == [PAIR_A]
    assert [row["pair"] for row in losers["rows"]] == [PAIR_B]


def test_significant_only_filters_with_all_threshold_types(monkeypatch: pytest.MonkeyPatch) -> None:
    trades = (
        _trade(PAIR_A, BASE_TS + 60, 5.0),
        *(_trade(PAIR_B, BASE_TS + 60 + idx, 0.0) for idx in range(5)),
        _trade(PAIR_C, BASE_TS + 60, 10.0),
        _trade(PAIR_C, BASE_TS + 120, -6.0),
        _trade(PAIR_D, BASE_TS + 60, 2.0),
        _trade(PAIR_E, BASE_TS + 60, -2.0),
        _trade(PAIR_F, BASE_TS + 60, 1.0),
    )
    _patch_loader(monkeypatch, PairHistoryDataBundle(trades=trades))

    payload = service.get_pair_history_summary(significant_only=True, sort_by="pair", sort_dir="asc", refresh=True)

    assert {row["pair"] for row in payload["rows"]} == {PAIR_A, PAIR_B, PAIR_C, PAIR_D, PAIR_E}
    assert PAIR_F not in {row["pair"] for row in payload["rows"]}


def test_search_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_loader(monkeypatch, PairHistoryDataBundle(trades=(_trade(PAIR_A, BASE_TS + 60, 1.0),)))

    payload = service.get_pair_history_summary(search="aaa-usdt", refresh=True)

    assert [row["pair"] for row in payload["rows"]] == [PAIR_A]


def test_sorting_for_supported_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = PairHistoryDataBundle(
        trades=(
            _trade(PAIR_A, BASE_TS + 300, 3.0),
            _trade(PAIR_A, BASE_TS + 360, -1.0),
            _trade(PAIR_B, BASE_TS + 120, 7.0),
            _trade(PAIR_C, BASE_TS + 480, -2.0),
            _trade(PAIR_C, BASE_TS + 540, 1.0),
            _trade(PAIR_C, BASE_TS + 600, 1.0),
        )
    )
    _patch_loader(monkeypatch, bundle)

    by_pnl = service.get_pair_history_summary(sort_by="net_pnl_usdt", sort_dir="desc", refresh=True)
    by_trades = service.get_pair_history_summary(sort_by="total_trades", sort_dir="desc", refresh=True)
    by_win = service.get_pair_history_summary(sort_by="win_rate", sort_dir="desc", refresh=True)
    by_last = service.get_pair_history_summary(sort_by="last_traded_at", sort_dir="asc", refresh=True)

    assert [row["pair"] for row in by_pnl["rows"]] == [PAIR_B, PAIR_A, PAIR_C]
    assert by_trades["rows"][0]["pair"] == PAIR_C
    assert by_win["rows"][0]["pair"] == PAIR_B
    assert [row["pair"] for row in by_last["rows"]] == [PAIR_B, PAIR_A, PAIR_C]


def test_pagination_works(monkeypatch: pytest.MonkeyPatch) -> None:
    trades = tuple(_trade(f"PAIR-{idx}/USDT", BASE_TS + idx, float(idx)) for idx in range(5))
    _patch_loader(monkeypatch, PairHistoryDataBundle(trades=trades))

    payload = service.get_pair_history_summary(sort_by="total_trades", sort_dir="asc", page=2, page_size=2, refresh=True)

    assert payload["meta"]["total_rows"] == 5
    assert payload["meta"]["total_pages"] == 3
    assert payload["meta"]["page"] == 2
    assert len(payload["rows"]) == 2


def test_cache_hit_and_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_loader(monkeypatch, PairHistoryDataBundle(trades=(_trade(PAIR_A, BASE_TS + 60, 1.0),)))

    first = service.get_pair_history_summary()
    second = service.get_pair_history_summary()

    assert len(calls) == 1
    assert first["cache"]["cache_hit"] is False
    assert second["cache"]["cache_hit"] is True


def test_refresh_true_bypasses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int | None, int | None]] = []

    def fake_loader(start_ts: int | None, end_ts: int | None) -> PairHistoryDataBundle:
        calls.append((start_ts, end_ts))
        pnl = float(len(calls))
        return PairHistoryDataBundle(trades=(_trade(PAIR_A, BASE_TS + 60, pnl),))

    monkeypatch.setattr(service, "_load_pair_history_data", fake_loader)

    first = service.get_pair_history_summary()
    refreshed = service.get_pair_history_summary(refresh=True)

    assert len(calls) == 2
    assert first["rows"][0]["net_pnl_usdt"] == 1.0
    assert refreshed["cache"]["cache_hit"] is False
    assert refreshed["rows"][0]["net_pnl_usdt"] == 2.0


def test_missing_optional_hedge_and_ml_data_remains_null(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_loader(monkeypatch, PairHistoryDataBundle(trades=(_trade(PAIR_A, BASE_TS + 60, 0.0),)))

    row = service.get_pair_history_summary(refresh=True)["rows"][0]

    assert row["avg_hedge_ratio"] is None
    assert row["avg_hedge_drift_pct"] is None
    assert row["best_trade"]["entry_hedge_ratio"] is None
    assert row["best_trade"]["final_rank_score_at_entry"] is None
    assert row["best_trade"]["bayesian_posterior_at_entry"] is None


def test_hedge_drift_filter_and_block_reason_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    event = {
        "ts": BASE_TS + 70,
        "event_type": "replay_blocked_signal",
        "payload_json": {"pair": PAIR_A, "block_reasons": ["pair_in_hospital", "liquidity_failed"]},
    }
    bundle = PairHistoryDataBundle(
        trades=(
            _trade(PAIR_A, BASE_TS + 60, 1.0, payload_json={"hedge_ratio_drift_pct": 0.25}),
            _trade(PAIR_B, BASE_TS + 60, 1.0),
        ),
        run_events=(event,),
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_pair_history_summary(hedge_drift_filter="high_drift", refresh=True)

    assert [row["pair"] for row in payload["rows"]] == [PAIR_A]
    assert payload["rows"][0]["avg_hedge_drift_pct"] == 0.25
    assert payload["rows"][0]["block_reason_counts"] == {"pair_in_hospital": 1, "liquidity_failed": 1}


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


def test_response_is_json_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = PairHistoryDataBundle(
        trades=(
            _trade(
                PAIR_G,
                BASE_TS + 60,
                0.0,
                fees_usdt=0.0,
                slippage_usdt=0.0,
                payload_json={"entry_hedge_ratio": 1.2, "final_rank_score": 0.0},
            ),
        ),
        pair_state={"hospital": {}, "graveyard": {}, "health_failures": {PAIR_G: {"reason": "stale"}}},
    )
    _patch_loader(monkeypatch, bundle)

    payload = service.get_pair_history_summary(refresh=True)

    assert payload["rows"][0]["status"] == "warning"
    assert payload["rows"][0]["best_trade"]["fees_usdt"] == 0.0
    assert payload["rows"][0]["best_trade"]["final_rank_score_at_entry"] == 0.0
    json.dumps(payload)
