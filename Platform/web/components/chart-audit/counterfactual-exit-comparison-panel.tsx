"use client";

import type { CounterfactualExitStudy } from "../../lib/api";
import { UI_CLASSES } from "../../lib/ui-classes";
import { TableFrame } from "../panels";

export function CounterfactualExitComparisonPanel({
  selectedEntryId,
  study,
  loading,
  error,
  onCompare,
  onClear,
}: {
  selectedEntryId: string | null;
  study: CounterfactualExitStudy | null;
  loading: boolean;
  error: string | null;
  onCompare: () => void;
  onClear: () => void;
}) {
  if (!selectedEntryId) {
    return (
      <div className="rounded-xl border border-dashed border-gray-300 p-6 text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">
        Select an actual or replay entry marker to compare exits.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-gray-200 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-950/40">
        <div>
          <p className="text-sm font-semibold text-gray-800 dark:text-white/90">Selected entry</p>
          <p className="mt-1 font-mono text-xs text-gray-500 dark:text-gray-400">{selectedEntryId}</p>
        </div>
        <div className="flex gap-2">
          <button type="button" className={UI_CLASSES.secondaryButton} onClick={onClear}>
            Clear
          </button>
          <button type="button" className={UI_CLASSES.primaryButton} onClick={onCompare} disabled={loading}>
            {loading ? "Comparing..." : "Compare exits"}
          </button>
        </div>
      </div>

      {error ? (
        <div className="rounded-xl border border-error-200 bg-error-50 p-4 text-sm text-error-700 dark:border-error-900 dark:bg-error-950/20 dark:text-error-400">
          {error}
        </div>
      ) : null}

      {study ? (
        <div className="space-y-3">
          <div className="grid gap-3 md:grid-cols-3">
            <Summary label="Best policy by PnL" value={study.best_policy_by_pnl ?? "n/a"} />
            <Summary label="Risk adjusted best" value={study.best_policy_by_risk_adjusted_return ?? "n/a"} />
            <Summary label="Actual PnL" value={fmtMoney(study.actual_pnl_usdt)} />
          </div>
          <TableFrame compact>
            <table className="min-w-[920px] text-left text-sm">
              <thead className="border-b border-gray-200 text-xs uppercase tracking-[0.12em] text-gray-500 dark:border-gray-800">
                <tr>
                  <th className="px-4 py-3">Policy</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Exit Z</th>
                  <th className="px-4 py-3">Net PnL</th>
                  <th className="px-4 py-3">Delta</th>
                  <th className="px-4 py-3">Hold</th>
                  <th className="px-4 py-3">Note</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {study.results.map((result) => (
                  <tr key={result.exit_strategy} className="text-gray-700 dark:text-gray-300">
                    <td className="px-4 py-3 font-medium">{result.exit_strategy}</td>
                    <td className="px-4 py-3">{result.status}</td>
                    <td className="px-4 py-3">{fmt(result.hypothetical_exit_z)}</td>
                    <td className="px-4 py-3">{fmtMoney(result.hypothetical_net_pnl_usdt)}</td>
                    <td className="px-4 py-3">{fmtMoney(result.pnl_delta_usdt)}</td>
                    <td className="px-4 py-3">{fmtDuration(result.hold_seconds)}</td>
                    <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{result.note ?? "n/a"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableFrame>
        </div>
      ) : null}
    </div>
  );
}

function Summary({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-3 dark:border-gray-800 dark:bg-gray-900">
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-gray-500">{label}</p>
      <p className="mt-1 truncate font-mono text-sm text-gray-900 dark:text-white/90">{value}</p>
    </div>
  );
}

function fmt(value: number | null | undefined): string {
  return value === null || value === undefined || Number.isNaN(value)
    ? "n/a"
    : value.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function fmtMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString(undefined, { maximumFractionDigits: 2 })} USDT`;
}

function fmtDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "n/a";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${(seconds / 3600).toLocaleString(undefined, { maximumFractionDigits: 1 })}h`;
}
