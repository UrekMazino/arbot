export type TokenPair = {
  access_token: string;
  token_type: string;
  refresh_token: string;
};

export type RunSummary = {
  id: string;
  bot_instance_id: string;
  run_key: string;
  status: string;
  start_ts: string;
  end_ts: string | null;
  start_equity: number | null;
  end_equity: number | null;
  session_pnl: number | null;
  max_drawdown: number | null;
};

export type RunEvent = {
  id: string;
  event_id: string;
  run_id: string;
  ts: string;
  event_type: string;
  severity: string;
  payload_json: Record<string, unknown>;
};

export type Trade = {
  id: string;
  run_id: string;
  pair_key: string;
  entry_ts: string | null;
  exit_ts: string | null;
  side: string | null;
  entry_z: number | null;
  exit_z: number | null;
  pnl_usdt: number | null;
  hold_minutes: number | null;
  strategy: string | null;
  regime: string | null;
  exit_reason: string | null;
};

export type WalkForwardPoint = {
  exit_ts: string;
  pnl_usdt: number;
};

export type ScorecardCell = {
  entry_strategy: string | null;
  entry_regime: string | null;
  trades: number;
  wins: number;
  win_rate_pct: number | null;
  avg_pnl_usdt: number | null;
  sum_pnl_usdt: number | null;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8081/api/v2";

async function apiRequest<T>(
  path: string,
  options: RequestInit,
  token?: string,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (options.headers && typeof options.headers === "object" && !Array.isArray(options.headers)) {
    Object.assign(headers, options.headers as Record<string, string>);
  }

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    cache: "no-store",
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text}`);
  }

  return (await response.json()) as T;
}

export async function login(email: string, password: string): Promise<TokenPair> {
  return apiRequest<TokenPair>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function getRuns(token: string): Promise<RunSummary[]> {
  return apiRequest<RunSummary[]>("/runs?limit=100", { method: "GET" }, token);
}

export async function getRunEvents(token: string, runId: string): Promise<RunEvent[]> {
  return apiRequest<RunEvent[]>(`/runs/${runId}/events?limit=200`, { method: "GET" }, token);
}

export async function getRunTrades(token: string, runId: string): Promise<Trade[]> {
  return apiRequest<Trade[]>(`/runs/${runId}/trades?limit=300`, { method: "GET" }, token);
}

export async function getRunWalkForward(token: string, runId: string): Promise<WalkForwardPoint[]> {
  return apiRequest<WalkForwardPoint[]>(`/runs/${runId}/analytics/walk-forward`, { method: "GET" }, token);
}

export async function getRunScorecard(token: string, runId: string): Promise<ScorecardCell[]> {
  return apiRequest<ScorecardCell[]>(`/runs/${runId}/analytics/scorecard`, { method: "GET" }, token);
}

export function apiBaseUrl(): string {
  return API_BASE;
}

export function wsDashboardUrl(botInstanceId: string): string {
  const wsBase = process.env.NEXT_PUBLIC_WS_BASE || "ws://127.0.0.1:8081";
  const encoded = encodeURIComponent(botInstanceId);
  return `${wsBase}/ws/dashboard?bot_instance_id=${encoded}`;
}
