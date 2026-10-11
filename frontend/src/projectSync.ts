import type { ProjectDefinition } from "../../shared_ts/models";
import { migrateProject } from "./projectMigration";

export type HydrationDecision =
  | { action: "ignore" }
  | { action: "schedule-save"; project: ProjectDefinition }
  | { action: "reconcile"; project: ProjectDefinition };

/**
 * Pure decision for what a project-service response should do to local state.
 * Keeping this outside the hook makes the race/migration rules directly
 * testable without a DOM or React renderer. "reconcile" defers the actual
 * newer-version comparison to the caller, which must use the freshest local
 * project (e.g. via a functional setState updater), not a value captured
 * when the request was issued.
 */
export const decideHydration = (
  received: ProjectDefinition,
  defaults: ProjectDefinition,
  localEditPending: boolean
): HydrationDecision => {
  if (localEditPending) return { action: "ignore" };
  const { project: normalized, changed } = migrateProject(received, defaults);
  if (changed) return { action: "schedule-save", project: normalized };
  return { action: "reconcile", project: normalized };
};

/** Recovery path: keep local edits, replaying them on top of the newer server version. */
export const resolveConflictKeepingLocalChanges = (
  project: ProjectDefinition,
  conflict: ProjectDefinition
): ProjectDefinition => ({
  ...project,
  meta: { ...project.meta, version: conflict.meta.version }
});
