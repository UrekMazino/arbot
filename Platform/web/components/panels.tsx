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
