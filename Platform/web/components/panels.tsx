"use client";

import { ReactNode } from "react";

type PanelCardProps = {
  title: string;
  subtitle?: string;
  className?: string;
  actions?: ReactNode;
  children: ReactNode;
};

export function PanelCard({ title, subtitle, className = "", actions, children }: PanelCardProps) {
  const classes = [
    "rounded-2xl border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-900",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <article className={classes}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-gray-800 dark:text-white/90">{title}</h3>
          {subtitle ? <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{subtitle}</p> : null}
        </div>
        {actions ? <div className="shrink-0">{actions}</div> : null}
      </div>
      {children}
    </article>
  );
}

export function TableFrame({ compact = false, children }: { compact?: boolean; children: ReactNode }) {
  return (
    <div
      className={`overflow-auto rounded-xl border border-gray-200 dark:border-gray-800 ${
        compact ? "max-h-80" : "max-h-[34rem]"
      } custom-scrollbar`}
    >
      {children}
    </div>
  );
}

type MetricTone = "teal" | "amber" | "sky" | "violet" | "rose";

type MetricCardProps = {
  label: string;
  value: string;
  hint?: string;
  tone?: MetricTone;
};

export function MetricCard({ label, value, hint, tone = "teal" }: MetricCardProps) {
  const toneClasses: Record<MetricTone, string> = {
    teal: "border-success-200/70 bg-success-25 dark:border-success-900 dark:bg-success-950/20",
    amber: "border-warning-200/80 bg-warning-25 dark:border-warning-900 dark:bg-warning-950/20",
    sky: "border-blue-light-200/80 bg-blue-light-25 dark:border-blue-light-900 dark:bg-blue-light-950/20",
    violet: "border-brand-200/80 bg-brand-25 dark:border-brand-900 dark:bg-brand-950/25",
    rose: "border-error-200/80 bg-error-25 dark:border-error-900 dark:bg-error-950/20",
  };

  return (
    <article
      className={`rounded-2xl border p-4 shadow-sm dark:shadow-none ${toneClasses[tone]}`}
    >
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-gray-500 dark:text-gray-400">{label}</p>
      <p className="mt-2 truncate text-2xl font-semibold text-gray-900 dark:text-white/90">{value}</p>
      {hint ? <p className="mt-1 truncate text-xs text-gray-500 dark:text-gray-400">{hint}</p> : null}
    </article>
  );
}

type StatusTone = "success" | "warn" | "error" | "info";

export function StatusPill({ label, tone = "info" }: { label: string; tone?: StatusTone }) {
  const toneClasses: Record<StatusTone, string> = {
    success: "border-success-200 bg-success-50 text-success-700 dark:border-success-900 dark:bg-success-950/20 dark:text-success-400",
    warn: "border-warning-200 bg-warning-50 text-warning-700 dark:border-warning-900 dark:bg-warning-950/20 dark:text-warning-400",
    error: "border-error-200 bg-error-50 text-error-700 dark:border-error-900 dark:bg-error-950/20 dark:text-error-400",
    info: "border-blue-light-200 bg-blue-light-50 text-blue-light-700 dark:border-blue-light-900 dark:bg-blue-light-950/20 dark:text-blue-light-400",
  };

  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.08em] ${toneClasses[tone]}`}
    >
      {label}
    </span>
  );
}
