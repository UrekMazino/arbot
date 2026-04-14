"use client";

import React, { memo, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  AdminBotStatus,
  AdminLogTail,
  AdminLogRun,
  AdminPairsHealth,
  AdminReportRun,
  UserRecord,
  clearAdminLogs,
  getAdminBotLogTail,
  getAdminBotStatus,
  getAdminLogRuns,
  getAdminPairsHealth,
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
import { useBotStatus, useLogRuns, useDashboardWebSocket, useLogStream } from "../../../lib/hooks";
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

function fmtUptime(startTime: number | null, isCurrentRun: boolean, isRunning: boolean, lastUpdateAt: string | null | undefined): string {
  if (!startTime || Number.isNaN(startTime)) return "n/a";

  // Determine if we should use live or frozen time
  // Use live time if:
  // 1. This is the current run AND bot is running (live tracking)
  // 2. OR if we don't have a valid lastUpdateAt and bot is running (use current time)
  const useLiveTime = (isCurrentRun && isRunning) || (!lastUpdateAt && isRunning);

  // Use lastUpdateAt if available and we're not using live time
  // Otherwise use startTime as fallback (shows 0 duration if no update time)
  const endTime = useLiveTime
    ? (Date.now() / 1000)
    : (lastUpdateAt ? new Date(lastUpdateAt).getTime() / 1000 : startTime);

  const diff = endTime - startTime;
  if (diff < 0) return "n/a";
  const hours = Math.floor(diff / 3600);
  const minutes = Math.floor((diff % 3600) / 60);
  const seconds = Math.floor(diff % 60);
  if (hours > 0) {
    return useLiveTime ? `${hours}h ${minutes}m` : `${hours}h ${minutes}m (stopped)`;
  }
  return useLiveTime ? `${minutes}m ${seconds}s` : `${minutes}m ${seconds}s (stopped)`;
}

function fmtDuration(seconds: number): string {
  if (!seconds || Number.isNaN(seconds)) return "0s";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) {
    return `${h}h ${m}m`;
  }
  if (m > 0) {
    return `${m}m ${s}s`;
  }
  return `${s}s`;
}

export default function AdminConsolePage() {
  const router = useRouter();
  const { isFloating, setFloating, logTail: sharedLogTail, setLogTail: setSharedLogTail } = useFloatingTerminal();
  const [status, setStatus] = useState("Signed out");
  const [error, setError] = useState("");
  const [authChecked, setAuthChecked] = useState(false);
  const [profileResolved, setProfileResolved] = useState(false);
  const [activeTab, setActiveTab] = useState<"control" | "logs" | "pairs">("control");

  const [me, setMe] = useState<UserRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [terminalFullscreen, setTerminalFullscreen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const [waitingForRun, setWaitingForRun] = useState(false);
  const [lastKnownRunKey, setLastKnownRunKey] = useState<string | null>(null);

  // Use custom hooks for bot and log management
  const {
    botStatus, setBotStatus,
    pairsHealth, setPairsHealth,
    startingEquity, runningEquity, sessionPnl, runUptime,
    setStartingEquity, setRunningEquity, setSessionPnl, setRunUptime,
  } = useBotStatus();

  const {
    logRuns, setLogRuns,
    reportRuns, setReportRuns,
    selectedRunKey, setSelectedRunKey,
    localLogTail, setLocalLogTail,
    pairHistory, setPairHistory,
    pairCount, setPairCount,
  } = useLogRuns();

  // SSE for real-time log streaming
  const { logLines: streamLogLines, isStreaming, startStream, stopStream } = useLogStream(selectedRunKey);

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
    setPairsHealth(null);
    if (isFloating) setSharedLogTail(null);
    setFloating(false);
    if (redirectToLogin) {
      router.replace("/login?next=/admin/console");
    }
  }, [
    router,
    setFloating,
    setStatus,
    setError,
    setProfileResolved,
    setMe,
    setBotStatus,
    setLogRuns,
    setReportRuns,
    setLocalLogTail,
    setPairsHealth,
    isFloating,
    setSharedLogTail,
  ]);

  const reportFileCount = useMemo(
    () => reportRuns.reduce((acc, row) => acc + row.file_count, 0),
    [reportRuns],
  );
  const navItems = useMemo(() => getAdminNavItems(me), [me]);
  const fallbackHref = useMemo(() => getFirstAccessibleAdminPath(me), [me]);
  const canViewLogs = hasPermission(me, "view_logs");
  const canManageBot = hasPermission(me, "manage_bot");
  const canViewConsole = canAccessAdminPath(me, "/admin/console");
  // Use shared logTail from context when floating, otherwise use local state + SSE stream
  const displayLogTail = isFloating ? sharedLogTail : localLogTail;
  // Use SSE streamed lines when available and not floating
  const displayLines = (!isFloating && streamLogLines.length > 0) ? streamLogLines : displayLogTail?.lines || [];
  const showingControlLog = displayLogTail?.run_key === "__control__";

  // Memoize run key options for dropdown to prevent recalculation
  const runKeyOptions = useMemo(
    () => logRuns.map((row) => (
      <option key={row.run_key} value={row.run_key}>
        {row.run_key}
      </option>
    )),
    [logRuns],
  );

  const loadAdminData = useCallback(async () => {
      const meData = await getMe();
      setMe(meData);

      if (!canAccessAdminPath(meData, "/admin/console")) {
        setBotStatus(null);
        setLogRuns([]);
        setReportRuns([]);
        setLocalLogTail(null);
        setPairsHealth(null);
        return;
      }

      const canLoadStatus = hasPermission(meData, "manage_bot") || hasPermission(meData, "view_logs");
      const canLoadLogs = hasPermission(meData, "view_logs");
      const canLoadReports = hasPermission(meData, "view_reports");

      // First load status and log runs to determine which run to load
      const [statusData, logsData, reportsData, healthData] = await Promise.all([
        canLoadStatus ? getAdminBotStatus() : Promise.resolve(null),
        canLoadLogs ? getAdminLogRuns() : Promise.resolve([] as AdminLogRun[]),
        canLoadReports ? getAdminReportRuns() : Promise.resolve([] as AdminReportRun[]),
        canLoadStatus ? getAdminPairsHealth() : Promise.resolve(null),
      ]);

      setBotStatus(statusData);
      setLogRuns(logsData);
      setReportRuns(reportsData);
      setPairsHealth(healthData);

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
        // Set equity data on initial load
        if (displayLogTailData?.equity !== null) {
          setStartingEquity(displayLogTailData.equity);
          setRunningEquity(displayLogTailData.equity);
        }
        if (displayLogTailData?.session_pnl !== null && displayLogTailData?.session_pnl_pct !== null) {
          setSessionPnl({ amount: displayLogTailData.session_pnl, pct: displayLogTailData.session_pnl_pct });
        }
        // Set uptime and pair history
        if (displayLogTailData?.run_start_time !== null) {
          setRunUptime(displayLogTailData.run_start_time);
        }
        if (displayLogTailData?.pair_history) {
          setPairHistory(displayLogTailData.pair_history);
          setPairCount(displayLogTailData.pair_count || 0);
        }
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
      // Update equity data from log tail
      if (next?.equity !== null) {
        setRunningEquity(next.equity);
      }
      if (next?.session_pnl !== null && next?.session_pnl_pct !== null) {
        setSessionPnl({ amount: next.session_pnl, pct: next.session_pnl_pct });
      }
      // Update uptime and pair history
      if (next?.run_start_time !== null) {
        setRunUptime(next.run_start_time);
      }
      if (next?.pair_history) {
        setPairHistory(next.pair_history);
        setPairCount(next.pair_count || 0);
      }
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
    }, [
      canViewLogs,
      waitingForRun,
      lastKnownRunKey,
      isFloating,
      setSharedLogTail,
      setLocalLogTail,
      setRunningEquity,
      setSessionPnl,
      setRunUptime,
      setPairHistory,
      setPairCount,
      setSelectedRunKey,
    ]);

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
          // Update equity data from log tail
          if (tail?.equity !== null) {
            setRunningEquity(tail.equity);
            // Set starting equity when switching to a new run
            if (selectedRunKey !== latestRunKey) {
              setStartingEquity(tail.equity);
            }
          }
          if (tail?.session_pnl !== null && tail?.session_pnl_pct !== null) {
            setSessionPnl({ amount: tail.session_pnl, pct: tail.session_pnl_pct });
          }
          // Update uptime and pair history
          if (tail?.run_start_time !== null) {
            setRunUptime(tail.run_start_time);
          }
          if (tail?.pair_history) {
            setPairHistory(tail.pair_history);
            setPairCount(tail.pair_count || 0);
          }
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
  }, [
    waitingForRun,
    canViewLogs,
    lastKnownRunKey,
    selectedRunKey,
    setLogRuns,
    setLocalLogTail,
    setRunningEquity,
    setStartingEquity,
    setSessionPnl,
    setRunUptime,
    setPairHistory,
    setPairCount,
    setBotStatus,
    setSelectedRunKey,
  ]);

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

  const [redirectHandled, setRedirectHandled] = useState(false);
  
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
      setRedirectHandled(true);
      router.replace(fallbackHref);
    }
  }, [
    profileResolved,
    me,
    canViewConsole,
    fallbackHref,
    router,
    setBotStatus,
    setLogRuns,
    setReportRuns,
    setLocalLogTail,
    setStatus,
    setError,
  ]);

  useEffect(() => {
    // SSE streaming - replaces polling when not floating
    if (!canViewConsole || !canViewLogs || isFloating) return;
    startStream(selectedRunKey || "latest");
    return () => stopStream();
  }, [canViewConsole, canViewLogs, selectedRunKey, isFloating, startStream, stopStream]);

  // Poll log tail metadata (equity, pair_count) while using SSE for real-time logs
  useEffect(() => {
    if (!canViewConsole || !canViewLogs || isFloating) return;

    let isMounted = true;
    let inFlight = false;

    const pollMetadata = async () => {
      if (inFlight) return;
      inFlight = true;

      try {
        const tail = await getAdminBotLogTail(selectedRunKey || "latest", 50);
        if (!isMounted) return;

        // Update localLogTail with fresh metadata (but keep existing lines if SSE is active)
        if (streamLogLines.length > 0) {
          // SSE is active, merge new metadata with SSE lines
          setLocalLogTail({
            ...tail,
            lines: streamLogLines, // Keep SSE lines
          });
        } else {
          // No SSE, use full tail data
          setLocalLogTail(tail);
        }

        // Update equity data
        if (tail?.equity !== null) {
          setRunningEquity(tail.equity);
          // Set starting equity only if not already set
          if (startingEquity === null) {
            setStartingEquity(tail.equity);
          }
        }
        if (tail?.session_pnl !== null && tail?.session_pnl_pct !== null) {
          setSessionPnl({ amount: tail.session_pnl, pct: tail.session_pnl_pct });
        }
        if (tail?.run_start_time !== null) {
          setRunUptime(tail.run_start_time);
        }
        if (tail?.pair_history) {
          setPairHistory(tail.pair_history);
          setPairCount(tail.pair_count || 0);
        }
      } catch {
        // Ignore errors
      } finally {
        inFlight = false;
      }
    };

    // Poll immediately then every 5 seconds
    pollMetadata();
    const timer = window.setInterval(pollMetadata, 5000);

    return () => {
      isMounted = false;
      window.clearInterval(timer);
    };
  }, [
    canViewConsole,
    canViewLogs,
    selectedRunKey,
    isFloating,
    streamLogLines,
    startingEquity,
    setLocalLogTail,
    setRunningEquity,
    setStartingEquity,
    setSessionPnl,
    setRunUptime,
    setPairHistory,
    setPairCount,
  ]);

  // Poll pairs health data
  useEffect(() => {
    if (!canViewConsole) return;

    let isMounted = true;
    let inFlight = false;
    const timer = window.setInterval(async () => {
      if (!canManageBot && !canViewLogs) return;
      if (inFlight) return;

      inFlight = true;

      try {
        const health = await getAdminPairsHealth();
        if (isMounted) setPairsHealth(health);
      } catch {
        // ignore
      } finally {
        inFlight = false;
      }
    }, 10000);

    return () => {
      isMounted = false;
      window.clearInterval(timer);
    };
  }, [
    canViewConsole,
    canManageBot,
    canViewLogs,
    setPairsHealth,
  ]);

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
          <button
            onClick={() => setActiveTab("pairs")}
            className={tabButtonClass(activeTab === "pairs")}
          >
            Pairs Health
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
                <pre className="custom-scrollbar mt-2 h-[520px] overflow-auto rounded-xl border border-gray-700 bg-gray-950 p-3 text-xs leading-relaxed text-emerald-100" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                  {displayLines.length > 0 ? displayLines.map((line, i) => <span key={i}>{line}<br /></span>) : "No log lines yet."}
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
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Starting Equity</p>
                    <p className="mt-1.5 font-mono text-sm text-gray-900 dark:text-white/90">{startingEquity !== null ? `${startingEquity.toFixed(2)} USDT` : "n/a"}</p>
                  </div>
                  <div className="border-b border-gray-200 pb-3 dark:border-gray-700">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Latest Run</p>
                    <p className="mt-1.5 truncate font-mono text-sm text-gray-900 dark:text-white/90">{botStatus?.latest_run_key || "n/a"}</p>
                  </div>
                  <div className="border-b border-gray-200 pb-3 dark:border-gray-700">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Running Equity</p>
                    <p className="mt-1.5 font-mono text-sm text-gray-900 dark:text-white/90">
                      {runningEquity !== null ? `${runningEquity.toFixed(2)} USDT` : "n/a"}
                      {sessionPnl && (
                        <span className={`ml-2 text-xs ${sessionPnl.amount >= 0 ? "text-green-600 dark:text-green-400" : "text-red-600 dark:text-red-400"}`}>
                          ({sessionPnl.amount >= 0 ? "+" : ""}{sessionPnl.amount.toFixed(2)} / {sessionPnl.pct.toFixed(2)}%)
                        </span>
                      )}
                    </p>
                  </div>
                  <div className="pt-1">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Run Uptime</p>
                    <p className="mt-1.5 font-mono text-sm text-gray-900 dark:text-white/90">{fmtUptime(runUptime, Boolean(selectedRunKey === "latest" || selectedRunKey === botStatus?.latest_run_key), Boolean(botStatus?.running), localLogTail?.updated_at)}</p>
                  </div>
                  <div className="pt-1">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Pairs Used</p>
                    <p className="mt-1.5 font-mono text-sm text-gray-900 dark:text-white/90">{pairCount > 0 ? pairCount : "n/a"}</p>
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
                    <select className="mt-1.5 w-full min-w-[180px] rounded border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white/90" value={selectedRunKey} onChange={async (e) => {
                      const newKey = e.target.value;
                      setSelectedRunKey(newKey);
                      // Fetch equity for newly selected run
                      if (newKey !== "latest") {
                        const tail = await getAdminBotLogTail(newKey, 320);
                        if (tail?.equity !== null) {
                          setStartingEquity(tail.equity);
                          setRunningEquity(tail.equity);
                        }
                        if (tail?.session_pnl !== null && tail?.session_pnl_pct !== null) {
                          setSessionPnl({ amount: tail.session_pnl, pct: tail.session_pnl_pct });
                        } else {
                          setSessionPnl(null);
                        }
                        // Update uptime and pair history
                        if (tail?.run_start_time !== null) {
                          setRunUptime(tail.run_start_time);
                        }
                        if (tail?.pair_history) {
                          setPairHistory(tail.pair_history);
                          setPairCount(tail.pair_count || 0);
                        } else {
                          setPairHistory([]);
                          setPairCount(0);
                        }
                      }
                    }}>
                      <option value="latest">latest</option>
                      {runKeyOptions}
                    </select>
                  </div>
                </div>
              </PanelCard>

              {/* Pair History Table */}
              {pairHistory.length > 0 && (
                <PanelCard title="Pair History" subtitle={`${pairHistory.length} pairs used in this run`}>
                  <TableFrame>
                    <table>
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>Pair</th>
                          <th>Uptime</th>
                          <th>Duration</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pairHistory.map((entry, idx) => {
                          // Calculate total run duration consistently
                          const totalDuration = runUptime && localLogTail?.updated_at
                            ? (new Date(localLogTail.updated_at).getTime() / 1000 - runUptime)
                            : pairHistory.reduce((sum, p) => sum + p.duration_seconds, 0);
                          const pct = totalDuration > 0 ? (entry.duration_seconds / totalDuration) * 100 : 0;
                          return (
                            <tr key={entry.pair}>
                              <td className="text-xs text-gray-500">{idx + 1}</td>
                              <td className="font-mono text-xs">{entry.pair}</td>
                              <td className="text-xs">{fmtDuration(entry.duration_seconds)}</td>
                              <td className="text-xs text-gray-500">
                                {entry.duration_seconds > 0 ? `${pct.toFixed(1)}%` : "0%"}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </TableFrame>
                </PanelCard>
              )}
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
              <pre className="custom-scrollbar flex-1 overflow-auto rounded-xl border border-gray-700 bg-gray-950 p-3 text-xs leading-relaxed text-emerald-100" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                {displayLines.length > 0 ? displayLines.map((line, i) => <span key={i}>{line}<br /></span>) : "No log lines yet."}
              </pre>
            </div>
          </div>
        ) : null}
        </>
        )}

        {activeTab === "logs" && (
          <section className="grid gap-2">
            <div className="flex justify-end">
              <button
                className="rounded bg-red-600 px-3 py-1.5 text-xs text-white hover:bg-red-700 dark:bg-red-700 dark:hover:bg-red-600"
                onClick={async () => {
                  if (!confirm("Clear old logs and reports? The most recent run will be kept.")) return;
                  setBusy(true);
                  try {
                    const result = await clearAdminLogs(true);
                    alert(`Cleared ${result.deleted_logs} logs and ${result.deleted_reports} reports.`);
                    // Refresh the log runs list
                    const logs = await getAdminLogRuns();
                    setLogRuns(logs);
                    const reports = await getAdminReportRuns();
                    setReportRuns(reports);
                  } catch (err) {
                    alert("Failed to clear logs: " + (err instanceof Error ? err.message : "Unknown error"));
                  } finally {
                    setBusy(false);
                  }
                }}
                disabled={busy}
              >
                Clear Old Logs
              </button>
            </div>
            <div className="grid gap-2 xl:grid-cols-2">
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
            </div>
          </section>
        )}

        {activeTab === "pairs" && (
          <section className="grid gap-4">
            {/* Active Pair */}
            <PanelCard title="Active Pair">
              {pairsHealth?.active_pair ? (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Symbol 1</p>
                    <p className="mt-1 font-mono text-sm text-gray-900 dark:text-white/90">
                      {(pairsHealth.active_pair as Record<string, unknown>)?.ticker_1 as string || "n/a"}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Symbol 2</p>
                    <p className="mt-1 font-mono text-sm text-gray-900 dark:text-white/90">
                      {(pairsHealth.active_pair as Record<string, unknown>)?.ticker_2 as string || "n/a"}
                    </p>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-gray-500 dark:text-gray-400">No active pair</p>
              )}
            </PanelCard>

            {/* Hospital - Pairs on Cooldown */}
            <PanelCard
              title="Hospital (Cooldown)"
              subtitle={`${pairsHealth?.hospital?.length || 0} pairs on cooldown`}
            >
              <TableFrame>
                <table>
                  <thead>
                    <tr>
                      <th>Pair</th>
                      <th>Reason</th>
                      <th>Cooldown</th>
                      <th>Remaining</th>
                      <th>Status</th>
                      <th>Visits</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pairsHealth?.hospital?.map((entry) => (
                      <tr key={entry.pair}>
                        <td className="font-mono text-xs">{entry.pair}</td>
                        <td className="text-xs">{entry.reason}</td>
                        <td className="text-xs">{entry.cooldown_seconds}s</td>
                        <td className="text-xs">
                          {entry.is_ready ? (
                            <span className="text-green-600 dark:text-green-400">Ready</span>
                          ) : (
                            <span className="text-amber-600 dark:text-amber-400">
                              {Math.round((entry.remaining_seconds ?? 0) / 60)}m
                            </span>
                          )}
                        </td>
                        <td>
                          <StatusPill
                            label={entry.is_ready ? "Ready" : "Cooldown"}
                            tone={entry.is_ready ? "success" : "warn"}
                          />
                        </td>
                        <td className="text-xs">{entry.visits}</td>
                      </tr>
                    ))}
                    {!pairsHealth?.hospital?.length ? (
                      <tr>
                        <td colSpan={6} className="text-sm text-gray-500 dark:text-gray-400">
                          No pairs in hospital
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </TableFrame>
            </PanelCard>

            {/* Graveyard - Failed Pairs */}
            <PanelCard
              title="Graveyard (Failed)"
              subtitle={`${pairsHealth?.graveyard?.length || 0} permanently excluded pairs`}
            >
              <TableFrame>
                <table>
                  <thead>
                    <tr>
                      <th>Pair</th>
                      <th>Reason</th>
                      <th>TTL Days</th>
                      <th>Added</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pairsHealth?.graveyard?.map((entry) => (
                      <tr key={entry.pair}>
                        <td className="font-mono text-xs">{entry.pair}</td>
                        <td className="text-xs">{entry.reason}</td>
                        <td className="text-xs">{entry.ttl_days ?? "Permanent"}</td>
                        <td className="text-xs">
                          {entry.added_at ? new Date(entry.added_at * 1000).toLocaleDateString() : "n/a"}
                        </td>
                      </tr>
                    ))}
                    {!pairsHealth?.graveyard?.length ? (
                      <tr>
                        <td colSpan={4} className="text-sm text-gray-500 dark:text-gray-400">
                          No pairs in graveyard
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
