"""Safe JSON persistence for advanced ML model state.

Model state is never allowed to crash the trading bot on startup. Missing,
corrupted, incompatible, or partially written state falls back to caller-provided
safe defaults and emits a critical log entry so live advanced mode can stay off
while shadow mode continues.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Callable, Protocol, TypeVar

from core.features.feature_schema import FeatureSchemaVersionMismatch


logger = logging.getLogger(__name__)

T = TypeVar("T")


class StatefulModel(Protocol):
    def to_dict(self) -> dict[str, Any]:
        ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        ...

    def save_state(self, store: "ModelStateStore") -> None:
        ...

    def load_state(self, store: "ModelStateStore") -> None:
        ...


def _safe_default(default_factory: Callable[[], T] | T) -> T:
    return default_factory() if callable(default_factory) else default_factory


class ModelStateStore:
    def __init__(
        self,
        root_path: str | Path,
        *,
        atomic_write: bool = True,
        corrupted_state_policy: str = "safe_defaults",
        log: logging.Logger | None = None,
    ) -> None:
        self.root_path = Path(root_path)
        self.atomic_write = bool(atomic_write)
        self.corrupted_state_policy = str(corrupted_state_policy or "safe_defaults")
        self.log = log or logger
        self._lock = threading.RLock()

    def path_for(self, model_name: str) -> Path:
        name = str(model_name or "").strip()
        if not name:
            raise ValueError("model_name must be a non-empty string.")
        if any(part in {"", ".", ".."} for part in Path(name).parts):
            raise ValueError(f"Unsafe model_name: {model_name!r}")
        if not name.endswith(".json"):
            name = f"{name}.json"
        return self.root_path / name

    def load_json(
        self,
        model_name: str,
        default_factory: Callable[[], dict[str, Any]] | dict[str, Any],
        *,
        expected_feature_schema_version: int | None = None,
    ) -> dict[str, Any]:
        path = self.path_for(model_name)
        with self._lock:
            if not path.exists():
                return self._fallback(
                    model_name,
                    default_factory,
                    reason="missing_state",
                    detail=f"Model state file not found: {path}",
                )
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("Model state JSON must be an object.")
                self._validate_feature_schema_version(
                    data,
                    expected_feature_schema_version=expected_feature_schema_version,
                )
                return data
            except Exception as exc:
                return self._fallback(
                    model_name,
                    default_factory,
                    reason="state_load_failed",
                    detail=str(exc),
                )

    def save_json(self, model_name: str, state: dict[str, Any]) -> Path:
        if not isinstance(state, dict):
            raise ValueError("Model state must be a dictionary.")
        path = self.path_for(model_name)
        payload = json.dumps(state, indent=2, sort_keys=True)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            if self.atomic_write:
                temp_path = path.with_name(f".{path.name}.tmp")
                temp_path.write_text(payload, encoding="utf-8")
                temp_path.replace(path)
            else:
                path.write_text(payload, encoding="utf-8")
        return path

    def load_model(
        self,
        model_name: str,
        model_cls: type[T],
        default_factory: Callable[[], T],
        *,
        expected_feature_schema_version: int | None = None,
    ) -> T:
        data = self.load_json(
            model_name,
            lambda: {},
            expected_feature_schema_version=expected_feature_schema_version,
        )
        if not data:
            return default_factory()
        try:
            return model_cls.from_dict(data)  # type: ignore[attr-defined]
        except Exception as exc:
            self._log_critical(
                model_name,
                "model_hydration_failed",
                str(exc),
            )
            return default_factory()

    def save_model(self, model_name: str, model: StatefulModel) -> Path:
        return self.save_json(model_name, model.to_dict())

    def _fallback(
        self,
        model_name: str,
        default_factory: Callable[[], dict[str, Any]] | dict[str, Any],
        *,
        reason: str,
        detail: str,
    ) -> dict[str, Any]:
        if self.corrupted_state_policy != "safe_defaults":
            raise RuntimeError(f"Unsupported corrupted_state_policy: {self.corrupted_state_policy}")
        self._log_critical(model_name, reason, detail)
        default_state = _safe_default(default_factory)
        if not isinstance(default_state, dict):
            raise ValueError("default_factory must produce a dictionary for load_json.")
        return dict(default_state)

    def _log_critical(self, model_name: str, reason: str, detail: str) -> None:
        self.log.critical(
            "Model state fallback to safe defaults: model=%s reason=%s detail=%s. "
            "Advanced live mode must remain disabled until state is healthy.",
            model_name,
            reason,
            detail,
        )

    @staticmethod
    def _validate_feature_schema_version(
        data: dict[str, Any],
        *,
        expected_feature_schema_version: int | None,
    ) -> None:
        if expected_feature_schema_version is None:
            return
        actual = data.get("feature_schema_version")
        if actual is None:
            schema_payload = data.get("feature_schema")
            if isinstance(schema_payload, dict):
                actual = schema_payload.get("feature_schema_version", schema_payload.get("version"))
        if int(actual or 0) != int(expected_feature_schema_version):
            raise FeatureSchemaVersionMismatch(
                "Feature schema version mismatch: "
                f"expected {expected_feature_schema_version}, got {actual!r}."
            )


__all__ = [
    "ModelStateStore",
    "StatefulModel",
]
