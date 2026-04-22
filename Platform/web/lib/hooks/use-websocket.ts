"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type WsMessage = {
  event_type: string;
  ts: number;
  payload: unknown;
};

type ConnectionState = "connecting" | "connected" | "disconnected" | "error";

/**
 * Custom hook for WebSocket connection
 * Connects to dashboard WebSocket for real-time updates
 */
export function useDashboardWebSocket(botInstanceId?: string) {
  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected");
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null);
  const [heartbeat, setHeartbeat] = useState<number | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Cleanup existing connection
  const cleanup = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnectionState("disconnected");
  }, []);

  // Connect to WebSocket
  const connect = useCallback(() => {
    // Already connected
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    // Cleanup any existing connection first
    cleanup();

    setConnectionState("connecting");

    // Build WebSocket URL
    const wsUrl = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/dashboard${botInstanceId ? `?bot_instance_id=${botInstanceId}` : ""}`;

    try {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        setConnectionState("connected");
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as WsMessage;
          setLastMessage(data);

          if (data.event_type === "heartbeat") {
            setHeartbeat(data.ts);
          }
        } catch {
          // Ignore parse errors
        }
      };

      ws.onerror = () => {
        setConnectionState("error");
      };

      ws.onclose = () => {
        setConnectionState("disconnected");
        wsRef.current = null;
      };

      wsRef.current = ws;
    } catch {
      setConnectionState("error");
    }
  }, [botInstanceId, cleanup]);

  // Disconnect
  const disconnect = useCallback(() => {
    cleanup();
  }, [cleanup]);

  // Connect on mount, auto-reconnect on disconnect via effect
  useEffect(() => {
    const timer = setTimeout(connect, 0);

    return () => {
      clearTimeout(timer);
      cleanup();
    };
  }, [connect, cleanup]);

  /**
   * Extract log lines from WebSocket messages
   */
  const logLines = lastMessage?.payload
    ? (lastMessage.payload as { lines?: string[] })?.lines ?? []
    : [];

  return {
    connectionState,
    lastMessage,
    heartbeat,
    logLines,
    connect,
    disconnect,
    isConnected: connectionState === "connected",
  };
}
