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
)
POSITION_OPEN_RE = re.compile(r"Position opened: entry_z=(?P<entry_z>[-+]?\d+\.\d+)")
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


def _write_csv(path, rows, fieldnames):
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
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
    _write_csv(index_csv, rows, INDEX_FIELDS)


def generate_report(log_path, output_dir, env_path=None, run_id=None, run_sequence=None, report_version="v1"):
    log_path = Path(log_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    env_values = _load_env_file(env_path) if env_path else {}
    ratio_env = env_values.get("STATBOT_MIN_LIQUIDITY_RATIO") or env_values.get("STATBOT_LIQUIDITY_MIN_RATIO") or ""
    min_liquidity_ratio = _safe_float(ratio_env) if ratio_env else 0.0
    ratio_threshold = min_liquidity_ratio if min_liquidity_ratio and min_liquidity_ratio > 0 else 1.0

    equity_curve = []
    trades = []
    alerts = []
    liquidity_checks = []
    entry_slippage = []
    open_positions = []
    entry_order_map = {}

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

            if not pair:
                tmatch = TICKER_CONFIG_RE.search(clean_msg)
                if tmatch:
                    pair = f"{tmatch.group('t1')}/{tmatch.group('t2')}"

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

            open_match = POSITION_OPEN_RE.search(clean_msg)
            if open_match and ts:
                open_positions.append({"timestamp": ts, "entry_z": open_match.group("entry_z")})

            trade_match = TRADE_CLOSED_RE.search(clean_msg)
            if trade_match and ts:
                hold_minutes = None
                entry_z = None
                if open_positions:
                    entry = open_positions.pop(0)
                    entry_z = entry.get("entry_z")
                    delta = ts - entry.get("timestamp")
                    hold_minutes = round(delta.total_seconds() / 60, 2)

                trades.append(
                    {
                        "timestamp": ts.isoformat(),
                        "result": trade_match.group("result"),
                        "pnl_usdt": _safe_float(trade_match.group("pnl")),
                        "pnl_pct": _safe_float(trade_match.group("pnl_pct")),
                        "equity_usdt": _safe_float(trade_match.group("equity")),
                        "session_pnl_usdt": _safe_float(trade_match.group("session")),
                        "session_pnl_pct": _safe_float(trade_match.group("session_pct")),
                        "hold_minutes": hold_minutes,
                        "entry_z": entry_z,
                    }
                )

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

    repo_root = Path(__file__).resolve().parents[1]
    version = _read_version(repo_root)
    git_sha = _git_sha(repo_root)
    config_snapshot = _redact_config(env_values)

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
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
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
    }

    summary_path = output_dir / "summary.json"
    summary_txt_path = output_dir / "summary.txt"
    equity_path = output_dir / "equity_curve.csv"
    trades_path = output_dir / "trades.csv"
    liquidity_path = output_dir / "liquidity_checks.csv"
    slippage_path = output_dir / "entry_slippage.csv"
    alerts_path = output_dir / "alerts.txt"
    config_path = output_dir / "config_snapshot.json"

    summary["equity_curve_path"] = str(equity_path)
    summary["trades_path"] = str(trades_path)
    summary["liquidity_checks_path"] = str(liquidity_path)
    summary["entry_slippage_path"] = str(slippage_path)
    summary["alerts_path"] = str(alerts_path)
    summary["config_snapshot_path"] = str(config_path)
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
            "result",
            "pnl_usdt",
            "pnl_pct",
            "equity_usdt",
            "session_pnl_usdt",
            "session_pnl_pct",
            "hold_minutes",
            "entry_z",
        ],
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
    )

    if alerts:
        alerts_path.write_text("\n".join(alerts) + "\n", encoding="utf-8")

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    config_path.write_text(json.dumps(config_snapshot, indent=2), encoding="utf-8")

    files_list = [
        summary_path.name,
        summary_txt_path.name,
        config_path.name,
    ]
    for path in [
        equity_path,
        trades_path,
        liquidity_path,
        slippage_path,
        alerts_path,
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
                f"Total PnL: {summary['total_pnl']} ({summary['total_pnl_pct']}%)",
                f"Max drawdown: {summary['max_drawdown_usdt']} ({summary['max_drawdown_pct']}%)",
                f"Trades: {summary['trades_total']} | Wins: {summary['wins']} | Losses: {summary['losses']} | Win rate: {summary['win_rate_pct']}",
                f"Avg trade PnL: {summary['avg_trade_pnl_usdt']} | Avg hold (min): {summary['avg_hold_minutes']}",
                "",
                "EXECUTION QUALITY",
                f"Signals: {summary['signals_total']} | Entries: {summary['entries_total']}",
                f"Liquidity rejects: {summary['liquidity_rejects']} ({summary['liquidity_reject_rate_pct']}%)",
                f"Liquidity low pct: {summary['liquidity_low_pct']}",
                f"Liquidity ratio avg (long/short): {summary['liquidity_avg_long_ratio']} / {summary['liquidity_avg_short_ratio']}",
                f"Slippage samples: {summary['slippage_samples']}",
                f"Slippage avg bps (signed/abs): {summary['slippage_avg_bps']} / {summary['slippage_avg_abs_bps']}",
                f"Slippage max abs bps: {summary['slippage_max_abs_bps']}",
                "",
                "ALERTS",
                f"Alerts: {summary['alerts_total']} | Errors: {summary['errors_total']}",
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
