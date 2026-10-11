import { useCallback, useEffect, useRef, useState } from "react";
import type { DataSnapshot } from "../../shared_ts/models";

export type StudioDataMode = "live" | "demo" | "replay" | "empty";
export type ConnectionState = "idle" | "connecting" | "connected" | "reconnecting" | "offline";

const isSnapshot = (value: unknown): value is DataSnapshot => {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const snapshot = value as Partial<DataSnapshot>;
  return snapshot.schemaVersion === "1.0" &&
    ["live", "demo", "replay"].includes(snapshot.mode ?? "") &&
    Array.isArray(snapshot.games) && Array.isArray(snapshot.standings) &&
    !!snapshot.source && typeof snapshot.source === "object";
};

const queryFor = (mode: Exclude<StudioDataMode, "empty">, date: string, force = false) => {
  const query = new URLSearchParams({ mode, date });
  if (force) query.set("force", "true");
  return query.toString();
};

/** One REST bootstrap plus a resilient same-origin websocket update stream. */
export function useScoreboardData(mode: StudioDataMode, date: string) {
  const [snapshot, setSnapshot] = useState<DataSnapshot | null>(null);
  const [connection, setConnection] = useState<ConnectionState>(mode === "empty" ? "idle" : "connecting");
  const [lastMessageAt, setLastMessageAt] = useState<number | null>(null);
  const snapshotRef = useRef<DataSnapshot | null>(null);

  useEffect(() => {
    snapshotRef.current = snapshot;
  }, [snapshot]);

  useEffect(() => {
    if (mode === "empty") {
      setSnapshot(null);
      setConnection("idle");
      setLastMessageAt(null);
      return;
    }

    let disposed = false;
    let reconnectTimer: number | undefined;
    let socket: WebSocket | undefined;
    let attempt = 0;
    const controller = new AbortController();
    setSnapshot(null);
    setConnection("connecting");
    setLastMessageAt(null);

    const accept = (value: unknown) => {
      if (!isSnapshot(value) || disposed) return;
      setSnapshot(value);
      setLastMessageAt(Date.now());
    };

    const bootstrap = async () => {
      try {
        const response = await fetch(`/api/v1/snapshot?${queryFor(mode, date)}`, {
          cache: "no-store",
          signal: controller.signal
        });
        const value: unknown = await response.json();
        accept(value);
      } catch {
        // The websocket below owns reconnection and the visible offline state.
      }
    };

    const connect = () => {
      if (disposed) return;
      setConnection(attempt === 0 ? "connecting" : "reconnecting");
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(
        `${protocol}//${window.location.host}/api/v1/stream?${queryFor(mode, date)}`
      );
      socket.onopen = () => {
        attempt = 0;
        setConnection("connected");
      };
      socket.onmessage = (event) => {
        try {
          accept(JSON.parse(String(event.data)) as unknown);
        } catch {
          // Malformed provider data is inert and the last known frame remains visible.
        }
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        if (disposed) return;
        attempt += 1;
        setConnection(snapshotRef.current ? "reconnecting" : "offline");
        reconnectTimer = window.setTimeout(connect, Math.min(30_000, 1_000 * 2 ** Math.min(attempt, 5)));
      };
    };

    void bootstrap();
    connect();
    return () => {
      disposed = true;
      controller.abort();
      socket?.close();
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer);
    };
  }, [date, mode]);

  const refresh = useCallback(async () => {
    if (mode === "empty") return;
    try {
      const response = await fetch(`/api/v1/snapshot?${queryFor(mode, date, true)}`, {
        cache: "no-store"
      });
      if (!response.ok) throw new Error(`Snapshot refresh failed (${response.status})`);
      const value: unknown = await response.json();
      if (isSnapshot(value)) {
        setSnapshot(value);
        setLastMessageAt(Date.now());
      }
    } catch {
      setConnection(snapshotRef.current ? "reconnecting" : "offline");
    }
  }, [date, mode]);

  return { snapshot, connection, lastMessageAt, refresh };
}
