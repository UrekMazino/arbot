"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

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
  login,
  removeUserRole,
  startAdminBot,
  stopAdminBot,
  updateAdminEnvSetting,
} from "../../lib/api";
import { DashboardShell } from "../../components/dashboard-shell";
import { MetricCard, PanelCard, StatusPill, TableFrame } from "../../components/panels";

const ADMIN_ACCESS_TOKEN_KEY = "v2_admin_access_token";
const ADMIN_REFRESH_TOKEN_KEY = "v2_admin_refresh_token";

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

function statusTone(value: string | null | undefined): "success" | "warn" | "error" | "info" {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) return "info";
  if (
    normalized.includes("running") ||
    normalized.includes("pass") ||
    normalized.includes("active") ||
    normalized.includes("ok") ||
    normalized.includes("success")
  ) {
    return "success";
  }
  if (normalized.includes("warn") || normalized.includes("pending") || normalized.includes("start")) {
    return "warn";
  }
  if (
    normalized.includes("fail") ||
    normalized.includes("error") ||
    normalized.includes("critical") ||
    normalized.includes("stop") ||
    normalized.includes("inactive")
  ) {
    return "error";
  }
  return "info";
}

export default function SuperAdminPage() {
  const [email, setEmail] = useState("admin@okxstatbot.dev");
  const [password, setPassword] = useState("ChangeMeNow123!");
  const [token, setToken] = useState<string>("");
  const [status, setStatus] = useState("Signed out");
  const [error, setError] = useState("");

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

  const clearAdminSession = useCallback((reason = "Signed out") => {
    localStorage.removeItem(ADMIN_ACCESS_TOKEN_KEY);
    localStorage.removeItem(ADMIN_REFRESH_TOKEN_KEY);
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
  }, []);

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
    const stored = localStorage.getItem(ADMIN_ACCESS_TOKEN_KEY) || "";
    if (!stored) return;
    setToken(stored);
    setStatus("Session restored");
    loadAdminData(stored)
      .then(() => refreshLogTail(stored, "latest"))
      .catch((err: unknown) => {
        if (isUnauthorizedError(err)) {
          clearAdminSession("Session expired. Please sign in again.");
          setError("Session expired. Please sign in again.");
          return;
        }
        const msg = err instanceof Error ? err.message : "Failed loading admin data";
        setError(msg);
      });
  }, [clearAdminSession, loadAdminData, refreshLogTail]);

  useEffect(() => {
    if (!token || !me?.is_superuser) return;
    const timer = window.setInterval(() => {
      refreshLogTail(token, selectedRunKey || "latest").catch((err: unknown) => {
        if (isUnauthorizedError(err)) {
          clearAdminSession("Session expired. Please sign in again.");
          setError("Session expired. Please sign in again.");
        }
      });
    }, 2000);
    return () => window.clearInterval(timer);
  }, [clearAdminSession, token, me?.is_superuser, selectedRunKey, refreshLogTail]);

  async function onLoginSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const pair = await login(email, password);
      localStorage.setItem(ADMIN_ACCESS_TOKEN_KEY, pair.access_token);
      localStorage.setItem(ADMIN_REFRESH_TOKEN_KEY, pair.refresh_token);
      setToken(pair.access_token);
      await loadAdminData(pair.access_token);
      await refreshLogTail(pair.access_token, "latest");
      setStatus("Authenticated");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Login failed";
      setError(msg);
      setStatus("Authentication failed");
    } finally {
      setBusy(false);
    }
  }

  function handleLogout() {
    clearAdminSession("Signed out");
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
        clearAdminSession("Session expired. Please sign in again.");
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
        clearAdminSession("Session expired. Please sign in again.");
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
        clearAdminSession("Session expired. Please sign in again.");
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
        clearAdminSession("Session expired. Please sign in again.");
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
        clearAdminSession("Session expired. Please sign in again.");
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
        clearAdminSession("Session expired. Please sign in again.");
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
        clearAdminSession("Session expired. Please sign in again.");
        setError("Session expired. Please sign in again.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Remove role failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <DashboardShell
        title="Super Admin Console"
        subtitle="Control bot runs, live logs, settings, users, and roles."
        status={status}
        activeHref="/admin"
        navItems={[
          { href: "/", label: "Analytics", hint: "Runs, quality, reports" },
          { href: "/admin", label: "Super Admin", hint: "Control plane" },
        ]}
      >
        <div className="admin-shell">
          <section className="admin-auth card">
            <h1>Super Admin Console</h1>
            <p className="muted">Control bot runs, live logs, settings, users, and roles.</p>
            <form onSubmit={onLoginSubmit} className="admin-auth-form">
              <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" required />
              <input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                type="password"
                placeholder="Password"
                required
              />
              <button type="submit" disabled={busy}>
                {busy ? "Signing in..." : "Sign in"}
              </button>
            </form>
            {error ? <p className="error">{error}</p> : null}
          </section>
        </div>
      </DashboardShell>
    );
  }

  if (me && !me.is_superuser) {
    return (
      <DashboardShell
        title="Super Admin Console"
        subtitle="Control bot runs, live logs, settings, users, and roles."
        status={status}
        activeHref="/admin"
        navItems={[
          { href: "/", label: "Analytics", hint: "Runs, quality, reports" },
          { href: "/admin", label: "Super Admin", hint: "Control plane" },
        ]}
      >
        <div className="admin-shell">
          <section className="card">
            <h1>Super Admin Console</h1>
            <p className="error">Current account is not superuser.</p>
          </section>
        </div>
      </DashboardShell>
    );
  }

  return (
    <DashboardShell
      title="Super Admin Console"
      subtitle="Start/stop bot runs, monitor live terminal, and manage users and runtime settings."
      status={status}
      activeHref="/admin"
      navItems={[
        { href: "/", label: "Analytics", hint: "Runs, quality, reports" },
        { href: "/admin", label: "Super Admin", hint: "Control plane" },
      ]}
      actions={
        <div className="admin-hero-actions">
          <button onClick={handleRefreshAll} disabled={busy}>
            Refresh
          </button>
          <button onClick={handleStart} disabled={busy || Boolean(botStatus?.running)}>
            Start Bot
          </button>
          <button className="ghost" onClick={handleStop} disabled={busy || !botStatus?.running}>
            Stop Bot
          </button>
          <button className="ghost" onClick={handleLogout} disabled={busy}>
            Logout
          </button>
        </div>
      }
    >
      <div className="admin-shell">
        <section className="admin-hero">
          <div>
            <p className="eyebrow">V2 Control Plane</p>
            <h1>Super Admin Console</h1>
            <p className="muted">{status}</p>
          </div>
        </section>

      {error ? <p className="error">{error}</p> : null}

      <section className="ta-metrics-grid">
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

      <section className="admin-grid">
        <PanelCard title="Bot Control" subtitle="Live process status and active run context.">
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
        </PanelCard>

        <PanelCard title="Live Terminal" className="terminal-card">
          <div className="terminal-header">
            <select value={selectedRunKey} onChange={(e) => setSelectedRunKey(e.target.value)}>
              <option value="latest">latest</option>
              {logRuns.map((row) => (
                <option key={row.run_key} value={row.run_key}>
                  {row.run_key}
                </option>
              ))}
            </select>
          </div>
          <pre className="terminal-body">{(logTail?.lines || []).join("\n") || "No log lines yet."}</pre>
        </PanelCard>
      </section>

      <section className="admin-grid">
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
                    <td colSpan={3} className="muted">
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
                    <td colSpan={4} className="muted">
                      No report runs found.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </TableFrame>
        </PanelCard>
      </section>

      <section className="card">
        <h3>Settings (.env)</h3>
        <p className="tiny">Editing values here updates `Execution/.env` directly.</p>
        <div className="table-wrap">
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
                    <button className="ghost" onClick={() => saveEnvKey(key)} disabled={busy}>
                      Save
                    </button>
                  </td>
                </tr>
              ))}
              {!sortedEnvKeys.length ? (
                <tr>
                  <td colSpan={3} className="muted">
                    No settings found.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="admin-grid">
        <article className="card">
          <h3>User Management</h3>
          <form onSubmit={handleCreateUser} className="admin-inline-form">
            <input value={newUserEmail} onChange={(e) => setNewUserEmail(e.target.value)} placeholder="email" required />
            <input
              value={newUserPassword}
              onChange={(e) => setNewUserPassword(e.target.value)}
              placeholder="password"
              type="password"
              required
            />
            <label className="tiny">
              <input type="checkbox" checked={newUserSuper} onChange={(e) => setNewUserSuper(e.target.checked)} />
              superuser
            </label>
            <button type="submit" disabled={busy}>
              Create
            </button>
          </form>

          <div className="table-wrap compact">
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
                      <div className="role-list">
                        {user.roles.map((role) => (
                          <button
                            key={`${user.id}-${role.name}`}
                            className="role-chip"
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
          </div>
        </article>

        <article className="card">
          <h3>Role Management</h3>
          <form onSubmit={handleAssignRole} className="admin-inline-form">
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
            <button type="submit" disabled={busy}>
              Assign Role
            </button>
          </form>
          <p className="muted tiny">Click role chips in User Management table to remove roles.</p>
        </article>
      </section>
      </div>
    </DashboardShell>
  );
}
