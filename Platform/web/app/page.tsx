"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import {
  ConfigSnapshotResponse,
  DataQualitySummary,
  RunEvent,
  RunReportArtifact,
  RunSummary,
  ScorecardCell,
  Trade,
  WalkForwardPoint,
  apiBaseUrl,
  apiRootUrl,
  getRunConfigSnapshot,
  getRunDataQuality,
  getRunEvents,
  getRunReportArtifacts,
  getRunScorecard,
  getRunTrades,
  getRunWalkForward,
  getRuns,
  isUnauthorizedError,
  login,
  wsDashboardUrl,
} from "../lib/api";
import { DashboardShell } from "../components/dashboard-shell";
import { MetricCard, PanelCard, StatusPill, TableFrame } from "../components/panels";
import {
  clearStoredAdminSession,
  getStoredAdminAccessToken,
  getStoredAdminRefreshToken,
  persistAdminSession,
} from "../lib/auth";

type LiveMsg = {
  event_type?: string;
  ts?: number;
  severity?: string;
  payload?: Record<string, unknown>;
};

type TimelineCategory = "switch" | "gate" | "alert" | "exit" | "other";
type TimelineSource = "history" | "live";
type TimelineFilterCategory = "all" | "core" | TimelineCategory;
type TimelineSeverity = "all" | "info" | "warn" | "error" | "critical";
type RunPnlFilter = "all" | "positive" | "negative";
type ChartWindow = "30" | "80" | "all";

type TimelineEvent = {
  id: string;
  source: TimelineSource;
  eventType: string;
  severity: Exclude<TimelineSeverity, "all">;
  tsMs: number;
  category: TimelineCategory;
  summary: string;
};

function fmtNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return value.toFixed(digits);
}

function fmtSignedNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`;
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return "n/a";
  return dt.toLocaleString();
}

function fmtDuration(startIso: string, endIso: string | null): string {
  const start = new Date(startIso).getTime();
  const end = endIso ? new Date(endIso).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return "n/a";
  const sec = Math.floor((end - start) / 1000);
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  return `${h}h ${m}m`;
}

function fmtBytes(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(2)} MB`;
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return value as Record<string, unknown>;
}

function normalizeSeverity(value: unknown): Exclude<TimelineSeverity, "all"> {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "warn") return "warn";
  if (normalized === "error") return "error";
  if (normalized === "critical") return "critical";
  return "info";
}

function classifyEventType(eventType: string, severity: Exclude<TimelineSeverity, "all">): TimelineCategory {
  const text = eventType.toLowerCase();
  if (
    text.includes("pair_switch") ||
    text.includes("strategy_change") ||
    text.includes("strategy_update") ||
    text.includes("regime_change") ||
    text.includes("regime_update")
  ) {
    return "switch";
  }
  if (
    text.includes("gate") ||
    text.includes("blocked") ||
    text.includes("coint_lost") ||
    text.includes("mean_shift")
  ) {
    return "gate";
  }
  if (text.includes("trade_close") || text.includes("exit") || text.includes("stop_loss") || text.includes("profit")) {
    return "exit";
  }
  if (text.includes("alert") || severity !== "info") {
    return "alert";
  }
  return "other";
}

function summarizePayload(payload: Record<string, unknown>): string {
  const parts: string[] = [];
  const reason = payload.reason || payload.reason_code || payload.alert_type;
  if (reason) parts.push(`reason=${String(reason)}`);
  if (payload.pair) parts.push(`pair=${String(payload.pair)}`);
  if (payload.strategy) parts.push(`strategy=${String(payload.strategy)}`);
  if (payload.regime) parts.push(`regime=${String(payload.regime)}`);
  if (payload.exit_tier) parts.push(`exit=${String(payload.exit_tier)}`);
  if (payload.gate) parts.push(`gate=${String(payload.gate)}`);

  const pnl = payload.pnl_usdt;
  if (typeof pnl === "number" && Number.isFinite(pnl)) {
    parts.push(`pnl=${pnl.toFixed(2)}`);
  } else if (typeof pnl === "string" && pnl.trim()) {
    parts.push(`pnl=${pnl}`);
  }

  if (payload.message && !parts.length) parts.push(String(payload.message));
  return parts.join(" | ");
}

function normalizeHistoryEvent(ev: RunEvent): TimelineEvent {
  const severity = normalizeSeverity(ev.severity);
  const eventType = String(ev.event_type || "event");
  const payload = asRecord(ev.payload_json);
  const tsMs = Number.isFinite(Date.parse(ev.ts)) ? Date.parse(ev.ts) : Date.now();
  return {
    id: `history-${ev.event_id}`,
    source: "history",
    eventType,
    severity,
    tsMs,
    category: classifyEventType(eventType, severity),
    summary: summarizePayload(payload),
  };
}

function normalizeLiveEvent(msg: LiveMsg, idx: number): TimelineEvent {
  const payload = asRecord(msg.payload);
  const severity = normalizeSeverity(msg.severity || payload.severity);
  const eventType = String(msg.event_type || "event");
  const tsMs = typeof msg.ts === "number" && Number.isFinite(msg.ts) ? Math.floor(msg.ts * 1000) : Date.now() - idx * 10;
  return {
    id: `live-${eventType}-${tsMs}-${idx}`,
    source: "live",
    eventType,
    severity,
    tsMs,
    category: classifyEventType(eventType, severity),
    summary: summarizePayload(payload),
  };
}

function qualityClass(status: string | null | undefined): string {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "pass") {
    return "border border-success-200 bg-success-50 text-success-700 dark:border-success-900 dark:bg-success-950/20 dark:text-success-400";
  }
  if (normalized === "warn" || normalized === "unknown") {
    return "border border-warning-200 bg-warning-50 text-warning-700 dark:border-warning-900 dark:bg-warning-950/20 dark:text-warning-400";
  }
  return "border border-error-200 bg-error-50 text-error-700 dark:border-error-900 dark:bg-error-950/20 dark:text-error-400";
}

function eventSeverityClass(severity: Exclude<TimelineSeverity, "all">): string {
  switch (severity) {
    case "critical":
    case "error":
      return "border-error-200 bg-error-50 text-error-700 dark:border-error-900 dark:bg-error-950/20 dark:text-error-400";
    case "warn":
      return "border-warning-200 bg-warning-50 text-warning-700 dark:border-warning-900 dark:bg-warning-950/20 dark:text-warning-400";
    default:
      return "border-blue-light-200 bg-blue-light-50 text-blue-light-700 dark:border-blue-light-900 dark:bg-blue-light-950/20 dark:text-blue-light-400";
  }
}

function eventCategoryClass(category: TimelineCategory): string {
  switch (category) {
    case "switch":
      return "border-brand-200 bg-brand-50 text-brand-700 dark:border-brand-900 dark:bg-brand-950/20 dark:text-brand-300";
    case "gate":
      return "border-warning-200 bg-warning-50 text-warning-700 dark:border-warning-900 dark:bg-warning-950/20 dark:text-warning-400";
    case "alert":
      return "border-error-200 bg-error-50 text-error-700 dark:border-error-900 dark:bg-error-950/20 dark:text-error-400";
    case "exit":
      return "border-success-200 bg-success-50 text-success-700 dark:border-success-900 dark:bg-success-950/20 dark:text-success-400";
    default:
      return "border-gray-200 bg-gray-50 text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300";
  }
}

function deltaChipClass(delta: number): string {
  return `inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] ${
    delta >= 0
      ? "border-success-200 bg-success-50 text-success-700 dark:border-success-900 dark:bg-success-950/20 dark:text-success-400"
      : "border-error-200 bg-error-50 text-error-700 dark:border-error-900 dark:bg-error-950/20 dark:text-error-400"
  }`;
}

function statusTone(value: string | null | undefined): "success" | "warn" | "error" | "info" {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) return "info";
  if (
    normalized.includes("running") ||
    normalized.includes("pass") ||
    normalized.includes("active") ||
    normalized.includes("ok") ||
    normalized.includes("success") ||
    normalized.includes("done")
  ) {
    return "success";
  }
  if (
    normalized.includes("warn") ||
    normalized.includes("pending") ||
    normalized.includes("queue") ||
    normalized.includes("start") ||
    normalized.includes("refresh")
  ) {
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

type ChartPoint = {
  x: number;
  y: number;
  value: number;
  label: string;
};

function buildChartPoints(values: number[], labels: string[], width = 620, height = 190): ChartPoint[] {
  if (!values.length) return [];
  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  const spread = maxVal - minVal || 1;
  return values.map((value, idx) => {
    const x = values.length === 1 ? width / 2 : (idx / (values.length - 1)) * width;
    const y = height - ((value - minVal) / spread) * height;
    return {
      x,
      y,
      value,
      label: labels[idx] || "",
    };
  });
}

function pointsToPath(points: ChartPoint[]): string {
  if (!points.length) return "";
  return points
    .map((point, idx) => `${idx === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");
}

function pointsToAreaPath(points: ChartPoint[], height = 190): string {
  if (!points.length) return "";
  const linePath = pointsToPath(points);
  const first = points[0];
  const last = points[points.length - 1];
  return `${linePath} L ${last.x.toFixed(2)} ${height.toFixed(2)} L ${first.x.toFixed(2)} ${height.toFixed(2)} Z`;
}

function AttributionTable({ scorecard }: { scorecard: ScorecardCell[] }) {
  if (!scorecard.length) return <p className="text-sm text-gray-500 dark:text-gray-400">No attribution rows yet.</p>;
  return (
    <TableFrame compact>
      <table>
        <thead>
          <tr>
            <th>Strategy</th>
            <th>Regime</th>
            <th>Trades</th>
            <th>Win Rate</th>
            <th>Avg PnL</th>
            <th>Total PnL</th>
          </tr>
        </thead>
        <tbody>
          {scorecard.map((row, idx) => (
            <tr key={`${row.entry_strategy || "na"}-${row.entry_regime || "na"}-${idx}`}>
              <td>{row.entry_strategy || "n/a"}</td>
              <td>{row.entry_regime || "n/a"}</td>
              <td>{row.trades}</td>
              <td>{fmtNumber(row.win_rate_pct)}%</td>
              <td>{fmtNumber(row.avg_pnl_usdt)}</td>
              <td>{fmtNumber(row.sum_pnl_usdt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableFrame>
  );
}

export default function HomePage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@okxstatbot.dev");
  const [password, setPassword] = useState("ChangeMeNow123!");
  const [token, setToken] = useState<string>("");
  const [refreshToken, setRefreshToken] = useState<string>("");
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [walkForward, setWalkForward] = useState<WalkForwardPoint[]>([]);
  const [scorecard, setScorecard] = useState<ScorecardCell[]>([]);
  const [qualitySummary, setQualitySummary] = useState<DataQualitySummary | null>(null);
  const [configSnapshot, setConfigSnapshot] = useState<ConfigSnapshotResponse | null>(null);
  const [reportArtifacts, setReportArtifacts] = useState<RunReportArtifact[]>([]);
  const [downloadingFileId, setDownloadingFileId] = useState<string>("");
  const [liveFeed, setLiveFeed] = useState<LiveMsg[]>([]);
  const [timelineCategory, setTimelineCategory] = useState<TimelineFilterCategory>("core");
  const [timelineSeverity, setTimelineSeverity] = useState<TimelineSeverity>("all");
  const [timelineSource, setTimelineSource] = useState<"all" | TimelineSource>("all");
  const [runSearch, setRunSearch] = useState("");
  const [runStatusFilter, setRunStatusFilter] = useState("all");
  const [runPnlFilter, setRunPnlFilter] = useState<RunPnlFilter>("all");
  const [chartWindow, setChartWindow] = useState<ChartWindow>("80");
  const [status, setStatus] = useState<string>("Signed out");
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const clearSession = useCallback((reason = "Signed out") => {
    setToken("");
    setRefreshToken("");
    setRuns([]);
    setSelectedRunId("");
    setEvents([]);
    setTrades([]);
    setWalkForward([]);
    setScorecard([]);
    setQualitySummary(null);
    setConfigSnapshot(null);
    setReportArtifacts([]);
    setLiveFeed([]);
    clearStoredAdminSession();
    setStatus(reason);
  }, []);

  const selectedRun = useMemo(
    () => runs.find((r) => r.id === selectedRunId) || null,
    [runs, selectedRunId],
  );

  const tradeStats = useMemo(() => {
    if (!trades.length) {
      return { trades: 0, wins: 0, losses: 0, winRate: 0, pnl: 0 };
    }
    const wins = trades.filter((t) => (t.pnl_usdt || 0) > 0).length;
    const losses = trades.filter((t) => (t.pnl_usdt || 0) <= 0).length;
    const pnl = trades.reduce((acc, t) => acc + (t.pnl_usdt || 0), 0);
    return {
      trades: trades.length,
      wins,
      losses,
      winRate: (wins / trades.length) * 100,
      pnl,
    };
  }, [trades]);

  const runStatusOptions = useMemo(() => {
    const values = Array.from(
      new Set(
        runs
          .map((row) => String(row.status || "unknown").trim())
          .filter((row) => row.length > 0),
      ),
    );
    return values.sort((a, b) => a.localeCompare(b));
  }, [runs]);

  const filteredRuns = useMemo(() => {
    const search = runSearch.trim().toLowerCase();
    return runs.filter((row) => {
      const statusValue = String(row.status || "unknown").trim();
      if (runStatusFilter !== "all" && statusValue !== runStatusFilter) return false;
      if (runPnlFilter === "positive" && (row.session_pnl || 0) <= 0) return false;
      if (runPnlFilter === "negative" && (row.session_pnl || 0) >= 0) return false;
      if (!search) return true;
      return (
        String(row.run_key || "").toLowerCase().includes(search) ||
        String(row.bot_instance_id || "").toLowerCase().includes(search)
      );
    });
  }, [runs, runSearch, runStatusFilter, runPnlFilter]);

  const loadRuns = useCallback(async (authToken: string) => {
    const nextRuns = await getRuns(authToken);
    setRuns(nextRuns);
    if (nextRuns.length && !selectedRunId) {
      setSelectedRunId(nextRuns[0].id);
    }
  }, [selectedRunId]);

  const refreshRunDetails = useCallback(async (authToken: string, runId: string) => {
    if (!runId) return;
    const [runEvents, runTrades, runWalkForward, runScorecard, runQuality, runConfigSnapshot, runReportArtifacts] = await Promise.all([
      getRunEvents(authToken, runId),
      getRunTrades(authToken, runId),
      getRunWalkForward(authToken, runId),
      getRunScorecard(authToken, runId),
      getRunDataQuality(authToken, runId),
      getRunConfigSnapshot(authToken, runId),
      getRunReportArtifacts(authToken, runId),
    ]);
    setEvents(runEvents);
    setTrades(runTrades);
    setWalkForward(runWalkForward);
    setScorecard(runScorecard);
    setQualitySummary(runQuality);
    setConfigSnapshot(runConfigSnapshot);
    setReportArtifacts(runReportArtifacts);
  }, []);

  const equitySeries = useMemo(() => {
    if (!walkForward.length) return [] as { ts: string; equity: number }[];
    let cumulative = 0;
    return walkForward.map((point) => {
      cumulative += point.pnl_usdt || 0;
      return { ts: point.exit_ts, equity: cumulative };
    });
  }, [walkForward]);

  const windowedEquitySeries = useMemo(() => {
    if (chartWindow === "all") return equitySeries;
    const count = Number.parseInt(chartWindow, 10);
    if (!Number.isFinite(count) || count <= 0) return equitySeries;
    return equitySeries.slice(-count);
  }, [equitySeries, chartWindow]);

  const drawdownSeries = useMemo(() => {
    if (!windowedEquitySeries.length) return [] as { ts: string; drawdown: number }[];
    let peak = Number.NEGATIVE_INFINITY;
    return windowedEquitySeries.map((point) => {
      peak = Math.max(peak, point.equity);
      return {
        ts: point.ts,
        drawdown: point.equity - peak,
      };
    });
  }, [windowedEquitySeries]);

  const equityChart = useMemo(() => {
    const values = windowedEquitySeries.map((row) => row.equity);
    const labels = windowedEquitySeries.map((row) => row.ts);
    const points = buildChartPoints(values, labels);
    const latest = values.length ? values[values.length - 1] : 0;
    const delta = values.length >= 2 ? values[values.length - 1] - values[values.length - 2] : 0;
    return {
      points,
      path: pointsToPath(points),
      areaPath: pointsToAreaPath(points),
      latest,
      delta,
    };
  }, [windowedEquitySeries]);

  const drawdownChart = useMemo(() => {
    const values = drawdownSeries.map((row) => row.drawdown);
    const labels = drawdownSeries.map((row) => row.ts);
    const points = buildChartPoints(values, labels);
    const worst = values.length ? Math.min(...values) : 0;
    const delta = values.length >= 2 ? values[values.length - 1] - values[values.length - 2] : 0;
    return {
      points,
      path: pointsToPath(points),
      areaPath: pointsToAreaPath(points),
      worst,
      delta,
    };
  }, [drawdownSeries]);

  const reportFileCount = useMemo(
    () => reportArtifacts.reduce((acc, row) => acc + row.files.length, 0),
    [reportArtifacts],
  );

  const configSnapshotText = useMemo(() => {
    if (!configSnapshot?.config_snapshot) return "";
    try {
      return JSON.stringify(configSnapshot.config_snapshot, null, 2);
    } catch {
      return "";
    }
  }, [configSnapshot]);

  const timelineEvents = useMemo(() => {
    const persisted = events.map((ev) => normalizeHistoryEvent(ev));
    const live = liveFeed.map((msg, idx) => normalizeLiveEvent(msg, idx));
    const dedup = new Set<string>();
    const merged = [...live, ...persisted]
      .sort((a, b) => b.tsMs - a.tsMs)
      .filter((row) => {
        const key = `${row.eventType}|${row.tsMs}|${row.summary}|${row.category}`;
        if (dedup.has(key)) return false;
        dedup.add(key);
        return true;
      });

    return merged
      .filter((row) => {
        if (timelineSource !== "all" && row.source !== timelineSource) return false;
        if (timelineSeverity !== "all" && row.severity !== timelineSeverity) return false;
        if (timelineCategory === "core") {
          return row.category === "switch" || row.category === "gate" || row.category === "alert" || row.category === "exit";
        }
        if (timelineCategory !== "all" && row.category !== timelineCategory) return false;
        return true;
      })
      .slice(0, 80);
  }, [events, liveFeed, timelineCategory, timelineSeverity, timelineSource]);

  const downloadArtifactFile = useCallback(
    async (downloadUrl: string, fileName: string, fileId: string) => {
      if (!token) {
        setError("You must be signed in to download report files.");
        return;
      }
      setError("");
      setDownloadingFileId(fileId);
      try {
        const response = await fetch(`${apiRootUrl()}${downloadUrl}`, {
          method: "GET",
          headers: {
            Authorization: `Bearer ${token}`,
          },
          cache: "no-store",
        });
        if (!response.ok) {
          const text = await response.text();
          throw new Error(`Download failed (${response.status}): ${text.slice(0, 180)}`);
        }
        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = objectUrl;
        a.download = fileName || "report-artifact";
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(objectUrl);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to download report file";
        setError(msg);
      } finally {
        setDownloadingFileId("");
      }
    },
    [token],
  );

  async function onLoginSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const pair = await login(email, password);
      setToken(pair.access_token);
      setRefreshToken(pair.refresh_token);
      persistAdminSession(pair.access_token, pair.refresh_token, true);
      setStatus("Authenticated");
      await loadRuns(pair.access_token);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Login failed";
      setError(msg);
      setStatus("Authentication failed");
    } finally {
      setLoading(false);
    }
  }

  function onLogout() {
    clearSession("Signed out");
    router.replace("/login?next=/");
  }

  async function handleRefreshRuns() {
    if (!token) return;
    try {
      await loadRuns(token);
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearSession("Session expired. Please sign in again.");
        setError("Session expired. Please sign in again.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Failed to load runs";
      setError(msg);
    }
  }

  async function handleRefreshDetail() {
    if (!token || !selectedRunId) return;
    try {
      await refreshRunDetails(token, selectedRunId);
    } catch (err) {
      if (isUnauthorizedError(err)) {
        clearSession("Session expired. Please sign in again.");
        setError("Session expired. Please sign in again.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Failed to load run detail";
      setError(msg);
    }
  }

  useEffect(() => {
    const stored = getStoredAdminAccessToken();
    const storedRefresh = getStoredAdminRefreshToken();
    if (stored) {
      setToken(stored);
      setRefreshToken(storedRefresh);
      setStatus("Session restored");
      loadRuns(stored).catch((err: unknown) => {
        if (isUnauthorizedError(err)) {
          clearSession("Session expired. Please sign in again.");
          setError("Session expired. Please sign in again.");
          return;
        }
        const msg = err instanceof Error ? err.message : "Failed to load runs";
        setError(msg);
      });
    }
  }, [clearSession, loadRuns]);

  useEffect(() => {
    if (!token || !selectedRunId) return;
    refreshRunDetails(token, selectedRunId).catch((err: unknown) => {
      if (isUnauthorizedError(err)) {
        clearSession("Session expired. Please sign in again.");
        setError("Session expired. Please sign in again.");
        return;
      }
      const msg = err instanceof Error ? err.message : "Failed to load run detail";
      setError(msg);
    });
  }, [clearSession, token, selectedRunId, refreshRunDetails]);

  useEffect(() => {
    if (!selectedRun?.bot_instance_id) return;
    const ws = new WebSocket(wsDashboardUrl(selectedRun.bot_instance_id));

    ws.onmessage = (ev) => {
      try {
        const parsed = JSON.parse(ev.data) as LiveMsg;
        setLiveFeed((prev) => [parsed, ...prev].slice(0, 150));
      } catch {
        // ignore malformed messages
      }
    };

    ws.onerror = () => {
      setStatus("WS disconnected");
    };

    ws.onopen = () => {
      setStatus("WS connected");
    };

    return () => {
      ws.close();
    };
  }, [selectedRun?.bot_instance_id]);

  return (
    <DashboardShell
      title="Run Browser + Live Event Stream"
      subtitle="Monitor attribution, quality checks, reconciliation, and artifact outputs."
      status={status}
      activeHref="/"
      navItems={[
        { href: "/", label: "Analytics", hint: "Runs, quality, reports", group: "Monitor", icon: "AN" },
        { href: "/admin", label: "Super Admin", hint: "Control plane", group: "Operate", icon: "SA" },
      ]}
      actions={
        <p className="text-xs text-gray-500 dark:text-gray-400">
          API <code className="font-mono text-xs text-gray-700 dark:text-gray-300">{apiBaseUrl()}</code>
        </p>
      }
    >
      <div className="grid gap-4">
        <section className="rounded-2xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-900">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-500">V2 UI Foundation</p>
          <h1 className="mt-1 text-3xl font-semibold text-gray-900 dark:text-white/90">Run Browser + Live Event Stream</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">TailAdmin-style shell enabled for fast V2 expansion.</p>
        </section>

        <section className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white/90">Session</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">{status}</p>
            {refreshToken ? <p className="text-xs text-gray-500 dark:text-gray-400">Refresh token present</p> : null}
          </div>
          {!token ? (
            <form onSubmit={onLoginSubmit} className="flex w-full flex-wrap items-center gap-2 lg:w-auto">
              <input
                className="min-w-[220px] flex-1 lg:flex-none"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email"
                required
              />
              <input
                className="min-w-[220px] flex-1 lg:flex-none"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password"
                type="password"
                required
              />
              <button
                type="submit"
                disabled={loading}
                className="inline-flex items-center rounded-xl bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 disabled:opacity-70"
              >
                {loading ? "Signing in..." : "Sign in"}
              </button>
            </form>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={handleRefreshRuns}
                className="inline-flex items-center rounded-xl bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600"
              >
                Refresh runs
              </button>
              <button
                onClick={handleRefreshDetail}
                className="inline-flex items-center rounded-xl bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600"
              >
                Refresh detail
              </button>
              <button
                className="inline-flex items-center rounded-xl border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                onClick={onLogout}
              >
                Logout
              </button>
            </div>
          )}
          {error ? <p className="w-full text-sm text-error-600 dark:text-error-400">{error}</p> : null}
        </section>

        <section className="grid grid-cols-1 gap-3 sm:grid-cols-2 2xl:grid-cols-6">
          <MetricCard label="Selected Run" value={selectedRun?.run_key || "n/a"} hint={`${runs.length} runs loaded`} tone="sky" />
          <MetricCard
            label="Session PnL"
            value={`${fmtNumber(selectedRun?.session_pnl)} USDT`}
            hint={`equity close ${fmtNumber(selectedRun?.end_equity)}`}
            tone={selectedRun && (selectedRun.session_pnl || 0) < 0 ? "rose" : "teal"}
          />
          <MetricCard
            label="Win Rate"
            value={`${fmtNumber(tradeStats.winRate)}%`}
            hint={`${tradeStats.wins}W / ${tradeStats.losses}L`}
            tone="violet"
          />
          <MetricCard
            label="Worst Drawdown"
            value={`${fmtNumber(drawdownChart.worst)} USDT`}
            hint={`${drawdownChart.points.length} points`}
            tone="amber"
          />
          <MetricCard
            label="Data Quality"
            value={String(qualitySummary?.overall_status || "unknown").toUpperCase()}
            hint={`${qualitySummary?.recent_issues?.length || 0} recent issues`}
            tone={qualitySummary?.overall_status === "pass" ? "teal" : qualitySummary ? "amber" : "sky"}
          />
          <MetricCard label="Report Files" value={String(reportFileCount)} hint={`${reportArtifacts.length} report batches`} tone="sky" />
        </section>

        <section className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
          <PanelCard title="Runs" subtitle="Select run to load trades, events, and quality snapshots.">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <input
                className="min-w-[250px] flex-1"
                value={runSearch}
                onChange={(e) => setRunSearch(e.target.value)}
                placeholder="Search run key or bot id"
              />
              <select
                className="min-w-[160px]"
                value={runStatusFilter}
                onChange={(e) => setRunStatusFilter(e.target.value)}
              >
                <option value="all">All statuses</option>
                {runStatusOptions.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
              <div className="flex flex-wrap items-center gap-1.5">
                <button
                  type="button"
                  className={`rounded-full border px-3 py-1.5 text-xs font-medium ${
                    runPnlFilter === "all"
                      ? "border-brand-200 bg-brand-50 text-brand-700 dark:border-brand-800 dark:bg-brand-950/30 dark:text-brand-300"
                      : "border-gray-200 bg-white text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
                  }`}
                  onClick={() => setRunPnlFilter("all")}
                >
                  All PnL
                </button>
                <button
                  type="button"
                  className={`rounded-full border px-3 py-1.5 text-xs font-medium ${
                    runPnlFilter === "positive"
                      ? "border-brand-200 bg-brand-50 text-brand-700 dark:border-brand-800 dark:bg-brand-950/30 dark:text-brand-300"
                      : "border-gray-200 bg-white text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
                  }`}
                  onClick={() => setRunPnlFilter("positive")}
                >
                  Positive
                </button>
                <button
                  type="button"
                  className={`rounded-full border px-3 py-1.5 text-xs font-medium ${
                    runPnlFilter === "negative"
                      ? "border-brand-200 bg-brand-50 text-brand-700 dark:border-brand-800 dark:bg-brand-950/30 dark:text-brand-300"
                      : "border-gray-200 bg-white text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
                  }`}
                  onClick={() => setRunPnlFilter("negative")}
                >
                  Negative
                </button>
              </div>
              <span className="ml-auto text-xs text-gray-500 dark:text-gray-400">
                {filteredRuns.length}/{runs.length} shown
              </span>
            </div>

            <TableFrame>
              <table>
                <thead>
                  <tr>
                    <th>Run Key</th>
                    <th>Status</th>
                    <th>Session PnL</th>
                    <th>Duration</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRuns.map((run) => {
                    const active = run.id === selectedRunId;
                    return (
                      <tr
                        key={run.id}
                        className={`cursor-pointer transition-colors ${
                          active ? "bg-brand-50/70 dark:bg-brand-500/15" : "hover:bg-gray-50 dark:hover:bg-white/5"
                        }`}
                        onClick={() => setSelectedRunId(run.id)}
                      >
                        <td>{run.run_key}</td>
                        <td>
                          <StatusPill label={run.status || "unknown"} tone={statusTone(run.status)} />
                        </td>
                        <td>{fmtNumber(run.session_pnl)}</td>
                        <td>{fmtDuration(run.start_ts, run.end_ts)}</td>
                      </tr>
                    );
                  })}
                  {!filteredRuns.length ? (
                    <tr>
                      <td colSpan={4} className="text-sm text-gray-500 dark:text-gray-400">
                        No runs match current filters.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </TableFrame>
          </PanelCard>

          <PanelCard title="Run Detail">
            {selectedRun ? (
              <div className="space-y-1 text-sm text-gray-600 dark:text-gray-300">
                <p>
                  <strong className="text-gray-800 dark:text-white/90">Run:</strong> {selectedRun.run_key}
                </p>
                <p>
                  <strong className="text-gray-800 dark:text-white/90">Bot:</strong> {selectedRun.bot_instance_id}
                </p>
                <p>
                  <strong className="text-gray-800 dark:text-white/90">Started:</strong> {fmtDate(selectedRun.start_ts)}
                </p>
                <p>
                  <strong className="text-gray-800 dark:text-white/90">Ended:</strong> {fmtDate(selectedRun.end_ts)}
                </p>
              </div>
            ) : (
              <p className="text-sm text-gray-500 dark:text-gray-400">Select a run.</p>
            )}

            <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-3">
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-800/70">
                <span className="text-xs uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400">Trades</span>
                <strong className="mt-1 block text-lg text-gray-900 dark:text-white/90">{tradeStats.trades}</strong>
              </div>
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-800/70">
                <span className="text-xs uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400">Win Rate</span>
                <strong className="mt-1 block text-lg text-gray-900 dark:text-white/90">{fmtNumber(tradeStats.winRate)}%</strong>
              </div>
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-800/70">
                <span className="text-xs uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400">Total PnL</span>
                <strong className="mt-1 block text-lg text-gray-900 dark:text-white/90">{fmtNumber(tradeStats.pnl)}</strong>
              </div>
            </div>

            <h4 className="mt-5 text-base font-semibold text-gray-900 dark:text-white/90">Event Timeline</h4>
            <div className="mt-2 grid gap-2 md:grid-cols-4">
              <label className="grid gap-1 text-xs font-semibold uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400">
                Category
                <select
                  value={timelineCategory}
                  onChange={(e) => setTimelineCategory(e.target.value as TimelineFilterCategory)}
                >
                  <option value="core">Core (switch/gate/alert/exit)</option>
                  <option value="all">All</option>
                  <option value="switch">Switches</option>
                  <option value="gate">Gates</option>
                  <option value="alert">Alerts</option>
                  <option value="exit">Exits</option>
                  <option value="other">Other</option>
                </select>
              </label>
              <label className="grid gap-1 text-xs font-semibold uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400">
                Severity
                <select
                  value={timelineSeverity}
                  onChange={(e) => setTimelineSeverity(e.target.value as TimelineSeverity)}
                >
                  <option value="all">All</option>
                  <option value="info">Info</option>
                  <option value="warn">Warn</option>
                  <option value="error">Error</option>
                  <option value="critical">Critical</option>
                </select>
              </label>
              <label className="grid gap-1 text-xs font-semibold uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400">
                Source
                <select value={timelineSource} onChange={(e) => setTimelineSource(e.target.value as "all" | TimelineSource)}>
                  <option value="all">All</option>
                  <option value="history">Stored events</option>
                  <option value="live">WebSocket live</option>
                </select>
              </label>
              <div className="flex items-end text-sm text-gray-500 dark:text-gray-400">{timelineEvents.length} shown</div>
            </div>

            <ul className="mt-3 grid gap-2">
              {timelineEvents.map((row) => (
                <li key={row.id} className="rounded-xl border border-gray-200 bg-white p-3 dark:border-gray-800 dark:bg-gray-900/30">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] ${eventSeverityClass(
                        row.severity,
                      )}`}
                    >
                      {row.severity}
                    </span>
                    <span
                      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] ${eventCategoryClass(
                        row.category,
                      )}`}
                    >
                      {row.category}
                    </span>
                    <strong className="text-sm text-gray-800 dark:text-white/90">{row.eventType}</strong>
                    <span className="text-[11px] uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400">
                      {row.source === "history" ? "stored" : "live"}
                    </span>
                    <time className="ml-auto text-xs text-gray-500 dark:text-gray-400">{new Date(row.tsMs).toLocaleString()}</time>
                  </div>
                  {row.summary ? <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">{row.summary}</p> : null}
                </li>
              ))}
              {!timelineEvents.length ? (
                <li className="rounded-xl border border-dashed border-gray-300 p-3 text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">
                  No timeline events match the current filters.
                </li>
              ) : null}
            </ul>
          </PanelCard>
        </section>

        <section className="grid gap-4 xl:grid-cols-2">
          <article className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900">
            <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white/90">Equity Curve (Realized)</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">Cumulative realized PnL</p>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <button
                  type="button"
                  className={`rounded-full border px-3 py-1.5 text-xs font-medium ${
                    chartWindow === "30"
                      ? "border-brand-200 bg-brand-50 text-brand-700 dark:border-brand-800 dark:bg-brand-950/30 dark:text-brand-300"
                      : "border-gray-200 bg-white text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
                  }`}
                  onClick={() => setChartWindow("30")}
                >
                  30
                </button>
                <button
                  type="button"
                  className={`rounded-full border px-3 py-1.5 text-xs font-medium ${
                    chartWindow === "80"
                      ? "border-brand-200 bg-brand-50 text-brand-700 dark:border-brand-800 dark:bg-brand-950/30 dark:text-brand-300"
                      : "border-gray-200 bg-white text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
                  }`}
                  onClick={() => setChartWindow("80")}
                >
                  80
                </button>
                <button
                  type="button"
                  className={`rounded-full border px-3 py-1.5 text-xs font-medium ${
                    chartWindow === "all"
                      ? "border-brand-200 bg-brand-50 text-brand-700 dark:border-brand-800 dark:bg-brand-950/30 dark:text-brand-300"
                      : "border-gray-200 bg-white text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
                  }`}
                  onClick={() => setChartWindow("all")}
                >
                  All
                </button>
              </div>
            </div>
            {equityChart.points.length ? (
              <>
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-sm text-gray-500 dark:text-gray-400">
                  <span>Closed trades (window): {equityChart.points.length}</span>
                  <strong className="text-gray-900 dark:text-white/90">
                    Latest cumulative PnL: {fmtNumber(equityChart.latest)} USDT
                  </strong>
                  <span className={deltaChipClass(equityChart.delta)}>Delta {fmtSignedNumber(equityChart.delta)} USDT</span>
                </div>
                <svg
                  viewBox="0 0 620 190"
                  className="mt-1 h-[230px] w-full rounded-xl border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-950/40"
                  role="img"
                  aria-label="Equity curve chart"
                >
                  <path d={equityChart.areaPath} className="fill-brand-500/20 dark:fill-brand-500/30" />
                  <path d={equityChart.path} fill="none" stroke="#465fff" strokeWidth="3" />
                </svg>
              </>
            ) : (
              <p className="text-sm text-gray-500 dark:text-gray-400">No walk-forward points yet.</p>
            )}
          </article>

          <article className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900">
            <div className="mb-3">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white/90">Drawdown Curve</h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">Peak-to-trough drift</p>
            </div>
            {drawdownChart.points.length ? (
              <>
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-sm text-gray-500 dark:text-gray-400">
                  <span>Computed from cumulative realized PnL</span>
                  <strong className="text-gray-900 dark:text-white/90">
                    Worst drawdown: {fmtNumber(drawdownChart.worst)} USDT
                  </strong>
                  <span className={deltaChipClass(drawdownChart.delta)}>Delta {fmtSignedNumber(drawdownChart.delta)} USDT</span>
                </div>
                <svg
                  viewBox="0 0 620 190"
                  className="mt-1 h-[230px] w-full rounded-xl border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-950/40"
                  role="img"
                  aria-label="Drawdown chart"
                >
                  <path d={drawdownChart.areaPath} className="fill-warning-500/20 dark:fill-warning-500/25" />
                  <path d={drawdownChart.path} fill="none" stroke="#f79009" strokeWidth="3" />
                </svg>
              </>
            ) : (
              <p className="text-sm text-gray-500 dark:text-gray-400">No drawdown data yet.</p>
            )}
          </article>
        </section>

      <PanelCard title="Strategy x Regime Attribution">
        <AttributionTable scorecard={scorecard} />
      </PanelCard>

        <section className="grid gap-4 xl:grid-cols-2">
          <article className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white/90">Data Quality</h3>
            {qualitySummary ? (
              <div className="mt-3 space-y-3">
                <p className="text-sm text-gray-600 dark:text-gray-300">
                  <strong className="text-gray-900 dark:text-white/90">Overall:</strong>{" "}
                  <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.08em] ${qualityClass(qualitySummary.overall_status)}`}>
                    {qualitySummary.overall_status}
                  </span>
                </p>
                <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
                  <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-800/70">
                    <span className="text-xs uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400">Events</span>
                    <strong className="mt-1 block text-lg text-gray-900 dark:text-white/90">{qualitySummary.event_health.total}</strong>
                  </div>
                  <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-800/70">
                    <span className="text-xs uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400">Warn/Error/Critical</span>
                    <strong className="mt-1 block text-lg text-gray-900 dark:text-white/90">
                      {qualitySummary.event_health.warn}/{qualitySummary.event_health.error}/{qualitySummary.event_health.critical}
                    </strong>
                  </div>
                  <div className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-800/70">
                    <span className="text-xs uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400">Trade Integrity</span>
                    <strong className={`mt-1 block text-sm font-semibold uppercase tracking-[0.08em] ${qualityClass(qualitySummary.trade_integrity.status)}`}>
                      {qualitySummary.trade_integrity.status}
                    </strong>
                  </div>
                </div>

                <TableFrame compact>
                  <table>
                    <thead>
                      <tr>
                        <th>Warning Event Type</th>
                        <th>Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(qualitySummary.event_health.typed_warning_events).map(([name, count]) => (
                        <tr key={name}>
                          <td>{name}</td>
                          <td>{count}</td>
                        </tr>
                      ))}
                      {!Object.keys(qualitySummary.event_health.typed_warning_events).length ? (
                        <tr>
                          <td colSpan={2} className="text-sm text-gray-500 dark:text-gray-400">
                            No warning-type events recorded.
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </TableFrame>
              </div>
            ) : (
              <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">No data quality snapshot yet.</p>
            )}
          </article>

          <article className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white/90">Reconciliation</h3>
            {qualitySummary ? (
              <div className="mt-3 space-y-3 text-sm text-gray-600 dark:text-gray-300">
                <p>
                  <strong className="text-gray-900 dark:text-white/90">Status:</strong>{" "}
                  <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.08em] ${qualityClass(qualitySummary.reconciliation.status)}`}>
                    {qualitySummary.reconciliation.status}
                  </span>
                </p>
                <p>
                  <strong className="text-gray-900 dark:text-white/90">Run session PnL:</strong> {fmtNumber(qualitySummary.reconciliation.run_session_pnl_usdt)} USDT
                </p>
                <p>
                  <strong className="text-gray-900 dark:text-white/90">Closed-trade PnL sum:</strong> {fmtNumber(qualitySummary.reconciliation.trade_pnl_sum_usdt)} USDT
                </p>
                <p>
                  <strong className="text-gray-900 dark:text-white/90">Delta:</strong> {fmtNumber(qualitySummary.reconciliation.delta_usdt)} USDT |{" "}
                  {fmtNumber(qualitySummary.reconciliation.delta_pct_of_session)}%
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Thresholds: pass {"<="} {fmtNumber(qualitySummary.reconciliation.threshold_pass_usdt)} USDT, warn {"<="}{" "}
                  {fmtNumber(qualitySummary.reconciliation.threshold_warn_usdt)} USDT
                </p>

                <h4 className="text-base font-semibold text-gray-900 dark:text-white/90">Top Alerts</h4>
                <TableFrame compact>
                  <table>
                    <thead>
                      <tr>
                        <th>Alert Type</th>
                        <th>Count</th>
                        <th>Last Seen</th>
                      </tr>
                    </thead>
                    <tbody>
                      {qualitySummary.top_alerts.map((row) => (
                        <tr key={row.alert_type}>
                          <td>{row.alert_type}</td>
                          <td>{row.count}</td>
                          <td>{fmtDate(row.last_seen)}</td>
                        </tr>
                      ))}
                      {!qualitySummary.top_alerts.length ? (
                        <tr>
                          <td colSpan={3} className="text-sm text-gray-500 dark:text-gray-400">
                            No alert rows for this run.
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </TableFrame>
              </div>
            ) : (
              <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">No reconciliation snapshot yet.</p>
            )}
          </article>
        </section>

        <section className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white/90">Recent Quality/Reconciliation Issues</h3>
          {qualitySummary?.recent_issues?.length ? (
            <TableFrame>
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Severity</th>
                    <th>Type</th>
                    <th>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {qualitySummary.recent_issues.map((row) => (
                    <tr key={`${row.event_id}-${row.ts}`}>
                      <td>{fmtDate(row.ts)}</td>
                      <td>
                        <StatusPill label={row.severity} tone={statusTone(row.severity)} />
                      </td>
                      <td>{row.event_type}</td>
                      <td>{row.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableFrame>
          ) : (
            <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">No recent quality/reconciliation issues for this run.</p>
          )}
        </section>

        <section className="grid gap-4 xl:grid-cols-2">
          <article className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white/90">Config Snapshot</h3>
            {configSnapshot ? (
              <div className="mt-3 space-y-2 text-sm text-gray-600 dark:text-gray-300">
                <p>
                  <strong className="text-gray-900 dark:text-white/90">Source:</strong> {configSnapshot.source}
                </p>
                <p>
                  <strong className="text-gray-900 dark:text-white/90">Captured:</strong> {fmtDate(configSnapshot.created_at)}
                </p>
                {configSnapshot.error ? <p className="text-sm text-error-600 dark:text-error-400">Snapshot error: {configSnapshot.error}</p> : null}
                {configSnapshot.config_snapshot ? (
                  <details className="mt-2" open>
                    <summary className="cursor-pointer text-sm text-gray-500 dark:text-gray-400">
                      View config JSON ({Object.keys(configSnapshot.config_snapshot).length} keys)
                    </summary>
                    <pre className="custom-scrollbar mt-2 max-h-64 overflow-auto rounded-xl border border-gray-200 bg-gray-50 p-3 text-xs text-gray-700 dark:border-gray-800 dark:bg-gray-950/40 dark:text-gray-200">
                      {configSnapshotText}
                    </pre>
                  </details>
                ) : (
                  <p className="text-sm text-gray-500 dark:text-gray-400">No config snapshot available for this run yet.</p>
                )}
              </div>
            ) : (
              <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">Loading config snapshot...</p>
            )}
          </article>

          <article className="rounded-2xl border border-gray-200 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white/90">Report Artifacts</h3>
            {reportArtifacts.length ? (
              <TableFrame compact>
                <table>
                  <thead>
                    <tr>
                      <th>Report</th>
                      <th>Status</th>
                      <th>File</th>
                      <th>Size</th>
                      <th>Download</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reportArtifacts.flatMap((report) =>
                      report.files.length
                        ? report.files.map((file) => (
                            <tr key={`${report.id}-${file.id}`}>
                              <td>{report.id.slice(0, 8)}</td>
                              <td>{report.status}</td>
                              <td>{file.name}</td>
                              <td>{fmtBytes(file.size_bytes)}</td>
                              <td>
                                <button
                                  type="button"
                                  className="inline-flex items-center rounded-xl border border-gray-300 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                                  disabled={!token || downloadingFileId === file.id}
                                  onClick={() => downloadArtifactFile(file.download_url, file.name, file.id)}
                                >
                                  {downloadingFileId === file.id ? "Downloading..." : "Download"}
                                </button>
                              </td>
                            </tr>
                          ))
                        : [
                            <tr key={`${report.id}-nofile`}>
                              <td>{report.id.slice(0, 8)}</td>
                              <td>{report.status}</td>
                              <td className="text-sm text-gray-500 dark:text-gray-400" colSpan={3}>
                                No files linked for this report.
                              </td>
                            </tr>,
                          ],
                    )}
                  </tbody>
                </table>
              </TableFrame>
            ) : (
              <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">No report artifacts found for this run.</p>
            )}
          </article>
        </section>
      </div>
    </DashboardShell>
  );
}
