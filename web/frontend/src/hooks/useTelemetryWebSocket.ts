import { useCallback, useEffect, useRef, useState } from "react";
import { parseTelemetryMessage, type TelemetryFrame } from "../lib/telemetryTypes";

export type WsConnectionStatus = "idle" | "connecting" | "open" | "reconnecting" | "error";

export type UseTelemetryWebSocketOptions = {
  /**
   * When false, the hook does not open a WebSocket (avoids console noise when the API is down).
   * Set true after the backend health check succeeds. `reconnectNow()` still attempts one connect.
   */
  enabled?: boolean;
};

const INITIAL_BACKOFF_MS = 500;
const MAX_BACKOFF_MS = 8000;

function nextBackoff(attempt: number): number {
  return Math.min(MAX_BACKOFF_MS, INITIAL_BACKOFF_MS * 2 ** attempt);
}

export function useTelemetryWebSocket(url: string, options?: UseTelemetryWebSocketOptions) {
  const enabled = options?.enabled ?? true;
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  const [status, setStatus] = useState<WsConnectionStatus>("idle");
  const [lastFrame, setLastFrame] = useState<TelemetryFrame | null>(null);
  const [lastCloseCode, setLastCloseCode] = useState<number | null>(null);
  const [lastCloseReason, setLastCloseReason] = useState<string>("");
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedIntentionallyRef = useRef(false);
  const attemptRef = useRef(0);
  const frameRef = useRef<TelemetryFrame | null>(null);
  const rafPendingRef = useRef(false);

  const flushFrame = useCallback(() => {
    rafPendingRef.current = false;
    const f = frameRef.current;
    if (f) setLastFrame(f);
  }, []);

  const pushFrame = useCallback(
    (frame: TelemetryFrame) => {
      frameRef.current = frame;
      if (rafPendingRef.current) return;
      rafPendingRef.current = true;
      requestAnimationFrame(flushFrame);
    },
    [flushFrame]
  );

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current != null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const connect = useCallback(
    (isReconnect: boolean) => {
      clearReconnectTimer();
      closedIntentionallyRef.current = false;
      if (isReconnect) {
        setStatus("reconnecting");
        setReconnectAttempt(attemptRef.current);
      } else {
        setStatus("connecting");
        attemptRef.current = 0;
        setReconnectAttempt(0);
      }

      let ws: WebSocket;
      try {
        ws = new WebSocket(url);
        wsRef.current = ws;
      } catch {
        setStatus("error");
        const delay = nextBackoff(attemptRef.current);
        attemptRef.current += 1;
        setReconnectAttempt(attemptRef.current);
        reconnectTimerRef.current = setTimeout(() => connect(true), delay);
        return;
      }

      ws.onopen = () => {
        attemptRef.current = 0;
        setReconnectAttempt(0);
        setLastCloseCode(null);
        setLastCloseReason("");
        setStatus("open");
      };

      ws.onmessage = (ev) => {
        try {
          const raw = JSON.parse(ev.data as string) as unknown;
          const frame = parseTelemetryMessage(raw);
          if (frame) pushFrame(frame);
        } catch {
          /* ignore */
        }
      };

      ws.onerror = () => {
        setStatus("error");
      };

      ws.onclose = (ev: CloseEvent) => {
        wsRef.current = null;
        setLastCloseCode(ev.code);
        setLastCloseReason(typeof ev.reason === "string" ? ev.reason : "");
        if (closedIntentionallyRef.current) {
          setStatus("idle");
          return;
        }
        if (!enabledRef.current) {
          setStatus("idle");
          return;
        }
        const delay = nextBackoff(attemptRef.current);
        attemptRef.current += 1;
        setReconnectAttempt(attemptRef.current);
        setStatus("reconnecting");
        reconnectTimerRef.current = setTimeout(() => connect(true), delay);
      };
    },
    [clearReconnectTimer, pushFrame, url]
  );

  useEffect(() => {
    if (!enabled) {
      closedIntentionallyRef.current = true;
      clearReconnectTimer();
      rafPendingRef.current = false;
      const w = wsRef.current;
      wsRef.current = null;
      if (w && (w.readyState === WebSocket.OPEN || w.readyState === WebSocket.CONNECTING)) {
        w.close();
      }
      setStatus("idle");
      setLastCloseCode(null);
      setLastCloseReason("");
      attemptRef.current = 0;
      setReconnectAttempt(0);
      return;
    }

    closedIntentionallyRef.current = false;
    connect(false);
    return () => {
      closedIntentionallyRef.current = true;
      clearReconnectTimer();
      rafPendingRef.current = false;
      const w = wsRef.current;
      wsRef.current = null;
      if (w && (w.readyState === WebSocket.OPEN || w.readyState === WebSocket.CONNECTING)) {
        w.close();
      }
    };
  }, [enabled, clearReconnectTimer, connect]);

  const reconnectNow = useCallback(() => {
    clearReconnectTimer();
    const w = wsRef.current;
    wsRef.current = null;
    if (w && (w.readyState === WebSocket.OPEN || w.readyState === WebSocket.CONNECTING)) {
      closedIntentionallyRef.current = true;
      w.close();
      closedIntentionallyRef.current = false;
    }
    attemptRef.current = 0;
    setReconnectAttempt(0);
    connect(false);
  }, [clearReconnectTimer, connect]);

  return { status, lastFrame, lastCloseCode, lastCloseReason, reconnectAttempt, reconnectNow };
}
