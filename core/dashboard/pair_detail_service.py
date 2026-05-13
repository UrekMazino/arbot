"""Read-only Pair Detail summary service."""

from __future__ import annotations

import copy
import csv
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from core.chart_audit.ml_score_lookup import get_stored_score_at
from core.dashboard.contracts import DashboardCacheMeta
from core.dashboard.pair_history_service import (
    _average,
    _best_trade,
    _coerce_timestamp,
    _extract_block_reasons,
    _finite_float,
    _first_not_none,
    _get_any,
    _hold_seconds,
    _load_pair_state_data,
    _normalize_pair,
    _payload,
    _platform_database_bundle,
    _status_for_pair,
    _timestamp_to_datetime,
    _trade_metadata_float,
    _trade_summary,
    _trade_timestamp,
    _worst_trade,
)


PAIR_DETAIL_CACHE_TTL_SECONDS = 300

_REPO_ROOT = Path(__file__).resolve().parents[2]
COINTEGRATED_PAIRS_CSV = _REPO_ROOT / "Strategy" / "output" / "2_cointegrated_pairs.csv"


@dataclass(frozen=True)
class PairDetailDataBundle:
    trades: tuple[Any, ...] = ()
    run_events: tuple[Any, ...] = ()
    pair_state: Mapping[str, Any] | None = None
    graveyard_tickers: frozenset[str] = frozenset()
    current_hedge_ratio: float | None = None
    counterfactual_records: tuple[Any, ...] = ()
    stored_scores: tuple[Any, ...] = ()


_CACHE: dict[tuple[str, str, int | None, int | None], tuple[float, dict[str, Any]]] = {}


def get_pair_detail_summary(
    pair: str,
    timeframe: str = "1m",
    start_ts: int | float | datetime | str | None = None,
    end_ts: int | float | datetime | str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Return a JSON-safe Pair Detail summary for one selected pair."""

    normalized_pair = _normalize_pair(pair) or ""
    normalized_timeframe = str(timeframe or "1m").strip() or "1m"
    start_value = _coerce_timestamp(start_ts)
    end_value = _coerce_timestamp(end_ts)
    cache_key = (normalized_pair, normalized_timeframe, start_value, end_value)
    now = time.time()

    if not refresh:
        cached = _CACHE.get(cache_key)
        if cached is not None:
            expires_at, payload = cached
            if now < expires_at:
                result = copy.deepcopy(payload)
                result["cache"]["cache_hit"] = True
                return result

    payload = _compute_pair_detail_summary(
        pair=normalized_pair,
        timeframe=normalized_timeframe,
        start_ts=start_value,
        end_ts=end_value,
        generated_at=now,
        ttl_seconds=PAIR_DETAIL_CACHE_TTL_SECONDS,
    )
    _CACHE[cache_key] = (now + PAIR_DETAIL_CACHE_TTL_SECONDS, copy.deepcopy(payload))
    return payload


def clear_pair_detail_cache() -> None:
    _CACHE.clear()


def _compute_pair_detail_summary(
    *,
    pair: str,
    timeframe: str,
    start_ts: int | None,
    end_ts: int | None,
    generated_at: float,
    ttl_seconds: int,
) -> dict[str, Any]:
    bundle = _load_pair_detail_data(pair=pair, timeframe=timeframe, start_ts=start_ts, end_ts=end_ts)
    trades = tuple(
        trade
        for trade in _filter_records_by_timestamp(bundle.trades, start_ts=start_ts, end_ts=end_ts)
        if _same_pair(pair, _get_any(trade, "pair_key", "pair") or _payload(trade).get("pair"))
    )
    run_events = tuple(
        event
        for event in _filter_records_by_timestamp(bundle.run_events, start_ts=start_ts, end_ts=end_ts)
        if _event_pair_matches(pair, event)
    )
    stored_scores = tuple(
        score
        for score in _filter_records_by_timestamp(bundle.stored_scores, start_ts=start_ts, end_ts=end_ts)
        if _score_pair_matches(pair, score)
    )
    latest_score = _latest_score(pair=pair, end_ts=end_ts, score_records=stored_scores or run_events)
    status = _status_for_pair(pair, pair_state=bundle.pair_state, graveyard_tickers=bundle.graveyard_tickers)

    return {
        "pair": pair,
        "timeframe": timeframe,
        "status": status,
        "summary": _build_summary(
            trades=trades,
            current_hedge_ratio=bundle.current_hedge_ratio,
            latest_score=latest_score,
        ),
        "best_trade": _trade_summary(_best_trade(trades)) if _best_trade(trades) is not None else None,
        "worst_trade": _trade_summary(_worst_trade(trades)) if _worst_trade(trades) is not None else None,
        "latest_trade": _trade_summary(_latest_trade(trades)) if _latest_trade(trades) is not None else None,
        "block_reason_counts": _block_reason_counts(run_events),
        "counterfactual_summary": _build_counterfactual_summary(bundle.counterfactual_records),
        "hedge_summary": _build_hedge_summary(
            trades=trades,
            counterfactual_records=bundle.counterfactual_records,
        ),
        "cache": DashboardCacheMeta(
            cache_hit=False,
            generated_at=generated_at,
            ttl_seconds=ttl_seconds,
            refresh_supported=True,
        ).to_dict(),
    }


def _build_summary(
    *,
    trades: Sequence[Any],
    current_hedge_ratio: float | None,
    latest_score: Any | None,
) -> dict[str, Any]:
    pnl_values = [_finite_float(_get_any(trade, "pnl_usdt", "pnl")) for trade in trades]
    pnl_values = [value for value in pnl_values if value is not None]
    wins = sum(1 for value in pnl_values if value > 0)
    gross_profit = sum(value for value in pnl_values if value > 0)
    gross_loss = abs(sum(value for value in pnl_values if value < 0))
    hold_values = [_hold_seconds(trade) for trade in trades]
    hedge_values = [_trade_metadata_float(trade, "entry_hedge_ratio", "hedge_ratio") for trade in trades]
    drift_values = [_trade_metadata_float(trade, "hedge_ratio_drift_pct") for trade in trades]

    return {
        "total_pnl_usdt": sum(pnl_values) if pnl_values else None,
        "total_trades": len(trades) if trades else None,
        "win_rate": (wins / len(pnl_values)) if pnl_values else None,
        "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else None,
        "avg_reversion_time_seconds": _average(value for value in hold_values if value is not None),
        "avg_hedge_ratio": _average(value for value in hedge_values if value is not None),
        "current_hedge_ratio": _finite_float(current_hedge_ratio),
        "avg_hedge_drift_pct": _average(value for value in drift_values if value is not None),
        "current_regime": _score_text(latest_score, "regime_name", "regime"),
        "current_bayesian_posterior": _score_float(latest_score, "bayesian_posterior"),
        "current_final_rank_score": _score_float(latest_score, "final_rank_score"),
    }


def _build_counterfactual_summary(records: Sequence[Any]) -> dict[str, Any]:
    return {
        "best_exit_policy": _best_exit_policy(records),
        "avg_missed_profit_usdt": _average_counterfactual_field(records, "missed_profit_usdt"),
        "avg_avoided_loss_usdt": _average_counterfactual_field(records, "avoided_loss_usdt"),
        "actual_exit_efficiency": _average_counterfactual_field(records, "actual_exit_efficiency"),
    }


def _build_hedge_summary(*, trades: Sequence[Any], counterfactual_records: Sequence[Any]) -> dict[str, Any]:
    entry_values = [_trade_metadata_float(trade, "entry_hedge_ratio", "hedge_ratio") for trade in trades]
    exit_values = [_trade_metadata_float(trade, "exit_hedge_ratio") for trade in trades]
    drift_values = [_trade_metadata_float(trade, "hedge_ratio_drift_pct") for trade in trades]

    equal_total = _sum_counterfactual_field(counterfactual_records, "equal_notional_total_pnl", "equal_notional_pnl_usdt")
    hedge_total = _sum_counterfactual_field(counterfactual_records, "hedge_ratio_sized_total_pnl", "hedge_ratio_sized_pnl_usdt")
    delta_total = _sum_counterfactual_field(counterfactual_records, "sizing_pnl_delta_usdt", "pnl_delta_usdt")

    return {
        "avg_entry_hedge_ratio": _average(value for value in entry_values if value is not None),
        "avg_exit_hedge_ratio": _average(value for value in exit_values if value is not None),
        "avg_hedge_drift_pct": _average(value for value in drift_values if value is not None),
        "equal_notional_total_pnl": equal_total,
        "hedge_ratio_sized_total_pnl": hedge_total,
        "sizing_pnl_delta_usdt": delta_total,
    }


def _load_pair_detail_data(
    *,
    pair: str,
    timeframe: str,
    start_ts: int | None,
    end_ts: int | None,
) -> PairDetailDataBundle:
    pair_state, graveyard_tickers = _load_pair_state_data()
    current_hedge_ratio = _load_current_hedge_ratio(pair)
    try:
        SessionLocal, models, select, or_ = _platform_database_bundle()
    except Exception:
        return PairDetailDataBundle(
            pair_state=pair_state,
            graveyard_tickers=graveyard_tickers,
            current_hedge_ratio=current_hedge_ratio,
        )

    db = SessionLocal()
    try:
        Trade = models.Trade
        RunEvent = models.RunEvent
        start_dt = _timestamp_to_datetime(start_ts)
        end_dt = _timestamp_to_datetime(end_ts)

        trade_stmt = select(Trade).where(Trade.pair_key == pair)
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

        run_events = tuple(event for event in db.execute(event_stmt).scalars().all() if _event_pair_matches(pair, event))
        return PairDetailDataBundle(
            trades=tuple(db.execute(trade_stmt).scalars().all()),
            run_events=run_events,
            pair_state=pair_state,
            graveyard_tickers=graveyard_tickers,
            current_hedge_ratio=current_hedge_ratio,
            stored_scores=run_events,
        )
    except Exception:
        return PairDetailDataBundle(
            pair_state=pair_state,
            graveyard_tickers=graveyard_tickers,
            current_hedge_ratio=current_hedge_ratio,
        )
    finally:
        try:
            db.close()
        except Exception:
            pass


def _load_current_hedge_ratio(pair: str) -> float | None:
    if not pair or not COINTEGRATED_PAIRS_CSV.exists():
        return None
    try:
        with COINTEGRATED_PAIRS_CSV.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                sym_1 = str(row.get("sym_1") or "").strip()
                sym_2 = str(row.get("sym_2") or "").strip()
                row_pair = f"{sym_1}/{sym_2}" if sym_1 and sym_2 else str(row.get("pair") or "").strip()
                if _same_pair(pair, row_pair):
                    return _finite_float(row.get("hedge_ratio"))
    except Exception:
        return None
    return None


def _filter_records_by_timestamp(records: Sequence[Any], *, start_ts: int | None, end_ts: int | None) -> tuple[Any, ...]:
    filtered = []
    for record in records:
        timestamp = _record_timestamp(record)
        if start_ts is not None and (timestamp is None or timestamp < start_ts):
            continue
        if end_ts is not None and (timestamp is None or timestamp > end_ts):
            continue
        filtered.append(record)
    return tuple(filtered)


def _record_timestamp(record: Any) -> int | None:
    return _first_not_none(
        _coerce_timestamp(_get_any(record, "timestamp", "ts")),
        _trade_timestamp(record),
        _coerce_timestamp(_payload(record).get("timestamp") or _payload(record).get("ts")),
    )


def _latest_trade(trades: Sequence[Any]) -> Any | None:
    with_timestamps = [(trade, _trade_timestamp(trade)) for trade in trades]
    with_timestamps = [(trade, timestamp) for trade, timestamp in with_timestamps if timestamp is not None]
    if not with_timestamps:
        return None
    return max(with_timestamps, key=lambda item: item[1])[0]


def _block_reason_counts(events: Sequence[Any]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for event in events:
        for reason in _extract_block_reasons(event):
            counter[reason] += 1
    return dict(counter)


def _latest_score(*, pair: str, end_ts: int | None, score_records: Sequence[Any]) -> Any | None:
    if not score_records:
        return None
    target_ts = end_ts or max((_record_timestamp(record) or 0 for record in score_records), default=0)
    if not target_ts:
        return None
    direct_scores = [
        record
        for record in score_records
        if _is_score_snapshot(record) and (_record_timestamp(record) or 0) <= target_ts and _score_pair_matches(pair, record)
    ]
    if direct_scores:
        return max(direct_scores, key=lambda record: _record_timestamp(record) or 0)
    try:
        return get_stored_score_at(pair, target_ts, stored_events=score_records)
    except Exception:
        return None


def _score_float(score: Any | None, *keys: str) -> float | None:
    if score is None:
        return None
    payload = _payload(score)
    metadata = _get_any(score, "metadata")
    for key in keys:
        value = _finite_float(_get_any(score, key))
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


def _score_text(score: Any | None, *keys: str) -> str | None:
    if score is None:
        return None
    payload = _payload(score)
    metadata = _get_any(score, "metadata")
    for key in keys:
        value = _normalize_text(_get_any(score, key))
        if value:
            return value
        value = _normalize_text(payload.get(key))
        if value:
            return value
        if isinstance(metadata, Mapping):
            value = _normalize_text(metadata.get(key))
            if value:
                return value
    return None


def _average_counterfactual_field(records: Sequence[Any], *keys: str) -> float | None:
    values = [_record_float(record, *keys) for record in records]
    return _average(value for value in values if value is not None)


def _sum_counterfactual_field(records: Sequence[Any], *keys: str) -> float | None:
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


def _best_exit_policy(records: Sequence[Any]) -> str | None:
    policies = [
        _normalize_text(
            _first_not_none(
                _get_any(record, "best_exit_policy", "best_policy_by_pnl"),
                _payload(record).get("best_exit_policy"),
                _payload(record).get("best_policy_by_pnl"),
            )
        )
        for record in records
    ]
    policies = [policy for policy in policies if policy]
    if not policies:
        return None
    return Counter(policies).most_common(1)[0][0]


def _event_pair_matches(pair: str, event: Any) -> bool:
    payload = _payload(event)
    return _same_pair(pair, _first_not_none(payload.get("pair"), payload.get("pair_key"), _get_any(event, "pair", "pair_key")))


def _score_pair_matches(pair: str, score: Any) -> bool:
    score_pair = _first_not_none(_get_any(score, "pair"), _payload(score).get("pair"))
    return True if not score_pair else _same_pair(pair, score_pair)


def _is_score_snapshot(record: Any) -> bool:
    return any(
        _get_any(record, key) is not None or _payload(record).get(key) is not None
        for key in (
            "score_source",
            "regime_name",
            "regime",
            "bayesian_posterior",
            "final_rank_score",
        )
    )


def _same_pair(left: Any, right: Any) -> bool:
    left_text = _normalize_pair(left)
    right_text = _normalize_pair(right)
    if not left_text or not right_text:
        return False
    return left_text == right_text or _sorted_pair_key(left_text) == _sorted_pair_key(right_text)


def _sorted_pair_key(pair: str) -> str:
    parts = [part.strip().upper() for part in str(pair or "").split("/") if part.strip()]
    return "/".join(sorted(parts)) if len(parts) == 2 else str(pair or "").strip().upper()


def _normalize_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


__all__ = [
    "COINTEGRATED_PAIRS_CSV",
    "PAIR_DETAIL_CACHE_TTL_SECONDS",
    "PairDetailDataBundle",
    "clear_pair_detail_cache",
    "get_pair_detail_summary",
]
