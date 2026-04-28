from __future__ import annotations

import json
import mimetypes
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from collections import deque
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9 fallback
    ZoneInfo = None

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import (
    Alert,
    BotConfig,
    BotInstance,
    EquitySnapshot,
    PositionSnapshot,
    RegimeMetric,
    Report,
    ReportFile,
    Run,
    RunEvent,
    RunPairSegment,
    StrategyMetric,
    Trade,
)
from .log_rotation import log_rotation_settings, open_rotating_append_log, rotated_log_paths
from .run_pair_segments import list_run_pair_history_rows_by_run_key, sync_run_pair_segments_for_event


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _strip_wrapping_quotes(value: str | None) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _workspace_root() -> Path:
    explicit = str(os.getenv("BOT_CONTROL_WORKSPACE_ROOT", "")).strip()
    if explicit:
        return Path(explicit).resolve()
    docker_root = Path("/workspace")
    if docker_root.exists():
        return docker_root.resolve()
    return Path(__file__).resolve().parents[4]


WORKSPACE_ROOT = _workspace_root()
EXECUTION_ROOT = WORKSPACE_ROOT / "Execution"
LOGS_ROOT = WORKSPACE_ROOT / "Logs" / "v1"
REPORTS_ROOT = WORKSPACE_ROOT / "Reports" / "v1"
ENV_FILE = EXECUTION_ROOT / ".env"
STATE_FILE = EXECUTION_ROOT / "state" / "ui_bot_control.json"
CONTROL_LOG_FILE = LOGS_ROOT / "superadmin_bot_control.log"
PAIR_SUPPLY_LOG_FILE = LOGS_ROOT / "pair_supply_scheduler.log"
STARTING_EQUITY_RE = re.compile(r"Starting equity:\s*(?P<eq>[-+]?\d+(?:\.\d+)?)\s*USDT", re.IGNORECASE)
LOG_TIMESTAMP_RE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
PAIR_TEXT_PATTERN = r"[A-Z0-9]+-[A-Z]+-SWAP/[A-Z0-9]+-[A-Z]+-SWAP"
CURRENT_PAIR_RE = re.compile(rf"Current pair: (?P<pair>{PAIR_TEXT_PATTERN})")
PAIR_SWITCH_RE = re.compile(rf"Switching from (?P<from_pair>{PAIR_TEXT_PATTERN}) to (?P<to_pair>{PAIR_TEXT_PATTERN})")
TICKER_CONFIG_RE = re.compile(
    r"Ticker configuration validated: ticker_1=(?P<t1>[A-Z0-9]+-[A-Z]+-SWAP), ticker_2=(?P<t2>[A-Z0-9]+-[A-Z]+-SWAP)"
)
RUN_KEY_SORT_RE = re.compile(r"^run_(?P<seq>\d+)_(?P<date>\d{8})_(?P<time>\d{6})$", re.IGNORECASE)


def _default_bot_command() -> list[str]:
    entrypoint = EXECUTION_ROOT / "main_execution.py"
    return [sys.executable, str(entrypoint)]


def _resolve_bot_command() -> list[str]:
    raw = str(os.getenv("BOT_CONTROL_COMMAND", "")).strip()
    if not raw:
        return _default_bot_command()
    normalized = raw.replace("{workspace}", str(WORKSPACE_ROOT))
    try:
        return shlex.split(normalized, posix=(os.name != "nt"))
    except Exception:
        return _default_bot_command()


def _normalize_bot_child_env(env: dict[str, str]) -> dict[str, str]:
    child_env = dict(env)
    raw_base = str(child_env.get("STATBOT_EVENT_API_BASE") or "").strip()
    if os.name != "nt" and Path("/workspace").exists():
        if not raw_base:
            child_env["STATBOT_EVENT_API_BASE"] = "http://127.0.0.1:8080/api/v2"
        elif raw_base.startswith(("http://127.0.0.1:8081/", "http://localhost:8081/")):
            child_env["STATBOT_EVENT_API_BASE"] = raw_base.replace(":8081/", ":8080/", 1)
        elif raw_base.startswith(("http://127.0.0.1:8082/", "http://localhost:8082/")):
            child_env["STATBOT_EVENT_API_BASE"] = raw_base.replace(":8082/", ":8080/", 1)
    return child_env


def _parse_iso_timestamp(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _env_float(name: str, default: float, minimum: float | None = None) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw not in (None, "") else float(default)
    except (TypeError, ValueError):
        value = float(default)
    if minimum is not None and value < minimum:
        value = minimum
    return value


def _configured_log_timezone_name() -> str:
    env_value = _strip_wrapping_quotes(os.getenv("STATBOT_TIMEZONE") or os.getenv("TZ"))
    if env_value:
        return env_value
    env_settings = read_env_settings()
    return _strip_wrapping_quotes(env_settings.get("STATBOT_TIMEZONE") or env_settings.get("TZ"))


def _resolve_log_timezone():
    timezone_name = _configured_log_timezone_name()
    if timezone_name and ZoneInfo is not None:
        try:
            return ZoneInfo(timezone_name)
        except Exception:
            pass
    try:
        local_tz = datetime.now().astimezone().tzinfo
        if local_tz is not None:
            return local_tz
    except Exception:
        pass
    return timezone.utc


def _log_now() -> datetime:
    return datetime.now(_resolve_log_timezone())


def _path_mtime(path: Path | None) -> float:
    if not path:
        return 0.0
    try:
        return float(path.stat().st_mtime)
    except Exception:
        return 0.0


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    status_path = Path("/proc") / str(pid) / "status"
    if status_path.exists():
        try:
            for line in status_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.startswith("State:"):
                    state_code = line.split(":", 1)[1].strip().split()[0].upper()
                    if state_code == "Z":
                        return False
                    break
        except Exception:
            pass
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_process_cmdline(pid: int) -> list[str]:
    if pid <= 0 or os.name == "nt":
        return []
    cmdline_path = Path("/proc") / str(pid) / "cmdline"
    try:
        raw = cmdline_path.read_bytes()
    except Exception:
        return []
    return [
        part.decode("utf-8", errors="ignore")
        for part in raw.split(b"\0")
        if part
    ]


def _is_managed_bot_process(pid: int) -> bool:
    if not _pid_exists(pid):
        return False
    if os.name == "nt":
        return True

    cmdline = _read_process_cmdline(pid)
    if not cmdline:
        return False

    # Docker PID namespaces can reuse a stale bot PID for uvicorn/node/etc. Only
    # trust the persisted PID when it still points at the execution entrypoint.
    joined = " ".join(cmdline).replace("\\", "/")
    if "Execution.main_execution" in joined:
        return True

    for arg in cmdline:
        normalized = arg.replace("\\", "/")
        if normalized.endswith("/Execution/main_execution.py") or normalized.endswith("Execution/main_execution.py"):
            return True
        try:
            if Path(arg).name == "main_execution.py":
                return True
        except Exception:
            continue
    return False


def _current_process_owner() -> str:
    owner = str(os.getenv("STATBOT_PROCESS_OWNER", "api") or "api").strip()
    return owner or "api"


def _is_remote_runner_state(data: dict) -> bool:
    process_owner = str(data.get("process_owner") or "").strip()
    process_mode = str(data.get("process_mode") or "").strip().lower()
    return process_mode == "runner" and bool(process_owner) and process_owner != _current_process_owner()


def _remote_runner_heartbeat_stale(data: dict) -> bool:
    heartbeat = _parse_iso_timestamp(data.get("runner_heartbeat_at"))
    if heartbeat is None:
        return True
    if heartbeat.tzinfo is None:
        heartbeat = heartbeat.replace(tzinfo=timezone.utc)
    max_age_seconds = _env_float("STATBOT_RUNNER_HEARTBEAT_STALE_SECONDS", 20.0, minimum=5.0)
    age_seconds = (datetime.now(timezone.utc) - heartbeat.astimezone(timezone.utc)).total_seconds()
    return age_seconds > max_age_seconds


def _read_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(data: dict) -> None:
    payload = dict(data or {})
    payload["updated_at"] = _utc_iso_now()
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _run_log_has_run_end(path: Path | None) -> bool:
    if not path or not path.exists():
        return False
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            read_size = min(size, 16384)
            if read_size <= 0:
                return False
            handle.seek(-read_size, os.SEEK_END)
            tail = handle.read().decode("utf-8", errors="ignore")
    except Exception:
        return False
    return "RUN_END:" in tail


def _append_fallback_run_end_log(path: Path | None, reason: str, detail: str, exit_code: int = 0) -> bool:
    if not path:
        return False
    try:
        if _run_log_has_run_end(path):
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        ts = _log_now()
        timestamp_text = f"{ts.strftime('%Y-%m-%d %H:%M:%S')},{int(ts.microsecond / 1000):03d}"
        message = f"RUN_END: reason={reason}"
        detail_text = str(detail or "").strip()
        if detail_text:
            message += f" detail={detail_text}"
        message += f" exit_code={int(exit_code)}"
        with path.open("a", encoding="utf-8", errors="ignore") as handle:
            handle.write(f"{timestamp_text} WARNING {message}\n")
        return True
    except Exception:
        return False


def _ensure_manual_stop_artifacts(
    run_key: str | None,
    run_log_file: str | None,
    requested_by: str | None = None,
    started_at_text: str | None = None,
) -> dict:
    selected_run_key = str(run_key or "").strip()
    if not selected_run_key:
        return {"saved": False, "detail": "missing_run_key"}

    log_path = Path(run_log_file).expanduser() if run_log_file else None
    fallback_detail = "Ended by user via admin stop fallback"
    log_written = _append_fallback_run_end_log(log_path, "manual_stop", fallback_detail, exit_code=0)

    db: Session = SessionLocal()
    try:
        run = db.execute(select(Run).where(Run.run_key == selected_run_key)).scalar_one_or_none()
        if run is None:
            bot_instance = db.execute(
                select(BotInstance).where(BotInstance.name == "default")
            ).scalar_one_or_none()
            if bot_instance is None:
                bot_instance = BotInstance(name="default", environment="demo")
                db.add(bot_instance)
                db.flush()

            parsed_started_at = _parse_iso_timestamp(started_at_text)
            if parsed_started_at is None:
                parsed_started_at = datetime.now(timezone.utc)
            elif parsed_started_at.tzinfo is None:
                parsed_started_at = parsed_started_at.replace(tzinfo=timezone.utc)
            else:
                parsed_started_at = parsed_started_at.astimezone(timezone.utc)

            run = Run(
                bot_instance_id=bot_instance.id,
                run_key=selected_run_key,
                status="stopped",
                start_ts=parsed_started_at,
                end_ts=datetime.now(timezone.utc),
            )
            db.add(run)
            db.flush()

        now_utc = datetime.now(timezone.utc)
        if str(run.status or "").strip().lower() != "stopped":
            run.status = "stopped"
        if run.end_ts is None:
            run.end_ts = now_utc

        stop_event = db.execute(
            select(RunEvent)
            .where(RunEvent.run_id == run.id, RunEvent.event_type == "status_update")
            .order_by(RunEvent.ts.desc(), RunEvent.created_at.desc(), RunEvent.id.desc())
            .limit(10)
        ).scalars().all()

        stop_event_row = None
        for row in stop_event:
            payload = row.payload_json if isinstance(row.payload_json, dict) else {}
            status_text = str(payload.get("status") or "").strip().lower()
            if status_text in {"manual_stop", "run_end"}:
                stop_event_row = row
                break

        if stop_event_row is None:
            stop_event_row = RunEvent(
                event_id=str(uuid.uuid4()),
                run_id=run.id,
                bot_instance_id=run.bot_instance_id,
                ts=now_utc,
                event_type="status_update",
                severity="info",
                payload_json={
                    "status": "manual_stop",
                    "message": "Ended by user",
                    "detail": fallback_detail,
                    "source": "bot_control_fallback",
                    "requested_by": requested_by or "",
                },
            )
            db.add(stop_event_row)
            db.flush()
            try:
                from .run_pair_segments import sync_run_pair_segments_for_event

                sync_run_pair_segments_for_event(db, run, stop_event_row)
            except Exception:
                pass

        db.commit()

        try:
            from .live_report import materialize_live_run_report

            report_result = materialize_live_run_report(db, run)
        except Exception as exc:
            report_result = {"saved": False, "detail": f"live_report_failed:{exc}"}

        return {
            "saved": bool(report_result.get("saved")) or bool(log_written),
            "detail": report_result.get("detail") or "manual_stop_artifacts_created",
            "log_written": log_written,
            "report_saved": bool(report_result.get("saved")),
        }
    finally:
        db.close()


def _tail_lines(path: Path, line_count: int) -> list[str]:
    max_lines = max(min(int(line_count), 5000), 1)
    lines: deque[str] = deque(maxlen=max_lines)
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw in handle:
            lines.append(raw.rstrip("\n"))
    return list(lines)


def _head_lines(path: Path, line_count: int) -> list[str]:
    max_lines = max(min(int(line_count), 5000), 1)
    lines: list[str] = []
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for idx, raw in enumerate(handle):
            if idx >= max_lines:
                break
            lines.append(raw.rstrip("\n"))
    return lines


def _coerce_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_log_timestamp(line: str) -> float | None:
    ts_match = LOG_TIMESTAMP_RE.match(line)
    if not ts_match:
        return None
    try:
        return datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=_resolve_log_timezone()
        ).timestamp()
    except Exception:
        return None


def _extract_log_timestamp_text(line: str) -> str | None:
    ts_match = LOG_TIMESTAMP_RE.match(line)
    if not ts_match:
        return None
    return ts_match.group(1)


def _format_log_threshold_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    try:
        if value.tzinfo is not None:
            value = value.astimezone(_resolve_log_timezone())
        return value.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _extract_pair_from_line(line: str) -> str | None:
    current_pair_match = CURRENT_PAIR_RE.search(line)
    if current_pair_match:
        return current_pair_match.group("pair")

    ticker_config_match = TICKER_CONFIG_RE.search(line)
    if ticker_config_match:
        return f"{ticker_config_match.group('t1')}/{ticker_config_match.group('t2')}"

    return None


def _append_pair_history_entry(pair_history: list[dict], pair: str | None, start_ts: float | None, end_ts: float | None) -> None:
    if not pair or start_ts is None or end_ts is None:
        return
    duration = float(end_ts) - float(start_ts)
    if duration < 0:
        return
    pair_history.append(
        {
            "pair": pair,
            "duration_seconds": duration,
        }
    )


def _extract_pair_history(lines: list[str], *, run_start_time: float | None, last_update_time: float | None) -> list[dict]:
    pair_history: list[dict] = []
    current_pair: str | None = None
    current_pair_start_ts: float | None = None

    for line in lines:
        line_ts = _parse_log_timestamp(line)
        if line_ts is None:
            continue

        new_pair = _extract_pair_from_line(line)
        if new_pair is not None and new_pair != current_pair:
            _append_pair_history_entry(pair_history, current_pair, current_pair_start_ts, line_ts)
            current_pair = new_pair
            current_pair_start_ts = line_ts

        switch_match = PAIR_SWITCH_RE.search(line)
        if not switch_match:
            continue

        from_pair = switch_match.group("from_pair")
        to_pair = switch_match.group("to_pair")

        if current_pair is None:
            current_pair = from_pair
            current_pair_start_ts = run_start_time if run_start_time is not None else line_ts
        elif current_pair != from_pair:
            _append_pair_history_entry(pair_history, current_pair, current_pair_start_ts, line_ts)
            current_pair = from_pair
            current_pair_start_ts = run_start_time if run_start_time is not None else line_ts

        _append_pair_history_entry(pair_history, current_pair, current_pair_start_ts, line_ts)
        current_pair = to_pair
        current_pair_start_ts = line_ts

    _append_pair_history_entry(pair_history, current_pair, current_pair_start_ts, last_update_time)
    return pair_history


def _load_pair_history_from_database(run_key: str, *, last_update_time: float | None) -> list[dict]:
    reference_time = None
    if last_update_time is not None:
        reference_time = datetime.fromtimestamp(float(last_update_time), tz=timezone.utc)

    db: Session = SessionLocal()
    try:
        return list_run_pair_history_rows_by_run_key(
            db,
            run_key,
            reference_time=reference_time,
            ensure_backfilled=True,
        )
    finally:
        db.close()


def _extract_start_snapshot_from_lines(lines: list[str]) -> dict[str, float | None]:
    starting_equity = None
    run_start_time = None
    for line in lines:
        if starting_equity is None:
            match = STARTING_EQUITY_RE.search(line)
            if match:
                starting_equity = _coerce_float(match.group("eq"))
        if run_start_time is None:
            run_start_time = _parse_log_timestamp(line)
        if starting_equity is not None and run_start_time is not None:
            break
    return {
        "starting_equity": starting_equity,
        "run_start_time": run_start_time,
    }


def _read_run_start_snapshot(log_file: Path | None) -> dict[str, float | None]:
    if not log_file or not log_file.exists():
        return {"starting_equity": None, "run_start_time": None}
    try:
        header_lines = _head_lines(log_file, 200)
    except Exception:
        return {"starting_equity": None, "run_start_time": None}
    return _extract_start_snapshot_from_lines(header_lines)


def _read_recent_start_snapshot(
    log_file: Path | None,
    *,
    line_count: int = 400,
    started_after_text: str | None = None,
) -> dict[str, float | None]:
    if not log_file or not log_file.exists():
        return {"starting_equity": None, "run_start_time": None}
    try:
        lines = _tail_lines(log_file, line_count)
    except Exception:
        return {"starting_equity": None, "run_start_time": None}

    starting_equity = None
    run_start_time = None
    for line in lines:
        line_text_ts = _extract_log_timestamp_text(line)
        if started_after_text is not None and line_text_ts is not None and line_text_ts < started_after_text:
            continue
        line_ts = _parse_log_timestamp(line)
        if run_start_time is None and line_ts is not None:
            run_start_time = line_ts
        match = STARTING_EQUITY_RE.search(line)
        if match:
            starting_equity = _coerce_float(match.group("eq"))
            if line_ts is not None:
                run_start_time = line_ts
    return {
        "starting_equity": starting_equity,
        "run_start_time": run_start_time,
    }


def _load_run_snapshot(run_key: str | None) -> dict[str, float | None]:
    selected = str(run_key or "").strip()
    if not selected or selected == "__control__":
        return {"starting_equity": None, "run_start_time": None}

    state = _read_state()
    state_started_at = _parse_iso_timestamp(state.get("started_at"))
    state_started_text = _format_log_threshold_text(state_started_at)
    state_snapshot = {"starting_equity": None, "run_start_time": None}
    if state.get("run_key") == selected:
        state_snapshot = {
            "starting_equity": _coerce_float(state.get("starting_equity")),
            "run_start_time": _coerce_float(state.get("run_start_time")),
        }

    db_snapshot = {"starting_equity": None, "run_start_time": None}
    try:
        db: Session = SessionLocal()
        try:
            run = db.execute(select(Run).where(Run.run_key == selected)).scalar_one_or_none()
            if run:
                db_snapshot = {
                    "starting_equity": _coerce_float(run.start_equity),
                    "run_start_time": run.start_ts.timestamp() if getattr(run, "start_ts", None) else None,
                }
        finally:
            db.close()
    except Exception:
        pass

    log_run_key, log_file = _resolve_run_log_file(selected)
    log_snapshot = _read_run_start_snapshot(log_file if log_run_key == selected else None)
    control_snapshot = {"starting_equity": None, "run_start_time": None}
    if state.get("run_key") == selected:
        control_snapshot = _read_recent_start_snapshot(
            CONTROL_LOG_FILE,
            line_count=500,
            started_after_text=state_started_text,
        )
        if control_snapshot["starting_equity"] is None and control_snapshot["run_start_time"] is None:
            # Be forgiving if the control log timezone and state timestamp do
            # not line up; the latest startup snapshot in the tail is still the
            # best active-run fallback.
            control_snapshot = _read_recent_start_snapshot(
                CONTROL_LOG_FILE,
                line_count=500,
            )

    return {
        "starting_equity": (
            state_snapshot["starting_equity"]
            if state_snapshot["starting_equity"] is not None
            else db_snapshot["starting_equity"]
            if db_snapshot["starting_equity"] is not None
            else log_snapshot["starting_equity"]
            if log_snapshot["starting_equity"] is not None
            else control_snapshot["starting_equity"]
        ),
        "run_start_time": (
            state_snapshot["run_start_time"]
            if state_snapshot["run_start_time"] is not None
            else db_snapshot["run_start_time"]
            if db_snapshot["run_start_time"] is not None
            else log_snapshot["run_start_time"]
            if log_snapshot["run_start_time"] is not None
            else control_snapshot["run_start_time"]
        ),
    }


def _update_current_run_state_snapshot(
    run_key: str,
    *,
    run_log_file: Path | None = None,
    starting_equity: float | None = None,
    run_start_time: float | None = None,
) -> None:
    state = _read_state()
    if state.get("run_key") != run_key:
        return

    changed = False
    if run_log_file is not None:
        run_log_text = str(run_log_file)
        if state.get("run_log_file") != run_log_text:
            state["run_log_file"] = run_log_text
            changed = True
    existing_starting_equity = _coerce_float(state.get("starting_equity"))
    if starting_equity is not None and existing_starting_equity is None:
        state["starting_equity"] = float(starting_equity)
        changed = True
    existing_run_start_time = _coerce_float(state.get("run_start_time"))
    if run_start_time is not None and existing_run_start_time is None:
        state["run_start_time"] = float(run_start_time)
        changed = True

    if changed:
        _write_state(state)


def _persist_run_start_snapshot(
    run_key: str,
    *,
    starting_equity: float | None = None,
    run_start_time: float | None = None,
) -> dict:
    if not run_key:
        return {"saved": False, "detail": "missing_run_key"}

    _update_current_run_state_snapshot(
        run_key,
        starting_equity=starting_equity,
        run_start_time=run_start_time,
    )

    if starting_equity is None and run_start_time is None:
        return {"saved": False, "detail": "empty_snapshot"}

    try:
        db: Session = SessionLocal()
        try:
            run = db.execute(select(Run).where(Run.run_key == run_key)).scalar_one_or_none()
            if not run:
                return {"saved": False, "detail": "run_not_found"}

            changed = False
            existing_start_equity = _coerce_float(run.start_equity)
            if starting_equity is not None and existing_start_equity is None:
                run.start_equity = float(starting_equity)
                changed = True
            if run_start_time is not None and getattr(run, "start_ts", None) is None:
                run.start_ts = datetime.fromtimestamp(float(run_start_time), tz=timezone.utc)
                changed = True
            if changed:
                db.commit()
            return {"saved": changed, "detail": "updated" if changed else "unchanged"}
        finally:
            db.close()
    except Exception as exc:
        return {"saved": False, "detail": f"db_error:{exc}"}


def _backfill_run_start_snapshot(run_key: str, run_log_file: Path, timeout_seconds: float = 45.0) -> None:
    deadline = time.time() + max(float(timeout_seconds), 1.0)
    while time.time() < deadline:
        snapshot = _read_run_start_snapshot(run_log_file)
        starting_equity = snapshot.get("starting_equity")
        run_start_time = snapshot.get("run_start_time")
        if starting_equity is not None or run_start_time is not None:
            _persist_run_start_snapshot(
                run_key,
                starting_equity=starting_equity,
                run_start_time=run_start_time,
            )
            return
        time.sleep(0.5)


def _latest_run_log_file() -> tuple[str | None, Path | None]:
    if not LOGS_ROOT.exists():
        return None, None
    candidates: list[tuple[str, Path, float]] = []
    for run_dir in LOGS_ROOT.iterdir():
        if not run_dir.is_dir():
            continue
        if not run_dir.name.startswith("run_"):
            continue
        run_logs = sorted(run_dir.glob("log_*.log"))
        if not run_logs:
            continue
        log_file = run_logs[-1]
        try:
            mtime = log_file.stat().st_mtime
        except Exception:
            mtime = 0.0
        candidates.append((run_dir.name, log_file, mtime))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: item[2], reverse=True)
    run_key, log_file, _ = candidates[0]
    return run_key, log_file


def _resolve_run_directory(root: Path, run_key: str | None) -> Path | None:
    selected = str(run_key or "").strip()
    if not selected:
        return None
    candidate = (root / selected).resolve()
    root_resolved = root.resolve()
    if candidate.parent != root_resolved:
        return None
    if not candidate.exists() or not candidate.is_dir():
        return None
    if not candidate.name.startswith("run_"):
        return None
    return candidate


def _resolve_run_log_file(run_key: str | None) -> tuple[str | None, Path | None]:
    selected = str(run_key or "").strip()
    if not selected or selected.lower() == "latest":
        return _latest_run_log_file()
    run_dir = _resolve_run_directory(LOGS_ROOT, selected)
    if not run_dir:
        return None, None
    logs = sorted(run_dir.glob("log_*.log"))
    if not logs:
        return None, None
    return selected, logs[-1]


def _resolve_live_tail_target(run_key: str | None) -> tuple[str | None, Path | None, str]:
    selected = str(run_key or "").strip()
    if selected and selected.lower() != "latest":
        resolved_run_key, log_file = _resolve_run_log_file(selected)
        return resolved_run_key, log_file, "requested_run"

    state = _read_state()
    latest_run_key, latest_log_file = _latest_run_log_file()
    control_mtime = _path_mtime(CONTROL_LOG_FILE if CONTROL_LOG_FILE.exists() else None)
    latest_log_mtime = _path_mtime(latest_log_file)
    started_at = _parse_iso_timestamp(state.get("started_at"))
    started_ts = started_at.timestamp() if started_at else 0.0
    should_prefer_control = CONTROL_LOG_FILE.exists() and (
        not latest_log_file
        or (started_ts > 0 and latest_log_mtime < started_ts)
    )
    if should_prefer_control:
        return "__control__", CONTROL_LOG_FILE, "control_log_preferred"
    return latest_run_key, latest_log_file, "latest_run"


def resolve_live_stream_target(run_key: str | None = None) -> dict:
    resolved_run_key, log_file, source = _resolve_live_tail_target(run_key)
    if not log_file or not log_file.exists():
        raise FileNotFoundError("Log stream target not found")
    return {
        "run_key": resolved_run_key,
        "log_file": str(log_file),
        "source": source,
    }


def _normalize_status(state: dict) -> dict:
    data = dict(state or {})
    pid = int(data.get("pid") or 0)
    if _is_remote_runner_state(data):
        running = bool(data.get("running"))
        if running and _remote_runner_heartbeat_stale(data):
            running = False
            data["detail"] = "runner_stale"
        pid_alive = running
    else:
        pid_alive = _pid_exists(pid)
        running = _is_managed_bot_process(pid)
    data["pid"] = pid
    data["running"] = running
    if not running and pid > 0:
        data["stopped_at"] = data.get("stopped_at") or _utc_iso_now()
        prior_detail = str(data.get("detail") or "").strip().lower()
        if prior_detail in {"", "started", "already_running"}:
            data["detail"] = "stale_pid_reused" if pid_alive else "process_exited"
    run_key, run_log_file = _latest_run_log_file()
    data["latest_run_key"] = run_key
    data["latest_log_file"] = str(run_log_file) if run_log_file else None
    data["workspace_root"] = str(WORKSPACE_ROOT)
    data["control_log_file"] = str(CONTROL_LOG_FILE)
    return data


def get_bot_status() -> dict:
    state = _read_state()
    normalized = _normalize_status(state)
    if normalized != state:
        _write_state(normalized)
    return normalized


def _use_bot_runner_mode() -> bool:
    mode = str(os.getenv("STATBOT_BOT_PROCESS_MODE", "local") or "local").strip().lower()
    return mode in {"docker", "external", "runner"}


def _request_bot_runner(desired_running: bool, requested_by: str | None = None) -> dict:
    state = get_bot_status()
    running = bool(state.get("running"))
    state["desired_running"] = bool(desired_running)
    state["requested_by"] = requested_by or state.get("requested_by", "")
    state["request_updated_at"] = _utc_iso_now()
    state["process_mode"] = "runner"
    if desired_running:
        state["detail"] = "already_running" if running else "start_requested"
        if not running:
            state["stopped_at"] = None
    else:
        state["detail"] = "stop_requested" if running else "already_stopped"
        if not running:
            state["running"] = False
            state["stopped_at"] = state.get("stopped_at") or _utc_iso_now()
    _write_state(state)
    return _normalize_status(state)


def _start_bot_local(requested_by: str | None = None) -> dict:
    status = get_bot_status()
    if status.get("running"):
        status["detail"] = "already_running"
        return status

    command = _resolve_bot_command()
    if not command:
        return {"running": False, "detail": "empty_command"}

    entrypoint_exists = True
    if len(command) >= 2 and command[1].endswith(".py"):
        entrypoint_exists = Path(command[1]).exists()
    if not entrypoint_exists:
        return {
            "running": False,
            "detail": "entrypoint_missing",
            "command": command,
        }

    LOGS_ROOT.mkdir(parents=True, exist_ok=True)

    env = _normalize_bot_child_env(os.environ.copy())
    # Start the top-level execution manager so exit code 3 can trigger in-process restarts.
    env.pop("STATBOT_MANAGED", None)
    env["PYTHONUNBUFFERED"] = "1"

    # Compute the run_key that the execution script will use
    run_id = _log_now().strftime("%Y%m%d_%H%M%S")
    run_seq = 1
    if LOGS_ROOT.exists():
        max_seq = 0
        for entry in LOGS_ROOT.iterdir():
            if entry.is_dir() and entry.name.startswith("run_"):
                parts = entry.name.split("_")
                if len(parts) >= 3:
                    try:
                        seq = int(parts[1])
                        if seq > max_seq:
                            max_seq = seq
                    except (ValueError, IndexError):
                        pass
        run_seq = max_seq + 1
    run_key = f"run_{run_seq:02d}_{run_id}"
    run_log_dir = LOGS_ROOT / run_key
    run_log_file = run_log_dir / f"log_{run_id}.log"
    env["STATBOT_LOG_PATH"] = str(run_log_file)

    try:
        proc = subprocess.Popen(
            command,
            cwd=str(WORKSPACE_ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        return {
            "running": False,
            "detail": f"start_failed:{exc}",
            "command": command,
        }

    state = {
        "running": True,
        "pid": int(proc.pid or 0),
        "started_at": _utc_iso_now(),
        "stopped_at": None,
        "detail": "started",
        "command": command,
        "cwd": str(WORKSPACE_ROOT),
        "requested_by": requested_by or "",
        "control_log_file": str(CONTROL_LOG_FILE),
        "run_key": run_key,
        "run_log_file": str(run_log_file),
        "starting_equity": None,
        "run_start_time": None,
        "desired_running": True,
        "process_owner": str(os.getenv("STATBOT_PROCESS_OWNER", "api") or "api"),
    }
    _write_state(state)

    # Save run to database
    _save_run_to_database(run_key, requested_by)

    snapshot_thread = threading.Thread(
        target=_backfill_run_start_snapshot,
        args=(run_key, run_log_file),
        daemon=True,
        name=f"bot-start-snapshot-{run_key}",
    )
    snapshot_thread.start()

    return _normalize_status(state)


def start_bot(requested_by: str | None = None) -> dict:
    if _use_bot_runner_mode():
        return _request_bot_runner(True, requested_by=requested_by)
    return _start_bot_local(requested_by=requested_by)


def _save_run_to_database(run_key: str, requested_by: str | None = None) -> dict:
    """Save a new run to the database when bot starts."""
    try:
        db: Session = SessionLocal()
        try:
            # Get or create default bot instance
            bot_instance = db.execute(
                select(BotInstance).where(BotInstance.name == "default")
            ).scalar_one_or_none()

            if not bot_instance:
                bot_instance = BotInstance(name="default", environment="demo")
                db.add(bot_instance)
                db.flush()

            # Create new run record
            run = Run(
                bot_instance_id=bot_instance.id,
                run_key=run_key,
                status="running",
                start_ts=datetime.now(timezone.utc),
            )
            db.add(run)
            db.commit()
            return {"saved": True, "run_id": run.id, "run_key": run.run_key}
        finally:
            db.close()
    except Exception as e:
        return {"saved": False, "error": str(e)}


def _send_stop_signal(pid: int, sig: int) -> None:
    if os.name != "nt":
        os.killpg(os.getpgid(pid), sig)
        return

    ctrl_break = getattr(signal, "CTRL_BREAK_EVENT", None)
    if sig == getattr(signal, "SIGINT", None) and ctrl_break is not None:
        os.kill(pid, ctrl_break)
        return
    os.kill(pid, sig)


def _stop_bot_local(requested_by: str | None = None, timeout_seconds: float = 12.0) -> dict:
    state = get_bot_status()
    pid = int(state.get("pid") or 0)
    run_key = str(state.get("run_key") or "").strip()
    run_log_file = str(state.get("run_log_file") or "").strip()
    if pid <= 0 or not state.get("running"):
        state["running"] = False
        state["detail"] = "already_stopped"
        state["stopped_at"] = state.get("stopped_at") or _utc_iso_now()
        state["requested_by"] = requested_by or state.get("requested_by", "")
        state["desired_running"] = False
        _write_state(state)
        return state

    if not _is_managed_bot_process(pid):
        state["running"] = False
        state["detail"] = "stale_pid_reused" if _pid_exists(pid) else "process_exited"
        state["stopped_at"] = state.get("stopped_at") or _utc_iso_now()
        state["requested_by"] = requested_by or state.get("requested_by", "")
        state["desired_running"] = False
        _write_state(state)
        return _normalize_status(state)

    terminated = False
    detail = "interrupt_sent"
    interrupt_sent = False
    try:
        _send_stop_signal(pid, signal.SIGINT)
        interrupt_sent = True
    except Exception as exc:
        detail = f"interrupt_signal_failed:{exc}"

    deadline = time.time() + max(float(timeout_seconds), 1.0)
    while interrupt_sent and time.time() < deadline:
        if not _pid_exists(pid):
            terminated = True
            break
        time.sleep(0.2)

    if not terminated:
        try:
            _send_stop_signal(pid, signal.SIGTERM)
            detail = "term_sent"
        except Exception as exc:
            detail = f"term_signal_failed:{exc}"

        term_deadline = min(deadline + 2.0, time.time() + 2.0)
        while time.time() < term_deadline:
            if not _pid_exists(pid):
                terminated = True
                break
            time.sleep(0.2)

    if not terminated:
        try:
            _send_stop_signal(pid, signal.SIGKILL)
            terminated = True
            detail = "killed"
        except Exception as exc:
            detail = f"kill_failed:{exc}"

    state["running"] = False
    state["stopped_at"] = _utc_iso_now()
    state["detail"] = "stopped" if terminated else detail
    state["requested_by"] = requested_by or state.get("requested_by", "")
    state["desired_running"] = False
    _write_state(state)
    if terminated and run_key:
        fallback_result = _ensure_manual_stop_artifacts(
            run_key,
            run_log_file,
            requested_by=requested_by,
            started_at_text=state.get("started_at"),
        )
        if not bool(fallback_result.get("saved")) and fallback_result.get("detail"):
            state["detail"] = str(fallback_result.get("detail"))
            _write_state(state)
    return _normalize_status(state)


def stop_bot(requested_by: str | None = None, timeout_seconds: float = 12.0) -> dict:
    if _use_bot_runner_mode():
        return _request_bot_runner(False, requested_by=requested_by)
    return _stop_bot_local(requested_by=requested_by, timeout_seconds=timeout_seconds)


def tail_run_log(run_key: str | None = None, lines: int = 400) -> dict:
    resolved_run_key, log_file, source = _resolve_live_tail_target(run_key)
    state = _read_state()
    snapshot_run_key = resolved_run_key
    if resolved_run_key == "__control__":
        active_run_key = str(state.get("run_key") or "").strip()
        if active_run_key:
            snapshot_run_key = active_run_key
    run_snapshot = _load_run_snapshot(snapshot_run_key)
    starting_equity = run_snapshot.get("starting_equity")
    stored_run_start_time = run_snapshot.get("run_start_time")
    if snapshot_run_key and snapshot_run_key != "__control__":
        _persist_run_start_snapshot(
            snapshot_run_key,
            starting_equity=starting_equity,
            run_start_time=stored_run_start_time,
        )
    if not log_file:
        if CONTROL_LOG_FILE.exists():
            try:
                output_lines = _tail_lines(CONTROL_LOG_FILE, lines)
            except Exception as exc:
                return {
                    "run_key": "__control__",
                    "log_file": str(CONTROL_LOG_FILE),
                    "line_count": 0,
                    "lines": [],
                    "updated_at": _utc_iso_now(),
                    "detail": f"control_log_read_failed:{exc}",
                    "equity": None,
                    "starting_equity": starting_equity,
                    "session_pnl": None,
                    "session_pnl_pct": None,
                    "run_start_time": stored_run_start_time,
                }
            return {
                "run_key": "__control__",
                "log_file": str(CONTROL_LOG_FILE),
                "line_count": len(output_lines),
                "lines": output_lines,
                "updated_at": _utc_iso_now(),
                "detail": "control_log_fallback",
                "equity": None,
                "starting_equity": starting_equity,
                "session_pnl": None,
                "session_pnl_pct": None,
                "run_start_time": stored_run_start_time,
            }
        return {
            "run_key": resolved_run_key,
            "log_file": None,
            "line_count": 0,
            "lines": [],
            "updated_at": _utc_iso_now(),
            "detail": "log_not_found",
            "equity": None,
            "starting_equity": starting_equity,
            "session_pnl": None,
            "session_pnl_pct": None,
            "run_start_time": stored_run_start_time,
        }
    try:
        output_lines = _tail_lines(log_file, lines)
    except Exception as exc:
        return {
            "run_key": resolved_run_key,
            "log_file": str(log_file),
            "line_count": 0,
            "lines": [],
            "updated_at": _utc_iso_now(),
            "detail": f"log_read_failed:{exc}",
            "equity": None,
            "starting_equity": starting_equity,
            "session_pnl": None,
            "session_pnl_pct": None,
            "run_start_time": stored_run_start_time,
        }

    analysis_lines = output_lines
    analysis_line_count = max(int(lines), 5000)
    if analysis_line_count > len(output_lines):
        try:
            analysis_lines = _tail_lines(log_file, analysis_line_count)
        except Exception:
            analysis_lines = output_lines

    if resolved_run_key and resolved_run_key != "__control__":
        snapshot = _read_run_start_snapshot(log_file)
        if snapshot.get("starting_equity") is not None or snapshot.get("run_start_time") is not None:
            _persist_run_start_snapshot(
                resolved_run_key,
                starting_equity=snapshot.get("starting_equity"),
                run_start_time=snapshot.get("run_start_time"),
            )
            if starting_equity is None:
                starting_equity = snapshot.get("starting_equity")
            if stored_run_start_time is None:
                stored_run_start_time = snapshot.get("run_start_time")

    # Extract equity info from last PnL line
    equity = None
    session_pnl = None
    session_pnl_pct = None
    run_start_time = stored_run_start_time
    last_update_time = None  # Track most recent timestamp

    # First pass: find run_start_time (earliest timestamp) and last_update_time (most recent)
    for line in analysis_lines:
        line_ts = _parse_log_timestamp(line)
        if line_ts is not None:
            if run_start_time is None:
                run_start_time = line_ts
            last_update_time = line_ts

    # Second pass: process equity using the latest available PnL line.
    for line in reversed(analysis_lines):
        # Extract equity from PnL line
        if "PnL:" in line and "Equity:" in line:
            try:
                equity_match = re.search(r"Equity:\s*([\d.]+)\s*USDT", line)
                session_match = re.search(r"Session:\s*([+-]?[\d.]+)\s*USDT\s*\(([+-]?[\d.]+)%\)", line)
                if equity_match:
                    equity = float(equity_match.group(1))
                if session_match:
                    session_pnl = float(session_match.group(1))
                    session_pnl_pct = float(session_match.group(2))
            except Exception:
                pass

    pair_history = _extract_pair_history(
        analysis_lines,
        run_start_time=run_start_time,
        last_update_time=last_update_time,
    )
    if resolved_run_key and resolved_run_key != "__control__":
        try:
            db_pair_history = _load_pair_history_from_database(
                resolved_run_key,
                last_update_time=last_update_time,
            )
            if db_pair_history:
                pair_history = db_pair_history
        except Exception:
            pass

    # If run_start_time wasn't set, use last_update_time as fallback (for runs with timestamps)
    if run_start_time is None and last_update_time is not None:
        run_start_time = last_update_time

    # Format last log time as ISO for frontend
    last_log_iso = datetime.fromtimestamp(last_update_time, timezone.utc).isoformat() if last_update_time else None

    return {
        "run_key": resolved_run_key,
        "log_file": str(log_file),
        "line_count": len(output_lines),
        "lines": output_lines,
        "updated_at": last_log_iso,  # Use actual last log time instead of current time
        "detail": source,
        "equity": equity,
        "starting_equity": starting_equity,
        "session_pnl": session_pnl,
        "session_pnl_pct": session_pnl_pct,
        "run_start_time": run_start_time,
        "run_end_time": last_update_time,
        "pair_history": pair_history,
        "pair_count": len(pair_history),
    }


def list_log_runs(limit: int = 100) -> list[dict]:
    if not LOGS_ROOT.exists():
        return []
    rows: list[dict] = []
    for run_dir in LOGS_ROOT.iterdir():
        if not run_dir.is_dir() or not run_dir.name.startswith("run_"):
            continue
        log_files = sorted(run_dir.glob("log_*.log"))
        if not log_files:
            continue
        log_file = log_files[-1]
        try:
            stat = log_file.stat()
            rows.append(
                {
                    "run_key": run_dir.name,
                    "log_file": str(log_file),
                    "size_bytes": int(stat.st_size),
                    "mtime_ts": float(stat.st_mtime),
                }
            )
        except Exception:
            continue
    rows.sort(key=lambda item: item.get("mtime_ts", 0.0), reverse=True)
    return rows[: max(min(int(limit), 500), 1)]


def read_run_log(run_key: str) -> dict:
    resolved_run_key, log_file = _resolve_run_log_file(run_key)
    if not resolved_run_key or not log_file:
        raise FileNotFoundError("Log run not found")

    try:
        content = log_file.read_text(encoding="utf-8", errors="ignore")
        stat = log_file.stat()
    except Exception as exc:
        raise RuntimeError(f"Failed to read log file: {exc}") from exc

    line_count = content.count("\n")
    if content and not content.endswith("\n"):
        line_count += 1

    return {
        "run_key": resolved_run_key,
        "log_file": str(log_file),
        "content": content,
        "size_bytes": int(stat.st_size),
        "line_count": int(line_count),
        "updated_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def _clear_deleted_run_state(run_key: str) -> None:
    selected = str(run_key or "").strip()
    if not selected:
        return
    state = _read_state()
    if str(state.get("run_key") or "").strip() != selected:
        return
    if bool(state.get("running")):
        return
    for key in ("run_key", "run_log_file", "starting_equity", "run_start_time"):
        state.pop(key, None)
    _write_state(state)


def _delete_run_database_records(db: Session, run_key: str) -> dict[str, int]:
    selected = str(run_key or "").strip()
    counts = {
        "deleted_run_rows": 0,
        "deleted_run_events": 0,
        "deleted_pair_segments": 0,
        "deleted_trades": 0,
        "deleted_strategy_metrics": 0,
        "deleted_regime_metrics": 0,
        "deleted_bot_configs": 0,
        "deleted_alerts": 0,
        "deleted_equity_snapshots": 0,
        "deleted_position_snapshots": 0,
        "deleted_report_rows": 0,
        "deleted_report_files": 0,
    }
    if not selected:
        return counts

    run = db.execute(select(Run).where(Run.run_key == selected)).scalar_one_or_none()
    if not run:
        return counts

    report_ids = db.execute(
        select(Report.id).where(Report.run_id == run.id)
    ).scalars().all()
    if report_ids:
        counts["deleted_report_files"] = int(
            db.execute(delete(ReportFile).where(ReportFile.report_id.in_(report_ids))).rowcount or 0
        )
    counts["deleted_report_rows"] = int(
        db.execute(delete(Report).where(Report.run_id == run.id)).rowcount or 0
    )

    for key, model in (
        ("deleted_run_events", RunEvent),
        ("deleted_pair_segments", RunPairSegment),
        ("deleted_trades", Trade),
        ("deleted_strategy_metrics", StrategyMetric),
        ("deleted_regime_metrics", RegimeMetric),
        ("deleted_bot_configs", BotConfig),
        ("deleted_alerts", Alert),
        ("deleted_equity_snapshots", EquitySnapshot),
        ("deleted_position_snapshots", PositionSnapshot),
    ):
        counts[key] = int(db.execute(delete(model).where(model.run_id == run.id)).rowcount or 0)

    counts["deleted_run_rows"] = int(
        db.execute(delete(Run).where(Run.id == run.id)).rowcount or 0
    )
    return counts


def delete_log_run(run_key: str) -> dict:
    requested_run_key = str(run_key or "").strip()
    if not requested_run_key:
        raise FileNotFoundError("Run data not found")

    resolved_run_key, log_file = _resolve_run_log_file(requested_run_key)
    effective_run_key = resolved_run_key or requested_run_key

    status = get_bot_status()
    active_run_key = str(status.get("run_key") or "").strip()
    latest_run_key = str(status.get("latest_run_key") or "").strip()
    if status.get("running") and effective_run_key in {active_run_key, latest_run_key}:
        raise RuntimeError("Cannot delete the active log run while the bot is running")

    run_dir = _resolve_run_directory(LOGS_ROOT, effective_run_key)
    report_dir = _resolve_run_directory(REPORTS_ROOT, effective_run_key)

    removed_files = 0
    if run_dir:
        for path in run_dir.rglob("*"):
            if path.is_file():
                removed_files += 1
    removed_report_files = 0
    if report_dir:
        for path in report_dir.rglob("*"):
            if path.is_file():
                removed_report_files += 1

    db_counts: dict[str, int] = {}
    db: Session | None = None
    try:
        db = SessionLocal()
        db_counts = _delete_run_database_records(db, effective_run_key)
        has_database_artifacts = any(value > 0 for value in db_counts.values())
        if not run_dir and not report_dir and not has_database_artifacts:
            raise FileNotFoundError("Run data not found")
        db.commit()
    except FileNotFoundError:
        if db is not None:
            db.rollback()
        raise
    except Exception as exc:
        if db is not None:
            db.rollback()
        raise RuntimeError(f"Failed to delete database records for {effective_run_key}: {exc}") from exc
    finally:
        if db is not None:
            db.close()

    if run_dir:
        try:
            shutil.rmtree(run_dir)
        except Exception as exc:
            raise RuntimeError(f"Failed to delete log run: {exc}") from exc
    if report_dir:
        try:
            shutil.rmtree(report_dir)
        except Exception as exc:
            raise RuntimeError(f"Failed to delete report run: {exc}") from exc

    _clear_deleted_run_state(effective_run_key)

    return {
        "deleted": True,
        "run_key": effective_run_key,
        "log_file": str(log_file) if log_file else None,
        "removed_files": removed_files,
        "removed_report_files": removed_report_files,
        "deleted_report_dir": bool(report_dir),
        **db_counts,
    }


def list_report_runs(limit: int = 100) -> list[dict]:
    if not REPORTS_ROOT.exists():
        return []
    rows: list[dict] = []
    for run_dir in REPORTS_ROOT.iterdir():
        if not run_dir.is_dir() or not run_dir.name.startswith("run_"):
            continue
        files = [p for p in run_dir.iterdir() if p.is_file()]
        summary_path = run_dir / "summary.json"
        summary_exists = summary_path.exists()
        latest_mtime = 0.0
        for file_path in files:
            try:
                latest_mtime = max(latest_mtime, float(file_path.stat().st_mtime))
            except Exception:
                continue
        rows.append(
            {
                "run_key": run_dir.name,
                "path": str(run_dir),
                "file_count": len(files),
                "summary_json": summary_exists,
                "mtime_ts": latest_mtime,
            }
        )

    def _report_sort_key(item: dict) -> tuple:
        run_key = str(item.get("run_key") or "").strip()
        match = RUN_KEY_SORT_RE.match(run_key)
        if match:
            timestamp_key = f"{match.group('date')}{match.group('time')}"
            sequence = int(match.group("seq") or 0)
            return (timestamp_key, sequence, float(item.get("mtime_ts") or 0.0), run_key)
        return ("", 0, float(item.get("mtime_ts") or 0.0), run_key)

    rows.sort(key=_report_sort_key, reverse=True)
    return rows[: max(min(int(limit), 500), 1)]


def _read_json_object(path: Path) -> dict | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(parsed, dict):
        return parsed
    return {"_value": parsed}


def _coerce_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _report_file_sort_key(name: str) -> tuple[int, str]:
    priority = {
        "summary.json": 0,
        "report_manifest.json": 1,
        "trade_closes.csv": 2,
        "open_trades.csv": 3,
        "pair_history.csv": 4,
        "equity_curve.csv": 5,
        "event_counts.json": 6,
    }
    return priority.get(name, 100), name.lower()


def get_report_run_summary(db: Session, run_key: str) -> dict:
    selected = str(run_key or "").strip()
    if not selected:
        raise FileNotFoundError("Report run not found")

    run = db.execute(select(Run).where(Run.run_key == selected)).scalar_one_or_none()
    report_dir = _resolve_run_directory(REPORTS_ROOT, selected)
    summary_path = report_dir / "summary.json" if report_dir else None
    manifest_path = report_dir / "report_manifest.json" if report_dir else None
    db_changed_after_summary = False
    if run and summary_path is not None and summary_path.exists():
        latest_event_created_at = db.execute(
            select(func.max(RunEvent.created_at)).where(RunEvent.run_id == run.id)
        ).scalar_one_or_none()
        if latest_event_created_at is not None:
            if latest_event_created_at.tzinfo is None:
                latest_event_created_at = latest_event_created_at.replace(tzinfo=timezone.utc)
            else:
                latest_event_created_at = latest_event_created_at.astimezone(timezone.utc)
            try:
                summary_mtime = datetime.fromtimestamp(summary_path.stat().st_mtime, tz=timezone.utc)
                db_changed_after_summary = latest_event_created_at.timestamp() > (summary_mtime.timestamp() + 0.5)
            except Exception:
                db_changed_after_summary = True
    should_refresh = bool(
        run and (
            run.status == "running"
            or summary_path is None
            or not summary_path.exists()
            or manifest_path is None
            or not manifest_path.exists()
            or db_changed_after_summary
        )
    )
    refreshed = False

    if should_refresh:
        from .live_report import materialize_live_run_report

        result = materialize_live_run_report(db, run)
        refreshed = bool(result.get("saved"))
        report_dir = _resolve_run_directory(REPORTS_ROOT, selected)
        summary_path = report_dir / "summary.json" if report_dir else None
        manifest_path = report_dir / "report_manifest.json" if report_dir else None

    if not report_dir:
        raise FileNotFoundError("Report run not found")

    summary = _read_json_object(summary_path) if summary_path else None
    manifest = _read_json_object(manifest_path) if manifest_path else None
    manifest_entries = manifest.get("files") if isinstance(manifest, dict) else None
    manifest_by_name: dict[str, dict] = {}
    if isinstance(manifest_entries, list):
        for entry in manifest_entries:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            if name:
                manifest_by_name[name] = entry

    files: list[dict] = []
    for path in sorted(report_dir.glob("*"), key=lambda item: _report_file_sort_key(item.name)):
        if not path.is_file():
            continue
        manifest_entry = manifest_by_name.get(path.name, {})
        mime_type, _ = mimetypes.guess_type(str(path))
        rows = _coerce_int(manifest_entry.get("rows")) if isinstance(manifest_entry, dict) else None
        if rows is None and path.suffix.lower() == ".json":
            rows = 1
        try:
            stat = path.stat()
            size_bytes = int(stat.st_size)
            mtime_ts = float(stat.st_mtime)
        except Exception:
            size_bytes = None
            mtime_ts = None
        files.append(
            {
                "name": path.name,
                "format": str(manifest_entry.get("format") or path.suffix.lstrip(".") or "").strip() or None,
                "rows": rows,
                "size_bytes": size_bytes,
                "mtime_ts": mtime_ts,
                "mime_type": mime_type,
            }
        )

    generated_at = None
    if isinstance(manifest, dict):
        generated_at = str(manifest.get("generated_at") or "").strip() or None
    if not generated_at and isinstance(summary, dict):
        generated_at = str(summary.get("report_created_at") or "").strip() or None

    report_version = None
    report_source = None
    if isinstance(summary, dict):
        report_version = str(summary.get("report_version") or "").strip() or None
        report_source = str(summary.get("report_source") or "").strip() or None
    if not report_version and isinstance(manifest, dict):
        report_version = str(manifest.get("report_version") or "").strip() or None
    if not report_source and isinstance(manifest, dict):
        report_source = str(manifest.get("report_source") or "").strip() or None

    return {
        "run_key": selected,
        "run_id": run.id if run else None,
        "path": str(report_dir),
        "refreshed": refreshed,
        "summary_available": summary is not None,
        "generated_at": generated_at,
        "report_version": report_version,
        "report_source": report_source,
        "summary": summary,
        "manifest": manifest,
        "files": files,
    }


def get_report_run_file(run_key: str, file_name: str) -> dict:
    report_dir = _resolve_run_directory(REPORTS_ROOT, run_key)
    if not report_dir:
        raise FileNotFoundError("Report run not found")
    requested_name = str(file_name or "").strip()
    if not requested_name:
        raise FileNotFoundError("Report file not found")
    candidate = (report_dir / requested_name).resolve()
    if candidate.parent != report_dir.resolve():
        raise FileNotFoundError("Report file not found")
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError("Report file not found")
    mime_type, _ = mimetypes.guess_type(str(candidate))
    return {
        "path": str(candidate),
        "filename": candidate.name,
        "media_type": mime_type or "application/octet-stream",
    }


def build_report_run_zip(run_key: str) -> tuple[bytes, str]:
    report_dir = _resolve_run_directory(REPORTS_ROOT, run_key)
    if not report_dir:
        raise FileNotFoundError("Report run not found")

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(report_dir.rglob("*")):
            if not path.is_file():
                continue
            archive.write(path, arcname=f"{report_dir.name}/{path.relative_to(report_dir).as_posix()}")
    return buffer.getvalue(), f"{report_dir.name}_report.zip"


def clear_logs_and_reports(keep_latest: bool = False) -> dict:
    """Clear log and report directories.

    Args:
        keep_latest: If True, keeps the most recent run directory. If False, clears all.

    Returns:
        dict with counts of deleted items and any errors.
    """
    deleted_logs = 0
    deleted_reports = 0
    deleted_log_files = 0
    deleted_run_rows = 0
    deleted_run_events = 0
    deleted_pair_segments = 0
    deleted_trades = 0
    deleted_strategy_metrics = 0
    deleted_regime_metrics = 0
    deleted_bot_configs = 0
    deleted_alerts = 0
    deleted_equity_snapshots = 0
    deleted_position_snapshots = 0
    deleted_report_rows = 0
    deleted_report_files = 0
    deleted_indexes = 0
    errors: list[str] = []

    def get_sorted_runs(root: Path) -> list[tuple[float, Path]]:
        if not root.exists():
            return []
        runs: list[tuple[float, Path]] = []
        for run_dir in root.iterdir():
            if run_dir.is_dir() and run_dir.name.startswith("run_"):
                try:
                    mtime = run_dir.stat().st_mtime
                    runs.append((mtime, run_dir))
                except Exception:
                    continue
        runs.sort(key=lambda x: x[0], reverse=True)
        return runs

    def remove_path(path: Path) -> bool:
        try:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
            return True
        except Exception as exc:
            errors.append(f"Failed to delete {path.name}: {exc}")
            return False

    def clear_index_files(root: Path) -> int:
        removed = 0
        for name in ("index.csv", "index.json"):
            path = root / name
            if path.exists() and remove_path(path):
                removed += 1
        return removed

    protected_run_keys: set[str] = set()
    run_keys_to_delete: set[str] = set()
    log_dirs_to_delete: list[Path] = []
    report_dirs_to_delete: list[Path] = []

    # Handle logs
    if LOGS_ROOT.exists():
        log_runs = get_sorted_runs(LOGS_ROOT)
        for idx, (_, run_dir) in enumerate(log_runs):
            if keep_latest and idx == 0:
                protected_run_keys.add(run_dir.name)
                continue  # Keep the newest
            run_keys_to_delete.add(run_dir.name)
            log_dirs_to_delete.append(run_dir)
        aggregate_log_files = [CONTROL_LOG_FILE, LOGS_ROOT / PAIR_SUPPLY_LOG_FILE.name]
        _max_log_mb, max_backups = log_rotation_settings(ENV_FILE)
        for path in aggregate_log_files:
            for candidate in [path, *rotated_log_paths(path, max_backups)]:
                if candidate.exists() and remove_path(candidate):
                    deleted_log_files += 1
        deleted_indexes += clear_index_files(LOGS_ROOT)

    # Handle reports
    if REPORTS_ROOT.exists():
        report_runs = get_sorted_runs(REPORTS_ROOT)
        for idx, (_, run_dir) in enumerate(report_runs):
            if keep_latest and idx == 0:
                protected_run_keys.add(run_dir.name)
                continue  # Keep the newest
            run_keys_to_delete.add(run_dir.name)
            report_dirs_to_delete.append(run_dir)
        deleted_indexes += clear_index_files(REPORTS_ROOT)

    db: Session | None = None
    try:
        db = SessionLocal()
        run_keys_from_db = {
            str(run_key or "").strip()
            for run_key in db.execute(select(Run.run_key)).scalars().all()
            if str(run_key or "").strip()
        }
        if keep_latest:
            latest_db_run_key = db.execute(
                select(Run.run_key).order_by(Run.start_ts.desc()).limit(1)
            ).scalar_one_or_none()
            if latest_db_run_key:
                protected_run_keys.add(str(latest_db_run_key).strip())
        if not keep_latest:
            run_keys_to_delete.update(run_keys_from_db)
        else:
            run_keys_to_delete.update(run_keys_from_db - protected_run_keys)

        for run_key in sorted(run_keys_to_delete):
            counts = _delete_run_database_records(db, run_key)
            deleted_run_rows += counts["deleted_run_rows"]
            deleted_run_events += counts["deleted_run_events"]
            deleted_pair_segments += counts["deleted_pair_segments"]
            deleted_trades += counts["deleted_trades"]
            deleted_strategy_metrics += counts["deleted_strategy_metrics"]
            deleted_regime_metrics += counts["deleted_regime_metrics"]
            deleted_bot_configs += counts["deleted_bot_configs"]
            deleted_alerts += counts["deleted_alerts"]
            deleted_equity_snapshots += counts["deleted_equity_snapshots"]
            deleted_position_snapshots += counts["deleted_position_snapshots"]
            deleted_report_rows += counts["deleted_report_rows"]
            deleted_report_files += counts["deleted_report_files"]

        for run_key in run_keys_to_delete:
            _clear_deleted_run_state(run_key)

        if run_keys_to_delete:
            db.commit()
    except Exception as exc:
        if db is not None:
            db.rollback()
        errors.append(f"Failed to clear run records: {exc}")
    finally:
        if db is not None:
            db.close()

    for run_dir in log_dirs_to_delete:
        if remove_path(run_dir):
            deleted_logs += 1

    for run_dir in report_dirs_to_delete:
        if remove_path(run_dir):
            deleted_reports += 1

    return {
        "deleted_logs": deleted_logs,
        "deleted_reports": deleted_reports,
        "deleted_log_files": deleted_log_files,
        "deleted_run_rows": deleted_run_rows,
        "deleted_run_events": deleted_run_events,
        "deleted_pair_segments": deleted_pair_segments,
        "deleted_trades": deleted_trades,
        "deleted_strategy_metrics": deleted_strategy_metrics,
        "deleted_regime_metrics": deleted_regime_metrics,
        "deleted_bot_configs": deleted_bot_configs,
        "deleted_alerts": deleted_alerts,
        "deleted_equity_snapshots": deleted_equity_snapshots,
        "deleted_position_snapshots": deleted_position_snapshots,
        "deleted_report_rows": deleted_report_rows,
        "deleted_report_files": deleted_report_files,
        "deleted_indexes": deleted_indexes,
        "kept_latest": keep_latest,
        "errors": errors,
    }


def read_env_settings() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_FILE.exists():
        return values
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except Exception:
        return values
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip()
    return values


def update_env_setting(key: str, value: str) -> dict:
    setting_key = str(key or "").strip()
    if not setting_key:
        return {"ok": False, "detail": "empty_key"}
    if any(ch.isspace() for ch in setting_key):
        return {"ok": False, "detail": "invalid_key_whitespace"}

    new_value = str(value if value is not None else "")

    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    updated = False
    next_lines: list[str] = []
    for raw in lines:
        stripped = raw.lstrip()
        if stripped.startswith("#") or "=" not in raw:
            next_lines.append(raw)
            continue
        old_key, _old_value = raw.split("=", 1)
        if old_key.strip() == setting_key:
            next_lines.append(f"{setting_key}={new_value}")
            updated = True
        else:
            next_lines.append(raw)

    if not updated:
        if next_lines and next_lines[-1].strip():
            next_lines.append("")
        next_lines.append(f"{setting_key}={new_value}")

    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text("\n".join(next_lines).rstrip("\n") + "\n", encoding="utf-8")
    return {"ok": True, "detail": "updated", "key": setting_key, "value": new_value}


PAIR_STRATEGY_STATE_FILE = EXECUTION_ROOT / "state" / "pair_strategy_state.json"
ACTIVE_PAIR_FILE = EXECUTION_ROOT / "state" / "active_pair.json"
MANUAL_PAIR_SWITCH_FILE = EXECUTION_ROOT / "state" / "manual_pair_switch.json"
GRAVEYARD_TICKERS_FILE = EXECUTION_ROOT / "state" / "graveyard_tickers.json"
TICKER_GRAVEYARD_PREFIX = "ticker::"
TICKER_ID_RE = re.compile(r"^[A-Z0-9]+-[A-Z]+-SWAP$")


class ManualPairSwitchBlocked(RuntimeError):
    def __init__(self, result: dict):
        self.result = result
        super().__init__(str(result.get("detail") or "Manual pair switch blocked"))


def _read_json_object(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_object(path: Path, data: dict) -> None:
    payload = dict(data or {})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _normalize_ticker_id(value: object) -> str:
    ticker = str(value or "").strip().upper()
    if not ticker or not TICKER_ID_RE.match(ticker):
        raise ValueError(f"Invalid OKX swap ticker: {value}")
    return ticker


def _pair_key(ticker_1: str | None, ticker_2: str | None) -> str | None:
    t1 = str(ticker_1 or "").strip().upper()
    t2 = str(ticker_2 or "").strip().upper()
    if not t1 or not t2:
        return None
    return f"{t1}/{t2}"


def _read_active_pair() -> dict | None:
    active = _read_json_object(ACTIVE_PAIR_FILE)
    t1 = str(active.get("ticker_1") or "").strip().upper()
    t2 = str(active.get("ticker_2") or "").strip().upper()
    if not t1 or not t2:
        return None
    return {"ticker_1": t1, "ticker_2": t2, "pair": f"{t1}/{t2}"}


def _write_active_pair(ticker_1: str, ticker_2: str) -> None:
    _write_json_object(
        ACTIVE_PAIR_FILE,
        {
            "ticker_1": ticker_1,
            "ticker_2": ticker_2,
            "updated_at": _utc_iso_now(),
            "source": "manual_dashboard_switch",
        },
    )


def _append_control_log(level: str, message: str) -> None:
    try:
        CONTROL_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        ts = _log_now()
        timestamp_text = f"{ts.strftime('%Y-%m-%d %H:%M:%S')},{int(ts.microsecond / 1000):03d}"
        with open_rotating_append_log(CONTROL_LOG_FILE, env_file=ENV_FILE) as handle:
            handle.write(f"{timestamp_text} {str(level or 'INFO').upper()} {message}\n")
    except Exception:
        pass


def _manual_switch_target_in_pair_universe(ticker_1: str, ticker_2: str) -> bool:
    try:
        from .cointegrated_pairs import list_cointegrated_pairs

        universe = list_cointegrated_pairs(limit=1000)
        target = {ticker_1, ticker_2}
        for pair in universe.get("pairs", []):
            if {str(pair.get("sym_1") or "").strip().upper(), str(pair.get("sym_2") or "").strip().upper()} == target:
                return True
    except Exception:
        return True
    return False


def _latest_run_for_manual_switch(db: Session, bot_status: dict) -> Run | None:
    run_key = str(bot_status.get("run_key") or bot_status.get("latest_run_key") or "").strip()
    if run_key:
        run = db.execute(select(Run).where(Run.run_key == run_key)).scalar_one_or_none()
        if run:
            return run
    return db.execute(
        select(Run)
        .order_by(Run.start_ts.desc(), Run.created_at.desc(), Run.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _latest_event_payload(db: Session, run_id: str, event_type: str) -> dict:
    row = db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run_id, RunEvent.event_type == event_type)
        .order_by(RunEvent.ts.desc(), RunEvent.created_at.desc(), RunEvent.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row and isinstance(row.payload_json, dict):
        return row.payload_json
    return {}


def _latest_event_row(db: Session, run_id: str, event_type: str) -> RunEvent | None:
    return db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run_id, RunEvent.event_type == event_type)
        .order_by(RunEvent.ts.desc(), RunEvent.created_at.desc(), RunEvent.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _as_utc_dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _ts_is_at_or_after(candidate: datetime | None, reference: datetime | None) -> bool:
    candidate_utc = _as_utc_dt(candidate)
    reference_utc = _as_utc_dt(reference)
    if candidate_utc is None:
        return False
    if reference_utc is None:
        return True
    return candidate_utc >= reference_utc


def _latest_trade_close_ts(db: Session, run_id: str, pair_key: str | None = None) -> datetime | None:
    rows = db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run_id, RunEvent.event_type == "trade_close")
        .order_by(RunEvent.ts.desc(), RunEvent.created_at.desc(), RunEvent.id.desc())
    ).scalars().all()
    for row in rows:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        raw_pair = str(payload.get("pair") or payload.get("current_pair") or "").strip().upper()
        event_pair = raw_pair
        if "/" in raw_pair:
            left, right = raw_pair.split("/", 1)
            event_pair = _pair_key(left, right) or raw_pair
        if pair_key and (not event_pair or event_pair != pair_key):
            continue
        return _as_utc_dt(row.ts)
    return None


def _manual_switch_blockers(db: Session, run: Run | None, *, bot_running: bool) -> list[str]:
    if run is None:
        return []

    blockers: list[str] = []
    latest_equity = db.execute(
        select(EquitySnapshot)
        .where(EquitySnapshot.run_id == run.id)
        .order_by(EquitySnapshot.ts.desc(), EquitySnapshot.created_at.desc(), EquitySnapshot.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if latest_equity is not None and bool(latest_equity.in_position):
        pair = str(latest_equity.current_pair or "").strip() or "the active pair"
        blockers.append(f"Latest runtime snapshot reports an open position/order on {pair}.")

    latest_heartbeat_row = _latest_event_row(db, run.id, "heartbeat")
    heartbeat_payload = latest_heartbeat_row.payload_json if latest_heartbeat_row and isinstance(latest_heartbeat_row.payload_json, dict) else {}
    if bool(heartbeat_payload.get("in_position")):
        pair = str(heartbeat_payload.get("current_pair") or heartbeat_payload.get("pair") or "").strip() or "the active pair"
        blockers.append(f"Latest heartbeat reports the bot is still in position/orders on {pair}.")

    open_trade = db.execute(
        select(Trade)
        .where(Trade.run_id == run.id, Trade.exit_ts.is_(None))
        .order_by(Trade.entry_ts.desc().nullslast(), Trade.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if open_trade is not None and (bot_running or str(run.status or "").strip().lower() == "running"):
        flat_runtime_after_trade = (
            (latest_equity is not None and not bool(latest_equity.in_position) and _ts_is_at_or_after(latest_equity.ts, open_trade.entry_ts))
            or (latest_heartbeat_row is not None and not bool(heartbeat_payload.get("in_position")) and _ts_is_at_or_after(latest_heartbeat_row.ts, open_trade.entry_ts))
            or _ts_is_at_or_after(_latest_trade_close_ts(db, run.id, open_trade.pair_key), open_trade.entry_ts)
        )
        if not flat_runtime_after_trade:
            blockers.append(f"Open trade record exists for {open_trade.pair_key}; wait for it to close before switching.")

    return list(dict.fromkeys(blockers))


def _record_manual_pair_switch_event(
    db: Session,
    run: Run | None,
    *,
    request_id: str,
    requested_by: str | None,
    from_pair: str | None,
    to_pair: str,
    status_text: str,
    reason: str,
    blockers: list[str] | None = None,
    severity: str = "info",
) -> RunEvent | None:
    if run is None:
        return None
    row = RunEvent(
        event_id=str(uuid.uuid4()),
        run_id=run.id,
        bot_instance_id=run.bot_instance_id,
        ts=datetime.now(timezone.utc),
        event_type="pair_switch",
        severity=str(severity or "info").lower(),
        payload_json={
            "from_pair": from_pair,
            "to_pair": to_pair,
            "reason": reason,
            "status": status_text,
            "requested_by": requested_by or "",
            "manual_request_id": request_id,
            "blockers": blockers or [],
        },
    )
    db.add(row)
    db.flush()
    sync_run_pair_segments_for_event(db, run, row)
    return row


def manual_switch_active_pair(
    sym_1: str,
    sym_2: str,
    requested_by: str | None = None,
    force: bool = False,
) -> dict:
    """Request a manual active-pair switch from the Cointegration dashboard.

    Args:
        sym_1: First ticker symbol (e.g., 'ETH-USDT-SWAP')
        sym_2: Second ticker symbol (e.g., 'SOL-USDT-SWAP')
        requested_by: Email of the user requesting the switch
        force: If True, bypass blockers and force close any open positions/trades
    """
    ticker_1_next = _normalize_ticker_id(sym_1)
    ticker_2_next = _normalize_ticker_id(sym_2)
    if ticker_1_next == ticker_2_next:
        raise ValueError("Manual pair switch requires two different tickers.")
    if not _manual_switch_target_in_pair_universe(ticker_1_next, ticker_2_next):
        raise ValueError(f"{ticker_1_next}/{ticker_2_next} is not in the current Pair Universe.")

    target_pair = f"{ticker_1_next}/{ticker_2_next}"
    previous = _read_active_pair()
    from_pair = previous.get("pair") if previous else None
    request_id = str(uuid.uuid4())
    bot_status = get_bot_status()
    bot_running = bool(bot_status.get("running"))

    db: Session = SessionLocal()
    try:
        run = _latest_run_for_manual_switch(db, bot_status)
        # If force=True, bypass all blockers
        if not force:
            blockers = _manual_switch_blockers(db, run, bot_running=bot_running)
            if blockers:
                detail = "Manual pair switch is not allowed because " + " ".join(blockers)
                _record_manual_pair_switch_event(
                    db,
                    run,
                    request_id=request_id,
                    requested_by=requested_by,
                    from_pair=from_pair,
                    to_pair=target_pair,
                    status_text="blocked",
                    reason="manual_switch",
                    blockers=blockers,
                    severity="warn",
                )
                db.commit()
                _append_control_log(
                    "WARNING",
                    f"Manual pair switch blocked by {requested_by or 'unknown'}: from={from_pair or 'n/a'} to={target_pair} blockers={' | '.join(blockers)}",
                )
                raise ManualPairSwitchBlocked(
                    {
                        "ok": False,
                        "allowed": False,
                        "status": "blocked",
                        "detail": detail,
                        "blockers": blockers,
                        "requested_by": requested_by or "",
                        "previous_active_pair": previous,
                        "target_pair": {"ticker_1": ticker_1_next, "ticker_2": ticker_2_next, "pair": target_pair},
                        "running": bot_running,
                        "request_id": request_id,
                        "force_available": True,
                    }
                )
        else:
            # Force mode: log the forced switch request
            _append_control_log(
                "WARNING",
                f"FORCE manual pair switch requested by {requested_by or 'unknown'}: from={from_pair or 'n/a'} to={target_pair}; will force close positions",
            )

        if from_pair == target_pair:
            detail = f"{target_pair} is already the active pair."
            _append_control_log("INFO", f"Manual pair switch no-op by {requested_by or 'unknown'}: {target_pair} is already active")
            return {
                "ok": True,
                "allowed": True,
                "status": "already_active",
                "detail": detail,
                "requested_by": requested_by or "",
                "previous_active_pair": previous,
                "active_pair": previous,
                "target_pair": {"ticker_1": ticker_1_next, "ticker_2": ticker_2_next, "pair": target_pair},
                "running": bot_running,
                "request_id": request_id,
            }

        if bot_running:
            request = {
                "id": request_id,
                "status": "requested",
                "ticker_1": ticker_1_next,
                "ticker_2": ticker_2_next,
                "pair": target_pair,
                "requested_by": requested_by or "",
                "requested_at": _utc_iso_now(),
                "from_pair": from_pair,
                "force": force,
            }
            _write_json_object(MANUAL_PAIR_SWITCH_FILE, request)
            _record_manual_pair_switch_event(
                db,
                run,
                request_id=request_id,
                requested_by=requested_by,
                from_pair=from_pair,
                to_pair=target_pair,
                status_text="requested",
                reason="manual_switch" + ("_force" if force else ""),
                severity="warning" if force else "info",
            )
            db.commit()
            _append_control_log(
                "INFO",
                f"Manual pair switch requested by {requested_by or 'unknown'}: from={from_pair or 'n/a'} to={target_pair}; waiting for execution loop safety check",
            )
            return {
                "ok": True,
                "allowed": True,
                "status": "requested",
                "pending": True,
                "detail": f"Manual switch to {target_pair} requested. The running bot will apply it after its safety check.",
                "requested_by": requested_by or "",
                "previous_active_pair": previous,
                "active_pair": previous,
                "target_pair": {"ticker_1": ticker_1_next, "ticker_2": ticker_2_next, "pair": target_pair},
                "running": bot_running,
                "request_id": request_id,
            }

        _write_active_pair(ticker_1_next, ticker_2_next)
        active_pair = _read_active_pair()
        _append_control_log(
            "INFO",
            f"Manual active pair set by {requested_by or 'unknown'} while bot stopped: from={from_pair or 'n/a'} to={target_pair}",
        )
        return {
            "ok": True,
            "allowed": True,
            "status": "applied",
            "pending": False,
            "detail": f"Active pair set to {target_pair}. The next bot start will use this pair.",
            "requested_by": requested_by or "",
            "previous_active_pair": previous,
            "active_pair": active_pair,
            "target_pair": {"ticker_1": ticker_1_next, "ticker_2": ticker_2_next, "pair": target_pair},
            "running": bot_running,
            "request_id": request_id,
        }
    finally:
        db.close()


def _normalize_restricted_ticker_entry(ticker: str, entry: object, default_source: str) -> dict | None:
    ticker_text = str(ticker or "").strip()
    if not ticker_text:
        return None

    if isinstance(entry, dict):
        added_at_raw = entry.get("ts", 0)
        try:
            added_at = float(added_at_raw)
        except (TypeError, ValueError):
            added_at = 0.0
        ttl_days_raw = entry.get("ttl_days")
        try:
            ttl_days = float(ttl_days_raw) if ttl_days_raw is not None else None
        except (TypeError, ValueError):
            ttl_days = None
        code = str(entry.get("code") or "").strip()
        message = str(entry.get("msg") or "").strip()
        reason = str(entry.get("reason") or "").strip() or (message or "restricted")
        source = str(entry.get("source") or default_source).strip() or default_source
        return {
            "ticker": ticker_text,
            "reason": reason,
            "message": message,
            "code": code,
            "added_at": added_at,
            "ttl_days": ttl_days,
            "source": source,
        }

    text = str(entry or "").strip()
    if not text:
        return None
    return {
        "ticker": ticker_text,
        "reason": text,
        "message": text,
        "code": "",
        "added_at": 0.0,
        "ttl_days": None,
        "source": default_source,
    }


def _is_ticker_graveyard_key(key: str) -> bool:
    return str(key or "").startswith(TICKER_GRAVEYARD_PREFIX)


def _graveyard_ticker_from_key(key: str) -> str:
    key_text = str(key or "").strip()
    if not _is_ticker_graveyard_key(key_text):
        return ""
    return key_text[len(TICKER_GRAVEYARD_PREFIX):]


def clear_active_pair(requested_by: str | None = None, auto_select_healthiest: bool = False) -> dict:
    """Clear the persisted active_pair.json so startup falls back to defaults.

    Args:
        requested_by: Email of the user requesting the clear
        auto_select_healthiest: If True, find the healthiest pair and set it as the new active pair
    """
    existed = ACTIVE_PAIR_FILE.exists()
    previous: dict | None = None

    if existed:
        previous_data = _read_json_object(ACTIVE_PAIR_FILE)
        if previous_data.get("ticker_1") and previous_data.get("ticker_2"):
            previous = {
                "ticker_1": str(previous_data.get("ticker_1") or "").strip(),
                "ticker_2": str(previous_data.get("ticker_2") or "").strip(),
            }

    status = get_bot_status()
    running = bool(status.get("running"))
    new_pair = None

    # If auto_select_healthiest is True, find the healthiest pair and set it
    if auto_select_healthiest:
        try:
            from .cointegrated_pairs import get_healthiest_pair_from_curator

            healthiest = get_healthiest_pair_from_curator()
            if healthiest and healthiest.get("ticker_1") and healthiest.get("ticker_2"):
                _write_active_pair(
                    str(healthiest["ticker_1"]),
                    str(healthiest["ticker_2"]),
                )
                new_pair = {
                    "ticker_1": str(healthiest["ticker_1"]),
                    "ticker_2": str(healthiest["ticker_2"]),
                    "pair": str(healthiest.get("pair", "")),
                    "priority_rank": healthiest.get("priority_rank"),
                    "score": healthiest.get("score"),
                }
                existed = True
            else:
                _append_control_log("WARNING", "Clear active pair: no healthiest pair found in curator report")
        except Exception as exc:
            _append_control_log("WARNING", f"Clear active pair: failed to find healthiest pair: {exc}")

    # Only remove the file if we're not setting a new pair
    if new_pair is None and existed:
        try:
            ACTIVE_PAIR_FILE.unlink()
        except FileNotFoundError:
            existed = False
        except Exception as exc:
            raise RuntimeError(f"Failed to clear active pair: {exc}") from exc

    detail = "Persisted active pair cleared."
    if new_pair:
        detail = f"Cleared and switched to healthiest pair: {new_pair.get('pair')}"
    elif not existed:
        detail = "No persisted active pair was set."
    elif running:
        detail = (
            "Persisted active pair cleared. The running bot keeps its in-memory pair until restart."
        )

    return {
        "ok": True,
        "cleared": True,
        "file_existed": existed,
        "running": running,
        "detail": detail,
        "requested_by": requested_by or "",
        "previous_active_pair": previous,
        "active_pair": new_pair,
    }


def get_pair_health_data() -> dict:
    """Get pair health data from state files."""
    result = {
        "hospital": [],
        "graveyard": [],
        "restricted_tickers": [],
        "active_pair": None,
    }

    # Read hospital and graveyard from pair_strategy_state.json
    if PAIR_STRATEGY_STATE_FILE.exists():
        try:
            data = _read_json_object(PAIR_STRATEGY_STATE_FILE)
            now = time.time()

            # Process hospital entries
            hospital = data.get("hospital", {})
            for pair_key, entry in hospital.items():
                if not isinstance(entry, dict):
                    continue
                ts = entry.get("ts", 0)
                cooldown = entry.get("cooldown", 3600)
                elapsed = now - ts
                remaining = max(0, cooldown - elapsed)
                is_ready = remaining <= 0

                result["hospital"].append({
                    "pair": pair_key,
                    "reason": entry.get("reason", "unknown"),
                    "added_at": ts,
                    "cooldown_seconds": cooldown,
                    "elapsed_seconds": elapsed,
                    "remaining_seconds": remaining,
                    "is_ready": is_ready,
                    "visits": entry.get("visits", 1),
                })

            # Process graveyard entries
            graveyard = data.get("graveyard", {})
            merged_restricted = {}
            for pair_key, entry in graveyard.items():
                if not isinstance(entry, dict):
                    continue
                if _is_ticker_graveyard_key(pair_key):
                    ticker = _graveyard_ticker_from_key(pair_key)
                    normalized = _normalize_restricted_ticker_entry(ticker, entry, default_source="runtime")
                    if normalized:
                        merged_restricted[ticker] = normalized
                    continue
                ts = entry.get("ts", 0)
                ttl_days = entry.get("ttl_days")

                result["graveyard"].append({
                    "pair": pair_key,
                    "reason": entry.get("reason", "unknown"),
                    "added_at": ts,
                    "ttl_days": ttl_days,
                })

            restricted_tickers = data.get("restricted_tickers", {})
            for ticker, entry in _read_json_object(GRAVEYARD_TICKERS_FILE).items():
                normalized = _normalize_restricted_ticker_entry(ticker, entry, default_source="seed")
                if normalized:
                    merged_restricted[str(ticker)] = normalized
            if isinstance(restricted_tickers, dict):
                for ticker, entry in restricted_tickers.items():
                    normalized = _normalize_restricted_ticker_entry(ticker, entry, default_source="runtime")
                    if normalized:
                        merged_restricted[str(ticker)] = normalized

            result["restricted_tickers"] = sorted(
                merged_restricted.values(),
                key=lambda item: (str(item.get("source") or ""), str(item.get("ticker") or "")),
            )

        except Exception:
            pass
    elif GRAVEYARD_TICKERS_FILE.exists():
        merged_restricted = {}
        for ticker, entry in _read_json_object(GRAVEYARD_TICKERS_FILE).items():
            normalized = _normalize_restricted_ticker_entry(ticker, entry, default_source="seed")
            if normalized:
                merged_restricted[str(ticker)] = normalized
        result["restricted_tickers"] = sorted(
            merged_restricted.values(),
            key=lambda item: (str(item.get("source") or ""), str(item.get("ticker") or "")),
        )

    # Read active pair
    if ACTIVE_PAIR_FILE.exists():
        try:
            active_pair = json.loads(ACTIVE_PAIR_FILE.read_text(encoding="utf-8"))
            if (
                isinstance(active_pair, dict)
                and active_pair.get("ticker_1")
                and active_pair.get("ticker_2")
            ):
                result["active_pair"] = active_pair
        except Exception:
            pass

    return result
