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

// Tooltip configuration for settings with descriptions and default values
const SETTING_TOOLTIPS: Record<string, { description: string; default: string }> = {
  // Execution settings
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
  ROUTER_MODE: { description: "Strategy router mode: active or passive", default: "active" },
  LIQUIDITY_PCT: { description: "Minimum liquidity percentage filter", default: "0" },
  CORR_MIN: { description: "Minimum correlation coefficient (0-1)", default: "0.6" },
  MIN_P_VALUE: { description: "Minimum p-value for cointegration (scientific notation)", default: "1e-08" },
  MAX_P_VALUE: { description: "Maximum p-value for cointegration", default: "0.01" },
  MIN_ZERO_CROSSINGS: { description: "Minimum zero crossings for valid pair", default: "3" },
  MAX_PAIRS_PER_TICKER: { description: "Maximum cointegrated pairs per ticker", default: "10" },
  MIN_ORDERBOOK_DEPTH: { description: "Minimum orderbook depth in USDT", default: "1000" },
  MIN_ORDERBOOK_LEVELS: { description: "Minimum orderbook levels required", default: "10" },
  STRATEGY_EVAL_SECONDS: { description: "Seconds between strategy evaluation", default: "30" },
  REGIME_ROUTER_MODE: { description: "Regime detection router mode: active or passive", default: "active" },
  REGIME_EVAL_SECONDS: { description: "Seconds between regime evaluation", default: "30" },
  SCORE_WINDOW_TRADES: { description: "Number of trades for rolling score window", default: "20" },
  SCORE_MIN_TRADES: { description: "Minimum trades required for scoring", default: "8" },
  SCORE_MIN_WIN_RATE: { description: "Minimum win rate for scoring (0-1)", default: "0.35" },
  SCORE_MAX_ROLLING_LOSS_USDT: { description: "Maximum rolling loss in USDT", default: "20" },
  COOLDOWN_SECONDS: { description: "Cooldown seconds between trades", default: "3600" },
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

// Helper to get tooltip info from full env key
function getTooltipInfo(fullKey: string): { description: string; default: string } | null {
  // Extract short key (e.g., STATBOT_LOCK_ON_PAIR -> LOCK_ON_PAIR)
  // Handle prefixes in order: STRATEGY_, REGIME_, then STATBOT_
  let shortKey = fullKey;
  if (fullKey.startsWith("STATBOT_STRATEGY_")) {
    shortKey = fullKey.replace("STATBOT_STRATEGY_", "");
  } else if (fullKey.startsWith("STATBOT_REGIME_")) {
    shortKey = fullKey.replace("STATBOT_REGIME_", "");
  } else if (fullKey.startsWith("STATBOT_")) {
    shortKey = fullKey.replace("STATBOT_", "");
  }
  return SETTING_TOOLTIPS[shortKey] || null;
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

  const executionKeys = useMemo(
    () => sortedEnvKeys.filter((key) => !key.startsWith("STATBOT_STRATEGY_") && !key.startsWith("STATBOT_STRATEGY_INTERNAL_") && !apiKeys.has(key)),
    [sortedEnvKeys, apiKeys],
  );

  const strategyKeys = useMemo(
    () => sortedEnvKeys.filter((key) => key.startsWith("STATBOT_STRATEGY_") && !key.startsWith("STATBOT_STRATEGY_INTERNAL_") && !apiKeys.has(key)),
    [sortedEnvKeys, apiKeys],
  );

  const botEnvKeys = useMemo(
    () => sortedEnvKeys.filter((key) => !apiKeys.has(key)),
    [sortedEnvKeys, apiKeys],
  );

  const apiEnvKeys = useMemo(
    () => sortedEnvKeys.filter((key) => apiKeys.has(key)),
    [sortedEnvKeys, apiKeys],
  );

  const filteredExecutionKeys = useMemo(() => {
    return executionKeys.filter((key) => key.toLowerCase().includes(searchTerm.toLowerCase()));
  }, [executionKeys, searchTerm]);

  const filteredStrategyKeys = useMemo(() => {
    return strategyKeys.filter((key) => key.toLowerCase().includes(searchTerm.toLowerCase()));
  }, [strategyKeys, searchTerm]);

  const filteredKeys = useMemo(() => {
    const sourceKeys = activeTab === "bot" ? botEnvKeys : apiEnvKeys;
    return sourceKeys.filter((key) => key.toLowerCase().includes(searchTerm.toLowerCase()));
  }, [botEnvKeys, apiEnvKeys, activeTab, searchTerm]);

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
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">General bot settings. Updates `Execution/.env` directly.</p>
                  </div>
                  <input
                    type="text"
                    placeholder="Search settings..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-500 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-800 dark:text-white dark:placeholder-gray-400"
                  />
                </div>

                {/* Side-by-side tables for Execution and Strategy */}
                <div className="grid gap-6 lg:grid-cols-2">
                  {/* Execution Settings */}
                  <div>
                    <h4 className="mb-3 text-base font-semibold text-gray-900 dark:text-white/90">Execution Settings</h4>
                    <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
                      <table className="w-full border-collapse">
                        <thead>
                          <tr className="bg-gray-50 dark:bg-gray-800">
                            <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Key</th>
                            <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 w-32">Value</th>
                            <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 w-16">Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filteredExecutionKeys.map((key) => {
                            const isEditing = editingEnvKeys.has(key);
                            const currentValue = envEdits[key] ?? envSettings.values?.[key] ?? "";
                            const tooltipInfo = getTooltipInfo(key);
                            return (
                              <tr key={key} className="border-t border-gray-100 dark:border-gray-800">
                                <td className="relative px-3 py-2 text-xs text-gray-600 dark:text-gray-400 font-mono">
                                  <div className="flex items-center gap-1">
                                    <span>{key.replace("STATBOT_", "")}</span>
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
                          {!filteredExecutionKeys.length ? (
                            <tr>
                              <td colSpan={3} className="px-3 py-4 text-xs text-gray-500 dark:text-gray-400 text-center">
                                {searchTerm ? "No matches." : "No Execution settings."}
                              </td>
                            </tr>
                          ) : null}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Strategy Settings */}
                  <div>
                    <h4 className="mb-3 text-base font-semibold text-gray-900 dark:text-white/90">Strategy Settings</h4>
                    <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
                      <table className="w-full border-collapse">
                        <thead>
                          <tr className="bg-gray-50 dark:bg-gray-800">
                            <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">Key</th>
                            <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 w-32">Value</th>
                            <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400 w-16">Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filteredStrategyKeys.map((key) => {
                            const isEditing = editingEnvKeys.has(key);
                            const currentValue = envEdits[key] ?? envSettings.values?.[key] ?? "";
                            const tooltipInfo = getTooltipInfo(key);
                            return (
                              <tr key={key} className="border-t border-gray-100 dark:border-gray-800">
                                <td className="relative px-3 py-2 text-xs text-gray-600 dark:text-gray-400 font-mono">
                                  <div className="flex items-center gap-1">
                                    <span>{key.replace("STATBOT_STRATEGY_", "")}</span>
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
                          {!filteredStrategyKeys.length ? (
                            <tr>
                              <td colSpan={3} className="px-3 py-4 text-xs text-gray-500 dark:text-gray-400 text-center">
                                {searchTerm ? "No matches." : "No Strategy settings."}
                              </td>
                            </tr>
                          ) : null}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
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
