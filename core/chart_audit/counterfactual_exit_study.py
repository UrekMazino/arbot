"""Lazy counterfactual exit studies for chart audit.

Counterfactual studies are analysis-only. They may evaluate candles after an
already-resolved entry marker, but they must never influence entry generation,
live trading, order execution, or replay state.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from core.chart_audit.ml_replay_types import ReplayMLScoreSnapshot


BUY_SPREAD = "BUY_SPREAD"
SELL_SPREAD = "SELL_SPREAD"


class CounterfactualExitStrategy(str, Enum):
    EXIT_AT_Z_0_50 = "exit_at_z_0_50"
    EXIT_AT_Z_0_35 = "exit_at_z_0_35"
    EXIT_AT_Z_0_00 = "exit_at_z_0_00"
    EXIT_ON_MEAN_CROSSING = "exit_on_mean_crossing"
    EXIT_ON_MAX_HOLD = "exit_on_max_hold"
    EXIT_ON_TRAILING_STOP = "exit_on_trailing_stop"
    EXIT_ON_ADVERSE_ACCELERATION = "exit_on_adverse_acceleration"
    EXIT_ON_REGIME_BREAK = "exit_on_regime_break"
    EXIT_ON_EV_MANAGER = "exit_on_ev_manager"
    EXIT_ON_MICROSTRUCTURE_STRESS = "exit_on_microstructure_stress"


class CounterfactualExitStatus(str, Enum):
    TRIGGERED = "triggered"
    NOT_TRIGGERED = "not_triggered"
    FORCED_CLOSE_AT_WINDOW_END = "forced_close_at_window_end"
    UNAVAILABLE = "unavailable"


ALL_COUNTERFACTUAL_EXIT_STRATEGIES = (
    CounterfactualExitStrategy.EXIT_AT_Z_0_50,
    CounterfactualExitStrategy.EXIT_AT_Z_0_35,
    CounterfactualExitStrategy.EXIT_AT_Z_0_00,
    CounterfactualExitStrategy.EXIT_ON_MEAN_CROSSING,
    CounterfactualExitStrategy.EXIT_ON_MAX_HOLD,
    CounterfactualExitStrategy.EXIT_ON_TRAILING_STOP,
    CounterfactualExitStrategy.EXIT_ON_ADVERSE_ACCELERATION,
    CounterfactualExitStrategy.EXIT_ON_REGIME_BREAK,
    CounterfactualExitStrategy.EXIT_ON_EV_MANAGER,
    CounterfactualExitStrategy.EXIT_ON_MICROSTRUCTURE_STRESS,
)


@dataclass(frozen=True)
class CounterfactualExitConfig:
    max_hold_seconds: float = 6 * 3600.0
    fee_bps: float = 0.0
    slippage_bps: float = 0.0
    force_close_at_window_end: bool = False
    regime_break_threshold: float = 0.65
    ev_exit_score_threshold: float = 0.55
    microstructure_stress_threshold: float = 0.70


@dataclass(frozen=True)
class _CounterfactualCandle:
    timestamp: int
    z_score: float | None = None
    spread: float | None = None
    spread_mean: float | None = None
    price_1: float | None = None
    price_2: float | None = None


@dataclass(frozen=True)
class _EntryAnchor:
    entry_id: str
    entry_marker_type: str
    pair: str
    timeframe: str
    entry_timestamp: float
    entry_side: str
    entry_z: float | None
    entry_spread: float | None
    trade_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CounterfactualExitResult:
    entry_id: str
    exit_strategy: CounterfactualExitStrategy | str
    status: CounterfactualExitStatus | str
    entry_timestamp: int | float
    entry_side: str | None
    entry_z: float | None
    entry_spread: float | None
    hypothetical_exit_timestamp: int | None
    hypothetical_exit_z: float | None
    hypothetical_exit_spread: float | None
    hypothetical_gross_pnl_usdt: float | None
    hypothetical_fees_usdt: float | None
    hypothetical_slippage_usdt: float | None
    hypothetical_net_pnl_usdt: float | None
    hold_seconds: int | None
    max_adverse_excursion_z: float | None
    max_favorable_excursion_z: float | None
    max_adverse_excursion_usdt: float | None
    max_favorable_excursion_usdt: float | None
    equal_notional_pnl_usdt: float | None = None
    hedge_ratio_sized_pnl_usdt: float | None = None
    pnl_delta_usdt: float | None = None
    pnl_delta_pct: float | None = None
    note: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {item.name: _json_value(getattr(self, item.name)) for item in fields(self)}


@dataclass(frozen=True)
class CounterfactualExitStudy:
    entry_id: str
    entry_marker_type: str
    pair: str
    timeframe: str
    entry_timestamp: int | float
    entry_side: str | None
    entry_z: float | None
    entry_spread: float | None
    actual_exit_timestamp: int | float | None
    actual_exit_z: float | None
    actual_pnl_usdt: float | None
    results: tuple[CounterfactualExitResult, ...]
    best_policy_by_pnl: str | None = None
    best_policy_by_risk_adjusted_return: str | None = None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "entry_marker_type": self.entry_marker_type,
            "pair": self.pair,
            "timeframe": self.timeframe,
            "entry_timestamp": self.entry_timestamp,
            "entry_side": self.entry_side,
            "entry_z": self.entry_z,
            "entry_spread": self.entry_spread,
            "actual_exit_timestamp": self.actual_exit_timestamp,
            "actual_exit_z": self.actual_exit_z,
            "actual_pnl_usdt": self.actual_pnl_usdt,
            "results": [result.to_dict() for result in self.results],
            "best_policy_by_pnl": self.best_policy_by_pnl,
            "best_policy_by_risk_adjusted_return": self.best_policy_by_risk_adjusted_return,
            "warnings": list(self.warnings),
        }


def build_counterfactual_exit_study(
    *,
    entry_marker: Mapping[str, Any],
    pair: str,
    timeframe: str,
    chart_points: Sequence[Mapping[str, Any]],
    actual_markers: Sequence[Mapping[str, Any]] = (),
    score_rows: Sequence[ReplayMLScoreSnapshot | Mapping[str, Any]] = (),
    config: CounterfactualExitConfig | None = None,
) -> CounterfactualExitStudy:
    """Build one lazy counterfactual study for a resolved entry marker."""

    cfg = config or CounterfactualExitConfig()
    anchor = _entry_anchor(entry_marker, pair=pair, timeframe=timeframe)
    candles = tuple(_normalize_candles(chart_points))
    entry_reference = _entry_reference_candle(anchor, candles)
    post_entry_candles = tuple(candle for candle in candles if candle.timestamp > int(anchor.entry_timestamp))
    actual_exit = _actual_exit_for_entry(anchor, actual_markers)

    warnings: list[str] = []
    if not post_entry_candles:
        warnings.append("No post-entry candles available for counterfactual study.")
    if entry_reference is None:
        warnings.append("Entry reference candle unavailable; PnL estimates may be skipped.")

    results = tuple(
        _simulate_strategy(
            strategy,
            anchor=anchor,
            entry_reference=entry_reference,
            post_entry_candles=post_entry_candles,
            score_rows=score_rows,
            config=cfg,
        )
        for strategy in ALL_COUNTERFACTUAL_EXIT_STRATEGIES
    )
    return CounterfactualExitStudy(
        entry_id=anchor.entry_id,
        entry_marker_type=anchor.entry_marker_type,
        pair=anchor.pair,
        timeframe=anchor.timeframe,
        entry_timestamp=anchor.entry_timestamp,
        entry_side=anchor.entry_side,
        entry_z=anchor.entry_z,
        entry_spread=anchor.entry_spread,
        actual_exit_timestamp=_optional_int_timestamp(_get_any(actual_exit, "timestamp")) if actual_exit else None,
        actual_exit_z=_optional_float(_get_any(actual_exit, "z_score", "zscore")) if actual_exit else None,
        actual_pnl_usdt=_optional_float(_get_any(actual_exit, "pnl_usdt")) if actual_exit else None,
        results=results,
        best_policy_by_pnl=_best_policy_by_pnl(results),
        best_policy_by_risk_adjusted_return=_best_policy_by_risk_adjusted_return(results),
        warnings=tuple(warnings),
    )


def _simulate_strategy(
    strategy: CounterfactualExitStrategy,
    *,
    anchor: _EntryAnchor,
    entry_reference: _CounterfactualCandle | None,
    post_entry_candles: tuple[_CounterfactualCandle, ...],
    score_rows: Sequence[ReplayMLScoreSnapshot | Mapping[str, Any]],
    config: CounterfactualExitConfig,
) -> CounterfactualExitResult:
    if strategy == CounterfactualExitStrategy.EXIT_AT_Z_0_50:
        exit_candle = _first_candle(post_entry_candles, lambda candle, _prev: candle.z_score is not None and abs(candle.z_score) <= 0.50)
        return _result_for_exit(strategy, anchor, entry_reference, post_entry_candles, exit_candle, config, "Z reverted to 0.50 exit threshold.")
    if strategy == CounterfactualExitStrategy.EXIT_AT_Z_0_35:
        exit_candle = _first_candle(post_entry_candles, lambda candle, _prev: candle.z_score is not None and abs(candle.z_score) <= 0.35)
        return _result_for_exit(strategy, anchor, entry_reference, post_entry_candles, exit_candle, config, "Z reverted to 0.35 exit threshold.")
    if strategy == CounterfactualExitStrategy.EXIT_AT_Z_0_00:
        exit_candle = _first_zero_crossing_candle(anchor, post_entry_candles, allow_touch=True)
        return _result_for_exit(strategy, anchor, entry_reference, post_entry_candles, exit_candle, config, "Z crossed or touched zero.")
    if strategy == CounterfactualExitStrategy.EXIT_ON_MEAN_CROSSING:
        exit_candle = _first_zero_crossing_candle(anchor, post_entry_candles, allow_touch=False)
        return _result_for_exit(strategy, anchor, entry_reference, post_entry_candles, exit_candle, config, "Z crossed through the spread mean from the entry side.")
    if strategy == CounterfactualExitStrategy.EXIT_ON_MAX_HOLD:
        exit_candle = _first_candle(
            post_entry_candles,
            lambda candle, _prev: candle.timestamp - int(anchor.entry_timestamp) >= int(config.max_hold_seconds),
        )
        return _result_for_exit(strategy, anchor, entry_reference, post_entry_candles, exit_candle, config, "Maximum hold duration reached.")
    if strategy == CounterfactualExitStrategy.EXIT_ON_REGIME_BREAK:
        return _advanced_score_result(
            strategy,
            anchor=anchor,
            entry_reference=entry_reference,
            post_entry_candles=post_entry_candles,
            score_rows=score_rows,
            config=config,
            predicate=lambda score: score.break_risk is not None and score.break_risk >= config.regime_break_threshold,
            note="Stored replay score indicated regime break risk.",
        )
    if strategy == CounterfactualExitStrategy.EXIT_ON_EV_MANAGER:
        return _advanced_score_result(
            strategy,
            anchor=anchor,
            entry_reference=entry_reference,
            post_entry_candles=post_entry_candles,
            score_rows=score_rows,
            config=config,
            predicate=lambda score: (
                score.exit_score is not None and score.exit_score >= config.ev_exit_score_threshold
            )
            or (score.ev_hold_value_usdt is not None and score.ev_hold_value_usdt < 0.0),
            note="Stored replay score indicated EV/exit manager pressure.",
        )
    if strategy == CounterfactualExitStrategy.EXIT_ON_MICROSTRUCTURE_STRESS:
        return _advanced_score_result(
            strategy,
            anchor=anchor,
            entry_reference=entry_reference,
            post_entry_candles=post_entry_candles,
            score_rows=score_rows,
            config=config,
            predicate=lambda score: (
                score.microstructure_risk is not None
                and score.microstructure_risk >= config.microstructure_stress_threshold
            ),
            note="Stored replay score indicated microstructure stress.",
        )
    return _unavailable_result(
        strategy,
        anchor,
        "Counterfactual policy is not implemented in the Phase 3 MVP.",
    )


def _advanced_score_result(
    strategy: CounterfactualExitStrategy,
    *,
    anchor: _EntryAnchor,
    entry_reference: _CounterfactualCandle | None,
    post_entry_candles: tuple[_CounterfactualCandle, ...],
    score_rows: Sequence[ReplayMLScoreSnapshot | Mapping[str, Any]],
    config: CounterfactualExitConfig,
    predicate: Any,
    note: str,
) -> CounterfactualExitResult:
    normalized_scores = tuple(_normalize_score_row(row) for row in score_rows)
    post_scores = tuple(
        score
        for score in normalized_scores
        if score is not None and score.timestamp is not None and int(score.timestamp) > int(anchor.entry_timestamp)
    )
    if not post_scores:
        return _unavailable_result(
            strategy,
            anchor,
            "Stored Phase 2.5 score rows unavailable; counterfactual policy skipped.",
        )
    for score in post_scores:
        if predicate(score):
            exit_candle = _first_candle_at_or_after(post_entry_candles, int(score.timestamp or 0))
            if exit_candle is None:
                return _not_triggered_result(
                    strategy,
                    anchor,
                    post_entry_candles,
                    "Stored score triggered after available chart window.",
                    config=config,
                    entry_reference=entry_reference,
                )
            return _result_for_exit(
                strategy,
                anchor,
                entry_reference,
                post_entry_candles,
                exit_candle,
                config,
                note,
                metadata={"score_timestamp": score.timestamp, "score_source": score.score_source.value},
            )
    return _not_triggered_result(
        strategy,
        anchor,
        post_entry_candles,
        "Stored score condition did not trigger within selected chart window.",
        config=config,
        entry_reference=entry_reference,
    )


def _result_for_exit(
    strategy: CounterfactualExitStrategy,
    anchor: _EntryAnchor,
    entry_reference: _CounterfactualCandle | None,
    post_entry_candles: tuple[_CounterfactualCandle, ...],
    exit_candle: _CounterfactualCandle | None,
    config: CounterfactualExitConfig,
    note: str,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> CounterfactualExitResult:
    if exit_candle is None:
        return _not_triggered_result(
            strategy,
            anchor,
            post_entry_candles,
            "Exit condition did not trigger within selected chart window.",
            config=config,
            entry_reference=entry_reference,
        )
    return _build_result(
        strategy,
        CounterfactualExitStatus.TRIGGERED,
        anchor,
        entry_reference,
        post_entry_candles,
        exit_candle,
        config,
        note,
        metadata=metadata,
    )


def _not_triggered_result(
    strategy: CounterfactualExitStrategy,
    anchor: _EntryAnchor,
    post_entry_candles: tuple[_CounterfactualCandle, ...],
    note: str,
    *,
    config: CounterfactualExitConfig,
    entry_reference: _CounterfactualCandle | None,
) -> CounterfactualExitResult:
    if config.force_close_at_window_end and post_entry_candles:
        return _build_result(
            strategy,
            CounterfactualExitStatus.FORCED_CLOSE_AT_WINDOW_END,
            anchor,
            entry_reference,
            post_entry_candles,
            post_entry_candles[-1],
            config,
            "Forced close at selected chart window end for analysis only; strategy condition did not trigger.",
        )
    mae_mfe = _mae_mfe(anchor, entry_reference, post_entry_candles, None)
    return CounterfactualExitResult(
        entry_id=anchor.entry_id,
        exit_strategy=strategy,
        status=CounterfactualExitStatus.NOT_TRIGGERED,
        entry_timestamp=anchor.entry_timestamp,
        entry_side=anchor.entry_side,
        entry_z=anchor.entry_z,
        entry_spread=anchor.entry_spread,
        hypothetical_exit_timestamp=None,
        hypothetical_exit_z=None,
        hypothetical_exit_spread=None,
        hypothetical_gross_pnl_usdt=None,
        hypothetical_fees_usdt=None,
        hypothetical_slippage_usdt=None,
        hypothetical_net_pnl_usdt=None,
        hold_seconds=None,
        max_adverse_excursion_z=mae_mfe["max_adverse_excursion_z"],
        max_favorable_excursion_z=mae_mfe["max_favorable_excursion_z"],
        max_adverse_excursion_usdt=mae_mfe["max_adverse_excursion_usdt"],
        max_favorable_excursion_usdt=mae_mfe["max_favorable_excursion_usdt"],
        note=note,
        metadata={"post_entry_candle_count": len(post_entry_candles)},
    )


def _unavailable_result(
    strategy: CounterfactualExitStrategy,
    anchor: _EntryAnchor,
    note: str,
) -> CounterfactualExitResult:
    return CounterfactualExitResult(
        entry_id=anchor.entry_id,
        exit_strategy=strategy,
        status=CounterfactualExitStatus.UNAVAILABLE,
        entry_timestamp=anchor.entry_timestamp,
        entry_side=anchor.entry_side,
        entry_z=anchor.entry_z,
        entry_spread=anchor.entry_spread,
        hypothetical_exit_timestamp=None,
        hypothetical_exit_z=None,
        hypothetical_exit_spread=None,
        hypothetical_gross_pnl_usdt=None,
        hypothetical_fees_usdt=None,
        hypothetical_slippage_usdt=None,
        hypothetical_net_pnl_usdt=None,
        hold_seconds=None,
        max_adverse_excursion_z=None,
        max_favorable_excursion_z=None,
        max_adverse_excursion_usdt=None,
        max_favorable_excursion_usdt=None,
        note=note,
    )


def _build_result(
    strategy: CounterfactualExitStrategy,
    status: CounterfactualExitStatus,
    anchor: _EntryAnchor,
    entry_reference: _CounterfactualCandle | None,
    post_entry_candles: tuple[_CounterfactualCandle, ...],
    exit_candle: _CounterfactualCandle,
    config: CounterfactualExitConfig,
    note: str,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> CounterfactualExitResult:
    pnl = _pnl_summary(anchor, entry_reference, exit_candle, config)
    mae_mfe = _mae_mfe(anchor, entry_reference, post_entry_candles, exit_candle)
    notes = [note]
    notes.extend(pnl["notes"])
    result_metadata = {
        "price_source": pnl["price_source"],
        "gross_pair_notional_usdt": pnl["gross_pair_notional_usdt"],
        "selected_leg1_notional_usdt": pnl["selected_leg1_notional_usdt"],
        "selected_leg2_notional_usdt": pnl["selected_leg2_notional_usdt"],
        "post_entry_candle_count": len(post_entry_candles),
    }
    if metadata:
        result_metadata.update(metadata)
    return CounterfactualExitResult(
        entry_id=anchor.entry_id,
        exit_strategy=strategy,
        status=status,
        entry_timestamp=anchor.entry_timestamp,
        entry_side=anchor.entry_side,
        entry_z=anchor.entry_z,
        entry_spread=anchor.entry_spread,
        hypothetical_exit_timestamp=exit_candle.timestamp,
        hypothetical_exit_z=exit_candle.z_score,
        hypothetical_exit_spread=exit_candle.spread,
        hypothetical_gross_pnl_usdt=pnl["gross_pnl"],
        hypothetical_fees_usdt=pnl["fees"],
        hypothetical_slippage_usdt=pnl["slippage"],
        hypothetical_net_pnl_usdt=pnl["net_pnl"],
        hold_seconds=max(int(exit_candle.timestamp - int(anchor.entry_timestamp)), 0),
        max_adverse_excursion_z=mae_mfe["max_adverse_excursion_z"],
        max_favorable_excursion_z=mae_mfe["max_favorable_excursion_z"],
        max_adverse_excursion_usdt=mae_mfe["max_adverse_excursion_usdt"],
        max_favorable_excursion_usdt=mae_mfe["max_favorable_excursion_usdt"],
        equal_notional_pnl_usdt=pnl["equal_notional_pnl"],
        hedge_ratio_sized_pnl_usdt=pnl["hedge_ratio_sized_pnl"],
        pnl_delta_usdt=pnl["pnl_delta"],
        pnl_delta_pct=pnl["pnl_delta_pct"],
        note=" ".join(item for item in notes if item),
        metadata={key: value for key, value in result_metadata.items() if value is not None},
    )


def _pnl_summary(
    anchor: _EntryAnchor,
    entry_reference: _CounterfactualCandle | None,
    exit_candle: _CounterfactualCandle,
    config: CounterfactualExitConfig,
) -> dict[str, Any]:
    sizing = _sizing(anchor.metadata)
    notes: list[str] = []
    if sizing["hedge_ratio"] is None:
        notes.append("Hedge ratio unavailable; sizing comparison skipped.")
    if entry_reference is None or not _has_prices(entry_reference) or not _has_prices(exit_candle):
        notes.append("Raw leg prices unavailable; PnL estimate skipped.")
        return {
            "gross_pnl": None,
            "fees": None,
            "slippage": None,
            "net_pnl": None,
            "equal_notional_pnl": None,
            "hedge_ratio_sized_pnl": None,
            "pnl_delta": None,
            "pnl_delta_pct": None,
            "notes": notes,
            "price_source": "unavailable",
            **sizing,
        }
    if sizing["gross_pair_notional_usdt"] is None:
        notes.append("Gross notional unavailable; PnL estimate skipped.")
        return {
            "gross_pnl": None,
            "fees": None,
            "slippage": None,
            "net_pnl": None,
            "equal_notional_pnl": None,
            "hedge_ratio_sized_pnl": None,
            "pnl_delta": None,
            "pnl_delta_pct": None,
            "notes": notes,
            "price_source": _price_source(anchor, entry_reference),
            **sizing,
        }

    selected_leg1 = sizing["selected_leg1_notional_usdt"]
    selected_leg2 = sizing["selected_leg2_notional_usdt"]
    gross = sizing["gross_pair_notional_usdt"]
    if selected_leg1 is None or selected_leg2 is None:
        selected_leg1 = gross / 2.0
        selected_leg2 = gross / 2.0

    gross_pnl = _gross_pnl(
        anchor.entry_side,
        entry_reference.price_1,
        exit_candle.price_1,
        entry_reference.price_2,
        exit_candle.price_2,
        selected_leg1,
        selected_leg2,
    )
    fees = gross * 2.0 * max(config.fee_bps, 0.0) / 10_000.0
    slippage = gross * 2.0 * max(config.slippage_bps, 0.0) / 10_000.0
    equal_notional_pnl = _gross_pnl(
        anchor.entry_side,
        entry_reference.price_1,
        exit_candle.price_1,
        entry_reference.price_2,
        exit_candle.price_2,
        gross / 2.0,
        gross / 2.0,
    )
    hedge_ratio_sized_pnl = None
    pnl_delta = None
    pnl_delta_pct = None
    hedge_ratio = sizing["hedge_ratio"]
    if hedge_ratio is not None:
        beta = abs(float(hedge_ratio))
        leg1 = gross / (1.0 + beta)
        leg2 = gross * beta / (1.0 + beta)
        hedge_ratio_sized_pnl = _gross_pnl(
            anchor.entry_side,
            entry_reference.price_1,
            exit_candle.price_1,
            entry_reference.price_2,
            exit_candle.price_2,
            leg1,
            leg2,
        )
        pnl_delta = hedge_ratio_sized_pnl - equal_notional_pnl
        pnl_delta_pct = pnl_delta / max(abs(equal_notional_pnl), 1e-9)

    return {
        "gross_pnl": gross_pnl,
        "fees": fees,
        "slippage": slippage,
        "net_pnl": gross_pnl - fees - slippage,
        "equal_notional_pnl": equal_notional_pnl,
        "hedge_ratio_sized_pnl": hedge_ratio_sized_pnl,
        "pnl_delta": pnl_delta,
        "pnl_delta_pct": pnl_delta_pct,
        "notes": notes,
        "price_source": _price_source(anchor, entry_reference),
        **sizing,
    }


def _mae_mfe(
    anchor: _EntryAnchor,
    entry_reference: _CounterfactualCandle | None,
    post_entry_candles: tuple[_CounterfactualCandle, ...],
    exit_candle: _CounterfactualCandle | None,
) -> dict[str, float | None]:
    if exit_candle is not None:
        path = tuple(candle for candle in post_entry_candles if candle.timestamp <= exit_candle.timestamp)
    else:
        path = post_entry_candles
    z_values = [candle.z_score for candle in path if candle.z_score is not None]
    adverse_z = None
    favorable_z = None
    if anchor.entry_z is not None and z_values:
        if anchor.entry_side == BUY_SPREAD:
            adverse_z = min(z_values) - anchor.entry_z
            favorable_z = max(z_values) - anchor.entry_z
        else:
            adverse_z = max(z_values) - anchor.entry_z
            favorable_z = min(z_values) - anchor.entry_z

    pnl_values: list[float] = []
    for candle in path:
        summary = _pnl_summary(anchor, entry_reference, candle, CounterfactualExitConfig())
        value = summary.get("gross_pnl")
        if value is not None:
            pnl_values.append(float(value))
    return {
        "max_adverse_excursion_z": adverse_z,
        "max_favorable_excursion_z": favorable_z,
        "max_adverse_excursion_usdt": min(pnl_values) if pnl_values else None,
        "max_favorable_excursion_usdt": max(pnl_values) if pnl_values else None,
    }


def _gross_pnl(
    side: str | None,
    entry_p1: float | None,
    exit_p1: float | None,
    entry_p2: float | None,
    exit_p2: float | None,
    leg1_notional: float,
    leg2_notional: float,
) -> float:
    if not all(_is_positive(value) for value in (entry_p1, exit_p1, entry_p2, exit_p2)):
        raise ValueError("raw leg prices must be positive for PnL calculation")
    ret_1 = math.log(float(exit_p1) / float(entry_p1))
    ret_2 = math.log(float(exit_p2) / float(entry_p2))
    if side == BUY_SPREAD:
        return float(leg1_notional) * ret_1 - float(leg2_notional) * ret_2
    if side == SELL_SPREAD:
        return -float(leg1_notional) * ret_1 + float(leg2_notional) * ret_2
    return 0.0


def _entry_anchor(marker: Mapping[str, Any], *, pair: str, timeframe: str) -> _EntryAnchor:
    marker_type = str(marker.get("marker_type") or "").strip()
    if marker_type not in {"actual_entry", "replay_entry_candidate"}:
        raise ValueError("counterfactual entry_id must resolve to actual_entry or replay_entry_candidate")
    entry_id = str(marker.get("entry_id") or "").strip()
    if not entry_id:
        raise ValueError("counterfactual entry marker is missing entry_id")
    timestamp = _coerce_timestamp(
        marker.get("original_event_timestamp") if marker_type == "actual_entry" else None
    )
    if timestamp is None:
        timestamp = _coerce_timestamp(marker.get("timestamp"))
    if timestamp is None:
        raise ValueError("counterfactual entry marker is missing a valid timestamp")
    side = _normalize_side(marker.get("side"), marker.get("z_score"))
    if side is None:
        raise ValueError("counterfactual entry marker is missing side")
    metadata = marker.get("metadata")
    return _EntryAnchor(
        entry_id=entry_id,
        entry_marker_type=marker_type,
        pair=pair,
        timeframe=timeframe,
        entry_timestamp=timestamp,
        entry_side=side,
        entry_z=_optional_float(marker.get("z_score")),
        entry_spread=_optional_float(marker.get("spread")),
        trade_id=_normalize_text(marker.get("trade_id")),
        metadata=metadata if isinstance(metadata, Mapping) else {},
    )


def _normalize_candles(points: Sequence[Mapping[str, Any]]) -> list[_CounterfactualCandle]:
    candles: list[_CounterfactualCandle] = []
    for point in points:
        timestamp = _optional_int_timestamp(_get_any(point, "timestamp", "ts"))
        if timestamp is None:
            continue
        candles.append(
            _CounterfactualCandle(
                timestamp=timestamp,
                z_score=_optional_float(_get_any(point, "zscore", "z_score")),
                spread=_optional_float(_get_any(point, "spread")),
                spread_mean=_optional_float(_get_any(point, "spread_mean")),
                price_1=_optional_float(_get_any(point, "price_1", "close_1")),
                price_2=_optional_float(_get_any(point, "price_2", "close_2")),
            )
        )
    return sorted(candles, key=lambda candle: candle.timestamp)


def _entry_reference_candle(
    anchor: _EntryAnchor,
    candles: tuple[_CounterfactualCandle, ...],
) -> _CounterfactualCandle | None:
    entry_price_1 = _optional_float(
        _get_any(anchor.metadata, "entry_price_1", "leg1_entry_price", "price_1")
    )
    entry_price_2 = _optional_float(
        _get_any(anchor.metadata, "entry_price_2", "leg2_entry_price", "price_2")
    )
    if entry_price_1 is not None and entry_price_2 is not None:
        return _CounterfactualCandle(
            timestamp=int(anchor.entry_timestamp),
            z_score=anchor.entry_z,
            spread=anchor.entry_spread,
            price_1=entry_price_1,
            price_2=entry_price_2,
        )
    exact = next((candle for candle in candles if candle.timestamp == int(anchor.entry_timestamp)), None)
    if exact is not None:
        return exact
    return next((candle for candle in candles if candle.timestamp > int(anchor.entry_timestamp)), None)


def _price_source(anchor: _EntryAnchor, entry_reference: _CounterfactualCandle | None) -> str | None:
    if entry_reference is None:
        return None
    if _get_any(anchor.metadata, "entry_price_1", "leg1_entry_price", "price_1") is not None and _get_any(
        anchor.metadata,
        "entry_price_2",
        "leg2_entry_price",
        "price_2",
    ) is not None:
        return "exact_trade_price"
    if entry_reference.timestamp == int(anchor.entry_timestamp):
        return "entry_candle"
    return "candle_approximation"


def _first_candle(
    candles: tuple[_CounterfactualCandle, ...],
    predicate: Any,
) -> _CounterfactualCandle | None:
    previous = None
    for candle in candles:
        if predicate(candle, previous):
            return candle
        previous = candle
    return None


def _first_zero_crossing_candle(
    anchor: _EntryAnchor,
    candles: tuple[_CounterfactualCandle, ...],
    *,
    allow_touch: bool,
) -> _CounterfactualCandle | None:
    previous_z = anchor.entry_z
    for candle in candles:
        z_score = candle.z_score
        if z_score is None:
            continue
        if anchor.entry_side == BUY_SPREAD:
            if allow_touch and z_score >= 0.0:
                return candle
            if previous_z is not None and previous_z < 0.0 and z_score > 0.0:
                return candle
        if anchor.entry_side == SELL_SPREAD:
            if allow_touch and z_score <= 0.0:
                return candle
            if previous_z is not None and previous_z > 0.0 and z_score < 0.0:
                return candle
        previous_z = z_score
    return None


def _first_candle_at_or_after(
    candles: tuple[_CounterfactualCandle, ...],
    timestamp: int,
) -> _CounterfactualCandle | None:
    return next((candle for candle in candles if candle.timestamp >= timestamp), None)


def _actual_exit_for_entry(anchor: _EntryAnchor, actual_markers: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    if anchor.entry_marker_type != "actual_entry":
        return None
    candidates = []
    for marker in actual_markers:
        marker_type = str(marker.get("marker_type") or "")
        if marker_type not in {"actual_exit", "actual_regime_exit", "actual_manual_exit"}:
            continue
        if anchor.trade_id and str(marker.get("trade_id") or "") != anchor.trade_id:
            continue
        timestamp = _coerce_timestamp(marker.get("timestamp"))
        if timestamp is None or timestamp < anchor.entry_timestamp:
            continue
        candidates.append((timestamp, marker))
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def _normalize_score_row(row: ReplayMLScoreSnapshot | Mapping[str, Any]) -> ReplayMLScoreSnapshot | None:
    if isinstance(row, ReplayMLScoreSnapshot):
        return row
    if isinstance(row, Mapping):
        try:
            return ReplayMLScoreSnapshot(
                pair=row.get("pair"),
                timestamp=row.get("timestamp"),
                score_source=row.get("score_source") or "stored_live",
                hard_validation_valid=row.get("hard_validation_valid"),
                regime_name=row.get("regime_name") or row.get("regime"),
                regime_confidence=row.get("regime_confidence"),
                break_risk=row.get("break_risk"),
                bayesian_posterior=row.get("bayesian_posterior"),
                bayesian_quality_grade=row.get("bayesian_quality_grade"),
                final_rank_score=row.get("final_rank_score"),
                microstructure_risk=row.get("microstructure_risk"),
                liquidity_score=row.get("liquidity_score"),
                ev_hold_value_usdt=row.get("ev_hold_value_usdt"),
                exit_score=row.get("exit_score"),
                quality_gate_passed=row.get("quality_gate_passed"),
            )
        except (TypeError, ValueError):
            return None
    return None


def _sizing(metadata: Mapping[str, Any]) -> dict[str, float | None]:
    target_leg1 = _optional_float(_get_any(metadata, "target_leg1_notional_usdt"))
    target_leg2 = _optional_float(_get_any(metadata, "target_leg2_notional_usdt"))
    actual_leg1 = _optional_float(_get_any(metadata, "actual_leg1_notional_usdt"))
    actual_leg2 = _optional_float(_get_any(metadata, "actual_leg2_notional_usdt"))
    gross = _optional_float(
        _get_any(metadata, "target_gross_pair_notional_usdt", "gross_pair_notional_usdt")
    )
    if gross is None and target_leg1 is not None and target_leg2 is not None:
        gross = target_leg1 + target_leg2
    if gross is None and actual_leg1 is not None and actual_leg2 is not None:
        gross = actual_leg1 + actual_leg2
    return {
        "gross_pair_notional_usdt": gross,
        "selected_leg1_notional_usdt": target_leg1 or actual_leg1,
        "selected_leg2_notional_usdt": target_leg2 or actual_leg2,
        "hedge_ratio": _optional_float(
            _get_any(metadata, "entry_hedge_ratio", "hedge_ratio_at_t", "hedge_ratio")
        ),
    }


def _best_policy_by_pnl(results: tuple[CounterfactualExitResult, ...]) -> str | None:
    candidates = [
        result
        for result in results
        if result.status == CounterfactualExitStatus.TRIGGERED
        and result.hypothetical_net_pnl_usdt is not None
    ]
    if not candidates:
        return None
    return str(max(candidates, key=lambda item: float(item.hypothetical_net_pnl_usdt or 0.0)).exit_strategy.value)


def _best_policy_by_risk_adjusted_return(results: tuple[CounterfactualExitResult, ...]) -> str | None:
    scored: list[tuple[float, CounterfactualExitResult]] = []
    for result in results:
        if result.status != CounterfactualExitStatus.TRIGGERED or result.hypothetical_net_pnl_usdt is None:
            continue
        adverse = abs(float(result.max_adverse_excursion_usdt or 0.0))
        scored.append((float(result.hypothetical_net_pnl_usdt) / max(adverse, 1.0), result))
    if not scored:
        return None
    return str(max(scored, key=lambda item: item[0])[1].exit_strategy.value)


def _has_prices(candle: _CounterfactualCandle) -> bool:
    return _is_positive(candle.price_1) and _is_positive(candle.price_2)


def _is_positive(value: Any) -> bool:
    parsed = _optional_float(value)
    return parsed is not None and parsed > 0.0


def _normalize_side(value: Any, z_score: Any = None) -> str | None:
    text = _normalize_text(value)
    if text:
        normalized = text.upper()
        if normalized in {"BUY", "LONG", "LONG_SPREAD", "BUY_SPREAD", "POSITIVE"}:
            return BUY_SPREAD
        if normalized in {"SELL", "SHORT", "SHORT_SPREAD", "SELL_SPREAD", "NEGATIVE"}:
            return SELL_SPREAD
    parsed_z = _optional_float(z_score)
    if parsed_z is not None:
        return BUY_SPREAD if parsed_z < 0 else SELL_SPREAD
    return None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _optional_int_timestamp(value: Any) -> int | None:
    timestamp = _coerce_timestamp(value)
    return int(timestamp) if timestamp is not None else None


def _coerce_timestamp(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt_value = value
        if dt_value.tzinfo is None:
            dt_value = dt_value.replace(tzinfo=timezone.utc)
        return float(dt_value.timestamp())
    if isinstance(value, (int, float)):
        parsed = float(value)
        if not math.isfinite(parsed):
            return None
        if parsed > 10_000_000_000:
            parsed /= 1000.0
        return parsed
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        try:
            parsed_dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return _coerce_timestamp(parsed_dt)
    if not math.isfinite(parsed):
        return None
    if parsed > 10_000_000_000:
        parsed /= 1000.0
    return parsed


def _get_any(record: Any, *keys: str) -> Any:
    for key in keys:
        if isinstance(record, Mapping) and key in record:
            return record[key]
        if not isinstance(record, Mapping) and hasattr(record, key):
            return getattr(record, key)
    return None


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


__all__ = [
    "ALL_COUNTERFACTUAL_EXIT_STRATEGIES",
    "CounterfactualExitConfig",
    "CounterfactualExitResult",
    "CounterfactualExitStatus",
    "CounterfactualExitStrategy",
    "CounterfactualExitStudy",
    "build_counterfactual_exit_study",
]
