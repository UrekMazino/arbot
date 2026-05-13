from __future__ import annotations

from core.chart_audit.counterfactual_exit_study import (
    CounterfactualExitStrategy,
    build_counterfactual_exit_study,
)
from core.chart_audit.curator_state_source import CuratorStateAtResult
from core.chart_audit.marker_types import CuratorState
from core.chart_audit.replay_snapshot import ReplayConfigSnapshot
from core.chart_audit.replay_snapshot_factory import ReplaySnapshotFactory


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


def _curator(timestamp: int) -> CuratorStateAtResult:
    return CuratorStateAtResult(
        curator_state=CuratorState.TRADABLE,
        curator_state_source="historical",
        transition_timestamp=timestamp,
    )


def _point(idx: int, spread: float, zscore: float | None = None) -> dict[str, float]:
    return {
        "timestamp": BASE_TS + idx * 60,
        "spread": spread,
        "spread_mean": 0.0,
        "zscore": spread if zscore is None else zscore,
        "price_1": 100.0 + idx,
        "price_2": 100.0,
    }


def _replay_payloads(points: list[dict[str, float]]) -> list[dict[str, object]]:
    factory = ReplaySnapshotFactory(
        pair=PAIR,
        timeframe="1m",
        candles=points,
        curator_state_at=_curator,
        config_at=_config,
    )
    return [marker.to_dict() for marker in factory.replay()]


def test_counterfactual_uses_only_candles_after_entry() -> None:
    entry = {
        "marker_type": "replay_entry_candidate",
        "entry_id": f"replay_{PAIR}_{BASE_TS}_BUY_SPREAD",
        "timestamp": BASE_TS,
        "side": "BUY_SPREAD",
        "z_score": -2.0,
        "spread": -2.0,
        "metadata": {"target_gross_pair_notional_usdt": 1000.0, "hedge_ratio_at_t": 1.0},
    }
    study = build_counterfactual_exit_study(
        entry_marker=entry,
        pair=PAIR,
        timeframe="1m",
        chart_points=[
            _point(-2, 0.0),
            _point(-1, -0.1),
            _point(0, -2.0),
            _point(1, -0.4),
        ],
    )

    result = next(item for item in study.results if item.exit_strategy == CounterfactualExitStrategy.EXIT_AT_Z_0_50)

    assert result.hypothetical_exit_timestamp == BASE_TS + 60
    assert result.metadata["post_entry_candle_count"] == 1


def test_counterfactual_results_do_not_change_replay_entry_generation() -> None:
    points = [_point(0, 0.0), _point(1, 0.0), _point(2, -10.0), _point(3, -0.1)]
    before = _replay_payloads(points)
    entry = {
        "marker_type": "replay_entry_candidate",
        "entry_id": f"replay_{PAIR}_{BASE_TS + 120}_BUY_SPREAD",
        "timestamp": BASE_TS + 120,
        "side": "BUY_SPREAD",
        "z_score": -10.0,
        "spread": -10.0,
        "metadata": {"target_gross_pair_notional_usdt": 1000.0, "hedge_ratio_at_t": 1.0},
    }

    build_counterfactual_exit_study(
        entry_marker=entry,
        pair=PAIR,
        timeframe="1m",
        chart_points=points,
    )

    after = _replay_payloads(points)
    assert before == after
