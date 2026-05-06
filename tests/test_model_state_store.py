from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from core.storage.model_state_store import ModelStateStore


def _safe_defaults() -> dict:
    return {
        "feature_schema_version": 2,
        "advanced_live_enabled": False,
        "weights": [],
    }


def test_missing_state_initializes_safe_defaults_and_logs_critical(tmp_path, caplog):
    store = ModelStateStore(tmp_path)

    with caplog.at_level(logging.CRITICAL):
        state = store.load_json("missing_model", _safe_defaults)

    assert state == _safe_defaults()
    assert "fallback to safe defaults" in caplog.text
    assert "missing_state" in caplog.text
    assert "Advanced live mode must remain disabled" in caplog.text


def test_corrupted_json_initializes_safe_defaults_without_crashing(tmp_path, caplog):
    path = tmp_path / "bayes.json"
    path.write_text("{not-json", encoding="utf-8")
    store = ModelStateStore(tmp_path)

    with caplog.at_level(logging.CRITICAL):
        state = store.load_json("bayes", _safe_defaults)

    assert state == _safe_defaults()
    assert "state_load_failed" in caplog.text
    assert "Advanced live mode must remain disabled" in caplog.text


def test_atomic_write_writes_temp_file_then_renames(monkeypatch, tmp_path):
    store = ModelStateStore(tmp_path, atomic_write=True)
    replace_calls = []
    original_replace = Path.replace

    def spy_replace(self: Path, target: str | Path):
        replace_calls.append(
            {
                "source_name": self.name,
                "target_name": Path(target).name,
                "source_existed_before_replace": self.exists(),
            }
        )
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", spy_replace)

    path = store.save_json("linucb", {"b": [1.0], "feature_schema_version": 1})

    assert path == tmp_path / "linucb.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "b": [1.0],
        "feature_schema_version": 1,
    }
    assert replace_calls == [
        {
            "source_name": ".linucb.json.tmp",
            "target_name": "linucb.json",
            "source_existed_before_replace": True,
        }
    ]
    assert not (tmp_path / ".linucb.json.tmp").exists()


def test_feature_schema_version_mismatch_falls_back_to_safe_defaults(tmp_path, caplog):
    path = tmp_path / "bandit.json"
    path.write_text(
        json.dumps(
            {
                "feature_schema_version": 1,
                "weights": [99.0],
                "advanced_live_enabled": True,
            }
        ),
        encoding="utf-8",
    )
    store = ModelStateStore(tmp_path)

    with caplog.at_level(logging.CRITICAL):
        state = store.load_json("bandit", _safe_defaults, expected_feature_schema_version=2)

    assert state == _safe_defaults()
    assert state["advanced_live_enabled"] is False
    assert "Feature schema version mismatch" in caplog.text
    assert "Advanced live mode must remain disabled" in caplog.text


def test_nested_feature_schema_version_mismatch_falls_back(tmp_path, caplog):
    path = tmp_path / "reputation.json"
    path.write_text(
        json.dumps(
            {
                "feature_schema": {
                    "feature_schema_version": 1,
                    "names": ["p_value"],
                },
                "weights": [99.0],
            }
        ),
        encoding="utf-8",
    )
    store = ModelStateStore(tmp_path)

    with caplog.at_level(logging.CRITICAL):
        state = store.load_json("reputation", _safe_defaults, expected_feature_schema_version=2)

    assert state == _safe_defaults()
    assert "Feature schema version mismatch" in caplog.text


@dataclass
class DummyModel:
    value: int = 0

    def to_dict(self) -> dict:
        return {"value": self.value, "feature_schema_version": 2}

    @classmethod
    def from_dict(cls, data: dict) -> "DummyModel":
        return cls(value=int(data["value"]))

    def save_state(self, store: ModelStateStore) -> None:
        store.save_model("dummy", self)

    def load_state(self, store: ModelStateStore) -> None:
        loaded = store.load_model("dummy", DummyModel, DummyModel)
        self.value = loaded.value


def test_save_and_load_stateful_model(tmp_path):
    store = ModelStateStore(tmp_path)
    model = DummyModel(value=7)

    store.save_model("dummy", model)
    loaded = store.load_model("dummy", DummyModel, DummyModel, expected_feature_schema_version=2)

    assert loaded == DummyModel(value=7)


def test_model_hydration_error_falls_back_without_crashing(tmp_path, caplog):
    path = tmp_path / "dummy.json"
    path.write_text(json.dumps({"feature_schema_version": 2}), encoding="utf-8")
    store = ModelStateStore(tmp_path)

    with caplog.at_level(logging.CRITICAL):
        loaded = store.load_model("dummy", DummyModel, lambda: DummyModel(value=3))

    assert loaded == DummyModel(value=3)
    assert "model_hydration_failed" in caplog.text
