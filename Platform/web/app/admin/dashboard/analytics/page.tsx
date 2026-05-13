"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  AnalyticsDashboardResponse,
  PairSummary,
  UserRecord,
  getAnalyticsDashboard,
  getMe,
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
import { PortfolioChart } from "../../../../components/portfolio-chart";

type AnalyticsRange = "7d" | "30d" | "90d" | "all";

const ACTIVE_HREF = "/admin/dashboard/analytics";

export default function AnalyticsPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserRecord | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<AnalyticsRange>("30d");
  const [dashboard, setDashboard] = useState<AnalyticsDashboardResponse | null>(null);

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
        const response = await getAnalyticsDashboard({
          startTs: rangeStartTs(range),
          endTs: range === "all" ? undefined : Math.floor(Date.now() / 1000),
          refresh: forceRefresh,
        });
        setDashboard(response);
      } catch (err) {
        setDashboard(null);
        setError(isUnauthorizedError(err) ? "Unauthorized" : errorMessage(err, "Failed to load analytics dashboard."));
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

  const equityChartData = useMemo(() => mapEquityCurve(dashboard), [dashboard]);
  const dailyPnlData = useMemo(() => mapSeries(dashboard?.pnl_timeseries.daily_pnl ?? [], "date", "pnl_usdt"), [dashboard]);
  const drawdownData = useMemo(() => mapSeries(dashboard?.pnl_timeseries.drawdown_curve ?? [], "timestamp", "drawdown_usdt"), [dashboard]);

  const cacheStatus = dashboard?.cache
    ? `Updated ${formatTimestamp(dashboard.cache.generated_at)} · ${dashboard.cache.cache_hit ? "cache hit" : "fresh"} · TTL ${dashboard.cache.ttl_seconds ?? "n/a"}s`
    : "Read-only";

  if (authLoading) {
    return (
      <DashboardShell
        title="Analytics"
        subtitle="Strategy-wide performance, pair, exit, ML, and hedge-ratio analytics."
        status="Loading"
        activeHref={ACTIVE_HREF}
        navItems={navItems}
        auth={auth}
      >
        <PanelCard title="Loading" subtitle="Checking dashboard access.">
          <p className="text-sm text-gray-500 dark:text-gray-400">Loading analytics...</p>
        </PanelCard>
      </DashboardShell>
    );
  }

  return (
    <DashboardShell
      title="Analytics"
      subtitle="Strategy-wide performance, pair, exit, ML, and hedge-ratio analytics."
      status={dashboardLoading ? "Loading analytics..." : cacheStatus}
      activeHref={ACTIVE_HREF}
      navItems={navItems}
      auth={auth}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <select
            className={UI_CLASSES.inputSmall}
            value={range}
            onChange={(event) => setRange(event.target.value as AnalyticsRange)}
          >
            <option value="7d">7d</option>
            <option value="30d">30d</option>
            <option value="90d">90d</option>
            <option value="all">All</option>
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
        <PanelCard title="Unable to load analytics" subtitle={error}>
          <button type="button" className={UI_CLASSES.primaryButton} onClick={() => void loadDashboard(true)}>
            Retry
          </button>
        </PanelCard>
      ) : null}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <MetricCard label="Total PnL" value={formatMoney(dashboard?.performance.total_pnl_usdt)} tone={pnlTone(dashboard?.performance.total_pnl_usdt)} />
        <MetricCard label="Realized PnL" value={formatMoney(dashboard?.performance.realized_pnl_usdt)} tone={pnlTone(dashboard?.performance.realized_pnl_usdt)} />
        <MetricCard label="Unrealized PnL" value={formatMoney(dashboard?.performance.unrealized_pnl_usdt)} tone="sky" />
        <MetricCard label="Win Rate" value={formatPercent(dashboard?.performance.win_rate)} tone="teal" />
        <MetricCard label="Profit Factor" value={formatNumber(dashboard?.performance.profit_factor)} tone="sky" />
        <MetricCard label="Max Drawdown" value={formatMoney(dashboard?.performance.max_drawdown_usdt)} tone="rose" />
        <MetricCard label="Trade Count" value={formatInteger(dashboard?.performance.trade_count)} tone="violet" />
        <MetricCard label="Avg Hold Time" value={formatDuration(dashboard?.performance.avg_hold_seconds)} tone="violet" />
        <MetricCard label="Average Win" value={formatMoney(dashboard?.performance.average_win_usdt)} tone="teal" />
        <MetricCard label="Average Loss" value={formatMoney(dashboard?.performance.average_loss_usdt)} tone="rose" />
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <PanelCard title="Equity Curve" subtitle="Stored equity snapshots only.">
          {equityChartData.length ? (
            <PortfolioChart
              data={equityChartData}
              height={260}
              title="Equity Curve"
              subtitle="Dashboard analytics service"
              caption={`${equityChartData.length} points`}
            />
          ) : (
            <EmptyState message="No data available yet." />
          )}
        </PanelCard>
        <PanelCard title="Daily / Session PnL" subtitle="Aggregated from closed trades.">
          <SimpleBarChart data={dailyPnlData} valueKey="value" labelKey="label" emptyMessage="No data available yet." />
        </PanelCard>
        <PanelCard title="Drawdown Curve" subtitle="Computed from available equity curve.">
          <SimpleLineChart data={drawdownData} valueKey="value" labelKey="label" emptyMessage="No data available yet." />
        </PanelCard>
        <PanelCard title="Distribution" subtitle="PnL and trade duration distributions are not part of the standardized backend yet.">
          <EmptyState message="No data available yet." />
        </PanelCard>
      </section>

      <PanelCard title="Pair Leaderboards" subtitle="Pair history summaries reused for strategy-wide ranking.">
        <div className="grid gap-4 xl:grid-cols-2">
          <Leaderboard title="Top pairs by PnL" rows={dashboard?.pair_leaderboards.top_pairs_by_pnl ?? []} valueKey="net_pnl_usdt" valueFormatter={formatMoney} />
          <Leaderboard title="Bottom pairs by PnL" rows={dashboard?.pair_leaderboards.bottom_pairs_by_pnl ?? []} valueKey="net_pnl_usdt" valueFormatter={formatMoney} />
          <Leaderboard title="Top pairs by win rate" rows={dashboard?.pair_leaderboards.top_pairs_by_win_rate ?? []} valueKey="win_rate" valueFormatter={formatPercent} />
          <Leaderboard title="Worst pairs by drawdown" rows={dashboard?.pair_leaderboards.worst_pairs_by_drawdown ?? []} valueKey="max_drawdown_usdt" valueFormatter={formatMoney} />
          <Leaderboard title="High hedge-drift pairs" rows={dashboard?.pair_leaderboards.pairs_with_high_hedge_drift ?? []} valueKey="avg_hedge_drift_pct" valueFormatter={formatPercent} />
          <Leaderboard title="Frequent blocked pairs" rows={dashboard?.pair_leaderboards.pairs_with_frequent_blocks ?? []} valueKey="block_count" valueFormatter={formatInteger} />
        </div>
      </PanelCard>

      <section className="grid gap-4 xl:grid-cols-3">
        <PanelCard title="Exit Policy Analysis" subtitle="Stored counterfactual and Exit Orchestrator records only.">
          <KeyValueList
            rows={[
              ["Best counterfactual exit policy", dashboard?.exit_analysis.best_counterfactual_exit_policy ?? "n/a"],
              ["Actual exit efficiency", formatPercent(dashboard?.exit_analysis.actual_exit_efficiency)],
              ["Average missed profit", formatMoney(dashboard?.exit_analysis.avg_missed_profit_usdt)],
              ["Average avoided loss", formatMoney(dashboard?.exit_analysis.avg_avoided_loss_usdt)],
            ]}
          />
          <DistributionTable
            title="Exit policy distribution"
            distribution={dashboard?.exit_analysis.exit_policy_distribution ?? {}}
            emptyMessage="No exit orchestrator data available yet."
          />
        </PanelCard>

        <PanelCard title="ML Analysis" subtitle="Stored score history only.">
          <KeyValueList rows={[["Break risk before losses", formatNumber(dashboard?.ml_analysis.break_risk_before_losses)]]} />
          <SmallRows
            title="PnL by regime"
            rows={dashboard?.ml_analysis.pnl_by_regime ?? []}
            columns={[
              ["regime", "Regime"],
              ["pnl_usdt", "PnL"],
              ["trade_count", "Trades"],
            ]}
          />
          <SmallRows
            title="Win rate by regime"
            rows={dashboard?.ml_analysis.win_rate_by_regime ?? []}
            columns={[
              ["regime", "Regime"],
              ["win_rate", "Win Rate"],
              ["trade_count", "Trades"],
            ]}
          />
          <SmallRows
            title="Bayesian posterior vs outcome"
            rows={dashboard?.ml_analysis.bayesian_posterior_vs_outcome ?? []}
            columns={[
              ["bayesian_posterior", "Posterior"],
              ["pnl_usdt", "PnL"],
              ["won", "Won"],
            ]}
          />
          <SmallRows
            title="Final rank score vs outcome"
            rows={dashboard?.ml_analysis.final_rank_score_vs_outcome ?? []}
            columns={[
              ["final_rank_score", "Final Rank"],
              ["pnl_usdt", "PnL"],
              ["won", "Won"],
            ]}
          />
          <SmallRows
            title="Microstructure risk vs slippage"
            rows={dashboard?.ml_analysis.microstructure_risk_vs_slippage ?? []}
            columns={[
              ["microstructure_risk", "Risk"],
              ["slippage_usdt", "Slippage"],
            ]}
          />
        </PanelCard>

        <PanelCard title="Hedge-Ratio Analysis" subtitle="Stored Phase 2.25 / Phase 3 sizing comparison fields.">
          <KeyValueList
            rows={[
              ["Equal-notional total PnL", formatMoney(dashboard?.hedge_analysis.equal_notional_total_pnl)],
              ["Hedge-ratio-sized total PnL", formatMoney(dashboard?.hedge_analysis.hedge_ratio_sized_total_pnl)],
              ["Sizing PnL delta", formatMoney(dashboard?.hedge_analysis.sizing_pnl_delta_usdt)],
              ["High drift trade count", formatInteger(dashboard?.hedge_analysis.high_drift_trade_count)],
            ]}
          />
        </PanelCard>
      </section>
    </DashboardShell>
  );
}

function Leaderboard({
  title,
  rows,
  valueKey,
  valueFormatter,
}: {
  title: string;
  rows: Array<PairSummary & { block_count?: number | null }>;
  valueKey: keyof PairSummary | "block_count";
  valueFormatter: (value: number | null | undefined) => string;
}) {
  return (
    <div>
      <h4 className="mb-2 text-sm font-semibold text-gray-800 dark:text-white/90">{title}</h4>
      {!rows.length ? (
        <EmptyState message="No data available yet." compact />
      ) : (
        <TableFrame compact maxHeightClass="max-h-72">
          <table className="min-w-[520px] text-left text-sm">
            <thead className="border-b border-gray-200 text-xs uppercase tracking-[0.12em] text-gray-500 dark:border-gray-800">
              <tr>
                <th className="px-4 py-3">Pair</th>
                <th className="px-4 py-3">Value</th>
                <th className="px-4 py-3">Trades</th>
                <th className="px-4 py-3">Tags</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {rows.map((row) => (
                <tr key={`${title}-${row.pair}`} className="text-gray-700 dark:text-gray-300">
                  <td className="px-4 py-3 font-medium">{row.pair}</td>
                  <td className="px-4 py-3">{valueFormatter(valueFromRow(row, valueKey))}</td>
                  <td className="px-4 py-3">{formatInteger(row.total_trades)}</td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {(row.tags ?? []).slice(0, 3).map((tag) => (
                        <StatusPill key={tag} label={String(tag).replaceAll("_", " ")} tone="neutral" />
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableFrame>
      )}
    </div>
  );
}

function KeyValueList({ rows }: { rows: Array<[string, string]> }) {
  return (
    <div className="mb-4 grid gap-3">
      {rows.map(([label, value]) => (
        <div key={label} className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-950/40">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-gray-500">{label}</p>
          <p className="mt-1 font-mono text-sm text-gray-900 dark:text-white/90">{value}</p>
        </div>
      ))}
    </div>
  );
}

function DistributionTable({
  title,
  distribution,
  emptyMessage,
}: {
  title: string;
  distribution: Record<string, number>;
  emptyMessage: string;
}) {
  const rows = Object.entries(distribution);
  return (
    <div className="mt-4">
      <h4 className="mb-2 text-sm font-semibold text-gray-800 dark:text-white/90">{title}</h4>
      {!rows.length ? (
        <EmptyState message={emptyMessage} compact />
      ) : (
        <div className="space-y-2">
          {rows.map(([name, count]) => (
            <div key={name} className="flex justify-between rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-800">
              <span>{name}</span>
              <span className="font-mono">{count}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SmallRows({
  title,
  rows,
  columns,
}: {
  title: string;
  rows: Array<Record<string, unknown>>;
  columns: Array<[string, string]>;
}) {
  return (
    <div className="mt-4">
      <h4 className="mb-2 text-sm font-semibold text-gray-800 dark:text-white/90">{title}</h4>
      {!rows.length ? (
        <EmptyState message="No data available yet." compact />
      ) : (
        <TableFrame compact maxHeightClass="max-h-56">
          <table className="min-w-[420px] text-left text-sm">
            <thead className="border-b border-gray-200 text-xs uppercase tracking-[0.12em] text-gray-500 dark:border-gray-800">
              <tr>
                {columns.map(([, label]) => (
                  <th key={label} className="px-4 py-3">{label}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
              {rows.slice(0, 10).map((row, index) => (
                <tr key={`${title}-${index}`} className="text-gray-700 dark:text-gray-300">
                  {columns.map(([key]) => (
                    <td key={key} className="px-4 py-3">{formatUnknown(row[key])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </TableFrame>
      )}
    </div>
  );
}

function SimpleBarChart({
  data,
  valueKey,
  labelKey,
  emptyMessage,
}: {
  data: Array<Record<string, string | number>>;
  valueKey: string;
  labelKey: string;
  emptyMessage: string;
}) {
  if (!data.length) return <EmptyState message={emptyMessage} />;
  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey={labelKey} tickLine={false} axisLine={false} fontSize={12} />
          <YAxis tickLine={false} axisLine={false} fontSize={12} />
          <Tooltip />
          <Bar dataKey={valueKey} fill="#465fff" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function SimpleLineChart({
  data,
  valueKey,
  labelKey,
  emptyMessage,
}: {
  data: Array<Record<string, string | number>>;
  valueKey: string;
  labelKey: string;
  emptyMessage: string;
}) {
  if (!data.length) return <EmptyState message={emptyMessage} />;
  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey={labelKey} tickLine={false} axisLine={false} fontSize={12} />
          <YAxis tickLine={false} axisLine={false} fontSize={12} />
          <Tooltip />
          <Line dataKey={valueKey} stroke="#f04438" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
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

function mapEquityCurve(dashboard: AnalyticsDashboardResponse | null) {
  return (dashboard?.pnl_timeseries.equity_curve ?? [])
    .map((point) => {
      const timestamp = timestampMs(point.timestamp ?? point.ts);
      const equity = numberValue(point.equity_usdt ?? point.equity);
      if (timestamp === null || equity === null) return null;
      return {
        ts: new Date(timestamp).toISOString(),
        equity,
        drawdown: numberValue(point.drawdown_usdt) ?? 0,
        drawdown_pct: numberValue(point.drawdown_pct),
        pnl_usdt: numberValue(point.session_pnl_usdt ?? point.pnl_usdt),
        source: stringValue(point.source),
      };
    })
    .filter((point): point is NonNullable<typeof point> => point !== null);
}

function mapSeries(rows: Array<Record<string, unknown>>, labelField: string, valueField: string) {
  return rows
    .map((row) => {
      const value = numberValue(row[valueField]);
      if (value === null) return null;
      return {
        label: labelField === "timestamp" ? shortTimestamp(row[labelField]) : String(row[labelField] ?? "n/a"),
        value,
      };
    })
    .filter((row): row is { label: string; value: number } => row !== null);
}

function valueFromRow(row: PairSummary & { block_count?: number | null }, key: keyof PairSummary | "block_count"): number | null {
  return numberValue(row[key as keyof typeof row]);
}

function rangeStartTs(range: AnalyticsRange): number | undefined {
  if (range === "all") return undefined;
  const days = range === "7d" ? 7 : range === "30d" ? 30 : 90;
  return Math.floor(Date.now() / 1000) - days * 86_400;
}

function timestampMs(value: unknown): number | null {
  const numeric = numberValue(value);
  if (numeric !== null) return numeric > 10_000_000_000 ? numeric : numeric * 1000;
  const parsed = new Date(String(value ?? "")).getTime();
  return Number.isFinite(parsed) ? parsed : null;
}

function shortTimestamp(value: unknown): string {
  const ms = timestampMs(value);
  if (ms === null) return "n/a";
  return new Date(ms).toLocaleDateString();
}

function formatTimestamp(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const ms = value > 10_000_000_000 ? value : value * 1000;
  return new Date(ms).toLocaleString();
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

function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return value.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function formatInteger(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return Math.round(value).toLocaleString();
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${(value * 100).toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
}

function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString(undefined, { maximumFractionDigits: 2 })} USDT`;
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "n/a";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${(seconds / 3600).toLocaleString(undefined, { maximumFractionDigits: 1 })}h`;
  return `${(seconds / 86400).toLocaleString(undefined, { maximumFractionDigits: 1 })}d`;
}

function formatUnknown(value: unknown): string {
  if (typeof value === "boolean") return value ? "true" : "false";
  const numeric = numberValue(value);
  if (numeric !== null) return formatNumber(numeric);
  return stringValue(value) ?? "n/a";
}

function pnlTone(value: number | null | undefined): "teal" | "rose" | "sky" {
  if (value === null || value === undefined || Number.isNaN(value)) return "sky";
  return value >= 0 ? "teal" : "rose";
}

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message.replace(/^HTTP\s+\d+:\s*/i, "") || fallback : fallback;
}
