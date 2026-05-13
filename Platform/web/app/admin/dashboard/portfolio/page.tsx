"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  PortfolioDashboardResponse,
  UserRecord,
  getMe,
  getPortfolioDashboard,
  isUnauthorizedError,
} from "../../../../lib/api";
import { DashboardShell } from "../../../../components/dashboard-shell";
import { MetricCard, PanelCard, StatusPill } from "../../../../components/panels";
import { getStoredAdminEmail } from "../../../../lib/auth";
import {
  canAccessAdminPath,
  getAdminNavItems,
  getFirstAccessibleAdminPath,
} from "../../../../lib/admin-access";
import { UI_CLASSES } from "../../../../lib/ui-classes";
import { PortfolioChart } from "../../../../components/portfolio-chart";

type PortfolioRange = "24h" | "7d" | "30d" | "90d" | "all";

type SeriesPoint = {
  label: string;
  x: number;
  value: number;
  detail?: string | null;
};

const RANGE_OPTIONS: Array<{ value: PortfolioRange; label: string; seconds: number | null }> = [
  { value: "24h", label: "24H", seconds: 24 * 60 * 60 },
  { value: "7d", label: "7D", seconds: 7 * 24 * 60 * 60 },
  { value: "30d", label: "30D", seconds: 30 * 24 * 60 * 60 },
  { value: "90d", label: "90D", seconds: 90 * 24 * 60 * 60 },
  { value: "all", label: "All", seconds: null },
];

function finiteNumber(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function fmtNumber(value: number | null | undefined, digits = 2): string {
  const numeric = finiteNumber(value);
  if (numeric === null) return "n/a";
  return numeric.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function fmtSignedNumber(value: number | null | undefined, digits = 2): string {
  const numeric = finiteNumber(value);
  if (numeric === null) return "n/a";
  return `${numeric >= 0 ? "+" : ""}${fmtNumber(numeric, digits)}`;
}

function fmtRatioPct(value: number | null | undefined, digits = 1): string {
  const numeric = finiteNumber(value);
  if (numeric === null) return "n/a";
  return `${(numeric * 100).toFixed(digits)}%`;
}

function fmtDateFromSeconds(value: number | null | undefined): string {
  const numeric = finiteNumber(value);
  if (numeric === null) return "n/a";
  const ms = numeric > 10_000_000_000 ? numeric : numeric * 1000;
  const dt = new Date(ms);
  if (Number.isNaN(dt.getTime())) return "n/a";
  return dt.toLocaleString();
}

function fmtShortDate(value: number): string {
  const ms = value > 10_000_000_000 ? value : value * 1000;
  const dt = new Date(ms);
  if (Number.isNaN(dt.getTime())) return String(value);
  return dt.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function rangeStartTs(range: PortfolioRange): number | undefined {
  const option = RANGE_OPTIONS.find((item) => item.value === range);
  if (!option?.seconds) return undefined;
  return Math.floor(Date.now() / 1000) - option.seconds;
}

function rangeButtonClass(active: boolean): string {
  return [
    "rounded-xl px-3 py-2 text-sm font-semibold transition",
    active
      ? "bg-brand-500 text-white shadow-sm"
      : "border border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700",
  ].join(" ");
}

function EmptyState({ label = "No data available yet." }: { label?: string }) {
  return <p className="py-10 text-center text-sm text-gray-500 dark:text-gray-400">{label}</p>;
}

function MiniSeriesChart({
  title,
  subtitle,
  points,
  color,
  valueLabel,
  valueFormatter = fmtNumber,
}: {
  title: string;
  subtitle: string;
  points: SeriesPoint[];
  color: string;
  valueLabel: string;
  valueFormatter?: (value: number | null | undefined) => string;
}) {
  if (!points.length) {
    return (
      <PanelCard title={title} subtitle={subtitle}>
        <EmptyState />
      </PanelCard>
    );
  }

  return (
    <PanelCard title={title} subtitle={subtitle}>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={points}>
          <defs>
            <linearGradient id={`${title.replace(/\W+/g, "-")}-gradient`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35} />
              <stop offset="85%" stopColor={color} stopOpacity={0.04} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            dataKey="x"
            tickFormatter={fmtShortDate}
            tickLine={false}
            axisLine={false}
            tickMargin={10}
            fontSize={12}
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            tickMargin={10}
            fontSize={12}
            tickFormatter={(value) => fmtNumber(Number(value), 0)}
          />
          <Tooltip
            content={({ active, payload }) => {
              const item = (payload?.[0]?.payload as SeriesPoint | undefined) || null;
              if (!active || !item) return null;
              return (
                <div className="rounded-lg border border-gray-200 bg-white p-3 text-sm shadow-lg dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100">
                  <p className="font-semibold text-gray-900 dark:text-white">{item.label}</p>
                  <p className="mt-1">
                    <span className="font-mono text-brand-600">{valueLabel}:</span> {valueFormatter(item.value)}
                  </p>
                  {item.detail ? <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{item.detail}</p> : null}
                </div>
              );
            }}
          />
          <Area
            type="linear"
            dataKey="value"
            stroke={color}
            strokeWidth={2}
            fill={`url(#${title.replace(/\W+/g, "-")}-gradient)`}
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </PanelCard>
  );
}

function highlightLabel(value: string | null | undefined): string {
  const text = String(value || "").trim();
  return text || "n/a";
}

function statusTone(status: string | null | undefined): "success" | "warning" | "neutral" {
  const normalized = String(status || "").toLowerCase();
  if (!normalized) return "neutral";
  if (["running", "ok", "healthy", "active"].includes(normalized)) return "success";
  if (["stopped", "error", "failed", "warn", "warning"].includes(normalized)) return "warning";
  return "neutral";
}

export default function PortfolioPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserRecord | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [dashboardLoading, setDashboardLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<PortfolioRange>("7d");
  const [dashboard, setDashboard] = useState<PortfolioDashboardResponse | null>(null);

  const navItems = useMemo(() => getAdminNavItems(user), [user]);

  useEffect(() => {
    getMe()
      .then((u) => setUser(u))
      .catch(() => setUser(null))
      .finally(() => setAuthLoading(false));
  }, []);

  const auth = useMemo(
    () => ({
      email: getStoredAdminEmail(),
      hasToken: true,
    }),
    [],
  );

  useEffect(() => {
    if (authLoading || !user) return;
    const currentPath = pathname;
    const hasAccess = canAccessAdminPath(user, currentPath);
    const firstAccessible = getFirstAccessibleAdminPath(user);

    if (!hasAccess) {
      if (!firstAccessible) {
        router.replace("/");
        return;
      }
      if (firstAccessible !== currentPath) {
        router.replace(firstAccessible);
      }
    }
  }, [authLoading, user, pathname, router]);

  const loadDashboard = useCallback(
    async (forceRefresh = false) => {
      setDashboardLoading(true);
      setRefreshing(forceRefresh);
      setError(null);
      try {
        const data = await getPortfolioDashboard({
          startTs: rangeStartTs(range),
          endTs: Math.floor(Date.now() / 1000),
          refresh: forceRefresh,
        });
        setDashboard(data);
      } catch (err) {
        setError(isUnauthorizedError(err) ? "Unauthorized" : "Failed to load portfolio dashboard");
        setDashboard(null);
      } finally {
        setDashboardLoading(false);
        setRefreshing(false);
      }
    },
    [range],
  );

  useEffect(() => {
    void loadDashboard(false);
  }, [loadDashboard]);

  if (authLoading) {
    return <div className="p-8 text-center text-gray-500">Loading...</div>;
  }

  const activeHref = "/admin/dashboard/portfolio";
  const summary = dashboard?.summary;
  const charts = dashboard?.charts;
  const highlights = dashboard?.highlights;
  const openPositionCount = summary?.open_positions === null || summary?.open_positions === undefined
    ? null
    : summary.open_positions.length;
  const cacheCaption = dashboard?.cache
    ? `Generated ${fmtDateFromSeconds(dashboard.cache.generated_at)} | TTL ${dashboard.cache.ttl_seconds ?? "n/a"}s | ${dashboard.cache.cache_hit ? "cache hit" : "fresh"}`
    : "Cache metadata unavailable";

  const equityChartPoints = (charts?.equity_curve || []).map((point, index) => {
    const drawdown = charts?.drawdown_curve.find((row) => row.timestamp === point.timestamp);
    const previous = index > 0 ? charts?.equity_curve[index - 1] : null;
    return {
      ts: new Date(point.timestamp * 1000).toISOString(),
      equity: point.equity_usdt,
      drawdown: drawdown?.drawdown_usdt ?? 0,
      drawdown_pct: drawdown?.drawdown_pct ?? null,
      pnl_usdt: previous ? point.equity_usdt - previous.equity_usdt : point.session_pnl_usdt ?? null,
      pnl_pct: previous && previous.equity_usdt !== 0 ? (point.equity_usdt - previous.equity_usdt) / previous.equity_usdt : null,
      run_key: point.run_id ?? null,
      source: point.source ?? null,
      samples: 1,
    };
  });

  const dailyPnlPoints: SeriesPoint[] = (charts?.daily_pnl || []).map((point, index) => ({
    label: point.date,
    x: Date.parse(`${point.date}T00:00:00Z`) || index,
    value: point.pnl_usdt,
    detail: `${point.trade_count} closed trade${point.trade_count === 1 ? "" : "s"}`,
  }));

  const drawdownPoints: SeriesPoint[] = (charts?.drawdown_curve || []).map((point) => ({
    label: fmtDateFromSeconds(point.timestamp),
    x: point.timestamp,
    value: point.drawdown_usdt,
    detail: `Peak ${fmtNumber(point.peak_equity_usdt)} USDT`,
  }));

  const exposurePoints: SeriesPoint[] = (charts?.open_exposure || []).map((point) => ({
    label: fmtDateFromSeconds(point.timestamp),
    x: point.timestamp,
    value: point.open_exposure_usdt,
    detail: point.pair || null,
  }));
  const highlightRows: Array<{ label: string; value: string | null | undefined }> = [
    { label: "Best performing pair", value: highlights?.best_performing_pair },
    { label: "Worst performing pair", value: highlights?.worst_performing_pair },
    { label: "Most traded pair", value: highlights?.most_traded_pair },
    { label: "Highest drawdown pair", value: highlights?.highest_drawdown_pair },
    { label: "Current regime state", value: highlights?.current_regime_state },
    { label: "Current risk level", value: highlights?.current_risk_level },
  ];

  return (
    <DashboardShell
      title="Portfolio"
      subtitle="Read-only portfolio performance and current exposure"
      status={error ? "WARN" : summary?.bot_status ? summary.bot_status.toUpperCase() : "OK"}
      activeHref={activeHref}
      navItems={navItems}
      auth={auth}
    >
      <div className="space-y-6">
        <PanelCard
          title="Portfolio Overview"
          subtitle={cacheCaption}
          titleRight={
            <div className="flex flex-wrap items-center justify-end gap-2">
              {summary?.bot_status ? <StatusPill label={summary.bot_status} tone={statusTone(summary.bot_status)} /> : null}
              <button
                type="button"
                className={UI_CLASSES.secondaryButton}
                onClick={() => void loadDashboard(true)}
                disabled={dashboardLoading || refreshing}
              >
                {refreshing ? "Refreshing..." : "Refresh"}
              </button>
            </div>
          }
        >
          <div className="mb-5 flex flex-wrap gap-2">
            {RANGE_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                className={rangeButtonClass(range === option.value)}
                onClick={() => setRange(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>

          {dashboardLoading && !dashboard ? (
            <EmptyState label="Loading portfolio dashboard..." />
          ) : error ? (
            <p className="py-10 text-center text-sm text-error-600 dark:text-error-400">{error}</p>
          ) : null}

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Total Equity" value={fmtNumber(summary?.total_equity_usdt)} unit="USDT" tone="sky" />
            <MetricCard label="Session PnL" value={fmtSignedNumber(summary?.session_pnl_usdt)} unit="USDT" tone={(summary?.session_pnl_usdt ?? 0) >= 0 ? "teal" : "rose"} />
            <MetricCard label="Realized PnL" value={fmtSignedNumber(summary?.realized_pnl_usdt)} unit="USDT" tone={(summary?.realized_pnl_usdt ?? 0) >= 0 ? "teal" : "rose"} />
            <MetricCard label="Unrealized PnL" value={fmtSignedNumber(summary?.unrealized_pnl_usdt)} unit="USDT" tone={(summary?.unrealized_pnl_usdt ?? 0) >= 0 ? "teal" : "rose"} />
            <MetricCard label="Win Rate" value={fmtRatioPct(summary?.win_rate)} hint="Closed trades" tone="violet" />
            <MetricCard label="Profit Factor" value={fmtNumber(summary?.profit_factor)} hint="Gross profit / gross loss" tone="violet" />
            <MetricCard label="Max Drawdown" value={fmtSignedNumber(summary?.max_drawdown_usdt)} unit="USDT" tone="amber" />
            <MetricCard label="Open Positions" value={openPositionCount === null ? "n/a" : String(openPositionCount)} hint="Stored position snapshots" tone="sky" />
            <MetricCard label="Active Pair" value={summary?.active_pair || "n/a"} tone="sky" />
            <MetricCard label="Bot Status" value={summary?.bot_status || "n/a"} tone={statusTone(summary?.bot_status) === "success" ? "teal" : "amber"} />
            <MetricCard label="Open Exposure" value={fmtNumber(summary?.open_exposure_usdt)} unit="USDT" tone="amber" />
          </div>
        </PanelCard>

        <PanelCard title="Equity Curve" subtitle="Stored account equity samples from the selected range.">
          {equityChartPoints.length ? (
            <PortfolioChart
              data={equityChartPoints}
              height={340}
              caption={cacheCaption}
              title="Total Equity"
              subtitle="No synthetic equity values are filled in for missing samples."
            />
          ) : (
            <EmptyState />
          )}
        </PanelCard>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <MiniSeriesChart
            title="Daily PnL"
            subtitle="Closed-trade PnL grouped by UTC day."
            points={dailyPnlPoints}
            color="#16a34a"
            valueLabel="PnL"
            valueFormatter={(value) => `${fmtSignedNumber(value)} USDT`}
          />
          <MiniSeriesChart
            title="Drawdown"
            subtitle="Derived from stored equity samples."
            points={drawdownPoints}
            color="#f59e0b"
            valueLabel="Drawdown"
            valueFormatter={(value) => `${fmtSignedNumber(value)} USDT`}
          />
          <MiniSeriesChart
            title="Open Exposure"
            subtitle="Stored position exposure snapshots."
            points={exposurePoints}
            color="#465fff"
            valueLabel="Exposure"
            valueFormatter={(value) => `${fmtNumber(value)} USDT`}
          />
        </div>

        <PanelCard title="Highlights" subtitle="Null metrics are rendered as n/a until a read-only source is available.">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {highlightRows.map(({ label, value }) => (
              <div
                key={label}
                className="rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-950/40"
              >
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">{label}</p>
                <p className="mt-2 truncate font-mono text-sm font-semibold text-gray-900 dark:text-white/90">
                  {highlightLabel(value)}
                </p>
              </div>
            ))}
          </div>
        </PanelCard>
      </div>
    </DashboardShell>
  );
}
