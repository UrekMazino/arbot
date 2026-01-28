import time

_LAST_LOG_TS = {}


def is_disconnect_error(err):
    text = str(err).lower()
    patterns = (
        "server disconnected",
        "connection reset",
        "connection aborted",
        "connection refused",
        "connection error",
        "connection",
        "timed out",
        "timeout",
    )
    return any(pat in text for pat in patterns)


def _should_log(key, cooldown_seconds):
    now = time.time()
    last = _LAST_LOG_TS.get(key, 0.0)
    if now - last >= cooldown_seconds:
        _LAST_LOG_TS[key] = now
        return True
    return False


def log_disconnect_once(key, message, cooldown_seconds=60, logger=None):
    if not _should_log(key, cooldown_seconds):
        return False
    msg = f"{message} (cooldown {cooldown_seconds}s)"
    if logger:
        logger.warning(msg)
    else:
        print(msg)
    return True


def call_with_retries(func, attempts=3, base_delay=1.0, max_delay=8.0):
    delay = base_delay
    last_exc = None
    for attempt in range(attempts):
        try:
            return func()
        except Exception as exc:
            last_exc = exc
            if not is_disconnect_error(exc) or attempt >= attempts - 1:
                break
            time.sleep(delay)
            delay = min(max_delay, delay * 2)
    if last_exc:
        raise last_exc
    return None
