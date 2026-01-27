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
    Z_SCORE_CRITICAL
)

from func_pair_state import get_consecutive_losses

# Risk management thresholds
ZSCORE_HARD_STOP = 2.5  # Hard stop-loss if Z-score exceeds this (regime break detection)
ZSCORE_EXIT_TARGET = 0.05  # Exit at mean reversion with small buffer for fees (~0.07% round-trip)
RISK_PER_TRADE_PCT = 0.02  # 2% of total capital risked per trade

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
from func_price_calls import get_ticker_trade_liquidity
from func_get_zscore import get_latest_zscore
from func_execution_calls import initialise_order_execution
from func_order_review import check_order
import time
import math
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import datetime

# Logger for trade management diagnostics
log_path = Path(__file__).resolve().parent / "logfile_okx.log"
logger = logging.getLogger("func_trade_management")
if not logger.handlers:
    # RotatingFileHandler: max 5MB per file, keep 3 backup files
    fh = RotatingFileHandler(log_path, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.setLevel(logging.INFO)

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
    
    # ENTRY LOGIC
    if not in_position:
        # Check if Z-score has persisted at extreme level for MIN_PERSIST_BARS bars
        if len(z_history) >= MIN_PERSIST_BARS:
            recent_zscores = z_history[-MIN_PERSIST_BARS:]
            all_extreme = all(abs(z) >= ENTRY_Z for z in recent_zscores)
            
            if all_extreme:
                # Determine direction based on current Z-score
                if current_z <= -ENTRY_Z:
                    return "BUY_SPREAD", f"Entry signal: Z={current_z:.4f} persistent at -ENTRY_Z (oversold, bars={MIN_PERSIST_BARS})"
                elif current_z >= ENTRY_Z:
                    return "SELL_SPREAD", f"Entry signal: Z={current_z:.4f} persistent at +ENTRY_Z (overbought, bars={MIN_PERSIST_BARS})"
            else:
                return None, f"No entry - Z-score not persistent (need {MIN_PERSIST_BARS} bars, got recent avg={abs(sum(recent_zscores)/len(recent_zscores)):.4f})"
        else:
            return None, f"Insufficient history: {len(z_history)} bars < {MIN_PERSIST_BARS} required"
    
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
    if abs(zscore) < 1.0:
        status = "😴 Very quiet (|Z| < 1.0)"
    elif abs(zscore) < 2.0:
        status = "⏳ Waiting (1.0 < |Z| < 2.0)"
    elif abs(zscore) < 3.0:
        status = "🎯 TRADEABLE (|Z| > 2.0)"
    else:
        status = "🚨 Extreme (|Z| > 3.0)"
    
    msg = f"Current Z-Score: {zscore:+.2f} - {status}"
    logger.info(msg)


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
        should_switch, score, rec = check_pair_health(metrics, latest_zscore)
        if should_switch:
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
    else:
        # Log waiting status
        if abs(latest_zscore) < ENTRY_Z:
            logger.info("⏳ WAITING: Not at entry threshold yet")
        else:
            # It's beyond threshold but not persistent yet
            logger.info(f"⏳ WAITING: Z-score extreme ({latest_zscore:+.2f}) but not persistent yet")

    # Place and manage trades
    if hot and kill_switch == 0:

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
        # Risk per trade = 2% of total capital
        risk_usdt = tradeable_capital_usdt * RISK_PER_TRADE_PCT
        
        # Stop loss distance in percentage (3% = 0.03)
        stop_loss_pct = stop_loss_fail_safe
        
        # Position size = Risk / Stop distance
        # This ensures we never risk more than 2% per trade
        initial_capital_usdt = risk_usdt / stop_loss_pct
        
        # Split equally between long and short
        capital_long = initial_capital_usdt
        capital_short = initial_capital_usdt
        
        # Validate against available capital
        if initial_capital_usdt * 2 > tradeable_capital_usdt:
            logger.warning(
                "Position size (%.2f per side) would exceed total capital. Reducing to 50/50 split.",
                initial_capital_usdt
            )
            capital_long = tradeable_capital_usdt * 0.5
            capital_short = tradeable_capital_usdt * 0.5
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
        
        initial_fill_target_long_usdt = avg_liquidity_long * last_price_long
        initial_fill_target_short_usdt = avg_liquidity_short * last_price_short
        initial_capital_injection_usdt = min(initial_fill_target_long_usdt, initial_fill_target_short_usdt)

        # Ensure initial capital injection does not exceed allocated capital
        if limit_order_basis:
            if initial_capital_injection_usdt > capital_long:
                initial_capital_usdt = capital_long
            else:
                initial_capital_usdt = initial_capital_injection_usdt
        else:
            initial_capital_usdt = capital_long

        logger.info(
            "Liquidity check: long_target=%.2f short_target=%.2f liquidity_long=%.4f liquidity_short=%.4f",
            initial_fill_target_long_usdt,
            initial_fill_target_short_usdt,
            avg_liquidity_long,
            avg_liquidity_short,
        )

        # Set the remaining capital
        remaining_capital_long = capital_long
        remaining_capital_short = capital_short

        # Trade until filled or signal is false
        order_status_long = ""
        order_status_short = ""
        count_long = 0
        count_short = 0
        while kill_switch == 0:
            # Place long order
            if count_long == 0:
                result_long = initialise_order_execution(
                    long_ticker,
                    "buy",
                    initial_capital_usdt,
                )
                if result_long:
                    order_long_id = result_long.get("entry_id", "")
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
                            "Placed long entry: id=%s capital=%.2f remaining=%.2f",
                            order_long_id,
                            initial_capital_usdt,
                            remaining_capital_long,
                        )
                else:
                    order_long_id = ""
                    order_status_long = "failed"

            # Place short order
            if count_short == 0:
                result_short = initialise_order_execution(
                    short_ticker,
                    "sell",
                    initial_capital_usdt,
                )
                if result_short:
                    order_short_id = result_short.get("entry_id", "")
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
                            "Placed short entry: id=%s capital=%.2f remaining=%.2f",
                            order_short_id,
                            initial_capital_usdt,
                            remaining_capital_short,
                        )
                else:
                    order_short_id = ""
                    order_status_short = "failed"
            
            # Exit loop after both orders placed
            if count_long == 1 and count_short == 1:
                msg = f"Both orders placed. Long: {order_status_long}, Short: {order_status_short}"
                print(msg)
                logger.info(msg)
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
                        kill_switch = 1                        
                    # If position filled, place another trade if capital remains
                    if order_status_long == "Position Filled" and order_status_short == "Position Filled":
                        msg = "✅ Trade executed successfully"
                        print(msg)
                        logger.info(msg)
                        trade_placed = True
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

    # 1. Periodic Health Check
    if health_check_due or coint_flag == 0:
        # Note: we might not want to switch immediately if in position, 
        # but the previous logic did. I'll stick to previous logic for now.
        should_switch, score, rec = check_pair_health(metrics, latest_zscore)
        if should_switch:
            # If in position, maybe we should close first?
            # Current bot logic for kill_switch=3 in main_execution calls _switch_to_next_pair
            # which doesn't close positions. 
            # I'll let main handle closing if kill_switch becomes 2.
            # But if it's 3, it restarts.
            # Usually, we should exit if health is bad.
            logger.warning("Pair health failed while in position. Triggering exit.")
            return 2 # Trigger close all
            
    # 2. EXIT LOGIC: Mean Reversion
    if abs(latest_zscore) <= EXIT_Z:
        msg = f"🟢 KILL-SWITCH TRIGGERED: Mean reversion exit - Z={latest_zscore:.4f} reverted within EXIT_Z={EXIT_Z}"
        logger.info(msg)
        print(msg)
        return 2

    # 3. HARD STOP-LOSS: Regime break
    if abs(latest_zscore) > ZSCORE_HARD_STOP:
        msg = f"🔴 KILL-SWITCH TRIGGERED: Regime break detected - Z={latest_zscore:.4f} exceeded hard stop {ZSCORE_HARD_STOP}"
        logger.error(msg)
        print(msg)
        return 2
        
    # 4. MONITORING: Hold position
    logger.info(f"Hold position - Z={latest_zscore:.4f} still beyond EXIT_Z ({EXIT_Z})")
    return kill_switch