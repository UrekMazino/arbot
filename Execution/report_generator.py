import argparse
import csv
import json
import os
import re
import subprocess
import sys
from datetime import datetime
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

ALERT_PATTERNS = [
    re.compile(r"\bERROR\b", re.IGNORECASE),
    re.compile(r"CRITICAL|UNHANDLED EXCEPTION", re.IGNORECASE),
    re.compile(r"KILL-SWITCH TRIGGERED", re.IGNORECASE),
    re.compile(r"CIRCUIT BREAKER", re.IGNORECASE),
    re.compile(r"compliance restricted", re.IGNORECASE),
    re.compile(r"ORDERBOOK DEAD", re.IGNORECASE),
    re.compile(r"PNL_ALERT", re.IGNORECASE),
]


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
    candidates = sorted(log_dir.glob("log_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


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


def generate_report(log_path, output_dir, env_path=None):
    log_path = Path(log_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    equity_curve = []
    trades = []
    alerts = []
    liquidity_checks = []
    open_positions = []

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
    long_ratios = []
    short_ratios = []

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

            liq_match = LIQUIDITY_RE.search(clean_msg)
            if liq_match and ts:
                long_target = _safe_float(liq_match.group("long_target"))
                short_target = _safe_float(liq_match.group("short_target"))
                liquidity_long = _safe_float(liq_match.group("liquidity_long"))
                liquidity_short = _safe_float(liq_match.group("liquidity_short"))
                long_ratio = None
                short_ratio = None
                if liquidity_long and liquidity_long > 0 and long_target is not None:
                    long_ratio = long_target / liquidity_long
                    long_ratios.append(long_ratio)
                if liquidity_short and liquidity_short > 0 and short_target is not None:
                    short_ratio = short_target / liquidity_short
                    short_ratios.append(short_ratio)

                if long_ratio is None or short_ratio is None:
                    status = "unknown"
                    liquidity_unknown += 1
                elif long_ratio <= 1.0 and short_ratio <= 1.0:
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
    if session_pnl is None and ending_equity is not None and starting_equity is not None:
        session_pnl = ending_equity - starting_equity
        if starting_equity > 0:
            session_pct = (session_pnl / starting_equity) * 100

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
    env_values = _load_env_file(env_path) if env_path else {}
    config_snapshot = _redact_config(env_values)

    run_id = start_ts.strftime("%Y%m%d_%H%M%S") if start_ts else datetime.now().strftime("%Y%m%d_%H%M%S")

    summary = {
        "run_id": run_id,
        "version": version or "",
        "git_sha": git_sha,
        "log_path": str(log_path),
        "start_time": start_ts.isoformat() if start_ts else "",
        "end_time": end_ts.isoformat() if end_ts else "",
        "duration_seconds": duration_seconds,
        "pair": pair or "",
        "td_mode": td_mode or "",
        "pos_mode": pos_mode or "",
        "starting_equity": starting_equity,
        "ending_equity": ending_equity,
        "session_pnl": session_pnl,
        "session_pnl_pct": session_pct,
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
        "alerts_total": len(alerts),
        "errors_total": sum(1 for line in alerts if "ERROR" in line),
        "liquidity_samples": liquidity_samples,
        "liquidity_high_samples": liquidity_high,
        "liquidity_low_samples": liquidity_low,
        "liquidity_unknown_samples": liquidity_unknown,
        "liquidity_low_pct": liquidity_pct_low,
        "liquidity_max_long_ratio": max_long_ratio,
        "liquidity_max_short_ratio": max_short_ratio,
        "liquidity_avg_long_ratio": avg_long_ratio,
        "liquidity_avg_short_ratio": avg_short_ratio,
    }

    summary_path = output_dir / "summary.json"
    summary_txt_path = output_dir / "summary.txt"
    equity_path = output_dir / "equity_curve.csv"
    trades_path = output_dir / "trades.csv"
    liquidity_path = output_dir / "liquidity_checks.csv"
    alerts_path = output_dir / "alerts.txt"
    config_path = output_dir / "config_snapshot.json"

    summary["equity_curve_path"] = str(equity_path)
    summary["trades_path"] = str(trades_path)
    summary["liquidity_checks_path"] = str(liquidity_path)
    summary["alerts_path"] = str(alerts_path)
    summary["config_snapshot_path"] = str(config_path)

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    config_path.write_text(json.dumps(config_snapshot, indent=2), encoding="utf-8")

    summary_txt_path.write_text(
        "\n".join(
            [
                f"Run ID: {summary['run_id']}",
                f"Version: {summary['version'] or 'n/a'}",
                f"Git SHA: {summary['git_sha'] or 'n/a'}",
                f"Pair: {summary['pair'] or 'n/a'}",
                f"Start: {summary['start_time'] or 'n/a'}",
                f"End: {summary['end_time'] or 'n/a'}",
                f"Duration: {summary['duration_seconds'] or 'n/a'} sec",
                f"Starting equity: {summary['starting_equity']}",
                f"Ending equity: {summary['ending_equity']}",
                f"Session PnL: {summary['session_pnl']} ({summary['session_pnl_pct']}%)",
                f"Total PnL: {summary['total_pnl']} ({summary['total_pnl_pct']}%)",
                f"Max drawdown: {summary['max_drawdown_usdt']} ({summary['max_drawdown_pct']}%)",
                f"Trades: {summary['trades_total']} | Wins: {summary['wins']} | Losses: {summary['losses']} | Win rate: {summary['win_rate_pct']}",
                f"Avg trade PnL: {summary['avg_trade_pnl_usdt']}",
                f"Avg hold minutes: {summary['avg_hold_minutes']}",
                f"Alerts: {summary['alerts_total']} | Errors: {summary['errors_total']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

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

    if alerts:
        alerts_path.write_text("\n".join(alerts) + "\n", encoding="utf-8")

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

    run_id = start_ts.strftime("%Y%m%d_%H%M%S") if start_ts else datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir) if args.output_dir else repo_root / "Reports" / f"run_{run_id}"
    env_path = Path(args.env_path) if args.env_path else repo_root / "Execution" / ".env"

    summary_path = generate_report(log_path, output_dir, env_path=env_path)
    print(f"report_generator: wrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
