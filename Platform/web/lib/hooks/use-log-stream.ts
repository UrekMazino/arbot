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

  const startStream = useCallback((key?: string) => {
    if (typeof window === "undefined") return;

    // Cleanup previous stream
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    setError(null);
    setLogLines([]);
    setIsStreaming(true);

    const streamKey = key ?? defaultKey;
    const baseUrl = apiBaseUrl();
    const streamUrl = `${baseUrl}/admin/bot/logs/stream?run_key=${encodeURIComponent(streamKey)}`;
    console.log("[SSE] Connecting to:", streamUrl);

    const eventSource = new EventSource(streamUrl);

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
      setIsStreaming(false);
      eventSource.close();
    };

    eventSource.onopen = () => {
      setIsStreaming(true);
    };

    eventSourceRef.current = eventSource;
  }, [defaultKey]);

  const stopStream = useCallback(() => {
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