export type MessageResponse = {
  message: string;
};

export type ForgotPasswordResponse = {
  message: string;
  reset_token?: string;
};

export type RoleRecord = {
  id: string;
  name: string;
  description: string | null;
  permissions: string[];
};

export type UserRecord = {
  id: string;
  email: string;
  is_active: boolean;
  permissions: string[];
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

export type RunPairSegment = {
  id: string;
  run_id: string;
  pair: string;
  sequence_no: number;
  started_at: string | null;
  ended_at: string | null;
  switch_reason: string | null;
  duration_seconds: number;
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
  run_key?: string | null;
  run_log_file?: string | null;
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
  equity: number | null;
  starting_equity: number | null;
  session_pnl: number | null;
  session_pnl_pct: number | null;
  run_start_time: number | null;
  pair_history: Array<{ pair: string; duration_seconds: number }>;
  pair_count: number;
};

export type AdminRunRuntime = {
  run_id: string | null;
  run_key: string | null;
  status: string;
  running: boolean;
  detail: string;
  started_at: string | null;
  stopped_at: string | null;
  updated_at: string | null;
  duration_seconds: number;
  starting_equity: number | null;
  equity: number | null;
  session_pnl: number | null;
  session_pnl_pct: number | null;
  run_start_time: number | null;
  pair_history: Array<{ pair: string; duration_seconds: number }>;
  pair_count: number;
  current_pair: string | null;
  latest_regime: string | null;
  latest_strategy: string | null;
  source: string;
};

export type AdminLogRun = {
  run_key: string;
  log_file: string;
  size_bytes: number;
  mtime_ts: number;
};

export type AdminLogFile = {
  run_key: string;
  log_file: string;
  content: string;
  size_bytes: number;
  line_count: number;
  updated_at: string;
};

export type AdminReportRun = {
  run_key: string;
  path: string;
  file_count: number;
  summary_json: boolean;
  mtime_ts: number;
};

export type AdminReportArtifactFile = {
  name: string;
  format: string | null;
  rows: number | null;
  size_bytes: number | null;
  mtime_ts: number | null;
  mime_type: string | null;
};

export type AdminReportSummary = {
  run_key: string;
  run_id: string | null;
  path: string;
  refreshed: boolean;
  summary_available: boolean;
  generated_at: string | null;
  report_version: string | null;
  report_source: string | null;
  summary: Record<string, unknown> | null;
  manifest: Record<string, unknown> | null;
  files: AdminReportArtifactFile[];
};

export type AdminEnvSettings = {
  path: string;
  values: Record<string, string>;
};

export type PairHealthEntry = {
  pair: string;
  reason: string;
  added_at: number;
  cooldown_seconds?: number;
  elapsed_seconds?: number;
  remaining_seconds?: number;
  is_ready?: boolean;
  visits?: number;
  ttl_days?: number | null;
};

export type RestrictedTickerEntry = {
  ticker: string;
  reason: string;
  message: string;
  code: string;
  added_at: number;
  ttl_days?: number | null;
  source: string;
};

export type AdminPairsHealth = {
  hospital: PairHealthEntry[];
  graveyard: PairHealthEntry[];
  restricted_tickers: RestrictedTickerEntry[];
  active_pair: Record<string, unknown> | null;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8081/api/v2";

async function apiRequest<T>(
  path: string,
  options: RequestInit,
  retry = false,
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (options.headers && typeof options.headers === "object" && !Array.isArray(options.headers)) {
    Object.assign(headers, options.headers as Record<string, string>);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    cache: "no-store",
    credentials: "include",
  });

  if (!response.ok) {
    if (
      response.status === 401 &&
      !retry &&
      !path.startsWith("/auth/login") &&
      !path.startsWith("/auth/refresh")
    ) {
      try {
        await refreshSession();
        return apiRequest<T>(path, options, true);
      } catch {
        // ignore refresh failure and return original error
      }
    }

    const text = await response.text();
    let message = text;
    try {
      const parsed = JSON.parse(text);
      if (parsed && typeof parsed === "object") {
        const parsedRecord = parsed as Record<string, unknown>;
        if (response.status === 400 || response.status === 422) {
          message = "Invalid request. Please check your input and try again.";
        } else if (typeof parsedRecord.detail === "string") {
          message = parsedRecord.detail;
        } else if (typeof parsedRecord.message === "string") {
          message = parsedRecord.message;
        }
      }
    } catch {
      // ignore parse errors and keep raw text
    }
    throw new Error(`HTTP ${response.status}: ${message}`);
  }

  return (await response.json()) as T;
}

function parseContentDispositionFilename(value: string | null): string | null {
  if (!value) return null;
  const utf8Match = value.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }
  const basicMatch = value.match(/filename="?([^"]+)"?/i);
  return basicMatch?.[1] ?? null;
}

async function downloadApiFile(path: string, fallbackFilename: string): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "GET",
    cache: "no-store",
    credentials: "include",
  });

  if (!response.ok) {
    const text = await response.text();
    let message = text;
    try {
      const parsed = JSON.parse(text);
      if (parsed && typeof parsed === "object") {
        const parsedRecord = parsed as Record<string, unknown>;
        if (typeof parsedRecord.detail === "string") {
          message = parsedRecord.detail;
        } else if (typeof parsedRecord.message === "string") {
          message = parsedRecord.message;
        }
      }
    } catch {
      // ignore parse errors and keep raw text
    }
    throw new Error(`HTTP ${response.status}: ${message}`);
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const filename = parseContentDispositionFilename(response.headers.get("Content-Disposition")) || fallbackFilename;
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

export async function login(email: string, password: string, rememberMe = true): Promise<MessageResponse> {
  return apiRequest<MessageResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password, remember_me: rememberMe }),
  });
}

export async function refreshSession(): Promise<MessageResponse> {
  return apiRequest<MessageResponse>("/auth/refresh", { method: "POST" });
}

export async function logout(): Promise<MessageResponse> {
  return apiRequest<MessageResponse>("/auth/logout", { method: "POST" });
}

export async function forgotPassword(email: string): Promise<ForgotPasswordResponse> {
  return apiRequest<ForgotPasswordResponse>("/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function resetPassword(resetToken: string, password: string): Promise<MessageResponse> {
  return apiRequest<MessageResponse>("/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ reset_token: resetToken, password }),
  });
}

export async function getMe(): Promise<UserRecord> {
  return apiRequest<UserRecord>("/auth/me", { method: "GET" });
}

export async function getRuns(): Promise<RunSummary[]> {
  return apiRequest<RunSummary[]>("/runs?limit=100", { method: "GET" });
}

export async function getRunEvents(runId: string): Promise<RunEvent[]> {
  return apiRequest<RunEvent[]>(`/runs/${runId}/events?limit=200`, { method: "GET" });
}

export async function getRunTrades(runId: string): Promise<Trade[]> {
  return apiRequest<Trade[]>(`/runs/${runId}/trades?limit=300`, { method: "GET" });
}

export async function getRunPairSegments(runId: string): Promise<RunPairSegment[]> {
  return apiRequest<RunPairSegment[]>(`/runs/${runId}/pair-segments`, { method: "GET" });
}

export async function getRunWalkForward(runId: string): Promise<WalkForwardPoint[]> {
  return apiRequest<WalkForwardPoint[]>(`/runs/${runId}/analytics/walk-forward`, { method: "GET" });
}

export async function getRunScorecard(runId: string): Promise<ScorecardCell[]> {
  return apiRequest<ScorecardCell[]>(`/runs/${runId}/analytics/scorecard`, { method: "GET" });
}

export async function getRunDataQuality(runId: string): Promise<DataQualitySummary> {
  return apiRequest<DataQualitySummary>(`/runs/${runId}/analytics/data-quality`, { method: "GET" });
}

export async function getRunConfigSnapshot(runId: string): Promise<ConfigSnapshotResponse> {
  return apiRequest<ConfigSnapshotResponse>(`/runs/${runId}/config-snapshot`, { method: "GET" });
}

export async function getRunReportArtifacts(runId: string): Promise<RunReportArtifact[]> {
  return apiRequest<RunReportArtifact[]>(`/runs/${runId}/report-artifacts?limit=10`, { method: "GET" });
}

export async function getAdminBotStatus(): Promise<AdminBotStatus> {
  return apiRequest<AdminBotStatus>("/admin/bot/status", { method: "GET" });
}

export async function startAdminBot(): Promise<AdminBotStatus> {
  return apiRequest<AdminBotStatus>("/admin/bot/start", { method: "POST", body: JSON.stringify({}) });
}

export async function stopAdminBot(): Promise<AdminBotStatus> {
  return apiRequest<AdminBotStatus>("/admin/bot/stop", { method: "POST", body: JSON.stringify({}) });
}

export async function getAdminBotLogTail(
  runKey: string,
  lines = 300,
): Promise<AdminLogTail> {
  const key = encodeURIComponent(runKey || "latest");
  return apiRequest<AdminLogTail>(`/admin/bot/logs/tail?run_key=${key}&lines=${lines}`, { method: "GET" });
}

export async function getAdminRunRuntime(runKey: string): Promise<AdminRunRuntime> {
  const key = encodeURIComponent(runKey || "latest");
  return apiRequest<AdminRunRuntime>(`/admin/runs/runtime?run_key=${key}`, { method: "GET" });
}

export async function getAdminLogRuns(limit = 100): Promise<AdminLogRun[]> {
  return apiRequest<AdminLogRun[]>(`/admin/logs/runs?limit=${limit}`, { method: "GET" });
}

export async function getAdminLogFile(runKey: string): Promise<AdminLogFile> {
  const key = encodeURIComponent(runKey);
  return apiRequest<AdminLogFile>(`/admin/logs/runs/${key}`, { method: "GET" });
}

export async function deleteAdminLogRun(runKey: string): Promise<{ deleted: boolean; run_key: string; log_file: string | null; removed_files: number; removed_report_files?: number; deleted_report_dir?: boolean }> {
  const key = encodeURIComponent(runKey);
  return apiRequest<{ deleted: boolean; run_key: string; log_file: string | null; removed_files: number; removed_report_files?: number; deleted_report_dir?: boolean }>(`/admin/logs/runs/${key}`, { method: "DELETE" });
}

export async function getAdminReportRuns(limit = 100): Promise<AdminReportRun[]> {
  return apiRequest<AdminReportRun[]>(`/admin/reports/runs?limit=${limit}`, { method: "GET" });
}

export async function getAdminReportRunSummary(runKey: string): Promise<AdminReportSummary> {
  const key = encodeURIComponent(runKey);
  return apiRequest<AdminReportSummary>(`/admin/reports/runs/${key}/summary`, { method: "GET" });
}

export async function downloadAdminReportFile(runKey: string, fileName: string): Promise<void> {
  const key = encodeURIComponent(runKey);
  const name = encodeURIComponent(fileName);
  await downloadApiFile(`/admin/reports/runs/${key}/files/${name}/download`, fileName);
}

export async function downloadAdminReportZip(runKey: string): Promise<void> {
  const key = encodeURIComponent(runKey);
  await downloadApiFile(`/admin/reports/runs/${key}/download`, `${runKey}_report.zip`);
}

export async function getAdminEnvSettings(): Promise<AdminEnvSettings> {
  return apiRequest<AdminEnvSettings>("/admin/settings/env", { method: "GET" });
}

export async function updateAdminEnvSetting(key: string, value: string): Promise<AdminEnvSettings> {
  const encodedKey = encodeURIComponent(key);
  const res = await apiRequest<{ values: Record<string, string> }>(
    `/admin/settings/env/${encodedKey}`,
    {
      method: "PUT",
      body: JSON.stringify({ value }),
    },
  );
  return { path: "Execution/.env", values: res.values || {} };
}

export async function getAdminPairsHealth(): Promise<AdminPairsHealth> {
  return apiRequest<AdminPairsHealth>("/admin/pairs/health", { method: "GET" });
}

export async function clearAdminActivePair(): Promise<{
  ok: boolean;
  cleared: boolean;
  file_existed: boolean;
  running: boolean;
  detail: string;
  requested_by: string;
  previous_active_pair: Record<string, string> | null;
  active_pair: null;
}> {
  return apiRequest("/admin/pairs/active/clear", { method: "POST", body: JSON.stringify({}) });
}

export interface ClearLogsResult {
  deleted_logs: number;
  deleted_reports: number;
  deleted_log_files: number;
  deleted_run_rows?: number;
  deleted_run_events?: number;
  deleted_pair_segments?: number;
  deleted_trades?: number;
  deleted_strategy_metrics?: number;
  deleted_regime_metrics?: number;
  deleted_bot_configs?: number;
  deleted_alerts?: number;
  deleted_position_snapshots?: number;
  deleted_report_rows: number;
  deleted_report_files: number;
  deleted_indexes: number;
  kept_latest: boolean;
  errors: string[];
}

export async function clearAdminLogs(keepLatest = false): Promise<ClearLogsResult> {
  return apiRequest<ClearLogsResult>(`/admin/logs/clear?keep_latest=${keepLatest}`, { method: "POST" });
}

export async function listUsers(): Promise<UserRecord[]> {
  return apiRequest<UserRecord[]>("/users", { method: "GET" });
}

export async function listRoles(): Promise<RoleRecord[]> {
  return apiRequest<RoleRecord[]>("/users/roles", { method: "GET" });
}

export async function createUser(
  body: { email: string; password: string; is_active?: boolean },
): Promise<UserRecord> {
  return apiRequest<UserRecord>(
    "/users",
    {
      method: "POST",
      body: JSON.stringify({
        email: body.email,
        password: body.password,
        is_active: body.is_active ?? true,
      }),
    },
  );
}

export async function assignUserRole(userId: string, role: string): Promise<{ message: string }> {
  const encodedUser = encodeURIComponent(userId);
  return apiRequest<{ message: string }>(
    `/users/${encodedUser}/roles`,
    { method: "POST", body: JSON.stringify({ role }) },
  );
}

export async function removeUserRole(userId: string, role: string): Promise<{ message: string }> {
  const encodedUser = encodeURIComponent(userId);
  const encodedRole = encodeURIComponent(role);
  return apiRequest<{ message: string }>(`/users/${encodedUser}/roles/${encodedRole}`, { method: "DELETE" });
}

export async function deleteUser(userId: string): Promise<{ message: string }> {
  const encodedUser = encodeURIComponent(userId);
  return apiRequest<{ message: string }>(`/users/${encodedUser}`, { method: "DELETE" });
}

export async function updateUserPermissions(
  userId: string,
  permissions: string[],
): Promise<UserRecord> {
  const encodedUser = encodeURIComponent(userId);
  return apiRequest<UserRecord>(
    `/users/${encodedUser}/permissions`,
    {
      method: "PUT",
      body: JSON.stringify({ permissions }),
    },
  );
}

export async function createRole(
  body: { name: string; description?: string | null; permissions?: string[] },
): Promise<RoleRecord> {
  return apiRequest<RoleRecord>(
    "/users/roles",
    {
      method: "POST",
      body: JSON.stringify({
        name: body.name,
        description: body.description || null,
        permissions: body.permissions || [],
      }),
    },
  );
}

export async function updateRole(
  roleId: string,
  body: { name?: string; description?: string | null; permissions?: string[] },
): Promise<RoleRecord> {
  const encodedRoleId = encodeURIComponent(roleId);
  return apiRequest<RoleRecord>(
    `/users/roles/${encodedRoleId}`,
    {
      method: "PUT",
      body: JSON.stringify(body),
    },
  );
}

export async function deleteRole(roleId: string): Promise<{ message: string }> {
  const encodedRoleId = encodeURIComponent(roleId);
  return apiRequest<{ message: string }>(`/users/roles/${encodedRoleId}`, { method: "DELETE" });
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

export function isUnauthorizedError(err: unknown): boolean {
  return err instanceof Error && err.message.includes("HTTP 401");
}

export function isForbiddenError(err: unknown): boolean {
  return err instanceof Error && err.message.includes("HTTP 403");
}
