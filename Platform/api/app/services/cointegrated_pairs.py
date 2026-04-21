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
LOGS_ROOT = WORKSPACE_ROOT / "Logs" / "v1"
COINT_CSV = STRATEGY_OUTPUT_ROOT / "2_cointegrated_pairs.csv"
PRICE_JSON = STRATEGY_OUTPUT_ROOT / "1_price_list.json"
STATUS_JSON = STRATEGY_OUTPUT_ROOT / "2_cointegrated_pairs_status.json"
PAIR_SUPPLY_STATE = EXECUTION_STATE_ROOT / "pair_supply_control.json"
PAIR_SUPPLY_LOG = LOGS_ROOT / "pair_supply_scheduler.log"


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
    try:
        value = int(float(raw)) if raw not in (None, "") else int(default)
    except (TypeError, ValueError):
        value = int(default)
    if minimum is not None and value < minimum:
        value = minimum
    return value


def get_pair_supply_status() -> dict[str, Any]:
    state = _read_supply_state()
    pid = int(state.get("pid") or 0)
    running = _pid_exists(pid)
    if pid > 0 and not running and state.get("running"):
        state["running"] = False
        state["stopped_at"] = state.get("stopped_at") or _utc_iso_now()
        state["detail"] = "process_exited"
        _write_supply_state(state)
    return {
        **state,
        "running": running,
        "pid": pid,
        "log_file": str(PAIR_SUPPLY_LOG),
        "status": _load_status(),
    }


def start_pair_supply(requested_by: str | None = None) -> dict[str, Any]:
    status = get_pair_supply_status()
    if status.get("running"):
        status["detail"] = "already_running"
        return status

    entrypoint = WORKSPACE_ROOT / "Strategy" / "pair_supply_daemon.py"
    if not entrypoint.exists():
        return {"running": False, "detail": "entrypoint_missing", "entrypoint": str(entrypoint)}

    interval_seconds = _env_int("STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS", 900, minimum=60)
    LOGS_ROOT.mkdir(parents=True, exist_ok=True)
    log_handle = PAIR_SUPPLY_LOG.open("a", encoding="utf-8", errors="ignore")
    env = os.environ.copy()
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
    }
    _write_supply_state(state)
    return get_pair_supply_status()


def stop_pair_supply(requested_by: str | None = None, timeout_seconds: float = 8.0) -> dict[str, Any]:
    state = get_pair_supply_status()
    pid = int(state.get("pid") or 0)
    if pid <= 0 or not state.get("running"):
        state["running"] = False
        state["detail"] = "already_stopped"
        state["stopped_at"] = state.get("stopped_at") or _utc_iso_now()
        state["requested_by"] = requested_by or state.get("requested_by", "")
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
        }
    )
    _write_supply_state(state)
    return get_pair_supply_status()


def _read_pairs_frame() -> pd.DataFrame:
    if not COINT_CSV.exists():
        raise FileNotFoundError(f"Cointegrated pairs CSV not found: {COINT_CSV}")
    try:
        return pd.read_csv(COINT_CSV)
    except Exception as exc:
        raise RuntimeError(f"Could not read cointegrated pairs CSV: {exc}") from exc


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
        "pairs": pairs,
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
