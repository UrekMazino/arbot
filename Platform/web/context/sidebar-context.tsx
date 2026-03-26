"use client";

import { createContext, useContext, useMemo, useState } from "react";

type SidebarContextValue = {
  isExpanded: boolean;
  isMobileOpen: boolean;
  isHovered: boolean;
  toggleSidebar: () => void;
  toggleMobileSidebar: () => void;
  closeMobileSidebar: () => void;
  setHovered: (value: boolean) => void;
};

const SidebarContext = createContext<SidebarContextValue | null>(null);

function readStoredExpanded(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return localStorage.getItem("v2_sidebar_collapsed") !== "1";
  } catch {
    return true;
  }
}

export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const [isExpanded, setIsExpanded] = useState(readStoredExpanded);
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  const toggleSidebar = () => {
    setIsExpanded((prev) => {
      const next = !prev;
      try {
        localStorage.setItem("v2_sidebar_collapsed", next ? "0" : "1");
      } catch {
        // no-op
      }
      return next;
    });
  };

  const toggleMobileSidebar = () => setIsMobileOpen((prev) => !prev);
  const closeMobileSidebar = () => setIsMobileOpen(false);

  const value = useMemo<SidebarContextValue>(
    () => ({
      isExpanded,
      isMobileOpen,
      isHovered,
      toggleSidebar,
      toggleMobileSidebar,
      closeMobileSidebar,
      setHovered: setIsHovered,
    }),
    [isExpanded, isHovered, isMobileOpen],
  );

  return <SidebarContext.Provider value={value}>{children}</SidebarContext.Provider>;
}

export function useSidebar() {
  const context = useContext(SidebarContext);
  if (!context) {
    throw new Error("useSidebar must be used inside SidebarProvider.");
  }
  return context;
}
