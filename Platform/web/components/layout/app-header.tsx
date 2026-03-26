"use client";

import { ReactNode } from "react";

import { useSidebar } from "../../context/sidebar-context";
import { useTheme } from "../../context/theme-context";
import { ProfileMenu } from "./profile-menu";

type AuthInfo = {
  email?: string;
  hasToken?: boolean;
};

type AppHeaderProps = {
  title: string;
  subtitle: string;
  status: string;
  actions?: ReactNode;
  auth?: AuthInfo;
};

export function AppHeader({ title, subtitle, status, actions, auth }: AppHeaderProps) {
  const { toggleSidebar, toggleMobileSidebar } = useSidebar();
  const { theme, toggleTheme } = useTheme();
  const uiBuild = process.env.NEXT_PUBLIC_UI_BUILD || "0d5a617";

  const handleMenuClick = () => {
    if (typeof window !== "undefined" && window.innerWidth >= 1024) {
      toggleSidebar();
      return;
    }
    toggleMobileSidebar();
  };

  return (
    <header className="sticky top-0 z-30 border-b border-gray-200 bg-white/95 backdrop-blur-sm dark:border-gray-800 dark:bg-gray-900/95">
      <div className="flex items-center justify-between gap-4 px-4 py-3 lg:px-6">
        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            className="inline-flex h-10 items-center justify-center rounded-lg border border-gray-200 px-3 text-xs font-semibold uppercase tracking-[0.12em] text-gray-600 dark:border-gray-700 dark:text-gray-300"
            onClick={handleMenuClick}
            aria-label="Toggle sidebar"
          >
            Menu
          </button>

          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-brand-500">Operations Console</p>
            <h1 className="truncate text-xl font-semibold text-gray-800 dark:text-white/90">{title}</h1>
            <p className="truncate text-sm text-gray-500 dark:text-gray-400">{subtitle}</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="inline-flex rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-brand-700 dark:border-brand-800 dark:bg-brand-950/30 dark:text-brand-300">
            UI build {uiBuild}
          </span>
          <span className="hidden rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-gray-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400 md:inline-flex">
            {status}
          </span>
          <button
            type="button"
            className="inline-flex items-center rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-gray-600 dark:border-gray-700 dark:text-gray-300"
            onClick={toggleTheme}
          >
            {theme === "dark" ? "Light" : "Dark"}
          </button>
          {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
          {auth?.hasToken && <ProfileMenu email={auth.email} />}
        </div>
      </div>
    </header>
  );
}
