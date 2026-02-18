from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path


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


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
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


def _normalize_status(state: dict) -> dict:
    data = dict(state or {})
    pid = int(data.get("pid") or 0)
    running = _pid_exists(pid)
    data["pid"] = pid
    data["running"] = running
    if not running and pid > 0:
        data["stopped_at"] = data.get("stopped_at") or _utc_iso_now()
        data["detail"] = data.get("detail") or "process_not_found"
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
    }
    _write_state(state)
    return _normalize_status(state)


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
    resolved_run_key, log_file = _resolve_run_log_file(run_key)
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
                }
            return {
                "run_key": "__control__",
                "log_file": str(CONTROL_LOG_FILE),
                "line_count": len(output_lines),
                "lines": output_lines,
                "updated_at": _utc_iso_now(),
                "detail": "control_log_fallback",
            }
        return {
            "run_key": resolved_run_key,
            "log_file": None,
            "line_count": 0,
            "lines": [],
            "updated_at": _utc_iso_now(),
            "detail": "log_not_found",
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
        }
    return {
        "run_key": resolved_run_key,
        "log_file": str(log_file),
        "line_count": len(output_lines),
        "lines": output_lines,
        "updated_at": _utc_iso_now(),
        "detail": "ok",
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
