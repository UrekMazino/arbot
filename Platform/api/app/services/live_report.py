from __future__ import annotations

import csv
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import BotConfig, EquitySnapshot, PositionSnapshot, RegimeMetric, Run, RunEvent, StrategyMetric, Trade
from .run_runtime import get_run_runtime_snapshot


def _workspace_root() -> Path:
    explicit = str(os.getenv("BOT_CONTROL_WORKSPACE_ROOT", "")).strip()
    if explicit:
        return Path(explicit).resolve()
    docker_root = Path("/workspace")
    if docker_root.exists():
        return docker_root.resolve()
    return Path(__file__).resolve().parents[4]


WORKSPACE_ROOT = _workspace_root()
REPORTS_ROOT = WORKSPACE_ROOT / "Reports" / "v1"


def _coerce_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_bool(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _coerce_timestamp(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def _remove_if_exists(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception:
        return


def _artifact(path: Path, fmt: str, rows: int) -> dict:
    return {"name": path.name, "path": str(path), "format": fmt, "rows": rows}


def _normalize_key(value: object) -> str:
    return str(value or "").strip().upper()


def _trade_event_lookup(rows: list[RunEvent]) -> dict[tuple[str, str], dict]:
    lookup: dict[tuple[str, str], dict] = {}
    for row in rows:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        pair_key = _normalize_key(payload.get("pair"))
        lookup[(_coerce_timestamp(row.ts), pair_key)] = payload
    return lookup


def _build_trade_rows_from_events(rows: list[RunEvent]) -> list[dict]:
    trade_rows: list[dict] = []
    for row in rows:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        trade_rows.append(
            {
                "timestamp": _coerce_timestamp(row.ts),
                "pair": str(payload.get("pair") or "").strip(),
                "side": str(payload.get("side") or "").strip(),
                "entry_ts": str(payload.get("entry_ts") or "").strip(),
                "exit_ts": _coerce_timestamp(row.ts),
                "entry_z": _coerce_float(payload.get("entry_z")),
                "exit_z": _coerce_float(payload.get("exit_z")),
                "pnl_usdt": _coerce_float(payload.get("pnl_usdt")),
                "pnl_pct": _coerce_float(payload.get("pnl_pct")),
                "strategy": str(payload.get("strategy") or "").strip(),
                "regime": str(payload.get("regime") or "").strip(),
                "entry_strategy": str(payload.get("entry_strategy") or "").strip(),
                "entry_regime": str(payload.get("entry_regime") or "").strip(),
                "hold_minutes": _coerce_float(payload.get("hold_minutes")),
                "exit_reason": str(payload.get("exit_reason") or "").strip(),
                "exit_tier": str(payload.get("exit_tier") or "").strip(),
                "entry_z_threshold_used": _coerce_float(payload.get("entry_z_threshold_used")),
                "size_multiplier_used": _coerce_float(payload.get("size_multiplier_used")),
                "entry_notional_usdt": _coerce_float(payload.get("entry_notional_usdt")),
                "ending_equity_usdt": _coerce_float(payload.get("ending_equity_usdt")),
                "session_pnl_usdt": _coerce_float(payload.get("session_pnl_usdt")),
                "session_pnl_pct": _coerce_float(payload.get("session_pnl_pct")),
                "max_favorable_pnl_usdt": _coerce_float(payload.get("max_favorable_pnl_usdt")),
                "max_adverse_pnl_usdt": _coerce_float(payload.get("max_adverse_pnl_usdt")),
                "z_at_max_favorable_pnl": _coerce_float(payload.get("z_at_max_favorable_pnl")),
                "z_at_max_adverse_pnl": _coerce_float(payload.get("z_at_max_adverse_pnl")),
                "timestamp_at_max_favorable_pnl": _coerce_float(payload.get("timestamp_at_max_favorable_pnl")),
                "timestamp_at_max_adverse_pnl": _coerce_float(payload.get("timestamp_at_max_adverse_pnl")),
                "guard_floor_at_max_favorable_pnl": _coerce_float(payload.get("guard_floor_at_max_favorable_pnl")),
                "full_tp_touched": _coerce_bool(payload.get("full_tp_touched")),
                "guard_blocked_full_tp_count": _coerce_int(payload.get("guard_blocked_full_tp_count")),
                "partial_exit_before_full_tp": _coerce_bool(payload.get("partial_exit_before_full_tp")),
            }
        )
    return trade_rows


def _build_trade_rows_from_models(trades: list[Trade], event_lookup: dict[tuple[str, str], dict]) -> list[dict]:
    trade_rows: list[dict] = []
    for trade in trades:
        exit_ts_text = _coerce_timestamp(trade.exit_ts)
        pair_key = str(trade.pair_key or "").strip()
        payload = event_lookup.get((exit_ts_text, _normalize_key(pair_key)), {})
        trade_rows.append(
            {
                "timestamp": exit_ts_text or _coerce_timestamp(trade.entry_ts),
                "pair": pair_key,
                "side": str(trade.side or payload.get("side") or "").strip(),
                "entry_ts": _coerce_timestamp(trade.entry_ts),
                "exit_ts": exit_ts_text,
                "entry_z": _coerce_float(trade.entry_z),
                "exit_z": _coerce_float(trade.exit_z)
                if _coerce_float(trade.exit_z) is not None
                else _coerce_float(payload.get("exit_z")),
                "pnl_usdt": _coerce_float(trade.pnl_usdt),
                "pnl_pct": _coerce_float(payload.get("pnl_pct")),
                "strategy": str(trade.strategy or payload.get("strategy") or "").strip(),
                "regime": str(trade.regime or payload.get("regime") or "").strip(),
                "entry_strategy": str(trade.entry_strategy or payload.get("entry_strategy") or "").strip(),
                "entry_regime": str(trade.entry_regime or payload.get("entry_regime") or "").strip(),
                "hold_minutes": _coerce_float(trade.hold_minutes),
                "exit_reason": str(trade.exit_reason or payload.get("exit_reason") or "").strip(),
                "exit_tier": str(trade.exit_tier or payload.get("exit_tier") or "").strip(),
                "entry_z_threshold_used": _coerce_float(trade.entry_z_threshold_used),
                "size_multiplier_used": _coerce_float(trade.size_multiplier_used),
                "entry_notional_usdt": _coerce_float(payload.get("entry_notional_usdt")),
                "ending_equity_usdt": _coerce_float(payload.get("ending_equity_usdt")),
                "session_pnl_usdt": _coerce_float(payload.get("session_pnl_usdt")),
                "session_pnl_pct": _coerce_float(payload.get("session_pnl_pct")),
                "max_favorable_pnl_usdt": _coerce_float(payload.get("max_favorable_pnl_usdt")),
                "max_adverse_pnl_usdt": _coerce_float(payload.get("max_adverse_pnl_usdt")),
                "z_at_max_favorable_pnl": _coerce_float(payload.get("z_at_max_favorable_pnl")),
                "z_at_max_adverse_pnl": _coerce_float(payload.get("z_at_max_adverse_pnl")),
                "timestamp_at_max_favorable_pnl": _coerce_float(payload.get("timestamp_at_max_favorable_pnl")),
                "timestamp_at_max_adverse_pnl": _coerce_float(payload.get("timestamp_at_max_adverse_pnl")),
                "guard_floor_at_max_favorable_pnl": _coerce_float(payload.get("guard_floor_at_max_favorable_pnl")),
                "full_tp_touched": _coerce_bool(payload.get("full_tp_touched")),
                "guard_blocked_full_tp_count": _coerce_int(payload.get("guard_blocked_full_tp_count")),
                "partial_exit_before_full_tp": _coerce_bool(payload.get("partial_exit_before_full_tp")),
            }
        )
    return trade_rows


def _build_open_trade_rows_from_models(trades: list[Trade]) -> list[dict]:
    open_rows: list[dict] = []
    for trade in trades:
        open_rows.append(
            {
                "timestamp": _coerce_timestamp(trade.entry_ts),
                "pair": str(trade.pair_key or "").strip(),
                "side": str(trade.side or "").strip(),
                "entry_ts": _coerce_timestamp(trade.entry_ts),
                "entry_z": _coerce_float(trade.entry_z),
                "strategy": str(trade.strategy or "").strip(),
                "regime": str(trade.regime or "").strip(),
                "entry_strategy": str(trade.entry_strategy or "").strip(),
                "entry_regime": str(trade.entry_regime or "").strip(),
                "entry_z_threshold_used": _coerce_float(trade.entry_z_threshold_used),
                "size_multiplier_used": _coerce_float(trade.size_multiplier_used),
            }
        )
    return open_rows


def _build_open_trade_rows_from_events(rows: list[RunEvent]) -> list[dict]:
    open_rows: list[dict] = []
    for row in rows:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        open_rows.append(
            {
                "timestamp": _coerce_timestamp(row.ts),
                "pair": str(payload.get("pair") or "").strip(),
                "side": str(payload.get("side") or "").strip(),
                "entry_ts": str(payload.get("entry_ts") or "").strip(),
                "entry_z": _coerce_float(payload.get("entry_z")),
                "strategy": str(payload.get("strategy") or "").strip(),
                "regime": str(payload.get("regime") or "").strip(),
                "entry_strategy": str(payload.get("entry_strategy") or "").strip(),
                "entry_regime": str(payload.get("entry_regime") or "").strip(),
                "entry_z_threshold_used": _coerce_float(payload.get("entry_z_threshold_used")),
                "size_multiplier_used": _coerce_float(payload.get("size_multiplier_used")),
            }
        )
    return open_rows


def _derive_strategy_metrics_from_trades(trade_rows: list[dict]) -> list[dict]:
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
    for row in trade_rows:
        strategy = _normalize_key(row.get("entry_strategy") or row.get("strategy")) or "UNKNOWN"
        bucket = aggregates[strategy]
        bucket["trades"] += 1.0
        pnl_usdt = _coerce_float(row.get("pnl_usdt"))
        if pnl_usdt is not None:
            bucket["pnl_sum"] += pnl_usdt
            if pnl_usdt > 0:
                bucket["wins"] += 1.0
            elif pnl_usdt < 0:
                bucket["losses"] += 1.0
        hold_minutes = _coerce_float(row.get("hold_minutes"))
        if hold_minutes is not None:
            bucket["hold_sum"] += hold_minutes
            bucket["hold_count"] += 1.0

    output: list[dict] = []
    for strategy in sorted(aggregates):
        bucket = aggregates[strategy]
        trades = int(bucket["trades"])
        wins = int(bucket["wins"])
        losses = int(bucket["losses"])
        win_rate_pct = (wins / trades * 100.0) if trades > 0 else None
        output.append(
            {
                "strategy": strategy,
                "trades": trades,
                "wins": wins,
                "losses": losses,
                "win_rate_pct": round(win_rate_pct, 2) if win_rate_pct is not None else None,
                "pnl_usdt": bucket["pnl_sum"],
                "avg_hold_minutes": (
                    bucket["hold_sum"] / bucket["hold_count"] if bucket["hold_count"] > 0 else None
                ),
            }
        )
    return output


def _derive_regime_metrics_from_events(db: Session, run: Run) -> list[dict]:
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
    latest_event = db.execute(
        select(RunEvent.ts)
        .where(RunEvent.run_id == run.id)
        .order_by(RunEvent.ts.desc(), RunEvent.created_at.desc(), RunEvent.id.desc())
        .limit(1)
    ).first()

    durations: dict[str, float] = defaultdict(float)
    switches: dict[str, int] = defaultdict(int)
    gate_blocks: dict[str, int] = defaultdict(int)

    reference_end = datetime.now(timezone.utc)
    if latest_event and latest_event[0] is not None:
        reference_end = latest_event[0]
        if reference_end.tzinfo is None:
            reference_end = reference_end.replace(tzinfo=timezone.utc)
        else:
            reference_end = reference_end.astimezone(timezone.utc)
    if run.end_ts is not None:
        end_ts = run.end_ts if run.end_ts.tzinfo is not None else run.end_ts.replace(tzinfo=timezone.utc)
        end_ts = end_ts.astimezone(timezone.utc)
        if end_ts > reference_end:
            reference_end = end_ts

    normalized_regimes: list[tuple[str, datetime, bool]] = []
    for row in regime_events:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        regime = _normalize_key(payload.get("regime"))
        if not regime:
            continue
        ts_value = row.ts if row.ts.tzinfo is not None else row.ts.replace(tzinfo=timezone.utc)
        ts_value = ts_value.astimezone(timezone.utc)
        normalized_regimes.append((regime, ts_value, bool(payload.get("changed"))))

    for idx, (regime, ts_value, changed) in enumerate(normalized_regimes):
        next_ts = reference_end
        if idx + 1 < len(normalized_regimes):
            next_ts = normalized_regimes[idx + 1][1]
        durations[regime] += max((next_ts - ts_value).total_seconds(), 0.0)
        if changed:
            switches[regime] += 1

    for row in gate_events:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        if str(payload.get("gate_type") or "").strip().lower() != "regime":
            continue
        regime = _normalize_key(payload.get("regime")) or "UNKNOWN"
        gate_blocks[regime] += 1

    total_duration = sum(durations.values())
    output: list[dict] = []
    for regime in sorted(set(durations) | set(switches) | set(gate_blocks)):
        time_pct = (durations[regime] / total_duration * 100.0) if total_duration > 0 else None
        output.append(
            {
                "regime": regime,
                "time_pct": round(time_pct, 2) if time_pct is not None else None,
                "switches": int(switches.get(regime, 0)),
                "gate_blocks": int(gate_blocks.get(regime, 0)),
            }
        )
    return output


def _event_payload(row: RunEvent) -> dict:
    return row.payload_json if isinstance(row.payload_json, dict) else {}


def _json_text(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True)
    except Exception:
        return str(value)


def _build_liquidity_check_rows(rows: list[RunEvent]) -> list[dict]:
    output: list[dict] = []
    for row in rows:
        payload = _event_payload(row)
        output.append(
            {
                "timestamp": _coerce_timestamp(row.ts),
                "pair": str(payload.get("pair") or "").strip(),
                "strategy": str(payload.get("strategy") or "").strip(),
                "regime": str(payload.get("regime") or "").strip(),
                "long_ticker": str(payload.get("long_ticker") or "").strip(),
                "short_ticker": str(payload.get("short_ticker") or "").strip(),
                "status": str(payload.get("status") or "").strip(),
                "target_usdt": _coerce_float(payload.get("target_usdt")),
                "liquidity_long_usdt": _coerce_float(payload.get("liquidity_long_usdt")),
                "liquidity_short_usdt": _coerce_float(payload.get("liquidity_short_usdt")),
                "ratio_long": _coerce_float(payload.get("ratio_long")),
                "ratio_short": _coerce_float(payload.get("ratio_short")),
                "min_ratio": _coerce_float(payload.get("min_ratio")),
                "selected_ratio": _coerce_float(payload.get("selected_ratio")),
                "fallback_used": bool(payload.get("fallback_used")),
                "downsized": bool(payload.get("downsized")),
                "attempt_count": payload.get("attempt_count"),
                "reason": str(payload.get("reason") or "").strip(),
            }
        )
    return output


def _build_fill_summary_rows(rows: list[RunEvent]) -> list[dict]:
    output: list[dict] = []
    for row in rows:
        payload = _event_payload(row)
        output.append(
            {
                "timestamp": _coerce_timestamp(row.ts),
                "pair": str(payload.get("pair") or "").strip(),
                "strategy": str(payload.get("strategy") or "").strip(),
                "regime": str(payload.get("regime") or "").strip(),
                "ticker": str(payload.get("ticker") or "").strip(),
                "side": str(payload.get("side") or "").strip(),
                "order_id": str(payload.get("order_id") or "").strip(),
                "preview_price": _coerce_float(payload.get("preview_price")),
                "fill_price": _coerce_float(payload.get("fill_price")),
                "filled_qty": _coerce_float(payload.get("filled_qty")),
                "fill_count": payload.get("fill_count"),
                "fee_usdt": _coerce_float(payload.get("fee_usdt")),
                "fill_pnl_usdt": _coerce_float(payload.get("fill_pnl_usdt")),
                "slippage_bps": _coerce_float(payload.get("slippage_bps")),
                "abs_slippage_bps": _coerce_float(payload.get("abs_slippage_bps")),
            }
        )
    return output


def _build_reconciliation_rows(rows: list[RunEvent]) -> list[dict]:
    output: list[dict] = []
    for row in rows:
        payload = _event_payload(row)
        output.append(
            {
                "timestamp": _coerce_timestamp(row.ts),
                "pair": str(payload.get("pair") or "").strip(),
                "strategy": str(payload.get("strategy") or "").strip(),
                "regime": str(payload.get("regime") or "").strip(),
                "entry_ts": str(payload.get("entry_ts") or "").strip(),
                "exit_reason": str(payload.get("exit_reason") or "").strip(),
                "trade_pnl": _coerce_float(payload.get("trade_pnl")),
                "equity_change": _coerce_float(payload.get("equity_change")),
                "difference": _coerce_float(payload.get("difference")),
                "fees": _coerce_float(payload.get("fees")),
                "slippage": _coerce_float(payload.get("slippage")),
                "funding": _coerce_float(payload.get("funding")),
                "unexplained": _coerce_float(payload.get("unexplained")),
                "basis": str(payload.get("basis") or "").strip(),
                "delta_warn_threshold": _coerce_float(payload.get("delta_warn_threshold")),
                "unexplained_warn_threshold": _coerce_float(payload.get("unexplained_warn_threshold")),
                "unexplained_pct_warn_threshold": _coerce_float(payload.get("unexplained_pct_warn_threshold")),
                "unexplained_pct": _coerce_float(payload.get("unexplained_pct")),
                "large_delta_warning": bool(payload.get("large_delta_warning")),
                "large_unexplained_warning": bool(payload.get("large_unexplained_warning")),
                "post_close_equity_available": bool(payload.get("post_close_equity_available")),
                "pass_fail": str(payload.get("pass_fail") or "").strip(),
            }
        )
    return output


def _build_entry_rejection_rows(rows: list[RunEvent]) -> list[dict]:
    output: list[dict] = []
    for row in rows:
        payload = _event_payload(row)
        output.append(
            {
                "timestamp": _coerce_timestamp(row.ts),
                "pair": str(payload.get("pair") or "").strip(),
                "strategy": str(payload.get("strategy") or "").strip(),
                "regime": str(payload.get("regime") or "").strip(),
                "reject_type": str(payload.get("reject_type") or "").strip(),
                "reason": str(payload.get("reason") or "").strip(),
                "long_ticker": str(payload.get("long_ticker") or "").strip(),
                "short_ticker": str(payload.get("short_ticker") or "").strip(),
                "target_usdt": _coerce_float(payload.get("target_usdt")),
                "liquidity_long_usdt": _coerce_float(payload.get("liquidity_long_usdt")),
                "liquidity_short_usdt": _coerce_float(payload.get("liquidity_short_usdt")),
                "ratio_long": _coerce_float(payload.get("ratio_long")),
                "ratio_short": _coerce_float(payload.get("ratio_short")),
                "min_ratio": _coerce_float(payload.get("min_ratio")),
                "available_usdt": _coerce_float(payload.get("available_usdt")),
                "total_notional_usdt": _coerce_float(payload.get("total_notional_usdt")),
                "action": str(payload.get("action") or "").strip(),
                "long_error": str(payload.get("long_error") or "").strip(),
                "short_error": str(payload.get("short_error") or "").strip(),
            }
        )
    return output


def _build_alert_rows(rows: list[RunEvent]) -> list[dict]:
    output: list[dict] = []
    for row in rows:
        payload = _event_payload(row)
        output.append(
            {
                "timestamp": _coerce_timestamp(row.ts),
                "event_type": str(row.event_type or "").strip(),
                "severity": str(row.severity or "").strip(),
                "pair": str(payload.get("pair") or "").strip(),
                "strategy": str(payload.get("strategy") or "").strip(),
                "regime": str(payload.get("regime") or "").strip(),
                "alert_type": str(payload.get("alert_type") or "").strip(),
                "warning_type": str(payload.get("warning_type") or "").strip(),
                "message": str(payload.get("message") or "").strip(),
                "basis": str(payload.get("basis") or "").strip(),
                "difference": _coerce_float(payload.get("difference")),
                "unexplained": _coerce_float(payload.get("unexplained")),
                "unexplained_pct": _coerce_float(payload.get("unexplained_pct")),
                "details_json": _json_text(payload),
            }
        )
    return output


EXIT_DECISION_TRACE_FIELDS = [
    "timestamp",
    "pair",
    "entry_ts",
    "entry_z",
    "current_z",
    "floating_pnl_usdt",
    "base_min_profit_usdt",
    "effective_min_profit_usdt",
    "full_tp_guard_multiplier",
    "take_profit_z",
    "full_tp_zone_hit",
    "trade_manager_guard_passed",
    "full_tp_guard_passed",
    "full_tp_candidate_created",
    "full_tp_candidate_blocked",
    "full_tp_selected",
    "full_tp_blocked_reason",
    "orchestrator_base_min_profit_usdt",
    "orchestrator_effective_min_profit_usdt",
    "orchestrator_guard_multiplier",
    "orchestrator_guard_passed",
    "pnl_profit_lock_enabled",
    "pnl_profit_lock_active",
    "max_favorable_pnl_usdt",
    "pnl_profit_lock_floor",
    "pnl_profit_lock_giveback_pct",
    "pnl_profit_lock_selected",
    "partial_tp_eligible",
    "trailing_stop_eligible",
    "regime_break_eligible",
    "stall_exit_eligible",
    "selected_exit_reason",
    "selected_exit_action",
    "selected_candidate_name",
    "blocked_candidate_names",
    "trade_manager_action",
    "trade_manager_reason",
    "why_full_tp_not_selected",
]


EXIT_DECISION_SUMMARY_FIELDS = [
    "pair",
    "entry_ts",
    "full_tp_zone_eval_count",
    "full_tp_guard_pass_count",
    "full_tp_guard_block_count",
    "full_tp_selected_count",
    "selected_exit_reason",
    "first_full_tp_zone_time",
    "first_full_tp_guard_pass_time",
    "max_pnl_during_full_tp_zone",
    "z_at_max_pnl_during_full_tp_zone",
]


def _build_exit_decision_trace_rows(rows: list[RunEvent]) -> list[dict]:
    output: list[dict] = []
    for row in rows:
        payload = _event_payload(row)
        output.append(
            {
                "timestamp": _coerce_timestamp(row.ts),
                "pair": str(payload.get("pair") or "").strip(),
                "entry_ts": str(payload.get("entry_ts") or "").strip(),
                "entry_z": _coerce_float(payload.get("entry_z")),
                "current_z": _coerce_float(payload.get("current_z")),
                "floating_pnl_usdt": _coerce_float(payload.get("floating_pnl_usdt")),
                "base_min_profit_usdt": _coerce_float(payload.get("base_min_profit_usdt")),
                "effective_min_profit_usdt": _coerce_float(payload.get("effective_min_profit_usdt")),
                "full_tp_guard_multiplier": _coerce_float(payload.get("full_tp_guard_multiplier")),
                "take_profit_z": _coerce_float(payload.get("take_profit_z")),
                "full_tp_zone_hit": _coerce_bool(payload.get("full_tp_zone_hit")),
                "trade_manager_guard_passed": _coerce_bool(payload.get("trade_manager_guard_passed")),
                "full_tp_guard_passed": _coerce_bool(payload.get("full_tp_guard_passed")),
                "full_tp_candidate_created": _coerce_bool(payload.get("full_tp_candidate_created")),
                "full_tp_candidate_blocked": _coerce_bool(payload.get("full_tp_candidate_blocked")),
                "full_tp_selected": _coerce_bool(payload.get("full_tp_selected")),
                "full_tp_blocked_reason": str(payload.get("full_tp_blocked_reason") or "").strip(),
                "orchestrator_base_min_profit_usdt": _coerce_float(
                    payload.get("orchestrator_base_min_profit_usdt")
                ),
                "orchestrator_effective_min_profit_usdt": _coerce_float(
                    payload.get("orchestrator_effective_min_profit_usdt")
                ),
                "orchestrator_guard_multiplier": _coerce_float(payload.get("orchestrator_guard_multiplier")),
                "orchestrator_guard_passed": _coerce_bool(payload.get("orchestrator_guard_passed")),
                "pnl_profit_lock_enabled": _coerce_bool(payload.get("pnl_profit_lock_enabled")),
                "pnl_profit_lock_active": _coerce_bool(payload.get("pnl_profit_lock_active")),
                "max_favorable_pnl_usdt": _coerce_float(payload.get("max_favorable_pnl_usdt")),
                "pnl_profit_lock_floor": _coerce_float(payload.get("pnl_profit_lock_floor")),
                "pnl_profit_lock_giveback_pct": _coerce_float(payload.get("pnl_profit_lock_giveback_pct")),
                "pnl_profit_lock_selected": _coerce_bool(payload.get("pnl_profit_lock_selected")),
                "partial_tp_eligible": _coerce_bool(payload.get("partial_tp_eligible")),
                "trailing_stop_eligible": _coerce_bool(payload.get("trailing_stop_eligible")),
                "regime_break_eligible": _coerce_bool(payload.get("regime_break_eligible")),
                "stall_exit_eligible": _coerce_bool(payload.get("stall_exit_eligible")),
                "selected_exit_reason": str(payload.get("selected_exit_reason") or "").strip(),
                "selected_exit_action": str(payload.get("selected_exit_action") or "").strip(),
                "selected_candidate_name": str(payload.get("selected_candidate_name") or "").strip(),
                "blocked_candidate_names": str(payload.get("blocked_candidate_names") or "").strip(),
                "trade_manager_action": str(payload.get("trade_manager_action") or "").strip(),
                "trade_manager_reason": str(payload.get("trade_manager_reason") or "").strip(),
                "why_full_tp_not_selected": str(payload.get("why_full_tp_not_selected") or "").strip(),
            }
        )
    return output


def _build_exit_decision_summary_rows(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        pair = str(row.get("pair") or "").strip()
        entry_ts = str(row.get("entry_ts") or "").strip()
        grouped[(pair, entry_ts)].append(row)

    output: list[dict] = []
    for (pair, entry_ts), trade_rows in grouped.items():
        zone_rows = [row for row in trade_rows if bool(row.get("full_tp_zone_hit"))]
        guard_pass_rows = [row for row in zone_rows if bool(row.get("full_tp_guard_passed"))]
        guard_block_rows = [
            row
            for row in zone_rows
            if (
                str(row.get("full_tp_blocked_reason") or "").strip()
                or str(row.get("why_full_tp_not_selected") or "").strip()
                in {
                    "net_profit_guard_blocked",
                    "trade_manager_net_profit_guard_blocked",
                    "orchestrator_net_profit_guard_blocked",
                }
            )
        ]
        selected_rows = [
            row
            for row in trade_rows
            if str(row.get("selected_candidate_name") or "").strip() == "trade_manager_take_profit"
        ]
        final_exit_rows = [
            row
            for row in trade_rows
            if str(row.get("selected_exit_action") or "").strip().lower() in {"full_exit", "partial_exit"}
            or str(row.get("selected_candidate_name") or "").strip()
        ]
        selected_exit_reason = ""
        if final_exit_rows:
            last = final_exit_rows[-1]
            selected_exit_reason = (
                str(last.get("selected_candidate_name") or "").strip()
                or str(last.get("selected_exit_reason") or "").strip()
            )

        max_zone_row = None
        for row in zone_rows:
            pnl = _coerce_float(row.get("floating_pnl_usdt"))
            if pnl is None:
                continue
            if max_zone_row is None or pnl > (_coerce_float(max_zone_row.get("floating_pnl_usdt")) or float("-inf")):
                max_zone_row = row

        output.append(
            {
                "pair": pair,
                "entry_ts": entry_ts,
                "full_tp_zone_eval_count": len(zone_rows),
                "full_tp_guard_pass_count": len(guard_pass_rows),
                "full_tp_guard_block_count": len(guard_block_rows),
                "full_tp_selected_count": len(selected_rows),
                "selected_exit_reason": selected_exit_reason,
                "first_full_tp_zone_time": str(zone_rows[0].get("timestamp") or "").strip() if zone_rows else "",
                "first_full_tp_guard_pass_time": (
                    str(guard_pass_rows[0].get("timestamp") or "").strip() if guard_pass_rows else ""
                ),
                "max_pnl_during_full_tp_zone": (
                    _coerce_float(max_zone_row.get("floating_pnl_usdt")) if max_zone_row else None
                ),
                "z_at_max_pnl_during_full_tp_zone": (
                    _coerce_float(max_zone_row.get("current_z")) if max_zone_row else None
                ),
            }
        )
    return output


def materialize_live_run_report(db: Session, run: Run) -> dict:
    run_key = str(run.run_key or "").strip()
    if not run_key:
        return {"saved": False, "detail": "missing_run_key"}

    snapshot = get_run_runtime_snapshot(db, run_key, include_pair_history=True)
    if not snapshot.get("run_key"):
        return {"saved": False, "detail": "runtime_snapshot_unavailable"}

    report_dir = REPORTS_ROOT / run_key
    report_dir.mkdir(parents=True, exist_ok=True)

    event_counts = {
        str(row[0] or "").strip(): int(row[1] or 0)
        for row in db.execute(
            select(RunEvent.event_type, func.count(RunEvent.id))
            .where(RunEvent.run_id == run.id)
            .group_by(RunEvent.event_type)
        ).all()
        if str(row[0] or "").strip()
    }
    severity_counts = {
        str(row[0] or "").strip(): int(row[1] or 0)
        for row in db.execute(
            select(RunEvent.severity, func.count(RunEvent.id))
            .where(RunEvent.run_id == run.id)
            .group_by(RunEvent.severity)
        ).all()
        if str(row[0] or "").strip()
    }

    equity_curve = []
    equity_snapshot_rows = db.execute(
        select(EquitySnapshot)
        .where(EquitySnapshot.run_id == run.id)
        .order_by(EquitySnapshot.ts.asc(), EquitySnapshot.created_at.asc(), EquitySnapshot.id.asc())
    ).scalars().all()
    if equity_snapshot_rows:
        for row in equity_snapshot_rows:
            equity_curve.append(
                {
                    "timestamp": _coerce_timestamp(row.ts),
                    "equity_usdt": _coerce_float(row.equity_usdt),
                    "session_pnl_usdt": _coerce_float(row.session_pnl_usdt),
                    "session_pnl_pct": _coerce_float(row.session_pnl_pct),
                    "pair": str(row.current_pair or "").strip(),
                    "regime": str(row.regime or "").strip(),
                    "strategy": str(row.strategy or "").strip(),
                    "in_position": bool(row.in_position),
                    "entry_z": _coerce_float(row.entry_z),
                    "current_z": _coerce_float(row.current_z),
                    "hold_minutes": _coerce_float(row.hold_minutes),
                    "unrealized_pnl_usdt": _coerce_float(row.unrealized_pnl_usdt),
                    "source": str(row.source or "").strip(),
                }
            )
    else:
        heartbeat_rows = db.execute(
            select(RunEvent)
            .where(RunEvent.run_id == run.id, RunEvent.event_type == "heartbeat")
            .order_by(RunEvent.ts.asc(), RunEvent.created_at.asc(), RunEvent.id.asc())
        ).scalars().all()
        starting_equity = _coerce_float(snapshot.get("starting_equity"))
        for row in heartbeat_rows:
            payload = row.payload_json if isinstance(row.payload_json, dict) else {}
            equity_usdt = _coerce_float(payload.get("equity_usdt"))
            session_pnl_usdt = _coerce_float(payload.get("session_pnl_usdt"))
            session_pnl_pct = _coerce_float(payload.get("session_pnl_pct"))
            if equity_usdt is not None and starting_equity is not None:
                session_pnl_usdt = equity_usdt - starting_equity
                session_pnl_pct = (session_pnl_usdt / starting_equity * 100.0) if starting_equity > 0 else None
            equity_curve.append(
                {
                    "timestamp": _coerce_timestamp(row.ts),
                    "equity_usdt": equity_usdt,
                    "session_pnl_usdt": session_pnl_usdt,
                    "session_pnl_pct": session_pnl_pct,
                    "pair": str(payload.get("current_pair") or payload.get("pair") or "").strip(),
                    "regime": str(payload.get("regime") or "").strip(),
                    "strategy": str(payload.get("strategy") or "").strip(),
                    "in_position": bool(payload.get("in_position")),
                    "entry_z": _coerce_float(payload.get("entry_z")),
                    "current_z": _coerce_float(payload.get("current_z")),
                    "hold_minutes": _coerce_float(payload.get("hold_minutes")),
                    "unrealized_pnl_usdt": _coerce_float(payload.get("unrealized_pnl_usdt")),
                    "source": "heartbeat_event",
                }
            )

    trade_close_events = db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run.id, RunEvent.event_type == "trade_close")
        .order_by(RunEvent.ts.asc(), RunEvent.created_at.asc(), RunEvent.id.asc())
    ).scalars().all()
    trade_open_events = db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run.id, RunEvent.event_type == "trade_open")
        .order_by(RunEvent.ts.asc(), RunEvent.created_at.asc(), RunEvent.id.asc())
    ).scalars().all()
    trade_event_lookup = _trade_event_lookup(trade_close_events)
    all_model_trades = db.execute(
        select(Trade)
        .where(Trade.run_id == run.id)
        .order_by(Trade.entry_ts.asc(), Trade.exit_ts.asc(), Trade.id.asc())
    ).scalars().all()
    model_trades = [trade for trade in all_model_trades if trade.exit_ts is not None]
    open_model_trades = [trade for trade in all_model_trades if trade.exit_ts is None]

    if model_trades:
        trade_rows = _build_trade_rows_from_models(model_trades, trade_event_lookup)
        trades_source = "trades_table"
    else:
        trade_rows = _build_trade_rows_from_events(trade_close_events)
        trades_source = "trade_close_events"
    open_trade_rows = _build_open_trade_rows_from_models(open_model_trades)
    if not open_trade_rows and trade_open_events and len(trade_open_events) > len(trade_rows):
        open_trade_rows = _build_open_trade_rows_from_events(trade_open_events[len(trade_rows):])

    liquidity_check_events = db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run.id, RunEvent.event_type == "liquidity_check")
        .order_by(RunEvent.ts.asc(), RunEvent.created_at.asc(), RunEvent.id.asc())
    ).scalars().all()
    liquidity_check_rows = _build_liquidity_check_rows(liquidity_check_events)

    fill_summary_events = db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run.id, RunEvent.event_type == "fill_summary")
        .order_by(RunEvent.ts.asc(), RunEvent.created_at.asc(), RunEvent.id.asc())
    ).scalars().all()
    fill_summary_rows = _build_fill_summary_rows(
        [
            row
            for row in fill_summary_events
            if str(_event_payload(row).get("fill_kind") or "").strip().lower() == "entry"
        ]
    )

    reconciliation_events = db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run.id, RunEvent.event_type == "reconciliation_check")
        .order_by(RunEvent.ts.asc(), RunEvent.created_at.asc(), RunEvent.id.asc())
    ).scalars().all()
    reconciliation_rows = _build_reconciliation_rows(reconciliation_events)

    entry_reject_events = db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run.id, RunEvent.event_type == "entry_reject")
        .order_by(RunEvent.ts.asc(), RunEvent.created_at.asc(), RunEvent.id.asc())
    ).scalars().all()
    entry_rejection_rows = _build_entry_rejection_rows(entry_reject_events)

    alert_events = db.execute(
        select(RunEvent)
        .where(
            RunEvent.run_id == run.id,
            RunEvent.event_type.in_(("risk_alert", "data_quality_warning", "reconciliation_warning")),
        )
        .order_by(RunEvent.ts.asc(), RunEvent.created_at.asc(), RunEvent.id.asc())
    ).scalars().all()
    alert_rows = _build_alert_rows(alert_events)

    exit_decision_trace_events = db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run.id, RunEvent.event_type == "exit_decision_trace")
        .order_by(RunEvent.ts.asc(), RunEvent.created_at.asc(), RunEvent.id.asc())
    ).scalars().all()
    exit_decision_trace_rows = _build_exit_decision_trace_rows(exit_decision_trace_events)
    exit_decision_summary_rows = _build_exit_decision_summary_rows(exit_decision_trace_rows)

    wins = 0
    losses = 0
    for row in trade_rows:
        pnl_usdt = _coerce_float(row.get("pnl_usdt"))
        if pnl_usdt is None:
            continue
        if pnl_usdt > 0:
            wins += 1
        elif pnl_usdt < 0:
            losses += 1
    closed_trades_total = len(trade_rows)
    open_trades_total = len(open_trade_rows)
    trade_opens_total = max(len(trade_open_events), len(all_model_trades), closed_trades_total)
    trades_total = max(trade_opens_total, closed_trades_total + open_trades_total)
    win_rate_pct = round((wins / closed_trades_total) * 100.0, 2) if closed_trades_total > 0 else None

    pair_switches = 0
    gate_blocks = 0
    for row in db.execute(
        select(RunEvent)
        .where(
            RunEvent.run_id == run.id,
            RunEvent.event_type.in_(("pair_switch", "gate_enforced")),
        )
        .order_by(RunEvent.ts.asc(), RunEvent.created_at.asc(), RunEvent.id.asc())
    ).scalars().all():
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        if row.event_type == "pair_switch":
            status_text = str(payload.get("status") or "").strip().lower()
            if status_text == "switched":
                pair_switches += 1
        elif row.event_type == "gate_enforced":
            gate_blocks += 1

    pair_history_rows = [
        {
            "sequence_no": row.get("sequence_no"),
            "pair": row.get("pair"),
            "started_at": row.get("started_at"),
            "ended_at": row.get("ended_at"),
            "switch_reason": row.get("switch_reason"),
            "duration_seconds": row.get("duration_seconds"),
        }
        for row in snapshot.get("pair_history", [])
    ]

    latest_bot_config = db.execute(
        select(BotConfig)
        .where(BotConfig.run_id == run.id)
        .order_by(BotConfig.created_at.desc(), BotConfig.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    config_snapshot = (
        latest_bot_config.config_snapshot_json
        if latest_bot_config and isinstance(latest_bot_config.config_snapshot_json, dict)
        else None
    )
    config_source = "bot_configs" if config_snapshot else "none"

    strategy_metric_models = db.execute(
        select(StrategyMetric)
        .where(StrategyMetric.run_id == run.id)
        .order_by(StrategyMetric.strategy.asc(), StrategyMetric.id.asc())
    ).scalars().all()
    if strategy_metric_models:
        strategy_metric_rows = [
            {
                "strategy": str(row.strategy or "").strip(),
                "trades": int(row.trades or 0),
                "wins": int(row.wins or 0),
                "losses": int(row.losses or 0),
                "win_rate_pct": _coerce_float(row.win_rate_pct),
                "pnl_usdt": _coerce_float(row.pnl_usdt),
                "avg_hold_minutes": _coerce_float(row.avg_hold_minutes),
            }
            for row in strategy_metric_models
        ]
        strategy_metrics_source = "strategy_metrics"
    else:
        strategy_metric_rows = _derive_strategy_metrics_from_trades(trade_rows)
        strategy_metrics_source = "trades_derived"

    regime_metric_models = db.execute(
        select(RegimeMetric)
        .where(RegimeMetric.run_id == run.id)
        .order_by(RegimeMetric.regime.asc(), RegimeMetric.id.asc())
    ).scalars().all()
    if regime_metric_models:
        regime_metric_rows = [
            {
                "regime": str(row.regime or "").strip(),
                "time_pct": _coerce_float(row.time_pct),
                "switches": int(row.switches or 0),
                "gate_blocks": int(row.gate_blocks or 0),
            }
            for row in regime_metric_models
        ]
        regime_metrics_source = "regime_metrics"
    else:
        regime_metric_rows = _derive_regime_metrics_from_events(db, run)
        regime_metrics_source = "events_derived"

    position_snapshot_models = db.execute(
        select(PositionSnapshot)
        .where(PositionSnapshot.run_id == run.id)
        .order_by(PositionSnapshot.ts.asc(), PositionSnapshot.id.asc())
    ).scalars().all()
    position_snapshot_rows = [
        {
            "timestamp": _coerce_timestamp(row.ts),
            "pair": str(row.pair_key or "").strip(),
            "notional_usdt": _coerce_float(row.notional_usdt),
            "unrealized_pnl_usdt": _coerce_float(row.unrealized_pnl_usdt),
            "entry_z": _coerce_float(row.entry_z),
            "current_z": _coerce_float(row.current_z),
            "hold_minutes": _coerce_float(row.hold_minutes),
        }
        for row in position_snapshot_models
    ]
    position_snapshots_source = "position_snapshots" if position_snapshot_rows else "none"

    data_sources = {
        "runtime": "events_db",
        "equity_curve": "equity_snapshots" if equity_snapshot_rows else "heartbeat_events" if equity_curve else "none",
        "trades": trades_source,
        "open_trades": "trades_table" if open_model_trades else "trade_open_events" if open_trade_rows else "none",
        "config": config_source,
        "strategy_metrics": strategy_metrics_source,
        "regime_metrics": regime_metrics_source,
        "position_snapshots": position_snapshots_source,
        "liquidity_checks": "liquidity_check_events" if liquidity_check_rows else "none",
        "entry_slippage": "fill_summary_events" if fill_summary_rows else "none",
        "reconciliation_checks": "reconciliation_check_events" if reconciliation_rows else "none",
        "entry_rejections": "entry_reject_events" if entry_rejection_rows else "none",
        "alerts": "risk_and_warning_events" if alert_rows else "none",
        "exit_decision_trace": "exit_decision_trace_events" if exit_decision_trace_rows else "none",
    }
    summary = {
        "report_version": "v2-live",
        "report_source": "events_db_materialized",
        "run_id": snapshot.get("run_id"),
        "run_key": snapshot.get("run_key"),
        "status": snapshot.get("status"),
        "running": snapshot.get("running"),
        "start_time": snapshot.get("started_at"),
        "end_time": snapshot.get("stopped_at"),
        "updated_at": snapshot.get("updated_at"),
        "duration_seconds": snapshot.get("duration_seconds"),
        "starting_equity": snapshot.get("starting_equity"),
        "ending_equity": snapshot.get("equity"),
        "session_pnl": snapshot.get("session_pnl"),
        "session_pnl_pct": snapshot.get("session_pnl_pct"),
        "current_pair": snapshot.get("current_pair"),
        "latest_regime": snapshot.get("latest_regime"),
        "latest_strategy": snapshot.get("latest_strategy"),
        "pair_count": snapshot.get("pair_count"),
        "pair_switches": pair_switches,
        "gate_blocks": gate_blocks,
        "trades_total": trades_total,
        "trade_opens_total": trade_opens_total,
        "open_trades_total": open_trades_total,
        "closed_trades_total": closed_trades_total,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": win_rate_pct,
        "win_rate_basis": "closed_trades",
        "strategy_metric_rows": len(strategy_metric_rows),
        "regime_metric_rows": len(regime_metric_rows),
        "position_snapshot_rows": len(position_snapshot_rows),
        "liquidity_check_rows": len(liquidity_check_rows),
        "entry_slippage_rows": len(fill_summary_rows),
        "reconciliation_rows": len(reconciliation_rows),
        "entry_rejection_rows": len(entry_rejection_rows),
        "alert_rows": len(alert_rows),
        "exit_decision_trace_rows": len(exit_decision_trace_rows),
        "exit_decision_summary_rows": len(exit_decision_summary_rows),
        "event_counts": event_counts,
        "severity_counts": severity_counts,
        "data_sources": data_sources,
        "report_created_at": datetime.now(timezone.utc).isoformat(),
    }

    summary_path = report_dir / "summary.json"
    equity_curve_path = report_dir / "equity_curve.csv"
    pair_history_path = report_dir / "pair_history.csv"
    trade_closes_path = report_dir / "trade_closes.csv"
    open_trades_path = report_dir / "open_trades.csv"
    event_counts_path = report_dir / "event_counts.json"
    config_snapshot_path = report_dir / "config_snapshot.json"
    strategy_metrics_path = report_dir / "strategy_metrics.csv"
    regime_metrics_path = report_dir / "regime_metrics.csv"
    position_snapshots_path = report_dir / "position_snapshots.csv"
    liquidity_checks_path = report_dir / "liquidity_checks.csv"
    entry_slippage_path = report_dir / "entry_slippage.csv"
    reconciliation_checks_path = report_dir / "reconciliation_checks.csv"
    entry_rejections_path = report_dir / "entry_rejections.csv"
    risk_alerts_path = report_dir / "risk_alerts.csv"
    exit_decision_trace_path = report_dir / "exit_decision_trace.csv"
    exit_decision_summary_path = report_dir / "exit_decision_summary.csv"
    manifest_path = report_dir / "report_manifest.json"

    _write_csv(
        equity_curve_path,
        equity_curve,
        [
            "timestamp",
            "equity_usdt",
            "session_pnl_usdt",
            "session_pnl_pct",
            "pair",
            "regime",
            "strategy",
            "in_position",
            "entry_z",
            "current_z",
            "hold_minutes",
            "unrealized_pnl_usdt",
            "source",
        ],
    )
    _write_csv(
        pair_history_path,
        pair_history_rows,
        ["sequence_no", "pair", "started_at", "ended_at", "switch_reason", "duration_seconds"],
    )
    _write_csv(
        trade_closes_path,
        trade_rows,
        [
            "timestamp",
            "pair",
            "side",
            "entry_ts",
            "exit_ts",
            "entry_z",
            "exit_z",
            "pnl_usdt",
            "pnl_pct",
            "strategy",
            "regime",
            "entry_strategy",
            "entry_regime",
            "hold_minutes",
            "exit_reason",
            "exit_tier",
            "entry_z_threshold_used",
            "size_multiplier_used",
            "entry_notional_usdt",
            "ending_equity_usdt",
            "session_pnl_usdt",
            "session_pnl_pct",
            "max_favorable_pnl_usdt",
            "max_adverse_pnl_usdt",
            "z_at_max_favorable_pnl",
            "z_at_max_adverse_pnl",
            "timestamp_at_max_favorable_pnl",
            "timestamp_at_max_adverse_pnl",
            "guard_floor_at_max_favorable_pnl",
            "full_tp_touched",
            "guard_blocked_full_tp_count",
            "partial_exit_before_full_tp",
        ],
    )
    _write_csv(
        open_trades_path,
        open_trade_rows,
        [
            "timestamp",
            "pair",
            "side",
            "entry_ts",
            "entry_z",
            "strategy",
            "regime",
            "entry_strategy",
            "entry_regime",
            "entry_z_threshold_used",
            "size_multiplier_used",
        ],
    )

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    event_counts_path.write_text(
        json.dumps(
            {
                "event_counts": event_counts,
                "severity_counts": severity_counts,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    artifact_entries = [
        _artifact(summary_path, "json", 1),
        _artifact(equity_curve_path, "csv", len(equity_curve)),
        _artifact(pair_history_path, "csv", len(pair_history_rows)),
        _artifact(trade_closes_path, "csv", len(trade_rows)),
        _artifact(open_trades_path, "csv", len(open_trade_rows)),
        _artifact(event_counts_path, "json", len(event_counts)),
    ]

    if config_snapshot:
        config_snapshot_path.write_text(json.dumps(config_snapshot, indent=2), encoding="utf-8")
        artifact_entries.append(_artifact(config_snapshot_path, "json", 1))
    else:
        _remove_if_exists(config_snapshot_path)

    if strategy_metric_rows:
        _write_csv(
            strategy_metrics_path,
            strategy_metric_rows,
            ["strategy", "trades", "wins", "losses", "win_rate_pct", "pnl_usdt", "avg_hold_minutes"],
        )
        artifact_entries.append(_artifact(strategy_metrics_path, "csv", len(strategy_metric_rows)))
    else:
        _remove_if_exists(strategy_metrics_path)

    if regime_metric_rows:
        _write_csv(
            regime_metrics_path,
            regime_metric_rows,
            ["regime", "time_pct", "switches", "gate_blocks"],
        )
        artifact_entries.append(_artifact(regime_metrics_path, "csv", len(regime_metric_rows)))
    else:
        _remove_if_exists(regime_metrics_path)

    if position_snapshot_rows:
        _write_csv(
            position_snapshots_path,
            position_snapshot_rows,
            ["timestamp", "pair", "notional_usdt", "unrealized_pnl_usdt", "entry_z", "current_z", "hold_minutes"],
        )
        artifact_entries.append(_artifact(position_snapshots_path, "csv", len(position_snapshot_rows)))
    else:
        _remove_if_exists(position_snapshots_path)

    if liquidity_check_rows:
        _write_csv(
            liquidity_checks_path,
            liquidity_check_rows,
            [
                "timestamp",
                "pair",
                "strategy",
                "regime",
                "long_ticker",
                "short_ticker",
                "status",
                "target_usdt",
                "liquidity_long_usdt",
                "liquidity_short_usdt",
                "ratio_long",
                "ratio_short",
                "min_ratio",
                "selected_ratio",
                "fallback_used",
                "downsized",
                "attempt_count",
                "reason",
            ],
        )
        artifact_entries.append(_artifact(liquidity_checks_path, "csv", len(liquidity_check_rows)))
    else:
        _remove_if_exists(liquidity_checks_path)

    if fill_summary_rows:
        _write_csv(
            entry_slippage_path,
            fill_summary_rows,
            [
                "timestamp",
                "pair",
                "strategy",
                "regime",
                "ticker",
                "side",
                "order_id",
                "preview_price",
                "fill_price",
                "filled_qty",
                "fill_count",
                "fee_usdt",
                "fill_pnl_usdt",
                "slippage_bps",
                "abs_slippage_bps",
            ],
        )
        artifact_entries.append(_artifact(entry_slippage_path, "csv", len(fill_summary_rows)))
    else:
        _remove_if_exists(entry_slippage_path)

    if reconciliation_rows:
        _write_csv(
            reconciliation_checks_path,
            reconciliation_rows,
            [
                "timestamp",
                "pair",
                "strategy",
                "regime",
                "entry_ts",
                "exit_reason",
                "trade_pnl",
                "equity_change",
                "difference",
                "fees",
                "slippage",
                "funding",
                "unexplained",
                "basis",
                "delta_warn_threshold",
                "unexplained_warn_threshold",
                "unexplained_pct_warn_threshold",
                "unexplained_pct",
                "large_delta_warning",
                "large_unexplained_warning",
                "post_close_equity_available",
                "pass_fail",
            ],
        )
        artifact_entries.append(_artifact(reconciliation_checks_path, "csv", len(reconciliation_rows)))
    else:
        _remove_if_exists(reconciliation_checks_path)

    if entry_rejection_rows:
        _write_csv(
            entry_rejections_path,
            entry_rejection_rows,
            [
                "timestamp",
                "pair",
                "strategy",
                "regime",
                "reject_type",
                "reason",
                "long_ticker",
                "short_ticker",
                "target_usdt",
                "liquidity_long_usdt",
                "liquidity_short_usdt",
                "ratio_long",
                "ratio_short",
                "min_ratio",
                "available_usdt",
                "total_notional_usdt",
                "action",
                "long_error",
                "short_error",
            ],
        )
        artifact_entries.append(_artifact(entry_rejections_path, "csv", len(entry_rejection_rows)))
    else:
        _remove_if_exists(entry_rejections_path)

    if alert_rows:
        _write_csv(
            risk_alerts_path,
            alert_rows,
            [
                "timestamp",
                "event_type",
                "severity",
                "pair",
                "strategy",
                "regime",
                "alert_type",
                "warning_type",
                "message",
                "basis",
                "difference",
                "unexplained",
                "unexplained_pct",
                "details_json",
            ],
        )
        artifact_entries.append(_artifact(risk_alerts_path, "csv", len(alert_rows)))
    else:
        _remove_if_exists(risk_alerts_path)

    if exit_decision_trace_rows:
        _write_csv(exit_decision_trace_path, exit_decision_trace_rows, EXIT_DECISION_TRACE_FIELDS)
        artifact_entries.append(_artifact(exit_decision_trace_path, "csv", len(exit_decision_trace_rows)))
    else:
        _remove_if_exists(exit_decision_trace_path)

    if exit_decision_summary_rows:
        _write_csv(exit_decision_summary_path, exit_decision_summary_rows, EXIT_DECISION_SUMMARY_FIELDS)
        artifact_entries.append(_artifact(exit_decision_summary_path, "csv", len(exit_decision_summary_rows)))
    else:
        _remove_if_exists(exit_decision_summary_path)

    manifest_path.write_text(
        json.dumps(
            {
                "report_version": "v2-live",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "run_key": run_key,
                "report_source": "events_db_materialized",
                "data_sources": data_sources,
                "files": artifact_entries,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "saved": True,
        "detail": "updated",
        "run_key": run_key,
        "path": str(report_dir),
        "files": len(artifact_entries),
        "artifacts": artifact_entries,
    }
