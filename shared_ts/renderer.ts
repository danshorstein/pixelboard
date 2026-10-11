import { glyphForCodePoint, measureBdfText, parseBdf, type BdfFont } from "./bdf";
import type {
  BasesDiamondElement,
  BoxElement,
  ClockElement,
  CountTextElement,
  DesignOverrides,
  DisplayDefinition,
  DisplayElement,
  DisplaySceneSet,
  FontValue,
  LineElement,
  NormalizedGameState,
  OutsDotsElement,
  SceneName,
  ScrollTextElement,
  SpriteElement,
  StandingTeamState,
  StandingsState,
  TextElement
} from "./models";

export type Rgba = readonly [number, number, number, number];

interface ClipRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

const WHITE: Rgba = [255, 255, 255, 255];
const BLACK: Rgba = [0, 0, 0, 255];

const finiteInteger = (value: unknown, fallback: number): number => {
  const numeric = typeof value === "number" ? value : Number.NaN;
  return Number.isFinite(numeric) ? Math.trunc(numeric) : fallback;
};

const outputDimension = (value: unknown, fallback: number): number => {
  const candidate = finiteInteger(value, fallback);
  return candidate > 0 && candidate <= 4096 ? candidate : Math.max(1, Math.min(4096, fallback));
};

const inClip = (x: number, y: number, clip?: ClipRect): boolean =>
  !clip || (x >= clip.x && y >= clip.y && x < clip.x + clip.width && y < clip.y + clip.height);

/** A logical RGBA framebuffer. Every drawing operation is clipped and total. */
export class PixelBuffer {
  readonly width: number;
  readonly height: number;
  readonly data: Uint8ClampedArray;

  constructor(width: number, height: number, background: Rgba = BLACK) {
    this.width = outputDimension(width, 1);
    this.height = outputDimension(height, 1);
    this.data = new Uint8ClampedArray(this.width * this.height * 4);
    this.clear(background);
  }

  clear(color: Rgba = BLACK): void {
    for (let offset = 0; offset < this.data.length; offset += 4) {
      this.data[offset] = color[0];
      this.data[offset + 1] = color[1];
      this.data[offset + 2] = color[2];
      this.data[offset + 3] = color[3];
    }
  }

  setPixel(x: number, y: number, color: Rgba, clip?: ClipRect): void {
    const px = Math.trunc(x);
    const py = Math.trunc(y);
    if (px < 0 || py < 0 || px >= this.width || py >= this.height || !inClip(px, py, clip)) return;
    const offset = (py * this.width + px) * 4;
    this.data[offset] = color[0];
    this.data[offset + 1] = color[1];
    this.data[offset + 2] = color[2];
    this.data[offset + 3] = color[3];
  }

  blendPixel(x: number, y: number, color: Rgba, clip?: ClipRect): void {
    if (color[3] <= 0) return;
    if (color[3] >= 255) {
      this.setPixel(x, y, color, clip);
      return;
    }
    const px = Math.trunc(x);
    const py = Math.trunc(y);
    if (px < 0 || py < 0 || px >= this.width || py >= this.height || !inClip(px, py, clip)) return;
    const offset = (py * this.width + px) * 4;
    const alpha = color[3] / 255;
    const inverse = 1 - alpha;
    this.data[offset] = Math.round(color[0] * alpha + this.data[offset] * inverse);
    this.data[offset + 1] = Math.round(color[1] * alpha + this.data[offset + 1] * inverse);
    this.data[offset + 2] = Math.round(color[2] * alpha + this.data[offset + 2] * inverse);
    this.data[offset + 3] = 255;
  }

  getPixel(x: number, y: number): Rgba | undefined {
    const px = Math.trunc(x);
    const py = Math.trunc(y);
    if (px < 0 || py < 0 || px >= this.width || py >= this.height) return undefined;
    const offset = (py * this.width + px) * 4;
    return [
      this.data[offset],
      this.data[offset + 1],
      this.data[offset + 2],
      this.data[offset + 3]
    ];
  }

  fillRect(x: number, y: number, width: number, height: number, color: Rgba, clip?: ClipRect): void {
    const left = Math.trunc(x);
    const top = Math.trunc(y);
    const right = left + Math.max(0, Math.trunc(width));
    const bottom = top + Math.max(0, Math.trunc(height));
    for (let py = top; py < bottom; py += 1) {
      for (let px = left; px < right; px += 1) this.setPixel(px, py, color, clip);
    }
  }

  strokeRect(x: number, y: number, width: number, height: number, color: Rgba, clip?: ClipRect): void {
    const w = Math.max(0, Math.trunc(width));
    const h = Math.max(0, Math.trunc(height));
    if (w === 0 || h === 0) return;
    this.drawLine(x, y, x + w - 1, y, color, clip);
    this.drawLine(x, y + h - 1, x + w - 1, y + h - 1, color, clip);
    this.drawLine(x, y, x, y + h - 1, color, clip);
    this.drawLine(x + w - 1, y, x + w - 1, y + h - 1, color, clip);
  }

  drawLine(x1: number, y1: number, x2: number, y2: number, color: Rgba, clip?: ClipRect): void {
    let x = Math.trunc(x1);
    let y = Math.trunc(y1);
    const endX = Math.trunc(x2);
    const endY = Math.trunc(y2);
    const deltaX = Math.abs(endX - x);
    const stepX = x < endX ? 1 : -1;
    const deltaY = -Math.abs(endY - y);
    const stepY = y < endY ? 1 : -1;
    let error = deltaX + deltaY;
    // The endpoint distance limits iteration even for wildly off-canvas lines.
    const maxSteps = Math.min(32768, deltaX + Math.abs(deltaY) + 2);
    for (let step = 0; step < maxSteps; step += 1) {
      this.setPixel(x, y, color, clip);
      if (x === endX && y === endY) break;
      const doubled = 2 * error;
      if (doubled >= deltaY) {
        error += deltaY;
        x += stepX;
      }
      if (doubled <= deltaX) {
        error += deltaX;
        y += stepY;
      }
    }
  }
}

export interface MonoSprite {
  readonly width: number;
  readonly height: number;
  /** Either one string per row, or a flat row-major array of truthy pixels. */
  readonly pixels: readonly string[] | ArrayLike<number | boolean>;
}

export interface RgbSprite {
  readonly width: number;
  readonly height: number;
  /** Flat RGB or RGBA bytes. */
  readonly data: ArrayLike<number>;
}

export type SpriteAsset = MonoSprite | RgbSprite;

export interface ResolvedDesignSettings {
  layoutPreset: string;
  colors: Record<string, string | boolean>;
  fonts: Record<string, string>;
  elements: Record<string, boolean>;
  transition: string;
}

const ownRecord = (value: unknown): Record<string, unknown> | undefined =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;

const overrideValue = (
  overrides: DesignOverrides | undefined,
  group: "colors" | "fonts" | "elements",
  key: string
): unknown => {
  if (!overrides) return undefined;
  const nested = ownRecord(overrides[group]);
  if (nested && Object.prototype.hasOwnProperty.call(nested, key)) return nested[key];
  for (const candidate of [`${group}.${key}`, `$${group}.${key}`, key]) {
    if (Object.prototype.hasOwnProperty.call(overrides, candidate)) return overrides[candidate];
  }
  return undefined;
};

const HEX_COLOR = /^#[0-9A-Fa-f]{6}$/;

/** Resolves declared defaults plus safe, declared project overrides. */
export const resolveDesignSettings = (
  definition: DisplayDefinition,
  overrides: DesignOverrides = {}
): ResolvedDesignSettings => {
  const layoutCandidate =
    typeof overrides.layoutPreset === "string"
      ? overrides.layoutPreset
      : typeof overrides["layoutPreset.default"] === "string"
        ? (overrides["layoutPreset.default"] as string)
        : definition.parameters.layoutPreset.default;
  const layoutPreset = definition.parameters.layoutPreset.options.includes(layoutCandidate)
    ? layoutCandidate
    : definition.parameters.layoutPreset.default;

  const colors: Record<string, string | boolean> = {};
  for (const [key, parameter] of Object.entries(definition.parameters.colors)) {
    const override = overrideValue(overrides, "colors", key);
    if (parameter.type === "toggle") {
      colors[key] = typeof override === "boolean" ? override : parameter.default;
    } else {
      colors[key] = typeof override === "string" && HEX_COLOR.test(override)
        ? override.toUpperCase()
        : parameter.default.toUpperCase();
    }
  }

  const fonts: Record<string, string> = {};
  for (const [key, parameter] of Object.entries(definition.parameters.fonts)) {
    const override = overrideValue(overrides, "fonts", key);
    fonts[key] = typeof override === "string" && parameter.options.includes(override)
      ? override
      : parameter.default;
  }

  const elements: Record<string, boolean> = {};
  for (const [key, defaultValue] of Object.entries(definition.parameters.elements)) {
    const override = overrideValue(overrides, "elements", key);
    elements[key] = typeof override === "boolean" ? override : defaultValue;
  }

  const transitionOverride =
    typeof overrides.transition === "string"
      ? overrides.transition
      : ownRecord(overrides.transition)?.value;
  const transition =
    typeof transitionOverride === "string" &&
    definition.parameters.transition.options.includes(transitionOverride)
      ? transitionOverride
      : definition.parameters.transition.default;

  return { layoutPreset, colors, fonts, elements, transition };
};

export const resolveSceneSet = (
  definition: DisplayDefinition,
  settings: ResolvedDesignSettings
): DisplaySceneSet => {
  const preset = definition.presets?.[settings.layoutPreset];
  return preset ? { ...definition.scenes, ...preset } : definition.scenes;
};

export const parseHexColor = (value: unknown, fallback: Rgba = WHITE): Rgba => {
  if (typeof value !== "string" || !HEX_COLOR.test(value)) return fallback;
  return [
    Number.parseInt(value.slice(1, 3), 16),
    Number.parseInt(value.slice(3, 5), 16),
    Number.parseInt(value.slice(5, 7), 16),
    255
  ];
};

const SAFE_PATH_SEGMENT = /^[A-Za-z_][A-Za-z0-9_]*$/;
const FORBIDDEN_PATH_SEGMENTS = new Set(["__proto__", "prototype", "constructor"]);

/** Reads only own data properties using the display-definition binding grammar. */
export const getBindingValue = (context: unknown, path: string): unknown => {
  if (typeof path !== "string" || path.length === 0) return undefined;
  let value: unknown = context;
  for (const segment of path.split(".")) {
    if (!SAFE_PATH_SEGMENT.test(segment) || FORBIDDEN_PATH_SEGMENTS.has(segment)) return undefined;
    if (value === null || typeof value !== "object") return undefined;
    if (!Object.prototype.hasOwnProperty.call(value, segment)) return undefined;
    value = (value as Record<string, unknown>)[segment];
  }
  return value;
};

const CONDITION =
  /^([A-Za-z_][A-Za-z0-9_.]*)\s*(==|!=|<=|>=|<|>)\s*(null|true|false|-?[0-9]+(?:\.[0-9]+)?|"[^"]*"|'[^']*')$/;

const parseLiteral = (literal: string): string | number | boolean | null => {
  if (literal === "null") return null;
  if (literal === "true") return true;
  if (literal === "false") return false;
  if ((literal.startsWith('"') && literal.endsWith('"')) ||
      (literal.startsWith("'") && literal.endsWith("'"))) return literal.slice(1, -1);
  return Number(literal);
};

/** Evaluates exactly one path-to-literal comparison. Invalid input is inert. */
export const evaluateCondition = (expression: unknown, context: unknown): boolean => {
  if (typeof expression !== "string") return false;
  const match = CONDITION.exec(expression);
  if (!match) return false;
  const left = getBindingValue(context, match[1]);
  const operator = match[2];
  const right = parseLiteral(match[3]);

  if (right === null) {
    const nullish = left === null || left === undefined;
    return operator === "==" ? nullish : operator === "!=" ? !nullish : false;
  }
  if (operator === "==") return left === right;
  if (operator === "!=") return left !== right;
  if (typeof left !== typeof right) return false;
  if (typeof left === "number" && typeof right === "number") {
    if (!Number.isFinite(left) || !Number.isFinite(right)) return false;
    if (operator === "<") return left < right;
    if (operator === "<=") return left <= right;
    if (operator === ">") return left > right;
    if (operator === ">=") return left >= right;
  }
  if (typeof left === "string" && typeof right === "string") {
    if (operator === "<") return left < right;
    if (operator === "<=") return left <= right;
    if (operator === ">") return left > right;
    if (operator === ">=") return left >= right;
  }
  return false;
};

const scoreDisplay = (score: number | null | undefined): string =>
  typeof score === "number" && Number.isFinite(score) ? String(score) : "-";

const formatWallTime = (value: string | null | undefined, format: "12h" | "24h" = "12h"): string => {
  if (!value) return "TIME TBA";
  const match = /T(\d{2}):(\d{2})/.exec(value);
  if (!match) return "TIME TBA";
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour > 23 || minute > 59) return "TIME TBA";
  if (format === "24h") return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
  const suffix = hour >= 12 ? "PM" : "AM";
  const hour12 = hour % 12 || 12;
  return `${hour12}:${String(minute).padStart(2, "0")} ${suffix}`;
};

const inningDisplay = (game: NormalizedGameState | null | undefined): string => {
  if (!game) return "-";
  if (game.status === "final") return "F";
  if (game.inning == null) return "-";
  const prefix: Record<string, string> = { top: "T", bottom: "B", middle: "M", end: "E" };
  return `${game.inningHalf ? prefix[game.inningHalf] ?? "" : ""}${game.inning}`;
};

const STATUS_LABEL: Record<NormalizedGameState["status"], string> = {
  pregame: "PREGAME",
  in_progress: "LIVE",
  final: "FINAL",
  delayed: "DELAYED",
  postponed: "POSTPONED",
  suspended: "SUSPENDED",
  canceled: "CANCELED",
  unknown: "STATUS N/A"
};

const probableDisplay = (game: NormalizedGameState | null | undefined): string => {
  const away = game?.probables?.away?.trim();
  const home = game?.probables?.home?.trim();
  if (away && home) return `P: ${away} / ${home}`;
  if (away) return `P: ${away} / HOME TBA`;
  if (home) return `P: AWAY TBA / ${home}`;
  return "PROBABLES TBA";
};

const isFavoriteGame = (
  game: NormalizedGameState | null | undefined,
  favorites: readonly string[]
): boolean => !!game && (favorites.includes(game.away.abbr) || favorites.includes(game.home.abbr));

export interface DerivedBindings {
  inningDisplay: string;
  statusLabel: string;
  startTimeDisplay: string;
  probableDisplay: string;
  matchupDisplay: string;
  scorelineDisplay: string;
  gameNumberDisplay: string;
  venueDisplay: string;
  idleMessage: string;
  awayLogoAssetKey: string;
  homeLogoAssetKey: string;
  gameLogosAvailable: boolean;
  isFavorite: boolean;
  pitcherDisplay: string;
  batterDisplay: string;
  pitchDisplay: string;
  playDisplay: string;
  battedBallDisplay: string;
  broadcastContextDisplay: string;
}

export interface DerivedStandingsBindings {
  rankDisplay: string;
  recordDisplay: string;
  divisionDisplay: string;
  gamesBackDisplay: string;
  logoAssetKey: string;
  logoAvailable: boolean;
  isFavorite: boolean;
}

export const deriveStandingsBindings = (
  standings: StandingsState | null | undefined,
  row: StandingTeamState | null | undefined,
  options: {
    favorites?: readonly string[];
    logoAssetKey?: string | null;
    logoAvailable?: boolean;
  } = {}
): DerivedStandingsBindings => {
  const gamesBack = row?.gamesBack;
  return {
    rankDisplay: row ? `#${row.rank}` : "#-",
    recordDisplay: row ? `${row.wins}-${row.losses}` : "-- --",
    divisionDisplay: standings?.division.name.toUpperCase() ?? "STANDINGS",
    gamesBackDisplay: gamesBack === 0 ? "-" : gamesBack == null ? "-" : `${gamesBack}`,
    logoAssetKey: options.logoAssetKey ?? "",
    logoAvailable: options.logoAvailable === true,
    isFavorite: !!row && (options.favorites ?? []).includes(row.team.abbr)
  };
};

export const deriveBindings = (
  game: NormalizedGameState | null | undefined,
  options: {
    favorite?: boolean;
    favorites?: readonly string[];
    idleMessage?: string;
    awayLogoAssetKey?: string | null;
    homeLogoAssetKey?: string | null;
    awayLogoAvailable?: boolean;
    homeLogoAvailable?: boolean;
  } = {}
): DerivedBindings => {
  const favorite = options.favorite ?? isFavoriteGame(game, options.favorites ?? []);
  const away = game?.away.abbr ?? "AWAY";
  const home = game?.home.abbr ?? "HOME";
  const shortName = (value: string | null | undefined, fallback: string): string => {
    const parts = value?.trim().split(/\s+/).filter(Boolean) ?? [];
    return (parts.at(-1) ?? fallback).toUpperCase();
  };
  const hasPitcher = !!game?.currentPitcher?.name?.trim();
  const hasBatter = !!game?.currentBatter?.name?.trim();
  const pitcherDisplay = hasPitcher ? shortName(game?.currentPitcher?.name, "") : "";
  const batterDisplay = hasBatter ? shortName(game?.currentBatter?.name, "") : "";
  const pitchCode = game?.lastPitch?.code?.trim().toUpperCase()
    || game?.lastPitch?.type?.trim().toUpperCase()
    || "";
  const pitchSpeed = game?.lastPitch?.startSpeedMph;
  const pitchDisplay = pitchCode
    ? `${pitchCode}${typeof pitchSpeed === "number" ? ` ${Math.round(pitchSpeed)} MPH` : ""}`
    : "";
  const play = game?.lastPlay;
  let playDisplay = play?.displayText?.trim().toUpperCase() || "";
  if (!playDisplay && play) {
    if (play.eventType === "home_run") {
      playDisplay = play.rbi === 4 ? "GRAND SLAM" : play.rbi && play.rbi > 1 ? `${play.rbi}-RUN HR` : "HOME RUN";
    } else {
      playDisplay = play.event.trim().toUpperCase();
    }
  }
  const distance = game?.battedBall?.estimatedDistanceFt;
  const exitVelocity = game?.battedBall?.exitVelocityMph;
  const battedBallDisplay = [
    typeof distance === "number" ? `${Math.round(distance)} FT` : "",
    typeof exitVelocity === "number" ? `${Math.round(exitVelocity)} MPH` : ""
  ].filter(Boolean).join("  ");
  // Missing player context falls back to inning/status instead of rendering
  // literal placeholder names like "P PITCHER  B BATTER".
  const statusContextDisplay = game
    ? (inningDisplay(game) !== "-" ? `${inningDisplay(game)} · ` : "")
      + (game.statusDetail?.trim().toUpperCase() || STATUS_LABEL[game.status] || "STATUS N/A")
    : "NO GAMES";
  const matchup = hasPitcher || hasBatter
    ? `P ${pitcherDisplay || "TBD"}  B ${batterDisplay || "TBD"}`
    : statusContextDisplay;
  const broadcastContextDisplay = playDisplay
    ? `${playDisplay}${battedBallDisplay ? `  ${battedBallDisplay}` : ""}`
    : pitchDisplay
      ? `${pitchDisplay}  ${hasPitcher || hasBatter ? `${pitcherDisplay || "TBD"} > ${batterDisplay || "TBD"}` : statusContextDisplay}`
      : matchup;
  return {
    inningDisplay: inningDisplay(game),
    statusLabel: game
      ? game.statusDetail?.trim().toUpperCase() || STATUS_LABEL[game.status] || "STATUS N/A"
      : "NO GAMES",
    startTimeDisplay: formatWallTime(game?.startTimeLocal ?? game?.startTimeUtc),
    probableDisplay: probableDisplay(game),
    matchupDisplay: `${away} AT ${home}`,
    scorelineDisplay: `${away} ${scoreDisplay(game?.away.score)}-${scoreDisplay(game?.home.score)} ${home}`,
    gameNumberDisplay: game?.doubleheader ? `G${game.gameNumber}` : "",
    venueDisplay: game?.venue?.trim() || "VENUE TBA",
    idleMessage: options.idleMessage?.trim() || "CHECK BACK FOR THE NEXT GAME",
    awayLogoAssetKey: options.awayLogoAssetKey ?? "",
    homeLogoAssetKey: options.homeLogoAssetKey ?? "",
    gameLogosAvailable: !!game && options.awayLogoAvailable === true && options.homeLogoAvailable === true,
    isFavorite: favorite,
    pitcherDisplay,
    batterDisplay,
    pitchDisplay,
    playDisplay,
    battedBallDisplay,
    broadcastContextDisplay
  };
};

export const createBindingContext = (
  game: NormalizedGameState | null | undefined,
  options: {
    favorite?: boolean;
    favorites?: readonly string[];
    idleMessage?: string;
    standings?: StandingsState | null;
    standingTeam?: StandingTeamState | null;
    logoAssetKey?: string | null;
    logoAvailable?: boolean;
    awayLogoAssetKey?: string | null;
    homeLogoAssetKey?: string | null;
    awayLogoAvailable?: boolean;
    homeLogoAvailable?: boolean;
    transportHeld?: boolean;
    dataFreshness?: "fresh" | "stale" | "failed" | "loading";
    dataError?: string | null;
  } = {}
): Record<string, unknown> => ({
  ...(game ?? {}),
  ...(options.standingTeam ?? {}),
  ...deriveBindings(game, options),
  ...(options.standingTeam || options.standings
    ? deriveStandingsBindings(options.standings, options.standingTeam, options)
    : {}),
  transportHeld: options.transportHeld === true,
  dataFreshness: options.dataFreshness ?? "fresh",
  dataError: options.dataError ?? null
});

const stringifyValue = (value: unknown): string => {
  if (value === null || value === undefined) return "N/A";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "N/A";
};

const resolveFontName = (value: FontValue, settings: ResolvedDesignSettings): string => {
  const match = /^\$fonts\.([A-Za-z][A-Za-z0-9_]*)$/.exec(value);
  return match ? settings.fonts[match[1]] ?? "" : value;
};

const normalizeFonts = (fonts: Readonly<Record<string, BdfFont | string>>): Record<string, BdfFont> => {
  const parsed: Record<string, BdfFont> = {};
  for (const [key, font] of Object.entries(fonts)) {
    try {
      parsed[key] = typeof font === "string" ? parseBdf(font) : font;
    } catch {
      // A bad optional font is ignored; other valid fonts and primitives render.
    }
  }
  return parsed;
};

const selectFont = (
  value: FontValue,
  settings: ResolvedDesignSettings,
  fonts: Readonly<Record<string, BdfFont>>
): BdfFont | undefined => {
  const name = resolveFontName(value, settings);
  return fonts[name] ?? fonts["5x7"] ?? Object.values(fonts)[0];
};

interface RenderContext {
  definition: DisplayDefinition;
  settings: ResolvedDesignSettings;
  bindings: Record<string, unknown>;
  game: NormalizedGameState | null;
  standingTeam: StandingTeamState | null;
  favorites: readonly string[];
  fonts: Readonly<Record<string, BdfFont>>;
  assets: Readonly<Record<string, SpriteAsset>>;
  elapsedMs: number;
  now: Date | string | number;
}

const favoriteTeamAbbr = (context: RenderContext): string | undefined => {
  if (context.bindings.isFavorite !== true) return undefined;
  if (context.standingTeam) return context.standingTeam.team.abbr;
  if (!context.game) return undefined;
  if (context.favorites.includes(context.game.away.abbr)) return context.game.away.abbr;
  if (context.favorites.includes(context.game.home.abbr)) return context.game.home.abbr;
  return context.game.home.abbr || context.game.away.abbr;
};

const resolveColor = (
  value: string | undefined,
  context: RenderContext,
  binding?: string,
  fallback: Rgba = WHITE
): Rgba => {
  if (!value) return fallback;
  const match = /^\$colors\.([A-Za-z][A-Za-z0-9_]*)$/.exec(value);
  if (!match) return parseHexColor(value, fallback);
  const role = match[1];
  const useTeamColors = context.settings.colors.useTeamColors === true;
  let resolved = context.settings.colors[role];

  if (useTeamColors && role === "teamText" && context.standingTeam) {
    resolved = context.definition.teamColors?.[context.standingTeam.team.abbr] ?? resolved;
  } else if (useTeamColors && role === "teamText" && context.game) {
    const side = binding?.split(".")[0];
    const abbr = side === "away" ? context.game.away.abbr : side === "home" ? context.game.home.abbr : undefined;
    if (abbr && context.definition.teamColors?.[abbr]) resolved = context.definition.teamColors[abbr];
  } else if (useTeamColors && role === "favoriteAccent") {
    const abbr = favoriteTeamAbbr(context);
    if (abbr && context.definition.teamColors?.[abbr]) resolved = context.definition.teamColors[abbr];
  }

  return parseHexColor(resolved, fallback);
};

const visible = (element: DisplayElement, context: RenderContext): boolean => {
  if (element.visibleWhen !== undefined) {
    const match = /^\$elements\.([A-Za-z][A-Za-z0-9_]*)$/.exec(element.visibleWhen);
    if (!match || context.settings.elements[match[1]] !== true) return false;
  }
  return element.when === undefined || evaluateCondition(element.when, context.bindings);
};

const drawText = (
  buffer: PixelBuffer,
  font: BdfFont,
  text: string,
  x: number,
  y: number,
  color: Rgba,
  align: "left" | "center" | "right" = "left",
  maxWidth?: number,
  outerClip?: ClipRect
): void => {
  const measured = measureBdfText(font, text);
  const originX = align === "center" ? Math.trunc(x - measured / 2) : align === "right" ? x - measured : x;
  const boundedWidth = maxWidth === undefined ? undefined : Math.max(0, Math.trunc(maxWidth));
  let clip = outerClip;
  if (boundedWidth !== undefined) {
    const clipX = align === "center" ? Math.trunc(x - boundedWidth / 2) : align === "right" ? x - boundedWidth : x;
    const ownClip: ClipRect = { x: clipX, y: -4096, width: boundedWidth, height: 8192 };
    if (clip) {
      const left = Math.max(clip.x, ownClip.x);
      const top = Math.max(clip.y, ownClip.y);
      const right = Math.min(clip.x + clip.width, ownClip.x + ownClip.width);
      const bottom = Math.min(clip.y + clip.height, ownClip.y + ownClip.height);
      clip = { x: left, y: top, width: Math.max(0, right - left), height: Math.max(0, bottom - top) };
    } else {
      clip = ownClip;
    }
  }

  let cursorX = Math.trunc(originX);
  const fontTop = font.yOffset + font.height;
  for (const character of text) {
    const glyph = glyphForCodePoint(font, character.codePointAt(0) ?? 0);
    if (!glyph) {
      cursorX += font.width;
      continue;
    }
    const glyphTop = glyph.yOffset + glyph.height;
    const drawX = cursorX + glyph.xOffset - font.xOffset;
    const drawY = Math.trunc(y) + fontTop - glyphTop;
    for (let gy = 0; gy < glyph.height; gy += 1) {
      for (let gx = 0; gx < glyph.width; gx += 1) {
        if (glyph.bitmap[gy * glyph.width + gx]) buffer.setPixel(drawX + gx, drawY + gy, color, clip);
      }
    }
    cursorX += glyph.advanceX;
  }
};

const drawBox = (buffer: PixelBuffer, element: BoxElement, context: RenderContext): void => {
  const color = resolveColor(element.color, context);
  if (element.filled) buffer.fillRect(element.x, element.y, element.width, element.height, color);
  else buffer.strokeRect(element.x, element.y, element.width, element.height, color);
};

const drawLine = (buffer: PixelBuffer, element: LineElement, context: RenderContext): void =>
  buffer.drawLine(element.x1, element.y1, element.x2, element.y2, resolveColor(element.color, context));

const monoPixel = (sprite: MonoSprite, x: number, y: number): boolean => {
  if (Array.isArray(sprite.pixels) && typeof sprite.pixels[0] === "string") {
    const character = (sprite.pixels as readonly string[])[y]?.[x];
    return character !== undefined && character !== "0" && character !== "." && character !== " ";
  }
  return Boolean((sprite.pixels as ArrayLike<number | boolean>)[y * sprite.width + x]);
};

const drawSprite = (buffer: PixelBuffer, element: SpriteElement, context: RenderContext): void => {
  const bound = element.bind ? getBindingValue(context.bindings, element.bind) : undefined;
  const assetKey = element.asset ?? (typeof bound === "string" ? bound : "");
  if (!/^(?!.*(?:^|\/)\.\.(?:\/|$))[A-Za-z0-9][A-Za-z0-9._:/-]*$/.test(assetKey)) return;
  const asset = Object.prototype.hasOwnProperty.call(context.assets, assetKey)
    ? context.assets[assetKey]
    : undefined;
  if (!asset) return;
  const width = Math.max(0, finiteInteger(asset.width, 0));
  const height = Math.max(0, finiteInteger(asset.height, 0));
  if (element.mode === "1bit" && "pixels" in asset) {
    const color = resolveColor(element.color, context);
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        if (monoPixel(asset, x, y)) buffer.setPixel(element.x + x, element.y + y, color);
      }
    }
  } else if (element.mode === "rgb" && "data" in asset) {
    const channels = asset.data.length >= width * height * 4 ? 4 : 3;
    let peak = 255;
    if (assetKey.startsWith("team-logo:")) {
      peak = 0;
      for (let i = 0; i + channels <= asset.data.length; i += channels) {
        if (channels === 3 || asset.data[i + 3] > 0) peak = Math.max(peak, asset.data[i], asset.data[i + 1], asset.data[i + 2]);
      }
    }
    const channel = (value: number) => peak === 0 ? 220 : peak < 128 ? Math.min(255, Math.round(value * 220 / peak)) : value;
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) {
        const offset = (y * width + x) * channels;
        buffer.blendPixel(element.x + x, element.y + y, [
          channel(Number(asset.data[offset] ?? 0)),
          channel(Number(asset.data[offset + 1] ?? 0)),
          channel(Number(asset.data[offset + 2] ?? 0)),
          channels === 4 ? Number(asset.data[offset + 3] ?? 0) : 255
        ]);
      }
    }
  }
};

const drawDiamond = (
  buffer: PixelBuffer,
  centerX: number,
  centerY: number,
  radius: number,
  color: Rgba,
  occupied: boolean
): void => {
  for (let dy = -radius; dy <= radius; dy += 1) {
    for (let dx = -radius; dx <= radius; dx += 1) {
      const distance = Math.abs(dx) + Math.abs(dy);
      if ((occupied && distance <= radius) || (!occupied && distance === radius)) {
        buffer.setPixel(centerX + dx, centerY + dy, color);
      }
    }
  }
};

const drawBases = (buffer: PixelBuffer, element: BasesDiamondElement, context: RenderContext): void => {
  const value = getBindingValue(context.bindings, element.bind);
  if (value === null || typeof value !== "object") return;
  const bases = value as Record<string, unknown>;
  const size = Math.max(2, Math.min(12, finiteInteger(element.size, 3)));
  const empty = resolveColor(element.color, context, element.bind);
  const occupied = resolveColor(element.occupiedColor, context, element.bind);
  drawDiamond(buffer, element.x + size * 2, element.y + size, size, bases.second ? occupied : empty, bases.second === true);
  drawDiamond(buffer, element.x + size, element.y + size * 2, size, bases.third ? occupied : empty, bases.third === true);
  drawDiamond(buffer, element.x + size * 3, element.y + size * 2, size, bases.first ? occupied : empty, bases.first === true);
};

const drawOuts = (buffer: PixelBuffer, element: OutsDotsElement, context: RenderContext): void => {
  const raw = getBindingValue(context.bindings, element.bind);
  if (typeof raw !== "number" || !Number.isFinite(raw)) return;
  const outs = Math.max(0, Math.min(3, Math.trunc(raw)));
  const spacing = Math.max(2, Math.min(20, finiteInteger(element.spacing, 5)));
  const inactive = resolveColor(element.color, context, element.bind);
  const active = resolveColor(element.activeColor, context, element.bind);
  for (let index = 0; index < 3; index += 1) {
    buffer.fillRect(element.x + index * spacing, element.y, 2, 2, index < outs ? active : inactive);
  }
};

const drawCount = (buffer: PixelBuffer, element: CountTextElement, context: RenderContext): void => {
  const count = getBindingValue(context.bindings, element.bind);
  if (count === null || typeof count !== "object") return;
  const values = count as Record<string, unknown>;
  const balls = typeof values.balls === "number" ? values.balls : "-";
  const strikes = typeof values.strikes === "number" ? values.strikes : "-";
  const font = selectFont(element.font, context.settings, context.fonts);
  if (!font) return;
  drawText(
    buffer,
    font,
    `${element.prefix ?? ""}${balls}-${strikes}`,
    element.x,
    element.y,
    resolveColor(element.color, context, element.bind)
  );
};

const textForElement = (element: TextElement | ScrollTextElement, context: RenderContext): string =>
  element.text !== undefined ? element.text : stringifyValue(getBindingValue(context.bindings, element.bind ?? ""));

const drawStaticText = (buffer: PixelBuffer, element: TextElement, context: RenderContext): void => {
  const font = selectFont(element.font, context.settings, context.fonts);
  if (!font) return;
  drawText(
    buffer,
    font,
    textForElement(element, context),
    element.x,
    element.y,
    resolveColor(element.color, context, element.bind),
    element.align,
    element.maxWidth
  );
};

const drawScrollText = (buffer: PixelBuffer, element: ScrollTextElement, context: RenderContext): void => {
  const font = selectFont(element.font, context.settings, context.fonts);
  if (!font) return;
  const text = textForElement(element, context);
  const textWidth = measureBdfText(font, text);
  const viewport: ClipRect = {
    x: Math.trunc(element.x),
    y: -4096,
    width: Math.max(0, Math.trunc(element.width)),
    height: 8192
  };
  let origin = element.x;
  if (textWidth > viewport.width && viewport.width > 0) {
    const gap = Math.max(4, font.width);
    const cycle = textWidth + gap;
    const distance = Math.floor((Math.max(0, context.elapsedMs) / 1000) * Math.max(0, element.speedPxPerSec));
    origin = element.x - (distance % cycle);
    drawText(buffer, font, text, origin, element.y, resolveColor(element.color, context, element.bind), "left", undefined, viewport);
    if (origin + textWidth < element.x + viewport.width) {
      drawText(buffer, font, text, origin + cycle, element.y, resolveColor(element.color, context, element.bind), "left", undefined, viewport);
    }
    return;
  }
  drawText(buffer, font, text, origin, element.y, resolveColor(element.color, context, element.bind), "left", undefined, viewport);
};

const clockText = (now: Date | string | number, format: ClockElement["format"]): string => {
  if (typeof now === "string") {
    const formatted = formatWallTime(now, format);
    return formatted === "TIME TBA" ? (format === "12h" ? "12:00 AM" : "00:00") : formatted;
  }
  const date = now instanceof Date ? now : new Date(now);
  if (!Number.isFinite(date.getTime())) return format === "12h" ? "12:00 AM" : "00:00";
  const hour = date.getUTCHours();
  const minute = date.getUTCMinutes();
  if (format === "24h") return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
  const suffix = hour >= 12 ? "PM" : "AM";
  return `${hour % 12 || 12}:${String(minute).padStart(2, "0")} ${suffix}`;
};

const drawClock = (buffer: PixelBuffer, element: ClockElement, context: RenderContext): void => {
  const font = selectFont(element.font, context.settings, context.fonts);
  if (!font) return;
  drawText(
    buffer,
    font,
    clockText(context.now, element.format),
    element.x,
    element.y,
    resolveColor(element.color, context)
  );
};

const drawElement = (buffer: PixelBuffer, element: DisplayElement, context: RenderContext): void => {
  if (!visible(element, context)) return;
  switch (element.type) {
    case "text": drawStaticText(buffer, element, context); break;
    case "box": drawBox(buffer, element, context); break;
    case "line": drawLine(buffer, element, context); break;
    case "sprite": drawSprite(buffer, element, context); break;
    case "basesDiamond": drawBases(buffer, element, context); break;
    case "outsDots": drawOuts(buffer, element, context); break;
    case "countText": drawCount(buffer, element, context); break;
    case "scrollText": drawScrollText(buffer, element, context); break;
    case "clock": drawClock(buffer, element, context); break;
  }
};

export interface RenderSceneOptions {
  definition: DisplayDefinition;
  scene: SceneName;
  game?: NormalizedGameState | null;
  standings?: StandingsState | null;
  standingTeam?: StandingTeamState | null;
  logoAssetKey?: string | null;
  awayLogoAssetKey?: string | null;
  homeLogoAssetKey?: string | null;
  fonts: Readonly<Record<string, BdfFont | string>>;
  /** Selected profile dimensions. Definition content clips or leaves blank. */
  logical?: { width: number; height: number };
  overrides?: DesignOverrides;
  favorite?: boolean;
  favorites?: readonly string[];
  idleMessage?: string;
  /** Deterministic marquee position. */
  elapsedMs?: number;
  /** Deterministic clock input; defaults to the Unix epoch. */
  now?: Date | string | number;
  assets?: Readonly<Record<string, SpriteAsset>>;
  /** Current screen is held while live game data continues updating. */
  transportHeld?: boolean;
  dataFreshness?: "fresh" | "stale" | "failed" | "loading";
  dataError?: string | null;
}

/** Transparent assets are absent; dark team marks are lifted when drawn. */
const hasVisibleLogoPixels = (asset: SpriteAsset | undefined): boolean => {
  if (!asset || !("data" in asset)) return false;
  const channels = asset.data.length >= asset.width * asset.height * 4 ? 4 : 3;
  for (let offset = 0; offset + channels <= asset.data.length; offset += channels) {
    const alpha = channels === 4 ? asset.data[offset + 3] : 255;
    if (alpha > 0) return true;
  }
  return false;
};

/** Renders one scene to an ImageData-friendly, logical RGBA pixel buffer. */
export const renderScene = (options: RenderSceneOptions): PixelBuffer => {
  const settings = resolveDesignSettings(options.definition, options.overrides);
  const sceneSet = resolveSceneSet(options.definition, settings);
  const logical = options.logical ?? options.definition.targetLogical;
  const width = outputDimension(logical?.width, options.definition.targetLogical.width);
  const height = outputDimension(logical?.height, options.definition.targetLogical.height);
  const background = parseHexColor(settings.colors.background, BLACK);
  const buffer = new PixelBuffer(width, height, background);
  const game = options.game ?? null;
  const standingTeam = options.standingTeam ?? null;
  const favorites = options.favorites ?? [];
  const assets = options.assets ?? {};
  const logoAssetKey = options.logoAssetKey ?? null;
  const awayLogoAssetKey = options.awayLogoAssetKey ?? null;
  const homeLogoAssetKey = options.homeLogoAssetKey ?? null;
  const context: RenderContext = {
    definition: options.definition,
    settings,
    bindings: createBindingContext(game, {
      favorite: options.favorite,
      favorites,
      idleMessage: options.idleMessage,
      standings: options.standings,
      standingTeam,
      logoAssetKey,
      logoAvailable: !!logoAssetKey && hasVisibleLogoPixels(assets[logoAssetKey]),
      awayLogoAssetKey,
      homeLogoAssetKey,
      awayLogoAvailable: !!awayLogoAssetKey && hasVisibleLogoPixels(assets[awayLogoAssetKey]),
      homeLogoAvailable: !!homeLogoAssetKey && hasVisibleLogoPixels(assets[homeLogoAssetKey]),
      transportHeld: options.transportHeld,
      dataFreshness: options.dataFreshness,
      dataError: options.dataError
    }),
    game,
    standingTeam,
    favorites,
    fonts: normalizeFonts(options.fonts),
    assets,
    elapsedMs: Number.isFinite(options.elapsedMs) ? Math.max(0, options.elapsedMs!) : 0,
    now: options.now ?? 0
  };

  for (const element of sceneSet[options.scene]?.elements ?? []) {
    try {
      drawElement(buffer, element, context);
    } catch {
      // Imported definitions are inert data. One malformed optional element
      // cannot break the rest of a frame or execute anything.
    }
  }
  for (const element of options.definition.overlays ?? []) {
    try {
      drawElement(buffer, element, context);
    } catch {
      // Definition-owned overlays have the same inert-data boundary as scenes.
    }
  }
  return buffer;
};

/** Synonym used by consumers that treat a scene render as a video frame. */
export const renderFrame = renderScene;
