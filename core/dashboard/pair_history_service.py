"""Read-only Pair History dashboard service."""

from __future__ import annotations

import copy
import json
import math
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from core.dashboard.contracts import DashboardCacheMeta, DashboardTag, PairSummary, TradeSummary


PAIR_HISTORY_CACHE_TTL_SECONDS = 300
MAX_PAGE_SIZE = 200
SIGNIFICANT_PNL_THRESHOLD = 5.0
SIGNIFICANT_TRADE_COUNT_THRESHOLD = 5
SIGNIFICANT_DRAWDOWN_THRESHOLD = 5.0
SIGNIFICANT_TRADE_THRESHOLD = 2.0
HIGH_HEDGE_DRIFT_THRESHOLD = 0.20
HIGH_SLIPPAGE_USDT_THRESHOLD = 1.0

_REPO_ROOT = Path(__file__).resolve().parents[2]
PAIR_STRATEGY_STATE_FILE = _REPO_ROOT / "Execution" / "state" / "pair_strategy_state.json"
GRAVEYARD_TICKERS_FILE = _REPO_ROOT / "Execution" / "state" / "graveyard_tickers.json"


@dataclass(frozen=True)
class PairHistoryDataBundle:
    trades: tuple[Any, ...] = ()
    run_events: tuple[Any, ...] = ()
    pair_state: Mapping[str, Any] | None = None
    graveyard_tickers: frozenset[str] = frozenset()


@dataclass
class _PairAggregate:
    pair: str
    trades: list[Any]
    block_reason_counts: Counter[str]
    status: str | None
    regimes: set[str]


_CACHE: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}


def get_pair_history_summary(
    start_ts: int | float | datetime | str | None = None,
    end_ts: int | float | datetime | str | None = None,
    status: str | None = None,
    pnl_filter: str | None = None,
    min_trade_count: int | str | None = None,
    min_win_rate: float | str | None = None,
    max_win_rate: float | str | None = None,
    regime: str | None = None,
    hedge_drift_filter: str | None = None,
    significant_only: bool = False,
    search: str | None = None,
    sort_by: str = "net_pnl_usdt",
    sort_dir: str = "desc",
    page: int | str = 1,
    page_size: int | str = 50,
    refresh: bool = False,
) -> dict[str, Any]:
    """Return a JSON-safe Pair History response."""

    normalized = _normalize_request(
        start_ts=start_ts,
        end_ts=end_ts,
        status=status,
        pnl_filter=pnl_filter,
        min_trade_count=min_trade_count,
        min_win_rate=min_win_rate,
        max_win_rate=max_win_rate,
        regime=regime,
        hedge_drift_filter=hedge_drift_filter,
        significant_only=significant_only,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
    cache_key = tuple(normalized[key] for key in sorted(normalized))
    now = time.time()

    if not refresh:
        cached = _CACHE.get(cache_key)
        if cached is not None:
            expires_at, payload = cached
            if now < expires_at:
                result = copy.deepcopy(payload)
                result["cache"]["cache_hit"] = True
                return result

    payload = _compute_pair_history_summary(
        generated_at=now,
        ttl_seconds=PAIR_HISTORY_CACHE_TTL_SECONDS,
        **normalized,
    )
    _CACHE[cache_key] = (now + PAIR_HISTORY_CACHE_TTL_SECONDS, copy.deepcopy(payload))
    return payload


def clear_pair_history_cache() -> None:
    _CACHE.clear()


def _compute_pair_history_summary(
    *,
    start_ts: int | None,
    end_ts: int | None,
    status: str | None,
    pnl_filter: str,
    min_trade_count: int | None,
    min_win_rate: float | None,
    max_win_rate: float | None,
    regime: str | None,
    hedge_drift_filter: str,
    significant_only: bool,
    search: str | None,
    sort_by: str,
    sort_dir: str,
    page: int,
    page_size: int,
    generated_at: float,
    ttl_seconds: int,
) -> dict[str, Any]:
    bundle = _load_pair_history_data(start_ts=start_ts, end_ts=end_ts)
    aggregates = _build_pair_aggregates(
        trades=_filter_records_by_timestamp(bundle.trades, start_ts=start_ts, end_ts=end_ts),
        run_events=_filter_records_by_timestamp(bundle.run_events, start_ts=start_ts, end_ts=end_ts),
        pair_state=bundle.pair_state,
        graveyard_tickers=bundle.graveyard_tickers,
    )
    rows = [_row_from_aggregate(aggregate) for aggregate in aggregates.values()]
    rows = _apply_filters(
        rows=rows,
        aggregates=aggregates,
        status=status,
        pnl_filter=pnl_filter,
        min_trade_count=min_trade_count,
        min_win_rate=min_win_rate,
        max_win_rate=max_win_rate,
        regime=regime,
        hedge_drift_filter=hedge_drift_filter,
        significant_only=significant_only,
        search=search,
    )
    rows = _sort_rows(rows, sort_by=sort_by, sort_dir=sort_dir)
    kpis = _build_kpis(rows)
    total_rows = len(rows)
    total_pages = math.ceil(total_rows / page_size) if total_rows else 0
    offset = (page - 1) * page_size
    paged_rows = rows[offset : offset + page_size]
    cache = DashboardCacheMeta(
        cache_hit=False,
        generated_at=generated_at,
        ttl_seconds=ttl_seconds,
        refresh_supported=True,
    )
    return {
        "rows": paged_rows,
        "meta": {
            "page": page,
            "page_size": page_size,
            "total_rows": total_rows,
            "total_pages": total_pages,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
        },
        "kpis": kpis,
        "cache": cache.to_dict(),
    }


def _build_pair_aggregates(
    *,
    trades: Sequence[Any],
    run_events: Sequence[Any],
    pair_state: Mapping[str, Any] | None,
    graveyard_tickers: frozenset[str],
) -> dict[str, _PairAggregate]:
    pairs = {pair for trade in trades if (pair := _normalize_pair(_get_any(trade, "pair_key", "pair")))}
    pairs.update(
        pair
        for event in run_events
        if (pair := _normalize_pair(_payload(event).get("pair") or _payload(event).get("pair_key") or _get_any(event, "pair", "pair_key")))
    )

    aggregates: dict[str, _PairAggregate] = {}
    for pair in sorted(pairs):
        aggregates[pair] = _PairAggregate(
            pair=pair,
            trades=[],
            block_reason_counts=Counter(),
            status=_status_for_pair(pair, pair_state=pair_state, graveyard_tickers=graveyard_tickers),
            regimes=set(),
        )

    for trade in trades:
        pair = _normalize_pair(_get_any(trade, "pair_key", "pair"))
        if not pair:
            continue
        aggregate = aggregates.setdefault(
            pair,
            _PairAggregate(
                pair=pair,
                trades=[],
                block_reason_counts=Counter(),
                status=_status_for_pair(pair, pair_state=pair_state, graveyard_tickers=graveyard_tickers),
                regimes=set(),
            ),
        )
        aggregate.trades.append(trade)
        regime = _normalize_text(_get_any(trade, "entry_regime", "regime") or _payload(trade).get("regime_at_entry"))
        if regime:
            aggregate.regimes.add(regime.lower())

    for event in run_events:
        payload = _payload(event)
        pair = _normalize_pair(payload.get("pair") or payload.get("pair_key") or _get_any(event, "pair", "pair_key"))
        if not pair:
            continue
        aggregate = aggregates.setdefault(
            pair,
            _PairAggregate(
                pair=pair,
                trades=[],
                block_reason_counts=Counter(),
                status=_status_for_pair(pair, pair_state=pair_state, graveyard_tickers=graveyard_tickers),
                regimes=set(),
            ),
        )
        for reason in _extract_block_reasons(event):
            aggregate.block_reason_counts[reason] += 1

    return aggregates


def _row_from_aggregate(aggregate: _PairAggregate) -> dict[str, Any]:
    trades = sorted(
        aggregate.trades,
        key=lambda trade: _trade_timestamp(trade) or 0,
    )
    pnl_values = [_finite_float(_get_any(trade, "pnl_usdt", "pnl")) for trade in trades]
    pnl_values = [value for value in pnl_values if value is not None]
    wins = sum(1 for value in pnl_values if value > 0)
    gross_profit = sum(value for value in pnl_values if value > 0)
    gross_loss = abs(sum(value for value in pnl_values if value < 0))
    best_trade = _best_trade(trades)
    worst_trade = _worst_trade(trades)
    hold_values = [_hold_seconds(trade) for trade in trades]
    entry_z_values = [_finite_float(_get_any(trade, "entry_z")) for trade in trades]
    exit_z_values = [_finite_float(_get_any(trade, "exit_z")) for trade in trades]
    hedge_values = [_trade_metadata_float(trade, "entry_hedge_ratio", "hedge_ratio") for trade in trades]
    drift_values = [_trade_metadata_float(trade, "hedge_ratio_drift_pct") for trade in trades]
    slippage_values = [_trade_metadata_float(trade, "slippage_usdt") for trade in trades]
    avg_hedge_drift = _average(value for value in drift_values if value is not None)
    net_pnl = sum(pnl_values) if pnl_values else None
    max_drawdown = _max_drawdown_from_trades(trades)
    tags = _tags_for_pair(
        status=aggregate.status,
        total_trades=len(trades),
        net_pnl=net_pnl,
        win_rate=(wins / len(pnl_values)) if pnl_values else None,
        profit_factor=(gross_profit / gross_loss) if gross_loss > 0 else None,
        avg_hedge_drift_pct=avg_hedge_drift,
        avg_slippage_usdt=_average(value for value in slippage_values if value is not None),
    )
    summary = PairSummary(
        pair=aggregate.pair,
        status=aggregate.status,
        total_trades=len(trades),
        net_pnl_usdt=net_pnl,
        realized_pnl_usdt=net_pnl,
        unrealized_pnl_usdt=None,
        win_rate=(wins / len(pnl_values)) if pnl_values else None,
        profit_factor=(gross_profit / gross_loss) if gross_loss > 0 else None,
        max_drawdown_usdt=max_drawdown,
        avg_hold_seconds=_average(value for value in hold_values if value is not None),
        avg_entry_z=_average(value for value in entry_z_values if value is not None),
        avg_exit_z=_average(value for value in exit_z_values if value is not None),
        avg_hedge_ratio=_average(value for value in hedge_values if value is not None),
        avg_hedge_drift_pct=avg_hedge_drift,
        hospital_count=1 if aggregate.status == "hospital" else 0 if aggregate.status else None,
        graveyard_count=1 if aggregate.status == "graveyard" else 0 if aggregate.status else None,
        block_reason_counts=dict(aggregate.block_reason_counts),
        best_trade=_trade_summary(best_trade) if best_trade is not None else None,
        worst_trade=_trade_summary(worst_trade) if worst_trade is not None else None,
        last_traded_at=max((_trade_timestamp(trade) or 0 for trade in trades), default=0) or None,
        tags=tags,
    )
    return summary.to_dict()


def _apply_filters(
    *,
    rows: list[dict[str, Any]],
    aggregates: Mapping[str, _PairAggregate],
    status: str | None,
    pnl_filter: str,
    min_trade_count: int | None,
    min_win_rate: float | None,
    max_win_rate: float | None,
    regime: str | None,
    hedge_drift_filter: str,
    significant_only: bool,
    search: str | None,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    regime_text = str(regime or "").strip().lower()
    search_text = str(search or "").strip().lower()
    for row in rows:
        if status and row.get("status") != status:
            continue
        net_pnl = _finite_float(row.get("net_pnl_usdt"))
        if pnl_filter == "winners" and not (net_pnl is not None and net_pnl > 0):
            continue
        if pnl_filter == "losers" and not (net_pnl is not None and net_pnl < 0):
            continue
        if min_trade_count is not None and int(row.get("total_trades") or 0) < min_trade_count:
            continue
        win_rate = _finite_float(row.get("win_rate"))
        if min_win_rate is not None and not (win_rate is not None and win_rate >= min_win_rate):
            continue
        if max_win_rate is not None and not (win_rate is not None and win_rate <= max_win_rate):
            continue
        if regime_text:
            aggregate = aggregates.get(str(row.get("pair") or ""))
            if aggregate is None or regime_text not in aggregate.regimes:
                continue
        if hedge_drift_filter == "high_drift" and DashboardTag.HIGH_DRIFT.value not in set(row.get("tags") or []):
            continue
        if significant_only and not _is_significant(row):
            continue
        if search_text and search_text not in str(row.get("pair") or "").lower():
            continue
        filtered.append(row)
    return filtered


def _sort_rows(rows: list[dict[str, Any]], *, sort_by: str, sort_dir: str) -> list[dict[str, Any]]:
    reverse = sort_dir == "desc"
    with_values: list[dict[str, Any]] = []
    without_values: list[dict[str, Any]] = []
    for row in rows:
        value = _sort_value(row, sort_by)
        (with_values if value is not None else without_values).append(row)
    with_values.sort(key=lambda row: _sort_value(row, sort_by), reverse=reverse)
    without_values.sort(key=lambda row: str(row.get("pair") or ""))
    return with_values + without_values


def _sort_value(row: Mapping[str, Any], sort_by: str) -> Any:
    if sort_by == "best_trade":
        trade = row.get("best_trade")
        return _finite_float(trade.get("pnl_usdt")) if isinstance(trade, Mapping) else None
    if sort_by == "worst_trade":
        trade = row.get("worst_trade")
        return _finite_float(trade.get("pnl_usdt")) if isinstance(trade, Mapping) else None
    return _finite_float(row.get(sort_by)) if sort_by != "last_traded_at" else _coerce_timestamp(row.get(sort_by))


def _build_kpis(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    statuses = [str(row.get("status") or "").lower() for row in rows]
    return {
        "total_pairs": len(rows),
        "tradable_pairs": sum(1 for status in statuses if status in {"stable", "warning"}),
        "profitable_pairs": sum(1 for row in rows if (_finite_float(row.get("net_pnl_usdt")) or 0.0) > 0),
        "losing_pairs": sum(1 for row in rows if (_finite_float(row.get("net_pnl_usdt")) or 0.0) < 0),
        "hospital_pairs": sum(1 for status in statuses if status == "hospital"),
        "graveyard_pairs": sum(1 for status in statuses if status == "graveyard"),
    }


def _normalize_request(**kwargs: Any) -> dict[str, Any]:
    page = _positive_int(kwargs["page"], default=1, minimum=1, maximum=1_000_000)
    page_size = _positive_int(kwargs["page_size"], default=50, minimum=1, maximum=MAX_PAGE_SIZE)
    sort_by = str(kwargs["sort_by"] or "net_pnl_usdt").strip() or "net_pnl_usdt"
    if sort_by not in {
        "net_pnl_usdt",
        "total_trades",
        "win_rate",
        "profit_factor",
        "max_drawdown_usdt",
        "best_trade",
        "worst_trade",
        "avg_hold_seconds",
        "last_traded_at",
        "avg_hedge_drift_pct",
    }:
        sort_by = "net_pnl_usdt"
    sort_dir = str(kwargs["sort_dir"] or "desc").strip().lower()
    if sort_dir not in {"asc", "desc"}:
        sort_dir = "desc"
    pnl_filter = str(kwargs["pnl_filter"] or "all").strip().lower()
    if pnl_filter not in {"all", "winners", "losers"}:
        pnl_filter = "all"
    hedge_drift_filter = str(kwargs["hedge_drift_filter"] or "all").strip().lower()
    if hedge_drift_filter not in {"all", "high_drift"}:
        hedge_drift_filter = "all"
    status = _normalized_filter_text(kwargs["status"])
    if status == "all":
        status = None
    return {
        "start_ts": _coerce_timestamp(kwargs["start_ts"]),
        "end_ts": _coerce_timestamp(kwargs["end_ts"]),
        "status": status,
        "pnl_filter": pnl_filter,
        "min_trade_count": _optional_int(kwargs["min_trade_count"]),
        "min_win_rate": _optional_float(kwargs["min_win_rate"]),
        "max_win_rate": _optional_float(kwargs["max_win_rate"]),
        "regime": _normalized_filter_text(kwargs["regime"]),
        "hedge_drift_filter": hedge_drift_filter,
        "significant_only": _truthy(kwargs["significant_only"]),
        "search": _normalized_filter_text(kwargs["search"]),
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "page": page,
        "page_size": page_size,
    }


def _load_pair_history_data(start_ts: int | None, end_ts: int | None) -> PairHistoryDataBundle:
    pair_state, graveyard_tickers = _load_pair_state_data()
    try:
        SessionLocal, models, select, or_ = _platform_database_bundle()
    except Exception:
        return PairHistoryDataBundle(pair_state=pair_state, graveyard_tickers=graveyard_tickers)

    db = SessionLocal()
    try:
        Trade = models.Trade
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

        event_stmt = select(RunEvent)
        if start_dt is not None:
            event_stmt = event_stmt.where(RunEvent.ts >= start_dt)
        if end_dt is not None:
            event_stmt = event_stmt.where(RunEvent.ts <= end_dt)

        return PairHistoryDataBundle(
            trades=tuple(db.execute(trade_stmt).scalars().all()),
            run_events=tuple(db.execute(event_stmt).scalars().all()),
            pair_state=pair_state,
            graveyard_tickers=graveyard_tickers,
        )
    except Exception:
        return PairHistoryDataBundle(pair_state=pair_state, graveyard_tickers=graveyard_tickers)
    finally:
        try:
            db.close()
        except Exception:
            pass


def _platform_database_bundle() -> tuple[Any, Any, Any, Any]:
    repo_root = Path(__file__).resolve().parents[2]
    platform_root = repo_root / "Platform" / "api"
    if str(platform_root) not in sys.path:
        sys.path.append(str(platform_root))
    from sqlalchemy import or_, select

    from app import models
    from app.database import SessionLocal

    return SessionLocal, models, select, or_


def _load_pair_state_data() -> tuple[Mapping[str, Any] | None, frozenset[str]]:
    pair_state: Mapping[str, Any] | None = None
    graveyard_tickers: set[str] = set()
    if PAIR_STRATEGY_STATE_FILE.exists():
        try:
            parsed = json.loads(PAIR_STRATEGY_STATE_FILE.read_text(encoding="utf-8"))
            pair_state = parsed if isinstance(parsed, Mapping) else None
        except Exception:
            pair_state = None
    if GRAVEYARD_TICKERS_FILE.exists():
        try:
            parsed = json.loads(GRAVEYARD_TICKERS_FILE.read_text(encoding="utf-8"))
            if isinstance(parsed, Mapping):
                graveyard_tickers.update(str(key).strip() for key in parsed if str(key).strip())
            elif isinstance(parsed, list):
                graveyard_tickers.update(str(item).strip() for item in parsed if str(item).strip())
        except Exception:
            pass
    return pair_state, frozenset(graveyard_tickers)


def _filter_records_by_timestamp(records: Sequence[Any], *, start_ts: int | None, end_ts: int | None) -> tuple[Any, ...]:
    filtered = []
    for record in records:
        timestamp = _trade_timestamp(record) or _coerce_timestamp(_get_any(record, "ts", "timestamp"))
        if start_ts is not None and (timestamp is None or timestamp < start_ts):
            continue
        if end_ts is not None and (timestamp is None or timestamp > end_ts):
            continue
        filtered.append(record)
    return tuple(filtered)


def _status_for_pair(
    pair: str,
    *,
    pair_state: Mapping[str, Any] | None,
    graveyard_tickers: frozenset[str],
) -> str | None:
    if pair_state is None and not graveyard_tickers:
        return None
    direct_keys = {pair, _reverse_pair(pair)}
    graveyard = pair_state.get("graveyard", {}) if isinstance(pair_state, Mapping) else {}
    hospital = pair_state.get("hospital", {}) if isinstance(pair_state, Mapping) else {}
    health_failures = pair_state.get("health_failures", {}) if isinstance(pair_state, Mapping) else {}
    min_capital = pair_state.get("min_capital_cooldowns", {}) if isinstance(pair_state, Mapping) else {}
    if isinstance(graveyard, Mapping):
        for key in graveyard:
            key_text = str(key or "").strip()
            if key_text in direct_keys or (key_text.startswith("ticker::") and _ticker_in_pair(key_text.removeprefix("ticker::"), pair)):
                return "graveyard"
    if any(_ticker_in_pair(ticker, pair) for ticker in graveyard_tickers):
        return "graveyard"
    if isinstance(hospital, Mapping) and any(str(key or "").strip() in direct_keys for key in hospital):
        return "hospital"
    if isinstance(health_failures, Mapping) and any(str(key or "").strip() in direct_keys for key in health_failures):
        return "warning"
    if isinstance(min_capital, Mapping) and any(str(key or "").strip() in direct_keys for key in min_capital):
        return "warning"
    return "stable"


def _trade_summary(trade: Any) -> dict[str, Any]:
    payload = _payload(trade)
    entry_ts = _coerce_timestamp(_get_any(trade, "entry_ts", "entry_time", "entry_timestamp"))
    exit_ts = _coerce_timestamp(_get_any(trade, "exit_ts", "exit_time", "exit_timestamp"))
    entry_hedge_ratio = _first_not_none(
        _finite_float(_get_any(trade, "entry_hedge_ratio")),
        _finite_float(payload.get("entry_hedge_ratio")),
        _finite_float(payload.get("hedge_ratio")),
    )
    exit_hedge_ratio = _first_not_none(
        _finite_float(_get_any(trade, "exit_hedge_ratio")),
        _finite_float(payload.get("exit_hedge_ratio")),
    )
    summary = TradeSummary(
        trade_id=str(_get_any(trade, "trade_id", "id", "event_id") or f"{_normalize_pair(_get_any(trade, 'pair_key', 'pair'))}:{entry_ts or exit_ts or 'unknown'}"),
        pair=_normalize_pair(_get_any(trade, "pair_key", "pair")) or "",
        side=_normalize_text(_first_not_none(_get_any(trade, "side"), payload.get("side"))),
        entry_time=entry_ts,
        exit_time=exit_ts,
        entry_z=_finite_float(_first_not_none(_get_any(trade, "entry_z"), payload.get("entry_z"))),
        exit_z=_finite_float(_first_not_none(_get_any(trade, "exit_z"), payload.get("exit_z"))),
        hold_seconds=_hold_seconds(trade),
        pnl_usdt=_finite_float(_first_not_none(_get_any(trade, "pnl_usdt", "pnl"), payload.get("pnl_usdt"))),
        fees_usdt=_finite_float(_first_not_none(_get_any(trade, "fees_usdt"), payload.get("fees_usdt"))),
        slippage_usdt=_finite_float(_first_not_none(_get_any(trade, "slippage_usdt"), payload.get("slippage_usdt"))),
        exit_reason=_normalize_text(_first_not_none(_get_any(trade, "exit_reason"), payload.get("exit_reason"))),
        entry_hedge_ratio=entry_hedge_ratio,
        exit_hedge_ratio=exit_hedge_ratio,
        hedge_ratio_drift_pct=_first_not_none(
            _finite_float(_get_any(trade, "hedge_ratio_drift_pct")),
            _finite_float(payload.get("hedge_ratio_drift_pct")),
        ),
        regime_at_entry=_normalize_text(_first_not_none(_get_any(trade, "entry_regime", "regime"), payload.get("regime_at_entry"))),
        final_rank_score_at_entry=_finite_float(_first_not_none(payload.get("final_rank_score_at_entry"), payload.get("final_rank_score"))),
        bayesian_posterior_at_entry=_finite_float(_first_not_none(payload.get("bayesian_posterior_at_entry"), payload.get("bayesian_posterior"))),
    )
    return summary.to_dict()


def _best_trade(trades: Sequence[Any]) -> Any | None:
    with_pnl = [trade for trade in trades if _finite_float(_get_any(trade, "pnl_usdt", "pnl")) is not None]
    return max(with_pnl, key=lambda trade: _finite_float(_get_any(trade, "pnl_usdt", "pnl")) or 0.0) if with_pnl else None


def _worst_trade(trades: Sequence[Any]) -> Any | None:
    with_pnl = [trade for trade in trades if _finite_float(_get_any(trade, "pnl_usdt", "pnl")) is not None]
    return min(with_pnl, key=lambda trade: _finite_float(_get_any(trade, "pnl_usdt", "pnl")) or 0.0) if with_pnl else None


def _max_drawdown_from_trades(trades: Sequence[Any]) -> float | None:
    ordered = sorted(trades, key=lambda trade: _trade_timestamp(trade) or 0)
    cumulative = 0.0
    peak = 0.0
    worst_drawdown = 0.0
    seen = False
    for trade in ordered:
        pnl = _finite_float(_get_any(trade, "pnl_usdt", "pnl"))
        if pnl is None:
            continue
        seen = True
        cumulative += pnl
        peak = max(peak, cumulative)
        worst_drawdown = min(worst_drawdown, cumulative - peak)
    return worst_drawdown if seen else None


def _is_significant(row: Mapping[str, Any]) -> bool:
    best = row.get("best_trade")
    worst = row.get("worst_trade")
    return any(
        (
            abs(_finite_float(row.get("net_pnl_usdt")) or 0.0) >= SIGNIFICANT_PNL_THRESHOLD,
            int(row.get("total_trades") or 0) >= SIGNIFICANT_TRADE_COUNT_THRESHOLD,
            abs(_finite_float(row.get("max_drawdown_usdt")) or 0.0) >= SIGNIFICANT_DRAWDOWN_THRESHOLD,
            isinstance(best, Mapping) and (_finite_float(best.get("pnl_usdt")) or 0.0) >= SIGNIFICANT_TRADE_THRESHOLD,
            isinstance(worst, Mapping) and (_finite_float(worst.get("pnl_usdt")) or 0.0) <= -SIGNIFICANT_TRADE_THRESHOLD,
        )
    )


def _tags_for_pair(
    *,
    status: str | None,
    total_trades: int,
    net_pnl: float | None,
    win_rate: float | None,
    profit_factor: float | None,
    avg_hedge_drift_pct: float | None,
    avg_slippage_usdt: float | None,
) -> list[str]:
    tags: list[str] = []
    if net_pnl is not None and net_pnl > 0:
        tags.append(DashboardTag.PROFITABLE.value)
    if net_pnl is not None and net_pnl < 0:
        tags.append(DashboardTag.LOSING.value)
    if status in {DashboardTag.STABLE.value, DashboardTag.WARNING.value, DashboardTag.HOSPITAL.value, DashboardTag.GRAVEYARD.value}:
        tags.append(status)
    if avg_hedge_drift_pct is not None and avg_hedge_drift_pct >= HIGH_HEDGE_DRIFT_THRESHOLD:
        tags.append(DashboardTag.HIGH_DRIFT.value)
    if avg_slippage_usdt is not None and avg_slippage_usdt >= HIGH_SLIPPAGE_USDT_THRESHOLD:
        tags.append(DashboardTag.HIGH_SLIPPAGE.value)
    if total_trades >= 3 and win_rate is not None and profit_factor is not None and win_rate >= 0.60 and profit_factor >= 1.50:
        tags.append(DashboardTag.GOOD_REVERTER.value)
    if total_trades >= 5 and net_pnl is not None and net_pnl >= SIGNIFICANT_PNL_THRESHOLD and win_rate is not None and win_rate >= 0.60 and profit_factor is not None and profit_factor >= 1.50:
        tags.append(DashboardTag.ELITE.value)
    return tags


def _extract_block_reasons(event: Any) -> list[str]:
    payload = _payload(event)
    event_type = str(_get_any(event, "event_type") or payload.get("event_type") or "").lower()
    if "block" not in event_type and not any(key in payload for key in ("block_reasons", "block_reason")):
        return []
    reasons = payload.get("block_reasons") or payload.get("block_reason") or payload.get("reason")
    if isinstance(reasons, str):
        return [reasons] if reasons.strip() else []
    if isinstance(reasons, Sequence):
        return [str(reason).strip() for reason in reasons if str(reason).strip()]
    return []


def _payload(record: Any) -> Mapping[str, Any]:
    payload = _get_any(record, "payload_json", "payload", "metadata")
    return payload if isinstance(payload, Mapping) else {}


def _trade_metadata_float(trade: Any, *keys: str) -> float | None:
    payload = _payload(trade)
    for key in keys:
        value = _finite_float(_get_any(trade, key))
        if value is not None:
            return value
        value = _finite_float(payload.get(key))
        if value is not None:
            return value
    return None


def _trade_timestamp(record: Any) -> int | None:
    return _first_not_none(
        _coerce_timestamp(_get_any(record, "exit_ts", "exit_time", "exit_timestamp")),
        _coerce_timestamp(_get_any(record, "entry_ts", "entry_time", "entry_timestamp")),
    )


def _hold_seconds(trade: Any) -> float | None:
    seconds = _finite_float(_get_any(trade, "hold_seconds"))
    if seconds is not None:
        return seconds
    minutes = _finite_float(_get_any(trade, "hold_minutes"))
    return minutes * 60.0 if minutes is not None else None


def _average(values: Iterable[float]) -> float | None:
    total = 0.0
    count = 0
    for value in values:
        total += value
        count += 1
    return total / count if count else None


def _first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _get_any(record: Any, *keys: str) -> Any:
    if record is None:
        return None
    for key in keys:
        if isinstance(record, Mapping) and key in record and record[key] is not None:
            return record[key]
        if not isinstance(record, Mapping) and hasattr(record, key):
            value = getattr(record, key)
            if value is not None:
                return value
    return None


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _optional_float(value: Any) -> float | None:
    return _finite_float(value)


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _positive_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    parsed = _optional_int(value)
    if parsed is None:
        return default
    return min(max(parsed, minimum), maximum)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalized_filter_text(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text or None


def _normalize_pair(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _reverse_pair(pair: str) -> str:
    parts = pair.split("/")
    return f"{parts[1]}/{parts[0]}" if len(parts) == 2 else pair


def _ticker_in_pair(ticker: str, pair: str) -> bool:
    ticker_text = str(ticker or "").strip()
    return bool(ticker_text) and ticker_text in {part.strip() for part in pair.split("/")}


def _coerce_timestamp(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    if isinstance(value, date):
        return int(datetime(value.year, value.month, value.day, tzinfo=timezone.utc).timestamp())
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())
    if not math.isfinite(numeric):
        return None
    if numeric > 10_000_000_000:
        numeric /= 1000.0
    return int(numeric)


def _timestamp_to_datetime(value: int | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, timezone.utc)


__all__ = [
    "GRAVEYARD_TICKERS_FILE",
    "HIGH_HEDGE_DRIFT_THRESHOLD",
    "PAIR_HISTORY_CACHE_TTL_SECONDS",
    "PAIR_STRATEGY_STATE_FILE",
    "PairHistoryDataBundle",
    "clear_pair_history_cache",
    "get_pair_history_summary",
]
