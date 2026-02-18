export type TokenPair = {
  access_token: string;
  token_type: string;
  refresh_token: string;
};

export type RoleRecord = {
  id: string;
  name: string;
  description: string | null;
};

export type UserRecord = {
  id: string;
  email: string;
  is_active: boolean;
  is_superuser: boolean;
  roles: RoleRecord[];
  created_at: string;
  updated_at: string;
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

export type DataQualityIssue = {
  event_id: string;
  ts: string;
  event_type: string;
  severity: string;
  message: string;
};

export type DataQualitySummary = {
  run_id: string;
  generated_at: string;
  overall_status: string;
  event_health: {
    total: number;
    warn: number;
    error: number;
    critical: number;
    typed_warning_events: Record<string, number>;
  };
  trade_integrity: {
    status: string;
    total_rows: number;
    closed_rows: number;
    open_rows: number;
    closed_missing_pnl: number;
    closed_missing_exit_reason: number;
  };
  reconciliation: {
    status: string;
    run_session_pnl_usdt: number | null;
    trade_pnl_sum_usdt: number;
    delta_usdt: number | null;
    delta_pct_of_session: number | null;
    threshold_pass_usdt: number;
    threshold_warn_usdt: number;
  };
  top_alerts: Array<{
    alert_type: string;
    count: number;
    last_seen: string | null;
  }>;
  recent_issues: DataQualityIssue[];
};

export type ConfigSnapshotResponse = {
  run_id: string;
  source: string;
  created_at: string | null;
  report_id: string | null;
  file_id: string | null;
  path: string | null;
  config_snapshot: Record<string, unknown> | null;
  error?: string;
};

export type ReportArtifactFile = {
  id: string;
  name: string;
  path: string;
  mime_type: string | null;
  size_bytes: number | null;
  checksum: string | null;
  created_at: string | null;
  download_url: string;
};

export type RunReportArtifact = {
  id: string;
  run_id: string;
  status: string;
  requested_by: string | null;
  requested_at: string | null;
  finished_at: string | null;
  error_text: string | null;
  files: ReportArtifactFile[];
};

export type AdminBotStatus = {
  running: boolean;
  pid: number;
  started_at?: string | null;
  stopped_at?: string | null;
  detail?: string;
  command?: string[];
  cwd?: string;
  requested_by?: string;
  latest_run_key?: string | null;
  latest_log_file?: string | null;
  workspace_root?: string;
  control_log_file?: string | null;
};

export type AdminLogTail = {
  run_key: string | null;
  log_file: string | null;
  line_count: number;
  lines: string[];
  updated_at: string;
  detail: string;
};

export type AdminLogRun = {
  run_key: string;
  log_file: string;
  size_bytes: number;
  mtime_ts: number;
};

export type AdminReportRun = {
  run_key: string;
  path: string;
  file_count: number;
  summary_json: boolean;
  mtime_ts: number;
};

export type AdminEnvSettings = {
  path: string;
  values: Record<string, string>;
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

export async function getMe(token: string): Promise<UserRecord> {
  return apiRequest<UserRecord>("/auth/me", { method: "GET" }, token);
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

export async function getRunDataQuality(token: string, runId: string): Promise<DataQualitySummary> {
  return apiRequest<DataQualitySummary>(`/runs/${runId}/analytics/data-quality`, { method: "GET" }, token);
}

export async function getRunConfigSnapshot(token: string, runId: string): Promise<ConfigSnapshotResponse> {
  return apiRequest<ConfigSnapshotResponse>(`/runs/${runId}/config-snapshot`, { method: "GET" }, token);
}

export async function getRunReportArtifacts(token: string, runId: string): Promise<RunReportArtifact[]> {
  return apiRequest<RunReportArtifact[]>(`/runs/${runId}/report-artifacts?limit=10`, { method: "GET" }, token);
}

export async function getAdminBotStatus(token: string): Promise<AdminBotStatus> {
  return apiRequest<AdminBotStatus>("/admin/bot/status", { method: "GET" }, token);
}

export async function startAdminBot(token: string): Promise<AdminBotStatus> {
  return apiRequest<AdminBotStatus>("/admin/bot/start", { method: "POST", body: JSON.stringify({}) }, token);
}

export async function stopAdminBot(token: string): Promise<AdminBotStatus> {
  return apiRequest<AdminBotStatus>("/admin/bot/stop", { method: "POST", body: JSON.stringify({}) }, token);
}

export async function getAdminBotLogTail(
  token: string,
  runKey: string,
  lines = 300,
): Promise<AdminLogTail> {
  const key = encodeURIComponent(runKey || "latest");
  return apiRequest<AdminLogTail>(`/admin/bot/logs/tail?run_key=${key}&lines=${lines}`, { method: "GET" }, token);
}

export async function getAdminLogRuns(token: string, limit = 100): Promise<AdminLogRun[]> {
  return apiRequest<AdminLogRun[]>(`/admin/logs/runs?limit=${limit}`, { method: "GET" }, token);
}

export async function getAdminReportRuns(token: string, limit = 100): Promise<AdminReportRun[]> {
  return apiRequest<AdminReportRun[]>(`/admin/reports/runs?limit=${limit}`, { method: "GET" }, token);
}

export async function getAdminEnvSettings(token: string): Promise<AdminEnvSettings> {
  return apiRequest<AdminEnvSettings>("/admin/settings/env", { method: "GET" }, token);
}

export async function updateAdminEnvSetting(token: string, key: string, value: string): Promise<AdminEnvSettings> {
  const encodedKey = encodeURIComponent(key);
  const res = await apiRequest<{ values: Record<string, string> }>(
    `/admin/settings/env/${encodedKey}`,
    {
      method: "PUT",
      body: JSON.stringify({ value }),
    },
    token,
  );
  return { path: "Execution/.env", values: res.values || {} };
}

export async function listUsers(token: string): Promise<UserRecord[]> {
  return apiRequest<UserRecord[]>("/users", { method: "GET" }, token);
}

export async function listRoles(token: string): Promise<RoleRecord[]> {
  return apiRequest<RoleRecord[]>("/users/roles", { method: "GET" }, token);
}

export async function createUser(
  token: string,
  body: { email: string; password: string; is_active?: boolean; is_superuser?: boolean },
): Promise<UserRecord> {
  return apiRequest<UserRecord>(
    "/users",
    {
      method: "POST",
      body: JSON.stringify({
        email: body.email,
        password: body.password,
        is_active: body.is_active ?? true,
        is_superuser: body.is_superuser ?? false,
      }),
    },
    token,
  );
}

export async function assignUserRole(token: string, userId: string, role: string): Promise<{ message: string }> {
  const encodedUser = encodeURIComponent(userId);
  return apiRequest<{ message: string }>(
    `/users/${encodedUser}/roles`,
    { method: "POST", body: JSON.stringify({ role }) },
    token,
  );
}

export async function removeUserRole(token: string, userId: string, role: string): Promise<{ message: string }> {
  const encodedUser = encodeURIComponent(userId);
  const encodedRole = encodeURIComponent(role);
  return apiRequest<{ message: string }>(`/users/${encodedUser}/roles/${encodedRole}`, { method: "DELETE" }, token);
}

export function apiBaseUrl(): string {
  return API_BASE;
}

export function apiRootUrl(): string {
  return API_BASE.replace(/\/api\/v2\/?$/, "");
}

export function wsDashboardUrl(botInstanceId: string): string {
  const wsBase = process.env.NEXT_PUBLIC_WS_BASE || "ws://127.0.0.1:8081";
  const encoded = encodeURIComponent(botInstanceId);
  return `${wsBase}/ws/dashboard?bot_instance_id=${encoded}`;
}
