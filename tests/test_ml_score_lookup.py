from __future__ import annotations

from core.chart_audit.ml_replay_types import MLScoreSource
from core.chart_audit.ml_score_lookup import get_score_source_for_range, get_stored_score_at


PAIR = "AAA-USDT-SWAP/BBB-USDT-SWAP"


def _event(event_type: str, timestamp: int, payload: dict[str, object]) -> dict[str, object]:
    return {
        "event_type": event_type,
        "timestamp": timestamp,
        "payload": {"pair": PAIR, **payload},
    }


def test_stored_ml_lookup_ignores_scores_after_timestamp() -> None:
    records = [
        _event("advanced_ml_regime_shadow", 100, {"advanced_regime": "mean_reverting", "break_risk": 0.2}),
        _event("advanced_ml_exit_shadow", 200, {"total_exit_score": 0.9, "book_stress": 0.8}),
    ]

    score = get_stored_score_at(PAIR, 150, stored_events=records)

    assert score is not None
    assert score.timestamp == 100
    assert score.score_source == MLScoreSource.STORED_LIVE
    assert score.break_risk == 0.2
    assert score.exit_score is None


def test_stored_ml_lookup_uses_latest_score_at_or_before_timestamp() -> None:
    records = [
        _event("advanced_ml_regime_shadow", 100, {"advanced_regime": "mean_reverting", "break_risk": 0.2}),
        _event("advanced_ml_exit_shadow", 200, {"total_exit_score": 0.4, "expected_hold_value_usdt": 1.25}),
    ]

    score = get_stored_score_at(PAIR, 250, stored_events=records)

    assert score is not None
    assert score.timestamp == 200
    assert score.regime_name == "mean_reverting"
    assert score.break_risk == 0.2
    assert score.exit_score == 0.4
    assert score.ev_hold_value_usdt == 1.25


def test_missing_ml_score_returns_none_without_current_runtime_fallback() -> None:
    records = [
        _event("advanced_ml_regime_shadow", 300, {"advanced_regime": "mean_reverting", "break_risk": 0.2}),
    ]

    assert get_stored_score_at(PAIR, 200, stored_events=records) is None
    assert get_stored_score_at(PAIR, 200) is None


def test_lookup_normalizes_trade_quality_gate_and_learning_events() -> None:
    records = [
        _event("trade_quality_gate", 100, {"passed": False, "hard_reasons": ["zero_crossings_below_hard_min"]}),
        _event(
            "advanced_ml_learning_update",
            120,
            {
                "bayesian_posterior": 0.61,
                "bayesian_quality_grade": "C",
                "final_rank_score": 0.72,
            },
        ),
    ]

    score = get_stored_score_at(PAIR, 150, stored_events=records)

    assert score is not None
    assert score.quality_gate_passed is False
    assert score.hard_validation_valid is False
    assert score.bayesian_posterior == 0.61
    assert score.bayesian_quality_grade == "C"
    assert score.final_rank_score == 0.72
    assert [reason.value for reason in score.block_reasons] == ["zero_crossings_too_low"]


def test_unknown_payload_shape_is_unavailable_safely() -> None:
    records = [_event("advanced_ml_regime_shadow", 100, {"unrelated": "value"})]

    assert get_stored_score_at(PAIR, 150, stored_events=records) is None


def test_score_source_for_range_returns_stored_rows_only() -> None:
    records = [
        _event("advanced_ml_regime_shadow", 100, {"advanced_regime": "mean_reverting", "break_risk": 0.2}),
        _event("advanced_ml_exit_shadow", 200, {"total_exit_score": 0.4}),
        _event("advanced_ml_exit_shadow", 300, {"total_exit_score": 0.9}),
    ]

    rows = get_score_source_for_range(PAIR, 150, 250, stored_events=records)

    assert len(rows) == 1
    assert rows[0].timestamp == 200
    assert rows[0].score_source == MLScoreSource.STORED_LIVE
