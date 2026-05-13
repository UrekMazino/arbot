"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  RiskEventSummary,
  RiskHealthDashboardResponse,
  UserRecord,
  getMe,
  getRiskHealthDashboard,
  isUnauthorizedError,
} from "../../../../lib/api";
import { getStoredAdminEmail } from "../../../../lib/auth";
import {
  canAccessAdminPath,
  getAdminNavItems,
  getFirstAccessibleAdminPath,
} from "../../../../lib/admin-access";
import { UI_CLASSES } from "../../../../lib/ui-classes";
import { DashboardShell } from "../../../../components/dashboard-shell";
import { MetricCard, PanelCard, StatusPill, TableFrame } from "../../../../components/panels";

type RiskRange = "24h" | "7d" | "30d" | "all";
type PairHealthRow = string | Record<string, unknown>;

const ACTIVE_HREF = "/admin/dashboard/risk-health";
const RANGE_OPTIONS: Array<{ value: RiskRange; label: string; seconds: number | null }> = [
  { value: "24h", label: "24H", seconds: 86_400 },
  { value: "7d", label: "7D", seconds: 7 * 86_400 },
  { value: "30d", label: "30D", seconds: 30 * 86_400 },
  { value: "all", label: "All", seconds: null },
];

export default function RiskHealthPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserRecord | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<RiskRange>("24h");
  const [dashboard, setDashboard] = useState<RiskHealthDashboardResponse | null>(null);

  const navItems = useMemo(() => getAdminNavItems(user), [user]);
  const auth = useMemo(() => ({ email: getStoredAdminEmail(), hasToken: true }), []);

  useEffect(() => {
    getMe()
      .then((record) => setUser(record))
      .catch(() => setUser(null))
      .finally(() => setAuthLoading(false));
  }, []);

  useEffect(() => {
    if (authLoading || !user) return;
    const hasAccess = canAccessAdminPath(user, pathname);
    const firstAccessible = getFirstAccessibleAdminPath(user);
    if (!hasAccess) {
      router.replace(firstAccessible ?? "/");
    }
  }, [authLoading, pathname, router, user]);

  const loadDashboard = useCallback(
    async (forceRefresh = false) => {
      setDashboardLoading(true);
      setRefreshing(forceRefresh);
      setError(null);
      try {
        const response = await getRiskHealthDashboard({
          startTs: rangeStartTs(range),
          endTs: range === "all" ? undefined : Math.floor(Date.now() / 1000),
          refresh: forceRefresh,
        });
        setDashboard(response);
      } catch (err) {
        setDashboard(null);
        setError(isUnauthorizedError(err) ? "Unauthorized" : errorMessage(err, "Failed to load risk and health dashboard."));
      } finally {
        setDashboardLoading(false);
        setRefreshing(false);
      }
    },
    [range],
  );

  useEffect(() => {
    if (authLoading) return;
    void loadDashboard(false);
  }, [authLoading, loadDashboard]);

  const cacheStatus = dashboard?.cache
    ? `Updated ${formatTimestamp(dashboard.cache.generated_at)} | ${dashboard.cache.cache_hit ? "cache hit" : "fresh"} | TTL ${dashboard.cache.ttl_seconds ?? "n/a"}s`
    : "Read-only";
  const alertCount = dashboard?.alerts.length ?? 0;
  const liquidityStressCount = dashboard?.pair_health.liquidity_stress_pairs.length ?? null;

  if (authLoading) {
    return (
      <DashboardShell
        title="Risk & Health"
        subtitle="Read-only safety, pair health, and execution telemetry."
        status="Loading"
        activeHref={ACTIVE_HREF}
        navItems={navItems}
        auth={auth}
      >
        <PanelCard title="Loading" subtitle="Checking dashboard access.">
          <p className="text-sm text-gray-500 dark:text-gray-400">Loading risk dashboard...</p>
        </PanelCard>
      </DashboardShell>
    );
  }

  return (
    <DashboardShell
      title="Risk & Health"
      subtitle="Is the bot safe to keep running?"
      status={dashboardLoading ? "Loading risk..." : cacheStatus}
      activeHref={ACTIVE_HREF}
      navItems={navItems}
      auth={auth}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <select
            className={UI_CLASSES.inputSmall}
            value={range}
            onChange={(event) => setRange(event.target.value as RiskRange)}
          >
            {RANGE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            className={UI_CLASSES.secondaryButton}
            onClick={() => void loadDashboard(true)}
            disabled={refreshing}
          >
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      }
    >
      {error ? (
        <PanelCard title="Unable to load Risk & Health" subtitle={error}>
          <button type="button" className={UI_CLASSES.primaryButton} onClick={() => void loadDashboard(true)}>
            Retry
          </button>
        </PanelCard>
      ) : null}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Current Drawdown" value={formatMoney(dashboard?.risk_kpis.current_drawdown_usdt)} tone="rose" />
        <MetricCard label="Daily Loss Limit Usage" value={formatPercent(dashboard?.risk_kpis.daily_loss_limit_usage_pct)} tone="amber" />
        <MetricCard label="Open Exposure" value={formatMoney(dashboard?.risk_kpis.open_exposure_usdt)} tone="amber" />
        <MetricCard label="Open Positions" value={formatInteger(dashboard?.risk_kpis.open_positions)} tone="sky" />
        <MetricCard label="Orphan/Desync Status" value={formatText(dashboard?.risk_kpis.orphan_desync_status)} tone={dashboard?.risk_kpis.orphan_desync_status ? "rose" : "sky"} />
        <MetricCard label="API Latency" value={formatLatency(dashboard?.risk_kpis.api_latency_ms)} tone="violet" />
        <MetricCard label="Order Failures" value={formatInteger(dashboard?.risk_kpis.order_failure_count)} tone="rose" />
        <MetricCard label="Stale Orderbooks" value={formatInteger(dashboard?.risk_kpis.orderbook_stale_count)} tone="amber" />
      </section>

      <PanelCard
        title="Active Alerts"
        subtitle="Deduplicated by alert type and pair within the backend risk window."
        titleRight={<StatusPill label={`${alertCount} active`} tone={alertCount > 0 ? "warning" : "success"} />}
      >
        <AlertsTable alerts={dashboard?.alerts ?? []} />
      </PanelCard>

      <section className="grid gap-4 xl:grid-cols-2">
        <PanelCard title="Pair Health" subtitle="Pair lifecycle and stored score risk categories.">
          <div className="grid gap-4">
            <PairHealthTable title="Hospital pairs" rows={dashboard?.pair_health.hospital_pairs ?? []} valueKey="reason" />
            <PairHealthTable title="Graveyard pairs" rows={dashboard?.pair_health.graveyard_pairs ?? []} valueKey="reason" />
            <PairHealthTable title="High break-risk pairs" rows={dashboard?.pair_health.high_break_risk_pairs ?? []} valueKey="break_risk" />
            <PairHealthTable title="High hedge-drift positions" rows={dashboard?.pair_health.high_hedge_drift_positions ?? []} valueKey="hedge_ratio_drift_pct" />
            <PairHealthTable title="Liquidity stress pairs" rows={dashboard?.pair_health.liquidity_stress_pairs ?? []} valueKey="liquidity_score" />
          </div>
        </PanelCard>

        <PanelCard title="Execution Health" subtitle="Stored heartbeat and event-derived execution safety signals.">
          <KeyValueGrid
            rows={[
              ["API latency", formatLatency(dashboard?.risk_kpis.api_latency_ms)],
              ["Order failures", formatInteger(dashboard?.risk_kpis.order_failure_count)],
              ["Stale orderbooks", formatInteger(dashboard?.risk_kpis.orderbook_stale_count)],
              ["Orphan/desync status", formatText(dashboard?.risk_kpis.orphan_desync_status)],
              ["Liquidity stress count", liquidityStressCount === null ? "n/a" : formatInteger(liquidityStressCount)],
              ["Bot status", formatBotStatus(dashboard?.bot_status)],
            ]}
          />
        </PanelCard>
      </section>

      <PanelCard title="Risk Trend" subtitle="Drawdown, exposure, and consecutive-loss trend rows will appear when a read-only trend source is available.">
        <EmptyState message="Risk trend data unavailable." />
      </PanelCard>
    </DashboardShell>
  );
}

function AlertsTable({ alerts }: { alerts: RiskEventSummary[] }) {
  if (!alerts.length) {
    return <EmptyState message="No active risk alerts." />;
  }
  return (
    <TableFrame maxHeightClass="max-h-[34rem]">
      <table className="min-w-[920px] text-left text-sm">
        <thead className="border-b border-gray-200 text-xs uppercase tracking-[0.12em] text-gray-500 dark:border-gray-800">
          <tr>
            <th className="px-4 py-3">Severity</th>
            <th className="px-4 py-3">Type</th>
            <th className="px-4 py-3">Pair</th>
            <th className="px-4 py-3">Message</th>
            <th className="px-4 py-3">Latest Timestamp</th>
            <th className="px-4 py-3">Occurrence Count</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
          {alerts.map((alert, index) => (
            <tr key={`${alert.type}-${alert.pair ?? "global"}-${alert.latest_timestamp ?? index}`} className="text-gray-700 dark:text-gray-300">
              <td className="px-4 py-3">
                <StatusPill label={formatText(alert.severity)} tone={severityTone(alert.severity)} />
              </td>
              <td className="px-4 py-3 font-mono text-xs">{formatText(alert.type)}</td>
              <td className="px-4 py-3">{formatText(alert.pair)}</td>
              <td className="px-4 py-3">{formatText(alert.message)}</td>
              <td className="px-4 py-3">{formatTimestamp(alert.latest_timestamp)}</td>
              <td className="px-4 py-3 font-mono">{formatInteger(alert.occurrence_count)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableFrame>
  );
}

function PairHealthTable({
  title,
  rows,
  valueKey,
}: {
  title: string;
  rows: PairHealthRow[];
  valueKey: string;
}) {
  return (
    <div>
      <h4 className="mb-2 text-sm font-semibold text-gray-800 dark:text-white/90">{title}</h4>
      {!rows.length ? (
        <EmptyState message="No pairs in this category." compact />
      ) : (
        <TableFrame compact maxHeightClass="max-h-60">
          <table className="min-w-[560px] text-left text-sm">
            <thead className="border-b border-gray-200 text-xs uppercase tracking-[0.12em] text-gray-500 dark:border-gray-800">
              <tr>
                <th className="px-4 py-3">Pair</th>
                <th className="px-4 py-3">Value</th>
                <th className="px-4 py-3">Latest</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {rows.map((row, index) => (
                <tr key={`${title}-${rowPair(row)}-${index}`} className="text-gray-700 dark:text-gray-300">
                  <td className="px-4 py-3 font-medium">{rowPair(row)}</td>
                  <td className="px-4 py-3 font-mono">{formatUnknown(rowValue(row, valueKey))}</td>
                  <td className="px-4 py-3">{formatTimestamp(rowValue(row, "latest_timestamp"))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableFrame>
      )}
    </div>
  );
}

function KeyValueGrid({ rows }: { rows: Array<[string, string]> }) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {rows.map(([label, value]) => (
        <div key={label} className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-950/40">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">{label}</p>
          <p className="mt-2 font-mono text-sm font-semibold text-gray-900 dark:text-white/90">{value}</p>
        </div>
      ))}
    </div>
  );
}

function EmptyState({ message, compact = false }: { message: string; compact?: boolean }) {
  return (
    <div className={`rounded-xl border border-dashed border-gray-300 text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400 ${compact ? "p-3" : "p-6"}`}>
      {message}
    </div>
  );
}

function rangeStartTs(range: RiskRange): number | undefined {
  const option = RANGE_OPTIONS.find((item) => item.value === range);
  if (!option?.seconds) return undefined;
  return Math.floor(Date.now() / 1000) - option.seconds;
}

function rowPair(row: PairHealthRow): string {
  if (typeof row === "string") return row;
  return stringValue(row.pair) ?? stringValue(row.pair_key) ?? stringValue(row.symbol) ?? "n/a";
}

function rowValue(row: PairHealthRow, key: string): unknown {
  return typeof row === "string" ? null : row[key];
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function stringValue(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  return text || null;
}

function formatUnknown(value: unknown): string {
  const numeric = numberValue(value);
  if (numeric !== null) return formatNumber(numeric);
  return stringValue(value) ?? "n/a";
}

function formatText(value: unknown): string {
  return stringValue(value) ?? "n/a";
}

function formatBotStatus(value: Record<string, unknown> | null | undefined): string {
  if (!value || Object.keys(value).length === 0) return "n/a";
  return stringValue(value.status) ?? stringValue(value.state) ?? JSON.stringify(value);
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function formatInteger(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return Math.round(value).toLocaleString();
}

function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString(undefined, { maximumFractionDigits: 2 })} USDT`;
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const normalized = Math.abs(value) > 1 ? value : value * 100;
  return `${normalized.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
}

function formatLatency(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 0 })} ms`;
}

function formatTimestamp(value: unknown): string {
  const numeric = numberValue(value);
  if (numeric === null) return "n/a";
  const ms = numeric > 10_000_000_000 ? numeric : numeric * 1000;
  const date = new Date(ms);
  return Number.isNaN(date.getTime()) ? "n/a" : date.toLocaleString();
}

function severityTone(value: string | null | undefined): "info" | "warning" | "error" | "danger" | "neutral" {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "critical") return "danger";
  if (normalized === "error") return "error";
  if (normalized === "warning" || normalized === "warn") return "warning";
  if (normalized === "info") return "info";
  return "neutral";
}

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message.replace(/^HTTP\s+\d+:\s*/i, "") || fallback : fallback;
}
