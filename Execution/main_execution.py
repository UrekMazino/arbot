# Remove Pandas Future Warnings
import os
import warnings

warnings.simplefilter(action="ignore", category=FutureWarning)

# General imports
from config_execution_api import (
    default_leverage,
    max_cycles,
    pos_mode,
    signal_negative_ticker,
    signal_positive_ticker,
)
from func_position_calls import open_position_confirmation, active_position_confirmation
from func_trade_management import manage_new_trades
from func_execution_calls import set_leverage
from func_close_positions import close_all_positions
from func_save_status import save_status
import time


def _is_hedged_mode(mode_value):
    normalized = str(mode_value or "").strip().lower()
    return normalized in ("long_short", "long_short_mode", "hedge", "hedged")


def _set_leverage_for_ticker(ticker, leverage):
    if _is_hedged_mode(pos_mode):
        set_leverage(ticker, leverage, pos_side="long")
        set_leverage(ticker, leverage, pos_side="short")
        return
    set_leverage(ticker, leverage)


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
