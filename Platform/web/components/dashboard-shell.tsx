"use client";

import { ReactNode } from "react";

import { useSidebar } from "../context/sidebar-context";
import { ThemeProvider } from "../context/theme-context";
import { AppHeader } from "./layout/app-header";
import { AppSidebar } from "./layout/app-sidebar";
import { Backdrop } from "./layout/backdrop";
import type { SidebarIconName } from "./layout/sidebar-icons";

export type DashboardNavItem = {
  href: string;
  label: string;
  hint?: string;
  group?: string;
  icon?: SidebarIconName;
  children?: DashboardNavItem[];
};

type AuthInfo = {
  email?: string;
  hasToken?: boolean;
};

type DashboardShellProps = {
  title: string;
  subtitle: string;
  status: string;
  activeHref: string;
  navItems: DashboardNavItem[];
  actions?: ReactNode;
  auth?: AuthInfo;
  children: ReactNode;
};

function DashboardFrame({
  title,
  subtitle,
  status,
  activeHref,
  navItems,
  actions,
  auth,
  children,
}: DashboardShellProps) {
  const { isExpanded, isMobileOpen } = useSidebar();
  // Mobile: no margin when sidebar is closed on mobile.
  // Desktop (lg): margin based on expanded state
  // Very large screens (min 1700px): cap the margin so it stays fixed
  const contentMargin = isMobileOpen ? "ml-0" : isExpanded ? "lg:ml-[290px] min-[1700px]:ml-[290px]" : "lg:ml-[90px] min-[1700px]:ml-[90px]";

  return (
    <div className="h-dvh overflow-hidden bg-gray-50 text-gray-900 dark:bg-gray-900 dark:text-white/90">
      <AppSidebar activeHref={activeHref} navItems={navItems} />
      <Backdrop />

      <div className={`app-shell-shift flex h-dvh flex-col overflow-hidden ${contentMargin}`}>
        <AppHeader title={title} subtitle={subtitle} status={status} actions={actions} auth={auth} />
        <main className="flex min-h-0 flex-1 flex-col overflow-y-auto w-full px-4 py-4 md:px-6 md:py-6">{children}</main>
      </div>
    </div>
  );
}

export function DashboardShell(props: DashboardShellProps) {
  return (
    <ThemeProvider>
      <DashboardFrame {...props} />
    </ThemeProvider>
  );
}
