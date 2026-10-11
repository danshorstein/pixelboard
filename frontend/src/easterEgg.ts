import { useEffect, useState } from "react";

// Command identity, not physical button color, keeps the shared browser and
// Python/GPIO event contract independent of a particular controller.
export type SecretCommand = "next" | "hold";

export const FIREWORKS_SEQUENCE: readonly SecretCommand[] = [
  "next", "next", "next",
  "hold", "hold", "hold",
  "next", "next", "next"
];

export const advanceSecretSequence = (progress: number, press: SecretCommand) => {
  if (FIREWORKS_SEQUENCE[progress] === press) return progress + 1;
  return press === FIREWORKS_SEQUENCE[0] ? 1 : 0;
};

export function useFireworksEgg(durationMs = 30_000, resetAfterMs = 4_000) {
  const [progress, setProgress] = useState(0);
  const [deadline, setDeadline] = useState<number | null>(null);
  const [clock, setClock] = useState(() => Date.now());
  const [lastPressAt, setLastPressAt] = useState<number | null>(null);

  useEffect(() => {
    if (deadline === null) return;
    const timer = window.setInterval(() => {
      const now = Date.now();
      setClock(now);
      if (now >= deadline) setDeadline(null);
    }, 100);
    return () => window.clearInterval(timer);
  }, [deadline]);

  const press = (command: SecretCommand) => {
    if (deadline !== null) {
      // NEXT exits an active celebration early; normal short-press NEXT
      // semantics elsewhere (rotation advance) still apply unconditionally.
      if (command === "next") setDeadline(null);
      return;
    }
    const now = Date.now();
    const startingProgress = lastPressAt !== null && now - lastPressAt <= resetAfterMs ? progress : 0;
    const nextProgress = advanceSecretSequence(startingProgress, command);
    setLastPressAt(now);
    if (nextProgress === FIREWORKS_SEQUENCE.length) {
      setDeadline(now + durationMs);
      setProgress(0);
      return;
    }
    setProgress(nextProgress);
  };

  const remainingMs = deadline === null ? 0 : Math.max(0, deadline - clock);
  return {
    isActive: deadline !== null,
    elapsedMs: deadline === null ? 0 : durationMs - remainingMs,
    remainingSec: deadline === null ? 0 : Math.ceil(remainingMs / 1000),
    progress,
    press
  };
}
