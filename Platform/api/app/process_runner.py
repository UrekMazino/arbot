from __future__ import annotations

import argparse
import logging
import os
import signal
import time
from datetime import datetime, timezone

from .services import bot_control, cointegrated_pairs


LOG = logging.getLogger("process_runner")
STOP_REQUESTED = False


def _handle_stop(signum, _frame) -> None:
    global STOP_REQUESTED
    STOP_REQUESTED = True
    LOG.warning("Received signal %s; stopping runner loop", signum)


def _sleep(seconds: float) -> None:
    deadline = time.time() + max(float(seconds), 0.1)
    while not STOP_REQUESTED and time.time() < deadline:
        time.sleep(min(0.5, max(0.1, deadline - time.time())))


def _env_flag(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, minimum: float | None = None) -> float:
    raw = os.getenv(name)
    try:
        value = float(raw) if raw not in (None, "") else float(default)
    except (TypeError, ValueError):
        value = float(default)
    if minimum is not None and value < minimum:
        value = minimum
    return value


def _parse_iso_timestamp(value: object) -> datetime | None:
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


def _request_is_fresh(status: dict) -> bool:
    request_time = _parse_iso_timestamp(status.get("request_updated_at"))
    if request_time is None:
        return False
    grace_seconds = _env_float("STATBOT_RUNNER_STARTUP_REQUEST_GRACE_SECONDS", 30.0, minimum=0.0)
    age_seconds = (datetime.now(timezone.utc) - request_time).total_seconds()
    return age_seconds <= grace_seconds


def _should_resume_desired(status: dict) -> bool:
    if not bool(status.get("desired_running")):
        return False
    if _env_flag("STATBOT_RUNNER_RESUME_DESIRED", False):
        return True
    return _request_is_fresh(status)


def _runner_owner(default: str) -> str:
    owner = str(os.getenv("STATBOT_PROCESS_OWNER", default) or default).strip()
    return owner or default


def _find_local_process(command_fragment: str) -> int:
    fragment = str(command_fragment or "").strip()
    if not fragment or os.name == "nt":
        return 0
    proc_root = "/proc"
    try:
        names = [name for name in os.listdir(proc_root) if name.isdigit()]
    except Exception:
        return 0
    current_pid = os.getpid()
    matches: list[int] = []
    for name in names:
        try:
            pid = int(name)
        except ValueError:
            continue
        if pid == current_pid:
            continue
        cmdline_path = os.path.join(proc_root, name, "cmdline")
        try:
            with open(cmdline_path, "rb") as handle:
                cmdline = handle.read().replace(b"\0", b" ").decode("utf-8", errors="ignore")
        except Exception:
            continue
        if fragment in cmdline:
            matches.append(pid)
    return min(matches) if matches else 0


def _recover_bot_process_status(status: dict) -> dict:
    status = dict(status or {})
    if bool(status.get("running")):
        return status
    pid = _find_local_process("main_execution.py")
    if pid <= 0:
        return status
    status["running"] = True
    status["pid"] = pid
    status["detail"] = "runner_recovered_process"
    status["process_owner"] = _runner_owner("bot-runner")
    status["desired_running"] = bool(status.get("desired_running")) if "desired_running" in status else True
    status["stopped_at"] = None
    return status


def _recover_pair_supply_process_status(status: dict) -> dict:
    status = dict(status or {})
    if bool(status.get("running")):
        return status
    pid = _find_local_process("pair_supply_daemon.py")
    if pid <= 0:
        return status
    status["running"] = True
    status["pid"] = pid
    status["detail"] = "runner_recovered_process"
    status["process_owner"] = _runner_owner("pair-supply-runner")
    status["desired_running"] = bool(status.get("desired_running")) if "desired_running" in status else True
    status["stopped_at"] = None
    return status


def _mark_bot_heartbeat(status: dict) -> dict:
    status = dict(status or {})
    status["process_mode"] = "runner"
    status["runner_owner"] = _runner_owner("bot-runner")
    status["runner_heartbeat_at"] = bot_control._utc_iso_now()
    bot_control._write_state(status)
    return status


def _mark_pair_supply_heartbeat(status: dict) -> dict:
    status = dict(status or {})
    status["process_mode"] = "runner"
    status["runner_owner"] = _runner_owner("pair-supply-runner")
    status["runner_heartbeat_at"] = cointegrated_pairs._utc_iso_now()
    cointegrated_pairs._write_supply_state(status)
    return status


def _clear_stale_bot_request_on_start() -> None:
    status = bot_control.get_bot_status()
    if _should_resume_desired(status):
        return
    if not bool(status.get("desired_running")):
        _mark_bot_heartbeat(status)
        return

    LOG.info("Clearing stale bot start request on runner startup")
    status["desired_running"] = False
    status["detail"] = "runner_ready_stopped" if not status.get("running") else "runner_startup_stop_requested"
    status["stopped_at"] = status.get("stopped_at") or bot_control._utc_iso_now()
    _mark_bot_heartbeat(status)
    if status.get("running"):
        bot_control._stop_bot_local(requested_by="bot-runner_startup")


def _clear_stale_pair_supply_request_on_start() -> None:
    status = cointegrated_pairs.get_pair_supply_status()
    if _should_resume_desired(status):
        return
    if not bool(status.get("desired_running")):
        _mark_pair_supply_heartbeat(status)
        return

    LOG.info("Clearing stale pair supply start request on runner startup")
    status["desired_running"] = False
    status["detail"] = (
        "runner_ready_stopped" if not status.get("running") else "runner_startup_stop_requested"
    )
    status["stopped_at"] = status.get("stopped_at") or cointegrated_pairs._utc_iso_now()
    _mark_pair_supply_heartbeat(status)
    if status.get("running"):
        cointegrated_pairs._stop_pair_supply_local(requested_by="pair-supply-runner_startup")


def run_bot_loop(poll_seconds: float) -> int:
    LOG.info("Bot runner started")
    _clear_stale_bot_request_on_start()
    last_start_attempt = 0.0
    while not STOP_REQUESTED:
        try:
            status = bot_control.get_bot_status()
            status = _recover_bot_process_status(status)
            _mark_bot_heartbeat(status)
            desired = bool(status.get("desired_running"))
            running = bool(status.get("running"))
            requested_by = str(status.get("requested_by") or "bot-runner")
            if desired and not running and (time.time() - last_start_attempt) >= 5.0:
                last_start_attempt = time.time()
                LOG.info("Starting requested bot execution process")
                _mark_bot_heartbeat(bot_control._start_bot_local(requested_by=requested_by))
            elif not desired and running:
                LOG.info("Stopping requested bot execution process")
                _mark_bot_heartbeat(bot_control._stop_bot_local(requested_by=requested_by))
        except Exception:
            LOG.exception("Bot runner cycle failed")
        _sleep(poll_seconds)

    try:
        status = bot_control.get_bot_status()
        if status.get("running"):
            LOG.info("Runner shutdown: stopping bot execution process")
            bot_control._stop_bot_local(requested_by="bot-runner_shutdown")
    except Exception:
        LOG.exception("Failed to stop bot process during runner shutdown")
    LOG.info("Bot runner stopped")
    return 0


def run_pair_supply_loop(poll_seconds: float) -> int:
    LOG.info("Pair supply runner started")
    _clear_stale_pair_supply_request_on_start()
    last_start_attempt = 0.0
    while not STOP_REQUESTED:
        try:
            status = cointegrated_pairs.get_pair_supply_status()
            status = _recover_pair_supply_process_status(status)
            _mark_pair_supply_heartbeat(status)
            desired = bool(status.get("desired_running"))
            running = bool(status.get("running"))
            requested_by = str(status.get("requested_by") or "pair-supply-runner")
            if desired and not running and (time.time() - last_start_attempt) >= 5.0:
                last_start_attempt = time.time()
                LOG.info("Starting requested pair supply process")
                _mark_pair_supply_heartbeat(
                    cointegrated_pairs._start_pair_supply_local(requested_by=requested_by)
                )
            elif not desired and running:
                LOG.info("Stopping requested pair supply process")
                _mark_pair_supply_heartbeat(
                    cointegrated_pairs._stop_pair_supply_local(requested_by=requested_by)
                )
        except Exception:
            LOG.exception("Pair supply runner cycle failed")
        _sleep(poll_seconds)

    try:
        status = cointegrated_pairs.get_pair_supply_status()
        if status.get("running"):
            LOG.info("Runner shutdown: stopping pair supply process")
            cointegrated_pairs._stop_pair_supply_local(requested_by="pair-supply-runner_shutdown")
    except Exception:
        LOG.exception("Failed to stop pair supply process during runner shutdown")
    LOG.info("Pair supply runner stopped")
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    parser = argparse.ArgumentParser(description="Run managed OKXStatBot background processes")
    parser.add_argument("target", choices=("bot", "pair-supply"))
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args()

    if args.target == "bot":
        return run_bot_loop(args.poll_seconds)
    return run_pair_supply_loop(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
