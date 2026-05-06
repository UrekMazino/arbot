from __future__ import annotations

import numpy as np
import pytest

from core.features.feature_schema import (
    FeatureSchema,
    FeatureSchemaVersionMismatch,
    NamedFeatureVector,
)


def test_feature_schema_rejects_wrong_vector_length():
    schema = FeatureSchema(("p_value", "liquidity_score"))

    with pytest.raises(ValueError, match="length"):
        schema.validate(np.array([0.01]))


def test_feature_schema_rejects_non_1d_vector():
    schema = FeatureSchema(("p_value", "liquidity_score"))

    with pytest.raises(ValueError, match="1D"):
        schema.validate(np.array([[0.01, 0.9]]))


@pytest.mark.parametrize("bad_value", [np.nan, np.inf, -np.inf])
def test_feature_schema_rejects_nan_and_inf(bad_value):
    schema = FeatureSchema(("p_value", "liquidity_score"))

    with pytest.raises(ValueError, match="NaN or inf"):
        schema.validate(np.array([0.01, bad_value]))


def test_named_feature_vector_validates_and_gets_by_name():
    schema = FeatureSchema(("p_value", "liquidity_score", "break_risk"))
    vector = NamedFeatureVector(schema, np.array([0.01, 0.8, 0.2]))

    assert vector.get("liquidity_score") == pytest.approx(0.8)
    assert vector.to_dict() == {
        "p_value": pytest.approx(0.01),
        "liquidity_score": pytest.approx(0.8),
        "break_risk": pytest.approx(0.2),
    }


def test_feature_schema_index_changes_with_feature_order_deterministically():
    first = FeatureSchema(("p_value", "liquidity_score", "break_risk"))
    second = FeatureSchema(("break_risk", "p_value", "liquidity_score"))

    assert first.index("liquidity_score") == 1
    assert second.index("liquidity_score") == 2


def test_feature_schema_serializes_feature_schema_version():
    schema = FeatureSchema(("p_value", "liquidity_score"), feature_schema_version=3)

    payload = schema.to_dict()
    restored = FeatureSchema.from_dict(payload, expected_feature_schema_version=3)

    assert payload["feature_schema_version"] == 3
    assert payload["version"] == 3
    assert restored.names == ("p_value", "liquidity_score")
    assert restored.feature_schema_version == 3


def test_feature_schema_version_mismatch_fails_closed():
    payload = {
        "feature_schema_version": 1,
        "names": ["p_value", "liquidity_score"],
    }

    with pytest.raises(FeatureSchemaVersionMismatch, match="version mismatch"):
        FeatureSchema.from_dict(payload, expected_feature_schema_version=2)


def test_feature_schema_rejects_duplicate_feature_names():
    with pytest.raises(ValueError, match="unique"):
        FeatureSchema(("p_value", "p_value"))


def test_named_feature_vector_rejects_unknown_feature_name():
    schema = FeatureSchema(("p_value", "liquidity_score"))
    vector = NamedFeatureVector(schema, [0.01, 0.8])

    with pytest.raises(KeyError):
        vector.get("break_risk")
