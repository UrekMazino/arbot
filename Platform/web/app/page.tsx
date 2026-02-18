"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import {
  RunEvent,
  RunSummary,
  ScorecardCell,
  Trade,
  WalkForwardPoint,
  apiBaseUrl,
  getRunEvents,
  getRunScorecard,
  getRunTrades,
  getRunWalkForward,
  getRuns,
  login,
  wsDashboardUrl,
} from "../lib/api";

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

function AttributionTable({ scorecard }: { scorecard: ScorecardCell[] }) {
  if (!scorecard.length) return <p className="muted">No attribution rows yet.</p>;
  return (
    <div className="table-wrap compact">
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
    </div>
  );
}

export default function HomePage() {
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
  const [liveFeed, setLiveFeed] = useState<LiveMsg[]>([]);
  const [timelineCategory, setTimelineCategory] = useState<TimelineFilterCategory>("core");
  const [timelineSeverity, setTimelineSeverity] = useState<TimelineSeverity>("all");
  const [timelineSource, setTimelineSource] = useState<"all" | TimelineSource>("all");
  const [status, setStatus] = useState<string>("Signed out");
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(false);

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

  const loadRuns = useCallback(async (authToken: string) => {
    const nextRuns = await getRuns(authToken);
    setRuns(nextRuns);
    if (nextRuns.length && !selectedRunId) {
      setSelectedRunId(nextRuns[0].id);
    }
  }, [selectedRunId]);

  const refreshRunDetails = useCallback(async (authToken: string, runId: string) => {
    if (!runId) return;
    const [runEvents, runTrades, runWalkForward, runScorecard] = await Promise.all([
      getRunEvents(authToken, runId),
      getRunTrades(authToken, runId),
      getRunWalkForward(authToken, runId),
      getRunScorecard(authToken, runId),
    ]);
    setEvents(runEvents);
    setTrades(runTrades);
    setWalkForward(runWalkForward);
    setScorecard(runScorecard);
  }, []);

  const equitySeries = useMemo(() => {
    if (!walkForward.length) return [] as { ts: string; equity: number }[];
    let cumulative = 0;
    return walkForward.map((point) => {
      cumulative += point.pnl_usdt || 0;
      return { ts: point.exit_ts, equity: cumulative };
    });
  }, [walkForward]);

  const drawdownSeries = useMemo(() => {
    if (!equitySeries.length) return [] as { ts: string; drawdown: number }[];
    let peak = Number.NEGATIVE_INFINITY;
    return equitySeries.map((point) => {
      peak = Math.max(peak, point.equity);
      return {
        ts: point.ts,
        drawdown: point.equity - peak,
      };
    });
  }, [equitySeries]);

  const equityChart = useMemo(() => {
    const values = equitySeries.map((row) => row.equity);
    const labels = equitySeries.map((row) => row.ts);
    const points = buildChartPoints(values, labels);
    const latest = values.length ? values[values.length - 1] : 0;
    return { points, path: pointsToPath(points), latest };
  }, [equitySeries]);

  const drawdownChart = useMemo(() => {
    const values = drawdownSeries.map((row) => row.drawdown);
    const labels = drawdownSeries.map((row) => row.ts);
    const points = buildChartPoints(values, labels);
    const worst = values.length ? Math.min(...values) : 0;
    return { points, path: pointsToPath(points), worst };
  }, [drawdownSeries]);

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

  async function onLoginSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const pair = await login(email, password);
      setToken(pair.access_token);
      setRefreshToken(pair.refresh_token);
      localStorage.setItem("v2_access_token", pair.access_token);
      localStorage.setItem("v2_refresh_token", pair.refresh_token);
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
    setToken("");
    setRefreshToken("");
    setRuns([]);
    setSelectedRunId("");
    setEvents([]);
    setTrades([]);
    setWalkForward([]);
    setScorecard([]);
    setLiveFeed([]);
    localStorage.removeItem("v2_access_token");
    localStorage.removeItem("v2_refresh_token");
    setStatus("Signed out");
  }

  useEffect(() => {
    const stored = localStorage.getItem("v2_access_token") || "";
    const storedRefresh = localStorage.getItem("v2_refresh_token") || "";
    if (stored) {
      setToken(stored);
      setRefreshToken(storedRefresh);
      setStatus("Session restored");
      loadRuns(stored).catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : "Failed to load runs";
        setError(msg);
      });
    }
  }, [loadRuns]);

  useEffect(() => {
    if (!token || !selectedRunId) return;
    refreshRunDetails(token, selectedRunId).catch((err: unknown) => {
      const msg = err instanceof Error ? err.message : "Failed to load run detail";
      setError(msg);
    });
  }, [token, selectedRunId, refreshRunDetails]);

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
    <main className="page-shell">
      <section className="hero">
        <p className="eyebrow">V2 UI Foundation</p>
        <h1>Run Browser + Live Event Stream</h1>
        <p>
          API: <code>{apiBaseUrl()}</code>
        </p>
      </section>

      <section className="auth-panel card">
        <div>
          <h2>Session</h2>
          <p className="muted">{status}</p>
          {refreshToken ? <p className="tiny">Refresh token present</p> : null}
        </div>
        {!token ? (
          <form onSubmit={onLoginSubmit} className="auth-form">
            <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" required />
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              type="password"
              required
            />
            <button type="submit" disabled={loading}>
              {loading ? "Signing in..." : "Sign in"}
            </button>
          </form>
        ) : (
          <div className="auth-actions">
            <button onClick={() => loadRuns(token)}>Refresh runs</button>
            <button onClick={() => selectedRunId && refreshRunDetails(token, selectedRunId)}>Refresh detail</button>
            <button className="ghost" onClick={onLogout}>
              Logout
            </button>
          </div>
        )}
        {error ? <p className="error">{error}</p> : null}
      </section>

      <section className="grid-main">
        <article className="card">
          <h3>Runs</h3>
          <div className="table-wrap">
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
                {runs.map((run) => {
                  const active = run.id === selectedRunId;
                  return (
                    <tr
                      key={run.id}
                      className={active ? "active-row" : ""}
                      onClick={() => setSelectedRunId(run.id)}
                    >
                      <td>{run.run_key}</td>
                      <td>{run.status}</td>
                      <td>{fmtNumber(run.session_pnl)}</td>
                      <td>{fmtDuration(run.start_ts, run.end_ts)}</td>
                    </tr>
                  );
                })}
                {!runs.length ? (
                  <tr>
                    <td colSpan={4} className="muted">
                      No runs yet.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </article>

        <article className="card detail">
          <h3>Run Detail</h3>
          {selectedRun ? (
            <div className="detail-block">
              <p>
                <strong>Run:</strong> {selectedRun.run_key}
              </p>
              <p>
                <strong>Bot:</strong> {selectedRun.bot_instance_id}
              </p>
              <p>
                <strong>Started:</strong> {fmtDate(selectedRun.start_ts)}
              </p>
              <p>
                <strong>Ended:</strong> {fmtDate(selectedRun.end_ts)}
              </p>
            </div>
          ) : (
            <p className="muted">Select a run.</p>
          )}

          <div className="stats-row">
            <div className="stat-box">
              <span>Trades</span>
              <strong>{tradeStats.trades}</strong>
            </div>
            <div className="stat-box">
              <span>Win Rate</span>
              <strong>{fmtNumber(tradeStats.winRate)}%</strong>
            </div>
            <div className="stat-box">
              <span>Total PnL</span>
              <strong>{fmtNumber(tradeStats.pnl)}</strong>
            </div>
          </div>

          <h4>Event Timeline</h4>
          <div className="timeline-toolbar">
            <label>
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
            <label>
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
            <label>
              Source
              <select value={timelineSource} onChange={(e) => setTimelineSource(e.target.value as "all" | TimelineSource)}>
                <option value="all">All</option>
                <option value="history">Stored events</option>
                <option value="live">WebSocket live</option>
              </select>
            </label>
            <span className="timeline-count muted">{timelineEvents.length} shown</span>
          </div>

          <ul className="timeline events">
            {timelineEvents.map((row) => (
              <li key={row.id}>
                <div className="timeline-line">
                  <span className={`pill ${row.severity}`}>{row.severity}</span>
                  <span className={`pill category-${row.category}`}>{row.category}</span>
                  <strong>{row.eventType}</strong>
                  <span className="timeline-source muted">{row.source === "history" ? "stored" : "live"}</span>
                  <time>{new Date(row.tsMs).toLocaleString()}</time>
                </div>
                {row.summary ? <p className="timeline-summary">{row.summary}</p> : null}
              </li>
            ))}
            {!timelineEvents.length ? <li className="muted">No timeline events match the current filters.</li> : null}
          </ul>
        </article>
      </section>

      <section className="grid-analytics">
        <article className="card">
          <h3>Equity Curve (Realized)</h3>
          {equityChart.points.length ? (
            <>
              <div className="chart-meta">
                <span>Closed trades: {equityChart.points.length}</span>
                <strong>Latest cumulative PnL: {fmtNumber(equityChart.latest)} USDT</strong>
              </div>
              <svg viewBox="0 0 620 190" className="chart-svg" role="img" aria-label="Equity curve chart">
                <path d={equityChart.path} fill="none" stroke="#0f766e" strokeWidth="3" />
              </svg>
            </>
          ) : (
            <p className="muted">No walk-forward points yet.</p>
          )}
        </article>

        <article className="card">
          <h3>Drawdown Curve</h3>
          {drawdownChart.points.length ? (
            <>
              <div className="chart-meta">
                <span>Computed from cumulative realized PnL</span>
                <strong>Worst drawdown: {fmtNumber(drawdownChart.worst)} USDT</strong>
              </div>
              <svg viewBox="0 0 620 190" className="chart-svg" role="img" aria-label="Drawdown chart">
                <path d={drawdownChart.path} fill="none" stroke="#b45309" strokeWidth="3" />
              </svg>
            </>
          ) : (
            <p className="muted">No drawdown data yet.</p>
          )}
        </article>
      </section>

      <section className="card">
        <h3>Strategy x Regime Attribution</h3>
        <AttributionTable scorecard={scorecard} />
      </section>
    </main>
  );
}
