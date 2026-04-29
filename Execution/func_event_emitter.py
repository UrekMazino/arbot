from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

_MODE_VALUES = {"off", "shadow", "active"}
_SEVERITY_VALUES = {"info", "warn", "error", "critical"}
_KNOWN_EVENT_TYPES = {
    "heartbeat",
    "regime_update",
    "strategy_update",
    "trade_open",
    "trade_close",
    "pair_switch",
    "risk_alert",
    "report_status",
    "entry_reject",
    "liquidity_check",
    "trade_quality_gate",
    "fill_summary",
    "reconciliation_check",
    "gate_enforced",
    "reconciliation_warning",
    "data_quality_warning",
    "status_update",
}
_ID_SAFE_RE = re.compile(r"[^a-zA-Z0-9._-]+")
_RUN_DIR_RE = re.compile(r"^run_\d+_\d{8}_\d{6}$")
_DEFAULT_SPOOL_DIR = Path(__file__).resolve().parent / "state" / "event_spool"


def _to_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _to_int(raw: str | None, default: int, minimum: int) -> int:
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        value = default
    if value < minimum:
        value = minimum
    return value


def _to_float(raw: str | None, default: float, minimum: float) -> float:
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = default
    if value < minimum:
        value = minimum
    return value


def _safe_identifier(value: str | None, fallback: str, max_len: int = 36) -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    text = _ID_SAFE_RE.sub("-", text).strip("-")
    if not text:
        text = fallback
    if len(text) > max_len:
        text = text[:max_len]
    return text


def _infer_run_id() -> str:
    env_run_id = os.getenv("STATBOT_RUN_ID")
    if env_run_id:
        return _safe_identifier(env_run_id, "run-unknown")

    log_path_raw = str(os.getenv("STATBOT_LOG_PATH", "") or "").strip()
    if log_path_raw:
        try:
            log_path = Path(log_path_raw).expanduser()
            run_dir_name = log_path.parent.name
            if _RUN_DIR_RE.match(run_dir_name):
                return _safe_identifier(run_dir_name, "run-unknown")
            stem = log_path.stem
            if stem.startswith("log_"):
                return _safe_identifier(stem.replace("log_", "", 1), "run-unknown")
        except Exception:
            pass

    return _safe_identifier(time.strftime("%Y%m%d_%H%M%S"), "run-unknown")


def _normalize_mode(raw: str | None) -> str:
    mode = str(raw or "active").strip().lower()
    if mode not in _MODE_VALUES:
        return "active"
    return mode


class EventEmitter:
    def __init__(self, logger: Any = None):
        self.logger = logger
        self.mode = _normalize_mode(os.getenv("STATBOT_EVENT_EMITTER_MODE", "active"))
        self.enabled = self.mode != "off"
        self.api_base = str(
            os.getenv("STATBOT_EVENT_API_BASE", "http://127.0.0.1:8081/api/v2") or ""
        ).strip().rstrip("/")
        self.timeout_seconds = _to_float(
            os.getenv("STATBOT_EVENT_TIMEOUT_SECONDS", "3"),
            default=3.0,
            minimum=0.5,
        )
        self.batch_size = _to_int(
            os.getenv("STATBOT_EVENT_BATCH_SIZE", "25"),
            default=25,
            minimum=1,
        )
        self.flush_seconds = _to_int(
            os.getenv("STATBOT_EVENT_FLUSH_SECONDS", "10"),
            default=10,
            minimum=1,
        )
        self.spool_replay_enabled = _to_bool(
            os.getenv("STATBOT_EVENT_REPLAY_SPOOL", "1"),
            default=True,
        )
        spool_dir_raw = str(os.getenv("STATBOT_EVENT_SPOOL_DIR", "") or "").strip()
        self.spool_dir = Path(spool_dir_raw).expanduser() if spool_dir_raw else _DEFAULT_SPOOL_DIR
        self.ingest_key = str(os.getenv("STATBOT_EVENT_INGEST_KEY", "") or "").strip()
        self.bot_instance_id = _safe_identifier(
            os.getenv("STATBOT_BOT_INSTANCE_ID"),
            fallback="statbot-v1-local",
            max_len=36,
        )
        self.run_id = _infer_run_id()
        self._queue: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._last_flush_ts = 0.0
        self._shadow_notice_logged = False

        if self.enabled:
            self.spool_dir.mkdir(parents=True, exist_ok=True)

    def _log(self, level: str, message: str, *args: Any) -> None:
        if not self.logger:
            return
        try:
            log_fn = getattr(self.logger, level, None)
            if callable(log_fn):
                log_fn(message, *args)
        except Exception:
            return

    def _build_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None,
        severity: str,
        ts: float | None,
        run_id: str | None,
    ) -> dict[str, Any]:
        e_type = str(event_type or "").strip().lower()
        if not e_type:
            raise ValueError("event_type is required")
        sev = str(severity or "info").strip().lower()
        if sev not in _SEVERITY_VALUES:
            sev = "info"
        if e_type not in _KNOWN_EVENT_TYPES:
            self._log("warning", "EVENT_EMITTER unknown event_type=%s (sending anyway)", e_type)
        body = payload if isinstance(payload, dict) else {"value": payload}
        now_ts = float(ts if ts is not None else time.time())
        event_run_id = _safe_identifier(run_id, self.run_id) if run_id else self.run_id
        return {
            "event_id": str(uuid.uuid4()),
            "run_id": event_run_id,
            "bot_instance_id": self.bot_instance_id,
            "ts": now_ts,
            "event_type": e_type,
            "severity": sev,
            "payload": body,
        }

    def emit(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        severity: str = "info",
        ts: float | None = None,
        run_id: str | None = None,
        flush: bool = False,
    ) -> bool:
        if not self.enabled:
            return False

        event = self._build_event(event_type, payload, severity, ts, run_id)
        if self.mode == "shadow":
            if not self._shadow_notice_logged:
                self._log("info", "EVENT_EMITTER shadow mode enabled; events are not posted")
                self._shadow_notice_logged = True
            self._log(
                "debug",
                "EVENT_SHADOW type=%s severity=%s run_id=%s",
                event["event_type"],
                event["severity"],
                event["run_id"],
            )
            return True

        with self._lock:
            self._queue.append(event)
            should_flush = flush
            if not should_flush:
                should_flush = len(self._queue) >= self.batch_size
            if not should_flush:
                should_flush = (time.time() - self._last_flush_ts) >= self.flush_seconds

        if should_flush:
            self.flush()
        return True

    def flush(self, force: bool = False) -> None:
        if not self.enabled or self.mode != "active":
            return

        if self.spool_replay_enabled:
            self._replay_spool(max_files=2)

        while True:
            with self._lock:
                if not self._queue:
                    self._last_flush_ts = time.time()
                    return
                if not force and len(self._queue) < self.batch_size:
                    if (time.time() - self._last_flush_ts) < self.flush_seconds:
                        return
                batch = list(self._queue[: self.batch_size])

            if self._post_batch(batch):
                with self._lock:
                    del self._queue[: len(batch)]
                    self._last_flush_ts = time.time()
                continue

            # Network/API path failed; spool and drop from memory queue to prevent unbounded growth.
            self._spool_events(batch)
            with self._lock:
                del self._queue[: len(batch)]
                self._last_flush_ts = time.time()
            return

    def close(self) -> None:
        self.flush(force=True)

    def _endpoint(self) -> str:
        return f"{self.api_base}/bots/{self.bot_instance_id}/events/batch"

    def _request_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.ingest_key:
            headers["X-Bot-Ingest-Key"] = self.ingest_key
        return headers

    def _post_batch(self, events: list[dict[str, Any]]) -> bool:
        if not events:
            return True
        payload = {"events": events}
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        req = urllib_request.Request(
            self._endpoint(),
            data=body,
            headers=self._request_headers(),
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=self.timeout_seconds) as resp:
                code = int(getattr(resp, "status", 0) or 0)
                if 200 <= code < 300:
                    return True
                self._log("warning", "EVENT_EMITTER post failed status=%s", code)
                return False
        except urllib_error.HTTPError as exc:
            self._log("warning", "EVENT_EMITTER post failed status=%s reason=%s", exc.code, exc.reason)
            return False
        except urllib_error.URLError as exc:
            self._log("warning", "EVENT_EMITTER network error: %s", exc.reason)
            return False
        except Exception as exc:
            self._log("warning", "EVENT_EMITTER unexpected post error: %s", exc)
            return False

    def _spool_events(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        try:
            self.spool_dir.mkdir(parents=True, exist_ok=True)
            spool_name = f"{int(time.time())}_{uuid.uuid4().hex}.ndjson"
            spool_path = self.spool_dir / spool_name
            with spool_path.open("w", encoding="utf-8") as handle:
                for row in events:
                    handle.write(json.dumps(row, ensure_ascii=True, separators=(",", ":")))
                    handle.write("\n")
            self._log(
                "warning",
                "EVENT_EMITTER spooled %d events to %s",
                len(events),
                spool_path,
            )
        except Exception as exc:
            self._log("warning", "EVENT_EMITTER spool write failed: %s", exc)

    def _replay_spool(self, max_files: int = 2) -> None:
        try:
            files = sorted(self.spool_dir.glob("*.ndjson"))
        except Exception:
            return
        if not files:
            return

        for spool_file in files[:max_files]:
            try:
                lines = spool_file.read_text(encoding="utf-8").splitlines()
                events = []
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        continue
                if not events:
                    spool_file.unlink(missing_ok=True)
                    continue
                if self._post_batch(events):
                    spool_file.unlink(missing_ok=True)
                    self._log("info", "EVENT_EMITTER replayed %d events from %s", len(events), spool_file)
                else:
                    # Stop replay on first failed spool file to preserve order.
                    return
            except Exception:
                return


_EMITTER_SINGLETON: EventEmitter | None = None
_EMITTER_LOCK = threading.Lock()


def get_event_emitter(logger: Any = None) -> EventEmitter:
    global _EMITTER_SINGLETON
    with _EMITTER_LOCK:
        if _EMITTER_SINGLETON is None:
            _EMITTER_SINGLETON = EventEmitter(logger=logger)
        elif logger is not None and _EMITTER_SINGLETON.logger is None:
            _EMITTER_SINGLETON.logger = logger
        return _EMITTER_SINGLETON


def get_event_context(logger: Any = None) -> dict[str, str]:
    emitter = get_event_emitter(logger=logger)
    return {
        "mode": emitter.mode,
        "run_id": emitter.run_id,
        "bot_instance_id": emitter.bot_instance_id,
    }


def emit_event(
    event_type: str,
    payload: dict[str, Any] | None = None,
    severity: str = "info",
    ts: float | None = None,
    run_id: str | None = None,
    flush: bool = False,
    logger: Any = None,
) -> bool:
    emitter = get_event_emitter(logger=logger)
    return emitter.emit(
        event_type=event_type,
        payload=payload,
        severity=severity,
        ts=ts,
        run_id=run_id,
        flush=flush,
    )


def flush_events(force: bool = False, logger: Any = None) -> None:
    emitter = get_event_emitter(logger=logger)
    emitter.flush(force=force)
