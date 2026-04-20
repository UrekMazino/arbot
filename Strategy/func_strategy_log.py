import logging
import os
from datetime import datetime, timezone
from functools import lru_cache
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9 fallback
    ZoneInfo = None

_LOGGER = None


def _strip_wrapping_quotes(value):
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


@lru_cache(maxsize=1)
def _env_file_values():
    values = {}
    env_path = Path(__file__).resolve().parents[1] / "Execution" / ".env"
    if not env_path.exists():
        return values
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
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
        values[key] = _strip_wrapping_quotes(value)
    return values


def _config_value(name, default=None):
    raw = os.getenv(name)
    if raw is not None and str(raw).strip() != "":
        return _strip_wrapping_quotes(raw)
    value = _env_file_values().get(name)
    if value is None or str(value).strip() == "":
        return default
    return value


def _int_env(name, default):
    raw = _config_value(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default


def _resolve_log_timezone():
    timezone_name = str(_config_value("STATBOT_TIMEZONE", _config_value("TZ", "")) or "").strip()
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


def get_strategy_logger():
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER

    logger = logging.getLogger("strategy")
    if logger.handlers:
        _LOGGER = logger
        return logger

    level_name = str(_config_value("STATBOT_LOG_LEVEL", "INFO")).strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)
    log_timezone = _resolve_log_timezone()

    class TimezoneAwareFormatter(logging.Formatter):
        def __init__(self, fmt=None, datefmt=None, tzinfo=None):
            super().__init__(fmt=fmt, datefmt=datefmt)
            self._tzinfo = tzinfo or timezone.utc

        def formatTime(self, record, datefmt=None):
            dt = datetime.fromtimestamp(record.created, tz=self._tzinfo)
            if datefmt:
                return dt.strftime(datefmt)
            return f"{dt.strftime('%Y-%m-%d %H:%M:%S')},{int(record.msecs):03d}"

    log_path = str(_config_value("STATBOT_LOG_PATH", "") or "").strip()
    if log_path:
        max_mb = _int_env("STATBOT_LOG_MAX_MB", 5)
        backups = _int_env("STATBOT_LOG_BACKUPS", 3)
        if max_mb <= 0:
            max_mb = 5
        if backups < 0:
            backups = 3
        max_bytes = max_mb * 1024 * 1024
        handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backups,
            encoding="utf-8",
        )
        handler.setFormatter(TimezoneAwareFormatter("%(asctime)s %(levelname)s %(message)s", tzinfo=log_timezone))
        logger.addHandler(handler)
        logger.propagate = False
    else:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(TimezoneAwareFormatter("%(asctime)s %(levelname)s %(message)s", tzinfo=log_timezone))
        logger.addHandler(console_handler)
        logger.propagate = False

    # Quiet noisy HTTP client logs (OKX SDK uses httpx/httpcore under the hood).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    _LOGGER = logger
    return logger
