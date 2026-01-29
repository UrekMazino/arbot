import json
import os
import re
import subprocess
import time
import uuid
from collections import deque
from pathlib import Path

import requests


DEFAULT_LOG_DIR = Path(__file__).resolve().parents[1] / "Logs"
DEFAULT_LOG_PATH = DEFAULT_LOG_DIR / "logfile_okx.log"
DEFAULT_GATEWAY_URL = "http://127.0.0.1:18789"
DEFAULT_ALERT_COOLDOWN = 60
DEFAULT_CONTEXT_LINES = 5
DEFAULT_DELIVERY_MODE = "gateway"

DEFAULT_PATTERNS = [
    ("CRITICAL", re.compile(r"CRITICAL|UNHANDLED EXCEPTION", re.IGNORECASE)),
    ("ERROR", re.compile(r"\\bERROR\\b", re.IGNORECASE)),
    ("KILL_SWITCH", re.compile(r"KILL-SWITCH TRIGGERED", re.IGNORECASE)),
    ("CIRCUIT_BREAKER", re.compile(r"CIRCUIT BREAKER", re.IGNORECASE)),
    ("COMPLIANCE", re.compile(r"compliance restricted", re.IGNORECASE)),
    ("ORDERBOOK_DEAD", re.compile(r"ORDERBOOK DEAD", re.IGNORECASE)),
    ("NO_REPLACEMENT", re.compile(r"No replacement pairs available", re.IGNORECASE)),
    ("PNL_ALERT", re.compile(r"PNL_ALERT", re.IGNORECASE)),
]
LOG_PREFIX_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) (?P<level>[A-Z]+) (?P<msg>.*)$"
)
RE_TICKER_CONFIG = re.compile(
    r"ticker_1=(?P<t1>[^,]+), ticker_2=(?P<t2>[^,]+), signal_positive=(?P<sp>[^,]+), signal_negative=(?P<sn>[^\s]+)"
)
RE_START_EQUITY = re.compile(r"Starting equity: (?P<eq>[-+]?\d+\.\d+) USDT")
RE_BALANCE_SNAPSHOT = re.compile(
    r"Balance snapshot \(USDT\): availBal=(?P<avail_bal>[-+]?\d+\.\d+) \| availEq=(?P<avail_eq>[-+]?\d+\.\d+) \| td_mode=(?P<td_mode>[^\s|]+) \| pos_mode=(?P<pos_mode>[^\s|]+)"
)
RE_UPTIME = re.compile(r"Uptime: (?P<uptime>.+)$")
RE_TIME_IN_PAIR = re.compile(r"Time in pair: (?P<time>[-+]?\d+(?:\.\d+)?) min")
RE_SIGNALS_TRADES = re.compile(r"Signals seen: (?P<signals>\d+) \| Trades: (?P<trades>\d+)")
RE_PNL_LINE = re.compile(
    r"PnL: (?P<pnl>[-+]?\d+\.\d+) USDT \((?P<pnl_pct>[-+]?\d+\.\d+)%\) \| Equity: (?P<equity>\d+\.\d+) USDT \| Session: (?P<session>[-+]?\d+\.\d+) USDT \((?P<session_pct>[-+]?\d+\.\d+)%\)"
)
RE_ZSCORE_LINE = re.compile(r"Z-Score: (?P<zscore>[-+]?\d+\.\d+)")
RE_OKX_API_ERROR = re.compile(
    r"OKX API error for (?P<inst>[^:]+): code=(?P<code>[^,]+), msg=(?P<msg>.+)$"
)


def _strip_non_ascii(text):
    if not text:
        return ""
    return "".join(ch for ch in text if ord(ch) < 128).strip()


def _parse_log_line(line):
    match = LOG_PREFIX_RE.match(line)
    if not match:
        return None
    return match.groupdict()


def _update_state(state, parsed):
    msg = parsed.get("msg", "") if parsed else ""
    clean_msg = _strip_non_ascii(msg)

    match = RE_TICKER_CONFIG.search(clean_msg)
    if match:
        state["ticker_1"] = match.group("t1")
        state["ticker_2"] = match.group("t2")
        state["signal_positive"] = match.group("sp")
        state["signal_negative"] = match.group("sn")

    match = RE_START_EQUITY.search(clean_msg)
    if match:
        state["starting_equity"] = match.group("eq")

    match = RE_BALANCE_SNAPSHOT.search(clean_msg)
    if match:
        state["avail_bal"] = match.group("avail_bal")
        state["avail_eq"] = match.group("avail_eq")
        state["td_mode"] = match.group("td_mode")
        state["pos_mode"] = match.group("pos_mode")

    match = RE_UPTIME.search(clean_msg)
    if match:
        state["uptime"] = match.group("uptime")

    match = RE_TIME_IN_PAIR.search(clean_msg)
    if match:
        state["time_in_pair"] = match.group("time")

    match = RE_SIGNALS_TRADES.search(clean_msg)
    if match:
        state["signals"] = match.group("signals")
        state["trades"] = match.group("trades")

    match = RE_PNL_LINE.search(clean_msg)
    if match:
        state["pnl"] = match.group("pnl")
        state["pnl_pct"] = match.group("pnl_pct")
        state["equity"] = match.group("equity")
        state["session"] = match.group("session")
        state["session_pct"] = match.group("session_pct")

    match = RE_ZSCORE_LINE.search(clean_msg)
    if match:
        state["zscore"] = match.group("zscore")

    match = RE_OKX_API_ERROR.search(clean_msg)
    if match:
        inst = match.group("inst")
        code = match.group("code")
        msg = match.group("msg")
        state["last_api_error"] = f"API error for {inst} code={code} msg={msg}"


def _format_exec_alert(key, parsed, state):
    ts = parsed.get("ts") if parsed else ""
    event_msg = _strip_non_ascii(parsed.get("msg", "")) if parsed else ""

    lines = [f"[{key}] StatBot alert"]
    if ts:
        lines.append(f"Time: {ts}")

    pair = ""
    if state.get("ticker_1") and state.get("ticker_2"):
        pair = f"{state['ticker_1']}/{state['ticker_2']}"
    if pair:
        extras = []
        if state.get("td_mode"):
            extras.append(f"td_mode={state['td_mode']}")
        if state.get("pos_mode"):
            extras.append(f"pos_mode={state['pos_mode']}")
        line = f"Pair: {pair}"
        if extras:
            line = f"{line} | " + " | ".join(extras)
        lines.append(line)

    status_parts = []
    if state.get("uptime"):
        status_parts.append(f"Uptime: {state['uptime']}")
    if state.get("time_in_pair"):
        status_parts.append(f"Time in pair: {state['time_in_pair']} min")
    signals = state.get("signals")
    trades = state.get("trades")
    if signals or trades:
        status_parts.append(f"Signals/Trades: {signals or 'n/a'}/{trades or 'n/a'}")
    if status_parts:
        lines.append(" | ".join(status_parts))

    equity = state.get("equity") or state.get("starting_equity") or state.get("avail_eq")
    if state.get("pnl") or equity or state.get("session"):
        pnl = state.get("pnl") or "n/a"
        pnl_pct = state.get("pnl_pct") or "n/a"
        equity_val = equity or "n/a"
        session = state.get("session") or "n/a"
        session_pct = state.get("session_pct") or "n/a"
        lines.append(
            f"PnL: {pnl} USDT ({pnl_pct}%) | Equity: {equity_val} USDT | Session: {session} USDT ({session_pct}%)"
        )

    if state.get("zscore"):
        lines.append(f"Z-Score: {state['zscore']}")

    if event_msg:
        lines.append(f"Event: {event_msg}")

    diag = state.get("last_api_error")
    if diag and diag != event_msg:
        lines.append(f"Diag: {diag}")

    return "\n".join(lines)


def _load_gateway_token():
    env_token = os.getenv("MOLT_HOOK_TOKEN") or os.getenv("CLAWDBOT_GATEWAY_TOKEN")
    if env_token:
        return env_token

    config_path = Path(os.getenv("MOLT_CONFIG_PATH", Path.home() / ".clawdbot" / "clawdbot.json"))
    if not config_path.exists():
        return ""
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    return (
        data.get("gateway", {})
        .get("auth", {})
        .get("token", "")
    )


def _resolve_clawdbot_cmd():
    explicit = os.getenv("MOLT_CLAWDBOT_CMD")
    if explicit:
        return explicit

    if os.name == "nt":
        appdata = os.getenv("APPDATA")
        if appdata:
            candidate = Path(appdata) / "npm" / "clawdbot.cmd"
            if candidate.exists():
                return str(candidate)

    return "clawdbot"


def _send_gateway_message(message, channel, recipient):
    if not recipient:
        print("molt_monitor: MOLT_TO is required for gateway send.")
        return False

    cmd = _resolve_clawdbot_cmd()
    token = os.getenv("MOLT_GATEWAY_TOKEN") or os.getenv("CLAWDBOT_GATEWAY_TOKEN") or _load_gateway_token()
    payload = {
        "to": recipient,
        "message": message,
        "idempotencyKey": str(uuid.uuid4()),
    }
    if channel:
        payload["channel"] = channel

    args = [
        cmd,
        "gateway",
        "call",
        "send",
        "--params",
        json.dumps(payload),
        "--json",
    ]
    if token:
        args.extend(["--token", token])

    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15)
    except Exception as exc:
        print(f"molt_monitor: gateway send failed to run: {exc}")
        return False

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        detail = stderr or stdout or "unknown error"
        print(f"molt_monitor: gateway send failed: {detail}")
        return False

    return True


def _send_hook_message(message, token, gateway_url, channel, recipient, name):
    url = gateway_url.rstrip("/") + "/hooks/agent"
    payload = {
        "message": message,
        "deliver": True,
        "wakeMode": "now",
        "channel": channel or "last",
        "name": name or "StatBot",
    }
    if recipient:
        payload["to"] = recipient

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as exc:
        print(f"molt_monitor: failed to send hook message: {exc}")
        return False

    if response.status_code not in (200, 202):
        print(f"molt_monitor: hook error {response.status_code}: {response.text[:200]}")
        return False

    return True


def _open_log_file(path, start_at_end=True):
    handle = open(path, "r", encoding="utf-8", errors="ignore")
    if start_at_end:
        handle.seek(0, os.SEEK_END)
    return handle


def _resolve_log_path():
    env_path = os.getenv("STATBOT_LOG_PATH")
    if env_path:
        return Path(env_path)

    candidates = sorted(DEFAULT_LOG_DIR.glob("log_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    if candidates:
        return candidates[0]

    return DEFAULT_LOG_PATH


def monitor_log():
    log_path = _resolve_log_path()
    gateway_url = os.getenv("MOLT_GATEWAY_URL", DEFAULT_GATEWAY_URL)
    token = _load_gateway_token()
    channel = os.getenv("MOLT_CHANNEL", "last")
    recipient = os.getenv("MOLT_TO", "")
    name = os.getenv("MOLT_AGENT_NAME", "StatBot Monitor")
    cooldown = int(os.getenv("MOLT_ALERT_COOLDOWN_SECONDS", DEFAULT_ALERT_COOLDOWN))
    context_lines = int(os.getenv("MOLT_ALERT_CONTEXT_LINES", DEFAULT_CONTEXT_LINES))
    include_context = os.getenv("MOLT_ALERT_INCLUDE_CONTEXT", "").lower() in ("1", "true", "yes")
    start_at_end = os.getenv("MOLT_MONITOR_FROM_START", "").lower() not in ("1", "true", "yes")
    delivery_mode = os.getenv("MOLT_DELIVERY_MODE", DEFAULT_DELIVERY_MODE).strip().lower()

    if delivery_mode == "hooks" and not token:
        print("molt_monitor: no hook token found. Set MOLT_HOOK_TOKEN or configure gateway.auth.token.")
        return

    if not log_path.exists():
        print(f"molt_monitor: log file not found: {log_path}")
        return

    print(f"molt_monitor: watching {log_path}")
    handle = _open_log_file(log_path, start_at_end=start_at_end)
    last_offsets = handle.tell()

    recent = deque(maxlen=context_lines)
    last_sent = {}
    state = {}

    while True:
        line = handle.readline()
        if not line:
            if log_path.exists():
                size = log_path.stat().st_size
                if size < last_offsets:
                    handle.close()
                    handle = _open_log_file(log_path, start_at_end=False)
                    last_offsets = handle.tell()
            time.sleep(1)
            continue

        last_offsets = handle.tell()
        stripped = line.strip()
        if not stripped:
            continue
        recent.append(stripped)
        parsed = _parse_log_line(stripped)
        if parsed:
            _update_state(state, parsed)

        for key, pattern in DEFAULT_PATTERNS:
            if not pattern.search(stripped):
                continue
            now = time.time()
            last_time = last_sent.get(key, 0)
            if now - last_time < cooldown:
                break
            last_sent[key] = now
            message = _format_exec_alert(key, parsed, state)
            if include_context and recent:
                context = "\n".join(recent)
                message = f"{message}\n\nContext:\n{context}"
            if delivery_mode == "hooks":
                _send_hook_message(message, token, gateway_url, channel, recipient, name)
            else:
                _send_gateway_message(message, channel, recipient)
            break


if __name__ == "__main__":
    monitor_log()
