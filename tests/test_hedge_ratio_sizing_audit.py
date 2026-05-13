from __future__ import annotations

import pytest

from core.chart_audit.hedge_ratio_sizing_audit import (
    HEDGE_RATIO_SOURCE_DISCOVERY_STALE,
    HEDGE_RATIO_SOURCE_FRESH,
    HEDGE_RATIO_SOURCE_MONITORING,
    HEDGE_SIZING_MODE_EQUAL_NOTIONAL,
    HEDGE_SIZING_MODE_GROSS_NORMALIZED_BETA,
    build_entry_hedge_metadata,
    build_sizing_preview,
    compute_hedge_ratio_execution_error_pct,
    compute_hedge_sizing_error_pct,
    gross_normalized_beta_sizing,
    resolve_hedge_ratio_source,
    validate_hedge_ratio,
)
from core.chart_audit.marker_types import BlockReason
from core.chart_audit.replay_snapshot import FrozenCointegrationResult, ReplayConfigSnapshot


def _config(**overrides: object) -> ReplayConfigSnapshot:
    payload = {
        "config_version": "test",
        "config_source": "historical",
        "entry_z_threshold": 2.0,
        "exit_z_threshold": 0.35,
        "persistence_candles": 1,
        "max_hold_seconds": 3600.0,
        "min_zero_crossings": 0,
        "min_cointegration_window": 1,
        "target_gross_pair_notional_usdt": 1500.0,
    }
    payload.update(overrides)
    return ReplayConfigSnapshot(**payload)  # type: ignore[arg-type]


def test_gross_normalized_beta_sizing_preserves_gross_and_beta_ratio() -> None:
    plan = gross_normalized_beta_sizing(1500.0, 1.8, side="BUY_SPREAD")

    assert plan.leg1_notional_usdt + plan.leg2_notional_usdt == pytest.approx(1500.0)
    assert plan.leg2_notional_usdt / plan.leg1_notional_usdt == pytest.approx(1.8)
    assert plan.leg1_side == "long"
    assert plan.leg2_side == "short"


def test_invalid_hedge_ratio_handling() -> None:
    negative = validate_hedge_ratio(-1.2, _config())
    out_of_range = validate_hedge_ratio(9.0, _config())

    assert negative.valid is False
    assert BlockReason.HEDGE_RATIO_INVALID in negative.block_reasons
    assert out_of_range.valid is False
    assert BlockReason.HEDGE_RATIO_UNSTABLE in out_of_range.block_reasons


def test_negative_hedge_ratio_can_be_allowed_by_config() -> None:
    allowed = validate_hedge_ratio(-1.2, _config(reject_negative_hedge_ratio=False))

    assert allowed.valid is True
    assert allowed.beta == 1.2


def test_hedge_sizing_error_pct_formula() -> None:
    result = compute_hedge_sizing_error_pct(
        actual_leg1_notional_usdt=540.0,
        actual_leg2_notional_usdt=940.0,
        target_leg1_notional_usdt=535.0,
        target_leg2_notional_usdt=965.0,
    )

    assert result == pytest.approx(max(abs(540 - 535) / 535, abs(940 - 965) / 965))


def test_hedge_ratio_execution_error_pct_formula() -> None:
    result = compute_hedge_ratio_execution_error_pct(
        actual_leg1_notional_usdt=500.0,
        actual_leg2_notional_usdt=850.0,
        hedge_ratio=1.8,
    )

    assert result == pytest.approx(abs((850 / 500) - 1.8) / 1.8)


def test_disabled_sizing_returns_equal_notional_selected_with_preview_delta() -> None:
    preview = build_sizing_preview(
        gross_pair_notional_usdt=1500.0,
        hedge_ratio=1.8,
        hedge_ratio_source=HEDGE_RATIO_SOURCE_FRESH,
        config=_config(hedge_ratio_sizing_enabled=False, hedge_sizing_mode=HEDGE_SIZING_MODE_GROSS_NORMALIZED_BETA),
        side="BUY_SPREAD",
    )

    assert preview.sizing_enabled is False
    assert preview.selected is not None
    assert preview.selected.mode == HEDGE_SIZING_MODE_EQUAL_NOTIONAL
    assert preview.gross_normalized_beta is not None
    assert preview.max_delta_usdt is not None
    assert preview.max_delta_usdt > 0


def test_enabled_sizing_selects_gross_normalized_beta_plan() -> None:
    preview = build_sizing_preview(
        gross_pair_notional_usdt=1500.0,
        hedge_ratio=1.8,
        hedge_ratio_source=HEDGE_RATIO_SOURCE_FRESH,
        config=_config(hedge_ratio_sizing_enabled=True, hedge_sizing_mode=HEDGE_SIZING_MODE_GROSS_NORMALIZED_BETA),
        side="SELL_SPREAD",
    )

    assert preview.selected is not None
    assert preview.selected.mode == HEDGE_SIZING_MODE_GROSS_NORMALIZED_BETA
    assert preview.selected.leg1_side == "short"
    assert preview.selected.leg2_side == "long"


def test_entry_metadata_contains_target_actual_and_error_fields() -> None:
    metadata = build_entry_hedge_metadata(
        gross_pair_notional_usdt=1500.0,
        hedge_ratio=1.8,
        hedge_ratio_source=HEDGE_RATIO_SOURCE_FRESH,
        config=_config(hedge_ratio_sizing_enabled=True, hedge_sizing_mode=HEDGE_SIZING_MODE_GROSS_NORMALIZED_BETA),
        side="BUY_SPREAD",
        actual_leg1_notional_usdt=534.9,
        actual_leg2_notional_usdt=963.8,
    )

    assert metadata["entry_hedge_ratio"] == 1.8
    assert metadata["hedge_ratio_source"] == HEDGE_RATIO_SOURCE_FRESH
    assert metadata["hedge_sizing_mode"] == HEDGE_SIZING_MODE_GROSS_NORMALIZED_BETA
    assert metadata["target_gross_pair_notional_usdt"] == 1500.0
    assert metadata["target_leg1_notional_usdt"] == pytest.approx(1500 / 2.8)
    assert metadata["target_leg2_notional_usdt"] == pytest.approx(1500 * 1.8 / 2.8)
    assert metadata["actual_leg1_notional_usdt"] == 534.9
    assert metadata["actual_leg2_notional_usdt"] == 963.8
    assert metadata["hedge_sizing_error_pct"] >= 0
    assert metadata["hedge_ratio_execution_error_pct"] >= 0
    assert metadata["leg1_side"] == "long"
    assert metadata["leg2_side"] == "short"


def test_hedge_ratio_source_priority() -> None:
    fresh = FrozenCointegrationResult(hedge_ratio=1.7, is_valid=True)
    monitoring = {"hedge_ratio": 1.5}
    discovery = {"hedge_ratio": 1.2}

    assert resolve_hedge_ratio_source(
        fresh_cointegration_result=fresh,
        monitoring_metrics=monitoring,
        discovery_row=discovery,
    ) == (1.7, HEDGE_RATIO_SOURCE_FRESH)
    assert resolve_hedge_ratio_source(
        monitoring_metrics=monitoring,
        discovery_row=discovery,
    ) == (1.5, HEDGE_RATIO_SOURCE_MONITORING)
    assert resolve_hedge_ratio_source(discovery_row=discovery) == (1.2, HEDGE_RATIO_SOURCE_DISCOVERY_STALE)
