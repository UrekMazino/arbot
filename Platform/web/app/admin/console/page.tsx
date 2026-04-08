"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  AdminBotStatus,
  AdminLogRun,
  AdminLogTail,
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
import { clearStoredAdminSession, getStoredAdminAccessToken, getStoredAdminEmail } from "../../../lib/auth";
import { UI_CLASSES } from "../../../lib/ui-classes";
import { DashboardShell } from "../../../components/dashboard-shell";
import { MetricCard, PanelCard, StatusPill, TableFrame } from "../../../components/panels";

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
  const [token, setToken] = useState<string>("");
  const [status, setStatus] = useState("Signed out");
  const [error, setError] = useState("");
  const [authChecked, setAuthChecked] = useState(false);
  const [profileResolved, setProfileResolved] = useState(false);

  const [me, setMe] = useState<UserRecord | null>(null);
  const [botStatus, setBotStatus] = useState<AdminBotStatus | null>(null);
  const [logRuns, setLogRuns] = useState<AdminLogRun[]>([]);
  const [reportRuns, setReportRuns] = useState<AdminReportRun[]>([]);
  const [selectedRunKey, setSelectedRunKey] = useState("latest");
  const [logTail, setLogTail] = useState<AdminLogTail | null>(null);
  const [busy, setBusy] = useState(false);
  const [terminalFullscreen, setTerminalFullscreen] = useState(false);
  const [terminalPosition, setTerminalPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });

  const clearAdminSession = useCallback((reason = "Signed out", redirectToLogin = false) => {
    clearStoredAdminSession();
    setToken("");
    setStatus(reason);
    setError("");
    setProfileResolved(false);
    setMe(null);
    setBotStatus(null);
    setLogRuns([]);
    setReportRuns([]);
    setLogTail(null);
    if (redirectToLogin) {
      router.replace("/login?next=/admin/console");
    }
  }, [router]);

  const reportFileCount = useMemo(
    () => reportRuns.reduce((acc, row) => acc + row.file_count, 0),
    [reportRuns],
  );
  const navItems = useMemo(() => getAdminNavItems(me), [me]);
  const fallbackHref = useMemo(() => getFirstAccessibleAdminPath(me), [me]);
  const canViewLogs = hasPermission(me, "view_logs");
  const canManageBot = hasPermission(me, "manage_bot");
  const canViewReports = hasPermission(me, "view_reports");
  const canViewConsole = canAccessAdminPath(me, "/admin/console");
  const showingControlLog = logTail?.run_key === "__control__";

  const loadAdminData = useCallback(
    async (authToken: string) => {
      const meData = await getMe(authToken);
      setMe(meData);

      if (!canAccessAdminPath(meData, "/admin/console")) {
        setBotStatus(null);
        setLogRuns([]);
        setReportRuns([]);
        setLogTail(null);
        return;
      }

      const canLoadStatus = hasPermission(meData, "manage_bot") || hasPermission(meData, "view_logs");
      const canLoadLogs = hasPermission(meData, "view_logs");
      const canLoadReports = hasPermission(meData, "view_reports");
      const [statusData, logsData, reportsData, logTailData] = await Promise.all([
        canLoadStatus ? getAdminBotStatus(authToken) : Promise.resolve(null),
        canLoadLogs ? getAdminLogRuns(authToken) : Promise.resolve([] as AdminLogRun[]),
        canLoadReports ? getAdminReportRuns(authToken) : Promise.resolve([] as AdminReportRun[]),
        canLoadLogs ? getAdminBotLogTail(authToken, "latest", 320) : Promise.resolve(null),
      ]);
      setBotStatus(statusData);
      setLogRuns(logsData);
      setReportRuns(reportsData);
      setLogTail(logTailData);
      if (logTailData?.run_key && logTailData.run_key !== "__control__") {
        setSelectedRunKey(logTailData.run_key);
      } else {
        setSelectedRunKey("latest");
      }
    },
    [],
  );

  const refreshLogTail = useCallback(
    async (authToken: string, runKey: string) => {
      if (!canViewLogs) {
        setLogTail(null);
        return;
      }
      const next = await getAdminBotLogTail(authToken, runKey || "latest", 320);
      setLogTail(next);
      if (runKey === "latest" && next?.run_key && next.run_key !== "__control__") {
        setSelectedRunKey(next.run_key);
      } else if (runKey === "latest") {
        setSelectedRunKey("latest");
      }
    },
    [canViewLogs],
  );

  useEffect(() => {
    const stored = getStoredAdminAccessToken();
    const storedEmail = getStoredAdminEmail();
    if (!stored) {
      setAuthChecked(true);
      router.replace("/login?next=/admin/console");
      return;
    }
    setToken(stored);
    setStatus("Loading console...");
    setAuthChecked(true);
    setProfileResolved(false);
    // Set stored email as fallback while API data loads
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
    loadAdminData(stored)
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
    setLogTail(null);
    if (fallbackHref && fallbackHref !== "/admin/console") {
      setStatus("Redirecting");
      setError("Console access is not enabled for your account.");
      router.replace(fallbackHref);
    }
  }, [canViewConsole, fallbackHref, me, profileResolved, router]);

  useEffect(() => {
    if (!token || !canViewConsole || !canViewLogs) return;
    const timer = window.setInterval(() => {
      refreshLogTail(token, selectedRunKey || "latest").catch((err: unknown) => {
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
  }, [canViewConsole, canViewLogs, clearAdminSession, token, selectedRunKey, refreshLogTail]);

  async function handleStart() {
    if (!token || !canManageBot) return;
    setBusy(true);
    setError("");
    try {
      const next = await startAdminBot(token);
      setBotStatus(next);
      setStatus("Bot start requested");
    } catch (err) {
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
    if (!token || !canManageBot) return;
    setBusy(true);
    setError("");
    try {
      const next = await stopAdminBot(token);
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
    if (!token) return;
    setBusy(true);
    setError("");
    try {
      await loadAdminData(token);
      if (canViewLogs) {
        await refreshLogTail(token, selectedRunKey || "latest");
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
  const secondaryButtonClasses = UI_CLASSES.secondaryButton;

  const handleTerminalDragStart = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('[data-no-drag]')) return;
    setIsDragging(true);
    setDragOffset({
      x: e.clientX - terminalPosition.x,
      y: e.clientY - terminalPosition.y,
    });
  };

  const handleTerminalDragMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    setTerminalPosition({
      x: e.clientX - dragOffset.x,
      y: e.clientY - dragOffset.y,
    });
  };

  const handleTerminalDragEnd = () => {
    setIsDragging(false);
  };

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
          hasToken: Boolean(token),
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
        hasToken: Boolean(token),
      }}
    >
      <div className="grid gap-2">
        <section className={sectionCardClasses}>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-500">Control Panel</p>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{status}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button onClick={handleRefreshAll} disabled={busy} className={primaryButtonClasses}>
                Refresh
              </button>
              {canManageBot ? (
                <>
                  <button onClick={handleStart} disabled={busy || Boolean(botStatus?.running)} className={primaryButtonClasses}>
                    Start Bot
                  </button>
                  <button className="inline-flex items-center rounded-xl border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700" onClick={handleStop} disabled={busy || !botStatus?.running}>
                    Stop Bot
                  </button>
                </>
              ) : null}
            </div>
          </div>
        </section>

        {error ? <p className="text-sm text-error-600 dark:text-error-400">{error}</p> : null}

        <section className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Bot Runtime"
          value={botStatus?.running ? "RUNNING" : "STOPPED"}
          hint={botStatus?.pid ? `PID ${botStatus.pid}` : "process not active"}
          tone={botStatus?.running ? "teal" : "rose"}
        />
        <MetricCard
          label="Latest Run Key"
          value={showingControlLog ? "CONTROL LOG" : botStatus?.latest_run_key || "n/a"}
          hint={showingControlLog ? "Startup / Control Output" : `selected ${selectedRunKey}`}
          tone="sky"
        />
        <MetricCard
          label="Log Runs"
          value={String(logRuns.length)}
          hint={logRuns[0] ? `Last Update ${fmtUnix(logRuns[0].mtime_ts)}` : "no logs yet"}
          tone="amber"
        />
        <MetricCard
          label="Report Files"
          value={String(reportFileCount)}
          hint={`${reportRuns.length} Report Batches`}
          tone="violet"
        />
        </section>

        <section className="grid gap-2">
        <PanelCard title="Bot Control" subtitle="Live process status and active run context.">
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
          </div>
        </PanelCard>

        {terminalFullscreen ? (
          <div
            className="fixed inset-0 z-50 flex flex-col bg-gray-900"
            onMouseMove={handleTerminalDragMove}
            onMouseUp={handleTerminalDragEnd}
            onMouseLeave={handleTerminalDragEnd}
          >
            <div
              className="flex items-center justify-between border-b border-gray-700 bg-gray-800 px-4 py-3 cursor-move"
              onMouseDown={handleTerminalDragStart}
              data-no-drag="false"
            >
              <h3 className="text-lg font-semibold text-white">Live Terminal</h3>
              <button
                onClick={() => setTerminalFullscreen(false)}
                className="rounded px-3 py-1 text-sm font-medium text-gray-300 hover:bg-gray-700"
                data-no-drag="true"
              >
                Exit Fullscreen
              </button>
            </div>
            <div className="flex flex-1 flex-col overflow-hidden p-4">
              <div className="mb-3 flex items-center justify-between gap-2" data-no-drag="true">
                <select className="min-w-[180px] rounded border border-gray-600 bg-gray-700 px-2 py-1 text-sm text-white" value={selectedRunKey} onChange={(e) => setSelectedRunKey(e.target.value)}>
                  <option value="latest">latest</option>
                  {logRuns.map((row) => (
                    <option key={row.run_key} value={row.run_key}>
                      {row.run_key}
                    </option>
                  ))}
                </select>
              </div>
              {showingControlLog ? (
                <p className="mb-2 text-xs text-gray-400">
                  Showing current startup/control output until a fresh run log is created.
                </p>
              ) : null}
              <pre className="custom-scrollbar flex-1 overflow-auto rounded-xl border border-gray-700 bg-gray-950 p-3 text-xs leading-relaxed text-emerald-100">
                {(logTail?.lines || []).join("\n") || "No log lines yet."}
              </pre>
            </div>
          </div>
        ) : null}
        <PanelCard title="Live Terminal" className="grid min-h-[560px] grid-rows-[auto_1fr]">
          <div className="mb-2 flex items-center justify-between gap-2">
            <select className="min-w-[180px]" value={selectedRunKey} onChange={(e) => setSelectedRunKey(e.target.value)}>
              <option value="latest">latest</option>
              {logRuns.map((row) => (
                <option key={row.run_key} value={row.run_key}>
                  {row.run_key}
                </option>
              ))}
            </select>
            <button
              onClick={() => setTerminalFullscreen(true)}
              className="rounded border border-gray-300 bg-white px-3 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
            >
              ⛶ Fullscreen
            </button>
          </div>
          {showingControlLog ? (
            <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
              Showing current startup/control output until a fresh run log is created.
            </p>
          ) : null}
          <pre className="custom-scrollbar mt-1 max-h-[620px] overflow-auto rounded-xl border border-gray-700 bg-gray-950 p-3 text-xs leading-relaxed text-emerald-100">
            {(logTail?.lines || []).join("\n") || "No log lines yet."}
          </pre>
        </PanelCard>
        </section>

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
      </div>
    </DashboardShell>
  );
}
