"use client";

import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import {
  AdminBotStatus,
  AdminLogFile,
  AdminLogTail,
  AdminLogRun,
  AdminPairsHealth,
  AdminReportArtifactFile,
  AdminReportRun,
  AdminReportSummary,
  AdminRunRuntime,
  UserRecord,
  clearAdminActivePair,
  clearAdminLogs,
  deleteAdminLogRun,
  downloadAdminReportFile,
  downloadAdminReportZip,
  getAdminBotLogTail,
  getAdminBotStatus,
  getAdminLogFile,
  getAdminLogRuns,
  getAdminPairsHealth,
  getAdminReportRunSummary,
  getAdminReportRuns,
  getAdminRunRuntime,
  getMe,
  isUnauthorizedError,
  isForbiddenError,
  removePairFromGraveyard,
  startAdminBot,
  stopAdminBot,
} from "../../../lib/api";
import {
  canAccessAdminPath,
  getAdminNavItems,
  getFirstAccessibleAdminPath,
  hasAnyPermission,
  hasPermission,
} from "../../../lib/admin-access";
import { clearStoredAdminSession, getStoredAdminEmail } from "../../../lib/auth";
import { UI_CLASSES } from "../../../lib/ui-classes";
import { useBotStatus, useLogRuns, useDashboardWebSocket, useLogStream } from "../../../lib/hooks";
import { useFloatingTerminal } from "../../../context/floating-terminal-context";
import { DashboardShell } from "../../../components/dashboard-shell";
import { PanelCard, StatusPill, TableFrame } from "../../../components/panels";
import { useConfirmDialog } from "../../../components/ui/confirm-dialog";

type SearchMatch = {
  start: number;
  end: number;
  matchIndex: number;
};

type SearchModel = {
  totalMatches: number;
  matchesByLine: Map<number, SearchMatch[]>;
};

function buildSearchModel(lines: string[], query: string): SearchModel {
  const trimmed = query.trim().toLowerCase();
  if (!trimmed) {
    return { totalMatches: 0, matchesByLine: new Map<number, SearchMatch[]>() };
  }

  const matchesByLine = new Map<number, SearchMatch[]>();
  let totalMatches = 0;

  lines.forEach((line, lineIndex) => {
    const lineLower = line.toLowerCase();
    let searchFrom = 0;
    const lineMatches: SearchMatch[] = [];

    while (searchFrom <= lineLower.length) {
      const foundAt = lineLower.indexOf(trimmed, searchFrom);
      if (foundAt === -1) break;
      lineMatches.push({
        start: foundAt,
        end: foundAt + trimmed.length,
        matchIndex: totalMatches,
      });
      totalMatches += 1;
      searchFrom = foundAt + Math.max(trimmed.length, 1);
    }

    if (lineMatches.length > 0) {
      matchesByLine.set(lineIndex, lineMatches);
    }
  });

  return { totalMatches, matchesByLine };
}

function nextSearchIndex(currentIndex: number, totalMatches: number, direction: 1 | -1): number {
  if (totalMatches <= 0) return -1;
  if (currentIndex < 0 || currentIndex >= totalMatches) {
    return direction === 1 ? 0 : totalMatches - 1;
  }
  return (currentIndex + direction + totalMatches) % totalMatches;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function SearchBar({
  query,
  onQueryChange,
  totalMatches,
  activeMatchIndex,
  onPrev,
  onNext,
  inputRef,
}: {
  query: string;
  onQueryChange: (value: string) => void;
  totalMatches: number;
  activeMatchIndex: number;
  onPrev: () => void;
  onNext: () => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
}) {
  const hasQuery = query.trim().length > 0;
  const hasMatches = totalMatches > 0;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <input
        ref={inputRef}
        type="search"
        value={query}
        onChange={(event) => onQueryChange(event.target.value)}
        placeholder="Search terminal..."
        className="w-48 rounded border border-gray-600 bg-gray-900 px-2 py-1 text-xs text-white placeholder:text-gray-500 focus:border-brand-500 focus:outline-none"
      />
      <span className="min-w-[68px] text-right text-xs text-gray-400">
        {hasQuery ? (hasMatches ? `${activeMatchIndex + 1}/${totalMatches}` : "0 matches") : "Search"}
      </span>
      <button
        type="button"
        onClick={onPrev}
        disabled={!hasMatches}
        className="rounded border border-gray-600 px-2 py-1 text-xs text-gray-300 hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Prev
      </button>
      <button
        type="button"
        onClick={onNext}
        disabled={!hasMatches}
        className="rounded border border-gray-600 px-2 py-1 text-xs text-gray-300 hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Next
      </button>
    </div>
  );
}

const SearchableTerminalContent = memo(function SearchableTerminalContent({
  lines,
  emptyText,
  searchModel,
  activeMatchIndex,
  className,
}: {
  lines: string[];
  emptyText: string;
  searchModel: SearchModel;
  activeMatchIndex: number;
  className: string;
}) {
  const activeMatchRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (searchModel.totalMatches <= 0 || activeMatchIndex < 0) return;
    activeMatchRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [searchModel.totalMatches, activeMatchIndex]);

  return (
    <pre className={className} style={{ whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
      {lines.length > 0 ? (
        lines.map((line, lineIndex) => {
          const lineMatches = searchModel.matchesByLine.get(lineIndex) || [];
          let cursor = 0;
          const parts: React.ReactNode[] = [];

          lineMatches.forEach((match) => {
            if (match.start > cursor) {
              parts.push(line.slice(cursor, match.start));
            }
            const isActive = match.matchIndex === activeMatchIndex;
            parts.push(
              <mark
                key={`match-${lineIndex}-${match.matchIndex}`}
                ref={isActive ? (node) => { activeMatchRef.current = node; } : undefined}
                className={isActive ? "rounded bg-amber-300 px-0.5 text-gray-950" : "rounded bg-emerald-700/60 px-0.5 text-white"}
              >
                {line.slice(match.start, match.end)}
              </mark>,
            );
            cursor = match.end;
          });

          if (cursor < line.length) {
            parts.push(line.slice(cursor));
          }

          const lineHasActiveMatch = lineMatches.some((match) => match.matchIndex === activeMatchIndex);

          return (
            <span
              key={lineIndex}
              className={lineHasActiveMatch ? "block rounded bg-white/5" : undefined}
            >
              {parts.length > 0 ? parts : line}
              <br />
            </span>
          );
        })
      ) : (
        emptyText
      )}
    </pre>
  );
});

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

function fmtNumber(value: number | null | undefined, maximumFractionDigits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits,
  });
}

function fmtCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)} USDT`;
}

function fmtPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function readRecordString(record: Record<string, unknown> | null | undefined, key: string): string | null {
  if (!record) return null;
  const value = record[key];
  const text = typeof value === "string" ? value.trim() : String(value ?? "").trim();
  return text || null;
}

function readRecordNumber(record: Record<string, unknown> | null | undefined, key: string): number | null {
  if (!record) return null;
  return coerceNumber(record[key]);
}

function coerceNumber(value: unknown): number | null {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function readRecordObject(record: Record<string, unknown> | null | undefined, key: string): Record<string, unknown> | null {
  if (!record) return null;
  const value = record[key];
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function artifactTone(file: AdminReportArtifactFile): "success" | "info" | "neutral" {
  const fmt = String(file.format || "").toLowerCase();
  if (fmt === "csv") return "info";
  if (fmt === "json") return "success";
  return "neutral";
}

function parseRunKeySortParts(runKey: string): { timestampKey: string; sequence: number } | null {
  const match = String(runKey || "").match(/^run_(\d+)_(\d{8})_(\d{6})$/i);
  if (!match) return null;
  return {
    sequence: Number(match[1] || 0),
    timestampKey: `${match[2]}${match[3]}`,
  };
}

function sortReportRunsDesc(rows: AdminReportRun[]): AdminReportRun[] {
  return [...rows].sort((a, b) => {
    const aRun = parseRunKeySortParts(a.run_key);
    const bRun = parseRunKeySortParts(b.run_key);
    if (aRun && bRun) {
      const timestampCompare = bRun.timestampKey.localeCompare(aRun.timestampKey);
      if (timestampCompare !== 0) return timestampCompare;
      const sequenceDelta = bRun.sequence - aRun.sequence;
      if (sequenceDelta !== 0) return sequenceDelta;
    }
    const mtimeDelta = Number(b.mtime_ts || 0) - Number(a.mtime_ts || 0);
    if (mtimeDelta !== 0) return mtimeDelta;
    return String(b.run_key || "").localeCompare(String(a.run_key || ""));
  });
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
  const [logViewerRun, setLogViewerRun] = useState<AdminLogRun | null>(null);
  const [logViewerData, setLogViewerData] = useState<AdminLogFile | null>(null);
  const [logViewerBusy, setLogViewerBusy] = useState(false);
  const [logViewerError, setLogViewerError] = useState("");
  const [reportViewerRunKey, setReportViewerRunKey] = useState("");
  const [reportViewerData, setReportViewerData] = useState<AdminReportSummary | null>(null);
  const [reportViewerBusy, setReportViewerBusy] = useState(false);
  const [reportViewerError, setReportViewerError] = useState("");
  const [reportDownloadKey, setReportDownloadKey] = useState("");
  const [terminalSearchQuery, setTerminalSearchQuery] = useState("");
  const [terminalActiveMatchIndex, setTerminalActiveMatchIndex] = useState(-1);
  const [logViewerSearchQuery, setLogViewerSearchQuery] = useState("");
  const [logViewerActiveMatchIndex, setLogViewerActiveMatchIndex] = useState(-1);
  const [selectedArtifactsRunKey, setSelectedArtifactsRunKey] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const [waitingForRun, setWaitingForRun] = useState(false);
  const [lastKnownRunKey, setLastKnownRunKey] = useState<string | null>(null);
  const [runtimeSnapshot, setRuntimeSnapshot] = useState<AdminRunRuntime | null>(null);
  const [graveyardRemoveBusyPair, setGraveyardRemoveBusyPair] = useState("");
  const terminalSearchInputRef = useRef<HTMLInputElement | null>(null);
  const logViewerSearchInputRef = useRef<HTMLInputElement | null>(null);
  const { ConfirmDialogComponent: actionConfirmDialog, confirm: showActionConfirm } = useConfirmDialog();

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
  const { logLines: streamLogLines, isStreaming, error: streamError, startStream, stopStream } = useLogStream(selectedRunKey);

  const closeLogViewer = useCallback(() => {
    setLogViewerRun(null);
    setLogViewerData(null);
    setLogViewerError("");
    setLogViewerBusy(false);
    setLogViewerSearchQuery("");
    setLogViewerActiveMatchIndex(-1);
  }, []);

  const closeReportViewer = useCallback(() => {
    setReportViewerRunKey("");
    setReportViewerData(null);
    setReportViewerBusy(false);
    setReportViewerError("");
    setReportDownloadKey("");
  }, []);

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
    closeLogViewer();
    closeReportViewer();
    setTerminalFullscreen(false);
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
    closeLogViewer,
    closeReportViewer,
    setTerminalFullscreen,
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
  const canViewReports = hasPermission(me, "view_reports");
  const canManageBot = hasPermission(me, "manage_bot");
  const canManageLogsReports = hasPermission(me, "manage_logs_reports");
  const canSwitchActivePair = hasAnyPermission(me, ["switch_active_pair", "manage_bot"]);
  const canViewPairUniverse = hasPermission(me, "view_pair_universe");
  const canManagePairSupply = hasAnyPermission(me, ["manage_pair_supply", "manage_bot"]);
  const canViewConsole = canAccessAdminPath(me, "/admin/console");
  const botTargetRunning = botStatus?.desired_running ?? botStatus?.running ?? false;
  const botTransitioning = Boolean(
    botStatus && botStatus.desired_running !== undefined && botStatus.desired_running !== botStatus.running,
  );
  const botStatusLabel = botTransitioning
    ? botTargetRunning
      ? "starting"
      : "stopping"
    : botStatus?.running
      ? "running"
      : "stopped";
  const botStatusTone = botTransitioning ? "warning" : botStatus?.running ? "success" : "error";
  // Use shared logTail from context when floating, otherwise use local state + SSE stream
  const displayLogTail = isFloating ? sharedLogTail : localLogTail;
  // Use SSE streamed lines when available and not floating
  const displayLines = (!isFloating && streamLogLines.length > 0) ? streamLogLines : displayLogTail?.lines || [];
  const showingControlLog = displayLogTail?.run_key === "__control__";
  const logViewerLines = useMemo(
    () => (logViewerData?.content ? logViewerData.content.split(/\r?\n/) : []),
    [logViewerData?.content],
  );
  const terminalSearchModel = useMemo(
    () => buildSearchModel(displayLines, terminalSearchQuery),
    [displayLines, terminalSearchQuery],
  );
  const logViewerSearchModel = useMemo(
    () => buildSearchModel(logViewerLines, logViewerSearchQuery),
    [logViewerLines, logViewerSearchQuery],
  );
  const artifactRunKeys = useMemo(
    () => Array.from(new Set([...logRuns.map((row) => row.run_key), ...reportRuns.map((row) => row.run_key)])),
    [logRuns, reportRuns],
  );
  const reportSummary = reportViewerData?.summary ?? null;
  const reportTradesTotal = readRecordNumber(reportSummary, "trades_total");
  const reportClosedTradesTotal = readRecordNumber(reportSummary, "closed_trades_total") ?? reportTradesTotal;
  const reportOpenTradesTotal = readRecordNumber(reportSummary, "open_trades_total") ?? 0;
  const reportTradeOpensTotal = readRecordNumber(reportSummary, "trade_opens_total") ?? reportTradesTotal;
  const reportDataSources = useMemo(() => {
    const dataSources = readRecordObject(reportSummary, "data_sources");
    return Object.entries(dataSources || {});
  }, [reportSummary]);
  const reportEventCounts = useMemo(() => {
    const counts = readRecordObject(reportSummary, "event_counts");
    return Object.entries(counts || {})
      .map(([key, value]) => ({ key, count: coerceNumber(value) ?? 0 }))
      .filter((row) => Number.isFinite(row.count) && row.count > 0)
      .sort((a, b) => b.count - a.count);
  }, [reportSummary]);
  const reportSeverityCounts = useMemo(() => {
    const counts = readRecordObject(reportSummary, "severity_counts");
    return Object.entries(counts || {})
      .map(([key, value]) => ({ key, count: coerceNumber(value) ?? 0 }))
      .filter((row) => Number.isFinite(row.count) && row.count > 0)
      .sort((a, b) => b.count - a.count);
  }, [reportSummary]);
  const runtimeUpdatedAt = runtimeSnapshot?.updated_at || localLogTail?.updated_at;

  // Memoize run key options for dropdown to prevent recalculation
  const runKeyOptions = useMemo(
    () => logRuns.map((row) => (
      <option key={row.run_key} value={row.run_key}>
        {row.run_key}
      </option>
    )),
    [logRuns],
  );

  const applyRuntimeMetrics = useCallback(
    (
      runtime: AdminRunRuntime | null,
      options?: {
        preserveStartingEquity?: boolean;
        preserveRunningEquity?: boolean;
        preserveRunUptime?: boolean;
      },
    ) => {
      if (!runtime) return;

      if (runtime.starting_equity !== null) {
        setStartingEquity(runtime.starting_equity);
      } else if (!options?.preserveStartingEquity) {
        setStartingEquity(null);
      }

      if (runtime.equity !== null) {
        setRunningEquity(runtime.equity);
      } else if (runtime.starting_equity !== null) {
        setRunningEquity(runtime.starting_equity);
      } else if (!options?.preserveRunningEquity) {
        setRunningEquity(null);
      }

      if (runtime.session_pnl !== null && runtime.session_pnl_pct !== null) {
        setSessionPnl({ amount: runtime.session_pnl, pct: runtime.session_pnl_pct });
      } else {
        setSessionPnl(null);
      }

      if (runtime.run_start_time !== null) {
        setRunUptime(runtime.run_start_time);
      } else if (!options?.preserveRunUptime) {
        setRunUptime(null);
      }

      if (runtime.pair_history) {
        setPairHistory(runtime.pair_history);
        setPairCount(runtime.pair_count || 0);
      } else {
        setPairHistory([]);
        setPairCount(0);
      }
    },
    [
      setStartingEquity,
      setRunningEquity,
      setSessionPnl,
      setRunUptime,
      setPairHistory,
      setPairCount,
    ],
  );

  const loadAdminData = useCallback(async () => {
      const meData = await getMe();
      setMe(meData);

      if (!canAccessAdminPath(meData, "/admin/console")) {
        setBotStatus(null);
        setLogRuns([]);
        setReportRuns([]);
        setLocalLogTail(null);
        setRuntimeSnapshot(null);
        setPairsHealth(null);
        return;
      }

      const canLoadStatus = hasPermission(meData, "manage_bot") || hasPermission(meData, "view_logs");
      const canLoadLogs = hasPermission(meData, "view_logs");
      const canLoadReports = hasPermission(meData, "view_reports");
      const canLoadPairHealth =
        canLoadStatus || hasPermission(meData, "view_pair_universe") || hasPermission(meData, "switch_active_pair");

      // First load status and log runs to determine which run to load
      const [statusData, logsData, reportsData, healthData] = await Promise.all([
        canLoadStatus ? getAdminBotStatus() : Promise.resolve(null),
        canLoadLogs ? getAdminLogRuns() : Promise.resolve([] as AdminLogRun[]),
        canLoadReports ? getAdminReportRuns() : Promise.resolve([] as AdminReportRun[]),
        canLoadPairHealth ? getAdminPairsHealth() : Promise.resolve(null),
      ]);

      setBotStatus(statusData);
      setLogRuns(logsData);
      setReportRuns(sortReportRunsDesc(reportsData));
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
        const [displayLogTailData, runtimeData] = await Promise.all([
          getAdminBotLogTail(runKeyToLoad, 320),
          getAdminRunRuntime(runKeyToLoad),
        ]);
        setLocalLogTail(displayLogTailData);
        setRuntimeSnapshot(runtimeData);
        applyRuntimeMetrics(runtimeData);
        if (runtimeData?.run_key) {
          setSelectedRunKey(runtimeData.run_key);
        } else if (displayLogTailData?.run_key && displayLogTailData.run_key !== "__control__") {
          setSelectedRunKey(displayLogTailData.run_key);
        } else {
          setSelectedRunKey(runKeyToLoad);
        }
      }
    },
    [applyRuntimeMetrics],
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

  const handleOpenLogViewer = useCallback(async (row: AdminLogRun) => {
    if (!canViewLogs) return;
    setLogViewerRun(row);
    setLogViewerData(null);
    setLogViewerError("");
    setLogViewerBusy(true);
    try {
      const next = await getAdminLogFile(row.run_key);
      setLogViewerData(next);
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      if (isForbiddenError(err)) {
        setLogViewerError("Insufficient permissions to view this log.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Failed to load log file";
      setLogViewerError(msg);
    } finally {
      setLogViewerBusy(false);
    }
  }, [canViewLogs, clearAdminSession, setError]);

  const handleOpenReportViewer = useCallback(async (runKey: string) => {
    if (!canViewReports) return;
    const targetRunKey = String(runKey || "").trim();
    if (!targetRunKey) return;
    setReportViewerRunKey(targetRunKey);
    setReportViewerData(null);
    setReportViewerError("");
    setReportViewerBusy(true);
    try {
      const next = await getAdminReportRunSummary(targetRunKey);
      setReportViewerData(next);
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      if (isForbiddenError(err)) {
        setReportViewerError("Insufficient permissions to view this report.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Failed to load report summary";
      setReportViewerError(msg);
    } finally {
      setReportViewerBusy(false);
    }
  }, [canViewReports, clearAdminSession, setError]);

  const handleDownloadReportFile = useCallback(async (runKey: string, fileName: string) => {
    const targetRunKey = String(runKey || "").trim();
    const targetFileName = String(fileName || "").trim();
    if (!targetRunKey || !targetFileName) return;
    setReportDownloadKey(targetFileName);
    try {
      await downloadAdminReportFile(targetRunKey, targetFileName);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Download failed";
      window.alert(`Failed to download ${targetFileName}: ${message}`);
    } finally {
      setReportDownloadKey("");
    }
  }, []);

  const handleDownloadReportZip = useCallback(async (runKey: string) => {
    const targetRunKey = String(runKey || "").trim();
    if (!targetRunKey) return;
    setReportDownloadKey("__zip__");
    try {
      await downloadAdminReportZip(targetRunKey);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Download failed";
      window.alert(`Failed to download ${targetRunKey} report bundle: ${message}`);
    } finally {
      setReportDownloadKey("");
    }
  }, []);

  const handleDeleteRun = useCallback(async (runKey: string) => {
    if (!canManageLogsReports) return;
    const targetRunKey = String(runKey || "").trim();
    if (!targetRunKey) return;
    setBusy(true);
    setError("");
    try {
      await deleteAdminLogRun(targetRunKey);
      if (logViewerRun?.run_key === targetRunKey) {
        closeLogViewer();
      }
      if (reportViewerRunKey === targetRunKey) {
        closeReportViewer();
      }
      await loadAdminData();
      setStatus(`Deleted ${targetRunKey}`);
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      if (isForbiddenError(err)) {
        setError("Insufficient permissions to delete logs and reports.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Delete failed";
      setError(msg);
      window.alert(`Failed to delete ${targetRunKey}: ${msg}`);
    } finally {
      setBusy(false);
    }
  }, [canManageLogsReports, logViewerRun, reportViewerRunKey, closeLogViewer, closeReportViewer, loadAdminData, clearAdminSession, setError]);

  const requestDeleteRun = useCallback((runKey: string) => {
    const targetRunKey = String(runKey || "").trim();
    if (!targetRunKey) return;
    showActionConfirm({
      title: "Delete Run Data",
      description: `This will remove ${targetRunKey} from Logs & Reports, including its report folder and run history stored in the database.`,
      confirmLabel: "Delete Run",
      cancelLabel: "Cancel",
      variant: "danger",
      onConfirm: async () => {
        await handleDeleteRun(targetRunKey);
      },
    });
  }, [showActionConfirm, handleDeleteRun]);

  const handleClearLogsAndReports = useCallback(async () => {
    if (!canManageLogsReports) return;
    setBusy(true);
    try {
      const result = await clearAdminLogs(false);
      const details = [
        `Cleared ${result.deleted_logs} log runs`,
        `${result.deleted_reports} report folders`,
        `${result.deleted_report_rows} report records`,
      ];
      if (result.deleted_log_files > 0) {
        details.push(`${result.deleted_log_files} auxiliary log files`);
      }
      if (result.deleted_report_files > 0) {
        details.push(`${result.deleted_report_files} report file records`);
      }
      if (typeof result.deleted_run_rows === "number" && result.deleted_run_rows > 0) {
        details.push(`${result.deleted_run_rows} run records`);
      }
      if (typeof result.deleted_pair_segments === "number" && result.deleted_pair_segments > 0) {
        details.push(`${result.deleted_pair_segments} pair history rows`);
      }
      if (typeof result.deleted_trades === "number" && result.deleted_trades > 0) {
        details.push(`${result.deleted_trades} trade rows`);
      }
      if (result.deleted_indexes > 0) {
        details.push(`${result.deleted_indexes} derived indexes`);
      }
      if (result.errors.length > 0) {
        details.push(`${result.errors.length} cleanup errors`);
      }
      alert(`${details.join(", ")}.`);
      closeReportViewer();
      await loadAdminData();
    } catch (err) {
      if (isForbiddenError(err)) {
        setError("Insufficient permissions to clear logs and reports.");
        return;
      }
      alert("Failed to clear logs and reports: " + (err instanceof Error ? err.message : "Unknown error"));
    } finally {
      setBusy(false);
    }
  }, [canManageLogsReports, closeReportViewer, loadAdminData, setError]);

  const requestClearLogsAndReports = useCallback(() => {
    showActionConfirm({
      title: "Clear All",
      description: "This will permanently remove all log runs, all report folders, and their related database history, including the most recent run.",
      confirmLabel: "Clear Everything",
      cancelLabel: "Cancel",
      variant: "danger",
      onConfirm: async () => {
        await handleClearLogsAndReports();
      },
    });
  }, [showActionConfirm, handleClearLogsAndReports]);

  const handleClearActivePair = useCallback(async () => {
    if (!canSwitchActivePair) return;
    setBusy(true);
    setError("");
    try {
      const result = await clearAdminActivePair();
      await loadAdminData();
      setStatus(result.detail || "Persisted active pair cleared");
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      if (isForbiddenError(err)) {
        setError("Insufficient permissions to clear the active pair.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Clear active pair failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }, [canSwitchActivePair, loadAdminData, clearAdminSession, setError]);

  const requestClearActivePair = useCallback(() => {
    showActionConfirm({
      title: "Clear Active Pair",
      description:
        "This clears the saved active pair from disk so the next startup falls back to defaults or discovers a new pair. If the bot is already running, its in-memory pair will stay active until restart.",
      confirmLabel: "Clear Pair",
      cancelLabel: "Cancel",
      variant: "danger",
      onConfirm: async () => {
        await handleClearActivePair();
      },
    });
  }, [showActionConfirm, handleClearActivePair]);

  const handleRemoveGraveyardPair = useCallback(async (pair: string) => {
    if (!canManagePairSupply) return;
    const targetPair = String(pair || "").trim();
    if (!targetPair) return;
    setGraveyardRemoveBusyPair(targetPair);
    setError("");
    try {
      const result = await removePairFromGraveyard(targetPair);
      setPairsHealth(result.health);
      setStatus(result.removed ? `Removed ${result.pair_key} from graveyard` : `${result.pair_key} was not in graveyard`);
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearAdminSession("Session expired. Please sign in again.", true);
        setError("Session expired. Please sign in again.");
        return;
      }
      if (isForbiddenError(err)) {
        setError("Insufficient permissions to remove graveyard pairs.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Remove graveyard pair failed";
      setError(msg);
    } finally {
      setGraveyardRemoveBusyPair("");
    }
  }, [canManagePairSupply, clearAdminSession, setError, setPairsHealth, setStatus]);

  const requestRemoveGraveyardPair = useCallback((pair: string) => {
    const targetPair = String(pair || "").trim();
    if (!targetPair) return;
    showActionConfirm({
      title: "Remove From Graveyard",
      description: `Remove ${targetPair} from Pair Health graveyard? This only clears the pair-level exclusion from state.`,
      confirmLabel: "Remove Pair",
      cancelLabel: "Cancel",
      variant: "warning",
      onConfirm: async () => {
        await handleRemoveGraveyardPair(targetPair);
      },
    });
  }, [showActionConfirm, handleRemoveGraveyardPair]);

  useEffect(() => {
    if (artifactRunKeys.length === 0) {
      setSelectedArtifactsRunKey("");
      return;
    }
    if (!selectedArtifactsRunKey || !artifactRunKeys.includes(selectedArtifactsRunKey)) {
      setSelectedArtifactsRunKey(artifactRunKeys[0] || "");
    }
  }, [artifactRunKeys, selectedArtifactsRunKey]);

  useEffect(() => {
    if (!terminalFullscreen) {
      setTerminalSearchQuery("");
      setTerminalActiveMatchIndex(-1);
      return;
    }
    if (terminalSearchModel.totalMatches <= 0) {
      setTerminalActiveMatchIndex(-1);
      return;
    }
    setTerminalActiveMatchIndex((current) => (
      current >= 0 && current < terminalSearchModel.totalMatches ? current : 0
    ));
  }, [terminalFullscreen, terminalSearchModel.totalMatches]);

  useEffect(() => {
    setTerminalActiveMatchIndex(
      terminalSearchQuery.trim() && terminalSearchModel.totalMatches > 0 ? 0 : -1,
    );
  }, [terminalSearchQuery, terminalSearchModel.totalMatches]);

  useEffect(() => {
    if (!logViewerRun) {
      setLogViewerSearchQuery("");
      setLogViewerActiveMatchIndex(-1);
      return;
    }
    if (logViewerSearchModel.totalMatches <= 0) {
      setLogViewerActiveMatchIndex(-1);
      return;
    }
    setLogViewerActiveMatchIndex((current) => (
      current >= 0 && current < logViewerSearchModel.totalMatches ? current : 0
    ));
  }, [logViewerRun, logViewerSearchModel.totalMatches]);

  useEffect(() => {
    setLogViewerActiveMatchIndex(
      logViewerSearchQuery.trim() && logViewerSearchModel.totalMatches > 0 ? 0 : -1,
    );
  }, [logViewerSearchQuery, logViewerSearchModel.totalMatches]);

  useEffect(() => {
    if (!terminalFullscreen && !logViewerRun && !reportViewerRunKey) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "f") {
        event.preventDefault();
        if (logViewerRun) {
          logViewerSearchInputRef.current?.focus();
          return;
        }
        if (terminalFullscreen) {
          terminalSearchInputRef.current?.focus();
        }
        return;
      }
      if (event.key !== "Escape") return;
      if (reportViewerRunKey) {
        closeReportViewer();
        return;
      }
      if (logViewerRun) {
        closeLogViewer();
        return;
      }
      setTerminalFullscreen(false);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [terminalFullscreen, logViewerRun, reportViewerRunKey, closeLogViewer, closeReportViewer]);

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
          const [tail, runtimeData, statusData] = await Promise.all([
            getAdminBotLogTail(latestRunKey, 320),
            getAdminRunRuntime(latestRunKey),
            getAdminBotStatus(),
          ]);
          setLocalLogTail(tail);
          setRuntimeSnapshot(runtimeData);
          applyRuntimeMetrics(runtimeData);
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
    setRuntimeSnapshot,
    setRunningEquity,
    setStartingEquity,
    setSessionPnl,
    setRunUptime,
    setPairHistory,
    setPairCount,
    setBotStatus,
    setSelectedRunKey,
    applyRuntimeMetrics,
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
    setRuntimeSnapshot(null);
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
    setRuntimeSnapshot,
    setStatus,
    setError,
  ]);

  useEffect(() => {
    // SSE streaming - replaces polling when not floating
    if (!canViewConsole || !canViewLogs || isFloating) return;
    startStream(selectedRunKey || "latest");
    return () => stopStream();
  }, [canViewConsole, canViewLogs, selectedRunKey, isFloating, startStream, stopStream]);

  useEffect(() => {
    if (!waitingForRun) return;
    const resolvedRunKey = runtimeSnapshot?.run_key || localLogTail?.run_key || botStatus?.latest_run_key || "";
    if (!resolvedRunKey || resolvedRunKey === "latest" || resolvedRunKey === "__control__") return;
    setWaitingForRun(false);
    setLastKnownRunKey(null);
    if (!selectedRunKey || selectedRunKey === "latest") {
      setSelectedRunKey(resolvedRunKey);
    }
  }, [
    waitingForRun,
    runtimeSnapshot?.run_key,
    localLogTail?.run_key,
    botStatus?.latest_run_key,
    selectedRunKey,
    setSelectedRunKey,
  ]);

  // Poll structured runtime metadata from the event/DB pipeline while SSE handles terminal lines.
  useEffect(() => {
    if (!canViewConsole || !canViewLogs || isFloating) return;

    let isMounted = true;
    let inFlight = false;

    const pollRuntime = async () => {
      if (inFlight) return;
      inFlight = true;

      try {
        const runtimeData = await getAdminRunRuntime(selectedRunKey || "latest");
        if (!isMounted) return;
        setRuntimeSnapshot(runtimeData);
        applyRuntimeMetrics(runtimeData, {
          preserveStartingEquity: true,
          preserveRunningEquity: true,
          preserveRunUptime: true,
        });
      } catch {
        // Ignore errors
      } finally {
        inFlight = false;
      }
    };

    // Poll immediately then every 5 seconds
    pollRuntime();
    const timer = window.setInterval(pollRuntime, 5000);

    return () => {
      isMounted = false;
      window.clearInterval(timer);
    };
  }, [
    canViewConsole,
    canViewLogs,
    selectedRunKey,
    isFloating,
    setRuntimeSnapshot,
    applyRuntimeMetrics,
  ]);

  // Poll pairs health data
  useEffect(() => {
    if (!canViewConsole) return;

    let isMounted = true;
    let inFlight = false;
    const timer = window.setInterval(async () => {
      if (!canManageBot && !canViewLogs && !canSwitchActivePair && !canViewPairUniverse) return;
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
    canSwitchActivePair,
    canViewPairUniverse,
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
      const settled = await pollBotStatus(true);
      const effectiveStatus = settled || next;
      const nextRunKey = String(effectiveStatus.run_key || effectiveStatus.latest_run_key || "latest").trim() || "latest";
      if (nextRunKey !== "latest" && nextRunKey !== "__control__") {
        setWaitingForRun(false);
        setLastKnownRunKey(null);
      }
      setSelectedRunKey(nextRunKey);
      if (canViewLogs) {
        await refreshLogTail(nextRunKey);
      }
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
      await pollBotStatus(false);
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

  async function pollBotStatus(expectedRunning: boolean): Promise<AdminBotStatus | null> {
    let latest: AdminBotStatus | null = null;
    for (let attempt = 0; attempt < 12; attempt += 1) {
      await sleep(attempt === 0 ? 400 : 750);
      latest = await getAdminBotStatus();
      setBotStatus(latest);
      const latestTarget = latest.desired_running ?? latest.running;
      if (latestTarget === expectedRunning && latest.running === expectedRunning) break;
    }
    return latest;
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
  const contentLayoutClasses =
    activeTab === "control" || activeTab === "logs"
      ? "flex h-full min-h-0 flex-col gap-2 overflow-hidden"
      : "grid gap-2";

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
      <div className={contentLayoutClasses}>
        <section className={`${sectionCardClasses} shrink-0`}>
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
        <div className="shrink-0 flex flex-wrap gap-8 border-b border-gray-200 dark:border-gray-700">
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
            <section className="grid flex-1 min-h-0 overflow-hidden gap-2 lg:grid-cols-2 lg:auto-rows-fr">
              {/* Terminal - Left side */}
              <PanelCard
                className="flex h-full min-h-0 flex-col overflow-hidden"
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
                <div className="flex min-h-0 flex-1 flex-col">
                  {waitingForRun ? (
                    <p className="mb-2 text-xs text-amber-600 dark:text-amber-400">
                      Waiting for new run to start...
                    </p>
                  ) : streamError ? (
                    <p className="mb-2 text-xs text-amber-600 dark:text-amber-400">
                      {streamError}. Reconnecting...
                    </p>
                  ) : showingControlLog ? (
                    <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
                      Showing current startup/control output until a fresh run log is created.
                    </p>
                  ) : isStreaming ? (
                    <p className="mb-2 text-xs text-emerald-600 dark:text-emerald-400">
                      Live stream connected.
                    </p>
                  ) : null}
                  <pre className="custom-scrollbar mt-2 min-h-0 flex-1 overflow-auto rounded-xl border border-gray-700 bg-gray-950 p-3 text-xs leading-relaxed text-emerald-100" style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                    {displayLines.length > 0 ? displayLines.map((line, i) => <span key={i}>{line}<br /></span>) : "No log lines yet."}
                  </pre>
                </div>
              </PanelCard>

              {/* Bot Control - Right side */}
              <PanelCard
                className="flex h-full min-h-0 flex-col overflow-hidden"
                title="Bot Control"
                subtitle="Process status and run context."
                actions={
                  canManageBot ? (
                    <div className="flex gap-2">
                      <button
                        onClick={handleStart}
                        disabled={busy || botTargetRunning}
                        className={primaryButtonClasses}
                      >
                        {botTransitioning && botTargetRunning ? "Starting..." : "Start Bot"}
                      </button>
                      <button
                        className="inline-flex items-center rounded-xl border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
                        onClick={handleStop}
                        disabled={busy || !botTargetRunning}
                      >
                        {botTransitioning && !botTargetRunning ? "Stopping..." : "Stop Bot"}
                      </button>
                    </div>
                  ) : null
                }
              >
                <div className="flex min-h-0 flex-1 flex-col">
                  <div className="grid grid-cols-2 gap-x-6 gap-y-4">
                    <div className="border-b border-gray-200 pb-3 dark:border-gray-700">
                      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Status</p>
                      <div className="mt-1.5"><StatusPill label={botStatusLabel} tone={botStatusTone} /></div>
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
                      <p className="mt-1.5 font-mono text-sm text-gray-900 dark:text-white/90">{fmtUptime(runUptime, Boolean(selectedRunKey === "latest" || selectedRunKey === botStatus?.latest_run_key), Boolean(runtimeSnapshot?.running ?? botStatus?.running), runtimeUpdatedAt)}</p>
                    </div>
                    <div className="pt-1">
                      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Pairs Used</p>
                      <p className="mt-1.5 font-mono text-sm text-gray-900 dark:text-white/90">{pairCount}</p>
                    </div>
                    <div className="pt-1">
                      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Started</p>
                      <p className="mt-1.5 font-mono text-xs text-gray-600 dark:text-gray-400">{fmtDate(runtimeSnapshot?.started_at || botStatus?.started_at || null)}</p>
                    </div>
                    <div className="pt-1">
                      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Stopped</p>
                      <p className="mt-1.5 font-mono text-xs text-gray-600 dark:text-gray-400">{fmtDate(runtimeSnapshot?.stopped_at || botStatus?.stopped_at || null)}</p>
                    </div>
                    <div className="col-span-2">
                      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Select Run</p>
                      <select className="mt-1.5 w-full min-w-[180px] rounded border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-white/90" value={selectedRunKey} onChange={async (e) => {
                        const newKey = e.target.value;
                        setSelectedRunKey(newKey);
                        const [tail, runtimeData] = await Promise.all([
                          getAdminBotLogTail(newKey, 320),
                          getAdminRunRuntime(newKey),
                        ]);
                        setLocalLogTail(tail);
                        setRuntimeSnapshot(runtimeData);
                        applyRuntimeMetrics(runtimeData);
                      }}>
                        <option value="latest">latest</option>
                        {runKeyOptions}
                      </select>
                    </div>
                  </div>
                  <div className="mt-4 flex min-h-0 flex-1 flex-col border-t border-gray-200 pt-4 dark:border-gray-700">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Pair History</p>
                      <p className="text-xs text-gray-500 dark:text-gray-400">{pairHistory.length} pairs used in this run</p>
                    </div>
                    {pairHistory.length > 0 ? (
                      <TableFrame compact maxHeightClass="max-h-full" className="mt-2 min-h-0 flex-1">
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
                              const totalDuration = runtimeSnapshot?.duration_seconds
                                ? runtimeSnapshot.duration_seconds
                                : pairHistory.reduce((sum, p) => sum + p.duration_seconds, 0);
                              const pct = totalDuration > 0 ? (entry.duration_seconds / totalDuration) * 100 : 0;
                              return (
                                <tr key={`${entry.pair}-${idx}`}>
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
                    ) : (
                      <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">No pair history recorded yet.</p>
                    )}
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
              className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-700 bg-gray-800 px-4 py-3"
            >
              <div className="flex items-center gap-3">
                <h3 className="text-lg font-semibold text-white">Terminal</h3>
                <SearchBar
                  query={terminalSearchQuery}
                  onQueryChange={setTerminalSearchQuery}
                  totalMatches={terminalSearchModel.totalMatches}
                  activeMatchIndex={terminalActiveMatchIndex}
                  onPrev={() => setTerminalActiveMatchIndex((current) => nextSearchIndex(current, terminalSearchModel.totalMatches, -1))}
                  onNext={() => setTerminalActiveMatchIndex((current) => nextSearchIndex(current, terminalSearchModel.totalMatches, 1))}
                  inputRef={terminalSearchInputRef}
                />
              </div>
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
              ) : streamError ? (
                <p className="mb-2 text-xs text-amber-400">
                  {streamError}. Reconnecting...
                </p>
              ) : showingControlLog ? (
                <p className="mb-2 text-xs text-gray-400">
                  Showing current startup/control output until a fresh run log is created.
                </p>
              ) : isStreaming ? (
                <p className="mb-2 text-xs text-emerald-400">
                  Live stream connected.
                </p>
              ) : null}
              <SearchableTerminalContent
                lines={displayLines}
                emptyText="No log lines yet."
                searchModel={terminalSearchModel}
                activeMatchIndex={terminalActiveMatchIndex}
                className="custom-scrollbar flex-1 overflow-auto rounded-xl border border-gray-700 bg-gray-950 p-3 text-xs leading-relaxed text-emerald-100"
              />
            </div>
          </div>
        ) : null}

        </>
        )}

        {logViewerRun ? (
          <div className="fixed inset-0 z-[60] flex flex-col bg-gray-900">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-700 bg-gray-800 px-4 py-3">
              <div>
                <h3 className="text-lg font-semibold text-white">Log Viewer</h3>
                <p className="mt-1 font-mono text-xs text-gray-400">
                  {logViewerRun.run_key}
                  {logViewerData?.updated_at ? ` | Updated ${fmtDate(logViewerData.updated_at)}` : ""}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <SearchBar
                  query={logViewerSearchQuery}
                  onQueryChange={setLogViewerSearchQuery}
                  totalMatches={logViewerSearchModel.totalMatches}
                  activeMatchIndex={logViewerActiveMatchIndex}
                  onPrev={() => setLogViewerActiveMatchIndex((current) => nextSearchIndex(current, logViewerSearchModel.totalMatches, -1))}
                  onNext={() => setLogViewerActiveMatchIndex((current) => nextSearchIndex(current, logViewerSearchModel.totalMatches, 1))}
                  inputRef={logViewerSearchInputRef}
                />
                <button
                  onClick={closeLogViewer}
                  className="rounded px-3 py-1 text-sm font-medium text-gray-300 hover:bg-gray-700"
                >
                  Exit Fullscreen
                </button>
              </div>
            </div>
            <div className="flex flex-1 flex-col overflow-hidden p-4">
              {logViewerBusy ? (
                <p className="text-sm text-gray-300">Loading full log...</p>
              ) : logViewerError ? (
                <p className="text-sm text-red-300">{logViewerError}</p>
              ) : (
                <>
                  <div className="mb-2 flex flex-wrap items-center gap-3 text-xs text-gray-400">
                    <span>{fmtBytes(logViewerData?.size_bytes ?? logViewerRun.size_bytes)}</span>
                    <span>{(logViewerData?.line_count ?? 0).toLocaleString()} lines</span>
                  </div>
                  <SearchableTerminalContent
                    lines={logViewerLines}
                    emptyText="No log content found."
                    searchModel={logViewerSearchModel}
                    activeMatchIndex={logViewerActiveMatchIndex}
                    className="custom-scrollbar flex-1 overflow-auto rounded-xl border border-gray-700 bg-gray-950 p-3 font-mono text-xs leading-relaxed text-emerald-100"
                  />
                </>
              )}
            </div>
          </div>
        ) : null}

        {reportViewerRunKey ? (
          <div className="fixed inset-0 z-[60] flex flex-col bg-gray-100 dark:bg-gray-950">
            <div className="flex flex-wrap items-start justify-between gap-3 border-b border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-gray-900">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Report Summary</h3>
                <p className="mt-1 font-mono text-xs text-gray-500 dark:text-gray-400">
                  {reportViewerRunKey}
                  {reportViewerData?.generated_at ? ` | Generated ${fmtDate(reportViewerData.generated_at)}` : ""}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => void handleDownloadReportZip(reportViewerRunKey)}
                  disabled={reportViewerBusy || !!reportViewerError || reportDownloadKey === "__zip__"}
                  className="inline-flex items-center rounded-xl border border-brand-200 bg-brand-50 px-3 py-1.5 text-xs font-medium text-brand-700 hover:bg-brand-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-brand-900 dark:bg-brand-950/30 dark:text-brand-300 dark:hover:bg-brand-950/40"
                >
                  {reportDownloadKey === "__zip__" ? "Preparing ZIP..." : "Download All ZIP"}
                </button>
                <button
                  onClick={closeReportViewer}
                  className="rounded px-3 py-1 text-sm font-medium text-gray-500 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
                >
                  Exit Fullscreen
                </button>
              </div>
            </div>
            <div className="flex flex-1 flex-col overflow-hidden p-4">
              {reportViewerBusy ? (
                <p className="text-sm text-gray-600 dark:text-gray-300">Loading report summary...</p>
              ) : reportViewerError ? (
                <p className="text-sm text-red-600 dark:text-red-300">{reportViewerError}</p>
              ) : !reportViewerData ? (
                <p className="text-sm text-gray-500 dark:text-gray-400">No report summary available.</p>
              ) : (
                <div className="grid flex-1 min-h-0 gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(320px,0.95fr)]">
                  <div className="flex min-h-0 flex-col gap-4">
                    <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                      <article className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Status</p>
                        <div className="mt-2 flex items-center gap-2">
                          <StatusPill
                            label={readRecordString(reportSummary, "status") || "unknown"}
                            tone={readRecordString(reportSummary, "status") === "running" ? "success" : "neutral"}
                          />
                          {reportViewerData.refreshed ? <StatusPill label="refreshed" tone="info" /> : null}
                        </div>
                        <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                          {reportViewerData.report_version || "report version unavailable"}
                        </p>
                      </article>
                      <article className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Session PnL</p>
                        <p className="mt-2 font-mono text-lg font-semibold text-gray-900 dark:text-white">
                          {fmtCurrency(readRecordNumber(reportSummary, "session_pnl"))}
                        </p>
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          {fmtPercent(readRecordNumber(reportSummary, "session_pnl_pct"))}
                        </p>
                      </article>
                      <article className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Duration</p>
                        <p className="mt-2 font-mono text-lg font-semibold text-gray-900 dark:text-white">
                          {fmtDuration(readRecordNumber(reportSummary, "duration_seconds") ?? 0)}
                        </p>
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          Started {fmtDate(readRecordString(reportSummary, "start_time"))}
                        </p>
                      </article>
                      <article className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Trades</p>
                        <p className="mt-2 font-mono text-lg font-semibold text-gray-900 dark:text-white">
                          {fmtNumber(reportTradesTotal, 0)}
                        </p>
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          {fmtNumber(reportClosedTradesTotal, 0)} closed / {fmtNumber(reportOpenTradesTotal, 0)} open
                          {" | "}
                          Win rate {fmtPercent(readRecordNumber(reportSummary, "win_rate_pct"))}
                        </p>
                      </article>
                      <article className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Pair Activity</p>
                        <p className="mt-2 font-mono text-lg font-semibold text-gray-900 dark:text-white">
                          {fmtNumber(readRecordNumber(reportSummary, "pair_switches"), 0)} switches
                        </p>
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          {fmtNumber(readRecordNumber(reportSummary, "pair_count"), 0)} pairs tracked
                        </p>
                      </article>
                      <article className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Alerts</p>
                        <p className="mt-2 font-mono text-lg font-semibold text-gray-900 dark:text-white">
                          {fmtNumber(readRecordNumber(reportSummary, "alert_rows"), 0)}
                        </p>
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          Gate blocks {fmtNumber(readRecordNumber(reportSummary, "gate_blocks"), 0)}
                        </p>
                      </article>
                    </section>

                    <PanelCard
                      title="Overview"
                      subtitle="This summary comes from the live event-backed report pack for the selected run."
                      className="shrink-0"
                    >
                      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Current Pair</p>
                          <p className="mt-1 font-mono text-xs text-gray-900 dark:text-white/90">{readRecordString(reportSummary, "current_pair") || "n/a"}</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Latest Strategy</p>
                          <p className="mt-1 text-sm text-gray-900 dark:text-white/90">{readRecordString(reportSummary, "latest_strategy") || "n/a"}</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Latest Regime</p>
                          <p className="mt-1 text-sm text-gray-900 dark:text-white/90">{readRecordString(reportSummary, "latest_regime") || "n/a"}</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Starting Equity</p>
                          <p className="mt-1 font-mono text-sm text-gray-900 dark:text-white/90">{fmtCurrency(readRecordNumber(reportSummary, "starting_equity"))}</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Ending Equity</p>
                          <p className="mt-1 font-mono text-sm text-gray-900 dark:text-white/90">{fmtCurrency(readRecordNumber(reportSummary, "ending_equity"))}</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Report Source</p>
                          <p className="mt-1 text-sm text-gray-900 dark:text-white/90">{reportViewerData.report_source || "n/a"}</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Closed Wins</p>
                          <p className="mt-1 text-sm text-gray-900 dark:text-white/90">{fmtNumber(readRecordNumber(reportSummary, "wins"), 0)}</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Closed Losses</p>
                          <p className="mt-1 text-sm text-gray-900 dark:text-white/90">{fmtNumber(readRecordNumber(reportSummary, "losses"), 0)}</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Trade Opens</p>
                          <p className="mt-1 text-sm text-gray-900 dark:text-white/90">{fmtNumber(reportTradeOpensTotal, 0)}</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Open Trades</p>
                          <p className="mt-1 text-sm text-gray-900 dark:text-white/90">{fmtNumber(reportOpenTradesTotal, 0)}</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Closed Trades</p>
                          <p className="mt-1 text-sm text-gray-900 dark:text-white/90">{fmtNumber(reportClosedTradesTotal, 0)}</p>
                        </div>
                        <div>
                          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Updated At</p>
                          <p className="mt-1 text-sm text-gray-900 dark:text-white/90">
                            {fmtDate(readRecordString(reportSummary, "updated_at") || reportViewerData.generated_at)}
                          </p>
                        </div>
                      </div>
                    </PanelCard>

                    <div className="grid flex-1 min-h-0 gap-4 lg:grid-cols-2">
                      <PanelCard title="Data Sources" subtitle="Each section shows where the report data came from." className="flex min-h-0 flex-col overflow-hidden">
                        <TableFrame compact maxHeightClass="max-h-full" className="min-h-0 flex-1">
                          <table className="text-xs">
                            <thead>
                              <tr>
                                <th>Section</th>
                                <th>Source</th>
                              </tr>
                            </thead>
                            <tbody>
                              {reportDataSources.map(([section, source]) => (
                                <tr key={section}>
                                  <td className="font-medium">{section.replace(/_/g, " ")}</td>
                                  <td>
                                    <StatusPill
                                      label={String(source || "none")}
                                      tone={String(source || "").toLowerCase() === "none" ? "neutral" : "info"}
                                    />
                                  </td>
                                </tr>
                              ))}
                              {!reportDataSources.length ? (
                                <tr>
                                  <td colSpan={2} className="text-xs text-gray-500 dark:text-gray-400">
                                    No data-source metadata available.
                                  </td>
                                </tr>
                              ) : null}
                            </tbody>
                          </table>
                        </TableFrame>
                      </PanelCard>

                      <PanelCard title="Event Signals" subtitle="Quick counts from the live event stream." className="flex min-h-0 flex-col overflow-hidden">
                        <div className="grid min-h-0 flex-1 gap-4 md:grid-cols-2">
                          <div className="flex min-h-0 flex-col overflow-hidden">
                            <h4 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Top Events</h4>
                            <TableFrame compact maxHeightClass="max-h-full" className="min-h-0 flex-1">
                              <table className="text-xs">
                                <thead>
                                  <tr>
                                    <th>Event</th>
                                    <th>Count</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {reportEventCounts.slice(0, 8).map((row) => (
                                    <tr key={row.key}>
                                      <td className="font-medium">{row.key}</td>
                                      <td>{fmtNumber(row.count, 0)}</td>
                                    </tr>
                                  ))}
                                  {!reportEventCounts.length ? (
                                    <tr>
                                      <td colSpan={2} className="text-xs text-gray-500 dark:text-gray-400">
                                        No event counts available.
                                      </td>
                                    </tr>
                                  ) : null}
                                </tbody>
                              </table>
                            </TableFrame>
                          </div>
                          <div className="flex min-h-0 flex-col overflow-hidden">
                            <h4 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Severity Mix</h4>
                            <TableFrame compact maxHeightClass="max-h-full" className="min-h-0 flex-1">
                              <table className="text-xs">
                                <thead>
                                  <tr>
                                    <th>Severity</th>
                                    <th>Count</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {reportSeverityCounts.map((row) => (
                                    <tr key={row.key}>
                                      <td>
                                        <StatusPill
                                          label={row.key}
                                          tone={row.key === "error" || row.key === "critical" ? "danger" : row.key === "warn" ? "warn" : "info"}
                                        />
                                      </td>
                                      <td>{fmtNumber(row.count, 0)}</td>
                                    </tr>
                                  ))}
                                  {!reportSeverityCounts.length ? (
                                    <tr>
                                      <td colSpan={2} className="text-xs text-gray-500 dark:text-gray-400">
                                        No severity counts available.
                                      </td>
                                    </tr>
                                  ) : null}
                                </tbody>
                              </table>
                            </TableFrame>
                          </div>
                        </div>
                      </PanelCard>
                    </div>
                  </div>

                  <div className="flex min-h-0 flex-col gap-4">
                    <PanelCard
                      title="Artifacts"
                      subtitle="Download the generated source files for this run individually, or take the whole pack as a ZIP."
                      className="flex min-h-0 flex-col overflow-hidden"
                    >
                      <TableFrame compact maxHeightClass="max-h-full" className="min-h-0 flex-1">
                        <table className="text-xs">
                          <thead>
                            <tr>
                              <th>File</th>
                              <th>Format</th>
                              <th>Rows</th>
                              <th>Size</th>
                              <th>Action</th>
                            </tr>
                          </thead>
                          <tbody>
                            {reportViewerData.files.map((file) => (
                              <tr key={file.name}>
                                <td className="font-mono text-[11px] text-gray-700 dark:text-gray-300">{file.name}</td>
                                <td>
                                  <StatusPill label={String(file.format || "file")} tone={artifactTone(file)} />
                                </td>
                                <td>{file.rows === null || file.rows === undefined ? "n/a" : fmtNumber(file.rows, 0)}</td>
                                <td>{fmtBytes(file.size_bytes)}</td>
                                <td>
                                  <button
                                    type="button"
                                    onClick={() => void handleDownloadReportFile(reportViewerRunKey, file.name)}
                                    disabled={!!reportDownloadKey}
                                    className="inline-flex items-center rounded-lg border border-gray-300 px-2.5 py-1 text-[11px] font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:text-gray-200 dark:hover:bg-gray-800"
                                  >
                                    {reportDownloadKey === file.name ? "Downloading..." : "Download"}
                                  </button>
                                </td>
                              </tr>
                            ))}
                            {!reportViewerData.files.length ? (
                              <tr>
                                <td colSpan={5} className="text-xs text-gray-500 dark:text-gray-400">
                                  No downloadable report artifacts found for this run.
                                </td>
                              </tr>
                            ) : null}
                          </tbody>
                        </table>
                      </TableFrame>
                    </PanelCard>

                    <PanelCard title="Report Notes" subtitle="Quick metadata for this pack." className="shrink-0">
                      <div className="space-y-3 text-sm text-gray-600 dark:text-gray-300">
                        <div className="flex items-start justify-between gap-3">
                          <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Path</span>
                          <span className="max-w-[70%] break-all font-mono text-[11px] text-right text-gray-700 dark:text-gray-300">
                            {reportViewerData.path}
                          </span>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Files</span>
                          <span className="font-mono text-sm text-gray-900 dark:text-white">{fmtNumber(reportViewerData.files.length, 0)}</span>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Summary</span>
                          <StatusPill label={reportViewerData.summary_available ? "available" : "missing"} tone={reportViewerData.summary_available ? "success" : "warn"} />
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">Created</span>
                          <span className="text-right text-sm text-gray-900 dark:text-white">{fmtDate(reportViewerData.generated_at)}</span>
                        </div>
                      </div>
                    </PanelCard>
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : null}

        {activeTab === "logs" && (
          <section className="flex flex-1 min-h-0 flex-col gap-2 overflow-hidden">
            {canManageLogsReports ? (
              <div className="shrink-0 flex justify-end">
                <button
                  className="rounded bg-red-600 px-3 py-1.5 text-xs text-white hover:bg-red-700 dark:bg-red-700 dark:hover:bg-red-600"
                  onClick={requestClearLogsAndReports}
                  disabled={busy}
                >
                  Clear Logs and Reports
                </button>
              </div>
            ) : null}
            <PanelCard
              title="Logs & Reports"
              subtitle="View full logs from the run name. Deleting the selected run clears both its log and report data."
              className="flex h-full min-h-0 flex-col overflow-hidden"
              actions={
                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center rounded-full border border-gray-300 bg-white px-3 py-1 font-mono text-xs text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
                    {selectedArtifactsRunKey || "No run selected"}
                  </span>
                  {canManageLogsReports ? (
                    <button
                      type="button"
                      onClick={() => requestDeleteRun(selectedArtifactsRunKey)}
                      disabled={busy || !selectedArtifactsRunKey}
                      className="inline-flex items-center rounded-xl border border-red-300 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-900 dark:bg-red-950/20 dark:text-red-300 dark:hover:bg-red-950/40"
                    >
                      Delete Selected Run
                    </button>
                  ) : null}
                </div>
              }
            >
              <div className="grid flex-1 min-h-0 overflow-hidden gap-2 xl:grid-cols-2 xl:auto-rows-fr">
                <div className="flex h-full min-h-0 flex-col overflow-hidden">
                  <div className="mb-3">
                    <h4 className="text-sm font-semibold text-gray-900 dark:text-white/90">All Logs</h4>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Click a run name to open the full terminal log.</p>
                  </div>
                  <TableFrame compact maxHeightClass="max-h-full" className="min-h-0 flex-1">
                    <table className="text-xs">
                      <thead>
                        <tr>
                          <th className="h-9 py-0 align-middle">Run</th>
                          <th className="h-9 py-0 align-middle">Size</th>
                          <th className="h-9 py-0 align-middle">Updated</th>
                        </tr>
                      </thead>
                      <tbody>
                        {logRuns.map((row) => (
                          <tr
                            key={row.run_key}
                            onClick={() => setSelectedArtifactsRunKey(row.run_key)}
                            className={selectedArtifactsRunKey === row.run_key ? "cursor-pointer bg-brand-50/80 dark:bg-brand-950/20" : "cursor-pointer"}
                          >
                            <td className="h-10 py-0 align-middle">
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setSelectedArtifactsRunKey(row.run_key);
                                  void handleOpenLogViewer(row);
                                }}
                                className="inline-flex items-center font-mono text-left text-xs leading-none text-brand-600 hover:underline dark:text-brand-400"
                                title={`View ${row.run_key}`}
                              >
                                {row.run_key}
                              </button>
                            </td>
                            <td className="h-10 py-0 align-middle">{fmtBytes(row.size_bytes)}</td>
                            <td className="h-10 py-0 align-middle">{fmtUnix(row.mtime_ts)}</td>
                          </tr>
                        ))}
                        {!logRuns.length ? (
                          <tr>
                            <td colSpan={3} className="h-10 py-0 align-middle text-xs text-gray-500 dark:text-gray-400">
                              No log runs found.
                            </td>
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                  </TableFrame>
                </div>

                <div className="flex h-full min-h-0 flex-col overflow-hidden">
                  <div className="mb-3">
                    <h4 className="text-sm font-semibold text-gray-900 dark:text-white/90">All Reports</h4>
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Select the matching run here when you want the shared delete action to remove both artifacts.</p>
                  </div>
                  <TableFrame compact maxHeightClass="max-h-full" className="min-h-0 flex-1">
                    <table className="text-xs">
                      <thead>
                        <tr>
                          <th className="h-9 py-0 align-middle">Run</th>
                          <th className="h-9 py-0 align-middle">Files</th>
                          <th className="h-9 py-0 align-middle">Summary</th>
                          <th className="h-9 py-0 align-middle">Updated</th>
                        </tr>
                      </thead>
                      <tbody>
                        {reportRuns.map((row) => (
                          <tr
                            key={row.run_key}
                            onClick={() => setSelectedArtifactsRunKey(row.run_key)}
                            className={selectedArtifactsRunKey === row.run_key ? "cursor-pointer bg-brand-50/80 dark:bg-brand-950/20" : "cursor-pointer"}
                          >
                            <td className="h-10 py-0 align-middle">
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setSelectedArtifactsRunKey(row.run_key);
                                  void handleOpenReportViewer(row.run_key);
                                }}
                                className="inline-flex items-center font-mono text-left text-xs leading-none text-brand-600 hover:underline dark:text-brand-400"
                                title={`View ${row.run_key} report`}
                              >
                                {row.run_key}
                              </button>
                            </td>
                            <td className="h-10 py-0 align-middle">{row.file_count}</td>
                            <td className="h-10 py-0 align-middle">
                              <span
                                className={
                                  row.summary_json
                                    ? "inline-flex items-center rounded-full border border-success-200 bg-success-50 px-2 py-0.5 text-[10px] font-semibold uppercase leading-none tracking-[0.08em] text-success-700 dark:border-success-900 dark:bg-success-950/20 dark:text-success-400"
                                    : "inline-flex items-center rounded-full border border-warning-200 bg-warning-50 px-2 py-0.5 text-[10px] font-semibold uppercase leading-none tracking-[0.08em] text-warning-700 dark:border-warning-900 dark:bg-warning-950/20 dark:text-warning-400"
                                }
                              >
                                {row.summary_json ? "available" : "missing"}
                              </span>
                            </td>
                            <td className="h-10 py-0 align-middle">{fmtUnix(row.mtime_ts)}</td>
                          </tr>
                        ))}
                        {!reportRuns.length ? (
                          <tr>
                            <td colSpan={4} className="h-10 py-0 align-middle text-xs text-gray-500 dark:text-gray-400">
                              No report runs found.
                            </td>
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                  </TableFrame>
                </div>
              </div>
            </PanelCard>
          </section>
        )}

        {activeTab === "pairs" && (
          <section className="grid gap-4">
            {/* Active Pair */}
            <PanelCard
              title="Active Pair"
              actions={
                canSwitchActivePair ? (
                  <button
                    type="button"
                    onClick={requestClearActivePair}
                    disabled={busy || !pairsHealth?.active_pair}
                    className="inline-flex items-center rounded-xl border border-red-300 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-900 dark:bg-red-950/20 dark:text-red-300 dark:hover:bg-red-950/40"
                  >
                    Clear Active Pair
                  </button>
                ) : null
              }
            >
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
                      <th>Action</th>
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
                        <td className="text-xs">
                          {canManagePairSupply ? (
                            <button
                              type="button"
                              onClick={() => requestRemoveGraveyardPair(entry.pair)}
                              disabled={graveyardRemoveBusyPair === entry.pair}
                              className="inline-flex items-center rounded-xl border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-800 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-amber-900 dark:bg-amber-950/20 dark:text-amber-300 dark:hover:bg-amber-950/40"
                            >
                              {graveyardRemoveBusyPair === entry.pair ? "Removing..." : "Remove"}
                            </button>
                          ) : (
                            <span className="text-gray-400 dark:text-gray-500">No access</span>
                          )}
                        </td>
                      </tr>
                    ))}
                    {!pairsHealth?.graveyard?.length ? (
                      <tr>
                        <td colSpan={5} className="text-sm text-gray-500 dark:text-gray-400">
                          No pairs in graveyard
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </TableFrame>
            </PanelCard>

            <PanelCard
              title="Ticker Graveyard"
              subtitle={`${pairsHealth?.restricted_tickers?.length || 0} excluded tickers`}
            >
              <TableFrame>
                <table>
                  <thead>
                    <tr>
                      <th>Ticker</th>
                      <th>Reason</th>
                      <th>Detail</th>
                      <th>Source</th>
                      <th>Added</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pairsHealth?.restricted_tickers?.map((entry) => (
                      <tr key={entry.ticker}>
                        <td className="font-mono text-xs">{entry.ticker}</td>
                        <td className="text-xs">{entry.reason}</td>
                        <td className="text-xs">{entry.message || entry.code || "n/a"}</td>
                        <td className="text-xs">{entry.source}</td>
                        <td className="text-xs">
                          {entry.added_at ? new Date(entry.added_at * 1000).toLocaleDateString() : "n/a"}
                        </td>
                      </tr>
                    ))}
                    {!pairsHealth?.restricted_tickers?.length ? (
                      <tr>
                        <td colSpan={5} className="text-sm text-gray-500 dark:text-gray-400">
                          No restricted tickers
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
      {actionConfirmDialog}
    </DashboardShell>
  );
}
