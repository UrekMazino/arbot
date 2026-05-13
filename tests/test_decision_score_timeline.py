from __future__ import annotations

import math

from core.chart_audit.curator_state_source import CuratorStateAtResult
from core.chart_audit.decision_score_timeline import (
    DecisionScoreTimelineConfig,
    build_decision_score_timeline,
)
from core.chart_audit.marker_types import CuratorState
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
        min_cointegration_window=2,
    )


def _curator(timestamp: int) -> CuratorStateAtResult:
    return CuratorStateAtResult(
        curator_state=CuratorState.TRADABLE if timestamp < BASE_TS + 120 else CuratorState.ANALYSIS_ONLY,
        curator_state_source="historical",
        transition_timestamp=timestamp,
    )


def _candle(idx: int, *, beta: float = 1.0) -> dict[str, float]:
    x = 0.01 * idx
    return {
        "timestamp": BASE_TS + idx * 60,
        "close_1": 100.0 * math.exp(beta * x),
        "close_2": 100.0 * math.exp(x),
    }


def _timeline(candles, scores=(), markers=()):
    return build_decision_score_timeline(
        pair=PAIR,
        timeframe="1m",
        candles=candles,
        stored_scores=scores,
        config=DecisionScoreTimelineConfig(include_decision_timeline=True, max_timeline_points=100),
        curator_state_at=_curator,
        config_at=_config,
        entry_markers=markers,
    )


def test_latest_stored_score_at_or_before_timestamp_is_used() -> None:
    score = ReplayMLScoreSnapshot(
        pair=PAIR,
        timestamp=BASE_TS + 60,
        score_source=MLScoreSource.STORED_LIVE,
        regime_name="mean_reverting",
        break_risk=0.2,
        bayesian_posterior=0.7,
        final_rank_score=0.8,
    )

    timeline = _timeline([_candle(0), _candle(1), _candle(2)], [score])
    rows = [point.to_dict() for point in timeline.points]

    assert rows[0]["score_source"] == "unavailable"
    assert rows[1]["score_source"] == "stored_live"
    assert rows[2]["score_source"] == "stored_live"
    assert rows[2]["regime"] == "mean_reverting"
    assert rows[2]["bayesian_posterior"] == 0.7
    assert rows[2]["final_rank_score"] == 0.8


def test_missing_score_returns_unavailable_with_null_score_fields() -> None:
    timeline = _timeline([_candle(0), _candle(1)])
    row = timeline.points[-1].to_dict()

    assert row["score_source"] == "unavailable"
    assert row["regime"] is None
    assert row["regime_confidence"] is None
    assert row["break_risk"] is None
    assert row["bayesian_posterior"] is None
    assert row["final_rank_score"] is None
    assert row["microstructure_risk"] is None
    assert row["ev_hold_value_usdt"] is None
    assert row["exit_score"] is None
    assert row["quality_gate_passed"] is None


def test_timeline_includes_point_in_time_curator_state() -> None:
    timeline = _timeline([_candle(0), _candle(1), _candle(2)])
    rows = [point.to_dict() for point in timeline.points]

    assert rows[0]["curator_state"] == "tradable"
    assert rows[2]["curator_state"] == "analysis_only"
    assert rows[2]["curator_state_source"] == "historical"


def test_timeline_includes_hedge_ratio_and_active_entry_drift() -> None:
    markers = [
        {
            "marker_type": "replay_entry_candidate",
            "entry_id": f"replay_{PAIR}_{BASE_TS + 60}_BUY_SPREAD",
            "timestamp": BASE_TS + 60,
            "side": "BUY_SPREAD",
            "metadata": {"hedge_ratio_at_t": 1.0},
        }
    ]
    timeline = _timeline([_candle(0, beta=2.0), _candle(1, beta=2.0), _candle(2, beta=2.0)], markers=markers)
    row = timeline.points[-1].to_dict()

    assert row["hedge_ratio_at_t"] is not None
    assert row["hedge_ratio_at_t"] == 2.0
    assert row["hedge_ratio_drift_pct"] == 1.0
    assert row["metadata"]["active_entry_id"] == markers[0]["entry_id"]


def test_timeline_preserves_extra_score_fields_from_mapping_rows() -> None:
    timeline = _timeline(
        [_candle(0), _candle(1)],
        [
            {
                "pair": PAIR,
                "timestamp": BASE_TS,
                "score_source": "stored_live",
                "linucb_score": 0.44,
                "trade_quality_score": 0.66,
                "liquidity_score": 0.88,
                "quality_gate_passed": True,
            }
        ],
    )
    row = timeline.points[-1].to_dict()

    assert row["linucb_score"] == 0.44
    assert row["trade_quality_score"] == 0.66
    assert row["liquidity_score"] == 0.88
    assert row["quality_gate_passed"] is True
