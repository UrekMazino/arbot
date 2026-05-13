"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type {
  ChartAuditActualMarker,
  ChartAuditReplayMarker,
  PairDecisionAuditChart,
} from "../../lib/api";

type EntryMarker = ChartAuditActualMarker | ChartAuditReplayMarker;

type ChartPoint = {
  timestamp: number;
  timeLabel: string;
  zscore: number | null;
  spread: number | null;
};

type MarkerPoint = {
  timestamp: number;
  timeLabel: string;
  y: number;
  marker: EntryMarker | Record<string, unknown>;
  markerKind: "actual" | "replay" | "statistical";
  markerType: string;
};

export function PairZScoreChart({
  chart,
  selectedEntryId,
  onSelectEntryMarker,
}: {
  chart: PairDecisionAuditChart | null;
  selectedEntryId?: string | null;
  onSelectEntryMarker?: (marker: EntryMarker) => void;
}) {
  const rows = normalizeSeries(chart);
  const statistical = normalizeStatisticalMarkers(chart);
  const replayEntries = normalizeReplayMarkers(chart, "replay_entry_candidate");
  const replayExits = normalizeReplayMarkers(chart, "replay_exit_candidate");
  const replayBlocked = normalizeReplayMarkers(chart, "replay_blocked_signal");
  const actualEntries = normalizeActualMarkers(chart, "actual_entry");
  const actualExits = normalizeActualMarkers(chart, "actual_exit");
  const actualOther = normalizeActualMarkers(chart, null).filter(
    (point) => point.markerType !== "actual_entry" && point.markerType !== "actual_exit",
  );

  if (!chart || rows.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-gray-300 p-6 text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">
        No chart audit data available for this pair/time range.
      </div>
    );
  }

  return (
    <div className="h-[420px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 10, right: 24, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.25)" />
          <XAxis
            dataKey="timestamp"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(value) => formatTimestamp(Number(value))}
            minTickGap={36}
            stroke="#94a3b8"
          />
          <YAxis stroke="#94a3b8" width={48} />
          <Tooltip content={<ChartAuditMarkerTooltip />} />
          <Legend />
          <ReferenceLine y={2} stroke="#f59e0b" strokeDasharray="5 5" label="+2" />
          <ReferenceLine y={-2} stroke="#f59e0b" strokeDasharray="5 5" label="-2" />
          <ReferenceLine y={0} stroke="#64748b" strokeDasharray="3 3" />
          <Line
            type="monotone"
            dataKey="zscore"
            name="Z-score"
            stroke="#38bdf8"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
            connectNulls={false}
          />
          <Scatter name="Mean crossings" data={statistical} dataKey="y" fill="#94a3b8" shape={<HollowDiamond color="#94a3b8" />} />
          <Scatter
            name="Replay entries"
            data={replayEntries}
            dataKey="y"
            fill="#22c55e"
            shape={<ReplayEntryShape selectedEntryId={selectedEntryId} />}
            onClick={(point) => onMarkerClick(point, onSelectEntryMarker)}
          />
          <Scatter name="Replay exits" data={replayExits} dataKey="y" fill="#3b82f6" shape={<HollowDiamond color="#3b82f6" />} onClick={(point) => onMarkerClick(point, onSelectEntryMarker)} />
          <Scatter name="Replay blocked" data={replayBlocked} dataKey="y" fill="#f59e0b" shape={<HollowX color="#f59e0b" />} />
          <Scatter name="Actual entries" data={actualEntries} dataKey="y" fill="#16a34a" shape={<SolidCircle color="#16a34a" />} onClick={(point) => onMarkerClick(point, onSelectEntryMarker)} />
          <Scatter name="Actual exits" data={actualExits} dataKey="y" fill="#2563eb" shape={<SolidCircle color="#2563eb" />} />
          <Scatter name="Actual other" data={actualOther} dataKey="y" fill="#ef4444" shape={<SolidSquare color="#ef4444" />} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function onMarkerClick(point: unknown, callback?: (marker: EntryMarker) => void) {
  if (!callback || !point || typeof point !== "object") return;
  const marker = (point as { marker?: EntryMarker }).marker;
  if (!marker) return;
  if (marker.marker_type === "actual_entry" || marker.marker_type === "replay_entry_candidate") {
    callback(marker);
  }
}

function normalizeSeries(chart: PairDecisionAuditChart | null): ChartPoint[] {
  return (chart?.zscore_series ?? [])
    .map((point) => {
      const timestamp = toSeconds(point.timestamp);
      if (timestamp === null) return null;
      return {
        timestamp,
        timeLabel: formatTimestamp(timestamp),
        zscore: toNumber(point.zscore),
        spread: toNumber(point.spread),
      };
    })
    .filter((point): point is ChartPoint => point !== null);
}

function normalizeStatisticalMarkers(chart: PairDecisionAuditChart | null): MarkerPoint[] {
  return (chart?.statistical_markers ?? [])
    .map((marker) => markerPoint(marker.timestamp, marker.zscore, marker, "statistical", marker.marker_type))
    .filter((point): point is MarkerPoint => point !== null);
}

function normalizeReplayMarkers(chart: PairDecisionAuditChart | null, type: ChartAuditReplayMarker["marker_type"]): MarkerPoint[] {
  return (chart?.replay_markers ?? [])
    .filter((marker) => marker.marker_type === type)
    .map((marker) => markerPoint(marker.timestamp, marker.z_score, marker, "replay", marker.marker_type))
    .filter((point): point is MarkerPoint => point !== null);
}

function normalizeActualMarkers(chart: PairDecisionAuditChart | null, type: ChartAuditActualMarker["marker_type"] | null): MarkerPoint[] {
  return (chart?.actual_markers ?? [])
    .filter((marker) => type === null || marker.marker_type === type)
    .map((marker) => markerPoint(marker.timestamp, marker.z_score, marker, "actual", marker.marker_type))
    .filter((point): point is MarkerPoint => point !== null);
}

function markerPoint(
  timestampValue: unknown,
  zValue: unknown,
  marker: EntryMarker | Record<string, unknown>,
  markerKind: MarkerPoint["markerKind"],
  markerType: string,
): MarkerPoint | null {
  const timestamp = toSeconds(timestampValue);
  if (timestamp === null) return null;
  return {
    timestamp,
    timeLabel: formatTimestamp(timestamp),
    y: toNumber(zValue) ?? 0,
    marker,
    markerKind,
    markerType,
  };
}

function ChartAuditMarkerTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload?: unknown }> }) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload as Partial<MarkerPoint & ChartPoint> | undefined;
  if (!row) return null;
  const marker = row.marker as EntryMarker | undefined;
  if (!marker) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-3 text-xs shadow-xl dark:border-gray-700 dark:bg-gray-900">
        <div className="font-semibold text-gray-900 dark:text-white">{row.timeLabel}</div>
        <div className="mt-1 text-gray-600 dark:text-gray-300">z_score: {fmt(row.zscore)}</div>
        <div className="text-gray-600 dark:text-gray-300">spread: {fmt(row.spread)}</div>
      </div>
    );
  }
  const metadata = marker.metadata ?? {};
  return (
    <div className="max-w-xs rounded-lg border border-gray-200 bg-white p-3 text-xs shadow-xl dark:border-gray-700 dark:bg-gray-900">
      <div className="font-semibold text-gray-900 dark:text-white">{row.timeLabel}</div>
      <div className="mt-1 text-gray-600 dark:text-gray-300">type: {marker.marker_type}</div>
      <div className="text-gray-600 dark:text-gray-300">side: {marker.side ?? "n/a"}</div>
      <div className="text-gray-600 dark:text-gray-300">z_score: {fmt(marker.z_score)}</div>
      <div className="text-gray-600 dark:text-gray-300">spread: {fmt(marker.spread)}</div>
      {"status" in marker ? <div className="text-gray-600 dark:text-gray-300">status: {marker.status ?? "n/a"}</div> : null}
      {"curator_state" in marker ? <div className="text-gray-600 dark:text-gray-300">curator_state: {marker.curator_state ?? "n/a"}</div> : null}
      {"curator_state_source" in marker ? <div className="text-gray-600 dark:text-gray-300">curator_state_source: {marker.curator_state_source ?? "n/a"}</div> : null}
      {"config_source" in marker ? <div className="text-gray-600 dark:text-gray-300">config_source: {marker.config_source ?? "n/a"}</div> : null}
      {"passed" in marker ? <div className="text-gray-600 dark:text-gray-300">passed: {boolText(marker.passed)}</div> : null}
      <div className="text-gray-600 dark:text-gray-300">block_reasons: {(marker.block_reasons ?? []).join(", ") || "n/a"}</div>
      <div className="text-gray-600 dark:text-gray-300">reason: {marker.reason ?? "n/a"}</div>
      <div className="mt-2 border-t border-gray-200 pt-2 text-gray-600 dark:border-gray-700 dark:text-gray-300">
        score_source: {metadataText(metadata, "score_source") ?? "n/a"}
      </div>
      <div className="text-gray-600 dark:text-gray-300">regime: {metadataText(metadata, "regime_name") ?? "n/a"}</div>
      <div className="text-gray-600 dark:text-gray-300">final_rank: {fmt(metadataNumber(metadata, "final_rank_score"))}</div>
      <div className="text-gray-600 dark:text-gray-300">hedge_ratio: {fmt(metadataNumber(metadata, "hedge_ratio_at_t"))}</div>
    </div>
  );
}

function ReplayEntryShape(props: Record<string, unknown> & { selectedEntryId?: string | null }) {
  const payload = props.payload as MarkerPoint | undefined;
  const marker = payload?.marker as ChartAuditReplayMarker | undefined;
  const selected = marker?.entry_id && marker.entry_id === props.selectedEntryId;
  const color = marker?.side === "SELL_SPREAD" ? "#ef4444" : "#22c55e";
  return <HollowTriangle {...props} color={color} direction={marker?.side === "SELL_SPREAD" ? "down" : "up"} strokeWidth={selected ? 3 : 2} />;
}

function HollowTriangle(props: Record<string, unknown> & { color: string; direction?: "up" | "down"; strokeWidth?: number }) {
  const cx = Number(props.cx ?? 0);
  const cy = Number(props.cy ?? 0);
  const direction = props.direction ?? "up";
  const points = direction === "down"
    ? `${cx - 7},${cy - 6} ${cx + 7},${cy - 6} ${cx},${cy + 7}`
    : `${cx},${cy - 7} ${cx + 7},${cy + 6} ${cx - 7},${cy + 6}`;
  return <polygon points={points} fill="white" fillOpacity={0.02} stroke={props.color} strokeWidth={props.strokeWidth ?? 2} />;
}

function HollowDiamond(props: Record<string, unknown> & { color: string }) {
  const cx = Number(props.cx ?? 0);
  const cy = Number(props.cy ?? 0);
  const points = `${cx},${cy - 7} ${cx + 7},${cy} ${cx},${cy + 7} ${cx - 7},${cy}`;
  return <polygon points={points} fill="white" fillOpacity={0.02} stroke={props.color} strokeWidth={2} />;
}

function HollowX(props: Record<string, unknown> & { color: string }) {
  const cx = Number(props.cx ?? 0);
  const cy = Number(props.cy ?? 0);
  return (
    <g stroke={props.color} strokeWidth={2}>
      <line x1={cx - 6} y1={cy - 6} x2={cx + 6} y2={cy + 6} />
      <line x1={cx + 6} y1={cy - 6} x2={cx - 6} y2={cy + 6} />
    </g>
  );
}

function SolidCircle(props: Record<string, unknown> & { color: string }) {
  return <circle cx={Number(props.cx ?? 0)} cy={Number(props.cy ?? 0)} r={5} fill={props.color} stroke="white" strokeWidth={1.5} />;
}

function SolidSquare(props: Record<string, unknown> & { color: string }) {
  const cx = Number(props.cx ?? 0);
  const cy = Number(props.cy ?? 0);
  return <rect x={cx - 5} y={cy - 5} width={10} height={10} fill={props.color} stroke="white" strokeWidth={1.5} />;
}

function toSeconds(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  const numeric = typeof value === "number" ? value : Number(value);
  if (Number.isFinite(numeric)) return numeric > 10_000_000_000 ? numeric / 1000 : numeric;
  const parsed = new Date(String(value)).getTime();
  return Number.isFinite(parsed) ? parsed / 1000 : null;
}

function toNumber(value: unknown): number | null {
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function fmt(value: unknown): string {
  const numeric = toNumber(value);
  return numeric === null ? "n/a" : numeric.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function formatTimestamp(seconds: number): string {
  return new Date(seconds * 1000).toLocaleString();
}

function boolText(value: unknown): string {
  if (value === true || value === "true") return "true";
  if (value === false || value === "false") return "false";
  return "n/a";
}

function metadataNumber(metadata: Record<string, unknown>, key: string): number | null {
  return toNumber(metadata[key]);
}

function metadataText(metadata: Record<string, unknown>, key: string): string | null {
  const value = metadata[key];
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  return text || null;
}
