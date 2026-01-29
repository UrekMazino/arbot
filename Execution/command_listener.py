import json
import os
import subprocess
import time
from collections import deque
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from func_log_setup import get_logger
from molt_monitor import _parse_log_line, _resolve_log_path, _update_state

logger = get_logger("command_listener")

if load_dotenv:
    env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(env_path)
else:
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        try:
            for raw in env_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
        except Exception as exc:
            logger.warning("Failed to load .env: %s", exc)

DEFAULT_POLL_SECONDS = 5
DEFAULT_READ_LIMIT = 20
DEFAULT_STATE_LINES = 500
DEFAULT_PREFIXES = ("!", "/")

STATE_FILE = Path(__file__).resolve().parents[1] / "Logs" / "command_listener_state.json"


def _bool_env(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    val = str(raw).strip().lower()
    if val in ("1", "true", "yes", "y", "on"):
        return True
    if val in ("0", "false", "no", "n", "off"):
        return False
    return default


def _load_state(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(path, data):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


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


def _tail_lines(path, max_lines):
    if not path.exists():
        return []
    lines = deque(maxlen=max_lines)
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if line:
                lines.append(line.strip())
    return list(lines)


def _prime_state(state, log_path, max_lines):
    for line in _tail_lines(log_path, max_lines):
        parsed = _parse_log_line(line)
        if parsed:
            _update_state(state, parsed)


def _follow_log(handle, state):
    updated = False
    while True:
        line = handle.readline()
        if not line:
            break
        updated = True
        parsed = _parse_log_line(line.strip())
        if parsed:
            _update_state(state, parsed)
    return updated


def _read_messages(cmd, channel, target, account, after_id, limit, include_thread):
    args = [cmd, "message", "read", "--channel", channel, "--target", target, "--json", "--limit", str(limit)]
    if account:
        args.extend(["--account", account])
    if after_id:
        args.extend(["--after", str(after_id)])
    if include_thread:
        args.append("--include-thread")
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except Exception as exc:
        logger.warning("Message read failed: %s", exc)
        return []
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if detail:
            logger.warning("Message read error: %s", detail)
        return []
    try:
        payload = json.loads(result.stdout or "{}")
    except Exception:
        logger.warning("Message read returned invalid JSON.")
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("messages", "data", "items", "results"):
            if isinstance(payload.get(key), list):
                return payload.get(key)
        payload_block = payload.get("payload")
        if isinstance(payload_block, dict):
            for key in ("messages", "data", "items", "results"):
                if isinstance(payload_block.get(key), list):
                    return payload_block.get(key)
    return []


def _send_message(cmd, channel, target, account, message):
    if not message:
        return False
    safe_message = " | ".join(part.strip() for part in message.splitlines() if part.strip())
    args = [cmd, "message", "send", "--channel", channel, "--target", target, "--message", safe_message]
    if account:
        args.extend(["--account", account])
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except Exception as exc:
        logger.warning("Send failed: %s", exc)
        return False
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if detail:
            logger.warning("Send error: %s", detail)
        return False
    logger.info("Command reply sent to %s", target)
    return True


def _message_content(msg):
    if not isinstance(msg, dict):
        return ""
    for key in ("content", "text", "message", "body"):
        value = msg.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _message_id(msg):
    if not isinstance(msg, dict):
        return ""
    for key in ("id", "messageId", "message_id", "msgId"):
        value = msg.get(key)
        if value:
            return str(value)
    return ""


def _message_id_numeric(msg_id):
    if not msg_id:
        return None
    try:
        return int(msg_id)
    except (TypeError, ValueError):
        return None


def _message_ts(msg):
    if not isinstance(msg, dict):
        return ""
    for key in ("timestamp", "createdAt", "created_at", "ts"):
        value = msg.get(key)
        if value:
            return str(value)
    return ""


def _is_own_message(msg):
    if not isinstance(msg, dict):
        return False
    for key in ("fromSelf", "fromMe", "isSelf", "self", "outgoing"):
        if msg.get(key) is True:
            return True
    author = msg.get("author")
    if isinstance(author, dict) and author.get("bot") is True:
        return True
    return False


def _resolve_reply_target(msg, fallback):
    if not isinstance(msg, dict):
        return fallback
    for key in ("target", "channel", "channelId", "channel_id", "conversationId"):
        value = msg.get(key)
        if isinstance(value, str) and value.strip():
            if key in ("channelId", "channel_id") and not value.startswith("channel:"):
                return f"channel:{value}"
            return value
    return fallback


def _extract_command(content, prefixes, require_prefix):
    if not content:
        return None
    text = content.strip()
    lowered = text.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            remainder = lowered[len(prefix):].strip()
            return remainder.split()[0] if remainder else None
    if require_prefix:
        return None
    if len(lowered.split()) == 1:
        return lowered
    return None


def _format_status(state):
    def _coalesce(value, default="n/a"):
        if value is None:
            return default
        if isinstance(value, str) and not value.strip():
            return default
        return value

    parts = ["StatBot status"]
    if state.get("ticker_1") and state.get("ticker_2"):
        pair = f"{state['ticker_1']}/{state['ticker_2']}"
        extras = []
        if state.get("td_mode"):
            extras.append(f"td_mode={state['td_mode']}")
        if state.get("pos_mode"):
            extras.append(f"pos_mode={state['pos_mode']}")
        pair_line = f"Pair: {pair}"
        if extras:
            pair_line = f"{pair_line} ({', '.join(extras)})"
        parts.append(pair_line)

    if state.get("uptime"):
        parts.append(f"Uptime: {state['uptime']}")
    if state.get("time_in_pair"):
        parts.append(f"Time in pair: {state['time_in_pair']} min")

    signals = state.get("signals")
    trades = state.get("trades")
    if signals is not None or trades is not None:
        parts.append(f"Signals/Trades: {_coalesce(signals)}/{_coalesce(trades)}")

    pnl = _coalesce(state.get("pnl"))
    pnl_pct = _coalesce(state.get("pnl_pct"))
    equity = _coalesce(state.get("equity") or state.get("starting_equity") or state.get("avail_eq"))
    session = _coalesce(state.get("session"))
    session_pct = _coalesce(state.get("session_pct"))
    parts.append(f"PnL: {pnl} USDT ({pnl_pct}%) | Equity: {equity} USDT | Session: {session} USDT ({session_pct}%)")

    if state.get("zscore"):
        parts.append(f"Z: {state['zscore']}")

    if state.get("avail_eq") or state.get("avail_bal"):
        parts.append(f"AvailEq: {_coalesce(state.get('avail_eq'))} | AvailBal: {_coalesce(state.get('avail_bal'))}")

    if state.get("last_api_error"):
        parts.append(f"Last API error: {state['last_api_error']}")

    return " | ".join(parts)


def _format_pnl(state):
    pnl = state.get("pnl") or "n/a"
    pnl_pct = state.get("pnl_pct") or "n/a"
    equity = state.get("equity") or state.get("starting_equity") or state.get("avail_eq") or "n/a"
    session = state.get("session") or "n/a"
    session_pct = state.get("session_pct") or "n/a"
    return (
        f"PnL: {pnl} USDT ({pnl_pct}%) | Equity: {equity} USDT | "
        f"Session: {session} USDT ({session_pct}%)"
    )


def _format_pair(state):
    pair = "n/a"
    if state.get("ticker_1") and state.get("ticker_2"):
        pair = f"{state['ticker_1']}/{state['ticker_2']}"
    td_mode = state.get("td_mode") or "n/a"
    pos_mode = state.get("pos_mode") or "n/a"
    return f"Pair: {pair} | td_mode={td_mode} | pos_mode={pos_mode}"


def _format_balance(state):
    start_eq = state.get("starting_equity") or "n/a"
    avail_eq = state.get("avail_eq") or "n/a"
    avail_bal = state.get("avail_bal") or "n/a"
    return f"Starting equity: {start_eq} USDT | AvailEq: {avail_eq} | AvailBal: {avail_bal}"


def _format_help(prefixes):
    prefix_hint = prefixes[0] if prefixes else "!"
    return (
        "Commands: "
        f"{prefix_hint}status, {prefix_hint}pnl, {prefix_hint}pair, "
        f"{prefix_hint}balance, {prefix_hint}help"
    )


def run():
    channel = os.getenv("STATBOT_COMMAND_CHANNEL") or os.getenv("MOLT_CHANNEL", "")
    target = os.getenv("STATBOT_COMMAND_TARGET") or os.getenv("MOLT_TO", "")
    account = os.getenv("STATBOT_COMMAND_ACCOUNT", "")
    poll_seconds = int(os.getenv("STATBOT_COMMAND_POLL_SECONDS", DEFAULT_POLL_SECONDS))
    limit = int(os.getenv("STATBOT_COMMAND_READ_LIMIT", DEFAULT_READ_LIMIT))
    include_thread = _bool_env("STATBOT_COMMAND_INCLUDE_THREAD", False)
    require_prefix = _bool_env("STATBOT_COMMAND_PREFIX_REQUIRED", False)

    prefixes_raw = os.getenv("STATBOT_COMMAND_PREFIXES", "")
    if prefixes_raw:
        prefixes = tuple(p.strip() for p in prefixes_raw.split(",") if p.strip())
    else:
        prefixes = DEFAULT_PREFIXES

    if not channel or not target:
        logger.error("STATBOT_COMMAND_CHANNEL and STATBOT_COMMAND_TARGET are required.")
        return

    cmd = _resolve_clawdbot_cmd()
    log_path = _resolve_log_path()
    state = {}
    if log_path.exists():
        _prime_state(state, log_path, DEFAULT_STATE_LINES)

    state_data = _load_state(STATE_FILE)
    last_id = state_data.get("last_message_id", "")

    logger.info(
        "Command listener active (channel=%s target=%s prefixes=%s prefix_required=%s poll=%ss)",
        channel,
        target,
        ",".join(prefixes),
        require_prefix,
        poll_seconds,
    )
    logger.info("Command listener using clawdbot cmd: %s", cmd)

    handle = None
    last_offsets = 0

    while True:
        new_log_path = _resolve_log_path()
        if new_log_path != log_path:
            log_path = new_log_path
            state = {}
            if log_path.exists():
                _prime_state(state, log_path, DEFAULT_STATE_LINES)
            if handle:
                handle.close()
                handle = None
                last_offsets = 0

        if log_path.exists() and handle is None:
            handle = open(log_path, "r", encoding="utf-8", errors="ignore")
            handle.seek(0, os.SEEK_END)
            last_offsets = handle.tell()

        if handle:
            updated = _follow_log(handle, state)
            if updated:
                last_offsets = handle.tell()
            else:
                if log_path.exists():
                    size = log_path.stat().st_size
                    if size < last_offsets:
                        handle.close()
                        handle = None
                        last_offsets = 0

        messages = _read_messages(cmd, channel, target, account, last_id, limit, include_thread)
        if messages:
            logger.info("Command listener fetched %d messages", len(messages))
            sorted_msgs = []
            for msg in messages:
                ts_raw = msg.get("timestampMs") if isinstance(msg, dict) else None
                ts_val = None
                if ts_raw is not None:
                    try:
                        ts_val = int(ts_raw)
                    except (TypeError, ValueError):
                        ts_val = None
                sorted_msgs.append((ts_val, msg))
            sorted_msgs.sort(key=lambda item: item[0] if item[0] is not None else 0)

            max_id_val = _message_id_numeric(last_id)
            max_id_str = last_id

            for _, msg in sorted_msgs:
                msg_id = _message_id(msg)
                if msg_id:
                    msg_id_val = _message_id_numeric(msg_id)
                    if msg_id_val is not None:
                        if max_id_val is None or msg_id_val > max_id_val:
                            max_id_val = msg_id_val
                    else:
                        max_id_str = msg_id

                if _is_own_message(msg):
                    continue
                content = _message_content(msg)
                command = _extract_command(content, prefixes, require_prefix)
                if not command:
                    continue

                logger.info("Command received: %s", command)

                if command in ("status", "stat"):
                    reply = _format_status(state)
                elif command in ("pnl", "profit", "loss"):
                    reply = _format_pnl(state)
                elif command in ("pair", "pairs"):
                    reply = _format_pair(state)
                elif command in ("balance", "bal"):
                    reply = _format_balance(state)
                elif command in ("help", "commands"):
                    reply = _format_help(prefixes)
                else:
                    reply = ""

                if reply:
                    reply_target = _resolve_reply_target(msg, target)
                    sent = _send_message(cmd, channel, reply_target, account, reply)
                    if not sent:
                        logger.warning("Failed to send reply for command: %s", command)

            if max_id_val is not None:
                last_id = str(max_id_val)
            elif max_id_str:
                last_id = max_id_str
            _save_state(STATE_FILE, {"last_message_id": last_id})

        time.sleep(max(1, poll_seconds))


if __name__ == "__main__":
    run()
