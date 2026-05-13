"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  getMe,
  getPairHistory,
  isUnauthorizedError,
  PairHistoryResponse,
  PairSummary,
  UserRecord,
} from "../../../../../lib/api";
import {
  canAccessAdminPath,
  getAdminNavItems,
  getFirstAccessibleAdminPath,
} from "../../../../../lib/admin-access";
import { getStoredAdminEmail } from "../../../../../lib/auth";
import { UI_CLASSES } from "../../../../../lib/ui-classes";
import { DashboardShell } from "../../../../../components/dashboard-shell";
import { MetricCard, PanelCard, StatusPill, TableFrame } from "../../../../../components/panels";

type StatusFilter = "all" | "stable" | "warning" | "hospital" | "graveyard";
type PnlFilter = "all" | "winners" | "losers";
type HedgeDriftFilter = "all" | "high_drift";
type SortDir = "asc" | "desc";

type FilterState = {
  search: string;
  status: StatusFilter;
  pnlFilter: PnlFilter;
  minTradeCount: string;
  minWinRate: string;
  maxWinRate: string;
  regime: string;
  hedgeDriftFilter: HedgeDriftFilter;
  significantOnly: boolean;
  startDate: string;
  endDate: string;
};

const ACTIVE_HREF = "/admin/dashboard/pairs/history";
const DEFAULT_FILTERS: FilterState = {
  search: "",
  status: "all",
  pnlFilter: "all",
  minTradeCount: "",
  minWinRate: "",
  maxWinRate: "",
  regime: "",
  hedgeDriftFilter: "all",
  significantOnly: false,
  startDate: "",
  endDate: "",
};

const SORTABLE_COLUMNS = new Set([
  "net_pnl_usdt",
  "total_trades",
  "win_rate",
  "profit_factor",
  "max_drawdown_usdt",
  "avg_hold_seconds",
  "last_traded_at",
  "avg_hedge_drift_pct",
]);

function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "n/a";
  return value.toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function formatInteger(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "n/a";
  return Math.round(value).toLocaleString();
}

function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString(undefined, {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  })} USDT`;
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "n/a";
  return `${(value * 100).toLocaleString(undefined, {
    maximumFractionDigits: 1,
    minimumFractionDigits: 1,
  })}%`;
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "n/a";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${formatNumber(seconds / 3600, 1)}h`;
  return `${formatNumber(seconds / 86400, 1)}d`;
}

function formatTimestamp(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "n/a";
  const millis = seconds > 10_000_000_000 ? seconds : seconds * 1000;
  return new Date(millis).toLocaleString();
}

function parseOptionalNumber(value: string): number | undefined {
  if (!value.trim()) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function parseDateInput(value: string): number | undefined {
  if (!value) return undefined;
  const millis = new Date(value).getTime();
  return Number.isFinite(millis) ? Math.floor(millis / 1000) : undefined;
}

function pnlClass(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "text-slate-300";
  }
  if (value > 0) return "text-emerald-300";
  if (value < 0) return "text-rose-300";
  return "text-slate-300";
}

function statusTone(status: string | null | undefined): "success" | "warn" | "error" | "neutral" {
  switch ((status ?? "").toLowerCase()) {
    case "stable":
    case "tradable":
      return "success";
    case "warning":
      return "warn";
    case "hospital":
    case "graveyard":
      return "error";
    default:
      return "neutral";
  }
}

function tagTone(tag: string): "success" | "warn" | "error" | "info" | "neutral" {
  switch (tag) {
    case "elite":
    case "profitable":
    case "stable":
    case "good_reverter":
      return "success";
    case "warning":
    case "high_drift":
    case "high_slippage":
    case "high_break_risk":
      return "warn";
    case "hospital":
    case "graveyard":
    case "losing":
    case "bad_executor":
      return "error";
    default:
      return "info";
  }
}

function pairDetailHref(pair: string): string {
  return `/admin/dashboard/pair-detail?pair=${encodeURIComponent(pair)}&timeframe=1m`;
}

export default function PairHistoryPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserRecord | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [sortBy, setSortBy] = useState("net_pnl_usdt");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [data, setData] = useState<PairHistoryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const {
    startDate,
    endDate,
    status,
    pnlFilter,
    minTradeCount,
    minWinRate,
    maxWinRate,
    regime,
    hedgeDriftFilter,
    significantOnly,
  } = filters;

  useEffect(() => {
    let mounted = true;
    setAuthLoading(true);
    getMe()
      .then((record) => {
        if (!mounted) return;
        setUser(record);
        if (!canAccessAdminPath(record, pathname ?? ACTIVE_HREF)) {
          router.replace(getFirstAccessibleAdminPath(record) ?? "/");
        }
      })
      .catch((err) => {
        if (!mounted) return;
        if (isUnauthorizedError(err)) {
          const next = pathname ?? ACTIVE_HREF;
          router.replace(`/admin/login?next=${encodeURIComponent(next)}`);
          return;
        }
        setError(err instanceof Error ? err.message : "Unable to verify admin access.");
      })
      .finally(() => {
        if (mounted) setAuthLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [pathname, router]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setDebouncedSearch(filters.search.trim());
    }, 300);
    return () => window.clearTimeout(timeout);
  }, [filters.search]);

  const navItems = useMemo(() => getAdminNavItems(user), [user]);

  const loadPairHistory = useCallback(
    async (forceRefresh = false) => {
      setError(null);
      if (forceRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      try {
        const response = await getPairHistory({
          startTs: parseDateInput(startDate),
          endTs: parseDateInput(endDate),
          status: status === "all" ? undefined : status,
          pnlFilter,
          minTradeCount: parseOptionalNumber(minTradeCount),
          minWinRate: parseOptionalNumber(minWinRate),
          maxWinRate: parseOptionalNumber(maxWinRate),
          regime: regime.trim() || undefined,
          hedgeDriftFilter,
          significantOnly,
          search: debouncedSearch || undefined,
          sortBy,
          sortDir,
          page,
          pageSize,
          refresh: forceRefresh,
        });
        setData(response);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load pair history.");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [
      debouncedSearch,
      endDate,
      hedgeDriftFilter,
      maxWinRate,
      minTradeCount,
      minWinRate,
      page,
      pageSize,
      pnlFilter,
      regime,
      significantOnly,
      sortBy,
      sortDir,
      startDate,
      status,
    ],
  );

  useEffect(() => {
    if (authLoading || !user || !canAccessAdminPath(user, ACTIVE_HREF)) return;
    void loadPairHistory(false);
  }, [authLoading, loadPairHistory, user]);

  const updateFilter = <K extends keyof FilterState>(key: K, value: FilterState[K]) => {
    setFilters((current) => ({ ...current, [key]: value }));
    setPage(1);
  };

  const toggleSort = (field: string) => {
    if (!SORTABLE_COLUMNS.has(field)) return;
    if (sortBy === field) {
      setSortDir((direction) => (direction === "asc" ? "desc" : "asc"));
    } else {
      setSortDir("desc");
      setSortBy(field);
    }
    setPage(1);
  };

  const sortLabel = (field: string) => {
    if (sortBy !== field) return "Sort";
    return sortDir === "asc" ? "Sorted ascending" : "Sorted descending";
  };

  const meta = data?.meta;
  const totalPages = Math.max(1, meta?.total_pages ?? 1);
  const rows = data?.rows ?? [];
  const cache = data?.cache;

  const renderSortableHeader = (label: string, field: string) => (
    <button
      className="inline-flex items-center gap-1 text-left text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 transition hover:text-slate-200"
      type="button"
      onClick={() => toggleSort(field)}
      aria-label={sortLabel(field)}
    >
      {label}
      <span className="text-[10px] text-slate-500">
        {sortBy === field ? (sortDir === "asc" ? "▲" : "▼") : ""}
      </span>
    </button>
  );

  if (authLoading) {
    return (
      <DashboardShell
        title="Pair History"
        subtitle="Review historical pair performance, significant wins/losses, hedge drift, and pair health."
        status="Read-only"
        activeHref={ACTIVE_HREF}
        navItems={navItems}
        auth={{ email: getStoredAdminEmail(), hasToken: true }}
      >
        <PanelCard title="Loading" subtitle="Checking dashboard access.">
          <p className="text-sm text-slate-400">Loading pair history...</p>
        </PanelCard>
      </DashboardShell>
    );
  }

  return (
    <DashboardShell
      title="Pair History"
      subtitle="Review historical pair performance, significant wins/losses, hedge drift, and pair health."
      status={cache ? `Updated ${formatTimestamp(cache.generated_at)}` : "Read-only"}
      activeHref={ACTIVE_HREF}
      navItems={navItems}
      auth={{ email: user?.email ?? getStoredAdminEmail(), hasToken: true }}
      actions={
        <button
          type="button"
          className={UI_CLASSES.secondaryButton}
          onClick={() => void loadPairHistory(true)}
          disabled={refreshing}
        >
          {refreshing ? "Refreshing..." : "Refresh"}
        </button>
      }
    >
      {error ? (
        <PanelCard title="Unable to load pair history" subtitle={error}>
          <button type="button" className={UI_CLASSES.primaryButton} onClick={() => void loadPairHistory(true)}>
            Retry
          </button>
        </PanelCard>
      ) : null}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
        <MetricCard label="Total Pairs" value={formatInteger(data?.kpis.total_pairs)} tone="sky" />
        <MetricCard label="Tradable Pairs" value={formatInteger(data?.kpis.tradable_pairs)} tone="teal" />
        <MetricCard label="Profitable Pairs" value={formatInteger(data?.kpis.profitable_pairs)} tone="teal" />
        <MetricCard label="Losing Pairs" value={formatInteger(data?.kpis.losing_pairs)} tone="rose" />
        <MetricCard label="Hospital Pairs" value={formatInteger(data?.kpis.hospital_pairs)} tone="amber" />
        <MetricCard label="Graveyard Pairs" value={formatInteger(data?.kpis.graveyard_pairs)} tone="violet" />
      </section>

      <PanelCard
        title="Filters"
        subtitle={
          cache
            ? `${cache.cache_hit ? "Cache hit" : "Fresh result"} · TTL ${cache.ttl_seconds ?? "n/a"}s`
            : "Search, filter, and sort read-only pair history."
        }
      >
        <div className="grid gap-4 lg:grid-cols-4">
          <label className="space-y-2 text-sm text-slate-300">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Search Pair</span>
            <input
              className={UI_CLASSES.input}
              value={filters.search}
              onChange={(event) => updateFilter("search", event.target.value)}
              placeholder="BTC-USDT-SWAP / ETH-USDT-SWAP"
            />
          </label>
          <label className="space-y-2 text-sm text-slate-300">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Status</span>
            <select
              className={UI_CLASSES.input}
              value={filters.status}
              onChange={(event) => updateFilter("status", event.target.value as StatusFilter)}
            >
              <option value="all">All</option>
              <option value="stable">Stable</option>
              <option value="warning">Warning</option>
              <option value="hospital">Hospital</option>
              <option value="graveyard">Graveyard</option>
            </select>
          </label>
          <label className="space-y-2 text-sm text-slate-300">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">PnL</span>
            <select
              className={UI_CLASSES.input}
              value={filters.pnlFilter}
              onChange={(event) => updateFilter("pnlFilter", event.target.value as PnlFilter)}
            >
              <option value="all">All</option>
              <option value="winners">Winners</option>
              <option value="losers">Losers</option>
            </select>
          </label>
          <label className="space-y-2 text-sm text-slate-300">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Hedge Drift</span>
            <select
              className={UI_CLASSES.input}
              value={filters.hedgeDriftFilter}
              onChange={(event) => updateFilter("hedgeDriftFilter", event.target.value as HedgeDriftFilter)}
            >
              <option value="all">All</option>
              <option value="high_drift">High drift</option>
            </select>
          </label>
          <label className="space-y-2 text-sm text-slate-300">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Min Trades</span>
            <input
              className={UI_CLASSES.input}
              type="number"
              min="0"
              value={filters.minTradeCount}
              onChange={(event) => updateFilter("minTradeCount", event.target.value)}
              placeholder="n/a"
            />
          </label>
          <label className="space-y-2 text-sm text-slate-300">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Win Rate Min</span>
            <input
              className={UI_CLASSES.input}
              type="number"
              min="0"
              max="1"
              step="0.01"
              value={filters.minWinRate}
              onChange={(event) => updateFilter("minWinRate", event.target.value)}
              placeholder="0.50"
            />
          </label>
          <label className="space-y-2 text-sm text-slate-300">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Win Rate Max</span>
            <input
              className={UI_CLASSES.input}
              type="number"
              min="0"
              max="1"
              step="0.01"
              value={filters.maxWinRate}
              onChange={(event) => updateFilter("maxWinRate", event.target.value)}
              placeholder="1.00"
            />
          </label>
          <label className="space-y-2 text-sm text-slate-300">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Regime</span>
            <input
              className={UI_CLASSES.input}
              value={filters.regime}
              onChange={(event) => updateFilter("regime", event.target.value)}
              placeholder="n/a"
            />
          </label>
          <label className="space-y-2 text-sm text-slate-300">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Start</span>
            <input
              className={UI_CLASSES.input}
              type="datetime-local"
              value={filters.startDate}
              onChange={(event) => updateFilter("startDate", event.target.value)}
            />
          </label>
          <label className="space-y-2 text-sm text-slate-300">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">End</span>
            <input
              className={UI_CLASSES.input}
              type="datetime-local"
              value={filters.endDate}
              onChange={(event) => updateFilter("endDate", event.target.value)}
            />
          </label>
          <label className="flex items-center gap-3 rounded-md border border-white/10 bg-white/[0.03] px-3 py-3 text-sm text-slate-300 lg:mt-7">
            <input
              type="checkbox"
              checked={filters.significantOnly}
              onChange={(event) => updateFilter("significantOnly", event.target.checked)}
            />
            Significant only
          </label>
          <button
            type="button"
            className={`${UI_CLASSES.secondaryButton} lg:mt-7`}
            onClick={() => {
              setFilters(DEFAULT_FILTERS);
              setPage(1);
            }}
          >
            Clear Filters
          </button>
        </div>
      </PanelCard>

      <PanelCard
        title="Pair Review"
        subtitle={
          meta
            ? `${formatInteger(meta.total_rows)} pairs · page ${meta.page} of ${Math.max(1, meta.total_pages)}`
            : "Searchable pair performance and health history."
        }
      >
        {loading && !data ? (
          <div className="rounded-md border border-white/10 bg-white/[0.03] p-6 text-sm text-slate-400">
            Loading pair history...
          </div>
        ) : rows.length === 0 ? (
          <div className="rounded-md border border-white/10 bg-white/[0.03] p-6 text-sm text-slate-400">
            No pairs found for the selected filters.
          </div>
        ) : (
          <TableFrame>
            <table className="min-w-[1440px] text-left text-sm">
              <thead className="border-b border-white/10 text-slate-500">
                <tr>
                  <th className="px-4 py-3">Pair</th>
                  <th className="px-4 py-3">{renderSortableHeader("Net PnL", "net_pnl_usdt")}</th>
                  <th className="px-4 py-3">{renderSortableHeader("Trades", "total_trades")}</th>
                  <th className="px-4 py-3">{renderSortableHeader("Win Rate", "win_rate")}</th>
                  <th className="px-4 py-3">{renderSortableHeader("Profit Factor", "profit_factor")}</th>
                  <th className="px-4 py-3">{renderSortableHeader("Max Drawdown", "max_drawdown_usdt")}</th>
                  <th className="px-4 py-3">Best Trade</th>
                  <th className="px-4 py-3">Worst Trade</th>
                  <th className="px-4 py-3">{renderSortableHeader("Avg Hold", "avg_hold_seconds")}</th>
                  <th className="px-4 py-3">Avg Entry Z</th>
                  <th className="px-4 py-3">Avg Exit Z</th>
                  <th className="px-4 py-3">Avg Hedge Ratio</th>
                  <th className="px-4 py-3">{renderSortableHeader("Hedge Drift", "avg_hedge_drift_pct")}</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">{renderSortableHeader("Last Trade", "last_traded_at")}</th>
                  <th className="px-4 py-3">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/10">
                {rows.map((row) => (
                  <PairHistoryRow key={row.pair} row={row} onOpen={() => router.push(pairDetailHref(row.pair))} />
                ))}
              </tbody>
            </table>
          </TableFrame>
        )}

        <div className="mt-4 flex flex-col gap-3 text-sm text-slate-400 md:flex-row md:items-center md:justify-between">
          <div>
            Page {meta?.page ?? page} of {totalPages} · {formatInteger(meta?.total_rows)} rows
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2">
              <span>Rows</span>
              <select
                className={UI_CLASSES.inputSmall}
                value={pageSize}
                onChange={(event) => {
                  setPageSize(Number(event.target.value));
                  setPage(1);
                }}
              >
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
                <option value={200}>200</option>
              </select>
            </label>
            <button
              type="button"
              className={UI_CLASSES.secondaryButton}
              disabled={page <= 1 || loading}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
            >
              Previous
            </button>
            <button
              type="button"
              className={UI_CLASSES.secondaryButton}
              disabled={page >= totalPages || loading}
              onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
            >
              Next
            </button>
          </div>
        </div>
      </PanelCard>
    </DashboardShell>
  );
}

function PairHistoryRow({ row, onOpen }: { row: PairSummary; onOpen: () => void }) {
  return (
    <tr className="text-slate-300 transition hover:bg-white/[0.03]">
      <td className="px-4 py-3 align-top">
        <div className="font-medium text-slate-100">{row.pair}</div>
        {row.tags.length > 0 ? (
          <div className="mt-2 flex max-w-[280px] flex-wrap gap-1.5">
            {row.tags.map((tag) => (
              <StatusPill key={tag} label={tag.replaceAll("_", " ")} tone={tagTone(tag)} />
            ))}
          </div>
        ) : (
          <div className="mt-1 text-xs text-slate-500">No tags</div>
        )}
      </td>
      <td className={`px-4 py-3 align-top font-medium ${pnlClass(row.net_pnl_usdt)}`}>
        {formatMoney(row.net_pnl_usdt)}
      </td>
      <td className="px-4 py-3 align-top">{formatInteger(row.total_trades)}</td>
      <td className="px-4 py-3 align-top">{formatPercent(row.win_rate)}</td>
      <td className="px-4 py-3 align-top">{formatNumber(row.profit_factor)}</td>
      <td className={`px-4 py-3 align-top ${pnlClass(row.max_drawdown_usdt)}`}>
        {formatMoney(row.max_drawdown_usdt)}
      </td>
      <td className={`px-4 py-3 align-top ${pnlClass(row.best_trade?.pnl_usdt)}`}>
        {formatMoney(row.best_trade?.pnl_usdt)}
      </td>
      <td className={`px-4 py-3 align-top ${pnlClass(row.worst_trade?.pnl_usdt)}`}>
        {formatMoney(row.worst_trade?.pnl_usdt)}
      </td>
      <td className="px-4 py-3 align-top">{formatDuration(row.avg_hold_seconds)}</td>
      <td className="px-4 py-3 align-top">{formatNumber(row.avg_entry_z)}</td>
      <td className="px-4 py-3 align-top">{formatNumber(row.avg_exit_z)}</td>
      <td className="px-4 py-3 align-top">{formatNumber(row.avg_hedge_ratio, 4)}</td>
      <td className="px-4 py-3 align-top">{formatPercent(row.avg_hedge_drift_pct)}</td>
      <td className="px-4 py-3 align-top">
        <StatusPill label={row.status ?? "n/a"} tone={statusTone(row.status)} />
      </td>
      <td className="px-4 py-3 align-top">{formatTimestamp(row.last_traded_at)}</td>
      <td className="px-4 py-3 align-top">
        <button type="button" className={UI_CLASSES.secondaryButton} onClick={onOpen}>
          Open Pair Detail
        </button>
      </td>
    </tr>
  );
}
