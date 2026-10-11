import { describe, expect, it } from "vitest";
import type { ProjectDefinition } from "../../shared_ts/models";
import { migrateProject } from "./projectMigration";
import defaultProjectFixture from "../../fixtures/project.json";

const defaults = defaultProjectFixture as ProjectDefinition;

describe("migrateProject", () => {
  it("does not touch an already-current project and reports unchanged", () => {
    const { project, changed } = migrateProject(structuredClone(defaults), defaults);
    expect(changed).toBe(false);
    expect(project).toEqual(defaults);
  });

  it("preserves saved quiet-hour and data preferences instead of resetting them to defaults", () => {
    const legacy: ProjectDefinition = {
      ...structuredClone(defaults),
      schemaVersion: "1.1",
      quietHours: { enabled: true, start: "23:00", end: "06:00", behavior: "sleep" },
      data: { ...defaults.data, refreshSecLive: 42 }
    };
    delete (legacy as { brightness?: unknown }).brightness;

    const { project, changed } = migrateProject(legacy, defaults);

    expect(changed).toBe(true);
    expect(project.quietHours).toEqual({ enabled: true, start: "23:00", end: "06:00", behavior: "sleep" });
    expect(project.data.refreshSecLive).toBe(42);
    expect(project.schemaVersion).toBe("1.2");
  });

  it("fills in missing brightness from legacy defaults without touching a present value", () => {
    const legacyMissing = structuredClone(defaults);
    delete (legacyMissing as { brightness?: unknown }).brightness;
    const { project: filled } = migrateProject(legacyMissing, defaults);
    expect(filled.brightness).toEqual({ normal: 35, dim: 10 });

    const custom = { ...structuredClone(defaults), brightness: { normal: 80, dim: 5 } };
    const { project: preserved, changed } = migrateProject(custom, defaults);
    expect(preserved.brightness).toEqual({ normal: 80, dim: 5 });
    expect(changed).toBe(false);
  });

  it("preserves a customized rotation.standings block instead of replacing it", () => {
    const customized: ProjectDefinition = {
      ...structuredClone(defaults),
      rotation: {
        ...defaults.rotation,
        standings: {
          enabled: true,
          divisions: ["AL East"],
          afterEveryGameScreens: 7,
          teamDwellSec: 9,
          favoriteTeamDwellSec: 11
        }
      }
    };
    const { project } = migrateProject(customized, defaults);
    expect(project.rotation.standings).toEqual({
      enabled: true,
      divisions: ["AL East"],
      afterEveryGameScreens: 7,
      teamDwellSec: 9,
      favoriteTeamDwellSec: 11
    });
  });
});
