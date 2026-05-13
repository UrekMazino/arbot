from __future__ import annotations

from core.chart_audit.marker_types import BlockReason, CuratorState, ReplayMarkerType
from core.chart_audit.ml_replay_scoring_bridge import ReplayMLScoringBridge
from core.chart_audit.ml_replay_types import ML_REPLAY_MARKER_METADATA_FIELDS, MLScoreSource, ReplayMLGateConfig, ReplayMLScoreSnapshot
from core.chart_audit.point_in_time_replay import PointInTimeReplayEngine
from core.chart_audit.replay_snapshot import FrozenCointegrationResult, ReplayConfigSnapshot, ReplaySnapshot


BASE_TS = 1_715_000_000


def _config(
    *,
    ml_gate_config: ReplayMLGateConfig | None = None,
    target_gross_pair_notional_usdt: float | None = None,
) -> ReplayConfigSnapshot:
    return ReplayConfigSnapshot(
        config_version="test",
        config_source="historical",
        entry_z_threshold=2.0,
        exit_z_threshold=0.35,
        persistence_candles=2,
        max_hold_seconds=180.0,
        min_zero_crossings=2,
        min_liquidity_score=0.2,
        max_orderbook_age_ms=1_000.0,
        max_spread_bps=5.0,
        max_slippage_bps=8.0,
        min_cointegration_window=1,
        target_gross_pair_notional_usdt=target_gross_pair_notional_usdt,
        ml_gate_config=ml_gate_config or ReplayMLGateConfig(),
    )


def _snapshot(zscores: list[float], *, config: ReplayConfigSnapshot | None = None) -> ReplaySnapshot:
    timestamp = BASE_TS + (len(zscores) - 1) * 60
    spreads = tuple(float(idx) for idx in range(len(zscores)))
    cfg = config or _config()
    return ReplaySnapshot(
        pair="AAA-USDT-SWAP/BBB-USDT-SWAP",
        timeframe="1m",
        timestamp=timestamp,
        candles_until_t=tuple({"timestamp": BASE_TS + idx * 60, "spread": spread} for idx, spread in enumerate(spreads)),
        zscore_until_t=tuple(zscores),
        spread_until_t=spreads,
        rolling_mean_until_t=None,
        rolling_std_until_t=None,
        hedge_ratio_until_t=1.0,
        cointegration_result_until_t=FrozenCointegrationResult(
            p_value=0.01,
            adf_stat=-3.0,
            hedge_ratio=1.0,
            zero_crossings=3,
            is_valid=True,
        ),
        zero_crossing_count_until_t=3,
        curator_state=CuratorState.TRADABLE,
        curator_state_source="historical",
        pair_health_state="stable",
        orderbook_snapshot={
            "timestamp": timestamp,
            "book_freshness_ms": 500.0,
            "spread_bps": 2.0,
            "slippage_bps": 3.0,
            "liquidity_score": 0.8,
        },
        config_snapshot=cfg,
        config_source=cfg.config_source,
        actual_events_at_t=(),
    )


def _engine_with_score(score: ReplayMLScoreSnapshot) -> PointInTimeReplayEngine:
    return PointInTimeReplayEngine(
        ml_scoring_bridge=ReplayMLScoringBridge(score_lookup=lambda _pair, _timestamp: score)
    )


def test_replay_marker_metadata_includes_all_phase_2_5_fields() -> None:
    score = ReplayMLScoreSnapshot(
        pair="AAA-USDT-SWAP/BBB-USDT-SWAP",
        timestamp=BASE_TS + 60,
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

    marker = _engine_with_score(score).evaluate(_snapshot([-2.1, -2.2]))[0]

    for field in ML_REPLAY_MARKER_METADATA_FIELDS:
        assert field in marker.metadata
    assert marker.metadata["score_source"] == "stored_live"
    assert marker.metadata["regime_name"] == "mean_reverting"


def test_ml_gate_disabled_leaves_existing_replay_behavior_unchanged() -> None:
    config = _config(ml_gate_config=ReplayMLGateConfig(enabled=False))
    score = ReplayMLScoreSnapshot(score_source=MLScoreSource.STORED_LIVE, break_risk=0.95)

    marker = _engine_with_score(score).evaluate(_snapshot([-2.1, -2.2], config=config))[0]

    assert marker.marker_type == ReplayMarkerType.REPLAY_ENTRY_CANDIDATE
    assert marker.passed is True


def test_ml_gate_enabled_blocks_replay_entry_due_to_high_break_risk() -> None:
    score = ReplayMLScoreSnapshot(score_source=MLScoreSource.STORED_LIVE, break_risk=0.95)

    marker = _engine_with_score(score).evaluate(_snapshot([-2.1, -2.2]))[0]

    assert marker.marker_type == ReplayMarkerType.REPLAY_BLOCKED_SIGNAL
    assert marker.passed is False
    assert BlockReason.REGIME_BREAK_RISK_HIGH in marker.block_reasons


def test_ml_gate_enabled_blocks_replay_entry_due_to_low_final_rank_score() -> None:
    score = ReplayMLScoreSnapshot(score_source=MLScoreSource.STORED_LIVE, final_rank_score=0.2)

    marker = _engine_with_score(score).evaluate(_snapshot([-2.1, -2.2]))[0]

    assert marker.marker_type == ReplayMarkerType.REPLAY_BLOCKED_SIGNAL
    assert marker.passed is False
    assert BlockReason.QUALITY_GATE_FAILED in marker.block_reasons


def test_ml_unavailable_does_not_block_valid_replay_entry() -> None:
    marker = PointInTimeReplayEngine().evaluate(_snapshot([-2.1, -2.2]))[0]

    assert marker.marker_type == ReplayMarkerType.REPLAY_ENTRY_CANDIDATE
    assert marker.passed is True
    assert marker.metadata["score_source"] == "unavailable"


def test_replay_with_stored_ml_score_is_deterministic() -> None:
    score = ReplayMLScoreSnapshot(score_source=MLScoreSource.STORED_LIVE, break_risk=0.2, final_rank_score=0.8)
    snapshots = [_snapshot([-2.1, -2.2]), _snapshot([-2.1, -2.2, -0.2])]

    first = [marker.to_dict() for marker in generate_replay_markers_with_score(snapshots, score)]
    second = [marker.to_dict() for marker in generate_replay_markers_with_score(snapshots, score)]

    assert first == second


def test_hedge_ratio_metadata_is_preserved_with_ml_metadata() -> None:
    score = ReplayMLScoreSnapshot(score_source=MLScoreSource.STORED_LIVE, break_risk=0.2)
    config = _config(target_gross_pair_notional_usdt=1500.0)

    marker = _engine_with_score(score).evaluate(_snapshot([-2.1, -2.2], config=config))[0]

    assert marker.metadata["score_source"] == "stored_live"
    assert marker.metadata["hedge_ratio_at_t"] == 1.0
    assert marker.metadata["hedge_ratio_source"] == "fresh_cointegration_at_entry"
    assert marker.metadata["target_gross_pair_notional_usdt"] == 1500.0
    assert marker.metadata["target_leg1_notional_usdt"] == 750.0
    assert marker.metadata["target_leg2_notional_usdt"] == 750.0


def generate_replay_markers_with_score(
    snapshots: list[ReplaySnapshot],
    score: ReplayMLScoreSnapshot,
) -> list[object]:
    engine = _engine_with_score(score)
    markers: list[object] = []
    for snapshot in snapshots:
        markers.extend(engine.evaluate(snapshot))
    return markers
