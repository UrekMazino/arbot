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
    <header className="sticky top-0 z-30 border-b border-gray-200 bg-white shadow-xs dark:border-gray-800 dark:bg-gray-900">
      <div className="flex items-center justify-between gap-4 px-4 py-4 lg:px-8">
        {/* Left: Menu + Page Title */}
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-gray-200 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800"
            onClick={handleMenuClick}
            aria-label="Toggle sidebar"
          >
            <svg className="h-5 w-5 text-gray-600 dark:text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>

          <div className="min-w-0 border-l border-gray-200 pl-3 dark:border-gray-700">
            <h1 className="truncate text-lg font-semibold text-gray-900 dark:text-white/90">{title}</h1>
            <p className="truncate text-xs text-gray-500 dark:text-gray-400">{subtitle}</p>
          </div>
        </div>

        {/* Right: Actions + Status + Theme + Profile */}
        <div className="flex items-center gap-2 lg:gap-3">
          {/* Custom Actions */}
          {actions ? <div className="flex items-center gap-2">{actions}</div> : null}

          {/* Status Badge */}
          <div className="hidden items-center gap-2 xl:flex">
            <div className="h-2 w-2 rounded-full bg-success-500"></div>
            <span className="text-xs font-medium text-gray-600 dark:text-gray-300">{status}</span>
          </div>

          {/* Divider */}
          <div className="hidden h-5 w-px bg-gray-200 lg:block dark:bg-gray-700"></div>

          {/* UI Build Badge */}
          <span className="hidden rounded-full border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs font-semibold text-gray-600 lg:inline-flex dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
            {uiBuild}
          </span>

          {/* Theme Toggle */}
          <button
            type="button"
            className="inline-flex items-center justify-center h-9 w-9 rounded-lg border border-gray-200 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800"
            onClick={toggleTheme}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          >
            {theme === "dark" ? (
              <svg className="h-5 w-5 text-gray-600 dark:text-gray-300" fill="currentColor" viewBox="0 0 20 20">
                <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
              </svg>
            ) : (
              <svg className="h-5 w-5 text-gray-600 dark:text-gray-300" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l-2.12-2.12a4 4 0 00-.707-.707m2.12-2.122l2.12 2.122a4 4 0 01.707.707m1.414-1.414l2.121-2.121a1 1 0 00-1.414-1.414l-2.121 2.121a1 1 0 001.414 1.414zM4.586 4.586L2.464 2.464a1 1 0 00-1.414 1.414l2.122 2.122a1 1 0 001.414-1.414z" clipRule="evenodd" />
              </svg>
            )}
          </button>

          {/* Profile Menu */}
          {auth?.hasToken && <ProfileMenu email={auth.email} />}
        </div>
      </div>
    </header>
  );
}
