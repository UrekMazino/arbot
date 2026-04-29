"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  AdminPairsHealth,
  ApiError,
  CointegratedPair,
  CointegratedPairDetail,
  CointegratedPairsResponse,
  PairSupplyStatus,
  UserRecord,
  getCointegratedPairDetail,
  getCointegratedPairs,
  getAdminPairsHealth,
  getMe,
  getPairSupplyStatus,
  isUnauthorizedError,
  removeCointegratedPair,
  setPairCuratorEnabled,
  switchAdminActivePair,
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
  hasAnyPermission,
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

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function cleanApiMessage(err: unknown, fallback: string): string {
  const raw = err instanceof Error ? err.message : fallback;
  return raw.replace(/^HTTP\s+\d+:\s*/i, "").trim() || fallback;
}

function activePairKey(activePair: Record<string, unknown> | null | undefined): string | null {
  const t1 = String(activePair?.ticker_1 || "").trim().toUpperCase();
  const t2 = String(activePair?.ticker_2 || "").trim().toUpperCase();
  if (!t1 || !t2) return null;
  return `${t1}/${t2}`;
}

function pairMatches(pair: CointegratedPair, query: string): boolean {
  if (!query.trim()) return true;
  const haystack = `${pair.sym_1} ${pair.sym_2} ${pair.pair}`.toLowerCase();
  return haystack.includes(query.trim().toLowerCase());
}

function sameStringArray(left?: string[], right?: string[]): boolean {
  const a = left || [];
  const b = right || [];
  if (a.length !== b.length) return false;
  for (let idx = 0; idx < a.length; idx += 1) {
    if (a[idx] !== b[idx]) return false;
  }
  return true;
}

function samePairSnapshot(left: CointegratedPair, right: CointegratedPair): boolean {
  return (
    left.id === right.id &&
    left.rank === right.rank &&
    left.sym_1 === right.sym_1 &&
    left.sym_2 === right.sym_2 &&
    left.pair === right.pair &&
    left.p_value === right.p_value &&
    left.adf_stat === right.adf_stat &&
    left.hedge_ratio === right.hedge_ratio &&
    left.zero_crossing === right.zero_crossing &&
    left.min_capital_per_leg === right.min_capital_per_leg &&
    left.min_equity_recommended === right.min_equity_recommended &&
    left.pair_liquidity_min === right.pair_liquidity_min &&
    left.pair_order_capacity_usdt === right.pair_order_capacity_usdt &&
    left.curator_score === right.curator_score &&
    left.curator_status === right.curator_status &&
    left.curator_recommendation === right.curator_recommendation &&
    left.curator_priority_rank === right.curator_priority_rank &&
    left.curator_checked_at === right.curator_checked_at &&
    sameStringArray(left.curator_reasons, right.curator_reasons)
  );
}

function mergeCatalogSnapshot(
  current: CointegratedPairsResponse | null,
  incoming: CointegratedPairsResponse,
): CointegratedPairsResponse {
  if (!current) return incoming;
  const currentPairs = new Map(current.pairs.map((pair) => [pair.id, pair]));
  const mergedPairs = incoming.pairs.map((pair) => {
    const existing = currentPairs.get(pair.id);
    if (!existing) return pair;
    return samePairSnapshot(existing, pair) ? existing : { ...existing, ...pair, curator_reasons: pair.curator_reasons || [] };
  });
  return { ...current, ...incoming, pairs: mergedPairs };
}

function pairButtonClass(active: boolean): string {
  return [
    "w-full rounded-2xl border p-3 text-left transition",
    active
      ? "border-brand-500 bg-brand-50 shadow-sm dark:border-brand-400 dark:bg-brand-950/30"
      : "border-gray-200 bg-white hover:border-brand-300 hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-900 dark:hover:border-brand-700 dark:hover:bg-gray-800/60",
  ].join(" ");
}

function listButtonClass(active: boolean): string {
  return [
    "grid w-full grid-cols-[minmax(13rem,1.2fr)_repeat(5,minmax(6rem,0.7fr))_minmax(5rem,0.4fr)] items-center gap-3 border-b border-gray-200 px-4 py-3 text-sm transition last:border-b-0 dark:border-gray-800",
    active
      ? "bg-brand-50 text-brand-700 dark:bg-brand-950/30 dark:text-brand-300"
      : "bg-white hover:bg-gray-50 dark:bg-gray-900 dark:hover:bg-gray-800/70",
  ].join(" ");
}

function pairActionButtonClass(tone: "switch" | "remove"): string {
  const palette =
    tone === "remove"
      ? "hover:border-error-300 hover:text-error-700 dark:hover:border-error-800 dark:hover:text-error-300"
      : "hover:border-brand-300 hover:text-brand-700 dark:hover:border-brand-700 dark:hover:text-brand-300";
  return [
    "inline-flex h-8 w-8 items-center justify-center rounded-lg border border-gray-300 bg-white text-gray-600 disabled:cursor-not-allowed disabled:opacity-45 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300",
    palette,
  ].join(" ");
}

function curatorTone(status: string | null | undefined): "success" | "warn" | "error" | "info" | "neutral" {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "healthy") return "success";
  if (normalized === "watch" || normalized === "stale") return "warn";
  if (normalized === "degraded" || normalized === "hospital_candidate") return "error";
  if (normalized === "hospital" || normalized === "graveyard") return "neutral";
  return "info";
}

function curatorLabel(pair: CointegratedPair): string {
  const status = String(pair.curator_status || "unscored").replace(/_/g, " ");
  const score = pair.curator_score;
  if (typeof score === "number" && Number.isFinite(score)) return `${Math.round(score)} ${status}`;
  return status;
}

function curatorReason(pair: CointegratedPair): string {
  const reasons = pair.curator_reasons || [];
  if (!reasons.length) return pair.curator_recommendation || "No curator notes yet";
  return reasons.slice(0, 2).map((reason) => reason.replace(/_/g, " ")).join(", ");
}

function pairMiniPillClass(tone: "success" | "warn" | "error" | "info" | "neutral"): string {
  const toneClasses = {
    success: "border-success-700/50 bg-success-950/35 text-success-300",
    warn: "border-warning-700/50 bg-warning-950/35 text-warning-300",
    error: "border-error-700/50 bg-error-950/35 text-error-300",
    info: "border-blue-light-700/50 bg-blue-light-950/35 text-blue-light-300",
    neutral: "border-gray-700 bg-gray-900/70 text-gray-300",
  };
  return `inline-flex items-center rounded-full border px-1.5 py-0.5 text-[9px] font-semibold uppercase leading-none tracking-[0.05em] ${toneClasses[tone]}`;
}

function SwitchIcon({ spinning = false }: { spinning?: boolean }) {
  return (
    <svg
      aria-hidden="true"
      className={spinning ? "h-4 w-4 animate-spin" : "h-4 w-4"}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M4 6h9.5a2.5 2.5 0 0 1 0 5H7" />
      <path d="M7 3 4 6l3 3" />
      <path d="M16 14H6.5a2.5 2.5 0 0 1 0-5H13" />
      <path d="m13 17 3-3-3-3" />
    </svg>
  );
}

function RemoveIcon({ spinning = false }: { spinning?: boolean }) {
  if (spinning) {
    return (
      <svg
        aria-hidden="true"
        className="h-4 w-4 animate-spin"
        viewBox="0 0 20 20"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      >
        <path d="M10 3.5a6.5 6.5 0 1 1-6.1 4.3" />
      </svg>
    );
  }
  return (
    <svg
      aria-hidden="true"
      className="h-4 w-4"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
    >
      <path d="M5 5l10 10" />
      <path d="M15 5 5 15" />
    </svg>
  );
}

function FullscreenIcon() {
  return (
    <svg
      aria-hidden="true"
      className="h-4 w-4"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M7.5 3.5h-4v4" />
      <path d="M3.5 3.5 8 8" />
      <path d="M12.5 3.5h4v4" />
      <path d="M16.5 3.5 12 8" />
      <path d="M7.5 16.5h-4v-4" />
      <path d="M3.5 16.5 8 12" />
      <path d="M12.5 16.5h4v-4" />
      <path d="M16.5 16.5 12 12" />
    </svg>
  );
}

function ChartEmpty({ message }: { message: string }) {
  return <p className="py-20 text-center text-sm text-gray-500 dark:text-gray-400">{message}</p>;
}

function PairUniverseCharts({
  chartData,
  fullscreen = false,
  selectedPair,
}: {
  chartData: CointegratedPairDetail["points"];
  fullscreen?: boolean;
  selectedPair: CointegratedPair;
}) {
  const priceHeight = fullscreen ? 360 : 280;
  const spreadHeight = fullscreen ? 420 : 300;
  const headingClass = fullscreen
    ? "mb-3 text-sm font-semibold text-white/90"
    : "mb-2 text-sm font-semibold text-gray-800 dark:text-white/90";
  const lineAnimation = {
    isAnimationActive: true,
    animationDuration: fullscreen ? 850 : 700,
    animationEasing: "ease-in-out" as const,
  };

  return (
    <div className={fullscreen ? "space-y-10" : "space-y-8"}>
      <div>
        <h4 className={headingClass}>Normalized Price Path</h4>
        <ResponsiveContainer width="100%" height={priceHeight}>
          <LineChart data={chartData}>
            <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#263244" />
            <XAxis dataKey="ts" tickFormatter={fmtTick} tickLine={false} axisLine={false} fontSize={11} />
            <YAxis tickLine={false} axisLine={false} fontSize={11} domain={["auto", "auto"]} />
            <Tooltip labelFormatter={(value) => fmtDate(String(value))} />
            <Legend />
            <Line type="monotone" dataKey="price_1_norm" name={selectedPair.sym_1} stroke="#2563eb" strokeWidth={2.5} dot={false} {...lineAnimation} />
            <Line type="monotone" dataKey="price_2_norm" name={selectedPair.sym_2} stroke="#14b8a6" strokeWidth={2.5} dot={false} {...lineAnimation} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div>
        <h4 className={headingClass}>Spread Z-Score</h4>
        <ResponsiveContainer width="100%" height={spreadHeight}>
          <LineChart data={chartData}>
            <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="#263244" />
            <XAxis dataKey="ts" tickFormatter={fmtTick} tickLine={false} axisLine={false} fontSize={11} />
            <YAxis yAxisId="z" tickLine={false} axisLine={false} fontSize={11} domain={["auto", "auto"]} />
            <YAxis yAxisId="spread" orientation="right" tickLine={false} axisLine={false} fontSize={11} domain={["auto", "auto"]} />
            <Tooltip labelFormatter={(value) => fmtDate(String(value))} />
            <Legend />
            <Line yAxisId="spread" type="monotone" dataKey="spread" name="Spread" stroke="#94a3b8" strokeWidth={1.6} dot={false} {...lineAnimation} />
            <Line
              yAxisId="spread"
              type="monotone"
              dataKey="spread_mean"
              name="Spread mean"
              stroke="#64748b"
              strokeDasharray="3 6"
              strokeWidth={1}
              dot={false}
              {...lineAnimation}
            />
            <Line
              yAxisId="spread"
              type="linear"
              dataKey="crossing_spread"
              name="Chart crossing"
              legendType="circle"
              stroke="transparent"
              strokeWidth={0}
              connectNulls={false}
              dot={{
                r: fullscreen ? 5 : 4,
                fill: "#facc15",
                stroke: "#0f172a",
                strokeWidth: 1.8,
              }}
              activeDot={{
                r: fullscreen ? 7 : 6,
                fill: "#facc15",
                stroke: "#fef3c7",
                strokeWidth: 2,
              }}
              isAnimationActive={false}
            />
            <Line yAxisId="z" type="monotone" dataKey="zscore" name="Z-score" stroke="#f97316" strokeWidth={2.6} dot={false} {...lineAnimation} />
            <Line yAxisId="z" type="monotone" dataKey="z_upper" name="+2" stroke="#ef4444" strokeDasharray="5 5" dot={false} {...lineAnimation} />
            <Line yAxisId="z" type="monotone" dataKey="z_lower" name="-2" stroke="#22c55e" strokeDasharray="5 5" dot={false} {...lineAnimation} />
            <Line yAxisId="z" type="monotone" dataKey="z_mid" name="0" stroke="#64748b" strokeDasharray="4 6" dot={false} {...lineAnimation} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default function CointegratedPairPage() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [pairsLoading, setPairsLoading] = useState(false);
  const [pairsRefreshing, setPairsRefreshing] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [catalog, setCatalog] = useState<CointegratedPairsResponse | null>(null);
  const [pairsHealth, setPairsHealth] = useState<AdminPairsHealth | null>(null);
  const [supplyStatus, setSupplyStatus] = useState<PairSupplyStatus | null>(null);
  const [supplyBusy, setSupplyBusy] = useState(false);
  const [doctorBusy, setDoctorBusy] = useState(false);
  const [switchBusyPairId, setSwitchBusyPairId] = useState<string | null>(null);
  const [removeBusyPairId, setRemoveBusyPairId] = useState<string | null>(null);
  const [switchModal, setSwitchModal] = useState<{
    title: string;
    message: string;
    pair?: CointegratedPair;
    blockers?: string[];
    forceAvailable?: boolean;
  } | null>(null);
  const [selectedPair, setSelectedPair] = useState<CointegratedPair | null>(null);
  const [detail, setDetail] = useState<CointegratedPairDetail | null>(null);
  const [graphFullscreen, setGraphFullscreen] = useState(false);
  const [showGraph, setShowGraph] = useState(true);
  const [query, setQuery] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const refreshInFlightRef = useRef(false);
  const detailRefreshInFlightRef = useRef(false);
  const detailRequestIdRef = useRef(0);
  const foregroundDetailRequestIdRef = useRef(0);

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
        const [data, supply, health] = await Promise.all([
          getCointegratedPairs(500),
          getPairSupplyStatus().catch(() => null),
          getAdminPairsHealth().catch(() => null),
        ]);
        if (cancelled) return;
        setCatalog(data);
        setSupplyStatus(supply);
        setPairsHealth(health);
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
    if (!graphFullscreen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setGraphFullscreen(false);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [graphFullscreen]);

  const filteredPairs = useMemo(
    () => (catalog?.pairs || []).filter((pair) => pairMatches(pair, query)),
    [catalog, query],
  );

  const activeHref = "/admin/dashboard/cointegrated-pair";
  const status = catalog?.status;
  const preservedExisting = statusBool(status, "preserved_existing");
  const latestAttemptRows = statusNumber(status, "latest_attempt_rows");
  const canonicalRows = statusNumber(status, "canonical_rows");
  const usableCrossingPairs = statusNumber(status, "usable_pairs_with_crossings");
  const preFilterCrossingPairs = statusNumber(status, "pre_filter_pairs_with_crossings");
  const latestAttemptHint =
    usableCrossingPairs !== null && preFilterCrossingPairs !== null
      ? `${usableCrossingPairs} usable crossing pairs from ${preFilterCrossingPairs} pre-filter candidates`
      : preservedExisting
        ? "Empty scan preserved last-good CSV"
        : "Latest scan became canonical";
  const curatorCounts = catalog?.curator?.status_counts || {};
  const curatorHealthyCount = Number(curatorCounts.healthy || 0);
  const curatorWatchCount = Number(curatorCounts.watch || 0) + Number(curatorCounts.degraded || 0) + Number(curatorCounts.hospital_candidate || 0);
  const chartData = detail?.points || [];
  const canManageSupply = hasAnyPermission(user, ["manage_pair_supply", "manage_bot"]);
  const canSwitchPair = hasAnyPermission(user, ["switch_active_pair", "manage_bot"]);
  const canForceSwitchPair = hasAnyPermission(user, ["manage_bot"]);
  const pairDoctorEnabled = catalog?.curator?.enabled ?? false;
  const pairDoctorRefreshSeconds = Math.max(5, Number(catalog?.pair_doctor_ui_refresh_seconds || 20) || 20);
  const selectedSym1 = selectedPair?.sym_1 || "";
  const selectedSym2 = selectedPair?.sym_2 || "";
  const activeKey = activePairKey(pairsHealth?.active_pair);
  const supplyTargetRunning = supplyStatus?.desired_running ?? supplyStatus?.running ?? false;
  const supplyTransitioning = Boolean(
    supplyStatus && supplyStatus.desired_running !== undefined && supplyStatus.desired_running !== supplyStatus.running,
  );
  const supplyButtonLabel =
    supplyBusy || supplyTransitioning
      ? supplyTargetRunning
        ? "Starting..."
        : "Stopping..."
      : supplyTargetRunning
        ? "Stop Supply"
        : "Start Supply";

  const loadPairDetail = useCallback(async (sym1: string, sym2: string, options: { background?: boolean } = {}) => {
    const background = Boolean(options.background);
    if (background && detailRefreshInFlightRef.current) return;
    const requestId = detailRequestIdRef.current + 1;
    detailRequestIdRef.current = requestId;
    if (background) {
      detailRefreshInFlightRef.current = true;
    } else {
      foregroundDetailRequestIdRef.current = requestId;
      setDetailLoading(true);
      setError(null);
    }
    try {
      const data = await getCointegratedPairDetail(sym1, sym2, 720);
      if (detailRequestIdRef.current !== requestId) return;
      setDetail(data);
    } catch (err) {
      if (detailRequestIdRef.current !== requestId) return;
      if (!background) {
        setError(isUnauthorizedError(err) ? "Unauthorized" : "Failed to load selected pair graph");
        setDetail(null);
      }
    } finally {
      if (background) {
        detailRefreshInFlightRef.current = false;
      } else if (foregroundDetailRequestIdRef.current === requestId) {
        setDetailLoading(false);
      }
    }
  }, []);

  const refreshCatalog = useCallback(async (options: { removedPairId?: string; background?: boolean; refreshDetail?: boolean } = {}) => {
    if (refreshInFlightRef.current) return;
    const background = Boolean(options.background);
    refreshInFlightRef.current = true;
    if (!background) {
      setPairsRefreshing(true);
      setError(null);
    }
    try {
      const [data, supply, health] = await Promise.all([
        getCointegratedPairs(500),
        getPairSupplyStatus().catch(() => null),
        getAdminPairsHealth().catch(() => null),
      ]);
      setCatalog((current) => mergeCatalogSnapshot(current, data));
      setSupplyStatus(supply);
      setPairsHealth(health);
      let nextSelectedPair: CointegratedPair | null = null;
      setSelectedPair((current) => {
        if (!current || current.id === options.removedPairId) return data.pairs[0] || null;
        nextSelectedPair = data.pairs.find((pair) => pair.id === current.id) || data.pairs[0] || null;
        return nextSelectedPair;
      });
      if (!nextSelectedPair && data.pairs.length) {
        nextSelectedPair = data.pairs[0] || null;
      }
      if (nextSelectedPair) {
        setDetail((current) =>
          current && current.pair.id === nextSelectedPair?.id
            ? { ...current, pair: nextSelectedPair }
            : current,
        );
      }
      if (options.refreshDetail && nextSelectedPair) {
        void loadPairDetail(nextSelectedPair.sym_1, nextSelectedPair.sym_2, { background });
      }
    } catch (err) {
      if (!background || !catalog) {
        setError(isUnauthorizedError(err) ? "Unauthorized" : "Failed to refresh cointegrated pairs");
      }
    } finally {
      refreshInFlightRef.current = false;
      if (!background) {
        setPairsRefreshing(false);
      }
    }
  }, [catalog, loadPairDetail]);

  useEffect(() => {
    if (!selectedSym1 || !selectedSym2) {
      setDetail(null);
      setGraphFullscreen(false);
      return;
    }
    void loadPairDetail(selectedSym1, selectedSym2);
  }, [loadPairDetail, selectedSym1, selectedSym2]);

  useEffect(() => {
    if (!pairDoctorEnabled) return;
    const intervalId = window.setInterval(() => {
      if (document.visibilityState === "hidden") return;
      if (doctorBusy || supplyBusy || switchBusyPairId || removeBusyPairId) return;
      void refreshCatalog({ background: true, refreshDetail: true });
    }, pairDoctorRefreshSeconds * 1000);
    return () => window.clearInterval(intervalId);
  }, [doctorBusy, pairDoctorEnabled, pairDoctorRefreshSeconds, refreshCatalog, removeBusyPairId, supplyBusy, switchBusyPairId]);

  if (loading) {
    return <div className="p-8 text-center text-gray-500">Loading...</div>;
  }

  async function togglePairSupply() {
    if (!canManageSupply) return;
    setSupplyBusy(true);
    setError(null);
    try {
      const expectedRunning = !supplyTargetRunning;
      const next = supplyTargetRunning ? await stopPairSupply() : await startPairSupply();
      setSupplyStatus(next);
      for (let attempt = 0; attempt < 12; attempt += 1) {
        await sleep(attempt === 0 ? 400 : 750);
        const latest = await getPairSupplyStatus();
        setSupplyStatus(latest);
        const latestTarget = latest.desired_running ?? latest.running;
        if (latestTarget === expectedRunning && latest.running === expectedRunning) break;
      }
    } catch (err) {
      setError(isUnauthorizedError(err) ? "Unauthorized" : "Failed to update pair supply process");
    } finally {
      setSupplyBusy(false);
    }
  }

  async function togglePairDoctor(enabled: boolean) {
    if (!canManageSupply) return;
    setDoctorBusy(true);
    setError(null);
    try {
      await setPairCuratorEnabled(enabled);
      await refreshCatalog({ refreshDetail: true });
    } catch (err) {
      setError(isUnauthorizedError(err) ? "Unauthorized" : "Failed to update Pair Doctor");
    } finally {
      setDoctorBusy(false);
    }
  }

  async function handleRemovePair(pair: CointegratedPair) {
    if (!canManageSupply || removeBusyPairId || switchBusyPairId || activeKey === pair.pair) return;
    const confirmed = window.confirm(
      `Remove ${pair.pair} from Pair Universe? This will not add it to hospital or graveyard.`,
    );
    if (!confirmed) return;

    setRemoveBusyPairId(pair.id);
    setError(null);
    try {
      await removeCointegratedPair(pair.sym_1, pair.sym_2);
      await refreshCatalog({ removedPairId: pair.id, refreshDetail: true });
    } catch (err) {
      setError(isUnauthorizedError(err) ? "Unauthorized" : cleanApiMessage(err, "Failed to remove pair"));
    } finally {
      setRemoveBusyPairId(null);
    }
  }

  async function handleManualSwitch(pair: CointegratedPair, force: boolean = false) {
    if (!canSwitchPair || switchBusyPairId) return;
    setSwitchBusyPairId(pair.id);
    setError(null);
    try {
      const result = await switchAdminActivePair(pair.sym_1, pair.sym_2, force);
      const [health] = await Promise.all([
        getAdminPairsHealth().catch(() => null),
        sleep(result.pending ? 1200 : 0),
      ]);
      if (health) setPairsHealth(health);
      if (result.pending) {
        void sleep(2500).then(async () => {
          const latest = await getAdminPairsHealth().catch(() => null);
          if (latest) setPairsHealth(latest);
        });
      }
    } catch (err) {
      const payload = err instanceof ApiError && err.payload && typeof err.payload === "object"
        ? err.payload as { blockers?: string[]; force_available?: boolean }
        : null;
      setSwitchModal({
        title: "Manual switch blocked",
        message: cleanApiMessage(
          err,
          "Manual pair switch is not allowed while there is an active position or order.",
        ),
        pair,
        blockers: payload?.blockers,
        forceAvailable: canForceSwitchPair && (payload?.force_available ?? false),
      });
    } finally {
      setSwitchBusyPairId(null);
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
      {switchModal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-950/55 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-warning-200 bg-white p-5 shadow-2xl dark:border-warning-900 dark:bg-gray-900">
            <div className="flex items-start gap-3">
              <div className="mt-0.5 rounded-full bg-warning-50 p-2 text-warning-700 dark:bg-warning-950/30 dark:text-warning-300">
                <SwitchIcon />
              </div>
              <div>
                <h2 className="text-base font-semibold text-gray-950 dark:text-white">{switchModal.title}</h2>
                <p className="mt-2 text-sm leading-6 text-gray-600 dark:text-gray-300">{switchModal.message}</p>
                {switchModal.blockers && switchModal.blockers.length > 0 && (
                  <ul className="mt-2 list-disc pl-4 text-xs text-gray-500 dark:text-gray-400">
                    {switchModal.blockers.map((blocker, idx) => (
                      <li key={idx}>{blocker}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              {switchModal.forceAvailable && switchModal.pair ? (
                <>
                  <button
                    type="button"
                    className="inline-flex items-center rounded-xl border border-warning-200 bg-warning-50 px-3 py-2 text-sm font-medium text-warning-700 hover:bg-warning-100 dark:border-warning-800 dark:bg-warning-950/30 dark:text-warning-300 dark:hover:bg-warning-950/50"
                    onClick={() => {
                      const pair = switchModal.pair;
                      setSwitchModal(null);
                      if (pair) {
                        handleManualSwitch(pair, true);
                      }
                    }}
                  >
                    Force Switch
                  </button>
                  <button
                    type="button"
                    className={UI_CLASSES.primaryButton}
                    onClick={() => setSwitchModal(null)}
                  >
                    Cancel
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className={UI_CLASSES.primaryButton}
                  onClick={() => setSwitchModal(null)}
                >
                  OK
                </button>
              )}
            </div>
          </div>
        </div>
      ) : null}
      {graphFullscreen && selectedPair && chartData.length ? (
        <div className="fixed inset-0 z-[60] bg-gray-950/90 p-3 backdrop-blur-sm sm:p-5">
          <div className="flex h-full flex-col overflow-hidden rounded-3xl border border-white/10 bg-gray-950/95 shadow-2xl">
            <div className="flex items-center justify-between gap-4 border-b border-white/10 px-4 py-3 sm:px-5">
              <div className="min-w-0">
                <p className="font-mono text-sm font-semibold text-white sm:text-base">{selectedPair.pair}</p>
                <p className="mt-1 text-xs text-gray-400">Pair Universe fullscreen chart</p>
              </div>
              <button
                type="button"
                className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/15 bg-white/10 text-white hover:bg-white/15"
                onClick={() => setGraphFullscreen(false)}
                aria-label="Close fullscreen pair graph"
                title="Close fullscreen"
              >
                <RemoveIcon />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-4 custom-scrollbar sm:p-6">
              <PairUniverseCharts chartData={chartData} selectedPair={selectedPair} fullscreen />
            </div>
          </div>
        </div>
      ) : null}
      <div className="space-y-6">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
          <MetricCard
            label="Canonical Pairs"
            value={String(catalog?.pair_count ?? canonicalRows ?? 0)}
            hint={`CSV updated ${fmtDate(catalog?.updated_at)}`}
            tone="sky"
          />
          <MetricCard
            label="Latest Attempt"
            value={latestAttemptRows === null ? "n/a" : String(latestAttemptRows)}
            hint={latestAttemptHint}
            tone={preservedExisting ? "amber" : "teal"}
          />
          <MetricCard
            label="Pair Supply"
            value={supplyStatus?.running ? "Running" : "Stopped"}
            hint={supplyStatus?.running ? `PID ${supplyStatus.pid}` : supplyStatus?.detail || "Independent scanner"}
            tone={supplyStatus?.running ? "teal" : "amber"}
          />
          <MetricCard
            label="Curator"
            value={!pairDoctorEnabled ? "Disabled" : catalog?.curator?.running ? "Running" : catalog?.curator_updated_at ? "Scored" : "Pending"}
            hint={
              !pairDoctorEnabled
                ? "Pair Doctor unchecked"
                : catalog?.curator_updated_at
                ? `${curatorHealthyCount} healthy, ${curatorWatchCount} watch`
                : "Waiting for first advisory scan"
            }
            tone={!pairDoctorEnabled ? "violet" : curatorWatchCount > 0 ? "amber" : catalog?.curator_updated_at ? "teal" : "violet"}
          />
          <MetricCard
            label="Selected Z"
            value={fmtNumber(detail?.stats.zscore_current, 3)}
            hint={selectedPair?.pair || "No pair selected"}
            tone={Math.abs(detail?.stats.zscore_current || 0) >= 2 ? "amber" : "violet"}
          />
        </div>

        <div
          className={[
            "grid min-h-0 grid-cols-1 gap-6",
            showGraph ? "xl:grid-cols-[minmax(22rem,0.9fr)_minmax(0,1.6fr)]" : "xl:grid-cols-1",
          ].join(" ")}
        >
          <PanelCard
            title="Pair Universe"
            subtitle="Co-integrated pairs reserved"
            titleRight={
              <div className="ml-auto flex max-w-full flex-col items-end gap-1.5">
                <div className="flex max-w-full flex-wrap items-center justify-end gap-1.5 sm:flex-nowrap">
                  <span
                    className={[
                      "inline-flex items-center rounded-full border px-1.5 py-0.5 text-[9px] font-semibold uppercase leading-none tracking-[0.06em]",
                      preservedExisting
                        ? "border-warning-200 bg-warning-50 text-warning-700 dark:border-warning-900 dark:bg-warning-950/20 dark:text-warning-400"
                        : "border-success-200 bg-success-50 text-success-700 dark:border-success-900 dark:bg-success-950/20 dark:text-success-400",
                    ].join(" ")}
                  >
                    {preservedExisting ? "Last-good preserved" : "Fresh"}
                  </span>
                  <button
                    type="button"
                    className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-gray-300 bg-white text-gray-600 hover:bg-gray-50 disabled:opacity-70 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                    onClick={() => {
                      void refreshCatalog({ refreshDetail: true });
                    }}
                    disabled={pairsLoading || pairsRefreshing}
                    aria-label="Refresh pair universe"
                    title="Refresh pair universe"
                  >
                    <svg
                      aria-hidden="true"
                      className={pairsLoading || pairsRefreshing ? "h-3.5 w-3.5 animate-spin" : "h-3.5 w-3.5"}
                      viewBox="0 0 20 20"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M16.5 10a6.5 6.5 0 1 1-1.9-4.6" />
                      <path d="M16.5 4.5v4h-4" />
                    </svg>
                  </button>
                  <button
                    type="button"
                    className="inline-flex h-8 items-center rounded-lg border border-gray-300 bg-white px-2.5 text-[11px] font-semibold text-gray-600 hover:bg-gray-50 disabled:opacity-70 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                    onClick={() => {
                      if (showGraph) setGraphFullscreen(false);
                      setShowGraph(!showGraph);
                    }}
                    aria-label={showGraph ? "Hide pair graph" : "Show pair graph"}
                    title={showGraph ? "Hide graph and widen Pair Universe" : "Show graph"}
                  >
                    {showGraph ? "Hide Graph" : "Show Graph"}
                  </button>
                  <button
                    type="button"
                    className={
                      supplyTargetRunning
                        ? "inline-flex h-10 min-w-[8.5rem] shrink-0 items-center justify-center whitespace-nowrap rounded-xl border border-error-300 bg-error-50 px-4 text-sm font-semibold leading-none text-error-700 hover:bg-error-100 disabled:opacity-70 dark:border-error-900 dark:bg-error-950/20 dark:text-error-400"
                        : "inline-flex h-10 min-w-[8.5rem] shrink-0 items-center justify-center whitespace-nowrap rounded-xl bg-brand-500 px-4 text-sm font-semibold leading-none text-white hover:bg-brand-600 disabled:opacity-70"
                    }
                    onClick={togglePairSupply}
                    disabled={supplyBusy || !canManageSupply}
                    title={!canManageSupply ? "Pair supply permission required" : undefined}
                  >
                    {supplyButtonLabel}
                  </button>
                </div>
                <label className="inline-flex cursor-pointer select-none items-center justify-end gap-1.5 text-[11px] font-medium leading-none text-gray-500 disabled:cursor-not-allowed dark:text-gray-400">
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5 rounded border-gray-300 text-brand-600 focus:ring-brand-500 disabled:cursor-not-allowed disabled:opacity-60"
                    checked={pairDoctorEnabled}
                    disabled={doctorBusy || !canManageSupply}
                    onChange={(event) => {
                      void togglePairDoctor(event.target.checked);
                    }}
                  />
                  <span>Pair Doctor</span>
                </label>
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

            {pairsLoading && !catalog ? (
              <ChartEmpty message="Loading pair universe..." />
            ) : error && !catalog ? (
              <ChartEmpty message={error} />
            ) : !filteredPairs.length ? (
              <ChartEmpty message="No pairs match the current search." />
            ) : viewMode === "grid" ? (
              <div
                className="grid max-h-[38rem] gap-2.5 overflow-auto pr-1 custom-scrollbar"
                style={{
                  gridTemplateColumns: `repeat(auto-fit, minmax(min(100%, ${showGraph ? "18rem" : "15.75rem"}), 1fr))`,
                }}
              >
                {filteredPairs.map((pair) => {
                  const isActive = activeKey === pair.pair;
                  const isSwitching = switchBusyPairId === pair.id;
                  const isRemoving = removeBusyPairId === pair.id;
                  return (
                    <div key={pair.id} className={pairButtonClass(selectedPair?.id === pair.id)}>
                      <div className="space-y-2.5">
                        <button
                          type="button"
                          className="block w-full min-w-0 text-left"
                          onClick={() => setSelectedPair(pair)}
                        >
                          <p className="break-words font-mono text-[0.78rem] font-semibold leading-4 text-gray-900 dark:text-white">{pair.pair}</p>
                          <p className="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">Rank #{pair.rank}</p>
                        </button>
                        <div className="flex items-center justify-between gap-1.5">
                          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                            <span className={pairMiniPillClass(isActive ? "success" : "info")}>
                              {isActive ? "Active" : `${pair.zero_crossing ?? 0} crosses`}
                            </span>
                            {pairDoctorEnabled ? (
                              <span className={pairMiniPillClass(curatorTone(pair.curator_status))}>{curatorLabel(pair)}</span>
                            ) : null}
                          </div>
                          <div className="flex shrink-0 items-center gap-1.5">
                            <button
                              type="button"
                              className={pairActionButtonClass("switch")}
                              onClick={() => handleManualSwitch(pair)}
                              disabled={!canSwitchPair || isActive || Boolean(switchBusyPairId)}
                              aria-label={`Switch active pair to ${pair.pair}`}
                              title={
                                !canSwitchPair
                                  ? "Switch active pair permission required"
                                  : isActive
                                    ? "This pair is already active"
                                    : `Switch active pair to ${pair.pair}`
                              }
                            >
                              <SwitchIcon spinning={isSwitching} />
                            </button>
                            <button
                              type="button"
                              className={pairActionButtonClass("remove")}
                              onClick={() => handleRemovePair(pair)}
                              disabled={!canManageSupply || isActive || Boolean(removeBusyPairId) || Boolean(switchBusyPairId)}
                              aria-label={`Remove ${pair.pair} from Pair Universe`}
                              title={
                                !canManageSupply
                                  ? "Pair supply permission required"
                                  : isActive
                                    ? "Switch away from the active pair before removing it"
                                    : `Remove ${pair.pair} from Pair Universe`
                              }
                            >
                              <RemoveIcon spinning={isRemoving} />
                            </button>
                          </div>
                        </div>
                      </div>
                      <button
                        type="button"
                        className="mt-3 grid w-full grid-cols-2 gap-x-3 gap-y-2 text-left text-[11px] leading-4"
                        onClick={() => setSelectedPair(pair)}
                      >
                        <span className="text-gray-500">p-value <b className="font-mono text-gray-900 dark:text-white">{fmtNumber(pair.p_value, 5)}</b></span>
                        <span className="text-gray-500">hedge <b className="font-mono text-gray-900 dark:text-white">{fmtNumber(pair.hedge_ratio, 3)}</b></span>
                        <span className="text-gray-500">liq <b className="font-mono text-gray-900 dark:text-white">{fmtCompact(pair.pair_liquidity_min)}</b></span>
                        <span className="text-gray-500">cap <b className="font-mono text-gray-900 dark:text-white">{fmtCompact(pair.pair_order_capacity_usdt)}</b></span>
                        {pairDoctorEnabled ? (
                          <span className="col-span-2 truncate text-gray-500">
                            doctor <b className="font-mono text-gray-900 dark:text-white">{curatorReason(pair)}</b>
                          </span>
                        ) : null}
                      </button>
                    </div>
                  );
                })}
              </div>
            ) : (
              <TableFrame maxHeightClass="max-h-[38rem]">
                <div className="min-w-[780px]">
                  <div className="grid grid-cols-[minmax(13rem,1.2fr)_repeat(5,minmax(6rem,0.7fr))_minmax(5rem,0.4fr)] gap-3 border-b border-gray-200 bg-gray-50 px-4 py-3 text-xs font-semibold uppercase tracking-[0.12em] text-gray-500 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-400">
                    <span>Pair</span>
                    <span>Crosses</span>
                    <span>p-value</span>
                    <span>Hedge</span>
                    <span>Liquidity</span>
                    <span>Capacity</span>
                    <span className="text-right">Actions</span>
                  </div>
                  {filteredPairs.map((pair) => {
                    const isActive = activeKey === pair.pair;
                    const isSwitching = switchBusyPairId === pair.id;
                    const isRemoving = removeBusyPairId === pair.id;
                    return (
                      <div
                        key={pair.id}
                        role="button"
                        tabIndex={0}
                        className={listButtonClass(selectedPair?.id === pair.id)}
                        onClick={() => setSelectedPair(pair)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") setSelectedPair(pair);
                        }}
                      >
                        <span className="min-w-0">
                          <span className="block truncate font-mono font-semibold">{pair.pair}</span>
                          {pairDoctorEnabled ? (
                            <span className="mt-1 block truncate text-[11px] text-gray-500 dark:text-gray-400">
                              Pair Doctor: {curatorLabel(pair)} - {curatorReason(pair)}
                            </span>
                          ) : null}
                        </span>
                        <span>{isActive ? "Active" : pair.zero_crossing ?? 0}</span>
                        <span>{fmtNumber(pair.p_value, 5)}</span>
                        <span>{fmtNumber(pair.hedge_ratio, 3)}</span>
                        <span>{fmtCompact(pair.pair_liquidity_min)}</span>
                        <span>{fmtCompact(pair.pair_order_capacity_usdt)}</span>
                        <span className="flex justify-end gap-2">
                          <button
                            type="button"
                            className={pairActionButtonClass("switch")}
                            onClick={(event) => {
                              event.stopPropagation();
                              handleManualSwitch(pair);
                            }}
                            disabled={!canSwitchPair || isActive || Boolean(switchBusyPairId)}
                            aria-label={`Switch active pair to ${pair.pair}`}
                            title={
                              !canSwitchPair
                                ? "Switch active pair permission required"
                                : isActive
                                  ? "This pair is already active"
                                  : `Switch active pair to ${pair.pair}`
                            }
                          >
                            <SwitchIcon spinning={isSwitching} />
                          </button>
                          <button
                            type="button"
                            className={pairActionButtonClass("remove")}
                            onClick={(event) => {
                              event.stopPropagation();
                              handleRemovePair(pair);
                            }}
                            disabled={!canManageSupply || isActive || Boolean(removeBusyPairId) || Boolean(switchBusyPairId)}
                            aria-label={`Remove ${pair.pair} from Pair Universe`}
                            title={
                              !canManageSupply
                                ? "Pair supply permission required"
                                : isActive
                                  ? "Switch away from the active pair before removing it"
                                  : `Remove ${pair.pair} from Pair Universe`
                            }
                          >
                            <RemoveIcon spinning={isRemoving} />
                          </button>
                        </span>
                      </div>
                    );
                  })}
                </div>
              </TableFrame>
            )}
          </PanelCard>

          {showGraph ? (
          <div className="space-y-6">
            <PanelCard
              title={selectedPair ? selectedPair.pair : "Pair Detail"}
              subtitle="Normalized prices, spread, and z-score computed from Strategy price history."
              titleRight={
                detailLoading ? (
                  <StatusPill label="Loading" tone="neutral" />
                ) : (
                  <div className="flex items-center gap-2">
                    {selectedPair && chartData.length ? (
                      <button
                        type="button"
                        className="inline-flex items-center gap-1.5 rounded-xl border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-gray-700 shadow-sm hover:border-brand-300 hover:text-brand-700 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-300 dark:hover:border-brand-700 dark:hover:text-brand-300"
                        onClick={() => setGraphFullscreen(true)}
                        aria-label="Open pair graph fullscreen"
                        title="Open graph fullscreen"
                      >
                        <FullscreenIcon />
                        <span className="hidden sm:inline">Full screen</span>
                      </button>
                    ) : null}
                    <StatusPill label="Chart" tone="success" />
                  </div>
                )
              }
            >
              {detailLoading ? (
                <ChartEmpty message="Loading pair graph..." />
              ) : !selectedPair ? (
                <ChartEmpty message="Select a pair to view cointegration graphs." />
              ) : !chartData.length ? (
                <ChartEmpty message="No chart data available for this pair." />
              ) : (
                <PairUniverseCharts chartData={chartData} selectedPair={selectedPair} />
              )}
            </PanelCard>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <MetricCard label="p-value" value={fmtNumber(detail?.pair.p_value, 5)} hint="Lower is stronger" tone="teal" />
              <MetricCard
                label="Chart Crossings"
                value={String(detail?.stats.zero_crossing_window ?? detail?.pair.zero_crossing ?? "n/a")}
                hint="Displayed window, noise-filtered"
                tone="sky"
              />
              <MetricCard label="Spread Std" value={fmtNumber(detail?.stats.spread_std, 5)} hint="Latest chart window" tone="violet" />
            </div>
          </div>
          ) : null}
        </div>
      </div>
    </DashboardShell>
  );
}
