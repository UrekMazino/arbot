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
import { clearStoredAdminSession, getStoredAdminAccessToken, getStoredAdminEmail } from "../../../lib/auth";
import { UI_CLASSES } from "../../../lib/ui-classes";
import { DashboardShell } from "../../../components/dashboard-shell";

type TabType = "bot" | "api";

export default function SettingsPage() {
  const router = useRouter();
  const [token, setToken] = useState<string>("");
  const [status, setStatus] = useState("Signed out");
  const [error, setError] = useState("");
  const [authChecked, setAuthChecked] = useState(false);
  const [activeTab, setActiveTab] = useState<TabType>("bot");
  const [me, setMe] = useState<UserRecord | null>(null);

  const [envSettings, setEnvSettings] = useState<AdminEnvSettings>({ path: "Execution/.env", values: {} });
  const [envEdits, setEnvEdits] = useState<Record<string, string>>({});
  const [editingEnvKeys, setEditingEnvKeys] = useState<Set<string>>(new Set());
  const [showPasswordKeys, setShowPasswordKeys] = useState<Set<string>>(new Set());
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const navItems = useMemo(() => getAdminNavItems(me), [me]);
  const fallbackHref = useMemo(() => getFirstAccessibleAdminPath(me), [me]);
  const canEditSettings = hasPermission(me, "edit_settings");
  const canManageApi = hasPermission(me, "manage_api");
  const canViewSettings = canAccessAdminPath(me, "/admin/settings");

  const clearAdminSession = useCallback((reason = "Signed out", redirectToLogin = false) => {
    clearStoredAdminSession();
    setToken("");
    setStatus(reason);
    setError("");
    if (redirectToLogin) {
      router.replace("/login?next=/admin/settings");
    }
  }, [router]);

  const loadEnvSettings = useCallback(async (authToken: string) => {
    const envData = await getAdminEnvSettings(authToken);
    setEnvSettings(envData);
    if (envData?.values) {
      setEnvEdits(envData.values);
    }
  }, []);

  useEffect(() => {
    const stored = getStoredAdminAccessToken();
    if (!stored) {
      setAuthChecked(true);
      router.replace("/login?next=/admin/settings");
      return;
    }
    setToken(stored);
    setStatus("Session restored");
    getMe(stored)
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
        await loadEnvSettings(stored);
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
      .finally(() => setAuthChecked(true));
  }, [clearAdminSession, loadEnvSettings, router]);

  useEffect(() => {
    if (!me || canViewSettings) {
      return;
    }
    setEnvSettings({ path: "Execution/.env", values: {} });
    setEnvEdits({});
    if (fallbackHref && fallbackHref !== "/admin/settings") {
      setStatus("Redirecting");
      setError("Settings access is not enabled for your account.");
      router.replace(fallbackHref);
    }
  }, [canViewSettings, fallbackHref, me, router]);

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

  const apiKeys = useMemo(
    () => new Set(["OKX_API_KEY", "OKX_API_SECRET", "OKX_FLAG", "OKX_PASSPHRASE"]),
    [],
  );

  const sortedEnvKeys = useMemo(
    () => Object.keys(envSettings.values || {}).sort((a, b) => a.localeCompare(b)),
    [envSettings.values],
  );

  const botEnvKeys = useMemo(
    () => sortedEnvKeys.filter((key) => !apiKeys.has(key)),
    [sortedEnvKeys, apiKeys],
  );

  const apiEnvKeys = useMemo(
    () => sortedEnvKeys.filter((key) => apiKeys.has(key)),
    [sortedEnvKeys, apiKeys],
  );

  const filteredKeys = useMemo(() => {
    const sourceKeys = activeTab === "bot" ? botEnvKeys : apiEnvKeys;
    return sourceKeys.filter((key) => key.toLowerCase().includes(searchTerm.toLowerCase()));
  }, [botEnvKeys, apiEnvKeys, activeTab, searchTerm]);

  async function saveEnvKey(key: string) {
    if (!token) return;
    const value = envEdits[key] ?? "";
    setBusy(true);
    setError("");
    try {
      const next = await updateAdminEnvSetting(token, key, value);
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

  if (!token) {
    return null;
  }

  if (me && !canViewSettings && !fallbackHref) {
    return (
      <DashboardShell
        title="Settings"
        subtitle="Configure environment variables and API credentials."
        status="Access restricted"
        activeHref="/admin/settings"
        navItems={navItems}
        auth={{
          email: me.email || (typeof window !== "undefined" ? getStoredAdminEmail() : ""),
          hasToken: Boolean(token),
        }}
      >
        <section className={sectionCardClasses}>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-white/90">Settings</h1>
          <p className="mt-2 text-sm text-error-600 dark:text-error-400">Settings permissions are not enabled for this account.</p>
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
        hasToken: Boolean(token),
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

        <section className={sectionCardClasses}>
          <div className="border-b border-gray-200 dark:border-gray-700">
            <div className="flex gap-8">
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
          </div>

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
                                  className="w-full h-8 rounded border border-gray-300 px-2 py-1 text-sm text-gray-900 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-600 dark:bg-gray-700 dark:text-white dark:placeholder-gray-400"
                                />
                              ) : (
                                <span className="text-gray-700 dark:text-gray-300">{currentValue || "(empty)"}</span>
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
                                <button
                                  className={secondaryButtonClasses}
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
                      {!filteredKeys.length ? (
                        <tr>
                          <td colSpan={3} className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">
                            {searchTerm ? "No settings match your search." : "No settings found."}
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
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
