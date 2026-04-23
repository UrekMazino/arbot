"""
Continuously curate the Pair Universe without placing trades.

The curator is an advisory process: it reads the canonical pair supply and
Strategy price history, scores current pair health, and writes recommendations
for the API/UI. It does not move pairs into hospital/graveyard or switch active
pairs; execution remains the authority for trade lifecycle decisions.
"""

from __future__ import annotations

import json
import math
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared_cointegration_validator import evaluate_cointegration, latest_finite


STRATEGY_OUTPUT_ROOT = ROOT_DIR / "Strategy" / "output"
EXECUTION_STATE_ROOT = ROOT_DIR / "Execution" / "state"
EXECUTION_ENV_FILE = ROOT_DIR / "Execution" / ".env"
LOGS_ROOT = ROOT_DIR / "Logs" / "v1"

COINT_CSV = STRATEGY_OUTPUT_ROOT / "2_cointegrated_pairs.csv"
PRICE_JSON = STRATEGY_OUTPUT_ROOT / "1_price_list.json"
CURATOR_REPORT_JSON = STRATEGY_OUTPUT_ROOT / "pair_universe_curator.json"
CURATOR_STATE_JSON = EXECUTION_STATE_ROOT / "pair_universe_curator_control.json"
CURATOR_LOG = LOGS_ROOT / "pair_universe_curator.log"

STOP_REQUESTED = False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso_now() -> str:
    return _utc_now().isoformat()


def _strip_env_quotes(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _load_execution_env() -> dict[str, str]:
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
        if key and not key.startswith("#"):
            values[key] = _strip_env_quotes(value)
    return values


def _setting(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw not in (None, ""):
        return str(raw)
    return _load_execution_env().get(name, default)


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    raw = _setting(name, str(default))
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        value = int(default)
    if minimum is not None and value < minimum:
        value = minimum
    return value


def _env_float(name: str, default: float, minimum: float | None = None) -> float:
    raw = _setting(name, str(default))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = float(default)
    if minimum is not None and value < minimum:
        value = minimum
    return value


def _env_flag(name: str, default: bool = False) -> bool:
    raw = _setting(name, "1" if default else "0").strip().lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _safe_int(value: Any) -> int:
    number = _safe_float(value)
    return int(number) if number is not None else 0


def _normalize_pair_key(sym_1: Any, sym_2: Any) -> str:
    a = str(sym_1 or "").strip().upper()
    b = str(sym_2 or "").strip().upper()
    if not a or not b:
        return ""
    return "/".join(sorted((a, b)))


def _normalize_pair_key_text(pair_key: Any) -> str:
    parts = str(pair_key or "").strip().upper().split("/")
    if len(parts) != 2:
        return ""
    return _normalize_pair_key(parts[0], parts[1])


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


def _log(message: str) -> None:
    text = f"{_utc_iso_now()} pair_curator {message}"
    log_path = Path(str(os.getenv("STATBOT_PAIR_CURATOR_LOG_PATH") or CURATOR_LOG))
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        _rotate_log_if_needed(log_path)
        with log_path.open("a", encoding="utf-8", errors="ignore") as handle:
            handle.write(f"{text}\n")
    except Exception:
        print(text, flush=True)


def _write_state(**updates: Any) -> dict[str, Any]:
    state = _read_json_object(CURATOR_STATE_JSON)
    state.update(updates)
    state["updated_at"] = _utc_iso_now()
    _write_json_atomic(CURATOR_STATE_JSON, state)
    return state


def _load_pair_lifecycle_state(now_ts: float) -> dict[str, str]:
    state = _read_json_object(EXECUTION_STATE_ROOT / "pair_strategy_state.json")
    lifecycle: dict[str, str] = {}

    graveyard = state.get("graveyard", {})
    if isinstance(graveyard, dict):
        for raw_key in graveyard.keys():
            if str(raw_key).startswith("ticker::"):
                continue
            pair_key = _normalize_pair_key_text(raw_key)
            if pair_key:
                lifecycle[pair_key] = "graveyard"

    hospital = state.get("hospital", {})
    if isinstance(hospital, dict):
        for raw_key, entry in hospital.items():
            pair_key = _normalize_pair_key_text(raw_key)
            if not pair_key or not isinstance(entry, dict):
                continue
            ts = _safe_float(entry.get("ts")) or 0.0
            cooldown = _safe_float(entry.get("cooldown")) or 0.0
            if ts > 0 and cooldown > 0 and now_ts - ts < cooldown:
                lifecycle.setdefault(pair_key, "hospital")

    return lifecycle


def _extract_prices(price_data: dict[str, Any], symbol: str, limit: int) -> list[float]:
    payload = price_data.get(symbol)
    if not isinstance(payload, dict):
        return []
    prices: list[float] = []
    for row in payload.get("klines") or []:
        if not isinstance(row, dict):
            continue
        close = _safe_float(row.get("close"))
        if close is not None and close > 0:
            prices.append(close)
    return prices[-limit:]


def _score_p_value(p_value: float | None, critical: float) -> float:
    if p_value is None:
        return 0.0
    if p_value <= 0:
        return 25.0
    if p_value >= critical:
        return max(0.0, 8.0 * (1.0 - min(p_value / max(critical * 2.0, 1e-9), 1.0)))
    return 25.0 * (1.0 - min(p_value / max(critical, 1e-9), 1.0))


def _score_liquidity(liquidity: float | None) -> float:
    if liquidity is None or liquidity <= 0:
        return 0.0
    return min(20.0, max(0.0, math.log10(max(liquidity, 1.0)) / 5.0 * 20.0))


def _score_crossings(crossings: int, target: int) -> float:
    return min(20.0, (max(crossings, 0) / max(target, 1)) * 20.0)


def _score_capacity(capacity: float | None) -> float:
    if capacity is None or capacity <= 0:
        return 0.0
    return min(10.0, max(0.0, math.log10(max(capacity, 1.0)) / 5.0 * 10.0))


def _classify_pair(
    *,
    lifecycle_status: str | None,
    coint_flag: int,
    p_value: float | None,
    crossings: int,
    liquidity: float | None,
    price_samples: int,
    stale_prices: bool,
    critical_p: float,
    min_crossings: int,
    min_liquidity: float,
    previous: dict[str, Any],
) -> tuple[str, str, int, int, list[str]]:
    reasons: list[str] = []
    if lifecycle_status in {"graveyard", "hospital"}:
        reasons.append(f"lifecycle_{lifecycle_status}")
        return lifecycle_status, "hold", 0, 0, reasons

    if price_samples < 50:
        raw_status = "no_data"
        reasons.append("insufficient_price_history")
    elif stale_prices:
        raw_status = "stale"
        reasons.append("price_history_stale")
    elif coint_flag != 1:
        raw_status = "degraded"
        reasons.append("cointegration_failed")
    elif p_value is not None and p_value > critical_p:
        raw_status = "watch"
        reasons.append("p_value_above_threshold")
    elif crossings < min_crossings:
        raw_status = "watch"
        reasons.append("low_crossing_frequency")
    elif liquidity is not None and liquidity > 0 and liquidity < min_liquidity:
        raw_status = "watch"
        reasons.append("liquidity_below_target")
    else:
        raw_status = "healthy"
        reasons.append("cointegration_confirmed")

    previous_failures = _safe_int(previous.get("failure_count"))
    previous_recoveries = _safe_int(previous.get("recovery_count"))
    bad = raw_status in {"degraded", "no_data", "stale"}
    good = raw_status == "healthy"
    failure_count = previous_failures + 1 if bad else 0
    recovery_count = previous_recoveries + 1 if good else 0

    if failure_count >= 3:
        return "hospital_candidate", "cooldown_candidate", failure_count, 0, reasons
    if failure_count >= 2:
        return "degraded", "watch", failure_count, 0, reasons
    if bad:
        return "watch", "watch", failure_count, 0, reasons
    if good and previous.get("status") in {"degraded", "hospital_candidate"} and recovery_count < 2:
        reasons.append("recovery_confirmation_pending")
        return "watch", "watch", 0, recovery_count, reasons
    if good:
        return "healthy", "promote", 0, recovery_count, reasons
    return raw_status, "watch", 0, 0, reasons


def _curate_row(
    row: pd.Series,
    rank: int,
    price_data: dict[str, Any],
    previous_pairs: dict[str, Any],
    lifecycle: dict[str, str],
    settings: dict[str, Any],
) -> dict[str, Any]:
    sym_1 = str(row.get("sym_1") or "").strip().upper()
    sym_2 = str(row.get("sym_2") or "").strip().upper()
    pair_key = _normalize_pair_key(sym_1, sym_2)
    previous = previous_pairs.get(pair_key, {}) if isinstance(previous_pairs, dict) else {}

    limit = int(settings["kline_limit"])
    prices_1 = _extract_prices(price_data, sym_1, limit)
    prices_2 = _extract_prices(price_data, sym_2, limit)
    min_len = min(len(prices_1), len(prices_2))
    prices_1 = prices_1[-min_len:]
    prices_2 = prices_2[-min_len:]

    metrics: dict[str, Any] = {}
    if min_len >= max(50, int(settings["z_window"]) + 2):
        metrics = evaluate_cointegration(
            prices_1,
            prices_2,
            window=int(settings["z_window"]),
            pvalue_threshold=float(settings["critical_p"]),
            zero_cross_threshold_ratio=float(settings["cross_threshold_ratio"]),
            already_logged=False,
        )

    p_value = _safe_float(metrics.get("p_value")) if metrics else _safe_float(row.get("p_value"))
    coint_flag = int(metrics.get("coint_flag", 0)) if metrics else 0
    crossings = _safe_int(metrics.get("zero_crossings")) if metrics else _safe_int(row.get("zero_crossing"))
    liquidity = _safe_float(row.get("pair_liquidity_min"))
    capacity = _safe_float(row.get("pair_order_capacity_usdt"))
    latest_z = metrics.get("latest_zscore") if metrics else None
    if latest_z is None and metrics.get("zscore_values") is not None:
        try:
            latest_z = latest_finite(list(metrics.get("zscore_values")))
        except Exception:
            latest_z = None

    price_mtime = PRICE_JSON.stat().st_mtime if PRICE_JSON.exists() else 0.0
    stale_prices = price_mtime > 0 and (time.time() - price_mtime) > float(settings["stale_seconds"])

    status, recommendation, failure_count, recovery_count, reasons = _classify_pair(
        lifecycle_status=lifecycle.get(pair_key),
        coint_flag=coint_flag,
        p_value=p_value,
        crossings=crossings,
        liquidity=liquidity,
        price_samples=min_len,
        stale_prices=stale_prices,
        critical_p=float(settings["critical_p"]),
        min_crossings=int(settings["min_crossings"]),
        min_liquidity=float(settings["min_liquidity"]),
        previous=previous if isinstance(previous, dict) else {},
    )

    score = (
        _score_p_value(p_value, float(settings["critical_p"]))
        + _score_crossings(crossings, int(settings["target_crossings"]))
        + _score_liquidity(liquidity)
        + _score_capacity(capacity)
        + (20.0 if coint_flag == 1 else 0.0)
    )
    if status in {"watch", "stale"}:
        score *= 0.75
    elif status in {"degraded", "hospital_candidate", "no_data"}:
        score *= 0.35
    elif status in {"hospital", "graveyard"}:
        score = 0.0

    return {
        "pair_key": pair_key,
        "pair": f"{sym_1}/{sym_2}",
        "sym_1": sym_1,
        "sym_2": sym_2,
        "source_rank": rank,
        "score": round(max(min(score, 100.0), 0.0), 2),
        "status": status,
        "recommendation": recommendation,
        "reasons": reasons,
        "failure_count": failure_count,
        "recovery_count": recovery_count,
        "coint_flag": coint_flag,
        "p_value": p_value,
        "zero_crossings": crossings,
        "liquidity_min": liquidity,
        "capacity_usdt": capacity,
        "latest_zscore": float(latest_z) if isinstance(latest_z, (int, float)) and math.isfinite(latest_z) else None,
        "price_samples": min_len,
        "checked_at": _utc_iso_now(),
    }


def run_curator_once() -> dict[str, Any]:
    if not COINT_CSV.exists():
        raise FileNotFoundError(f"Pair supply CSV not found: {COINT_CSV}")
    if not PRICE_JSON.exists():
        raise FileNotFoundError(f"Price history JSON not found: {PRICE_JSON}")

    df = pd.read_csv(COINT_CSV)
    price_data = _read_json_object(PRICE_JSON)
    previous_report = _read_json_object(CURATOR_REPORT_JSON)
    previous_pairs = previous_report.get("pairs", {})
    previous_pairs = previous_pairs if isinstance(previous_pairs, dict) else {}
    lifecycle = _load_pair_lifecycle_state(time.time())

    settings = {
        "critical_p": _env_float("STATBOT_P_VALUE_CRITICAL", 0.15, minimum=0.000001),
        "z_window": _env_int("STATBOT_STRATEGY_Z_SCORE_WINDOW", 60, minimum=2),
        "kline_limit": _env_int("STATBOT_PAIR_CURATOR_KLINE_LIMIT", 720, minimum=100),
        "min_crossings": _env_int("STATBOT_PAIR_CURATOR_MIN_CROSSINGS", 3, minimum=0),
        "target_crossings": _env_int("STATBOT_PAIR_CURATOR_TARGET_CROSSINGS", 20, minimum=1),
        "min_liquidity": _env_float("STATBOT_PAIR_CURATOR_MIN_LIQUIDITY_USDT", 1000.0, minimum=0.0),
        "cross_threshold_ratio": _env_float("STATBOT_COINT_ZERO_CROSS_THRESHOLD_RATIO", 0.1, minimum=0.0),
        "stale_seconds": _env_int("STATBOT_PAIR_CURATOR_STALE_SECONDS", 3600, minimum=60),
    }

    pair_entries: dict[str, Any] = {}
    for rank, (_, row) in enumerate(df.iterrows(), start=1):
        pair_key = _normalize_pair_key(row.get("sym_1"), row.get("sym_2"))
        if not pair_key:
            continue
        pair_entries[pair_key] = _curate_row(row, rank, price_data, previous_pairs, lifecycle, settings)

    ranked_pairs = sorted(
        pair_entries.values(),
        key=lambda item: (
            -float(item.get("score") or 0.0),
            str(item.get("status") or ""),
            int(item.get("source_rank") or 0),
        ),
    )
    status_counts: dict[str, int] = {}
    for item in ranked_pairs:
        status = str(item.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    for idx, item in enumerate(ranked_pairs, start=1):
        item["priority_rank"] = idx

    report = {
        "version": 1,
        "updated_at": _utc_iso_now(),
        "source_path": str(COINT_CSV),
        "price_path": str(PRICE_JSON),
        "pair_count": len(pair_entries),
        "status_counts": status_counts,
        "settings": settings,
        "top_pairs": ranked_pairs[:10],
        "pairs": {str(item["pair_key"]): item for item in ranked_pairs},
    }
    _write_json_atomic(CURATOR_REPORT_JSON, report)
    _write_state(
        running=not STOP_REQUESTED,
        last_run_at=report["updated_at"],
        pair_count=len(pair_entries),
        status_counts=status_counts,
        report_file=str(CURATOR_REPORT_JSON),
        detail="ok",
    )
    return report


def _handle_stop(signum, _frame) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True
    _log(f"stop_requested signal={signum}")
    _write_state(running=False, desired_running=False, stopped_at=_utc_iso_now(), detail="stop_requested")


def _sleep_interruptibly(seconds: int) -> None:
    deadline = time.time() + max(seconds, 1)
    while not STOP_REQUESTED and time.time() < deadline:
        time.sleep(min(2.0, max(0.1, deadline - time.time())))


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    interval = _env_int("STATBOT_PAIR_CURATOR_INTERVAL_SECONDS", 60, minimum=5)
    enabled = _env_flag("STATBOT_PAIR_CURATOR_ENABLED", True)
    if not enabled:
        _write_state(running=False, desired_running=False, detail="disabled")
        _log("disabled")
        return 0

    _write_state(
        running=True,
        desired_running=True,
        pid=os.getpid(),
        started_at=_utc_iso_now(),
        stopped_at=None,
        interval_seconds=interval,
        report_file=str(CURATOR_REPORT_JSON),
        log_file=str(Path(str(os.getenv("STATBOT_PAIR_CURATOR_LOG_PATH") or CURATOR_LOG))),
        detail="started",
    )
    _log(f"starting interval={interval}s")

    while not STOP_REQUESTED:
        try:
            report = run_curator_once()
            _log(
                "scan_complete "
                f"pairs={report.get('pair_count', 0)} "
                f"status_counts={json.dumps(report.get('status_counts', {}), sort_keys=True)}"
            )
        except Exception as exc:
            _write_state(running=True, detail=f"scan_failed:{exc}", last_error=str(exc))
            _log(f"scan_failed error={exc}")
        _sleep_interruptibly(interval)

    _write_state(running=False, desired_running=False, stopped_at=_utc_iso_now(), detail="stopped")
    _log("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
