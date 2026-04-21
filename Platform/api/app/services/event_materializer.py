from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from ..models import (
    BotConfig,
    EquitySnapshot,
    PositionSnapshot,
    RegimeMetric,
    Run,
    RunEvent,
    StrategyMetric,
    Trade,
)


def _coerce_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _zero_near(value: float | None, tolerance: float = 1e-8) -> float | None:
    if value is None:
        return None
    return 0.0 if abs(value) < tolerance else value


def _coerce_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    numeric = _coerce_float(value)
    if numeric is not None:
        try:
            return datetime.fromtimestamp(numeric, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_pair_text(value: object) -> str | None:
    text = str(value or "").strip()
    if not text or "/" not in text:
        return None
    left, right = text.split("/", 1)
    left = left.strip().upper()
    right = right.strip().upper()
    if not left or not right:
        return None
    return f"{left}/{right}"


def _normalize_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_upper(value: object) -> str | None:
    text = _normalize_text(value)
    return text.upper() if text else None


def _payload_dict(event: RunEvent) -> dict:
    return event.payload_json if isinstance(event.payload_json, dict) else {}


def _latest_bot_config(db: Session, run_id: str) -> BotConfig | None:
    return db.execute(
        select(BotConfig)
        .where(BotConfig.run_id == run_id)
        .order_by(desc(BotConfig.created_at), desc(BotConfig.id))
        .limit(1)
    ).scalar_one_or_none()


def _latest_open_trade(db: Session, run_id: str, pair_key: str | None = None) -> Trade | None:
    stmt = (
        select(Trade)
        .where(Trade.run_id == run_id, Trade.exit_ts.is_(None))
        .order_by(desc(Trade.entry_ts), desc(Trade.id))
    )
    if pair_key:
        stmt = stmt.where(Trade.pair_key == pair_key)
    return db.execute(stmt.limit(1)).scalar_one_or_none()


def _latest_runtime_event_ts(db: Session, run_id: str) -> datetime:
    row = db.execute(
        select(RunEvent.ts)
        .where(RunEvent.run_id == run_id)
        .order_by(desc(RunEvent.ts), desc(RunEvent.created_at), desc(RunEvent.id))
        .limit(1)
    ).first()
    if row and row[0] is not None:
        ts = row[0]
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def _sync_bot_config_for_event(db: Session, run: Run, event: RunEvent) -> None:
    if str(event.event_type or "").strip().lower() != "status_update":
        return
    payload = _payload_dict(event)
    status_text = str(payload.get("status") or "").strip().lower()
    if status_text != "startup_complete":
        return
    config_snapshot = payload.get("config_snapshot")
    if not isinstance(config_snapshot, dict) or not config_snapshot:
        return

    existing = _latest_bot_config(db, run.id)
    if existing is None:
        db.add(BotConfig(run_id=run.id, config_snapshot_json=dict(config_snapshot)))
        db.flush()
        return

    if existing.config_snapshot_json != config_snapshot:
        existing.config_snapshot_json = dict(config_snapshot)
        db.flush()


def _sync_trade_open_for_event(db: Session, run: Run, event: RunEvent) -> None:
    payload = _payload_dict(event)
    pair_key = _normalize_pair_text(payload.get("pair"))
    if pair_key is None:
        return

    trade = _latest_open_trade(db, run.id, pair_key)
    if trade is None:
        trade = Trade(run_id=run.id, pair_key=pair_key)
        db.add(trade)

    entry_ts = _coerce_datetime(payload.get("entry_ts")) or event.ts
    trade.entry_ts = trade.entry_ts or entry_ts
    trade.pair_key = pair_key
    trade.side = _normalize_text(payload.get("side")) or trade.side

    entry_z = _coerce_float(payload.get("entry_z"))
    if entry_z is not None:
        trade.entry_z = entry_z

    strategy = _normalize_upper(payload.get("strategy"))
    regime = _normalize_upper(payload.get("regime"))
    entry_strategy = _normalize_upper(payload.get("entry_strategy")) or strategy
    entry_regime = _normalize_upper(payload.get("entry_regime")) or regime

    if strategy:
        trade.strategy = strategy
    if regime:
        trade.regime = regime
    if entry_strategy:
        trade.entry_strategy = entry_strategy
    if entry_regime:
        trade.entry_regime = entry_regime

    entry_z_threshold_used = _coerce_float(payload.get("entry_z_threshold_used"))
    if entry_z_threshold_used is not None:
        trade.entry_z_threshold_used = entry_z_threshold_used
    size_multiplier_used = _coerce_float(payload.get("size_multiplier_used"))
    if size_multiplier_used is not None:
        trade.size_multiplier_used = size_multiplier_used

    db.flush()


def _sync_trade_close_for_event(db: Session, run: Run, event: RunEvent) -> None:
    payload = _payload_dict(event)
    pair_key = _normalize_pair_text(payload.get("pair"))
    hold_minutes = _coerce_float(payload.get("hold_minutes"))
    trade = None
    if pair_key is not None:
        trade = _latest_open_trade(db, run.id, pair_key)
    if trade is None:
        trade = _latest_open_trade(db, run.id)
    if trade is None:
        synthetic_entry_ts = _coerce_datetime(payload.get("entry_ts"))
        if synthetic_entry_ts is None and hold_minutes is not None and hold_minutes >= 0:
            synthetic_entry_ts = event.ts - timedelta(minutes=hold_minutes)
        trade = Trade(
            run_id=run.id,
            pair_key=pair_key or "UNKNOWN/UNKNOWN",
            entry_ts=synthetic_entry_ts,
        )
        db.add(trade)

    if pair_key:
        trade.pair_key = pair_key

    entry_ts = _coerce_datetime(payload.get("entry_ts"))
    if trade.entry_ts is None and entry_ts is not None:
        trade.entry_ts = entry_ts

    trade.exit_ts = event.ts
    trade.side = _normalize_text(payload.get("side")) or trade.side

    entry_z = _coerce_float(payload.get("entry_z"))
    if entry_z is not None and trade.entry_z is None:
        trade.entry_z = entry_z

    exit_z = _coerce_float(payload.get("exit_z"))
    if exit_z is not None:
        trade.exit_z = exit_z

    pnl_usdt = _coerce_float(payload.get("pnl_usdt"))
    if pnl_usdt is not None:
        trade.pnl_usdt = pnl_usdt
    if hold_minutes is not None:
        trade.hold_minutes = hold_minutes

    strategy = _normalize_upper(payload.get("strategy"))
    regime = _normalize_upper(payload.get("regime"))
    entry_strategy = _normalize_upper(payload.get("entry_strategy")) or strategy
    entry_regime = _normalize_upper(payload.get("entry_regime")) or regime

    if strategy:
        trade.strategy = strategy
    if regime:
        trade.regime = regime
    if entry_strategy and not trade.entry_strategy:
        trade.entry_strategy = entry_strategy
    if entry_regime and not trade.entry_regime:
        trade.entry_regime = entry_regime

    exit_reason = _normalize_text(payload.get("exit_reason"))
    if exit_reason:
        trade.exit_reason = exit_reason
    exit_tier = _normalize_text(payload.get("exit_tier"))
    if exit_tier:
        trade.exit_tier = exit_tier

    entry_z_threshold_used = _coerce_float(payload.get("entry_z_threshold_used"))
    if entry_z_threshold_used is not None and trade.entry_z_threshold_used is None:
        trade.entry_z_threshold_used = entry_z_threshold_used
    size_multiplier_used = _coerce_float(payload.get("size_multiplier_used"))
    if size_multiplier_used is not None and trade.size_multiplier_used is None:
        trade.size_multiplier_used = size_multiplier_used

    db.flush()


def _sync_position_snapshot_for_event(db: Session, run: Run, event: RunEvent) -> None:
    payload = _payload_dict(event)
    if not bool(payload.get("in_position")):
        return

    pair_key = _normalize_pair_text(payload.get("current_pair") or payload.get("pair"))
    if pair_key is None:
        return

    notional_usdt = _coerce_float(payload.get("entry_notional_usdt"))
    unrealized_pnl_usdt = _coerce_float(payload.get("unrealized_pnl_usdt"))
    entry_z = _coerce_float(payload.get("entry_z"))
    current_z = _coerce_float(payload.get("current_z"))
    hold_minutes = _coerce_float(payload.get("hold_minutes"))
    if all(
        value is None
        for value in (notional_usdt, unrealized_pnl_usdt, entry_z, current_z, hold_minutes)
    ):
        return

    hold_minutes_int = None
    if hold_minutes is not None:
        hold_minutes_int = max(int(round(hold_minutes)), 0)

    db.add(
        PositionSnapshot(
            run_id=run.id,
            ts=event.ts,
            pair_key=pair_key,
            notional_usdt=notional_usdt,
            unrealized_pnl_usdt=unrealized_pnl_usdt,
            entry_z=entry_z,
            current_z=current_z,
            hold_minutes=hold_minutes_int,
        )
    )
    db.flush()


def _sync_equity_snapshot_for_event(db: Session, run: Run, event: RunEvent) -> None:
    event_type = str(event.event_type or "").strip().lower()
    payload = _payload_dict(event)
    source = event_type
    equity_usdt = None

    if event_type == "heartbeat":
        equity_usdt = _coerce_float(payload.get("equity_usdt"))
        source = "heartbeat"
    elif event_type == "status_update":
        status_text = str(payload.get("status") or "").strip().lower()
        if status_text != "startup_complete":
            return
        equity_usdt = _coerce_float(payload.get("starting_equity_usdt"))
        source = "startup"
    elif event_type == "trade_close":
        equity_usdt = _coerce_float(payload.get("ending_equity_usdt"))
        source = "trade_close"
    else:
        return

    if equity_usdt is None:
        return

    existing = db.execute(
        select(EquitySnapshot)
        .where(EquitySnapshot.source_event_id == event.event_id)
        .limit(1)
    ).scalar_one_or_none()
    snapshot = existing or EquitySnapshot(
        run_id=run.id,
        ts=event.ts,
        equity_usdt=equity_usdt,
        source=source,
        source_event_id=event.event_id,
    )
    if existing is None:
        db.add(snapshot)

    start_equity = _coerce_float(run.start_equity)
    session_pnl_usdt = _coerce_float(payload.get("session_pnl_usdt"))
    if session_pnl_usdt is None and start_equity is not None:
        session_pnl_usdt = equity_usdt - start_equity
    session_pnl_usdt = _zero_near(session_pnl_usdt)

    session_pnl_pct = _coerce_float(payload.get("session_pnl_pct"))
    if session_pnl_pct is None and session_pnl_usdt is not None and start_equity and start_equity > 0:
        session_pnl_pct = (session_pnl_usdt / start_equity) * 100.0
    session_pnl_pct = _zero_near(session_pnl_pct)

    snapshot.run_id = run.id
    snapshot.ts = event.ts
    snapshot.equity_usdt = equity_usdt
    snapshot.session_pnl_usdt = session_pnl_usdt
    snapshot.session_pnl_pct = session_pnl_pct
    snapshot.current_pair = _normalize_pair_text(payload.get("current_pair") or payload.get("pair"))
    snapshot.regime = _normalize_upper(payload.get("regime"))
    snapshot.strategy = _normalize_upper(payload.get("strategy"))
    snapshot.in_position = bool(payload.get("in_position"))
    snapshot.entry_z = _coerce_float(payload.get("entry_z"))
    snapshot.current_z = _coerce_float(payload.get("current_z"))
    snapshot.hold_minutes = _coerce_float(payload.get("hold_minutes"))
    snapshot.unrealized_pnl_usdt = _coerce_float(payload.get("unrealized_pnl_usdt"))
    snapshot.source = source
    snapshot.source_event_id = event.event_id
    db.flush()

    _rebuild_run_equity_summary(db, run)


def _rebuild_run_equity_summary(db: Session, run: Run) -> None:
    rows = db.execute(
        select(EquitySnapshot)
        .where(EquitySnapshot.run_id == run.id)
        .order_by(EquitySnapshot.ts.asc(), EquitySnapshot.created_at.asc(), EquitySnapshot.id.asc())
    ).scalars().all()
    if not rows:
        return

    latest_equity = _coerce_float(rows[-1].equity_usdt)
    start_equity = _coerce_float(run.start_equity) or _coerce_float(rows[0].equity_usdt)
    if latest_equity is not None:
        run.end_equity = latest_equity
    if latest_equity is not None and start_equity is not None:
        run.session_pnl = _zero_near(latest_equity - start_equity)

    peak = None
    max_drawdown = 0.0
    for row in rows:
        equity = _coerce_float(row.equity_usdt)
        if equity is None:
            continue
        peak = equity if peak is None else max(peak, equity)
        max_drawdown = min(max_drawdown, equity - peak)
    run.max_drawdown = _zero_near(max_drawdown)
    db.flush()


def _rebuild_strategy_metrics_for_run(db: Session, run: Run) -> None:
    closed_trades = db.execute(
        select(Trade)
        .where(Trade.run_id == run.id, Trade.exit_ts.is_not(None))
        .order_by(Trade.exit_ts.asc(), Trade.id.asc())
    ).scalars().all()

    aggregates: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "trades": 0.0,
            "wins": 0.0,
            "losses": 0.0,
            "pnl_sum": 0.0,
            "hold_sum": 0.0,
            "hold_count": 0.0,
        }
    )
    for trade in closed_trades:
        strategy = _normalize_upper(trade.entry_strategy or trade.strategy) or "UNKNOWN"
        bucket = aggregates[strategy]
        bucket["trades"] += 1.0
        pnl_usdt = _coerce_float(trade.pnl_usdt)
        if pnl_usdt is not None:
            bucket["pnl_sum"] += pnl_usdt
            if pnl_usdt > 0:
                bucket["wins"] += 1.0
            elif pnl_usdt < 0:
                bucket["losses"] += 1.0
        hold_minutes = _coerce_float(trade.hold_minutes)
        if hold_minutes is not None:
            bucket["hold_sum"] += hold_minutes
            bucket["hold_count"] += 1.0

    db.execute(delete(StrategyMetric).where(StrategyMetric.run_id == run.id))
    for strategy in sorted(aggregates):
        bucket = aggregates[strategy]
        trades = int(bucket["trades"])
        wins = int(bucket["wins"])
        losses = int(bucket["losses"])
        win_rate_pct = (wins / trades * 100.0) if trades > 0 else None
        avg_hold_minutes = (
            bucket["hold_sum"] / bucket["hold_count"] if bucket["hold_count"] > 0 else None
        )
        db.add(
            StrategyMetric(
                run_id=run.id,
                strategy=strategy,
                trades=trades,
                wins=wins,
                losses=losses,
                win_rate_pct=round(win_rate_pct, 2) if win_rate_pct is not None else None,
                pnl_usdt=bucket["pnl_sum"],
                avg_hold_minutes=avg_hold_minutes,
            )
        )
    db.flush()


def _rebuild_regime_metrics_for_run(db: Session, run: Run) -> None:
    regime_events = db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run.id, RunEvent.event_type == "regime_update")
        .order_by(RunEvent.ts.asc(), RunEvent.created_at.asc(), RunEvent.id.asc())
    ).scalars().all()
    gate_events = db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run.id, RunEvent.event_type == "gate_enforced")
        .order_by(RunEvent.ts.asc(), RunEvent.created_at.asc(), RunEvent.id.asc())
    ).scalars().all()

    durations: dict[str, float] = defaultdict(float)
    switches: dict[str, int] = defaultdict(int)
    gate_blocks: dict[str, int] = defaultdict(int)

    reference_end = _latest_runtime_event_ts(db, run.id)
    if run.end_ts is not None:
        end_ts = run.end_ts
        if end_ts.tzinfo is None:
            end_ts = end_ts.replace(tzinfo=timezone.utc)
        else:
            end_ts = end_ts.astimezone(timezone.utc)
        if end_ts > reference_end:
            reference_end = end_ts

    normalized_regime_events: list[tuple[str, datetime, bool]] = []
    for row in regime_events:
        payload = _payload_dict(row)
        regime = _normalize_upper(payload.get("regime"))
        if not regime:
            continue
        event_ts = row.ts if row.ts.tzinfo is not None else row.ts.replace(tzinfo=timezone.utc)
        normalized_regime_events.append((regime, event_ts, bool(payload.get("changed"))))

    for idx, (regime, ts_value, changed) in enumerate(normalized_regime_events):
        next_ts = reference_end
        if idx + 1 < len(normalized_regime_events):
            next_ts = normalized_regime_events[idx + 1][1]
        duration_seconds = max((next_ts - ts_value).total_seconds(), 0.0)
        durations[regime] += duration_seconds
        if changed:
            switches[regime] += 1

    for row in gate_events:
        payload = _payload_dict(row)
        if str(payload.get("gate_type") or "").strip().lower() != "regime":
            continue
        regime = _normalize_upper(payload.get("regime")) or "UNKNOWN"
        gate_blocks[regime] += 1

    total_duration = sum(durations.values())
    db.execute(delete(RegimeMetric).where(RegimeMetric.run_id == run.id))
    for regime in sorted(set(durations) | set(switches) | set(gate_blocks)):
        time_pct = (durations[regime] / total_duration * 100.0) if total_duration > 0 else None
        db.add(
            RegimeMetric(
                run_id=run.id,
                regime=regime,
                time_pct=round(time_pct, 2) if time_pct is not None else None,
                switches=int(switches.get(regime, 0)),
                gate_blocks=int(gate_blocks.get(regime, 0)),
            )
        )
    db.flush()


def materialize_run_entities_for_event(db: Session, run: Run, event: RunEvent) -> None:
    event_type = str(event.event_type or "").strip().lower()
    _sync_bot_config_for_event(db, run, event)
    _sync_equity_snapshot_for_event(db, run, event)

    if event_type == "trade_open":
        _sync_trade_open_for_event(db, run, event)
    elif event_type == "trade_close":
        _sync_trade_close_for_event(db, run, event)
        _rebuild_strategy_metrics_for_run(db, run)

    if event_type == "heartbeat":
        _sync_position_snapshot_for_event(db, run, event)
        _rebuild_regime_metrics_for_run(db, run)
    elif event_type in {"regime_update", "gate_enforced", "status_update"}:
        _rebuild_regime_metrics_for_run(db, run)
