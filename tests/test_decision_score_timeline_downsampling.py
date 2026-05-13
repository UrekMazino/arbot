from __future__ import annotations

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


def _score(idx: int, value: float, *, regime: str = "a") -> ReplayMLScoreSnapshot:
    return ReplayMLScoreSnapshot(
        pair=PAIR,
        timestamp=BASE_TS + idx * 60,
        score_source=MLScoreSource.STORED_LIVE,
        regime_name=regime,
        break_risk=value,
        bayesian_posterior=value,
        final_rank_score=value,
        quality_gate_passed=value >= 0.5,
    )


def _timeline(max_points: int, method: str, *, scores=None):
    return build_decision_score_timeline(
        pair=PAIR,
        timeframe="1m",
        candles=[_candle(idx) for idx in range(6)],
        stored_scores=scores if scores is not None else [_score(idx, idx / 10.0, regime=f"r{idx}") for idx in range(6)],
        config=DecisionScoreTimelineConfig(
            include_decision_timeline=True,
            max_timeline_points=max_points,
            downsample_method=method,
        ),
        config_at=_config,
    )


def test_max_timeline_points_caps_returned_rows_and_meta_counts() -> None:
    timeline = _timeline(3, "last")
    meta = timeline.meta.to_dict()

    assert len(timeline.points) <= 3
    assert meta["timeline_original_points"] == 6
    assert meta["timeline_returned_points"] == 3
    assert meta["timeline_downsample_method"] == "last"


def test_last_downsampling_uses_latest_row_in_each_bucket() -> None:
    timeline = _timeline(3, "last")
    rows = [point.to_dict() for point in timeline.points]

    assert [row["timestamp"] for row in rows] == [BASE_TS + 60, BASE_TS + 180, BASE_TS + 300]
    assert [row["regime"] for row in rows] == ["r1", "r3", "r5"]


def test_mean_downsampling_averages_numeric_and_keeps_last_categorical() -> None:
    timeline = _timeline(3, "mean")
    rows = [point.to_dict() for point in timeline.points]

    assert rows[0]["break_risk"] == 0.05
    assert rows[0]["bayesian_posterior"] == 0.05
    assert rows[0]["final_rank_score"] == 0.05
    assert rows[0]["regime"] == "r1"
    assert rows[0]["quality_gate_passed"] is False
    assert rows[2]["regime"] == "r5"
    assert rows[2]["quality_gate_passed"] is True


def test_none_downsampling_returns_all_rows() -> None:
    timeline = _timeline(2, "none")

    assert len(timeline.points) == 6
    assert timeline.meta.timeline_original_points == 6
    assert timeline.meta.timeline_returned_points == 6
