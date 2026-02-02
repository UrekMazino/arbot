# Strategy Scheduler - Hourly Cointegration Updates

## Overview

The Strategy Scheduler runs cointegration pair discovery every hour **without stopping** the Execution process. This keeps the cointegrated pairs fresh while maintaining active trades.

## Files Added

1. **`strategy_scheduler.py`** - Background scheduler that runs Strategy hourly
2. **`start_bot.py`** - Unified launcher for both Execution and Scheduler
3. **`SCHEDULER_README.md`** - This file

## Usage

### Option 1: Run Both Together (Recommended)

Start both Execution and Strategy Scheduler with one command:

```bash
python start_bot.py
```

This will:
- Start Strategy Scheduler first (runs initial scan)
- Start Execution process after 2 seconds
- Monitor both processes
- Stop both gracefully on Ctrl+C

### Option 2: Run Separately

Start Strategy Scheduler independently:

```bash
python strategy_scheduler.py
```

Then start Execution in another terminal:

```bash
cd Execution
python main_execution.py
```

## Configuration

### Strategy Interval

Control how often Strategy runs via environment variable:

```bash
# .env file
STATBOT_STRATEGY_INTERVAL=3600  # Seconds (default: 3600 = 1 hour)
```

**Minimum interval**: 300 seconds (5 minutes)

### Examples

```bash
# Every hour (default)
STATBOT_STRATEGY_INTERVAL=3600

# Every 30 minutes
STATBOT_STRATEGY_INTERVAL=1800

# Every 2 hours
STATBOT_STRATEGY_INTERVAL=7200
```

## Logs

Strategy Scheduler creates separate logs:

```
Logs/strategy_scheduler_YYYYMMDD_HHMMSS.log
```

Each Strategy run is logged with:
- Start/end timestamps
- Duration
- Output from Strategy main_strategy.py
- Success/failure counts

## How It Works

1. **Scheduler Loop**: Runs in background, executes Strategy every N seconds
2. **Subprocess Execution**: Spawns Strategy as subprocess (doesn't block Execution)
3. **State Persistence**: Strategy updates `2_cointegrated_pairs.csv` on disk
4. **Execution Reads**: Execution process reads fresh pairs when switching
5. **No Interruption**: Active trades continue unaffected

## Process Management

### Stop All Processes

Press `Ctrl+C` when using `start_bot.py` - gracefully stops both processes.

### Kill Specific Process

```bash
# Find PIDs
ps aux | grep python

# Kill scheduler only
kill <scheduler_pid>

# Kill execution only
kill <execution_pid>
```

### Check Status

```bash
# View scheduler logs
tail -f Logs/strategy_scheduler_*.log

# View execution logs
tail -f Logs/log_*.log
```

## Benefits

1. **Fresh Pairs**: Hourly updates ensure cointegration pairs stay current
2. **No Downtime**: Execution never stops, trades continue uninterrupted
3. **Adaptive**: Bot adapts to market regime changes automatically
4. **Monitoring**: Separate logs for easy debugging
5. **Graveyard Sync**: Excludes failed pairs from discovery automatically

## Graveyard Integration

The scheduler automatically:
- Loads graveyard from `Execution/state/pair_strategy_state.json`
- Excludes graveyard pairs from cointegration discovery
- Respects 7-day cooldowns
- Filters permanent blacklist (BIO, MUBARAK, ZETA, IMX, MAGIC)

## Troubleshooting

### Scheduler Not Starting

```bash
# Check if script exists
ls -la strategy_scheduler.py

# Run manually to see errors
python strategy_scheduler.py
```

### Strategy Failing

```bash
# Check Strategy logs
cat Logs/strategy_scheduler_*.log

# Run Strategy manually
cd Strategy
python main_strategy.py
```

### Execution Not Finding New Pairs

Verify Strategy output exists:
```bash
ls -la Strategy/output/2_cointegrated_pairs.csv
```

## Example Output

```
============================================================
STRATEGY SCHEDULER STARTED
============================================================
Interval: 3600s (1.00h)
Press Ctrl+C to stop
============================================================
2026-02-02 00:00:00 [INFO] Run #1 starting at 2026-02-02 00:00:00
============================================================
2026-02-02 00:00:05 [INFO] Starting Strategy cointegration scan...
============================================================
2026-02-02 00:02:30 [INFO] [Strategy] Strategy scan starting...
2026-02-02 00:02:31 [INFO] [Strategy] Symbols qualifying for trading: 147
2026-02-02 00:08:45 [INFO] [Strategy] Cointegration: pairs_kept=23 total_pairs=147
2026-02-02 00:08:46 [INFO] Strategy scan completed successfully in 141.2s
============================================================
2026-02-02 00:08:46 [INFO] Run #1 complete
2026-02-02 00:08:46 [INFO] Stats: Total=1 Success=1 Fail=0
2026-02-02 00:08:46 [INFO] Next run in 3600s (1.00h) at 2026-02-02 01:08:46
============================================================
```

## Environment Variables Summary

| Variable | Default | Description |
|----------|---------|-------------|
| `STATBOT_STRATEGY_INTERVAL` | 3600 | Seconds between Strategy runs |
| `STATBOT_STRATEGY_KLINE_LIMIT` | 10080 | Bars for cointegration (7 days @ 1m) |
| `STATBOT_LOCK_ON_PAIR` | False | Lock Execution to specific pair |

## Notes

- Scheduler uses same `.env` configuration as Strategy
- First run happens immediately on startup
- Subsequent runs every N seconds
- Timeout: 600 seconds (10 minutes) per Strategy run
- Graceful shutdown on Ctrl+C
