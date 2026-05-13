"""Hedge-ratio drift audit helpers.

The drift monitor emits an ExitCandidate for the existing orchestrator. It does
not directly close, resize, or rebalance positions.
"""

from __future__ import annotations

import math
from typing import Any

from core.ev.hold_exit_ev import ExitAction, clamp01
from core.trade_management.exit_orchestrator import ExitCandidate, ExitCandidateCategory


HEDGE_RATIO_DRIFT_SOURCE = "hedge_ratio_drift"


def compute_hedge_ratio_drift_pct(
    *,
    entry_hedge_ratio: float,
    current_hedge_ratio: float,
) -> float:
    entry = _finite_float(entry_hedge_ratio)
    current = _finite_float(current_hedge_ratio)
    if entry is None or current is None:
        raise ValueError("entry_hedge_ratio and current_hedge_ratio must be finite numbers")
    return abs(current - entry) / max(abs(entry), 1e-9)


def hedge_ratio_drift_exit_candidate(
    *,
    entry_hedge_ratio: float | None,
    current_hedge_ratio: float | None,
    config: Any,
    entry_id: str | None = None,
) -> ExitCandidate | None:
    entry = _finite_float(entry_hedge_ratio)
    current = _finite_float(current_hedge_ratio)
    if entry is None or current is None:
        return None

    max_drift = _positive_config_float(config, "max_hedge_ratio_drift_pct", 0.20)
    severe_drift = _positive_config_float(config, "severe_hedge_ratio_drift_pct", 0.35)
    drift = compute_hedge_ratio_drift_pct(entry_hedge_ratio=entry, current_hedge_ratio=current)
    if drift < max_drift:
        return None

    severity = clamp01(drift / severe_drift)
    action = ExitAction.FULL_EXIT if drift >= severe_drift else ExitAction.TIGHTEN_STOP
    return ExitCandidate(
        name=HEDGE_RATIO_DRIFT_SOURCE,
        category=ExitCandidateCategory.QUALITY,
        action=action,
        reason="hedge ratio drift exceeded configured threshold",
        priority=100,
        exit_percentage=1.0 if action == ExitAction.FULL_EXIT else 0.0,
        severity=severity,
        net_profit_guard_applies=False,
        metadata={
            "source": HEDGE_RATIO_DRIFT_SOURCE,
            "entry_id": entry_id,
            "entry_hedge_ratio": entry,
            "current_hedge_ratio": current,
            "hedge_ratio_drift_pct": drift,
            "max_hedge_ratio_drift_pct": max_drift,
            "severe_hedge_ratio_drift_pct": severe_drift,
            "blockable_by_net_profit_guard": False,
        },
    )


def _positive_config_float(config: Any, name: str, default: float) -> float:
    value = getattr(config, name, default)
    parsed = _finite_float(value)
    return parsed if parsed is not None and parsed > 0.0 else float(default)


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


__all__ = [
    "HEDGE_RATIO_DRIFT_SOURCE",
    "compute_hedge_ratio_drift_pct",
    "hedge_ratio_drift_exit_candidate",
]
