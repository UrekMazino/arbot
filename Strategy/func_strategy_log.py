import logging
import os
from logging.handlers import RotatingFileHandler

_LOGGER = None


def _int_env(name, default):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default


def get_strategy_logger():
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER

    logger = logging.getLogger("strategy")
    if logger.handlers:
        _LOGGER = logger
        return logger

    level_name = os.getenv("STATBOT_LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)

    log_path = os.getenv("STATBOT_LOG_PATH", "").strip()
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
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
    else:
        logging.basicConfig(level=level)

    # Quiet noisy HTTP client logs (OKX SDK uses httpx/httpcore under the hood).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    _LOGGER = logger
    return logger
