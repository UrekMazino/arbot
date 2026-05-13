from __future__ import annotations

import math

import pytest

from core.chart_audit.counterfactual_exit_study import (
    CounterfactualExitConfig,
    CounterfactualExitStatus,
    CounterfactualExitStrategy,
    build_counterfactual_exit_study,
)
from core.chart_audit.ml_replay_types import MLScoreSource, ReplayMLScoreSnapshot


BASE_TS = 1_715_000_000
PAIR = "AAA-USDT-SWAP/BBB-USDT-SWAP"


def _point(idx: int, z: float, *, price_1: float = 100.0, price_2: float = 100.0) -> dict[str, float]:
    return {
        "timestamp": BASE_TS + idx * 60,
        "zscore": z,
        "spread": z,
        "spread_mean": 0.0,
        "price_1": price_1,
        "price_2": price_2,
    }


def _replay_entry(side: str = "BUY_SPREAD", *, timestamp: int = BASE_TS) -> dict[str, object]:
    return {
        "marker_type": "replay_entry_candidate",
        "entry_id": f"replay_{PAIR}_{timestamp}_{side}",
        "timestamp": timestamp,
        "side": side,
        "z_score": -2.0 if side == "BUY_SPREAD" else 2.0,
        "spread": -2.0 if side == "BUY_SPREAD" else 2.0,
        "metadata": {
            "target_gross_pair_notional_usdt": 1000.0,
            "target_leg1_notional_usdt": 500.0,
            "target_leg2_notional_usdt": 500.0,
            "hedge_ratio_at_t": 1.0,
        },
    }


def _study(entry: dict[str, object], points: list[dict[str, float]], **kwargs):
    return build_counterfactual_exit_study(
        entry_marker=entry,
        pair=PAIR,
        timeframe="1m",
        chart_points=points,
        **kwargs,
    )


def _result(study, strategy: CounterfactualExitStrategy):
    return next(item for item in study.results if item.exit_strategy == strategy)


def test_replay_entry_study_anchors_to_replay_entry_id() -> None:
    entry = _replay_entry()
    study = _study(entry, [_point(0, -2.0), _point(1, -0.4)])

    assert study.entry_id == entry["entry_id"]
    assert study.entry_marker_type == "replay_entry_candidate"
    assert study.entry_timestamp == BASE_TS
    assert study.entry_side == "BUY_SPREAD"


def test_actual_trade_study_anchors_to_actual_entry_timestamp_and_trade_id() -> None:
    entry = {
        "marker_type": "actual_entry",
        "entry_id": "actual_T1",
        "trade_id": "T1",
        "timestamp": BASE_TS + 30,
        "original_event_timestamp": BASE_TS + 30,
        "side": "BUY_SPREAD",
        "z_score": -2.1,
        "spread": -2.1,
        "metadata": {"target_gross_pair_notional_usdt": 1000.0, "entry_hedge_ratio": 1.0},
    }
    actual_exit = {
        "marker_type": "actual_exit",
        "trade_id": "T1",
        "timestamp": BASE_TS + 120,
        "z_score": -0.2,
        "pnl_usdt": 2.5,
    }

    study = build_counterfactual_exit_study(
        entry_marker=entry,
        pair=PAIR,
        timeframe="1m",
        chart_points=[_point(0, -2.1), _point(1, -0.4), _point(2, -0.2)],
        actual_markers=[actual_exit],
    )

    assert study.entry_id == "actual_T1"
    assert study.entry_marker_type == "actual_entry"
    assert study.entry_timestamp == BASE_TS + 30
    assert study.actual_exit_timestamp == BASE_TS + 120
    assert study.actual_exit_z == -0.2
    assert study.actual_pnl_usdt == 2.5


def test_historical_mean_crossing_cannot_anchor_counterfactual_study() -> None:
    with pytest.raises(ValueError, match="actual_entry or replay_entry_candidate"):
        _study(
            {
                "marker_type": "historical_mean_crossing",
                "entry_id": "crossing",
                "timestamp": BASE_TS,
            },
            [_point(0, 0.0), _point(1, 0.0)],
        )


def test_replay_blocked_signal_cannot_anchor_counterfactual_study() -> None:
    with pytest.raises(ValueError, match="actual_entry or replay_entry_candidate"):
        _study(
            {
                "marker_type": "replay_blocked_signal",
                "entry_id": "blocked",
                "timestamp": BASE_TS,
                "side": "BUY_SPREAD",
            },
            [_point(0, -2.0), _point(1, -0.4)],
        )


def test_not_triggered_policy_returns_not_triggered_status() -> None:
    study = _study(_replay_entry(), [_point(0, -2.0), _point(1, -1.5), _point(2, -1.2)])

    result = _result(study, CounterfactualExitStrategy.EXIT_AT_Z_0_35)

    assert result.status == CounterfactualExitStatus.NOT_TRIGGERED
    assert result.hypothetical_exit_timestamp is None
    assert result.hypothetical_net_pnl_usdt is None
    assert result.note == "Exit condition did not trigger within selected chart window."


def test_exit_at_z_zero_preserves_zero_zscore_candle() -> None:
    study = _study(_replay_entry(), [_point(0, -2.0), _point(1, 0.0)])

    result = _result(study, CounterfactualExitStrategy.EXIT_AT_Z_0_00)

    assert result.status == CounterfactualExitStatus.TRIGGERED
    assert result.hypothetical_exit_timestamp == BASE_TS + 60
    assert result.hypothetical_exit_z == 0.0


def test_forced_close_is_labeled_as_analysis_window_close() -> None:
    study = _study(
        _replay_entry(),
        [_point(0, -2.0), _point(1, -1.5), _point(2, -1.2, price_1=101.0)],
        config=CounterfactualExitConfig(force_close_at_window_end=True),
    )

    result = _result(study, CounterfactualExitStrategy.EXIT_AT_Z_0_35)

    assert result.status == CounterfactualExitStatus.FORCED_CLOSE_AT_WINDOW_END
    assert result.hypothetical_exit_timestamp == BASE_TS + 120
    assert "Forced close at selected chart window end for analysis only" in result.note


def test_buy_spread_pnl_formula_works() -> None:
    study = _study(
        _replay_entry("BUY_SPREAD"),
        [_point(0, -2.0), _point(1, -0.4, price_1=110.0, price_2=90.0)],
    )

    result = _result(study, CounterfactualExitStrategy.EXIT_AT_Z_0_50)

    expected = 500.0 * math.log(110.0 / 100.0) - 500.0 * math.log(90.0 / 100.0)
    assert result.status == CounterfactualExitStatus.TRIGGERED
    assert result.hypothetical_gross_pnl_usdt == pytest.approx(expected)
    assert result.hypothetical_net_pnl_usdt == pytest.approx(expected)


def test_sell_spread_pnl_formula_works() -> None:
    study = _study(
        _replay_entry("SELL_SPREAD"),
        [_point(0, 2.0), _point(1, 0.4, price_1=90.0, price_2=110.0)],
    )

    result = _result(study, CounterfactualExitStrategy.EXIT_AT_Z_0_50)

    expected = -500.0 * math.log(90.0 / 100.0) + 500.0 * math.log(110.0 / 100.0)
    assert result.status == CounterfactualExitStatus.TRIGGERED
    assert result.hypothetical_gross_pnl_usdt == pytest.approx(expected)


def test_equal_notional_vs_hedge_ratio_sized_pnl_keeps_gross_exposure_constant() -> None:
    entry = _replay_entry()
    entry["metadata"] = {
        "target_gross_pair_notional_usdt": 900.0,
        "target_leg1_notional_usdt": 300.0,
        "target_leg2_notional_usdt": 600.0,
        "hedge_ratio_at_t": 2.0,
    }

    study = _study(entry, [_point(0, -2.0), _point(1, -0.4, price_1=110.0, price_2=95.0)])
    result = _result(study, CounterfactualExitStrategy.EXIT_AT_Z_0_50)

    equal_expected = 450.0 * math.log(110.0 / 100.0) - 450.0 * math.log(95.0 / 100.0)
    hedge_expected = 300.0 * math.log(110.0 / 100.0) - 600.0 * math.log(95.0 / 100.0)
    assert result.metadata["gross_pair_notional_usdt"] == 900.0
    assert result.equal_notional_pnl_usdt == pytest.approx(equal_expected)
    assert result.hedge_ratio_sized_pnl_usdt == pytest.approx(hedge_expected)
    assert result.pnl_delta_usdt == pytest.approx(hedge_expected - equal_expected)


def test_mae_mfe_z_and_usdt_fields_are_explicit() -> None:
    study = _study(
        _replay_entry(),
        [
            _point(0, -2.0),
            _point(1, -2.5, price_1=98.0, price_2=102.0),
            _point(2, -0.4, price_1=110.0, price_2=90.0),
        ],
    )

    result = _result(study, CounterfactualExitStrategy.EXIT_AT_Z_0_50)

    assert result.max_adverse_excursion_z is not None
    assert result.max_favorable_excursion_z is not None
    assert result.max_adverse_excursion_usdt is not None
    assert result.max_favorable_excursion_usdt is not None


def test_raw_prices_unavailable_returns_exit_timing_but_null_pnl() -> None:
    study = _study(
        _replay_entry(),
        [
            {"timestamp": BASE_TS, "zscore": -2.0, "spread": -2.0, "spread_mean": 0.0},
            {"timestamp": BASE_TS + 60, "zscore": -0.4, "spread": -0.4, "spread_mean": 0.0},
        ],
    )

    result = _result(study, CounterfactualExitStrategy.EXIT_AT_Z_0_50)

    assert result.status == CounterfactualExitStatus.TRIGGERED
    assert result.hypothetical_exit_timestamp == BASE_TS + 60
    assert result.hypothetical_net_pnl_usdt is None
    assert "Raw leg prices unavailable; PnL estimate skipped." in result.note


def test_advanced_policies_are_unavailable_when_stored_scores_are_missing() -> None:
    study = _study(_replay_entry(), [_point(0, -2.0), _point(1, -0.4)])

    ev_result = _result(study, CounterfactualExitStrategy.EXIT_ON_EV_MANAGER)
    micro_result = _result(study, CounterfactualExitStrategy.EXIT_ON_MICROSTRUCTURE_STRESS)

    assert ev_result.status == CounterfactualExitStatus.UNAVAILABLE
    assert micro_result.status == CounterfactualExitStatus.UNAVAILABLE
    assert "Stored Phase 2.5 score rows unavailable" in ev_result.note


def test_advanced_policy_can_trigger_from_stored_score_row() -> None:
    study = _study(
        _replay_entry(),
        [_point(0, -2.0), _point(1, -1.5), _point(2, -1.2)],
        score_rows=[
            ReplayMLScoreSnapshot(
                pair=PAIR,
                timestamp=BASE_TS + 60,
                score_source=MLScoreSource.STORED_LIVE,
                break_risk=0.8,
            )
        ],
    )

    result = _result(study, CounterfactualExitStrategy.EXIT_ON_REGIME_BREAK)

    assert result.status == CounterfactualExitStatus.TRIGGERED
    assert result.hypothetical_exit_timestamp == BASE_TS + 60
