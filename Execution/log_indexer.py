import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


RUN_DIR_RE = re.compile(r"^run_(?P<seq>\d+)_\d{8}_\d{6}$")
LOG_FILE_RE = re.compile(r"^log_(?P<ts>\d{8}_\d{6})\.log$", re.IGNORECASE)
LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) (?P<level>[A-Z]+) (?P<msg>.*)$"
)
RUN_END_RE = re.compile(
    r"RUN_END: reason=(?P<reason>[A-Za-z0-9_\-]+)(?: detail=(?P<detail>.*))?$"
)

INDEX_FIELDS = [
    "run_sequence",
    "run_id",
    "log_path",
    "run_end_reason",
    "run_end_detail",
    "run_end_time",
    "start_time",
    "end_time",
    "duration_seconds",
    "duration_human",
    "size_bytes",
    "size_human",
    "rotated_files",
    "rotated_total_bytes",
]


def _parse_ts(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S,%f")
    except ValueError:
        return None


def _format_duration(seconds):
    if seconds is None:
        return "n/a"
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "n/a"
    if seconds < 0:
        return "n/a"
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    if days:
        return f"{days}d {hours}h {minutes}m {sec}s"
    if hours:
        return f"{hours}h {minutes}m {sec}s"
    if minutes:
        return f"{minutes}m {sec}s"
    return f"{sec}s"


def _format_bytes(value):
    try:
        size = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if size < 0:
        return "n/a"
    units = ["B", "KB", "MB", "GB"]
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    return f"{size:.2f} {units[idx]}"


def _primary_log_file(run_dir, run_id):
    candidates = []
    if run_id:
        candidate = run_dir / f"log_{run_id}.log"
        if candidate.exists():
            return candidate
    for entry in run_dir.glob("log_*.log"):
        candidates.append(entry)
    if not candidates:
        return None
    candidates = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _rotated_files(run_dir, log_file):
    if not log_file:
        return []
    prefix = log_file.name + "."
    return [p for p in run_dir.iterdir() if p.is_file() and p.name.startswith(prefix)]


def _parse_log_bounds(log_file):
    if not log_file or not log_file.exists():
        return None, None, None, None, None
    start_ts = None
    end_ts = None
    run_end_reason = None
    run_end_detail = None
    run_end_time = None
    try:
        with open(log_file, "r", encoding="utf-8", errors="ignore") as handle:
            for raw in handle:
                match = LOG_LINE_RE.match(raw.strip())
                if not match:
                    continue
                ts = _parse_ts(match.group("ts"))
                if not ts:
                    continue
                if start_ts is None:
                    start_ts = ts
                end_ts = ts
                end_match = RUN_END_RE.search(match.group("msg") or "")
                if end_match:
                    run_end_reason = end_match.group("reason")
                    detail = (end_match.group("detail") or "").strip()
                    if detail and " exit_code=" in detail:
                        detail = detail.split(" exit_code=", 1)[0].strip()
                    run_end_detail = detail if detail else None
                    run_end_time = ts
    except Exception:
        return None, None, None, None, None
    return start_ts, end_ts, run_end_reason, run_end_detail, run_end_time


def _collect_runs(log_root):
    runs = []
    if not log_root.exists():
        return runs
    for entry in log_root.iterdir():
        if not entry.is_dir():
            continue
        match = RUN_DIR_RE.match(entry.name)
        if not match:
            continue
        try:
            run_seq = int(match.group("seq"))
        except (TypeError, ValueError):
            run_seq = None
        run_id = entry.name.split("_", 2)[-1] if "_" in entry.name else ""
        log_file = _primary_log_file(entry, run_id)
        start_ts, end_ts, run_end_reason, run_end_detail, run_end_time = _parse_log_bounds(log_file)
        duration_seconds = None
        if start_ts and end_ts:
            duration_seconds = int((end_ts - start_ts).total_seconds())

        rotated = _rotated_files(entry, log_file)
        size_bytes = 0
        if log_file and log_file.exists():
            size_bytes += log_file.stat().st_size
        rotated_total = 0
        for rot in rotated:
            rotated_total += rot.stat().st_size
            size_bytes += rot.stat().st_size

        runs.append(
            {
                "run_sequence": run_seq,
                "run_id": run_id or "",
                "log_path": str(log_file) if log_file else "",
                "run_end_reason": run_end_reason,
                "run_end_detail": run_end_detail,
                "run_end_time": run_end_time.isoformat() if run_end_time else "",
                "start_time": start_ts.isoformat() if start_ts else "",
                "end_time": end_ts.isoformat() if end_ts else "",
                "duration_seconds": duration_seconds,
                "duration_human": _format_duration(duration_seconds),
                "size_bytes": size_bytes if size_bytes else None,
                "size_human": _format_bytes(size_bytes) if size_bytes else "0.00 B",
                "rotated_files": len(rotated),
                "rotated_total_bytes": rotated_total if rotated_total else 0,
            }
        )
    return runs


def _sort_runs(runs):
    def _key(item):
        seq = item.get("run_sequence")
        if isinstance(seq, int):
            return (0, seq)
        start = item.get("start_time") or ""
        return (1, start)

    return sorted(runs, key=_key)


def write_log_index(log_root):
    runs = _sort_runs(_collect_runs(log_root))
    payload = {
        "log_version": "v1",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "run_count": len(runs),
        "runs": runs,
    }
    log_root.mkdir(parents=True, exist_ok=True)
    index_json = log_root / "index.json"
    index_csv = log_root / "index.csv"
    index_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if runs:
        with open(index_csv, "w", newline="", encoding="utf-8") as handle:
            handle.write(",".join(INDEX_FIELDS) + "\n")
            for row in runs:
                values = []
                for field in INDEX_FIELDS:
                    value = row.get(field)
                    if value is None:
                        value = ""
                    values.append(str(value))
                handle.write(",".join(values) + "\n")


def main():
    repo_root = Path(__file__).resolve().parents[1]
    log_root = repo_root / "Logs" / "v1"
    write_log_index(log_root)
    print(f"log_indexer: wrote {log_root / 'index.json'}")


if __name__ == "__main__":
    raise SystemExit(main())
