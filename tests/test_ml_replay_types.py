from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from core.chart_audit.marker_types import BlockReason
from core.chart_audit.ml_replay_types import (
    ML_REPLAY_MARKER_METADATA_FIELDS,
    MLScoreSource,
    ReplayMLGateConfig,
    ReplayMLScoreSnapshot,
    unavailable_ml_score,
)


def test_replay_ml_score_snapshot_has_explicit_source_and_nullable_fields() -> None:
    score = unavailable_ml_score("AAA/BBB", 100)

    assert score.score_source == MLScoreSource.UNAVAILABLE
    assert score.pair == "AAA/BBB"
    assert score.timestamp == 100
    assert score.hard_validation_valid is None
    assert score.regime_name is None
    assert score.regime_confidence is None
    assert score.break_risk is None
    assert score.bayesian_posterior is None
    assert score.bayesian_quality_grade is None
    assert score.final_rank_score is None
    assert score.microstructure_risk is None
    assert score.liquidity_score is None
    assert score.ev_hold_value_usdt is None
    assert score.exit_score is None
    assert score.quality_gate_passed is None


def test_replay_ml_score_snapshot_is_frozen_and_serializes_block_reasons() -> None:
    score = ReplayMLScoreSnapshot(
        pair="AAA/BBB",
        timestamp=100,
        score_source="stored_live",
        break_risk="0.7",
        block_reasons=("regime_break_risk_high", BlockReason.QUALITY_GATE_FAILED),
        metadata={"b": [2, 3], "a": "first"},
    )

    assert score.score_source == MLScoreSource.STORED_LIVE
    assert score.break_risk == 0.7
    assert score.block_reasons == (
        BlockReason.REGIME_BREAK_RISK_HIGH,
        BlockReason.QUALITY_GATE_FAILED,
    )
    assert score.to_dict()["block_reasons"] == ["regime_break_risk_high", "quality_gate_failed"]
    assert score.to_dict()["metadata"] == {"a": "first", "b": [2, 3]}
    with pytest.raises(FrozenInstanceError):
        score.break_risk = 0.2  # type: ignore[misc]


def test_marker_metadata_contains_phase_2_5_fields() -> None:
    score = ReplayMLScoreSnapshot(
        pair="AAA/BBB",
        timestamp=100,
        score_source=MLScoreSource.STORED_LIVE,
        hard_validation_valid=True,
        regime_name="mean_reverting",
        regime_confidence=0.8,
        break_risk=0.2,
        bayesian_posterior=0.7,
        bayesian_quality_grade="B",
        final_rank_score=0.9,
        microstructure_risk=0.1,
        liquidity_score=0.95,
        ev_hold_value_usdt=0.42,
        exit_score=0.3,
        quality_gate_passed=True,
    )

    metadata = score.to_marker_metadata()

    for field in ML_REPLAY_MARKER_METADATA_FIELDS:
        assert field in metadata
    assert metadata["score_source"] == "stored_live"


def test_replay_ml_gate_config_defaults_and_coercion() -> None:
    config = ReplayMLGateConfig(enabled="true", min_liquidity_score="0.2")

    assert config.enabled is True
    assert config.min_bayesian_posterior == 0.55
    assert config.min_final_rank_score == 0.50
    assert config.max_break_risk == 0.65
    assert config.max_microstructure_risk == 0.70
    assert config.min_liquidity_score == 0.2
    assert config.require_hard_validation is True
