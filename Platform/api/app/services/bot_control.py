from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import BotInstance, Run


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
STARTING_EQUITY_RE = re.compile(r"Starting equity:\s*(?P<eq>[-+]?\d+(?:\.\d+)?)\s*USDT", re.IGNORECASE)
LOG_TIMESTAMP_RE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
CURRENT_PAIR_RE = re.compile(r"Current pair: (?P<pair>[A-Z0-9]+-[A-Z]+-SWAP/[A-Z0-9]+-[A-Z]+-SWAP)")
PAIR_SWITCH_RE = re.compile(r"Switching from (?P<pair>[A-Z0-9]+-[A-Z]+-SWAP/[A-Z0-9]+-[A-Z]+-SWAP) to")
TICKER_CONFIG_RE = re.compile(
    r"Ticker configuration validated: ticker_1=(?P<t1>[A-Z0-9]+-[A-Z]+-SWAP), ticker_2=(?P<t2>[A-Z0-9]+-[A-Z]+-SWAP)"
)


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


def _parse_iso_timestamp(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


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
        return datetime.strptime(ts_match.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
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
            value = value.astimezone(timezone.utc)
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
    if starting_equity is not None and _coerce_float(state.get("starting_equity")) != float(starting_equity):
        state["starting_equity"] = float(starting_equity)
        changed = True
    if run_start_time is not None and _coerce_float(state.get("run_start_time")) != float(run_start_time):
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
            if starting_equity is not None and _coerce_float(run.start_equity) != float(starting_equity):
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


def _resolve_run_log_file(run_key: str | None) -> tuple[str | None, Path | None]:
    selected = str(run_key or "").strip()
    if not selected or selected.lower() == "latest":
        return _latest_run_log_file()
    run_dir = LOGS_ROOT / selected
    if not run_dir.exists() or not run_dir.is_dir():
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
        or control_mtime >= latest_log_mtime
        or (started_ts > 0 and latest_log_mtime < started_ts)
    )
    if should_prefer_control:
        return "__control__", CONTROL_LOG_FILE, "control_log_preferred"
    return latest_run_key, latest_log_file, "latest_run"


def _normalize_status(state: dict) -> dict:
    data = dict(state or {})
    pid = int(data.get("pid") or 0)
    running = _pid_exists(pid)
    data["pid"] = pid
    data["running"] = running
    if not running and pid > 0:
        data["stopped_at"] = data.get("stopped_at") or _utc_iso_now()
        prior_detail = str(data.get("detail") or "").strip().lower()
        if prior_detail in {"", "started", "already_running"}:
            data["detail"] = "process_exited"
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


def start_bot(requested_by: str | None = None) -> dict:
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
    CONTROL_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log_handle = CONTROL_LOG_FILE.open("a", encoding="utf-8", errors="ignore")

    env = os.environ.copy()
    env["STATBOT_MANAGED"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    # Compute the run_key that the execution script will use
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
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
            stdout=log_handle,
            stderr=log_handle,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        log_handle.close()
        return {
            "running": False,
            "detail": f"start_failed:{exc}",
            "command": command,
        }
    log_handle.close()

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


def stop_bot(requested_by: str | None = None, timeout_seconds: float = 12.0) -> dict:
    state = get_bot_status()
    pid = int(state.get("pid") or 0)
    if pid <= 0 or not state.get("running"):
        state["running"] = False
        state["detail"] = "already_stopped"
        state["stopped_at"] = state.get("stopped_at") or _utc_iso_now()
        state["requested_by"] = requested_by or state.get("requested_by", "")
        _write_state(state)
        return state

    terminated = False
    detail = "stop_sent"
    try:
        if os.name != "nt":
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception as exc:
        detail = f"term_signal_failed:{exc}"

    deadline = time.time() + max(float(timeout_seconds), 1.0)
    while time.time() < deadline:
        if not _pid_exists(pid):
            terminated = True
            break
        time.sleep(0.2)

    if not terminated:
        try:
            if os.name != "nt":
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            else:
                os.kill(pid, signal.SIGKILL)
            terminated = True
            detail = "killed"
        except Exception as exc:
            detail = f"kill_failed:{exc}"

    state["running"] = False
    state["stopped_at"] = _utc_iso_now()
    state["detail"] = "stopped" if terminated else detail
    state["requested_by"] = requested_by or state.get("requested_by", "")
    _write_state(state)
    return _normalize_status(state)


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
    pair_history: list[dict] = []
    current_pair = None
    current_pair_start_ts = None

    # First pass: find run_start_time (earliest timestamp) and last_update_time (most recent)
    for line in output_lines:
        line_ts = _parse_log_timestamp(line)
        if line_ts is not None:
            if run_start_time is None:
                run_start_time = line_ts
            last_update_time = line_ts

    # Second pass: process equity and pair history (can still use reverse iteration)
    for line in reversed(output_lines):
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

        # Parse timestamp from log line - only for pair tracking, NOT for run_start_time
        line_ts = _parse_log_timestamp(line)
        if line_ts is not None:
            try:
                # Don't set run_start_time here - it was already set in first pass

                # Track pair switches
                new_pair = _extract_pair_from_line(line)
                if new_pair is not None:
                    if current_pair and current_pair != new_pair:
                        # Record previous pair's duration.
                        duration = line_ts - current_pair_start_ts if current_pair_start_ts else 0
                        pair_history.append({
                            "pair": current_pair,
                            "duration_seconds": duration,
                        })
                    current_pair = new_pair
                    current_pair_start_ts = line_ts

                switch_match = PAIR_SWITCH_RE.search(line)
                if switch_match:
                    switched_pair = switch_match.group("pair")
                    if current_pair == switched_pair:
                        # Pair was switched away.
                        duration = line_ts - current_pair_start_ts if current_pair_start_ts else 0
                        pair_history.append({
                            "pair": current_pair,
                            "duration_seconds": duration,
                        })
                        current_pair = None
                        current_pair_start_ts = None
            except Exception:
                pass

    # Add the last active pair if still active - use last_update_time for duration
    if current_pair and current_pair_start_ts and last_update_time:
        duration = last_update_time - current_pair_start_ts
        pair_history.append({
            "pair": current_pair,
            "duration_seconds": duration,
        })

    # If run_start_time wasn't set, use last_update_time as fallback (for runs with timestamps)
    if run_start_time is None and last_update_time is not None:
        run_start_time = last_update_time

    # Format last log time as ISO for frontend
    last_log_iso = datetime.fromtimestamp(last_update_time).isoformat() if last_update_time else None

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
    rows.sort(key=lambda item: item.get("mtime_ts", 0.0), reverse=True)
    return rows[: max(min(int(limit), 500), 1)]


def clear_logs_and_reports(keep_latest: bool = True) -> dict:
    """Clear log and report directories.

    Args:
        keep_latest: If True, keeps the most recent run directory. If False, clears all.

    Returns:
        dict with counts of deleted items and any errors.
    """
    deleted_logs = 0
    deleted_reports = 0
    errors: list[str] = []

    # Get list of run directories sorted by modification time (newest first)
    def get_sorted_runs(root):
        if not root.exists():
            return []
        runs = []
        for run_dir in root.iterdir():
            if run_dir.is_dir() and run_dir.name.startswith("run_"):
                try:
                    mtime = run_dir.stat().st_mtime
                    runs.append((mtime, run_dir))
                except Exception:
                    continue
        runs.sort(key=lambda x: x[0], reverse=True)
        return runs

    # Handle logs
    if LOGS_ROOT.exists():
        log_runs = get_sorted_runs(LOGS_ROOT)
        for idx, (_, run_dir) in enumerate(log_runs):
            if keep_latest and idx == 0:
                continue  # Keep the newest
            try:
                # Remove all files in the directory
                for file in run_dir.iterdir():
                    if file.is_file():
                        file.unlink()
                # Remove the directory
                run_dir.rmdir()
                deleted_logs += 1
            except Exception as e:
                errors.append(f"Failed to delete log {run_dir.name}: {e}")

    # Handle reports
    if REPORTS_ROOT.exists():
        report_runs = get_sorted_runs(REPORTS_ROOT)
        for idx, (_, run_dir) in enumerate(report_runs):
            if keep_latest and idx == 0:
                continue  # Keep the newest
            try:
                for file in run_dir.iterdir():
                    if file.is_file():
                        file.unlink()
                run_dir.rmdir()
                deleted_reports += 1
            except Exception as e:
                errors.append(f"Failed to delete report {run_dir.name}: {e}")

    return {
        "deleted_logs": deleted_logs,
        "deleted_reports": deleted_reports,
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


def get_pair_health_data() -> dict:
    """Get pair health data from state files."""
    import json

    result = {
        "hospital": [],
        "graveyard": [],
        "active_pair": None,
    }

    # Read hospital and graveyard from pair_strategy_state.json
    if PAIR_STRATEGY_STATE_FILE.exists():
        try:
            data = json.loads(PAIR_STRATEGY_STATE_FILE.read_text(encoding="utf-8"))
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
            for pair_key, entry in graveyard.items():
                if not isinstance(entry, dict):
                    continue
                ts = entry.get("ts", 0)
                ttl_days = entry.get("ttl_days")

                result["graveyard"].append({
                    "pair": pair_key,
                    "reason": entry.get("reason", "unknown"),
                    "added_at": ts,
                    "ttl_days": ttl_days,
                })

        except Exception:
            pass

    # Read active pair
    if ACTIVE_PAIR_FILE.exists():
        try:
            result["active_pair"] = json.loads(ACTIVE_PAIR_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    return result
