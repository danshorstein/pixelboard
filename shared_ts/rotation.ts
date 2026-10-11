import type {
  ContentMode,
  GameStatus,
  GameSceneName,
  NormalizedGameState,
  PlaylistItem,
  RotationClock,
  RotationRules,
  GamePlaylistItem,
  IdlePlaylistItem,
  ScenePlaylistItem,
  StandingsPlaylistItem,
  StandingsState
} from "./models";

const STATUS_RANK: Record<GameStatus, number> = {
  in_progress: 0,
  pregame: 1,
  final: 2,
  delayed: 3,
  postponed: 3,
  suspended: 3,
  canceled: 3,
  unknown: 3
};

const STATUS_SCENE: Record<GameStatus, GameSceneName> = {
  in_progress: "live",
  pregame: "pregame",
  final: "final",
  delayed: "statusOnly",
  postponed: "statusOnly",
  suspended: "statusOnly",
  canceled: "statusOnly",
  unknown: "statusOnly"
};

const parseMinutes = (value: string): number | null => {
  const match = /^(\d{2}):(\d{2})$/.exec(value);
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour > 23 || minute > 59) return null;
  return hour * 60 + minute;
};

export const isQuietTime = (
  quietHours: RotationRules["quietHours"],
  clock: RotationClock
): boolean => {
  if (!quietHours?.enabled) return false;
  const now = parseMinutes(clock.localTime);
  const start = parseMinutes(quietHours.start);
  const end = parseMinutes(quietHours.end);
  if (now === null || start === null || end === null || start === end) return false;
  return start < end ? now >= start && now < end : now >= start || now < end;
};

export const sceneForStatus = (status: GameStatus): GameSceneName => STATUS_SCENE[status];

const isFavoriteGame = (game: NormalizedGameState, favorites: ReadonlySet<string>) =>
  favorites.has(game.home.abbr) || favorites.has(game.away.abbr);

const startKey = (game: NormalizedGameState) => {
  if (!game.startTimeUtc) return Number.POSITIVE_INFINITY;
  const value = Date.parse(game.startTimeUtc);
  return Number.isFinite(value) ? value : Number.POSITIVE_INFINITY;
};

const compareStrings = (left: string, right: string) =>
  left < right ? -1 : left > right ? 1 : 0;

const safeDwell = (value: number) =>
  Number.isFinite(value) && value > 0 ? Math.max(1, Math.trunc(value)) : 1;

const toGameItem = (
  game: NormalizedGameState,
  rules: RotationRules,
  favorites: ReadonlySet<string>
): GamePlaylistItem => {
  const favorite = isFavoriteGame(game, favorites);
  return {
    kind: "game",
    gameId: game.gameId,
    scene: STATUS_SCENE[game.status] ?? "statusOnly",
    dwellSec: safeDwell(favorite ? rules.favoriteDwellSec : rules.otherDwellSec),
    favorite
  };
};

const idleItem = (rules: RotationRules): IdlePlaylistItem => ({
  kind: "idle",
  gameId: null,
  scene: "idle",
  dwellSec: safeDwell(rules.otherDwellSec),
  favorite: false
});

const toStandingsItems = (
  snapshots: readonly StandingsState[],
  rules: RotationRules,
  favorites: ReadonlySet<string>
): StandingsPlaylistItem[] => {
  const config = rules.standings;
  if (!config) return [];
  const divisions = new Set(config.divisions);
  return [...snapshots]
    .filter((snapshot) => divisions.size === 0 || divisions.has(snapshot.division.name) || snapshot.source.provider === "local-manual")
    .sort((left, right) =>
      compareStrings(left.league, right.league) ||
      compareStrings(left.division.name, right.division.name) ||
      compareStrings(left.standingsId, right.standingsId)
    )
    .flatMap((snapshot) =>
      [...snapshot.teams]
        .sort((left, right) => left.rank - right.rank || compareStrings(left.team.abbr, right.team.abbr))
        .map((row) => {
          const favorite = favorites.has(row.team.abbr);
          return {
            kind: "standings" as const,
            standingsId: snapshot.standingsId,
            teamId: String(row.team.id),
            scene: "standings" as const,
            dwellSec: safeDwell(favorite ? config.favoriteTeamDwellSec : config.teamDwellSec),
            favorite
          };
        })
    );
};

const interleaveStandings = (
  games: readonly GamePlaylistItem[],
  standings: readonly StandingsPlaylistItem[],
  afterEvery: number
): ScenePlaylistItem[] => {
  if (standings.length === 0) return [...games];
  if (games.length === 0) return [...standings];
  const interval = Math.max(1, Math.trunc(afterEvery));
  const mixed: ScenePlaylistItem[] = [];
  let insertedStandings = false;
  games.forEach((game, index) => {
    mixed.push(game);
    if ((index + 1) % interval === 0) {
      mixed.push(...standings);
      insertedStandings = true;
    }
  });
  if (!insertedStandings) mixed.push(...standings);
  return mixed;
};

export interface BuildPlaylistOptions {
  standings?: readonly StandingsState[];
  contentMode?: ContentMode;
}

/**
 * Deterministically turns normalized game-state data into the emulator/device
 * playlist contract. The input array and its game objects are never mutated.
 */
export const buildPlaylist = (
  gameStates: readonly NormalizedGameState[],
  rules: RotationRules,
  clock: RotationClock,
  options: BuildPlaylistOptions = {}
): PlaylistItem[] => {
  if (isQuietTime(rules.quietHours, clock) && rules.quietHours?.behavior === "sleep") {
    return [{ kind: "directive", directive: rules.quietHours!.behavior, dwellSec: 0 }];
  }

  const favorites = new Set(rules.favorites);
  const pinned = rules.pinnedGameId
    ? gameStates.find((game) => game.gameId === rules.pinnedGameId && game.status !== "final")
    : undefined;

  if (pinned) return [toGameItem(pinned, rules, favorites)];

  const ordered = [...gameStates].sort((left, right) => {
    if (rules.favoritesFirst) {
      const favoriteDifference =
        Number(isFavoriteGame(right, favorites)) - Number(isFavoriteGame(left, favorites));
      if (favoriteDifference !== 0) return favoriteDifference;
    }

    if (rules.liveFirst) {
      const statusDifference =
        (STATUS_RANK[left.status] ?? 3) - (STATUS_RANK[right.status] ?? 3);
      if (statusDifference !== 0) return statusDifference;
    }

    const timeDifference = startKey(left) - startKey(right);
    if (Number.isFinite(timeDifference) && timeDifference !== 0) return timeDifference;

    const gameNumberDifference = left.gameNumber - right.gameNumber;
    if (gameNumberDifference !== 0) return gameNumberDifference;
    return compareStrings(left.gameId, right.gameId);
  });

  const gameItems = ordered.map((game) => toGameItem(game, rules, favorites));
  const standingsItems = toStandingsItems(options.standings ?? [], rules, favorites);
  const mode = options.contentMode ?? "games";

  if (mode === "standings") return standingsItems.length > 0 ? standingsItems : [idleItem(rules)];
  if (mode === "games" || !rules.standings?.enabled) {
    return gameItems.length > 0 ? gameItems : [idleItem(rules)];
  }
  const mixed = interleaveStandings(
    gameItems,
    standingsItems,
    rules.standings.afterEveryGameScreens
  );
  return mixed.length > 0 ? mixed : [idleItem(rules)];
};
