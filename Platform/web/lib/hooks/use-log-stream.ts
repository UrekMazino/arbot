"use client";

import { useCallback, useRef, useState } from "react";
import { apiBaseUrl } from "../../lib/api";

type LogStreamMessage = {
  lines?: string[];
  error?: string;
};

/**
 * Hook for streaming logs via Server-Sent Events (SSE)
 */
export function useLogStream(defaultKey: string = "latest") {
  const [logLines, setLogLines] = useState<string[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const latestKeyRef = useRef<string>(defaultKey);
  const stoppedRef = useRef(false);

  const startStream = useCallback((key?: string) => {
    if (typeof window === "undefined") return;

    // Cleanup previous stream
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    stoppedRef.current = false;
    setError(null);
    setLogLines([]);
    setIsStreaming(true);

    const streamKey = key ?? defaultKey;
    latestKeyRef.current = streamKey;
    const baseUrl = apiBaseUrl();
    const streamUrl = `${baseUrl}/admin/bot/logs/stream?run_key=${encodeURIComponent(streamKey)}`;
    console.log("[SSE] Connecting to:", streamUrl);

    const eventSource = new EventSource(streamUrl, { withCredentials: true });

    eventSource.onmessage = (event) => {
      console.log("[SSE] Received:", event.data);
      try {
        const data = JSON.parse(event.data) as LogStreamMessage;

        if (data.error) {
          setError(data.error);
          setIsStreaming(false);
          return;
        }

        if (Array.isArray(data.lines) && data.lines.length > 0) {
          const newLines = data.lines.filter(
            (line): line is string => typeof line === "string"
          );
          console.log("[SSE] New lines:", newLines.length);
          setLogLines((prev) => [...prev.slice(-500), ...newLines]);
        }
      } catch {
        // Ignore parse errors
      }
    };

    eventSource.onerror = (e) => {
      console.log("[SSE] Error:", e);
      setError("Live stream disconnected");
      setIsStreaming(false);
      eventSource.close();
      eventSourceRef.current = null;
      if (!stoppedRef.current && typeof window !== "undefined") {
        reconnectTimerRef.current = window.setTimeout(() => {
          reconnectTimerRef.current = null;
          startStream(latestKeyRef.current);
        }, 3000);
      }
    };

    eventSource.onopen = () => {
      setIsStreaming(true);
    };

    eventSourceRef.current = eventSource;
  }, [defaultKey]);

  const stopStream = useCallback(() => {
    stoppedRef.current = true;
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsStreaming(false);
  }, []);

  // Clear accumulated log lines
  const clearLogLines = useCallback(() => {
    setLogLines([]);
  }, []);

  return {
    logLines,
    isStreaming,
    error,
    startStream,
    stopStream,
    clearLogLines,
  };
}
