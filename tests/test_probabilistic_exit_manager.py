from __future__ import annotations

from dataclasses import dataclass

import pytest

from core.config.advanced_ml_config import AdvancedMLConfig
from core.ev.hold_exit_ev import ExitAction
from core.regime.regime_types import RegimeName
from core.trade_management.probabilistic_exit_manager import (
    ProbabilisticExitManager,
    ShadowDecisionRecord,
    compute_drawdown_risk_score,
    compute_execution_risk_score,
    compute_exit_scores,
    compute_trend_continuation_risk,
)


@dataclass(frozen=True)
class Pair:
    key: str = "AAA|BBB|1m|2880"


class FakeExistingBotAdapter:
    def __init__(self) -> None:
        self.submitted: list[dict] = []

    def get_pair_state(self, pair):
        return "stable"

    def get_orderbook_snapshot(self, symbol: str):
        return None

    def get_current_position(self, pair):
        return {"size": 1.0}

    def get_trade_lifecycle_event(self):
        return None

    def read_existing_trade_state(self):
        return {"action": "hold", "reason": "legacy hold"}

    def submit_exit_order(self, pair, exit_percentage: float, order_style: str, reason: str):
        payload = {
            "pair": pair,
            "exit_percentage": exit_percentage,
            "order_style": order_style,
            "reason": reason,
        }
        self.submitted.append(payload)
        return payload


def _config() -> AdvancedMLConfig:
    config = AdvancedMLConfig()
    config.pipeline.shadow_mode = True
    config.microstructure.max_allowed_slippage_bps = 10.0
    config.microstructure.max_book_age_ms = 1_000.0
    config.microstructure.max_urgency_boost = 0.75
    config.microstructure.max_exit_urgency_multiplier = 1.75
    config.regime.max_spread_widening_bps = 10.0
    config.regime.min_top_depth_usdt = 1_000.0
    config.exit.max_drawdown_usdt = 10.0
    config.exit.max_hold_seconds = 1_000.0
    config.exit.default_half_life_seconds = 100.0
    config.exit.mean_reversion_hold_discount = 0.0
    config.ev.use_historical_spread_edge = False
    config.ev.warn_when_using_default_spread_edge = False
    return config


def _features(**overrides):
    data = {
        "position_notional_usdt": 10.0,
        "exit_notional_usdt": 10.0,
        "entry_z": 2.0,
        "current_z": 1.8,
        "previous_z": 1.7,
        "time_in_trade_seconds": 100.0,
        "estimated_half_life_seconds": 100.0,
        "z_history_values": [2.0, 1.9, 1.8],
        "bayesian_posterior": 0.5,
        "regime": RegimeName.MEAN_REVERTING,
        "regime_confidence": 0.7,
        "regime_mean_reversion_confidence": 0.7,
        "z_velocity_toward_mean_score": 0.2,
        "break_risk": 0.1,
        "adverse_z_velocity_score": 0.1,
        "liquidity_score": 0.9,
        "liquidity_risk_score": 0.1,
        "trend_score": 0.2,
        "normalized_spread_vol_spike": 0.3,
        "expected_taker_fee_bps": 2.0,
        "recent_maker_fill_probability": 0.8,
        "desired_exit_notional_usdt": 50.0,
        "order_capacity_usdt": 100.0,
        "api_latency_ms": 100.0,
        "recent_order_failures": 1.0,
        "current_drawdown_usdt": 2.0,
        "slippage_estimate_bps": 1.0,
        "spread_bps": 1.0,
        "update_age_ms": 0.0,
        "bid_depth": 500.0,
        "ask_depth": 500.0,
    }
    data.update(overrides)
    return data


def test_manager_requires_existing_bot_adapter_protocol_only():
    with pytest.raises(TypeError, match="ExistingBotAdapter"):
        ProbabilisticExitManager(object(), _config())

    manager = ProbabilisticExitManager(FakeExistingBotAdapter(), _config())
    assert isinstance(manager.adapter, FakeExistingBotAdapter)


def test_trend_continuation_risk_formula_is_exact():
    score = compute_trend_continuation_risk(
        {
            "trend_score": 0.6,
            "adverse_z_velocity_score": 0.5,
            "normalized_spread_vol_spike": 0.25,
        }
    )

    assert score == pytest.approx(0.50 * 0.6 + 0.30 * 0.5 + 0.20 * 0.25)


def test_execution_risk_score_formula_is_exact():
    config = _config()
    score = compute_execution_risk_score(
        {
            "expected_taker_fee_bps": 5.0,
            "recent_maker_fill_probability": 0.40,
            "desired_exit_notional_usdt": 50.0,
            "order_capacity_usdt": 100.0,
            "api_latency_ms": 500.0,
            "recent_order_failures": 2.0,
        },
        config,
    )

    assert score == pytest.approx(
        0.30 * 0.50
        + 0.25 * 0.60
        + 0.20 * 0.50
        + 0.15 * 0.50
        + 0.10 * 0.20
    )


def test_drawdown_risk_score_formula_and_missing_default():
    config = _config()

    assert compute_drawdown_risk_score({}, config) == 0.0
    assert compute_drawdown_risk_score({"current_drawdown_usdt": 2.5}, config) == pytest.approx(0.25)


def test_exit_scores_use_pre_microstructure_then_total_multiplier():
    config = _config()
    scores = compute_exit_scores(
        _features(
            trend_score=0.6,
            adverse_z_velocity_score=0.5,
            normalized_spread_vol_spike=0.25,
            current_drawdown_usdt=2.5,
        ),
        config=config,
        microstructure_multiplier=1.5,
    )

    assert scores.trend_continuation_risk == pytest.approx(0.50)
    assert scores.drawdown_risk_score == pytest.approx(0.25)
    assert scores.total_exit_score == pytest.approx(
        min(scores.pre_microstructure_exit_score * 1.5, 1.0)
    )


def test_hard_kill_overrides_soft_scoring_and_executes_in_live_mode():
    adapter = FakeExistingBotAdapter()
    config = _config()
    manager = ProbabilisticExitManager(adapter, config, shadow_mode=False)

    decision = manager.evaluate_exit(
        Pair(),
        _features(
            current_z=5.5,
            entry_z=2.0,
            catastrophic_divergence_sigma=1.0,
            take_profit_score=0.0,
            break_risk=0.0,
        ),
    )

    assert decision.hard_kill_triggered is True
    assert decision.action == ExitAction.FULL_EXIT
    assert decision.exit_percentage == 1.0
    assert decision.reason == "catastrophic divergence"
    assert len(adapter.submitted) == 1
    assert adapter.submitted[0]["reason"] == "catastrophic divergence"


def test_no_execution_in_shadow_mode_records_shadow_decision():
    adapter = FakeExistingBotAdapter()
    manager = ProbabilisticExitManager(adapter, _config(), shadow_mode=True)

    decision = manager.evaluate_exit(
        Pair(),
        _features(current_z=5.5, entry_z=2.0, catastrophic_divergence_sigma=1.0),
        old_action="hold",
        old_reason="legacy hold",
    )

    assert decision.hard_kill_triggered is True
    assert adapter.submitted == []
    assert len(manager.shadow_records) == 1
    record = manager.shadow_records[0]
    assert record.old_action == "hold"
    assert record.new_action == "full_exit"
    assert record.old_reason == "legacy hold"
    assert record.new_reason == "catastrophic divergence"


def test_shadow_decision_record_has_no_post_trade_only_fields():
    field_names = set(ShadowDecisionRecord.__dataclass_fields__)

    assert "would_have_exited_earlier" not in field_names
    assert "would_have_exited_later" not in field_names
    assert "would_have_exited_earlier_count" not in field_names
    assert "would_have_exited_later_count" not in field_names


def test_soft_partial_exit_executes_only_when_live():
    adapter = FakeExistingBotAdapter()
    manager = ProbabilisticExitManager(adapter, _config(), shadow_mode=False)

    decision = manager.evaluate_exit(
        Pair(),
        _features(
            take_profit_score=1.0,
            break_risk=1.0,
            liquidity_risk_score=1.0,
            current_drawdown_usdt=8.0,
            trend_score=1.0,
            adverse_z_velocity_score=1.0,
            normalized_spread_vol_spike=1.0,
            update_age_ms=0.0,
            liquidity_score=1.0,
        ),
    )

    assert decision.hard_kill_triggered is False
    assert decision.action in (ExitAction.PARTIAL_EXIT, ExitAction.FULL_EXIT)
    assert adapter.submitted
