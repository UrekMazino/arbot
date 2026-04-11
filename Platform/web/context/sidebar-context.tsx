"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

type SidebarContextValue = {
  isExpanded: boolean;
  isMobileOpen: boolean;
  toggleSidebar: () => void;
  toggleMobileSidebar: () => void;
  closeMobileSidebar: () => void;
};

const SidebarContext = createContext<SidebarContextValue | null>(null);
const SIDEBAR_KEY = "v2_sidebar_collapsed";
const SIDEBAR_EVENT = "v2_sidebar_change";

export function SidebarProvider({ children }: { children: React.ReactNode }) {
  // Check if we're on the client
  const isClient = typeof window !== "undefined";

  // Read from localStorage on initial render (works on both client and server)
  const getInitialState = (): boolean => {
    if (!isClient) return true;
    try {
      const stored = localStorage.getItem(SIDEBAR_KEY);
      return stored === null || stored !== "1";
    } catch {
      return true;
    }
  };

  const [isExpanded, setIsExpanded] = useState<boolean>(getInitialState);
  const [isMobileOpen, setIsMobileOpen] = useState(false);

  // Listen for storage and custom events to sync state across browser tabs
  useEffect(() => {
    const handler = () => {
      const stored = localStorage.getItem(SIDEBAR_KEY);
      setIsExpanded(stored === null || stored !== "1");
    };
    window.addEventListener("storage", handler);
    window.addEventListener(SIDEBAR_EVENT, handler);
    return () => {
      window.removeEventListener("storage", handler);
      window.removeEventListener(SIDEBAR_EVENT, handler);
    };
  }, []);

  const toggleSidebar = useCallback(() => {
    const next = !isExpanded;
    setIsExpanded(next);
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
      toggleSidebar,
      toggleMobileSidebar,
      closeMobileSidebar,
    }),
    [closeMobileSidebar, isExpanded, isMobileOpen, toggleMobileSidebar, toggleSidebar],
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
