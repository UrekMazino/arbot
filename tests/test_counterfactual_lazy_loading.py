from __future__ import annotations

import pytest

from core.chart_audit import chart_audit_service as service
from core.chart_audit.curator_state_source import CuratorStateAtResult
from core.chart_audit.marker_types import CuratorState
from core.chart_audit.replay_snapshot import ReplayConfigSnapshot


BASE_TS = 1_715_000_000
PAIR = "AAA-USDT-SWAP/BBB-USDT-SWAP"


def _chart_detail() -> dict[str, object]:
    return {
        "points": [
            {
                "ts": BASE_TS + idx * 60,
                "timestamp": BASE_TS + idx * 60,
                "spread": spread,
                "spread_mean": 0.0,
                "zscore": spread,
                "price_1": 100.0 + idx,
                "price_2": 100.0,
                "crossing_spread": None,
            }
            for idx, spread in enumerate([0.0, 0.0, -10.0, -0.4])
        ]
    }


def _config(_timestamp: int) -> ReplayConfigSnapshot:
    return ReplayConfigSnapshot(
        config_version="test",
        config_source="historical",
        entry_z_threshold=2.0,
        exit_z_threshold=0.35,
        persistence_candles=1,
        max_hold_seconds=3600.0,
        min_zero_crossings=0,
        min_cointegration_window=1,
        target_gross_pair_notional_usdt=1000.0,
    )


def _curator(timestamp: int) -> CuratorStateAtResult:
    return CuratorStateAtResult(
        curator_state=CuratorState.TRADABLE,
        curator_state_source="historical",
        transition_timestamp=timestamp,
    )


def _replay_markers(*_args, **_kwargs) -> list[dict[str, object]]:
    return [
        {
            "marker_type": "replay_entry_candidate",
            "entry_id": f"replay_{PAIR}_{BASE_TS + 120}_BUY_SPREAD",
            "timestamp": BASE_TS + 120,
            "side": "BUY_SPREAD",
            "z_score": -10.0,
            "spread": -10.0,
            "metadata": {
                "target_gross_pair_notional_usdt": 1000.0,
                "hedge_ratio_at_t": 1.0,
            },
        }
    ]


def _patch_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "_load_existing_pair_chart_detail", lambda *args: _chart_detail())
    monkeypatch.setattr(service, "_load_actual_records", lambda *args: [])
    monkeypatch.setattr(service, "_replay_markers_from_points", _replay_markers)
    monkeypatch.setattr(service, "config_at", _config)
    monkeypatch.setattr(service, "curator_state_at", lambda _pair, timestamp: _curator(timestamp))


def test_initial_chart_load_keeps_counterfactuals_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sources(monkeypatch)
    called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("counterfactuals should be lazy")

    monkeypatch.setattr(service, "build_counterfactual_exit_study", fail_if_called)

    payload = service.get_pair_decision_audit_chart(PAIR, "1m", BASE_TS, BASE_TS + 180)

    assert payload["counterfactual_exit_studies"] == []
    assert payload["counterfactuals_lazy_load"] is True
    assert called is False


def test_lazy_counterfactual_service_resolves_replay_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sources(monkeypatch)
    chart = service.get_pair_decision_audit_chart(PAIR, "1m", BASE_TS, BASE_TS + 180)
    entry_id = chart["replay_markers"][0]["entry_id"]

    study = service.get_counterfactual_exit_study(
        entry_id=entry_id,
        pair=PAIR,
        timeframe="1m",
        start_ts=BASE_TS,
        end_ts=BASE_TS + 180,
    )

    assert study["entry_id"] == entry_id
    assert study["entry_marker_type"] == "replay_entry_candidate"
    assert study["results"]


def test_lazy_counterfactual_service_rejects_unknown_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_sources(monkeypatch)

    with pytest.raises(ValueError, match="eligible actual_entry or replay_entry_candidate"):
        service.get_counterfactual_exit_study(
            entry_id="missing",
            pair=PAIR,
            timeframe="1m",
            start_ts=BASE_TS,
            end_ts=BASE_TS + 180,
        )
