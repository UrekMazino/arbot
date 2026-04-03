"use client";

import Link from "next/link";
import { useMemo } from "react";

import { useSidebar } from "../../context/sidebar-context";
import type { DashboardNavItem } from "../dashboard-shell";

type AppSidebarProps = {
  activeHref: string;
  navItems: DashboardNavItem[];
};

export function AppSidebar({ activeHref, navItems }: AppSidebarProps) {
  const { isExpanded, isMobileOpen, isHovered, setHovered, closeMobileSidebar } = useSidebar();

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

  const showLabel = isExpanded || isMobileOpen || isHovered;
  const widthClass = showLabel ? "w-[290px]" : "w-[90px]";
  const homeHref = navItems[0]?.href || "/admin";

  return (
    <aside
      className={`fixed top-0 left-0 z-50 h-screen border-r border-gray-200 bg-white transition-all duration-300 ease-in-out dark:border-gray-800 dark:bg-gray-900 ${widthClass} ${
        isMobileOpen ? "translate-x-0" : "-translate-x-full"
      } lg:translate-x-0`}
      onMouseEnter={() => {
        if (!isExpanded) setHovered(true);
      }}
      onMouseLeave={() => setHovered(false)}
    >
      <div
        className={`flex items-center border-b border-gray-200 px-4 py-6 dark:border-gray-800 ${
          showLabel ? "justify-start" : "justify-center"
        }`}
      >
        <Link href={homeHref} className="inline-flex items-center gap-2">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-brand-500 text-xs font-bold text-white">
            OS
          </span>
          {showLabel ? <span className="text-base font-semibold text-gray-800 dark:text-white/90">OKX StatBot</span> : null}
        </Link>
      </div>

      <nav className="h-[calc(100vh-81px)] overflow-y-auto px-3 py-4" aria-label="Primary">
        {groupedNav.map((section) => (
          <div key={section.group} className="mb-5">
            <p
              className={`mb-2 px-2 text-xs uppercase tracking-[0.2em] text-gray-400 ${
                showLabel ? "text-left" : "text-center"
              }`}
            >
              {showLabel ? section.group : "..."}
            </p>
            <ul className="space-y-1.5">
              {section.items.map((item) => {
                const active = item.href === activeHref;
                const iconText = (item.icon || item.label.slice(0, 2)).toUpperCase().slice(0, 2);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={closeMobileSidebar}
                      className={`group flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                        active
                          ? "bg-brand-50 text-brand-600 dark:bg-brand-500/20 dark:text-brand-300"
                          : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/5"
                      } ${showLabel ? "justify-start" : "justify-center"}`}
                    >
                      <span
                        className={`inline-flex h-6 w-6 items-center justify-center rounded-md border text-[10px] font-bold tracking-[0.08em] ${
                          active
                            ? "border-brand-500/60 bg-brand-500/20 text-brand-600 dark:text-brand-300"
                            : "border-gray-300 bg-gray-100 text-gray-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400"
                        }`}
                      >
                        {iconText}
                      </span>
                      {showLabel ? (
                        <span className="flex min-w-0 flex-col">
                          <span className="truncate">{item.label}</span>
                          {item.hint ? <span className="truncate text-xs text-gray-400">{item.hint}</span> : null}
                        </span>
                      ) : null}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
    </aside>
  );
}
