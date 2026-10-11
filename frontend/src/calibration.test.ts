import { describe, expect, it } from "vitest";
import type { DeviceProfile } from "../../shared_ts/models";
import {
  CSS_PX_PER_MM_FALLBACK,
  calibrationFromCard,
  calibrationFromMonitor,
  physicalSizeCssPx,
  sameFingerprint
} from "./calibration";

describe("physical-size calibration", () => {
  it("derives CSS px/mm from a dragged credit-card reference", () => {
    expect(calibrationFromCard(342.4)).toBeCloseTo(4, 6);
    expect(calibrationFromCard(0)).toBe(CSS_PX_PER_MM_FALLBACK);
  });

  it("accounts for devicePixelRatio in monitor-based calibration", () => {
    const cssPxPerMm = calibrationFromMonitor(24, 1920, 1080, 1);
    expect(cssPxPerMm).toBeCloseTo(Math.hypot(1920, 1080) / 24 / 25.4, 6);
    expect(calibrationFromMonitor(24, 3840, 2160, 2)).toBeCloseTo(cssPxPerMm, 6);
  });

  it("invalidates calibration when DPR or screen metrics change", () => {
    const baseline = { devicePixelRatio: 2, screenWidth: 1440, screenHeight: 900 };
    expect(sameFingerprint(baseline, { ...baseline })).toBe(true);
    expect(sameFingerprint(baseline, { ...baseline, devicePixelRatio: 1 })).toBe(false);
    expect(sameFingerprint(baseline, { ...baseline, screenWidth: 1280 })).toBe(false);
  });

  it("uses profile active dimensions for the money-demo size switch", () => {
    const profile = {
      physical: { widthMm: 510, heightMm: 127, pixelPitchMm: 4 }
    } as DeviceProfile;
    expect(physicalSizeCssPx(profile, 4)).toEqual({ width: 2040, height: 508 });
  });
});
