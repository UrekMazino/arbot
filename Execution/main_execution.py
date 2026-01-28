# Remove Pandas Future Warnings
import os
import warnings
import logging
import math
import time
import sys
import subprocess
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
    account_session,
    lock_on_pair,
    allowed_settle_ccy
)
from func_position_calls import (
    open_position_confirmation, 
    active_position_confirmation,
    get_account_state,
    check_inst_status,
    get_pos_data_from_state
)
from func_price_calls import get_ticker_trade_liquidity
from func_trade_management import manage_new_trades, monitor_exit, RISK_PER_TRADE_PCT
from func_get_zscore import get_latest_zscore
from func_execution_calls import set_leverage, get_min_capital_requirements
from func_close_positions import close_all_positions, get_position_info, close_non_active_positions
from func_save_status import save_status
from fee_tracker import FeeTracker
from func_pair_state import (
    add_to_graveyard,
    is_in_graveyard,
    can_switch,
    set_last_switch_time,
    get_last_switch_time,
    record_trade_result,
    get_last_health_score,
    get_last_switch_reason,
    set_last_switch_reason,
    get_min_capital_cooldown,
    set_min_capital_cooldown,
    clear_entry_tracking,
    clear_persistence_history,
    set_entry_equity,
    get_entry_equity,
    get_entry_notional,
    is_restricted_ticker
)

# Setup logging
logger = get_logger("main_execution")

SWITCH_RESULT_SWITCHED = "switched"
SWITCH_RESULT_BLOCKED = "blocked"
SWITCH_RESULT_HARD_STOP = "hard_stop"
STRATEGY_REFRESH_SLEEP_SECONDS = 300


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
        f"❌ STARTUP ERROR: ticker_1 must be non-empty string. Got: {ticker_1}"
    )
    assert ticker_2 and isinstance(ticker_2, str), (
        f"❌ STARTUP ERROR: ticker_2 must be non-empty string. Got: {ticker_2}"
    )
    
    # Check tickers are different
    assert ticker_1 != ticker_2, (
        f"❌ STARTUP ERROR: ticker_1 and ticker_2 must be different. Both are: {ticker_1}"
    )
    
    # Check signal tickers are configured
    assert signal_positive_ticker and isinstance(signal_positive_ticker, str), (
        f"❌ STARTUP ERROR: signal_positive_ticker must be non-empty string. Got: {signal_positive_ticker}"
    )
    assert signal_negative_ticker and isinstance(signal_negative_ticker, str), (
        f"❌ STARTUP ERROR: signal_negative_ticker must be non-empty string. Got: {signal_negative_ticker}"
    )
    
    # Check signal tickers are different
    assert signal_positive_ticker != signal_negative_ticker, (
        f"❌ STARTUP ERROR: signal_positive_ticker and signal_negative_ticker must be different. "
        f"Both are: {signal_positive_ticker}"
    )
    
    # Check signal tickers match configured tickers
    valid_tickers = {ticker_1, ticker_2}
    assert signal_positive_ticker in valid_tickers, (
        f"❌ STARTUP ERROR: signal_positive_ticker '{signal_positive_ticker}' must be one of "
        f"['{ticker_1}', '{ticker_2}']"
    )
    assert signal_negative_ticker in valid_tickers, (
        f"❌ STARTUP ERROR: signal_negative_ticker '{signal_negative_ticker}' must be one of "
        f"['{ticker_1}', '{ticker_2}']"
    )
    
    logger.info(
        "✓ Ticker configuration validated: ticker_1=%s, ticker_2=%s, "
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
    try:
        balance_res = account_session.get_account_balance()
        if balance_res.get("code") != "0":
            return 0.0
        details = balance_res.get("data", [{}])[0].get("details", [])
        for det in details:
            if det.get("ccy") == "USDT":
                return float(det.get("availBal", 0))
    except Exception as exc:
        logger.warning("Failed to fetch available USDT: %s", exc)
    return 0.0


def _get_equity_usdt():
    try:
        balance_res = account_session.get_account_balance()
        if balance_res.get("code") != "0":
            return 0.0
        details = balance_res.get("data", [{}])[0].get("details", [])
        for det in details:
            if det.get("ccy") == "USDT":
                return float(det.get("eq", 0))
    except Exception as exc:
        logger.warning("Failed to fetch equity USDT: %s", exc)
    return 0.0


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
    if initial_capital_usdt * 2 > effective_capital:
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
0 → 0: Normal cycle, no signal or cointegration failed
        → returns 0 to main_execution

0 → 1: Hot trigger activated + cointegration valid + Z-score extreme
        → manage_new_trades() returns 1 after placing orders
        → main_execution sees 1, calls close_all_positions()

1 → 2: Close operation complete
        → close_all_positions() returns 2
        → circuit breaker also returns 2
        → hard stop/regime break also returns 2
        → main_execution exits loop

0 → 3: Health check failed (Low correlation, trending spread, etc.)
        → manage_new_trades() returns 3
        → main_execution sees 3, calls _switch_to_next_pair()
"""


def _switch_to_next_pair(health_score=None, switch_reason="health"):
    """
    Read the cointegrated pairs from Strategy folder and switch to the next one.
    Includes Graveyard and Cooldown checks with emergency override for critical health.

    Args:
        health_score: Current pair health score (0-100). If below 25, overrides cooldown.
    """
    import pandas as pd
    from pathlib import Path

    if lock_on_pair:
        logger.warning(
            "Pair switch requested (reason=%s) but lock_on_pair is enabled. Staying on current pair.",
            switch_reason,
        )
        return SWITCH_RESULT_BLOCKED

    # 1. Check Cooldown with emergency override
    last_switch = get_last_switch_time()
    elapsed = (time.time() - last_switch) / 3600

    if not can_switch(cooldown_hours=24, health_score=health_score, emergency_threshold=40):
        logger.warning("Switch aborted: Cooldown active (%.1fh elapsed, 24h required)", elapsed)
        if health_score is not None:
            logger.warning("Health score: %s/100 (emergency override requires < 40)", health_score)
        return SWITCH_RESULT_BLOCKED

    # Log if emergency override was used
    if health_score is not None and health_score < 40:
        logger.warning(
            "EMERGENCY OVERRIDE: Health score %s < 40, bypassing cooldown (%.1fh elapsed)",
            health_score,
            elapsed,
        )
    elif elapsed < 24:
        logger.info("Cooldown bypassed but health not critical: %s/100", health_score)

    logger.info("Attempting to switch to next pair (reason=%s)...", switch_reason)
    csv_path = Path(__file__).resolve().parent.parent / "Strategy" / "2_cointegrated_pairs.csv"

    per_leg_capital = _get_per_leg_allocation()
    logger.info("Per-leg allocation for min-capital filter: %.8f", per_leg_capital)

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
            min_equity = _parse_min_equity(row.get("min_equity_recommended"))
            pairs.append({"sym_1": sym_1, "sym_2": sym_2, "min_equity": min_equity})
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

        for i in range(1, len(pairs)):
            idx = (curr_idx + i) % len(pairs)
            pair = pairs[idx]
            t1, t2 = pair["sym_1"], pair["sym_2"]
            if is_in_graveyard(t1, t2):
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
            add_to_graveyard(curr_t1, curr_t2, reason=switch_reason)

        msg = f"Switching from {curr_t1}/{curr_t2} to {next_t1}/{next_t2}"
        print(msg)
        logger.info(msg)

        if save_active_pair(next_t1, next_t2):
            logger.info("New pair saved to active_pair.json")
            set_last_switch_time()
            return SWITCH_RESULT_SWITCHED

        logger.error("Failed to save new pair to active_pair.json")
        return SWITCH_RESULT_HARD_STOP
    except Exception as e:
        logger.error(f"Error switching pair: {e}")
        return SWITCH_RESULT_HARD_STOP


def _calculate_cumulative_pnl(ticker_p, ticker_n, state, price_p=None, price_n=None):
    """
    Calculate cumulative P&L from open positions using fetched account state.
    """
    total_pnl = 0.0
    positions = []
    if isinstance(state, dict):
        positions = state.get("positions", [])

    used_positions = 0
    tickers = {ticker_p, ticker_n}

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
        if total_pnl != 0.0:
            logger.info(
                "Cumulative P&L: %.2f USDT (%.2f%%) | Threshold: %.2f USDT",
                total_pnl,
                pnl_pct,
                -tradeable_capital_usdt * max_drawdown_pct,
            )
        return total_pnl, pnl_pct

    try:
        total_pnl = 0.0
        # Fallback to price-based estimate if position UPL is unavailable.
        for ticker, price_override in [(ticker_p, price_p), (ticker_n, price_n)]:
            for direction in ["Long", "Short"]:
                entry_price, size = get_pos_data_from_state(state, ticker, direction=direction)
                if entry_price and size and size > 0:
                    current_price = price_override
                    if not current_price:
                        _, current_price = get_ticker_trade_liquidity(ticker, limit=1)

                    if current_price and current_price > 0:
                        if direction == "Long":
                            pnl = (current_price - entry_price) * size
                        else:
                            pnl = (entry_price - current_price) * size
                        total_pnl += pnl
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
        if total_pnl != 0.0:
            logger.info(
                "Cumulative P&L: %.2f USDT (%.2f%%) | Threshold: %.2f USDT",
                total_pnl,
                pnl_pct,
                -tradeable_capital_usdt * max_drawdown_pct,
            )
        return total_pnl, pnl_pct
    except Exception as e:
        logger.error(f"Error calculating P&L: {e}")
        return 0.0, 0.0


""" RUN STATBOT """
if __name__ == "__main__":
    # Manager process to handle restarts (especially on Windows)
    if os.getenv("STATBOT_MANAGED") != "1":
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
                sys.exit(0)
            
            if ret == 3:
                # Code 3 signals a pair switch and restart
                print("\n--- Restarting StatBot for New Pair ---\n")
                continue
            sys.exit(ret)

    # Validate ticker configuration at startup
    try:
        _validate_ticker_configuration()
    except AssertionError as e:
        logger.critical(str(e))
        print(str(e))
        exit(1)

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
        bot_start_time = float(os.getenv("STATBOT_START_TS") or "")
    except ValueError:
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

    # Capture starting equity for session P&L tracking
    starting_equity = 0.0
    try:
        balance_res = account_session.get_account_balance()
        if balance_res.get("code") == "0":
            details = balance_res.get("data", [{}])[0].get("details", [])
            for det in details:
                if det.get("ccy") == "USDT":
                    starting_equity = float(det.get("eq", 0))
                    break
        logger.info(f"📊 Starting equity: {starting_equity:.2f} USDT")
    except Exception as e:
        logger.warning(f"Failed to capture starting equity: {e}")

    # Save status
    save_status(status_dict)

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

    try:
        cycles_run = 0
        while True:
            cycles_run += 1
            current_time = time.time()
            
            # Pause - protect API
            time.sleep(3)

            # 1. Consolidated API Fetch (Position/Order Status)
            acc_state = get_account_state()
            is_p_open, is_p_active = check_inst_status(acc_state, signal_positive_ticker)
            is_n_open, is_n_active = check_inst_status(acc_state, signal_negative_ticker)

            checks_all = [is_p_open, is_n_open, is_p_active, is_n_active]
            is_manage_new_trades = not any(checks_all)

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
            _, _, metrics = zscore_results
            price_p, price_n = metrics.get("price_1"), metrics.get("price_2")

            # 2a. ORDERBOOK DEAD CHECK: Switch if tickers are delisted/illiquid
            if metrics.get("orderbook_dead", False):
                if lock_on_pair:
                    logger.error("🚨 ORDERBOOK DEAD: Tickers appear delisted/illiquid, lock_on_pair enabled.")
                    status_dict["message"] = "Orderbook dead; lock_on_pair enabled"
                    save_status(status_dict)
                else:
                    logger.error("🚨 ORDERBOOK DEAD: Tickers appear delisted/illiquid. Switching pairs...")
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
            total_pnl, pnl_pct = _calculate_cumulative_pnl(
                signal_positive_ticker, signal_negative_ticker,
                acc_state, price_p, price_n
            )

            # Get account equity
            try:
                balance_res = account_session.get_account_balance()
                equity_usdt = 0.0
                if balance_res.get("code") == "0":
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

            # Log cycle with PnL, equity, and session performance
            pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
            session_emoji = "🟢" if session_pnl >= 0 else "🔴"
            uptime = _format_uptime(current_time - bot_start_time)
            logger.info(f"--- Cycle {cycles_run} | {ticker_1}/{ticker_2} | Uptime: {uptime} | {pnl_emoji} PnL: {total_pnl:+.2f} USDT ({pnl_pct:+.2f}%) | Equity: {equity_usdt:.2f} USDT | {session_emoji} Session: {session_pnl:+.2f} USDT ({session_pnl_pct:+.2f}%) ---")

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
                    other_note = ""
                    if other_positions:
                        preview = ", ".join(other_positions[:5])
                        suffix = "..." if len(other_positions) > 5 else ""
                        other_note = f" other_positions={len(other_positions)} [{preview}{suffix}]"
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
                print(_green(f"Uptime: {uptime}"))
                last_status_update = current_time
            max_loss_allowed = tradeable_capital_usdt * max_drawdown_pct
            
            if total_pnl < -max_loss_allowed:
                msg = f"⚠️  CIRCUIT BREAKER TRIGGERED: P&L={total_pnl:.2f} USDT ({pnl_pct:.2f}%) exceeds max drawdown {max_drawdown_pct*100:.1f}%"
                print(msg)
                logger.warning(msg)
                status_dict["message"] = "Circuit breaker triggered - closing all positions"
                save_status(status_dict)
                close_all_positions(0)
                break

            # Check if health check is due
            health_check_due = (current_time - last_health_check >= HEALTH_CHECK_INTERVAL)
            if health_check_due:
                last_health_check = current_time

            # 4. Check for signal and place new trades
            if is_manage_new_trades and kill_switch == 0:
                status_dict["message"] = "Managing new trades..."
                save_status(status_dict)
                res_ks, sig_seen, tr_placed = manage_new_trades(kill_switch, health_check_due, zscore_results)
                kill_switch = res_ks
                if sig_seen: signals_seen += 1
                if tr_placed:
                    trades_executed += 1
                    if equity_usdt is not None:
                        set_entry_equity(equity_usdt)
            
            # 5. Monitoring existing trades / Mean reversion exit
            if not is_manage_new_trades or kill_switch == 1:
                res_ks = monitor_exit(kill_switch, health_check_due, zscore_results)
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
                
                # Phase 3: Record trade result before closing
                # total_pnl was calculated at the start of the loop
                is_win = total_pnl > 0
                entry_equity = get_entry_equity()
                entry_notional = get_entry_notional()
                if entry_equity is not None and equity_usdt is not None and entry_notional:
                    equity_change = equity_usdt - entry_equity
                    costs = fee_tracker.record_trade_costs(entry_notional)
                    reconciliation = fee_tracker.reconcile_equity_drift(total_pnl, equity_change)
                    logger.info(
                        "Trade costs: entry_fee=%.4f exit_fee=%.4f slippage=%.4f total=%.4f",
                        costs["entry_fee"],
                        costs["exit_fee"],
                        costs["slippage"],
                        costs["total_costs"],
                    )
                    logger.info(
                        "Equity reconciliation: trade_pnl=%.2f equity_change=%.2f diff=%.2f fees=%.2f "
                        "slippage=%.2f funding=%.2f unexplained=%.2f",
                        reconciliation["trade_pnl"],
                        reconciliation["equity_change"],
                        reconciliation["difference"],
                        reconciliation["fees"],
                        reconciliation["slippage"],
                        reconciliation["funding"],
                        reconciliation["unexplained"],
                    )
                record_trade_result(is_win)
                logger.info(f"Trade result recorded: {'WIN' if is_win else 'LOSS'} (PNL: {total_pnl:.2f} USDT)")
                
                kill_switch = close_all_positions(kill_switch)

                # Sleep for 5 seconds
                time.sleep(5)

            if cycle_limit and cycles_run >= cycle_limit:
                status_dict["message"] = "Max cycles reached; exiting."
                save_status(status_dict)
                break
    except Exception as e:
        logger.critical(f"UNHANDLED EXCEPTION in main loop: {e}", exc_info=True)
        print(f"CRITICAL ERROR: {e}")
        status_dict["message"] = f"Crashed: {e}"
        save_status(status_dict)
