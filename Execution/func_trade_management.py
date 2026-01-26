from scipy.stats import false_discovery_control

from config_execution_api import account_session
from config_execution_api import signal_positive_ticker
from config_execution_api import signal_negative_ticker
from config_execution_api import signal_trigger_thresh
from config_execution_api import tradeable_capital_usdt
from config_execution_api import limit_order_basis
from config_execution_api import stop_loss_fail_safe

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

# Manage new trade assessment and order placing
def manage_new_trades(kill_switch):
    """
    Manage trade entry, monitoring, and exit.
    
    INPUT: kill_switch (expected: 0 = ACTIVE)
    
    FLOW:
    -----
    1. Get latest Z-score and check cointegration (p_value < 0.05)
    2. If cointegration fails → return 0 (no trade)
    3. If Z-score extreme AND cointegration valid → place orders
    4. Monitor orders and Z-score in real-time
    5. Exit conditions checked continuously:
       - Hard stop (Z > ±2.5) → kill_switch = 2
       - Signal flip → kill_switch = 2
       - Cointegration lost → kill_switch = 2
       - Mean reversion (Z ≈ 0.05) → kill_switch = 2
       - Both orders placed → kill_switch = 1
    
    RETURN:
    -------
    kill_switch: 0 (no trade), 1 (orders placed), or 2 (stop)
    
    LOGGING:
    --------
    All state changes, entries, exits, and stop triggers are logged with timestamps.
    """

    # Set variables
    order_long_id = ""
    order_short_id = ""
    signal_side = ""
    hot = False

    # Get and save the latest z-score
    zscore, signal_sign_positive, coint_flag = get_latest_zscore()

    # Filter out NaN values and get the latest valid z-score
    valid_zscores = [z for z in zscore if not math.isnan(z)]
    if not valid_zscores:
        logger.info("No valid z-scores yet (insufficient data for rolling window calculation)")
        return kill_switch
    
    latest_zscore = valid_zscores[-1]
    
    # Enforce cointegration check before trading (p_value < 0.05)
    if coint_flag != 1:
        logger.warning("Cointegration test failed (p_value >= 0.05): Pair not statistically valid for trading")
        return kill_switch
    
    # Switch to hot if meets signal threshold AND cointegration is valid
    if abs(latest_zscore) >= signal_trigger_thresh:

        # Activate hot trigger
        hot = True
        msg = f"Hot trigger activated: {signal_sign_positive} @ {latest_zscore:.4f}"
        print(msg)
        logger.info(msg)
        print("Placing and monitoring existing orders...")
        logger.info("Placing and monitoring existing orders...")

    # Place and manage trades
    if hot and kill_switch == 0:

        # Get the trade history for liquidity
        avg_liquidity_ticker_p, last_price_p = get_ticker_trade_liquidity(signal_positive_ticker)
        avg_liquidity_ticker_n, last_price_n = get_ticker_trade_liquidity(signal_negative_ticker)

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
            zscore_new, signal_sign_positive_new, coint_flag_new = get_latest_zscore() 
            if  kill_switch == 0:
                valid_zscores = [z for z in zscore_new if not math.isnan(z)]
                latest_zscore = valid_zscores[-1]
                
                # Check cointegration validity during monitoring
                if coint_flag_new != 1:
                    logger.warning("Cointegration lost during trade (p_value >= 0.05): Closing position")
                    account_session.cancel_orders(inst_id=signal_positive_ticker)
                    account_session.cancel_orders(inst_id=signal_negative_ticker)
                    kill_switch = 2
                    break

                # HARD STOP-LOSS: Regime break detection (Z-score too extreme = cointegration failed)
                # HARD STOP-LOSS: Regime break detection (Z-score too extreme = cointegration failed)
                if abs(latest_zscore) > ZSCORE_HARD_STOP:
                    msg = f"⚠️  REGIME BREAK DETECTED: Z-score={latest_zscore:.4f} exceeded hard stop {ZSCORE_HARD_STOP}"
                    print(msg)
                    logger.warning(msg)
                    account_session.cancel_orders(inst_id=signal_positive_ticker)
                    account_session.cancel_orders(inst_id=signal_negative_ticker)
                    kill_switch = 2
                    break

                # SIGNAL DIRECTION FLIP: If Z-score flips sign unexpectedly, close immediately
                elif signal_sign_positive_new != signal_sign_positive:
                    msg = f"⚠️  SIGNAL FLIPPED: Expected {signal_sign_positive}, got {signal_sign_positive_new}"
                    print(msg)
                    logger.warning(msg)
                    account_session.cancel_orders(inst_id=signal_positive_ticker)
                    account_session.cancel_orders(inst_id=signal_negative_ticker)
                    kill_switch = 2
                    break

                # Log zscore update
                logger.info("Z-score update: %.4f", latest_zscore)

                if abs(latest_zscore) > signal_trigger_thresh * 0.9 and signal_sign_positive_new == signal_sign_positive:

                    # Check long order status
                    if count_long == 1:
                        order_status_long = check_order(long_ticker, order_long_id, remaining_capital_long, "buy")
                    # Check short order status
                    if count_short == 1:
                        order_status_short = check_order(short_ticker, order_short_id, remaining_capital_short, "sell")
                    # If orders still active, do nothing
                    if order_status_long == "Order Active" or order_status_short == "Order Active":
                        continue
                    # If orders partial filled, do nothing
                    if order_status_long == "Partial Fill" or order_status_short == "Partial Fill":
                        continue
                    # If orders trade complete, stop opening new trades
                    if order_status_long == "Trade Complete" and order_status_short == "Trade Complete":
                        kill_switch = 1                        
                    # If position filled, place another trade if capital remains
                    if order_status_long == "Position Filled" and order_status_short == "Position Filled":
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
                    account_session.cancel_orders(inst_id=signal_positive_ticker)
                    account_session.cancel_orders(inst_id=signal_negative_ticker)
                    logger.info("Cancelled active orders due to z-score moving out of tolerance")
                    kill_switch = 1

    # Check for signal to be false and exit at mean reversion
    if kill_switch == 1:
        """
        Exit when mean reversion is complete:
        - Positive signal: Z-score has reverted near zero (exit target)
        - Negative signal: Z-score has reverted to near zero from below
        
        This captures the full arbitrage profit while accounting for fees (~0.07% round-trip)
        """
        if signal_side == "positive" and latest_zscore < ZSCORE_EXIT_TARGET:
            msg = f"✅ Mean reversion complete (Z={latest_zscore:.4f} < {ZSCORE_EXIT_TARGET}): Taking profit"
            print(msg)
            logger.info(msg)
            kill_switch = 2
        elif signal_side == "negative" and latest_zscore > -ZSCORE_EXIT_TARGET:
            msg = f"✅ Mean reversion complete (Z={latest_zscore:.4f} > {-ZSCORE_EXIT_TARGET}): Taking profit"
            print(msg)
            logger.info(msg)
            kill_switch = 2