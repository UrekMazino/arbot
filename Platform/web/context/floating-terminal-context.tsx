"use client";

import { createContext, useCallback, useContext, useState } from "react";
import { AdminLogTail } from "../lib/api";

type TerminalPosition = { x: number; y: number };
type TerminalSize = { width: number; height: number };

type FloatingTerminalContextType = {
  isFloating: boolean;
  position: TerminalPosition;
  size: TerminalSize;
  selectedRunKey: string;
  logTail: AdminLogTail | null;
  setFloating: (value: boolean) => void;
  setPosition: (pos: TerminalPosition) => void;
  setSize: (sz: TerminalSize) => void;
  setSelectedRunKey: (key: string) => void;
  setLogTail: (tail: AdminLogTail | null) => void;
};

const FloatingTerminalContext = createContext<FloatingTerminalContextType | null>(null);

export function FloatingTerminalProvider({ children }: { children: React.ReactNode }) {
  const [isFloating, setFloating] = useState(false);
  const [position, setPosition] = useState<TerminalPosition>({ x: 0, y: 0 });
  const [size, setSize] = useState<TerminalSize>({ width: 480, height: 320 });
  const [selectedRunKey, setSelectedRunKey] = useState("latest");
  const [logTail, setLogTail] = useState<AdminLogTail | null>(null);

  const handleSetFloating = useCallback((value: boolean) => {
    if (value && position.x === 0 && position.y === 0) {
      // Initialize position to top-right on first float
      setPosition({ x: typeof window !== "undefined" ? window.innerWidth - 500 : 20, y: 20 });
    }
    setFloating(value);
  }, [position]);

  return (
    <FloatingTerminalContext.Provider
      value={{
        isFloating,
        position,
        size,
        selectedRunKey,
        logTail,
        setFloating: handleSetFloating,
        setPosition,
        setSize,
        setSelectedRunKey,
        setLogTail,
      }}
    >
      {children}
    </FloatingTerminalContext.Provider>
  );
}

export function useFloatingTerminal() {
  const ctx = useContext(FloatingTerminalContext);
  if (!ctx) {
    throw new Error("useFloatingTerminal must be used within FloatingTerminalProvider");
  }
  return ctx;
}
