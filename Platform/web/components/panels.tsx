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
  const classes = ["card", className].filter(Boolean).join(" ");
  return (
    <article className={classes}>
      <div className="panel-head">
        <div>
          <h3>{title}</h3>
          {subtitle ? <p className="panel-subtitle">{subtitle}</p> : null}
        </div>
        {actions ? <div>{actions}</div> : null}
      </div>
      {children}
    </article>
  );
}

export function TableFrame({ compact = false, children }: { compact?: boolean; children: ReactNode }) {
  return <div className={`table-wrap${compact ? " compact" : ""}`}>{children}</div>;
}

type MetricTone = "teal" | "amber" | "sky" | "violet" | "rose";

type MetricCardProps = {
  label: string;
  value: string;
  hint?: string;
  tone?: MetricTone;
};

export function MetricCard({ label, value, hint, tone = "teal" }: MetricCardProps) {
  return (
    <article className={`metric-card metric-tone-${tone}`}>
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}</p>
      {hint ? <p className="metric-hint">{hint}</p> : null}
    </article>
  );
}

type StatusTone = "success" | "warn" | "error" | "info";

export function StatusPill({ label, tone = "info" }: { label: string; tone?: StatusTone }) {
  return <span className={`status-pill status-${tone}`}>{label}</span>;
}
