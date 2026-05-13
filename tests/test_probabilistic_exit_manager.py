from __future__ import annotations

from dataclasses import dataclass
import json

import pytest

from core.config.advanced_ml_config import AdvancedMLConfig
from core.ev.hold_exit_ev import ExitAction
from core.regime.regime_types import RegimeName
from core.trade_management.probabilistic_exit_manager import (
    ProbabilisticExitManager,
    PostTradeShadowReport,
    ShadowDecisionRecord,
    compute_drawdown_risk_score,
    compute_execution_risk_score,
    compute_exit_scores,
    compute_trend_continuation_risk,
)


@dataclass(frozen=True)
class Pair:
    key: str = "AAA|BBB|1m|200"


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
    config.pipeline.enabled = True
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


def test_disabled_advanced_exit_noops_and_does_not_submit_order():
    adapter = FakeExistingBotAdapter()
    config = _config()
    config.pipeline.enabled = False
    manager = ProbabilisticExitManager(adapter, config, shadow_mode=False)
    pair = Pair()

    decision = manager.evaluate_exit(
        pair,
        _features(current_z=5.5, entry_z=2.0, catastrophic_divergence_sigma=1.0),
    )

    assert decision.action == ExitAction.HOLD
    assert decision.reason == "advanced exit disabled by config"
    assert decision.metadata["advanced_enabled"] is False
    assert decision.metadata["pair"] == pair
    assert adapter.submitted == []


def test_soft_exit_decision_metadata_includes_pair_for_runtime_logs():
    adapter = FakeExistingBotAdapter()
    config = _config()
    manager = ProbabilisticExitManager(adapter, config, shadow_mode=True)
    pair = Pair()

    decision = manager.evaluate_exit(
        pair,
        _features(current_z=1.8, entry_z=2.0, catastrophic_divergence_sigma=10.0),
    )

    assert decision.hard_kill_triggered is False
    assert decision.reason == "probabilistic soft exit scoring"
    assert decision.metadata["pair"] == pair


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


def test_post_trade_shadow_report_computes_counterfactual_metrics_after_close():
    adapter = FakeExistingBotAdapter()
    manager = ProbabilisticExitManager(adapter, _config(), shadow_mode=True)
    pair = Pair()

    manager.evaluate_exit(
        pair,
        _features(
            trade_id="trade-1",
            current_z=5.5,
            entry_z=2.0,
            catastrophic_divergence_sigma=1.0,
        ),
        old_action="hold",
        old_reason="legacy hold",
    )
    manager.shadow_records[0] = ShadowDecisionRecord(
        **{
            **manager.shadow_records[0].__dict__,
            "timestamp": 100.0,
        }
    )

    report = manager.generate_post_trade_shadow_report(
        pair,
        trade_id="trade-1",
        actual_exit_timestamp=160.0,
        actual_pnl_usdt=-12.0,
    )

    assert report.would_have_exited_earlier_count == 1
    assert report.would_have_exited_later_count == 0
    assert report.avoided_loss_estimate_usdt == pytest.approx(12.0)
    assert report.missed_profit_estimate_usdt == pytest.approx(0.0)
    assert report.net_policy_delta_usdt == pytest.approx(12.0)
    assert report.exit_time_distribution_shift_seconds == pytest.approx(-60.0)
    json.dumps(report.to_dict(), default=str)


def test_shadow_circuit_breakers_use_configured_eval_window():
    adapter = FakeExistingBotAdapter()
    config = _config()
    config.pipeline.shadow_eval_window = 2
    config.pipeline.max_shadow_disagreement_rate = 0.25
    config.pipeline.min_shadow_policy_delta_usdt = 0.0
    manager = ProbabilisticExitManager(adapter, config, shadow_mode=True)
    pair = Pair()
    manager.post_trade_shadow_reports.extend(
        [
            PostTradeShadowReport(pair, "old", 1.0, 0.0, 0, 0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0),
            PostTradeShadowReport(pair, "recent-1", 0.0, 1.0, 1, 0, 0.0, 5.0, -5.0, 1.0, 0.0, -10.0),
            PostTradeShadowReport(pair, "recent-2", 0.0, 1.0, 1, 0, 0.0, 5.0, -5.0, 1.0, 0.0, -20.0),
        ]
    )

    status = manager.shadow_circuit_breaker_status()

    assert status["window"] == 2
    assert status["evaluated_reports"] == 2
    assert status["mean_disagreement_rate"] == pytest.approx(1.0)
    assert status["mean_net_policy_delta_usdt"] == pytest.approx(-5.0)
    assert status["disable_advanced_live_exits"] is True
    assert status["keep_shadow_mode_enabled"] is True


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
