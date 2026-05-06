"""
Run Strategy discovery continuously as an independent pair-supply process.

The canonical 2_cointegrated_pairs.csv is protected by func_cointegration:
empty scans are recorded as latest attempts but do not erase the last-good
pair supply used by execution.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


STOP_REQUESTED = False
PAIR_SUPPLY_ENV_OVERRIDE_KEYS = {
    "STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS",
    "STATBOT_PAIR_SUPPLY_FAST_INTERVAL_SECONDS",
    "STATBOT_PAIR_SUPPLY_FULL_DISCOVERY_INTERVAL_SECONDS",
    "STATBOT_PAIR_SUPPLY_FULL_DISCOVERY_MIN_ACTIVE_PAIRS",
    "STATBOT_PAIR_SUPPLY_RUN_IMMEDIATELY",
    "STATBOT_PAIR_SUPPLY_RUN_CURATOR_AFTER_SCAN",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso_now() -> str:
    return _utc_now().isoformat()


def _strip_env_quotes(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _load_execution_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / "Execution" / ".env"
    if not env_path.exists():
        return
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if text.startswith("export "):
            text = text[len("export ") :].strip()
        if "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        if not key or key.startswith("#"):
            continue
        parsed_value = _strip_env_quotes(value)
        if key in PAIR_SUPPLY_ENV_OVERRIDE_KEYS:
            os.environ[key] = parsed_value
        else:
            os.environ.setdefault(key, parsed_value)


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    try:
        value = int(float(raw)) if raw not in (None, "") else int(default)
    except (TypeError, ValueError):
        value = int(default)
    if minimum is not None and value < minimum:
        value = minimum
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return bool(default)
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _pair_supply_log_path() -> Path | None:
    raw = str(os.getenv("STATBOT_PAIR_SUPPLY_LOG_PATH") or "").strip()
    if not raw:
        return None
    return Path(raw)


def _rotate_log_if_needed(path: Path) -> None:
    max_mb = _env_int("STATBOT_LOG_MAX_MB", 5, minimum=1)
    backups = _env_int("STATBOT_LOG_BACKUPS", 3, minimum=0)
    max_bytes = max_mb * 1024 * 1024
    try:
        if not path.exists() or path.stat().st_size < max_bytes:
            return
        if backups <= 0:
            path.unlink(missing_ok=True)
            return
        path.with_name(f"{path.name}.{backups}").unlink(missing_ok=True)
        for idx in range(backups - 1, 0, -1):
            src = path.with_name(f"{path.name}.{idx}")
            if src.exists():
                src.replace(path.with_name(f"{path.name}.{idx + 1}"))
        path.replace(path.with_name(f"{path.name}.1"))
    except OSError:
        return


def _write_log_line(message: str) -> None:
    log_path = _pair_supply_log_path()
    if log_path is None:
        print(message, flush=True)
        return
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        _rotate_log_if_needed(log_path)
        with log_path.open("a", encoding="utf-8", errors="ignore") as handle:
            handle.write(f"{message}\n")
    except Exception:
        print(message, flush=True)


def _pair_supply_interval_seconds() -> int:
    return _env_int("STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS", 300, minimum=5)


def _pair_supply_fast_interval_seconds() -> int:
    raw = os.getenv("STATBOT_PAIR_SUPPLY_FAST_INTERVAL_SECONDS")
    if raw in (None, ""):
        return _pair_supply_interval_seconds()
    return _env_int("STATBOT_PAIR_SUPPLY_FAST_INTERVAL_SECONDS", _pair_supply_interval_seconds(), minimum=5)


def _pair_supply_full_discovery_interval_seconds() -> int:
    return _env_int("STATBOT_PAIR_SUPPLY_FULL_DISCOVERY_INTERVAL_SECONDS", 900, minimum=60)


def _pair_supply_full_discovery_min_active_pairs() -> int:
    return _env_int("STATBOT_PAIR_SUPPLY_FULL_DISCOVERY_MIN_ACTIVE_PAIRS", 3, minimum=1)


def _status_json_path(strategy_dir: Path) -> Path:
    return strategy_dir / "output" / "2_cointegrated_pairs_status.json"


def _cointegrated_pairs_csv_path(strategy_dir: Path) -> Path:
    return strategy_dir / "output" / "2_cointegrated_pairs.csv"


def _price_json_path(strategy_dir: Path) -> Path:
    return strategy_dir / "output" / "1_price_list.json"


def _pair_supply_state_path(strategy_dir: Path) -> Path:
    return strategy_dir.parent / "Execution" / "state" / "pair_supply_control.json"


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp.replace(path)


def _parse_iso_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_after(now: datetime, seconds: int) -> str:
    return (now + timedelta(seconds=max(int(seconds), 0))).isoformat()


def _count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            rows = [line for line in handle if line.strip()]
    except Exception:
        return 0
    return max(len(rows) - 1, 0)


def _canonical_rows(status: dict[str, Any], csv_path: Path | None = None) -> int:
    for key in ("canonical_rows", "canonical_pairs_rows"):
        try:
            value = int(status.get(key) or 0)
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            return value
    if csv_path is not None:
        return _count_csv_rows(csv_path)
    return 0


def _curator_healthy_count(status: dict[str, Any]) -> int | None:
    counts = status.get("curator_status_counts")
    if not isinstance(counts, dict):
        return None
    try:
        return int(counts.get("healthy") or 0)
    except (TypeError, ValueError):
        return 0


def _active_pair_count(status: dict[str, Any], csv_path: Path | None = None) -> int:
    try:
        active = int(status.get("curator_active_pair_count") or 0)
    except (TypeError, ValueError):
        active = 0
    if active > 0:
        return active
    return _canonical_rows(status, csv_path=csv_path)


def _last_full_discovery_at(status: dict[str, Any], state: dict[str, Any]) -> str:
    for source in (state, status):
        for key in (
            "last_full_discovery_at",
            "last_full_discovery_completed_at",
            "pair_universe_generation",
        ):
            value = str(source.get(key) or "").strip()
            if value:
                return value
    nested = state.get("status")
    if isinstance(nested, dict):
        return _last_full_discovery_at(nested, {})
    return ""


def _full_discovery_forced(state: dict[str, Any]) -> bool:
    raw_values = (
        state.get("force_full_discovery"),
        state.get("full_discovery_requested"),
    )
    return any(str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"} for value in raw_values)


def _should_run_full_discovery(
    *,
    status: dict[str, Any],
    state: dict[str, Any],
    csv_path: Path,
    price_path: Path,
    first_run: bool,
    run_immediately: bool,
    full_interval_seconds: int,
    min_active_pairs: int,
    now: datetime | None = None,
) -> tuple[bool, str]:
    now = _utc_now() if now is None else now
    canonical_rows = _canonical_rows(status, csv_path=csv_path)
    active_pairs = _active_pair_count(status, csv_path=csv_path)
    healthy_count = _curator_healthy_count(status)

    if _full_discovery_forced(state):
        return True, "forced"
    if not csv_path.exists() or canonical_rows <= 0:
        return True, "missing_canonical_supply"
    if not price_path.exists():
        return True, "missing_price_history"
    if active_pairs < min_active_pairs:
        return True, "insufficient_active_pairs"
    if healthy_count is not None and healthy_count <= 0:
        return True, "no_healthy_curator_pairs"

    last_full = _parse_iso_timestamp(_last_full_discovery_at(status, state))
    if last_full is None:
        if first_run and run_immediately:
            return False, "startup_existing_supply_health_refresh"
        return True, "no_full_discovery_timestamp"

    due_at = last_full + timedelta(seconds=max(int(full_interval_seconds), 1))
    if now >= due_at:
        return True, "scheduled"
    return False, "health_refresh"


def _scheduler_metadata(
    *,
    mode: str,
    detail: str,
    now: datetime,
    fast_interval_seconds: int,
    full_interval_seconds: int,
    next_full_discovery_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "updated_at": now.isoformat(),
        "pair_supply_mode": mode,
        "pair_supply_detail": detail,
        "health_refresh_interval_seconds": int(fast_interval_seconds),
        "full_discovery_interval_seconds": int(full_interval_seconds),
    }
    if next_full_discovery_at is not None:
        payload["next_full_discovery_at"] = next_full_discovery_at
    if extra:
        payload.update(extra)
    return payload


def _merge_status_payload(strategy_dir: Path, payload: dict[str, Any]) -> None:
    status_path = _status_json_path(strategy_dir)
    status = _read_json_object(status_path)
    status.update(payload)
    _write_json_atomic(status_path, status)

    state_path = _pair_supply_state_path(strategy_dir)
    state = _read_json_object(state_path)
    nested = state.get("status")
    if not isinstance(nested, dict):
        nested = {}
    nested.update(payload)
    state["status"] = nested
    state.update({key: value for key, value in payload.items() if key != "updated_at"})
    state["updated_at"] = payload.get("updated_at") or _utc_iso_now()
    _write_json_atomic(state_path, state)


def _mark_scheduler_mode(
    strategy_dir: Path,
    *,
    mode: str,
    detail: str,
    fast_interval_seconds: int,
    full_interval_seconds: int,
    next_full_discovery_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = _scheduler_metadata(
        mode=mode,
        detail=detail,
        now=_utc_now(),
        fast_interval_seconds=fast_interval_seconds,
        full_interval_seconds=full_interval_seconds,
        next_full_discovery_at=next_full_discovery_at,
        extra=extra,
    )
    _merge_status_payload(strategy_dir, payload)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return int(default)


def _read_scheduler_counts(strategy_dir: Path) -> tuple[int, int]:
    status = _read_json_object(_status_json_path(strategy_dir))
    return (
        _safe_int(status.get("full_discovery_count")),
        _safe_int(status.get("health_refresh_count")),
    )


def _handle_stop(signum, _frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True
    _write_log_line(f"{_utc_iso_now()} pair_supply stop_requested signal={signum}")


def _sleep_interruptibly(seconds: int) -> None:
    deadline = time.time() + max(seconds, 1)
    while not STOP_REQUESTED and time.time() < deadline:
        time.sleep(min(5, max(0.1, deadline - time.time())))


def _run_strategy_process(strategy_script: Path, strategy_dir: Path, env: dict[str, str]) -> int:
    proc = subprocess.Popen(
        [sys.executable, str(strategy_script)],
        cwd=str(strategy_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.stdout is not None:
        for raw_line in proc.stdout:
            _write_log_line(raw_line.rstrip("\n"))
    return int(proc.wait())


def _run_pair_curator_once() -> dict[str, Any] | None:
    _write_log_line(f"{_utc_iso_now()} pair_supply curator_start")
    try:
        from pair_universe_curator import run_curator_once

        report = run_curator_once()
    except Exception as exc:
        _write_log_line(f"{_utc_iso_now()} pair_supply curator_error error={exc}")
        return None

    _write_log_line(
        f"{_utc_iso_now()} pair_supply curator_complete "
        f"generation={report.get('source_generation') or 'unknown'} "
        f"pairs={report.get('pair_count', 0)} active_pairs={report.get('active_pair_count', 0)}",
    )
    return report if isinstance(report, dict) else {}


def _run_health_refresh(
    strategy_dir: Path,
    *,
    fast_interval_seconds: int,
    full_interval_seconds: int,
    next_full_discovery_at: str,
) -> int:
    started = _utc_now()
    _write_log_line(f"{started.isoformat()} pair_supply health_refresh_start")
    _mark_scheduler_mode(
        strategy_dir,
        mode="health_refresh",
        detail="health_refresh",
        fast_interval_seconds=fast_interval_seconds,
        full_interval_seconds=full_interval_seconds,
        next_full_discovery_at=next_full_discovery_at,
        extra={"last_health_refresh_started_at": started.isoformat()},
    )
    report = _run_pair_curator_once()
    elapsed = (_utc_now() - started).total_seconds()
    status = _read_json_object(_status_json_path(strategy_dir))
    full_count, health_count = _read_scheduler_counts(strategy_dir)
    completed_at = _utc_iso_now()
    if report is None:
        _write_log_line(
            f"{completed_at} pair_supply health_refresh_error elapsed_seconds={elapsed:.1f}",
        )
        detail = "health_refresh_failed"
        ret = 2
    else:
        _write_log_line(
            f"{completed_at} pair_supply health_refresh_complete "
            f"generation={report.get('source_generation') or 'unknown'} "
            f"pairs={report.get('pair_count', 0)} active_pairs={report.get('active_pair_count', 0)} "
            f"elapsed_seconds={elapsed:.1f}",
        )
        detail = "idle"
        ret = 0

    _mark_scheduler_mode(
        strategy_dir,
        mode="idle",
        detail=detail,
        fast_interval_seconds=fast_interval_seconds,
        full_interval_seconds=full_interval_seconds,
        next_full_discovery_at=next_full_discovery_at,
        extra={
            "full_discovery_count": full_count,
            "health_refresh_count": health_count + 1,
            "last_health_refresh_at": completed_at,
            "last_health_refresh_elapsed_seconds": round(elapsed, 3),
            "canonical_rows": _canonical_rows(status, csv_path=_cointegrated_pairs_csv_path(strategy_dir)),
        },
    )
    return ret


def _run_full_discovery(
    strategy_dir: Path,
    strategy_script: Path,
    *,
    reason: str,
    fast_interval_seconds: int,
    full_interval_seconds: int,
) -> int:
    started = _utc_now()
    _write_log_line(f"{started.isoformat()} pair_supply full_discovery_start reason={reason}")
    _write_log_line(f"{started.isoformat()} pair_supply scan_start")
    _mark_scheduler_mode(
        strategy_dir,
        mode="full_discovery",
        detail=f"full_discovery:{reason}",
        fast_interval_seconds=fast_interval_seconds,
        full_interval_seconds=full_interval_seconds,
        extra={
            "last_full_discovery_started_at": started.isoformat(),
            "last_full_discovery_reason": reason,
        },
    )
    try:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        ret = _run_strategy_process(strategy_script, strategy_dir, env)
        if ret == 0 and _env_bool("STATBOT_PAIR_SUPPLY_RUN_CURATOR_AFTER_SCAN", True):
            if _run_pair_curator_once() is None:
                ret = 2
    except Exception as exc:
        ret = 1
        _write_log_line(f"{_utc_iso_now()} pair_supply scan_error error={exc}")

    elapsed = (_utc_now() - started).total_seconds()
    completed_at = _utc_iso_now()
    _write_log_line(
        f"{completed_at} pair_supply scan_end exit_code={ret} elapsed_seconds={elapsed:.1f}",
    )
    status = _read_json_object(_status_json_path(strategy_dir))
    full_count, health_count = _read_scheduler_counts(strategy_dir)
    next_full = _iso_after(_utc_now(), full_interval_seconds)
    extra = {
        "full_discovery_count": full_count + 1,
        "health_refresh_count": health_count,
        "last_full_discovery_at": completed_at,
        "last_full_discovery_completed_at": completed_at,
        "last_full_discovery_elapsed_seconds": round(elapsed, 3),
        "last_full_discovery_exit_code": ret,
        "force_full_discovery": False,
        "full_discovery_requested": False,
        "canonical_rows": _canonical_rows(status, csv_path=_cointegrated_pairs_csv_path(strategy_dir)),
    }
    _mark_scheduler_mode(
        strategy_dir,
        mode="idle",
        detail="idle" if ret == 0 else f"full_discovery_failed:{ret}",
        fast_interval_seconds=fast_interval_seconds,
        full_interval_seconds=full_interval_seconds,
        next_full_discovery_at=next_full,
        extra=extra,
    )
    return ret


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    _load_execution_env()

    strategy_dir = Path(__file__).resolve().parent
    strategy_script = strategy_dir / "main_strategy.py"
    fast_interval_seconds = _pair_supply_fast_interval_seconds()
    full_interval_seconds = _pair_supply_full_discovery_interval_seconds()
    min_active_pairs = _pair_supply_full_discovery_min_active_pairs()
    run_immediately = _env_bool("STATBOT_PAIR_SUPPLY_RUN_IMMEDIATELY", True)

    _write_log_line(
        f"{_utc_iso_now()} pair_supply starting "
        f"health_interval={fast_interval_seconds}s full_discovery_interval={full_interval_seconds}s "
        f"min_active_pairs={min_active_pairs} immediate={int(run_immediately)}",
    )
    _mark_scheduler_mode(
        strategy_dir,
        mode="idle",
        detail="started",
        fast_interval_seconds=fast_interval_seconds,
        full_interval_seconds=full_interval_seconds,
        extra={
            "running": True,
            "pid": os.getpid(),
            "desired_running": True,
            "started_at": _utc_iso_now(),
        },
    )

    first_run = True
    while not STOP_REQUESTED:
        if first_run and not run_immediately:
            _write_log_line(f"{_utc_iso_now()} pair_supply initial_run_skipped")
        else:
            state = _read_json_object(_pair_supply_state_path(strategy_dir))
            status = _read_json_object(_status_json_path(strategy_dir))
            should_full, reason = _should_run_full_discovery(
                status=status,
                state=state,
                csv_path=_cointegrated_pairs_csv_path(strategy_dir),
                price_path=_price_json_path(strategy_dir),
                first_run=first_run,
                run_immediately=run_immediately,
                full_interval_seconds=full_interval_seconds,
                min_active_pairs=min_active_pairs,
            )
            last_full = _parse_iso_timestamp(_last_full_discovery_at(status, state))
            next_full = _iso_after(last_full or _utc_now(), full_interval_seconds)
            if should_full:
                _run_full_discovery(
                    strategy_dir,
                    strategy_script,
                    reason=reason,
                    fast_interval_seconds=fast_interval_seconds,
                    full_interval_seconds=full_interval_seconds,
                )
            else:
                _run_health_refresh(
                    strategy_dir,
                    fast_interval_seconds=fast_interval_seconds,
                    full_interval_seconds=full_interval_seconds,
                    next_full_discovery_at=next_full,
                )

        first_run = False
        if STOP_REQUESTED:
            break
        _write_log_line(f"{_utc_iso_now()} pair_supply sleeping seconds={fast_interval_seconds}")
        _sleep_interruptibly(fast_interval_seconds)

    try:
        _mark_scheduler_mode(
            strategy_dir,
            mode="stopped",
            detail="stopped",
            fast_interval_seconds=fast_interval_seconds,
            full_interval_seconds=full_interval_seconds,
            extra={"running": False, "stopped_at": _utc_iso_now()},
        )
    except Exception:
        pass
    _write_log_line(f"{_utc_iso_now()} pair_supply stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
