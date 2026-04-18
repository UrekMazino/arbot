# Remove Pandas Future Warnings
import os
import json
import warnings
import logging
import math
import time
import sys
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from func_log_setup import get_logger

warnings.simplefilter(action="ignore", category=FutureWarning)

# General imports
from config_execution_api import (
    default_leverage,
    max_cycles,
    pos_mode,
    signal_negative_ticker,
    signal_positive_ticker,
    tradeable_capital_usdt,
    stop_loss_fail_safe,
    max_drawdown_pct,
    ticker_1,
    ticker_2,
    save_active_pair,
    STATUS_UPDATE_INTERVAL,
    HEALTH_CHECK_INTERVAL,
    td_mode,
    account_session,
    trade_session,
    lock_on_pair,
    allowed_settle_ccy,
    is_permanently_blacklisted,
    get_blacklist_reason
)
from func_position_calls import (
    open_position_confirmation, 
    active_position_confirmation,
    get_account_state,
    check_inst_status,
    get_pos_data_from_state
)
from func_price_calls import (
    get_ticker_trade_liquidity,
    get_ticker_liquidity_analysis,
    get_price_klines,
    normalize_candlesticks,
)
from func_trade_management import manage_new_trades, monitor_exit, RISK_PER_TRADE_PCT
from func_get_zscore import get_latest_zscore
from func_execution_calls import set_leverage, get_min_capital_requirements
from func_close_positions import close_all_positions, get_position_info, close_non_active_positions
from func_event_emitter import emit_event, flush_events, get_event_context
from func_save_status import save_status
from regime_router import RegimeInput, RegimeRouter, should_block_new_entries as should_block_regime_entries
from strategy_router import (
    StrategyInput,
    StrategyRouter,
    should_block_new_entries as should_block_strategy_entries,
)
from func_strategy_state import record_strategy_trade_result
from fee_tracker import FeeTracker
from func_pair_state import (
    add_to_graveyard,
    add_to_hospital,
    remove_from_hospital,
    is_in_graveyard,
    is_in_hospital,
    is_good_pair_history,
    can_switch,
    set_last_switch_time,
    get_last_switch_time,
    get_switch_rate_limit_remaining,
    record_trade_result,
    record_pair_trade_result,
    get_pair_history_stats,
    should_blacklist_pair,
    get_hospital_entries,
    get_hospital_remaining,
    normalize_pair_key,
    get_last_health_score,
    get_last_switch_reason,
    set_last_switch_reason,
    get_min_capital_cooldown,
    set_min_capital_cooldown,
    clear_entry_tracking,
    clear_persistence_history,
    set_entry_equity,
    get_entry_equity,
    get_entry_time,
    get_entry_notional,
    get_entry_strategy,
    get_entry_regime,
    is_restricted_ticker,
    reset_health_failure,
    cleanup_expired_graveyard
)

# Setup logging
logger = get_logger("main_execution")

SWITCH_RESULT_SWITCHED = "switched"
SWITCH_RESULT_BLOCKED = "blocked"
SWITCH_RESULT_HARD_STOP = "hard_stop"
STRATEGY_REFRESH_SLEEP_SECONDS = 5
_PNL_LOG_INTERVAL_SECONDS = 60
_PNL_LOG_DELTA_THRESHOLD = 0.5
_LAST_PNL_LOG_TS = 0.0
_LAST_PNL_LOG_VAL = None
_PNL_ALERT_USDT = None
_PNL_ALERT_PCT = None
_PNL_ALERT_INTERVAL_SECONDS = None
_LAST_PNL_ALERT_TS = 0.0
_LAST_PNL_ALERT_VAL = None
_LAST_PNL_ALERT_SIGN = 0
_PNL_FALLBACK_ACTIVE = False
_PNL_FALLBACK_BASIS = ""
_REPORT_UPTIME_TRIGGERED = False
_RUN_END_LOGGED = False
_COINT_GATE_STREAK = 0  # Track consecutive cointegration gate occurrences
_COINT_GATE_THRESHOLD = 2  # Trigger switch after N consecutive coint_gate decisions
FORCED_SWITCH_EXIT_REASONS = {
    "exit_tier_1_stop_loss",
    "exit_tier_15_riskoff_coint_loss",
    "exit_tier_2_coint_losing",
    "exit_tier_3_coint_grace",
    "exit_tier_4_divergence",
}


def _should_log_pnl(total_pnl):
    global _LAST_PNL_LOG_TS
    global _LAST_PNL_LOG_VAL
    now = time.time()
    delta = None
    if _LAST_PNL_LOG_VAL is not None:
        delta = abs(total_pnl - _LAST_PNL_LOG_VAL)
    if _LAST_PNL_LOG_VAL is None or (delta is not None and delta >= _PNL_LOG_DELTA_THRESHOLD):
        _LAST_PNL_LOG_TS = now
        _LAST_PNL_LOG_VAL = total_pnl
        return True
    if (now - _LAST_PNL_LOG_TS) >= _PNL_LOG_INTERVAL_SECONDS:
        _LAST_PNL_LOG_TS = now
        _LAST_PNL_LOG_VAL = total_pnl
        return True
    return False


def _get_pnl_alert_thresholds():
    global _PNL_ALERT_USDT
    global _PNL_ALERT_PCT
    global _PNL_ALERT_INTERVAL_SECONDS
    if _PNL_ALERT_USDT is None:
        try:
            _PNL_ALERT_USDT = float(os.getenv("STATBOT_PNL_ALERT_USDT", "10"))
        except (TypeError, ValueError):
            _PNL_ALERT_USDT = 10.0
    if _PNL_ALERT_PCT is None:
        try:
            _PNL_ALERT_PCT = float(os.getenv("STATBOT_PNL_ALERT_PCT", "0.5"))
        except (TypeError, ValueError):
            _PNL_ALERT_PCT = 0.5
    if _PNL_ALERT_INTERVAL_SECONDS is None:
        try:
            _PNL_ALERT_INTERVAL_SECONDS = int(os.getenv("STATBOT_PNL_ALERT_INTERVAL_SECONDS", "600"))
        except (TypeError, ValueError):
            _PNL_ALERT_INTERVAL_SECONDS = 600
    return _PNL_ALERT_USDT, _PNL_ALERT_PCT, _PNL_ALERT_INTERVAL_SECONDS


def _get_pair_idle_timeout_min():
    raw = os.getenv("STATBOT_PAIR_IDLE_TIMEOUT_MIN", "0")
    try:
        minutes = float(raw)
    except (TypeError, ValueError):
        minutes = 0.0
    if minutes < 0:
        minutes = 0.0
    return minutes


def _env_flag(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    value = str(raw).strip().lower()
    if value in ("1", "true", "yes", "y", "on"):
        return True
    if value in ("0", "false", "no", "n", "off"):
        return False
    return bool(default)


def _get_coint_gate_threshold():
    """Get the number of consecutive coint_gate evaluations before triggering pair switch."""
    raw = os.getenv("STATBOT_COINT_GATE_THRESHOLD", "2")
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        value = 2
    if value < 1:
        value = 1
    if value > 10:
        value = 10
    return value


def _get_switch_precheck_coint_enabled():
    return _env_flag("STATBOT_SWITCH_PRECHECK_COINT", True)


def _get_switch_precheck_fail_open():
    return _env_flag("STATBOT_SWITCH_PRECHECK_FAIL_OPEN", False)


def _get_switch_precheck_limit():
    raw = os.getenv("STATBOT_SWITCH_PRECHECK_LIMIT", "120")
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        value = 120
    if value < 60:
        value = 60
    return value


def _get_switch_precheck_window():
    raw = os.getenv("STATBOT_SWITCH_PRECHECK_WINDOW", "60")
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        value = 60
    if value < 20:
        value = 20
    return value


def _env_float(name, default):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return float(default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def _get_recon_fee_fill_limit():
    raw = os.getenv("STATBOT_RECON_FEE_FILL_LIMIT", "200")
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        value = 200
    if value < 20:
        value = 20
    if value > 500:
        value = 500
    return value


def _get_recon_delta_warn_threshold_usdt(recon_basis):
    base = max(_env_float("STATBOT_RECON_DELTA_WARN_USDT", 0.10), 0.01)
    preclose = max(_env_float("STATBOT_RECON_DELTA_WARN_USDT_PRE_CLOSE", 0.25), 0.01)
    fallback = max(_env_float("STATBOT_RECON_DELTA_WARN_USDT_FALLBACK", 1.00), 0.01)
    basis = str(recon_basis or "").strip().lower()
    if basis.startswith("pre_close_equity_delta"):
        return preclose
    if "fallback" in basis:
        return fallback
    return base


def _get_recon_unexplained_warn_threshold_usdt(recon_basis):
    base = max(_env_float("STATBOT_RECON_UNEXPLAINED_WARN_USDT", 0.10), 0.01)
    preclose = max(_env_float("STATBOT_RECON_UNEXPLAINED_WARN_USDT_PRE_CLOSE", 0.15), 0.01)
    fallback = max(_env_float("STATBOT_RECON_UNEXPLAINED_WARN_USDT_FALLBACK", 0.50), 0.01)
    basis = str(recon_basis or "").strip().lower()
    if basis.startswith("pre_close_equity_delta"):
        return preclose
    if "fallback" in basis:
        return fallback
    return base


def _get_recon_unexplained_warn_threshold_pct():
    return max(_env_float("STATBOT_RECON_UNEXPLAINED_WARN_PCT", 50.0), 0.0)


def _get_regime_eval_seconds():
    raw = os.getenv("STATBOT_REGIME_EVAL_SECONDS", "60")
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        value = 60
    if value < 10:
        value = 10
    return value


def _get_regime_market_symbol():
    symbol = str(os.getenv("STATBOT_REGIME_MARKET_SYMBOL", "BTC-USDT-SWAP") or "").strip().upper()
    if not symbol:
        return "BTC-USDT-SWAP"
    return symbol


def _get_strategy_eval_seconds():
    raw = os.getenv("STATBOT_STRATEGY_EVAL_SECONDS", "60")
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        value = 60
    if value < 10:
        value = 10
    return value


def _get_event_heartbeat_seconds():
    raw = os.getenv("STATBOT_EVENT_HEARTBEAT_SECONDS", "60")
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        value = 60
    if value < 5:
        value = 5
    return value


def _get_balance_fetch_timeout_seconds():
    raw = os.getenv("STATBOT_BALANCE_FETCH_TIMEOUT_SECONDS", "8")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 8.0
    if value <= 0:
        value = 8.0
    return value


def _get_account_balance_safe(timeout_seconds=None):
    timeout = timeout_seconds if timeout_seconds is not None else _get_balance_fetch_timeout_seconds()
    result = {"response": None, "error": None}

    def _worker():
        try:
            result["response"] = account_session.get_account_balance()
        except Exception as exc:
            result["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        logger.warning("Account balance request timed out after %.1fs.", timeout)
        return None
    if result["error"] is not None:
        logger.warning("Account balance request failed: %s", result["error"])
        return None
    if not isinstance(result["response"], dict):
        return None
    return result["response"]


def _sanitize_run_end_detail(detail, max_len=300):
    if detail is None:
        return ""
    text = str(detail).replace("\n", " ").replace("\r", " ").strip()
    if max_len and len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _run_end_already_logged():
    log_path = str(os.getenv("STATBOT_LOG_PATH", "") or "").strip()
    if not log_path:
        return False
    path = Path(log_path)
    if not path.exists():
        return False
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            read_size = min(size, 16384)
            if read_size <= 0:
                return False
            f.seek(-read_size, os.SEEK_END)
            tail = f.read().decode("utf-8", errors="ignore")
    except Exception:
        return False

    lines = [line.strip() for line in tail.splitlines() if line.strip()]
    if not lines:
        return False
    for line in reversed(lines[-40:]):
        if "RUN_END:" in line:
            try:
                ts_text = line[:19]
                ts_dt = datetime.strptime(ts_text, "%Y-%m-%d %H:%M:%S")
                if abs(time.time() - ts_dt.timestamp()) <= 600:
                    return True
            except Exception:
                return True
    return False


def _log_run_end(reason, detail="", exit_code=None):
    global _RUN_END_LOGGED
    if _RUN_END_LOGGED:
        return
    if _run_end_already_logged():
        _RUN_END_LOGGED = True
        return
    _RUN_END_LOGGED = True
    reason = str(reason or "").strip() or "unknown"
    detail = _sanitize_run_end_detail(detail)
    msg = f"RUN_END: reason={reason}"
    if detail:
        msg += f" detail={detail}"
    if exit_code is not None:
        msg += f" exit_code={exit_code}"
    logger.warning(msg)


def _maybe_log_pnl_alert(total_pnl, pnl_pct, session_pnl, session_pnl_pct, equity_usdt):
    global _LAST_PNL_ALERT_TS
    global _LAST_PNL_ALERT_VAL
    global _LAST_PNL_ALERT_SIGN

    threshold_usdt, threshold_pct, min_interval = _get_pnl_alert_thresholds()
    if threshold_usdt <= 0 and threshold_pct <= 0:
        return

    if abs(session_pnl) < threshold_usdt and abs(session_pnl_pct) < threshold_pct:
        return

    now = time.time()
    sign = 1 if session_pnl > 0 else -1 if session_pnl < 0 else 0
    should_alert = False
    if _LAST_PNL_ALERT_VAL is None:
        should_alert = True
    else:
        delta = abs(session_pnl - _LAST_PNL_ALERT_VAL)
        if sign != _LAST_PNL_ALERT_SIGN:
            should_alert = True
        elif threshold_usdt > 0 and delta >= threshold_usdt:
            should_alert = True

    if not should_alert and (now - _LAST_PNL_ALERT_TS) < min_interval:
        return

    _LAST_PNL_ALERT_TS = now
    _LAST_PNL_ALERT_VAL = session_pnl
    _LAST_PNL_ALERT_SIGN = sign
    logger.warning(
        "PNL_ALERT: Session PnL %+0.2f USDT (%+0.2f%%) | Total PnL %+0.2f USDT (%+0.2f%%) | Equity %.2f USDT",
        session_pnl,
        session_pnl_pct,
        total_pnl,
        pnl_pct,
        equity_usdt,
    )


def _start_molt_monitor():
    disable = str(os.getenv("STATBOT_MOLT_MONITOR", "")).strip().lower()
    if disable in ("0", "false", "no", "off"):
        logger.info("Molt monitor disabled via STATBOT_MOLT_MONITOR.")
        return None
    if os.getenv("STATBOT_MOLT_MONITOR_STARTED") == "1":
        return None

    monitor_script = Path(__file__).resolve().parent / "molt_monitor.py"
    if not monitor_script.exists():
        logger.warning("Molt monitor script missing: %s", monitor_script)
        return None

    env = os.environ.copy()
    env["STATBOT_MOLT_MONITOR_STARTED"] = "1"
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )
    try:
        proc = subprocess.Popen(
            [sys.executable, str(monitor_script)],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except Exception as exc:
        logger.warning("Failed to start Molt monitor: %s", exc)
        return None

    os.environ["STATBOT_MOLT_MONITOR_STARTED"] = "1"
    logger.info("Started Molt monitor (pid=%s).", proc.pid)
    return proc


def _start_command_listener():
    disable = str(os.getenv("STATBOT_COMMAND_LISTENER", "")).strip().lower()
    if disable in ("0", "false", "no", "off"):
        logger.info("Command listener disabled via STATBOT_COMMAND_LISTENER.")
        return None
    if os.getenv("STATBOT_COMMAND_LISTENER_STARTED") == "1":
        return None

    listener_script = Path(__file__).resolve().parent / "command_listener.py"
    if not listener_script.exists():
        logger.warning("Command listener script missing: %s", listener_script)
        return None

    env = os.environ.copy()
    env["STATBOT_COMMAND_LISTENER_STARTED"] = "1"
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )
    try:
        proc = subprocess.Popen(
            [sys.executable, str(listener_script)],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except Exception as exc:
        logger.warning("Failed to start command listener: %s", exc)
        return None

    os.environ["STATBOT_COMMAND_LISTENER_STARTED"] = "1"
    logger.info("Started command listener (pid=%s).", proc.pid)
    return proc


def _run_report_generator():
    disable = str(os.getenv("STATBOT_REPORT_ENABLE", "1")).strip().lower()
    if disable in ("0", "false", "no", "off"):
        logger.info("Report generator disabled via STATBOT_REPORT_ENABLE.")
        return False

    report_script = Path(__file__).resolve().parent / "report_generator.py"
    if not report_script.exists():
        logger.warning("Report generator script missing: %s", report_script)
        return False

    try:
        ret = subprocess.call([sys.executable, str(report_script)], env=os.environ.copy())
    except Exception as exc:
        logger.warning("Report generator failed to run: %s", exc)
        return False

    if ret != 0:
        logger.warning("Report generator returned non-zero exit code: %s", ret)
        return False

    logger.info("Report generator completed.")
    return True


def _get_report_uptime_hours():
    raw = os.getenv("STATBOT_REPORT_UPTIME_HOURS", "0")
    try:
        hours = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if hours <= 0:
        return 0.0
    return hours


def _get_max_uptime_hours():
    raw = os.getenv("STATBOT_MAX_UPTIME_HOURS", "0")
    try:
        hours = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if hours <= 0:
        return 0.0
    return hours


def _report_state_path():
    return Path(__file__).resolve().parents[1] / "Reports" / "report_state.json"


def _load_report_state(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_report_state(path, data):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to persist report state: %s", exc)


def _maybe_run_uptime_report(current_time, bot_start_time):
    global _REPORT_UPTIME_TRIGGERED
    hours = _get_report_uptime_hours()
    if hours <= 0:
        return
    if _REPORT_UPTIME_TRIGGERED:
        return
    state_path = _report_state_path()
    state = _load_report_state(state_path)
    if state.get("uptime_hours") == hours and state.get("triggered_at"):
        _REPORT_UPTIME_TRIGGERED = True
        return
    uptime_hours = (current_time - bot_start_time) / 3600.0
    if uptime_hours < hours:
        return
    if _run_report_generator():
        _REPORT_UPTIME_TRIGGERED = True
        _save_report_state(
            state_path,
            {"uptime_hours": hours, "triggered_at": datetime.utcnow().isoformat() + "Z"},
        )
        logger.info("Uptime report generated at %.2f hours.", uptime_hours)


def _validate_ticker_configuration():
    """
    Validate ticker configuration at bot startup.
    Ensures signal_positive_ticker and signal_negative_ticker are properly configured
    and distinct to prevent reversed long/short assignments.
    
    Raises:
        AssertionError: If configuration is invalid
    """
    # Check tickers are configured
    assert ticker_1 and isinstance(ticker_1, str), (
        f"âŒ STARTUP ERROR: ticker_1 must be non-empty string. Got: {ticker_1}"
    )
    assert ticker_2 and isinstance(ticker_2, str), (
        f"âŒ STARTUP ERROR: ticker_2 must be non-empty string. Got: {ticker_2}"
    )
    
    # Check tickers are different
    assert ticker_1 != ticker_2, (
        f"âŒ STARTUP ERROR: ticker_1 and ticker_2 must be different. Both are: {ticker_1}"
    )
    
    # Check signal tickers are configured
    assert signal_positive_ticker and isinstance(signal_positive_ticker, str), (
        f"âŒ STARTUP ERROR: signal_positive_ticker must be non-empty string. Got: {signal_positive_ticker}"
    )
    assert signal_negative_ticker and isinstance(signal_negative_ticker, str), (
        f"âŒ STARTUP ERROR: signal_negative_ticker must be non-empty string. Got: {signal_negative_ticker}"
    )
    
    # Check signal tickers are different
    assert signal_positive_ticker != signal_negative_ticker, (
        f"âŒ STARTUP ERROR: signal_positive_ticker and signal_negative_ticker must be different. "
        f"Both are: {signal_positive_ticker}"
    )
    
    # Check signal tickers match configured tickers
    valid_tickers = {ticker_1, ticker_2}
    assert signal_positive_ticker in valid_tickers, (
        f"âŒ STARTUP ERROR: signal_positive_ticker '{signal_positive_ticker}' must be one of "
        f"['{ticker_1}', '{ticker_2}']"
    )
    assert signal_negative_ticker in valid_tickers, (
        f"âŒ STARTUP ERROR: signal_negative_ticker '{signal_negative_ticker}' must be one of "
        f"['{ticker_1}', '{ticker_2}']"
    )
    
    logger.info(
        "âœ“ Ticker configuration validated: ticker_1=%s, ticker_2=%s, "
        "signal_positive=%s, signal_negative=%s",
        ticker_1, ticker_2, signal_positive_ticker, signal_negative_ticker
    )


def _is_hedged_mode(mode_value):
    normalized = str(mode_value or "").strip().lower()
    return normalized in ("long_short", "long_short_mode", "hedge", "hedged")


def _set_leverage_for_ticker(ticker, leverage):
    if _is_hedged_mode(pos_mode):
        set_leverage(ticker, leverage, pos_side="long")
        set_leverage(ticker, leverage, pos_side="short")
        return
    set_leverage(ticker, leverage)


def _get_available_usdt():
    balance_res = _get_account_balance_safe()
    if not balance_res or balance_res.get("code") != "0":
        return 0.0
    details = balance_res.get("data", [{}])[0].get("details", [])
    for det in details:
        if det.get("ccy") == "USDT":
            try:
                return float(det.get("availBal", 0))
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _get_equity_usdt():
    balance_res = _get_account_balance_safe()
    if not balance_res or balance_res.get("code") != "0":
        return 0.0
    details = balance_res.get("data", [{}])[0].get("details", [])
    for det in details:
        if det.get("ccy") == "USDT":
            try:
                return float(det.get("eq", 0))
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _extract_usdt_balance_snapshot(balance_res):
    starting_equity = 0.0
    avail_bal = 0.0
    avail_eq = 0.0
    if not balance_res or balance_res.get("code") != "0":
        return starting_equity, avail_bal, avail_eq

    details = balance_res.get("data", [{}])[0].get("details", [])
    for det in details:
        if det.get("ccy") == "USDT":
            try:
                starting_equity = float(det.get("eq", 0) or 0)
            except (TypeError, ValueError):
                starting_equity = 0.0
            try:
                avail_bal = float(det.get("availBal", 0) or 0)
            except (TypeError, ValueError):
                avail_bal = 0.0
            try:
                avail_eq = float(det.get("availEq", 0) or 0)
            except (TypeError, ValueError):
                avail_eq = 0.0
            break
    return starting_equity, avail_bal, avail_eq


def _capture_starting_equity_snapshot():
    balance_res = None
    starting_equity = 0.0
    avail_bal = 0.0
    avail_eq = 0.0
    try:
        balance_res = _get_account_balance_safe()
        starting_equity, avail_bal, avail_eq = _extract_usdt_balance_snapshot(balance_res)
        logger.info("Starting equity: %.2f USDT", starting_equity)
    except Exception as exc:
        logger.warning("Failed to capture starting equity: %s", exc)

    try:
        logger.info(
            "Balance snapshot (USDT): availBal=%.2f | availEq=%.2f | td_mode=%s | pos_mode=%s",
            avail_bal,
            avail_eq,
            td_mode,
            pos_mode,
        )
    except Exception as exc:
        logger.warning("Failed to log balance snapshot: %s", exc)

    return starting_equity, balance_res, avail_bal, avail_eq


def _parse_min_equity(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0:
        return None
    return parsed


def _get_per_leg_allocation():
    available_usdt = _get_available_usdt()
    if available_usdt > 0:
        effective_capital = min(tradeable_capital_usdt, available_usdt * 0.95)
    else:
        effective_capital = tradeable_capital_usdt

    if stop_loss_fail_safe <= 0:
        return effective_capital * 0.5

    risk_usdt = effective_capital * RISK_PER_TRADE_PCT
    initial_capital_usdt = risk_usdt / stop_loss_fail_safe

    # If calculated position would exceed capital, scale down proportionally
    if initial_capital_usdt * 2 > effective_capital:
        # Calculate what the actual risk would be with 50/50 split
        actual_position_size = effective_capital * 0.5
        actual_risk_usdt = actual_position_size * stop_loss_fail_safe
        actual_risk_pct = (actual_risk_usdt / effective_capital) * 100

        # Warn if risk exceeds target
        if actual_risk_pct > RISK_PER_TRADE_PCT * 100:
            logger.warning(
                "âš ï¸  Position sizing adjusted: Actual risk=%.2f USDT (%.2f%%) exceeds target %.2f%% due to capital constraints",
                actual_risk_usdt,
                actual_risk_pct,
                RISK_PER_TRADE_PCT * 100
            )

        initial_capital_usdt = effective_capital * 0.5

    return initial_capital_usdt


def _get_min_capital_for_ticker(ticker):
    try:
        req = get_min_capital_requirements(ticker)
        if not req.get("ok"):
            logger.warning(
                "Min-capital check failed for %s: %s",
                ticker,
                req.get("error") or "unknown",
            )
            return {"min_capital": 0.0, "settle_ccy": ""}
        info = req.get("instrument_info") or {}
        settle_ccy = str(info.get("settleCcy") or "").upper()
        return {"min_capital": req.get("min_capital") or 0.0, "settle_ccy": settle_ccy}
    except Exception as exc:
        logger.warning("Min-capital check failed for %s: %s", ticker, exc)
    return {"min_capital": 0.0, "settle_ccy": ""}


def _settle_filter_ok(t1, t2, settle_t1, settle_t2):
    if allowed_settle_ccy:
        if settle_t1 not in allowed_settle_ccy or settle_t2 not in allowed_settle_ccy:
            logger.info(
                "Skipping pair %s/%s: settleCcy filter (t1=%s t2=%s allowed=%s).",
                t1,
                t2,
                settle_t1 or "unknown",
                settle_t2 or "unknown",
                ",".join(allowed_settle_ccy),
            )
            return False
    if settle_t1 and settle_t2 and settle_t1 != settle_t2:
        logger.info(
            "Skipping pair %s/%s: mismatched settleCcy (%s vs %s).",
            t1,
            t2,
            settle_t1,
            settle_t2,
        )
        return False
    return True


def _format_uptime(seconds):
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    if minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _green(text):
    return f"\x1b[32m{text}\x1b[0m"


def _sleep_with_progress(seconds, label="Sleeping"):
    total = max(0, int(seconds))
    if total <= 0:
        return
    def _format_mmss(value):
        mins, secs = divmod(max(0, int(value)), 60)
        return f"{mins:02d}:{secs:02d}"

    total_label = _format_mmss(total)
    print(f"{label} for {total_label}")
    bar_len = 20
    start = time.time()
    elapsed = 0
    while elapsed < total:
        filled = int((elapsed / total) * bar_len)
        bar = "#" * filled + "-" * (bar_len - filled)
        remaining = total - elapsed
        sys.stdout.write(
            f"\r{label}: [{bar}] {_format_mmss(elapsed)}/{total_label} remaining {_format_mmss(remaining)}"
        )
        sys.stdout.flush()
        sleep_for = min(5, total - elapsed)
        time.sleep(sleep_for)
        elapsed = int(time.time() - start)
    sys.stdout.write(
        f"\r{label}: [{'#' * bar_len}] {total_label}/{total_label} remaining 00:00\n"
    )
    sys.stdout.flush()


def _run_strategy_refresh():
    strategy_path = Path(__file__).resolve().parent.parent / "Strategy" / "main_strategy.py"
    if not strategy_path.exists():
        logger.error("Cannot refresh pairs: Strategy script not found at %s", strategy_path)
        return False
    logger.warning("No replacement pairs available. Running Strategy to refresh pair universe...")
    logger.info("Searching for new pairs via Strategy refresh...")
    print("Searching for new pairs...")
    try:
        env = os.environ.copy()
        ret = subprocess.call([sys.executable, str(strategy_path)], env=env)
    except Exception as exc:
        logger.error("Strategy refresh failed: %s", exc)
        return False
    if ret != 0:
        logger.error("Strategy refresh failed with exit code %s", ret)
        return False
    logger.info("Strategy refresh completed.")
    return True


def _run_strategy_at_startup():
    """Run Strategy at startup to discover pairs if CSV is empty or missing."""
    strategy_path = Path(__file__).resolve().parent.parent / "Strategy" / "main_strategy.py"
    if not strategy_path.exists():
        logger.error("Cannot run Strategy: script not found at %s", strategy_path)
        return False

    logger.warning("Cointegrated pairs CSV is empty or missing. Running Strategy to discover pairs...")
    print("Running Strategy to discover cointegrated pairs...")
    print(f"   Strategy: {strategy_path}")
    print("   This may take a few minutes...")

    try:
        env = os.environ.copy()
        ret = subprocess.call([sys.executable, str(strategy_path)], env=env)
    except Exception as exc:
        logger.error("Strategy startup run failed: %s", exc)
        return False

    if ret != 0:
        logger.error("Strategy startup run failed with exit code %s", ret)
        return False

    logger.info("Strategy startup run completed successfully.")
    return True


def _pair_meets_min_capital(t1, t2, per_leg_capital):
    remaining = get_min_capital_cooldown(t1, t2)
    if remaining > 0:
        logger.debug(
            "Skipping pair %s/%s due to min-capital cooldown (%.1f sec remaining).",
            t1,
            t2,
            remaining,
        )
        return False

    min_req_t1 = _get_min_capital_for_ticker(t1)
    min_req_t2 = _get_min_capital_for_ticker(t2)
    min_cap_t1 = min_req_t1["min_capital"]
    min_cap_t2 = min_req_t2["min_capital"]
    settle_t1 = min_req_t1["settle_ccy"]
    settle_t2 = min_req_t2["settle_ccy"]
    if not _settle_filter_ok(t1, t2, settle_t1, settle_t2):
        return False
    if min_cap_t1 <= 0 or min_cap_t2 <= 0:
        logger.warning(
            "Min-capital check failed for %s/%s (min1=%.8f min2=%.8f).",
            t1,
            t2,
            min_cap_t1,
            min_cap_t2,
        )
        return False
    required = max(min_cap_t1, min_cap_t2)
    if required > per_leg_capital:
        cooldown = set_min_capital_cooldown(t1, t2, required, per_leg_capital)
        logger.info(
            "Skipping pair %s/%s: min capital %.8f exceeds allocation %.8f (min1=%.8f min2=%.8f, cooldown=%.1fm).",
            t1,
            t2,
            required,
            per_leg_capital,
            min_cap_t1,
            min_cap_t2,
            cooldown / 60,
        )
        return False
    return True


"""
KILL_SWITCH STATE MACHINE DOCUMENTATION
========================================

kill_switch is a control state variable that manages the bot's execution flow.
All transitions are deterministic and logged.

States:
-------
0 = ACTIVE: Normal operation, seeking trades and monitoring positions
1 = CLOSING: Orders placed or monitoring complete; waiting for positions to close
2 = STOP: Final exit signal; close all remaining positions and exit
3 = SWITCH: Pair health degraded; switch to next prospect and restart

State Transitions (deterministic):
----------------------------------
0 â†’ 0: Normal cycle, no signal or cointegration failed
        â†’ returns 0 to main_execution

0 â†’ 1: Hot trigger activated + cointegration valid + Z-score extreme
        â†’ manage_new_trades() returns 1 after placing orders
        â†’ main_execution sees 1, calls close_all_positions()

1 â†’ 2: Close operation complete
        â†’ close_all_positions() returns 2
        â†’ circuit breaker also returns 2
        â†’ hard stop/regime break also returns 2
        â†’ main_execution exits loop

0 â†’ 3: Health check failed (Low correlation, trending spread, etc.)
        â†’ manage_new_trades() returns 3
        â†’ main_execution sees 3, calls _switch_to_next_pair()
"""


def _switch_to_next_pair(health_score=None, switch_reason="health"):
    """
    Read the cointegrated pairs from Strategy folder and switch to the next one.
    Includes Graveyard and Cooldown checks with emergency override for critical health.

    Args:
        health_score: Current pair health score (0-100). If below emergency threshold, can override cooldown.
    """
    import pandas as pd
    from pathlib import Path

    if lock_on_pair:
        logger.warning(
            "Pair switch requested (reason=%s) but lock_on_pair is enabled. Staying on current pair.",
            switch_reason,
        )
        emit_event(
            "pair_switch",
            payload={
                "from_pair": f"{ticker_1}/{ticker_2}",
                "to_pair": None,
                "reason": switch_reason,
                "status": SWITCH_RESULT_BLOCKED,
            },
            severity="warn",
            logger=logger,
        )
        return SWITCH_RESULT_BLOCKED

    # 1. Check Cooldown with emergency override
    last_switch = get_last_switch_time()
    elapsed = (time.time() - last_switch) / 3600

    if not can_switch(cooldown_hours=24, health_score=health_score, emergency_threshold=40):
        rate_limit_remaining = get_switch_rate_limit_remaining()
        if rate_limit_remaining > 0:
            logger.warning(
                "Switch aborted: rate limiter active (%.0fs remaining). Entering defensive mode.",
                rate_limit_remaining,
            )
            set_last_switch_reason("switch_rate_limited")
        else:
            logger.warning("Switch aborted: Cooldown active (%.1fh elapsed, 24h required)", elapsed)
            if health_score is not None:
                logger.warning("Health score: %s/100 (emergency override requires < 40)", health_score)
        emit_event(
            "pair_switch",
            payload={
                "from_pair": f"{ticker_1}/{ticker_2}",
                "to_pair": None,
                "reason": switch_reason,
                "status": SWITCH_RESULT_BLOCKED,
                "health_score": health_score,
            },
            severity="warn",
            logger=logger,
        )
        return SWITCH_RESULT_BLOCKED

    # Log if emergency override was used
    if elapsed < 24:
        is_emergency_reason = str(switch_reason or "").strip().lower() in ("health", "orderbook_dead")
        if health_score is not None and health_score < 40 and is_emergency_reason:
            logger.warning(
                "EMERGENCY OVERRIDE: Health score %s < 40, bypassing cooldown (%.1fh elapsed)",
                health_score,
                elapsed,
            )
        else:
            logger.info(
                "Cooldown bypassed for switch reason=%s (%.1fh elapsed).",
                switch_reason,
                elapsed,
            )

    logger.info("Attempting to switch to next pair (reason=%s)...", switch_reason)
    csv_path = Path(__file__).resolve().parent.parent / "Strategy" / "output" / "2_cointegrated_pairs.csv"

    per_leg_capital = _get_per_leg_allocation()
    logger.info("Per-leg allocation for min-capital filter: %.8f", per_leg_capital)
    precheck_coint_enabled = _get_switch_precheck_coint_enabled()
    precheck_fail_open = _get_switch_precheck_fail_open()
    precheck_limit = _get_switch_precheck_limit()
    precheck_window = _get_switch_precheck_window()
    precheck_cache = {}
    if precheck_coint_enabled:
        logger.info(
            "Pair switch pre-check enabled (coint, limit=%d, window=%d, fail_open=%d).",
            precheck_limit,
            precheck_window,
            int(precheck_fail_open),
        )

    def _pair_passes_switch_precheck(t1, t2):
        if not precheck_coint_enabled:
            return True

        pair_key = normalize_pair_key(t1, t2) or f"{t1}/{t2}"
        cached = precheck_cache.get(pair_key)
        if cached is not None:
            return bool(cached)

        try:
            _zs, _sign, metrics = get_latest_zscore(
                inst_id_1=t1,
                inst_id_2=t2,
                limit=precheck_limit,
                window=precheck_window,
                use_orderbook=False,
            )
            coint_flag = int(metrics.get("coint_flag", 0))
            passed = coint_flag == 1
            if not passed:
                logger.info(
                    "Skipping pair %s/%s: switch pre-check failed (coint=%d p=%.4f corr=%.3f).",
                    t1,
                    t2,
                    coint_flag,
                    float(metrics.get("p_value", 1.0) or 1.0),
                    float(metrics.get("correlation", 0.0) or 0.0),
                )
            precheck_cache[pair_key] = bool(passed)
            return bool(passed)
        except Exception as exc:
            if precheck_fail_open:
                logger.warning(
                    "Switch pre-check error for %s/%s: %s (fail-open).",
                    t1,
                    t2,
                    exc,
                )
                precheck_cache[pair_key] = True
                return True
            logger.warning(
                "Skipping pair %s/%s: switch pre-check error: %s",
                t1,
                t2,
                exc,
            )
            precheck_cache[pair_key] = False
            return False

    def _read_pairs():
        if not csv_path.exists():
            logger.error("Cannot switch pair: CSV not found at %s", csv_path)
            return []
        logger.info("Reading pairs from %s...", csv_path)
        df = pd.read_csv(csv_path)
        if df.empty:
            logger.error("Cannot switch pair: CSV is empty")
            return []

        # Get current pair from config
        curr_t1 = ticker_1
        curr_t2 = ticker_2
        logger.info("Current pair: %s/%s", curr_t1, curr_t2)

        # Ensure we have the necessary columns
        if "sym_1" not in df.columns or "sym_2" not in df.columns:
            logger.error("CSV missing sym_1 or sym_2 columns. Columns found: %s", df.columns.tolist())
            return []

        pairs = []
        for _, row in df.iterrows():
            sym_1 = row.get("sym_1")
            sym_2 = row.get("sym_2")
            if not sym_1 or not sym_2:
                continue

            # Skip permanently blacklisted tickers
            if is_permanently_blacklisted(sym_1):
                logger.info("Skipping pair %s/%s - %s is permanently blacklisted: %s",
                           sym_1, sym_2, sym_1, get_blacklist_reason(sym_1))
                continue
            if is_permanently_blacklisted(sym_2):
                logger.info("Skipping pair %s/%s - %s is permanently blacklisted: %s",
                           sym_1, sym_2, sym_2, get_blacklist_reason(sym_2))
                continue

            # Skip pairs with zero/missing liquidity data (dead orderbooks)
            avg_vol_1 = row.get("avg_quote_volume_1")
            avg_vol_2 = row.get("avg_quote_volume_2")
            pair_liq_min = row.get("pair_liquidity_min")

            if pd.isna(avg_vol_1) or pd.isna(avg_vol_2) or pd.isna(pair_liq_min):
                logger.info("Skipping pair %s/%s - missing liquidity data (likely delisted/illiquid)", sym_1, sym_2)
                continue

            if avg_vol_1 == 0 or avg_vol_2 == 0 or pair_liq_min == 0:
                logger.info("Skipping pair %s/%s - zero liquidity (dead orderbook)", sym_1, sym_2)
                continue

            min_equity = _parse_min_equity(row.get("min_equity_recommended"))
            pair_key = normalize_pair_key(sym_1, sym_2)
            pairs.append(
                {
                    "sym_1": sym_1,
                    "sym_2": sym_2,
                    "pair_key": pair_key,
                    "min_equity": min_equity,
                }
            )
        logger.info("Found %d pairs in CSV.", len(pairs))
        return pairs

    def _find_next_pair(pairs):
        curr_t1 = ticker_1
        curr_t2 = ticker_2
        curr_idx = -1
        for i, pair in enumerate(pairs):
            s1 = pair["sym_1"]
            s2 = pair["sym_2"]
            if (s1 == curr_t1 and s2 == curr_t2) or (s1 == curr_t2 and s2 == curr_t1):
                curr_idx = i
                break

        next_t1, next_t2 = None, None
        equity_usdt = _get_equity_usdt()
        if equity_usdt > 0:
            logger.info("Equity for min-equity filter: %.2f USDT", equity_usdt)
        else:
            logger.warning("Equity unavailable; skipping min-equity filter.")

        pair_by_key = {pair.get("pair_key"): pair for pair in pairs if pair.get("pair_key")}
        hospital_entries = get_hospital_entries()
        ready_hospital = []
        if hospital_entries:
            now = time.time()
            for key, entry in hospital_entries.items():
                if not isinstance(entry, dict):
                    continue
                ts = entry.get("ts") or 0
                cooldown = entry.get("cooldown") or 0
                if ts and cooldown >= 0 and (now - ts) >= cooldown:
                    ready_hospital.append((key, ts))

        if ready_hospital:
            ready_hospital.sort(key=lambda item: item[1])
            for key, _ts in ready_hospital:
                pair = pair_by_key.get(key)
                if not pair:
                    continue
                t1, t2 = pair["sym_1"], pair["sym_2"]
                if (t1 == curr_t1 and t2 == curr_t2) or (t1 == curr_t2 and t2 == curr_t1):
                    continue
                if is_in_graveyard(t1, t2):
                    continue
                if is_restricted_ticker(t1) or is_restricted_ticker(t2):
                    continue
                if not _pair_meets_min_capital(t1, t2, per_leg_capital):
                    continue
                min_equity = pair.get("min_equity")
                if equity_usdt > 0 and min_equity and min_equity > equity_usdt:
                    continue
                if not _pair_passes_switch_precheck(t1, t2):
                    # Health check failed - remove from hospital instead of keeping forever
                    logger.info("Removing hospital pair %s/%s: health check failed.", t1, t2)
                    remove_from_hospital(t1, t2)
                    continue
                logger.info("Prioritizing hospital pair %s/%s (cooldown complete, health passed).", t1, t2)
                # Remove from hospital now that cooldown is complete and pair is selected
                remove_from_hospital(t1, t2)
                return t1, t2

        for i in range(1, len(pairs)):
            idx = (curr_idx + i) % len(pairs)
            pair = pairs[idx]
            t1, t2 = pair["sym_1"], pair["sym_2"]
            if (t1 == curr_t1 and t2 == curr_t2) or (t1 == curr_t2 and t2 == curr_t1):
                continue
            if is_in_graveyard(t1, t2):
                continue
            if is_in_hospital(t1, t2):
                remaining = get_hospital_remaining(t1, t2)
                if remaining > 0:
                    logger.debug(
                        "Skipping pair %s/%s: hospital cooldown %.1f sec remaining.",
                        t1,
                        t2,
                        remaining,
                    )
                    continue
            if is_restricted_ticker(t1) or is_restricted_ticker(t2):
                logger.info(
                    "Skipping pair %s/%s: compliance restricted ticker.",
                    t1,
                    t2,
                )
                continue
            if not _pair_meets_min_capital(t1, t2, per_leg_capital):
                continue
            min_equity = pair.get("min_equity")
            if equity_usdt > 0 and min_equity and min_equity > equity_usdt:
                logger.info(
                    "Skipping pair %s/%s: min_equity_recommended %.2f exceeds equity %.2f",
                    t1,
                    t2,
                    min_equity,
                    equity_usdt,
                )
                continue
            if not _pair_passes_switch_precheck(t1, t2):
                continue
            next_t1, next_t2 = t1, t2
            logger.info("Found healthy replacement at index %d: %s/%s", idx, next_t1, next_t2)
            break
        return next_t1, next_t2

    try:
        next_t1, next_t2 = None, None
        while next_t1 is None:
            pairs = _read_pairs()
            if not pairs:
                refreshed = _run_strategy_refresh()
                if refreshed:
                    pairs = _read_pairs()
                    if pairs:
                        next_t1, next_t2 = _find_next_pair(pairs)
                if next_t1 is None:
                    logger.warning(
                        "No candidate pairs available. Retrying in %s seconds.",
                        STRATEGY_REFRESH_SLEEP_SECONDS,
                    )
                    logger.info(
                        "Sleeping for %s before retrying pair search.",
                        _format_uptime(STRATEGY_REFRESH_SLEEP_SECONDS),
                    )
                    _sleep_with_progress(STRATEGY_REFRESH_SLEEP_SECONDS, label="Sleeping")
                continue

            next_t1, next_t2 = _find_next_pair(pairs)
            if next_t1 is None:
                refreshed = _run_strategy_refresh()
                if refreshed:
                    pairs = _read_pairs()
                    if pairs:
                        next_t1, next_t2 = _find_next_pair(pairs)
                if next_t1 is None:
                    logger.error(
                        "No suitable replacement pair found. Retrying in %s seconds.",
                        STRATEGY_REFRESH_SLEEP_SECONDS,
                    )
                    logger.info(
                        "Sleeping for %s before retrying pair search.",
                        _format_uptime(STRATEGY_REFRESH_SLEEP_SECONDS),
                    )
                    _sleep_with_progress(STRATEGY_REFRESH_SLEEP_SECONDS, label="Sleeping")

        curr_t1 = ticker_1
        curr_t2 = ticker_2
        # Commit graveyard only after a replacement is found.
        if switch_reason != "min_capital":
            if switch_reason in ("health", "cointegration_lost", "idle_timeout"):
                stats = get_pair_history_stats(curr_t1, curr_t2)
                if stats and stats.get("trades", 0) == 0:
                    unproven_reason = f"{switch_reason}_unproven"
                    add_to_hospital(curr_t1, curr_t2, reason=unproven_reason)
                    logger.warning(
                        "Pair moved to hospital (unproven): %s/%s reason=%s trades=0",
                        curr_t1,
                        curr_t2,
                        unproven_reason,
                    )
                elif is_good_pair_history(curr_t1, curr_t2):
                    add_to_hospital(curr_t1, curr_t2, reason=switch_reason)
                    if stats:
                        logger.warning(
                            "Pair moved to hospital: %s/%s reason=%s trades=%d wins=%d losses=%d win_rate=%.1f%% win=%.2f loss=%.2f",
                            curr_t1,
                            curr_t2,
                            switch_reason,
                            stats["trades"],
                            stats["wins"],
                            stats["losses"],
                            stats["win_rate"] * 100,
                            stats["win_usdt"],
                            stats["loss_usdt"],
                        )
                    else:
                        logger.warning(
                            "Pair moved to hospital: %s/%s reason=%s",
                            curr_t1,
                            curr_t2,
                            switch_reason,
                        )
                else:
                    bad_reason = f"{switch_reason}_bad_history"
                    add_to_graveyard(curr_t1, curr_t2, reason=bad_reason)
                    if stats:
                        logger.warning(
                            "Pair moved to graveyard: %s/%s reason=%s trades=%d wins=%d losses=%d win_rate=%.1f%% win=%.2f loss=%.2f",
                            curr_t1,
                            curr_t2,
                            bad_reason,
                            stats["trades"],
                            stats["wins"],
                            stats["losses"],
                            stats["win_rate"] * 100,
                            stats["win_usdt"],
                            stats["loss_usdt"],
                        )
                    else:
                        logger.warning(
                            "Pair moved to graveyard: %s/%s reason=%s",
                            curr_t1,
                            curr_t2,
                            bad_reason,
                        )
            else:
                add_to_graveyard(curr_t1, curr_t2, reason=switch_reason)

        msg = f"Switching from {curr_t1}/{curr_t2} to {next_t1}/{next_t2}"
        print(msg)
        logger.info(msg)

        if save_active_pair(next_t1, next_t2):
            logger.info("New pair saved to state/active_pair.json")
            try:
                from func_regime_state import reset_regime_state
                reset_regime_state(reason=f"pair_switch:{switch_reason}")
                logger.info("Regime state reset after pair switch.")
            except Exception as exc:
                logger.warning("Failed to reset regime state after pair switch: %s", exc)
            reset_health_failure(curr_t1, curr_t2)
            set_last_switch_time()
            emit_event(
                "pair_switch",
                payload={
                    "from_pair": f"{curr_t1}/{curr_t2}",
                    "to_pair": f"{next_t1}/{next_t2}",
                    "reason": switch_reason,
                    "status": SWITCH_RESULT_SWITCHED,
                    "health_score": health_score,
                },
                severity="info",
                flush=True,
                logger=logger,
            )
            return SWITCH_RESULT_SWITCHED

        logger.error("Failed to save new pair to state/active_pair.json")
        emit_event(
            "pair_switch",
            payload={
                "from_pair": f"{curr_t1}/{curr_t2}",
                "to_pair": f"{next_t1}/{next_t2}",
                "reason": switch_reason,
                "status": SWITCH_RESULT_HARD_STOP,
            },
            severity="error",
            logger=logger,
        )
        return SWITCH_RESULT_HARD_STOP
    except Exception as e:
        logger.error(f"Error switching pair: {e}")
        emit_event(
            "risk_alert",
            payload={
                "alert_type": "pair_switch_exception",
                "message": str(e),
                "pair": f"{ticker_1}/{ticker_2}",
            },
            severity="error",
            logger=logger,
        )
        return SWITCH_RESULT_HARD_STOP


def _calculate_cumulative_pnl(ticker_p, ticker_n, state, price_p=None, price_n=None):
    """
    Calculate cumulative P&L from open positions using fetched account state.
    """
    global _PNL_FALLBACK_ACTIVE
    global _PNL_FALLBACK_BASIS
    total_pnl = 0.0
    positions = []
    if isinstance(state, dict):
        positions = state.get("positions", [])

    used_positions = 0
    tickers = {ticker_p, ticker_n}
    pnl_info = {
        "source": "upl",
        "used_positions": 0,
        "fallback_legs": 0,
        "fallback_basis": "",
    }

    for pos in positions:
        if not isinstance(pos, dict):
            continue
        inst_id = pos.get("instId")
        if inst_id not in tickers:
            continue
        try:
            upl = float(pos.get("upl", 0) or 0)
        except (TypeError, ValueError):
            continue
        total_pnl += upl
        used_positions += 1

    if used_positions > 0:
        pnl_pct = (total_pnl / tradeable_capital_usdt * 100) if tradeable_capital_usdt > 0 else 0.0
        if total_pnl != 0.0 and _should_log_pnl(total_pnl):
            logger.info(
                "Cumulative P&L: %.2f USDT (%.2f%%) | Threshold: %.2f USDT",
                total_pnl,
                pnl_pct,
                -tradeable_capital_usdt * max_drawdown_pct,
            )
        pnl_info["source"] = "upl"
        pnl_info["used_positions"] = used_positions
        if _PNL_FALLBACK_ACTIVE:
            logger.info("PnL fallback cleared: positions detected")
            _PNL_FALLBACK_ACTIVE = False
            _PNL_FALLBACK_BASIS = ""
        return total_pnl, pnl_pct, pnl_info

    try:
        total_pnl = 0.0
        fallback_basis = []
        fallback_legs = 0
        # Fallback to price-based estimate if position UPL is unavailable.
        for ticker, price_override in [(ticker_p, price_p), (ticker_n, price_n)]:
            for direction in ["Long", "Short"]:
                entry_price, size = get_pos_data_from_state(state, ticker, direction=direction)
                if entry_price and size and size > 0:
                    current_price = price_override
                    basis = "override" if current_price else "last_trade"
                    if not current_price:
                        _, current_price = get_ticker_trade_liquidity(ticker, limit=1)

                    if current_price and current_price > 0:
                        if direction == "Long":
                            pnl = (current_price - entry_price) * size
                        else:
                            pnl = (entry_price - current_price) * size
                        total_pnl += pnl
                        fallback_legs += 1
                        fallback_basis.append(f"{ticker}:{basis}")
                        logger.debug(
                            "P&L %s %s: entry=%.4f current=%.4f size=%.6f pnl=%.2f",
                            ticker,
                            direction.upper(),
                            entry_price,
                            current_price,
                            size,
                            pnl,
                        )

        pnl_pct = (total_pnl / tradeable_capital_usdt * 100) if tradeable_capital_usdt > 0 else 0.0
        if total_pnl != 0.0 and _should_log_pnl(total_pnl):
            logger.info(
                "Cumulative P&L: %.2f USDT (%.2f%%) | Threshold: %.2f USDT",
                total_pnl,
                pnl_pct,
                -tradeable_capital_usdt * max_drawdown_pct,
            )
        pnl_info["source"] = "fallback"
        pnl_info["fallback_legs"] = fallback_legs
        pnl_info["fallback_basis"] = ",".join(fallback_basis)
        basis_value = pnl_info["fallback_basis"] or "last_trade"
        if (not _PNL_FALLBACK_ACTIVE) or (basis_value != _PNL_FALLBACK_BASIS):
            logger.info(
                "PnL fallback used: legs=%d basis=%s",
                fallback_legs,
                basis_value,
            )
            _PNL_FALLBACK_ACTIVE = True
            _PNL_FALLBACK_BASIS = basis_value
        else:
            logger.debug(
                "PnL fallback used: legs=%d basis=%s",
                fallback_legs,
                basis_value,
            )
        return total_pnl, pnl_pct, pnl_info
    except Exception as e:
        logger.error(f"Error calculating P&L: {e}")
        pnl_info["source"] = "error"
        return 0.0, 0.0, pnl_info


""" RUN STATBOT """
if __name__ == "__main__":
    # Manager process to handle restarts (especially on Windows)
    if os.getenv("STATBOT_MANAGED") != "1":
        monitor_proc = _start_molt_monitor()
        command_proc = _start_command_listener()
        start_ts = os.getenv("STATBOT_START_TS")
        if not start_ts:
            start_ts = str(time.time())
        while True:
            env = os.environ.copy()
            env["STATBOT_MANAGED"] = "1"
            env["STATBOT_START_TS"] = start_ts
            try:
                # Use sys.executable to ensure the same Python interpreter is used
                ret = subprocess.call([sys.executable] + sys.argv, env=env)
            except KeyboardInterrupt:
                # Handle Ctrl+C in the manager
                if monitor_proc and monitor_proc.poll() is None:
                    monitor_proc.terminate()
                if command_proc and command_proc.poll() is None:
                    command_proc.terminate()
                _log_run_end("manual_stop", "Ended by user", exit_code=0)
                save_status({"message": "Run ended by user"})
                _run_report_generator()
                sys.exit(0)
            
            if ret == 3:
                # Code 3 signals a pair switch and restart
                print("\n--- Restarting StatBot for New Pair ---\n")
                continue
            _run_report_generator()
            if monitor_proc and monitor_proc.poll() is None:
                monitor_proc.terminate()
            if command_proc and command_proc.poll() is None:
                command_proc.terminate()
            sys.exit(ret)

    _start_molt_monitor()
    _start_command_listener()

    # Wait for cointegrated pairs CSV if empty
    csv_path = Path(__file__).resolve().parent.parent / "Strategy" / "output" / "2_cointegrated_pairs.csv"
    max_wait_seconds = 600  # Wait up to 10 minutes for Strategy to populate CSV
    poll_interval = 10  # Check every 10 seconds
    starting_equity, balance_res, avail_bal, avail_eq = _capture_starting_equity_snapshot()

    if not csv_path.exists() or csv_path.stat().st_size <= 200:  # Empty or header-only
        logger.info("Cointegrated pairs CSV is empty or missing. Running Strategy to discover pairs...")
        print("Running Strategy to discover cointegrated pairs...")

        # Run Strategy to populate the CSV
        strategy_success = _run_strategy_at_startup()
        if not strategy_success:
            logger.error("Strategy failed to produce pairs. Exiting.")
            print("Strategy failed to produce pairs. Check logs for errors.")
            exit(1)

        # Verify CSV now has data
        if not csv_path.exists() or csv_path.stat().st_size <= 200:
            logger.error("Strategy completed but no pairs found. Check filters.")
            print("Strategy completed but no pairs found. Check filters.")
            exit(1)

        import pandas as pd
        df = pd.read_csv(csv_path)
        logger.info(f"CSV populated with {len(df)} pairs. Proceeding with startup...")
        print(f"Found {len(df)} cointegrated pairs. Starting bot...")

    # Validate ticker configuration at startup
    try:
        _validate_ticker_configuration()
    except AssertionError as e:
        logger.critical(str(e))
        print(str(e))
        exit(1)

    try:
        removed = cleanup_expired_graveyard()
        if removed:
            logger.info("Cleaned %d expired graveyard entries.", removed)
    except Exception as exc:
        logger.warning("Failed to cleanup graveyard entries: %s", exc)

    per_leg_capital = _get_per_leg_allocation()
    if not _pair_meets_min_capital(ticker_1, ticker_2, per_leg_capital):
        logger.warning(
            "Active pair fails min-capital filter (allocation=%.8f). Switching pair.",
            per_leg_capital,
        )
        set_last_switch_reason("min_capital")
        if lock_on_pair:
            logger.warning("lock_on_pair enabled; staying on current pair despite min-capital failure.")
        else:
            switch_result = _switch_to_next_pair(health_score=0, switch_reason="min_capital")
            if switch_result == SWITCH_RESULT_SWITCHED:
                logger.info("Restarting process via Subprocess Manager (exit code 3)...")
                print("Restarting to apply new pair...")
                sys.exit(3)
            logger.error("No suitable replacement pair found for min-capital filter. Hard stop.")
            sys.exit(1)
    
    # Run the bot
    print("StatBot initialised...")

    # Initialise variables
    status_dict = {"message": "starting..."}
    order_long = {}
    order_short = {}
    signal_sign_positive = False
    kill_switch = 0
    
    # Session tracking
    try:
        bot_start_time = float(os.getenv("STATBOT_START_TS") or "0")
    except ValueError:
        bot_start_time = time.time()
    # Preserve bot_start_time across pair switches - if STATBOT_START_TS is set and valid, use it
    if bot_start_time <= 0:
        bot_start_time = time.time()
    pair_start_time = time.time()
    last_health_check = time.time()  # First check on startup or after 1h
    last_status_update = time.time()
    signals_seen = 0
    trades_executed = 0
    prev_equity_usdt = None
    prev_total_pnl = None
    manual_close_clear_count = 0
    manual_close_clear_threshold = 3
    fee_tracker = FeeTracker()
    regime_router = RegimeRouter()
    regime_mode = regime_router.mode
    regime_eval_seconds = _get_regime_eval_seconds()
    regime_market_symbol = _get_regime_market_symbol()
    last_regime_eval_ts = 0.0
    last_regime_decision = None
    last_regime_gate_log_ts = 0.0
    strategy_router = StrategyRouter()
    strategy_mode = strategy_router.mode
    strategy_eval_seconds = _get_strategy_eval_seconds()
    last_strategy_eval_ts = 0.0
    last_strategy_decision = None
    last_strategy_gate_log_ts = 0.0
    _COINT_GATE_THRESHOLD = _get_coint_gate_threshold()
    logger.info(
        "Cointegration gate streak threshold set to: %d consecutive evaluations before pair switch",
        _COINT_GATE_THRESHOLD,
    )
    event_context = get_event_context(logger=logger)
    event_heartbeat_seconds = _get_event_heartbeat_seconds()
    last_event_heartbeat_ts = 0.0

    logger.info(
        "Event emitter status: mode=%s run_id=%s bot_instance_id=%s",
        event_context.get("mode", "off"),
        event_context.get("run_id", ""),
        event_context.get("bot_instance_id", ""),
    )

    if regime_mode == "off":
        logger.info("Regime router disabled (STATBOT_REGIME_ROUTER_MODE=off).")
    elif regime_mode == "shadow":
        logger.info(
            "Regime router enabled in SHADOW mode: evaluation/logging only (no execution changes)."
        )
    else:
        logger.warning("Regime router ACTIVE mode enabled: gate + policy enforcement is on.")

    if strategy_mode == "off":
        logger.info("Strategy router disabled (STATBOT_STRATEGY_ROUTER_MODE=off).")
    elif strategy_mode == "shadow":
        logger.info(
            "Strategy router enabled in SHADOW mode: evaluation/logging only (no execution changes)."
        )
    else:
        logger.warning("Strategy router ACTIVE mode enabled: strategy gate + policy enforcement is on.")

    # Retry startup balance capture once if the earliest snapshot was unavailable.
    if (not balance_res or balance_res.get("code") != "0") and starting_equity <= 0:
        starting_equity, balance_res, avail_bal, avail_eq = _capture_starting_equity_snapshot()

    # Save status
    save_status(status_dict)

    emit_event(
        "status_update",
        payload={
            "status": "startup_complete",
            "pair": f"{ticker_1}/{ticker_2}",
            "regime_mode": regime_mode,
            "strategy_mode": strategy_mode,
            "starting_equity_usdt": starting_equity,
        },
        severity="info",
        logger=logger,
    )

    # Set leverage in case forgotten to do so on the platform
    print("Setting leverage...")
    _set_leverage_for_ticker(signal_positive_ticker, default_leverage)
    _set_leverage_for_ticker(signal_negative_ticker, default_leverage)

    # Reject active pair if settle currency is mismatched or not allowed.
    try:
        settle_req_1 = _get_min_capital_for_ticker(ticker_1)
        settle_req_2 = _get_min_capital_for_ticker(ticker_2)
        settle_1 = settle_req_1["settle_ccy"]
        settle_2 = settle_req_2["settle_ccy"]
        if not _settle_filter_ok(ticker_1, ticker_2, settle_1, settle_2):
            if lock_on_pair:
                logger.error(
                    "Active pair fails settleCcy filter but lock_on_pair is enabled (pair=%s/%s).",
                    ticker_1,
                    ticker_2,
                )
            else:
                set_last_switch_reason("settle_ccy_filter")
                switch_result = _switch_to_next_pair(health_score=0, switch_reason="settle_ccy_filter")
                if switch_result == SWITCH_RESULT_SWITCHED:
                    logger.info("Restarting process via Subprocess Manager (exit code 3)...")
                    print("Restarting to apply new pair...")
                    sys.exit(3)
                if switch_result == SWITCH_RESULT_HARD_STOP:
                    logger.critical("No replacement pairs available for settleCcy filter. Hard stop.")
                    sys.exit(1)
                logger.error("Pair switch blocked. Will retry next cycle.")
    except Exception as exc:
        logger.warning("SettleCcy filter check failed at startup: %s", exc)

    # Cleanup any positions/orders for instruments outside the active pair
    try:
        acc_state_start = get_account_state()
        closed_count = close_non_active_positions(
            {signal_positive_ticker, signal_negative_ticker},
            state=acc_state_start,
            include_orders=True,
        )
        if closed_count:
            logger.warning("Closed %d non-active positions at startup.", closed_count)
    except Exception as exc:
        logger.warning("Failed to cleanup non-active positions at startup: %s", exc)
    
    # Check if we should start in monitoring mode (positions already open)
    is_p_open = open_position_confirmation(signal_positive_ticker)
    is_n_open = open_position_confirmation(signal_negative_ticker)
    if is_p_open or is_n_open:
        logger.info("Open positions detected at startup. Entering monitoring mode (kill_switch=1).")
        kill_switch = 1

    # Commence bot
    print("Seeking trades...")
    try:
        cycle_limit = int(os.getenv("STATBOT_MAX_CYCLES", max_cycles))
    except (TypeError, ValueError):
        cycle_limit = max_cycles
    if cycle_limit < 0:
        cycle_limit = 0
    max_uptime_hours = _get_max_uptime_hours()
    run_end_reason = None
    run_end_detail = ""
    run_end_exit_code = 0

    try:
        cycles_run = 0
        while True:
            cycles_run += 1
            current_time = time.time()
            
            # Pause - protect API
            time.sleep(3)
            current_time = time.time()
            _maybe_run_uptime_report(current_time, bot_start_time)
            if max_uptime_hours > 0:
                uptime_hours = (current_time - bot_start_time) / 3600.0
                if uptime_hours >= max_uptime_hours:
                    run_end_reason = "max_uptime"
                    run_end_detail = (
                        f"limit_hours={max_uptime_hours:.2f} uptime_hours={uptime_hours:.2f}"
                    )
                    status_dict["message"] = "Max uptime reached; exiting."
                    save_status(status_dict)
                    break

            # 1. Consolidated API Fetch (Position/Order Status)
            acc_state = get_account_state()
            is_p_open, is_p_active = check_inst_status(acc_state, signal_positive_ticker)
            is_n_open, is_n_active = check_inst_status(acc_state, signal_negative_ticker)

            checks_all = [is_p_open, is_n_open, is_p_active, is_n_active]
            is_manage_new_trades = not any(checks_all)
            in_position_now = bool(is_p_open or is_n_open)
            in_position_or_orders = not is_manage_new_trades

            if is_restricted_ticker(signal_positive_ticker) or is_restricted_ticker(signal_negative_ticker):
                if lock_on_pair:
                    logger.error(
                        "Compliance restricted ticker in active pair; lock_on_pair enabled (pair=%s/%s).",
                        ticker_1,
                        ticker_2,
                    )
                    status_dict["message"] = "Compliance restricted; lock_on_pair enabled"
                    save_status(status_dict)
                else:
                    if is_manage_new_trades:
                        logger.error(
                            "Compliance restricted ticker in active pair; switching (pair=%s/%s).",
                            ticker_1,
                            ticker_2,
                        )
                        status_dict["message"] = "Compliance restricted; switching pair..."
                        save_status(status_dict)
                        set_last_switch_reason("compliance_restricted")
                        switch_result = _switch_to_next_pair(health_score=0, switch_reason="compliance_restricted")
                        if switch_result == SWITCH_RESULT_SWITCHED:
                            logger.info("Restarting process via Subprocess Manager (exit code 3)...")
                            print("Restarting to apply new pair...")
                            sys.exit(3)
                        if switch_result == SWITCH_RESULT_HARD_STOP:
                            status_dict["message"] = "Hard stop: no replacement pairs available"
                            save_status(status_dict)
                            logger.critical("No replacement pairs available after compliance restriction. Hard stop.")
                            sys.exit(1)
                        logger.error("Pair switch blocked. Will retry next cycle.")
                    else:
                        logger.warning(
                            "Compliance restricted ticker in active pair, but positions/orders are open. "
                            "Deferring switch."
                        )

            if kill_switch == 1 and is_manage_new_trades:
                manual_close_clear_count += 1
                if manual_close_clear_count >= manual_close_clear_threshold:
                    logger.warning(
                        "No active positions/orders detected while monitoring. Resetting kill_switch to resume trading."
                    )
                    clear_entry_tracking()
                    clear_persistence_history()
                    kill_switch = 0
                    manual_close_clear_count = 0
            else:
                manual_close_clear_count = 0

            # 2. Market Data Fetch
            zscore_results = get_latest_zscore()
            zscore_series, _, metrics = zscore_results
            latest_zscore = None
            for z_val in reversed(zscore_series or []):
                if isinstance(z_val, (int, float)) and math.isfinite(z_val):
                    latest_zscore = float(z_val)
                    break
            price_p, price_n = metrics.get("price_1"), metrics.get("price_2")

            # 2a. ORDERBOOK DEAD CHECK: Switch if tickers are delisted/illiquid
            if metrics.get("orderbook_dead", False):
                if lock_on_pair:
                    logger.error("ðŸš¨ ORDERBOOK DEAD: Tickers appear delisted/illiquid, lock_on_pair enabled.")
                    status_dict["message"] = "Orderbook dead; lock_on_pair enabled"
                    save_status(status_dict)
                else:
                    logger.error("ðŸš¨ ORDERBOOK DEAD: Tickers appear delisted/illiquid. Switching pairs...")
                    status_dict["message"] = "Orderbook dead; switching pair..."
                    save_status(status_dict)

                    health_score = 0  # Force emergency override
                    set_last_switch_reason("orderbook_dead")
                    switch_result = _switch_to_next_pair(health_score=health_score, switch_reason="orderbook_dead")
                    if switch_result == SWITCH_RESULT_SWITCHED:
                        logger.info("Restarting process via Subprocess Manager (exit code 3)...")
                        print("Restarting to apply new pair...")
                        sys.exit(3)
                    if switch_result == SWITCH_RESULT_HARD_STOP:
                        status_dict["message"] = "Hard stop: no replacement pairs available"
                        save_status(status_dict)
                        logger.critical("No replacement pairs available after orderbook dead. Hard stop.")
                        sys.exit(1)
                    logger.error("Pair switch blocked. Will retry next cycle.")

            # 3. CIRCUIT BREAKER: Check cumulative P&L
            total_pnl, pnl_pct, pnl_info = _calculate_cumulative_pnl(
                signal_positive_ticker, signal_negative_ticker,
                acc_state, price_p, price_n
            )

            # Get account equity
            try:
                balance_res = _get_account_balance_safe()
                equity_usdt = 0.0
                if balance_res and balance_res.get("code") == "0":
                    details = balance_res.get("data", [{}])[0].get("details", [])
                    for det in details:
                        if det.get("ccy") == "USDT":
                            equity_usdt = float(det.get("eq", 0))
                            break
            except:
                equity_usdt = 0.0

            # Calculate session P&L (realized gains/losses)
            session_pnl = equity_usdt - starting_equity if starting_equity > 0 else 0.0
            session_pnl_pct = (session_pnl / starting_equity * 100) if starting_equity > 0 else 0.0

            _maybe_log_pnl_alert(total_pnl, pnl_pct, session_pnl, session_pnl_pct, equity_usdt)
            if (current_time - last_event_heartbeat_ts) >= event_heartbeat_seconds:
                emit_event(
                    "heartbeat",
                    payload={
                        "cycle": cycles_run,
                        "uptime_seconds": max(current_time - bot_start_time, 0.0),
                        "in_position": bool(in_position_or_orders),
                        "current_pair": f"{ticker_1}/{ticker_2}",
                        "equity_usdt": equity_usdt,
                        "session_pnl_usdt": session_pnl,
                        "session_pnl_pct": session_pnl_pct,
                        "regime": (
                            getattr(last_regime_decision, "regime", None)
                            if last_regime_decision is not None
                            else None
                        ),
                        "strategy": (
                            getattr(last_strategy_decision, "active_strategy", None)
                            if last_strategy_decision is not None
                            else None
                        ),
                    },
                    severity="info",
                    logger=logger,
                )
                last_event_heartbeat_ts = current_time

            market_candles = None
            liq_long = None
            liq_short = None
            if regime_mode != "off":
                should_eval_regime = (
                    last_regime_decision is None
                    or (current_time - last_regime_eval_ts) >= regime_eval_seconds
                )
                if should_eval_regime:
                    try:
                        market_raw = get_price_klines(
                            regime_market_symbol,
                            bar="1m",
                            limit=180,
                            use_start_time=False,
                            ascending=False,
                        )
                        market_candles = normalize_candlesticks(market_raw, ascending=True) if market_raw else []
                        liq_long = get_ticker_liquidity_analysis(signal_positive_ticker)
                        liq_short = get_ticker_liquidity_analysis(signal_negative_ticker)
                        # Treat fallback as risk signal only when we are actually in-position.
                        fallback_active = bool(
                            pnl_info
                            and pnl_info.get("source") == "fallback"
                            and in_position_now
                        )

                        per_leg_target_usdt = max(tradeable_capital_usdt * 0.5, 1.0)
                        entry_notional = get_entry_notional()
                        if entry_notional:
                            try:
                                entry_notional_val = float(entry_notional)
                            except (TypeError, ValueError):
                                entry_notional_val = 0.0
                            if entry_notional_val > 0:
                                per_leg_target_usdt = max(entry_notional_val * 0.5, 1.0)

                        regime_input = RegimeInput(
                            ts=current_time,
                            ticker_1=ticker_1,
                            ticker_2=ticker_2,
                            latest_zscore=latest_zscore,
                            z_metrics=metrics or {},
                            market_candles=market_candles,
                            liq_long=liq_long or {},
                            liq_short=liq_short or {},
                            per_leg_target_usdt=per_leg_target_usdt,
                            pnl_fallback_active=fallback_active,
                            session_drawdown_pct=session_pnl_pct,
                        )
                        decision = regime_router.evaluate(regime_input)
                        prev_regime = last_regime_decision.regime if last_regime_decision else decision.regime
                        last_regime_decision = decision
                        last_regime_eval_ts = current_time

                        reasons_joined = "|".join(decision.reason_codes) if decision.reason_codes else "none"
                        diagnostics = decision.diagnostics or {}
                        logger.info(
                            "REGIME_STATUS: mode=%s regime=%s candidate=%s conf=%.2f trend=%.3f vol_pct=%.2f depth=%.2f coint=%d fallback=%d reasons=%s",
                            decision.mode,
                            decision.regime,
                            decision.candidate_regime,
                            decision.confidence,
                            diagnostics.get("trend_strength", 0.0),
                            diagnostics.get("vol_percentile", 0.0),
                            diagnostics.get("liq_depth_ratio_min", 0.0),
                            int(metrics.get("coint_flag", 0)),
                            1 if fallback_active else 0,
                            reasons_joined,
                        )
                        if decision.changed and prev_regime != decision.regime:
                            logger.warning(
                                "REGIME_CHANGE: from=%s to=%s conf=%.2f hold=%.0fs reasons=%s",
                                prev_regime,
                                decision.regime,
                                decision.confidence,
                                diagnostics.get("hold_seconds", 0.0),
                                reasons_joined,
                            )

                        logger.info(
                            "REGIME_POLICY: regime=%s entry_z=%.2f entry_z_max=%.2f min_persist=%d min_liq=%.2f size_mult=%.2f",
                            decision.regime,
                            decision.entry_z,
                            decision.entry_z_max,
                            decision.min_persist_bars,
                            decision.min_liquidity_ratio,
                            decision.size_multiplier,
                        )
                        emit_event(
                            "regime_update",
                            payload={
                                "regime": decision.regime,
                                "previous_regime": prev_regime,
                                "candidate_regime": decision.candidate_regime,
                                "changed": bool(decision.changed and prev_regime != decision.regime),
                                "confidence": decision.confidence,
                                "allow_new_entries": bool(decision.allow_new_entries),
                                "reason_codes": list(decision.reason_codes or []),
                                "mode": decision.mode,
                                "pair": f"{ticker_1}/{ticker_2}",
                            },
                            severity="info",
                            logger=logger,
                        )
                        if regime_mode in ("shadow", "active") and not decision.allow_new_entries:
                            gate_reason = decision.reason_codes[0] if decision.reason_codes else "n/a"
                            logger.info(
                                "REGIME_GATE: regime=%s allow_new_entries=0 reason=%s mode=%s",
                                decision.regime,
                                gate_reason,
                                regime_mode,
                            )
                    except Exception as regime_exc:
                        logger.warning("Regime router evaluation failed: %s", regime_exc)
                        emit_event(
                            "risk_alert",
                            payload={
                                "alert_type": "regime_eval_failure",
                                "message": str(regime_exc),
                                "pair": f"{ticker_1}/{ticker_2}",
                            },
                            severity="warn",
                            logger=logger,
                        )

            if strategy_mode != "off":
                should_eval_strategy = (
                    last_strategy_decision is None
                    or (current_time - last_strategy_eval_ts) >= strategy_eval_seconds
                )
                if should_eval_strategy:
                    try:
                        # Pair spread history is not currently emitted by get_latest_zscore();
                        # use z-score history as the normalized mean-shift proxy for Phase 3.
                        spread_history = list(zscore_series or [])

                        strategy_input = StrategyInput(
                            ts=current_time,
                            regime_decision=last_regime_decision,
                            in_position=in_position_or_orders,
                            coint_flag=int(metrics.get("coint_flag", 0)),
                            zscore_history=list(zscore_series or []),
                            spread_history=spread_history or None,
                        )
                        strategy_decision = strategy_router.evaluate(strategy_input)
                        prev_strategy = (
                            last_strategy_decision.active_strategy
                            if last_strategy_decision
                            else strategy_decision.active_strategy
                        )
                        last_strategy_decision = strategy_decision
                        last_strategy_eval_ts = current_time

                        strategy_reasons = (
                            "|".join(strategy_decision.reason_codes)
                            if strategy_decision.reason_codes
                            else "none"
                        )
                        strategy_diag = strategy_decision.diagnostics or {}
                        logger.info(
                            "STRATEGY_STATUS: mode=%s active=%s desired=%s pending=%s pending_count=%d allow_new=%d coint=%d hold=%.0fs reasons=%s",
                            strategy_decision.mode,
                            strategy_decision.active_strategy,
                            strategy_decision.desired_strategy,
                            strategy_decision.pending_strategy or "none",
                            strategy_decision.pending_count,
                            1 if strategy_decision.allow_new_entries else 0,
                            int(metrics.get("coint_flag", 0)),
                            float(strategy_diag.get("hold_seconds", 0.0)),
                            strategy_reasons,
                        )

                        if strategy_decision.changed and prev_strategy != strategy_decision.active_strategy:
                            logger.warning(
                                "STRATEGY_CHANGE: from=%s to=%s reason=%s in_position=%d",
                                prev_strategy,
                                strategy_decision.active_strategy,
                                strategy_reasons,
                                1 if in_position_or_orders else 0,
                            )
                        elif (
                            strategy_decision.pending_strategy
                            and strategy_decision.pending_strategy != strategy_decision.active_strategy
                        ):
                            logger.info(
                                "STRATEGY_PENDING: active=%s desired=%s pending=%s count=%d in_position=%d",
                                strategy_decision.active_strategy,
                                strategy_decision.desired_strategy,
                                strategy_decision.pending_strategy,
                                strategy_decision.pending_count,
                                1 if in_position_or_orders else 0,
                            )

                        if "coint_gate" in strategy_decision.reason_codes:
                            logger.info(
                                "COINT_GATE: strategy=%s coint_flag=0 allow_new=0 mode=%s",
                                strategy_decision.active_strategy,
                                strategy_mode,
                            )
                            # Track cointegration gate streak and trigger switch if persistent
                            _COINT_GATE_STREAK += 1
                            logger.warning(
                                "Cointegration gate streak: %d/%d (threshold for pair switch)",
                                _COINT_GATE_STREAK,
                                _COINT_GATE_THRESHOLD,
                            )
                            if _COINT_GATE_STREAK >= _COINT_GATE_THRESHOLD:
                                logger.warning(
                                    "Cointegration lost for %d consecutive evaluations. Triggering pair switch (reason=cointegration_lost).",
                                    _COINT_GATE_STREAK,
                                )
                                switch_result = _switch_to_next_pair(
                                    health_score=0,
                                    switch_reason="cointegration_lost"
                                )
                                logger.info(
                                    "Pair switch triggered due to cointegration loss: result=%s",
                                    switch_result,
                                )
                                _COINT_GATE_STREAK = 0  # Reset after switch attempt
                        else:
                            # Reset cointegration gate streak when cointegration recovers
                            if _COINT_GATE_STREAK > 0:
                                logger.info(
                                    "Cointegration recovered. Resetting gate streak from %d to 0.",
                                    _COINT_GATE_STREAK,
                                )
                                _COINT_GATE_STREAK = 0
                        if "mean_shift_gate" in strategy_decision.reason_codes:
                            logger.info(
                                "MEAN_SHIFT_GATE: strategy=TREND_SPREAD shift_z=%.3f threshold=%.3f allow_new=0 mode=%s basis=%s",
                                float(strategy_diag.get("mean_shift_z", 0.0)),
                                float(strategy_diag.get("mean_shift_threshold", 0.0)),
                                strategy_mode,
                                str(strategy_diag.get("mean_shift_basis", "n/a")),
                            )
                        if strategy_diag.get("cooldown_triggered"):
                            logger.warning(
                                "STRATEGY_COOLDOWN_ON: strategy=%s reason=%s until_ts=%.3f",
                                strategy_decision.active_strategy,
                                str(strategy_diag.get("cooldown_reason") or "unknown"),
                                float(strategy_diag.get("cooldown_until_ts", 0.0) or 0.0),
                            )
                        if strategy_diag.get("cooldown_cleared"):
                            logger.info(
                                "STRATEGY_COOLDOWN_OFF: strategy=%s",
                                strategy_decision.active_strategy,
                            )
                        emit_event(
                            "strategy_update",
                            payload={
                                "strategy": strategy_decision.active_strategy,
                                "previous_strategy": prev_strategy,
                                "desired_strategy": strategy_decision.desired_strategy,
                                "pending_strategy": strategy_decision.pending_strategy,
                                "pending_count": strategy_decision.pending_count,
                                "changed": bool(
                                    strategy_decision.changed
                                    and prev_strategy != strategy_decision.active_strategy
                                ),
                                "allow_new_entries": bool(strategy_decision.allow_new_entries),
                                "reason_codes": list(strategy_decision.reason_codes or []),
                                "mode": strategy_decision.mode,
                                "pair": f"{ticker_1}/{ticker_2}",
                                "in_position": bool(in_position_or_orders),
                            },
                            severity="info",
                            logger=logger,
                        )
                    except Exception as strategy_exc:
                        logger.warning("Strategy router evaluation failed: %s", strategy_exc)
                        emit_event(
                            "risk_alert",
                            payload={
                                "alert_type": "strategy_eval_failure",
                                "message": str(strategy_exc),
                                "pair": f"{ticker_1}/{ticker_2}",
                            },
                            severity="warn",
                            logger=logger,
                        )

            # Check per-pair loss limit (2% of tradeable capital)
            per_pair_loss_limit_pct = 0.02  # 2% per pair before forcing switch
            if tradeable_capital_usdt > 0:
                pair_loss_threshold = tradeable_capital_usdt * per_pair_loss_limit_pct
                if total_pnl < -pair_loss_threshold:
                    pair_loss_pct = (total_pnl / tradeable_capital_usdt) * 100
                    logger.warning(
                        "âš ï¸  PER-PAIR LOSS LIMIT: Pair loss=%.2f USDT (%.2f%%) exceeds %.1f%% limit. Switching pair...",
                        total_pnl,
                        pair_loss_pct,
                        per_pair_loss_limit_pct * 100
                    )

                    # Close positions and switch to new pair
                    if kill_switch == 0:
                        logger.info("Closing positions due to per-pair loss limit...")
                        kill_switch = 2  # Trigger position close

                    emit_event(
                        "risk_alert",
                        payload={
                            "alert_type": "pair_loss_limit",
                            "message": "Per-pair loss limit exceeded",
                            "pair": f"{ticker_1}/{ticker_2}",
                            "pnl_usdt": total_pnl,
                            "pnl_pct": pair_loss_pct,
                        },
                        severity="warn",
                        logger=logger,
                    )
                    # Mark for pair switch after positions close
                    set_last_switch_reason("pair_loss_limit")

            # Log cycle with PnL, equity, and session performance
            pnl_emoji = "ðŸŸ¢" if total_pnl >= 0 else "ðŸ”´"
            session_emoji = "ðŸŸ¢" if session_pnl >= 0 else "ðŸ”´"
            uptime = _format_uptime(current_time - bot_start_time)
            logger.debug(
                "--- Cycle %s | %s/%s | Uptime: %s | %s PnL: %+0.2f USDT (%+0.2f%%) | "
                "Equity: %.2f USDT | %s Session: %+0.2f USDT (%+0.2f%%) ---",
                cycles_run,
                ticker_1,
                ticker_2,
                uptime,
                pnl_emoji,
                total_pnl,
                pnl_pct,
                equity_usdt,
                session_emoji,
                session_pnl,
                session_pnl_pct,
            )

            if prev_equity_usdt is not None and prev_total_pnl is not None:
                equity_delta = equity_usdt - prev_equity_usdt
                pair_pnl_delta = total_pnl - prev_total_pnl
                drift = equity_delta - pair_pnl_delta
                if abs(drift) >= 0.5:
                    other_positions = []
                    for pos in acc_state.get("positions", []):
                        if not isinstance(pos, dict):
                            continue
                        inst_id = pos.get("instId")
                        if inst_id in (signal_positive_ticker, signal_negative_ticker):
                            continue
                        pos_raw = pos.get("pos") or pos.get("position") or pos.get("size")
                        try:
                            pos_val = float(pos_raw)
                        except (TypeError, ValueError):
                            continue
                        if abs(pos_val) > 0:
                            other_positions.append(inst_id)
                    other_orders = []
                    pair_orders = 0
                    for ord_item in acc_state.get("orders", []):
                        if not isinstance(ord_item, dict):
                            continue
                        inst_id = ord_item.get("instId")
                        if not inst_id:
                            continue
                        if inst_id in (signal_positive_ticker, signal_negative_ticker):
                            pair_orders += 1
                        else:
                            other_orders.append(inst_id)
                    other_note = ""
                    if other_positions:
                        preview = ", ".join(other_positions[:5])
                        suffix = "..." if len(other_positions) > 5 else ""
                        other_note = f" other_positions={len(other_positions)} [{preview}{suffix}]"
                    if other_orders:
                        preview = ", ".join(other_orders[:5])
                        suffix = "..." if len(other_orders) > 5 else ""
                        other_note += f" other_orders={len(other_orders)} [{preview}{suffix}]"
                    if pair_orders:
                        other_note += f" pair_orders={pair_orders}"
                    if pnl_info and pnl_info.get("source") == "fallback":
                        basis = pnl_info.get("fallback_basis") or "last_trade"
                        other_note += f" pnl_source=fallback basis={basis}"
                    logger.warning(
                        "Equity delta %.2f USDT differs from pair PnL delta %.2f USDT by %.2f USDT.%s",
                        equity_delta,
                        pair_pnl_delta,
                        drift,
                        other_note,
                    )

            prev_equity_usdt = equity_usdt
            prev_total_pnl = total_pnl

            # Trading Status Update every minute
            if current_time - last_status_update >= STATUS_UPDATE_INTERVAL:
                time_in_pair_min = (current_time - pair_start_time) / 60
                uptime = _format_uptime(current_time - bot_start_time)
                logger.info("--- Trading Status Update ---")
                logger.info(f"Uptime: {uptime}")
                logger.info(f"Time in pair: {time_in_pair_min:.1f} min")
                logger.info(f"Signals seen: {signals_seen} | Trades: {trades_executed}")
                logger.info(
                    "PnL: %+0.2f USDT (%+0.2f%%) | Equity: %.2f USDT | Session: %+0.2f USDT (%+0.2f%%)",
                    total_pnl,
                    pnl_pct,
                    equity_usdt,
                    session_pnl,
                    session_pnl_pct,
                )
                if latest_zscore is not None:
                    logger.info("Z-Score: %+0.2f", latest_zscore)
                print(_green(f"Uptime: {uptime}"))
                last_status_update = current_time
            # Check session-wide drawdown (not just current pair)
            if starting_equity > 0 and equity_usdt is not None:
                session_drawdown = equity_usdt - starting_equity
                session_drawdown_pct = (session_drawdown / starting_equity) * 100

                # Circuit breaker based on session-wide loss
                max_session_loss_usdt = starting_equity * max_drawdown_pct
                if session_drawdown < -max_session_loss_usdt:
                    msg = f"âš ï¸  SESSION CIRCUIT BREAKER: Equity={equity_usdt:.2f} (started at {starting_equity:.2f}), Loss={session_drawdown:.2f} USDT ({session_drawdown_pct:.2f}%) exceeds session limit {max_drawdown_pct*100:.1f}%"
                    print(msg)
                    logger.critical(msg)
                    emit_event(
                        "risk_alert",
                        payload={
                            "alert_type": "session_circuit_breaker",
                            "message": msg,
                            "pair": f"{ticker_1}/{ticker_2}",
                            "equity_usdt": equity_usdt,
                            "session_drawdown_usdt": session_drawdown,
                            "session_drawdown_pct": session_drawdown_pct,
                        },
                        severity="critical",
                        logger=logger,
                    )
                    status_dict["message"] = "Session circuit breaker triggered - closing all positions"
                    save_status(status_dict)
                    close_all_positions(0)
                    run_end_reason = "session_circuit_breaker"
                    run_end_detail = (
                        f"session_loss={session_drawdown:.2f} session_pct={session_drawdown_pct:.2f} limit={max_drawdown_pct*100:.1f}%"
                    )
                    break

            # Also check current pair drawdown (legacy check)
            max_loss_allowed = tradeable_capital_usdt * max_drawdown_pct
            if total_pnl < -max_loss_allowed:
                msg = f"âš ï¸  PAIR CIRCUIT BREAKER: P&L={total_pnl:.2f} USDT ({pnl_pct:.2f}%) exceeds pair limit {max_drawdown_pct*100:.1f}%"
                print(msg)
                logger.warning(msg)
                emit_event(
                    "risk_alert",
                    payload={
                        "alert_type": "pair_circuit_breaker",
                        "message": msg,
                        "pair": f"{ticker_1}/{ticker_2}",
                        "pnl_usdt": total_pnl,
                        "pnl_pct": pnl_pct,
                    },
                    severity="warn",
                    logger=logger,
                )
                status_dict["message"] = "Pair circuit breaker triggered - closing all positions"
                save_status(status_dict)
                close_all_positions(0)
                run_end_reason = "pair_circuit_breaker"
                run_end_detail = (
                    f"pair_pnl={total_pnl:.2f} pair_pct={pnl_pct:.2f} max_drawdown_pct={max_drawdown_pct*100:.1f}"
                )
                break

            # Check if health check is due
            health_check_due = (current_time - last_health_check >= HEALTH_CHECK_INTERVAL)
            if health_check_due:
                last_health_check = current_time

            idle_timeout_min = _get_pair_idle_timeout_min()
            if idle_timeout_min > 0 and is_manage_new_trades and kill_switch == 0:
                time_in_pair_min = (current_time - pair_start_time) / 60
                if time_in_pair_min >= idle_timeout_min:
                    logger.warning(
                        "Pair idle timeout reached (%.1f min >= %.1f). Switching pair.",
                        time_in_pair_min,
                        idle_timeout_min,
                    )
                    if lock_on_pair:
                        logger.warning("lock_on_pair enabled; staying on current pair despite idle timeout.")
                    else:
                        status_dict["message"] = "Idle timeout; switching pair..."
                        save_status(status_dict)
                        set_last_switch_reason("idle_timeout")
                        switch_result = _switch_to_next_pair(
                            health_score=0,
                            switch_reason="idle_timeout",
                        )
                        if switch_result == SWITCH_RESULT_SWITCHED:
                            logger.info("Restarting process via Subprocess Manager (exit code 3)...")
                            print("Restarting to apply new pair...")
                            sys.exit(3)
                        if switch_result == SWITCH_RESULT_HARD_STOP:
                            status_dict["message"] = "Hard stop: no replacement pairs available"
                            save_status(status_dict)
                            logger.critical("No replacement pairs available after idle timeout. Hard stop.")
                            sys.exit(1)
                        logger.error("Pair switch blocked. Will retry next cycle.")

            # 4. Check for signal and place new trades
            if is_manage_new_trades and kill_switch == 0:
                blocked_by_regime = should_block_regime_entries(regime_mode, last_regime_decision)
                blocked_by_strategy = should_block_strategy_entries(strategy_mode, last_strategy_decision)
                if blocked_by_regime or blocked_by_strategy:
                    gate_reason = "n/a"
                    gate_regime = "unknown"
                    gate_strategy = "unknown"
                    if last_regime_decision is not None:
                        reasons = list(getattr(last_regime_decision, "reason_codes", []) or [])
                        if reasons:
                            gate_reason = reasons[0]
                        gate_regime = str(getattr(last_regime_decision, "regime", "unknown") or "unknown")
                    if last_strategy_decision is not None:
                        strategy_reasons = list(getattr(last_strategy_decision, "reason_codes", []) or [])
                        if blocked_by_strategy and strategy_reasons:
                            gate_reason = strategy_reasons[0]
                        gate_strategy = str(
                            getattr(last_strategy_decision, "active_strategy", "unknown") or "unknown"
                        )
                    status_dict["message"] = "Entry gate active; skipping new entries."
                    save_status(status_dict)
                    if blocked_by_regime and (current_time - last_regime_gate_log_ts) >= 60:
                        logger.warning(
                            "REGIME_GATE_ENFORCED: mode=active regime=%s reason=%s action=skip_new_entries",
                            gate_regime,
                            gate_reason,
                        )
                        emit_event(
                            "gate_enforced",
                            payload={
                                "gate_type": "regime",
                                "mode": regime_mode,
                                "regime": gate_regime,
                                "reason": gate_reason,
                                "action": "skip_new_entries",
                            },
                            severity="warn",
                            logger=logger,
                        )
                        last_regime_gate_log_ts = current_time
                    if blocked_by_strategy and (current_time - last_strategy_gate_log_ts) >= 60:
                        logger.warning(
                            "STRATEGY_GATE_ENFORCED: mode=active strategy=%s reason=%s action=skip_new_entries",
                            gate_strategy,
                            gate_reason,
                        )
                        emit_event(
                            "gate_enforced",
                            payload={
                                "gate_type": "strategy",
                                "mode": strategy_mode,
                                "strategy": gate_strategy,
                                "reason": gate_reason,
                                "action": "skip_new_entries",
                            },
                            severity="warn",
                            logger=logger,
                        )
                        last_strategy_gate_log_ts = current_time
                else:
                    status_dict["message"] = "Managing new trades..."
                    save_status(status_dict)
                    res_ks, sig_seen, tr_placed = manage_new_trades(
                        kill_switch,
                        health_check_due,
                        zscore_results,
                        regime_mode=regime_mode,
                        regime_decision=last_regime_decision,
                        strategy_mode=strategy_mode,
                        strategy_decision=last_strategy_decision,
                    )
                    kill_switch = res_ks
                    if sig_seen:
                        signals_seen += 1
                    if tr_placed:
                        trades_executed += 1
                        if equity_usdt is not None:
                            set_entry_equity(equity_usdt)
                        emit_event(
                            "trade_open",
                            payload={
                                "pair": f"{ticker_1}/{ticker_2}",
                                "side": "unknown",
                                "entry_z": latest_zscore,
                                "strategy": (
                                    getattr(last_strategy_decision, "active_strategy", None)
                                    if last_strategy_decision is not None
                                    else None
                                ),
                                "regime": (
                                    getattr(last_regime_decision, "regime", None)
                                    if last_regime_decision is not None
                                    else None
                                ),
                            },
                            severity="info",
                            logger=logger,
                        )
            
            # 5. Monitoring existing trades / Mean reversion exit
            if not is_manage_new_trades or kill_switch == 1:
                res_ks = monitor_exit(
                    kill_switch,
                    health_check_due,
                    zscore_results,
                    regime_mode=regime_mode,
                    regime_decision=last_regime_decision,
                    strategy_mode=strategy_mode,
                    strategy_decision=last_strategy_decision,
                )
                kill_switch = res_ks

            # Handle pair switch signal (e.g. health check failed)
            if kill_switch == 3:
                if lock_on_pair:
                    status_dict["message"] = "Pair swap blocked (lock_on_pair enabled)."
                    save_status(status_dict)
                    logger.info("Kill switch 3 blocked: lock_on_pair enabled. Staying on current pair.")
                    kill_switch = 0
                else:
                    status_dict["message"] = "Health check failed; switching pair..."
                    save_status(status_dict)
                    logger.info("Kill switch 3: Pair health degraded. Switching to next prospect...")

                    # Get the last health score for emergency override
                    health_score = get_last_health_score()
                    switch_reason = get_last_switch_reason() or "health"

                    switch_result = _switch_to_next_pair(
                        health_score=health_score,
                        switch_reason=switch_reason,
                    )
                    if switch_result == SWITCH_RESULT_SWITCHED:
                        logger.info("Restarting process via Subprocess Manager (exit code 3)...")
                        print("Restarting to apply new pair...")
                        # Exit with code 3 to signal the manager to restart
                        sys.exit(3)
                    if switch_result == SWITCH_RESULT_HARD_STOP:
                        status_dict["message"] = "Hard stop: no replacement pairs available"
                        save_status(status_dict)
                        logger.critical("No replacement pairs available after health switch. Hard stop.")
                        sys.exit(1)
                    logger.error("Pair switch blocked. Resetting kill_switch to 0.")
                    # If switch failed, reset kill_switch and wait before trying again
                    kill_switch = 0
                    time.sleep(10)


            # Close all active orders and positions
            if kill_switch == 2:
                status_dict["message"] = "Closing existing trades..."
                save_status(status_dict)

                # Use post-close realized equity as source of truth for trade outcome.
                blacklist_pair = False
                entry_equity = get_entry_equity()
                entry_time_ts = get_entry_time()
                entry_notional = get_entry_notional()
                entry_strategy = str(get_entry_strategy() or "").strip().upper()
                entry_regime = str(get_entry_regime() or "").strip().upper()
                if not entry_strategy and last_strategy_decision is not None:
                    entry_strategy = str(
                        getattr(last_strategy_decision, "active_strategy", "") or ""
                    ).strip().upper()
                if not entry_regime and last_regime_decision is not None:
                    entry_regime = str(
                        getattr(last_regime_decision, "regime", "") or ""
                    ).strip().upper()
                if not entry_strategy:
                    entry_strategy = "UNKNOWN"
                if not entry_regime:
                    entry_regime = "UNKNOWN"
                switch_reason_after_close = get_last_switch_reason() or ""
                force_switch_after_close = switch_reason_after_close in FORCED_SWITCH_EXIT_REASONS
                reconciliation = None
                pre_close_equity = equity_usdt
                pre_close_equity_change = None
                funding_fees = 0.0
                costs = None
                pre_fee_total = None
                post_fee_total = None
                actual_fee_delta = None

                # Pre-close diagnostics (estimate only; not used for trade classification).
                if entry_equity is not None and pre_close_equity is not None:
                    pre_close_equity_change = pre_close_equity - entry_equity

                # Capture pre-close fee snapshot from fills so we can isolate close-time fee delta.
                try:
                    fee_snapshot = fee_tracker.get_actual_fees_from_okx(
                        trade_session,
                        limit=_get_recon_fee_fill_limit(),
                        tickers=[ticker_1, ticker_2],
                    )
                    pre_fee_total = float(fee_snapshot.get("total_fees", 0.0) or 0.0)
                except Exception as fee_exc:
                    logger.debug("Fee snapshot before close unavailable: %s", fee_exc)

                # Fetch actual funding fees from OKX.
                funding_fees = fee_tracker.fetch_funding_fees(account_session, ticker_1, ticker_2)
                if funding_fees > 0:
                    logger.info("Funding fees fetched from OKX: %.4f USDT", funding_fees)

                if entry_notional:
                    costs = fee_tracker.record_trade_costs(entry_notional)
                    logger.info(
                        "Trade costs: entry_fee=%.4f exit_fee=%.4f slippage=%.4f total=%.4f",
                        costs["entry_fee"],
                        costs["exit_fee"],
                        costs["slippage"],
                        costs["total_costs"],
                    )
                if pre_close_equity_change is not None and total_pnl is not None:
                    pre_close_diff = pre_close_equity_change - total_pnl
                    if abs(pre_close_diff) > 0.10:  # 10 cents threshold
                        logger.info(
                            "Pre-close PnL estimate delta: position_pnl=%.2f pre_close_equity_change=%.2f diff=%.2f",
                            total_pnl,
                            pre_close_equity_change,
                            pre_close_diff,
                        )

                kill_switch = close_all_positions(kill_switch)

                post_equity_usdt = None
                try:
                    balance_res = _get_account_balance_safe()
                    if balance_res and balance_res.get("code") == "0":
                        details = balance_res.get("data", [{}])[0].get("details", [])
                        for det in details:
                            if det.get("ccy") == "USDT":
                                post_equity_usdt = float(det.get("eq", 0))
                                break
                except Exception:
                    post_equity_usdt = None

                # Capture post-close fee snapshot and isolate fee delta during close.
                if pre_fee_total is not None:
                    try:
                        fee_snapshot_after = fee_tracker.get_actual_fees_from_okx(
                            trade_session,
                            limit=_get_recon_fee_fill_limit(),
                            tickers=[ticker_1, ticker_2],
                        )
                        post_fee_total = float(fee_snapshot_after.get("total_fees", 0.0) or 0.0)
                        actual_fee_delta = max(post_fee_total - pre_fee_total, 0.0)
                        logger.info(
                            "Fee snapshot around close: pre=%.4f post=%.4f delta=%.4f",
                            pre_fee_total,
                            post_fee_total,
                            actual_fee_delta,
                        )
                    except Exception as fee_exc:
                        logger.debug("Fee snapshot after close unavailable: %s", fee_exc)

                # Realized trade PnL: prefer post-close equity delta vs entry equity.
                if entry_equity is not None and post_equity_usdt is not None:
                    actual_pnl = post_equity_usdt - entry_equity
                elif pre_close_equity_change is not None:
                    actual_pnl = pre_close_equity_change
                    logger.warning(
                        "Post-close equity unavailable; using pre-close equity delta for trade result."
                    )
                else:
                    actual_pnl = total_pnl
                    logger.warning(
                        "Entry/post-close equity unavailable; falling back to pair PnL for trade result."
                    )

                hold_minutes = None
                if entry_time_ts is not None:
                    try:
                        hold_minutes = max((time.time() - float(entry_time_ts)) / 60.0, 0.0)
                    except (TypeError, ValueError):
                        hold_minutes = None

                # Reconcile estimate vs realized result using per-trade costs.
                if actual_pnl is not None:
                    if pre_close_equity_change is not None:
                        reconciliation_trade_pnl = pre_close_equity_change
                        recon_basis = "pre_close_equity_delta"
                    elif total_pnl is not None:
                        reconciliation_trade_pnl = total_pnl
                        recon_basis = "position_pnl"
                    else:
                        reconciliation_trade_pnl = actual_pnl
                        recon_basis = "actual_pnl_fallback"

                    if recon_basis == "position_pnl" and (_PNL_FALLBACK_ACTIVE or _PNL_FALLBACK_BASIS):
                        recon_basis = f"position_pnl_fallback_{(_PNL_FALLBACK_BASIS or 'unknown')}"

                    est_entry_fee = float(costs.get("entry_fee", 0.0) or 0.0) if isinstance(costs, dict) else 0.0
                    est_exit_fee = float(costs.get("exit_fee", 0.0) or 0.0) if isinstance(costs, dict) else 0.0
                    est_roundtrip_slippage = float(costs.get("slippage", 0.0) or 0.0) if isinstance(costs, dict) else 0.0

                    if recon_basis.startswith("pre_close_equity_delta"):
                        fees_for_reconciliation = (
                            actual_fee_delta if actual_fee_delta is not None and actual_fee_delta > 0 else est_exit_fee
                        )
                        slippage_for_reconciliation = est_roundtrip_slippage * 0.5
                        funding_for_reconciliation = 0.0
                    else:
                        fees_for_reconciliation = (
                            actual_fee_delta
                            if actual_fee_delta is not None and actual_fee_delta > 0
                            else (est_entry_fee + est_exit_fee)
                        )
                        slippage_for_reconciliation = est_roundtrip_slippage
                        funding_for_reconciliation = float(funding_fees or 0.0)

                    recon_delta_warn_threshold = _get_recon_delta_warn_threshold_usdt(recon_basis)
                    recon_unexplained_warn_threshold = _get_recon_unexplained_warn_threshold_usdt(recon_basis)
                    recon_unexplained_pct_warn_threshold = _get_recon_unexplained_warn_threshold_pct()

                    reconciliation = fee_tracker.reconcile_equity_drift(
                        reconciliation_trade_pnl,
                        actual_pnl,
                        fees=fees_for_reconciliation,
                        slippage=slippage_for_reconciliation,
                        funding=funding_for_reconciliation,
                    )
                    logger.info(
                        "Equity reconciliation (post-close): trade_pnl=%.2f equity_change=%.2f diff=%.2f "
                        "fees=%.2f slippage=%.2f funding=%.2f unexplained=%.2f "
                        "basis=%s delta_th=%.2f unexplained_th=%.2f",
                        reconciliation["trade_pnl"],
                        reconciliation["equity_change"],
                        reconciliation["difference"],
                        reconciliation["fees"],
                        reconciliation["slippage"],
                        reconciliation["funding"],
                        reconciliation["unexplained"],
                        recon_basis,
                        recon_delta_warn_threshold,
                        recon_unexplained_warn_threshold,
                    )

                    if post_equity_usdt is not None:
                        pnl_diff = abs(reconciliation["difference"])
                        if pnl_diff > recon_delta_warn_threshold:
                            logger.warning(
                                "Large realized-vs-estimated PnL delta: basis=%s position_pnl=%.2f "
                                "realized_equity_change=%.2f diff=%.2f threshold=%.2f",
                                recon_basis,
                                reconciliation_trade_pnl,
                                actual_pnl,
                                pnl_diff,
                                recon_delta_warn_threshold,
                            )

                        unexplained_pct = (
                            abs(reconciliation["unexplained"] / reconciliation["difference"]) * 100
                            if reconciliation["difference"] != 0
                            else 0
                        )
                        if (
                            abs(reconciliation["unexplained"]) > recon_unexplained_warn_threshold
                            and unexplained_pct > recon_unexplained_pct_warn_threshold
                        ):
                            logger.warning(
                                "Large unexplained reconciliation component (post-close): %.2f USDT "
                                "(%.1f%% of difference) basis=%s threshold=%.2f pct_threshold=%.1f",
                                reconciliation["unexplained"],
                                unexplained_pct,
                                recon_basis,
                                recon_unexplained_warn_threshold,
                                recon_unexplained_pct_warn_threshold,
                            )

                is_win = actual_pnl > 0
                result_label = "WIN" if is_win else "LOSS"
                exit_reason = switch_reason_after_close or "normal"
                record_trade_result(is_win)
                try:
                    strategy_perf = record_strategy_trade_result(
                        entry_strategy,
                        actual_pnl,
                        regime_name=entry_regime,
                        hold_minutes=hold_minutes,
                        exit_reason=exit_reason,
                    )
                    logger.info(
                        "STRATEGY_PERF_UPDATE: strategy=%s trades=%d rolling=%d rolling_pnl=%.2f rolling_win_rate=%s",
                        entry_strategy,
                        int(strategy_perf.get("trades_total", 0) or 0),
                        int(strategy_perf.get("rolling_count", 0) or 0),
                        float(strategy_perf.get("rolling_pnl_usdt", 0.0) or 0.0),
                        (
                            f"{float(strategy_perf.get('rolling_win_rate_pct')):.2f}%"
                            if strategy_perf.get("rolling_win_rate_pct") is not None
                            else "n/a"
                        ),
                    )
                except Exception as strategy_state_exc:
                    logger.warning("Failed to persist strategy performance state: %s", strategy_state_exc)

                # Log funding fees from reconciliation
                funding_fees = reconciliation.get("funding", 0.0) if reconciliation else 0.0
                if abs(funding_fees) > 0.01:  # Log if > 1 cent
                    logger.info(f"Funding fees paid during trade: {funding_fees:.2f} USDT")

                hold_label = f"{hold_minutes:.2f}" if hold_minutes is not None else "n/a"
                logger.info(
                    "STRATEGY_TRADE_CLOSE: strategy=%s regime=%s result=%s pnl=%.2f hold_min=%s exit_reason=%s",
                    entry_strategy,
                    entry_regime,
                    result_label,
                    actual_pnl,
                    hold_label,
                    exit_reason,
                )
                logger.info(f"Trade result recorded: {result_label} (PNL: {actual_pnl:.2f} USDT)")

                # Use realized post-close metrics for alert output.
                alert_pnl = actual_pnl
                if tradeable_capital_usdt > 0:
                    alert_pnl_pct = (alert_pnl / tradeable_capital_usdt) * 100
                else:
                    alert_pnl_pct = 0.0
                alert_equity = post_equity_usdt if post_equity_usdt is not None else pre_close_equity
                alert_session_pnl = session_pnl
                alert_session_pnl_pct = session_pnl_pct
                if alert_equity is not None and starting_equity > 0:
                    alert_session_pnl = alert_equity - starting_equity
                    alert_session_pnl_pct = (alert_session_pnl / starting_equity) * 100

                # Update pair history with realized PnL.
                history_pnl = actual_pnl
                if record_pair_trade_result(ticker_1, ticker_2, history_pnl):
                    stats = get_pair_history_stats(ticker_1, ticker_2)
                    if stats:
                        logger.info(
                            "Pair history updated: %s/%s trades=%d wins=%d losses=%d win_rate=%.1f%% win=%.2f loss=%.2f",
                            ticker_1,
                            ticker_2,
                            stats["trades"],
                            stats["wins"],
                            stats["losses"],
                            stats["win_rate"] * 100,
                            stats["win_usdt"],
                            stats["loss_usdt"],
                        )
                        if should_blacklist_pair(ticker_1, ticker_2):
                            add_to_graveyard(ticker_1, ticker_2, reason="bad_history")
                            set_last_switch_reason("bad_history")
                            blacklist_pair = True
                            logger.warning(
                                "Pair blacklisted: %s/%s trades=%d wins=%d losses=%d win_rate=%.1f%% win=%.2f loss=%.2f",
                                ticker_1,
                                ticker_2,
                                stats["trades"],
                                stats["wins"],
                                stats["losses"],
                                stats["win_rate"] * 100,
                                stats["win_usdt"],
                                stats["loss_usdt"],
                            )

                logger.warning(
                    "!!! PNL_ALERT !!! Trade closed %s | PnL %+0.2f USDT (%+0.2f%%) | Equity %.2f USDT | Session %+0.2f USDT (%+0.2f%%) | Strategy %s | Regime %s",
                    result_label,
                    alert_pnl,
                    alert_pnl_pct,
                    alert_equity if alert_equity is not None else 0.0,
                    alert_session_pnl,
                    alert_session_pnl_pct,
                    entry_strategy,
                    entry_regime,
                )
                emit_event(
                    "trade_close",
                    payload={
                        "pair": f"{ticker_1}/{ticker_2}",
                        "pnl_usdt": alert_pnl,
                        "pnl_pct": alert_pnl_pct,
                        "strategy": entry_strategy,
                        "regime": entry_regime,
                        "hold_minutes": hold_minutes,
                        "exit_reason": exit_reason,
                        "exit_tier": exit_reason if str(exit_reason).startswith("exit_tier_") else None,
                    },
                    severity="info" if alert_pnl >= 0 else "warn",
                    logger=logger,
                )

                if blacklist_pair:
                    if lock_on_pair:
                        logger.warning("Pair blacklisted but lock_on_pair enabled; staying on current pair.")
                    else:
                        status_dict["message"] = "Pair blacklisted; switching..."
                        save_status(status_dict)
                        switch_result = _switch_to_next_pair(
                            health_score=0,
                            switch_reason="bad_history",
                        )
                        if switch_result == SWITCH_RESULT_SWITCHED:
                            logger.info("Restarting process via Subprocess Manager (exit code 3)...")
                            print("Restarting to apply new pair...")
                            sys.exit(3)
                        if switch_result == SWITCH_RESULT_HARD_STOP:
                            status_dict["message"] = "Hard stop: no replacement pairs available"
                            save_status(status_dict)
                            logger.critical("No replacement pairs available after blacklist. Hard stop.")
                            sys.exit(1)
                        logger.error("Pair switch blocked after blacklist.")
                elif force_switch_after_close:
                    if lock_on_pair:
                        logger.warning(
                            "Forced post-exit pair switch blocked by lock_on_pair (reason=%s).",
                            switch_reason_after_close,
                        )
                    else:
                        status_dict["message"] = f"Post-exit switch ({switch_reason_after_close}); switching pair..."
                        save_status(status_dict)
                        switch_result = _switch_to_next_pair(
                            health_score=0,
                            switch_reason=switch_reason_after_close,
                        )
                        if switch_result == SWITCH_RESULT_SWITCHED:
                            logger.info("Restarting process via Subprocess Manager (exit code 3)...")
                            print("Restarting to apply new pair...")
                            sys.exit(3)
                        if switch_result == SWITCH_RESULT_HARD_STOP:
                            status_dict["message"] = "Hard stop: no replacement pairs available"
                            save_status(status_dict)
                            logger.critical("No replacement pairs available after forced post-exit switch.")
                            sys.exit(1)
                        logger.error(
                            "Post-exit forced switch blocked (reason=%s).",
                            switch_reason_after_close,
                        )
                    set_last_switch_reason("")

                # Sleep for 5 seconds
                time.sleep(5)

            if cycle_limit and cycles_run >= cycle_limit:
                status_dict["message"] = "Max cycles reached; exiting."
                save_status(status_dict)
                run_end_reason = "max_cycles"
                run_end_detail = f"cycles={cycles_run}"
                break
    except KeyboardInterrupt:
        run_end_reason = "manual_stop"
        run_end_detail = "Ended by user"
        run_end_exit_code = 0
        emit_event(
            "status_update",
            payload={"status": "manual_stop", "message": "Ended by user"},
            severity="info",
            logger=logger,
        )
    except Exception as e:
        logger.critical(f"UNHANDLED EXCEPTION in main loop: {e}", exc_info=True)
        print(f"CRITICAL ERROR: {e}")
        status_dict["message"] = f"Crashed: {e}"
        save_status(status_dict)
        emit_event(
            "risk_alert",
            payload={
                "alert_type": "unhandled_exception",
                "message": str(e),
                "pair": f"{ticker_1}/{ticker_2}",
            },
            severity="critical",
            logger=logger,
        )
        run_end_reason = "error"
        run_end_detail = str(e)
        run_end_exit_code = 1
    if run_end_reason:
        _log_run_end(run_end_reason, run_end_detail, exit_code=run_end_exit_code)
        status_dict["message"] = f"Run ended: {run_end_reason}"
        save_status(status_dict)
        emit_event(
            "status_update",
            payload={
                "status": "run_end",
                "reason": run_end_reason,
                "detail": run_end_detail,
                "exit_code": run_end_exit_code,
            },
            severity="info" if run_end_exit_code == 0 else "warn",
            logger=logger,
        )
        flush_events(force=True, logger=logger)
        _run_report_generator()
        sys.exit(run_end_exit_code)
