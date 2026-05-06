"""Bayesian pair quality scoring for hard-valid pair candidates."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any

from scipy.stats import beta as beta_distribution

from core.config.advanced_ml_config import AdvancedMLConfig
from core.regime.regime_types import RegimeName


GRADE_ORDER = ("D", "C", "B", "A")


@dataclass(frozen=True)
class BayesianPairScore:
    pair: Any
    posterior_good_probability: float
    confidence_interval: tuple[float, float]
    alpha: float
    beta: float
    evidence_count: int
    quality_grade: str
    feature_likelihoods: dict[str, float]
    reasons: list[str]
    timestamp: float


@dataclass
class PairBayesianState:
    alpha: float
    beta: float
    evidence_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "alpha": float(self.alpha),
            "beta": float(self.beta),
            "evidence_count": int(self.evidence_count),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PairBayesianState":
        if not isinstance(data, dict):
            raise ValueError("Pair Bayesian state payload must be a dictionary.")
        alpha = float(data["alpha"])
        beta = float(data["beta"])
        evidence_count = int(data.get("evidence_count", 0))
        if alpha <= 0.0 or beta <= 0.0:
            raise ValueError("Bayesian alpha and beta must be positive.")
        if evidence_count < 0:
            raise ValueError("evidence_count must be non-negative.")
        return cls(alpha=alpha, beta=beta, evidence_count=evidence_count)


class BayesianPairScorer:
    def __init__(
        self,
        config: AdvancedMLConfig | None = None,
        states: dict[str, PairBayesianState] | None = None,
    ) -> None:
        self.config = config or AdvancedMLConfig()
        self._states = dict(states or {})
        self._lock = threading.RLock()

    def score(
        self,
        candidate: Any | None = None,
        *,
        pair: Any | None = None,
        hard_validation: Any | None = None,
        regime_result: Any | None = None,
        features: dict[str, Any] | None = None,
        timestamp: float | None = None,
    ) -> BayesianPairScore:
        pair, hard_validation, merged_features = self._resolve_score_inputs(
            candidate=candidate,
            pair=pair,
            hard_validation=hard_validation,
            regime_result=regime_result,
            features=features,
        )
        if pair is None:
            raise ValueError("pair is required for Bayesian scoring.")
        pair_key = _pair_key(pair)

        if not _hard_validation_is_valid(hard_validation):
            return BayesianPairScore(
                pair=pair,
                posterior_good_probability=0.0,
                confidence_interval=(0.0, 0.0),
                alpha=self.config.bayes.alpha0,
                beta=self.config.bayes.beta0,
                evidence_count=0,
                quality_grade="D",
                feature_likelihoods={},
                reasons=["failed hard validation"],
                timestamp=float(timestamp if timestamp is not None else time.time()),
            )

        with self._lock:
            state = self._states.get(pair_key, self._new_state())
            alpha = float(state.alpha)
            beta = float(state.beta)
            evidence_count = int(state.evidence_count)

        base_posterior = alpha / (alpha + beta)
        lower_ci, upper_ci = _credible_interval(alpha, beta)
        reasons: list[str] = []
        effective_feature_weight = self.config.bayes.feature_weight
        if evidence_count < self.config.bayes.min_evidence:
            effective_feature_weight *= 0.25
            reasons.append("low Bayesian evidence")

        feature_likelihoods = self._feature_likelihoods(
            hard_validation=hard_validation,
            regime_result=regime_result,
            features=merged_features,
        )
        posterior = _feature_adjusted_posterior(
            base_posterior,
            feature_likelihoods,
            effective_feature_weight,
        )
        break_risk = _bounded_float(
            _read_attr(regime_result, "break_risk", merged_features.get("break_risk", 0.0)),
            default=0.0,
        )
        grade = _quality_grade(posterior, lower_ci, break_risk)
        if evidence_count < self.config.bayes.min_evidence:
            grade = _cap_grade(grade, self.config.bayes.max_grade_when_low_evidence)

        return BayesianPairScore(
            pair=pair,
            posterior_good_probability=posterior,
            confidence_interval=(lower_ci, upper_ci),
            alpha=alpha,
            beta=beta,
            evidence_count=evidence_count,
            quality_grade=grade,
            feature_likelihoods=feature_likelihoods,
            reasons=reasons,
            timestamp=float(timestamp if timestamp is not None else time.time()),
        )

    def update(
        self,
        candidate: Any | None = None,
        *,
        pair: Any | None = None,
        hard_validation: Any | None = None,
        net_pnl_after_fees: float | None = None,
        net_pnl_bps: float | None = None,
        severe_regime_break_occurred: bool = False,
        slippage_bps: float = 0.0,
        hold_time_seconds: float = 0.0,
        max_expected_slippage_bps: float | None = None,
        max_expected_hold_time_seconds: float | None = None,
        weight: float = 1.0,
    ) -> bool:
        pair, hard_validation, _ = self._resolve_score_inputs(
            candidate=candidate,
            pair=pair,
            hard_validation=hard_validation,
            regime_result=None,
            features=None,
        )
        if pair is None:
            raise ValueError("pair is required for Bayesian updates.")
        if not _hard_validation_is_valid(hard_validation):
            return False

        pnl_bps = _resolve_pnl_bps(net_pnl_bps, net_pnl_after_fees)
        pnl_after_fees = float(net_pnl_after_fees if net_pnl_after_fees is not None else pnl_bps)
        max_slippage = float(
            max_expected_slippage_bps
            if max_expected_slippage_bps is not None
            else self.config.microstructure.max_allowed_slippage_bps
        )
        max_hold = float(
            max_expected_hold_time_seconds
            if max_expected_hold_time_seconds is not None
            else self.config.exit.max_hold_seconds
        )
        success = (
            pnl_after_fees > 0.0
            and not severe_regime_break_occurred
            and float(slippage_bps) <= max_slippage
            and float(hold_time_seconds) <= max_hold
        )
        normalized_reward = math.tanh(pnl_bps / max(self.config.bandit.reward_scale_bps, 1e-9))
        if not success:
            normalized_reward = -abs(normalized_reward)

        pair_key = _pair_key(pair)
        update_weight = float(weight)
        if update_weight <= 0.0:
            raise ValueError("weight must be positive.")

        with self._lock:
            state = self._states.setdefault(pair_key, self._new_state())
            state.alpha = self.config.bayes.alpha0 + self.config.bayes.decay * (
                state.alpha - self.config.bayes.alpha0
            )
            state.beta = self.config.bayes.beta0 + self.config.bayes.decay * (
                state.beta - self.config.bayes.beta0
            )
            if normalized_reward >= 0.0:
                state.alpha += update_weight * normalized_reward
                state.beta += update_weight * (1.0 - normalized_reward)
            else:
                state.beta += update_weight * abs(normalized_reward)
            state.evidence_count += 1
        return True

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            states = {
                pair_key: state.to_dict()
                for pair_key, state in self._states.items()
            }
        return {
            "feature_schema_version": self.config.features.feature_schema_version,
            "alpha0": self.config.bayes.alpha0,
            "beta0": self.config.bayes.beta0,
            "states": states,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BayesianPairScorer":
        if not isinstance(data, dict):
            raise ValueError("Bayesian scorer payload must be a dictionary.")
        raw_states = data.get("states", {})
        if not isinstance(raw_states, dict):
            raise ValueError("Bayesian scorer states must be a dictionary.")
        config = AdvancedMLConfig()
        config.bayes.alpha0 = float(data.get("alpha0", config.bayes.alpha0))
        config.bayes.beta0 = float(data.get("beta0", config.bayes.beta0))
        states = {
            str(pair_key): PairBayesianState.from_dict(state_payload)
            for pair_key, state_payload in raw_states.items()
        }
        return cls(config=config, states=states)

    def save_state(self, store: Any) -> None:
        store.save_model("bayesian_pair_scorer", self)

    def load_state(self, store: Any) -> None:
        loaded = store.load_model("bayesian_pair_scorer", BayesianPairScorer, BayesianPairScorer)
        with self._lock:
            self._states = dict(loaded._states)

    def _new_state(self) -> PairBayesianState:
        return PairBayesianState(
            alpha=float(self.config.bayes.alpha0),
            beta=float(self.config.bayes.beta0),
            evidence_count=0,
        )

    def _resolve_score_inputs(
        self,
        *,
        candidate: Any | None,
        pair: Any | None,
        hard_validation: Any | None,
        regime_result: Any | None,
        features: dict[str, Any] | None,
    ) -> tuple[Any | None, Any | None, dict[str, Any]]:
        if candidate is not None:
            pair = pair if pair is not None else _read_attr(candidate, "pair")
            hard_validation = (
                hard_validation
                if hard_validation is not None
                else _read_attr(candidate, "hard_validation")
            )
            candidate_features = _features_to_dict(_read_attr(candidate, "pair_features"))
        else:
            candidate_features = {}
        merged_features = dict(candidate_features)
        merged_features.update(_features_to_dict(features))
        merged_features.update(_features_to_dict(_read_attr(regime_result, "features")))
        return pair, hard_validation, merged_features

    def _feature_likelihoods(
        self,
        *,
        hard_validation: Any,
        regime_result: Any | None,
        features: dict[str, Any],
    ) -> dict[str, float]:
        p_value = _read_attr(hard_validation, "p_value", features.get("p_value"))
        regime = _read_attr(regime_result, "regime", features.get("regime"))
        regime_confidence = _bounded_float(
            _read_attr(regime_result, "confidence", features.get("regime_confidence", 0.0)),
            default=0.0,
        )
        likelihoods = {
            "p_value": _p_value_multiplier(p_value),
        }
        regime_multiplier = _regime_multiplier(
            regime,
            regime_confidence=regime_confidence,
            mean_reverting_threshold=self.config.regime.mean_reverting_threshold,
        )
        if regime_multiplier is not None:
            likelihoods["regime"] = regime_multiplier
        return {name: _bounded_multiplier(value) for name, value in likelihoods.items()}


def _credible_interval(alpha: float, beta: float) -> tuple[float, float]:
    lower = float(beta_distribution.ppf(0.05, alpha, beta))
    upper = float(beta_distribution.ppf(0.95, alpha, beta))
    return max(0.0, lower), min(1.0, upper)


def _feature_adjusted_posterior(
    base_posterior: float,
    feature_likelihoods: dict[str, float],
    effective_feature_weight: float,
) -> float:
    log_multiplier_sum = sum(math.log(_bounded_multiplier(value)) for value in feature_likelihoods.values())
    adjusted_logit = _logit(base_posterior) + (log_multiplier_sum * float(effective_feature_weight))
    return _clamp(_sigmoid(adjusted_logit), 0.01, 0.99)


def _quality_grade(posterior: float, lower_ci: float, break_risk: float) -> str:
    if posterior >= 0.80 and lower_ci >= 0.55 and break_risk < 0.30:
        return "A"
    if posterior >= 0.65 and break_risk < 0.45:
        return "B"
    if posterior >= 0.50 and break_risk < 0.65:
        return "C"
    return "D"


def _cap_grade(grade: str, max_grade: str) -> str:
    grade = str(grade).upper()
    max_grade = str(max_grade).upper()
    if grade not in GRADE_ORDER or max_grade not in GRADE_ORDER:
        raise ValueError("Unknown Bayesian grade.")
    return GRADE_ORDER[min(GRADE_ORDER.index(grade), GRADE_ORDER.index(max_grade))]


def _p_value_multiplier(p_value: Any) -> float:
    if p_value is None:
        return 1.0
    p = _bounded_float(p_value, default=1.0)
    if p < 0.005:
        return 1.20
    if p < 0.010:
        return 1.10
    if p < 0.030:
        return 1.00
    if p < 0.050:
        return 0.90
    return 0.70


def _regime_multiplier(
    regime: Any,
    *,
    regime_confidence: float,
    mean_reverting_threshold: float,
) -> float | None:
    regime_name = _optional_regime_name(regime)
    if regime_name is None:
        return None
    if regime_name == RegimeName.MEAN_REVERTING:
        return 1.20 if regime_confidence >= mean_reverting_threshold else 1.10
    if regime_name == RegimeName.UNKNOWN:
        return 0.95
    if regime_name == RegimeName.TRENDING:
        return 0.75
    if regime_name == RegimeName.CORRELATION_BREAKDOWN:
        return 0.50
    if regime_name == RegimeName.LIQUIDITY_STRESS:
        return 0.45
    if regime_name == RegimeName.STRUCTURAL_BREAK:
        return 0.30
    if regime_name == RegimeName.HIGH_VOLATILITY:
        return 0.85
    if regime_name == RegimeName.LOW_VOLATILITY:
        return 0.90
    return None


def _optional_regime_name(regime: Any) -> RegimeName | None:
    if regime is None:
        return None
    if isinstance(regime, RegimeName):
        return regime
    try:
        return RegimeName(str(regime))
    except ValueError:
        return None


def _hard_validation_is_valid(hard_validation: Any) -> bool:
    return bool(_read_attr(hard_validation, "is_valid", False))


def _read_attr(source: Any, name: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _features_to_dict(features: Any) -> dict[str, Any]:
    if features is None:
        return {}
    if isinstance(features, dict):
        return dict(features)
    if hasattr(features, "to_dict"):
        return dict(features.to_dict())
    return {}


def _pair_key(pair: Any) -> str:
    key = _read_attr(pair, "key")
    return str(key if key is not None else pair)


def _resolve_pnl_bps(net_pnl_bps: float | None, net_pnl_after_fees: float | None) -> float:
    if net_pnl_bps is not None:
        return float(net_pnl_bps)
    if net_pnl_after_fees is not None:
        return float(net_pnl_after_fees)
    raise ValueError("net_pnl_bps or net_pnl_after_fees is required for Bayesian updates.")


def _bounded_float(value: Any, *, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _bounded_multiplier(value: float) -> float:
    return _clamp(float(value), 0.30, 1.50)


def _logit(p: float) -> float:
    bounded = _clamp(float(p), 1e-9, 1.0 - 1e-9)
    return math.log(bounded / (1.0 - bounded))


def _sigmoid(x: float) -> float:
    if x >= 0.0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


__all__ = [
    "BayesianPairScore",
    "BayesianPairScorer",
    "PairBayesianState",
]
