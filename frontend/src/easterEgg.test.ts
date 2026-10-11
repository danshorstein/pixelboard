import { describe, expect, it } from "vitest";
import { advanceSecretSequence, FIREWORKS_SEQUENCE } from "./easterEgg";
import { createFireworksFrame } from "./fireworks";

describe("fireworks Easter egg", () => {
  it("recognizes NEXT three times, HOLD three times, then NEXT three times", () => {
    const progress = FIREWORKS_SEQUENCE.reduce((value, press) => advanceSecretSequence(value, press), 0);
    expect(progress).toBe(FIREWORKS_SEQUENCE.length);
  });

  it("resets the sequence after an incorrect press while allowing a new NEXT start", () => {
    expect(advanceSecretSequence(3, "next")).toBe(1);
    expect(advanceSecretSequence(3, "hold")).toBe(4);
  });

  it("renders a complete logical fireworks frame", () => {
    const frame = createFireworksFrame(128, 32, 1_000);
    expect(frame.data).toHaveLength(128 * 32 * 4);
    expect(Array.from(frame.data).some((value, index) => index % 4 !== 3 && value > 30)).toBe(true);
  });
});
