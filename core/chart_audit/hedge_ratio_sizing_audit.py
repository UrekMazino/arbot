"""Hedge-ratio sizing audit helpers for chart replay and entry metadata.

These helpers are pure calculations. They do not place orders, rebalance open
positions, or change live sizing unless a caller explicitly chooses the returned
plan.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from core.chart_audit.marker_types import BlockReason


HEDGE_SIZING_MODE_EQUAL_NOTIONAL = "equal_notional"
HEDGE_SIZING_MODE_GROSS_NORMALIZED_BETA = "gross_normalized_beta"
HEDGE_RATIO_SOURCE_FRESH = "fresh_cointegration_at_entry"
HEDGE_RATIO_SOURCE_MONITORING = "monitoring_cointegration"
HEDGE_RATIO_SOURCE_DISCOVERY_STALE = "discovery_stale"


class HedgeRatioLegRole(str, Enum):
    LEG1 = "leg1"
    LEG2 = "leg2"


@dataclass(frozen=True)
class HedgeRatioValidation:
    valid: bool
    beta: float | None
    block_reasons: tuple[BlockReason, ...] = ()
    reason: str | None = None


@dataclass(frozen=True)
class HedgeRatioSizingPlan:
    mode: str
    gross_pair_notional_usdt: float
    leg1_notional_usdt: float
    leg2_notional_usdt: float
    beta: float
    leg1_side: str | None = None
    leg2_side: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "gross_pair_notional_usdt": self.gross_pair_notional_usdt,
            "leg1_notional_usdt": self.leg1_notional_usdt,
            "leg2_notional_usdt": self.leg2_notional_usdt,
            "beta": self.beta,
            "leg1_side": self.leg1_side,
            "leg2_side": self.leg2_side,
        }


@dataclass(frozen=True)
class HedgeRatioSizingPreview:
    selected_mode: str
    sizing_enabled: bool
    hedge_ratio: float | None
    hedge_ratio_source: str | None
    hedge_ratio_valid: bool
    block_reasons: tuple[BlockReason, ...]
    equal_notional: HedgeRatioSizingPlan | None
    gross_normalized_beta: HedgeRatioSizingPlan | None
    selected: HedgeRatioSizingPlan | None
    leg1_delta_usdt: float | None = None
    leg2_delta_usdt: float | None = None
    max_delta_usdt: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_mode": self.selected_mode,
            "sizing_enabled": self.sizing_enabled,
            "hedge_ratio": self.hedge_ratio,
            "hedge_ratio_source": self.hedge_ratio_source,
            "hedge_ratio_valid": self.hedge_ratio_valid,
            "block_reasons": [reason.value for reason in self.block_reasons],
            "equal_notional": self.equal_notional.to_dict() if self.equal_notional else None,
            "gross_normalized_beta": self.gross_normalized_beta.to_dict() if self.gross_normalized_beta else None,
            "selected": self.selected.to_dict() if self.selected else None,
            "leg1_delta_usdt": self.leg1_delta_usdt,
            "leg2_delta_usdt": self.leg2_delta_usdt,
            "max_delta_usdt": self.max_delta_usdt,
        }


def gross_normalized_beta_sizing(
    gross_pair_notional_usdt: float,
    hedge_ratio: float,
    *,
    side: str | None = None,
) -> HedgeRatioSizingPlan:
    gross = _positive_float(gross_pair_notional_usdt, "gross_pair_notional_usdt")
    beta = _positive_float(abs(float(hedge_ratio)), "hedge_ratio")
    leg1 = gross / (1.0 + beta)
    leg2 = gross * beta / (1.0 + beta)
    leg1_side, leg2_side = sides_for_spread_side(side)
    return HedgeRatioSizingPlan(
        mode=HEDGE_SIZING_MODE_GROSS_NORMALIZED_BETA,
        gross_pair_notional_usdt=gross,
        leg1_notional_usdt=leg1,
        leg2_notional_usdt=leg2,
        beta=beta,
        leg1_side=leg1_side,
        leg2_side=leg2_side,
    )


def equal_notional_sizing(
    gross_pair_notional_usdt: float,
    hedge_ratio: float | None = None,
    *,
    side: str | None = None,
) -> HedgeRatioSizingPlan:
    gross = _positive_float(gross_pair_notional_usdt, "gross_pair_notional_usdt")
    beta = abs(float(hedge_ratio)) if _finite_float(hedge_ratio) is not None else 1.0
    leg = gross / 2.0
    leg1_side, leg2_side = sides_for_spread_side(side)
    return HedgeRatioSizingPlan(
        mode=HEDGE_SIZING_MODE_EQUAL_NOTIONAL,
        gross_pair_notional_usdt=gross,
        leg1_notional_usdt=leg,
        leg2_notional_usdt=leg,
        beta=beta,
        leg1_side=leg1_side,
        leg2_side=leg2_side,
    )


def validate_hedge_ratio(hedge_ratio: Any, config: Any) -> HedgeRatioValidation:
    parsed = _finite_float(hedge_ratio)
    if parsed is None or parsed == 0.0:
        return HedgeRatioValidation(False, None, (BlockReason.HEDGE_RATIO_INVALID,), "missing or non-finite hedge ratio")
    if _bool_value(_get_any(config, "reject_negative_hedge_ratio", default=True)) and parsed < 0:
        return HedgeRatioValidation(False, None, (BlockReason.HEDGE_RATIO_INVALID,), "negative hedge ratio rejected")
    beta = abs(parsed)
    min_ratio = _finite_float(_get_any(config, "min_hedge_ratio", default=0.20)) or 0.20
    max_ratio = _finite_float(_get_any(config, "max_hedge_ratio", default=5.00)) or 5.00
    if beta < min_ratio or beta > max_ratio:
        return HedgeRatioValidation(
            False,
            beta,
            (BlockReason.HEDGE_RATIO_UNSTABLE,),
            "hedge ratio outside configured range",
        )
    return HedgeRatioValidation(True, beta)


def build_sizing_preview(
    *,
    gross_pair_notional_usdt: float | None,
    hedge_ratio: float | None,
    config: Any,
    side: str | None = None,
    hedge_ratio_source: str | None = None,
) -> HedgeRatioSizingPreview:
    mode = str(_get_any(config, "hedge_sizing_mode", default=HEDGE_SIZING_MODE_EQUAL_NOTIONAL) or "").strip()
    if mode not in {HEDGE_SIZING_MODE_EQUAL_NOTIONAL, HEDGE_SIZING_MODE_GROSS_NORMALIZED_BETA}:
        mode = HEDGE_SIZING_MODE_EQUAL_NOTIONAL
    sizing_enabled = _bool_value(_get_any(config, "hedge_ratio_sizing_enabled", default=False))
    validation = validate_hedge_ratio(hedge_ratio, config)
    gross = _finite_float(gross_pair_notional_usdt)
    if gross is None or gross <= 0:
        return HedgeRatioSizingPreview(
            selected_mode=mode,
            sizing_enabled=sizing_enabled,
            hedge_ratio=hedge_ratio,
            hedge_ratio_source=hedge_ratio_source,
            hedge_ratio_valid=validation.valid,
            block_reasons=validation.block_reasons,
            equal_notional=None,
            gross_normalized_beta=None,
            selected=None,
        )

    equal_plan = equal_notional_sizing(gross, validation.beta, side=side)
    beta_plan = (
        gross_normalized_beta_sizing(gross, validation.beta, side=side)
        if validation.valid and validation.beta is not None
        else None
    )
    selected = equal_plan
    if sizing_enabled and mode == HEDGE_SIZING_MODE_GROSS_NORMALIZED_BETA and beta_plan is not None:
        selected = beta_plan
    leg1_delta = beta_plan.leg1_notional_usdt - equal_plan.leg1_notional_usdt if beta_plan else None
    leg2_delta = beta_plan.leg2_notional_usdt - equal_plan.leg2_notional_usdt if beta_plan else None
    max_delta = max(abs(leg1_delta), abs(leg2_delta)) if leg1_delta is not None and leg2_delta is not None else None
    return HedgeRatioSizingPreview(
        selected_mode=selected.mode,
        sizing_enabled=sizing_enabled,
        hedge_ratio=hedge_ratio,
        hedge_ratio_source=hedge_ratio_source,
        hedge_ratio_valid=validation.valid,
        block_reasons=validation.block_reasons,
        equal_notional=equal_plan,
        gross_normalized_beta=beta_plan,
        selected=selected,
        leg1_delta_usdt=leg1_delta,
        leg2_delta_usdt=leg2_delta,
        max_delta_usdt=max_delta,
    )


def compute_hedge_sizing_error_pct(
    *,
    actual_leg1_notional_usdt: float,
    actual_leg2_notional_usdt: float,
    target_leg1_notional_usdt: float,
    target_leg2_notional_usdt: float,
) -> float:
    leg1_error = abs(float(actual_leg1_notional_usdt) - float(target_leg1_notional_usdt)) / max(
        float(target_leg1_notional_usdt),
        1e-9,
    )
    leg2_error = abs(float(actual_leg2_notional_usdt) - float(target_leg2_notional_usdt)) / max(
        float(target_leg2_notional_usdt),
        1e-9,
    )
    return max(leg1_error, leg2_error)


def compute_hedge_ratio_execution_error_pct(
    *,
    actual_leg1_notional_usdt: float,
    actual_leg2_notional_usdt: float,
    hedge_ratio: float,
) -> float:
    beta = abs(float(hedge_ratio))
    actual_ratio = float(actual_leg2_notional_usdt) / max(float(actual_leg1_notional_usdt), 1e-9)
    return abs(actual_ratio - beta) / max(beta, 1e-9)


def build_entry_hedge_metadata(
    *,
    gross_pair_notional_usdt: float | None,
    hedge_ratio: float | None,
    hedge_ratio_source: str | None,
    config: Any,
    side: str | None = None,
    actual_leg1_notional_usdt: float | None = None,
    actual_leg2_notional_usdt: float | None = None,
) -> dict[str, Any]:
    preview = build_sizing_preview(
        gross_pair_notional_usdt=gross_pair_notional_usdt,
        hedge_ratio=hedge_ratio,
        hedge_ratio_source=hedge_ratio_source,
        config=config,
        side=side,
    )
    selected = preview.selected
    metadata: dict[str, Any] = {
        "entry_hedge_ratio": hedge_ratio,
        "hedge_ratio_source": hedge_ratio_source,
        "hedge_sizing_mode": preview.selected_mode,
        "hedge_ratio_sizing_enabled": preview.sizing_enabled,
        "target_gross_pair_notional_usdt": gross_pair_notional_usdt,
        "target_leg1_notional_usdt": selected.leg1_notional_usdt if selected else None,
        "target_leg2_notional_usdt": selected.leg2_notional_usdt if selected else None,
        "actual_leg1_notional_usdt": actual_leg1_notional_usdt,
        "actual_leg2_notional_usdt": actual_leg2_notional_usdt,
        "leg1_side": selected.leg1_side if selected else sides_for_spread_side(side)[0],
        "leg2_side": selected.leg2_side if selected else sides_for_spread_side(side)[1],
        "hedge_ratio_valid": preview.hedge_ratio_valid,
        "hedge_sizing_preview": preview.to_dict(),
    }
    if (
        selected is not None
        and actual_leg1_notional_usdt is not None
        and actual_leg2_notional_usdt is not None
        and hedge_ratio is not None
    ):
        metadata["hedge_sizing_error_pct"] = compute_hedge_sizing_error_pct(
            actual_leg1_notional_usdt=actual_leg1_notional_usdt,
            actual_leg2_notional_usdt=actual_leg2_notional_usdt,
            target_leg1_notional_usdt=selected.leg1_notional_usdt,
            target_leg2_notional_usdt=selected.leg2_notional_usdt,
        )
        metadata["hedge_ratio_execution_error_pct"] = compute_hedge_ratio_execution_error_pct(
            actual_leg1_notional_usdt=actual_leg1_notional_usdt,
            actual_leg2_notional_usdt=actual_leg2_notional_usdt,
            hedge_ratio=hedge_ratio,
        )
    return {key: value for key, value in metadata.items() if value is not None}


def resolve_hedge_ratio_source(
    *,
    fresh_cointegration_result: Any | None = None,
    monitoring_metrics: Mapping[str, Any] | None = None,
    discovery_row: Mapping[str, Any] | None = None,
) -> tuple[float | None, str | None]:
    fresh_ratio = _finite_float(_get_any(fresh_cointegration_result, "hedge_ratio"))
    if fresh_ratio is not None:
        return fresh_ratio, HEDGE_RATIO_SOURCE_FRESH
    monitoring_ratio = _finite_float(_get_any(monitoring_metrics or {}, "hedge_ratio", "beta"))
    if monitoring_ratio is not None:
        return monitoring_ratio, HEDGE_RATIO_SOURCE_MONITORING
    discovery_ratio = _finite_float(_get_any(discovery_row or {}, "hedge_ratio", "beta"))
    if discovery_ratio is not None:
        return discovery_ratio, HEDGE_RATIO_SOURCE_DISCOVERY_STALE
    return None, None


def sides_for_spread_side(side: str | None) -> tuple[str | None, str | None]:
    side_text = str(side or "").strip().upper()
    if side_text == "BUY_SPREAD":
        return "long", "short"
    if side_text == "SELL_SPREAD":
        return "short", "long"
    return None, None


def _positive_float(value: Any, name: str) -> float:
    parsed = _finite_float(value)
    if parsed is None or parsed <= 0.0:
        raise ValueError(f"{name} must be a positive finite number")
    return parsed


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _get_any(record: Any, *keys: str, default: Any = None) -> Any:
    if record is None:
        return default
    for key in keys:
        if isinstance(record, Mapping) and key in record:
            return record[key]
        if not isinstance(record, Mapping) and hasattr(record, key):
            return getattr(record, key)
    return default


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on", "enabled"}


__all__ = [
    "HEDGE_RATIO_SOURCE_DISCOVERY_STALE",
    "HEDGE_RATIO_SOURCE_FRESH",
    "HEDGE_RATIO_SOURCE_MONITORING",
    "HEDGE_SIZING_MODE_EQUAL_NOTIONAL",
    "HEDGE_SIZING_MODE_GROSS_NORMALIZED_BETA",
    "HedgeRatioLegRole",
    "HedgeRatioSizingPlan",
    "HedgeRatioSizingPreview",
    "HedgeRatioValidation",
    "build_entry_hedge_metadata",
    "build_sizing_preview",
    "compute_hedge_ratio_execution_error_pct",
    "compute_hedge_sizing_error_pct",
    "equal_notional_sizing",
    "gross_normalized_beta_sizing",
    "resolve_hedge_ratio_source",
    "sides_for_spread_side",
    "validate_hedge_ratio",
]
