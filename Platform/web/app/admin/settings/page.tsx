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
  MIN_PERSIST_BARS: { description: "Minimum consecutive bars a signal must persist before entry", default: "4" },
  MAX_CONSECUTIVE_LOSSES: { description: "Consecutive pair losses allowed before pair retirement logic escalates", default: "2" },
  HEALTH_CHECK_INTERVAL: { description: "Seconds between pair health evaluations while running", default: "3600" },
  STATUS_UPDATE_INTERVAL: { description: "Seconds between execution status updates", default: "60" },
  P_VALUE_CRITICAL: { description: "Base p-value threshold used to judge cointegration health", default: "0.15" },
  ZERO_CROSSINGS_MIN: { description: "Minimum zero crossings expected for a healthy pair", default: "15" },
  CORRELATION_MIN: { description: "Minimum correlation threshold for pair health", default: "0.60" },
  TREND_CRITICAL: { description: "Maximum allowed spread trend magnitude before health degradation", default: "0.002" },
  Z_SCORE_CRITICAL: { description: "Maximum absolute Z-score tolerated before health degradation", default: "6.0" },
  MAX_DRAWDOWN_PCT: { description: "Circuit breaker loss threshold as a decimal of capital", default: "0.05" },
  LOCK_ON_PAIR: { description: "Lock to current pair until trade completes", default: "False" },
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
  HOSPITAL_COOLDOWN_SECONDS: { description: "Cooldown time in seconds for pairs in hospital", default: "3600" },
  // Strategy settings (exposed ones)
  STRATEGY_ROUTER_MODE: { description: "Strategy router mode: active or passive", default: "active" },
  STRATEGY_LIQUIDITY_PCT: { description: "Minimum liquidity percentage filter", default: "0" },
  STRATEGY_CORR_MIN: { description: "Minimum correlation coefficient (0-1)", default: "0.6" },
  STRATEGY_MIN_CAPITAL_PER_LEG: { description: "Minimum capital per leg in USDT (0=any)", default: "0" },
  STRATEGY_MIN_P_VALUE: { description: "Minimum p-value for cointegration (scientific notation)", default: "1e-08" },
  STRATEGY_MAX_P_VALUE: { description: "Maximum p-value for cointegration", default: "0.01" },
  STRATEGY_MIN_ZERO_CROSSINGS: { description: "Minimum zero crossings for valid pair", default: "3" },
  STRATEGY_MAX_PAIRS_PER_TICKER: { description: "Maximum cointegrated pairs per ticker", default: "10" },
  STRATEGY_MIN_ORDERBOOK_DEPTH: { description: "Minimum orderbook depth in USDT", default: "1000" },
  STRATEGY_MIN_ORDERBOOK_LEVELS: { description: "Minimum orderbook levels required", default: "10" },
  STRATEGY_EVAL_SECONDS: { description: "Seconds between strategy evaluation", default: "30" },
  REGIME_ROUTER_MODE: { description: "Regime detection router mode: active or passive", default: "active" },
  REGIME_EVAL_SECONDS: { description: "Seconds between regime evaluation", default: "30" },
  STRATEGY_SCORE_WINDOW_TRADES: { description: "Number of trades for rolling score window", default: "20" },
  STRATEGY_SCORE_MIN_TRADES: { description: "Minimum trades required for scoring", default: "8" },
  STRATEGY_SCORE_MIN_WIN_RATE: { description: "Minimum win rate for scoring (0-1)", default: "0.35" },
  STRATEGY_SCORE_MAX_ROLLING_LOSS_USDT: { description: "Maximum rolling loss in USDT", default: "20" },
  STRATEGY_COOLDOWN_SECONDS: { description: "Cooldown seconds between strategy switches or entries", default: "3600" },
  RANGE_Z_LOOKBACK: { description: "Lookback bars for range Z-score calculation", default: "200" },
  TREND_Z_LOOKBACK: { description: "Lookback bars for trend Z-score calculation", default: "60" },
  STRATEGY_TREND_DIRECTIONAL_FILTER_MODE: { description: "Trend directional filter mode: shadow, strict, or off", default: "shadow" },
  STRATEGY_TREND_DIRECTIONAL_FILTER_STRENGTH: { description: "Trend directional filter strength", default: "1.0" },
  ATM_MR_MAX_HOLD_HOURS: { description: "Max hold hours for mean reversion mode", default: "6" },
  ATM_MR_MAX_HOLD_WARNING_HOURS: { description: "Warning threshold for MR hold hours", default: "4" },
  ATM_TREND_MAX_HOLD_HOURS: { description: "Max hold hours for trend mode", default: "2" },
  ATM_TREND_MAX_HOLD_WARNING_HOURS: { description: "Warning threshold for trend hold hours", default: "1.5" },
  ATM_TREND_TRAILING_ACTIVATION: { description: "Trailing activation threshold", default: "1.0" },
  ATM_TREND_TRAILING_TIGHT_DISTANCE: { description: "Tight trailing distance", default: "0.25" },
  ATM_TREND_TRAILING_MID_DISTANCE: { description: "Mid trailing distance", default: "0.35" },
  ATM_TREND_TRAILING_LOOSE_DISTANCE: { description: "Loose trailing distance", default: "0.45" },
  REPORT_ENABLE: { description: "Enable periodic reports", default: "1" },
  REPORT_UPTIME_HOURS: { description: "Report uptime in hours", default: "24" },
  MAX_UPTIME_HOURS: { description: "Max uptime hours before restart", default: "24" },
  ORDERBOOK_BACKOFF_SECONDS: { description: "Backoff seconds when orderbook fails", default: "45" },
  ORDERBOOK_BACKOFF_RETRIES: { description: "Number of orderbook backoff retries", default: "2" },
  ORDERBOOK_BACKOFF_RETRY_SLEEP: { description: "Sleep seconds between backoff retries", default: "0.25" },
  MOLT_MONITOR: { description: "Enable molt monitor (1=yes, 0=no)", default: "0" },
  COMMAND_LISTENER: { description: "Enable command listener (1=yes, 0=no)", default: "0" },
  BALANCE_FETCH_TIMEOUT_SECONDS: { description: "Timeout for balance fetch in seconds", default: "8" },
  HARD_STOP_PNL_BASIS: { description: "Hard stop PnL basis: notional or cash", default: "notional" },
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
      "STATBOT_P_VALUE_CRITICAL",
      "STATBOT_ZERO_CROSSINGS_MIN",
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
      "STATBOT_MAX_CONSECUTIVE_LOSSES",
      "STATBOT_HEALTH_CHECK_INTERVAL",
      "STATBOT_STATUS_UPDATE_INTERVAL",
      "STATBOT_BLACKLIST_ENABLED",
      "STATBOT_BLACKLIST_MIN_TRADES",
      "STATBOT_BLACKLIST_MAX_LOSS_RATE",
      "STATBOT_BLACKLIST_REQUIRE_LOSS_DOMINANCE",
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
      "STATBOT_STRATEGY_LIQUIDITY_PCT",
      "STATBOT_STRATEGY_CORR_MIN",
      "STATBOT_STRATEGY_MIN_CAPITAL_PER_LEG",
      "STATBOT_STRATEGY_MIN_P_VALUE",
      "STATBOT_STRATEGY_MAX_P_VALUE",
      "STATBOT_STRATEGY_MIN_ZERO_CROSSINGS",
      "STATBOT_STRATEGY_MAX_PAIRS_PER_TICKER",
      "STATBOT_STRATEGY_MIN_ORDERBOOK_DEPTH",
      "STATBOT_STRATEGY_MIN_ORDERBOOK_LEVELS",
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

  const sortedEnvKeys = useMemo(
    () => Object.keys(envSettings.values || {}).sort((a, b) => a.localeCompare(b)),
    [envSettings.values],
  );

  const apiKeys = useMemo(
    () => new Set(["OKX_API_KEY", "OKX_API_SECRET", "OKX_FLAG", "OKX_PASSPHRASE"]),
    [],
  );

  const botEnvKeys = useMemo(
    () => sortedEnvKeys.filter((key) => !apiKeys.has(key) && !key.startsWith("STATBOT_STRATEGY_INTERNAL_")),
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
    // Reset the value to the original
    setEnvEdits((prev) => ({
      ...prev,
      [key]: envSettings.values?.[key] ?? "",
    }));
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
                                    const currentValue = envEdits[key] ?? envSettings.values?.[key] ?? "";
                                    const tooltipInfo = getTooltipInfo(key);
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
                                          ) : (
                                            <span className="text-gray-700 dark:text-gray-300 truncate block max-w-28">{currentValue || "(empty)"}</span>
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
                                              onClick={() => setEditingEnvKeys((prev) => new Set(prev).add(key))}
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
                        const currentValue = envEdits[key] ?? envSettings.values?.[key] ?? "";
                        return (
                          <tr key={key} className="h-10 border-b border-gray-100 dark:border-gray-800">
                            <td className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400">{key}</td>
                            <td className="px-4 py-2 text-sm w-96">
                              {isEditing ? (
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
                              ) : (
                                <div className="flex items-center justify-between gap-2">
                                  <span className="font-mono text-gray-700 dark:text-gray-300 flex-1 truncate">
                                    {showPasswordKeys.has(key)
                                      ? currentValue || "(empty)"
                                      : currentValue ? "•".repeat(Math.min(currentValue.length, 16)) : "(empty)"}
                                  </span>
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
                                    onClick={() => setEditingEnvKeys((prev) => new Set(prev).add(key))}
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
