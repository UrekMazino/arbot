"use client";

import type { DecisionScoreTimelineMeta, DecisionScoreTimelinePoint } from "../../lib/api";
import { TableFrame } from "../panels";

export function DecisionScoreTimelinePanel({
  timeline,
  meta,
  loading,
  error,
}: {
  timeline: DecisionScoreTimelinePoint[];
  meta?: DecisionScoreTimelineMeta;
  loading?: boolean;
  error?: string | null;
}) {
  if (loading) {
    return <Empty message="Loading decision score timeline..." />;
  }
  if (error) {
    return <Empty message={error} tone="error" />;
  }
  if (!timeline.length) {
    return <Empty message="Decision score timeline unavailable or not loaded." />;
  }

  return (
    <div className="space-y-3">
      {meta ? (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {meta.timeline_returned_points} of {meta.timeline_original_points} points · {meta.timeline_downsample_method}
        </p>
      ) : null}
      <TableFrame compact>
        <table className="min-w-[980px] text-left text-sm">
          <thead className="border-b border-gray-200 text-xs uppercase tracking-[0.12em] text-gray-500 dark:border-gray-800">
            <tr>
              <th className="px-4 py-3">Time</th>
              <th className="px-4 py-3">Source</th>
              <th className="px-4 py-3">Curator</th>
              <th className="px-4 py-3">Regime</th>
              <th className="px-4 py-3">Break Risk</th>
              <th className="px-4 py-3">Bayesian</th>
              <th className="px-4 py-3">Final Rank</th>
              <th className="px-4 py-3">Liquidity</th>
              <th className="px-4 py-3">Microstructure</th>
              <th className="px-4 py-3">EV Hold</th>
              <th className="px-4 py-3">Exit Score</th>
              <th className="px-4 py-3">Hedge Drift</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {timeline.slice(0, 120).map((point, index) => (
              <tr key={`${point.timestamp}-${index}`} className="text-gray-700 dark:text-gray-300">
                <td className="px-4 py-3">{fmtTime(point.timestamp)}</td>
                <td className="px-4 py-3">{point.score_source}</td>
                <td className="px-4 py-3">{point.curator_state ?? "n/a"}</td>
                <td className="px-4 py-3">{point.regime ?? "n/a"}</td>
                <td className="px-4 py-3">{fmt(point.break_risk)}</td>
                <td className="px-4 py-3">{fmt(point.bayesian_posterior)}</td>
                <td className="px-4 py-3">{fmt(point.final_rank_score)}</td>
                <td className="px-4 py-3">{fmt(point.liquidity_score)}</td>
                <td className="px-4 py-3">{fmt(point.microstructure_risk)}</td>
                <td className="px-4 py-3">{fmtMoney(point.ev_hold_value_usdt)}</td>
                <td className="px-4 py-3">{fmt(point.exit_score)}</td>
                <td className="px-4 py-3">{fmtPct(point.hedge_ratio_drift_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableFrame>
    </div>
  );
}

function Empty({ message, tone = "neutral" }: { message: string; tone?: "neutral" | "error" }) {
  const toneClass =
    tone === "error"
      ? "border-error-200 bg-error-50 text-error-700 dark:border-error-900 dark:bg-error-950/20 dark:text-error-400"
      : "border-dashed border-gray-300 text-gray-500 dark:border-gray-700 dark:text-gray-400";
  return <div className={`rounded-xl border p-6 text-sm ${toneClass}`}>{message}</div>;
}

function fmt(value: number | null | undefined): string {
  return value === null || value === undefined || Number.isNaN(value)
    ? "n/a"
    : value.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function fmtPct(value: number | null | undefined): string {
  return value === null || value === undefined || Number.isNaN(value)
    ? "n/a"
    : `${(value * 100).toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
}

function fmtMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function fmtTime(value: number | string): string {
  const numeric = typeof value === "number" ? value : Number(value);
  if (Number.isFinite(numeric)) {
    return new Date((numeric > 10_000_000_000 ? numeric : numeric * 1000)).toLocaleString();
  }
  const parsed = new Date(String(value));
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
}
