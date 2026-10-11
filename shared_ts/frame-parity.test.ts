import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import definitionJson from "../definition/mlb-classic/display-definition.json";
import gamesJson from "../fixtures/demo-day.json";
import frameCasesJson from "../fixtures/expected-render-frames.json";
import standingsJson from "../fixtures/demo-standings.json";
import type { DisplayDefinition, NormalizedGameState, SceneName, StandingsState } from "./models";
import { parseBdf } from "./bdf";
import { renderScene, type SpriteAsset } from "./renderer";

interface FrameCase {
  name: string;
  scene: SceneName;
  gameId?: string;
  standingAbbr?: string;
  logo?: boolean;
  logoTone?: string;
  gameLogos?: boolean;
  transportHeld?: boolean;
  layoutPreset?: string;
  elapsedMs: number;
  sha256: string;
}

const definition = definitionJson as unknown as DisplayDefinition;
const games = gamesJson as NormalizedGameState[];
const standings = standingsJson as StandingsState[];
const frameCases = frameCasesJson as FrameCase[];
const fonts = Object.fromEntries(["4x6", "5x7", "6x10"].map((name) => [
  name,
  parseBdf(readFileSync(new URL(`../definition/mlb-classic/fonts/${name}.bdf`, import.meta.url), "utf8"))
]));

const logoAsset = (tone?: string): SpriteAsset => {
  const data = new Uint8ClampedArray(16 * 16 * 4);
  for (let offset = 0; offset < data.length; offset += 4) {
    const pixel = offset / 4, x = pixel % 16, y = Math.floor(pixel / 16);
    const rgb = tone === 'black' ? [0, 0, 0] : tone === 'dark' ? [16, 32, 64] : [20, 110, 255];
    data[offset] = rgb[0]; data[offset + 1] = rgb[1]; data[offset + 2] = rgb[2];
    data[offset + 3] = tone ? (x < 2 || y < 2 || x > 13 || y > 13 ? 0 : (x % 2 ? 128 : 255)) : 255;
  }
  return { width: 16, height: 16, data };
};

const renderCase = (frameCase: FrameCase) => {
  const game = games.find((candidate) => candidate.gameId === frameCase.gameId) ?? null;
  const standingsSnapshot = standings[0] ?? null;
  const standingTeam = standingsSnapshot?.teams.find(
    (candidate) => candidate.team.abbr === frameCase.standingAbbr
  ) ?? null;
  const assetKey = frameCase.logo && standingTeam ? `team-logo:${standingTeam.team.id}:16` : null;
  const awayLogoAssetKey = frameCase.gameLogos && game ? `team-logo:${game.away.id}:16` : null;
  const homeLogoAssetKey = frameCase.gameLogos && game ? `team-logo:${game.home.id}:16` : null;
  const assets: Record<string, SpriteAsset> = {};
  if (assetKey) assets[assetKey] = logoAsset(frameCase.logoTone);
  if (awayLogoAssetKey) assets[awayLogoAssetKey] = logoAsset(frameCase.logoTone);
  if (homeLogoAssetKey) assets[homeLogoAssetKey] = logoAsset(frameCase.logoTone);
  return renderScene({
    definition,
    scene: frameCase.scene,
    game,
    standings: standingTeam ? standingsSnapshot : null,
    standingTeam,
    logoAssetKey: assetKey,
    awayLogoAssetKey,
    homeLogoAssetKey,
    fonts,
    favorites: ["WSH", "PHI"],
    elapsedMs: frameCase.elapsedMs,
    now: "2026-07-15T17:05:00-04:00",
    assets,
    transportHeld: frameCase.transportHeld,
    overrides: frameCase.layoutPreset ? { layoutPreset: frameCase.layoutPreset } : undefined
  });
};

describe("cross-runtime golden render frames", () => {
  for (const frameCase of frameCases) {
    it(frameCase.name, () => {
      const frame = renderCase(frameCase);
      const actual = createHash("sha256").update(frame.data).digest("hex");
      expect(actual).toBe(frameCase.sha256);
    });
  }
});
