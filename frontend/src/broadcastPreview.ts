import type { NormalizedGameState } from "../../shared_ts/models";

export type BroadcastPreviewMoment =
  | "live"
  | "single"
  | "double"
  | "triple"
  | "homeRun"
  | "grandSlam";

export const BROADCAST_PREVIEW_MOMENTS: ReadonlyArray<{
  id: BroadcastPreviewMoment;
  label: string;
}> = [
  { id: "live", label: "Normal feed" },
  { id: "single", label: "Single" },
  { id: "double", label: "Double" },
  { id: "triple", label: "Triple" },
  { id: "homeRun", label: "Home run" },
  { id: "grandSlam", label: "Grand slam" }
];

const scoreBattingTeam = (game: NormalizedGameState, runs: number) => {
  if (game.inningHalf === "top") {
    return {
      away: { ...game.away, score: (game.away.score ?? 0) + runs },
      home: { ...game.home }
    };
  }
  return {
    away: { ...game.away },
    home: { ...game.home, score: (game.home.score ?? 0) + runs }
  };
};

/**
 * Produces an in-memory browser preview. The source game is never mutated and
 * nothing here is sent to the live feed, saved project, or Raspberry Pi.
 */
export const withBroadcastPreviewMoment = (
  game: NormalizedGameState | null,
  moment: BroadcastPreviewMoment
): NormalizedGameState | null => {
  if (!game || moment === "live") return game;

  const shared = {
    ...game,
    status: "in_progress" as const,
    lastPitch: null,
    eventRevision: `browser-preview-${moment}`
  };

  if (moment === "single") {
    return {
      ...shared,
      bases: { first: true, second: false, third: false },
      lastPlay: {
        playId: "browser-preview-single",
        event: "Single",
        eventType: "single",
        displayText: "SINGLE",
        rbi: 0,
        scoringPlay: false
      },
      battedBall: { exitVelocityMph: 96.4, launchAngleDeg: 8, trajectory: "line_drive" }
    };
  }

  if (moment === "double") {
    return {
      ...shared,
      bases: { first: false, second: true, third: false },
      lastPlay: {
        playId: "browser-preview-double",
        event: "Double",
        eventType: "double",
        displayText: "DOUBLE",
        rbi: 0,
        scoringPlay: false
      },
      battedBall: { exitVelocityMph: 101.2, launchAngleDeg: 17, trajectory: "line_drive" }
    };
  }

  if (moment === "triple") {
    return {
      ...shared,
      bases: { first: false, second: false, third: true },
      lastPlay: {
        playId: "browser-preview-triple",
        event: "Triple",
        eventType: "triple",
        displayText: "TRIPLE",
        rbi: 0,
        scoringPlay: false
      },
      battedBall: { exitVelocityMph: 103.1, launchAngleDeg: 14, trajectory: "line_drive" }
    };
  }

  const grandSlam = moment === "grandSlam";
  const runs = grandSlam ? 4 : 1;
  const scored = scoreBattingTeam(game, runs);
  return {
    ...shared,
    ...scored,
    count: { balls: 0, strikes: 0 },
    bases: { first: false, second: false, third: false },
    lastPlay: {
      playId: grandSlam ? "browser-preview-grand-slam" : "browser-preview-home-run",
      event: "Home Run",
      eventType: "home_run",
      displayText: null,
      rbi: runs,
      scoringPlay: true
    },
    battedBall: grandSlam
      ? { exitVelocityMph: 110.1, launchAngleDeg: 28, estimatedDistanceFt: 421, trajectory: "fly_ball" }
      : { exitVelocityMph: 109.3, launchAngleDeg: 27, estimatedDistanceFt: 394, trajectory: "fly_ball" }
  };
};
