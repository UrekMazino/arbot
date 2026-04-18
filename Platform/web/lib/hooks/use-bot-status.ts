"use client";

import { useCallback, useState } from "react";
import {
  AdminBotStatus,
  getAdminBotStatus,
  getAdminPairsHealth,
  getAdminBotLogTail,
  AdminPairsHealth,
} from "../../lib/api";

/**
 * Custom hook for managing bot status state and polling
 * - Polls bot status at intervals
 * - Handles start/stop state
 * - Provides equity tracking
 */
export function useBotStatus(pollingEnabled: boolean = true) {
  const [botStatus, setBotStatus] = useState<AdminBotStatus | null>(null);
  const [pairsHealth, setPairsHealth] = useState<AdminPairsHealth | null>(null);

  // Equity state
  const [startingEquity, setStartingEquity] = useState<number | null>(null);
  const [runningEquity, setRunningEquity] = useState<number | null>(null);
  const [sessionPnl, setSessionPnl] = useState<{ amount: number; pct: number } | null>(null);
  const [runUptime, setRunUptime] = useState<number | null>(null);

  // Refresh bot status
  const refreshBotStatus = useCallback(async () => {
    try {
      const status = await getAdminBotStatus();
      setBotStatus(status);

      // Update equity from status if available
      if (status?.running) {
        // Bot is running - could extend to fetch live equity
      }
    } catch {
      // Ignore errors silently
    }
  }, []);

  // Refresh pairs health
  const refreshPairsHealth = useCallback(async () => {
    try {
      const health = await getAdminPairsHealth();
      setPairsHealth(health);
    } catch {
      // Ignore errors silently
    }
  }, []);

  // Fetch log tail and update equity
  const updateEquityFromTail = useCallback(
    async (runKey: string = "latest") => {
      try {
        const tail = await getAdminBotLogTail(runKey, 320);
        if (!tail) return;

        // Starting equity (set once when run loads)
        if (tail.starting_equity !== null) {
          setStartingEquity(tail.starting_equity);
        } else if (tail.equity !== null && startingEquity === null) {
          setStartingEquity(tail.equity);
        }
        if (tail.equity !== null) {
          setRunningEquity(tail.equity);
        } else if (tail.starting_equity !== null) {
          setRunningEquity(tail.starting_equity);
        }

        // Session PnL
        if (tail.session_pnl !== null && tail.session_pnl_pct !== null) {
          setSessionPnl({ amount: tail.session_pnl, pct: tail.session_pnl_pct });
        } else {
          setSessionPnl(null);
        }

        // Uptime
        if (tail.run_start_time !== null) {
          setRunUptime(tail.run_start_time);
        }

        return tail;
      } catch {
        return null;
      }
    },
    [startingEquity],
  );

  // Reset equity for new run
  const resetEquity = useCallback(() => {
    setStartingEquity(null);
    setRunningEquity(null);
    setSessionPnl(null);
    setRunUptime(null);
  }, []);

  // Poll both status and health
  const poll = useCallback(async () => {
    await Promise.all([refreshBotStatus(), refreshPairsHealth()]);
  }, [refreshBotStatus, refreshPairsHealth]);

  return {
    // Status
    botStatus,
    setBotStatus,
    pairsHealth,
    setPairsHealth,

    // Equity
    startingEquity,
    runningEquity,
    sessionPnl,
    runUptime,
    setStartingEquity,
    setRunningEquity,
    setSessionPnl,
    setRunUptime,

    // Actions
    refreshBotStatus,
    refreshPairsHealth,
    updateEquityFromTail,
    resetEquity,
    poll,

    // Config
    pollingEnabled,
  };
}
