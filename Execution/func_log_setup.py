import logging
import os
import re
from datetime import datetime, timezone
from functools import lru_cache
from logging.handlers import RotatingFileHandler
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9 fallback
    ZoneInfo = None

_LOG_SETUP_DONE = False
_LOG_FILE_PATH = None
_RUN_DIR_RE = re.compile(r"^run_(?P<seq>\d+)_\d{8}_\d{6}$")


def _strip_wrapping_quotes(value):
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


@lru_cache(maxsize=1)
def _env_file_values():
    values = {}
    env_path = Path(__file__).resolve().parent / ".env"
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


def _next_run_sequence(log_root):
    if not log_root.exists():
        return 1
    max_seq = 0
    for entry in log_root.iterdir():
        if not entry.is_dir():
            continue
        match = _RUN_DIR_RE.match(entry.name)
        if not match:
            continue
        try:
            seq = int(match.group("seq"))
        except (TypeError, ValueError):
            continue
        if seq > max_seq:
            max_seq = seq
    return max_seq + 1


def _build_log_path():
    env_path = _config_value("STATBOT_LOG_PATH")
    if env_path:
        resolved = Path(env_path).expanduser()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved
    logs_root = Path(__file__).resolve().parents[1] / "Logs" / "v1"
    logs_root.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(_resolve_log_timezone()).strftime("%Y%m%d_%H%M%S")
    run_seq = _next_run_sequence(logs_root)
    run_dir = logs_root / f"run_{run_seq:02d}_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / f"log_{run_id}.log"


def get_log_path():
    global _LOG_FILE_PATH
    if _LOG_FILE_PATH is None:
        _LOG_FILE_PATH = _build_log_path()
        os.environ.setdefault("STATBOT_LOG_PATH", str(_LOG_FILE_PATH))
    return _LOG_FILE_PATH


def setup_logging():
    global _LOG_SETUP_DONE
    if _LOG_SETUP_DONE:
        return

    log_path = get_log_path()
    log_file = str(log_path)
    max_mb = _int_env("STATBOT_LOG_MAX_MB", 5)
    backups = _int_env("STATBOT_LOG_BACKUPS", 3)
    if max_mb <= 0:
        max_mb = 5
    if backups < 0:
        backups = 3
    max_bytes = max_mb * 1024 * 1024

    level_name = str(_config_value("STATBOT_LOG_LEVEL", "INFO")).strip().upper()
    level = getattr(logging, level_name, logging.INFO)
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

    root = logging.getLogger()
    root.setLevel(level)

    for handler in root.handlers:
        if isinstance(handler, RotatingFileHandler):
            base = getattr(handler, "baseFilename", "")
            if base and os.path.abspath(base) == os.path.abspath(log_file):
                _LOG_SETUP_DONE = True
                return

    # File handler (plain text)
    handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backups,
        encoding="utf-8",
    )
    handler.setFormatter(TimezoneAwareFormatter("%(asctime)s %(levelname)s %(message)s", tzinfo=log_timezone))
    root.addHandler(handler)

    # Console handler (colored output)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)

    # ANSI color codes
    RESET = "\033[0m"
    COLORS = {
        "DEBUG": "\033[36m",    # Cyan
        "INFO": "\033[32m",     # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",    # Red
        "CRITICAL": "\033[35m", # Magenta
    }

    class ColoredFormatter(TimezoneAwareFormatter):
        def format(self, record):
            levelname = record.levelname
            color = COLORS.get(levelname, RESET)
            record.levelname = f"{color}{levelname}{RESET}"
            return super().format(record)

    console_handler.setFormatter(ColoredFormatter("%(asctime)s %(levelname)s %(message)s", tzinfo=log_timezone))
    root.addHandler(console_handler)

    # Quiet noisy HTTP client logs (OKX SDK uses httpx/httpcore under the hood).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    _LOG_SETUP_DONE = True


def get_logger(name):
    setup_logging()
    return logging.getLogger(name)
