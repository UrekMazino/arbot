"""Decayed regime transition weights.

Transition memory is intentionally a floating-weight model. Every observation
decays old mass and adds one fresh unit of evidence, so old regime behavior
fades without pretending these values are integer counts.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from core.regime.regime_types import RegimeName


def _regime_key(regime: RegimeName | str) -> str:
    if isinstance(regime, RegimeName):
        return regime.value
    return RegimeName(str(regime)).value


@dataclass
class RegimeTransitionMatrix:
    weights: dict[str, dict[str, float]] = field(default_factory=dict)
    decay: float = 0.995
    min_mass: float = 1e-6
    _lock: threading.RLock = field(
        default_factory=threading.RLock,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        self.decay = float(self.decay)
        self.min_mass = float(self.min_mass)
        if not 0.0 <= self.decay <= 1.0:
            raise ValueError("decay must be between 0.0 and 1.0.")
        if self.min_mass < 0.0:
            raise ValueError("min_mass must be non-negative.")
        self.weights = self._normalized_weights(self.weights)

    def update(self, previous: RegimeName | str, current: RegimeName | str) -> None:
        previous_key = _regime_key(previous)
        current_key = _regime_key(current)
        with self._lock:
            decayed = self._decayed_weights()
            row = decayed.setdefault(previous_key, {})
            row[current_key] = float(row.get(current_key, 0.0)) + 1.0
            self.weights = self._pruned_weights(decayed)

    def probabilities(self, current: RegimeName | str) -> dict[str, float]:
        current_key = _regime_key(current)
        with self._lock:
            row = {
                target: float(weight)
                for target, weight in self.weights.get(current_key, {}).items()
                if float(weight) > 0.0
            }
        total = sum(row.values())
        if total <= 0.0:
            return {}
        return {target: weight / total for target, weight in row.items()}

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            weights = {
                source: {target: float(weight) for target, weight in row.items()}
                for source, row in self.weights.items()
            }
        return {
            "weights": weights,
            "decay": self.decay,
            "min_mass": self.min_mass,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegimeTransitionMatrix":
        if not isinstance(data, dict):
            raise ValueError("Transition matrix payload must be a dictionary.")
        return cls(
            weights=dict(data.get("weights", {})),
            decay=float(data.get("decay", 0.995)),
            min_mass=float(data.get("min_mass", 1e-6)),
        )

    def _decayed_weights(self) -> dict[str, dict[str, float]]:
        return {
            source: {
                target: float(weight) * self.decay
                for target, weight in row.items()
            }
            for source, row in self.weights.items()
        }

    def _pruned_weights(
        self,
        weights: dict[str, dict[str, float]],
    ) -> dict[str, dict[str, float]]:
        pruned: dict[str, dict[str, float]] = {}
        for source, row in weights.items():
            kept = {
                target: float(weight)
                for target, weight in row.items()
                if float(weight) >= self.min_mass
            }
            if kept:
                pruned[source] = kept
        return pruned

    @staticmethod
    def _normalized_weights(weights: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
        if not isinstance(weights, dict):
            raise ValueError("weights must be a dictionary.")
        normalized: dict[str, dict[str, float]] = {}
        for source, row in weights.items():
            source_key = _regime_key(source)
            if not isinstance(row, dict):
                raise ValueError("transition matrix rows must be dictionaries.")
            normalized[source_key] = {
                _regime_key(target): float(weight)
                for target, weight in row.items()
            }
        return normalized


__all__ = [
    "RegimeTransitionMatrix",
]
