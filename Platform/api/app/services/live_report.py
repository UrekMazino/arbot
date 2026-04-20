from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Run, RunEvent
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

    heartbeat_rows = db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run.id, RunEvent.event_type == "heartbeat")
        .order_by(RunEvent.ts.asc(), RunEvent.created_at.asc(), RunEvent.id.asc())
    ).scalars().all()
    equity_curve = []
    for row in heartbeat_rows:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        equity_curve.append(
            {
                "timestamp": _coerce_timestamp(row.ts),
                "equity_usdt": _coerce_float(payload.get("equity_usdt")),
                "session_pnl_usdt": _coerce_float(payload.get("session_pnl_usdt")),
                "session_pnl_pct": _coerce_float(payload.get("session_pnl_pct")),
                "pair": str(payload.get("current_pair") or payload.get("pair") or "").strip(),
                "regime": str(payload.get("regime") or "").strip(),
                "strategy": str(payload.get("strategy") or "").strip(),
            }
        )

    trade_close_events = db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run.id, RunEvent.event_type == "trade_close")
        .order_by(RunEvent.ts.asc(), RunEvent.created_at.asc(), RunEvent.id.asc())
    ).scalars().all()
    trade_rows = []
    wins = 0
    losses = 0
    for row in trade_close_events:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        pnl_usdt = _coerce_float(payload.get("pnl_usdt"))
        if pnl_usdt is not None:
            if pnl_usdt > 0:
                wins += 1
            elif pnl_usdt < 0:
                losses += 1
        trade_rows.append(
            {
                "timestamp": _coerce_timestamp(row.ts),
                "pair": str(payload.get("pair") or "").strip(),
                "pnl_usdt": pnl_usdt,
                "pnl_pct": _coerce_float(payload.get("pnl_pct")),
                "strategy": str(payload.get("strategy") or "").strip(),
                "regime": str(payload.get("regime") or "").strip(),
                "hold_minutes": _coerce_float(payload.get("hold_minutes")),
                "exit_reason": str(payload.get("exit_reason") or "").strip(),
                "exit_tier": str(payload.get("exit_tier") or "").strip(),
            }
        )
    trades_total = len(trade_rows)
    win_rate_pct = round((wins / trades_total) * 100.0, 2) if trades_total > 0 else None

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

    summary = {
        "report_version": "v2-live",
        "report_source": "events_db",
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
        "wins": wins,
        "losses": losses,
        "win_rate_pct": win_rate_pct,
        "event_counts": event_counts,
        "severity_counts": severity_counts,
        "report_created_at": datetime.now(timezone.utc).isoformat(),
    }

    summary_path = report_dir / "summary.json"
    equity_curve_path = report_dir / "equity_curve.csv"
    pair_history_path = report_dir / "pair_history.csv"
    trade_closes_path = report_dir / "trade_closes.csv"
    event_counts_path = report_dir / "event_counts.json"
    manifest_path = report_dir / "report_manifest.json"

    _write_csv(
        equity_curve_path,
        equity_curve,
        ["timestamp", "equity_usdt", "session_pnl_usdt", "session_pnl_pct", "pair", "regime", "strategy"],
    )
    _write_csv(
        pair_history_path,
        pair_history_rows,
        ["sequence_no", "pair", "started_at", "ended_at", "switch_reason", "duration_seconds"],
    )
    _write_csv(
        trade_closes_path,
        trade_rows,
        ["timestamp", "pair", "pnl_usdt", "pnl_pct", "strategy", "regime", "hold_minutes", "exit_reason", "exit_tier"],
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
    manifest_path.write_text(
        json.dumps(
            {
                "report_version": "v2-live",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "run_key": run_key,
                "files": [
                    {"name": summary_path.name, "path": str(summary_path), "format": "json", "rows": 1},
                    {"name": equity_curve_path.name, "path": str(equity_curve_path), "format": "csv", "rows": len(equity_curve)},
                    {"name": pair_history_path.name, "path": str(pair_history_path), "format": "csv", "rows": len(pair_history_rows)},
                    {"name": trade_closes_path.name, "path": str(trade_closes_path), "format": "csv", "rows": len(trade_rows)},
                    {"name": event_counts_path.name, "path": str(event_counts_path), "format": "json", "rows": len(event_counts)},
                ],
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
        "files": 5,
    }
