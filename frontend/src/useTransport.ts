import { useEffect, useMemo, useRef, useState } from "react";
import type { ScenePlaylistItem } from "../../shared_ts/models";

const itemIdentity = (item: ScenePlaylistItem | null | undefined) => {
  if (!item) return "";
  if (item.kind === "game") return `game:${item.gameId}`;
  if (item.kind === "standings") return `standings:${item.standingsId}:${item.teamId}`;
  return "idle";
};

const itemSignature = (item: ScenePlaylistItem) =>
  `${itemIdentity(item)}:${item.scene}:${item.dwellSec}:${item.favorite}`;

export function useTransport(items: readonly ScenePlaylistItem[]) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [pinned, setPinned] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [timingWarning, setTimingWarning] = useState(false);
  const [holdEndingSec, setHoldEndingSec] = useState<number | null>(null);
  const hiddenAt = useRef<number | null>(null);
  const elapsedRef = useRef(0);
  const currentIdentityRef = useRef("");
  const previousSignatureRef = useRef("");

  const signature = useMemo(
    () => items.map(itemSignature).join("|"),
    [items]
  );

  useEffect(() => {
    if (previousSignatureRef.current === signature) return;
    previousSignatureRef.current = signature;
    const priorIdentity = currentIdentityRef.current;
    const preservedIndex = priorIdentity
      ? items.findIndex((item) => itemIdentity(item) === priorIdentity)
      : -1;
    setIndex(preservedIndex >= 0 ? preservedIndex : 0);
    setElapsedMs(0);
    elapsedRef.current = 0;
    if (priorIdentity && preservedIndex < 0) setPinned(false);
  }, [items, signature]);

  const safeIndex = items.length === 0 ? 0 : index % items.length;
  const current = items[safeIndex] ?? null;
  const currentIdentity = itemIdentity(current);
  const dwellMs = Math.max(1, current?.dwellSec ?? 1) * 1000;

  useEffect(() => {
    currentIdentityRef.current = currentIdentity;
  }, [currentIdentity]);

  useEffect(() => {
    if (!playing || pinned || !current || items.length < 1) return;
    const startedAt = performance.now() - elapsedRef.current;
    const timer = window.setInterval(() => {
      const elapsed = performance.now() - startedAt;
      if (elapsed >= dwellMs) {
        setIndex((value) => (value + 1) % items.length);
        elapsedRef.current = 0;
        setElapsedMs(0);
      } else {
        elapsedRef.current = elapsed;
        setElapsedMs(elapsed);
      }
    }, 100);
    return () => window.clearInterval(timer);
  }, [current, dwellMs, items.length, pinned, playing]);

  useEffect(() => {
    if (!pinned || current?.kind !== "game" || current.scene !== "final") {
      setHoldEndingSec(null);
      return;
    }
    const deadline = Date.now() + 60_000;
    const update = () => {
      const remaining = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      setHoldEndingSec(remaining);
      if (remaining === 0) {
        setPinned(false);
        setPlaying(true);
      }
    };
    update();
    const timer = window.setInterval(update, 250);
    return () => window.clearInterval(timer);
  }, [current?.kind, current?.scene, pinned]);

  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.hidden) {
        hiddenAt.current = Date.now();
      } else if (hiddenAt.current !== null) {
        if (Date.now() - hiddenAt.current > 1000) setTimingWarning(true);
        hiddenAt.current = null;
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => document.removeEventListener("visibilitychange", onVisibilityChange);
  }, []);

  const jump = (nextIndex: number) => {
    if (items.length === 0) return;
    setPinned(false);
    setIndex(Math.max(0, Math.min(items.length - 1, nextIndex)));
    elapsedRef.current = 0;
    setElapsedMs(0);
  };

  const step = (direction: -1 | 1) => {
    if (items.length === 0) return;
    setPinned(false);
    setIndex((value) => (value + direction + items.length) % items.length);
    elapsedRef.current = 0;
    setElapsedMs(0);
  };

  const next = () => {
    step(1);
  };

  return {
    current,
    index: safeIndex,
    playing,
    pinned,
    progress: Math.min(1, elapsedMs / dwellMs),
    remainingSec: Math.max(0, Math.ceil((dwellMs - elapsedMs) / 1000)),
    holdEndingSec,
    timingWarning,
    setPlaying,
    setPinned,
    jump,
    step,
    next,
    dismissTimingWarning: () => setTimingWarning(false)
  };
}
