"""Point-in-time indicator helpers for chart replay.

Every helper in this module accepts only data available at or before the
evaluated timestamp. Callers should pass ``candles_until_t`` from a
ReplaySnapshot, never a full future candle series.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from core.chart_audit.marker_types import BlockReason, CuratorState
from core.chart_audit.replay_snapshot import ReplayConfigSnapshot, ReplaySnapshot

try:
    from shared_cointegration_validator import (
        count_mean_reversion_crossings,
        evaluate_cointegration,
    )
except Exception:  # pragma: no cover - dependency fallback for constrained envs
    count_mean_reversion_crossings = None
    evaluate_cointegration = None


STATUS_OK = "ok"
STATUS_INSUFFICIENT_DATA = "insufficient_data"
STATUS_VALID_CANDIDATE = "valid_candidate"
STATUS_BLOCKED_CANDIDATE = "blocked_candidate"


@dataclass(frozen=True)
class SpreadPointInTimeResult:
    status: str
    spread_until_t: tuple[float, ...] = ()
    latest_spread: float | None = None
    hedge_ratio: float | None = None
    cointegration_result: Mapping[str, Any] | None = None
    reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "spread_until_t": list(self.spread_until_t),
            "latest_spread": self.latest_spread,
            "hedge_ratio": self.hedge_ratio,
            "cointegration_result": _json_mapping(self.cointegration_result),
            "reason": self.reason,
            "metadata": _json_mapping(self.metadata),
        }


@dataclass(frozen=True)
class ZScorePointInTimeResult:
    status: str
    zscore_until_t: tuple[float, ...] = ()
    latest_zscore: float | None = None
    spread_until_t: tuple[float, ...] = ()
    rolling_mean: float | None = None
    rolling_std: float | None = None
    hedge_ratio: float | None = None
    cointegration_result: Mapping[str, Any] | None = None
    reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "zscore_until_t": list(self.zscore_until_t),
            "latest_zscore": self.latest_zscore,
            "spread_until_t": list(self.spread_until_t),
            "rolling_mean": self.rolling_mean,
            "rolling_std": self.rolling_std,
            "hedge_ratio": self.hedge_ratio,
            "cointegration_result": _json_mapping(self.cointegration_result),
            "reason": self.reason,
            "metadata": _json_mapping(self.metadata),
        }


@dataclass(frozen=True)
class ZeroCrossingsPointInTimeResult:
    status: str
    zero_crossings: int = 0
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "zero_crossings": self.zero_crossings,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class BasicHardValidationPointInTimeResult:
    status: str
    passed: bool
    block_reasons: tuple[BlockReason, ...] = ()
    reason: str | None = None
    metrics: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "passed": self.passed,
            "block_reasons": [reason.value for reason in self.block_reasons],
            "reason": self.reason,
            "metrics": _json_mapping(self.metrics),
        }


def compute_spread_point_in_time(
    candles_until_t: Sequence[Any],
    config_snapshot: ReplayConfigSnapshot,
) -> SpreadPointInTimeResult:
    """Compute spread and hedge ratio from candles available up to t only."""

    del config_snapshot  # Reserved for later replay config fields.
    candles = tuple(candles_until_t or ())
    provided_spreads = _finite_values(_extract_spread_value(candle) for candle in candles)
    if provided_spreads and len(provided_spreads) == len(candles):
        return SpreadPointInTimeResult(
            status=STATUS_OK,
            spread_until_t=tuple(provided_spreads),
            latest_spread=provided_spreads[-1],
            cointegration_result={
                "status": STATUS_INSUFFICIENT_DATA,
                "reason": "price history unavailable; used provided point-in-time spread values",
            },
            metadata={"spread_source": "provided_candle_spread"},
        )

    price_pairs = [_extract_price_pair(candle) for candle in candles]
    if not price_pairs or any(pair is None for pair in price_pairs):
        return SpreadPointInTimeResult(
            status=STATUS_INSUFFICIENT_DATA,
            reason="candles_until_t must contain either spread values or two close price series",
        )

    prices_1 = [float(pair[0]) for pair in price_pairs if pair is not None]
    prices_2 = [float(pair[1]) for pair in price_pairs if pair is not None]
    if len(prices_1) < 2 or len(prices_2) < 2:
        return SpreadPointInTimeResult(
            status=STATUS_INSUFFICIENT_DATA,
            reason="at least two candles are required to compute point-in-time spread",
        )
    if any(value <= 0 for value in prices_1 + prices_2):
        return SpreadPointInTimeResult(
            status=STATUS_INSUFFICIENT_DATA,
            reason="log-price spread requires positive close prices",
        )

    log_1 = tuple(math.log(value) for value in prices_1)
    log_2 = tuple(math.log(value) for value in prices_2)
    hedge_ratio = _ols_beta(log_1, log_2)
    if hedge_ratio is None:
        return SpreadPointInTimeResult(
            status=STATUS_INSUFFICIENT_DATA,
            reason="hedge ratio unavailable from candles_until_t",
        )

    spread = tuple(float(y - hedge_ratio * x) for y, x in zip(log_1, log_2))
    return SpreadPointInTimeResult(
        status=STATUS_OK,
        spread_until_t=spread,
        latest_spread=spread[-1],
        hedge_ratio=hedge_ratio,
        cointegration_result=_cointegration_result_point_in_time(log_1, log_2),
        metadata={"spread_source": "log_price_ols"},
    )


def compute_zscore_point_in_time(
    candles_until_t: Sequence[Any],
    config_snapshot: ReplayConfigSnapshot,
) -> ZScorePointInTimeResult:
    """Compute rolling Z-scores from only ``candles_until_t``."""

    spread_result = compute_spread_point_in_time(candles_until_t, config_snapshot)
    if spread_result.status != STATUS_OK:
        return ZScorePointInTimeResult(
            status=STATUS_INSUFFICIENT_DATA,
            reason=spread_result.reason,
            hedge_ratio=spread_result.hedge_ratio,
            cointegration_result=spread_result.cointegration_result,
            metadata=spread_result.metadata,
        )

    spreads = spread_result.spread_until_t
    window = _zscore_window(config_snapshot, len(spreads))
    zscores = _rolling_zscores_point_in_time(spreads, window)
    finite_zscores = tuple(value for value in zscores if _is_finite(value))
    if not finite_zscores:
        return ZScorePointInTimeResult(
            status=STATUS_INSUFFICIENT_DATA,
            spread_until_t=spreads,
            hedge_ratio=spread_result.hedge_ratio,
            cointegration_result=spread_result.cointegration_result,
            reason="insufficient spread history or zero variance for point-in-time z-score",
            metadata={**dict(spread_result.metadata), "zscore_window": window},
        )

    rolling_slice = tuple(spreads[-window:])
    rolling_mean = _mean(rolling_slice)
    rolling_std = _sample_std(rolling_slice)
    return ZScorePointInTimeResult(
        status=STATUS_OK,
        zscore_until_t=finite_zscores,
        latest_zscore=finite_zscores[-1],
        spread_until_t=spreads,
        rolling_mean=rolling_mean,
        rolling_std=rolling_std,
        hedge_ratio=spread_result.hedge_ratio,
        cointegration_result=spread_result.cointegration_result,
        metadata={**dict(spread_result.metadata), "zscore_window": window},
    )


def compute_zero_crossings_point_in_time(spread_or_z_until_t: Sequence[Any]) -> ZeroCrossingsPointInTimeResult:
    """Count mean-reversion crossings using only values provided up to t."""

    values = tuple(_finite_values(spread_or_z_until_t))
    if len(values) < 2:
        return ZeroCrossingsPointInTimeResult(
            status=STATUS_INSUFFICIENT_DATA,
            reason="at least two finite values are required for zero-crossing count",
        )

    try:
        if count_mean_reversion_crossings is not None:
            crossings = int(count_mean_reversion_crossings(values))
        else:
            crossings = _fallback_mean_reversion_crossings(values)
    except Exception:
        crossings = _fallback_mean_reversion_crossings(values)

    return ZeroCrossingsPointInTimeResult(
        status=STATUS_OK,
        zero_crossings=max(crossings, 0),
    )


def compute_basic_hard_validation_point_in_time(
    snapshot: ReplaySnapshot,
) -> BasicHardValidationPointInTimeResult:
    """Run MVP replay hard validation against a point-in-time snapshot."""

    block_reasons: list[BlockReason] = []
    insufficient = False

    if not _finite_values(snapshot.zscore_until_t):
        insufficient = True
        block_reasons.append(BlockReason.INSUFFICIENT_HISTORY)
    if not _finite_values(snapshot.spread_until_t):
        insufficient = True
        if BlockReason.INSUFFICIENT_HISTORY not in block_reasons:
            block_reasons.append(BlockReason.INSUFFICIENT_HISTORY)

    block_reasons.extend(_curator_block_reasons(snapshot.curator_state))
    if snapshot.curator_state == CuratorState.INSUFFICIENT_HISTORY:
        insufficient = True
    if str(snapshot.curator_state_source or "").strip().lower() == "unavailable":
        insufficient = True
        block_reasons.append(BlockReason.CURATOR_STATE_UNAVAILABLE)

    coint_result = snapshot.cointegration_result_until_t if isinstance(snapshot.cointegration_result_until_t, Mapping) else {}
    coint_status = str(coint_result.get("status") or "").strip().lower()
    if coint_status == STATUS_INSUFFICIENT_DATA:
        insufficient = True
        block_reasons.append(BlockReason.INSUFFICIENT_HISTORY)
    coint_flag = _optional_int(coint_result.get("coint_flag"))
    if coint_flag is not None and coint_flag != 1:
        block_reasons.append(BlockReason.COINTEGRATION_INVALID)

    zero_crossings = snapshot.zero_crossing_count_until_t
    if zero_crossings is None:
        insufficient = True
        block_reasons.append(BlockReason.INSUFFICIENT_HISTORY)
    elif int(zero_crossings) < int(snapshot.config_snapshot.min_zero_crossings):
        block_reasons.append(BlockReason.ZERO_CROSSINGS_TOO_LOW)

    hedge_ratio = _optional_float(snapshot.hedge_ratio_until_t)
    if hedge_ratio is not None and (hedge_ratio == 0.0 or not math.isfinite(hedge_ratio)):
        block_reasons.append(BlockReason.HEDGE_RATIO_UNSTABLE)

    block_reasons.extend(_orderbook_block_reasons(snapshot.orderbook_snapshot, snapshot.config_snapshot))
    unique_reasons = _unique_reasons(block_reasons)

    if insufficient:
        status = STATUS_INSUFFICIENT_DATA
    elif unique_reasons:
        status = STATUS_BLOCKED_CANDIDATE
    else:
        status = STATUS_VALID_CANDIDATE

    return BasicHardValidationPointInTimeResult(
        status=status,
        passed=status == STATUS_VALID_CANDIDATE,
        block_reasons=unique_reasons,
        reason=_validation_reason(status, unique_reasons),
        metrics={
            "latest_zscore": _latest_finite(snapshot.zscore_until_t),
            "latest_spread": _latest_finite(snapshot.spread_until_t),
            "zero_crossings": zero_crossings,
            "min_zero_crossings": int(snapshot.config_snapshot.min_zero_crossings),
            "hedge_ratio": hedge_ratio,
            "curator_state": snapshot.curator_state.value,
            "curator_state_source": snapshot.curator_state_source,
            "config_source": snapshot.config_snapshot.config_source,
        },
    )


def _cointegration_result_point_in_time(log_1: Sequence[float], log_2: Sequence[float]) -> Mapping[str, Any]:
    if len(log_1) < 3 or len(log_2) < 3:
        return {
            "status": STATUS_INSUFFICIENT_DATA,
            "reason": "at least three candles are required for cointegration evaluation",
        }
    if evaluate_cointegration is None:
        return {
            "status": STATUS_INSUFFICIENT_DATA,
            "reason": "cointegration evaluator unavailable",
        }
    try:
        metrics = evaluate_cointegration(
            log_1,
            log_2,
            window=max(2, min(60, len(log_1))),
            already_logged=True,
        )
    except Exception:
        return {
            "status": STATUS_INSUFFICIENT_DATA,
            "reason": "cointegration evaluator failed for candles_until_t",
        }
    return _json_mapping({"status": STATUS_OK, **dict(metrics)})


def _rolling_zscores_point_in_time(values: Sequence[float], window: int) -> tuple[float, ...]:
    zscores: list[float] = []
    for idx in range(len(values)):
        end = idx + 1
        start = max(0, end - window)
        window_values = tuple(float(value) for value in values[start:end])
        if len(window_values) < 2:
            continue
        std = _sample_std(window_values)
        if std is None or std <= 0:
            continue
        zscores.append((float(values[idx]) - float(_mean(window_values))) / std)
    return tuple(zscores)


def _zscore_window(config_snapshot: ReplayConfigSnapshot, available_count: int) -> int:
    raw = _get_any(config_snapshot, "z_score_window", "zscore_window", "rolling_window", "window")
    parsed = _optional_int(raw)
    if parsed is None or parsed < 2:
        parsed = available_count
    return max(2, min(int(parsed), max(int(available_count), 2)))


def _extract_spread_value(candle: Any) -> float | None:
    return _optional_float(_get_any(candle, "spread", "spread_value", "point_in_time_spread"))


def _extract_price_pair(candle: Any) -> tuple[float, float] | None:
    price_1 = _optional_float(
        _get_any(
            candle,
            "price_1",
            "price1",
            "close_1",
            "close1",
            "ticker_1_close",
            "sym_1_close",
            "asset_1_close",
            "close_a",
        )
    )
    price_2 = _optional_float(
        _get_any(
            candle,
            "price_2",
            "price2",
            "close_2",
            "close2",
            "ticker_2_close",
            "sym_2_close",
            "asset_2_close",
            "close_b",
        )
    )
    if price_1 is None or price_2 is None:
        values = _get_any(candle, "prices", "close_prices")
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes, bytearray)) and len(values) >= 2:
            price_1 = _optional_float(values[0])
            price_2 = _optional_float(values[1])
    if price_1 is None or price_2 is None:
        return None
    return price_1, price_2


def _ols_beta(series_y: Sequence[float], series_x: Sequence[float]) -> float | None:
    if len(series_y) != len(series_x) or len(series_y) < 2:
        return None
    mean_y = _mean(series_y)
    mean_x = _mean(series_x)
    denominator = sum((float(x) - mean_x) ** 2 for x in series_x)
    if denominator <= 0:
        return None
    numerator = sum((float(x) - mean_x) * (float(y) - mean_y) for x, y in zip(series_x, series_y))
    beta = numerator / denominator
    return beta if math.isfinite(beta) else None


def _curator_block_reasons(curator_state: CuratorState) -> list[BlockReason]:
    mapping = {
        CuratorState.ANALYSIS_ONLY: BlockReason.ANALYSIS_ONLY,
        CuratorState.EXCLUDED: BlockReason.PAIR_EXCLUDED,
        CuratorState.HOSPITAL: BlockReason.PAIR_IN_HOSPITAL,
        CuratorState.GRAVEYARD: BlockReason.PAIR_IN_GRAVEYARD,
        CuratorState.STALE_DATA: BlockReason.STALE_DATA,
        CuratorState.INSUFFICIENT_HISTORY: BlockReason.INSUFFICIENT_HISTORY,
        CuratorState.LOW_LIQUIDITY: BlockReason.CURATOR_LOW_LIQUIDITY,
    }
    reason = mapping.get(curator_state)
    return [reason] if reason is not None else []


def _orderbook_block_reasons(orderbook_snapshot: Any, config: ReplayConfigSnapshot) -> list[BlockReason]:
    if orderbook_snapshot is None:
        return []
    reasons: list[BlockReason] = []
    age_ms = _optional_float(_get_any(orderbook_snapshot, "book_freshness_ms", "freshness_ms", "update_age_ms", "age_ms"))
    if config.max_orderbook_age_ms is not None and age_ms is not None and age_ms > float(config.max_orderbook_age_ms):
        reasons.append(BlockReason.ORDERBOOK_STALE)
    spread_bps = _optional_float(_get_any(orderbook_snapshot, "spread_bps", "book_spread_bps"))
    if config.max_spread_bps is not None and spread_bps is not None and spread_bps > float(config.max_spread_bps):
        reasons.append(BlockReason.LIQUIDITY_FAILED)
    slippage_bps = _optional_float(_get_any(orderbook_snapshot, "slippage_bps", "estimated_slippage_bps", "slippage_estimate_bps"))
    if config.max_slippage_bps is not None and slippage_bps is not None and slippage_bps > float(config.max_slippage_bps):
        reasons.append(BlockReason.LIQUIDITY_FAILED)
    liquidity_score = _optional_float(_get_any(orderbook_snapshot, "liquidity_score"))
    if (
        config.min_liquidity_score is not None
        and liquidity_score is not None
        and liquidity_score < float(config.min_liquidity_score)
    ):
        reasons.append(BlockReason.LIQUIDITY_FAILED)
    return reasons


def _validation_reason(status: str, block_reasons: tuple[BlockReason, ...]) -> str:
    if status == STATUS_VALID_CANDIDATE:
        return "point-in-time hard validation passed"
    if status == STATUS_INSUFFICIENT_DATA:
        return "insufficient point-in-time data for hard validation"
    return "blocked by " + ", ".join(reason.value for reason in block_reasons)


def _unique_reasons(reasons: Sequence[BlockReason]) -> tuple[BlockReason, ...]:
    seen: set[BlockReason] = set()
    ordered: list[BlockReason] = []
    for reason in reasons:
        if reason in seen:
            continue
        seen.add(reason)
        ordered.append(reason)
    return tuple(ordered)


def _fallback_mean_reversion_crossings(values: Sequence[float]) -> int:
    mean_value = _mean(values)
    centered = [float(value) - mean_value for value in values]
    std = _sample_std(centered) or 0.0
    threshold = abs(std) * 0.1
    directional: list[int] = []
    for value in centered:
        if value > threshold:
            directional.append(1)
        elif value < -threshold:
            directional.append(-1)
    if len(directional) < 2:
        return 0
    return sum(1 for left, right in zip(directional, directional[1:]) if left != right)


def _finite_values(values: Sequence[Any] | Any) -> list[float]:
    output: list[float] = []
    for value in values:
        parsed = _optional_float(value)
        if parsed is not None and math.isfinite(parsed):
            output.append(parsed)
    return output


def _latest_finite(values: Sequence[Any]) -> float | None:
    finite = _finite_values(values)
    return finite[-1] if finite else None


def _mean(values: Sequence[float]) -> float:
    return sum(float(value) for value in values) / float(len(values))


def _sample_std(values: Sequence[float]) -> float | None:
    if len(values) < 2:
        return None
    mean_value = _mean(values)
    variance = sum((float(value) - mean_value) ** 2 for value in values) / float(len(values) - 1)
    if variance < 0:
        return None
    std = math.sqrt(variance)
    return std if math.isfinite(std) else None


def _optional_int(value: Any) -> int | None:
    parsed = _optional_float(value)
    return int(parsed) if parsed is not None else None


def _optional_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _is_finite(value: Any) -> bool:
    parsed = _optional_float(value)
    return parsed is not None


def _get_any(record: Any, *keys: str) -> Any:
    for key in keys:
        if isinstance(record, Mapping) and key in record:
            return record[key]
        if not isinstance(record, Mapping) and hasattr(record, key):
            return getattr(record, key)
    return None


def _json_mapping(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {str(key): _json_value(item) for key, item in value.items()}


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _json_mapping(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if hasattr(value, "tolist"):
        try:
            return _json_value(value.tolist())
        except Exception:
            return None
    parsed = _optional_float(value)
    if parsed is not None:
        return parsed
    return value


__all__ = [
    "BasicHardValidationPointInTimeResult",
    "SpreadPointInTimeResult",
    "STATUS_BLOCKED_CANDIDATE",
    "STATUS_INSUFFICIENT_DATA",
    "STATUS_OK",
    "STATUS_VALID_CANDIDATE",
    "ZScorePointInTimeResult",
    "ZeroCrossingsPointInTimeResult",
    "compute_basic_hard_validation_point_in_time",
    "compute_spread_point_in_time",
    "compute_zero_crossings_point_in_time",
    "compute_zscore_point_in_time",
]
