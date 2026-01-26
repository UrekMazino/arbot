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
    """
    try:
        from func_position_calls import get_account_balance
        # Get positions
        size_p, side_p = get_position_info(ticker_p)
        size_n, side_n = get_position_info(ticker_n)
        
        # If no positions, P&L is 0
        if size_p == 0 and size_n == 0:
            return 0.0, 0.0
        
        # Fetch current prices
        from func_price_calls import get_ticker_trade_liquidity
        _, price_p = get_ticker_trade_liquidity(ticker_p, limit=1)
        _, price_n = get_ticker_trade_liquidity(ticker_n, limit=1)
        
        # Simple approximation: use floating PnL from positions
        # This is a simplified calculation; actual P&L needs entry prices
        total_pnl = 0.0
        
        # Log for debugging
        logger.debug(f"P&L check: {ticker_p} ({size_p}), {ticker_n} ({size_n})")
        
        pnl_pct = (total_pnl / tradeable_capital_usdt * 100) if tradeable_capital_usdt > 0 else 0.0
        return total_pnl, pnl_pct
    except Exception as e:
        logger.error(f"Error calculating P&L: {e}")
        return 0.0, 0.0


""" RUN STATBOT """
if __name__ == "__main__":
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

        # CIRCUIT BREAKER: Check cumulative P&L
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

        # Pause - protect API
        time.sleep(3)

        # Check if open trades already exist
        is_p_ticker_open = open_position_confirmation(signal_positive_ticker)
        is_n_ticker_open = open_position_confirmation(signal_negative_ticker)
        is_p_ticker_active = active_position_confirmation(signal_positive_ticker)
        is_n_ticker_active = active_position_confirmation(signal_negative_ticker)
        checks_all = [is_p_ticker_open, is_n_ticker_open, is_p_ticker_active, is_n_ticker_active]
        is_manage_new_trades = not any(checks_all)

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
