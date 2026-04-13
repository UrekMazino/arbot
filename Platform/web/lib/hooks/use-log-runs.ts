"use client";

import { useCallback, useState } from "react";
import {
  AdminLogRun,
  AdminReportRun,
  getAdminLogRuns,
  getAdminReportRuns,
  getAdminBotLogTail,
  AdminLogTail,
} from "../../lib/api";

/**
 * Custom hook for managing log runs and reports
 * - Fetches log/report runs list
 * - Handles run selection
 * - Caches log tail data
 */
export function useLogRuns(defaultLines: number = 320) {
  const [logRuns, setLogRuns] = useState<AdminLogRun[]>([]);
  const [reportRuns, setReportRuns] = useState<AdminReportRun[]>([]);
  const [selectedRunKey, setSelectedRunKey] = useState<string>("latest");
  const [localLogTail, setLocalLogTail] = useState<AdminLogTail | null>(null);
  const [pairHistory, setPairHistory] = useState<Array<{ pair: string; duration_seconds: number }>>([]);
  const [pairCount, setPairCount] = useState<number>(0);

  // Fetch all log runs
  const fetchLogRuns = useCallback(async () => {
    try {
      const runs = await getAdminLogRuns();
      setLogRuns(runs);
      return runs;
    } catch {
      return [];
    }
  }, []);

  // Fetch all report runs
  const fetchReportRuns = useCallback(async () => {
    try {
      const runs = await getAdminReportRuns();
      setReportRuns(runs);
      return runs;
    } catch {
      return [];
    }
  }, []);

  // Fetch both log and report runs
  const fetchAllRuns = useCallback(async () => {
    const [logs, reports] = await Promise.all([fetchLogRuns(), fetchReportRuns()]);
    return { logs, reports };
  }, [fetchLogRuns, fetchReportRuns]);

  // Select a run key and fetch its log tail
  const selectRun = useCallback(
    async (runKey: string) => {
      setSelectedRunKey(runKey);

      try {
        const tail = await getAdminBotLogTail(runKey || "latest", defaultLines);
        setLocalLogTail(tail);

        // Update pair history if available
        if (tail?.pair_history) {
          setPairHistory(tail.pair_history);
          setPairCount(tail.pair_count || 0);
        } else {
          setPairHistory([]);
          setPairCount(0);
        }

        return tail;
      } catch {
        setLocalLogTail(null);
        setPairHistory([]);
        setPairCount(0);
        return null;
      }
    },
    [defaultLines],
  );

  // Clear runs data
  const clearRuns = useCallback(() => {
    setLogRuns([]);
    setReportRuns([]);
    setSelectedRunKey("latest");
    setLocalLogTail(null);
    setPairHistory([]);
    setPairCount(0);
  }, []);

  return {
    // State
    logRuns,
    setLogRuns,
    reportRuns,
    setReportRuns,
    selectedRunKey,
    setSelectedRunKey,
    localLogTail,
    setLocalLogTail,
    pairHistory,
    setPairHistory,
    pairCount,
    setPairCount,

    // Actions
    fetchLogRuns,
    fetchReportRuns,
    fetchAllRuns,
    selectRun,
    clearRuns,
  };
}