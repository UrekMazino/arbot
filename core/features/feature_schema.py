"""Versioned feature schemas and named feature vectors.

The advanced ML stack must not pass anonymous numpy arrays into statistical or
learning models. This module keeps vector length, feature names, finite values,
and schema-version compatibility explicit at the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


class FeatureSchemaVersionMismatch(ValueError):
    """Raised when persisted feature schema metadata is incompatible."""


@dataclass(frozen=True)
class FeatureSchema:
    names: tuple[str, ...]
    feature_schema_version: int = 1
    reject_nan_features: bool = True

    @property
    def version(self) -> int:
        return self.feature_schema_version

    def __post_init__(self) -> None:
        if not self.names:
            raise ValueError("Feature schema must include at least one feature.")
        normalized = tuple(str(name).strip() for name in self.names)
        if any(not name for name in normalized):
            raise ValueError("Feature names must be non-empty strings.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Feature names must be unique.")
        if normalized != self.names:
            object.__setattr__(self, "names", normalized)
        try:
            version = int(self.feature_schema_version)
        except (TypeError, ValueError) as exc:
            raise ValueError("feature_schema_version must be an integer.") from exc
        if version < 1:
            raise ValueError("feature_schema_version must be >= 1.")
        object.__setattr__(self, "feature_schema_version", version)

    def index(self, name: str) -> int:
        if name not in self.names:
            raise KeyError(f"Feature not in schema: {name}")
        return self.names.index(name)

    def validate(self, values: np.ndarray | list[float] | tuple[float, ...]) -> np.ndarray:
        array = np.asarray(values, dtype=float)
        if array.ndim != 1:
            raise ValueError("Feature vector must be 1D.")
        if array.shape[0] != len(self.names):
            raise ValueError("Feature vector length does not match schema.")
        if self.reject_nan_features and not np.all(np.isfinite(array)):
            raise ValueError("Feature vector contains NaN or inf.")
        return array

    def assert_compatible_version(self, expected_feature_schema_version: int) -> None:
        expected = int(expected_feature_schema_version)
        if self.feature_schema_version != expected:
            raise FeatureSchemaVersionMismatch(
                "Feature schema version mismatch: "
                f"expected {expected}, got {self.feature_schema_version}."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_schema_version": self.feature_schema_version,
            "version": self.feature_schema_version,
            "names": list(self.names),
            "reject_nan_features": self.reject_nan_features,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        expected_feature_schema_version: int | None = None,
    ) -> "FeatureSchema":
        if not isinstance(data, dict):
            raise ValueError("Feature schema payload must be a dictionary.")
        raw_names = data.get("names")
        if not isinstance(raw_names, (list, tuple)):
            raise ValueError("Feature schema payload must include names.")
        version = int(data.get("feature_schema_version", data.get("version", 1)))
        schema = cls(
            names=tuple(str(name) for name in raw_names),
            feature_schema_version=version,
            reject_nan_features=bool(data.get("reject_nan_features", True)),
        )
        if expected_feature_schema_version is not None:
            schema.assert_compatible_version(expected_feature_schema_version)
        return schema


@dataclass
class NamedFeatureVector:
    schema: FeatureSchema
    values: np.ndarray

    def __post_init__(self) -> None:
        self.values = self.schema.validate(self.values)

    def get(self, name: str) -> float:
        return float(self.values[self.schema.index(name)])

    def to_dict(self) -> dict[str, float]:
        return {name: float(self.values[idx]) for idx, name in enumerate(self.schema.names)}


__all__ = [
    "FeatureSchema",
    "FeatureSchemaVersionMismatch",
    "NamedFeatureVector",
]
