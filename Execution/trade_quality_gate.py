from __future__ import annotations

from dataclasses import dataclass, field
import math
import os
from typing import Any


_MODE_VALUES = {"off", "shadow", "active"}
_BROKEN_HEALTH_STATES = {"broken", "degraded", "failed", "fail", "critical", "unhealthy"}


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _safe_int(value: Any, default: int = 0) -> int:
    parsed = _safe_float(value, None)
    if parsed is None:
        return default
    return int(parsed)


def _env_float(name: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    parsed = _safe_float(os.getenv(name), default)
    if parsed is None:
        parsed = default
    if minimum is not None and parsed < minimum:
        parsed = minimum
    if maximum is not None and parsed > maximum:
        parsed = maximum
    return float(parsed)


def _env_int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    parsed = _safe_int(os.getenv(name), default)
    if minimum is not None and parsed < minimum:
        parsed = minimum
    if maximum is not None and parsed > maximum:
        parsed = maximum
    return int(parsed)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


@dataclass(frozen=True)
class TradeQualitySettings:
    mode: str = "active"
    min_score: float = 72.0
    preferred_max_p_value: float = 0.05
    hard_max_p_value: float = 0.15
    hard_min_zero_crossings: int = 3
    min_zero_crossings: int = 15
    target_zero_crossings: int = 30
    min_correlation: float = 0.60
    max_spread_trend: float = 0.002
    hard_max_spread_trend: float = 0.010
    min_edge_z: float = 1.20
    min_pair_trades: int = 4
    min_pair_win_rate: float = 0.45
    max_pair_consecutive_losses: int = 2
    require_pair_profit: bool = True


@dataclass(frozen=True)
class TradeQualityDecision:
    allow: bool
    passed: bool
    mode: str
    score: float
    min_score: float
    reason: str
    reasons: list[str] = field(default_factory=list)
    hard_reasons: list[str] = field(default_factory=list)
    components: dict[str, float] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "allow": bool(self.allow),
            "passed": bool(self.passed),
            "mode": self.mode,
            "score": round(float(self.score), 2),
            "min_score": round(float(self.min_score), 2),
            "reason": self.reason,
            "reasons": list(self.reasons),
            "hard_reasons": list(self.hard_reasons),
            "components": {key: round(float(value), 4) for key, value in self.components.items()},
            "diagnostics": dict(self.diagnostics),
        }


def load_trade_quality_settings(
    *,
    p_value_critical: float = 0.15,
    zero_crossings_min: int = 15,
    correlation_min: float = 0.60,
    trend_critical: float = 0.002,
) -> TradeQualitySettings:
    enabled = _env_flag("STATBOT_TRADE_QUALITY_GATE", True)
    mode = str(os.getenv("STATBOT_TRADE_QUALITY_GATE_MODE") or "active").strip().lower()
    if not enabled:
        mode = "off"
    if mode not in _MODE_VALUES:
        mode = "active"

    p_critical = _safe_float(p_value_critical, 0.15) or 0.15
    p_critical = max(min(p_critical, 1.0), 1e-9)
    preferred_p = min(p_critical, 0.05)

    min_zc = max(int(zero_crossings_min or 0), 0)
    target_zc = max(min_zc * 2, 20)
    trend = abs(_safe_float(trend_critical, 0.002) or 0.002)

    return TradeQualitySettings(
        mode=mode,
        min_score=_env_float("STATBOT_TQG_MIN_SCORE", 72.0, minimum=0.0, maximum=100.0),
        preferred_max_p_value=_env_float(
            "STATBOT_TQG_MAX_P_VALUE",
            preferred_p,
            minimum=1e-9,
            maximum=1.0,
        ),
        hard_max_p_value=_env_float(
            "STATBOT_TQG_HARD_MAX_P_VALUE",
            p_critical,
            minimum=1e-9,
            maximum=1.0,
        ),
        hard_min_zero_crossings=_env_int("STATBOT_TQG_HARD_MIN_ZERO_CROSSINGS", 3, minimum=0),
        min_zero_crossings=_env_int("STATBOT_TQG_MIN_ZERO_CROSSINGS", min_zc, minimum=0),
        target_zero_crossings=_env_int("STATBOT_TQG_TARGET_ZERO_CROSSINGS", target_zc, minimum=1),
        min_correlation=_env_float(
            "STATBOT_TQG_MIN_CORRELATION",
            max(min(float(correlation_min or 0.0), 1.0), 0.0),
            minimum=0.0,
            maximum=1.0,
        ),
        max_spread_trend=_env_float("STATBOT_TQG_MAX_SPREAD_TREND", trend, minimum=0.0),
        hard_max_spread_trend=_env_float(
            "STATBOT_TQG_HARD_MAX_SPREAD_TREND",
            max(trend * 5.0, trend),
            minimum=0.0,
        ),
        min_edge_z=_env_float("STATBOT_TQG_MIN_EDGE_Z", 1.20, minimum=0.0),
        min_pair_trades=_env_int("STATBOT_TQG_PAIR_MIN_TRADES", 4, minimum=0),
        min_pair_win_rate=_env_float("STATBOT_TQG_PAIR_MIN_WIN_RATE", 0.45, minimum=0.0, maximum=1.0),
        max_pair_consecutive_losses=_env_int("STATBOT_TQG_PAIR_MAX_CONSECUTIVE_LOSSES", 2, minimum=0),
        require_pair_profit=_env_flag("STATBOT_TQG_PAIR_REQUIRE_PROFIT", True),
    )


def _score_p_value(p_value: float | None, preferred_max: float, hard_max: float) -> float:
    if p_value is None:
        return 6.0
    if p_value <= 0:
        return 16.0
    preferred_max = max(preferred_max, 1e-9)
    hard_max = max(hard_max, preferred_max)
    if p_value <= preferred_max:
        return max(8.0, 16.0 * (1.0 - 0.50 * (p_value / preferred_max)))
    return max(0.0, 8.0 * (1.0 - ((p_value - preferred_max) / (hard_max - preferred_max + 1e-9))))


def _score_adf(adf_stat: float | None, critical_value: float | None) -> float:
    if adf_stat is None or critical_value is None or abs(critical_value) <= 1e-12:
        return 2.0
    if adf_stat >= critical_value:
        return 0.0
    margin = (critical_value - adf_stat) / abs(critical_value)
    return max(0.0, min(5.0, (margin / 0.20) * 5.0))


def _score_correlation(correlation: float | None, returns_correlation: float | None, minimum: float) -> float:
    if correlation is None:
        price_score = 4.0
    elif correlation < minimum:
        price_score = max(0.0, (correlation / max(minimum, 1e-9)) * 4.0)
    else:
        price_score = 4.0 + min(4.0, ((correlation - minimum) / max(1.0 - minimum, 1e-9)) * 4.0)

    if returns_correlation is None:
        returns_score = 2.0
    else:
        returns_floor = max(minimum * 0.5, 0.10)
        if returns_correlation <= 0:
            returns_score = 0.0
        elif returns_correlation < returns_floor:
            returns_score = (returns_correlation / returns_floor) * 2.0
        else:
            returns_score = 2.0 + min(2.0, ((returns_correlation - returns_floor) / max(1.0 - returns_floor, 1e-9)) * 2.0)
    return min(12.0, price_score + returns_score)


def _score_signal_shape(
    *,
    signal: str,
    zscores: list[float],
    latest_zscore: float,
    entry_z: float,
    entry_z_max: float,
    entry_z_tolerance: float,
) -> tuple[float, list[str], dict[str, Any]]:
    reasons: list[str] = []
    diagnostics: dict[str, Any] = {}
    entry_floor = max(float(entry_z) - max(float(entry_z_tolerance), 0.0), 0.0)
    abs_z = abs(latest_zscore)
    band_width = max(float(entry_z_max) - entry_floor, 0.25)
    band_progress = max(0.0, min(1.0, (abs_z - entry_floor) / band_width))
    band_score = 10.0 + (band_progress * 5.0)

    motion_score = 5.0
    if len(zscores) >= 2:
        previous_z = float(zscores[-2])
        if signal == "SELL_SPREAD":
            away_delta = latest_zscore - previous_z
        else:
            away_delta = previous_z - latest_zscore
        diagnostics["z_away_delta"] = round(float(away_delta), 6)
        if away_delta <= 0:
            motion_score = 5.0
        elif away_delta <= 0.15:
            motion_score = 3.0
            reasons.append("z_drift_mildly_away")
        else:
            motion_score = 0.0
            reasons.append("z_still_accelerating_away")

    return min(20.0, band_score + motion_score), reasons, diagnostics


def _score_liquidity(ratio_long: float | None, ratio_short: float | None, min_ratio: float) -> float:
    if ratio_long is None or ratio_short is None:
        return 7.0
    min_ratio = max(float(min_ratio or 0.0), 0.0)
    ratio_min = min(ratio_long, ratio_short)
    if min_ratio <= 0:
        return min(15.0, 10.0 + min(ratio_min, 5.0))
    return max(0.0, min(15.0, (ratio_min / max(min_ratio * 1.5, 1e-9)) * 15.0))


def _score_pair_history(pair_stats: dict[str, Any] | None, settings: TradeQualitySettings) -> tuple[float, list[str]]:
    reasons: list[str] = []
    if not isinstance(pair_stats, dict):
        return 7.0, ["pair_history_unavailable"]

    trades = _safe_int(pair_stats.get("trades"), 0)
    if trades < settings.min_pair_trades:
        return 7.0, ["pair_history_insufficient"]

    win_rate = _safe_float(pair_stats.get("win_rate"), 0.0) or 0.0
    win_usdt = _safe_float(pair_stats.get("win_usdt"), 0.0) or 0.0
    loss_usdt = _safe_float(pair_stats.get("loss_usdt"), 0.0) or 0.0
    consecutive_losses = _safe_int(pair_stats.get("consecutive_losses"), 0)

    if win_rate < settings.min_pair_win_rate:
        reasons.append("pair_win_rate_below_target")
    if settings.require_pair_profit and loss_usdt > 0 and win_usdt <= loss_usdt:
        reasons.append("pair_profit_factor_below_one")
    if consecutive_losses > 0:
        reasons.append("pair_recent_losses")

    win_score = min(5.0, (win_rate / max(settings.min_pair_win_rate, 1e-9)) * 5.0)
    if loss_usdt <= 0:
        profit_score = 3.0 if win_usdt > 0 else 1.5
    else:
        profit_score = min(3.0, (win_usdt / loss_usdt) * 3.0)
    recent_loss_score = max(0.0, 2.0 - float(consecutive_losses))
    return max(0.0, min(10.0, win_score + profit_score + recent_loss_score)), reasons


def evaluate_trade_quality(
    *,
    signal: str,
    metrics: dict[str, Any] | None,
    zscores: list[float] | None,
    pair_stats: dict[str, Any] | None,
    entry_z: float,
    entry_z_max: float,
    entry_z_tolerance: float,
    exit_z: float,
    ratio_long: float | None,
    ratio_short: float | None,
    min_liquidity_ratio: float,
    target_usdt: float | None = None,
    liquidity_long_usdt: float | None = None,
    liquidity_short_usdt: float | None = None,
    p_value_critical: float = 0.15,
    zero_crossings_min: int = 15,
    correlation_min: float = 0.60,
    trend_critical: float = 0.002,
    settings: TradeQualitySettings | None = None,
) -> TradeQualityDecision:
    settings = settings or load_trade_quality_settings(
        p_value_critical=p_value_critical,
        zero_crossings_min=zero_crossings_min,
        correlation_min=correlation_min,
        trend_critical=trend_critical,
    )
    if settings.mode == "off":
        return TradeQualityDecision(
            allow=True,
            passed=True,
            mode=settings.mode,
            score=100.0,
            min_score=settings.min_score,
            reason="trade_quality_gate_disabled",
            components={"disabled": 100.0},
        )

    metrics = metrics or {}
    zscores = [float(z) for z in (zscores or []) if _safe_float(z, None) is not None]
    latest_zscore = _safe_float(metrics.get("latest_zscore"), None)
    if latest_zscore is None and zscores:
        latest_zscore = zscores[-1]

    p_value = _safe_float(metrics.get("p_value"), None)
    adf_stat = _safe_float(metrics.get("adf_stat"), None)
    critical_value = _safe_float(metrics.get("critical_value"), None)
    zero_crossings = _safe_int(metrics.get("zero_crossings"), 0)
    correlation = _safe_float(metrics.get("correlation"), None)
    returns_correlation = _safe_float(metrics.get("returns_correlation"), None)
    spread_trend = _safe_float(metrics.get("spread_trend"), None)
    coint_flag = _safe_int(metrics.get("coint_flag"), 0)
    coint_health = str(metrics.get("coint_health") or "").strip().lower()
    abs_z = abs(latest_zscore) if latest_zscore is not None else None
    entry_floor = max(float(entry_z) - max(float(entry_z_tolerance), 0.0), 0.0)

    hard_reasons: list[str] = []
    reasons: list[str] = []
    diagnostics: dict[str, Any] = {
        "p_value": p_value,
        "zero_crossings": zero_crossings,
        "correlation": correlation,
        "returns_correlation": returns_correlation,
        "spread_trend": spread_trend,
        "latest_zscore": latest_zscore,
        "target_usdt": target_usdt,
        "liquidity_long_usdt": liquidity_long_usdt,
        "liquidity_short_usdt": liquidity_short_usdt,
        "ratio_long": ratio_long,
        "ratio_short": ratio_short,
        "min_liquidity_ratio": min_liquidity_ratio,
    }

    if signal not in {"BUY_SPREAD", "SELL_SPREAD"}:
        hard_reasons.append("unsupported_signal")
    if coint_flag != 1:
        hard_reasons.append("cointegration_not_confirmed")
    if coint_health in _BROKEN_HEALTH_STATES:
        hard_reasons.append(f"cointegration_health_{coint_health}")
    if p_value is not None and p_value > settings.hard_max_p_value:
        hard_reasons.append("p_value_above_hard_limit")
    if latest_zscore is None:
        hard_reasons.append("latest_zscore_missing")
    elif abs_z is not None:
        if abs_z < entry_floor:
            hard_reasons.append("zscore_below_entry_floor")
        if abs_z > float(entry_z_max):
            hard_reasons.append("zscore_beyond_max_entry_band")
    if zero_crossings < settings.hard_min_zero_crossings:
        hard_reasons.append("zero_crossings_below_hard_min")
    if (
        spread_trend is not None
        and settings.hard_max_spread_trend > 0
        and abs(spread_trend) > settings.hard_max_spread_trend
    ):
        hard_reasons.append("spread_trend_above_hard_limit")

    pair_trades = _safe_int((pair_stats or {}).get("trades"), 0) if isinstance(pair_stats, dict) else 0
    pair_consecutive_losses = _safe_int((pair_stats or {}).get("consecutive_losses"), 0) if isinstance(pair_stats, dict) else 0
    if (
        settings.max_pair_consecutive_losses > 0
        and pair_trades >= settings.min_pair_trades
        and pair_consecutive_losses >= settings.max_pair_consecutive_losses
    ):
        hard_reasons.append("pair_consecutive_losses_at_limit")

    components: dict[str, float] = {}
    components["cointegration"] = min(
        25.0,
        _score_p_value(p_value, settings.preferred_max_p_value, settings.hard_max_p_value)
        + _score_adf(adf_stat, critical_value)
        + (4.0 if coint_flag == 1 else 0.0),
    )
    components["mean_reversion"] = min(
        15.0,
        min(10.0, (zero_crossings / max(settings.target_zero_crossings, 1)) * 10.0)
        + (
            5.0
            if spread_trend is None or settings.max_spread_trend <= 0
            else max(0.0, 5.0 * (1.0 - (abs(spread_trend) / max(settings.max_spread_trend, 1e-12))))
        )
    )
    components["correlation"] = _score_correlation(correlation, returns_correlation, settings.min_correlation) * (10.0 / 12.0)

    if latest_zscore is None:
        components["signal_shape"] = 0.0
    else:
        signal_score, signal_reasons, signal_diagnostics = _score_signal_shape(
            signal=signal,
            zscores=zscores,
            latest_zscore=latest_zscore,
            entry_z=float(entry_z),
            entry_z_max=float(entry_z_max),
            entry_z_tolerance=float(entry_z_tolerance),
        )
        components["signal_shape"] = signal_score
        reasons.extend(signal_reasons)
        diagnostics.update(signal_diagnostics)

    components["liquidity"] = _score_liquidity(ratio_long, ratio_short, min_liquidity_ratio)

    if abs_z is None:
        edge_z = 0.0
    else:
        edge_z = max(0.0, abs_z - max(float(exit_z), 0.0))
    diagnostics["edge_z"] = round(float(edge_z), 6)
    components["cost_edge"] = min(8.0, (edge_z / max(settings.min_edge_z, 1e-9)) * 8.0)

    pair_history_score, pair_history_reasons = _score_pair_history(pair_stats, settings)
    components["pair_history"] = pair_history_score * (7.0 / 10.0)
    reasons.extend(pair_history_reasons)

    if p_value is not None and p_value > settings.preferred_max_p_value:
        reasons.append("p_value_above_quality_target")
    if zero_crossings < settings.min_zero_crossings:
        reasons.append("zero_crossings_below_quality_target")
    if correlation is not None and correlation < settings.min_correlation:
        reasons.append("correlation_below_quality_target")
    if spread_trend is not None and settings.max_spread_trend > 0 and abs(spread_trend) > settings.max_spread_trend:
        reasons.append("spread_trend_above_quality_target")
    if edge_z < settings.min_edge_z:
        reasons.append("edge_z_below_cost_buffer")

    score = round(sum(components.values()), 2)
    passed = not hard_reasons and score >= settings.min_score
    allow = passed or settings.mode == "shadow"
    if hard_reasons:
        reason = hard_reasons[0]
    elif score < settings.min_score:
        reason = "score_below_threshold"
    else:
        reason = "quality_passed"

    return TradeQualityDecision(
        allow=allow,
        passed=passed,
        mode=settings.mode,
        score=score,
        min_score=settings.min_score,
        reason=reason,
        reasons=sorted(set(reasons)),
        hard_reasons=sorted(set(hard_reasons)),
        components=components,
        diagnostics=diagnostics,
    )
