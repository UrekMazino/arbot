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
import { clearStoredAdminSession, getStoredAdminAccessToken, getStoredAdminEmail } from "../../../lib/auth";
import { UI_CLASSES } from "../../../lib/ui-classes";
import { DashboardShell } from "../../../components/dashboard-shell";
import { MetricCard, PanelCard, StatusPill, TableFrame } from "../../../components/panels";

function hasAdminRole(user: UserRecord | null): boolean {
  return Boolean(user?.roles.some((role) => role.name.toLowerCase() === "admin"));
}

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

  const [me, setMe] = useState<UserRecord | null>(null);
  const [botStatus, setBotStatus] = useState<AdminBotStatus | null>(null);
  const [logRuns, setLogRuns] = useState<AdminLogRun[]>([]);
  const [reportRuns, setReportRuns] = useState<AdminReportRun[]>([]);
  const [selectedRunKey, setSelectedRunKey] = useState("latest");
  const [logTail, setLogTail] = useState<AdminLogTail | null>(null);
  const [busy, setBusy] = useState(false);

  const clearAdminSession = useCallback((reason = "Signed out", redirectToLogin = false) => {
    clearStoredAdminSession();
    setToken("");
    setStatus(reason);
    setError("");
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
  const isAdmin = hasAdminRole(me);

  const loadAdminData = useCallback(
    async (authToken: string) => {
      const meData = await getMe(authToken);
      setMe(meData);

      if (!hasAdminRole(meData)) {
        setBotStatus(null);
        setLogRuns([]);
        setReportRuns([]);
        setLogTail(null);
        return;
      }

      const [statusData, logsData, reportsData] = await Promise.all([
        getAdminBotStatus(authToken),
        getAdminLogRuns(authToken),
        getAdminReportRuns(authToken),
      ]);
      setBotStatus(statusData);
      setLogRuns(logsData);
      setReportRuns(reportsData);
    },
    [],
  );

  const refreshLogTail = useCallback(
    async (authToken: string, runKey: string) => {
      const next = await getAdminBotLogTail(authToken, runKey || "latest", 320);
      setLogTail(next);
      if (runKey === "latest" && next?.run_key) {
        setSelectedRunKey(next.run_key);
      }
    },
    [],
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
    setStatus("Session restored");
    // Set stored email as fallback while API data loads
    if (storedEmail) {
      const fallbackMe: UserRecord = {
        id: "",
        email: storedEmail,
        is_active: false,
        roles: [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      setMe((prev) => (prev ? { ...prev, email: storedEmail } : fallbackMe));
    }
    loadAdminData(stored)
      .then(() => refreshLogTail(stored, "latest"))
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
      .finally(() => setAuthChecked(true));
  }, [clearAdminSession, loadAdminData, refreshLogTail, router]);

  useEffect(() => {
    if (!token || !isAdmin) return;
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
  }, [clearAdminSession, token, isAdmin, selectedRunKey, refreshLogTail]);

  async function handleStart() {
    if (!token) return;
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
    if (!token) return;
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
      await refreshLogTail(token, selectedRunKey || "latest");
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

  return (
    <DashboardShell
      title="Console"
      subtitle="Start/stop bot runs, monitor live terminal, and manage users and runtime settings."
      status={status}
      activeHref="/admin/console"
      navItems={[
        { href: "/admin/dashboard", label: "Dashboard", hint: "Runs, quality, reports", group: "Monitor", icon: "DB" },
        { href: "/admin/console", label: "Console", hint: "Control plane", group: "Operate", icon: "CM" },
        { href: "/admin/settings", label: "Settings", hint: "Configuration & credentials", group: "Operate", icon: "ST" },
        { href: "/admin/access", label: "Access", hint: "Users, roles, permissions", group: "Operate", icon: "UM" },
      ]}
      auth={{
        email: me?.email || (typeof window !== "undefined" ? getStoredAdminEmail() : ""),
        hasToken: Boolean(token),
      }}
    >
      <div className="grid gap-4">
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
              <button onClick={handleStart} disabled={busy || Boolean(botStatus?.running)} className={primaryButtonClasses}>
                Start Bot
              </button>
              <button className={secondaryButtonClasses} onClick={handleStop} disabled={busy || !botStatus?.running}>
                Stop Bot
              </button>
            </div>
          </div>
        </section>

        {error ? <p className="text-sm text-error-600 dark:text-error-400">{error}</p> : null}

        <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 2xl:grid-cols-6">
        <MetricCard
          label="Bot Runtime"
          value={botStatus?.running ? "RUNNING" : "STOPPED"}
          hint={botStatus?.pid ? `pid ${botStatus.pid}` : "process not active"}
          tone={botStatus?.running ? "teal" : "rose"}
        />
        <MetricCard
          label="Latest Run Key"
          value={botStatus?.latest_run_key || "n/a"}
          hint={`selected ${selectedRunKey}`}
          tone="sky"
        />
        <MetricCard
          label="Log Runs"
          value={String(logRuns.length)}
          hint={logRuns[0] ? `last update ${fmtUnix(logRuns[0].mtime_ts)}` : "no logs yet"}
          tone="amber"
        />
        <MetricCard
          label="Report Files"
          value={String(reportFileCount)}
          hint={`${reportRuns.length} report batches`}
          tone="violet"
        />
        </section>

        <section className="grid gap-4 xl:grid-cols-2">
        <PanelCard title="Bot Control" subtitle="Live process status and active run context.">
          <div className="space-y-2 text-sm text-gray-600 dark:text-gray-300">
          <p>
            <strong>Running:</strong>{" "}
            <StatusPill label={botStatus?.running ? "running" : "stopped"} tone={botStatus?.running ? "success" : "error"} />
          </p>
          <p>
            <strong>PID:</strong> {botStatus?.pid || "n/a"}
          </p>
          <p>
            <strong>Latest run:</strong> {botStatus?.latest_run_key || "n/a"}
          </p>
          <p>
            <strong>Started:</strong> {fmtDate(botStatus?.started_at || null)}
          </p>
          <p>
            <strong>Stopped:</strong> {fmtDate(botStatus?.stopped_at || null)}
          </p>
          <p>
            <strong>Detail:</strong> {botStatus?.detail || "n/a"}
          </p>
          </div>
        </PanelCard>

        <PanelCard title="Live Terminal" className="grid min-h-[460px] grid-rows-[auto_1fr]">
          <div className="mb-2 flex items-center justify-between gap-2">
            <select className="min-w-[180px]" value={selectedRunKey} onChange={(e) => setSelectedRunKey(e.target.value)}>
              <option value="latest">latest</option>
              {logRuns.map((row) => (
                <option key={row.run_key} value={row.run_key}>
                  {row.run_key}
                </option>
              ))}
            </select>
          </div>
          <pre className="custom-scrollbar mt-1 max-h-[520px] overflow-auto rounded-xl border border-gray-700 bg-gray-950 p-3 text-xs leading-relaxed text-emerald-100">
            {(logTail?.lines || []).join("\n") || "No log lines yet."}
          </pre>
        </PanelCard>
        </section>

        <section className="grid gap-4 xl:grid-cols-2">
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
