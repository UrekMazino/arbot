"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import {
  RunEvent,
  RunSummary,
  Trade,
  apiBaseUrl,
  getRunEvents,
  getRunTrades,
  getRuns,
  login,
  wsDashboardUrl,
} from "../lib/api";

type LiveMsg = {
  event_type?: string;
  ts?: number;
  payload?: Record<string, unknown>;
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

export default function HomePage() {
  const [email, setEmail] = useState("admin@okxstatbot.dev");
  const [password, setPassword] = useState("ChangeMeNow123!");
  const [token, setToken] = useState<string>("");
  const [refreshToken, setRefreshToken] = useState<string>("");
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [liveFeed, setLiveFeed] = useState<LiveMsg[]>([]);
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
    const [runEvents, runTrades] = await Promise.all([
      getRunEvents(authToken, runId),
      getRunTrades(authToken, runId),
    ]);
    setEvents(runEvents);
    setTrades(runTrades);
  }, []);

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
        setLiveFeed((prev) => [parsed, ...prev].slice(0, 20));
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

          <h4>Recent Events</h4>
          <ul className="timeline">
            {events.slice(0, 12).map((ev) => (
              <li key={ev.event_id}>
                <span className={`pill ${ev.severity}`}>{ev.severity}</span>
                <strong>{ev.event_type}</strong>
                <time>{fmtDate(ev.ts)}</time>
              </li>
            ))}
            {!events.length ? <li className="muted">No events loaded.</li> : null}
          </ul>

          <h4>Live Feed</h4>
          <ul className="timeline small">
            {liveFeed.slice(0, 8).map((msg, idx) => (
              <li key={`${msg.event_type || "evt"}-${idx}`}>
                <strong>{msg.event_type || "message"}</strong>
                <time>{msg.ts ? new Date(msg.ts * 1000).toLocaleTimeString() : "now"}</time>
              </li>
            ))}
            {!liveFeed.length ? <li className="muted">Waiting for websocket events.</li> : null}
          </ul>
        </article>
      </section>
    </main>
  );
}
