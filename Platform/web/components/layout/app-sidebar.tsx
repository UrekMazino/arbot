"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { useSidebar } from "../../context/sidebar-context";
import type { DashboardNavItem } from "../dashboard-shell";
import { SidebarIcon } from "./sidebar-icons";

type AppSidebarProps = {
  activeHref: string;
  navItems: DashboardNavItem[];
};

export function AppSidebar({ activeHref, navItems }: AppSidebarProps) {
  const { isExpanded, isMobileOpen, closeMobileSidebar } = useSidebar();
  const [openSubmenus, setOpenSubmenus] = useState<Set<string>>(() => {
    // Auto-open submenus that contain the active page
    const toOpen = new Set<string>();
    navItems.forEach((item) => {
      if (item.children?.some((child) => child.href === activeHref)) {
        toOpen.add(item.href);
      }
    });
    return toOpen;
  });

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

  const showLabel = isExpanded || isMobileOpen;
  const widthClass = showLabel ? "w-[290px]" : "w-[90px]";
  const homeHref = navItems[0]?.href || "/admin";

  const toggleSubmenu = (href: string) => {
    setOpenSubmenus((prev) => {
      const next = new Set(prev);
      if (next.has(href)) {
        next.delete(href);
      } else {
        next.add(href);
      }
      return next;
    });
  };

  const isSubmenuOpen = (href: string) => openSubmenus.has(href);

  return (
    <aside
      className={`app-shell-shift fixed top-0 left-0 z-40 h-screen border-r border-gray-200 bg-white transition-transform duration-300 dark:border-gray-800 dark:bg-gray-900 ${
        isMobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
      } ${widthClass}`}
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
          {showLabel ? <span className="text-base font-semibold text-gray-800 dark:text-white/90">Project Y</span> : null}
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
                const active = item.href === activeHref || (item.children?.some((child) => child.href === activeHref));
                const hasChildren = item.children && item.children.length > 0;
                const submenuOpen = isSubmenuOpen(item.href);

                return (
                  <li key={item.href}>
                    {hasChildren ? (
                      <>
                        <button
                          onClick={() => toggleSubmenu(item.href)}
                          style={{ justifyContent: 'flex-start' }}
                          className={"group flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors " + (active ? "bg-brand-50 text-brand-600 dark:bg-brand-500/20 dark:text-brand-300" : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/5")}
                        >
                          <span className="[&>svg]:size-8">
                            <SidebarIcon name={item.icon} />
                          </span>
                          {showLabel && (
                            <span className="flex min-w-0 flex-col flex-1">
                              <span className="truncate">{item.label}</span>
                              {item.hint ? <span className="truncate text-xs text-gray-400">{item.hint}</span> : null}
                            </span>
                          )}
                          {showLabel && (
                            <svg
                              className={`h-4 w-4 transition-transform ${submenuOpen ? "rotate-180" : ""}`}
                              fill="none"
                              viewBox="0 0 24 24"
                              stroke="currentColor"
                            >
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                            </svg>
                          )}
                        </button>
                        {submenuOpen && showLabel && (
                          <ul className="ml-4 mt-1 space-y-1 border-l-2 border-gray-200 pl-2 dark:border-gray-700">
                            {item.children!.map((child) => {
                              const childActive = child.href === activeHref;
                              return (
                                <li key={child.href}>
                                  <Link
                                    href={child.href}
                                    onClick={closeMobileSidebar}
                                    className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                                      childActive
                                        ? "bg-brand-50 text-brand-600 dark:bg-brand-500/20 dark:text-brand-300"
                                        : "text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-white/5"
                                    }`}
                                  >
                                    <span className="truncate">{child.label}</span>
                                  </Link>
                                </li>
                              );
                            })}
                          </ul>
                        )}
                      </>
                    ) : (
                      <Link
                        href={item.href}
                        onClick={closeMobileSidebar}
                        style={{ justifyContent: showLabel ? 'flex-start' : 'center' }}
                        className={`group flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                          active
                            ? "bg-brand-50 text-brand-600 dark:bg-brand-500/20 dark:text-brand-300"
                            : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-white/5"
                        }`}
                      >
                        <span className="[&>svg]:size-8">
                          <SidebarIcon name={item.icon} />
                        </span>
                        {showLabel ? (
                          <span className="flex min-w-0 flex-col">
                            <span className="truncate">{item.label}</span>
                            {item.hint ? <span className="truncate text-xs text-gray-400">{item.hint}</span> : null}
                          </span>
                        ) : null}
                      </Link>
                    )}
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
