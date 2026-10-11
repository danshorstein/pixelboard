import type { ProjectDefinition } from "../../shared_ts/models";

export interface RotationDescriptionInput {
  /** How many screens the current playlist actually resolved to. */
  playlistLength: number;
  /** Whether standings data is actually loaded (a live-fetch failure means
   *  the rotation cannot show standings even if they're enabled). */
  standingsAvailable: boolean;
}

const joinTeams = (teams: readonly string[]): string => {
  if (teams.length === 0) return "favorites";
  if (teams.length === 1) return teams[0];
  if (teams.length === 2) return `${teams[0]} and ${teams[1]}`;
  return `${teams.slice(0, -1).join(", ")}, and ${teams[teams.length - 1]}`;
};

const screens = (count: number): string => `${count} screen${count === 1 ? "" : "s"}`;

/**
 * Human summary of the rotation, generated from the project settings and the
 * resolved playlist — never hardcoded. Replaces the fixed "four game screens,
 * then the full NL East / Washington and Philadelphia get longer cards" copy,
 * which lied whenever those settings were changed.
 */
export const describeRotation = (
  project: ProjectDefinition,
  { playlistLength, standingsAvailable }: RotationDescriptionInput
): string => {
  const standings = project.rotation.standings;
  const favorites = joinTeams(project.favorites);
  const total = `${screens(playlistLength)} in rotation`;

  if (!standings || !standings.enabled) {
    return `Games only — ${favorites} first, then the rest of the day. ${screens(playlistLength)} in rotation.`;
  }

  if (!standingsAvailable) {
    return `Games first, then the ${joinTeams(standings.divisions)} standings once that data loads. ${total}.`;
  }

  const every = standings.afterEveryGameScreens;
  const cadence =
    every === 1
      ? "After every game screen"
      : `After every ${every} game screens`;
  const divisions =
    standings.divisions.length > 0 ? joinTeams(standings.divisions) : "division";
  const longerCards =
    standings.favoriteTeamDwellSec > standings.teamDwellSec
      ? ` ${favorites} get longer standings cards (${standings.favoriteTeamDwellSec}s vs ${standings.teamDwellSec}s).`
      : "";

  return `${cadence}, the ${divisions} standings run in rank order.${longerCards} ${total}.`;
};
