"""Probabilistic exit orchestration through the existing bot adapter boundary."""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from typing import Any

from core.adapters.bot_adapter_types import ExistingBotAdapter
from core.config.advanced_ml_config import AdvancedMLConfig
from core.ev.hold_exit_ev import ExitAction, ExpectedValueDecision, HoldExitEVCalculator
from core.microstructure.microstructure_analyzer import (
    MicrostructureAnalyzer,
    MicrostructureExitResult,
)
from core.regime.regime_types import RegimeName


@dataclass(frozen=True)
class HardKillResult:
    triggered: bool
    action: ExitAction
    exit_percentage: float
    reason: str
    severity: float


@dataclass(frozen=True)
class ExitRiskWeights:
    take_profit: float = 0.16
    stall: float = 0.14
    regime_break: float = 0.22
    liquidity: float = 0.14
    execution: float = 0.10
    drawdown: float = 0.10
    trend: float = 0.09
    time_risk: float = 0.05

    def validate(self) -> None:
        total = (
            self.take_profit
            + self.stall
            + self.regime_break
            + self.liquidity
            + self.execution
            + self.drawdown
            + self.trend
            + self.time_risk
        )
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Exit risk weights must sum to 1.0, got {total}")


@dataclass(frozen=True)
class ExitScores:
    take_profit_score: float
    stall_score: float
    regime_break_score: float
    liquidity_risk_score: float
    execution_risk_score: float
    mean_reversion_score: float
    trend_continuation_risk: float
    drawdown_risk_score: float
    time_risk_score: float
    trailing_stop_pressure: float
    risk_pressure_score: float
    pre_microstructure_exit_score: float
    total_exit_score: float


@dataclass(frozen=True)
class ExitDecision:
    action: ExitAction
    exit_percentage: float
    reason: str
    scores: ExitScores
    ev: ExpectedValueDecision
    microstructure: MicrostructureExitResult
    hard_kill_triggered: bool
    blocked_by_net_profit_guard: bool
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ShadowDecisionRecord:
    pair: Any
    timestamp: float
    old_action: str
    new_action: str
    old_reason: str
    new_reason: str
    exit_score: float
    expected_hold_value_usdt: float
    microstructure_stress: float
    trade_features: dict[str, Any]


@dataclass(frozen=True)
class PostTradeShadowReport:
    pair: Any
    trade_id: str
    agreement_rate: float
    disagreement_rate: float
    would_have_exited_earlier_count: int
    would_have_exited_later_count: int
    avoided_loss_estimate_usdt: float
    missed_profit_estimate_usdt: float
    net_policy_delta_usdt: float
    false_exit_rate_estimate: float
    late_exit_rate_estimate: float
    exit_time_distribution_shift_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProbabilisticExitManager:
    def __init__(
        self,
        adapter: ExistingBotAdapter,
        config: AdvancedMLConfig | None = None,
        *,
        shadow_mode: bool | None = None,
        risk_weights: ExitRiskWeights | None = None,
        ev_calculator: HoldExitEVCalculator | None = None,
        microstructure_analyzer: MicrostructureAnalyzer | None = None,
    ) -> None:
        if not isinstance(adapter, ExistingBotAdapter):
            raise TypeError("ProbabilisticExitManager requires an ExistingBotAdapter.")
        self.adapter = adapter
        self.config = config or AdvancedMLConfig()
        self.shadow_mode = self.config.pipeline.shadow_mode if shadow_mode is None else bool(shadow_mode)
        self.risk_weights = risk_weights or ExitRiskWeights()
        self.risk_weights.validate()
        self.ev_calculator = ev_calculator or HoldExitEVCalculator(self.config)
        self.microstructure_analyzer = microstructure_analyzer or MicrostructureAnalyzer(self.config)
        self.shadow_records: list[ShadowDecisionRecord] = []
        self.post_trade_shadow_reports: list[PostTradeShadowReport] = []

    def evaluate_exit(
        self,
        pair: Any,
        trade_features: dict[str, Any],
        *,
        old_action: str = "hold",
        old_reason: str = "",
    ) -> ExitDecision:
        features = dict(trade_features)
        if not self.shadow_mode and not self.config.pipeline.enabled:
            return self._disabled_decision(pair, features)
        hard_kill = self.check_hard_kill(pair, features)
        if hard_kill.triggered:
            decision = self._hard_kill_decision(pair, features, hard_kill)
            self._execute_or_shadow(pair, decision, features, old_action, old_reason)
            return decision

        scores_without_micro = compute_exit_scores(
            features,
            config=self.config,
            weights=self.risk_weights,
            microstructure_multiplier=1.0,
        )
        ev = self.ev_calculator.decide(
            position_notional_usdt=_float_feature(features, "position_notional_usdt", 0.0),
            exit_notional_usdt=_float_feature(
                features,
                "exit_notional_usdt",
                _float_feature(features, "position_notional_usdt", 0.0),
            ),
            abs_current_z=abs(_float_feature(features, "current_z", 0.0)),
            time_in_trade_seconds=_float_feature(features, "time_in_trade_seconds", 0.0),
            half_life_seconds=max(
                _float_feature(
                    features,
                    "estimated_half_life_seconds",
                    self.config.exit.default_half_life_seconds,
                ),
                1.0,
            ),
            z_history_values=features.get("z_history_values", []),
            bayesian_posterior=_float_feature(features, "bayesian_posterior", 0.5),
            regime_mean_reversion_confidence=_float_feature(
                features,
                "regime_mean_reversion_confidence",
                _float_feature(features, "mean_reversion_score", 0.0),
            ),
            z_velocity_toward_mean_score=_float_feature(features, "z_velocity_toward_mean_score", 0.0),
            break_risk=_float_feature(features, "break_risk", 0.0),
            adverse_z_velocity_score=_float_feature(features, "adverse_z_velocity_score", 0.0),
            liquidity_score=_float_feature(features, "liquidity_score", 1.0),
            liquidity_risk_score=scores_without_micro.liquidity_risk_score,
            trend_continuation_risk=scores_without_micro.trend_continuation_risk,
            slippage_estimate_bps=_float_feature(features, "slippage_estimate_bps", 0.0),
            pre_microstructure_exit_score=scores_without_micro.pre_microstructure_exit_score,
            spread_volatility_spike_score=_float_feature(
                features,
                "normalized_spread_vol_spike",
                _float_feature(features, "spread_volatility_spike_score", 0.0),
            ),
            low_break_risk_score=clamp01(1.0 - _float_feature(features, "break_risk", 0.0)),
            historical_sigma_pnl_samples=features.get("historical_sigma_pnl_samples"),
        )
        microstructure = self.microstructure_analyzer.analyze_exit(
            update_age_ms=_float_feature(
                features,
                "update_age_ms",
                _float_feature(features, "book_freshness_ms", 0.0),
            ),
            bid_depth=_float_feature(features, "bid_depth", 0.0),
            ask_depth=_float_feature(features, "ask_depth", 0.0),
            estimated_slippage_bps=_float_feature(features, "slippage_estimate_bps", 0.0),
            spread_bps=_float_feature(features, "spread_bps", 0.0),
            adverse_z_velocity_score=_float_feature(features, "adverse_z_velocity_score", 0.0),
            regime=features.get("regime", RegimeName.UNKNOWN),
            hard_kill_triggered=False,
        )
        scores = compute_exit_scores(
            features,
            config=self.config,
            weights=self.risk_weights,
            microstructure_multiplier=microstructure.exit_urgency_multiplier,
        )
        action = _action_from_total_score(scores.total_exit_score)
        exit_percentage = _dynamic_exit_percentage(
            action=action,
            scores=scores,
            ev=ev,
            microstructure=microstructure,
            break_risk=_float_feature(features, "break_risk", 0.0),
            config=self.config,
            hard_kill_triggered=False,
        )
        blocked_by_net_profit_guard = _blocked_by_net_profit_guard(action, features)
        if blocked_by_net_profit_guard:
            action = ExitAction.HOLD
            exit_percentage = 0.0

        decision = ExitDecision(
            action=action,
            exit_percentage=exit_percentage,
            reason="probabilistic soft exit scoring",
            scores=scores,
            ev=ev,
            microstructure=microstructure,
            hard_kill_triggered=False,
            blocked_by_net_profit_guard=blocked_by_net_profit_guard,
            metadata={
                "pair": pair,
                "shadow_mode": self.shadow_mode,
                "ev_recommendation": ev.recommendation.value,
                "recommended_order_style": microstructure.recommended_order_style,
            },
        )
        self._execute_or_shadow(pair, decision, features, old_action, old_reason)
        return decision

    def generate_post_trade_shadow_report(
        self,
        pair: Any,
        *,
        trade_id: str,
        actual_exit_timestamp: float,
        actual_pnl_usdt: float,
    ) -> PostTradeShadowReport:
        records = [
            record
            for record in self.shadow_records
            if _pair_key(record.pair) == _pair_key(pair)
            and str(record.trade_features.get("trade_id", trade_id)) == str(trade_id)
        ]
        total = max(len(records), 1)
        agreements = sum(1 for record in records if record.old_action == record.new_action)
        would_have_exited_earlier = [
            record
            for record in records
            if _is_exit_action(record.new_action)
            and not _is_exit_action(record.old_action)
            and record.timestamp <= float(actual_exit_timestamp)
        ]
        would_have_exited_later = [
            record
            for record in records
            if _is_exit_action(record.old_action)
            and not _is_exit_action(record.new_action)
        ]
        earlier_count = len(would_have_exited_earlier)
        later_count = len(would_have_exited_later)
        pnl = float(actual_pnl_usdt)
        avoided_loss_estimate_usdt = max(-pnl, 0.0) * (earlier_count / total)
        missed_profit_estimate_usdt = max(pnl, 0.0) * (earlier_count / total)
        net_policy_delta_usdt = avoided_loss_estimate_usdt - missed_profit_estimate_usdt
        signed_shifts = [
            float(record.timestamp) - float(actual_exit_timestamp)
            for record in would_have_exited_earlier
        ] + [
            float(actual_exit_timestamp) - float(record.timestamp)
            for record in would_have_exited_later
        ]
        exit_time_distribution_shift_seconds = (
            sum(signed_shifts) / len(signed_shifts)
            if signed_shifts
            else 0.0
        )
        report = PostTradeShadowReport(
            pair=pair,
            trade_id=str(trade_id),
            agreement_rate=agreements / total,
            disagreement_rate=(total - agreements) / total,
            would_have_exited_earlier_count=earlier_count,
            would_have_exited_later_count=later_count,
            avoided_loss_estimate_usdt=avoided_loss_estimate_usdt,
            missed_profit_estimate_usdt=missed_profit_estimate_usdt,
            net_policy_delta_usdt=net_policy_delta_usdt,
            false_exit_rate_estimate=(
                (earlier_count / total)
                if pnl > 0.0
                else 0.0
            ),
            late_exit_rate_estimate=later_count / total,
            exit_time_distribution_shift_seconds=exit_time_distribution_shift_seconds,
        )
        self.post_trade_shadow_reports.append(report)
        return report

    def shadow_circuit_breaker_status(self) -> dict[str, Any]:
        window = max(int(self.config.pipeline.shadow_eval_window), 1)
        recent = self.post_trade_shadow_reports[-window:]
        if not recent:
            return {
                "evaluated_reports": 0,
                "window": window,
                "disable_advanced_live_exits": False,
                "keep_shadow_mode_enabled": True,
                "mean_disagreement_rate": 0.0,
                "mean_net_policy_delta_usdt": 0.0,
            }
        mean_disagreement = sum(report.disagreement_rate for report in recent) / len(recent)
        mean_delta = sum(report.net_policy_delta_usdt for report in recent) / len(recent)
        return {
            "evaluated_reports": len(recent),
            "window": window,
            "disable_advanced_live_exits": (
                mean_disagreement > self.config.pipeline.max_shadow_disagreement_rate
            ),
            "keep_shadow_mode_enabled": (
                mean_delta < self.config.pipeline.min_shadow_policy_delta_usdt
            ),
            "mean_disagreement_rate": mean_disagreement,
            "mean_net_policy_delta_usdt": mean_delta,
        }

    def check_hard_kill(self, pair: Any, features: dict[str, Any]) -> HardKillResult:
        del pair
        time_in_trade_seconds = _float_feature(features, "time_in_trade_seconds", 0.0)
        if time_in_trade_seconds > self.config.exit.max_hold_seconds:
            return HardKillResult(True, ExitAction.FULL_EXIT, 1.0, "max hold time exceeded", 0.80)

        abs_current_z = abs(_float_feature(features, "current_z", 0.0))
        abs_entry_z = abs(_float_feature(features, "entry_z", 0.0))
        catastrophic_divergence_sigma = _float_feature(features, "catastrophic_divergence_sigma", 2.0)
        if abs_current_z > abs_entry_z + catastrophic_divergence_sigma:
            return HardKillResult(True, ExitAction.FULL_EXIT, 1.0, "catastrophic divergence", 1.0)

        regime = _optional_regime(features.get("regime"))
        regime_confidence = _float_feature(features, "regime_confidence", 0.0)
        if (
            regime == RegimeName.STRUCTURAL_BREAK
            and regime_confidence >= self.config.regime.structural_break_confidence_threshold
        ):
            return HardKillResult(True, ExitAction.FULL_EXIT, 1.0, "confirmed structural break", 1.0)

        freshness_ms = _float_feature(
            features,
            "freshness_ms",
            _float_feature(features, "book_freshness_ms", _float_feature(features, "update_age_ms", 0.0)),
        )
        if freshness_ms > self.config.microstructure.max_book_age_ms:
            return HardKillResult(True, ExitAction.FULL_EXIT, 1.0, "stale orderbook", 0.75)

        min_exit_liquidity_score = _float_feature(features, "min_exit_liquidity_score", 0.10)
        if _float_feature(features, "liquidity_score", 1.0) < min_exit_liquidity_score:
            return HardKillResult(True, ExitAction.FULL_EXIT, 1.0, "liquidity collapse", 0.90)

        if bool(features.get("position_desync", False)):
            return HardKillResult(True, ExitAction.FULL_EXIT, 1.0, "position desync", 1.0)

        current_drawdown_usdt = features.get("current_drawdown_usdt")
        if current_drawdown_usdt is not None and float(current_drawdown_usdt) > self.config.exit.max_drawdown_usdt:
            return HardKillResult(True, ExitAction.FULL_EXIT, 1.0, "risk limit breach", 0.95)

        return HardKillResult(False, ExitAction.HOLD, 0.0, "", 0.0)

    def _hard_kill_decision(
        self,
        pair: Any,
        features: dict[str, Any],
        hard_kill: HardKillResult,
    ) -> ExitDecision:
        microstructure = _placeholder_microstructure(features, hard_kill)
        ev = _placeholder_ev(hard_kill)
        scores = ExitScores(
            take_profit_score=0.0,
            stall_score=0.0,
            regime_break_score=0.0,
            liquidity_risk_score=0.0,
            execution_risk_score=0.0,
            mean_reversion_score=0.0,
            trend_continuation_risk=0.0,
            drawdown_risk_score=0.0,
            time_risk_score=0.0,
            trailing_stop_pressure=0.0,
            risk_pressure_score=hard_kill.severity,
            pre_microstructure_exit_score=hard_kill.severity,
            total_exit_score=1.0,
        )
        return ExitDecision(
            action=hard_kill.action,
            exit_percentage=hard_kill.exit_percentage,
            reason=hard_kill.reason,
            scores=scores,
            ev=ev,
            microstructure=microstructure,
            hard_kill_triggered=True,
            blocked_by_net_profit_guard=False,
            metadata={
                "pair": pair,
                "shadow_mode": self.shadow_mode,
                "hard_kill_severity": hard_kill.severity,
            },
        )

    def _disabled_decision(self, pair: Any, features: dict[str, Any]) -> ExitDecision:
        hard_kill = HardKillResult(False, ExitAction.HOLD, 0.0, "advanced exit disabled", 0.0)
        return ExitDecision(
            action=ExitAction.HOLD,
            exit_percentage=0.0,
            reason="advanced exit disabled by config",
            scores=ExitScores(
                take_profit_score=0.0,
                stall_score=0.0,
                regime_break_score=0.0,
                liquidity_risk_score=0.0,
                execution_risk_score=0.0,
                mean_reversion_score=0.0,
                trend_continuation_risk=0.0,
                drawdown_risk_score=0.0,
                time_risk_score=0.0,
                trailing_stop_pressure=0.0,
                risk_pressure_score=0.0,
                pre_microstructure_exit_score=0.0,
                total_exit_score=0.0,
            ),
            ev=_placeholder_ev(hard_kill),
            microstructure=_placeholder_microstructure(features, hard_kill),
            hard_kill_triggered=False,
            blocked_by_net_profit_guard=False,
            metadata={
                "pair": pair,
                "shadow_mode": self.shadow_mode,
                "advanced_enabled": False,
            },
        )

    def _execute_or_shadow(
        self,
        pair: Any,
        decision: ExitDecision,
        trade_features: dict[str, Any],
        old_action: str,
        old_reason: str,
    ) -> None:
        if self.shadow_mode:
            self.shadow_records.append(
                ShadowDecisionRecord(
                    pair=pair,
                    timestamp=float(time.time()),
                    old_action=str(old_action),
                    new_action=decision.action.value,
                    old_reason=str(old_reason),
                    new_reason=decision.reason,
                    exit_score=decision.scores.total_exit_score,
                    expected_hold_value_usdt=decision.ev.expected_hold_value_usdt,
                    microstructure_stress=decision.microstructure.book_stress_score,
                    trade_features=dict(trade_features),
                )
            )
            return
        if decision.action in (ExitAction.PARTIAL_EXIT, ExitAction.FULL_EXIT):
            self.adapter.submit_exit_order(
                pair,
                decision.exit_percentage,
                decision.microstructure.recommended_order_style,
                decision.reason,
            )


def compute_exit_scores(
    features: dict[str, Any],
    *,
    config: AdvancedMLConfig,
    weights: ExitRiskWeights | None = None,
    microstructure_multiplier: float = 1.0,
) -> ExitScores:
    w = weights or ExitRiskWeights()
    w.validate()
    take_profit_score = clamp01(_float_feature(features, "take_profit_score", 0.0))
    stall_score = _stall_score(features, config)
    regime_break_score = clamp01(_float_feature(features, "regime_break_score", _float_feature(features, "break_risk", 0.0)))
    liquidity_risk_score = clamp01(
        _float_feature(
            features,
            "liquidity_risk_score",
            1.0 - _float_feature(features, "liquidity_score", 1.0),
        )
    )
    execution_risk_score = compute_execution_risk_score(features, config)
    mean_reversion_score = clamp01(_float_feature(features, "mean_reversion_score", 0.0))
    trend_continuation_risk = compute_trend_continuation_risk(features)
    drawdown_risk_score = compute_drawdown_risk_score(features, config)
    time_risk_score = clamp01(
        _float_feature(features, "time_in_trade_seconds", 0.0)
        / max(config.exit.max_hold_seconds, 1.0)
    )
    trailing_stop_pressure = clamp01(_float_feature(features, "trailing_stop_pressure", 0.0))
    risk_pressure_score = clamp01(
        w.take_profit * take_profit_score
        + w.stall * stall_score
        + w.regime_break * regime_break_score
        + w.liquidity * liquidity_risk_score
        + w.execution * execution_risk_score
        + w.drawdown * drawdown_risk_score
        + w.trend * trend_continuation_risk
        + w.time_risk * time_risk_score
    )
    hold_discount = 1.0 - config.exit.mean_reversion_hold_discount * mean_reversion_score
    pre_microstructure_exit_score = clamp01(risk_pressure_score * hold_discount)
    total_exit_score = clamp01(pre_microstructure_exit_score * float(microstructure_multiplier))
    return ExitScores(
        take_profit_score=take_profit_score,
        stall_score=stall_score,
        regime_break_score=regime_break_score,
        liquidity_risk_score=liquidity_risk_score,
        execution_risk_score=execution_risk_score,
        mean_reversion_score=mean_reversion_score,
        trend_continuation_risk=trend_continuation_risk,
        drawdown_risk_score=drawdown_risk_score,
        time_risk_score=time_risk_score,
        trailing_stop_pressure=trailing_stop_pressure,
        risk_pressure_score=risk_pressure_score,
        pre_microstructure_exit_score=pre_microstructure_exit_score,
        total_exit_score=total_exit_score,
    )


def compute_trend_continuation_risk(features: dict[str, Any]) -> float:
    return clamp01(
        0.50 * _float_feature(features, "trend_score", 0.0)
        + 0.30 * _float_feature(features, "adverse_z_velocity_score", 0.0)
        + 0.20 * _float_feature(
            features,
            "normalized_spread_vol_spike",
            _float_feature(features, "spread_volatility_spike_score", 0.0),
        )
    )


def compute_execution_risk_score(features: dict[str, Any], config: AdvancedMLConfig) -> float:
    taker_cost_score = clamp01(
        _float_feature(features, "expected_taker_fee_bps", 0.0)
        / max(config.microstructure.max_allowed_slippage_bps, 1e-9)
    )
    low_maker_fill_score = 1.0 - clamp01(_float_feature(features, "recent_maker_fill_probability", 1.0))
    capacity_pressure_score = clamp01(
        _float_feature(features, "desired_exit_notional_usdt", 0.0)
        / max(_float_feature(features, "order_capacity_usdt", 1.0), 1e-9)
    )
    api_health_score = clamp01(
        _float_feature(features, "api_latency_ms", 0.0)
        / max(config.microstructure.max_book_age_ms, 1e-9)
    )
    execution_failure_window = max(float(getattr(config, "execution_failure_window", 10)), 1.0)
    recent_order_failure_score = clamp01(
        _float_feature(features, "recent_order_failures", 0.0)
        / execution_failure_window
    )
    return clamp01(
        0.30 * taker_cost_score
        + 0.25 * low_maker_fill_score
        + 0.20 * capacity_pressure_score
        + 0.15 * api_health_score
        + 0.10 * recent_order_failure_score
    )


def compute_drawdown_risk_score(features: dict[str, Any], config: AdvancedMLConfig) -> float:
    if features.get("current_drawdown_usdt") is None:
        return 0.0
    return clamp01(
        float(features["current_drawdown_usdt"])
        / max(config.exit.max_drawdown_usdt, 1e-9)
    )


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def clamp(value: float, low: float, high: float) -> float:
    return max(float(low), min(float(high), float(value)))


def _stall_score(features: dict[str, Any], config: AdvancedMLConfig) -> float:
    abs_entry_z = abs(_float_feature(features, "entry_z", 0.0))
    abs_current_z = abs(_float_feature(features, "current_z", 0.0))
    abs_previous_z = abs(_float_feature(features, "previous_z", abs_current_z))
    time_in_trade_seconds = _float_feature(features, "time_in_trade_seconds", 0.0)
    half_life_seconds = max(
        _float_feature(
            features,
            "estimated_half_life_seconds",
            config.exit.default_half_life_seconds,
        ),
        1.0,
    )
    expected_progress_fraction = 1.0 - math.exp(-time_in_trade_seconds / half_life_seconds)
    expected_progress_sigma = max(
        abs_entry_z * expected_progress_fraction,
        config.exit.min_expected_progress_sigma,
    )
    actual_progress_sigma = abs_entry_z - abs_current_z
    stall_ratio = 1.0 - clamp01(actual_progress_sigma / expected_progress_sigma)
    abs_z_increasing_or_flat = abs_current_z >= abs_previous_z
    velocity_bad = 1.0 if abs_z_increasing_or_flat else 0.0
    time_pressure = clamp01(
        time_in_trade_seconds / max(config.exit.max_hold_seconds, 1.0)
    )
    abs_z_still_high = clamp01(
        abs_current_z / max(config.exit.z_still_high_threshold, 1e-9)
    )
    return clamp01(
        0.45 * stall_ratio
        + 0.25 * velocity_bad
        + 0.20 * time_pressure
        + 0.10 * abs_z_still_high
    )


def _action_from_total_score(score: float) -> ExitAction:
    if score < 0.30:
        return ExitAction.HOLD
    if score < 0.55:
        return ExitAction.TIGHTEN_STOP
    if score < 0.75:
        return ExitAction.PARTIAL_EXIT
    return ExitAction.FULL_EXIT


def _dynamic_exit_percentage(
    *,
    action: ExitAction,
    scores: ExitScores,
    ev: ExpectedValueDecision,
    microstructure: MicrostructureExitResult,
    break_risk: float,
    config: AdvancedMLConfig,
    hard_kill_triggered: bool,
) -> float:
    if action == ExitAction.HOLD:
        return 0.0
    if hard_kill_triggered or action == ExitAction.FULL_EXIT:
        return 1.0
    if action == ExitAction.TIGHTEN_STOP:
        return 0.0
    positive_ev_score = clamp01(
        max(ev.expected_hold_value_usdt, 0.0)
        / max(config.ev.strong_positive_ev_usdt, 1e-9)
    )
    liquidity_stress_score = microstructure.book_stress_score
    risk_score = clamp01(
        0.35 * scores.risk_pressure_score
        + 0.20 * break_risk
        + 0.20 * liquidity_stress_score
        + 0.15 * scores.execution_risk_score
        + 0.10 * scores.drawdown_risk_score
    )
    return clamp(
        config.exit.base_partial_exit
        + 0.40 * risk_score
        - 0.20 * positive_ev_score
        + 0.20 * liquidity_stress_score,
        config.exit.min_partial_exit,
        config.exit.max_partial_exit,
    )


def _blocked_by_net_profit_guard(action: ExitAction, features: dict[str, Any]) -> bool:
    if not bool(features.get("net_profit_guard_enabled", False)):
        return False
    if action not in (ExitAction.TIGHTEN_STOP, ExitAction.PARTIAL_EXIT):
        return False
    return _float_feature(features, "unrealized_pnl_usdt", 0.0) < 0.0


def _placeholder_microstructure(features: dict[str, Any], hard_kill: HardKillResult) -> MicrostructureExitResult:
    return MicrostructureExitResult(
        liquidity_fresh=False,
        book_stress_score=hard_kill.severity,
        slippage_risk_score=0.0,
        depth_imbalance_score=0.0,
        exit_urgency_multiplier=1.0,
        recommended_order_style="taker",
        reasons=[hard_kill.reason],
        metrics={
            "update_age_ms": _float_feature(features, "update_age_ms", 0.0),
            "hard_kill_severity": hard_kill.severity,
        },
    )


def _placeholder_ev(hard_kill: HardKillResult) -> ExpectedValueDecision:
    return ExpectedValueDecision(
        expected_hold_value_usdt=0.0,
        expected_hold_value_bps=0.0,
        probability_of_reversion=0.0,
        probability_of_adverse_move=1.0,
        probability_of_neutral=0.0,
        expected_gain_usdt=0.0,
        expected_loss_usdt=0.0,
        expected_fees_usdt=0.0,
        expected_slippage_usdt=0.0,
        time_risk_penalty_usdt=0.0,
        recommendation=hard_kill.action,
        reasons=[hard_kill.reason],
        metrics={"hard_kill_severity": hard_kill.severity},
    )


def _optional_regime(regime: Any) -> RegimeName | None:
    if regime is None:
        return None
    if isinstance(regime, RegimeName):
        return regime
    try:
        return RegimeName(str(regime))
    except ValueError:
        return None


def _float_feature(features: dict[str, Any], name: str, default: float) -> float:
    try:
        value = float(features.get(name, default))
    except (TypeError, ValueError):
        return float(default)
    if not math.isfinite(value):
        return float(default)
    return value


def _is_exit_action(action: Any) -> bool:
    value = str(action).lower()
    return value in {
        ExitAction.PARTIAL_EXIT.value,
        ExitAction.FULL_EXIT.value,
    }


def _pair_key(pair: Any) -> str:
    key = getattr(pair, "key", None)
    return str(key if key is not None else pair)


__all__ = [
    "ExitDecision",
    "ExitRiskWeights",
    "ExitScores",
    "HardKillResult",
    "PostTradeShadowReport",
    "ProbabilisticExitManager",
    "ShadowDecisionRecord",
    "clamp",
    "clamp01",
    "compute_drawdown_risk_score",
    "compute_execution_risk_score",
    "compute_exit_scores",
    "compute_trend_continuation_risk",
]
