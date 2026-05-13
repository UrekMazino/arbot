"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  ChartAuditActualMarker,
  ChartAuditReplayMarker,
  CounterfactualExitStudy,
  PairDecisionAuditChart,
  PairDetailSummaryResponse,
  TradeSummary,
  UserRecord,
  getCounterfactualExitStudy,
  getMe,
  getPairDecisionAuditChart,
  getPairDetailSummary,
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
import { MetricCard, PanelCard, TableFrame } from "../../../../components/panels";
import {
  CounterfactualExitComparisonPanel,
  DecisionScoreTimelinePanel,
  PairZScoreChart,
} from "../../../../components/chart-audit";

type DetailTab =
  | "overview"
  | "trades"
  | "replay"
  | "counterfactual"
  | "hedge"
  | "ml"
  | "liquidity"
  | "logs";

type SelectedEntry = {
  entryId: string;
  markerType: string;
};

const ACTIVE_HREF = "/admin/dashboard/pair-detail";

const TABS: Array<{ id: DetailTab; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "trades", label: "Trades" },
  { id: "replay", label: "Replay Audit" },
  { id: "counterfactual", label: "Counterfactual Exits" },
  { id: "hedge", label: "Hedge Ratio" },
  { id: "ml", label: "ML Scores" },
  { id: "liquidity", label: "Orderbook / Liquidity" },
  { id: "logs", label: "Logs" },
];

export default function PairDetailPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserRecord | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [pair, setPair] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState("1m");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [summary, setSummary] = useState<PairDetailSummaryResponse | null>(null);
  const [chart, setChart] = useState<PairDecisionAuditChart | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [chartLoading, setChartLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [chartError, setChartError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [scoresEnabled, setScoresEnabled] = useState(false);
  const [activeTab, setActiveTab] = useState<DetailTab>("overview");
  const [selectedEntry, setSelectedEntry] = useState<SelectedEntry | null>(null);
  const [counterfactualStudy, setCounterfactualStudy] = useState<CounterfactualExitStudy | null>(null);
  const [counterfactualLoading, setCounterfactualLoading] = useState(false);
  const [counterfactualError, setCounterfactualError] = useState<string | null>(null);

  const navItems = useMemo(() => getAdminNavItems(user), [user]);
  const auth = useMemo(() => ({ email: getStoredAdminEmail(), hasToken: true }), []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const pairParam = params.get("pair");
    const timeframeParam = params.get("timeframe");
    setPair(pairParam ? decodePairQueryValue(pairParam) : null);
    setTimeframe(timeframeParam?.trim() || "1m");
  }, []);

  useEffect(() => {
    getMe()
      .then((record) => setUser(record))
      .catch(() => setUser(null))
      .finally(() => setAuthLoading(false));
  }, []);

  useEffect(() => {
    if (authLoading || !user) return;
    if (!canAccessAdminPath(user, pathname)) {
      router.replace(getFirstAccessibleAdminPath(user) ?? "/");
    }
  }, [authLoading, pathname, router, user]);

  const startTs = useMemo(() => parseDateInput(startDate), [startDate]);
  const endTs = useMemo(() => parseDateInput(endDate), [endDate]);

  const loadSummary = useCallback(
    async (forceRefresh = false) => {
      if (!pair) return;
      setSummaryLoading(true);
      setSummaryError(null);
      try {
        const payload = await getPairDetailSummary({
          pair,
          timeframe,
          startTs,
          endTs,
          refresh: forceRefresh,
        });
        setSummary(payload);
      } catch (err) {
        setSummary(null);
        setSummaryError(errorMessage(err, "Failed to load pair detail summary."));
      } finally {
        setSummaryLoading(false);
      }
    },
    [endTs, pair, startTs, timeframe],
  );

  const loadChart = useCallback(
    async () => {
      if (!pair) return;
      setChartLoading(true);
      setChartError(null);
      try {
        const payload = await getPairDecisionAuditChart(pair, timeframe, startTs, endTs, {
          includeDecisionTimeline: scoresEnabled,
          maxTimelinePoints: 1440,
          downsampleMethod: "last",
        });
        setChart(payload);
      } catch (err) {
        setChart(null);
        setChartError(errorMessage(err, "Failed to load chart audit."));
      } finally {
        setChartLoading(false);
      }
    },
    [endTs, pair, scoresEnabled, startTs, timeframe],
  );

  useEffect(() => {
    if (!pair || authLoading) return;
    void loadSummary(false);
    void loadChart();
  }, [authLoading, loadChart, loadSummary, pair]);

  const refreshAll = useCallback(async () => {
    setRefreshing(true);
    try {
      await Promise.all([loadSummary(true), loadChart()]);
    } finally {
      setRefreshing(false);
    }
  }, [loadChart, loadSummary]);

  const handleSelectEntry = (marker: ChartAuditActualMarker | ChartAuditReplayMarker) => {
    const entryId = marker.entry_id || ("trade_id" in marker ? marker.trade_id : null);
    if (!entryId) {
      setCounterfactualError("Selected entry marker does not include an entry_id.");
      setActiveTab("counterfactual");
      return;
    }
    setSelectedEntry({ entryId, markerType: marker.marker_type });
    setCounterfactualStudy(null);
    setCounterfactualError(null);
    setActiveTab("counterfactual");
  };

  const loadCounterfactual = useCallback(async () => {
    if (!pair || !selectedEntry) return;
    const windowStart = startTs ?? chartStart(chart);
    const windowEnd = endTs ?? chartEnd(chart);
    if (windowStart === null || windowEnd === null) {
      setCounterfactualError("Chart window is unavailable; choose a date range before comparing exits.");
      return;
    }
    setCounterfactualLoading(true);
    setCounterfactualError(null);
    try {
      const payload = await getCounterfactualExitStudy(
        selectedEntry.entryId,
        pair,
        timeframe,
        windowStart,
        windowEnd,
      );
      setCounterfactualStudy(payload);
    } catch (err) {
      setCounterfactualStudy(null);
      setCounterfactualError(errorMessage(err, "Failed to load counterfactual exit study."));
    } finally {
      setCounterfactualLoading(false);
    }
  }, [chart, endTs, pair, selectedEntry, startTs, timeframe]);

  const statusTone = statusToTone(summary?.status);
  const cacheStatus = summaryLoading
    ? "Loading summary..."
    : summary?.cache
    ? `Updated ${formatTimestamp(summary.cache.generated_at)} · ${summary.cache.cache_hit ? "cache hit" : "fresh"}`
    : "Read-only";

  if (authLoading) {
    return (
      <DashboardShell
        title="Pair Detail"
        subtitle="Pair summary and chart audit."
        status="Loading"
        activeHref={ACTIVE_HREF}
        navItems={navItems}
        auth={auth}
      >
        <PanelCard title="Loading" subtitle="Checking dashboard access.">
          <p className="text-sm text-gray-500 dark:text-gray-400">Loading pair detail...</p>
        </PanelCard>
      </DashboardShell>
    );
  }

  if (!pair) {
    return (
      <DashboardShell
        title="Pair Detail"
        subtitle="Pair summary and chart audit."
        status="Missing pair"
        activeHref={ACTIVE_HREF}
        navItems={navItems}
        auth={auth}
      >
        <PanelCard title="Pair is required" subtitle="Open Pair Detail from Pair History or add a pair query parameter.">
          <button
            type="button"
            className={UI_CLASSES.primaryButton}
            onClick={() => router.push("/admin/dashboard/pairs/history")}
          >
            Back to Pair History
          </button>
        </PanelCard>
      </DashboardShell>
    );
  }

  return (
    <DashboardShell
      title="Pair Detail"
      subtitle={pair}
      status={cacheStatus}
      activeHref={ACTIVE_HREF}
      navItems={navItems}
      auth={auth}
      actions={
        <div className="flex flex-wrap gap-2">
          <button type="button" className={UI_CLASSES.secondaryButton} onClick={() => router.push("/admin/dashboard/pairs/history")}>
            Pair History
          </button>
          <button type="button" className={UI_CLASSES.secondaryButton} disabled={refreshing} onClick={() => void refreshAll()}>
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      }
    >
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-6">
        <MetricCard label="Pair" value={pair} tone="sky" />
        <MetricCard label="Current Status" value={summary?.status ?? "n/a"} tone={statusTone === "error" ? "rose" : statusTone === "warn" ? "amber" : "teal"} />
        <MetricCard label="Total PnL" value={formatMoney(summary?.summary.total_pnl_usdt)} tone={pnlTone(summary?.summary.total_pnl_usdt)} />
        <MetricCard label="Total Trades" value={formatInteger(summary?.summary.total_trades)} tone="violet" />
        <MetricCard label="Win Rate" value={formatPercent(summary?.summary.win_rate)} tone="teal" />
        <MetricCard label="Profit Factor" value={formatNumber(summary?.summary.profit_factor)} tone="sky" />
        <MetricCard label="Avg Reversion Time" value={formatDuration(summary?.summary.avg_reversion_time_seconds)} tone="violet" />
        <MetricCard label="Avg Hedge Ratio" value={formatNumber(summary?.summary.avg_hedge_ratio, 4)} tone="sky" />
        <MetricCard label="Current Hedge Ratio" value={formatNumber(summary?.summary.current_hedge_ratio, 4)} tone="sky" />
        <MetricCard label="Avg Hedge Drift" value={formatPercent(summary?.summary.avg_hedge_drift_pct)} tone="amber" />
        <MetricCard label="Current Regime" value={summary?.summary.current_regime ?? "n/a"} tone="violet" />
        <MetricCard label="Bayesian Score" value={formatNumber(summary?.summary.current_bayesian_posterior)} tone="teal" />
        <MetricCard label="Final Rank Score" value={formatNumber(summary?.summary.current_final_rank_score)} tone="teal" />
      </section>

      <PanelCard title="Controls" subtitle="Summary and chart audit are read-only analytics.">
        <div className="grid gap-4 md:grid-cols-5">
          <label className="space-y-2 text-sm text-gray-700 dark:text-gray-300">
            <span className="text-xs font-semibold uppercase tracking-[0.12em] text-gray-500">Timeframe</span>
            <input className={UI_CLASSES.input} value={timeframe} onChange={(event) => setTimeframe(event.target.value || "1m")} />
          </label>
          <label className="space-y-2 text-sm text-gray-700 dark:text-gray-300">
            <span className="text-xs font-semibold uppercase tracking-[0.12em] text-gray-500">Start</span>
            <input className={UI_CLASSES.input} type="datetime-local" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
          </label>
          <label className="space-y-2 text-sm text-gray-700 dark:text-gray-300">
            <span className="text-xs font-semibold uppercase tracking-[0.12em] text-gray-500">End</span>
            <input className={UI_CLASSES.input} type="datetime-local" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
          </label>
          <label className="mt-7 flex items-center gap-3 rounded-xl border border-gray-200 bg-gray-50 px-3 py-3 text-sm text-gray-700 dark:border-gray-800 dark:bg-gray-950/40 dark:text-gray-300">
            <input type="checkbox" checked={scoresEnabled} onChange={(event) => setScoresEnabled(event.target.checked)} />
            Scores layer
          </label>
          <button type="button" className={`${UI_CLASSES.primaryButton} mt-7`} onClick={() => void refreshAll()}>
            Apply
          </button>
        </div>
      </PanelCard>

      {summaryError ? <ErrorPanel message={summaryError} onRetry={() => void loadSummary(true)} /> : null}

      <PanelCard
        title="Chart Audit"
        subtitle="Z-score line, statistical markers, replay candidates, actual markers, blocked signals, and lazy counterfactual anchors."
        actions={chartLoading ? <span className="text-sm text-gray-500">Loading chart...</span> : null}
      >
        {chartError ? (
          <ErrorPanel message={chartError} onRetry={() => void loadChart()} />
        ) : (
          <PairZScoreChart chart={chart} selectedEntryId={selectedEntry?.entryId} onSelectEntryMarker={handleSelectEntry} />
        )}
        {scoresEnabled ? (
          <div className="mt-4">
            <DecisionScoreTimelinePanel
              timeline={chart?.decision_score_timeline ?? []}
              meta={chart?.decision_timeline_meta}
              loading={chartLoading}
              error={chartError}
            />
          </div>
        ) : null}
      </PanelCard>

      <PanelCard title="Pair Detail" subtitle="Review pair state, trades, replay quality, exits, hedge ratio, ML scores, liquidity, and logs.">
        <div className="mb-4 flex flex-wrap gap-2">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={activeTab === tab.id ? UI_CLASSES.primaryButton : UI_CLASSES.secondaryButton}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        {renderTabContent({
          activeTab,
          summary,
          chart,
          selectedEntry,
          counterfactualStudy,
          counterfactualLoading,
          counterfactualError,
          onCompare: loadCounterfactual,
          onClearCounterfactual: () => {
            setSelectedEntry(null);
            setCounterfactualStudy(null);
            setCounterfactualError(null);
          },
        })}
      </PanelCard>
    </DashboardShell>
  );
}

function renderTabContent({
  activeTab,
  summary,
  chart,
  selectedEntry,
  counterfactualStudy,
  counterfactualLoading,
  counterfactualError,
  onCompare,
  onClearCounterfactual,
}: {
  activeTab: DetailTab;
  summary: PairDetailSummaryResponse | null;
  chart: PairDecisionAuditChart | null;
  selectedEntry: SelectedEntry | null;
  counterfactualStudy: CounterfactualExitStudy | null;
  counterfactualLoading: boolean;
  counterfactualError: string | null;
  onCompare: () => void;
  onClearCounterfactual: () => void;
}) {
  if (activeTab === "overview") return <OverviewTab summary={summary} chart={chart} />;
  if (activeTab === "trades") return <TradesTab summary={summary} />;
  if (activeTab === "replay") return <ReplayAuditTab summary={summary} chart={chart} />;
  if (activeTab === "counterfactual") {
    return (
      <CounterfactualExitComparisonPanel
        selectedEntryId={selectedEntry?.entryId ?? null}
        study={counterfactualStudy}
        loading={counterfactualLoading}
        error={counterfactualError}
        onCompare={onCompare}
        onClear={onClearCounterfactual}
      />
    );
  }
  if (activeTab === "hedge") return <HedgeTab summary={summary} />;
  if (activeTab === "ml") {
    return (
      <div className="space-y-4">
        <KeyValueGrid
          rows={[
            ["Current regime", summary?.summary.current_regime ?? "n/a"],
            ["Current Bayesian posterior", formatNumber(summary?.summary.current_bayesian_posterior)],
            ["Current final rank score", formatNumber(summary?.summary.current_final_rank_score)],
          ]}
        />
        <DecisionScoreTimelinePanel
          timeline={chart?.decision_score_timeline ?? []}
          meta={chart?.decision_timeline_meta}
        />
      </div>
    );
  }
  if (activeTab === "liquidity") return <LiquidityTab chart={chart} />;
  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Pair-specific log filtering is not loaded here. Open logs and search for this pair if needed.
      </p>
      <a className={UI_CLASSES.secondaryButton} href="/admin/console/logs">
        Open Logs
      </a>
    </div>
  );
}

function OverviewTab({ summary, chart }: { summary: PairDetailSummaryResponse | null; chart: PairDecisionAuditChart | null }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <KeyValueGrid
        title="Pair performance summary"
        rows={[
          ["Status", summary?.status ?? "n/a"],
          ["Total PnL", formatMoney(summary?.summary.total_pnl_usdt)],
          ["Total trades", formatInteger(summary?.summary.total_trades)],
          ["Win rate", formatPercent(summary?.summary.win_rate)],
          ["Profit factor", formatNumber(summary?.summary.profit_factor)],
          ["Last trade result", formatMoney(summary?.latest_trade?.pnl_usdt)],
          ["Best trade", formatMoney(summary?.best_trade?.pnl_usdt)],
          ["Worst trade", formatMoney(summary?.worst_trade?.pnl_usdt)],
        ]}
      />
      <KeyValueGrid
        title="Latest state"
        rows={[
          ["Current regime", summary?.summary.current_regime ?? "n/a"],
          ["Bayesian posterior", formatNumber(summary?.summary.current_bayesian_posterior)],
          ["Final rank score", formatNumber(summary?.summary.current_final_rank_score)],
          ["Replay candidates", String(chart?.replay_markers.filter((marker) => marker.marker_type === "replay_entry_candidate").length ?? "n/a")],
          ["Blocked signals", String(chart?.replay_markers.filter((marker) => marker.marker_type === "replay_blocked_signal").length ?? "n/a")],
          ["Why state changed", mostCommonBlockReason(summary?.block_reason_counts) ?? "n/a"],
        ]}
      />
    </div>
  );
}

function TradesTab({ summary }: { summary: PairDetailSummaryResponse | null }) {
  const trades = [
    { label: "Best", trade: summary?.best_trade ?? null },
    { label: "Worst", trade: summary?.worst_trade ?? null },
    { label: "Latest", trade: summary?.latest_trade ?? null },
  ].filter((item) => item.trade);

  if (!trades.length) {
    return <EmptyState message="Detailed trade rows are unavailable from the summary endpoint." />;
  }

  return (
    <TableFrame>
      <table className="min-w-[1080px] text-left text-sm">
        <thead className="border-b border-gray-200 text-xs uppercase tracking-[0.12em] text-gray-500 dark:border-gray-800">
          <tr>
            <th className="px-4 py-3">Kind</th>
            <th className="px-4 py-3">Trade ID</th>
            <th className="px-4 py-3">Entry Time</th>
            <th className="px-4 py-3">Exit Time</th>
            <th className="px-4 py-3">Side</th>
            <th className="px-4 py-3">Entry Z</th>
            <th className="px-4 py-3">Exit Z</th>
            <th className="px-4 py-3">Hold Time</th>
            <th className="px-4 py-3">PnL</th>
            <th className="px-4 py-3">Fees</th>
            <th className="px-4 py-3">Slippage</th>
            <th className="px-4 py-3">Exit Reason</th>
            <th className="px-4 py-3">Hedge Ratio</th>
            <th className="px-4 py-3">Hedge Drift</th>
            <th className="px-4 py-3">Regime</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
          {trades.map(({ label, trade }) => (
            <TradeRow key={`${label}-${trade?.trade_id}`} label={label} trade={trade as TradeSummary} />
          ))}
        </tbody>
      </table>
    </TableFrame>
  );
}

function TradeRow({ label, trade }: { label: string; trade: TradeSummary }) {
  return (
    <tr className="text-gray-700 dark:text-gray-300">
      <td className="px-4 py-3">{label}</td>
      <td className="px-4 py-3 font-mono text-xs">{trade.trade_id}</td>
      <td className="px-4 py-3">{formatTimestamp(trade.entry_time)}</td>
      <td className="px-4 py-3">{formatTimestamp(trade.exit_time)}</td>
      <td className="px-4 py-3">{trade.side ?? "n/a"}</td>
      <td className="px-4 py-3">{formatNumber(trade.entry_z)}</td>
      <td className="px-4 py-3">{formatNumber(trade.exit_z)}</td>
      <td className="px-4 py-3">{formatDuration(trade.hold_seconds)}</td>
      <td className="px-4 py-3">{formatMoney(trade.pnl_usdt)}</td>
      <td className="px-4 py-3">{formatMoney(trade.fees_usdt)}</td>
      <td className="px-4 py-3">{formatMoney(trade.slippage_usdt)}</td>
      <td className="px-4 py-3">{trade.exit_reason ?? "n/a"}</td>
      <td className="px-4 py-3">{formatNumber(trade.entry_hedge_ratio, 4)}</td>
      <td className="px-4 py-3">{formatPercent(trade.hedge_ratio_drift_pct)}</td>
      <td className="px-4 py-3">{trade.regime_at_entry ?? "n/a"}</td>
    </tr>
  );
}

function ReplayAuditTab({ summary, chart }: { summary: PairDetailSummaryResponse | null; chart: PairDecisionAuditChart | null }) {
  const replayEntries = chart?.replay_markers.filter((marker) => marker.marker_type === "replay_entry_candidate").length ?? null;
  const actualEntries = chart?.actual_markers.filter((marker) => marker.marker_type === "actual_entry").length ?? null;
  const blocked = chart?.replay_markers.filter((marker) => marker.marker_type === "replay_blocked_signal").length ?? null;
  const conversion = replayEntries && actualEntries !== null ? actualEntries / replayEntries : null;

  return (
    <KeyValueGrid
      rows={[
        ["Replay candidates", formatInteger(replayEntries)],
        ["Actual executed trades", formatInteger(actualEntries)],
        ["Blocked signals", formatInteger(blocked)],
        ["Most common block reason", mostCommonBlockReason(summary?.block_reason_counts) ?? "n/a"],
        ["Candidate-to-trade conversion", formatPercent(conversion)],
      ]}
    />
  );
}

function HedgeTab({ summary }: { summary: PairDetailSummaryResponse | null }) {
  return (
    <KeyValueGrid
      rows={[
        ["Avg entry hedge ratio", formatNumber(summary?.hedge_summary.avg_entry_hedge_ratio, 4)],
        ["Avg exit hedge ratio", formatNumber(summary?.hedge_summary.avg_exit_hedge_ratio, 4)],
        ["Avg hedge drift %", formatPercent(summary?.hedge_summary.avg_hedge_drift_pct)],
        ["Equal-notional PnL", formatMoney(summary?.hedge_summary.equal_notional_total_pnl)],
        ["Hedge-ratio-sized PnL", formatMoney(summary?.hedge_summary.hedge_ratio_sized_total_pnl)],
        ["Sizing delta", formatMoney(summary?.hedge_summary.sizing_pnl_delta_usdt)],
      ]}
    />
  );
}

function LiquidityTab({ chart }: { chart: PairDecisionAuditChart | null }) {
  const metadata = latestLiquidityMetadata(chart);
  if (!metadata) {
    return <EmptyState message="Liquidity details unavailable for this pair/time range." />;
  }
  return (
    <KeyValueGrid
      rows={[
        ["Liquidity score", formatNumber(metadataNumber(metadata, "liquidity_score"))],
        ["Microstructure risk", formatNumber(metadataNumber(metadata, "microstructure_risk"))],
        ["Spread bps", formatNumber(metadataNumber(metadata, "spread_bps"))],
        ["Bid depth", formatNumber(metadataNumber(metadata, "bid_depth"))],
        ["Ask depth", formatNumber(metadataNumber(metadata, "ask_depth"))],
        ["Estimated slippage", formatNumber(metadataNumber(metadata, "estimated_slippage_bps"))],
        ["Orderbook freshness", formatNumber(metadataNumber(metadata, "orderbook_age_ms"))],
      ]}
    />
  );
}

function KeyValueGrid({ title, rows }: { title?: string; rows: Array<[string, string]> }) {
  return (
    <div className="space-y-3">
      {title ? <h4 className="text-sm font-semibold text-gray-800 dark:text-white/90">{title}</h4> : null}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {rows.map(([label, value]) => (
          <div key={label} className="rounded-xl border border-gray-200 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-950/40">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-gray-500">{label}</p>
            <p className="mt-1 truncate font-mono text-sm text-gray-900 dark:text-white/90">{value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function ErrorPanel({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-xl border border-error-200 bg-error-50 p-4 text-sm text-error-700 dark:border-error-900 dark:bg-error-950/20 dark:text-error-400">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span>{message}</span>
        <button type="button" className={UI_CLASSES.secondaryButton} onClick={onRetry}>
          Retry
        </button>
      </div>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return <div className="rounded-xl border border-dashed border-gray-300 p-6 text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">{message}</div>;
}

function decodePairQueryValue(value: string): string {
  try {
    return decodeURIComponent(value).trim();
  } catch {
    return value.trim();
  }
}

function parseDateInput(value: string): number | undefined {
  if (!value) return undefined;
  const millis = new Date(value).getTime();
  return Number.isFinite(millis) ? Math.floor(millis / 1000) : undefined;
}

function chartStart(chart: PairDecisionAuditChart | null): number | null {
  if (chart?.start_ts !== null && chart?.start_ts !== undefined) return chart.start_ts;
  return chartTimestampAt(chart, 0);
}

function chartEnd(chart: PairDecisionAuditChart | null): number | null {
  if (chart?.end_ts !== null && chart?.end_ts !== undefined) return chart.end_ts;
  return chartTimestampAt(chart, (chart?.zscore_series.length ?? 0) - 1);
}

function chartTimestampAt(chart: PairDecisionAuditChart | null, index: number): number | null {
  const value = chart?.zscore_series[index]?.timestamp;
  if (value === null || value === undefined) return null;
  const numeric = typeof value === "number" ? value : Number(value);
  if (Number.isFinite(numeric)) return numeric > 10_000_000_000 ? numeric / 1000 : numeric;
  const parsed = new Date(String(value)).getTime();
  return Number.isFinite(parsed) ? parsed / 1000 : null;
}

function statusToTone(status: string | null | undefined): "success" | "warn" | "error" | "neutral" {
  const normalized = String(status || "").toLowerCase();
  if (["stable", "tradable", "active"].includes(normalized)) return "success";
  if (["warning", "warn"].includes(normalized)) return "warn";
  if (["hospital", "graveyard", "error"].includes(normalized)) return "error";
  return "neutral";
}

function pnlTone(value: number | null | undefined): "teal" | "rose" | "sky" {
  if (value === null || value === undefined || Number.isNaN(value)) return "sky";
  return value >= 0 ? "teal" : "rose";
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

function formatTimestamp(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return "n/a";
  const numeric = typeof value === "number" ? value : Number(value);
  if (Number.isFinite(numeric)) {
    return new Date((numeric > 10_000_000_000 ? numeric : numeric * 1000)).toLocaleString();
  }
  const parsed = new Date(String(value));
  return Number.isNaN(parsed.getTime()) ? "n/a" : parsed.toLocaleString();
}

function errorMessage(err: unknown, fallback: string): string {
  if (isUnauthorizedError(err)) return "Unauthorized";
  return err instanceof Error ? err.message.replace(/^HTTP\s+\d+:\s*/i, "") || fallback : fallback;
}

function mostCommonBlockReason(counts: Record<string, number> | undefined): string | null {
  const entries = Object.entries(counts ?? {});
  if (!entries.length) return null;
  entries.sort((left, right) => right[1] - left[1]);
  return `${entries[0][0]} (${entries[0][1]})`;
}

function latestLiquidityMetadata(chart: PairDecisionAuditChart | null): Record<string, unknown> | null {
  const marker = [...(chart?.replay_markers ?? [])]
    .reverse()
    .find((item) => item.metadata && ["liquidity_score", "microstructure_risk", "spread_bps", "bid_depth", "ask_depth"].some((key) => item.metadata?.[key] !== undefined));
  return marker?.metadata ?? null;
}

function metadataNumber(metadata: Record<string, unknown>, key: string): number | null {
  const value = metadata[key];
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}
