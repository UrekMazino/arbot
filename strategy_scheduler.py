"""
STRATEGY SCHEDULER - Runs Strategy cointegration discovery hourly
Without interrupting the Execution process
"""

import os
import sys
import time
import subprocess
import logging
from datetime import datetime
from pathlib import Path


def setup_logger():
    """Setup scheduler logger"""
    log_dir = Path(__file__).resolve().parent / "Logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"strategy_scheduler_{timestamp}.log"

    logger = logging.getLogger("strategy_scheduler")
    logger.setLevel(logging.INFO)

    # File handler
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.INFO)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger


def run_strategy_scan(logger):
    """Execute Strategy main_strategy.py as subprocess"""
    strategy_dir = Path(__file__).resolve().parent / "Strategy"
    strategy_script = strategy_dir / "main_strategy.py"

    if not strategy_script.exists():
        logger.error(f"Strategy script not found: {strategy_script}")
        return False

    logger.info("=" * 60)
    logger.info("Starting Strategy cointegration scan...")
    logger.info("=" * 60)

    start_time = time.time()

    try:
        # Run strategy as subprocess
        result = subprocess.run(
            [sys.executable, str(strategy_script)],
            cwd=str(strategy_dir),
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )

        duration = time.time() - start_time

        # Log output
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                logger.info(f"[Strategy] {line}")

        if result.stderr and result.returncode != 0:
            for line in result.stderr.strip().split('\n'):
                logger.error(f"[Strategy ERROR] {line}")

        if result.returncode == 0:
            logger.info(f"Strategy scan completed successfully in {duration:.1f}s")
            return True
        else:
            logger.error(f"Strategy scan failed with exit code {result.returncode}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("Strategy scan timed out after 600 seconds")
        return False
    except Exception as e:
        logger.error(f"Strategy scan error: {e}")
        return False


def main():
    """Main scheduler loop - runs Strategy every hour"""
    logger = setup_logger()

    # Get interval from environment (default 3600 = 1 hour)
    try:
        interval_seconds = int(os.getenv("STATBOT_STRATEGY_INTERVAL", "3600"))
        if interval_seconds < 300:  # Minimum 5 minutes
            logger.warning(f"Interval {interval_seconds}s too short, using 300s minimum")
            interval_seconds = 300
    except (TypeError, ValueError):
        interval_seconds = 3600

    interval_hours = interval_seconds / 3600

    logger.info("=" * 60)
    logger.info("STRATEGY SCHEDULER STARTED")
    logger.info("=" * 60)
    logger.info(f"Interval: {interval_seconds}s ({interval_hours:.2f}h)")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)

    run_count = 0
    success_count = 0
    fail_count = 0

    try:
        while True:
            run_count += 1

            logger.info(f"Run #{run_count} starting at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            success = run_strategy_scan(logger)

            if success:
                success_count += 1
            else:
                fail_count += 1

            logger.info("=" * 60)
            logger.info(f"Run #{run_count} complete")
            logger.info(f"Stats: Total={run_count} Success={success_count} Fail={fail_count}")
            logger.info(f"Next run in {interval_seconds}s ({interval_hours:.2f}h) at {datetime.fromtimestamp(time.time() + interval_seconds).strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 60)

            # Wait for next interval
            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        logger.info("=" * 60)
        logger.info("STRATEGY SCHEDULER STOPPED (Ctrl+C)")
        logger.info(f"Final Stats: Total={run_count} Success={success_count} Fail={fail_count}")
        logger.info("=" * 60)
        return 0
    except Exception as e:
        logger.error(f"Scheduler error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
