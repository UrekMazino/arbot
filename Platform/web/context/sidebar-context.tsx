"use client";

import { createContext, useCallback, useContext, useMemo, useState, useSyncExternalStore } from "react";

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
const SIDEBAR_KEY = "v2_sidebar_collapsed";
const SIDEBAR_EVENT = "v2_sidebar_change";

function readStoredExpanded(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return localStorage.getItem(SIDEBAR_KEY) !== "1";
  } catch {
    return true;
  }
}

function subscribeSidebar(onStoreChange: () => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  const handler = () => onStoreChange();
  window.addEventListener("storage", handler);
  window.addEventListener(SIDEBAR_EVENT, handler);
  return () => {
    window.removeEventListener("storage", handler);
    window.removeEventListener(SIDEBAR_EVENT, handler);
  };
}

export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const isExpanded = useSyncExternalStore<boolean>(subscribeSidebar, readStoredExpanded, () => true);
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  const toggleSidebar = useCallback(() => {
    const next = !isExpanded;
    try {
      localStorage.setItem(SIDEBAR_KEY, next ? "0" : "1");
      window.dispatchEvent(new Event(SIDEBAR_EVENT));
    } catch {
      // no-op
    }
  }, [isExpanded]);

  const toggleMobileSidebar = useCallback(() => {
    setIsMobileOpen((prev) => !prev);
  }, []);

  const closeMobileSidebar = useCallback(() => {
    setIsMobileOpen(false);
  }, []);

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
    [closeMobileSidebar, isExpanded, isHovered, isMobileOpen, toggleMobileSidebar, toggleSidebar],
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
