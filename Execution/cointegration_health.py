import math
import os


COINT_HEALTH_VALID = "valid"
COINT_HEALTH_WATCH = "watch"
COINT_HEALTH_BROKEN = "broken"


def _env_float(name, default, minimum=None, maximum=None):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        value = float(default)
    else:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = float(default)
    if minimum is not None and value < minimum:
        value = float(minimum)
    if maximum is not None and value > maximum:
        value = float(maximum)
    return value


def _safe_float(value, default=0.0):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not math.isfinite(parsed):
        return float(default)
    return parsed


def get_cointegration_health_settings(strict_pvalue=0.15):
    strict = _safe_float(strict_pvalue, 0.15)
    if strict < 0:
        strict = 0.0
    if strict > 1:
        strict = 1.0

    watch = _env_float("STATBOT_COINT_WATCH_P_VALUE", 0.25, minimum=0.0, maximum=1.0)
    fail = _env_float("STATBOT_COINT_FAIL_P_VALUE", 0.35, minimum=0.0, maximum=1.0)
    adf_margin_pct = _env_float("STATBOT_COINT_ADF_MARGIN_PCT", 0.10, minimum=0.0)

    if watch < strict:
        watch = strict
    if fail < watch:
        fail = watch

    return {
        "strict_pvalue": strict,
        "watch_pvalue": watch,
        "fail_pvalue": fail,
        "adf_margin_pct": adf_margin_pct,
    }


def classify_cointegration_health(metrics, strict_pvalue=0.15):
    """
    Classify live cointegration health using hysteresis bands.

    valid: strict coint flag/threshold passes.
    watch: slightly outside strict thresholds, so pause entries but avoid quick switching.
    broken: outside the grace band, eligible for the normal hard-fail switch streak.
    """
    metrics = metrics or {}
    settings = get_cointegration_health_settings(strict_pvalue)
    strict = settings["strict_pvalue"]
    watch = settings["watch_pvalue"]
    fail = settings["fail_pvalue"]
    adf_margin_pct = settings["adf_margin_pct"]

    coint_flag = int(_safe_float(metrics.get("coint_flag", 0), 0))
    p_value = _safe_float(metrics.get("p_value", 1.0), 1.0)
    adf_stat = _safe_float(metrics.get("adf_stat", 0.0), 0.0)
    critical_value = _safe_float(metrics.get("critical_value", 0.0), 0.0)

    has_adf = abs(critical_value) > 1e-12
    adf_gap = adf_stat - critical_value if has_adf else 0.0
    adf_margin = abs(critical_value) * adf_margin_pct if has_adf else 0.0
    adf_pass = bool(has_adf and adf_stat < critical_value)
    adf_near = bool(has_adf and adf_gap <= adf_margin)
    strict_pass = bool(p_value < strict and adf_pass)

    if coint_flag == 1 or strict_pass:
        state = COINT_HEALTH_VALID
        reason = "strict_cointegration_passed"
    elif p_value <= watch:
        state = COINT_HEALTH_WATCH
        reason = "p_value_watch_band"
    elif p_value <= fail and adf_near:
        state = COINT_HEALTH_WATCH
        reason = "adf_near_watch_band"
    else:
        state = COINT_HEALTH_BROKEN
        reason = "outside_watch_band"

    return {
        "state": state,
        "reason": reason,
        "is_valid": state == COINT_HEALTH_VALID,
        "is_watch": state == COINT_HEALTH_WATCH,
        "is_broken": state == COINT_HEALTH_BROKEN,
        "p_value": p_value,
        "adf_stat": adf_stat,
        "critical_value": critical_value,
        "adf_gap": adf_gap,
        "adf_margin": adf_margin,
        "adf_pass": adf_pass,
        "adf_near": adf_near,
        **settings,
    }
