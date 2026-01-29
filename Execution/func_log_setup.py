import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_SETUP_DONE = False
_LOG_FILE_PATH = None


def _int_env(name, default):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default


def _build_log_path():
    env_path = os.getenv("STATBOT_LOG_PATH")
    if env_path:
        resolved = Path(env_path).expanduser()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved
    logs_dir = Path(__file__).resolve().parents[1] / "Logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%m_%m%d%y_%H%M%S")
    return logs_dir / f"log_{timestamp}.log"


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

    level_name = os.getenv("STATBOT_LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    for handler in root.handlers:
        if isinstance(handler, RotatingFileHandler):
            base = getattr(handler, "baseFilename", "")
            if base and os.path.abspath(base) == os.path.abspath(log_file):
                _LOG_SETUP_DONE = True
                return

    handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backups,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root.addHandler(handler)

    # Quiet noisy HTTP client logs (OKX SDK uses httpx/httpcore under the hood).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    _LOG_SETUP_DONE = True


def get_logger(name):
    setup_logging()
    return logging.getLogger(name)
