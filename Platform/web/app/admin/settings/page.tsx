"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  AdminEnvSettings,
  UserRecord,
  getAdminEnvSettings,
  getMe,
  isUnauthorizedError,
  updateAdminEnvSetting,
} from "../../../lib/api";
import {
  canAccessAdminPath,
  getAdminNavItems,
  getFirstAccessibleAdminPath,
  hasPermission,
} from "../../../lib/admin-access";
import { clearStoredAdminSession, getStoredAdminEmail } from "../../../lib/auth";
import { UI_CLASSES } from "../../../lib/ui-classes";
import { DashboardShell } from "../../../components/dashboard-shell";

type TabType = "bot" | "api";
type SettingTooltip = { description: string; default: string };
type SettingOption = { label: string; value: string };
type SettingGroupDefinition = {
  id: string;
  title: string;
  description: string;
  keys?: string[];
  prefixes?: string[];
};
type ResolvedSettingGroup = SettingGroupDefinition & { settingKeys: string[] };

// Tooltip configuration for settings with descriptions and default values
const SETTING_TOOLTIPS: Record<string, SettingTooltip> = {
  // Execution settings
  DEFAULT_TICKER_1: { description: "Fallback first ticker when no active pair is stored", default: "ETH-USDT-SWAP" },
  DEFAULT_TICKER_2: { description: "Fallback second ticker when no active pair is stored", default: "SOL-USDT-SWAP" },
  LOCK_PAIR: { description: "Explicit locked pair payload used when lock-on-pair is enabled", default: "(empty)" },
  EXECUTION_SETTLE_CCY: { description: "Allowed settle currencies for execution pair validation", default: "USDT" },
  INST_TYPE: { description: "OKX instrument type used by execution", default: "SWAP" },
  EXECUTION_TIMEFRAME: { description: "Execution candle timeframe used for live Z-score and cointegration checks", default: "1m" },
  EXECUTION_KLINE_LIMIT: { description: "Execution candle sample size used for live cointegration and Z-score calculations", default: "200" },
  DEPTH: { description: "Orderbook depth request size; 5 uses books5, other values use books", default: "5" },
  TD_MODE: { description: "Trade mode for order placement: cross or isolated", default: "cross" },
  POS_MODE: { description: "Position mode for execution: net or long_short", default: "long_short" },
  DRY_RUN: { description: "When enabled, execution simulates orders without placing them", default: "0" },
  LIMIT_ORDER_BASIS: { description: "Place entry orders as limits instead of market orders", default: "1" },
  USE_FRESH_ORDERBOOK: { description: "Reserved toggle for forcing a fresh orderbook snapshot before entry", default: "0" },
  MAX_SNAPSHOT_AGE_SECONDS: { description: "Maximum allowed age for a reusable orderbook snapshot", default: "15" },
  STOP_LOSS_FAIL_SAFE: { description: "Fail-safe stop loss percentage as a decimal", default: "0.03" },
  DEFAULT_LEVERAGE: { description: "Default leverage applied to each leg at startup", default: "1" },
  MAX_CYCLES: { description: "Maximum execution cycles before stop; 0 runs indefinitely", default: "0" },
  SKIP_INSTRUMENT_FETCH: { description: "Skip OKX instrument metadata fetch at startup", default: "0" },
  OKX_SESSION_TIMEOUT_SECONDS: { description: "Network timeout for OKX SDK requests in seconds", default: "10" },
  TRADEABLE_CAPITAL_USDT: { description: "Capital budget used by execution sizing and circuit breakers", default: "2000" },
  Z_SCORE_WINDOW: { description: "Default rolling window used for Z-score calculations", default: "21" },
  ENTRY_Z: { description: "Base Z-score threshold required to open a position", default: "2.0" },
  ENTRY_Z_MAX: { description: "Maximum Z-score allowed for a new entry to avoid regime breaks", default: "3.0" },
  EXIT_Z: { description: "Base Z-score threshold used for mean reversion exits", default: "0.35" },
  MIN_PERSIST_BARS: { description: "Lookback checks used for adaptive entry persistence", default: "4" },
  ENTRY_MIN_QUALIFIED_BARS: { description: "Minimum in-band checks inside the persistence lookback; 0 uses MIN_PERSIST_BARS - 1", default: "0" },
  ENTRY_Z_TOLERANCE: { description: "Small Z-score threshold tolerance for near misses such as 1.98 vs 2.00", default: "0.05" },
  ENTRY_EXTREME_CLEAN_BARS: { description: "Recent clean in-band checks required after returning from ENTRY_Z_MAX breach", default: "2" },
  MAX_CONSECUTIVE_LOSSES: { description: "Consecutive losses on the same pair before pair retirement logic escalates", default: "2" },
  COINT_GATE_THRESHOLD: { description: "Consecutive broken cointegration-gate failures required before execution triggers a pair switch", default: "2" },
  COINT_WATCH_GATE_THRESHOLD: { description: "Consecutive near-cointegrated watch-band failures allowed before execution switches pair", default: "6" },
  HEALTH_CHECK_INTERVAL: { description: "Seconds between pair health evaluations while running", default: "3600" },
  STATUS_UPDATE_INTERVAL: { description: "Seconds between execution status updates", default: "60" },
  P_VALUE_CRITICAL: { description: "Base p-value threshold used to judge cointegration health", default: "0.15" },
  COINT_WATCH_P_VALUE: { description: "Soft p-value band where entries pause but pair switching is delayed", default: "0.25" },
  COINT_FAIL_P_VALUE: { description: "P-value level treated as broken unless ADF remains inside the watch margin", default: "0.35" },
  COINT_ADF_MARGIN_PCT: { description: "ADF margin as a fraction of critical value for near-cointegrated watch status", default: "0.10" },
  ZERO_CROSSINGS_MIN: { description: "Minimum zero crossings expected for a healthy pair", default: "15" },
  COINT_ZERO_CROSS_THRESHOLD_RATIO: { description: "Noise filter ratio used when counting spread zero crossings for shared cointegration validation", default: "0.1" },
  CORRELATION_MIN: { description: "Minimum correlation threshold for pair health", default: "0.60" },
  TREND_CRITICAL: { description: "Maximum allowed spread trend magnitude before health degradation", default: "0.002" },
  Z_SCORE_CRITICAL: { description: "Maximum absolute Z-score tolerated before health degradation", default: "6.0" },
  SWITCH_PRECHECK_COINT: { description: "Enable cointegration validation before switching into a discovered pair", default: "1" },
  SWITCH_PRECHECK_FAIL_OPEN: { description: "Allow pair switching to proceed when the pre-check validator errors instead of failing closed", default: "0" },
  SWITCH_PRECHECK_LIMIT: { description: "Candle count used for switch pre-check cointegration validation", default: "120" },
  SWITCH_PRECHECK_WINDOW: { description: "Z-score window used during switch pre-check validation", default: "60" },
  POST_SWITCH_ENTRY_WARMUP_SECONDS: { description: "Seconds to wait before allowing fresh entries after a successful pair switch", default: "60" },
  MAX_DRAWDOWN_PCT: { description: "Circuit breaker loss threshold as a decimal of capital", default: "0.05" },
  HEALTH_PROFIT_PROTECTION_MIN_PNL_PCT: { description: "Minimum in-trade PnL percentage that activates profitable-trade health protection", default: "0.10" },
  HEALTH_BREAKEVEN_PROTECTION_MIN_PNL_PCT: { description: "Minimum in-trade PnL percentage treated as near-breakeven for softer health thresholds", default: "-0.10" },
  HEALTH_PROFIT_PROTECTED_PVALUE_THRESHOLD: { description: "Relaxed p-value threshold used while a trade is already profit-protected", default: "0.30" },
  HEALTH_BREAKEVEN_PVALUE_THRESHOLD: { description: "Relaxed p-value threshold used while a trade is near breakeven", default: "0.20" },
  LOCK_ON_PAIR: { description: "Lock to current pair until trade completes", default: "False" },
  TIMEZONE: { description: "IANA timezone name used for raw log timestamps and run-key timestamp generation", default: "system local timezone" },
  LOG_MAX_MB: { description: "Maximum log file size in MB before rotation", default: "4" },
  LOG_BACKUPS: { description: "Number of backup log files to keep", default: "2" },
  MIN_LIQUIDITY_RATIO: { description: "Minimum liquidity ratio required for trading", default: "5.0" },
  LIQUIDITY_FALLBACK_TIER1: { description: "Liquidity fallback tier 1 threshold", default: "4.0" },
  LIQUIDITY_FALLBACK_TIER2: { description: "Liquidity fallback tier 2 threshold", default: "3.0" },
  LIQUIDITY_FALLBACK_MIN: { description: "Minimum liquidity fallback value", default: "2.5" },
  PAIR_IDLE_TIMEOUT_MIN: { description: "Maximum minutes to wait for pair signal before timeout", default: "120" },
  BLACKLIST_ENABLED: { description: "Enable automatic pair blacklisting", default: "1" },
  BLACKLIST_MIN_TRADES: { description: "Minimum trades before pair can be blacklisted", default: "10" },
  BLACKLIST_MAX_LOSS_RATE: { description: "Maximum loss rate before blacklisting (0-1)", default: "0.75" },
  BLACKLIST_REQUIRE_LOSS_DOMINANCE: { description: "Require loss dominance for blacklisting", default: "1" },
  PAIR_HISTORY_BREAKEVEN_EPSILON_USDT: { description: "Absolute PnL in USDT treated as neutral pair history instead of win/loss", default: "0.01" },
  HOSPITAL_COOLDOWN_SECONDS: { description: "Cooldown time in seconds for pairs in hospital", default: "3600" },
  STRATEGY_REFRESH_SLEEP_SECONDS: { description: "Sleep seconds between retry attempts when execution refreshes Strategy for replacement pairs", default: "5" },
  PAIR_SUPPLY_WAIT_SECONDS: { description: "Sleep seconds between execution checks while waiting for active continuous pair supply", default: "5" },
  // Strategy settings (exposed ones)
  STRATEGY_TIMEFRAME: { description: "Strategy candle timeframe used for discovery scans", default: "1m" },
  STRATEGY_Z_SCORE_WINDOW: { description: "Rolling window used for Strategy-side Z-score analytics", default: "60" },
  STRATEGY_KLINE_LIMIT: { description: "Historical candle count fetched per symbol for strategy discovery", default: "2880" },
  STRATEGY_INTERNAL_KLINE_WORKERS: { description: "Parallel worker count for Strategy kline fetches; lower values reduce CPU and request bursts", default: "2" },
  STRATEGY_INTERNAL_MIN_PAIRS: { description: "Minimum usable pairs Strategy tries to find before accepting a fallback scan result", default: "3" },
  STRATEGY_STARTUP_RETRY_SECONDS: { description: "Sleep seconds between startup Strategy discovery retries when no pairs are found", default: "5" },
  STRATEGY_STARTUP_MAX_ATTEMPTS: { description: "Maximum startup Strategy discovery attempts before execution gives up; 0 retries forever", default: "0" },
  PAIR_SUPPLY_INTERVAL_SECONDS: { description: "Seconds between independent continuous Strategy pair-supply scans; 0 starts the next scan immediately", default: "300" },
  PAIR_SUPPLY_RUN_IMMEDIATELY: { description: "Run the independent pair-supply scanner immediately on start instead of waiting one interval", default: "1" },
  STRATEGY_SETTLE_CCY: { description: "Comma-separated settle currencies Strategy is allowed to scan", default: "USDT" },
  STRATEGY_MIN_EQUITY: { description: "Maximum recommended pair equity allowed during strategy discovery (0 disables)", default: "0" },
  STRATEGY_ROUTER_MODE: { description: "Strategy router mode: off, shadow, or active", default: "off" },
  STRATEGY_FAST_PATH: { description: "Enable return-correlation prefilter before full cointegration scan", default: "1" },
  STRATEGY_LIQUIDITY_PCT: { description: "Minimum liquidity percentage filter", default: "0" },
  STRATEGY_LIQUIDITY_WINDOW: { description: "Lookback bars used when estimating average quote volume", default: "60" },
  STRATEGY_MIN_AVG_QUOTE_VOL: { description: "Minimum average quote volume per leg in USDT", default: "0" },
  STRATEGY_CORR_MIN: { description: "Minimum correlation coefficient (0-1)", default: "0.2" },
  STRATEGY_CORR_LOOKBACK: { description: "Optional return-correlation lookback bars for the Strategy fast path", default: "1440" },
  STRATEGY_MIN_CAPITAL_PER_LEG: { description: "Minimum capital per leg in USDT (0=any)", default: "0" },
  STRATEGY_MIN_P_VALUE: { description: "Minimum p-value for cointegration (scientific notation)", default: "1e-08" },
  STRATEGY_MAX_P_VALUE: { description: "Maximum p-value for cointegration", default: "0.01" },
  STRATEGY_MIN_ZERO_CROSSINGS: { description: "Minimum zero crossings for valid pair", default: "3" },
  STRATEGY_MIN_HEDGE_RATIO: { description: "Minimum absolute hedge ratio allowed for a discovered pair", default: "0.3" },
  STRATEGY_MAX_HEDGE_RATIO: { description: "Maximum absolute hedge ratio allowed for a discovered pair", default: "3.0" },
  PAIR_SUPPLY_MAX_PAIRS: { description: "Maximum total cointegrated pairs published by continuous pair supply", default: "10" },
  STRATEGY_MAX_PAIRS_PER_TICKER: { description: "Maximum cointegrated pairs per ticker", default: "10" },
  STRATEGY_MIN_ORDERBOOK_DEPTH: { description: "Minimum orderbook depth in USDT", default: "5000" },
  STRATEGY_SOFT_ORDERBOOK_DEPTH: { description: "Lower depth floor for soft-pass liquidity when imbalance is acceptable", default: "75% of hard depth" },
  STRATEGY_MAX_ORDERBOOK_IMBALANCE: { description: "Maximum strong-side to weak-side orderbook depth ratio for soft-pass liquidity; 0 disables imbalance cap", default: "12" },
  STRATEGY_MIN_ORDERBOOK_LEVELS: { description: "Minimum orderbook levels required", default: "7" },
  STRATEGY_MIN_ORDER_CAPACITY: { description: "Minimum OKX max market/stop order capacity per leg in USDT; filters symbols whose exchange max order size is too small", default: "50" },
  STRATEGY_EVAL_SECONDS: { description: "Seconds between strategy evaluation", default: "30" },
  REGIME_ROUTER_MODE: { description: "Regime detection router mode: off, shadow, or active", default: "off" },
  REGIME_EVAL_SECONDS: { description: "Seconds between regime evaluation", default: "30" },
  STRATEGY_SCORE_WINDOW_TRADES: { description: "Number of trades for rolling score window", default: "20" },
  STRATEGY_SCORE_MIN_TRADES: { description: "Minimum trades required for scoring", default: "8" },
  STRATEGY_SCORE_MIN_WIN_RATE: { description: "Minimum win rate for scoring (0-1)", default: "0.35" },
  STRATEGY_SCORE_MAX_ROLLING_LOSS_USDT: { description: "Maximum rolling loss in USDT", default: "20" },
  STRATEGY_COOLDOWN_SECONDS: { description: "Cooldown seconds between strategy switches or entries", default: "3600" },
  RANGE_Z_LOOKBACK: { description: "Lookback bars for range Z-score calculation", default: "200" },
  TREND_Z_LOOKBACK: { description: "Lookback bars for trend Z-score calculation", default: "60" },
  STRATEGY_TREND_ENTRY_Z: { description: "Entry Z-score required when the strategy router selects TREND_SPREAD", default: "2.8" },
  STRATEGY_TREND_MIN_PERSIST: { description: "Persistence bars required when the strategy router selects TREND_SPREAD", default: "4" },
  STRATEGY_TREND_DIRECTIONAL_FILTER_MODE: { description: "Trend directional filter mode: off, shadow, or active", default: "off" },
  STRATEGY_TREND_DIRECTIONAL_FILTER_STRENGTH: { description: "Trend directional filter strength", default: "1.0" },
  ATM_MR_MAX_HOLD_HOURS: { description: "Max hold hours for mean reversion mode", default: "6" },
  ATM_MR_MAX_HOLD_WARNING_HOURS: { description: "Warning threshold for MR hold hours", default: "4" },
  ATM_TREND_MAX_HOLD_HOURS: { description: "Max hold hours for trend mode", default: "2" },
  ATM_TREND_MAX_HOLD_WARNING_HOURS: { description: "Warning threshold for trend hold hours", default: "1.5" },
  ATM_TREND_TRAILING_ACTIVATION: { description: "Trailing activation threshold", default: "1.0" },
  ATM_TREND_TRAILING_TIGHT_DISTANCE: { description: "Tight trailing distance", default: "0.25" },
  ATM_TREND_TRAILING_MID_DISTANCE: { description: "Mid trailing distance", default: "0.35" },
  ATM_TREND_TRAILING_LOOSE_DISTANCE: { description: "Loose trailing distance", default: "0.45" },
  REPORT_ENABLE: { description: "Enable live report refresh hooks", default: "1" },
  REPORT_UPTIME_HOURS: { description: "Refresh report after this uptime in hours", default: "24" },
  MAX_UPTIME_HOURS: { description: "Max uptime hours before restart", default: "24" },
  ORDERBOOK_BACKOFF_SECONDS: { description: "Backoff seconds when orderbook fails", default: "45" },
  ORDERBOOK_BACKOFF_RETRIES: { description: "Number of orderbook backoff retries", default: "2" },
  ORDERBOOK_BACKOFF_RETRY_SLEEP: { description: "Sleep seconds between backoff retries", default: "0.25" },
  MOLT_MONITOR: { description: "Enable molt monitor (1=yes, 0=no)", default: "0" },
  COMMAND_LISTENER: { description: "Enable command listener (1=yes, 0=no)", default: "0" },
  BALANCE_FETCH_TIMEOUT_SECONDS: { description: "Timeout for balance fetch in seconds", default: "8" },
  HARD_STOP_PNL_BASIS: { description: "Hard stop PnL basis: notional or equity", default: "notional" },
  ENABLE_RISKOFF_COINT_EARLY_EXIT: { description: "Enable risk-off early exit on cointegration", default: "1" },
  RISKOFF_COINT_CONFIRM_COUNT: { description: "Confirmations required for risk-off exit", default: "3" },
  RISKOFF_COINT_GRACE_SECONDS: { description: "Grace seconds for risk-off cointegration exit", default: "90" },
  RISKOFF_COINT_MIN_LOSS_PCT: { description: "Minimum loss percentage for risk-off exit (0-1)", default: "0.25" },
};

const BOT_SETTING_GROUPS: SettingGroupDefinition[] = [
  {
    id: "execution-runtime",
    title: "Execution Runtime",
    description: "Core pair defaults, order placement mode, and exchange runtime controls.",
    keys: [
      "STATBOT_DEFAULT_TICKER_1",
      "STATBOT_DEFAULT_TICKER_2",
      "STATBOT_LOCK_ON_PAIR",
      "STATBOT_LOCK_PAIR",
      "STATBOT_EXECUTION_SETTLE_CCY",
      "STATBOT_INST_TYPE",
      "STATBOT_EXECUTION_TIMEFRAME",
      "STATBOT_EXECUTION_KLINE_LIMIT",
      "STATBOT_DEPTH",
      "STATBOT_TD_MODE",
      "STATBOT_POS_MODE",
      "STATBOT_DRY_RUN",
      "STATBOT_LIMIT_ORDER_BASIS",
      "STATBOT_USE_FRESH_ORDERBOOK",
      "STATBOT_MAX_SNAPSHOT_AGE_SECONDS",
      "STATBOT_DEFAULT_LEVERAGE",
      "STATBOT_MAX_CYCLES",
      "STATBOT_SKIP_INSTRUMENT_FETCH",
      "STATBOT_OKX_SESSION_TIMEOUT_SECONDS",
    ],
  },
  {
    id: "capital-risk",
    title: "Capital & Risk",
    description: "Sizing, leverage, stop-loss, and session or pair loss controls.",
    keys: [
      "STATBOT_TRADEABLE_CAPITAL_USDT",
      "STATBOT_STOP_LOSS_FAIL_SAFE",
      "STATBOT_MAX_DRAWDOWN_PCT",
      "STATBOT_HEALTH_PROFIT_PROTECTION_MIN_PNL_PCT",
      "STATBOT_HEALTH_BREAKEVEN_PROTECTION_MIN_PNL_PCT",
      "STATBOT_HEALTH_PROFIT_PROTECTED_PVALUE_THRESHOLD",
      "STATBOT_HEALTH_BREAKEVEN_PVALUE_THRESHOLD",
      "STATBOT_HARD_STOP_PNL_BASIS",
      "STATBOT_ENABLE_RISKOFF_COINT_EARLY_EXIT",
      "STATBOT_RISKOFF_COINT_CONFIRM_COUNT",
      "STATBOT_RISKOFF_COINT_GRACE_SECONDS",
      "STATBOT_RISKOFF_COINT_MIN_LOSS_PCT",
    ],
  },
  {
    id: "signals-thresholds",
    title: "Signal Thresholds",
    description: "Entry, exit, Z-score, and pair-quality thresholds used during execution.",
    keys: [
      "STATBOT_Z_SCORE_WINDOW",
      "STATBOT_ENTRY_Z",
      "STATBOT_ENTRY_Z_MAX",
      "STATBOT_EXIT_Z",
      "STATBOT_MIN_PERSIST_BARS",
      "STATBOT_ENTRY_MIN_QUALIFIED_BARS",
      "STATBOT_ENTRY_Z_TOLERANCE",
      "STATBOT_ENTRY_EXTREME_CLEAN_BARS",
      "STATBOT_P_VALUE_CRITICAL",
      "STATBOT_COINT_WATCH_P_VALUE",
      "STATBOT_COINT_FAIL_P_VALUE",
      "STATBOT_COINT_ADF_MARGIN_PCT",
      "STATBOT_ZERO_CROSSINGS_MIN",
      "STATBOT_COINT_ZERO_CROSS_THRESHOLD_RATIO",
      "STATBOT_CORRELATION_MIN",
      "STATBOT_TREND_CRITICAL",
      "STATBOT_Z_SCORE_CRITICAL",
    ],
  },
  {
    id: "pair-lifecycle",
    title: "Pair Lifecycle",
    description: "Switching, hospital, blacklist, and ongoing pair-health behavior.",
    keys: [
      "STATBOT_PAIR_IDLE_TIMEOUT_MIN",
      "STATBOT_MAX_SWITCHES",
      "STATBOT_SWITCH_COOLDOWN_SECONDS",
      "STATBOT_HOSPITAL_COOLDOWN_SECONDS",
      "STATBOT_STRATEGY_REFRESH_SLEEP_SECONDS",
      "STATBOT_PAIR_SUPPLY_WAIT_SECONDS",
      "STATBOT_MAX_CONSECUTIVE_LOSSES",
      "STATBOT_COINT_GATE_THRESHOLD",
      "STATBOT_COINT_WATCH_GATE_THRESHOLD",
      "STATBOT_SWITCH_PRECHECK_COINT",
      "STATBOT_SWITCH_PRECHECK_FAIL_OPEN",
      "STATBOT_SWITCH_PRECHECK_LIMIT",
      "STATBOT_SWITCH_PRECHECK_WINDOW",
      "STATBOT_POST_SWITCH_ENTRY_WARMUP_SECONDS",
      "STATBOT_HEALTH_CHECK_INTERVAL",
      "STATBOT_STATUS_UPDATE_INTERVAL",
      "STATBOT_BLACKLIST_ENABLED",
      "STATBOT_BLACKLIST_MIN_TRADES",
      "STATBOT_BLACKLIST_MAX_LOSS_RATE",
      "STATBOT_BLACKLIST_REQUIRE_LOSS_DOMINANCE",
      "STATBOT_PAIR_HISTORY_BREAKEVEN_EPSILON_USDT",
    ],
  },
  {
    id: "liquidity-ops",
    title: "Liquidity & Operations",
    description: "Liquidity filters, logging, report cadence, and operational retry controls.",
    keys: [
      "STATBOT_MIN_LIQUIDITY_RATIO",
      "STATBOT_LIQUIDITY_FALLBACK_TIER1",
      "STATBOT_LIQUIDITY_FALLBACK_TIER2",
      "STATBOT_LIQUIDITY_FALLBACK_MIN",
      "STATBOT_ORDERBOOK_BACKOFF_SECONDS",
      "STATBOT_ORDERBOOK_BACKOFF_RETRIES",
      "STATBOT_ORDERBOOK_BACKOFF_RETRY_SLEEP",
      "STATBOT_BALANCE_FETCH_TIMEOUT_SECONDS",
      "STATBOT_TIMEZONE",
      "STATBOT_LOG_MAX_MB",
      "STATBOT_LOG_BACKUPS",
      "STATBOT_MOLT_MONITOR",
      "STATBOT_COMMAND_LISTENER",
      "STATBOT_REPORT_ENABLE",
      "STATBOT_REPORT_UPTIME_HOURS",
      "STATBOT_MAX_UPTIME_HOURS",
    ],
  },
  {
    id: "strategy-discovery",
    title: "Strategy Discovery",
    description: "Pair discovery filters used by the strategy scanner.",
    keys: [
      "STATBOT_STRATEGY_TIMEFRAME",
      "STATBOT_STRATEGY_Z_SCORE_WINDOW",
      "STATBOT_STRATEGY_KLINE_LIMIT",
      "STATBOT_STRATEGY_INTERNAL_KLINE_WORKERS",
      "STATBOT_STRATEGY_INTERNAL_MIN_PAIRS",
      "STATBOT_STRATEGY_STARTUP_RETRY_SECONDS",
      "STATBOT_STRATEGY_STARTUP_MAX_ATTEMPTS",
      "STATBOT_PAIR_SUPPLY_INTERVAL_SECONDS",
      "STATBOT_PAIR_SUPPLY_RUN_IMMEDIATELY",
      "STATBOT_STRATEGY_SETTLE_CCY",
      "STATBOT_STRATEGY_MIN_EQUITY",
      "STATBOT_STRATEGY_FAST_PATH",
      "STATBOT_STRATEGY_LIQUIDITY_PCT",
      "STATBOT_STRATEGY_LIQUIDITY_WINDOW",
      "STATBOT_STRATEGY_MIN_AVG_QUOTE_VOL",
      "STATBOT_STRATEGY_CORR_MIN",
      "STATBOT_STRATEGY_CORR_LOOKBACK",
      "STATBOT_STRATEGY_MIN_CAPITAL_PER_LEG",
      "STATBOT_STRATEGY_MIN_P_VALUE",
      "STATBOT_STRATEGY_MAX_P_VALUE",
      "STATBOT_STRATEGY_MIN_ZERO_CROSSINGS",
      "STATBOT_STRATEGY_MIN_HEDGE_RATIO",
      "STATBOT_STRATEGY_MAX_HEDGE_RATIO",
      "STATBOT_PAIR_SUPPLY_MAX_PAIRS",
      "STATBOT_STRATEGY_MAX_PAIRS_PER_TICKER",
      "STATBOT_STRATEGY_MIN_ORDERBOOK_DEPTH",
      "STATBOT_STRATEGY_SOFT_ORDERBOOK_DEPTH",
      "STATBOT_STRATEGY_MAX_ORDERBOOK_IMBALANCE",
      "STATBOT_STRATEGY_MIN_ORDERBOOK_LEVELS",
      "STATBOT_STRATEGY_MIN_ORDER_CAPACITY",
    ],
  },
  {
    id: "strategy-router",
    title: "Strategy Router & Score",
    description: "Strategy cadence, scoring thresholds, and directional filter controls.",
    keys: [
      "STATBOT_STRATEGY_ROUTER_MODE",
      "STATBOT_STRATEGY_EVAL_SECONDS",
      "STATBOT_STRATEGY_SCORE_WINDOW_TRADES",
      "STATBOT_STRATEGY_SCORE_MIN_TRADES",
      "STATBOT_STRATEGY_SCORE_MIN_WIN_RATE",
      "STATBOT_STRATEGY_SCORE_MAX_ROLLING_LOSS_USDT",
      "STATBOT_STRATEGY_COOLDOWN_SECONDS",
      "STATBOT_RANGE_Z_LOOKBACK",
      "STATBOT_TREND_Z_LOOKBACK",
      "STATBOT_STRATEGY_TREND_ENTRY_Z",
      "STATBOT_STRATEGY_TREND_MIN_PERSIST",
      "STATBOT_STRATEGY_TREND_DIRECTIONAL_FILTER_MODE",
      "STATBOT_STRATEGY_TREND_DIRECTIONAL_FILTER_STRENGTH",
    ],
  },
  {
    id: "regime-router",
    title: "Regime Router",
    description: "Market-regime settings that influence policy and gating.",
    prefixes: ["STATBOT_REGIME_"],
  },
  {
    id: "trade-management",
    title: "Trade Management",
    description: "Hold-time, trailing, and ATM execution policy settings.",
    prefixes: ["STATBOT_ATM_"],
  },
];

function denormalizeSettingKey(key: string): string {
  if (key.startsWith("STATBOT_") || key.startsWith("OKX_")) {
    return key;
  }
  return `STATBOT_${key}`;
}

const KNOWN_API_ENV_KEYS = ["OKX_API_KEY", "OKX_API_SECRET", "OKX_FLAG", "OKX_PASSPHRASE"] as const;
const VISIBLE_INTERNAL_BOT_ENV_KEYS = new Set<string>([
  "STATBOT_STRATEGY_INTERNAL_KLINE_WORKERS",
  "STATBOT_STRATEGY_INTERNAL_MIN_PAIRS",
]);
const KNOWN_BOT_ENV_KEYS = Array.from(
  new Set([
    ...BOT_SETTING_GROUPS.flatMap((group) => group.keys ?? []),
    ...Object.keys(SETTING_TOOLTIPS)
      .map((key) => denormalizeSettingKey(key))
      .filter((key) => key.startsWith("STATBOT_")),
  ]),
).sort((a, b) => a.localeCompare(b));

const BOOLEAN_SETTING_KEYS = new Set<string>([
  "BLACKLIST_ENABLED",
  "BLACKLIST_REQUIRE_LOSS_DOMINANCE",
  "COMMAND_LISTENER",
  "DRY_RUN",
  "ENABLE_RISKOFF_COINT_EARLY_EXIT",
  "LIMIT_ORDER_BASIS",
  "LOCK_ON_PAIR",
  "MOLT_MONITOR",
  "PAIR_SUPPLY_RUN_IMMEDIATELY",
  "REPORT_ENABLE",
  "SKIP_INSTRUMENT_FETCH",
  "STRATEGY_FAST_PATH",
  "SWITCH_PRECHECK_COINT",
  "SWITCH_PRECHECK_FAIL_OPEN",
  "USE_FRESH_ORDERBOOK",
]);

const TIMEFRAME_OPTIONS: SettingOption[] = [
  "1m",
  "3m",
  "5m",
  "15m",
  "30m",
  "1H",
  "2H",
  "4H",
  "6H",
  "12H",
  "1D",
  "1W",
  "1M",
].map((value) => ({ label: value, value }));

const BOOLEAN_OPTIONS: SettingOption[] = [
  { label: "Enabled", value: "1" },
  { label: "Disabled", value: "0" },
];

const SETTING_SELECT_OPTIONS: Record<string, SettingOption[]> = {
  OKX_FLAG: [
    { label: "Demo", value: "1" },
    { label: "Live", value: "0" },
  ],
  EXECUTION_TIMEFRAME: TIMEFRAME_OPTIONS,
  HARD_STOP_PNL_BASIS: [
    { label: "Notional", value: "notional" },
    { label: "Equity", value: "equity" },
  ],
  INST_TYPE: [
    { label: "SWAP", value: "SWAP" },
    { label: "SPOT", value: "SPOT" },
    { label: "FUTURES", value: "FUTURES" },
    { label: "OPTION", value: "OPTION" },
    { label: "MARGIN", value: "MARGIN" },
  ],
  POS_MODE: [
    { label: "Long / Short", value: "long_short" },
    { label: "Net", value: "net" },
  ],
  REGIME_ROUTER_MODE: [
    { label: "Off", value: "off" },
    { label: "Shadow", value: "shadow" },
    { label: "Active", value: "active" },
  ],
  STRATEGY_ROUTER_MODE: [
    { label: "Off", value: "off" },
    { label: "Shadow", value: "shadow" },
    { label: "Active", value: "active" },
  ],
  STRATEGY_TIMEFRAME: TIMEFRAME_OPTIONS,
  STRATEGY_TREND_DIRECTIONAL_FILTER_MODE: [
    { label: "Off", value: "off" },
    { label: "Shadow", value: "shadow" },
    { label: "Active", value: "active" },
  ],
  TD_MODE: [
    { label: "Cross", value: "cross" },
    { label: "Isolated", value: "isolated" },
  ],
};

function getSettingOptions(fullKey: string): SettingOption[] | null {
  const normalized = normalizeSettingKey(fullKey);
  if (BOOLEAN_SETTING_KEYS.has(normalized)) {
    return BOOLEAN_OPTIONS;
  }
  return SETTING_SELECT_OPTIONS[normalized] || null;
}

function getOptionLabel(options: SettingOption[] | null, value: string): string {
  if (!options) {
    return value;
  }
  const match = options.find((option) => option.value.toLowerCase() === String(value || "").toLowerCase());
  return match?.label || value;
}

function getControlDefaultValue(fullKey: string): string {
  const tooltip = getTooltipInfo(fullKey);
  const options = getSettingOptions(fullKey);
  const rawDefault = String(tooltip?.default ?? "");
  if (!rawDefault || rawDefault === "(empty)") {
    return "";
  }
  if (!options?.length) {
    return rawDefault;
  }

  const normalizedDefault = rawDefault.trim().toLowerCase();
  const exact = options.find((option) => option.value.toLowerCase() === normalizedDefault);
  if (exact) {
    return exact.value;
  }
  if (normalizedDefault === "true") {
    return options.find((option) => option.value === "1")?.value || rawDefault;
  }
  if (normalizedDefault === "false") {
    return options.find((option) => option.value === "0")?.value || rawDefault;
  }
  return rawDefault;
}

function normalizeSettingKey(fullKey: string): string {
  if (fullKey.startsWith("STATBOT_")) {
    return fullKey.replace("STATBOT_", "");
  }
  return fullKey;
}

function formatSettingLabel(fullKey: string): string {
  return normalizeSettingKey(fullKey);
}

function getTooltipInfo(fullKey: string): SettingTooltip | null {
  return SETTING_TOOLTIPS[normalizeSettingKey(fullKey)] || null;
}

function buildSettingGroups(keys: string[], searchTerm: string, groups: SettingGroupDefinition[]): ResolvedSettingGroup[] {
  const loweredSearch = searchTerm.trim().toLowerCase();
  const filteredKeys = loweredSearch
    ? keys.filter((key) => key.toLowerCase().includes(loweredSearch))
    : [...keys];

  const remaining = new Set(filteredKeys);
  const resolved: ResolvedSettingGroup[] = [];

  for (const group of groups) {
    const matched = filteredKeys.filter((key) => {
      if (!remaining.has(key)) {
        return false;
      }
      if (group.keys?.includes(key)) {
        return true;
      }
      if (group.prefixes?.some((prefix) => key.startsWith(prefix))) {
        return true;
      }
      return false;
    });

    if (!matched.length) {
      continue;
    }

    matched.forEach((key) => remaining.delete(key));
    resolved.push({ ...group, settingKeys: matched });
  }

  const otherKeys = [...remaining].sort((a, b) => a.localeCompare(b));
  if (otherKeys.length) {
    resolved.push({
      id: "other",
      title: "Other Settings",
      description: "Settings that do not match one of the predefined groups yet.",
      settingKeys: otherKeys,
    });
  }

  return resolved;
}

export default function SettingsPage() {
  const router = useRouter();
  const [status, setStatus] = useState("Signed out");
  const [error, setError] = useState("");
  const [authChecked, setAuthChecked] = useState(false);
  const [profileResolved, setProfileResolved] = useState(false);
  const [activeTab, setActiveTab] = useState<TabType>("bot");
  const [me, setMe] = useState<UserRecord | null>(null);

  const [envSettings, setEnvSettings] = useState<AdminEnvSettings>({ path: "Execution/.env", values: {} });
  const [envEdits, setEnvEdits] = useState<Record<string, string>>({});
  const [editingEnvKeys, setEditingEnvKeys] = useState<Set<string>>(new Set());
  const [showPasswordKeys, setShowPasswordKeys] = useState<Set<string>>(new Set());
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [tooltipKey, setTooltipKey] = useState<string | null>(null);
  const [collapsedBotGroups, setCollapsedBotGroups] = useState<Record<string, boolean>>({});
  const navItems = useMemo(() => getAdminNavItems(me), [me]);
  const fallbackHref = useMemo(() => getFirstAccessibleAdminPath(me), [me]);
  const canEditSettings = hasPermission(me, "edit_settings");
  const canManageApi = hasPermission(me, "manage_api");
  const canViewSettings = canAccessAdminPath(me, "/admin/settings");

  const clearAdminSession = useCallback((reason = "Signed out", redirectToLogin = false) => {
    clearStoredAdminSession();
    setStatus(reason);
    setError("");
    setProfileResolved(false);
    setMe(null);
    if (redirectToLogin) {
      router.replace("/login?next=/admin/settings");
    }
  }, [router]);

  const loadEnvSettings = useCallback(async () => {
    const envData = await getAdminEnvSettings();
    setEnvSettings(envData);
    if (envData?.values) {
      setEnvEdits(envData.values);
    }
  }, []);

  useEffect(() => {
    const storedEmail = getStoredAdminEmail();
    if (storedEmail) {
      const fallbackMe: UserRecord = {
        id: "",
        email: storedEmail,
        is_active: false,
        permissions: [],
        roles: [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      setMe((prev) => (prev ? { ...prev, email: storedEmail } : fallbackMe));
    }

    setStatus("Loading settings...");
    setAuthChecked(true);
    setProfileResolved(false);
    getMe()
      .then(async (userData) => {
        setMe(userData);
        if (!canAccessAdminPath(userData, "/admin/settings")) {
          setStatus("Redirecting");
          setError("Settings access is not enabled for your account.");
          const nextHref = getFirstAccessibleAdminPath(userData);
          if (nextHref && nextHref !== "/admin/settings") {
            router.replace(nextHref);
          }
          return;
        }
        await loadEnvSettings();
        setStatus("Session restored");
      })
      .catch((err: unknown) => {
        if (isUnauthorizedError(err)) {
          clearAdminSession("Session expired. Please sign in again.", true);
          setError("Session expired. Please sign in again.");
          return;
        }
        const msg = err instanceof Error ? err.message : "Failed loading settings";
        setError(msg);
      })
      .finally(() => setProfileResolved(true));
  }, [clearAdminSession, loadEnvSettings, router]);

  useEffect(() => {
    if (!profileResolved || !me || canViewSettings) {
      return;
    }
    setEnvSettings({ path: "Execution/.env", values: {} });
    setEnvEdits({});
    if (fallbackHref && fallbackHref !== "/admin/settings") {
      setStatus("Redirecting");
      setError("Settings access is not enabled for your account.");
      router.replace(fallbackHref);
    }
  }, [canViewSettings, fallbackHref, me, profileResolved, router]);

  useEffect(() => {
    if (canEditSettings) {
      setActiveTab((prev) => (prev === "api" && !canManageApi ? "bot" : prev));
      return;
    }
    if (canManageApi) {
      setActiveTab("api");
    }
  }, [canEditSettings, canManageApi]);

  // Handle Esc key to cancel editing
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && editingEnvKeys.size > 0) {
        setEditingEnvKeys(new Set());
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [editingEnvKeys]);

  const sortedEnvKeys = useMemo(() => {
    const knownKeys = new Set<string>([...KNOWN_BOT_ENV_KEYS, ...KNOWN_API_ENV_KEYS]);
    const savedKeys = Object.keys(envSettings.values || {});
    for (const key of savedKeys) {
      knownKeys.add(key);
    }
    return [...knownKeys].sort((a, b) => a.localeCompare(b));
  }, [envSettings.values]);

  const apiKeys = useMemo(
    () => new Set<string>(KNOWN_API_ENV_KEYS),
    [],
  );

  const botEnvKeys = useMemo(
    () => sortedEnvKeys.filter((key) => {
      if (apiKeys.has(key)) {
        return false;
      }
      return !key.startsWith("STATBOT_STRATEGY_INTERNAL_") || VISIBLE_INTERNAL_BOT_ENV_KEYS.has(key);
    }),
    [sortedEnvKeys, apiKeys],
  );

  const apiEnvKeys = useMemo(
    () => sortedEnvKeys.filter((key) => apiKeys.has(key)),
    [sortedEnvKeys, apiKeys],
  );

  const groupedBotSettingSections = useMemo(
    () => buildSettingGroups(botEnvKeys, searchTerm, BOT_SETTING_GROUPS),
    [botEnvKeys, searchTerm],
  );
  const isBotSearchActive = searchTerm.trim().length > 0;

  const filteredKeys = useMemo(() => {
    return apiEnvKeys.filter((key) => key.toLowerCase().includes(searchTerm.toLowerCase()));
  }, [apiEnvKeys, searchTerm]);

  useEffect(() => {
    setCollapsedBotGroups((prev) => {
      const next: Record<string, boolean> = {};
      let changed = false;

      for (const group of groupedBotSettingSections) {
        if (Object.prototype.hasOwnProperty.call(prev, group.id)) {
          next[group.id] = prev[group.id];
        } else {
          next[group.id] = true;
          changed = true;
        }
      }

      const prevKeys = Object.keys(prev);
      if (prevKeys.length !== Object.keys(next).length) {
        changed = true;
      } else {
        for (const key of prevKeys) {
          if (!(key in next) || next[key] !== prev[key]) {
            changed = true;
            break;
          }
        }
      }

      return changed ? next : prev;
    });
  }, [groupedBotSettingSections]);

  const toggleBotGroup = useCallback((groupId: string) => {
    setCollapsedBotGroups((prev) => ({
      ...prev,
      [groupId]: !(prev[groupId] ?? true),
    }));
  }, []);

  const setAllBotGroupsCollapsed = useCallback((collapsed: boolean) => {
    setCollapsedBotGroups((prev) => {
      const next = { ...prev };
      for (const group of groupedBotSettingSections) {
        next[group.id] = collapsed;
      }
      return next;
    });
  }, [groupedBotSettingSections]);

  const startEditMode = useCallback((key: string) => {
    const hasStoredValue = Object.prototype.hasOwnProperty.call(envSettings.values || {}, key);
    const storedValue = hasStoredValue ? (envSettings.values?.[key] ?? "") : "";
    const nextValue = hasStoredValue ? storedValue : getControlDefaultValue(key);
    setEnvEdits((prev) => ({
      ...prev,
      [key]: nextValue,
    }));
    setEditingEnvKeys((prev) => {
      const next = new Set(prev);
      next.add(key);
      return next;
    });
  }, [envSettings.values]);

  async function saveEnvKey(key: string) {
    if (!me) return;
    const value = envEdits[key] ?? "";
    setBusy(true);
    setError("");
    try {
      const next = await updateAdminEnvSetting(key, value);
      setEnvSettings(next);
      setEnvEdits(next.values || {});
      setStatus(`Saved ${key}`);
      setEditingEnvKeys((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Failed saving env key";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  function cancelEditMode(key: string) {
    setEditingEnvKeys((prev) => {
      const next = new Set(prev);
      next.delete(key);
      return next;
    });
    setEnvEdits((prev) => {
      const next = { ...prev };
      if (Object.prototype.hasOwnProperty.call(envSettings.values || {}, key)) {
        next[key] = envSettings.values?.[key] ?? "";
      } else {
        delete next[key];
      }
      return next;
    });
  }

  const secondaryButtonClasses = UI_CLASSES.secondaryButton;
  const sectionCardClasses = UI_CLASSES.sectionCard;

  if (!authChecked) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900">
        <p className="text-sm text-gray-500 dark:text-gray-400">Checking admin session...</p>
      </div>
    );
  }

  if (profileResolved && me && !canViewSettings && !fallbackHref) {
    return (
      <DashboardShell
        title="Settings"
        subtitle="Configure environment variables and API credentials."
        status="Access restricted"
        activeHref="/admin/settings"
        navItems={navItems}
        auth={{
          email: me.email || (typeof window !== "undefined" ? getStoredAdminEmail() : ""),
          hasToken: Boolean(me),
        }}
      >
        <section className={sectionCardClasses}>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-white/90">Settings</h1>
          <p className="mt-2 text-sm text-error-600 dark:text-error-400">Settings permissions are not enabled for this account.</p>
        </section>
      </DashboardShell>
    );
  }

  if (!profileResolved) {
    return (
      <DashboardShell
        title="Settings"
        subtitle="Configure environment variables and API credentials."
        status={status}
        activeHref="/admin/settings"
        navItems={navItems}
        auth={{
          email: me?.email || (typeof window !== "undefined" ? getStoredAdminEmail() : ""),
          hasToken: Boolean(me),
        }}
      >
        <section className={sectionCardClasses}>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-500">Configuration</p>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{status}</p>
          </div>
        </section>
      </DashboardShell>
    );
  }

  const tabButtonClass = (isActive: boolean) =>
    `px-4 py-2 font-medium text-sm ${
      isActive
        ? "border-b-2 border-brand-500 text-brand-600 dark:text-brand-400"
        : "border-b-2 border-transparent text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-300"
    }`;

  return (
    <DashboardShell
      title="Settings"
      subtitle="Configure environment variables and API credentials."
      status={status}
      activeHref="/admin/settings"
      navItems={navItems}
      auth={{
        email: me?.email || (typeof window !== "undefined" ? getStoredAdminEmail() : ""),
        hasToken: Boolean(me),
      }}
    >
      <div className="grid gap-4">
        <section className={sectionCardClasses}>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-500">Configuration</p>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{status}</p>
            </div>
          </div>
        </section>

        {error ? <p className="text-sm text-error-600 dark:text-error-400">{error}</p> : null}

        {/* Tabs */}
        <div className="flex flex-wrap gap-8 border-b border-gray-200 dark:border-gray-700">
            {canEditSettings ? (
              <button
                onClick={() => setActiveTab("bot")}
                className={tabButtonClass(activeTab === "bot")}
              >
                Bot Settings
              </button>
            ) : null}
            {canManageApi ? (
              <button
                onClick={() => setActiveTab("api")}
                className={tabButtonClass(activeTab === "api")}
              >
                API Credentials
              </button>
            ) : null}
        </div>

        <section className={sectionCardClasses}>
          <div className="mt-6">
            {activeTab === "bot" && canEditSettings && (
              <div>
                <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white/90">Bot Configuration</h3>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      Grouped runtime settings. Updates `Execution/.env` directly.
                      {isBotSearchActive ? " Matching categories expand automatically while searching." : " Categories start collapsed for quicker scanning."}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      className={secondaryButtonClasses}
                      onClick={() => setAllBotGroupsCollapsed(false)}
                      disabled={!groupedBotSettingSections.length || isBotSearchActive}
                    >
                      Expand all
                    </button>
                    <button
                      type="button"
                      className={secondaryButtonClasses}
                      onClick={() => setAllBotGroupsCollapsed(true)}
                      disabled={!groupedBotSettingSections.length || isBotSearchActive}
                    >
                      Collapse all
                    </button>
                    <input
                      type="text"
                      placeholder="Search settings..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-500 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-white dark:placeholder-gray-400"
                    />
                  </div>
                </div>

                <div className="grid items-start gap-6 xl:grid-cols-2">
                  {groupedBotSettingSections.map((group) => {
                    const isCollapsed = isBotSearchActive ? false : (collapsedBotGroups[group.id] ?? true);

                    return (
                      <div key={group.id} className="self-start rounded-xl border border-gray-200 bg-white/70 dark:border-gray-700 dark:bg-gray-900/40">
                        <button
                          type="button"
                          onClick={() => toggleBotGroup(group.id)}
                          disabled={isBotSearchActive}
                          aria-expanded={!isCollapsed}
                          className="flex w-full items-start justify-between gap-4 px-4 py-4 text-left disabled:cursor-default"
                        >
                          <div>
                            <h4 className="text-base font-semibold text-gray-900 dark:text-white/90">{group.title}</h4>
                            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{group.description}</p>
                          </div>
                          <div className="shrink-0 text-right">
                            <p className="text-xs font-medium text-gray-500 dark:text-gray-400">{group.settingKeys.length} setting{group.settingKeys.length === 1 ? "" : "s"}</p>
                            <p className="mt-1 text-xs text-brand-600 dark:text-brand-400">
                              {isBotSearchActive ? "Open for search" : (isCollapsed ? "Expand" : "Collapse")}
                            </p>
                          </div>
                        </button>

                        {!isCollapsed ? (
                          <div className="border-t border-gray-200 dark:border-gray-700">
                            <div className="overflow-x-auto rounded-b-xl">
                              <table className="w-full border-collapse">
                                <thead>
                                  <tr className="bg-gray-50 dark:bg-gray-800">
                                    <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Key</th>
                                    <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 w-32">Value</th>
                                    <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 w-16">Action</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {group.settingKeys.map((key) => {
                                    const isEditing = editingEnvKeys.has(key);
                                    const tooltipInfo = getTooltipInfo(key);
                                    const hasStoredValue = Object.prototype.hasOwnProperty.call(envSettings.values || {}, key);
                                    const storedValue = hasStoredValue ? (envSettings.values?.[key] ?? "") : "";
                                    const defaultValue = getControlDefaultValue(key);
                                    const currentValue = isEditing
                                      ? (envEdits[key] ?? defaultValue)
                                      : (hasStoredValue ? storedValue : defaultValue);
                                    const settingOptions = getSettingOptions(key);
                                    const displayValue = currentValue || "(empty)";
                                    const displayLabel = currentValue
                                      ? getOptionLabel(settingOptions, currentValue)
                                      : "(empty)";
                                    const sourceLabel = hasStoredValue ? "Saved in .env" : (tooltipInfo ? "Using default" : "");
                                    return (
                                      <tr key={key} className="border-t border-gray-100 dark:border-gray-800">
                                        <td className="relative px-3 py-2 text-xs text-gray-600 dark:text-gray-400 font-mono">
                                          <div className="flex items-center gap-1">
                                            <span title={key}>{formatSettingLabel(key)}</span>
                                            {tooltipInfo && (
                                              <button
                                                type="button"
                                                onClick={() => setTooltipKey(tooltipKey === key ? null : key)}
                                                onMouseEnter={() => setTooltipKey(key)}
                                                onMouseLeave={() => setTooltipKey(null)}
                                                className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full bg-gray-200 text-[10px] font-semibold text-gray-500 hover:bg-gray-300 dark:bg-gray-700 dark:text-gray-400 dark:hover:bg-gray-600"
                                                title={tooltipInfo.default}
                                              >
                                                ?
                                              </button>
                                            )}
                                          </div>
                                          {tooltipInfo && tooltipKey === key && (
                                            <div className="absolute z-50 mt-2 w-64 max-w-xs rounded-md bg-gray-900 px-3 py-2 text-xs text-white shadow-lg whitespace-normal break-words">
                                              <p className="font-semibold">Default: {tooltipInfo.default}</p>
                                              <p className="mt-1 text-gray-300">{tooltipInfo.description}</p>
                                            </div>
                                          )}
                                        </td>
                                        <td className="px-3 py-2 text-xs">
                                          {isEditing ? (
                                            settingOptions ? (
                                              <select
                                                value={currentValue}
                                                onChange={(e) =>
                                                  setEnvEdits((prev) => ({
                                                    ...prev,
                                                    [key]: e.target.value,
                                                  }))
                                                }
                                                className="w-full h-6 rounded border border-gray-300 px-1 py-0.5 text-xs text-gray-900 focus:border-blue-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                                              >
                                                {settingOptions.map((option) => (
                                                  <option key={option.value} value={option.value}>
                                                    {option.label}
                                                  </option>
                                                ))}
                                              </select>
                                            ) : (
                                              <input
                                                value={currentValue}
                                                onChange={(e) =>
                                                  setEnvEdits((prev) => ({
                                                    ...prev,
                                                    [key]: e.target.value,
                                                  }))
                                                }
                                                className="w-full h-6 rounded border border-gray-300 px-1 py-0.5 text-xs text-gray-900 focus:border-blue-500 focus:outline-none dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                                              />
                                            )
                                          ) : (
                                            <div className="max-w-28">
                                              <span
                                                className="block truncate text-gray-700 dark:text-gray-300"
                                                title={displayValue}
                                              >
                                                {displayLabel}
                                              </span>
                                              {sourceLabel ? (
                                                <span className="mt-0.5 block text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">
                                                  {sourceLabel}
                                                </span>
                                              ) : null}
                                            </div>
                                          )}
                                        </td>
                                        <td className="px-3 py-2">
                                          {isEditing ? (
                                            <div className="flex gap-1">
                                              <button
                                                className="rounded bg-blue-600 px-2 py-0.5 text-xs text-white hover:bg-blue-700"
                                                onClick={() => saveEnvKey(key)}
                                                disabled={busy}
                                              >
                                                Save
                                              </button>
                                              <button
                                                className="rounded bg-gray-200 px-2 py-0.5 text-xs text-gray-700 hover:bg-gray-300 dark:bg-gray-600 dark:text-gray-200 dark:hover:bg-gray-500"
                                                onClick={() => cancelEditMode(key)}
                                                disabled={busy}
                                              >
                                                Cancel
                                              </button>
                                            </div>
                                          ) : (
                                            <button
                                              className="rounded border border-gray-300 bg-white px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
                                              onClick={() => startEditMode(key)}
                                              disabled={busy}
                                            >
                                              Edit
                                            </button>
                                          )}
                                        </td>
                                      </tr>
                                    );
                                  })}
                                  {!group.settingKeys.length ? (
                                    <tr>
                                      <td colSpan={3} className="px-3 py-4 text-xs text-gray-500 dark:text-gray-400 text-center">
                                        {searchTerm ? "No matches." : "No settings in this group."}
                                      </td>
                                    </tr>
                                  ) : null}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
                {!groupedBotSettingSections.length ? (
                  <p className="mt-4 text-sm text-gray-500 dark:text-gray-400">
                    {searchTerm ? "No bot settings match this search." : "No bot settings available."}
                  </p>
                ) : null}
              </div>
            )}

            {activeTab === "api" && canManageApi && (
              <div>
                <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white/90">OKX API Credentials</h3>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Manage OKX API keys. Keep these values secure!</p>
                  </div>
                  <input
                    type="text"
                    placeholder="Search credentials..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-500 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-white dark:placeholder-gray-400"
                  />
                </div>
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full border-collapse">
                    <thead>
                      <tr className="border-b border-gray-200 dark:border-gray-700">
                        <th className="px-4 py-2 text-left text-sm font-semibold text-gray-900 dark:text-white/90">Key</th>
                        <th className="px-4 py-2 text-left text-sm font-semibold text-gray-900 dark:text-white/90 w-96">Value</th>
                        <th className="px-4 py-2 text-left text-sm font-semibold text-gray-900 dark:text-white/90 w-40">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredKeys.map((key) => {
                        const isEditing = editingEnvKeys.has(key);
                        const hasStoredValue = Object.prototype.hasOwnProperty.call(envSettings.values || {}, key);
                        const storedValue = hasStoredValue ? (envSettings.values?.[key] ?? "") : "";
                        const defaultValue = getControlDefaultValue(key);
                        const currentValue = isEditing
                          ? (envEdits[key] ?? defaultValue)
                          : (hasStoredValue ? storedValue : defaultValue);
                        const settingOptions = getSettingOptions(key);
                        const sourceLabel = hasStoredValue ? "Saved in .env" : (defaultValue ? "Using default" : "");
                        return (
                          <tr key={key} className="h-10 border-b border-gray-100 dark:border-gray-800">
                            <td className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400">{key}</td>
                            <td className="px-4 py-2 text-sm w-96">
                              {isEditing ? (
                                settingOptions ? (
                                  <select
                                    value={currentValue}
                                    onChange={(e) =>
                                      setEnvEdits((prev) => ({
                                        ...prev,
                                        [key]: e.target.value,
                                      }))
                                    }
                                    className="w-full h-8 rounded border border-gray-300 px-2 py-1 text-sm text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white"
                                  >
                                    {settingOptions.map((option) => (
                                      <option key={option.value} value={option.value}>
                                        {option.label}
                                      </option>
                                    ))}
                                  </select>
                                ) : (
                                  <input
                                    value={currentValue}
                                    onChange={(e) =>
                                      setEnvEdits((prev) => ({
                                        ...prev,
                                        [key]: e.target.value,
                                      }))
                                    }
                                    type="password"
                                    className="w-full h-8 rounded border border-gray-300 px-2 py-1 text-sm text-gray-900 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white dark:placeholder-gray-400"
                                  />
                                )
                              ) : (
                                <div className="flex items-center justify-between gap-2">
                                  <span className="font-mono text-gray-700 dark:text-gray-300 flex-1 truncate">
                                    {settingOptions
                                      ? getOptionLabel(settingOptions, currentValue || "(empty)")
                                      : showPasswordKeys.has(key)
                                        ? currentValue || "(empty)"
                                        : currentValue ? "•".repeat(Math.min(currentValue.length, 16)) : "(empty)"}
                                  </span>
                                  {sourceLabel ? (
                                    <span className="shrink-0 text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">
                                      {sourceLabel}
                                    </span>
                                  ) : null}
                                </div>
                              )}
                            </td>
                            <td className="px-4 py-2 text-sm w-40">
                              {isEditing ? (
                                <div className="flex gap-2">
                                  <button
                                    className={UI_CLASSES.primaryButton}
                                    onClick={() => saveEnvKey(key)}
                                    disabled={busy}
                                  >
                                    Save
                                  </button>
                                  <button
                                    className={secondaryButtonClasses}
                                    onClick={() => cancelEditMode(key)}
                                    disabled={busy}
                                  >
                                    Cancel
                                  </button>
                                </div>
                              ) : (
                                <div className="flex gap-2">
                                  <button
                                    className={secondaryButtonClasses}
                                    onClick={() =>
                                      setShowPasswordKeys((prev) =>
                                        prev.has(key)
                                          ? new Set([...prev].filter((k) => k !== key))
                                          : new Set(prev).add(key)
                                      )
                                    }
                                    disabled={busy}
                                    title={showPasswordKeys.has(key) ? "Hide password" : "Show password"}
                                  >
                                    {showPasswordKeys.has(key) ? "Hide" : "Show"}
                                  </button>
                                  <button
                                    className={secondaryButtonClasses}
                                    onClick={() => startEditMode(key)}
                                    disabled={busy}
                                  >
                                    Edit
                                  </button>
                                </div>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                      {!filteredKeys.length ? (
                        <tr>
                          <td colSpan={3} className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">
                            {searchTerm ? "No credentials match your search." : "No credentials found."}
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
    </DashboardShell>
  );
}
