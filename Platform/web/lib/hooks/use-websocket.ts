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
  const reconnectAttempts = useRef(0);

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    setConnectionState("connecting");

    // Build WebSocket URL (use same host/protocol as current page)
    const wsUrl = `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/api/ws/dashboard${botInstanceId ? `?bot_instance_id=${botInstanceId}` : ""}`;

    try {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        setConnectionState("connected");
        setConnectionState("connected");
        reconnectAttempts.current = 0;
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

        // Auto-reconnect with backoff (max 5 attempts)
        if (reconnectAttempts.current < 5) {
          const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttempts.current++;
            connect();
          }, delay);
        }
      };

      wsRef.current = ws;
    } catch {
      setConnectionState("error");
    }
  }, [botInstanceId]);

  // Disconnect
  const disconnect = useCallback(() => {
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

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    connect();

    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  /**
   * Extract log lines from WebSocket messages
   * Looks for messages with payload containing lines
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