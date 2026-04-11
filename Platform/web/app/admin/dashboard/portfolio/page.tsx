"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, usePathname } from "next/navigation";

import {
  RunSummary,
  UserRecord,
  WalkForwardPoint,
  getMe,
  getRuns,
  getRunWalkForward,
  isUnauthorizedError,
} from "../../../../lib/api";
import { DashboardShell } from "../../../../components/dashboard-shell";
import { MetricCard, PanelCard } from "../../../../components/panels";
import { getStoredAdminEmail } from "../../../../lib/auth";
import {
  canAccessAdminPath,
  getAdminNavItems,
  getFirstAccessibleAdminPath,
} from "../../../../lib/admin-access";
import { PortfolioChart } from "../../../../components/portfolio-chart";

type ChartWindow = "30" | "80" | "all";

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

export default function PortfolioPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [walkForward, setWalkForward] = useState<WalkForwardPoint[]>([]);
  const [chartWindow, setChartWindow] = useState<ChartWindow>("80");

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
    getRuns()
      .then(setRuns)
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (!selectedRunId) {
      const latest = (runs || [])[0];
      if (latest) setSelectedRunId(latest.id);
      return;
    }
  }, [selectedRunId, runs]);

  useEffect(() => {
    if (!selectedRunId) return;
    getRunWalkForward(selectedRunId)
      .then(setWalkForward)
      .catch(console.error);
  }, [selectedRunId]);

  const selectedRun = useMemo(
    () => (runs || []).find((r) => r.id === selectedRunId) || null,
    [runs, selectedRunId],
  );

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

  const portfolioData = useMemo(() => {
    return windowedEquitySeries.map((point, idx) => ({
      ts: point.ts,
      equity: point.equity,
      drawdown: drawdownSeries[idx]?.drawdown || 0,
    }));
  }, [windowedEquitySeries, drawdownSeries]);

  if (loading) {
    return <div className="p-8 text-center text-gray-500">Loading...</div>;
  }

  const activeHref = "/admin/dashboard/portfolio";

  return (
    <DashboardShell
      title="Portfolio"
      subtitle="Equity curve & drawdown analysis"
      status="OK"
      activeHref={activeHref}
      navItems={navItems}
      auth={auth}
    >
      <div className="space-y-6">
        <div className="flex flex-wrap gap-4">
          <select
            className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
            value={selectedRunId || ""}
            onChange={(e) => setSelectedRunId(e.target.value)}
          >
            {(runs || []).filter(r => r && r.id).map((run) => (
              <option key={run.id} value={run.id}>
                {run.id.slice(0, 8)} ({fmtDate(run.start_ts)}) - {fmtSignedNumber(run.session_pnl)} USDT
              </option>
            ))}
          </select>
          <div className="flex rounded-lg border border-gray-300 dark:border-gray-600">
            <button
              className={`px-3 py-2 text-sm ${chartWindow === "30" ? "bg-brand-500 text-white" : "bg-white dark:bg-gray-800"}`}
              onClick={() => setChartWindow("30")}
            >
              30 pts
            </button>
            <button
              className={`px-3 py-2 text-sm ${chartWindow === "80" ? "bg-brand-500 text-white" : "bg-white dark:bg-gray-800"}`}
              onClick={() => setChartWindow("80")}
            >
              80 pts
            </button>
            <button
              className={`px-3 py-2 text-sm ${chartWindow === "all" ? "bg-brand-500 text-white" : "bg-white dark:bg-gray-800"}`}
              onClick={() => setChartWindow("all")}
            >
              All
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          <MetricCard label="End Equity" value={fmtNumber(selectedRun?.end_equity)} unit="USDT" />
          <MetricCard label="Start Equity" value={fmtNumber(selectedRun?.start_equity)} unit="USDT" />
          <MetricCard label="Session PnL" value={fmtSignedNumber(selectedRun?.session_pnl)} unit="USDT" />
          <MetricCard label="Max Drawdown" value={fmtNumber(selectedRun?.max_drawdown)} unit="USDT" />
        </div>

        <PanelCard title="Equity Curve">
          {portfolioData.length ? (
            <PortfolioChart
              data={portfolioData}
              height={350}
              windowSize={chartWindow}
              title="Portfolio Performance"
              subtitle="Equity curve vs benchmark (realized PnL)"
            />
          ) : (
            <p className="text-sm text-gray-500 dark:text-gray-400">No portfolio data yet.</p>
          )}
        </PanelCard>
      </div>
    </DashboardShell>
  );
}
