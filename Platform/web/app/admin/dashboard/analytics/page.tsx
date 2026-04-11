"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter, usePathname } from "next/navigation";

import {
  ConfigSnapshotResponse,
  DataQualitySummary,
  RunEvent,
  RunReportArtifact,
  RunSummary,
  ScorecardCell,
  Trade,
  UserRecord,
  WalkForwardPoint,
  apiRootUrl,
  getMe,
  getRunConfigSnapshot,
  getRunDataQuality,
  getRunEvents,
  getRunReportArtifacts,
  getRunScorecard,
  getRunTrades,
  getRunWalkForward,
  getRuns,
  isUnauthorizedError,
  wsDashboardUrl,
} from "../../../../lib/api";
import { DashboardShell } from "../../../../components/dashboard-shell";
import { MetricCard, PanelCard, StatusPill, TableFrame } from "../../../../components/panels";
import {
  clearStoredAdminSession,
  getStoredAdminEmail,
} from "../../../../lib/auth";
import {
  canAccessAdminPath,
  getAdminNavItems,
  getFirstAccessibleAdminPath,
  hasPermission,
} from "../../../../lib/admin-access";
import { UI_CLASSES } from "../../../../lib/ui-classes";

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
  if (normalized === "warning") {
    return "border border-warning-200 bg-warning-50 text-warning-700 dark:border-warning-900 dark:bg-warning-950/20 dark:text-warning-400";
  }
  if (normalized === "fail") {
    return "border border-danger-200 bg-danger-50 text-danger-700 dark:border-danger-900 dark:bg-danger-950/20 dark:text-danger-400";
  }
  return "border border-gray-200 bg-gray-50 text-gray-700 dark:border-gray-700 dark:bg-gray-800/50 dark:text-gray-400";
}

export default function AnalyticsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [timelineFilter, setTimelineFilter] = useState<TimelineFilterCategory>("all");
  const [timelineSeverity, setTimelineSeverity] = useState<TimelineSeverity>("all");
  const [timelineEvents, setTimelineEvents] = useState<TimelineEvent[]>([]);
  const [showLive, setShowLive] = useState(true);
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [liveEvents, setLiveEvents] = useState<TimelineEvent[]>([]);
  const [selectedRun, setSelectedRun] = useState<RunSummary | null>(null);
  const [runConfig, setRunConfig] = useState<ConfigSnapshotResponse | null>(null);
  const [runQuality, setRunQuality] = useState<DataQualitySummary | null>(null);
  const [scorecard, setScorecard] = useState<ScorecardCell[][] | null>(null);
  const [walkForward, setWalkForward] = useState<WalkForwardPoint[]>([]);
  const [runTrades, setRunTrades] = useState<Trade[]>([]);
  const [runArtifacts, setRunArtifacts] = useState<RunReportArtifact[]>([]);
  const [pnlFilter, setPnlFilter] = useState<RunPnlFilter>("all");

  const navItems = useMemo(() => getAdminNavItems(user), [user]);

  useEffect(() => {
    getMe()
      .then((u) => setUser(u))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  const auth = useMemo(
    () => ({
      email: getStoredAdminEmail(),
      hasToken: true,
    }),
    [],
  );

  useEffect(() => {
    if (loading || !user) return;
    // Check if user still has permission to access this page
    const currentPath = pathname;
    const hasAccess = canAccessAdminPath(user, currentPath);
    const firstAccessible = getFirstAccessibleAdminPath(user);

    if (!hasAccess) {
      // If there's no accessible page at all, go home
      if (!firstAccessible) {
        router.replace("/");
        return;
      }
      // Only redirect if the accessible page is different from current
      if (firstAccessible !== currentPath) {
        router.replace(firstAccessible);
      }
    }
  }, [loading, user, pathname, router]);

  useEffect(() => {
    if (!showLive) {
      ws?.close();
      setWs(null);
      return;
    }
    const w = new WebSocket(wsDashboardUrl);
    w.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data) as LiveMsg;
        setLiveEvents((prev) => [normalizeLiveEvent(msg, prev.length), ...prev].slice(0, 500));
      } catch (e) {
        console.error("WS parse error", e);
      }
    };
    setWs(w);
    return () => w.close();
  }, [showLive]);

  useEffect(() => {
    getRuns()
      .then(setRuns)
      .catch((e) => setError(isUnauthorizedError(e) ? "Unauthorized" : "Failed to load runs"));
  }, []);

  useEffect(() => {
    if (selectedRunId === null) {
      const latest = (runs || [])[0];
      if (latest) setSelectedRunId(latest.id);
      return;
    }
    const found = (runs || []).find((r) => r.id === selectedRunId);
    if (found) setSelectedRun(found);
  }, [selectedRunId, runs]);

  const filteredTimeline = useMemo(() => {
    let events = [...timelineEvents];
    if (showLive) {
      events = [...liveEvents, ...events];
    }
    return events
      .filter((ev) => timelineFilter === "all" || ev.category === timelineFilter || (timelineFilter === "core" && (ev.category === "switch" || ev.category === "gate")))
      .filter((ev) => timelineSeverity === "all" || ev.severity === timelineSeverity)
      .sort((a, b) => b.tsMs - a.tsMs)
      .slice(0, 100);
  }, [timelineEvents, liveEvents, showLive, timelineFilter, timelineSeverity]);

  const loadSelectedRunData = useCallback(async () => {
    if (!selectedRun) return;
    setRunConfig(null);
    setRunQuality(null);
    setScorecard(null);
    setWalkForward([]);
    setRunTrades([]);
    setRunArtifacts([]);
    setTimelineEvents([]);
    try {
      const [cfg, qual, score, wf, trades, arts, evts] = await Promise.all([
        getRunConfigSnapshot(selectedRun.id),
        getRunDataQuality(selectedRun.id),
        getRunScorecard(selectedRun.id),
        getRunWalkForward(selectedRun.id),
        getRunTrades(selectedRun.id),
        getRunReportArtifacts(selectedRun.id),
        getRunEvents(selectedRun.id),
      ]);
      setRunConfig(cfg);
      setRunQuality(qual);
      setScorecard(score);
      setWalkForward(wf);
      setRunTrades(trades);
      setRunArtifacts(arts);
      setTimelineEvents(evts.map(normalizeHistoryEvent));
    } catch (e) {
      console.error("Failed to load run data", e);
    }
  }, [selectedRun]);

  useEffect(() => {
    loadSelectedRunData();
  }, [loadSelectedRunData]);

  const filteredRuns = useMemo(() => {
    return (runs || []).filter((r) => {
      if (pnlFilter === "positive") return (r.realized_pl ?? 0) > 0;
      if (pnlFilter === "negative") return (r.realized_pl ?? 0) < 0;
      return true;
    });
  }, [runs, pnlFilter]);

  const handleLogout = useCallback(() => {
    clearStoredAdminSession();
    router.replace("/login");
  }, [router]);

  if (loading) {
    return <div className="p-8 text-center text-gray-500">Loading...</div>;
  }

  const activeHref = "/admin/dashboard/analytics";

  return (
    <DashboardShell
      title="Analytics"
      subtitle="Run monitoring, timeline & data quality"
      status="OK"
      activeHref={activeHref}
      navItems={navItems}
      auth={auth}
    >
      <div className="space-y-6">
        <div className="flex flex-wrap gap-4">
          <select
            className={UI_CLASSES.input}
            value={selectedRunId || ""}
            onChange={(e) => setSelectedRunId(e.target.value)}
          >
            {filteredRuns.filter(r => r && r.id).map((run) => (
              <option key={run.id} value={run.id}>
                {run.id.slice(0, 8)} ({fmtDate(run.start_ts)}) - {fmtSignedNumber(run.session_pnl)} USDT
              </option>
            ))}
          </select>
          <select className={UI_CLASSES.input} value={pnlFilter} onChange={(e) => setPnlFilter(e.target.value as RunPnlFilter)}>
            <option value="all">All PnL</option>
            <option value="positive">Positive only</option>
            <option value="negative">Negative only</option>
          </select>
          <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
            <input type="checkbox" checked={showLive} onChange={(e) => setShowLive(e.target.checked)} />
            Live events
          </label>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          <MetricCard label="Session PnL" value={fmtSignedNumber(selectedRun?.session_pnl)} unit="USDT" />
          <MetricCard label="Duration" value={selectedRun ? fmtDuration(selectedRun.start_ts, selectedRun.end_ts) : "n/a"} />
          <MetricCard label="Start Equity" value={fmtNumber(selectedRun?.start_equity)} unit="USDT" />
          <MetricCard label="End Equity" value={fmtNumber(selectedRun?.end_equity)} unit="USDT" />
        </div>

        <PanelCard title="Timeline" titleRight={
          <div className="flex gap-2">
            <select className={UI_CLASSES.inputSmall} value={timelineFilter} onChange={(e) => setTimelineFilter(e.target.value as TimelineFilterCategory)}>
              <option value="all">All</option>
              <option value="core">Core</option>
              <option value="switch">Switches</option>
              <option value="gate">Gates</option>
              <option value="alert">Alerts</option>
              <option value="exit">Exits</option>
              <option value="other">Other</option>
            </select>
            <select className={UI_CLASSES.inputSmall} value={timelineSeverity} onChange={(e) => setTimelineSeverity(e.target.value as TimelineSeverity)}>
              <option value="all">All</option>
              <option value="info">Info</option>
              <option value="warn">Warning</option>
              <option value="error">Error</option>
              <option value="critical">Critical</option>
            </select>
          </div>
        }>
          <TableFrame>
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700">
                  <th className="pb-2 font-medium text-gray-500">Time</th>
                  <th className="pb-2 font-medium text-gray-500">Source</th>
                  <th className="pb-2 font-medium text-gray-500">Type</th>
                  <th className="pb-2 font-medium text-gray-500">Summary</th>
                </tr>
              </thead>
              <tbody>
                {filteredTimeline.map((ev) => (
                  <tr key={ev.id} className="border-b border-gray-100 py-2 dark:border-gray-800">
                    <td className="py-2 font-mono text-xs">{new Date(ev.tsMs).toLocaleTimeString()}</td>
                    <td className="py-2">
                      <StatusPill label={ev.source} variant={ev.source === "live" ? "info" : "neutral"} />
                    </td>
                    <td className="py-2">
                      <StatusPill label={ev.severity} variant={ev.severity === "error" || ev.severity === "critical" ? "danger" : ev.severity === "warn" ? "warning" : "neutral"} />
                    </td>
                    <td className="py-2 max-w-md truncate" title={ev.summary}>{ev.summary}</td>
                  </tr>
                ))}
                {filteredTimeline.length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-8 text-center text-gray-400">No events</td>
                  </tr>
                )}
              </tbody>
            </table>
          </TableFrame>
        </PanelCard>

        {runQuality && runQuality.checks && (
          <PanelCard title="Data Quality" titleRight={<StatusPill label={runQuality.overall_status} variant={runQuality.overall_status === "pass" ? "success" : "warning"} />}>
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              {runQuality.checks.map((check) => (
                <div key={check.name} className={`rounded-lg p-3 ${qualityClass(check.status)}`}>
                  <div className="text-xs font-medium uppercase">{check.name}</div>
                  <div className="mt-1 text-sm">{check.message || check.status}</div>
                </div>
              ))}
            </div>
          </PanelCard>
        )}

        {runTrades.length > 0 && (
          <PanelCard title="Trades">
            <TableFrame>
              <div className="max-h-64 overflow-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 dark:border-gray-700">
                      <th className="pb-2 font-medium text-gray-500">Pair</th>
                      <th className="pb-2 font-medium text-gray-500">Side</th>
                      <th className="pb-2 font-medium text-gray-500">Entry</th>
                      <th className="pb-2 font-medium text-gray-500">Exit</th>
                      <th className="pb-2 font-medium text-gray-500">PnL</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runTrades.slice(0, 20).map((trade) => (
                      <tr key={trade.trade_id} className="border-b border-gray-100 py-2 dark:border-gray-800">
                        <td className="py-2 font-mono">{trade.pair}</td>
                        <td className="py-2">{trade.side}</td>
                        <td className="py-2">{fmtNumber(trade.entry_price)}</td>
                        <td className="py-2">{fmtNumber(trade.exit_price)}</td>
                        <td className={`py-2 font-mono ${(trade.realized_pnl ?? 0) >= 0 ? "text-success-600" : "text-danger-600"}`}>
                          {fmtSignedNumber(trade.realized_pnl)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </TableFrame>
          </PanelCard>
        )}
      </div>
    </DashboardShell>
  );
}
