from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _workspace_root() -> Path:
    explicit = str(os.getenv("BOT_CONTROL_WORKSPACE_ROOT", "")).strip()
    if explicit:
        return Path(explicit).resolve()
    docker_root = Path("/workspace")
    if docker_root.exists():
        return docker_root.resolve()
    return Path(__file__).resolve().parents[4]


WORKSPACE_ROOT = _workspace_root()
STRATEGY_OUTPUT_ROOT = WORKSPACE_ROOT / "Strategy" / "output"
EXECUTION_STATE_ROOT = WORKSPACE_ROOT / "Execution" / "state"
EXECUTION_ENV_FILE = WORKSPACE_ROOT / "Execution" / ".env"
LOGS_ROOT = WORKSPACE_ROOT / "Logs" / "v1"
COINT_CSV = STRATEGY_OUTPUT_ROOT / "2_cointegrated_pairs.csv"
PRICE_JSON = STRATEGY_OUTPUT_ROOT / "1_price_list.json"
STATUS_JSON = STRATEGY_OUTPUT_ROOT / "2_cointegrated_pairs_status.json"
PAIR_SUPPLY_STATE = EXECUTION_STATE_ROOT / "pair_supply_control.json"
PAIR_SUPPLY_LOG = LOGS_ROOT / "pair_supply_scheduler.log"
PAIR_STRATEGY_STATE = EXECUTION_STATE_ROOT / "pair_strategy_state.json"
MANUAL_GRAVEYARD_TTL_DAYS = 7


def _safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _safe_int(value: Any) -> int | None:
    number = _safe_float(value)
    if number is None:
        return None
    return int(number)


def _strip_env_quotes(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _read_execution_env_settings() -> dict[str, str]:
    if not EXECUTION_ENV_FILE.exists():
        return {}
    try:
        lines = EXECUTION_ENV_FILE.read_text(encoding="utf-8").splitlines()
    except Exception:
        return {}
    values: dict[str, str] = {}
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
        values[key] = _strip_env_quotes(value)
    return values


def _merged_child_env() -> dict[str, str]:
    env = os.environ.copy()
    for key, value in _read_execution_env_settings().items():
        env.setdefault(key, value)
    return env


def _mtime_iso(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    except Exception:
        return None


def _load_status() -> dict[str, Any]:
    if not STATUS_JSON.exists():
        return {}
    try:
        data = json.loads(STATUS_JSON.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unix_now() -> float:
    return time.time()


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_object(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _normalize_pair_key(sym_1: Any, sym_2: Any) -> str:
    ticker_1 = str(sym_1 or "").strip().upper()
    ticker_2 = str(sym_2 or "").strip().upper()
    if not ticker_1 or not ticker_2:
        return ""
    return "/".join(sorted((ticker_1, ticker_2)))


def _normalize_pair_key_text(pair_key: Any) -> str:
    parts = str(pair_key or "").strip().upper().split("/")
    if len(parts) != 2:
        return ""
    return _normalize_pair_key(parts[0], parts[1])


def _row_pair_key(row: pd.Series) -> str:
    return _normalize_pair_key(row.get("sym_1"), row.get("sym_2"))


def _load_pair_exclusions(now: float | None = None) -> dict[str, str]:
    now_ts = _unix_now() if now is None else float(now)
    state = _read_json_object(PAIR_STRATEGY_STATE)
    excluded: dict[str, str] = {}

    graveyard = state.get("graveyard", {})
    if isinstance(graveyard, dict):
        for raw_key in graveyard.keys():
            key_text = str(raw_key or "")
            if key_text.startswith("ticker::"):
                continue
            pair_key = _normalize_pair_key_text(key_text)
            if pair_key:
                excluded[pair_key] = "graveyard"

    hospital = state.get("hospital", {})
    if isinstance(hospital, dict):
        for raw_key, entry in hospital.items():
            pair_key = _normalize_pair_key_text(raw_key)
            if not pair_key or not isinstance(entry, dict):
                continue
            try:
                ts = float(entry.get("ts") or 0)
                cooldown = float(entry.get("cooldown") or 0)
            except (TypeError, ValueError):
                continue
            if ts > 0 and cooldown > 0 and now_ts - ts < cooldown:
                excluded.setdefault(pair_key, "hospital")

    return excluded


def _filter_excluded_pairs_frame(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    excluded = _load_pair_exclusions()
    if df.empty or not excluded:
        return df.copy(), 0
    working = df.copy()
    working["_pair_key"] = working.apply(_row_pair_key, axis=1)
    before = len(working)
    working = working[~working["_pair_key"].isin(excluded.keys())].copy()
    return working.drop(columns=["_pair_key"], errors="ignore"), int(before - len(working))


def _parse_iso_timestamp(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        wait_nohang = getattr(os, "WNOHANG", 1)
        try:
            waited_pid, _status = os.waitpid(pid, wait_nohang)
            if waited_pid == pid:
                return False
        except ChildProcessError:
            pass
        except OSError:
            pass
        status_path = Path("/proc") / str(pid) / "status"
        if status_path.exists():
            try:
                for line in status_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if line.startswith("State:"):
                        state_code = line.split(":", 1)[1].strip().split()[0].upper()
                        if state_code == "Z":
                            try:
                                os.waitpid(pid, wait_nohang)
                            except Exception:
                                pass
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


def _is_managed_pair_supply_process(pid: int) -> bool:
    if not _pid_exists(pid):
        return False
    if os.name == "nt":
        return True

    cmdline = _read_process_cmdline(pid)
    if not cmdline:
        return False
    joined = " ".join(cmdline).replace("\\", "/")
    return "pair_supply_daemon.py" in joined


def _current_process_owner() -> str:
    owner = str(os.getenv("STATBOT_PROCESS_OWNER", "api") or "api").strip()
    return owner or "api"


def _is_remote_runner_state(state: dict[str, Any]) -> bool:
    process_owner = str(state.get("process_owner") or "").strip()
    process_mode = str(state.get("process_mode") or "").strip().lower()
    return process_mode == "runner" and bool(process_owner) and process_owner != _current_process_owner()


def _remote_runner_heartbeat_stale(state: dict[str, Any]) -> bool:
    heartbeat = _parse_iso_timestamp(state.get("runner_heartbeat_at"))
    if heartbeat is None:
        return True
    max_age_seconds = _safe_float(os.getenv("STATBOT_RUNNER_HEARTBEAT_STALE_SECONDS")) or 20.0
    max_age_seconds = max(float(max_age_seconds), 5.0)
    age_seconds = (datetime.now(timezone.utc) - heartbeat).total_seconds()
    return age_seconds > max_age_seconds


def _read_supply_state() -> dict[str, Any]:
    if not PAIR_SUPPLY_STATE.exists():
        return {}
    try:
        data = json.loads(PAIR_SUPPLY_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_supply_state(data: dict[str, Any]) -> None:
    payload = dict(data or {})
    updated_at = _utc_iso_now()
    payload["updated_at"] = updated_at
    data["updated_at"] = updated_at
    PAIR_SUPPLY_STATE.parent.mkdir(parents=True, exist_ok=True)
    PAIR_SUPPLY_STATE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        raw = _read_execution_env_settings().get(name)
    try:
        value = int(float(raw)) if raw not in (None, "") else int(default)
    except (TypeError, ValueError):
        value = int(default)
    if minimum is not None and value < minimum:
        value = minimum
    return value


def _pair_supply_interval_seconds() -> int:
    return _env_int("STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS", 900, minimum=0)


def get_pair_supply_status() -> dict[str, Any]:
    state = _read_supply_state()
    pid = int(state.get("pid") or 0)
    if _is_remote_runner_state(state):
        running = bool(state.get("running"))
        if running and _remote_runner_heartbeat_stale(state):
            running = False
            state["detail"] = "runner_stale"
    else:
        running = _is_managed_pair_supply_process(pid)
    if pid > 0 and not running and state.get("running"):
        state["running"] = False
        state["stopped_at"] = state.get("stopped_at") or _utc_iso_now()
        if str(state.get("detail") or "") != "runner_stale":
            state["detail"] = "process_exited"
        _write_supply_state(state)
    return {
        **state,
        "running": running,
        "pid": pid,
        "log_file": str(PAIR_SUPPLY_LOG),
        "status": _load_status(),
    }


def _use_pair_supply_runner_mode() -> bool:
    mode = str(os.getenv("STATBOT_PAIR_SUPPLY_PROCESS_MODE", "local") or "local").strip().lower()
    return mode in {"docker", "external", "runner"}


def _request_pair_supply_runner(desired_running: bool, requested_by: str | None = None) -> dict[str, Any]:
    state = get_pair_supply_status()
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
    _write_supply_state(state)
    return get_pair_supply_status()


def _start_pair_supply_local(requested_by: str | None = None) -> dict[str, Any]:
    status = get_pair_supply_status()
    if status.get("running"):
        status["detail"] = "already_running"
        return status

    entrypoint = WORKSPACE_ROOT / "Strategy" / "pair_supply_daemon.py"
    if not entrypoint.exists():
        return {"running": False, "detail": "entrypoint_missing", "entrypoint": str(entrypoint)}

    interval_seconds = _pair_supply_interval_seconds()
    LOGS_ROOT.mkdir(parents=True, exist_ok=True)
    log_handle = PAIR_SUPPLY_LOG.open("a", encoding="utf-8", errors="ignore")
    env = _merged_child_env()
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS", str(interval_seconds))
    env.setdefault("STATBOT_PAIR_SUPPLY_RUN_IMMEDIATELY", "1")
    command = [sys.executable, str(entrypoint)]

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
        return {"running": False, "detail": f"start_failed:{exc}", "command": command}
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
        "interval_seconds": interval_seconds,
        "log_file": str(PAIR_SUPPLY_LOG),
        "desired_running": True,
        "process_owner": str(os.getenv("STATBOT_PROCESS_OWNER", "api") or "api"),
    }
    _write_supply_state(state)
    return get_pair_supply_status()


def start_pair_supply(requested_by: str | None = None) -> dict[str, Any]:
    if _use_pair_supply_runner_mode():
        return _request_pair_supply_runner(True, requested_by=requested_by)
    return _start_pair_supply_local(requested_by=requested_by)


def _stop_pair_supply_local(requested_by: str | None = None, timeout_seconds: float = 8.0) -> dict[str, Any]:
    state = get_pair_supply_status()
    pid = int(state.get("pid") or 0)
    if pid <= 0 or not state.get("running"):
        state["running"] = False
        state["detail"] = "already_stopped"
        state["stopped_at"] = state.get("stopped_at") or _utc_iso_now()
        state["requested_by"] = requested_by or state.get("requested_by", "")
        state["desired_running"] = False
        _write_supply_state(state)
        return get_pair_supply_status()

    try:
        if os.name != "nt":
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass

    deadline = time.time() + max(float(timeout_seconds), 1.0)
    while time.time() < deadline:
        if not _pid_exists(pid):
            break
        time.sleep(0.25)

    running = _pid_exists(pid)
    if running:
        try:
            if os.name != "nt":
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            else:
                os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
        time.sleep(0.25)
        running = _pid_exists(pid)

    state.update(
        {
            "running": running,
            "stopped_at": None if running else _utc_iso_now(),
            "detail": "stop_failed" if running else "stopped",
            "requested_by": requested_by or state.get("requested_by", ""),
            "desired_running": False,
        }
    )
    _write_supply_state(state)
    return get_pair_supply_status()


def stop_pair_supply(requested_by: str | None = None, timeout_seconds: float = 8.0) -> dict[str, Any]:
    if _use_pair_supply_runner_mode():
        return _request_pair_supply_runner(False, requested_by=requested_by)
    return _stop_pair_supply_local(requested_by=requested_by, timeout_seconds=timeout_seconds)


def _read_pairs_frame() -> pd.DataFrame:
    if not COINT_CSV.exists():
        raise FileNotFoundError(f"Cointegrated pairs CSV not found: {COINT_CSV}")
    try:
        return pd.read_csv(COINT_CSV)
    except Exception as exc:
        raise RuntimeError(f"Could not read cointegrated pairs CSV: {exc}") from exc


def _count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return int(len(pd.read_csv(path)))
    except Exception:
        return 0


def _pair_id(sym_1: str, sym_2: str) -> str:
    return f"{sym_1}__{sym_2}"


def _pair_row(row: pd.Series, rank: int) -> dict[str, Any]:
    sym_1 = str(row.get("sym_1") or "").strip()
    sym_2 = str(row.get("sym_2") or "").strip()
    return {
        "id": _pair_id(sym_1, sym_2),
        "rank": rank,
        "sym_1": sym_1,
        "sym_2": sym_2,
        "pair": f"{sym_1}/{sym_2}" if sym_1 and sym_2 else "",
        "p_value": _safe_float(row.get("p_value")),
        "adf_stat": _safe_float(row.get("adf_stat")),
        "hedge_ratio": _safe_float(row.get("hedge_ratio")),
        "zero_crossing": _safe_int(row.get("zero_crossing")),
        "min_capital_per_leg": _safe_float(row.get("min_capital_per_leg")),
        "min_equity_recommended": _safe_float(row.get("min_equity_recommended")),
        "pair_liquidity_min": _safe_float(row.get("pair_liquidity_min")),
        "pair_order_capacity_usdt": _safe_float(row.get("pair_order_capacity_usdt")),
    }


def list_cointegrated_pairs(limit: int = 500) -> dict[str, Any]:
    df = _read_pairs_frame()
    if "sym_1" not in df.columns or "sym_2" not in df.columns:
        raise RuntimeError("Cointegrated pairs CSV is missing sym_1/sym_2 columns.")

    df, excluded_count = _filter_excluded_pairs_frame(df)
    if "zero_crossing" in df.columns:
        df = df.sort_values(by=["zero_crossing"], ascending=[False], kind="stable")
    df = df.head(max(1, min(int(limit), 1000))).copy()
    pairs = [_pair_row(row, idx + 1) for idx, (_, row) in enumerate(df.iterrows())]
    status = _load_status()
    return {
        "source_path": str(COINT_CSV),
        "price_path": str(PRICE_JSON),
        "updated_at": _mtime_iso(COINT_CSV),
        "price_updated_at": _mtime_iso(PRICE_JSON),
        "status": status,
        "pair_count": len(pairs),
        "excluded_pair_count": excluded_count,
        "pairs": pairs,
    }


def _write_pairs_frame(df: pd.DataFrame) -> None:
    COINT_CSV.parent.mkdir(parents=True, exist_ok=True)
    temp_path = COINT_CSV.with_name(f".{COINT_CSV.stem}.manual_remove.tmp{COINT_CSV.suffix}")
    df.to_csv(temp_path, index=False)
    temp_path.replace(COINT_CSV)


def _update_pair_status_after_manual_remove(removed_count: int, pair_key: str, requested_by: str | None) -> None:
    status = _load_status()
    status.update(
        {
            "updated_at": _utc_iso_now(),
            "canonical_path": str(COINT_CSV),
            "canonical_rows": _count_csv_rows(COINT_CSV),
            "canonical_pairs_rows": _count_csv_rows(COINT_CSV),
            "manual_removed_pair": pair_key,
            "manual_removed_rows": int(removed_count),
            "manual_removed_at": _utc_iso_now(),
            "manual_removed_by": requested_by or "",
        }
    )
    _write_json_object(STATUS_JSON, status)

    supply_state = _read_supply_state()
    supply_status = supply_state.get("status")
    if isinstance(supply_status, dict):
        rows = _count_csv_rows(COINT_CSV)
        supply_status["canonical_rows"] = rows
        supply_status["canonical_pairs_rows"] = rows
        supply_status["manual_removed_pair"] = pair_key
        supply_status["manual_removed_rows"] = int(removed_count)
        supply_status["manual_removed_at"] = status["manual_removed_at"]
        supply_state["status"] = supply_status
        _write_supply_state(supply_state)


def _move_pair_to_manual_graveyard(sym_1: str, sym_2: str, requested_by: str | None) -> None:
    pair_key = _normalize_pair_key(sym_1, sym_2)
    if not pair_key:
        raise ValueError("sym_1 and sym_2 are required.")
    state = _read_json_object(PAIR_STRATEGY_STATE)
    graveyard = state.get("graveyard")
    if not isinstance(graveyard, dict):
        graveyard = {}
    hospital = state.get("hospital")
    if not isinstance(hospital, dict):
        hospital = {}

    graveyard[pair_key] = {
        "ts": _unix_now(),
        "reason": "manual",
        "ttl_days": MANUAL_GRAVEYARD_TTL_DAYS,
        "requested_by": requested_by or "",
    }
    hospital.pop(pair_key, None)
    state["graveyard"] = graveyard
    state["hospital"] = hospital
    _write_json_object(PAIR_STRATEGY_STATE, state)


def remove_cointegrated_pair(sym_1: str, sym_2: str, requested_by: str | None = None) -> dict[str, Any]:
    sym_1 = str(sym_1 or "").strip().upper()
    sym_2 = str(sym_2 or "").strip().upper()
    pair_key = _normalize_pair_key(sym_1, sym_2)
    if not pair_key:
        raise ValueError("sym_1 and sym_2 are required.")

    df = _read_pairs_frame()
    if "sym_1" not in df.columns or "sym_2" not in df.columns:
        raise RuntimeError("Cointegrated pairs CSV is missing sym_1/sym_2 columns.")

    _move_pair_to_manual_graveyard(sym_1, sym_2, requested_by=requested_by)

    working = df.copy()
    working["_pair_key"] = working.apply(_row_pair_key, axis=1)
    before = len(working)
    remaining = working[working["_pair_key"] != pair_key].drop(columns=["_pair_key"], errors="ignore").copy()
    removed_count = int(before - len(remaining))
    if removed_count:
        _write_pairs_frame(remaining)
    _update_pair_status_after_manual_remove(removed_count, pair_key, requested_by)

    return {
        "ok": True,
        "removed": removed_count > 0,
        "removed_rows": removed_count,
        "pair_key": pair_key,
        "status": "graveyard",
        "reason": "manual",
        "ttl_days": MANUAL_GRAVEYARD_TTL_DAYS,
        "pair_count": _count_csv_rows(COINT_CSV),
        "requested_by": requested_by or "",
    }


def _load_price_data() -> dict[str, Any]:
    if not PRICE_JSON.exists():
        raise FileNotFoundError(f"Strategy price JSON not found: {PRICE_JSON}")
    try:
        data = json.loads(PRICE_JSON.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Could not read Strategy price JSON: {exc}") from exc
    return data if isinstance(data, dict) else {}


def _extract_points(symbol_data: dict[str, Any]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for row in symbol_data.get("klines") or []:
        if not isinstance(row, dict):
            continue
        close = _safe_float(row.get("close"))
        if close is None or close <= 0:
            continue
        raw_ts = row.get("timestamp")
        iso_ts = None
        try:
            ts_float = float(raw_ts)
            if ts_float > 10_000_000_000:
                ts_float /= 1000.0
            iso_ts = datetime.fromtimestamp(ts_float, timezone.utc).isoformat()
        except Exception:
            iso_ts = str(raw_ts or "")
        points.append({"ts": iso_ts, "close": close})
    return points


def _find_pair_row(df: pd.DataFrame, sym_1: str, sym_2: str) -> tuple[int, pd.Series]:
    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        a = str(row.get("sym_1") or "").strip()
        b = str(row.get("sym_2") or "").strip()
        if (a == sym_1 and b == sym_2) or (a == sym_2 and b == sym_1):
            return idx, row
    raise FileNotFoundError(f"Pair not found in current cointegrated pairs CSV: {sym_1}/{sym_2}")


def get_cointegrated_pair_detail(sym_1: str, sym_2: str, limit: int = 720) -> dict[str, Any]:
    sym_1 = str(sym_1 or "").strip()
    sym_2 = str(sym_2 or "").strip()
    if not sym_1 or not sym_2:
        raise ValueError("sym_1 and sym_2 are required.")

    df = _read_pairs_frame()
    rank, row = _find_pair_row(df, sym_1, sym_2)
    price_data = _load_price_data()
    series_1 = _extract_points(price_data.get(sym_1, {}) if isinstance(price_data.get(sym_1), dict) else {})
    series_2 = _extract_points(price_data.get(sym_2, {}) if isinstance(price_data.get(sym_2), dict) else {})
    if not series_1 or not series_2:
        raise FileNotFoundError(f"Price history missing for {sym_1}/{sym_2}")

    min_len = min(len(series_1), len(series_2))
    limit = max(50, min(int(limit), 2000))
    min_len = min(min_len, limit)
    series_1 = series_1[-min_len:]
    series_2 = series_2[-min_len:]

    prices_1 = np.array([point["close"] for point in series_1], dtype=float)
    prices_2 = np.array([point["close"] for point in series_2], dtype=float)
    hedge_ratio = _safe_float(row.get("hedge_ratio")) or 1.0
    log_1 = np.log(prices_1)
    log_2 = np.log(prices_2)
    spread = log_1 - hedge_ratio * log_2
    spread_mean = float(np.mean(spread))
    spread_std = float(np.std(spread))
    zscores = np.zeros_like(spread) if spread_std <= 0 else (spread - spread_mean) / spread_std

    base_1 = prices_1[0] if prices_1[0] else 1.0
    base_2 = prices_2[0] if prices_2[0] else 1.0
    chart_points = []
    for idx in range(min_len):
        chart_points.append(
            {
                "idx": idx,
                "ts": series_1[idx]["ts"] or series_2[idx]["ts"],
                "price_1": float(prices_1[idx]),
                "price_2": float(prices_2[idx]),
                "price_1_norm": float((prices_1[idx] / base_1) * 100.0),
                "price_2_norm": float((prices_2[idx] / base_2) * 100.0),
                "spread": float(spread[idx]),
                "spread_mean": spread_mean,
                "zscore": float(zscores[idx]),
                "z_upper": 2.0,
                "z_lower": -2.0,
                "z_mid": 0.0,
            }
        )

    pair = _pair_row(row, rank)
    return {
        "pair": pair,
        "updated_at": _mtime_iso(COINT_CSV),
        "price_updated_at": _mtime_iso(PRICE_JSON),
        "points": chart_points,
        "stats": {
            "point_count": len(chart_points),
            "spread_mean": spread_mean,
            "spread_std": spread_std,
            "zscore_current": float(zscores[-1]) if len(zscores) else None,
            "price_1_current": float(prices_1[-1]) if len(prices_1) else None,
            "price_2_current": float(prices_2[-1]) if len(prices_2) else None,
        },
    }
