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
from datetime import datetime, timezone
from pathlib import Path


STOP_REQUESTED = False


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
        if key == "STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS":
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


def _handle_stop(signum, _frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True
    _write_log_line(f"{datetime.now(timezone.utc).isoformat()} pair_supply stop_requested signal={signum}")


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


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    _load_execution_env()

    strategy_dir = Path(__file__).resolve().parent
    strategy_script = strategy_dir / "main_strategy.py"
    interval_seconds = _pair_supply_interval_seconds()
    run_immediately = _env_bool("STATBOT_PAIR_SUPPLY_RUN_IMMEDIATELY", True)

    _write_log_line(
        f"{datetime.now(timezone.utc).isoformat()} pair_supply starting interval={interval_seconds}s immediate={int(run_immediately)}",
    )

    first_run = True
    while not STOP_REQUESTED:
        if not first_run or run_immediately:
            started = datetime.now(timezone.utc)
            _write_log_line(f"{started.isoformat()} pair_supply scan_start")
            try:
                env = os.environ.copy()
                env["PYTHONUNBUFFERED"] = "1"
                ret = _run_strategy_process(strategy_script, strategy_dir, env)
            except Exception as exc:
                ret = 1
                _write_log_line(f"{datetime.now(timezone.utc).isoformat()} pair_supply scan_error error={exc}")
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            _write_log_line(
                f"{datetime.now(timezone.utc).isoformat()} pair_supply scan_end exit_code={ret} elapsed_seconds={elapsed:.1f}",
            )

        first_run = False
        if STOP_REQUESTED:
            break
        _write_log_line(f"{datetime.now(timezone.utc).isoformat()} pair_supply sleeping seconds={interval_seconds}")
        _sleep_interruptibly(interval_seconds)

    _write_log_line(f"{datetime.now(timezone.utc).isoformat()} pair_supply stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
