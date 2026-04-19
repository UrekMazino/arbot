# OKX Statistical Arbitrage Bot

Trading bot for OKX exchange implementing statistical arbitrage strategies.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure API credentials:
   - Copy `Execution/.env` and update with your OKX API credentials
   - Get API keys from: https://www.okx.com/account/my-api

3. API Permissions Required:
   - Read (for market data and account info)
   - Trade (for placing/canceling orders)

## Configuration

Edit `Execution/.env`:
```env
OKX_API_KEY=your_api_key_here
OKX_API_SECRET=your_api_secret_here
OKX_PASSPHRASE=your_passphrase_here
OKX_FLAG=1  # 1 = demo trading, 0 = live trading

# Optional execution defaults
STATBOT_DEFAULT_TICKER_1=ETH-USDT-SWAP
STATBOT_DEFAULT_TICKER_2=SOL-USDT-SWAP
STATBOT_INST_TYPE=SWAP
STATBOT_DEPTH=5
STATBOT_TD_MODE=cross
STATBOT_POS_MODE=long_short
STATBOT_DRY_RUN=0
STATBOT_LIMIT_ORDER_BASIS=1
STATBOT_USE_FRESH_ORDERBOOK=0
STATBOT_MAX_SNAPSHOT_AGE_SECONDS=15
STATBOT_STOP_LOSS_FAIL_SAFE=0.03
STATBOT_DEFAULT_LEVERAGE=1
STATBOT_MAX_CYCLES=0
STATBOT_Z_SCORE_WINDOW=21
STATBOT_TRADEABLE_CAPITAL_USDT=2000
STATBOT_ENTRY_Z=2.0
STATBOT_ENTRY_Z_MAX=3.0
STATBOT_EXIT_Z=0.35
STATBOT_MIN_PERSIST_BARS=4
STATBOT_MAX_CONSECUTIVE_LOSSES=2
STATBOT_HEALTH_CHECK_INTERVAL=3600
STATBOT_STATUS_UPDATE_INTERVAL=60
STATBOT_P_VALUE_CRITICAL=0.15
STATBOT_ZERO_CROSSINGS_MIN=15
STATBOT_CORRELATION_MIN=0.60
STATBOT_TREND_CRITICAL=0.002
STATBOT_Z_SCORE_CRITICAL=6.0
STATBOT_MAX_DRAWDOWN_PCT=0.05
STATBOT_OKX_SESSION_TIMEOUT_SECONDS=10
```

## Usage

Run the strategy:
```bash
cd Strategy
python main_strategy.py
```

Run the execution bot:
```bash
cd Execution
python main_execution.py
```

Pre-live fee/rebate check (prints fee tier and recent bills):
```bash
cd Execution
python pre_live_checklist.py --mode live --inst-type SWAP
```

Test getting symbols by maker fees:
```bash
cd Strategy
python func_get_symbols.py
```

## Strategy Liquidity Filter

The Strategy can bias pair selection toward more liquid legs using average quote volume from recent klines.
If a scan yields zero cointegrated pairs, it retries with progressively lower percentiles and restores the base value afterward.

Configure in `OKXStatBot/Strategy/.env`:
```env
STATBOT_STRATEGY_LIQUIDITY_WINDOW=60
STATBOT_STRATEGY_LIQUIDITY_PCT=0.3
```

Fallback behavior:
- If no pairs are found at 0.30, Strategy retries at 0.25, 0.20, 0.15, 0.10, then 0.00, and restores the base value after success.

## Strategy Performance Tuning

Enable the fast path for large universes (keeps accuracy by using full-length cointegration after a light prefilter):

```env
STATBOT_STRATEGY_FAST_PATH=1
STATBOT_STRATEGY_CORR_MIN=0.1        # correlation prefilter on log returns (set 0 to disable)
STATBOT_STRATEGY_CORR_LOOKBACK=0     # 0 = full length, or set a bar count for faster prefilter
```

Enable incremental kline caching to avoid refetching all 1440 candles every run:

```env
STATBOT_STRATEGY_CACHE_KLINES=1
STATBOT_STRATEGY_CACHE_MAX_GAP_BARS=120
STATBOT_STRATEGY_CACHE_REFRESH_BARS=100
STATBOT_STRATEGY_CACHE_SLEEP=0.05
```

## Strategy Outputs

Strategy outputs are stored under `OKXStatBot/Strategy/output`:
- `1_price_list.json`
- `2_cointegrated_pairs.csv`
- `3_backtest_file.csv`
- `4_summary_report.csv` (overwritten each run)

## Documentation

For a detailed explanation of the bot's architecture, trading logic, risk management, and computations, please see:
- **[BOT_DOCUMENTATION.md](BOT_DOCUMENTATION.md)**: Comprehensive guide to the Execution system.
- **[KILL_SWITCH_STATE_MACHINE.md](KILL_SWITCH_STATE_MACHINE.md)**: Detailed state machine transitions.
- **[V2_ROADMAP.md](V2_ROADMAP.md)**: V2 UI roadmap plus queued pending engine phases.
- **[V2_UI_PLATFORM_SPEC.md](V2_UI_PLATFORM_SPEC.md)**: V2 web architecture, DB schema, API, auth, and rollout plan.
- **[Platform/README.md](Platform/README.md)**: V2 backend/worker scaffold and local startup guide.
- **[CHANGELOG.md](CHANGELOG.md)**: Release notes.
- **[VERSION](VERSION)**: Current version tag.

## Release Status (v1.0)

StatBot v1.0 is considered stable after a staged rollout:
- 24-72 hours demo soak, then 5-10 trading days small live.

### V1 Checklist
- Phase 0 (Smoke, 15-30 min): startup logs OK, availEq/availBal snapshot printed, no API errors.
- Phase 1 (Entry/Exit, 2-6h): at least one full entry/exit, contract value log present, no 51008 margin errors.
- Phase 2 (Soak, 24-72h demo): >=2 funding windows, one restart, one health check, log rotation OK, no crashes.
- Phase 3 (Limited live, 5-10d): small cap, PNL alerts appear, equity drift reasonable, no repeated order failures.

## Logging & Alerts

### Logs
- Per-run logs live in `OKXStatBot/Logs/v1/run_XX_YYYYMMDD_HHMMSS/log_YYYYMMDD_HHMMSS.log`
- Control size/retention in `Execution/.env`:
```env
STATBOT_LOG_MAX_MB=4
STATBOT_LOG_BACKUPS=2
STATBOT_LOG_LEVEL=INFO
```

At `OKXStatBot/Logs/v1`, an index is maintained:
- `index.json` (all runs + key log metadata)
- `index.csv` (CSV version of the same index)

### Execution State Files
Runtime state is stored under `OKXStatBot/Execution/state`:
- `active_pair.json`
- `status.json`
- `pair_strategy_state.json`
- `strategy_state.json` (strategy router + rolling strategy performance state)
- `regime_state.json` (Regime Router state, when enabled)

### Reports (v1 evidence packs)
After each run, StatBot can generate a report pack under `OKXStatBot/Reports/v1/run_XX_YYYYMMDD_HHMMSS`:
- `summary.json` (run metadata + performance summary)
- `summary.txt` (executive summary + files list)
- `equity_curve.csv` (equity/session/PNL timeline)
- `trades.csv` (trade closes with PnL and hold time)
- `strategy_regime_scorecard.csv` (trade outcomes grouped by entry strategy + entry regime)
- `strategy_performance.csv` (strategy-level PnL, win rate, hold, common exit reason)
- `strategy_switches.csv` (strategy-router change timeline from logs)
- `strategy_gates.csv` (strategy gate events: coint/mean-shift/policy and future cooldown/filter events)
- `data_quality_checks.csv` (structured pass/warn/fail checks for run quality)
- `reconciliation_checks.csv` (post-close equity reconciliation rows and warning flags)
- `liquidity_checks.csv` (per-entry liquidity snapshot with ratios + high/low classification)
- `entry_slippage.csv` (entry fill slippage vs preview price, bps)
- `alerts.txt` (errors, PNL alerts, critical events)
- `config_snapshot.json` (redacted .env snapshot)
- `report_manifest.json` (machine-readable file inventory, schema version, row counts)

At `OKXStatBot/Reports/v1`, an index is maintained for quick review:
- `index.json` (all runs + key metrics)
- `index.csv` (same, CSV-friendly)
  - Includes strategy/regime attribution, reconciliation warning counts, and data-quality counters for cross-run screening.

Manual/analysis runs:
- If you run `report_generator.py --output` with a name starting with `manual` or `analysis`, it will be saved under `run_XX_.../variants/<name>` to keep run numbers aligned.

Enable/disable:
```env
STATBOT_REPORT_ENABLE=1
```
Optional uptime trigger:
```env
STATBOT_REPORT_UPTIME_HOURS=24
```

Run end tracking:
- Logs emit `RUN_END: reason=... detail=... exit_code=...`
- Reports capture `run_end_reason`, `run_end_detail`, `run_end_time`
- Reasons: `manual_stop`, `error`, `max_uptime`, `max_cycles`, `circuit_breaker`

Max uptime (optional):
```env
STATBOT_MAX_UPTIME_HOURS=24
```

### Liquidity guard (optional)
Skip entries when available liquidity is too thin for the target size (liquidity/target):
```env
STATBOT_MIN_LIQUIDITY_RATIO=3.0
# Legacy name (same meaning):
# STATBOT_LIQUIDITY_MIN_RATIO=3.0
```
Behavior:
- If a leg fails the ratio, the bot attempts to downsize per-leg capital to meet the minimum.
- If the ratio still fails, the bot progressively relaxes the min ratio (default steps: 3.0 -> 2.5 -> 2.0 -> 1.5 -> 1.0).
- If the adjusted target drops below the exchange min order size, the entry is skipped.

### Regime Router (V1 Phase 2)
Phase 2 applies **entry gating + policy overrides** in `active` mode:
- `shadow`: evaluation/logging only.
- `active`: skips new entries when `allow_new_entries=0` and applies policy overrides for new entries:
  `entry_z`, `entry_z_max`, `min_persist_bars`, `min_liquidity_ratio` floor, and `size_multiplier`.
- Existing monitoring/exit/kill-switch behavior is unchanged.

Enable shadow mode:
```env
STATBOT_REGIME_ROUTER_MODE=shadow
```

Optional tuning:
```env
STATBOT_REGIME_MARKET_SYMBOL=BTC-USDT-SWAP
STATBOT_REGIME_EVAL_SECONDS=60
STATBOT_REGIME_MIN_HOLD_SECONDS=1200
STATBOT_REGIME_CONFIRM_COUNT=2
STATBOT_REGIME_TREND_THRESHOLD=1.2
STATBOT_REGIME_VOL_SHOCK_PCT=0.95
STATBOT_REGIME_VOL_EXPANSION=0.5
STATBOT_REGIME_THIN_DEPTH_RATIO=1.2
STATBOT_REGIME_RISKOFF_DRAWDOWN_PCT=1.5
```

Expected logs:
- `REGIME_STATUS`
- `REGIME_CHANGE`
- `REGIME_POLICY`
- `REGIME_GATE` (policy signal in shadow/active)
- `REGIME_GATE_ENFORCED` (only when active mode blocks new entries)
- `Regime size multiplier applied` (when active policy changes per-leg size)

Smoke test:
```bash
python -m pytest -q Execution/tests/test_regime_router.py
```

## Features

### Step 1: Get Tradeable Symbols by Maker Fees
- Fetches all available instruments (SWAP/Perpetual contracts)
- Retrieves trading fees for each instrument
- Filters symbols by maker fee threshold
- Identifies symbols with negative maker fees (rebates)
- Uses parallel processing with rate limiting

## API Documentation

- OKX API v5: https://www.okx.com/docs-v5/en/
- Public Data: https://www.okx.com/docs-v5/en/#public-data-rest-api
- Trading Account: https://www.okx.com/docs-v5/en/#trading-account-rest-api
- Order Book Trading: https://www.okx.com/docs-v5/en/#order-book-trading-trade

## Instrument Types

- `SWAP`: Perpetual swaps (no expiry)
- `FUTURES`: Futures contracts (with expiry)
- `SPOT`: Spot trading pairs
- `OPTION`: Options contracts

## Safety Features

- Rate limiting (5 req/sec default)
- Demo trading mode (OKX_FLAG=1)
- Error handling and retries
- Progress tracking
