"use client";

import { useSidebar } from "../../context/sidebar-context";

export function Backdrop() {
  const { isMobileOpen, closeMobileSidebar } = useSidebar();

  return (
    <button
      type="button"
      className={`app-overlay-fade fixed inset-0 z-40 bg-gray-900/45 lg:hidden ${
        isMobileOpen ? "opacity-100" : "pointer-events-none opacity-0"
      }`}
      aria-label="Close navigation"
      onClick={closeMobileSidebar}
    />
  );
}
