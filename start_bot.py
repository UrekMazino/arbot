"""
START BOT - Launch both Execution and Strategy Scheduler
"""

import os
import sys
import subprocess
import time
import signal
from pathlib import Path


processes = []


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\n\n" + "=" * 60)
    print("Stopping all processes...")
    print("=" * 60)

    for proc_name, proc in processes:
        if proc.poll() is None:  # Still running
            print(f"Terminating {proc_name}...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print(f"Force killing {proc_name}...")
                proc.kill()

    print("All processes stopped.")
    sys.exit(0)


def main():
    """Launch Execution and Strategy Scheduler concurrently"""
    signal.signal(signal.SIGINT, signal_handler)

    base_dir = Path(__file__).resolve().parent
    execution_script = base_dir / "Execution" / "main_execution.py"
    scheduler_script = base_dir / "strategy_scheduler.py"

    # Validate scripts exist
    if not execution_script.exists():
        print(f"ERROR: Execution script not found: {execution_script}")
        return 1

    if not scheduler_script.exists():
        print(f"ERROR: Scheduler script not found: {scheduler_script}")
        return 1

    print("=" * 60)
    print("OKXSTATBOT - STARTING")
    print("=" * 60)
    print(f"Execution: {execution_script.relative_to(base_dir)}")
    print(f"Scheduler: {scheduler_script.relative_to(base_dir)}")
    print("=" * 60)
    print("\nPress Ctrl+C to stop all processes\n")
    time.sleep(2)

    # Start Strategy Scheduler first (run initial scan)
    print("[1/2] Starting Strategy Scheduler...")
    scheduler_proc = subprocess.Popen(
        [sys.executable, str(scheduler_script)],
        cwd=str(base_dir)
    )
    processes.append(("Strategy Scheduler", scheduler_proc))
    print(f"Strategy Scheduler started (PID: {scheduler_proc.pid})")
    time.sleep(2)

    # Start Execution
    print("[2/2] Starting Execution...")
    execution_proc = subprocess.Popen(
        [sys.executable, str(execution_script)],
        cwd=str(base_dir / "Execution")
    )
    processes.append(("Execution", execution_proc))
    print(f"Execution started (PID: {execution_proc.pid})")

    print("\n" + "=" * 60)
    print("ALL PROCESSES RUNNING")
    print("=" * 60)
    print("Monitoring processes... (Ctrl+C to stop)")

    # Monitor processes
    try:
        while True:
            time.sleep(5)

            # Check if any process died
            for proc_name, proc in processes:
                if proc.poll() is not None:  # Process exited
                    exit_code = proc.returncode
                    print(f"\n⚠️  {proc_name} exited with code {exit_code}")

                    if exit_code != 0:
                        print(f"ERROR: {proc_name} crashed or exited with error")

                    # Stop all processes
                    signal_handler(None, None)

    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == "__main__":
    sys.exit(main())
