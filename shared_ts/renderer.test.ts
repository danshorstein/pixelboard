import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import definitionJson from "../definition/mlb-classic/display-definition.json";
import demoDayJson from "../fixtures/demo-day.json";
import standingsJson from "../fixtures/demo-standings.json";
import type {
  DisplayDefinition,
  DisplayElement,
  DisplayScene,
  NormalizedGameState,
  SceneName,
  StandingsState
} from "./models";
import { measureBdfText, parseBdf, type BdfFont } from "./bdf";
import {
  PixelBuffer,
  createBindingContext,
  deriveBindings,
  deriveStandingsBindings,
  evaluateCondition,
  renderScene,
  resolveDesignSettings,
  type Rgba,
  type SpriteAsset
} from "./renderer";

const definition = definitionJson as unknown as DisplayDefinition;
const games = demoDayJson as NormalizedGameState[];
const standings = standingsJson as StandingsState[];
const standingsSnapshot = standings[0];
const favoriteStanding = standingsSnapshot.teams.find((row) => row.team.abbr === "WSH")!;

const fontSource = (name: string) =>
  readFileSync(new URL(`../definition/mlb-classic/fonts/${name}.bdf`, import.meta.url), "utf8");

const fonts: Record<string, BdfFont> = {
  "4x6": parseBdf(fontSource("4x6")),
  "5x7": parseBdf(fontSource("5x7")),
  "6x10": parseBdf(fontSource("6x10"))
};

const liveGame = games.find((game) => game.status === "in_progress")!;
const pregameGame = games.find((game) => game.status === "pregame")!;
const finalGame = games.find((game) => game.status === "final")!;
const statusGame = games.find((game) => game.status === "delayed")!;

const hashBuffer = (data: Uint8ClampedArray): number => {
  let hash = 2166136261;
  for (const value of data) {
    hash ^= value;
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
};

const hasColor = (buffer: PixelBuffer, color: Rgba): boolean => {
  for (let offset = 0; offset < buffer.data.length; offset += 4) {
    if (
      buffer.data[offset] === color[0] &&
      buffer.data[offset + 1] === color[1] &&
      buffer.data[offset + 2] === color[2] &&
      buffer.data[offset + 3] === color[3]
    ) return true;
  }
  return false;
};

const nonBlackPixels = (buffer: PixelBuffer): number => {
  let count = 0;
  for (let offset = 0; offset < buffer.data.length; offset += 4) {
    if (buffer.data[offset] || buffer.data[offset + 1] || buffer.data[offset + 2]) count += 1;
  }
  return count;
};

const definitionWithElements = (elements: DisplayElement[]): DisplayDefinition => {
  const scene: DisplayScene = { elements };
  return {
    ...definition,
    scenes: {
      live: scene,
      pregame: scene,
      final: scene,
      statusOnly: scene,
      idle: scene
    },
    presets: undefined
  };
};

describe("BDF parser", () => {
  it("loads all real M1 fonts with their exact metrics and glyphs", () => {
    expect([fonts["4x6"].width, fonts["4x6"].height]).toEqual([4, 6]);
    expect([fonts["5x7"].width, fonts["5x7"].height]).toEqual([5, 7]);
    expect([fonts["6x10"].width, fonts["6x10"].height]).toEqual([6, 10]);
    for (const font of Object.values(fonts)) {
      const glyph = font.glyphs.get("A".codePointAt(0)!);
      expect(glyph).toBeDefined();
      expect(glyph!.bitmap.some(Boolean)).toBe(true);
      expect(measureBdfText(font, "FINAL")).toBeGreaterThan(0);
    }
  });

  it("rejects non-BDF input", () => {
    expect(() => parseBdf("not executable font data")).toThrow(/Invalid BDF/);
  });
});

describe("PixelBuffer", () => {
  it("has exact RGBA dimensions and clips every write", () => {
    const buffer = new PixelBuffer(4, 3);
    buffer.fillRect(-10, -10, 12, 12, [1, 2, 3, 255]);
    buffer.drawLine(-20, 2, 20, 2, [4, 5, 6, 255]);
    buffer.setPixel(4, 3, [255, 255, 255, 255]);
    expect(buffer.data).toHaveLength(4 * 3 * 4);
    expect(buffer.getPixel(-1, 0)).toBeUndefined();
    expect(buffer.getPixel(4, 2)).toBeUndefined();
    expect(buffer.getPixel(0, 0)).toEqual([1, 2, 3, 255]);
    expect(buffer.getPixel(3, 2)).toEqual([4, 5, 6, 255]);
  });
});

describe("real curated definition rendering", () => {
  it("honors selected logical dimensions and clips a 128-wide definition", () => {
    const buffer = renderScene({
      definition,
      scene: "live",
      game: liveGame,
      fonts,
      favorites: ["WSH", "PHI"],
      logical: { width: 64, height: 16 }
    });
    expect(buffer.width).toBe(64);
    expect(buffer.height).toBe(16);
    expect(buffer.data).toHaveLength(64 * 16 * 4);
    expect([...buffer.data.filter((_, index) => index % 4 === 3)].every((alpha) => alpha === 255)).toBe(true);
  });

  it("renders all five real scenes deliberately, nonempty, and distinctly", () => {
    const cases: Array<[SceneName, NormalizedGameState | null]> = [
      ["live", liveGame],
      ["pregame", pregameGame],
      ["final", finalGame],
      ["statusOnly", statusGame],
      ["idle", null]
    ];
    const frames = cases.map(([scene, game]) => renderScene({
      definition,
      scene,
      game,
      fonts,
      favorites: ["WSH", "PHI"],
      now: "2026-07-15T17:00:00-04:00"
    }));
    expect(frames.every((frame) => frame.width === 128 && frame.height === 32)).toBe(true);
    expect(frames.every((frame) => nonBlackPixels(frame) > 0)).toBe(true);
    expect(new Set(frames.map((frame) => hashBuffer(frame.data))).size).toBe(5);
  });

  it("renders a fixture with omitted optional bases and count without throwing", () => {
    const incomplete = games.find((game) => game.gameId.includes("missing-optionals"))!;
    expect(() => renderScene({
      definition,
      scene: "live",
      game: incomplete,
      fonts,
      overrides: { elements: { showBases: true, showCount: true, showOuts: true } }
    })).not.toThrow();
    expect(nonBlackPixels(renderScene({ definition, scene: "live", game: incomplete, fonts }))).toBeGreaterThan(0);
  });

  it("applies score color, score font, and layout preset overrides without mutating the definition", () => {
    const before = JSON.stringify(definition);
    const base = renderScene({ definition, scene: "live", game: liveGame, fonts });
    const recolored = renderScene({
      definition,
      scene: "live",
      game: liveGame,
      fonts,
      overrides: { colors: { scoreColor: "#00FF00", useTeamColors: false } }
    });
    const smallerFont = renderScene({
      definition,
      scene: "live",
      game: liveGame,
      fonts,
      overrides: { fonts: { scoreFont: "4x6" } }
    });
    const minimal = renderScene({
      definition,
      scene: "live",
      game: liveGame,
      fonts,
      overrides: { layoutPreset: "minimal" }
    });

    expect(hasColor(base, [255, 215, 0, 255])).toBe(true);
    expect(hasColor(recolored, [0, 255, 0, 255])).toBe(true);
    expect(hashBuffer(smallerFont.data)).not.toBe(hashBuffer(base.data));
    expect(hashBuffer(minimal.data)).not.toBe(hashBuffer(base.data));
    expect(resolveDesignSettings(definition, { fonts: { scoreFont: "4x6" } }).fonts.scoreFont).toBe("4x6");
    expect(JSON.stringify(definition)).toBe(before);
  });

  it("renders the Broadcast V2 preset with normalized pitch and matchup context", () => {
    const bindings = deriveBindings(liveGame);
    expect(bindings.pitcherDisplay).toBe("GORE");
    expect(bindings.batterDisplay).toBe("EDWARDS");
    expect(bindings.pitchDisplay).toBe("FF 97 MPH");
    expect(bindings.broadcastContextDisplay).toBe("FF 97 MPH  GORE > EDWARDS");

    const classic = renderScene({ definition, scene: "live", game: liveGame, fonts });
    const broadcast = renderScene({
      definition,
      scene: "live",
      game: liveGame,
      fonts,
      overrides: { layoutPreset: "broadcast" }
    });
    expect(nonBlackPixels(broadcast)).toBeGreaterThan(100);
    expect(hashBuffer(broadcast.data)).not.toBe(hashBuffer(classic.data));
  });

  it("brings both verified team logos into the Broadcast V2 score cards", () => {
    const awayKey = `team-logo:${liveGame.away.id}:16`;
    const homeKey = `team-logo:${liveGame.home.id}:16`;
    const logo = (color: readonly [number, number, number]): SpriteAsset => {
      const data = new Uint8ClampedArray(16 * 16 * 4);
      for (let offset = 0; offset < data.length; offset += 4) {
        data[offset] = color[0];
        data[offset + 1] = color[1];
        data[offset + 2] = color[2];
        data[offset + 3] = 255;
      }
      return { width: 16, height: 16, data };
    };
    const fallback = renderScene({
      definition,
      scene: "live",
      game: liveGame,
      fonts,
      overrides: { layoutPreset: "broadcast" }
    });
    const withLogos = renderScene({
      definition,
      scene: "live",
      game: liveGame,
      awayLogoAssetKey: awayKey,
      homeLogoAssetKey: homeKey,
      fonts,
      overrides: { layoutPreset: "broadcast" },
      assets: {
        [awayKey]: logo([0, 163, 224]),
        [homeKey]: logo([227, 24, 55])
      }
    });

    expect(hashBuffer(withLogos.data)).not.toBe(hashBuffer(fallback.data));
    expect(hasColor(withLogos, [0, 163, 224, 255])).toBe(true);
    expect(hasColor(withLogos, [227, 24, 55, 255])).toBe(true);
    expect(withLogos.getPixel(40, 10)).toEqual([50, 64, 75, 255]);
  });

  it("uses definition-owned team colors only while the toggle is enabled", () => {
    const withTeamColors = renderScene({
      definition,
      scene: "live",
      game: liveGame,
      favorite: false,
      fonts
    });
    const withoutTeamColors = renderScene({
      definition,
      scene: "live",
      game: liveGame,
      favorite: false,
      fonts,
      overrides: { colors: { useTeamColors: false } }
    });
    expect(hasColor(withTeamColors, [0, 163, 224, 255])).toBe(true); // MIA
    expect(hasColor(withoutTeamColors, [255, 255, 255, 255])).toBe(true);
    expect(hasColor(withoutTeamColors, [0, 163, 224, 255])).toBe(false);
  });

  it("renders the dedicated standings scene with a classy fallback or verified logo sprite", () => {
    const fallback = renderScene({
      definition,
      scene: "standings",
      standings: standingsSnapshot,
      standingTeam: favoriteStanding,
      fonts,
      favorites: ["WSH", "PHI"]
    });
    const logoData = new Uint8ClampedArray(16 * 16 * 4);
    for (let offset = 0; offset < logoData.length; offset += 4) {
      logoData[offset] = 20;
      logoData[offset + 1] = 110;
      logoData[offset + 2] = 255;
      logoData[offset + 3] = 255;
    }
    const assetKey = `team-logo:${favoriteStanding.team.id}:16`;
    const withLogo = renderScene({
      definition,
      scene: "standings",
      standings: standingsSnapshot,
      standingTeam: favoriteStanding,
      logoAssetKey: assetKey,
      fonts,
      favorites: ["WSH", "PHI"],
      assets: { [assetKey]: { width: 16, height: 16, data: logoData } }
    });

    expect(nonBlackPixels(fallback)).toBeGreaterThan(0);
    expect(hashBuffer(withLogo.data)).not.toBe(hashBuffer(fallback.data));
    expect(hasColor(fallback, [227, 24, 55, 255])).toBe(true);
  });

  it("renders a verified pair of team marks on live game rows", () => {
    const fallback = renderScene({ definition, scene: "live", game: liveGame, fonts });
    const awayKey = `team-logo:${liveGame.away.id}:16`;
    const homeKey = `team-logo:${liveGame.home.id}:16`;
    const logo = (color: readonly [number, number, number]): SpriteAsset => {
      const data = new Uint8ClampedArray(16 * 16 * 4);
      for (let offset = 0; offset < data.length; offset += 4) {
        data[offset] = color[0];
        data[offset + 1] = color[1];
        data[offset + 2] = color[2];
        data[offset + 3] = 255;
      }
      return { width: 16, height: 16, data };
    };
    const withLogos = renderScene({
      definition,
      scene: "live",
      game: liveGame,
      awayLogoAssetKey: awayKey,
      homeLogoAssetKey: homeKey,
      fonts,
      assets: {
        [awayKey]: logo([18, 52, 86]),
        [homeKey]: logo([227, 24, 55])
      }
    });

    expect(hashBuffer(withLogos.data)).not.toBe(hashBuffer(fallback.data));
    expect(hasColor(withLogos, [46, 133, 220, 255])).toBe(true);
    expect(hasColor(withLogos, [227, 24, 55, 255])).toBe(true);
    expect(withLogos.getPixel(63, 10)).toEqual([127, 219, 255, 255]);
    expect(withLogos.getPixel(64, 10)).toEqual([127, 219, 255, 255]);
  });

  it("renders definition-owned stale and failed source indicators", () => {
    const fresh = renderScene({ definition, scene: "live", game: liveGame, fonts, dataFreshness: "fresh" });
    const stale = renderScene({ definition, scene: "live", game: liveGame, fonts, dataFreshness: "stale" });
    const failed = renderScene({ definition, scene: "live", game: liveGame, fonts, dataFreshness: "failed" });
    expect(hasColor(fresh, [255, 176, 0, 255])).toBe(false);
    expect(hasColor(stale, [255, 176, 0, 255])).toBe(true);
    expect(hasColor(failed, [255, 51, 51, 255])).toBe(true);
    expect(hashBuffer(stale.data)).not.toBe(hashBuffer(failed.data));
  });

  it("renders an amber pause mark only while the current screen is held", () => {
    const rotating = renderScene({ definition, scene: "live", game: liveGame, fonts });
    const held = renderScene({ definition, scene: "live", game: liveGame, fonts, transportHeld: true });

    expect(rotating.getPixel(124, 1)).not.toEqual([255, 176, 0, 255]);
    expect(held.getPixel(124, 1)).toEqual([255, 176, 0, 255]);
    expect(held.getPixel(126, 3)).toEqual([255, 176, 0, 255]);
    expect(hashBuffer(held.data)).not.toBe(hashBuffer(rotating.data));
  });
});

describe("bindings and inert conditions", () => {
  it("provides every declared M1 derived binding", () => {
    expect(deriveBindings(liveGame, { favorites: ["WSH"] })).toMatchObject({
      inningDisplay: "T7",
      statusLabel: "LIVE",
      startTimeDisplay: "2:05 PM",
      matchupDisplay: "MIA AT WSH",
      scorelineDisplay: "MIA 2-3 WSH",
      gameNumberDisplay: "",
      venueDisplay: "Nationals Park",
      isFavorite: true
    });
    expect(deriveBindings(pregameGame).probableDisplay).toContain("Paul Skenes");
    expect(deriveBindings(null).idleMessage).toBe("CHECK BACK FOR THE NEXT GAME");
    expect(deriveBindings(liveGame, {
      awayLogoAssetKey: "team-logo:146:16",
      homeLogoAssetKey: "team-logo:120:16",
      awayLogoAvailable: true,
      homeLogoAvailable: true
    })).toMatchObject({
      awayLogoAssetKey: "team-logo:146:16",
      homeLogoAssetKey: "team-logo:120:16",
      gameLogosAvailable: true
    });
  });

  it("falls back to inning/status instead of placeholder player names when pitcher and batter are absent", () => {
    const gameWithoutPlayers = { ...liveGame, currentPitcher: null, currentBatter: null, lastPitch: null, lastPlay: null };
    const bindings = deriveBindings(gameWithoutPlayers);
    expect(bindings.broadcastContextDisplay).not.toContain("PITCHER");
    expect(bindings.broadcastContextDisplay).not.toContain("BATTER");
    expect(bindings.broadcastContextDisplay).toContain(bindings.inningDisplay);
    expect(bindings.broadcastContextDisplay).toContain(bindings.statusLabel);
  });

  it("derives stable rank, record, games-back, and logo bindings for standings", () => {
    expect(deriveStandingsBindings(standingsSnapshot, favoriteStanding, {
      favorites: ["WSH", "PHI"],
      logoAssetKey: "team-logo:120:16",
      logoAvailable: true
    })).toEqual({
      rankDisplay: "#3",
      recordDisplay: "48-48",
      divisionDisplay: "NL EAST",
      gamesBackDisplay: "10",
      logoAssetKey: "team-logo:120:16",
      logoAvailable: true,
      isFavorite: true
    });
  });

  it("accepts one safe comparison and rejects malicious or chained expressions", () => {
    const context = createBindingContext(liveGame, { favorite: true });
    expect(evaluateCondition("isFavorite == true", context)).toBe(true);
    expect(evaluateCondition("outs >= 2", context)).toBe(true);
    expect(evaluateCondition("count != null", context)).toBe(true);
    expect(evaluateCondition("isFavorite == true || constructor.constructor('return 1')()", context)).toBe(false);
    expect(evaluateCondition("__proto__.polluted == true", context)).toBe(false);

    const malicious = structuredClone(definition) as DisplayDefinition;
    malicious.scenes.live.elements.push({
      type: "box",
      x: 0,
      y: 0,
      width: 128,
      height: 32,
      color: "#00FF00",
      filled: true,
      when: "isFavorite == true; globalThis.__rendererPwned = true"
    });
    const safeFrame = renderScene({ definition, scene: "live", game: liveGame, fonts, favorite: true });
    const maliciousFrame = renderScene({ definition: malicious, scene: "live", game: liveGame, fonts, favorite: true });
    expect(maliciousFrame.data).toEqual(safeFrame.data);
  });
});

describe("complete element vocabulary", () => {
  const assets: Record<string, SpriteAsset> = {
    mono: { width: 3, height: 3, pixels: ["101", "010", "101"] },
    rgb: { width: 2, height: 2, data: [255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 0] }
  };
  const cases: Array<[string, DisplayElement]> = [
    ["text", { type: "text", x: 1, y: 1, font: "4x6", color: "#FFFFFF", text: "A" }],
    ["box", { type: "box", x: 1, y: 1, width: 8, height: 6, color: "#FFFFFF", filled: true }],
    ["line", { type: "line", x1: 0, y1: 0, x2: 12, y2: 8, color: "#FFFFFF" }],
    ["sprite 1bit", { type: "sprite", x: 1, y: 1, asset: "mono", mode: "1bit", color: "#FFFFFF" }],
    ["sprite rgb", { type: "sprite", x: 1, y: 1, asset: "rgb", mode: "rgb" }],
    ["basesDiamond", { type: "basesDiamond", x: 1, y: 1, bind: "bases", color: "#FFFFFF", occupiedColor: "#FFD700", size: 2 }],
    ["outsDots", { type: "outsDots", x: 1, y: 1, bind: "outs", color: "#FFFFFF", activeColor: "#FF0000", spacing: 3 }],
    ["countText", { type: "countText", x: 1, y: 1, bind: "count", font: "4x6", color: "#FFFFFF", prefix: "B-S " }],
    ["scrollText", { type: "scrollText", x: 1, y: 1, width: 20, font: "4x6", color: "#FFFFFF", speedPxPerSec: 5, text: "MARQUEE" }],
    ["clock", { type: "clock", x: 1, y: 1, font: "4x6", color: "#FFFFFF", format: "24h" }]
  ];

  for (const [label, element] of cases) {
    it(`renders ${label}`, () => {
      const frame = renderScene({
        definition: definitionWithElements([element]),
        scene: "live",
        game: liveGame,
        fonts,
        assets,
        logical: { width: 40, height: 16 },
        now: "2026-07-15T17:05:00-04:00",
        elapsedMs: 750
      });
      expect(nonBlackPixels(frame)).toBeGreaterThan(0);
    });
  }

  it("bounds scrollText pixels to its declared marquee viewport", () => {
    const frame = renderScene({
      definition: definitionWithElements([{
        type: "scrollText",
        x: 5,
        y: 1,
        width: 5,
        font: "4x6",
        color: "#FFFFFF",
        speedPxPerSec: 5,
        text: "CLIPPED MARQUEE"
      }]),
      scene: "live",
      game: liveGame,
      fonts,
      logical: { width: 16, height: 8 },
      elapsedMs: 1600
    });
    for (let y = 0; y < frame.height; y += 1) {
      for (let x = 0; x < frame.width; x += 1) {
        if (x < 5 || x >= 10) expect(frame.getPixel(x, y)).toEqual([0, 0, 0, 255]);
      }
    }
  });
});
