# Remove Pandas Future Warnings
import os
import warnings
import logging
import time
import sys
import subprocess
from pathlib import Path
from logging.handlers import RotatingFileHandler

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
    save_active_pair,
    STATUS_UPDATE_INTERVAL,
    HEALTH_CHECK_INTERVAL
)
from func_position_calls import (
    open_position_confirmation, 
    active_position_confirmation,
    get_account_state,
    check_inst_status,
    get_pos_data_from_state
)
from func_price_calls import get_ticker_trade_liquidity
from func_trade_management import manage_new_trades, monitor_exit
from func_get_zscore import get_latest_zscore
from func_execution_calls import set_leverage
from func_close_positions import close_all_positions, get_position_info
from func_save_status import save_status
from func_pair_state import (
    add_to_graveyard,
    is_in_graveyard,
    can_switch,
    set_last_switch_time,
    get_last_switch_time,
    record_trade_result,
    get_last_health_score
)

# Setup logging
logger = logging.getLogger("main_execution")
if not logger.handlers:
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


def _switch_to_next_pair(health_score=None):
    """
    Read the cointegrated pairs from Strategy folder and switch to the next one.
    Includes Graveyard and Cooldown checks with emergency override for critical health.

    Args:
        health_score: Current pair health score (0-100). If below 25, overrides cooldown.
    """
    import pandas as pd
    from pathlib import Path

    # 1. Check Cooldown with emergency override
    last_switch = get_last_switch_time()
    elapsed = (time.time() - last_switch) / 3600

    if not can_switch(cooldown_hours=24, health_score=health_score, emergency_threshold=40):
        logger.warning(f"Switch aborted: Cooldown active ({elapsed:.1f}h elapsed, 24h required)")
        if health_score is not None:
            logger.warning(f"Health score: {health_score}/100 (emergency override requires < 40)")
        return False

    # Log if emergency override was used
    if health_score is not None and health_score < 40:
        logger.warning(f"🚨 EMERGENCY OVERRIDE: Health score {health_score} < 40, bypassing cooldown ({elapsed:.1f}h elapsed)")
    elif elapsed < 24:
        logger.info(f"⚠️  Cooldown bypassed but health not critical: {health_score}/100")

    logger.info("Attempting to switch to next pair...")
    csv_path = Path(__file__).resolve().parent.parent / "Strategy" / "2_cointegrated_pairs.csv"
    if not csv_path.exists():
        logger.error(f"Cannot switch pair: CSV not found at {csv_path}")
        return False
        
    try:
        logger.info(f"Reading pairs from {csv_path}...")
        df = pd.read_csv(csv_path)
        if df.empty:
            logger.error("Cannot switch pair: CSV is empty")
            return False
            
        # Get current pair from config
        curr_t1 = ticker_1
        curr_t2 = ticker_2
        logger.info(f"Current pair: {curr_t1}/{curr_t2}")
        
        # Add current pair to graveyard before switching
        add_to_graveyard(curr_t1, curr_t2)
        
        # Ensure we have the necessary columns
        if 'sym_1' not in df.columns or 'sym_2' not in df.columns:
            logger.error(f"CSV missing sym_1 or sym_2 columns. Columns found: {df.columns.tolist()}")
            return False
            
        pairs = list(zip(df['sym_1'], df['sym_2']))
        logger.info(f"Found {len(pairs)} pairs in CSV.")
        
        # Find current pair index
        curr_idx = -1
        for i, (s1, s2) in enumerate(pairs):
            if (s1 == curr_t1 and s2 == curr_t2) or (s1 == curr_t2 and s2 == curr_t1):
                curr_idx = i
                break
        
        # Search for next healthy pair (not in graveyard)
        next_t1, next_t2 = None, None
        for i in range(1, len(pairs)):
            idx = (curr_idx + i) % len(pairs)
            t1, t2 = pairs[idx]
            if not is_in_graveyard(t1, t2):
                next_t1, next_t2 = t1, t2
                logger.info(f"Found healthy replacement at index {idx}: {next_t1}/{next_t2}")
                break
        
        if next_t1 is None:
            logger.error("❌ No suitable replacement pair found in CSV (all pairs in graveyard or CSV too small)")
            return False
            
        msg = f"🔄 Switching from {curr_t1}/{curr_t2} to {next_t1}/{next_t2}"
        print(msg)
        logger.info(msg)
        
        if save_active_pair(next_t1, next_t2):
            logger.info("New pair saved to active_pair.json")
            set_last_switch_time() # Update switch timestamp
            return True
        else:
            logger.error("Failed to save new pair to active_pair.json")
            return False
    except Exception as e:
        logger.error(f"Error switching pair: {e}")
        return False


def _calculate_cumulative_pnl(ticker_p, ticker_n, state, price_p=None, price_n=None):
    """
    Calculate cumulative P&L from open positions using fetched account state.
    """
    try:
        total_pnl = 0.0
        
        # Get position data from state
        # Direction doesn't matter much for get_pos_data_from_state if we want any, 
        # but the strategy usually has one per ticker.
        # Check both Long and Short just in case.
        
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
                        logger.debug(f"P&L {ticker} {direction.upper()}: entry={entry_price:.4f} current={current_price:.4f} size={size} pnl={pnl:.2f}")
        
        pnl_pct = (total_pnl / tradeable_capital_usdt * 100) if tradeable_capital_usdt > 0 else 0.0
        
        # Log summary
        if total_pnl != 0.0:
            logger.info(f"Cumulative P&L: {total_pnl:.2f} USDT ({pnl_pct:.2f}%) | Threshold: {-tradeable_capital_usdt * max_drawdown_pct:.2f} USDT")
        
        return total_pnl, pnl_pct
    except Exception as e:
        logger.error(f"Error calculating P&L: {e}")
        return 0.0, 0.0


""" RUN STATBOT """
if __name__ == "__main__":
    # Manager process to handle restarts (especially on Windows)
    if os.getenv("STATBOT_MANAGED") != "1":
        while True:
            env = os.environ.copy()
            env["STATBOT_MANAGED"] = "1"
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
    
    # Run the bot
    print("StatBot initialised...")

    # Initialise variables
    status_dict = {"message": "starting..."}
    order_long = {}
    order_short = {}
    signal_sign_positive = False
    kill_switch = 0
    
    # Session tracking
    pair_start_time = time.time()
    last_health_check = time.time()  # First check on startup or after 1h
    last_status_update = time.time()
    signals_seen = 0
    trades_executed = 0

    # Save status
    save_status(status_dict)

    # Set leverage in case forgotten to do so on the platform
    print("Setting leverage...")
    _set_leverage_for_ticker(signal_positive_ticker, default_leverage)
    _set_leverage_for_ticker(signal_negative_ticker, default_leverage)
    
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

            # 2. Market Data Fetch
            zscore_results = get_latest_zscore()
            _, _, metrics = zscore_results
            price_p, price_n = metrics.get("price_1"), metrics.get("price_2")

            # 3. CIRCUIT BREAKER: Check cumulative P&L
            total_pnl, pnl_pct = _calculate_cumulative_pnl(
                signal_positive_ticker, signal_negative_ticker,
                acc_state, price_p, price_n
            )

            # Log cycle with PnL
            pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
            logger.info(f"--- Cycle {cycles_run} | {ticker_1}/{ticker_2} | {pnl_emoji} PnL: {total_pnl:+.2f} USDT ({pnl_pct:+.2f}%) ---")

            # Trading Status Update every minute
            if current_time - last_status_update >= STATUS_UPDATE_INTERVAL:
                time_in_pair_min = (current_time - pair_start_time) / 60
                logger.info("--- Trading Status Update ---")
                logger.info(f"Time in pair: {time_in_pair_min:.1f} min")
                logger.info(f"Signals seen: {signals_seen} | Trades: {trades_executed}")
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
                if tr_placed: trades_executed += 1
            
            # 5. Monitoring existing trades / Mean reversion exit
            if not is_manage_new_trades or kill_switch == 1:
                res_ks = monitor_exit(kill_switch, health_check_due, zscore_results)
                kill_switch = res_ks

            # Handle pair switch signal (e.g. health check failed)
            if kill_switch == 3:
                status_dict["message"] = "Health check failed; switching pair..."
                save_status(status_dict)
                logger.info("Kill switch 3: Pair health degraded. Switching to next prospect...")

                # Get the last health score for emergency override
                health_score = get_last_health_score()

                if _switch_to_next_pair(health_score=health_score):
                    logger.info("Restarting process via Subprocess Manager (exit code 3)...")
                    print("Restarting to apply new pair...")
                    # Exit with code 3 to signal the manager to restart
                    sys.exit(3)
                else:
                    logger.error("Pair switch failed. Resetting kill_switch to 0.")
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
