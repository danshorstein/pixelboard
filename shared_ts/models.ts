export type GameStatus =
  | "pregame"
  | "in_progress"
  | "final"
  | "delayed"
  | "postponed"
  | "suspended"
  | "canceled"
  | "unknown";

export type GameSceneName = "live" | "pregame" | "final" | "statusOnly";
export type SceneName = GameSceneName | "idle" | "standings";

export interface TeamState {
  id: number | string;
  abbr: string;
  name: string;
  score: number | null;
}

export interface LivePlayerState {
  id: number | string;
  name: string;
  handedness?: "L" | "R" | "S" | null;
}

export interface LastPitchState {
  eventId: string;
  call: string;
  type: string;
  code?: string | null;
  startSpeedMph?: number | null;
  endSpeedMph?: number | null;
  zone?: number | null;
}

export interface LastPlayState {
  playId: string;
  event: string;
  eventType: string;
  description?: string | null;
  displayText?: string | null;
  rbi?: number | null;
  scoringPlay?: boolean;
}

export interface BattedBallState {
  exitVelocityMph?: number | null;
  launchAngleDeg?: number | null;
  estimatedDistanceFt?: number | null;
  trajectory?: string | null;
}

export interface NormalizedGameState {
  schemaVersion: "1.0";
  gameId: string;
  gameNumber: number;
  doubleheader: boolean;
  home: TeamState;
  away: TeamState;
  status: GameStatus;
  statusDetail?: string | null;
  inning?: number | null;
  inningHalf?: "top" | "bottom" | "middle" | "end" | null;
  outs?: number | null;
  count?: { balls: number; strikes: number } | null;
  bases?: { first: boolean; second: boolean; third: boolean } | null;
  startTimeUtc: string | null;
  startTimeLocal: string | null;
  probables?: { home: string | null; away: string | null } | null;
  currentBatter?: LivePlayerState | null;
  currentPitcher?: LivePlayerState | null;
  lastPitch?: LastPitchState | null;
  lastPlay?: LastPlayState | null;
  battedBall?: BattedBallState | null;
  eventRevision?: string | null;
  venue?: string | null;
  source: {
    provider: string;
    fetchedUtc: string;
    mode: "live" | "demo" | "replay";
    freshness: "fresh" | "stale" | "failed";
  };
}

export interface StandingTeamState {
  rank: number;
  team: {
    id: number | string;
    abbr: string;
    name: string;
  };
  wins: number;
  losses: number;
  gamesBack?: number | null;
}

/** Provider-neutral standings snapshot. Rows are ordered explicitly by rank. */
export interface StandingsState {
  schemaVersion: "1.0";
  standingsId: string;
  date: string;
  league: "AL" | "NL";
  division: {
    id: number | string;
    name: string;
  };
  teams: StandingTeamState[];
  source: {
    provider: string;
    fetchedUtc: string;
    mode: "live" | "demo" | "replay";
    freshness: "fresh" | "stale" | "failed";
  };
}

export interface DataSnapshot {
  schemaVersion: "1.0";
  date: string;
  mode: "live" | "demo" | "replay";
  games: NormalizedGameState[];
  standings: StandingsState[];
  source: {
    provider: string;
    fetchedUtc: string;
    freshness: "fresh" | "stale" | "failed";
    refreshSec: number;
    error: string | null;
  };
}

export interface QuietHours {
  enabled: boolean;
  start: string;
  end: string;
  behavior: "sleep" | "dim";
}

export interface RotationRules {
  favorites: readonly string[];
  favoriteDwellSec: number;
  otherDwellSec: number;
  liveFirst: boolean;
  favoritesFirst: boolean;
  pinnedGameId?: string | null;
  quietHours?: QuietHours;
  standings?: StandingsRotationRules;
}

export interface StandingsRotationRules {
  enabled: boolean;
  divisions: readonly string[];
  afterEveryGameScreens: number;
  teamDwellSec: number;
  favoriteTeamDwellSec: number;
}

export type ContentMode = "mixed" | "games" | "standings";

export interface RotationClock {
  nowUtc: string;
  localTime: string;
}

export interface GamePlaylistItem {
  kind: "game";
  gameId: string;
  scene: GameSceneName;
  dwellSec: number;
  favorite: boolean;
}

export interface StandingsPlaylistItem {
  kind: "standings";
  standingsId: string;
  teamId: string;
  scene: "standings";
  dwellSec: number;
  favorite: boolean;
}

export interface IdlePlaylistItem {
  kind: "idle";
  gameId: null;
  scene: "idle";
  dwellSec: number;
  favorite: false;
}

export type ScenePlaylistItem =
  | GamePlaylistItem
  | StandingsPlaylistItem
  | IdlePlaylistItem;

export interface DirectivePlaylistItem {
  kind: "directive";
  directive: "sleep" | "dim";
  dwellSec: 0;
}

export type PlaylistItem = ScenePlaylistItem | DirectivePlaylistItem;

export interface ProjectBrightness {
  normal: number;
  dim: number;
}

export interface RevealSettings {
  lines: string[];
  lineDwellSec: number;
  fireworksDwellSec: number;
}

export interface RecapSettings {
  morningStartLocal: string;
  morningEndLocal: string;
  searchDays: number;
  dwellSec: number;
}

export interface ProjectDefinition {
  schemaVersion: "1.0" | "1.1" | "1.2";
  id: string;
  name: string;
  description?: string;
  profileId: string;
  displayDefinitionId: string;
  timezone?: string;
  favorites: string[];
  rotation: Omit<RotationRules, "favorites" | "quietHours">;
  data: {
    provider: string;
    mode: "live" | "demo" | "replay";
    refreshSecLive: number;
    refreshSecPregame: number;
    refreshSecIdle: number;
    rolloverLocalTime: string;
  };
  quietHours: QuietHours;
  sports?: Partial<Record<"mlb" | "nfl" | "nba" | "nhl" | "team", { enabled: boolean; teams: string[] | null }>>;
  nfl?: {
    enabled?: boolean;
    favorites?: string[];
    favoritesOnly?: boolean;
    hiddenGames?: string[];
    dwellSec?: number;
    liveFirst?: boolean;
    liveOnly?: boolean;
    hideFinal?: boolean;
    layout?: "rows" | "compact";
  };
  controllerPreferences?: { wakeDurationSec?: number };
  brightness: ProjectBrightness;
  reveal?: RevealSettings;
  recap?: RecapSettings;
  designOverrides: Record<string, unknown>;
  meta: { owner: string; version: number; modified: string };
}

export const CURRENT_PROJECT_SCHEMA_VERSION = "1.2" as const;
export const LEGACY_BRIGHTNESS_DEFAULT: ProjectBrightness = {
  normal: 35,
  dim: 10,
};

export interface DeviceProfile {
  schemaVersion: "1.0";
  id: string;
  label?: string;
  description?: string;
  targetClass: string;
  logical: { width: number; height: number };
  physical: { widthMm: number; heightMm: number; pixelPitchMm: number };
  orientation: "landscape" | "portrait" | "square";
  capabilities: {
    color: "rgb888";
    maxAnimationFps: number;
    brightnessRange: [number, number];
    memoryBudgetMb: number;
    supportedElements?: string[];
  };
  validationRules: string[];
}

export type ColorValue = string;
export type FontValue = string;

export interface DisplayElementBase {
  when?: string;
  visibleWhen?: string;
}

export interface TextElement extends DisplayElementBase {
  type: "text";
  x: number;
  y: number;
  font: FontValue;
  color: ColorValue;
  text?: string;
  bind?: string;
  align?: "left" | "center" | "right";
  maxWidth?: number;
}

export interface BoxElement extends DisplayElementBase {
  type: "box";
  x: number;
  y: number;
  width: number;
  height: number;
  color: ColorValue;
  filled?: boolean;
}

export interface LineElement extends DisplayElementBase {
  type: "line";
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  color: ColorValue;
}

export interface SpriteElement extends DisplayElementBase {
  type: "sprite";
  x: number;
  y: number;
  /** Static asset key. Exactly one of asset or bind is supplied by valid definitions. */
  asset?: string;
  /** Binding whose value resolves to an asset key, used by optional team-logo packs. */
  bind?: string;
  mode: "1bit" | "rgb";
  color?: ColorValue;
}

export interface BasesDiamondElement extends DisplayElementBase {
  type: "basesDiamond";
  x: number;
  y: number;
  bind: string;
  color: ColorValue;
  occupiedColor: ColorValue;
  size?: number;
}

export interface OutsDotsElement extends DisplayElementBase {
  type: "outsDots";
  x: number;
  y: number;
  bind: string;
  color: ColorValue;
  activeColor: ColorValue;
  spacing?: number;
}

export interface CountTextElement extends DisplayElementBase {
  type: "countText";
  x: number;
  y: number;
  bind: string;
  font: FontValue;
  color: ColorValue;
  prefix?: string;
}

export interface ScrollTextElement extends DisplayElementBase {
  type: "scrollText";
  x: number;
  y: number;
  width: number;
  font: FontValue;
  color: ColorValue;
  speedPxPerSec: number;
  text?: string;
  bind?: string;
}

export interface ClockElement extends DisplayElementBase {
  type: "clock";
  x: number;
  y: number;
  font: FontValue;
  color: ColorValue;
  format: "12h" | "24h";
}

/** The complete, intentionally small M1 renderer vocabulary. */
export type DisplayElement =
  | TextElement
  | BoxElement
  | LineElement
  | SpriteElement
  | BasesDiamondElement
  | OutsDotsElement
  | CountTextElement
  | ScrollTextElement
  | ClockElement;

export interface DisplayScene {
  elements: DisplayElement[];
}

export interface DisplaySceneSet {
  live: DisplayScene;
  pregame: DisplayScene;
  final: DisplayScene;
  statusOnly: DisplayScene;
  idle: DisplayScene;
  standings?: DisplayScene;
}

export interface ChoiceParameter {
  type: "choice";
  default: string;
  options: string[];
}

export interface ColorParameter {
  type: "color";
  default: string;
}

export interface ToggleParameter {
  type: "toggle";
  default: boolean;
}

export interface DisplayParameters {
  layoutPreset: ChoiceParameter;
  colors: {
    background: ColorParameter;
    scoreColor: ColorParameter;
    teamText: ColorParameter;
    statusText: ColorParameter;
    favoriteAccent: ColorParameter;
    useTeamColors: ToggleParameter;
  };
  fonts: {
    scoreFont: ChoiceParameter;
    labelFont: ChoiceParameter;
  };
  elements: {
    showBases: boolean;
    showOuts: boolean;
    showCount: boolean;
    showProbables: boolean;
    showClockWhenIdle: boolean;
  };
  transition: ChoiceParameter;
}

export interface DisplayDefinition {
  schemaVersion: "1.0" | "1.1" | "1.2";
  id: string;
  version: string;
  targetLogical: { width: number; height: number };
  parameters: DisplayParameters;
  teamColors?: Record<string, string>;
  scenes: DisplaySceneSet;
  presets?: Record<string, DisplaySceneSet>;
  overlays?: DisplayElement[];
}

export interface DesignOverrides {
  layoutPreset?: unknown;
  colors?: Record<string, unknown>;
  fonts?: Record<string, unknown>;
  elements?: Record<string, unknown>;
  transition?: unknown;
  [key: string]: unknown;
}
