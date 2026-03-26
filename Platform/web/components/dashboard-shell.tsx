"use client";

import Link from "next/link";
import { ReactNode, useEffect, useMemo, useState } from "react";

export type DashboardNavItem = {
  href: string;
  label: string;
  hint?: string;
  group?: string;
  icon?: string;
};

type DashboardShellProps = {
  title: string;
  subtitle: string;
  status: string;
  activeHref: string;
  navItems: DashboardNavItem[];
  actions?: ReactNode;
  children: ReactNode;
};

export function DashboardShell({
  title,
  subtitle,
  status,
  activeHref,
  navItems,
  actions,
  children,
}: DashboardShellProps) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    try {
      const rawCollapsed = localStorage.getItem("v2_sidebar_collapsed");
      if (rawCollapsed === "1") {
        setSidebarCollapsed(true);
      }
      const rawTheme = localStorage.getItem("v2_theme");
      if (rawTheme === "dark" || rawTheme === "light") {
        setTheme(rawTheme);
      }
    } catch {
      // localStorage unavailable
    }
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("v2_theme", theme);
    } catch {
      // no-op
    }
  }, [theme]);

  useEffect(() => {
    try {
      localStorage.setItem("v2_sidebar_collapsed", sidebarCollapsed ? "1" : "0");
    } catch {
      // no-op
    }
  }, [sidebarCollapsed]);

  const shellClass = useMemo(() => {
    const classes = ["ta-shell"];
    if (sidebarCollapsed) classes.push("is-collapsed");
    if (sidebarOpen) classes.push("is-mobile-open");
    return classes.join(" ");
  }, [sidebarCollapsed, sidebarOpen]);

  const groupedNav = useMemo(() => {
    const map = new Map<string, DashboardNavItem[]>();
    for (const item of navItems) {
      const key = (item.group || "General").trim() || "General";
      const current = map.get(key) || [];
      current.push(item);
      map.set(key, current);
    }
    return Array.from(map.entries()).map(([group, items]) => ({ group, items }));
  }, [navItems]);

  const toggleTheme = () => setTheme((prev) => (prev === "light" ? "dark" : "light"));
  const toggleSidebarCollapse = () => setSidebarCollapsed((prev) => !prev);
  const toggleMobileSidebar = () => setSidebarOpen((prev) => !prev);

  return (
    <div className={shellClass}>
      <button
        type="button"
        className="ta-overlay"
        aria-label="Close navigation"
        onClick={() => setSidebarOpen(false)}
      />
      <aside className="ta-sidebar">
        <div className="ta-brand">
          <p className="ta-brand-kicker">okx statbot</p>
          <h2>Control Hub</h2>
          <p>Realtime operations, data quality, and run governance.</p>
        </div>

        <nav className="ta-nav" aria-label="Primary">
          {groupedNav.map((section) => (
            <div key={section.group} className="ta-nav-group">
              <p className="ta-nav-group-title">{section.group}</p>
              {section.items.map((item) => {
                const active = item.href === activeHref;
                const iconText = (item.icon || item.label.slice(0, 2)).toUpperCase().slice(0, 2);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    data-short={iconText}
                    className={`ta-nav-link${active ? " is-active" : ""}`}
                    onClick={() => setSidebarOpen(false)}
                  >
                    <span className="ta-nav-main">
                      <span className="ta-nav-icon" aria-hidden>
                        {iconText}
                      </span>
                      <span className="ta-nav-label">{item.label}</span>
                    </span>
                    {item.hint ? <small>{item.hint}</small> : null}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
      </aside>

      <div className="ta-main">
        <header className="ta-topbar">
          <div className="ta-topbar-left">
            <div className="ta-topbar-toggle-group">
              <button
                type="button"
                className="ta-icon-btn ta-menu-btn"
                onClick={toggleMobileSidebar}
                aria-label="Toggle menu"
              >
                Menu
              </button>
              <button
                type="button"
                className="ta-icon-btn ta-collapse-btn"
                onClick={toggleSidebarCollapse}
                aria-label="Toggle sidebar collapse"
              >
                {sidebarCollapsed ? "Expand" : "Collapse"}
              </button>
            </div>
            <p className="ta-kicker">Operations Console</p>
            <h1>{title}</h1>
            <p>{subtitle}</p>
          </div>
          <div className="ta-topbar-right">
            <span className="ta-status">{status}</span>
            <button type="button" className="ghost ta-theme-btn" onClick={toggleTheme}>
              {theme === "dark" ? "Light Theme" : "Dark Theme"}
            </button>
            {actions ? <div className="ta-actions">{actions}</div> : null}
          </div>
        </header>

        <section className="ta-content">{children}</section>
      </div>
    </div>
  );
}
