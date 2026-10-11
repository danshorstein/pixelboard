import { describe, expect, it } from "vitest";
import demoDayJson from "../fixtures/demo-day.json";
import expectedJson from "../fixtures/expected-playlist.json";
import expectedMixedJson from "../fixtures/expected-mixed-playlist.json";
import emptyDayJson from "../fixtures/empty-day.json";
import teamJson from "../fixtures/team-standings.json";
import standingsJson from "../fixtures/demo-standings.json";
import type {
  NormalizedGameState,
  RotationClock,
  RotationRules,
  StandingsState
} from "./models";
import { buildPlaylist, isQuietTime } from "./rotation";

const games = demoDayJson as NormalizedGameState[];
const emptyDay = emptyDayJson as NormalizedGameState[];
const standings = standingsJson as StandingsState[];
const clock: RotationClock = { nowUtc: "2026-07-15T21:00:00Z", localTime: "17:00" };
const rules: RotationRules = {
  favorites: ["WSH", "PHI"],
  favoriteDwellSec: 30,
  otherDwellSec: 12,
  liveFirst: true,
  favoritesFirst: true
};

describe("buildPlaylist", () => {
  it("matches the shared fixture contract exactly", () => {
    const actual = buildPlaylist(games, rules, clock).map((item) =>
      item.kind === "game"
        ? { gameId: item.gameId, scene: item.scene, dwellSec: item.dwellSec }
        : item
    );
    expect(actual).toEqual(expectedJson);
  });

  it("emits a deliberate idle scene for an empty schedule", () => {
    expect(buildPlaylist(emptyDay, rules, clock)).toEqual([
      { kind: "idle", gameId: null, scene: "idle", dwellSec: 12, favorite: false }
    ]);
  });

  it("pins a non-final game and releases a game that has gone final", () => {
    const liveGame = games.find((game) => game.status === "in_progress")!;
    const finalGame = games.find((game) => game.status === "final")!;
    const pinned = buildPlaylist(games, { ...rules, pinnedGameId: liveGame.gameId }, clock);
    expect(pinned).toHaveLength(1);
    expect(pinned[0]).toMatchObject({ kind: "game", gameId: liveGame.gameId });

    const released = buildPlaylist(games, { ...rules, pinnedGameId: finalGame.gameId }, clock);
    expect(released).toHaveLength(games.length);
  });

  it("handles cross-midnight quiet hours and emits the configured directive", () => {
    const quietHours = { enabled: true, start: "20:30", end: "07:00", behavior: "sleep" as const };
    expect(isQuietTime(quietHours, { ...clock, localTime: "23:45" })).toBe(true);
    expect(isQuietTime(quietHours, { ...clock, localTime: "06:59" })).toBe(true);
    expect(isQuietTime(quietHours, { ...clock, localTime: "12:00" })).toBe(false);
    expect(buildPlaylist(games, { ...rules, quietHours }, { ...clock, localTime: "21:00" })).toEqual([
      { kind: "directive", directive: "sleep", dwellSec: 0 }
    ]);
  });

  it("keeps rotating content during dim quiet hours", () => {
    const quietHours = { enabled: true, start: "21:30", end: "07:00", behavior: "dim" as const };
    const standingsRules: RotationRules = {
      ...rules,
      quietHours,
      standings: {
        enabled: true,
        divisions: ["NL East"],
        afterEveryGameScreens: 4,
        teamDwellSec: 4,
        favoriteTeamDwellSec: 6
      }
    };
    const rows = buildPlaylist(emptyDay, standingsRules, { ...clock, localTime: "22:04" }, {
      standings,
      contentMode: "standings"
    });
    expect(rows).toHaveLength(5);
    expect(rows.every((item) => item.kind === "standings")).toBe(true);
  });

  it("remains total for missing optional game fields", () => {
    const incomplete = games.find((game) => game.gameId.includes("missing-optionals"))!;
    expect(() => buildPlaylist([incomplete], rules, clock)).not.toThrow();
    expect(buildPlaylist([incomplete], rules, clock)[0]).toMatchObject({ scene: "live" });
  });

  it("does not mutate its input", () => {
    const before = JSON.stringify(games);
    buildPlaylist(games, rules, clock);
    expect(JSON.stringify(games)).toBe(before);
  });

  it("interleaves one full standings block after every four game screens", () => {
    const standingsRules: RotationRules = {
      ...rules,
      standings: {
        enabled: true,
        divisions: ["NL East"],
        afterEveryGameScreens: 4,
        teamDwellSec: 4,
        favoriteTeamDwellSec: 6
      }
    };
    const mixed = buildPlaylist(games, standingsRules, clock, { standings, contentMode: "mixed" });
    expect(mixed).toEqual(expectedMixedJson);
    expect(mixed.slice(0, 4).every((item) => item.kind === "game")).toBe(true);
    expect(mixed.slice(4, 9).map((item) => item.kind)).toEqual(Array(5).fill("standings"));
    expect(mixed.filter((item) => item.kind === "standings")).toHaveLength(10);
    expect(mixed.filter((item) => item.kind === "standings" && item.favorite)
      .every((item) => item.dwellSec === 6)).toBe(true);
  });

  it("supports a manual all-standings mode in rank order", () => {
    const standingsRules: RotationRules = {
      ...rules,
      standings: {
        enabled: true,
        divisions: ["NL East"],
        afterEveryGameScreens: 4,
        teamDwellSec: 4,
        favoriteTeamDwellSec: 6
      }
    };
    const rows = buildPlaylist(games, standingsRules, clock, { standings, contentMode: "standings" });
    expect(rows).toHaveLength(5);
    expect(rows.every((item) => item.kind === "standings")).toBe(true);
    expect(rows.map((item) => item.kind === "standings" ? item.teamId : "")).toEqual([
      "143", "121", "120", "144", "146"
    ]);
  });

  it("rotates standings instead of idle when the schedule has no games", () => {
    const standingsRules: RotationRules = {
      ...rules,
      standings: {
        enabled: true,
        divisions: ["NL East"],
        afterEveryGameScreens: 4,
        teamDwellSec: 4,
        favoriteTeamDwellSec: 6
      }
    };
    for (const contentMode of ["standings", "mixed"] as const) {
      const rows = buildPlaylist(emptyDay, standingsRules, clock, { standings, contentMode });
      expect(rows).toHaveLength(5);
      expect(rows.every((item) => item.kind === "standings")).toBe(true);
    }
  });

  it("guarantees one standings block when a short schedule never reaches the interval", () => {
    const standingsRules: RotationRules = {
      ...rules,
      standings: {
        enabled: true,
        divisions: ["NL East"],
        afterEveryGameScreens: 4,
        teamDwellSec: 4,
        favoriteTeamDwellSec: 6
      }
    };
    const shortLoop = buildPlaylist(games.slice(0, 1), standingsRules, clock, {
      standings,
      contentMode: "mixed"
    });
    expect(shortLoop.map((item) => item.kind)).toEqual(["game", ...Array(5).fill("standings")]);
  });

  it("honors ordering toggles while retaining every game", () => {
    const ordered = buildPlaylist(
      games,
      { ...rules, favoritesFirst: false, liveFirst: false },
      clock
    );
    expect(ordered).toHaveLength(games.length);
    expect(new Set(ordered.flatMap((item) => (item.kind === "game" ? [item.gameId] : []))).size).toBe(
      games.length
    );
  });
  it("keeps Pixelboard's manual row when MLB division filters are selected", () => {
    const result = buildPlaylist([], {...rules, standings:{enabled:true, divisions:['NL East'],afterEveryGameScreens:4,teamDwellSec:4,favoriteTeamDwellSec:6}}, clock,
      {standings:[...standings, ...teamJson as unknown as StandingsState[]],contentMode:'mixed'});
    expect(result.some(item => item.kind === 'standings' && item.teamId === 'sample-team')).toBe(true);
  });

});
