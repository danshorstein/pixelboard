import { describe, expect, it } from "vitest";
import projectFixture from "../../fixtures/project.json";
import type { ProjectDefinition } from "../../shared_ts/models";
import { describeRotation } from "./describeRotation";

const base = projectFixture as ProjectDefinition;

const withRotation = (rotation: Partial<ProjectDefinition["rotation"]>): ProjectDefinition => ({
  ...base,
  rotation: { ...base.rotation, ...rotation }
});

describe("describeRotation", () => {
  it("does not hardcode NL East or a four-game cadence", () => {
    const text = describeRotation(base, { playlistLength: 12, standingsAvailable: true });
    expect(text).toContain("NL East");
    expect(text).toContain("every 4 game screens");

    const changed = describeRotation(
      withRotation({
        standings: { ...base.rotation.standings!, divisions: ["AL West"], afterEveryGameScreens: 2 }
      }),
      { playlistLength: 10, standingsAvailable: true }
    );
    expect(changed).toContain("AL West");
    expect(changed).toContain("every 2 game screens");
    expect(changed).not.toContain("NL East");
  });

  it("says games-only when standings are disabled", () => {
    const text = describeRotation(
      withRotation({ standings: { ...base.rotation.standings!, enabled: false } }),
      { playlistLength: 8, standingsAvailable: true }
    );
    expect(text).toContain("Games only");
    expect(text).not.toContain("rank order");
  });

  it("does not claim standings are shown when the data is unavailable", () => {
    const text = describeRotation(base, { playlistLength: 6, standingsAvailable: false });
    expect(text).toContain("once that data loads");
    expect(text).not.toContain("rank order");
  });

  it("mentions longer favorite cards only when the favorite dwell is actually longer", () => {
    const longer = describeRotation(base, { playlistLength: 12, standingsAvailable: true });
    expect(longer).toContain("longer standings cards");

    const equal = describeRotation(
      withRotation({
        standings: { ...base.rotation.standings!, teamDwellSec: 5, favoriteTeamDwellSec: 5 }
      }),
      { playlistLength: 12, standingsAvailable: true }
    );
    expect(equal).not.toContain("longer standings cards");
  });

  it("reflects the favorites list rather than assuming two teams", () => {
    const one = describeRotation({ ...base, favorites: ["WSH"] }, { playlistLength: 12, standingsAvailable: true });
    expect(one).toContain("WSH get longer");
    expect(one).not.toContain("and PHI");

    const three = describeRotation(
      { ...base, favorites: ["WSH", "PHI", "NYM"] },
      { playlistLength: 12, standingsAvailable: true }
    );
    expect(three).toContain("WSH, PHI, and NYM");
  });

  it("singularizes a one-screen rotation", () => {
    const text = describeRotation(
      withRotation({ standings: { ...base.rotation.standings!, enabled: false } }),
      { playlistLength: 1, standingsAvailable: false }
    );
    expect(text).toContain("1 screen in rotation");
    expect(text).not.toContain("1 screens");
  });
});
