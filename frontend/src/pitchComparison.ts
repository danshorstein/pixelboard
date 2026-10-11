import type { DeviceProfile } from "../../shared_ts/models";

export interface PitchOption {
  profileId: "ticker-128x32-p3" | "ticker-128x32-p4" | "ticker-128x32-p5";
  pitchLabel: "P3" | "P4" | "P5";
  productId: string;
  productUrl: string;
  referencePriceUsd: number;
  singlePanel: {
    widthMm: number;
    heightMm: number;
    depthMm: number;
  };
  note: string;
}

export const PITCH_OPTIONS: readonly PitchOption[] = [
  {
    profileId: "ticker-128x32-p3",
    pitchLabel: "P3",
    productId: "2279",
    productUrl: "https://www.adafruit.com/product/2279",
    referencePriceUsd: 44.95,
    singlePanel: { widthMm: 191, heightMm: 96, depthMm: 15 },
    note: "The compact, close-up choice."
  },
  {
    profileId: "ticker-128x32-p4",
    pitchLabel: "P4",
    productId: "2278",
    productUrl: "https://www.adafruit.com/product/2278",
    referencePriceUsd: 39.95,
    singlePanel: { widthMm: 255, heightMm: 127, depthMm: 15 },
    note: "The approved all-around bedroom ticker."
  },
  {
    profileId: "ticker-128x32-p5",
    pitchLabel: "P5",
    productId: "2277",
    productUrl: "https://www.adafruit.com/product/2277",
    referencePriceUsd: 49.95,
    singlePanel: { widthMm: 318, heightMm: 158, depthMm: 15 },
    note: "The larger, across-the-room scoreboard."
  }
];

export const inches = (millimeters: number) => millimeters / 25.4;

export const wholeTickerInches = (profile: DeviceProfile) => ({
  width: inches(profile.physical.widthMm),
  height: inches(profile.physical.heightMm)
});

export const shareOfThirtyInchDresser = (profile: DeviceProfile) =>
  (inches(profile.physical.widthMm) / 30) * 100;

export const pitchOptionsForProfiles = (profiles: readonly DeviceProfile[]) =>
  PITCH_OPTIONS.flatMap((option) => {
    const profile = profiles.find((candidate) => candidate.id === option.profileId);
    return profile ? [{ option, profile }] : [];
  });
