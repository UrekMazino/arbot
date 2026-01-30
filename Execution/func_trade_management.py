import os
from scipy.stats import false_discovery_control

from config_execution_api import (
    account_session,
    signal_positive_ticker,
    signal_negative_ticker,
    ENTRY_Z,
    EXIT_Z,
    MIN_PERSIST_BARS,
    tradeable_capital_usdt,
    limit_order_basis,
    stop_loss_fail_safe,
    P_VALUE_CRITICAL,
    ZERO_CROSSINGS_MIN,
    CORRELATION_MIN,
    TREND_CRITICAL,
    Z_SCORE_CRITICAL,
    lock_on_pair,
    td_mode,
)

from func_pair_state import (
    get_consecutive_losses,
    set_last_health_score,
    set_last_switch_reason,
    set_min_capital_cooldown,
    add_restricted_ticker,
    is_restricted_ticker,
    get_last_switch_time,
    record_health_failure,
)

# Risk management thresholds
ZSCORE_HARD_STOP = 2.5  # Hard stop-loss if Z-score exceeds this (regime break detection)
ZSCORE_EXIT_TARGET = 0.05  # Exit at mean reversion with small buffer for fees (~0.07% round-trip)
RISK_PER_TRADE_PCT = 0.02  # 2% of total capital risked per trade
PARTIAL_EXIT_HEALTH_THRESHOLD = 60
PARTIAL_EXIT_MINUTES = 30
Z_STALL_BASE_WINDOW_SECONDS = 3600
Z_STALL_VOLATILITY_ACCEL_RATIO = 1.5
Z_STALL_EARLY_GRACE_MINUTES = 30
Z_STALL_LATE_STRICT_MINUTES = 120
Z_STALL_TRIGGER_ABS = 1.5
Z_STALL_WARN_ABS = 1.0
DEFAULT_LIQUIDITY_RATIO_STEPS = [3.0, 2.5, 2.0, 1.5, 1.0]
COMPLIANCE_RESTRICTION_CODE = "51155"
_ENTRY_BALANCE_SNAPSHOT_LOGGED = False
_ZSCORE_LOG_INTERVAL_SECONDS = 60
_WAITING_LOG_INTERVAL_SECONDS = 60
_HOLD_LOG_INTERVAL_SECONDS = 60
_LAST_ZSCORE_STATUS = None
_LAST_ZSCORE_LOG_TS = 0.0
_LAST_WAITING_LOG_TS = 0.0
_LAST_WAITING_MSG = ""
_LAST_HOLD_LOG_TS = 0.0


def _get_health_switch_settings():
    raw_required = os.getenv("STATBOT_HEALTH_FAILS_REQUIRED", "2")
    try:
        required = int(float(raw_required))
    except (TypeError, ValueError):
        required = 2
    if required < 1:
        required = 1

    raw_grace = os.getenv("STATBOT_HEALTH_SWITCH_GRACE_SECONDS", "300")
    try:
        grace_seconds = float(raw_grace)
    except (TypeError, ValueError):
        grace_seconds = 300.0
    if grace_seconds < 0:
        grace_seconds = 0.0
    return required, grace_seconds


def _env_float(name, default=None):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_float_list(name, default_list):
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return list(default_list)
    values = []
    for part in str(raw).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(float(part))
        except (TypeError, ValueError):
            continue
    return values if values else list(default_list)

"""
MANAGE_NEW_TRADES KILL_SWITCH TRANSITIONS
==========================================

Entry point: kill_switch = 0 (ACTIVE)

Exit conditions (all set kill_switch = 1 or 2):
----------------------------------------------

kill_switch = 1: Orders placed, enter monitoring phase
  → Returned when both entry orders successfully placed
  → Signals main_execution to call close_all_positions()

kill_switch = 2: Final stop, close everything
  → Hard stop triggered (Z > ±2.5): regime break detected
  → Signal flip: Z-score changed sign unexpectedly
  → Cointegration lost: p_value >= 0.05 during trade
  → Mean reversion complete: Z < 0.05 (profit taken)
  → Returns to main_execution which exits loop

All transitions are logged with timestamps and context.
"""
from advanced_trade_management import AdvancedTradeManager
from func_price_calls import get_ticker_trade_liquidity, get_ticker_liquidity_analysis
from func_calculation import get_contract_value_quote
from func_get_zscore import get_latest_zscore
from func_execution_calls import (
    initialise_order_execution,
    preview_entry_details,
    get_min_capital_requirements,
    _fetch_instrument_info,
    _adjust_quantity_to_lot_size,
)
from func_close_positions import close_all_positions, get_position_info, place_market_close_order
from func_order_review import check_order
from func_fill_logging import log_order_fills
import time
import math
import logging
from func_log_setup import get_logger
import datetime

# Logger for trade management diagnostics
logger = get_logger("func_trade_management")

# Advanced trade manager for dynamic exit logic
trade_manager = AdvancedTradeManager(
    config={
        "take_profit_z": EXIT_Z,
    }
)


def _open_trade_manager(entry_z, position_size, entry_time=None):
    try:
        trade_manager.open_position(entry_z=entry_z, position_size=position_size, entry_time=entry_time)
    except Exception as exc:
        logger.warning("Trade manager open failed: %s", exc)


def _ensure_trade_manager_state(entry_z, entry_time):
    state = trade_manager.trade_state
    if state is None:
        _open_trade_manager(entry_z, position_size=0.0, entry_time=entry_time)
        return

    reset_needed = False
    try:
        if entry_z is not None and abs(float(state.entry_z) - float(entry_z)) > 1e-4:
            reset_needed = True
    except (TypeError, ValueError):
        reset_needed = True

    try:
        if entry_time is not None and abs(float(state.entry_time) - float(entry_time)) > 60:
            reset_needed = True
    except (TypeError, ValueError):
        reset_needed = True

    if reset_needed:
        _close_trade_manager()
        _open_trade_manager(entry_z, position_size=0.0, entry_time=entry_time)


def _close_trade_manager():
    if trade_manager.trade_state is not None:
        trade_manager.close_position()


def _format_fill_summary(summary):
    if not summary:
        return "none"
    return (
        "ticker={ticker} avg_px={avg_px:.6f} qty={qty:.6f} fee={fee:.6f} pnl={pnl:.6f}"
    ).format(
        ticker=summary.get("inst_id") or "n/a",
        avg_px=summary.get("avg_px") or 0.0,
        qty=summary.get("qty") or 0.0,
        fee=summary.get("fee") or 0.0,
        pnl=summary.get("pnl") or 0.0,
    )


def _log_entry_fills(order_long_id, order_short_id, long_ticker, short_ticker):
    long_summary = log_order_fills(order_long_id, long_ticker, max_wait_seconds=5.0)
    short_summary = log_order_fills(order_short_id, short_ticker, max_wait_seconds=5.0)
    if long_summary or short_summary:
        logger.info(
            "ENTRY_FILL_SUMMARY: long(%s) | short(%s)",
            _format_fill_summary(long_summary),
            _format_fill_summary(short_summary),
        )


def _execute_partial_exit(percentage):
    if percentage <= 0:
        return False

    size_pos, side_pos = get_position_info(signal_positive_ticker)
    size_neg, side_neg = get_position_info(signal_negative_ticker)

    if size_pos <= 0 or size_neg <= 0:
        logger.warning(
            "Partial exit skipped: no position found (pos=%.6f, neg=%.6f).",
            size_pos,
            size_neg,
        )
        return False

    target_pos = size_pos * percentage
    target_neg = size_neg * percentage

    info_pos = _fetch_instrument_info(signal_positive_ticker)
    info_neg = _fetch_instrument_info(signal_negative_ticker)

    adj_pos = _adjust_quantity_to_lot_size(signal_positive_ticker, target_pos, instrument_info=info_pos)
    adj_neg = _adjust_quantity_to_lot_size(signal_negative_ticker, target_neg, instrument_info=info_neg)

    if adj_pos <= 0 or adj_neg <= 0:
        logger.warning(
            "Partial exit skipped: adjusted size below min (pos=%.6f, neg=%.6f).",
            adj_pos,
            adj_neg,
        )
        return False

    logger.info(
        "Partial exit: closing %.6f %s on %s, %.6f %s on %s.",
        adj_pos,
        side_pos,
        signal_positive_ticker,
        adj_neg,
        side_neg,
        signal_negative_ticker,
    )

    place_market_close_order(signal_positive_ticker, adj_pos, side_pos)
    place_market_close_order(signal_negative_ticker, adj_neg, side_neg)

    return True

def _resolve_entry_id(entry_result):
    if not isinstance(entry_result, dict):
        return ""
    entry_id = entry_result.get("entry_id") or ""
    if entry_id:
        return str(entry_id)
    entry = entry_result.get("entry")
    if isinstance(entry, dict):
        data = entry.get("data") or []
        if data and isinstance(data[0], dict):
            return str(data[0].get("ordId") or data[0].get("clOrdId") or "")
    return ""


def _entry_result_ok(entry_result):
    if not isinstance(entry_result, dict):
        return False
    if entry_result.get("ok") is False:
        return False
    return True


def _log_missing_entry_id(side_label, entry_result):
    code = None
    msg = None
    if isinstance(entry_result, dict):
        entry = entry_result.get("entry")
        if isinstance(entry, dict):
            code = entry.get("code")
            msg = entry.get("msg")
    err_msg = f"ERROR: {side_label} entry missing order id (code={code} msg={msg})."
    logger.error(err_msg)
    print(err_msg)

def _extract_entry_error(entry_result):
    if not isinstance(entry_result, dict):
        return "", ""
    entry = entry_result.get("entry")
    if not isinstance(entry, dict):
        return "", ""
    s_code = ""
    s_msg = ""
    data_list = entry.get("data", [])
    if isinstance(data_list, list) and data_list:
        order_data = data_list[0] if isinstance(data_list[0], dict) else {}
        s_code = order_data.get("sCode") or ""
        s_msg = order_data.get("sMsg") or ""
    if not s_code:
        code = entry.get("code")
        if code and code != "0":
            s_code = code
    if not s_msg:
        s_msg = entry.get("msg") or ""
    return str(s_code or ""), str(s_msg or "")

def _handle_compliance_restriction(entry_result, ticker):
    s_code, s_msg = _extract_entry_error(entry_result)
    if str(s_code) != COMPLIANCE_RESTRICTION_CODE:
        return False
    added = add_restricted_ticker(ticker, code=s_code, msg=s_msg)
    if added:
        logger.error(
            "Compliance restriction for %s (sCode=%s, sMsg=%s).",
            ticker,
            s_code,
            s_msg,
        )
        print(f"ERROR: Compliance restriction for {ticker}: sCode={s_code}, sMsg={s_msg}")
    set_last_switch_reason("compliance_restricted")
    set_last_health_score(0)
    return not lock_on_pair


def _build_liquidity_ratio_steps(base_ratio):
    try:
        base_ratio = float(base_ratio)
    except (TypeError, ValueError):
        base_ratio = 0.0

    if base_ratio <= 0:
        return [0.0]

    floor = _env_float("STATBOT_LIQUIDITY_FALLBACK_MIN")
    if floor is not None and base_ratio < floor:
        base_ratio = floor

    steps = []

    def _add_step(value):
        if value <= 0:
            return
        for existing in steps:
            if abs(existing - value) < 1e-9:
                return
        steps.append(value)

    _add_step(base_ratio)
    tier_candidates = []
    tier_1 = _env_float("STATBOT_LIQUIDITY_FALLBACK_TIER1")
    tier_2 = _env_float("STATBOT_LIQUIDITY_FALLBACK_TIER2")
    tier_3 = _env_float("STATBOT_LIQUIDITY_FALLBACK_TIER3")
    if tier_1 is not None:
        tier_candidates.append(tier_1)
    if tier_2 is not None:
        tier_candidates.append(tier_2)
    if tier_3 is not None:
        tier_candidates.append(tier_3)
    if floor is not None:
        tier_candidates.append(floor)
    if not tier_candidates:
        tier_candidates = _env_float_list(
            "STATBOT_LIQUIDITY_RATIO_STEPS",
            DEFAULT_LIQUIDITY_RATIO_STEPS,
        )

    for value in tier_candidates:
        if value is None:
            continue
        if floor is not None and value < floor:
            continue
        if value < base_ratio - 1e-9:
            _add_step(value)

    return steps or [base_ratio]

def _z_history_values(z_history):
    values = []
    for entry in z_history:
        z_val = entry.get("z") if isinstance(entry, dict) else entry
        try:
            values.append(float(z_val))
        except (TypeError, ValueError):
            continue
    return values

def _calc_std(values):
    if not values:
        return 0.0
    mean_val = sum(values) / len(values)
    variance = sum((val - mean_val) ** 2 for val in values) / len(values)
    return math.sqrt(variance)

def _recent_volatility(z_values):
    if len(z_values) < 10:
        return 0.5
    recent = z_values[-20:]
    return _calc_std(recent)

def _adaptive_stall_window_seconds(entry_z):
    abs_entry = abs(entry_z)
    if abs_entry < 2.5:
        return 1800
    if abs_entry < 3.5:
        return Z_STALL_BASE_WINDOW_SECONDS
    if abs_entry < 4.5:
        return 5400
    return 7200

def _adaptive_stall_epsilon(volatility, time_in_trade_sec):
    if volatility > 1.0:
        epsilon = 0.5
    elif volatility > 0.5:
        epsilon = 0.3
    else:
        epsilon = 0.2

    minutes_in_trade = time_in_trade_sec / 60.0
    if minutes_in_trade < Z_STALL_EARLY_GRACE_MINUTES:
        return None
    if minutes_in_trade < 60:
        epsilon *= 0.7
    elif minutes_in_trade > Z_STALL_LATE_STRICT_MINUTES:
        epsilon *= 1.3
    return epsilon

def _volatility_accelerating(z_values):
    if len(z_values) < 40:
        return False
    recent = z_values[-20:]
    prior = z_values[-40:-20]
    recent_vol = _calc_std(recent)
    prior_vol = _calc_std(prior)
    if prior_vol <= 0:
        return False
    return recent_vol > prior_vol * Z_STALL_VOLATILITY_ACCEL_RATIO

def _z_at_or_before(z_history, target_ts):
    z_val = None
    for entry in z_history:
        if not isinstance(entry, dict):
            continue
        ts = entry.get("ts")
        if ts is None:
            continue
        if ts <= target_ts:
            z_val = entry.get("z")
        elif z_val is not None:
            break
    if z_val is None:
        return None
    try:
        return float(z_val)
    except (TypeError, ValueError):
        return None

# Issue #11 Fix: Signal generation with persistence requirement and professional thresholds
def generate_signal(z_history, cointegration_ok, in_position):
    """
    Generate trading signals with persistence requirement to prevent flash trades.
    
    Implements professional-grade entry/exit logic:
    - ENTRY_Z = 2.0: Requires Z-score at ±2.0 (2 std deviations from mean)
    - EXIT_Z = 0.5: Exit when Z-score reverts toward ±0.5
    - MIN_PERSIST_BARS = 3: Require signal to persist for 3 bars (3 minutes @ 1m candles)
    
    Parameters:
        z_history (list): Full history of Z-score values
        cointegration_ok (int): 1 if cointegrated, 0 otherwise
        in_position (bool): Current position status
    
    Returns:
        (signal, reason): Tuple of (signal_str, reason_str)
            signal: "BUY_SPREAD", "SELL_SPREAD", "EXIT", or None
            reason: Descriptive string for logging
    """
    if not z_history:
        return None, "No z-score data available"
    
    current_z = z_history[-1]
    
    # Hard gate: No trade if cointegration is invalid
    if cointegration_ok != 1:
        return None, "No trade - cointegration invalid"
    
    # ENTRY LOGIC - Use persistent state history across cycles
    if not in_position:
        from func_pair_state import add_to_persistence_history, get_persistence_history, can_reenter

        # Check re-entry cooldown to prevent clustering at same Z level
        if not can_reenter(cooldown_minutes=5):
            return None, "Re-entry cooldown active (5 min since last exit)"

        # Add current z-score to persistent history
        add_to_persistence_history(current_z)

        # Get last N cycles from persistent state
        persistence_history = get_persistence_history()

        if len(persistence_history) >= MIN_PERSIST_BARS:
            recent_zscores = persistence_history[-MIN_PERSIST_BARS:]

            # Check if all recent z-scores are in the same extreme zone
            all_oversold = all(z <= -ENTRY_Z for z in recent_zscores)
            all_overbought = all(z >= ENTRY_Z for z in recent_zscores)

            if all_oversold:
                return "BUY_SPREAD", f"Entry signal: Z={current_z:.4f} persistent at -ENTRY_Z (oversold, bars={MIN_PERSIST_BARS})"
            elif all_overbought:
                return "SELL_SPREAD", f"Entry signal: Z={current_z:.4f} persistent at +ENTRY_Z (overbought, bars={MIN_PERSIST_BARS})"
            else:
                return None, f"No entry - Z-score not persistent (history: {[round(z, 2) for z in recent_zscores]})"
        else:
            return None, f"Insufficient history: {len(persistence_history)} cycles < {MIN_PERSIST_BARS} required"
    
    # EXIT LOGIC
    if in_position:
        if abs(current_z) <= EXIT_Z:
            return "EXIT", f"Exit signal: Z={current_z:.4f} reverted to EXIT_Z threshold ({EXIT_Z})"
        else:
            return None, f"Hold position - Z={current_z:.4f} still beyond EXIT_Z ({EXIT_Z})"
    
    return None, "No signal generated"


def check_pair_health(metrics, latest_zscore, silent=False):
    """
    Evaluate pair health based on statistical metrics.
    Returns (should_switch, health_score, recommendation)
    """
    health_score = 100
    critical_issues = []
    warnings_list = []
    
    p_val = metrics.get("p_value", 1.0)
    adf_stat = metrics.get("adf_stat", 0.0)
    crit_val = metrics.get("critical_value", -3.4)
    z_cross = metrics.get("zero_crossings", 0)
    correlation = metrics.get("correlation", 0.0)
    spread_trend = metrics.get("spread_trend", 0.0)
    coint_flag = metrics.get("coint_flag", 0)
    
    # 1. Statistical Strength (P-value)
    if p_val >= P_VALUE_CRITICAL:
        critical_issues.append(f"P-value ({p_val:.4f}) >= {P_VALUE_CRITICAL}")
        health_score -= 50
    elif p_val > 0.05:
        # We still keep a minor penalty for p-values between 0.05 and 0.15
        warnings_list.append(f"P-value ({p_val:.4f}) elevated")
        health_score -= 15

    # 2. ADF Ratio
    adf_ratio = abs(adf_stat / crit_val) if crit_val != 0 else 0
    if adf_ratio < 0.8:
        warnings_list.append(f"ADF ratio ({adf_ratio:.2f}) < 0.8")
        health_score -= 15
        
    # 3. Zero Crossings
    if z_cross < ZERO_CROSSINGS_MIN:
        warnings_list.append(f"Low Zero Crossings ({z_cross} < {ZERO_CROSSINGS_MIN})")
        health_score -= 15
        
    # 4. Spread Stationarity
    if abs(spread_trend) > TREND_CRITICAL:
        critical_issues.append(f"Spread Trending ({spread_trend:.4f} > {TREND_CRITICAL})")
        health_score -= 30
        
    # 5. Relationship Integrity
    if abs(latest_zscore) > Z_SCORE_CRITICAL:
        critical_issues.append(f"Extreme Z-score ({abs(latest_zscore):.2f} > {Z_SCORE_CRITICAL})")
        health_score -= 25
        
    # 6. Price Correlation
    if correlation < CORRELATION_MIN:
        warnings_list.append(f"Low Correlation ({correlation:.2f} < {CORRELATION_MIN})")
        health_score -= 15

    # 7. Recent Trading Performance
    losses = get_consecutive_losses()
    if losses >= 3:
        warnings_list.append(f"Consecutive Losses ({losses})")
        health_score -= 20
    elif losses > 0:
        warnings_list.append(f"Recent Loss detected ({losses})")
        health_score -= 5 * losses

    # Action determination
    should_switch = health_score < 40
    recommendation = "STOP_AND_SWITCH" if should_switch else ("MONITOR_CLOSELY" if health_score < 70 else "PAIR_IS_HEALTHY")

    # Store health score for emergency override checks
    from func_pair_state import set_last_health_score
    set_last_health_score(health_score)

    if not silent:
        logger.info("━━━ PERIODIC HEALTH CHECK ━━━")
        logger.info(f"P-value: {p_val:.4f} {'✅' if p_val < P_VALUE_CRITICAL else '❌'}")
        logger.info(f"Zero crossings: {z_cross} {'✅' if z_cross >= ZERO_CROSSINGS_MIN else '❌'}")
        logger.info(f"Correlation: {correlation:.2f} {'✅' if correlation >= CORRELATION_MIN else '❌'}")
        logger.info(f"Spread Trend: {spread_trend:.4f} {'✅' if abs(spread_trend) <= TREND_CRITICAL else '❌'}")
        logger.info(f"Health score: {health_score}/100 {'✅' if health_score >= 40 else '❌'}")
        
        if critical_issues:
            logger.warning(f"CRITICAL ISSUES: {', '.join(critical_issues)}")
        if warnings_list:
            logger.info(f"Warnings: {', '.join(warnings_list)}")
            
        if should_switch:
            logger.warning(f"❌ Pair health CRITICAL: {recommendation}")
        else:
            logger.info(f"✅ Pair is healthy, continuing... ({recommendation})")

    return should_switch, health_score, recommendation


def _log_zscore_status(zscore):
    """
    Log Z-score status with descriptive labels and emojis.
    """
    global _LAST_ZSCORE_STATUS
    global _LAST_ZSCORE_LOG_TS
    if abs(zscore) < 1.0:
        bucket = "quiet"
        status = "😴 Very quiet (|Z| < 1.0)"
    elif abs(zscore) < 2.0:
        bucket = "waiting"
        status = "⏳ Waiting (1.0 < |Z| < 2.0)"
    elif abs(zscore) < 3.0:
        bucket = "tradeable"
        status = "🎯 TRADEABLE (|Z| > 2.0)"
    else:
        bucket = "extreme"
        status = "🚨 Extreme (|Z| > 3.0)"
    
    msg = f"Current Z-Score: {zscore:+.2f} - {status}"
    now = time.time()
    if bucket != _LAST_ZSCORE_STATUS or (now - _LAST_ZSCORE_LOG_TS) >= _ZSCORE_LOG_INTERVAL_SECONDS:
        logger.info(msg)
        _LAST_ZSCORE_STATUS = bucket
        _LAST_ZSCORE_LOG_TS = now
    else:
        logger.debug(msg)


def _log_waiting(message):
    global _LAST_WAITING_LOG_TS
    global _LAST_WAITING_MSG
    now = time.time()
    if message != _LAST_WAITING_MSG or (now - _LAST_WAITING_LOG_TS) >= _WAITING_LOG_INTERVAL_SECONDS:
        logger.info(message)
        _LAST_WAITING_LOG_TS = now
        _LAST_WAITING_MSG = message
    else:
        logger.debug(message)


def _log_hold_position(zscore):
    global _LAST_HOLD_LOG_TS
    now = time.time()
    msg = f"Hold position - Z={zscore:.4f} still beyond EXIT_Z ({EXIT_Z})"
    if (now - _LAST_HOLD_LOG_TS) >= _HOLD_LOG_INTERVAL_SECONDS:
        logger.info(msg)
        _LAST_HOLD_LOG_TS = now
    else:
        logger.debug(msg)


# Manage new trade assessment and order placing
def manage_new_trades(kill_switch, health_check_due=False, zscore_results=None):
    """
    Manage trade entry, monitoring, and exit.
    
    INPUT: kill_switch (expected: 0 = ACTIVE)
    
    RETURN:
    -------
    (kill_switch, signal_detected, trade_placed)
    """

    # Set variables
    order_long_id = ""
    order_short_id = ""
    signal_side = ""
    hot = False
    signal_detected = False
    trade_placed = False

    # Get and save the latest z-score
    if zscore_results:
        zscore, signal_sign_positive, metrics = zscore_results
    else:
        zscore, signal_sign_positive, metrics = get_latest_zscore()
        
    coint_flag = metrics.get("coint_flag", 0)

    # Filter out NaN values and get the latest valid z-score
    valid_zscores = [z for z in zscore if not math.isnan(z)]
    if not valid_zscores:
        logger.info("No valid z-scores yet (insufficient data for rolling window calculation)")
        return kill_switch, False, False
    
    latest_zscore = valid_zscores[-1]
    
    # 1. Log Current Z-score status every cycle
    _log_zscore_status(latest_zscore)

    # 2. Run Health Check if due or if cointegration is lost
    if health_check_due or coint_flag == 0:
        log_health_details = bool(health_check_due)
        should_switch, score, rec = check_pair_health(
            metrics,
            latest_zscore,
            silent=not log_health_details,
        )
        failures = record_health_failure(
            signal_positive_ticker,
            signal_negative_ticker,
            should_switch,
        )
        if should_switch:
            required, grace_seconds = _get_health_switch_settings()
            if failures < required:
                if log_health_details:
                    logger.warning(
                        "Pair health critical (score=%s). Confirmation %d/%d; deferring switch.",
                        score,
                        failures,
                        required,
                    )
                else:
                    logger.debug(
                        "Pair health critical (score=%s). Confirmation %d/%d; deferring switch.",
                        score,
                        failures,
                        required,
                    )
                return kill_switch, False, False
            last_switch = get_last_switch_time()
            elapsed = time.time() - last_switch if last_switch else grace_seconds + 1
            if grace_seconds and elapsed < grace_seconds:
                if log_health_details:
                    logger.warning(
                        "Pair health critical but within grace period (%.0fs remaining).",
                        grace_seconds - elapsed,
                    )
                else:
                    logger.debug(
                        "Pair health critical but within grace period (%.0fs remaining).",
                        grace_seconds - elapsed,
                    )
                return kill_switch, False, False
            if coint_flag == 0:
                set_last_switch_reason("cointegration_lost")
            else:
                set_last_switch_reason("health")
            return 3, False, False
    
    # 3. Signal Generation
    signal, reason = generate_signal(valid_zscores, coint_flag, in_position=False)
    
    if signal in ["BUY_SPREAD", "SELL_SPREAD"]:
        # Activate hot trigger
        hot = True
        signal_detected = True
        msg = f"🎯 ENTRY SIGNAL DETECTED!"
        print(msg)
        logger.info(msg)
        logger.info(f"Reason: {reason}")
        global _ENTRY_BALANCE_SNAPSHOT_LOGGED
        if not _ENTRY_BALANCE_SNAPSHOT_LOGGED:
            try:
                balance_res = account_session.get_account_balance()
                avail_bal = 0.0
                avail_eq = 0.0
                if balance_res.get("code") == "0":
                    details = balance_res.get("data", [{}])[0].get("details", [])
                    for det in details:
                        if det.get("ccy") == "USDT":
                            avail_bal = float(det.get("availBal", 0))
                            avail_eq = float(det.get("availEq", 0))
                            break
                logger.info(
                    "💰 Pre-trade balance snapshot (USDT): availBal=%.2f | availEq=%.2f | td_mode=%s",
                    avail_bal,
                    avail_eq,
                    td_mode,
                )
            except Exception as exc:
                logger.warning("Failed to log pre-trade balance snapshot: %s", exc)
            _ENTRY_BALANCE_SNAPSHOT_LOGGED = True
    else:
        # Log waiting status
        if abs(latest_zscore) < ENTRY_Z:
            _log_waiting("⏳ WAITING: Not at entry threshold yet")
        else:
            # It's beyond threshold but not persistent yet
            _log_waiting(f"⏳ WAITING: Z-score extreme ({latest_zscore:+.2f}) but not persistent yet")

    # Place and manage trades
    if hot and kill_switch == 0:
        if is_restricted_ticker(signal_positive_ticker) or is_restricted_ticker(signal_negative_ticker):
            set_last_switch_reason("compliance_restricted")
            set_last_health_score(0)
            if not lock_on_pair:
                return 3, signal_detected, trade_placed
            return kill_switch, signal_detected, trade_placed

        # Get the trade history for liquidity
        avg_liquidity_ticker_p, last_price_p = get_ticker_trade_liquidity(signal_positive_ticker)
        avg_liquidity_ticker_n, last_price_n = get_ticker_trade_liquidity(signal_negative_ticker)

        # VALIDATION: Check prices and liquidity are valid
        if (last_price_p is None or last_price_p <= 0 or avg_liquidity_ticker_p is None or avg_liquidity_ticker_p <= 0):
            logger.error(
                "❌ Invalid price data for %s: price=%.4f liquidity=%.6f - Skipping trade",
                signal_positive_ticker,
                last_price_p or 0,
                avg_liquidity_ticker_p or 0,
            )
            return kill_switch
        
        if (last_price_n is None or last_price_n <= 0 or avg_liquidity_ticker_n is None or avg_liquidity_ticker_n <= 0):
            logger.error(
                "❌ Invalid price data for %s: price=%.4f liquidity=%.6f - Skipping trade",
                signal_negative_ticker,
                last_price_n or 0,
                avg_liquidity_ticker_n or 0,
            )
            return kill_switch
        
        logger.debug(
            "✓ Price validation passed: %s price=%.4f liq=%.6f, %s price=%.4f liq=%.6f",
            signal_positive_ticker, last_price_p, avg_liquidity_ticker_p,
            signal_negative_ticker, last_price_n, avg_liquidity_ticker_n,
        )

        # Determine long ticker vs short ticker liquidity ratio
        if signal_sign_positive:
            long_ticker = signal_positive_ticker
            short_ticker = signal_negative_ticker
            avg_liquidity_long = avg_liquidity_ticker_p
            avg_liquidity_short = avg_liquidity_ticker_n
            last_price_long = last_price_p
            last_price_short = last_price_n
        else:
            long_ticker = signal_negative_ticker
            short_ticker = signal_positive_ticker
            avg_liquidity_long = avg_liquidity_ticker_n
            avg_liquidity_short = avg_liquidity_ticker_p
            last_price_long = last_price_n
            last_price_short = last_price_p

        # Fill targets
        # POSITION SIZING (2% Risk Rule)
        # Check available funds (cross margin requires availEq, isolated uses availBal)
        use_avail_eq = str(td_mode or "").strip().lower() == "cross"
        available_label = "availEq" if use_avail_eq else "availBal"
        available_usdt = 0.0
        try:
            balance_res = account_session.get_account_balance()
            available_bal = 0.0
            available_eq = 0.0
            if balance_res.get("code") == "0":
                details = balance_res.get("data", [{}])[0].get("details", [])
                for det in details:
                    if det.get("ccy") == "USDT":
                        available_bal = float(det.get("availBal", 0))
                        available_eq = float(det.get("availEq", 0))
                        break
            
            logger.info(
                "💰 Available balance (availBal): %.2f USDT | Available equity (availEq): %.2f USDT",
                available_bal,
                available_eq,
            )

            available_usdt = available_eq if use_avail_eq else available_bal

            if available_usdt <= 0:
                logger.error(f"❌ No available USDT margin ({available_label}): {available_usdt}")
                return kill_switch, signal_detected, trade_placed

            # Use the lower of configured capital or available funds
            effective_capital = min(tradeable_capital_usdt, available_usdt * 0.95)  # 95% to leave buffer
            logger.info(
                "📊 Effective capital: %.2f USDT (config: %.2f, available %s: %.2f)",
                effective_capital,
                tradeable_capital_usdt,
                available_label,
                available_usdt,
            )
        except Exception as e:
            logger.error(f"Failed to check balance: {e}. Using configured capital.")
            available_usdt = tradeable_capital_usdt
            available_label = "configured"
            effective_capital = tradeable_capital_usdt
        
        # Risk per trade = 2% of effective capital
        risk_usdt = effective_capital * RISK_PER_TRADE_PCT
        
        # Stop loss distance in percentage (3% = 0.03)
        stop_loss_pct = stop_loss_fail_safe
        
        # Position size = Risk / Stop distance
        # This ensures we never risk more than 2% per trade
        initial_capital_usdt = risk_usdt / stop_loss_pct
        
        # Split equally between long and short
        capital_long = initial_capital_usdt
        capital_short = initial_capital_usdt
        
        # Validate against effective capital
        if initial_capital_usdt * 2 > effective_capital:
            logger.warning(
                "Position size (%.2f per side) would exceed effective capital. Reducing to 50/50 split.",
                initial_capital_usdt
            )
            capital_long = effective_capital * 0.5
            capital_short = effective_capital * 0.5
            initial_capital_usdt = capital_long
        
        # Log position sizing with 2% rule
        logger.info(
            "Position sizing (2%% RISK RULE): total_capital=%.2f risk_usdt=%.2f stop_loss_pct=%.2f%% "
            "position_per_side=%.2f long=%.2f short=%.2f",
            tradeable_capital_usdt,
            risk_usdt,
            stop_loss_pct * 100,
            initial_capital_usdt,
            capital_long,
            capital_short,
        )
        
        # Set the remaining capital
        remaining_capital_long = capital_long
        remaining_capital_short = capital_short

        # Evaluate min-capital requirements before preflight to avoid noisy adjustments
        min_req_long = get_min_capital_requirements(long_ticker)
        min_req_short = get_min_capital_requirements(short_ticker)
        if not min_req_long.get("ok") or not min_req_short.get("ok"):
            msg = (
                "ERROR: Min-capital requirements unavailable; "
                f"long={min_req_long.get('error') or 'unknown'} "
                f"short={min_req_short.get('error') or 'unknown'}. Skipping entry."
            )
            print(msg)
            logger.error(msg)
            return kill_switch, signal_detected, trade_placed

        min_capital_long = min_req_long.get("min_capital") or 0.0
        min_capital_short = min_req_short.get("min_capital") or 0.0
        required_floor = max(min_capital_long, min_capital_short)
        if required_floor > 0 and initial_capital_usdt < required_floor:
            if required_floor > capital_long or required_floor > capital_short:
                cooldown = set_min_capital_cooldown(
                    long_ticker,
                    short_ticker,
                    required_floor,
                    capital_long,
                )
                if lock_on_pair:
                    msg = (
                        "ERROR: Minimum per-leg capital exceeds allocation; "
                        f"required={required_floor:.8f} long_min={min_capital_long:.8f} "
                        f"short_min={min_capital_short:.8f} allocated={capital_long:.8f}. "
                        f"lock_on_pair enabled (cooldown={cooldown/60:.1f}m). Skipping entry."
                    )
                    print(msg)
                    logger.error(msg)
                    return kill_switch, signal_detected, trade_placed
                msg = (
                    "ERROR: Minimum per-leg capital exceeds allocation; "
                    f"required={required_floor:.8f} long_min={min_capital_long:.8f} "
                    f"short_min={min_capital_short:.8f} allocated={capital_long:.8f}. "
                    f"Switching pair (cooldown={cooldown/60:.1f}m)."
                )
                print(msg)
                logger.error(msg)
                set_last_switch_reason("min_capital")
                # Force pair switch by using emergency override threshold in main_execution.
                set_last_health_score(0)
                return 3, signal_detected, trade_placed

            logger.info(
                "Raising initial capital from %.8f to %.8f to meet min order size "
                "(long_min=%.8f short_min=%.8f).",
                initial_capital_usdt,
                required_floor,
                min_capital_long,
                min_capital_short,
            )
            initial_capital_usdt = required_floor

        long_info_req = min_req_long.get("instrument_info") or {}
        short_info_req = min_req_short.get("instrument_info") or {}
        long_contract_value_quote = get_contract_value_quote(last_price_long, long_info_req, inst_id=long_ticker)
        short_contract_value_quote = get_contract_value_quote(last_price_short, short_info_req, inst_id=short_ticker)
        if long_contract_value_quote <= 0:
            long_contract_value_quote = last_price_long
        if short_contract_value_quote <= 0:
            short_contract_value_quote = last_price_short

        liquidity_long_usdt = avg_liquidity_long * long_contract_value_quote
        liquidity_short_usdt = avg_liquidity_short * short_contract_value_quote
        initial_fill_target_long_usdt = liquidity_long_usdt
        initial_fill_target_short_usdt = liquidity_short_usdt
        initial_capital_injection_usdt = min(initial_fill_target_long_usdt, initial_fill_target_short_usdt)

        # Ensure initial capital injection does not exceed allocated capital
        if limit_order_basis:
            if initial_capital_injection_usdt > capital_long:
                initial_capital_usdt = capital_long
            else:
                initial_capital_usdt = initial_capital_injection_usdt
        else:
            initial_capital_usdt = capital_long

        base_target_usdt = initial_capital_usdt
        min_liquidity_ratio = 0.0
        ratio_env = os.getenv("STATBOT_MIN_LIQUIDITY_RATIO")
        if ratio_env is None or str(ratio_env).strip() == "":
            ratio_env = os.getenv("STATBOT_LIQUIDITY_MIN_RATIO", "0")
        try:
            min_liquidity_ratio = float(ratio_env)
        except (TypeError, ValueError):
            min_liquidity_ratio = 0.0

        def _liq_ratio(liquidity_usdt, target_usdt):
            if target_usdt <= 0:
                return 0.0
            if liquidity_usdt is None or liquidity_usdt <= 0:
                return 0.0
            return liquidity_usdt / target_usdt

        ratio_steps = _build_liquidity_ratio_steps(min_liquidity_ratio)
        selected_ratio = min_liquidity_ratio
        selected_target_usdt = base_target_usdt
        liquidity_ok = True

        if ratio_steps and ratio_steps[0] > 0:
            liquidity_ok = False
            for attempt, ratio_threshold in enumerate(ratio_steps, start=1):
                if ratio_threshold != min_liquidity_ratio:
                    logger.warning(
                        "Execution liquidity fallback attempt %d/%d: min_ratio=%.2fx",
                        attempt,
                        len(ratio_steps),
                        ratio_threshold,
                    )
                else:
                    logger.info(
                        "Execution liquidity attempt %d/%d: min_ratio=%.2fx",
                        attempt,
                        len(ratio_steps),
                        ratio_threshold,
                    )

                attempt_target = base_target_usdt
                ratio_long = _liq_ratio(liquidity_long_usdt, attempt_target)
                ratio_short = _liq_ratio(liquidity_short_usdt, attempt_target)

                if ratio_long < ratio_threshold or ratio_short < ratio_threshold:
                    worst_liquidity = min(liquidity_long_usdt, liquidity_short_usdt)
                    adjusted_target = (worst_liquidity / ratio_threshold) if worst_liquidity > 0 else 0.0
                    if adjusted_target <= 0:
                        logger.warning(
                            "Liquidity attempt %d/%d rejected: target=%.2f long_liq=%.2f short_liq=%.2f "
                            "ratios=%.2fx/%.2fx min=%.2fx.",
                            attempt,
                            len(ratio_steps),
                            attempt_target,
                            liquidity_long_usdt,
                            liquidity_short_usdt,
                            ratio_long,
                            ratio_short,
                            ratio_threshold,
                        )
                        continue
                    if required_floor > 0 and adjusted_target < required_floor:
                        logger.warning(
                            "Liquidity attempt %d/%d rejected: target=%.2f -> %.2f below min order %.2f "
                            "(liq min=%.2f, min_ratio=%.2fx).",
                            attempt,
                            len(ratio_steps),
                            attempt_target,
                            adjusted_target,
                            required_floor,
                            worst_liquidity,
                            ratio_threshold,
                        )
                        continue
                    if adjusted_target < attempt_target:
                        attempt_target = adjusted_target
                        ratio_long = _liq_ratio(liquidity_long_usdt, attempt_target)
                        ratio_short = _liq_ratio(liquidity_short_usdt, attempt_target)

                if ratio_long < ratio_threshold or ratio_short < ratio_threshold:
                    logger.warning(
                        "Liquidity attempt %d/%d rejected: ratios below min after adjust "
                        "(%.2fx/%.2fx < %.2fx).",
                        attempt,
                        len(ratio_steps),
                        ratio_long,
                        ratio_short,
                        ratio_threshold,
                    )
                    continue

                selected_ratio = ratio_threshold
                selected_target_usdt = attempt_target
                if selected_target_usdt < base_target_usdt:
                    logger.info(
                        "Liquidity downsize: target=%.2f -> %.2f to meet min ratio %.2fx "
                        "(liq_long=%.2f liq_short=%.2f).",
                        base_target_usdt,
                        selected_target_usdt,
                        selected_ratio,
                        liquidity_long_usdt,
                        liquidity_short_usdt,
                    )
                liquidity_ok = True
                break

            if not liquidity_ok:
                ratio_long = _liq_ratio(liquidity_long_usdt, base_target_usdt)
                ratio_short = _liq_ratio(liquidity_short_usdt, base_target_usdt)
                msg = (
                    "WARNING LIQUIDITY_REJECT: target=%.2f long_liq=%.2f short_liq=%.2f "
                    "ratios(liq/target)=%.2fx/%.2fx min=%.2fx. Skipping entry."
                    % (
                        base_target_usdt,
                        liquidity_long_usdt,
                        liquidity_short_usdt,
                        ratio_long,
                        ratio_short,
                        min_liquidity_ratio,
                    )
                )
                print(msg)
                logger.warning(msg)
                return kill_switch, signal_detected, trade_placed

        initial_capital_usdt = selected_target_usdt
        remaining_capital_long = min(remaining_capital_long, initial_capital_usdt)
        remaining_capital_short = min(remaining_capital_short, initial_capital_usdt)
        min_liquidity_ratio = selected_ratio
        ratio_long = _liq_ratio(liquidity_long_usdt, initial_capital_usdt)
        ratio_short = _liq_ratio(liquidity_short_usdt, initial_capital_usdt)

        logger.info(
            "Liquidity check: long_target=%.2f short_target=%.2f liquidity_long=%.2f liquidity_short=%.2f",
            initial_capital_usdt,
            initial_capital_usdt,
            liquidity_long_usdt,
            liquidity_short_usdt,
        )
        logger.info(
            "Liquidity ratios (liq/target): long=%.2fx short=%.2fx (min=%.2fx)",
            ratio_long,
            ratio_short,
            min_liquidity_ratio,
        )
        if min_liquidity_ratio > 0 and (ratio_long < min_liquidity_ratio or ratio_short < min_liquidity_ratio):
            msg = (
                "WARNING LIQUIDITY_REJECT: target=%.2f long_liq=%.2f short_liq=%.2f "
                "ratios(liq/target)=%.2fx/%.2fx min=%.2fx. Skipping entry."
                % (
                    initial_capital_usdt,
                    liquidity_long_usdt,
                    liquidity_short_usdt,
                    ratio_long,
                    ratio_short,
                    min_liquidity_ratio,
                )
            )
            print(msg)
            logger.warning(msg)
            return kill_switch, signal_detected, trade_placed

        # Preflight both legs to avoid one-sided entries on invalid trade details
        preflight_long = preview_entry_details(
            long_ticker,
            "buy",
            initial_capital_usdt,
            orderbook_payload=min_req_long.get("orderbook_payload"),
            instrument_info=min_req_long.get("instrument_info"),
        )
        preflight_short = preview_entry_details(
            short_ticker,
            "sell",
            initial_capital_usdt,
            orderbook_payload=min_req_short.get("orderbook_payload"),
            instrument_info=min_req_short.get("instrument_info"),
        )

        if not preflight_long.get("ok") or not preflight_short.get("ok"):
            msg = (
                "ERROR: Invalid trade details; "
                f"long={preflight_long.get('error') or 'ok'} "
                f"short={preflight_short.get('error') or 'ok'}. Skipping entry."
            )
            print(msg)
            logger.error(msg)
            return kill_switch, signal_detected, trade_placed

        long_entry_price = preflight_long.get("entry_price") or 0.0
        short_entry_price = preflight_short.get("entry_price") or 0.0
        long_qty = preflight_long.get("quantity") or 0.0
        short_qty = preflight_short.get("quantity") or 0.0
        logger.info(
            "Entry preview: long=%s price=%.6f qty=%.6f | short=%s price=%.6f qty=%.6f",
            long_ticker,
            long_entry_price,
            long_qty,
            short_ticker,
            short_entry_price,
            short_qty,
        )

        long_contract_value = preflight_long.get("contract_value_quote") or 0.0
        short_contract_value = preflight_short.get("contract_value_quote") or 0.0
        if long_contract_value <= 0 or short_contract_value <= 0:
            msg = "ERROR: Contract value unavailable for sizing; skipping entry."
            print(msg)
            logger.error(msg)
            return kill_switch, signal_detected, trade_placed

        long_info = preflight_long.get("instrument_info") or {}
        short_info = preflight_short.get("instrument_info") or {}
        logger.info(
            "Contract value long %s: ctVal=%s ctMult=%s ctValCcy=%s quote_per_contract=%.6f",
            long_ticker,
            long_info.get("ctVal"),
            long_info.get("ctMult"),
            long_info.get("ctValCcy") or "n/a",
            long_contract_value,
        )
        logger.info(
            "Contract value short %s: ctVal=%s ctMult=%s ctValCcy=%s quote_per_contract=%.6f",
            short_ticker,
            short_info.get("ctVal"),
            short_info.get("ctMult"),
            short_info.get("ctValCcy") or "n/a",
            short_contract_value,
        )

        long_notional = preflight_long.get("notional_usdt") or 0.0
        short_notional = preflight_short.get("notional_usdt") or 0.0
        total_notional = long_notional + short_notional
        if available_usdt > 0:
            max_notional = available_usdt * 0.95
            if total_notional > max_notional or long_notional > max_notional or short_notional > max_notional:
                msg = (
                    "ERROR: Pre-trade notional exceeds available "
                    f"{available_label}: long={long_notional:.2f} short={short_notional:.2f} "
                    f"total={total_notional:.2f} avail={available_usdt:.2f}"
                )
                print(msg)
                logger.error(msg)
                return kill_switch, signal_detected, trade_placed
            logger.info(
                "Pre-trade notional check: long=%.2f short=%.2f total=%.2f %s=%.2f",
                long_notional,
                short_notional,
                total_notional,
                available_label,
                available_usdt,
            )

        # Trade until filled or signal is false
        order_status_long = ""
        order_status_short = ""
        count_long = 0
        count_short = 0
        while kill_switch == 0:
            # Place long order
            if count_long == 0:
                long_payload = preflight_long.get("orderbook_payload") if preflight_long else None
                long_info = preflight_long.get("instrument_info") if preflight_long else None
                result_long = initialise_order_execution(
                    long_ticker,
                    "buy",
                    initial_capital_usdt,
                    orderbook_payload=long_payload,
                    instrument_info=long_info,
                )
                preflight_long = None
                if result_long and _entry_result_ok(result_long):
                    order_long_id = _resolve_entry_id(result_long)
                    if not order_long_id:
                        _log_missing_entry_id("Long", result_long)
                        close_all_positions(0)
                        return kill_switch, signal_detected, trade_placed
                    order_status_long = "placed"
                    count_long = 1
                    remaining_capital_long = remaining_capital_long - initial_capital_usdt
                    # Extract stop loss price from result if available
                    entry_price_long = result_long.get("entry_price", 0)
                    stop_price_long = result_long.get("stop_price", 0)
                    if entry_price_long > 0 and stop_price_long > 0:
                        stop_distance_pct = abs(entry_price_long - stop_price_long) / entry_price_long * 100
                        logger.info(
                            "Long entry: id=%s capital=%.2f entry_price=%.2f stop=%.2f distance=%.2f%% remaining=%.2f",
                            order_long_id,
                            initial_capital_usdt,
                            entry_price_long,
                            stop_price_long,
                            stop_distance_pct,
                            remaining_capital_long,
                        )
                    else:
                        logger.info(
                            "Placed long entry: ticker=%s id=%s entry_price=%.6f capital=%.2f remaining=%.2f",
                            long_ticker,
                            order_long_id,
                            long_entry_price,
                            initial_capital_usdt,
                            remaining_capital_long,
                        )
                else:
                    order_long_id = ""
                    order_status_long = "failed"
                    logger.error("Long entry failed; skipping pair entry. Response: %s", result_long)
                    if _handle_compliance_restriction(result_long, long_ticker):
                        return 3, signal_detected, trade_placed
                    return kill_switch, signal_detected, trade_placed

            # Place short order
            if count_short == 0:
                short_payload = preflight_short.get("orderbook_payload") if preflight_short else None
                short_info = preflight_short.get("instrument_info") if preflight_short else None
                result_short = initialise_order_execution(
                    short_ticker,
                    "sell",
                    initial_capital_usdt,
                    orderbook_payload=short_payload,
                    instrument_info=short_info,
                )
                preflight_short = None
                if result_short and _entry_result_ok(result_short):
                    order_short_id = _resolve_entry_id(result_short)
                    if not order_short_id:
                        _log_missing_entry_id("Short", result_short)
                        close_all_positions(0)
                        return kill_switch, signal_detected, trade_placed
                    order_status_short = "placed"
                    count_short = 1
                    remaining_capital_short = remaining_capital_short - initial_capital_usdt
                    # Extract stop loss price from result if available
                    entry_price_short = result_short.get("entry_price", 0)
                    stop_price_short = result_short.get("stop_price", 0)
                    if entry_price_short > 0 and stop_price_short > 0:
                        stop_distance_pct = abs(entry_price_short - stop_price_short) / entry_price_short * 100
                        logger.info(
                            "Short entry: id=%s capital=%.2f entry_price=%.2f stop=%.2f distance=%.2f%% remaining=%.2f",
                            order_short_id,
                            initial_capital_usdt,
                            entry_price_short,
                            stop_price_short,
                            stop_distance_pct,
                            remaining_capital_short,
                        )
                    else:
                        logger.info(
                            "Placed short entry: ticker=%s id=%s entry_price=%.6f capital=%.2f remaining=%.2f",
                            short_ticker,
                            order_short_id,
                            short_entry_price,
                            initial_capital_usdt,
                            remaining_capital_short,
                        )
                else:
                    order_short_id = ""
                    order_status_short = "failed"
                    logger.error("Short entry failed; closing any opened leg. Response: %s", result_short)
                    should_switch = _handle_compliance_restriction(result_short, short_ticker)
                    close_all_positions(0)
                    if should_switch:
                        return 3, signal_detected, trade_placed
                    return kill_switch, signal_detected, trade_placed
            
            # Exit loop after both orders placed
            if count_long == 1 and count_short == 1:
                msg = f"Both orders placed. Long: {order_status_long}, Short: {order_status_short}"
                print(msg)
                logger.info(msg)
                if order_long_id and order_short_id:
                    trade_placed = True

                if not limit_order_basis and order_long_id and order_short_id:
                    _log_entry_fills(order_long_id, order_short_id, long_ticker, short_ticker)

                # Record entry Z-score for regime break detection
                from func_pair_state import set_entry_z_score, clear_persistence_history, get_entry_time, set_entry_notional
                set_entry_z_score(latest_zscore)
                logger.info(f"📍 Entry Z-score recorded: {latest_zscore:.4f}")

                entry_time = get_entry_time()
                _open_trade_manager(latest_zscore, position_size=initial_capital_usdt * 2, entry_time=entry_time)
                set_entry_notional(initial_capital_usdt * 2)

                # Clear persistence history now that position is open
                clear_persistence_history()
                logger.info("🧹 Persistence history cleared (position opened)")

                break


            # Update the signal side
            if latest_zscore > 0:
                signal_side = "positive"
            else:
                signal_side = "negative"


            # Handle kill switch for Market orders
            if not limit_order_basis and count_long and count_short:
                kill_switch = 1
            
            # Allow for time to register the limit order
            time.sleep(3)

            # Check limit orders and ensure z-score still valid
            zscore_new, signal_sign_positive_new, metrics_new = get_latest_zscore() 
            if  kill_switch == 0:
                valid_zscores = [z for z in zscore_new if not math.isnan(z)]
                latest_zscore = valid_zscores[-1]
                
                # Check cointegration validity during monitoring
                if metrics_new.get("coint_flag", 0) != 1:
                    # Issue #13 Fix: Log kill-switch transition with trigger reason
                    msg = f"🔴 KILL-SWITCH TRIGGERED: Cointegration lost during trade (p_value >= {P_VALUE_CRITICAL})"
                    logger.error(msg)
                    print(msg)
                    kill_switch = 2
                    break

                # HARD STOP-LOSS: Regime break detection (Z-score too extreme = cointegration failed)
                if abs(latest_zscore) > ZSCORE_HARD_STOP:
                    # Issue #13 Fix: Log kill-switch transition with specific trigger
                    msg = f"🔴 KILL-SWITCH TRIGGERED: Regime break detected - Z-score={latest_zscore:.4f} exceeded hard stop {ZSCORE_HARD_STOP}"
                    logger.error(msg)
                    print(msg)
                    kill_switch = 2
                    break

                # SIGNAL DIRECTION FLIP: If Z-score flips sign unexpectedly, close immediately
                elif signal_sign_positive_new != signal_sign_positive:
                    # Issue #13 Fix: Log kill-switch transition with signal flip details
                    msg = f"🔴 KILL-SWITCH TRIGGERED: Signal direction flip - expected sign={signal_sign_positive}, got {signal_sign_positive_new}"
                    logger.error(msg)
                    print(msg)
                    kill_switch = 2
                    break

                # Log zscore update
                logger.info("Z-score update: %.4f", latest_zscore)

                # Check if Z-score still supports the position (within 90% of entry threshold)
                if abs(latest_zscore) > ENTRY_Z * 0.9 and signal_sign_positive_new == signal_sign_positive:

                    # Check long order status
                    if count_long == 1:
                        # VALIDATION: Ensure order_long_id is non-empty before checking
                        if not order_long_id or not isinstance(order_long_id, str):
                            logger.error(
                                "❌ Invalid long order ID: %s (type: %s). Skipping order check.",
                                repr(order_long_id),
                                type(order_long_id).__name__
                            )
                            order_status_long = "failed"
                        else:
                            order_status_long = check_order(long_ticker, order_long_id, remaining_capital_long, "buy")
                    
                    # Check short order status
                    if count_short == 1:
                        # VALIDATION: Ensure order_short_id is non-empty before checking
                        if not order_short_id or not isinstance(order_short_id, str):
                            logger.error(
                                "❌ Invalid short order ID: %s (type: %s). Skipping order check.",
                                repr(order_short_id),
                                type(order_short_id).__name__
                            )
                            order_status_short = "failed"
                        else:
                            order_status_short = check_order(short_ticker, order_short_id, remaining_capital_short, "sell")
                    # If orders still active, do nothing
                    if order_status_long == "Order Active" or order_status_short == "Order Active":
                        continue
                    # If orders partial filled, do nothing
                    if order_status_long == "Partial Fill" or order_status_short == "Partial Fill":
                        continue
                    # If orders trade complete, stop opening new trades
                    if order_status_long == "Trade Complete" and order_status_short == "Trade Complete":
                        msg = "✅ Trade executed successfully"
                        print(msg)
                        logger.info(msg)
                        trade_placed = True
                        if order_long_id and order_short_id:
                            _log_entry_fills(order_long_id, order_short_id, long_ticker, short_ticker)
                        kill_switch = 1                        
                    # If position filled, place another trade if capital remains
                    if order_status_long == "Position Filled" and order_status_short == "Position Filled":
                        msg = "✅ Trade executed successfully"
                        print(msg)
                        logger.info(msg)
                        trade_placed = True
                        if order_long_id and order_short_id:
                            _log_entry_fills(order_long_id, order_short_id, long_ticker, short_ticker)
                        if remaining_capital_long > 0 and remaining_capital_short > 0:
                            count_long = 0
                            count_short = 0
                        else:
                            kill_switch = 1
               
                    # If order cancelled for long - try again   
                    if order_status_long == "Try Again":
                        count_long = 0
                    # If order cancelled for short - try again
                    if order_status_short == "Try Again":
                        count_short = 0
                else:
                    # Cancel all active orders
                    logger.info("Z-score moved out of tolerance. Triggering exit mode (kill_switch=1).")
                    kill_switch = 1

    return kill_switch, signal_detected, trade_placed


def monitor_exit(kill_switch, health_check_due=False, zscore_results=None):
    """
    Monitor open positions for mean reversion or stop-loss.
    """
    # Get latest data
    if zscore_results:
        zscore, signal_sign_positive_new, metrics = zscore_results
    else:
        zscore, signal_sign_positive_new, metrics = get_latest_zscore()
        
    coint_flag = metrics.get("coint_flag", 0)
    
    valid_zscores = [z for z in zscore if not math.isnan(z)]
    if not valid_zscores:
        return kill_switch
        
    latest_zscore = valid_zscores[-1]
    _log_zscore_status(latest_zscore)

    # Track Z-score history for stall detection
    from func_pair_state import add_to_z_history
    add_to_z_history(latest_zscore)

    # 1. Periodic Health Check - ONLY FOR LOGGING, NOT IMMEDIATE EXIT
    # CRITICAL: Health checks are regime-level diagnostics for pair selection
    # They are NOT price-based risk controls and should NEVER force immediate exit
    if health_check_due:
        should_switch, score, rec = check_pair_health(metrics, latest_zscore, silent=False)
        if should_switch:
            # Log the health degradation but DO NOT exit position
            logger.warning(f"⚠️  Pair health degraded (score={score}) while in position.")
            logger.warning("This pair will be blacklisted after position closes normally.")
            logger.warning("Health checks do NOT force immediate exit - only price-based rules can.")
            # Mark pair for graveyard after position closes
            # (main_execution will handle this after normal exit)
            
    # 2. Advanced trade manager exit logic
    from func_pair_state import get_entry_z_score, get_entry_time
    entry_z = get_entry_z_score()
    entry_time = get_entry_time()

    if entry_z is not None:
        _ensure_trade_manager_state(entry_z, entry_time)
        tm_result = trade_manager.update(latest_zscore)

        if tm_result.get('action') == 'EXIT':
            msg = "KILL-SWITCH TRIGGERED: " + str(tm_result.get('message', tm_result.get('reason')))
            logger.warning(msg)
            print(msg)
            _close_trade_manager()
            return 2

        if tm_result.get('action') == 'PARTIAL_EXIT':
            percentage = tm_result.get('percentage', 0.0)
            if _execute_partial_exit(percentage):
                trade_manager.execute_partial_exit(pnl=0.0)
                logger.info("Partial exit completed (%.0f%%).", percentage * 100)
            else:
                logger.warning("Partial exit skipped (size below min or no position).")
                if trade_manager.trade_state is not None:
                    trade_manager.trade_state.partial_exits.append(
                        {"time": time.time(), "skipped": True}
                    )

        if tm_result.get('action') == 'WARNING':
            logger.warning(tm_result.get('reason', 'Trade manager warning'))
    else:
        _close_trade_manager()
        # NO ENTRY TRACKING (bot restarted with open positions)
        # CRITICAL: Don't apply regime break logic without entry context!
        # Only apply VERY conservative stops for true catastrophic scenarios
        logger.warning(f"⚠️  No entry Z-score tracked (restart scenario). Current Z={latest_zscore:.2f}")

        # Only trigger on EXTREME divergence (much higher threshold)
        if abs(latest_zscore) > 8.0:
            msg = f"🔴 KILL-SWITCH TRIGGERED: Catastrophic Z-score ({latest_zscore:.2f}) without entry context"
            logger.error(msg)
            print(msg)
            return 2
        else:
            logger.info(f"Holding position (no entry context). Will close on mean reversion only.")
        
    # 3. FUNDING BLEED GUARD (lowest priority)
    from func_position_calls import get_account_state
    state = get_account_state()
    total_unrealized_pnl = 0.0
    total_funding_cost = 0.0

    for pos in state.get("positions", []):
        upl = float(pos.get("upl", 0))
        funding = float(pos.get("fundingFee", 0))
        total_unrealized_pnl += upl
        total_funding_cost += abs(funding) if funding < 0 else 0

    if total_unrealized_pnl > 5.0 and total_funding_cost > 2.0:
        funding_ratio = (total_funding_cost / total_unrealized_pnl) * 100
        if funding_ratio > 30:
            msg = (
                "KILL-SWITCH TRIGGERED: Funding bleed - UPnL: +%.2f, Funding cost: %.2f (%.1f%% of profit)"
                % (total_unrealized_pnl, total_funding_cost, funding_ratio)
            )
            logger.warning(msg)
            print(msg)
            _close_trade_manager()
            return 2

    # 4. MEAN REVERSION (no entry context)
    if entry_z is None and abs(latest_zscore) <= EXIT_Z:
        msg = f"🟢 KILL-SWITCH TRIGGERED: Mean reversion exit (no entry context) - Z={latest_zscore:.4f}"
        logger.info(msg)
        print(msg)
        return 2

    # 5. MONITORING: Hold position
    _log_hold_position(latest_zscore)
    return kill_switch
