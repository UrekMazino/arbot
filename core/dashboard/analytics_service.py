"""Read-only Analytics Dashboard aggregation service."""

from __future__ import annotations

import copy
import time
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.dashboard.contracts import DashboardCacheMeta
from core.dashboard.pair_history_service import (
    HIGH_HEDGE_DRIFT_THRESHOLD,
    _average,
    _coerce_timestamp,
    _finite_float,
    _first_not_none,
    _get_any,
    _hold_seconds,
    _max_drawdown_from_trades,
    _normalize_pair,
    _payload,
    _platform_database_bundle,
    _timestamp_to_datetime,
    _trade_metadata_float,
    _trade_timestamp,
)
from core.dashboard.portfolio_service import build_daily_pnl, build_drawdown_curve, build_equity_curve


ANALYTICS_CACHE_TTL_SECONDS = 900


@dataclass(frozen=True)
class AnalyticsDataBundle:
    trades: tuple[Any, ...] = ()
    equity_snapshots: tuple[Any, ...] = ()
    pair_history_rows: tuple[Mapping[str, Any], ...] = ()
    exit_orchestrator_events: tuple[Any, ...] = ()
    counterfactual_records: tuple[Any, ...] = ()
    ml_score_records: tuple[Any, ...] = ()
    hedge_records: tuple[Any, ...] = ()


_CACHE: dict[tuple[int | None, int | None], tuple[float, dict[str, Any]]] = {}


def get_analytics_dashboard(
    start_ts: int | float | datetime | str | None = None,
    end_ts: int | float | datetime | str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Return a JSON-safe strategy-wide analytics dashboard payload."""

    start_value = _coerce_timestamp(start_ts)
    end_value = _coerce_timestamp(end_ts)
    cache_key = (start_value, end_value)
    now = time.time()

    if not refresh:
        cached = _CACHE.get(cache_key)
        if cached is not None:
            expires_at, payload = cached
            if now < expires_at:
                result = copy.deepcopy(payload)
                result["cache"]["cache_hit"] = True
                return result

    payload = _compute_analytics_dashboard(
        start_ts=start_value,
        end_ts=end_value,
        generated_at=now,
        ttl_seconds=ANALYTICS_CACHE_TTL_SECONDS,
    )
    _CACHE[cache_key] = (now + ANALYTICS_CACHE_TTL_SECONDS, copy.deepcopy(payload))
    return payload


def clear_analytics_cache() -> None:
    _CACHE.clear()


def compute_performance_metrics(
    *,
    trades: Sequence[Any] = (),
    drawdown_curve: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    pnl_values = [_finite_float(_get_any(trade, "pnl_usdt", "pnl")) for trade in trades]
    pnl_values = [value for value in pnl_values if value is not None]
    wins = [value for value in pnl_values if value > 0]
    losses = [value for value in pnl_values if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    hold_values = [_hold_seconds(trade) for trade in trades]
    drawdowns = [_finite_float(point.get("drawdown_usdt")) for point in drawdown_curve]
    drawdowns = [value for value in drawdowns if value is not None]

    realized = sum(pnl_values) if pnl_values else None
    return {
        "total_pnl_usdt": realized,
        "realized_pnl_usdt": realized,
        "unrealized_pnl_usdt": None,
        "win_rate": (len(wins) / len(pnl_values)) if pnl_values else None,
        "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else None,
        "average_win_usdt": _average(wins),
        "average_loss_usdt": _average(losses),
        "max_drawdown_usdt": min(drawdowns) if drawdowns else _max_drawdown_from_trades(trades),
        "trade_count": len(trades) if trades else None,
        "avg_hold_seconds": _average(value for value in hold_values if value is not None),
    }


def build_pnl_timeseries(*, trades: Sequence[Any] = (), equity_snapshots: Sequence[Any] = ()) -> dict[str, Any]:
    equity_curve = build_equity_curve(equity_snapshots)
    return {
        "daily_pnl": build_daily_pnl(trades),
        "equity_curve": equity_curve,
        "drawdown_curve": build_drawdown_curve(equity_curve),
    }


def build_pair_leaderboards(pair_history_rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    rows = [dict(row) for row in pair_history_rows]
    return {
        "top_pairs_by_pnl": _top_rows(rows, "net_pnl_usdt", reverse=True),
        "bottom_pairs_by_pnl": _top_rows(rows, "net_pnl_usdt", reverse=False),
        "top_pairs_by_win_rate": _top_rows(rows, "win_rate", reverse=True),
        "worst_pairs_by_drawdown": _top_rows(rows, "max_drawdown_usdt", reverse=False),
        "pairs_with_high_hedge_drift": _high_hedge_drift_rows(rows),
        "pairs_with_frequent_blocks": _frequent_block_rows(rows),
    }


def build_exit_analysis(
    *,
    exit_orchestrator_events: Sequence[Any] = (),
    counterfactual_records: Sequence[Any] = (),
) -> dict[str, Any]:
    distribution: Counter[str] = Counter()
    for event in exit_orchestrator_events:
        payload = _payload(event)
        policy = _normalize_text(
            _first_not_none(
                _get_any(event, "exit_policy", "policy", "source", "action"),
                payload.get("exit_policy"),
                payload.get("policy"),
                payload.get("source"),
                payload.get("action"),
            )
        )
        if policy:
            distribution[policy] += 1

    return {
        "best_counterfactual_exit_policy": _best_counterfactual_policy(counterfactual_records),
        "actual_exit_efficiency": _average_record_field(counterfactual_records, "actual_exit_efficiency"),
        "avg_missed_profit_usdt": _average_record_field(counterfactual_records, "avg_missed_profit_usdt", "missed_profit_usdt"),
        "avg_avoided_loss_usdt": _average_record_field(counterfactual_records, "avg_avoided_loss_usdt", "avoided_loss_usdt"),
        "exit_policy_distribution": dict(distribution),
    }


def build_ml_analysis(*, trades: Sequence[Any] = (), ml_score_records: Sequence[Any] = ()) -> dict[str, Any]:
    if not ml_score_records:
        return {
            "pnl_by_regime": [],
            "win_rate_by_regime": [],
            "bayesian_posterior_vs_outcome": [],
            "final_rank_score_vs_outcome": [],
            "break_risk_before_losses": None,
            "microstructure_risk_vs_slippage": [],
        }

    by_regime: dict[str, list[float]] = defaultdict(list)
    wins_by_regime: dict[str, list[float]] = defaultdict(list)
    bayesian_rows: list[dict[str, Any]] = []
    rank_rows: list[dict[str, Any]] = []
    micro_rows: list[dict[str, Any]] = []
    break_risks_before_losses: list[float] = []

    latest_break_risk = _latest_score_value(ml_score_records, "break_risk")
    for trade in trades:
        pnl = _finite_float(_get_any(trade, "pnl_usdt", "pnl"))
        payload = _payload(trade)
        regime = _normalize_text(
            _first_not_none(
                _get_any(trade, "entry_regime", "regime"),
                payload.get("regime_at_entry"),
                payload.get("regime_name"),
            )
        )
        if regime and pnl is not None:
            by_regime[regime].append(pnl)
            wins_by_regime[regime].append(1.0 if pnl > 0 else 0.0)
        posterior = _record_float(trade, "bayesian_posterior_at_entry", "bayesian_posterior")
        if posterior is not None and pnl is not None:
            bayesian_rows.append({"bayesian_posterior": posterior, "pnl_usdt": pnl, "won": pnl > 0})
        rank = _record_float(trade, "final_rank_score_at_entry", "final_rank_score")
        if rank is not None and pnl is not None:
            rank_rows.append({"final_rank_score": rank, "pnl_usdt": pnl, "won": pnl > 0})
        micro = _record_float(trade, "microstructure_risk")
        slippage = _record_float(trade, "slippage_usdt")
        if micro is not None and slippage is not None:
            micro_rows.append({"microstructure_risk": micro, "slippage_usdt": slippage})
        if pnl is not None and pnl < 0 and latest_break_risk is not None:
            break_risks_before_losses.append(latest_break_risk)

    return {
        "pnl_by_regime": [
            {"regime": regime, "pnl_usdt": sum(values), "trade_count": len(values)}
            for regime, values in sorted(by_regime.items())
        ],
        "win_rate_by_regime": [
            {"regime": regime, "win_rate": _average(values), "trade_count": len(values)}
            for regime, values in sorted(wins_by_regime.items())
        ],
        "bayesian_posterior_vs_outcome": bayesian_rows,
        "final_rank_score_vs_outcome": rank_rows,
        "break_risk_before_losses": _average(break_risks_before_losses),
        "microstructure_risk_vs_slippage": micro_rows,
    }


def build_hedge_analysis(
    *,
    trades: Sequence[Any] = (),
    hedge_records: Sequence[Any] = (),
    counterfactual_records: Sequence[Any] = (),
) -> dict[str, Any]:
    records = tuple(hedge_records) + tuple(counterfactual_records)
    drift_values = [_trade_metadata_float(trade, "hedge_ratio_drift_pct") for trade in trades]
    drift_values = [value for value in drift_values if value is not None]
    return {
        "equal_notional_total_pnl": _sum_record_field(records, "equal_notional_total_pnl", "equal_notional_pnl_usdt"),
        "hedge_ratio_sized_total_pnl": _sum_record_field(records, "hedge_ratio_sized_total_pnl", "hedge_ratio_sized_pnl_usdt"),
        "sizing_pnl_delta_usdt": _sum_record_field(records, "sizing_pnl_delta_usdt", "pnl_delta_usdt"),
        "high_drift_trade_count": sum(1 for value in drift_values if value >= HIGH_HEDGE_DRIFT_THRESHOLD) if drift_values else None,
    }


def _compute_analytics_dashboard(
    *,
    start_ts: int | None,
    end_ts: int | None,
    generated_at: float,
    ttl_seconds: int,
) -> dict[str, Any]:
    bundle = _load_analytics_data(start_ts=start_ts, end_ts=end_ts)
    pnl_timeseries = build_pnl_timeseries(trades=bundle.trades, equity_snapshots=bundle.equity_snapshots)
    pair_rows = tuple(bundle.pair_history_rows) or _pair_history_rows_from_trades(bundle.trades)
    return {
        "performance": compute_performance_metrics(
            trades=bundle.trades,
            drawdown_curve=pnl_timeseries["drawdown_curve"],
        ),
        "pnl_timeseries": pnl_timeseries,
        "pair_leaderboards": build_pair_leaderboards(pair_rows),
        "exit_analysis": build_exit_analysis(
            exit_orchestrator_events=bundle.exit_orchestrator_events,
            counterfactual_records=bundle.counterfactual_records,
        ),
        "ml_analysis": build_ml_analysis(
            trades=bundle.trades,
            ml_score_records=bundle.ml_score_records,
        ),
        "hedge_analysis": build_hedge_analysis(
            trades=bundle.trades,
            hedge_records=bundle.hedge_records,
            counterfactual_records=bundle.counterfactual_records,
        ),
        "cache": DashboardCacheMeta(
            cache_hit=False,
            generated_at=generated_at,
            ttl_seconds=ttl_seconds,
            refresh_supported=True,
        ).to_dict(),
    }


def _load_analytics_data(start_ts: int | None, end_ts: int | None) -> AnalyticsDataBundle:
    try:
        SessionLocal, models, select, or_ = _platform_database_bundle()
    except Exception:
        return AnalyticsDataBundle()

    db = SessionLocal()
    try:
        Trade = models.Trade
        EquitySnapshot = models.EquitySnapshot
        RunEvent = models.RunEvent
        start_dt = _timestamp_to_datetime(start_ts)
        end_dt = _timestamp_to_datetime(end_ts)

        trade_stmt = select(Trade)
        if start_dt is not None and end_dt is not None:
            trade_stmt = trade_stmt.where(or_(Trade.entry_ts.between(start_dt, end_dt), Trade.exit_ts.between(start_dt, end_dt)))
        elif start_dt is not None:
            trade_stmt = trade_stmt.where(or_(Trade.entry_ts >= start_dt, Trade.exit_ts >= start_dt))
        elif end_dt is not None:
            trade_stmt = trade_stmt.where(or_(Trade.entry_ts <= end_dt, Trade.exit_ts <= end_dt))

        equity_stmt = select(EquitySnapshot)
        event_stmt = select(RunEvent)
        if start_dt is not None:
            equity_stmt = equity_stmt.where(EquitySnapshot.ts >= start_dt)
            event_stmt = event_stmt.where(RunEvent.ts >= start_dt)
        if end_dt is not None:
            equity_stmt = equity_stmt.where(EquitySnapshot.ts <= end_dt)
            event_stmt = event_stmt.where(RunEvent.ts <= end_dt)

        events = tuple(db.execute(event_stmt).scalars().all())
        return AnalyticsDataBundle(
            trades=tuple(db.execute(trade_stmt).scalars().all()),
            equity_snapshots=tuple(db.execute(equity_stmt).scalars().all()),
            pair_history_rows=_load_pair_history_rows(start_ts=start_ts, end_ts=end_ts),
            exit_orchestrator_events=tuple(event for event in events if _is_exit_orchestrator_event(event)),
            counterfactual_records=tuple(event for event in events if _is_counterfactual_record(event)),
            ml_score_records=tuple(event for event in events if _is_stored_ml_score_record(event)),
            hedge_records=tuple(event for event in events if _is_hedge_record(event)),
        )
    except Exception:
        return AnalyticsDataBundle()
    finally:
        try:
            db.close()
        except Exception:
            pass


def _load_pair_history_rows(start_ts: int | None, end_ts: int | None) -> tuple[Mapping[str, Any], ...]:
    try:
        from core.dashboard.pair_history_service import get_pair_history_summary

        payload = get_pair_history_summary(
            start_ts=start_ts,
            end_ts=end_ts,
            page=1,
            page_size=200,
            sort_by="net_pnl_usdt",
            sort_dir="desc",
            refresh=True,
        )
        rows = payload.get("rows") if isinstance(payload, Mapping) else None
        return tuple(row for row in rows or () if isinstance(row, Mapping))
    except Exception:
        return ()


def _pair_history_rows_from_trades(trades: Sequence[Any]) -> tuple[Mapping[str, Any], ...]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for trade in trades:
        pair = _normalize_pair(_get_any(trade, "pair_key", "pair"))
        if pair:
            grouped[pair].append(trade)

    rows: list[Mapping[str, Any]] = []
    for pair, pair_trades in grouped.items():
        pnl_values = [_finite_float(_get_any(trade, "pnl_usdt", "pnl")) for trade in pair_trades]
        pnl_values = [value for value in pnl_values if value is not None]
        wins = [value for value in pnl_values if value > 0]
        losses = [value for value in pnl_values if value < 0]
        drift_values = [_trade_metadata_float(trade, "hedge_ratio_drift_pct") for trade in pair_trades]
        drift_values = [value for value in drift_values if value is not None]
        rows.append(
            {
                "pair": pair,
                "total_trades": len(pair_trades),
                "net_pnl_usdt": sum(pnl_values) if pnl_values else None,
                "win_rate": (len(wins) / len(pnl_values)) if pnl_values else None,
                "profit_factor": (sum(wins) / abs(sum(losses))) if losses else None,
                "max_drawdown_usdt": _max_drawdown_from_trades(pair_trades),
                "avg_hedge_drift_pct": _average(drift_values),
                "block_reason_counts": {},
            }
        )
    return tuple(rows)


def _top_rows(rows: Sequence[Mapping[str, Any]], key: str, *, reverse: bool, limit: int = 10) -> list[dict[str, Any]]:
    with_values = [row for row in rows if _finite_float(row.get(key)) is not None]
    with_values.sort(key=lambda row: _finite_float(row.get(key)) or 0.0, reverse=reverse)
    return [dict(row) for row in with_values[:limit]]


def _high_hedge_drift_rows(rows: Sequence[Mapping[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    filtered = [
        row
        for row in rows
        if (_finite_float(row.get("avg_hedge_drift_pct")) or 0.0) >= HIGH_HEDGE_DRIFT_THRESHOLD
    ]
    filtered.sort(key=lambda row: _finite_float(row.get("avg_hedge_drift_pct")) or 0.0, reverse=True)
    return [dict(row) for row in filtered[:limit]]


def _frequent_block_rows(rows: Sequence[Mapping[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
    filtered = []
    for row in rows:
        count = _block_count(row.get("block_reason_counts"))
        if count > 0:
            enriched = dict(row)
            enriched["block_count"] = count
            filtered.append(enriched)
    filtered.sort(key=lambda row: int(row.get("block_count") or 0), reverse=True)
    return filtered[:limit]


def _block_count(value: Any) -> int:
    if not isinstance(value, Mapping):
        return 0
    total = 0
    for count in value.values():
        try:
            total += int(count)
        except (TypeError, ValueError):
            continue
    return total


def _best_counterfactual_policy(records: Sequence[Any]) -> str | None:
    policies = [
        _normalize_text(
            _first_not_none(
                _get_any(record, "best_counterfactual_exit_policy", "best_exit_policy", "best_policy_by_pnl"),
                _payload(record).get("best_counterfactual_exit_policy"),
                _payload(record).get("best_exit_policy"),
                _payload(record).get("best_policy_by_pnl"),
            )
        )
        for record in records
    ]
    policies = [policy for policy in policies if policy]
    return Counter(policies).most_common(1)[0][0] if policies else None


def _average_record_field(records: Sequence[Any], *keys: str) -> float | None:
    values = [_record_float(record, *keys) for record in records]
    return _average(value for value in values if value is not None)


def _sum_record_field(records: Sequence[Any], *keys: str) -> float | None:
    values = [_record_float(record, *keys) for record in records]
    values = [value for value in values if value is not None]
    return sum(values) if values else None


def _record_float(record: Any, *keys: str) -> float | None:
    payload = _payload(record)
    metadata = _get_any(record, "metadata")
    for key in keys:
        value = _finite_float(_get_any(record, key))
        if value is not None:
            return value
        value = _finite_float(payload.get(key))
        if value is not None:
            return value
        if isinstance(metadata, Mapping):
            value = _finite_float(metadata.get(key))
            if value is not None:
                return value
    return None


def _latest_score_value(records: Sequence[Any], key: str) -> float | None:
    rows = [(record, _record_timestamp(record)) for record in records]
    rows = [(record, timestamp) for record, timestamp in rows if timestamp is not None]
    rows.sort(key=lambda item: item[1])
    for record, _ in reversed(rows):
        value = _record_float(record, key)
        if value is not None:
            return value
    return None


def _record_timestamp(record: Any) -> int | None:
    return _first_not_none(
        _coerce_timestamp(_get_any(record, "timestamp", "ts")),
        _trade_timestamp(record),
        _coerce_timestamp(_payload(record).get("timestamp") or _payload(record).get("ts")),
    )


def _is_exit_orchestrator_event(record: Any) -> bool:
    event_type = _event_type(record)
    return "exit_orchestrator" in event_type or event_type == "exit_candidate"


def _is_counterfactual_record(record: Any) -> bool:
    event_type = _event_type(record)
    payload = _payload(record)
    return "counterfactual" in event_type or any(
        key in payload
        for key in (
            "best_policy_by_pnl",
            "best_counterfactual_exit_policy",
            "actual_exit_efficiency",
            "missed_profit_usdt",
            "avoided_loss_usdt",
        )
    )


def _is_stored_ml_score_record(record: Any) -> bool:
    event_type = _event_type(record)
    return event_type.startswith("advanced_ml_") or event_type == "trade_quality_gate"


def _is_hedge_record(record: Any) -> bool:
    event_type = _event_type(record)
    payload = _payload(record)
    return "hedge" in event_type or any(
        key in payload
        for key in (
            "equal_notional_pnl_usdt",
            "hedge_ratio_sized_pnl_usdt",
            "sizing_pnl_delta_usdt",
            "pnl_delta_usdt",
        )
    )


def _event_type(record: Any) -> str:
    return str(_first_not_none(_get_any(record, "event_type", "type"), _payload(record).get("event_type")) or "").strip().lower()


def _normalize_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


__all__ = [
    "ANALYTICS_CACHE_TTL_SECONDS",
    "AnalyticsDataBundle",
    "build_exit_analysis",
    "build_hedge_analysis",
    "build_ml_analysis",
    "build_pair_leaderboards",
    "build_pnl_timeseries",
    "clear_analytics_cache",
    "compute_performance_metrics",
    "get_analytics_dashboard",
]
