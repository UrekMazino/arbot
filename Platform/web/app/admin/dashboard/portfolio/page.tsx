"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  PortfolioEquityBucket,
  PortfolioEquityCurve,
  PortfolioEquityRange,
  UserRecord,
  getMe,
  getPortfolioEquityCurve,
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
import { UI_CLASSES } from "../../../../lib/ui-classes";
import { PortfolioChart } from "../../../../components/portfolio-chart";

const RANGE_OPTIONS: Array<{ value: PortfolioEquityRange; label: string; hint: string }> = [
  { value: "24h", label: "24H", hint: "Intraday" },
  { value: "7d", label: "7D", hint: "Last week" },
  { value: "30d", label: "30D", hint: "Last month" },
  { value: "90d", label: "90D", hint: "Quarter" },
  { value: "all", label: "All", hint: "Full history" },
];

const BUCKET_OPTIONS: Array<{ value: PortfolioEquityBucket; label: string }> = [
  { value: "auto", label: "Auto" },
  { value: "raw", label: "Raw" },
  { value: "hour", label: "Hourly" },
  { value: "day", label: "Daily" },
  { value: "week", label: "Weekly" },
];

function fmtNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return value.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function fmtSignedNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${value >= 0 ? "+" : ""}${fmtNumber(value, digits)}`;
}

function fmtPct(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return "n/a";
  return dt.toLocaleString();
}

function bucketLabel(bucket: PortfolioEquityBucket | string | undefined): string {
  const found = BUCKET_OPTIONS.find((option) => option.value === bucket);
  return found?.label || String(bucket || "Auto");
}

function rangeLabel(range: PortfolioEquityRange): string {
  return RANGE_OPTIONS.find((option) => option.value === range)?.label || range;
}

function rangeButtonClass(active: boolean): string {
  return [
    "rounded-xl px-3 py-2 text-sm font-semibold transition",
    active
      ? "bg-brand-500 text-white shadow-sm"
      : "border border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700",
  ].join(" ");
}

export default function PortfolioPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [curveLoading, setCurveLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState<PortfolioEquityRange>("7d");
  const [bucket, setBucket] = useState<PortfolioEquityBucket>("auto");
  const [curve, setCurve] = useState<PortfolioEquityCurve | null>(null);

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
  }, [loading, user, pathname, router]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      await Promise.resolve();
      if (cancelled) return;
      setCurveLoading(true);
      setError(null);
      try {
        const data = await getPortfolioEquityCurve(range, bucket);
        if (!cancelled) setCurve(data);
      } catch (err) {
        if (cancelled) return;
        setError(isUnauthorizedError(err) ? "Unauthorized" : "Failed to load portfolio equity curve");
        setCurve(null);
      } finally {
        if (!cancelled) setCurveLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [range, bucket]);

  if (loading) {
    return <div className="p-8 text-center text-gray-500">Loading...</div>;
  }

  const activeHref = "/admin/dashboard/portfolio";
  const stats = curve?.stats;
  const chartData = curve?.points || [];
  const activeBucketLabel = curve ? bucketLabel(curve.bucket) : bucketLabel(bucket);
  const caption = `${rangeLabel(range)} range | ${bucket === "auto" ? `Auto -> ${activeBucketLabel}` : activeBucketLabel} | ${fmtDate(stats?.start_ts)} to ${fmtDate(stats?.end_ts)}`;

  return (
    <DashboardShell
      title="Portfolio"
      subtitle="Portfolio equity curve across all bot runs"
      status={error ? "WARN" : "OK"}
      activeHref={activeHref}
      navItems={navItems}
      auth={auth}
    >
      <div className="space-y-6">
        <PanelCard
          title="Portfolio Equity Curve"
          subtitle="Built from heartbeat equity events across every run. Bucketed views use the last equity sample in each period."
          titleRight={
            <div className="flex flex-wrap items-center justify-end gap-2">
              <select
                className={UI_CLASSES.inputSmall}
                value={bucket}
                onChange={(event) => setBucket(event.target.value as PortfolioEquityBucket)}
              >
                {BUCKET_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
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
                title={option.hint}
              >
                {option.label}
              </button>
            ))}
          </div>

          {curveLoading ? (
            <p className="py-12 text-center text-sm text-gray-500 dark:text-gray-400">Loading portfolio curve...</p>
          ) : error ? (
            <p className="py-12 text-center text-sm text-error-600 dark:text-error-400">{error}</p>
          ) : chartData.length ? (
            <PortfolioChart
              data={chartData}
              height={390}
              caption={caption}
              title="Account Equity"
              subtitle="Absolute portfolio equity with drawdown for the selected range"
            />
          ) : (
            <p className="py-12 text-center text-sm text-gray-500 dark:text-gray-400">
              No equity samples found yet. Start a run and the dashboard will plot heartbeat equity here.
            </p>
          )}
        </PanelCard>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="Current Equity"
            value={fmtNumber(stats?.end_equity)}
            unit="USDT"
            hint={`Started ${fmtNumber(stats?.start_equity)} USDT`}
            tone="sky"
          />
          <MetricCard
            label="Range Change"
            value={fmtSignedNumber(stats?.change_usdt)}
            unit="USDT"
            hint={fmtPct(stats?.change_pct)}
            tone={(stats?.change_usdt ?? 0) >= 0 ? "teal" : "rose"}
          />
          <MetricCard
            label="Max Drawdown"
            value={fmtNumber(stats?.max_drawdown)}
            unit="USDT"
            hint={fmtPct(stats?.max_drawdown_pct)}
            tone="amber"
          />
          <MetricCard
            label="Coverage"
            value={`${stats?.run_count ?? 0} runs`}
            hint={`${stats?.point_count ?? 0} plotted / ${stats?.raw_point_count ?? 0} raw samples`}
            tone="violet"
          />
        </div>
      </div>
    </DashboardShell>
  );
}
