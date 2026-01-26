# Remove Pandas Future Warnings
import os
import warnings
import logging

warnings.simplefilter(action="ignore", category=FutureWarning)

# General imports
from config_execution_api import (
    default_leverage,
    max_cycles,
    pos_mode,
    signal_negative_ticker,
    signal_positive_ticker,
    tradeable_capital_usdt,
    max_drawdown_pct,
    ticker_1,
    ticker_2,
)
from func_position_calls import open_position_confirmation, active_position_confirmation
from func_trade_management import manage_new_trades
from func_execution_calls import set_leverage
from func_close_positions import close_all_positions, get_position_info
from func_save_status import save_status
import time

# Setup logging
logger = logging.getLogger("main_execution")
if not logger.handlers:
    from logging.handlers import RotatingFileHandler
    from pathlib import Path
    log_path = Path(__file__).resolve().parent / "logfile_okx.log"
    fh = RotatingFileHandler(log_path, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.setLevel(logging.INFO)


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

Triggers for state changes:
---------------------------
0 → 1:  Signal detected (Z-score > threshold, cointegration valid)
1 → 2:  • Orders fully monitored/closed
         • Circuit breaker (P&L drawdown > 5%)
         • Hard stop (Z-score > ±2.5)
         • Signal flip (Z-score sign changes)
         • Cointegration lost during trade
         • Mean reversion complete (Z ≈ 0.05)
"""


def _calculate_cumulative_pnl(ticker_p, ticker_n):
    """
    Calculate cumulative P&L from both open positions.
    Returns (total_pnl_usdt, pnl_pct)
    
    Simple approach: Gets position details + current prices and calculates mark-to-market P&L
    from OKX position data (avgPx field contains entry price).
    """
    try:
        from func_position_calls import get_open_positions
        from func_price_calls import get_ticker_trade_liquidity
        
        total_pnl = 0.0
        
        # Get long position for positive ticker
        entry_price_p_long, size_p_long = get_open_positions(ticker_p, direction="Long")
        if entry_price_p_long and size_p_long and size_p_long > 0:
            _, current_price_p = get_ticker_trade_liquidity(ticker_p, limit=1)
            if current_price_p and current_price_p > 0:
                pnl_p_long = (current_price_p - entry_price_p_long) * size_p_long
                total_pnl += pnl_p_long
                logger.debug(f"P&L {ticker_p} LONG: entry={entry_price_p_long:.4f} current={current_price_p:.4f} size={size_p_long} pnl={pnl_p_long:.2f}")
        
        # Get short position for positive ticker
        entry_price_p_short, size_p_short = get_open_positions(ticker_p, direction="Short")
        if entry_price_p_short and size_p_short and size_p_short > 0:
            _, current_price_p = get_ticker_trade_liquidity(ticker_p, limit=1)
            if current_price_p and current_price_p > 0:
                pnl_p_short = (entry_price_p_short - current_price_p) * size_p_short
                total_pnl += pnl_p_short
                logger.debug(f"P&L {ticker_p} SHORT: entry={entry_price_p_short:.4f} current={current_price_p:.4f} size={size_p_short} pnl={pnl_p_short:.2f}")
        
        # Get long position for negative ticker
        entry_price_n_long, size_n_long = get_open_positions(ticker_n, direction="Long")
        if entry_price_n_long and size_n_long and size_n_long > 0:
            _, current_price_n = get_ticker_trade_liquidity(ticker_n, limit=1)
            if current_price_n and current_price_n > 0:
                pnl_n_long = (current_price_n - entry_price_n_long) * size_n_long
                total_pnl += pnl_n_long
                logger.debug(f"P&L {ticker_n} LONG: entry={entry_price_n_long:.4f} current={current_price_n:.4f} size={size_n_long} pnl={pnl_n_long:.2f}")
        
        # Get short position for negative ticker
        entry_price_n_short, size_n_short = get_open_positions(ticker_n, direction="Short")
        if entry_price_n_short and size_n_short and size_n_short > 0:
            _, current_price_n = get_ticker_trade_liquidity(ticker_n, limit=1)
            if current_price_n and current_price_n > 0:
                pnl_n_short = (entry_price_n_short - current_price_n) * size_n_short
                total_pnl += pnl_n_short
                logger.debug(f"P&L {ticker_n} SHORT: entry={entry_price_n_short:.4f} current={current_price_n:.4f} size={size_n_short} pnl={pnl_n_short:.2f}")
        
        pnl_pct = (total_pnl / tradeable_capital_usdt * 100) if tradeable_capital_usdt > 0 else 0.0
        
        # Log summary
        if total_pnl != 0.0:
            logger.info(f"Cumulative P&L: {total_pnl:.2f} USDT ({pnl_pct:.2f}%) | Threshold: {-tradeable_capital_usdt * max_drawdown_pct:.2f} USDT")
        
        return total_pnl, pnl_pct
    except Exception as e:
        logger.error(f"Error calculating P&L: {e}")
        # Return 0 safely to avoid circuit breaker issues
        return 0.0, 0.0


""" RUN STATBOT """
if __name__ == "__main__":
    # Validate ticker configuration at startup
    try:
        _validate_ticker_configuration()
    except AssertionError as e:
        logger.critical(str(e))
        print(str(e))
        exit(1)
    
    # Run the bot
    print("StatBot initialised...")

    # Initialise variables
    status_dict = {"message": "starting..."}
    order_long = {}
    order_short = {}
    signal_sign_positive = False
    kill_switch = 0

    # Save status
    save_status(status_dict)

    # Set leverage in case forgotten to do so on the platform
    print("Setting leverage...")
    _set_leverage_for_ticker(signal_positive_ticker, default_leverage)
    _set_leverage_for_ticker(signal_negative_ticker, default_leverage)

    # Commence bot
    print("Seeking trades...")
    try:
        cycle_limit = int(os.getenv("STATBOT_MAX_CYCLES", max_cycles))
    except (TypeError, ValueError):
        cycle_limit = max_cycles
    if cycle_limit < 0:
        cycle_limit = 0

    cycles_run = 0
    while True:

        # Pause - protect API
        time.sleep(3)

        # CHECK POSITION STATUS FIRST: Determine if we should manage new trades or close existing ones
        is_p_ticker_open = open_position_confirmation(signal_positive_ticker)
        is_n_ticker_open = open_position_confirmation(signal_negative_ticker)
        is_p_ticker_active = active_position_confirmation(signal_positive_ticker)
        is_n_ticker_active = active_position_confirmation(signal_negative_ticker)
        checks_all = [is_p_ticker_open, is_n_ticker_open, is_p_ticker_active, is_n_ticker_active]
        is_manage_new_trades = not any(checks_all)

        # CIRCUIT BREAKER: Check cumulative P&L AFTER position confirmation
        total_pnl, pnl_pct = _calculate_cumulative_pnl(signal_positive_ticker, signal_negative_ticker)
        max_loss_allowed = tradeable_capital_usdt * max_drawdown_pct
        
        if total_pnl < -max_loss_allowed:
            msg = f"⚠️  CIRCUIT BREAKER TRIGGERED: P&L={total_pnl:.2f} USDT ({pnl_pct:.2f}%) exceeds max drawdown {max_drawdown_pct*100:.1f}%"
            print(msg)
            logger.warning(msg)
            status_dict["message"] = "Circuit breaker triggered - closing all positions"
            save_status(status_dict)
            close_all_positions(0)
            break

        # Save status
        status_dict["message"] = "Initial checks made..."
        status_dict["checks"] = checks_all
        status_dict["cumulative_pnl_usdt"] = total_pnl
        status_dict["cumulative_pnl_pct"] = pnl_pct
        save_status(status_dict)

        # Check for signal and place new trades
        if is_manage_new_trades and kill_switch == 0:
            status_dict["message"] = "Managing new trades..."
            save_status(status_dict)
            kill_switch = manage_new_trades(kill_switch) or kill_switch


        # Close all active orders and positions
        if kill_switch == 2:
            status_dict["message"] = "Closing existing trades..."
            save_status(status_dict)
            kill_switch = close_all_positions(kill_switch)

            # Sleep for 5 seconds
            time.sleep(5)

        cycles_run += 1
        if cycle_limit and cycles_run >= cycle_limit:
            status_dict["message"] = "Max cycles reached; exiting."
            save_status(status_dict)
            break
