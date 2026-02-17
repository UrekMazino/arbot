import argparse
import csv
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) (?P<level>[A-Z]+) (?P<msg>.*)$"
)
TICKER_CONFIG_RE = re.compile(
    r"ticker_1=(?P<t1>[^,]+), ticker_2=(?P<t2>[^,]+), signal_positive=(?P<sp>[^,]+), signal_negative=(?P<sn>[^\s]+)"
)
START_EQUITY_RE = re.compile(r"Starting equity: (?P<eq>[-+]?\d+\.\d+) USDT")
BALANCE_SNAPSHOT_RE = re.compile(
    r"Balance snapshot \(USDT\): availBal=(?P<avail_bal>[-+]?\d+\.\d+) \| availEq=(?P<avail_eq>[-+]?\d+\.\d+) \| td_mode=(?P<td_mode>[^\s|]+) \| pos_mode=(?P<pos_mode>[^\s|]+)"
)
PNL_LINE_RE = re.compile(
    r"PnL: (?P<pnl>[-+]?\d+\.\d+) USDT \((?P<pnl_pct>[-+]?\d+\.\d+)%\) \| Equity: (?P<equity>\d+\.\d+) USDT \| "
    r"Session: (?P<session>[-+]?\d+\.\d+) USDT \((?P<session_pct>[-+]?\d+\.\d+)%\)"
)
TRADE_CLOSED_RE = re.compile(
    r"PNL_ALERT.*Trade closed (?P<result>WIN|LOSS) \| PnL (?P<pnl>[-+]?\d+\.\d+) USDT \((?P<pnl_pct>[-+]?\d+\.\d+)%\) "
    r"\| Equity (?P<equity>\d+\.\d+) USDT \| Session (?P<session>[-+]?\d+\.\d+) USDT \((?P<session_pct>[-+]?\d+\.\d+)%\)"
    r"(?: \| Strategy (?P<strategy>[A-Z0-9_]+) \| Regime (?P<regime>[A-Z0-9_]+))?"
)
POSITION_OPEN_RE = re.compile(r"Position opened: entry_z=(?P<entry_z>[-+]?\d+\.\d+)")
STRATEGY_TRADE_OPEN_RE = re.compile(
    r"STRATEGY_TRADE_OPEN: strategy=(?P<strategy>[A-Z0-9_]+) regime=(?P<regime>[A-Z0-9_]+) "
    r"entry_z=(?P<entry_z>[-+]?\d+\.\d+) size_mult=(?P<size_mult>[-+]?\d+\.\d+)"
)
STRATEGY_TRADE_CLOSE_RE = re.compile(
    r"STRATEGY_TRADE_CLOSE: strategy=(?P<strategy>[A-Z0-9_]+) regime=(?P<regime>[A-Z0-9_]+) "
    r"result=(?P<result>WIN|LOSS) pnl=(?P<pnl>[-+]?\d+\.\d+) hold_min=(?P<hold_min>[^\s]+) "
    r"exit_reason=(?P<exit_reason>[^\s]+)"
)
STRATEGY_CHANGE_RE = re.compile(
    r"STRATEGY_CHANGE: from=(?P<from>[A-Z0-9_]+) to=(?P<to>[A-Z0-9_]+) "
    r"reason=(?P<reason>[^\s]+) in_position=(?P<in_position>[01])"
)
STRATEGY_GATE_ENFORCED_RE = re.compile(
    r"STRATEGY_GATE_ENFORCED: strategy=(?P<strategy>[A-Z0-9_]+) reason=(?P<reason>[^\s]+) action=(?P<action>[^\s]+)"
)
COINT_GATE_RE = re.compile(
    r"COINT_GATE: strategy=(?P<strategy>[A-Z0-9_]+) coint_flag=(?P<coint_flag>\d+) allow_new=(?P<allow_new>[01]) mode=(?P<mode>[a-z]+)",
    re.IGNORECASE,
)
MEAN_SHIFT_GATE_RE = re.compile(
    r"MEAN_SHIFT_GATE: strategy=(?P<strategy>[A-Z0-9_]+) shift_z=(?P<shift_z>[-+]?\d+\.\d+) "
    r"threshold=(?P<threshold>[-+]?\d+\.\d+) allow_new=(?P<allow_new>[01]) mode=(?P<mode>[a-z]+) basis=(?P<basis>[^\s]+)",
    re.IGNORECASE,
)
STRATEGY_COOLDOWN_ON_RE = re.compile(
    r"STRATEGY_COOLDOWN_ON: strategy=(?P<strategy>[A-Z0-9_]+) reason=(?P<reason>[^\s]+) until_ts=(?P<until_ts>[-+]?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
STRATEGY_COOLDOWN_OFF_RE = re.compile(
    r"STRATEGY_COOLDOWN_OFF: strategy=(?P<strategy>[A-Z0-9_]+)",
    re.IGNORECASE,
)
DIRECTIONAL_FILTER_SHADOW_RE = re.compile(
    r"DIRECTIONAL_FILTER_SHADOW: strategy=(?P<strategy>[A-Z0-9_]+) allow_new=(?P<allow_new>[01]) reason=(?P<reason>[^\s]+)",
    re.IGNORECASE,
)
DIRECTIONAL_FILTER_ACTIVE_BLOCK_RE = re.compile(
    r"DIRECTIONAL_FILTER_ACTIVE_BLOCK: strategy=(?P<strategy>[A-Z0-9_]+) reason=(?P<reason>[^\s]+)",
    re.IGNORECASE,
)
LIQUIDITY_RE = re.compile(
    r"Liquidity check: long_target=(?P<long_target>[-+]?\d+\.\d+) short_target=(?P<short_target>[-+]?\d+\.\d+) "
    r"liquidity_long=(?P<liquidity_long>[-+]?\d+\.\d+) liquidity_short=(?P<liquidity_short>[-+]?\d+\.\d+)"
)
ENTRY_SIGNAL_RE = re.compile(r"ENTRY SIGNAL DETECTED", re.IGNORECASE)
LIQUIDITY_REJECT_RE = re.compile(r"LIQUIDITY_REJECT", re.IGNORECASE)
POSITION_OPENED_RE = re.compile(r"Position opened:", re.IGNORECASE)
ENTRY_PLACED_RE = re.compile(
    r"Placed (?P<side>long|short) entry: ticker=(?P<ticker>[^ ]+) id=(?P<ord_id>\d+) entry_price=(?P<entry_price>[-+]?\d+\.\d+)"
)
FILL_RE = re.compile(
    r"Fills for (?P<ticker>[^ ]+) ordId=(?P<ord_id>\d+): .* avg_px=(?P<avg_px>[-+]?\d+\.\d+)"
)
RUN_END_RE = re.compile(
    r"RUN_END: reason=(?P<reason>[A-Za-z0-9_\-]+)(?: detail=(?P<detail>.*))?$"
)
CURRENT_PAIR_RE = re.compile(r"Current pair: (?P<t1>[^/]+)/(?P<t2>[^\s]+)")
PAIR_SWITCH_RE = re.compile(r"Attempting to switch to next pair \(reason=(?P<reason>[^)]+)\)")
PAIR_SWITCH_BLOCKED_RE = re.compile(r"Pair switch blocked", re.IGNORECASE)
PAIR_MOVED_HOSPITAL_RE = re.compile(r"Pair moved to hospital: (?P<t1>[^/]+)/(?P<t2>[^\s]+) reason=(?P<reason>[^\s]+)")
PAIR_MOVED_GRAVEYARD_RE = re.compile(r"Pair moved to graveyard: (?P<t1>[^/]+)/(?P<t2>[^\s]+) reason=(?P<reason>[^\s]+)")
HOSPITAL_PRIORITY_RE = re.compile(r"Prioritizing hospital pair (?P<t1>[^/]+)/(?P<t2>[^\s]+)")
STRATEGY_REFRESH_RE = re.compile(r"(Strategy refresh|refresh pair universe|Searching for new pairs)", re.IGNORECASE)
LIQUIDITY_FALLBACK_ATTEMPT_RE = re.compile(
    r"Execution liquidity fallback attempt \d+/\d+: min_ratio=(?P<ratio>[-+]?\d+\.\d+)x"
)
LIQUIDITY_ATTEMPT_RE = re.compile(
    r"Execution liquidity attempt \d+/\d+: min_ratio=(?P<ratio>[-+]?\d+\.\d+)x"
)
LIQUIDITY_RATIO_RE = re.compile(
    r"Liquidity ratios .*long=(?P<long>[-+]?\d+\.\d+)x short=(?P<short>[-+]?\d+\.\d+)x \(min=(?P<min>[-+]?\d+\.\d+)x\)"
)
LIQUIDITY_DOWNSIZE_RE = re.compile(r"Liquidity downsize: target=[-+]?\d+\.\d+ -> [-+]?\d+\.\d+")
PNL_FALLBACK_USED_RE = re.compile(r"PnL fallback used: legs=(?P<legs>\d+) basis=(?P<basis>[^\s]+)")
PNL_FALLBACK_CLEARED_RE = re.compile(r"PnL fallback cleared", re.IGNORECASE)
ORDERBOOK_BACKOFF_RE = re.compile(r"Orderbook backoff for (?P<inst>[^:]+): (?P<reason>[^()]+) \((?P<seconds>\d+)s\)")
ORDERBOOK_BACKOFF_ACTIVE_RE = re.compile(r"orderbook backoff active", re.IGNORECASE)
ORDERBOOK_MID_FAIL_RE = re.compile(r"failed to fetch mid prices", re.IGNORECASE)
CANDLE_SHORTFALL_RE = re.compile(
    r"Warning:\s*Got\s+(?P<got>\d+)\s+candles,\s+expected\s+(?P<expected>\d+)",
    re.IGNORECASE,
)
RECON_POST_RE = re.compile(
    r"Equity reconciliation(?: \(post-close\))?:\s*trade_pnl=(?P<trade_pnl>[-+]?\d+\.\d+)\s+"
    r"equity_change=(?P<equity_change>[-+]?\d+\.\d+)\s+diff=(?P<diff>[-+]?\d+\.\d+)\s+"
    r"fees=(?P<fees>[-+]?\d+\.\d+)\s+slippage=(?P<slippage>[-+]?\d+\.\d+)\s+"
    r"funding=(?P<funding>[-+]?\d+\.\d+)\s+unexplained=(?P<unexplained>[-+]?\d+\.\d+)",
    re.IGNORECASE,
)
RECON_LARGE_DELTA_RE = re.compile(
    r"(?:Large realized-vs-estimated PnL delta|Large PnL discrepancy detected):.*diff=(?P<diff>[-+]?\d+\.\d+)",
    re.IGNORECASE,
)
RECON_LARGE_UNEXPLAINED_RE = re.compile(
    r"Large unexplained reconciliation component(?: \(post-close\))?:\s*(?P<unexplained>[-+]?\d+\.\d+)\s+USDT\s+\((?P<pct>[-+]?\d+\.\d+)%",
    re.IGNORECASE,
)

ALERT_PATTERNS = [
    re.compile(r"\bERROR\b", re.IGNORECASE),
    re.compile(r"CRITICAL|UNHANDLED EXCEPTION", re.IGNORECASE),
    re.compile(r"KILL-SWITCH TRIGGERED", re.IGNORECASE),
    re.compile(r"CIRCUIT BREAKER", re.IGNORECASE),
    re.compile(r"compliance restricted", re.IGNORECASE),
    re.compile(r"ORDERBOOK DEAD", re.IGNORECASE),
    re.compile(r"PNL_ALERT", re.IGNORECASE),
]

RUN_DIR_RE = re.compile(r"^run_(?P<seq>\d+)_\d{8}_\d{6}$")
REPORT_SCHEMA_VERSION = "1.3.0"
INDEX_FIELDS = [
    "run_sequence",
    "run_id",
    "start_time",
    "end_time",
    "duration_seconds",
    "duration_human",
    "pair",
    "run_end_reason",
    "run_end_detail",
    "run_end_time",
    "starting_equity",
    "ending_equity",
    "session_pnl",
    "session_pnl_pct",
    "total_pnl",
    "total_pnl_pct",
    "trades_total",
    "wins",
    "losses",
    "win_rate_pct",
    "max_drawdown_usdt",
    "max_drawdown_pct",
    "signals_total",
    "entries_total",
    "liquidity_rejects",
    "liquidity_reject_rate_pct",
    "slippage_avg_abs_bps",
    "slippage_max_abs_bps",
    "strategy_regime_attribution_pct",
    "strategy_regime_unknown_trades",
    "strategy_switches_total",
    "strategy_gates_total",
    "strategy_cooldown_events",
    "directional_filter_shadow_blocks",
    "directional_filter_active_blocks",
    "reconciliation_checks_total",
    "reconciliation_checks_fail",
    "reconciliation_large_delta_warnings",
    "reconciliation_large_unexplained_warnings",
    "candle_shortfall_events",
    "candle_shortfall_missing_total",
    "data_quality_checks_total",
    "data_quality_checks_fail",
    "data_quality_checks_warn",
    "alerts_total",
    "errors_total",
    "version",
    "git_sha",
    "report_folder",
    "report_root",
    "report_created_at",
]
VARIANT_NAME_RE = re.compile(r"^(analysis|manual)([_-].*)?$", re.IGNORECASE)


def _strip_non_ascii(text):
    if not text:
        return ""
    return "".join(ch for ch in text if ord(ch) < 128).strip()


def _parse_ts(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S,%f")
    except ValueError:
        return None


def _find_latest_log(log_dir):
    candidates = []
    if log_dir.exists():
        candidates.extend(list(log_dir.glob("log_*.log")))
        v1_dir = log_dir / "v1"
        if v1_dir.exists():
            candidates.extend(list(v1_dir.rglob("log_*.log")))
    if not candidates:
        return None
    candidates = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _load_env_file(path):
    values = {}
    if not path or not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
    return values


def _redact_config(values):
    redacted = {}
    for key, value in values.items():
        key_upper = key.upper()
        if any(token in key_upper for token in ("KEY", "SECRET", "PASSPHRASE", "TOKEN")):
            redacted[key] = "[REDACTED]"
        else:
            redacted[key] = value
    return redacted


def _git_sha(repo_root):
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _git_commits_since(repo_root, base_sha, max_count=100):
    base = str(base_sha or "").strip()
    if not base:
        return []
    try:
        result = subprocess.run(
            [
                "git",
                "log",
                f"{base}..HEAD",
                "--date=iso-strict",
                "--pretty=format:%h|%ad|%s",
                f"--max-count={int(max_count)}",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []
    commits = []
    for raw in (result.stdout or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        commits.append(
            {
                "sha": parts[0].strip(),
                "date": parts[1].strip(),
                "subject": parts[2].strip(),
            }
        )
    return commits


def _read_version(repo_root):
    version_path = repo_root / "VERSION"
    if version_path.exists():
        return version_path.read_text(encoding="utf-8").strip()
    return ""

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


def _report_root(repo_root):
    return repo_root / "Reports" / "v1"


def _next_run_sequence(report_root):
    if not report_root.exists():
        return 1
    max_seq = 0
    for entry in report_root.iterdir():
        if not entry.is_dir():
            continue
        match = RUN_DIR_RE.match(entry.name)
        if not match:
            continue
        try:
            seq = int(match.group("seq"))
        except (TypeError, ValueError):
            continue
        if seq > max_seq:
            max_seq = seq
    return max_seq + 1


def _parse_run_sequence(run_dir):
    if not run_dir:
        return None
    match = RUN_DIR_RE.match(run_dir.name)
    if not match:
        return None
    try:
        return int(match.group("seq"))
    except (TypeError, ValueError):
        return None


def _run_info_from_log_path(log_path):
    if not log_path:
        return None, None
    try:
        log_path = Path(log_path).resolve()
    except Exception:
        return None, None
    run_dir = log_path.parent
    match = RUN_DIR_RE.match(run_dir.name)
    if not match:
        return None, None
    try:
        run_seq = int(match.group("seq"))
    except (TypeError, ValueError):
        run_seq = None
    run_id = run_dir.name.split("_", 2)[-1] if "_" in run_dir.name else ""
    return run_seq, run_id or None


def _find_run_dir(report_root, run_id):
    if not run_id:
        return None
    candidate = report_root / f"run_*_{run_id}"
    matches = list(report_root.glob(candidate.name))
    if matches:
        return matches[0]
    return None


def _find_parent_run_dir(path, report_root):
    try:
        path = path.resolve()
        report_root = report_root.resolve()
    except Exception:
        return None
    for parent in [path] + list(path.parents):
        if parent == report_root:
            break
        if RUN_DIR_RE.match(parent.name) and report_root in parent.parents:
            return parent
    return None


def _is_variant_name(name):
    if not name:
        return False
    return VARIANT_NAME_RE.match(name.strip()) is not None


def _resolve_output_dir(repo_root, run_id, output_arg):
    report_root = _report_root(repo_root)
    report_version = "v1"
    if not output_arg:
        run_sequence = _next_run_sequence(report_root)
        run_folder = f"run_{run_sequence:02d}_{run_id}"
        return report_root / run_folder, run_sequence, report_version

    output_dir = Path(output_arg)
    if not output_dir.is_absolute():
        output_dir = (repo_root / output_dir).resolve()

    parent_run_dir = _find_parent_run_dir(output_dir, report_root)
    if parent_run_dir:
        run_sequence = _parse_run_sequence(parent_run_dir)
        return output_dir, run_sequence, report_version

    if _is_variant_name(output_dir.name):
        run_dir = _find_run_dir(report_root, run_id)
        if run_dir is None:
            run_sequence = _next_run_sequence(report_root)
            run_dir = report_root / f"run_{run_sequence:02d}_{run_id}"
        else:
            run_sequence = _parse_run_sequence(run_dir)
        output_dir = run_dir / "variants" / output_dir.name
        return output_dir, run_sequence, report_version

    return output_dir, None, report_version


def _write_csv(path, rows, fieldnames, write_header_if_empty=False):
    if not rows and not write_header_if_empty:
        return
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows or []:
            writer.writerow(row)


def _safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _collect_report_summaries(report_root):
    summaries = []
    if not report_root.exists():
        return summaries
    for entry in report_root.iterdir():
        if not entry.is_dir():
            continue
        if not RUN_DIR_RE.match(entry.name):
            continue
        summary_path = entry / "summary.json"
        if not summary_path.exists():
            continue
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict):
            summaries.append(data)
    return summaries


def _sort_summaries(summaries):
    def _key(item):
        seq = item.get("run_sequence")
        if isinstance(seq, int):
            return (0, seq)
        if isinstance(seq, str) and seq.isdigit():
            return (0, int(seq))
        start = item.get("start_time") or ""
        return (1, start)

    return sorted(summaries, key=_key)


def _write_report_index(report_root):
    summaries = _collect_report_summaries(report_root)
    summaries = _sort_summaries(summaries)
    rows = []
    for summary in summaries:
        row = {}
        duration_seconds = summary.get("duration_seconds")
        row["duration_human"] = _format_duration(duration_seconds)
        for field in INDEX_FIELDS:
            if field == "duration_human":
                continue
            row[field] = summary.get(field)
        row["duration_human"] = row.get("duration_human")
        rows.append(row)

    index_payload = {
        "report_version": "v1",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "run_count": len(rows),
        "runs": rows,
    }

    index_json = report_root / "index.json"
    index_csv = report_root / "index.csv"
    index_json.write_text(json.dumps(index_payload, indent=2), encoding="utf-8")
    _write_csv(index_csv, rows, INDEX_FIELDS, write_header_if_empty=True)


def _build_run_comparison(report_root, current_summary):
    summaries = _collect_report_summaries(report_root)
    summaries = _sort_summaries(summaries)
    if not summaries:
        return {}

    current_run_id = current_summary.get("run_id")
    current_seq = current_summary.get("run_sequence")
    prev_summary = None

    if isinstance(current_seq, int):
        candidates = [
            item
            for item in summaries
            if isinstance(item.get("run_sequence"), int) and item.get("run_sequence") < current_seq
        ]
        if candidates:
            prev_summary = max(candidates, key=lambda item: item.get("run_sequence", 0))
    if prev_summary is None:
        for item in reversed(summaries):
            if item.get("run_id") and item.get("run_id") != current_run_id:
                prev_summary = item
                break

    if prev_summary is None:
        return {}

    metrics = [
        ("session_pnl", "session_pnl"),
        ("session_pnl_pct", "session_pnl_pct"),
        ("total_pnl", "total_pnl"),
        ("total_pnl_pct", "total_pnl_pct"),
        ("trades_total", "trades_total"),
        ("win_rate_pct", "win_rate_pct"),
        ("max_drawdown_usdt", "max_drawdown_usdt"),
        ("signals_total", "signals_total"),
        ("entries_total", "entries_total"),
        ("liquidity_reject_rate_pct", "liquidity_reject_rate_pct"),
        ("slippage_avg_abs_bps", "slippage_avg_abs_bps"),
        ("duration_seconds", "duration_seconds"),
    ]

    deltas = []
    for label, key in metrics:
        curr_val = current_summary.get(key)
        prev_val = prev_summary.get(key)
        curr_num = _safe_float(curr_val)
        prev_num = _safe_float(prev_val)
        delta = None
        if curr_num is not None and prev_num is not None:
            delta = round(curr_num - prev_num, 4)
        deltas.append(
            {
                "metric": label,
                "current": curr_val,
                "previous": prev_val,
                "delta": delta,
            }
        )

    return {
        "previous_run_sequence": prev_summary.get("run_sequence"),
        "previous_run_id": prev_summary.get("run_id"),
        "metrics": deltas,
    }


def generate_report(log_path, output_dir, env_path=None, run_id=None, run_sequence=None, report_version="v1"):
    log_path = Path(log_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    existing_summary = {}
    existing_summary_path = output_dir / "summary.json"
    if existing_summary_path.exists():
        try:
            loaded_existing = json.loads(existing_summary_path.read_text(encoding="utf-8"))
            if isinstance(loaded_existing, dict):
                existing_summary = loaded_existing
        except Exception:
            existing_summary = {}
    env_values = _load_env_file(env_path) if env_path else {}
    ratio_env = env_values.get("STATBOT_MIN_LIQUIDITY_RATIO") or env_values.get("STATBOT_LIQUIDITY_MIN_RATIO") or ""
    min_liquidity_ratio = _safe_float(ratio_env) if ratio_env else 0.0
    ratio_threshold = min_liquidity_ratio if min_liquidity_ratio and min_liquidity_ratio > 0 else 1.0

    equity_curve = []
    trades = []
    alerts = []
    liquidity_checks = []
    entry_slippage = []
    data_quality_checks = []
    reconciliation_checks = []
    reconciliation_pending = []
    strategy_switches = []
    strategy_gates = []
    strategy_close_pending = []
    open_positions = []
    pending_trade_context = None
    entry_order_map = {}
    pairs_seen = []
    pair_stats = {}
    pair_switch_reasons = {}
    pair_switches = 0
    pair_switch_blocked = 0
    hospital_moves = 0
    graveyard_moves = 0
    hospital_prioritized = 0
    strategy_refreshes = 0
    idle_timeouts = 0
    pnl_fallback_count = 0
    pnl_fallback_cleared = 0
    pnl_fallback_active = False
    pnl_fallback_start = None
    pnl_fallback_seconds = 0.0
    pnl_fallback_basis_counts = {}
    liquidity_fallback_attempts = 0
    liquidity_fallback_ratios = []
    liquidity_attempts = 0
    liquidity_attempt_ratios = []
    liquidity_downsizes = 0
    entry_liquidity_min_ratios = []
    entries_with_fallback_liquidity = 0
    last_liquidity_min_ratio = None
    orderbook_backoff_events = 0
    orderbook_backoff_active = 0
    orderbook_mid_failures = 0
    orderbook_backoff_reasons = {}
    candle_shortfall_events = 0
    candle_shortfall_missing_total = 0
    recon_large_delta_warnings = 0
    recon_large_unexplained_warnings = 0
    strategy_cooldown_events = 0
    directional_filter_shadow_blocks = 0
    directional_filter_active_blocks = 0
    active_pair = None

    start_ts = None
    end_ts = None
    pair = None
    starting_equity = None
    last_equity = None
    last_session = None
    last_session_pct = None
    last_total_pnl = None
    last_total_pnl_pct = None
    td_mode = None
    pos_mode = None
    liquidity_high = 0
    liquidity_low = 0
    liquidity_unknown = 0
    signals_total = 0
    entries_total = 0
    liquidity_rejects = 0
    long_ratios = []
    short_ratios = []
    run_end_reason = None
    run_end_detail = None
    run_end_time = None

    def _track_pair(pair_value):
        nonlocal active_pair
        if not pair_value:
            return
        active_pair = pair_value
        if pair_value not in pairs_seen:
            pairs_seen.append(pair_value)

    def _pair_stats_entry(pair_value):
        if not pair_value:
            pair_value = "unknown"
        entry = pair_stats.get(pair_value)
        if entry is None:
            entry = {
                "pair": pair_value,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "pnl_usdt": 0.0,
                "pnl_win_usdt": 0.0,
                "pnl_loss_usdt": 0.0,
                "pnl_pct": 0.0,
                "hold_minutes": [],
            }
            pair_stats[pair_value] = entry
        return entry

    with open(log_path, "r", encoding="utf-8", errors="ignore") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            match = LOG_LINE_RE.match(line)
            if not match:
                continue
            ts = _parse_ts(match.group("ts"))
            level = match.group("level")
            msg = match.group("msg")
            clean_msg = _strip_non_ascii(msg)

            if ts and start_ts is None:
                start_ts = ts
            if ts:
                end_ts = ts

            tmatch = TICKER_CONFIG_RE.search(clean_msg)
            if tmatch:
                pair_value = f"{tmatch.group('t1')}/{tmatch.group('t2')}"
                if not pair:
                    pair = pair_value
                _track_pair(pair_value)

            pair_match = CURRENT_PAIR_RE.search(clean_msg)
            if pair_match:
                _track_pair(f"{pair_match.group('t1')}/{pair_match.group('t2')}")

            hospital_match = HOSPITAL_PRIORITY_RE.search(clean_msg)
            if hospital_match:
                hospital_prioritized += 1
                _track_pair(f"{hospital_match.group('t1')}/{hospital_match.group('t2')}")

            switch_match = PAIR_SWITCH_RE.search(clean_msg)
            if switch_match:
                pair_switches += 1
                reason = switch_match.group("reason")
                pair_switch_reasons[reason] = pair_switch_reasons.get(reason, 0) + 1

            if PAIR_SWITCH_BLOCKED_RE.search(clean_msg):
                pair_switch_blocked += 1

            if "Pair idle timeout reached" in clean_msg:
                idle_timeouts += 1

            if STRATEGY_REFRESH_RE.search(clean_msg):
                strategy_refreshes += 1

            moved_hospital_match = PAIR_MOVED_HOSPITAL_RE.search(clean_msg)
            if moved_hospital_match:
                hospital_moves += 1

            moved_graveyard_match = PAIR_MOVED_GRAVEYARD_RE.search(clean_msg)
            if moved_graveyard_match:
                graveyard_moves += 1

            if starting_equity is None:
                smatch = START_EQUITY_RE.search(clean_msg)
                if smatch:
                    starting_equity = _safe_float(smatch.group("eq"))

            bmatch = BALANCE_SNAPSHOT_RE.search(clean_msg)
            if bmatch:
                td_mode = bmatch.group("td_mode")
                pos_mode = bmatch.group("pos_mode")

            pmatch = PNL_LINE_RE.search(clean_msg)
            if pmatch and ts:
                pnl = _safe_float(pmatch.group("pnl"))
                pnl_pct = _safe_float(pmatch.group("pnl_pct"))
                equity = _safe_float(pmatch.group("equity"))
                session = _safe_float(pmatch.group("session"))
                session_pct = _safe_float(pmatch.group("session_pct"))

                last_total_pnl = pnl
                last_total_pnl_pct = pnl_pct
                last_equity = equity
                last_session = session
                last_session_pct = session_pct

                equity_curve.append(
                    {
                        "timestamp": ts.isoformat(),
                        "equity_usdt": equity,
                        "session_pnl_usdt": session,
                        "session_pnl_pct": session_pct,
                        "total_pnl_usdt": pnl,
                        "total_pnl_pct": pnl_pct,
                    }
                )

            shortfall_match = CANDLE_SHORTFALL_RE.search(clean_msg)
            if shortfall_match:
                got = int(shortfall_match.group("got"))
                expected = int(shortfall_match.group("expected"))
                candle_shortfall_events += 1
                if expected > got:
                    candle_shortfall_missing_total += (expected - got)

            recon_post_match = RECON_POST_RE.search(clean_msg)
            if recon_post_match and ts:
                reconciliation_pending.append(
                    {
                        "timestamp": ts.isoformat(),
                        "linked_trade_ts": "",
                        "pair": active_pair or pair or "unknown",
                        "entry_strategy": "UNKNOWN",
                        "entry_regime": "UNKNOWN",
                        "result": "",
                        "trade_pnl_estimate": _safe_float(recon_post_match.group("trade_pnl")),
                        "equity_change_realized": _safe_float(recon_post_match.group("equity_change")),
                        "diff": _safe_float(recon_post_match.group("diff")),
                        "fees": _safe_float(recon_post_match.group("fees")),
                        "slippage": _safe_float(recon_post_match.group("slippage")),
                        "funding": _safe_float(recon_post_match.group("funding")),
                        "unexplained": _safe_float(recon_post_match.group("unexplained")),
                        "large_delta_warning": 0,
                        "large_unexplained_warning": 0,
                        "unexplained_pct_warning": None,
                    }
                )

            recon_delta_match = RECON_LARGE_DELTA_RE.search(clean_msg)
            if recon_delta_match:
                recon_large_delta_warnings += 1
                if reconciliation_pending:
                    pending = reconciliation_pending[-1]
                    pending["large_delta_warning"] = 1
                    parsed_diff = _safe_float(recon_delta_match.group("diff"))
                    if parsed_diff is not None:
                        pending["diff"] = parsed_diff

            recon_unexpl_match = RECON_LARGE_UNEXPLAINED_RE.search(clean_msg)
            if recon_unexpl_match:
                recon_large_unexplained_warnings += 1
                if reconciliation_pending:
                    pending = reconciliation_pending[-1]
                    pending["large_unexplained_warning"] = 1
                    pending["unexplained"] = _safe_float(recon_unexpl_match.group("unexplained"))
                    pending["unexplained_pct_warning"] = _safe_float(recon_unexpl_match.group("pct"))

            strategy_change_match = STRATEGY_CHANGE_RE.search(clean_msg)
            if strategy_change_match and ts:
                strategy_switches.append(
                    {
                        "timestamp": ts.isoformat(),
                        "from_strategy": strategy_change_match.group("from"),
                        "to_strategy": strategy_change_match.group("to"),
                        "reason": strategy_change_match.group("reason"),
                        "in_position": int(strategy_change_match.group("in_position")),
                    }
                )

            strategy_gate_match = STRATEGY_GATE_ENFORCED_RE.search(clean_msg)
            if strategy_gate_match and ts:
                strategy_gates.append(
                    {
                        "timestamp": ts.isoformat(),
                        "gate_type": "policy_gate",
                        "strategy": strategy_gate_match.group("strategy"),
                        "mode": "active",
                        "allow_new": 0,
                        "reason": strategy_gate_match.group("reason"),
                        "details": f"action={strategy_gate_match.group('action')}",
                    }
                )

            coint_gate_match = COINT_GATE_RE.search(clean_msg)
            if coint_gate_match and ts:
                strategy_gates.append(
                    {
                        "timestamp": ts.isoformat(),
                        "gate_type": "coint_gate",
                        "strategy": coint_gate_match.group("strategy"),
                        "mode": str(coint_gate_match.group("mode") or "").lower(),
                        "allow_new": int(coint_gate_match.group("allow_new")),
                        "reason": "coint_gate",
                        "details": f"coint_flag={coint_gate_match.group('coint_flag')}",
                    }
                )

            mean_shift_gate_match = MEAN_SHIFT_GATE_RE.search(clean_msg)
            if mean_shift_gate_match and ts:
                strategy_gates.append(
                    {
                        "timestamp": ts.isoformat(),
                        "gate_type": "mean_shift_gate",
                        "strategy": mean_shift_gate_match.group("strategy"),
                        "mode": str(mean_shift_gate_match.group("mode") or "").lower(),
                        "allow_new": int(mean_shift_gate_match.group("allow_new")),
                        "reason": "mean_shift_gate",
                        "details": (
                            f"shift_z={mean_shift_gate_match.group('shift_z')} "
                            f"threshold={mean_shift_gate_match.group('threshold')} "
                            f"basis={mean_shift_gate_match.group('basis')}"
                        ),
                    }
                )

            cooldown_on_match = STRATEGY_COOLDOWN_ON_RE.search(clean_msg)
            if cooldown_on_match and ts:
                strategy_cooldown_events += 1
                strategy_gates.append(
                    {
                        "timestamp": ts.isoformat(),
                        "gate_type": "strategy_cooldown_on",
                        "strategy": cooldown_on_match.group("strategy"),
                        "mode": "active",
                        "allow_new": 0,
                        "reason": cooldown_on_match.group("reason"),
                        "details": f"until_ts={cooldown_on_match.group('until_ts')}",
                    }
                )

            cooldown_off_match = STRATEGY_COOLDOWN_OFF_RE.search(clean_msg)
            if cooldown_off_match and ts:
                strategy_gates.append(
                    {
                        "timestamp": ts.isoformat(),
                        "gate_type": "strategy_cooldown_off",
                        "strategy": cooldown_off_match.group("strategy"),
                        "mode": "active",
                        "allow_new": 1,
                        "reason": "cooldown_cleared",
                        "details": "",
                    }
                )

            directional_shadow_match = DIRECTIONAL_FILTER_SHADOW_RE.search(clean_msg)
            if directional_shadow_match and ts:
                allow_new_val = int(directional_shadow_match.group("allow_new"))
                if allow_new_val == 0:
                    directional_filter_shadow_blocks += 1
                strategy_gates.append(
                    {
                        "timestamp": ts.isoformat(),
                        "gate_type": "directional_filter_shadow",
                        "strategy": directional_shadow_match.group("strategy"),
                        "mode": "shadow",
                        "allow_new": allow_new_val,
                        "reason": directional_shadow_match.group("reason"),
                        "details": "",
                    }
                )

            directional_active_match = DIRECTIONAL_FILTER_ACTIVE_BLOCK_RE.search(clean_msg)
            if directional_active_match and ts:
                directional_filter_active_blocks += 1
                strategy_gates.append(
                    {
                        "timestamp": ts.isoformat(),
                        "gate_type": "directional_filter_active_block",
                        "strategy": directional_active_match.group("strategy"),
                        "mode": "active",
                        "allow_new": 0,
                        "reason": directional_active_match.group("reason"),
                        "details": "",
                    }
                )

            strategy_close_match = STRATEGY_TRADE_CLOSE_RE.search(clean_msg)
            if strategy_close_match and ts:
                hold_value = _safe_float(strategy_close_match.group("hold_min"))
                strategy_close_pending.append(
                    {
                        "timestamp": ts.isoformat(),
                        "strategy": strategy_close_match.group("strategy"),
                        "regime": strategy_close_match.group("regime"),
                        "result": strategy_close_match.group("result"),
                        "pnl_usdt": _safe_float(strategy_close_match.group("pnl")),
                        "hold_minutes": hold_value,
                        "exit_reason": strategy_close_match.group("exit_reason"),
                    }
                )

            open_match = POSITION_OPEN_RE.search(clean_msg)
            strategy_open_match = STRATEGY_TRADE_OPEN_RE.search(clean_msg)
            if strategy_open_match and ts:
                pending_trade_context = {
                    "strategy": strategy_open_match.group("strategy"),
                    "regime": strategy_open_match.group("regime"),
                    "entry_z": strategy_open_match.group("entry_z"),
                    "timestamp": ts,
                }

            if open_match and ts:
                entry_ctx = pending_trade_context or {}
                open_positions.append(
                    {
                        "timestamp": ts,
                        "entry_z": open_match.group("entry_z"),
                        "entry_strategy": entry_ctx.get("strategy"),
                        "entry_regime": entry_ctx.get("regime"),
                    }
                )
                pending_trade_context = None
                if last_liquidity_min_ratio is not None:
                    entry_liquidity_min_ratios.append(last_liquidity_min_ratio)
                    if last_liquidity_min_ratio < ratio_threshold:
                        entries_with_fallback_liquidity += 1
                    last_liquidity_min_ratio = None

            trade_match = TRADE_CLOSED_RE.search(clean_msg)
            if trade_match and ts:
                hold_minutes = None
                entry_z = None
                exit_reason = "unknown"
                close_ctx = strategy_close_pending.pop(0) if strategy_close_pending else None
                entry_strategy = (
                    str(trade_match.group("strategy") or "").strip().upper() if trade_match.group("strategy") else ""
                )
                entry_regime = (
                    str(trade_match.group("regime") or "").strip().upper() if trade_match.group("regime") else ""
                )
                if close_ctx is not None:
                    if not entry_strategy:
                        entry_strategy = str(close_ctx.get("strategy") or "").strip().upper()
                    if not entry_regime:
                        entry_regime = str(close_ctx.get("regime") or "").strip().upper()
                    hold_from_close = _safe_float(close_ctx.get("hold_minutes"))
                    if hold_from_close is not None:
                        hold_minutes = hold_from_close
                    exit_reason = str(close_ctx.get("exit_reason") or "unknown").strip().lower() or "unknown"
                if open_positions:
                    entry = open_positions.pop(0)
                    entry_z = entry.get("entry_z")
                    if not entry_strategy:
                        entry_strategy = str(entry.get("entry_strategy") or "").strip().upper()
                    if not entry_regime:
                        entry_regime = str(entry.get("entry_regime") or "").strip().upper()
                    delta = ts - entry.get("timestamp")
                    hold_minutes = round(delta.total_seconds() / 60, 2)
                if not entry_strategy:
                    entry_strategy = "UNKNOWN"
                if not entry_regime:
                    entry_regime = "UNKNOWN"
                pair_key = active_pair or pair or "unknown"
                trades.append(
                    {
                        "timestamp": ts.isoformat(),
                        "pair": pair_key,
                        "result": trade_match.group("result"),
                        "pnl_usdt": _safe_float(trade_match.group("pnl")),
                        "pnl_pct": _safe_float(trade_match.group("pnl_pct")),
                        "equity_usdt": _safe_float(trade_match.group("equity")),
                        "session_pnl_usdt": _safe_float(trade_match.group("session")),
                        "session_pnl_pct": _safe_float(trade_match.group("session_pct")),
                        "hold_minutes": hold_minutes,
                        "entry_z": entry_z,
                        "entry_strategy": entry_strategy,
                        "entry_regime": entry_regime,
                        "exit_reason": exit_reason,
                    }
                )
                stats_entry = _pair_stats_entry(pair_key)
                stats_entry["trades"] += 1
                pnl_val = _safe_float(trade_match.group("pnl")) or 0.0
                stats_entry["pnl_usdt"] += pnl_val
                pnl_pct_val = _safe_float(trade_match.group("pnl_pct")) or 0.0
                stats_entry["pnl_pct"] += pnl_pct_val
                if trade_match.group("result") == "WIN":
                    stats_entry["wins"] += 1
                    stats_entry["pnl_win_usdt"] += pnl_val
                elif trade_match.group("result") == "LOSS":
                    stats_entry["losses"] += 1
                    stats_entry["pnl_loss_usdt"] += pnl_val
                if hold_minutes is not None:
                    stats_entry["hold_minutes"].append(hold_minutes)

                if reconciliation_pending:
                    recon_row = reconciliation_pending.pop(0)
                    recon_row["linked_trade_ts"] = ts.isoformat()
                    recon_row["pair"] = pair_key
                    recon_row["entry_strategy"] = entry_strategy
                    recon_row["entry_regime"] = entry_regime
                    recon_row["result"] = trade_match.group("result")
                    diff_abs = abs(recon_row["diff"]) if recon_row["diff"] is not None else 0.0
                    unexpl_abs = abs(recon_row["unexplained"]) if recon_row["unexplained"] is not None else 0.0
                    pass_fail = (
                        recon_row.get("large_delta_warning", 0) == 0
                        and recon_row.get("large_unexplained_warning", 0) == 0
                        and diff_abs <= 0.10
                        and unexpl_abs <= 0.10
                    )
                    recon_row["pass_fail"] = "pass" if pass_fail else "fail"
                    reconciliation_checks.append(recon_row)

            if ENTRY_SIGNAL_RE.search(clean_msg):
                signals_total += 1
            if POSITION_OPENED_RE.search(clean_msg):
                entries_total += 1
            if LIQUIDITY_REJECT_RE.search(clean_msg):
                liquidity_rejects += 1

            entry_match = ENTRY_PLACED_RE.search(clean_msg)
            if entry_match and ts:
                ord_id = entry_match.group("ord_id")
                entry_order_map[ord_id] = {
                    "ticker": entry_match.group("ticker"),
                    "side": entry_match.group("side"),
                    "entry_price": _safe_float(entry_match.group("entry_price")),
                    "timestamp": ts.isoformat(),
                }

            fill_match = FILL_RE.search(clean_msg)
            if fill_match and ts:
                ord_id = fill_match.group("ord_id")
                avg_px = _safe_float(fill_match.group("avg_px"))
                entry_data = entry_order_map.pop(ord_id, None)
                if entry_data and avg_px is not None:
                    entry_price = entry_data.get("entry_price")
                    side = entry_data.get("side")
                    slippage_bps = None
                    abs_slippage_bps = None
                    if entry_price and entry_price > 0:
                        if side == "short":
                            slippage_bps = (entry_price - avg_px) / entry_price * 10000
                        else:
                            slippage_bps = (avg_px - entry_price) / entry_price * 10000
                        abs_slippage_bps = abs(slippage_bps)
                    entry_slippage.append(
                        {
                            "timestamp": ts.isoformat(),
                            "ticker": entry_data.get("ticker") or fill_match.group("ticker"),
                            "side": side,
                            "order_id": ord_id,
                            "entry_price": entry_price,
                            "fill_price": avg_px,
                            "slippage_bps": round(slippage_bps, 4) if slippage_bps is not None else None,
                            "abs_slippage_bps": round(abs_slippage_bps, 4) if abs_slippage_bps is not None else None,
                        }
                    )

            liq_match = LIQUIDITY_RE.search(clean_msg)
            if liq_match and ts:
                long_target = _safe_float(liq_match.group("long_target"))
                short_target = _safe_float(liq_match.group("short_target"))
                liquidity_long = _safe_float(liq_match.group("liquidity_long"))
                liquidity_short = _safe_float(liq_match.group("liquidity_short"))
                long_ratio = None
                short_ratio = None
                if (
                    liquidity_long is not None
                    and liquidity_long > 0
                    and long_target is not None
                    and long_target > 0
                ):
                    long_ratio = liquidity_long / long_target
                    long_ratios.append(long_ratio)
                if (
                    liquidity_short is not None
                    and liquidity_short > 0
                    and short_target is not None
                    and short_target > 0
                ):
                    short_ratio = liquidity_short / short_target
                    short_ratios.append(short_ratio)

                if long_ratio is None or short_ratio is None:
                    status = "unknown"
                    liquidity_unknown += 1
                elif long_ratio >= ratio_threshold and short_ratio >= ratio_threshold:
                    status = "high"
                    liquidity_high += 1
                else:
                    status = "low"
                    liquidity_low += 1

                liquidity_checks.append(
                    {
                        "timestamp": ts.isoformat(),
                        "long_target": long_target,
                        "short_target": short_target,
                        "liquidity_long": liquidity_long,
                        "liquidity_short": liquidity_short,
                        "long_ratio": round(long_ratio, 4) if long_ratio is not None else None,
                        "short_ratio": round(short_ratio, 4) if short_ratio is not None else None,
                        "status": status,
                    }
                )

            ratio_match = LIQUIDITY_RATIO_RE.search(clean_msg)
            if ratio_match:
                last_liquidity_min_ratio = _safe_float(ratio_match.group("min"))

            fallback_attempt_match = LIQUIDITY_FALLBACK_ATTEMPT_RE.search(clean_msg)
            if fallback_attempt_match:
                liquidity_fallback_attempts += 1
                ratio_val = _safe_float(fallback_attempt_match.group("ratio"))
                if ratio_val is not None:
                    liquidity_fallback_ratios.append(ratio_val)

            attempt_match = LIQUIDITY_ATTEMPT_RE.search(clean_msg)
            if attempt_match:
                liquidity_attempts += 1
                ratio_val = _safe_float(attempt_match.group("ratio"))
                if ratio_val is not None:
                    liquidity_attempt_ratios.append(ratio_val)

            if LIQUIDITY_DOWNSIZE_RE.search(clean_msg):
                liquidity_downsizes += 1

            pnl_fallback_match = PNL_FALLBACK_USED_RE.search(clean_msg)
            if pnl_fallback_match:
                pnl_fallback_count += 1
                basis = pnl_fallback_match.group("basis")
                pnl_fallback_basis_counts[basis] = pnl_fallback_basis_counts.get(basis, 0) + 1
                if ts and not pnl_fallback_active:
                    pnl_fallback_active = True
                    pnl_fallback_start = ts

            if PNL_FALLBACK_CLEARED_RE.search(clean_msg):
                pnl_fallback_cleared += 1
                if pnl_fallback_active and pnl_fallback_start and ts:
                    pnl_fallback_seconds += (ts - pnl_fallback_start).total_seconds()
                pnl_fallback_active = False
                pnl_fallback_start = None

            backoff_match = ORDERBOOK_BACKOFF_RE.search(clean_msg)
            if backoff_match:
                orderbook_backoff_events += 1
                reason = backoff_match.group("reason").strip()
                orderbook_backoff_reasons[reason] = orderbook_backoff_reasons.get(reason, 0) + 1

            if ORDERBOOK_BACKOFF_ACTIVE_RE.search(clean_msg):
                orderbook_backoff_active += 1

            if ORDERBOOK_MID_FAIL_RE.search(clean_msg):
                orderbook_mid_failures += 1

            if any(pat.search(clean_msg) for pat in ALERT_PATTERNS):
                alerts.append(f"{match.group('ts')} {level} {clean_msg}")

            run_end_match = RUN_END_RE.search(clean_msg)
            if run_end_match and ts:
                run_end_reason = run_end_match.group("reason")
                detail = (run_end_match.group("detail") or "").strip()
                if detail and " exit_code=" in detail:
                    detail = detail.split(" exit_code=", 1)[0].strip()
                run_end_detail = detail if detail else None
                run_end_time = ts.isoformat()

    if pnl_fallback_active and pnl_fallback_start and end_ts:
        pnl_fallback_seconds += (end_ts - pnl_fallback_start).total_seconds()

    for recon_row in reconciliation_pending:
        diff_abs = abs(recon_row["diff"]) if recon_row["diff"] is not None else 0.0
        unexpl_abs = abs(recon_row["unexplained"]) if recon_row["unexplained"] is not None else 0.0
        pass_fail = (
            recon_row.get("large_delta_warning", 0) == 0
            and recon_row.get("large_unexplained_warning", 0) == 0
            and diff_abs <= 0.10
            and unexpl_abs <= 0.10
        )
        recon_row["pass_fail"] = "pass" if pass_fail else "fail"
        reconciliation_checks.append(recon_row)

    duration_seconds = None
    if start_ts and end_ts:
        duration_seconds = int((end_ts - start_ts).total_seconds())

    ending_equity = last_equity
    session_pnl = last_session
    session_pct = last_session_pct
    total_pnl = last_total_pnl
    total_pnl_pct = last_total_pnl_pct

    if ending_equity is None and trades:
        ending_equity = trades[-1].get("equity_usdt")
    session_pnl_source = None
    equity_session_pnl = None
    equity_session_pct = None
    if ending_equity is not None and starting_equity is not None:
        equity_session_pnl = ending_equity - starting_equity
        if starting_equity > 0:
            equity_session_pct = (equity_session_pnl / starting_equity) * 100

    if session_pnl is None and equity_session_pnl is not None:
        session_pnl = equity_session_pnl
        session_pct = equity_session_pct
        session_pnl_source = "equity"
    elif session_pnl is not None and equity_session_pnl is not None:
        if abs(session_pnl - equity_session_pnl) > 0.01:
            session_pnl = equity_session_pnl
            session_pct = equity_session_pct
            session_pnl_source = "equity_override"
        else:
            session_pnl_source = "log"

    max_drawdown = None
    max_drawdown_pct = None
    if equity_curve:
        peak = None
        max_dd = 0.0
        max_dd_pct = 0.0
        for row in equity_curve:
            equity = row.get("equity_usdt")
            if equity is None:
                continue
            if peak is None or equity > peak:
                peak = equity
            if peak is not None:
                dd = peak - equity
                if dd > max_dd:
                    max_dd = dd
                    if peak > 0:
                        max_dd_pct = (dd / peak) * 100
        max_drawdown = round(max_dd, 4)
        max_drawdown_pct = round(max_dd_pct, 4)

    wins = sum(1 for t in trades if t.get("result") == "WIN")
    losses = sum(1 for t in trades if t.get("result") == "LOSS")
    trade_count = wins + losses
    win_rate = round((wins / trade_count) * 100, 2) if trade_count else None
    avg_trade_pnl = None
    avg_hold = None
    trade_pnls = [t.get("pnl_usdt") for t in trades if t.get("pnl_usdt") is not None]
    hold_times = [t.get("hold_minutes") for t in trades if t.get("hold_minutes") is not None]
    if trade_pnls:
        avg_trade_pnl = round(sum(trade_pnls) / len(trade_pnls), 4)
    if hold_times:
        avg_hold = round(sum(hold_times) / len(hold_times), 2)

    pair_rows = []
    for pair_key, stats in pair_stats.items():
        trades_total = stats.get("trades", 0)
        wins_total = stats.get("wins", 0)
        losses_total = stats.get("losses", 0)
        win_rate_pair = round((wins_total / trades_total) * 100, 2) if trades_total else None
        pnl_usdt = round(stats.get("pnl_usdt", 0.0), 4)
        pnl_pct = round(stats.get("pnl_pct", 0.0), 4) if trades_total else None
        hold_vals = stats.get("hold_minutes") or []
        avg_hold_pair = round(sum(hold_vals) / len(hold_vals), 2) if hold_vals else None
        avg_pnl_pair = round(pnl_usdt / trades_total, 4) if trades_total else None
        pair_rows.append(
            {
                "pair": pair_key,
                "trades": trades_total,
                "wins": wins_total,
                "losses": losses_total,
                "win_rate_pct": win_rate_pair,
                "pnl_usdt": pnl_usdt,
                "pnl_win_usdt": round(stats.get("pnl_win_usdt", 0.0), 4),
                "pnl_loss_usdt": round(stats.get("pnl_loss_usdt", 0.0), 4),
                "avg_pnl_usdt": avg_pnl_pair,
                "avg_hold_minutes": avg_hold_pair,
                "pnl_pct_sum": pnl_pct,
            }
        )
    pair_rows.sort(key=lambda row: row.get("trades", 0), reverse=True)

    strategy_regime_stats = {}
    for trade in trades:
        strategy_key = str(trade.get("entry_strategy") or "UNKNOWN").strip().upper() or "UNKNOWN"
        regime_key = str(trade.get("entry_regime") or "UNKNOWN").strip().upper() or "UNKNOWN"
        key = (strategy_key, regime_key)
        if key not in strategy_regime_stats:
            strategy_regime_stats[key] = {
                "entry_strategy": strategy_key,
                "entry_regime": regime_key,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "pnl_usdt": 0.0,
                "hold_minutes": [],
            }
        cell = strategy_regime_stats[key]
        cell["trades"] += 1
        result = str(trade.get("result") or "").strip().upper()
        if result == "WIN":
            cell["wins"] += 1
        elif result == "LOSS":
            cell["losses"] += 1
        pnl_val = _safe_float(trade.get("pnl_usdt"))
        if pnl_val is not None:
            cell["pnl_usdt"] += pnl_val
        hold_val = _safe_float(trade.get("hold_minutes"))
        if hold_val is not None:
            cell["hold_minutes"].append(hold_val)

    strategy_regime_rows = []
    for _, cell in strategy_regime_stats.items():
        trades_total = int(cell.get("trades", 0) or 0)
        pnl_total = float(cell.get("pnl_usdt", 0.0) or 0.0)
        holds = cell.get("hold_minutes") or []
        avg_pnl = round(pnl_total / trades_total, 4) if trades_total > 0 else None
        avg_hold = round(sum(holds) / len(holds), 2) if holds else None
        win_rate = round((cell.get("wins", 0) / trades_total) * 100, 2) if trades_total > 0 else None
        strategy_regime_rows.append(
            {
                "entry_strategy": cell.get("entry_strategy"),
                "entry_regime": cell.get("entry_regime"),
                "trades": trades_total,
                "wins": int(cell.get("wins", 0) or 0),
                "losses": int(cell.get("losses", 0) or 0),
                "win_rate_pct": win_rate,
                "pnl_usdt": round(pnl_total, 4),
                "avg_pnl_usdt": avg_pnl,
                "avg_hold_minutes": avg_hold,
            }
        )
    strategy_regime_rows.sort(
        key=lambda row: (row.get("trades", 0), row.get("pnl_usdt", 0.0)),
        reverse=True,
    )

    strategy_perf_stats = {}
    for trade in trades:
        strategy_key = str(trade.get("entry_strategy") or "UNKNOWN").strip().upper() or "UNKNOWN"
        if strategy_key not in strategy_perf_stats:
            strategy_perf_stats[strategy_key] = {
                "strategy": strategy_key,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "pnl_usdt": 0.0,
                "hold_minutes": [],
                "exit_reasons": {},
            }
        row = strategy_perf_stats[strategy_key]
        row["trades"] += 1
        result = str(trade.get("result") or "").strip().upper()
        if result == "WIN":
            row["wins"] += 1
        elif result == "LOSS":
            row["losses"] += 1
        pnl_val = _safe_float(trade.get("pnl_usdt"))
        if pnl_val is not None:
            row["pnl_usdt"] += pnl_val
        hold_val = _safe_float(trade.get("hold_minutes"))
        if hold_val is not None:
            row["hold_minutes"].append(hold_val)
        reason = str(trade.get("exit_reason") or "unknown").strip().lower() or "unknown"
        reason_counts = row["exit_reasons"]
        reason_counts[reason] = int(reason_counts.get(reason, 0) or 0) + 1

    strategy_perf_rows = []
    for strategy_key, row in strategy_perf_stats.items():
        trades_total = int(row.get("trades", 0) or 0)
        wins_total = int(row.get("wins", 0) or 0)
        losses_total = int(row.get("losses", 0) or 0)
        pnl_total = float(row.get("pnl_usdt", 0.0) or 0.0)
        holds = row.get("hold_minutes") or []
        avg_hold = round(sum(holds) / len(holds), 2) if holds else None
        avg_pnl = round(pnl_total / trades_total, 4) if trades_total > 0 else None
        win_rate = round((wins_total / trades_total) * 100, 2) if trades_total > 0 else None
        top_exit_reason = "unknown"
        if row.get("exit_reasons"):
            top_exit_reason = max(
                row["exit_reasons"].items(),
                key=lambda item: int(item[1]),
            )[0]
        strategy_perf_rows.append(
            {
                "strategy": strategy_key,
                "trades": trades_total,
                "wins": wins_total,
                "losses": losses_total,
                "win_rate_pct": win_rate,
                "pnl_usdt": round(pnl_total, 4),
                "avg_pnl_usdt": avg_pnl,
                "avg_hold_minutes": avg_hold,
                "top_exit_reason": top_exit_reason,
            }
        )
    strategy_perf_rows.sort(
        key=lambda row: (row.get("trades", 0), row.get("pnl_usdt", 0.0)),
        reverse=True,
    )

    strategy_trade_counts = {}
    strategy_pnl_usdt = {}
    strategy_win_rate_pct = {}
    for row in strategy_perf_rows:
        key = row.get("strategy")
        strategy_trade_counts[key] = int(row.get("trades", 0) or 0)
        strategy_pnl_usdt[key] = float(row.get("pnl_usdt", 0.0) or 0.0)
        strategy_win_rate_pct[key] = row.get("win_rate_pct")

    slippage_samples = len(entry_slippage)
    avg_slippage_bps = None
    avg_slippage_abs_bps = None
    max_slippage_abs_bps = None
    if entry_slippage:
        slippage_vals = [row.get("slippage_bps") for row in entry_slippage if row.get("slippage_bps") is not None]
        slippage_abs_vals = [
            row.get("abs_slippage_bps") for row in entry_slippage if row.get("abs_slippage_bps") is not None
        ]
        if slippage_vals:
            avg_slippage_bps = round(sum(slippage_vals) / len(slippage_vals), 4)
        if slippage_abs_vals:
            avg_slippage_abs_bps = round(sum(slippage_abs_vals) / len(slippage_abs_vals), 4)
            max_slippage_abs_bps = round(max(slippage_abs_vals), 4)

    liquidity_samples = len(liquidity_checks)
    liquidity_pct_low = None
    if liquidity_high + liquidity_low > 0:
        liquidity_pct_low = round((liquidity_low / (liquidity_high + liquidity_low)) * 100, 2)

    max_long_ratio = round(max(long_ratios), 4) if long_ratios else None
    max_short_ratio = round(max(short_ratios), 4) if short_ratios else None
    avg_long_ratio = round(sum(long_ratios) / len(long_ratios), 4) if long_ratios else None
    avg_short_ratio = round(sum(short_ratios) / len(short_ratios), 4) if short_ratios else None

    entry_liq_avg = None
    entry_liq_min = None
    if entry_liquidity_min_ratios:
        entry_liq_avg = round(sum(entry_liquidity_min_ratios) / len(entry_liquidity_min_ratios), 4)
        entry_liq_min = round(min(entry_liquidity_min_ratios), 4)

    pnl_fallback_pct_runtime = None
    if duration_seconds and duration_seconds > 0:
        pnl_fallback_pct_runtime = round((pnl_fallback_seconds / duration_seconds) * 100, 2)

    repo_root = Path(__file__).resolve().parents[1]
    version = _read_version(repo_root)
    git_sha = _git_sha(repo_root)
    previous_report_git_sha = str(existing_summary.get("git_sha") or "").strip()
    previous_report_created_at = existing_summary.get("report_created_at")
    post_run_fixes = []
    if previous_report_git_sha and git_sha and previous_report_git_sha != git_sha:
        post_run_fixes = _git_commits_since(repo_root, previous_report_git_sha, max_count=100)
    report_hardening_fixes = [
        "entry_slippage_materialized_when_empty",
        "total_pnl_semantics_clarified",
        "post_run_fixlog_commits_added",
    ]
    config_snapshot = _redact_config(env_values)

    liquidity_fallback_min_ratio = None
    liquidity_fallback_avg_ratio = None
    if liquidity_fallback_ratios:
        liquidity_fallback_min_ratio = round(min(liquidity_fallback_ratios), 4)
        liquidity_fallback_avg_ratio = round(sum(liquidity_fallback_ratios) / len(liquidity_fallback_ratios), 4)

    run_behavior = {
        "pair_switches": pair_switches,
        "pair_switch_reasons": pair_switch_reasons,
        "pair_switch_blocked": pair_switch_blocked,
        "idle_timeouts": idle_timeouts,
        "hospital_moves": hospital_moves,
        "graveyard_moves": graveyard_moves,
        "hospital_prioritized": hospital_prioritized,
        "strategy_refreshes": strategy_refreshes,
        "signals_to_entries_pct": round((entries_total / signals_total) * 100, 2) if signals_total else None,
        "entries_to_trades_pct": round((trade_count / entries_total) * 100, 2) if entries_total else None,
    }

    fallback_summary = {
        "pnl_fallback_used": pnl_fallback_count,
        "pnl_fallback_cleared": pnl_fallback_cleared,
        "pnl_fallback_seconds": round(pnl_fallback_seconds, 2),
        "pnl_fallback_pct_runtime": pnl_fallback_pct_runtime,
        "pnl_fallback_basis_counts": pnl_fallback_basis_counts,
        "liquidity_fallback_attempts": liquidity_fallback_attempts,
        "liquidity_fallback_min_ratio": liquidity_fallback_min_ratio,
        "liquidity_fallback_avg_ratio": liquidity_fallback_avg_ratio,
        "liquidity_downsizes": liquidity_downsizes,
        "entries_with_fallback_liquidity": entries_with_fallback_liquidity,
        "entry_liquidity_min_ratio_avg": entry_liq_avg,
        "entry_liquidity_min_ratio_min": entry_liq_min,
        "orderbook_backoff_events": orderbook_backoff_events,
        "orderbook_backoff_active": orderbook_backoff_active,
        "orderbook_midprice_failures": orderbook_mid_failures,
        "orderbook_backoff_reasons": orderbook_backoff_reasons,
    }

    strategy_regime_known_trades = sum(
        1
        for t in trades
        if str(t.get("entry_strategy") or "").strip().upper() not in ("", "UNKNOWN")
        and str(t.get("entry_regime") or "").strip().upper() not in ("", "UNKNOWN")
    )
    unknown_strategy_regime_trades = max(trade_count - strategy_regime_known_trades, 0)
    strategy_regime_attribution_pct = (
        round((strategy_regime_known_trades / trade_count) * 100, 2) if trade_count else None
    )

    recon_fail_count = sum(1 for row in reconciliation_checks if row.get("pass_fail") == "fail")
    recon_pass_count = sum(1 for row in reconciliation_checks if row.get("pass_fail") == "pass")
    recon_linked_count = sum(1 for row in reconciliation_checks if row.get("linked_trade_ts"))
    strategy_switches.sort(key=lambda row: row.get("timestamp") or "")
    strategy_gates.sort(key=lambda row: row.get("timestamp") or "")

    def _add_quality_check(check_name, severity, observed, expected, status, context=""):
        data_quality_checks.append(
            {
                "check_name": check_name,
                "severity": severity,
                "status": status,
                "observed": observed,
                "expected": expected,
                "context": context,
            }
        )

    _add_quality_check(
        "strategy_regime_attribution",
        "high",
        f"{strategy_regime_known_trades}/{trade_count}",
        "100% trade attribution",
        "pass" if unknown_strategy_regime_trades == 0 else "fail",
        f"attribution_pct={strategy_regime_attribution_pct}",
    )
    _add_quality_check(
        "reconciliation_large_delta_warnings",
        "high",
        recon_large_delta_warnings,
        "0",
        "pass" if recon_large_delta_warnings == 0 else "fail",
        "from post-close reconciliation warnings",
    )
    _add_quality_check(
        "reconciliation_large_unexplained_warnings",
        "high",
        recon_large_unexplained_warnings,
        "0",
        "pass" if recon_large_unexplained_warnings == 0 else "fail",
        "from post-close reconciliation warnings",
    )
    _add_quality_check(
        "reconciliation_rows_linked_to_trades",
        "medium",
        f"{recon_linked_count}/{len(reconciliation_checks)}",
        "all linked when available",
        "pass" if (len(reconciliation_checks) == 0 or recon_linked_count == len(reconciliation_checks)) else "warn",
        "older logs may miss linkage fields",
    )
    _add_quality_check(
        "orderbook_midprice_failures",
        "medium",
        orderbook_mid_failures,
        "0",
        "pass" if orderbook_mid_failures == 0 else "warn",
        "mid-price fallback pressure indicator",
    )
    _add_quality_check(
        "pnl_fallback_runtime_pct",
        "medium",
        pnl_fallback_pct_runtime,
        "<= 10%",
        "pass" if (pnl_fallback_pct_runtime is None or pnl_fallback_pct_runtime <= 10.0) else "warn",
        f"fallback_used={pnl_fallback_count}",
    )
    _add_quality_check(
        "candle_shortfall_events",
        "low",
        candle_shortfall_events,
        "0",
        "pass" if candle_shortfall_events == 0 else "warn",
        f"missing_total={candle_shortfall_missing_total}",
    )

    if run_id is None:
        run_id = start_ts.strftime("%Y%m%d_%H%M%S") if start_ts else datetime.now().strftime("%Y%m%d_%H%M%S")

    report_folder = output_dir.name
    report_root_path = str(output_dir)
    variant_of = None
    if output_dir.parent.name == "variants" and RUN_DIR_RE.match(output_dir.parent.parent.name):
        report_folder = f"variants/{output_dir.name}"
        variant_of = output_dir.parent.parent.name

    summary = {
        "report_version": report_version,
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "run_sequence": run_sequence,
        "run_id": run_id,
        "report_folder": report_folder,
        "report_root": report_root_path,
        "report_created_at": datetime.now(timezone.utc).isoformat(),
        "version": version or "",
        "git_sha": git_sha,
        "log_path": str(log_path),
        "start_time": start_ts.isoformat() if start_ts else "",
        "end_time": end_ts.isoformat() if end_ts else "",
        "duration_seconds": duration_seconds,
        "pair": pair or "",
        "pairs_seen": pairs_seen,
        "run_end_reason": run_end_reason,
        "run_end_detail": run_end_detail,
        "run_end_time": run_end_time,
        "td_mode": td_mode or "",
        "pos_mode": pos_mode or "",
        "starting_equity": starting_equity,
        "ending_equity": ending_equity,
        "session_pnl": session_pnl,
        "session_pnl_pct": session_pct,
        "session_pnl_source": session_pnl_source,
        "session_pnl_equity_delta": equity_session_pnl,
        "session_pnl_semantics": "Canonical run PnL based on session/equity delta.",
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "total_pnl_semantics": "Runtime live PnL snapshot from log PnL lines; not cumulative realized PnL.",
        "max_drawdown_usdt": max_drawdown,
        "max_drawdown_pct": max_drawdown_pct,
        "trades_total": trade_count,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": win_rate,
        "avg_trade_pnl_usdt": avg_trade_pnl,
        "avg_hold_minutes": avg_hold,
        "signals_total": signals_total,
        "entries_total": entries_total,
        "liquidity_rejects": liquidity_rejects,
        "liquidity_reject_rate_pct": round((liquidity_rejects / signals_total) * 100, 2)
        if signals_total
        else None,
        "alerts_total": len(alerts),
        "errors_total": sum(1 for line in alerts if "ERROR" in line),
        "liquidity_samples": liquidity_samples,
        "liquidity_high_samples": liquidity_high,
        "liquidity_low_samples": liquidity_low,
        "liquidity_unknown_samples": liquidity_unknown,
        "liquidity_low_pct": liquidity_pct_low,
        "liquidity_min_ratio": ratio_threshold,
        "liquidity_max_long_ratio": max_long_ratio,
        "liquidity_max_short_ratio": max_short_ratio,
        "liquidity_avg_long_ratio": avg_long_ratio,
        "liquidity_avg_short_ratio": avg_short_ratio,
        "slippage_samples": slippage_samples,
        "slippage_avg_bps": avg_slippage_bps,
        "slippage_avg_abs_bps": avg_slippage_abs_bps,
        "slippage_max_abs_bps": max_slippage_abs_bps,
        "entry_liquidity_min_ratio_avg": entry_liq_avg,
        "entry_liquidity_min_ratio_min": entry_liq_min,
        "entries_with_fallback_liquidity": entries_with_fallback_liquidity,
        "strategy_regime_cells": len(strategy_regime_rows),
        "strategy_regime_known_trades": strategy_regime_known_trades,
        "strategy_regime_unknown_trades": unknown_strategy_regime_trades,
        "strategy_regime_attribution_pct": strategy_regime_attribution_pct,
        "strategy_trade_counts": strategy_trade_counts,
        "strategy_pnl_usdt": strategy_pnl_usdt,
        "strategy_win_rate_pct": strategy_win_rate_pct,
        "strategy_switches_total": len(strategy_switches),
        "strategy_gates_total": len(strategy_gates),
        "strategy_cooldown_events": strategy_cooldown_events,
        "directional_filter_shadow_blocks": directional_filter_shadow_blocks,
        "directional_filter_active_blocks": directional_filter_active_blocks,
        "reconciliation_checks_total": len(reconciliation_checks),
        "reconciliation_checks_pass": recon_pass_count,
        "reconciliation_checks_fail": recon_fail_count,
        "reconciliation_large_delta_warnings": recon_large_delta_warnings,
        "reconciliation_large_unexplained_warnings": recon_large_unexplained_warnings,
        "candle_shortfall_events": candle_shortfall_events,
        "candle_shortfall_missing_total": candle_shortfall_missing_total,
        "data_quality_checks_total": len(data_quality_checks),
        "data_quality_checks_fail": sum(1 for row in data_quality_checks if row.get("status") == "fail"),
        "data_quality_checks_warn": sum(1 for row in data_quality_checks if row.get("status") == "warn"),
        "fallback_summary": fallback_summary,
        "run_behavior": run_behavior,
        "performance": {
            "session_pnl": session_pnl,
            "session_pnl_pct": session_pct,
            "total_pnl": total_pnl,
            "total_pnl_pct": total_pnl_pct,
            "total_pnl_semantics": "Runtime live snapshot (not cumulative realized).",
            "trades_total": trade_count,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": win_rate,
            "avg_trade_pnl_usdt": avg_trade_pnl,
            "avg_hold_minutes": avg_hold,
        },
        "risk": {
            "max_drawdown_usdt": max_drawdown,
            "max_drawdown_pct": max_drawdown_pct,
            "run_end_reason": run_end_reason,
            "run_end_detail": run_end_detail,
        },
        "execution_quality": {
            "signals_total": signals_total,
            "entries_total": entries_total,
            "liquidity_rejects": liquidity_rejects,
            "liquidity_reject_rate_pct": round((liquidity_rejects / signals_total) * 100, 2)
            if signals_total
            else None,
            "slippage_avg_abs_bps": avg_slippage_abs_bps,
            "slippage_max_abs_bps": max_slippage_abs_bps,
            "entry_liquidity_min_ratio_avg": entry_liq_avg,
            "entry_liquidity_min_ratio_min": entry_liq_min,
        },
        "data_quality": {
            "checks_total": len(data_quality_checks),
            "checks_fail": sum(1 for row in data_quality_checks if row.get("status") == "fail"),
            "checks_warn": sum(1 for row in data_quality_checks if row.get("status") == "warn"),
            "reconciliation_checks_total": len(reconciliation_checks),
            "reconciliation_checks_fail": recon_fail_count,
            "reconciliation_large_delta_warnings": recon_large_delta_warnings,
            "reconciliation_large_unexplained_warnings": recon_large_unexplained_warnings,
            "candle_shortfall_events": candle_shortfall_events,
            "orderbook_midprice_failures": orderbook_mid_failures,
        },
        "strategy_regime": {
            "cells": len(strategy_regime_rows),
            "known_trades": strategy_regime_known_trades,
            "unknown_trades": unknown_strategy_regime_trades,
            "attribution_pct": strategy_regime_attribution_pct,
            "trade_counts": strategy_trade_counts,
            "pnl_usdt": strategy_pnl_usdt,
            "win_rate_pct": strategy_win_rate_pct,
        },
        "strategy_observability": {
            "switches_total": len(strategy_switches),
            "gates_total": len(strategy_gates),
            "cooldown_events": strategy_cooldown_events,
            "directional_filter_shadow_blocks": directional_filter_shadow_blocks,
            "directional_filter_active_blocks": directional_filter_active_blocks,
        },
        "report_regenerated": bool(existing_summary),
        "previous_report_git_sha": previous_report_git_sha or None,
        "previous_report_created_at": previous_report_created_at or None,
        "post_run_fixes_count": len(post_run_fixes),
        "post_run_fixes": post_run_fixes,
        "report_hardening_fixes": report_hardening_fixes,
    }

    report_root = _report_root(repo_root)
    run_comparison = _build_run_comparison(report_root, summary)
    if run_comparison:
        summary["run_comparison"] = run_comparison

    summary_path = output_dir / "summary.json"
    summary_txt_path = output_dir / "summary.txt"
    equity_path = output_dir / "equity_curve.csv"
    trades_path = output_dir / "trades.csv"
    pair_perf_path = output_dir / "pair_performance.csv"
    strategy_regime_path = output_dir / "strategy_regime_scorecard.csv"
    strategy_perf_path = output_dir / "strategy_performance.csv"
    strategy_switches_path = output_dir / "strategy_switches.csv"
    strategy_gates_path = output_dir / "strategy_gates.csv"
    data_quality_path = output_dir / "data_quality_checks.csv"
    reconciliation_path = output_dir / "reconciliation_checks.csv"
    liquidity_path = output_dir / "liquidity_checks.csv"
    slippage_path = output_dir / "entry_slippage.csv"
    post_run_fixes_path = output_dir / "post_run_fixes.csv"
    alerts_path = output_dir / "alerts.txt"
    config_path = output_dir / "config_snapshot.json"
    manifest_path = output_dir / "report_manifest.json"

    summary["equity_curve_path"] = str(equity_path)
    summary["trades_path"] = str(trades_path)
    summary["pair_performance_path"] = str(pair_perf_path)
    summary["strategy_regime_scorecard_path"] = str(strategy_regime_path)
    summary["strategy_performance_path"] = str(strategy_perf_path)
    summary["strategy_switches_path"] = str(strategy_switches_path)
    summary["strategy_gates_path"] = str(strategy_gates_path)
    summary["data_quality_checks_path"] = str(data_quality_path)
    summary["reconciliation_checks_path"] = str(reconciliation_path)
    summary["liquidity_checks_path"] = str(liquidity_path)
    summary["entry_slippage_path"] = str(slippage_path)
    summary["post_run_fixes_path"] = str(post_run_fixes_path)
    summary["alerts_path"] = str(alerts_path)
    summary["config_snapshot_path"] = str(config_path)
    summary["report_manifest_path"] = str(manifest_path)
    summary["duration_human"] = _format_duration(duration_seconds)
    if variant_of:
        summary["variant_of"] = variant_of

    _write_csv(
        equity_path,
        equity_curve,
        ["timestamp", "equity_usdt", "session_pnl_usdt", "session_pnl_pct", "total_pnl_usdt", "total_pnl_pct"],
    )
    _write_csv(
        trades_path,
        trades,
        [
            "timestamp",
            "pair",
            "result",
            "pnl_usdt",
            "pnl_pct",
            "equity_usdt",
            "session_pnl_usdt",
            "session_pnl_pct",
            "hold_minutes",
            "entry_z",
            "entry_strategy",
            "entry_regime",
            "exit_reason",
        ],
    )
    _write_csv(
        pair_perf_path,
        pair_rows,
        [
            "pair",
            "trades",
            "wins",
            "losses",
            "win_rate_pct",
            "pnl_usdt",
            "pnl_win_usdt",
            "pnl_loss_usdt",
            "avg_pnl_usdt",
            "avg_hold_minutes",
            "pnl_pct_sum",
        ],
    )
    _write_csv(
        strategy_regime_path,
        strategy_regime_rows,
        [
            "entry_strategy",
            "entry_regime",
            "trades",
            "wins",
            "losses",
            "win_rate_pct",
            "pnl_usdt",
            "avg_pnl_usdt",
            "avg_hold_minutes",
        ],
        write_header_if_empty=True,
    )
    _write_csv(
        strategy_perf_path,
        strategy_perf_rows,
        [
            "strategy",
            "trades",
            "wins",
            "losses",
            "win_rate_pct",
            "pnl_usdt",
            "avg_pnl_usdt",
            "avg_hold_minutes",
            "top_exit_reason",
        ],
        write_header_if_empty=True,
    )
    _write_csv(
        strategy_switches_path,
        strategy_switches,
        [
            "timestamp",
            "from_strategy",
            "to_strategy",
            "reason",
            "in_position",
        ],
        write_header_if_empty=True,
    )
    _write_csv(
        strategy_gates_path,
        strategy_gates,
        [
            "timestamp",
            "gate_type",
            "strategy",
            "mode",
            "allow_new",
            "reason",
            "details",
        ],
        write_header_if_empty=True,
    )
    _write_csv(
        data_quality_path,
        data_quality_checks,
        [
            "check_name",
            "severity",
            "status",
            "observed",
            "expected",
            "context",
        ],
        write_header_if_empty=True,
    )
    _write_csv(
        reconciliation_path,
        reconciliation_checks,
        [
            "timestamp",
            "linked_trade_ts",
            "pair",
            "entry_strategy",
            "entry_regime",
            "result",
            "trade_pnl_estimate",
            "equity_change_realized",
            "diff",
            "fees",
            "slippage",
            "funding",
            "unexplained",
            "large_delta_warning",
            "large_unexplained_warning",
            "unexplained_pct_warning",
            "pass_fail",
        ],
        write_header_if_empty=True,
    )
    _write_csv(
        liquidity_path,
        liquidity_checks,
        [
            "timestamp",
            "long_target",
            "short_target",
            "liquidity_long",
            "liquidity_short",
            "long_ratio",
            "short_ratio",
            "status",
        ],
    )
    _write_csv(
        slippage_path,
        entry_slippage,
        [
            "timestamp",
            "ticker",
            "side",
            "order_id",
            "entry_price",
            "fill_price",
            "slippage_bps",
            "abs_slippage_bps",
        ],
        write_header_if_empty=True,
    )
    _write_csv(
        post_run_fixes_path,
        post_run_fixes,
        [
            "sha",
            "date",
            "subject",
        ],
        write_header_if_empty=True,
    )

    alerts_payload = "\n".join(alerts)
    if alerts_payload:
        alerts_payload += "\n"
    alerts_path.write_text(alerts_payload, encoding="utf-8")

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    config_path.write_text(json.dumps(config_snapshot, indent=2), encoding="utf-8")
    manifest = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_version": report_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "run_sequence": run_sequence,
        "git_sha": git_sha,
        "files": [
            {"name": summary_path.name, "path": str(summary_path), "format": "json", "rows": 1},
            {"name": summary_txt_path.name, "path": str(summary_txt_path), "format": "txt", "rows": None},
            {"name": config_path.name, "path": str(config_path), "format": "json", "rows": len(config_snapshot)},
            {"name": equity_path.name, "path": str(equity_path), "format": "csv", "rows": len(equity_curve)},
            {"name": trades_path.name, "path": str(trades_path), "format": "csv", "rows": len(trades)},
            {"name": pair_perf_path.name, "path": str(pair_perf_path), "format": "csv", "rows": len(pair_rows)},
            {
                "name": strategy_regime_path.name,
                "path": str(strategy_regime_path),
                "format": "csv",
                "rows": len(strategy_regime_rows),
            },
            {
                "name": strategy_perf_path.name,
                "path": str(strategy_perf_path),
                "format": "csv",
                "rows": len(strategy_perf_rows),
            },
            {
                "name": strategy_switches_path.name,
                "path": str(strategy_switches_path),
                "format": "csv",
                "rows": len(strategy_switches),
            },
            {
                "name": strategy_gates_path.name,
                "path": str(strategy_gates_path),
                "format": "csv",
                "rows": len(strategy_gates),
            },
            {"name": data_quality_path.name, "path": str(data_quality_path), "format": "csv", "rows": len(data_quality_checks)},
            {
                "name": reconciliation_path.name,
                "path": str(reconciliation_path),
                "format": "csv",
                "rows": len(reconciliation_checks),
            },
            {"name": liquidity_path.name, "path": str(liquidity_path), "format": "csv", "rows": len(liquidity_checks)},
            {"name": slippage_path.name, "path": str(slippage_path), "format": "csv", "rows": len(entry_slippage)},
            {"name": post_run_fixes_path.name, "path": str(post_run_fixes_path), "format": "csv", "rows": len(post_run_fixes)},
            {"name": alerts_path.name, "path": str(alerts_path), "format": "txt", "rows": len(alerts)},
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    switch_reason_parts = []
    for reason, count in sorted(pair_switch_reasons.items()):
        switch_reason_parts.append(f"{reason}={count}")
    switch_reason_line = ", ".join(switch_reason_parts) if switch_reason_parts else "n/a"

    backoff_reason_parts = []
    for reason, count in sorted(orderbook_backoff_reasons.items()):
        backoff_reason_parts.append(f"{reason}={count}")
    backoff_reason_line = ", ".join(backoff_reason_parts) if backoff_reason_parts else "n/a"

    comparison_lines = []
    if run_comparison:
        prev_seq = run_comparison.get("previous_run_sequence")
        prev_id = run_comparison.get("previous_run_id")
        comparison_lines.extend(
            [
                "RUN COMPARISON",
                f"Previous run: {prev_seq or 'n/a'} ({prev_id or 'n/a'})",
            ]
        )
        for item in run_comparison.get("metrics", []):
            metric = item.get("metric")
            curr_val = item.get("current")
            prev_val = item.get("previous")
            delta = item.get("delta")
            if delta is None:
                delta_str = "n/a"
            else:
                delta_str = f"{delta:+}"
            comparison_lines.append(f"{metric}: {curr_val} (prev {prev_val}, delta {delta_str})")

    post_run_fix_lines = []
    if post_run_fixes:
        post_run_fix_lines.extend(
            [
                "POST-RUN FIXES",
                f"Previous report git: {previous_report_git_sha or 'n/a'}",
                f"Current git: {git_sha or 'n/a'}",
                f"Fix commits since previous report: {len(post_run_fixes)}",
            ]
        )
        for item in post_run_fixes:
            post_run_fix_lines.append(
                f"- {item.get('sha')} | {item.get('date')} | {item.get('subject')}"
            )
    elif existing_summary:
        post_run_fix_lines.extend(
            [
                "POST-RUN FIXES",
                f"Previous report git: {previous_report_git_sha or 'n/a'}",
                f"Current git: {git_sha or 'n/a'}",
                "Fix commits since previous report: 0",
            ]
        )

    files_list = [
        summary_path.name,
        summary_txt_path.name,
        config_path.name,
    ]
    for path in [
        equity_path,
        trades_path,
        pair_perf_path,
        strategy_regime_path,
        strategy_perf_path,
        strategy_switches_path,
        strategy_gates_path,
        data_quality_path,
        reconciliation_path,
        liquidity_path,
        slippage_path,
        post_run_fixes_path,
        alerts_path,
        manifest_path,
    ]:
        if path.exists():
            files_list.append(path.name)

    summary_txt_path.write_text(
        "\n".join(
            [
                "REPORT OVERVIEW",
                f"Run: {summary['run_sequence'] or 'n/a'} ({summary['run_id']})",
                f"Version: {summary['version'] or 'n/a'} | Git: {summary['git_sha'] or 'n/a'}",
                f"Pair: {summary['pair'] or 'n/a'} | td_mode={summary['td_mode'] or 'n/a'} | pos_mode={summary['pos_mode'] or 'n/a'}",
                f"Pairs seen: {', '.join(summary.get('pairs_seen') or []) or 'n/a'}",
                f"Run end: {summary.get('run_end_reason') or 'n/a'}",
                f"Run end detail: {summary.get('run_end_detail') or 'n/a'}",
                f"Start: {summary['start_time'] or 'n/a'}",
                f"End: {summary['end_time'] or 'n/a'}",
                f"Duration: {_format_duration(summary['duration_seconds'])}",
                "",
                "PERFORMANCE",
                f"Starting equity: {summary['starting_equity']}",
                f"Ending equity: {summary['ending_equity']}",
                f"Session PnL: {summary['session_pnl']} ({summary['session_pnl_pct']}%)",
                f"Runtime Total PnL snapshot: {summary['total_pnl']} ({summary['total_pnl_pct']}%)",
                "Total PnL note: runtime live snapshot, not cumulative realized run PnL.",
                f"Max drawdown: {summary['max_drawdown_usdt']} ({summary['max_drawdown_pct']}%)",
                f"Trades: {summary['trades_total']} | Wins: {summary['wins']} | Losses: {summary['losses']} | Win rate: {summary['win_rate_pct']}",
                f"Avg trade PnL: {summary['avg_trade_pnl_usdt']} | Avg hold (min): {summary['avg_hold_minutes']}",
                f"Strategy/regime cells: {summary['strategy_regime_cells']} | Attributed trades: {summary['strategy_regime_known_trades']}",
                "",
                "STRATEGY OBSERVABILITY",
                f"Strategy trades: {summary['strategy_trade_counts']}",
                f"Strategy pnl: {summary['strategy_pnl_usdt']}",
                f"Strategy win rate: {summary['strategy_win_rate_pct']}",
                f"Strategy switches: {summary['strategy_switches_total']} | Gates: {summary['strategy_gates_total']}",
                f"Cooldown events: {summary['strategy_cooldown_events']} | Directional blocks (shadow/active): {summary['directional_filter_shadow_blocks']} / {summary['directional_filter_active_blocks']}",
                "",
                "EXECUTION QUALITY",
                f"Signals: {summary['signals_total']} | Entries: {summary['entries_total']}",
                f"Liquidity rejects: {summary['liquidity_rejects']} ({summary['liquidity_reject_rate_pct']}%)",
                f"Liquidity low pct: {summary['liquidity_low_pct']}",
                f"Liquidity ratio avg (long/short): {summary['liquidity_avg_long_ratio']} / {summary['liquidity_avg_short_ratio']}",
                f"Entry liquidity min ratio avg/min: {summary['entry_liquidity_min_ratio_avg']} / {summary['entry_liquidity_min_ratio_min']}",
                f"Entries with fallback liquidity: {summary['entries_with_fallback_liquidity']}",
                f"Slippage samples: {summary['slippage_samples']}",
                f"Slippage avg bps (signed/abs): {summary['slippage_avg_bps']} / {summary['slippage_avg_abs_bps']}",
                f"Slippage max abs bps: {summary['slippage_max_abs_bps']}",
                "",
                "FALLBACK EFFECTIVENESS",
                f"PnL fallback used: {fallback_summary['pnl_fallback_used']} | Cleared: {fallback_summary['pnl_fallback_cleared']}",
                f"PnL fallback runtime: {fallback_summary['pnl_fallback_seconds']}s ({fallback_summary['pnl_fallback_pct_runtime']}%)",
                f"Liquidity fallback attempts: {fallback_summary['liquidity_fallback_attempts']} | Min ratio: {fallback_summary['liquidity_fallback_min_ratio']} | Avg ratio: {fallback_summary['liquidity_fallback_avg_ratio']}",
                f"Liquidity downsizes: {fallback_summary['liquidity_downsizes']}",
                f"Orderbook backoff events: {fallback_summary['orderbook_backoff_events']} | Active: {fallback_summary['orderbook_backoff_active']}",
                f"Orderbook mid-price failures: {fallback_summary['orderbook_midprice_failures']}",
                f"Orderbook backoff reasons: {backoff_reason_line}",
                "",
                "DATA QUALITY",
                f"Checks: {summary['data_quality_checks_total']} | Fail: {summary['data_quality_checks_fail']} | Warn: {summary['data_quality_checks_warn']}",
                f"Reconciliation rows: {summary['reconciliation_checks_total']} | Pass: {summary['reconciliation_checks_pass']} | Fail: {summary['reconciliation_checks_fail']}",
                f"Reconciliation warnings (delta/unexplained): {summary['reconciliation_large_delta_warnings']} / {summary['reconciliation_large_unexplained_warnings']}",
                f"Candle shortfall events: {summary['candle_shortfall_events']} | Missing candles total: {summary['candle_shortfall_missing_total']}",
                "",
                "RUN BEHAVIOR",
                f"Pair switches: {run_behavior['pair_switches']} | Blocked: {run_behavior['pair_switch_blocked']}",
                f"Switch reasons: {switch_reason_line}",
                f"Idle timeouts: {run_behavior['idle_timeouts']}",
                f"Hospital moves: {run_behavior['hospital_moves']} | Graveyard moves: {run_behavior['graveyard_moves']}",
                f"Hospital prioritized: {run_behavior['hospital_prioritized']}",
                f"Strategy refreshes: {run_behavior['strategy_refreshes']}",
                f"Signals->Entries: {run_behavior['signals_to_entries_pct']}% | Entries->Trades: {run_behavior['entries_to_trades_pct']}%",
                "",
                "ALERTS",
                f"Alerts: {summary['alerts_total']} | Errors: {summary['errors_total']}",
                "",
                *comparison_lines,
                "",
                *post_run_fix_lines,
                "",
                "FILES",
                *[f"- {name}" for name in files_list],
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    repo_root = Path(__file__).resolve().parents[1]
    report_root = _report_root(repo_root)
    try:
        if output_dir.resolve().parent == report_root.resolve():
            _write_report_index(report_root)
    except Exception:
        pass
    try:
        from log_indexer import write_log_index
        log_root = repo_root / "Logs" / "v1"
        write_log_index(log_root)
    except Exception:
        pass

    return summary_path


def main():
    parser = argparse.ArgumentParser(description="Generate StatBot run report pack.")
    parser.add_argument("--log", dest="log_path", default="", help="Path to log file.")
    parser.add_argument("--output", dest="output_dir", default="", help="Output report directory.")
    parser.add_argument("--env", dest="env_path", default="", help="Path to .env file to snapshot.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    log_path = Path(args.log_path) if args.log_path else None

    if log_path is None:
        env_log = os.getenv("STATBOT_LOG_PATH")
        if env_log:
            log_path = Path(env_log)
        else:
            log_path = _find_latest_log(repo_root / "Logs")

    if not log_path or not log_path.exists():
        print("report_generator: log file not found.", file=sys.stderr)
        return 1

    start_ts = None
    with open(log_path, "r", encoding="utf-8", errors="ignore") as handle:
        for raw in handle:
            match = LOG_LINE_RE.match(raw.strip())
            if not match:
                continue
            ts = _parse_ts(match.group("ts"))
            if ts:
                start_ts = ts
                break

    log_run_sequence, log_run_id = _run_info_from_log_path(log_path)
    run_id = log_run_id or (
        start_ts.strftime("%Y%m%d_%H%M%S") if start_ts else datetime.now().strftime("%Y%m%d_%H%M%S")
    )

    report_root = _report_root(repo_root)
    if not args.output_dir and log_run_sequence and log_run_id:
        output_dir = report_root / f"run_{log_run_sequence:02d}_{log_run_id}"
        run_sequence = log_run_sequence
        report_version = "v1"
    else:
        output_dir, run_sequence, report_version = _resolve_output_dir(repo_root, run_id, args.output_dir)
    env_path = Path(args.env_path) if args.env_path else repo_root / "Execution" / ".env"

    summary_path = generate_report(
        log_path,
        output_dir,
        env_path=env_path,
        run_id=run_id,
        run_sequence=run_sequence,
        report_version=report_version,
    )
    print(f"report_generator: wrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
