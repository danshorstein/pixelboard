import { describe, expect, it } from "vitest";
import type { ProjectDefinition } from "../../shared_ts/models";
import { decideHydration, resolveConflictKeepingLocalChanges } from "./projectSync";
import defaultProjectFixture from "../../fixtures/project.json";

const defaults = defaultProjectFixture as ProjectDefinition;

describe("decideHydration", () => {
  it("ignores the server response while a local edit is in flight", () => {
    const decision = decideHydration(structuredClone(defaults), defaults, true);
    expect(decision.action).toBe("ignore");
  });

  it("schedules exactly one save through the normal writer when the server project needs migration", () => {
    const legacy: ProjectDefinition = { ...structuredClone(defaults), schemaVersion: "1.1" };
    delete (legacy as { brightness?: unknown }).brightness;
    const decision = decideHydration(legacy, defaults, false);
    expect(decision.action).toBe("schedule-save");
    if (decision.action === "schedule-save") {
      expect(decision.project.brightness).toEqual({ normal: 35, dim: 10 });
    }
  });

  it("reconciles without persisting when the server project is already current", () => {
    const decision = decideHydration(structuredClone(defaults), defaults, false);
    expect(decision.action).toBe("reconcile");
  });
});

describe("resolveConflictKeepingLocalChanges", () => {
  it("rebase's the local project onto the server's newer version without discarding local edits", () => {
    const local: ProjectDefinition = { ...structuredClone(defaults), name: "Edited locally" };
    const serverConflict: ProjectDefinition = { ...structuredClone(defaults), meta: { ...defaults.meta, version: defaults.meta.version + 3 } };
    const resolved = resolveConflictKeepingLocalChanges(local, serverConflict);
    expect(resolved.name).toBe("Edited locally");
    expect(resolved.meta.version).toBe(serverConflict.meta.version);
  });
});
