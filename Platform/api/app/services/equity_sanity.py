from __future__ import annotations

import math


def coerce_float(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def is_plausible_equity(
    equity,
    *,
    reference_equity: float | None = None,
    previous_equity: float | None = None,
) -> bool:
    value = coerce_float(equity)
    if value is None or value < 0:
        return False

    reference = coerce_float(reference_equity)
    previous = coerce_float(previous_equity)
    positive_anchor = max(reference or 0.0, previous or 0.0)

    if value <= 0 and positive_anchor > 1.0:
        return False

    return True
