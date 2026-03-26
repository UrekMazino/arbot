"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  AdminBotStatus,
  AdminEnvSettings,
  AdminLogRun,
  AdminLogTail,
  AdminReportRun,
  RoleRecord,
  UserRecord,
  assignUserRole,
  createUser,
  getAdminBotLogTail,
  getAdminBotStatus,
  getAdminEnvSettings,
  getAdminLogRuns,
  getAdminReportRuns,
  getMe,
  isUnauthorizedError,
  listRoles,
  listUsers,
  removeUserRole,
  startAdminBot,
  stopAdminBot,
  updateAdminEnvSetting,
} from "../../../lib/api";
import { clearStoredAdminSession, getStoredAdminAccessToken, getStoredAdminEmail } from "../../../lib/auth";
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

export default function SuperAdminPage() {
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
  const [envSettings, setEnvSettings] = useState<AdminEnvSettings>({ path: "Execution/.env", values: {} });
  const [envEdits, setEnvEdits] = useState<Record<string, string>>({});
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [roles, setRoles] = useState<RoleRecord[]>([]);
  const [busy, setBusy] = useState(false);

  const [newUserEmail, setNewUserEmail] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [newUserSuper, setNewUserSuper] = useState(false);
  const [roleTargetUser, setRoleTargetUser] = useState("");
  const [roleName, setRoleName] = useState("viewer");

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
    setUsers([]);
    setRoles([]);
    if (redirectToLogin) {
      router.replace("/login?next=/admin");
    }
  }, [router]);

  const sortedEnvKeys = useMemo(
    () => Object.keys(envSettings.values || {}).sort((a, b) => a.localeCompare(b)),
    [envSettings.values],
  );
  const reportFileCount = useMemo(
    () => reportRuns.reduce((acc, row) => acc + row.file_count, 0),
    [reportRuns],
  );

  const loadAdminData = useCallback(
    async (authToken: string) => {
      const [meData, statusData, logsData, reportsData, envData, usersData, rolesData] = await Promise.all([
        getMe(authToken),
        getAdminBotStatus(authToken),
        getAdminLogRuns(authToken),
        getAdminReportRuns(authToken),
        getAdminEnvSettings(authToken),
        listUsers(authToken),
        listRoles(authToken),
      ]);
      setMe(meData);
      setBotStatus(statusData);
      setLogRuns(logsData);
      setReportRuns(reportsData);
      setEnvSettings(envData);
      setUsers(usersData);
      setRoles(rolesData);
      if (!roleTargetUser && usersData.length > 0) {
        setRoleTargetUser(usersData[0].id);
      }
      if (envData?.values) {
        setEnvEdits(envData.values);
      }
    },
    [roleTargetUser],
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
    if (!stored) {
      setAuthChecked(true);
      router.replace("/login?next=/admin");
      return;
    }
    setToken(stored);
    setStatus("Session restored");
    loadAdminData(stored)
      .then(() => refreshLogTail(stored, "latest"))
      .catch((err: unknown) => {
        if (isUnauthorizedError(err)) {
          clearAdminSession("Session expired. Please sign in again.", true);
          setError("Session expired. Please sign in again.");
          return;
        }
        const msg = err instanceof Error ? err.message : "Failed loading admin data";
        setError(msg);
      })
      .finally(() => setAuthChecked(true));
  }, [clearAdminSession, loadAdminData, refreshLogTail, router]);

  useEffect(() => {
    if (!token || !me?.is_superuser) return;
    const timer = window.setInterval(() => {
      refreshLogTail(token, selectedRunKey || "latest").catch((err: unknown) => {
        if (isUnauthorizedError(err)) {
          clearAdminSession("Session expired. Please sign in again.", true);
          setError("Session expired. Please sign in again.");
        }
      });
    }, 2000);
    return () => window.clearInterval(timer);
  }, [clearAdminSession, token, me?.is_superuser, selectedRunKey, refreshLogTail]);

  function handleLogout() {
    clearAdminSession("Signed out", true);
  }

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
      const msg = err instanceof Error ? err.message : "Refresh failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

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

  async function handleCreateUser(e: FormEvent) {
    e.preventDefault();
    if (!token || !newUserEmail || !newUserPassword) return;
    setBusy(true);
    setError("");
    try {
      await createUser(token, {
        email: newUserEmail,
        password: newUserPassword,
        is_superuser: newUserSuper,
        is_active: true,
      });
      setNewUserEmail("");
      setNewUserPassword("");
      setNewUserSuper(false);
      const nextUsers = await listUsers(token);
      setUsers(nextUsers);
      setStatus("User created");
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Create user failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function handleAssignRole(e: FormEvent) {
    e.preventDefault();
    if (!token || !roleTargetUser || !roleName) return;
    setBusy(true);
    setError("");
    try {
      await assignUserRole(token, roleTargetUser, roleName);
      const nextUsers = await listUsers(token);
      setUsers(nextUsers);
      setStatus("Role assigned");
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Assign role failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoveRole(userId: string, role: string) {
    if (!token) return;
    setBusy(true);
    setError("");
    try {
      await removeUserRole(token, userId, role);
      const nextUsers = await listUsers(token);
      setUsers(nextUsers);
      setStatus("Role removed");
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Remove role failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  const primaryButtonClasses =
    "inline-flex items-center rounded-xl bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-70";
  const secondaryButtonClasses =
    "inline-flex items-center rounded-xl border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-70 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700";
  const sectionCardClasses = "rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900";

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

  if (me && !me.is_superuser) {
    return (
      <DashboardShell
        title="Console"
        subtitle="Control bot runs, live logs, settings, users, and roles."
        status={status}
        activeHref="/admin/console"
        navItems={[
          { href: "/admin/dashboard", label: "Dashboard", hint: "Runs, quality, reports", group: "Monitor", icon: "DB" },
          { href: "/admin/console", label: "Console", hint: "Control plane", group: "Operate", icon: "CM" },
        ]}
      >
        <div className="grid gap-4">
          <section className={sectionCardClasses}>
            <h1 className="text-2xl font-semibold text-gray-900 dark:text-white/90">Console</h1>
            <p className="mt-2 text-sm text-error-600 dark:text-error-400">Current account is not superuser.</p>
          </section>
        </div>
      </DashboardShell>
    );
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
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-500">V2 Control Plane</p>
              <h1 className="mt-1 text-2xl font-semibold text-gray-900 dark:text-white/90">Console</h1>
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
        <MetricCard
          label="Users"
          value={String(users.length)}
          hint={`${users.filter((user) => user.is_superuser).length} superusers`}
          tone="teal"
        />
        <MetricCard
          label="Roles"
          value={String(roles.length)}
          hint={roles.map((role) => role.name).slice(0, 3).join(", ") || "none"}
          tone="sky"
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

        <section className={sectionCardClasses}>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white/90">Settings (.env)</h3>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Editing values here updates `Execution/.env` directly.</p>
          <TableFrame>
          <table>
            <thead>
              <tr>
                <th>Key</th>
                <th>Value</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {sortedEnvKeys.map((key) => (
                <tr key={key}>
                  <td>{key}</td>
                  <td>
                    <input
                      value={envEdits[key] ?? ""}
                      onChange={(e) =>
                        setEnvEdits((prev) => ({
                          ...prev,
                          [key]: e.target.value,
                        }))
                      }
                    />
                  </td>
                  <td>
                    <button className={secondaryButtonClasses} onClick={() => saveEnvKey(key)} disabled={busy}>
                      Save
                    </button>
                  </td>
                </tr>
              ))}
              {!sortedEnvKeys.length ? (
                <tr>
                  <td colSpan={3} className="text-sm text-gray-500 dark:text-gray-400">
                    No settings found.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
          </TableFrame>
        </section>

        <section className="grid gap-4 xl:grid-cols-2">
          <article className={sectionCardClasses}>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white/90">User Management</h3>
            <form onSubmit={handleCreateUser} className="mb-3 mt-3 flex flex-wrap items-center gap-2">
            <input value={newUserEmail} onChange={(e) => setNewUserEmail(e.target.value)} placeholder="email" required />
            <input
              value={newUserPassword}
              onChange={(e) => setNewUserPassword(e.target.value)}
              placeholder="password"
              type="password"
              required
            />
            <label className="inline-flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
              <input className="h-4 w-4 min-w-0" type="checkbox" checked={newUserSuper} onChange={(e) => setNewUserSuper(e.target.checked)} />
              superuser
            </label>
            <button type="submit" disabled={busy} className={primaryButtonClasses}>
              Create
            </button>
          </form>

          <TableFrame compact>
            <table>
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Active</th>
                  <th>Super</th>
                  <th>Roles</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td>{user.email}</td>
                    <td>{user.is_active ? "yes" : "no"}</td>
                    <td>{user.is_superuser ? "yes" : "no"}</td>
                    <td>
                      <div className="flex flex-wrap items-center gap-1.5">
                        {user.roles.map((role) => (
                          <button
                            key={`${user.id}-${role.name}`}
                            className="inline-flex items-center rounded-full border border-gray-300 bg-white px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-60 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700"
                            onClick={() => handleRemoveRole(user.id, role.name)}
                            disabled={busy}
                          >
                            {role.name} x
                          </button>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableFrame>
        </article>

        <article className={sectionCardClasses}>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white/90">Role Management</h3>
          <form onSubmit={handleAssignRole} className="mt-3 flex flex-wrap items-center gap-2">
            <select value={roleTargetUser} onChange={(e) => setRoleTargetUser(e.target.value)}>
              {users.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.email}
                </option>
              ))}
            </select>
            <select value={roleName} onChange={(e) => setRoleName(e.target.value)}>
              {roles.map((role) => (
                <option key={role.id} value={role.name}>
                  {role.name}
                </option>
              ))}
            </select>
            <button type="submit" disabled={busy} className={primaryButtonClasses}>
              Assign Role
            </button>
          </form>
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">Click role chips in User Management table to remove roles.</p>
        </article>
        </section>
      </div>
    </DashboardShell>
  );
}
