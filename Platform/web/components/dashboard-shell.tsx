"use client";

import { ReactNode } from "react";

import { SidebarProvider, useSidebar } from "../context/sidebar-context";
import { ThemeProvider } from "../context/theme-context";
import { AppHeader } from "./layout/app-header";
import { AppSidebar } from "./layout/app-sidebar";
import { Backdrop } from "./layout/backdrop";

export type DashboardNavItem = {
  href: string;
  label: string;
  hint?: string;
  group?: string;
  icon?: string;
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
  const { isExpanded, isHovered, isMobileOpen } = useSidebar();
  const contentMargin = isMobileOpen ? "ml-0" : isExpanded || isHovered ? "lg:ml-[290px]" : "lg:ml-[90px]";

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900 dark:bg-gray-900 dark:text-white/90">
      <AppSidebar activeHref={activeHref} navItems={navItems} />
      <Backdrop />

      <div className={`app-shell-shift flex-1 ${contentMargin}`}>
        <AppHeader title={title} subtitle={subtitle} status={status} actions={actions} auth={auth} />
        <main className="mx-auto max-w-[1600px] px-4 py-4 md:px-6 md:py-6">{children}</main>
      </div>
    </div>
  );
}

export function DashboardShell(props: DashboardShellProps) {
  return (
    <ThemeProvider>
      <SidebarProvider>
        <DashboardFrame {...props} />
      </SidebarProvider>
    </ThemeProvider>
  );
}
