"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  CointegratedPair,
  CointegratedPairDetail,
  CointegratedPairsResponse,
  PairSupplyStatus,
  UserRecord,
  getCointegratedPairDetail,
  getCointegratedPairs,
  getMe,
  getPairSupplyStatus,
  isUnauthorizedError,
  startPairSupply,
  stopPairSupply,
} from "../../../../lib/api";
import { DashboardShell } from "../../../../components/dashboard-shell";
import { MetricCard, PanelCard, StatusPill, TableFrame } from "../../../../components/panels";
import { getStoredAdminEmail } from "../../../../lib/auth";
import {
  canAccessAdminPath,
  getAdminNavItems,
  getFirstAccessibleAdminPath,
  hasPermission,
} from "../../../../lib/admin-access";
import { UI_CLASSES } from "../../../../lib/ui-classes";

type ViewMode = "grid" | "list";

function fmtNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return value.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function fmtCompact(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return Intl.NumberFormat(undefined, {
    notation: "compact",
    maximumFractionDigits: digits,
  }).format(value);
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return "n/a";
  return dt.toLocaleString();
}

function fmtTick(iso: string): string {
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return iso;
  return dt.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function statusNumber(status: Record<string, unknown> | undefined, key: string): number | null {
  const value = status?.[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function statusBool(status: Record<string, unknown> | undefined, key: string): boolean {
  return status?.[key] === true || status?.[key] === "true";
}

function pairMatches(pair: CointegratedPair, query: string): boolean {
  if (!query.trim()) return true;
  const haystack = `${pair.sym_1} ${pair.sym_2} ${pair.pair}`.toLowerCase();
  return haystack.includes(query.trim().toLowerCase());
}

function pairButtonClass(active: boolean): string {
  return [
    "w-full rounded-2xl border p-4 text-left transition",
    active
      ? "border-brand-500 bg-brand-50 shadow-sm dark:border-brand-400 dark:bg-brand-950/30"
      : "border-gray-200 bg-white hover:border-brand-300 hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-900 dark:hover:border-brand-700 dark:hover:bg-gray-800/60",
  ].join(" ");
}

function listButtonClass(active: boolean): string {
  return [
    "grid w-full grid-cols-[minmax(13rem,1.2fr)_repeat(5,minmax(6rem,0.7fr))] items-center gap-3 border-b border-gray-200 px-4 py-3 text-left text-sm transition last:border-b-0 dark:border-gray-800",
    active
      ? "bg-brand-50 text-brand-700 dark:bg-brand-950/30 dark:text-brand-300"
      : "bg-white hover:bg-gray-50 dark:bg-gray-900 dark:hover:bg-gray-800/70",
  ].join(" ");
}

function ChartEmpty({ message }: { message: string }) {
  return <p className="py-20 text-center text-sm text-gray-500 dark:text-gray-400">{message}</p>;
}

export default function CointegratedPairPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [pairsLoading, setPairsLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<CointegratedPairsResponse | null>(null);
  const [supplyStatus, setSupplyStatus] = useState<PairSupplyStatus | null>(null);
  const [supplyBusy, setSupplyBusy] = useState(false);
  const [selectedPair, setSelectedPair] = useState<CointegratedPair | null>(null);
  const [detail, setDetail] = useState<CointegratedPairDetail | null>(null);
  const [query, setQuery] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("grid");

  const navItems = useMemo(() => getAdminNavItems(user), [user]);
  const auth = useMemo(() => ({ email: getStoredAdminEmail(), hasToken: true }), []);

  useEffect(() => {
    getMe()
      .then((u) => setUser(u))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (loading || !user) return;
    const firstAccessible = getFirstAccessibleAdminPath(user);
    if (!canAccessAdminPath(user, pathname)) {
      router.replace(firstAccessible || "/");
    }
  }, [loading, pathname, router, user]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      await Promise.resolve();
      if (cancelled) return;
      setPairsLoading(true);
      setError(null);
      try {
        const [data, supply] = await Promise.all([
          getCointegratedPairs(500),
          getPairSupplyStatus().catch(() => null),
        ]);
        if (cancelled) return;
        setCatalog(data);
        setSupplyStatus(supply);
        setSelectedPair((current) => current || data.pairs[0] || null);
      } catch (err) {
        if (cancelled) return;
        setError(isUnauthorizedError(err) ? "Unauthorized" : "Failed to load cointegrated pairs");
        setCatalog(null);
      } finally {
        if (!cancelled) setPairsLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedPair) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      await Promise.resolve();
      if (cancelled) return;
      setDetailLoading(true);
      setError(null);
      try {
        const data = await getCointegratedPairDetail(selectedPair.sym_1, selectedPair.sym_2, 720);
        if (!cancelled) setDetail(data);
      } catch (err) {
        if (cancelled) return;
        setError(isUnauthorizedError(err) ? "Unauthorized" : "Failed to load selected pair graph");
        setDetail(null);
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selectedPair]);

  const filteredPairs = useMemo(
    () => (catalog?.pairs || []).filter((pair) => pairMatches(pair, query)),
    [catalog, query],
  );

  if (loading) {
    return <div className="p-8 text-center text-gray-500">Loading...</div>;
  }

  const activeHref = "/admin/dashboard/cointegrated-pair";
  const status = catalog?.status;
  const preservedExisting = statusBool(status, "preserved_existing");
  const latestAttemptRows = statusNumber(status, "latest_attempt_rows");
  const canonicalRows = statusNumber(status, "canonical_rows");
  const chartData = detail?.points || [];
  const canManageSupply = hasPermission(user, "manage_bot");

  async function refreshCatalog() {
    setPairsLoading(true);
    setError(null);
    try {
      const [data, supply] = await Promise.all([
        getCointegratedPairs(500),
        getPairSupplyStatus().catch(() => null),
      ]);
      setCatalog(data);
      setSupplyStatus(supply);
      if (!selectedPair && data.pairs[0]) setSelectedPair(data.pairs[0]);
    } catch (err) {
      setError(isUnauthorizedError(err) ? "Unauthorized" : "Failed to refresh cointegrated pairs");
    } finally {
      setPairsLoading(false);
    }
  }

  async function togglePairSupply() {
    if (!canManageSupply) return;
    setSupplyBusy(true);
    setError(null);
    try {
      const next = supplyStatus?.running ? await stopPairSupply() : await startPairSupply();
      setSupplyStatus(next);
    } catch (err) {
      setError(isUnauthorizedError(err) ? "Unauthorized" : "Failed to update pair supply process");
    } finally {
      setSupplyBusy(false);
    }
  }

  return (
    <DashboardShell
      title="Cointegrated Pair"
      subtitle="Last-good pair supply from Strategy discovery"
      status={error ? "WARN" : preservedExisting ? "STALE" : "OK"}
      activeHref={activeHref}
      navItems={navItems}
      auth={auth}
    >
      <div className="space-y-6">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="Canonical Pairs"
            value={String(catalog?.pair_count ?? canonicalRows ?? 0)}
            hint={`CSV updated ${fmtDate(catalog?.updated_at)}`}
            tone="sky"
          />
          <MetricCard
            label="Latest Attempt"
            value={latestAttemptRows === null ? "n/a" : String(latestAttemptRows)}
            hint={preservedExisting ? "Empty scan preserved last-good CSV" : "Latest scan became canonical"}
            tone={preservedExisting ? "amber" : "teal"}
          />
          <MetricCard
            label="Pair Supply"
            value={supplyStatus?.running ? "Running" : "Stopped"}
            hint={supplyStatus?.running ? `PID ${supplyStatus.pid}` : supplyStatus?.detail || "Independent scanner"}
            tone={supplyStatus?.running ? "teal" : "amber"}
          />
          <MetricCard
            label="Selected Z"
            value={fmtNumber(detail?.stats.zscore_current, 3)}
            hint={selectedPair?.pair || "No pair selected"}
            tone={Math.abs(detail?.stats.zscore_current || 0) >= 2 ? "amber" : "violet"}
          />
        </div>

        <div className="grid min-h-0 grid-cols-1 gap-6 xl:grid-cols-[minmax(22rem,0.9fr)_minmax(0,1.6fr)]">
          <PanelCard
            title="Pair Universe"
            subtitle="Grid/list view of the canonical pair supply. Search still works even when Strategy preserves a previous scan."
            titleRight={
              <div className="flex flex-wrap items-center justify-end gap-2">
                {preservedExisting ? <StatusPill label="Last-good preserved" tone="warn" /> : <StatusPill label="Fresh" tone="success" />}
                <button
                  type="button"
                  className={UI_CLASSES.secondaryButton}
                  onClick={refreshCatalog}
                  disabled={pairsLoading}
                >
                  Refresh
                </button>
                <button
                  type="button"
                  className={
                    supplyStatus?.running
                      ? "inline-flex items-center rounded-xl border border-error-300 bg-error-50 px-4 py-2 text-sm font-medium text-error-700 hover:bg-error-100 disabled:opacity-70 dark:border-error-900 dark:bg-error-950/20 dark:text-error-400"
                      : UI_CLASSES.primaryButton
                  }
                  onClick={togglePairSupply}
                  disabled={supplyBusy || !canManageSupply}
                  title={!canManageSupply ? "Manage bot permission required" : undefined}
                >
                  {supplyBusy ? "Working..." : supplyStatus?.running ? "Stop Supply" : "Start Supply"}
                </button>
              </div>
            }
          >
            <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
              <input
                className={UI_CLASSES.input}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search ticker or pair..."
              />
              <div className="flex shrink-0 rounded-xl border border-gray-200 bg-gray-50 p-1 dark:border-gray-800 dark:bg-gray-950">
                {(["grid", "list"] as ViewMode[]).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setViewMode(mode)}
                    className={[
                      "rounded-lg px-3 py-2 text-xs font-semibold uppercase tracking-[0.08em]",
                      viewMode === mode
                        ? "bg-white text-brand-600 shadow-sm dark:bg-gray-800 dark:text-brand-300"
                        : "text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100",
                    ].join(" ")}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </div>

            {pairsLoading ? (
              <ChartEmpty message="Loading pair universe..." />
            ) : error && !catalog ? (
              <ChartEmpty message={error} />
            ) : !filteredPairs.length ? (
              <ChartEmpty message="No pairs match the current search." />
            ) : viewMode === "grid" ? (
              <div className="grid max-h-[38rem] grid-cols-1 gap-3 overflow-auto pr-1 custom-scrollbar 2xl:grid-cols-2">
                {filteredPairs.map((pair) => (
                  <button
                    key={pair.id}
                    type="button"
                    className={pairButtonClass(selectedPair?.id === pair.id)}
                    onClick={() => setSelectedPair(pair)}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-mono text-sm font-semibold text-gray-900 dark:text-white">{pair.pair}</p>
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Rank #{pair.rank}</p>
                      </div>
                      <StatusPill label={`${pair.zero_crossing ?? 0} crosses`} tone="info" />
                    </div>
                    <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
                      <span className="text-gray-500">p-value <b className="font-mono text-gray-900 dark:text-white">{fmtNumber(pair.p_value, 5)}</b></span>
                      <span className="text-gray-500">hedge <b className="font-mono text-gray-900 dark:text-white">{fmtNumber(pair.hedge_ratio, 3)}</b></span>
                      <span className="text-gray-500">liq <b className="font-mono text-gray-900 dark:text-white">{fmtCompact(pair.pair_liquidity_min)}</b></span>
                      <span className="text-gray-500">cap <b className="font-mono text-gray-900 dark:text-white">{fmtCompact(pair.pair_order_capacity_usdt)}</b></span>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <TableFrame maxHeightClass="max-h-[38rem]">
                <div className="min-w-[780px]">
                  <div className="grid grid-cols-[minmax(13rem,1.2fr)_repeat(5,minmax(6rem,0.7fr))] gap-3 border-b border-gray-200 bg-gray-50 px-4 py-3 text-xs font-semibold uppercase tracking-[0.12em] text-gray-500 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-400">
                    <span>Pair</span>
                    <span>Crosses</span>
                    <span>p-value</span>
                    <span>Hedge</span>
                    <span>Liquidity</span>
                    <span>Capacity</span>
                  </div>
                  {filteredPairs.map((pair) => (
                    <button
                      key={pair.id}
                      type="button"
                      className={listButtonClass(selectedPair?.id === pair.id)}
                      onClick={() => setSelectedPair(pair)}
                    >
                      <span className="font-mono font-semibold">{pair.pair}</span>
                      <span>{pair.zero_crossing ?? 0}</span>
                      <span>{fmtNumber(pair.p_value, 5)}</span>
                      <span>{fmtNumber(pair.hedge_ratio, 3)}</span>
                      <span>{fmtCompact(pair.pair_liquidity_min)}</span>
                      <span>{fmtCompact(pair.pair_order_capacity_usdt)}</span>
                    </button>
                  ))}
                </div>
              </TableFrame>
            )}
          </PanelCard>

          <div className="space-y-6">
            <PanelCard
              title={selectedPair ? selectedPair.pair : "Pair Detail"}
              subtitle="Normalized prices, spread, and z-score computed from Strategy price history."
              titleRight={detailLoading ? <StatusPill label="Loading" tone="neutral" /> : <StatusPill label="Chart" tone="success" />}
            >
              {detailLoading ? (
                <ChartEmpty message="Loading pair graph..." />
              ) : !selectedPair ? (
                <ChartEmpty message="Select a pair to view cointegration graphs." />
              ) : !chartData.length ? (
                <ChartEmpty message="No chart data available for this pair." />
              ) : (
                <div className="space-y-8">
                  <div>
                    <h4 className="mb-2 text-sm font-semibold text-gray-800 dark:text-white/90">Normalized Price Path</h4>
                    <ResponsiveContainer width="100%" height={280}>
                      <LineChart data={chartData}>
                        <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#263244" />
                        <XAxis dataKey="ts" tickFormatter={fmtTick} tickLine={false} axisLine={false} fontSize={11} />
                        <YAxis tickLine={false} axisLine={false} fontSize={11} domain={["auto", "auto"]} />
                        <Tooltip labelFormatter={(value) => fmtDate(String(value))} />
                        <Legend />
                        <Line type="monotone" dataKey="price_1_norm" name={selectedPair.sym_1} stroke="#2563eb" strokeWidth={2.5} dot={false} />
                        <Line type="monotone" dataKey="price_2_norm" name={selectedPair.sym_2} stroke="#14b8a6" strokeWidth={2.5} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>

                  <div>
                    <h4 className="mb-2 text-sm font-semibold text-gray-800 dark:text-white/90">Spread Z-Score</h4>
                    <ResponsiveContainer width="100%" height={300}>
                      <LineChart data={chartData}>
                        <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#263244" />
                        <XAxis dataKey="ts" tickFormatter={fmtTick} tickLine={false} axisLine={false} fontSize={11} />
                        <YAxis yAxisId="z" tickLine={false} axisLine={false} fontSize={11} domain={["auto", "auto"]} />
                        <YAxis yAxisId="spread" orientation="right" tickLine={false} axisLine={false} fontSize={11} domain={["auto", "auto"]} />
                        <Tooltip labelFormatter={(value) => fmtDate(String(value))} />
                        <Legend />
                        <Line yAxisId="spread" type="monotone" dataKey="spread" name="Spread" stroke="#94a3b8" strokeWidth={1.6} dot={false} />
                        <Line yAxisId="z" type="monotone" dataKey="zscore" name="Z-score" stroke="#f97316" strokeWidth={2.6} dot={false} />
                        <Line yAxisId="z" type="monotone" dataKey="z_upper" name="+2" stroke="#ef4444" strokeDasharray="5 5" dot={false} />
                        <Line yAxisId="z" type="monotone" dataKey="z_lower" name="-2" stroke="#22c55e" strokeDasharray="5 5" dot={false} />
                        <Line yAxisId="z" type="monotone" dataKey="z_mid" name="0" stroke="#64748b" strokeDasharray="4 6" dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </PanelCard>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <MetricCard label="p-value" value={fmtNumber(detail?.pair.p_value, 5)} hint="Lower is stronger" tone="teal" />
              <MetricCard label="Zero Crossings" value={String(detail?.pair.zero_crossing ?? "n/a")} hint="Mean-reversion frequency" tone="sky" />
              <MetricCard label="Spread Std" value={fmtNumber(detail?.stats.spread_std, 5)} hint="Latest chart window" tone="violet" />
            </div>
          </div>
        </div>
      </div>
    </DashboardShell>
  );
}
