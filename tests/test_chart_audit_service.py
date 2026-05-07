from __future__ import annotations

from core.chart_audit import chart_audit_service as service
from core.chart_audit.marker_types import ActualMarkerType, StatisticalMarkerType


def test_pair_decision_audit_chart_returns_phase_1_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        service,
        "_load_existing_pair_chart_detail",
        lambda pair, timeframe, start_ts, end_ts: {
            "points": [
                {
                    "ts": 1_715_000_000,
                    "zscore": None,
                    "spread": -4.20,
                    "spread_mean": -4.18,
                    "crossing_spread": None,
                    "crossing_label": None,
                },
                {
                    "ts": 1_715_000_060,
                    "zscore": 0.12,
                    "spread": -4.18,
                    "spread_mean": -4.18,
                    "crossing_spread": -4.18,
                    "crossing_label": "#1",
                },
            ]
        },
    )
    monkeypatch.setattr(
        service,
        "_load_actual_records",
        lambda pair, start_ts, end_ts: [
            {
                "event_type": "trade_open",
                "event_id": "evt-entry",
                "timestamp": 1_715_000_023.527,
                "payload": {
                    "trade_id": "trade-1",
                    "pair": "AAA-USDT-SWAP/BBB-USDT-SWAP",
                    "side": "buy_spread",
                    "z_score": -2.1,
                },
            }
        ],
    )

    payload = service.get_pair_decision_audit_chart(
        "AAA-USDT-SWAP/BBB-USDT-SWAP",
        "1m",
        1_715_000_000,
        1_715_000_120,
    )

    assert payload["pair"] == "AAA-USDT-SWAP/BBB-USDT-SWAP"
    assert payload["timeframe"] == "1m"
    assert len(payload["zscore_series"]) == 2
    assert payload["zscore_series"][1]["zscore"] == 0.12
    assert payload["statistical_markers"] == [
        {
            "timestamp": 1_715_000_060.0,
            "marker_category": "statistical",
            "marker_type": StatisticalMarkerType.HISTORICAL_MEAN_CROSSING.value,
            "spread": -4.18,
            "zscore": 0.12,
            "label": "#1",
            "metadata": {"source": "existing_chart_data"},
        }
    ]
    assert payload["replay_markers"] == []
    assert payload["counterfactual_exit_studies"] == []
    assert payload["counterfactuals_lazy_load"] is True
    assert payload["decision_score_timeline"] == []

    actual_marker = payload["actual_markers"][0]
    assert actual_marker["marker_type"] == ActualMarkerType.ACTUAL_ENTRY.value
    assert actual_marker["entry_id"] == "actual_trade-1"
    assert actual_marker["timestamp"] == 1_715_000_023.527
    assert actual_marker["original_event_timestamp"] == 1_715_000_023.527
    assert actual_marker["timestamp_alignment"] == "exact"


def test_pair_decision_audit_chart_degrades_when_sources_are_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(service, "_load_existing_pair_chart_detail", lambda *args: None)
    monkeypatch.setattr(service, "_load_actual_records", lambda *args: [])

    payload = service.get_pair_decision_audit_chart(
        "AAA-USDT-SWAP/BBB-USDT-SWAP",
        "1m",
        None,
        None,
    )

    assert payload["zscore_series"] == []
    assert payload["statistical_markers"] == []
    assert payload["actual_markers"] == []
    assert payload["replay_markers"] == []
    assert payload["counterfactual_exit_studies"] == []
    assert payload["counterfactuals_lazy_load"] is True
    assert payload["decision_score_timeline"] == []
