from __future__ import annotations

import pytest

from core.chart_audit import chart_audit_service as service
from core.chart_audit.decision_score_timeline import (
    DecisionScoreTimelineConfig,
    build_decision_score_timeline,
)
from core.chart_audit.ml_replay_types import MLScoreSource, ReplayMLScoreSnapshot
from core.chart_audit.replay_snapshot import ReplayConfigSnapshot


BASE_TS = 1_715_000_000
PAIR = "AAA-USDT-SWAP/BBB-USDT-SWAP"


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
    )


def _candle(idx: int) -> dict[str, float]:
    return {"timestamp": BASE_TS + idx * 60, "spread": float(idx)}


def test_no_lookahead_score_after_timestamp_is_not_used() -> None:
    timeline = build_decision_score_timeline(
        pair=PAIR,
        timeframe="1m",
        candles=[_candle(0), _candle(1)],
        stored_scores=[
            ReplayMLScoreSnapshot(
                pair=PAIR,
                timestamp=BASE_TS + 60,
                score_source=MLScoreSource.STORED_LIVE,
                break_risk=0.9,
            )
        ],
        config=DecisionScoreTimelineConfig(include_decision_timeline=True),
        config_at=_config,
    )
    rows = [point.to_dict() for point in timeline.points]

    assert rows[0]["score_source"] == "unavailable"
    assert rows[0]["break_risk"] is None
    assert rows[1]["score_source"] == "stored_live"
    assert rows[1]["break_risk"] == 0.9


def _chart_detail() -> dict[str, object]:
    return {
        "points": [
            {
                "ts": BASE_TS + idx * 60,
                "timestamp": BASE_TS + idx * 60,
                "spread": float(idx),
                "zscore": float(idx),
                "price_1": 100.0 + idx,
                "price_2": 100.0,
                "crossing_spread": None,
            }
            for idx in range(3)
        ]
    }


def test_chart_service_skips_timeline_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "_load_existing_pair_chart_detail", lambda *args: _chart_detail())
    monkeypatch.setattr(service, "_load_actual_records", lambda *args: [])
    monkeypatch.setattr(service, "_replay_markers_from_points", lambda **kwargs: [])

    called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("timeline should be optional")

    monkeypatch.setattr(service, "build_decision_score_timeline", fail_if_called)

    payload = service.get_pair_decision_audit_chart(PAIR, "1m", BASE_TS, BASE_TS + 120)

    assert payload["decision_score_timeline"] == []
    assert payload["decision_timeline_meta"]["timeline_returned_points"] == 0
    assert called is False


def test_chart_service_builds_timeline_when_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "_load_existing_pair_chart_detail", lambda *args: _chart_detail())
    monkeypatch.setattr(service, "_load_actual_records", lambda *args: [])
    monkeypatch.setattr(service, "_replay_markers_from_points", lambda **kwargs: [])
    monkeypatch.setattr(service, "config_at", _config)

    payload = service.get_pair_decision_audit_chart(
        PAIR,
        "1m",
        BASE_TS,
        BASE_TS + 120,
        include_decision_timeline=True,
        max_timeline_points=10,
    )

    assert len(payload["decision_score_timeline"]) == 3
    assert payload["decision_timeline_meta"]["timeline_original_points"] == 3
