"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  AdminBotStatus,
  AdminLogTail,
  AdminLogRun,
  AdminReportRun,
  UserRecord,
  getAdminBotLogTail,
  getAdminBotStatus,
  getAdminLogRuns,
  getAdminReportRuns,
  getMe,
  isUnauthorizedError,
  isForbiddenError,
  startAdminBot,
  stopAdminBot,
} from "../../../lib/api";
import {
  canAccessAdminPath,
  getAdminNavItems,
  getFirstAccessibleAdminPath,
  hasPermission,
} from "../../../lib/admin-access";
import { clearStoredAdminSession, getStoredAdminEmail } from "../../../lib/auth";
import { UI_CLASSES } from "../../../lib/ui-classes";
import { useFloatingTerminal } from "../../../context/floating-terminal-context";
import { DashboardShell } from "../../../components/dashboard-shell";
import { PanelCard, StatusPill, TableFrame } from "../../../components/panels";

function fmtDate(value: string | null | undefined): string {
  if (!value) return "n/a";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return "n/a";
  return dt.toLocaleString();
}

function fmtBytes(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(2)} MB`;
}

function fmtUnix(value: number | null | undefined): string {
  if (!value || Number.isNaN(value)) return "n/a";
  return new Date(value * 1000).toLocaleString();
}

export default function AdminConsolePage() {
  const router = useRouter();
  const { isFloating, setFloating, logTail: sharedLogTail, setLogTail: setSharedLogTail } = useFloatingTerminal();
  const [status, setStatus] = useState("Signed out");
  const [error, setError] = useState("");
  const [authChecked, setAuthChecked] = useState(false);
  const [profileResolved, setProfileResolved] = useState(false);
  const [activeTab, setActiveTab] = useState<"control" | "logs">("control");

  const [me, setMe] = useState<UserRecord | null>(null);
  const [botStatus, setBotStatus] = useState<AdminBotStatus | null>(null);
  const [logRuns, setLogRuns] = useState<AdminLogRun[]>([]);
  const [reportRuns, setReportRuns] = useState<AdminReportRun[]>([]);
  const [selectedRunKey, setSelectedRunKey] = useState("latest");
  const [localLogTail, setLocalLogTail] = useState<AdminLogTail | null>(null);
  const [busy, setBusy] = useState(false);
  const [terminalFullscreen, setTerminalFullscreen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const [waitingForRun, setWaitingForRun] = useState(false);
  const [lastKnownRunKey, setLastKnownRunKey] = useState<string | null>(null);

  const clearAdminSession = useCallback((reason = "Signed out", redirectToLogin = false) => {
    clearStoredAdminSession();
    setStatus(reason);
    setError("");
    setProfileResolved(false);
    setMe(null);
    setBotStatus(null);
    setLogRuns([]);
    setReportRuns([]);
    setLocalLogTail(null);
    if (isFloating) setSharedLogTail(null);
    setFloating(false);
    if (redirectToLogin) {
      router.replace("/login?next=/admin/console");
    }
  }, [router, setFloating]);

  const reportFileCount = useMemo(
    () => reportRuns.reduce((acc, row) => acc + row.file_count, 0),
    [reportRuns],
  );
  const navItems = useMemo(() => getAdminNavItems(me), [me]);
  const fallbackHref = useMemo(() => getFirstAccessibleAdminPath(me), [me]);
  const canViewLogs = hasPermission(me, "view_logs");
  const canManageBot = hasPermission(me, "manage_bot");
  const canViewConsole = canAccessAdminPath(me, "/admin/console");
  // Use shared logTail from context when floating, otherwise use local state
  const displayLogTail = isFloating ? sharedLogTail : localLogTail;
  const showingControlLog = displayLogTail?.run_key === "__control__";

  const loadAdminData = useCallback(async () => {
      const meData = await getMe();
      setMe(meData);

      if (!canAccessAdminPath(meData, "/admin/console")) {
        setBotStatus(null);
        setLogRuns([]);
        setReportRuns([]);
        setLocalLogTail(null);
        return;
      }

      const canLoadStatus = hasPermission(meData, "manage_bot") || hasPermission(meData, "view_logs");
      const canLoadLogs = hasPermission(meData, "view_logs");
      const canLoadReports = hasPermission(meData, "view_reports");

      // First load status and log runs to determine which run to load
      const [statusData, logsData, reportsData] = await Promise.all([
        canLoadStatus ? getAdminBotStatus() : Promise.resolve(null),
        canLoadLogs ? getAdminLogRuns() : Promise.resolve([] as AdminLogRun[]),
        canLoadReports ? getAdminReportRuns() : Promise.resolve([] as AdminReportRun[]),
      ]);

      setBotStatus(statusData);
      setLogRuns(logsData);
      setReportRuns(reportsData);

      // Determine which run key to load:
      // 1. If bot is running, use the latest_run_key from status
      // 2. Otherwise use the first log run (latest)
      // 3. If no runs, show control log
      let runKeyToLoad = "latest";
      if (statusData?.running && statusData?.latest_run_key) {
        runKeyToLoad = statusData.latest_run_key;
      } else if (logsData.length > 0) {
        runKeyToLoad = logsData[0].run_key;
      }

      // Load the log tail for the determined run key
      if (canLoadLogs) {
        const displayLogTailData = await getAdminBotLogTail(runKeyToLoad, 320);
        setLocalLogTail(displayLogTailData);
        if (displayLogTailData?.run_key && displayLogTailData.run_key !== "__control__") {
          setSelectedRunKey(displayLogTailData.run_key);
        } else {
          setSelectedRunKey(runKeyToLoad);
        }
      }
    },
    [],
  );

  const refreshLogTail = useCallback(
    async (runKey: string) => {
      if (!canViewLogs) {
        setLocalLogTail(null);
        if (isFloating) setSharedLogTail(null);
        return;
      }
      const next = await getAdminBotLogTail(runKey || "latest", 320);
      setLocalLogTail(next);
      // Also update shared context when floating
      if (isFloating) setSharedLogTail(next);

      // Check if a new run was created (when waiting for run)
      if (waitingForRun && next?.run_key && next.run_key !== "__control__") {
        const newRunKey = next.run_key;
        // If we have a last known run key and it's different, a new run was created
        if (lastKnownRunKey && newRunKey !== lastKnownRunKey) {
          setWaitingForRun(false);
          setLastKnownRunKey(null);
          setSelectedRunKey(newRunKey);
        } else if (!lastKnownRunKey) {
          // No previous run key, so this is a new run
          setWaitingForRun(false);
          setLastKnownRunKey(null);
          setSelectedRunKey(newRunKey);
        }
      }

      if (runKey === "latest" && next?.run_key && next.run_key !== "__control__") {
        setSelectedRunKey(next.run_key);
      } else if (runKey === "latest") {
        setSelectedRunKey("latest");
      }
    },
    [canViewLogs, waitingForRun, lastKnownRunKey],
  );

  // Effect to poll for new run when bot is starting
  useEffect(() => {
    if (!waitingForRun || !canViewLogs || !lastKnownRunKey) return;

    const timer = window.setInterval(async () => {
      // Fetch the log runs to check if a new one exists
      const runs = await getAdminLogRuns();
      setLogRuns(runs);

      // Check if there's a new run that's different from what we had
      if (runs.length > 0) {
        const latestRunKey = runs[0]?.run_key;
        if (latestRunKey && latestRunKey !== lastKnownRunKey && latestRunKey !== "__control__") {
          // New run detected! Fetch its log tail
          const tail = await getAdminBotLogTail(latestRunKey, 320);
          setLocalLogTail(tail);
          // Also update the bot status to get latest_run_key updated
          const statusData = await getAdminBotStatus();
          setBotStatus(statusData);
          setSelectedRunKey(latestRunKey);
          setWaitingForRun(false);
          setLastKnownRunKey(null);
        }
      }
    }, 2000);

    return () => window.clearInterval(timer);
  }, [waitingForRun, canViewLogs, lastKnownRunKey]);

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

    setStatus("Loading console...");
    setAuthChecked(true);
    setProfileResolved(false);
    loadAdminData()
      .then(() => {
        setStatus("Session restored");
      })
      .catch((err: unknown) => {
        if (isUnauthorizedError(err)) {
          clearAdminSession("Session expired. Please sign in again.", true);
          setError("Session expired. Please sign in again.");
          return;
        }
        if (isForbiddenError(err)) {
          setError("Insufficient permissions. Contact an admin.");
          return;
        }
        const msg = err instanceof Error ? err.message : "Failed loading admin data";
        setError(msg);
      })
      .finally(() => setProfileResolved(true));
  }, [clearAdminSession, loadAdminData, router]);

  useEffect(() => {
    if (!profileResolved || !me || canViewConsole) {
      return;
    }
    setBotStatus(null);
    setLogRuns([]);
    setReportRuns([]);
    setLocalLogTail(null);
    if (fallbackHref && fallbackHref !== "/admin/console") {
      setStatus("Redirecting");
      setError("Console access is not enabled for your account.");
      router.replace(fallbackHref);
    }
  }, [canViewConsole, fallbackHref, me, profileResolved, router]);

  useEffect(() => {
    // Only poll when floating terminal is NOT active (floating terminal handles its own polling)
    if (!canViewConsole || !canViewLogs || isFloating) return;
    const timer = window.setInterval(() => {
      refreshLogTail(selectedRunKey || "latest").catch((err: unknown) => {
        if (isUnauthorizedError(err)) {
          clearAdminSession("Session expired. Please sign in again.", true);
          setError("Session expired. Please sign in again.");
          return;
        }
        if (isForbiddenError(err)) {
          setError("Insufficient permissions to read log tail.");
        }
      });
    }, 2000);
    return () => window.clearInterval(timer);
  }, [canViewConsole, canViewLogs, clearAdminSession, selectedRunKey, refreshLogTail, isFloating]);

  async function handleStart() {
    if (!me || !canManageBot) return;
    setBusy(true);
    setError("");
    try {
      // Record current latest run key before starting
      setLastKnownRunKey(botStatus?.latest_run_key || null);
      setWaitingForRun(true);
      const next = await startAdminBot();
      setBotStatus(next);
      setStatus("Bot start requested");
    } catch (err) {
      setWaitingForRun(false);
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      if (isForbiddenError(err)) {
        setError("Insufficient permissions to start the bot.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Start failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function handleStop() {
    if (!me || !canManageBot) return;
    setBusy(true);
    setError("");
    try {
      const next = await stopAdminBot();
      setBotStatus(next);
      setStatus("Bot stop requested");
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      if (isForbiddenError(err)) {
        setError("Insufficient permissions to stop the bot.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Stop failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function handleRefreshAll() {
    if (!me) return;
    setBusy(true);
    setError("");
    try {
      await loadAdminData();
      if (canViewLogs) {
        await refreshLogTail(selectedRunKey || "latest");
      }
      setStatus("Refreshed");
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      if (isForbiddenError(err)) {
        setError("Insufficient permissions to refresh admin console.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Refresh failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  const sectionCardClasses = UI_CLASSES.sectionCard;
  const primaryButtonClasses = UI_CLASSES.primaryButton;

  const tabButtonClass = (isActive: boolean) =>
    `px-4 py-2 font-medium text-sm ${
      isActive
        ? "border-b-2 border-brand-500 text-brand-600 dark:text-brand-400"
        : "border-b-2 border-transparent text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-300"
    }`;

  if (!authChecked) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900">
        <p className="text-sm text-gray-500 dark:text-gray-400">Checking admin session...</p>
      </div>
    );
  }

  if (profileResolved && me && !canViewConsole && !fallbackHref) {
    return (
      <DashboardShell
        title="Console"
        subtitle="Start/stop bot runs, monitor live terminal, and manage users and runtime settings."
        status="Access restricted"
        activeHref="/admin/console"
        navItems={navItems}
        auth={{
          email: me.email || (typeof window !== "undefined" ? getStoredAdminEmail() : ""),
          hasToken: Boolean(me),
        }}
      >
        <section className={sectionCardClasses}>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-white/90">Console</h1>
          <p className="mt-2 text-sm text-error-600 dark:text-error-400">Console permissions are not enabled for this account.</p>
        </section>
      </DashboardShell>
    );
  }

  return (
    <DashboardShell
      title="Console"
      subtitle="Start/stop bot runs, monitor live terminal, and manage users and runtime settings."
      status={status}
      activeHref="/admin/console"
      navItems={navItems}
      auth={{
        email: me?.email || (typeof window !== "undefined" ? getStoredAdminEmail() : ""),
        hasToken: Boolean(me),
      }}
    >
      <div className="grid gap-2">
        <section className={sectionCardClasses}>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-500">Console</p>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{status}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button onClick={handleRefreshAll} disabled={busy} className={primaryButtonClasses}>
                Refresh
              </button>
            </div>
          </div>
        </section>

        {error ? <p className="text-sm text-error-600 dark:text-error-400">{error}</p> : null}

        {/* Tabs */}
        <div className="flex flex-wrap gap-8 border-b border-gray-200 dark:border-gray-700">
          <button
            onClick={() => setActiveTab("control")}
            className={tabButtonClass(activeTab === "control")}
          >
            Control Panel
          </button>
          <button
            onClick={() => setActiveTab("logs")}
            className={tabButtonClass(activeTab === "logs")}
          >
            Logs & Reports
          </button>
        </div>

        {activeTab === "control" && (
          <>
            {/* Terminal and Bot Control side by side */}
            <section className="grid gap-2 lg:grid-cols-2">
              {/* Terminal - Left side */}
              <PanelCard
                title="Terminal"
                actions={
                  <div className="flex gap-2">
                    <button
                      onClick={() => setFloating(!isFloating)}
                      className="rounded border border-gray-300 bg-white px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
                    >
                      {isFloating ? "⬜ Dock" : "⬛ Float"}
                    </button>
                    <button
                      onClick={() => setTerminalFullscreen(true)}
                      className="rounded border border-gray-300 bg-white px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
                    >
                      ⛶ Fullscreen
                    </button>
                  </div>
                }
              >
                {waitingForRun ? (
                  <p className="mb-2 text-xs text-amber-600 dark:text-amber-400">
                    Waiting for new run to start...
                  </p>
                ) : showingControlLog ? (
                  <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
                    Showing current startup/control output until a fresh run log is created.
                  </p>
                ) : null}
                <pre className="custom-scrollbar mt-2 h-[520px] overflow-auto rounded-xl border border-gray-700 bg-gray-950 p-3 text-xs leading-relaxed text-emerald-100">
                  {(displayLogTail?.lines || []).join("\n") || "No log lines yet."}
                </pre>
              </PanelCard>

              {/* Bot Control - Right side */}
              <PanelCard
                title="Bot Control"
                subtitle="Process status and run context."
                actions={
                  canManageBot ? (
                    <div className="flex gap-2">
                      <button
                        onClick={handleStart}
                        disabled={busy || Boolean(botStatus?.running)}
                        className={primaryButtonClasses}
                      >
                        Start Bot
                      </button>
                      <button
                        className="inline-flex items-center rounded-xl border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
                        onClick={handleStop}
                        disabled={busy || !botStatus?.running}
                      >
                        Stop Bot
                      </button>
                    </div>
                  ) : null
                }
              >
                <div className="grid grid-cols-2 gap-x-6 gap-y-4">
                  <div className="border-b border-gray-200 pb-3 dark:border-gray-700">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Status</p>
                    <div className="mt-1.5"><StatusPill label={botStatus?.running ? "running" : "stopped"} tone={botStatus?.running ? "success" : "error"} /></div>
                  </div>
                  <div className="border-b border-gray-200 pb-3 dark:border-gray-700">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">PID</p>
                    <p className="mt-1.5 font-mono text-sm text-gray-900 dark:text-white/90">{botStatus?.pid || "n/a"}</p>
                  </div>
                  <div className="border-b border-gray-200 pb-3 dark:border-gray-700">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Latest Run</p>
                    <p className="mt-1.5 truncate font-mono text-sm text-gray-900 dark:text-white/90">{botStatus?.latest_run_key || "n/a"}</p>
                  </div>
                  <div className="border-b border-gray-200 pb-3 dark:border-gray-700">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Detail</p>
                    <p className="mt-1.5 font-mono text-sm text-gray-900 dark:text-white/90">{botStatus?.detail || "n/a"}</p>
                  </div>
                  <div className="pt-1">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Started</p>
                    <p className="mt-1.5 font-mono text-xs text-gray-600 dark:text-gray-400">{fmtDate(botStatus?.started_at || null)}</p>
                  </div>
                  <div className="pt-1">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Stopped</p>
                    <p className="mt-1.5 font-mono text-xs text-gray-600 dark:text-gray-400">{fmtDate(botStatus?.stopped_at || null)}</p>
                  </div>
                  <div className="col-span-2">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Select Run</p>
                    <select className="mt-1.5 w-full min-w-[180px] rounded border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white/90" value={selectedRunKey} onChange={(e) => setSelectedRunKey(e.target.value)}>
                      <option value="latest">latest</option>
                      {logRuns.map((row) => (
                        <option key={row.run_key} value={row.run_key}>
                          {row.run_key}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </PanelCard>
            </section>

            {/* Fullscreen Terminal Modal - simplified without drag */}
            {terminalFullscreen ? (
          <div
            className="fixed inset-0 z-50 flex flex-col bg-gray-900"
          >
            <div
              className="flex items-center justify-between border-b border-gray-700 bg-gray-800 px-4 py-3"
            >
              <h3 className="text-lg font-semibold text-white">Terminal</h3>
              <button
                onClick={() => setTerminalFullscreen(false)}
                className="rounded px-3 py-1 text-sm font-medium text-gray-300 hover:bg-gray-700"
              >
                Exit Fullscreen
              </button>
            </div>
            <div className="flex flex-1 flex-col overflow-hidden p-4">
              {waitingForRun ? (
                <p className="mb-2 text-xs text-amber-400">
                  Waiting for new run to start...
                </p>
              ) : showingControlLog ? (
                <p className="mb-2 text-xs text-gray-400">
                  Showing current startup/control output until a fresh run log is created.
                </p>
              ) : null}
              <pre className="custom-scrollbar flex-1 overflow-auto rounded-xl border border-gray-700 bg-gray-950 p-3 text-xs leading-relaxed text-emerald-100">
                {(displayLogTail?.lines || []).join("\n") || "No log lines yet."}
              </pre>
            </div>
          </div>
        ) : null}
        </>
        )}

        {activeTab === "logs" && (
          <section className="grid gap-2 xl:grid-cols-2">
            <PanelCard title="All Logs">
              <TableFrame compact>
                <table>
                  <thead>
                    <tr>
                      <th>Run</th>
                      <th>Size</th>
                      <th>Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logRuns.map((row) => (
                      <tr key={row.run_key}>
                        <td>{row.run_key}</td>
                        <td>{fmtBytes(row.size_bytes)}</td>
                        <td>{fmtUnix(row.mtime_ts)}</td>
                      </tr>
                    ))}
                    {!logRuns.length ? (
                      <tr>
                        <td colSpan={3} className="text-sm text-gray-500 dark:text-gray-400">
                          No log runs found.
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </TableFrame>
            </PanelCard>

            <PanelCard title="All Reports">
              <TableFrame compact>
                <table>
                  <thead>
                    <tr>
                      <th>Run</th>
                      <th>Files</th>
                      <th>Summary</th>
                      <th>Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reportRuns.map((row) => (
                      <tr key={row.run_key}>
                        <td>{row.run_key}</td>
                        <td>{row.file_count}</td>
                        <td>
                          <StatusPill label={row.summary_json ? "available" : "missing"} tone={row.summary_json ? "success" : "warn"} />
                        </td>
                        <td>{fmtUnix(row.mtime_ts)}</td>
                      </tr>
                    ))}
                    {!reportRuns.length ? (
                      <tr>
                        <td colSpan={4} className="text-sm text-gray-500 dark:text-gray-400">
                          No report runs found.
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </TableFrame>
            </PanelCard>
          </section>
        )}
      </div>
    </DashboardShell>
  );
}
