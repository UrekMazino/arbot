"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useFloatingTerminal } from "../context/floating-terminal-context";
import { getAdminBotLogTail, getAdminBotStatus, getAdminLogRuns, AdminBotStatus } from "../lib/api";

export function FloatingTerminal() {
  const { isFloating, position, size, selectedRunKey, logTail, setFloating, setPosition, setSize, setSelectedRunKey, setLogTail } = useFloatingTerminal();

  const [logRuns, setLogRuns] = useState<{ run_key: string }[]>([]);

  // Use refs for drag state to avoid stale closures
  const isDraggingRef = useRef(false);
  const dragOffsetRef = useRef({ x: 0, y: 0 });
  const positionRef = useRef(position);
  const selectedRunKeyRef = useRef(selectedRunKey);

  // Keep positionRef in sync
  useEffect(() => {
    positionRef.current = position;
  }, [position]);

  // Keep selectedRunKeyRef in sync
  useEffect(() => {
    selectedRunKeyRef.current = selectedRunKey;
  }, [selectedRunKey]);

  const loadLogTail = useCallback(async (runKey: string) => {
    try {
      const data = await getAdminBotLogTail(runKey, 320);
      setLogTail(data);
      if (data?.run_key && data.run_key !== "__control__") {
        setSelectedRunKey(data.run_key);
      }
    } catch (err) {
      console.error("Failed to load log tail:", err);
    }
  }, [setSelectedRunKey, setLogTail]);

  // Determine which run key to load (same logic as console page)
  const getInitialRunKey = (status: AdminBotStatus | null, runs: { run_key: string }[]): string => {
    // 1. If bot is running, use latest_run_key from status
    if (status?.running && status?.latest_run_key) {
      return status.latest_run_key;
    }
    // 2. Otherwise use the first log run (latest)
    if (runs.length > 0) {
      return runs[0].run_key;
    }
    // 3. No runs - will show control log via API
    return "latest";
  };

  // Initial load - get status first to determine correct run
  useEffect(() => {
    if (!isFloating) return;

    Promise.all([
      getAdminBotStatus(),
      getAdminLogRuns(),
    ])
      .then(([statusData, runsData]) => {
        setLogRuns(runsData);
        const runKey = getInitialRunKey(statusData, runsData);
        return loadLogTail(runKey);
      })
      .catch(console.error);
  }, [isFloating, loadLogTail]);

  // Polling - just refresh current run
  useEffect(() => {
    if (!isFloating) return;
    const timer = setInterval(() => {
      loadLogTail(selectedRunKeyRef.current || "latest").catch(console.error);
    }, 2000);
    return () => clearInterval(timer);
  }, [isFloating, loadLogTail]);

  const handleDragStart = (e: React.MouseEvent) => {
    // Only start drag from the header bar itself
    const target = e.target as HTMLElement;
    if (target.closest('[data-no-drag="true"]')) return;
    if (!target.closest('[data-no-drag="false"]')) return;

    e.preventDefault();
    isDraggingRef.current = true;
    dragOffsetRef.current = {
      x: e.clientX - positionRef.current.x,
      y: e.clientY - positionRef.current.y,
    };
  };

  const handleDragMove = useCallback(
    (e: MouseEvent) => {
      if (!isDraggingRef.current) return;
      setPosition({
        x: e.clientX - dragOffsetRef.current.x,
        y: e.clientY - dragOffsetRef.current.y,
      });
    },
    [setPosition],
  );

  const handleDragEnd = useCallback(() => {
    isDraggingRef.current = false;
  }, []);

  // Set up global drag listeners
  useEffect(() => {
    window.addEventListener("mousemove", handleDragMove);
    window.addEventListener("mouseup", handleDragEnd);
    return () => {
      window.removeEventListener("mousemove", handleDragMove);
      window.removeEventListener("mouseup", handleDragEnd);
    };
  }, [handleDragMove, handleDragEnd]);

  const showingControlLog = logTail?.run_key === "__control__";

  if (!isFloating) return null;

  return (
    <div
      className="fixed z-[9999] flex flex-col rounded-xl border border-gray-600 bg-gray-900 shadow-2xl"
      style={{
        left: position.x,
        top: position.y,
        width: size.width,
        height: size.height,
      }}
    >
      {/* Header - draggable */}
      <div
        className="flex items-center justify-between cursor-move rounded-t-xl border-b border-gray-700 bg-gray-800 px-3 py-2"
        onMouseDown={handleDragStart}
        data-no-drag="false"
      >
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-gray-300">Terminal</span>
          <span className="rounded bg-green-900/50 px-1.5 py-0.5 text-[10px] text-green-400">
            Floating
          </span>
        </div>
        <div className="flex items-center gap-1" data-no-drag="true">
          {/* Run selector */}
          <select
            value={selectedRunKey}
            onChange={(e) => {
              setSelectedRunKey(e.target.value);
              loadLogTail(e.target.value);
            }}
            className="mr-1 rounded bg-gray-700 px-1.5 py-0.5 text-xs text-gray-300"
          >
            {logRuns.map((r) => (
              <option key={r.run_key} value={r.run_key}>
                {r.run_key}
              </option>
            ))}
          </select>
          {/* Resize buttons */}
          <button
            onClick={() => setSize({ width: size.width, height: Math.max(200, size.height - 50) })}
            className="rounded px-1.5 py-0.5 text-xs text-gray-400 hover:bg-gray-700"
            title="Resize smaller"
          >
            −
          </button>
          <button
            onClick={() => setSize({ width: size.width, height: Math.min(window.innerHeight - 100, size.height + 50) })}
            className="rounded px-1.5 py-0.5 text-xs text-gray-400 hover:bg-gray-700"
            title="Resize larger"
          >
            +
          </button>
          {/* Close button */}
          <button
            onClick={() => setFloating(false)}
            className="rounded px-1.5 py-0.5 text-xs text-gray-400 hover:bg-gray-700"
            title="Dock"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Terminal content */}
      <div className="flex flex-1 flex-col overflow-hidden rounded-b-xl">
        {showingControlLog ? (
          <p className="px-3 py-1 text-xs text-gray-400">Control output</p>
        ) : null}
        <pre className="custom-scrollbar flex-1 overflow-auto bg-gray-950 p-2 text-xs leading-relaxed text-emerald-100">
          {(logTail?.lines || []).join("\n") || "No log lines yet."}
        </pre>
      </div>
    </div>
  );
}
