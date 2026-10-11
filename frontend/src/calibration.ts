import type { DeviceProfile } from "../../shared_ts/models";

export const CREDIT_CARD_WIDTH_MM = 85.6;
export const CSS_PX_PER_MM_FALLBACK = 96 / 25.4;

export interface ScreenFingerprint {
  devicePixelRatio: number;
  screenWidth: number;
  screenHeight: number;
}

export interface CalibrationRecord {
  pxPerMm: number;
  method: "card" | "monitor";
  fingerprint: ScreenFingerprint;
  savedAt: string;
}

export const calibrationFromCard = (cardWidthCssPx: number): number =>
  cardWidthCssPx > 0 ? cardWidthCssPx / CREDIT_CARD_WIDTH_MM : CSS_PX_PER_MM_FALLBACK;

export const calibrationFromMonitor = (
  diagonalInches: number,
  resolutionWidthPx: number,
  resolutionHeightPx: number,
  devicePixelRatio: number
): number => {
  if (
    diagonalInches <= 0 ||
    resolutionWidthPx <= 0 ||
    resolutionHeightPx <= 0 ||
    devicePixelRatio <= 0
  ) {
    return CSS_PX_PER_MM_FALLBACK;
  }

  const physicalPixelsPerInch =
    Math.hypot(resolutionWidthPx, resolutionHeightPx) / diagonalInches;
  return physicalPixelsPerInch / 25.4 / devicePixelRatio;
};

export const sameFingerprint = (
  left: ScreenFingerprint,
  right: ScreenFingerprint
): boolean =>
  left.devicePixelRatio === right.devicePixelRatio &&
  left.screenWidth === right.screenWidth &&
  left.screenHeight === right.screenHeight;

export const physicalSizeCssPx = (profile: DeviceProfile, pxPerMm: number) => ({
  width: profile.physical.widthMm * pxPerMm,
  height: profile.physical.heightMm * pxPerMm
});

export const currentScreenFingerprint = (): ScreenFingerprint => ({
  devicePixelRatio: window.devicePixelRatio || 1,
  screenWidth: window.screen.width,
  screenHeight: window.screen.height
});
