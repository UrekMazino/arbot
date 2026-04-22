from __future__ import annotations

import os
from pathlib import Path
from typing import TextIO


def _strip_wrapping_quotes(value: str | None) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _read_env_file_value(env_file: Path | None, name: str) -> str | None:
    if not env_file or not env_file.exists():
        return None
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except Exception:
        return None
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == name:
            return _strip_wrapping_quotes(value)
    return None


def _int_setting(name: str, default: int, *, env_file: Path | None = None) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        raw = _read_env_file_value(env_file, name)
    try:
        return int(float(raw)) if raw not in (None, "") else int(default)
    except (TypeError, ValueError):
        return int(default)


def log_rotation_settings(env_file: Path | None = None) -> tuple[int, int]:
    max_mb = _int_setting("STATBOT_LOG_MAX_MB", 5, env_file=env_file)
    backups = _int_setting("STATBOT_LOG_BACKUPS", 3, env_file=env_file)
    if max_mb <= 0:
        max_mb = 5
    if backups < 0:
        backups = 3
    return max_mb, backups


def rotated_log_paths(path: Path, backups: int) -> list[Path]:
    backup_count = max(int(backups or 0), 0)
    return [path.with_name(f"{path.name}.{idx}") for idx in range(1, backup_count + 1)]


def rotate_log_file_if_needed(
    path: Path,
    *,
    env_file: Path | None = None,
    max_mb: int | None = None,
    backups: int | None = None,
    max_bytes: int | None = None,
) -> bool:
    if not path.exists():
        return False

    resolved_max_mb, resolved_backups = log_rotation_settings(env_file)
    if max_mb is not None:
        resolved_max_mb = int(max_mb)
    if backups is not None:
        resolved_backups = max(int(backups), 0)
    resolved_max_bytes = int(max_bytes) if max_bytes is not None else resolved_max_mb * 1024 * 1024
    if resolved_max_bytes <= 0:
        return False

    try:
        if path.stat().st_size < resolved_max_bytes:
            return False
    except OSError:
        return False

    try:
        if resolved_backups <= 0:
            path.unlink(missing_ok=True)
            return True

        oldest = path.with_name(f"{path.name}.{resolved_backups}")
        oldest.unlink(missing_ok=True)
        for idx in range(resolved_backups - 1, 0, -1):
            src = path.with_name(f"{path.name}.{idx}")
            if src.exists():
                src.replace(path.with_name(f"{path.name}.{idx + 1}"))
        path.replace(path.with_name(f"{path.name}.1"))
        return True
    except OSError:
        # The file can be held open by an active child process on Windows. In
        # that case, leave it alone and try again on the next start/append.
        return False


def open_rotating_append_log(
    path: Path,
    *,
    env_file: Path | None = None,
    max_mb: int | None = None,
    backups: int | None = None,
    max_bytes: int | None = None,
) -> TextIO:
    rotate_log_file_if_needed(
        path,
        env_file=env_file,
        max_mb=max_mb,
        backups=backups,
        max_bytes=max_bytes,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("a", encoding="utf-8", errors="ignore")
