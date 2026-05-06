"""LinUCB contextual bandit with schema-validated feature vectors."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

from core.config.advanced_ml_config import AdvancedMLConfig
from core.features.feature_schema import FeatureSchema, NamedFeatureVector


@dataclass(frozen=True)
class BanditContext:
    pair: Any
    features: NamedFeatureVector


@dataclass(frozen=True)
class BanditRankResult:
    pair: Any
    expected_reward: float
    uncertainty: float
    exploration_bonus: float
    final_rank_score: float
    selected_for_exploration: bool
    reasons: list[str]


class LinUCBContextualBandit:
    def __init__(
        self,
        config: AdvancedMLConfig | None = None,
        *,
        schema: FeatureSchema | None = None,
        A: np.ndarray | list[list[float]] | None = None,
        b: np.ndarray | list[float] | None = None,
    ) -> None:
        self.config = config or AdvancedMLConfig()
        self.schema = schema
        self.alpha = float(self.config.bandit.alpha)
        self.decay = float(self.config.bandit.decay)
        self.lambda_reg = float(self.config.bandit.lambda_reg)
        if not 0.0 <= self.decay <= 1.0:
            raise ValueError("decay must be between 0.0 and 1.0.")
        if self.lambda_reg <= 0.0:
            raise ValueError("lambda_reg must be positive.")
        self._lock = threading.RLock()
        self.A: np.ndarray | None = None
        self.b: np.ndarray | None = None
        if schema is not None:
            self._initialize_state(len(schema.names), A=A, b=b)
        elif A is not None or b is not None:
            raise ValueError("schema is required when restoring A or b.")

    def rank(
        self,
        context: Any,
        *,
        selected_for_exploration: bool = False,
    ) -> BanditRankResult:
        pair = _read_attr(context, "pair")
        if not _is_hard_valid_context(context):
            return BanditRankResult(
                pair=pair,
                expected_reward=0.0,
                uncertainty=0.0,
                exploration_bonus=0.0,
                final_rank_score=0.0,
                selected_for_exploration=False,
                reasons=["invalid candidate skipped"],
            )
        x = self._vector_from_context(context)
        with self._lock:
            self._ensure_state(len(x))
            assert self.A is not None
            assert self.b is not None
            matrix = self.A + self.lambda_reg * np.eye(len(x))
            theta = np.linalg.solve(matrix, self.b)
            expected_reward = float(theta.T @ x)
            A_inv_x = np.linalg.solve(matrix, x)
            uncertainty = self.alpha * math.sqrt(max(float(x.T @ A_inv_x), 0.0))
        final_rank_score = expected_reward + uncertainty
        return BanditRankResult(
            pair=pair,
            expected_reward=expected_reward,
            uncertainty=uncertainty,
            exploration_bonus=uncertainty,
            final_rank_score=final_rank_score,
            selected_for_exploration=bool(selected_for_exploration),
            reasons=["linucb score"],
        )

    def rank_many(self, contexts: Iterable[Any]) -> list[BanditRankResult]:
        results = [
            self.rank(context)
            for context in contexts
            if _is_hard_valid_context(context)
        ]
        return sorted(results, key=lambda result: result.final_rank_score, reverse=True)

    def select(self, contexts: Iterable[Any]) -> BanditRankResult | None:
        results = self.rank_many(contexts)
        return results[0] if results else None

    def update(
        self,
        context: Any,
        *,
        reward: float | None = None,
        reward_bps: float | None = None,
        pnl_bps: float = 0.0,
        fee_bps: float = 0.0,
        slippage_bps: float = 0.0,
        drawdown_penalty_bps: float = 0.0,
        regime_break_penalty_bps: float = 0.0,
        excessive_hold_penalty_bps: float = 0.0,
    ) -> bool:
        if not _is_hard_valid_context(context):
            return False
        x = self._vector_from_context(context)
        normalized_reward = self._normalize_reward(
            reward=reward,
            reward_bps=reward_bps,
            pnl_bps=pnl_bps,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            drawdown_penalty_bps=drawdown_penalty_bps,
            regime_break_penalty_bps=regime_break_penalty_bps,
            excessive_hold_penalty_bps=excessive_hold_penalty_bps,
        )
        with self._lock:
            self._ensure_state(len(x))
            assert self.A is not None
            assert self.b is not None
            identity = np.eye(len(x))
            self.A = (
                self.decay * self.A
                + (1.0 - self.decay) * self.lambda_reg * identity
                + np.outer(x, x)
            )
            self.b = self.decay * self.b + normalized_reward * x
        return True

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            if self.schema is None or self.A is None or self.b is None:
                return {
                    "feature_schema_version": self.config.features.feature_schema_version,
                    "schema": None,
                    "A": None,
                    "b": None,
                    "alpha": self.alpha,
                    "decay": self.decay,
                    "lambda_reg": self.lambda_reg,
                }
            return {
                "feature_schema_version": self.schema.feature_schema_version,
                "schema": self.schema.to_dict(),
                "A": self.A.tolist(),
                "b": self.b.tolist(),
                "alpha": self.alpha,
                "decay": self.decay,
                "lambda_reg": self.lambda_reg,
            }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LinUCBContextualBandit":
        if not isinstance(data, dict):
            raise ValueError("LinUCB payload must be a dictionary.")
        config = AdvancedMLConfig()
        config.bandit.alpha = float(data.get("alpha", config.bandit.alpha))
        config.bandit.decay = float(data.get("decay", config.bandit.decay))
        config.bandit.lambda_reg = float(data.get("lambda_reg", config.bandit.lambda_reg))
        schema_payload = data.get("schema")
        if schema_payload is None:
            return cls(config)
        schema = FeatureSchema.from_dict(schema_payload)
        return cls(
            config,
            schema=schema,
            A=np.asarray(data["A"], dtype=float),
            b=np.asarray(data["b"], dtype=float),
        )

    def save_state(self, store: Any) -> None:
        store.save_model("linucb", self)

    def load_state(self, store: Any) -> None:
        loaded = store.load_model(
            "linucb",
            LinUCBContextualBandit,
            lambda: LinUCBContextualBandit(self.config, schema=self.schema),
            expected_feature_schema_version=self.config.features.feature_schema_version,
        )
        with self._lock:
            self.schema = loaded.schema
            self.A = None if loaded.A is None else loaded.A.copy()
            self.b = None if loaded.b is None else loaded.b.copy()
            self.alpha = loaded.alpha
            self.decay = loaded.decay
            self.lambda_reg = loaded.lambda_reg

    def _vector_from_context(self, context: Any) -> np.ndarray:
        features = _read_attr(context, "features")
        if not isinstance(features, NamedFeatureVector):
            raise TypeError("LinUCB requires a NamedFeatureVector, not a raw feature array.")
        with self._lock:
            if self.schema is None:
                self.schema = features.schema
            elif self.schema.names != features.schema.names:
                raise ValueError("Feature schema names do not match LinUCB state.")
            elif self.schema.feature_schema_version != features.schema.feature_schema_version:
                raise ValueError("Feature schema version does not match LinUCB state.")
            return self.schema.validate(features.values).copy()

    def _ensure_state(self, dim: int) -> None:
        if self.A is None or self.b is None:
            self._initialize_state(dim)
        assert self.A is not None
        assert self.b is not None
        if self.A.shape != (dim, dim):
            raise ValueError("LinUCB A matrix dimension does not match feature schema.")
        if self.b.shape != (dim,):
            raise ValueError("LinUCB b vector dimension does not match feature schema.")

    def _initialize_state(
        self,
        dim: int,
        *,
        A: np.ndarray | list[list[float]] | None = None,
        b: np.ndarray | list[float] | None = None,
    ) -> None:
        if dim <= 0:
            raise ValueError("LinUCB feature dimension must be positive.")
        self.A = (
            np.asarray(A, dtype=float).copy()
            if A is not None
            else self.lambda_reg * np.eye(dim)
        )
        self.b = (
            np.asarray(b, dtype=float).copy()
            if b is not None
            else np.zeros(dim, dtype=float)
        )
        if self.A.shape != (dim, dim):
            raise ValueError("A must be a square matrix matching schema length.")
        if self.b.shape != (dim,):
            raise ValueError("b must be a vector matching schema length.")
        if not np.all(np.isfinite(self.A)) or not np.all(np.isfinite(self.b)):
            raise ValueError("LinUCB state contains NaN or inf.")

    def _normalize_reward(
        self,
        *,
        reward: float | None,
        reward_bps: float | None,
        pnl_bps: float,
        fee_bps: float,
        slippage_bps: float,
        drawdown_penalty_bps: float,
        regime_break_penalty_bps: float,
        excessive_hold_penalty_bps: float,
    ) -> float:
        if reward is not None:
            return float(reward)
        if reward_bps is None:
            reward_bps = (
                float(pnl_bps)
                - float(fee_bps)
                - float(slippage_bps)
                - float(drawdown_penalty_bps)
                - float(regime_break_penalty_bps)
                - float(excessive_hold_penalty_bps)
            )
        return math.tanh(float(reward_bps) / max(self.config.bandit.reward_scale_bps, 1e-9))


def _read_attr(source: Any, name: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _is_hard_valid_context(context: Any) -> bool:
    hard_validation = _read_attr(context, "hard_validation")
    if hard_validation is not None:
        return bool(_read_attr(hard_validation, "is_valid", False))
    is_valid = _read_attr(context, "is_valid")
    if is_valid is not None:
        return bool(is_valid)
    return True


LinUCB = LinUCBContextualBandit


__all__ = [
    "BanditContext",
    "BanditRankResult",
    "LinUCB",
    "LinUCBContextualBandit",
]
