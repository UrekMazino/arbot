from __future__ import annotations

import pytest

from core.chart_audit.marker_types import BlockReason, CuratorState
from core.chart_audit.ml_replay_scoring_bridge import ReplayMLScoringBridge, evaluate_replay_ml_gate
from core.chart_audit.ml_replay_types import MLScoreSource, ReplayMLGateConfig, ReplayMLScoreSnapshot
from core.chart_audit.replay_snapshot import FrozenCointegrationResult, ReplayConfigSnapshot, ReplaySnapshot


BASE_TS = 1_715_000_000


def _config() -> ReplayConfigSnapshot:
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


def _snapshot() -> ReplaySnapshot:
    return ReplaySnapshot(
        pair="AAA/BBB",
        timeframe="1m",
        timestamp=BASE_TS,
        candles_until_t=({"timestamp": BASE_TS, "spread": 0.0},),
        zscore_until_t=(-2.2,),
        spread_until_t=(0.0,),
        rolling_mean_until_t=None,
        rolling_std_until_t=None,
        hedge_ratio_until_t=1.0,
        cointegration_result_until_t=FrozenCointegrationResult(hedge_ratio=1.0, is_valid=True),
        zero_crossing_count_until_t=3,
        curator_state=CuratorState.TRADABLE,
        curator_state_source="historical",
        pair_health_state="stable",
        orderbook_snapshot={"timestamp": BASE_TS, "liquidity_score": 0.8},
        config_snapshot=_config(),
        config_source="historical",
        actual_events_at_t=(),
    )


def test_replay_scoring_bridge_rejects_non_replay_snapshot_inputs() -> None:
    with pytest.raises(TypeError, match="requires a ReplaySnapshot"):
        ReplayMLScoringBridge().score({"timestamp": BASE_TS})  # type: ignore[arg-type]


def test_replay_scoring_bridge_returns_unavailable_when_lookup_missing() -> None:
    score = ReplayMLScoringBridge().score(_snapshot())

    assert score.score_source == MLScoreSource.UNAVAILABLE
    assert score.break_risk is None


def test_replay_scoring_bridge_prefers_stored_lookup() -> None:
    stored = ReplayMLScoreSnapshot(
        pair="AAA/BBB",
        timestamp=BASE_TS,
        score_source=MLScoreSource.STORED_LIVE,
        break_risk=0.2,
    )

    score = ReplayMLScoringBridge(score_lookup=lambda _pair, _timestamp: stored).score(_snapshot())

    assert score is stored


def test_ml_gate_blocks_high_break_risk() -> None:
    result = evaluate_replay_ml_gate(
        ReplayMLScoreSnapshot(score_source=MLScoreSource.STORED_LIVE, break_risk=0.9),
        ReplayMLGateConfig(max_break_risk=0.65),
    )

    assert result.passed is False
    assert result.block_reasons == (BlockReason.REGIME_BREAK_RISK_HIGH,)


def test_ml_gate_blocks_low_final_rank_score() -> None:
    result = evaluate_replay_ml_gate(
        ReplayMLScoreSnapshot(score_source=MLScoreSource.STORED_LIVE, final_rank_score=0.2),
        ReplayMLGateConfig(min_final_rank_score=0.5),
    )

    assert result.passed is False
    assert result.block_reasons == (BlockReason.QUALITY_GATE_FAILED,)


def test_ml_gate_does_not_block_unavailable_scores() -> None:
    result = evaluate_replay_ml_gate(
        ReplayMLScoreSnapshot(score_source=MLScoreSource.UNAVAILABLE, break_risk=0.9, final_rank_score=0.1),
        ReplayMLGateConfig(),
    )

    assert result.passed is True
    assert result.block_reasons == ()
