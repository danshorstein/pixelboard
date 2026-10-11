import { describe, expect, it } from "vitest";
import { profiles } from "./catalog";
import {
  PITCH_OPTIONS,
  pitchOptionsForProfiles,
  shareOfThirtyInchDresser,
  wholeTickerInches
} from "./pitchComparison";

describe("pitch comparison data", () => {
  const choices = pitchOptionsForProfiles(profiles);

  it("keeps the three Adafruit pitch choices tied to the wide 128x32 profiles", () => {
    expect(choices.map(({ option }) => option.pitchLabel)).toEqual(["P3", "P4", "P5"]);
    expect(choices.every(({ profile }) => profile.logical.width === 128 && profile.logical.height === 32)).toBe(true);
  });

  it("uses the exact two-panel active widths for the comparison", () => {
    expect(choices.map(({ profile }) => profile.physical.widthMm)).toEqual([382, 510, 636]);
    expect(choices.map(({ profile }) => wholeTickerInches(profile).width.toFixed(1))).toEqual(["15.0", "20.1", "25.0"]);
  });

  it("shows larger pitches taking progressively more of a 30-inch dresser top", () => {
    const shares = choices.map(({ profile }) => shareOfThirtyInchDresser(profile));
    expect(shares[0]).toBeCloseTo(50.1, 1);
    expect(shares[1]).toBeCloseTo(66.9, 1);
    expect(shares[2]).toBeCloseTo(83.5, 1);
  });

  it("keeps Adafruit product links and per-panel dimensions available for every choice", () => {
    expect(PITCH_OPTIONS.map((option) => option.productId)).toEqual(["2279", "2278", "2277"]);
    expect(PITCH_OPTIONS.every((option) => option.productUrl.startsWith("https://www.adafruit.com/product/"))).toBe(true);
    expect(PITCH_OPTIONS.every((option) => option.singlePanel.depthMm === 15)).toBe(true);
  });
});
