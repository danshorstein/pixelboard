import { useCallback, useEffect, useRef, useState } from "react";
import type { ProjectDefinition } from "../../shared_ts/models";
import projectFixture from "../../fixtures/project.json";
import { migrateProject } from "./projectMigration";
import { decideHydration, resolveConflictKeepingLocalChanges } from "./projectSync";

const STORAGE_KEY = "scoreboard.m1.project.v1";
const defaultProject = projectFixture as ProjectDefinition;
const KNOWN_SCHEMA_VERSIONS = ["1.0", "1.1", "1.2"] as const;

const loadProject = (): { project: ProjectDefinition; changed: boolean } => {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return { project: structuredClone(defaultProject), changed: false };
    const parsed = JSON.parse(raw) as ProjectDefinition;
    if (
      !(KNOWN_SCHEMA_VERSIONS as readonly string[]).includes(parsed.schemaVersion) ||
      parsed.id !== defaultProject.id
    ) {
      return { project: structuredClone(defaultProject), changed: false };
    }
    return migrateProject(parsed, defaultProject);
  } catch {
    return { project: structuredClone(defaultProject), changed: false };
  }
};

const setNestedValue = (
  source: Record<string, unknown>,
  path: readonly string[],
  value: unknown
) => {
  const clone = structuredClone(source);
  let cursor = clone;
  for (const segment of path.slice(0, -1)) {
    const current = cursor[segment];
    if (!current || typeof current !== "object" || Array.isArray(current)) cursor[segment] = {};
    cursor = cursor[segment] as Record<string, unknown>;
  }
  cursor[path[path.length - 1]] = value;
  return clone;
};

type SaveFailureKind = "network" | "validation" | "conflict";

class ProjectSaveError extends Error {
  readonly kind: SaveFailureKind;
  readonly serverProject?: ProjectDefinition;

  constructor(kind: SaveFailureKind, message: string, serverProject?: ProjectDefinition) {
    super(message);
    this.kind = kind;
    this.serverProject = serverProject;
  }
}

export type SyncState = "local" | "saving" | "saved" | "offline" | "error";

export function useProject() {
  const initial = loadProject();
  const [project, setProject] = useState<ProjectDefinition>(initial.project);
  const [syncState, setSyncState] = useState<SyncState>("local");
  const [syncMessage, setSyncMessage] = useState("Saved in this browser");
  const [conflict, setConflict] = useState<ProjectDefinition | null>(null);
  const dirtyGeneration = useRef(initial.changed ? 1 : 0);
  // True only for a genuine in-flight user edit — never for a migration-triggered
  // autosave — so hydration still adopts/reconciles server state at mount.
  const localEditPending = useRef(false);

  const persist = useCallback(async (value: ProjectDefinition) => {
    let response: Response;
    try {
      response = await fetch(`/api/v1/projects/${encodeURIComponent(value.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(value)
      });
    } catch {
      throw new ProjectSaveError("network", "Project service unreachable");
    }
    if (response.status === 409) {
      const body = await response.json().catch(() => null) as { detail?: ProjectDefinition } | null;
      throw new ProjectSaveError("conflict", "Project was changed elsewhere", body?.detail);
    }
    if (!response.ok) {
      throw new ProjectSaveError("validation", `Project save failed (${response.status})`);
    }
    return await response.json() as ProjectDefinition;
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const hydrate = async () => {
      try {
        const response = await fetch(`/api/v1/projects/${encodeURIComponent(defaultProject.id)}`, {
          cache: "no-store",
          signal: controller.signal
        });
        if (!response.ok) throw new Error("Project service unavailable");
        const received = await response.json() as ProjectDefinition;
        if (controller.signal.aborted) return;
        const decision = decideHydration(received, defaultProject, localEditPending.current);
        if (decision.action === "ignore") return;
        if (decision.action === "schedule-save") {
          // Loading an already-current project must not issue an unsolicited
          // save, but a migrated legacy project does need to be written back —
          // route it through the single save-effect writer instead of persisting
          // here directly, so hydration and the debounced save never race.
          dirtyGeneration.current += 1;
          setProject(decision.project);
          setSyncState("saving");
          setSyncMessage("Updating saved project format…");
          return;
        }
        setProject((current) => (decision.project.meta.version > current.meta.version ? decision.project : current));
        setSyncState("saved");
        setSyncMessage("Project service connected");
      } catch {
        if (!controller.signal.aborted) {
          setSyncState("offline");
          setSyncMessage("Browser backup active · project service offline");
        }
      }
    };
    void hydrate();
    return () => controller.abort();
  }, [persist]);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(project));
    } catch {
      // Remains fully functional in-memory when browser storage is unavailable.
    }
  }, [project]);

  useEffect(() => {
    if (dirtyGeneration.current === 0 || conflict) return;
    const generation = dirtyGeneration.current;
    setSyncState("saving");
    setSyncMessage("Saving project…");
    const timer = window.setTimeout(() => {
      void persist(project).then((saved) => {
        if (dirtyGeneration.current !== generation) return;
        dirtyGeneration.current = 0;
        localEditPending.current = false;
        setProject(saved);
        setSyncState("saved");
        setSyncMessage(`Saved as version ${saved.meta.version}`);
      }).catch((error: unknown) => {
        if (dirtyGeneration.current !== generation) return;
        if (error instanceof ProjectSaveError && error.kind === "conflict") {
          localEditPending.current = false;
          setConflict(error.serverProject ?? null);
          setSyncState("error");
          setSyncMessage("Someone else changed this project on another screen · resolve to keep editing");
          return;
        }
        if (error instanceof ProjectSaveError && error.kind === "validation") {
          setSyncState("error");
          setSyncMessage("Save was rejected · check the changed values");
          return;
        }
        setSyncState("offline");
        setSyncMessage("Saved in this browser · project service offline");
      });
    }, 500);
    return () => window.clearTimeout(timer);
  }, [persist, project, conflict]);

  const updateProject = (updater: (current: ProjectDefinition) => ProjectDefinition) => {
    dirtyGeneration.current += 1;
    localEditPending.current = true;
    setProject((current) => ({
      ...updater(current),
      meta: { ...current.meta, modified: new Date().toISOString() }
    }));
  };

  return {
    project,
    syncState,
    syncMessage,
    conflict,
    /** Recovery path: keep this browser's edits, replaying them on top of the newer server version. */
    keepLocalChangesAfterConflict: () => {
      if (!conflict) return;
      setProject((current) => resolveConflictKeepingLocalChanges(current, conflict));
      setConflict(null);
      dirtyGeneration.current += 1;
    },
    /** Recovery path: discard this browser's pending edits and adopt the server's version. */
    discardLocalChangesAfterConflict: () => {
      if (!conflict) return;
      dirtyGeneration.current = 0;
      localEditPending.current = false;
      setProject(conflict);
      setConflict(null);
      setSyncState("saved");
      setSyncMessage(`Reloaded version ${conflict.meta.version}`);
    },
    selectProfile: (profileId: string) =>
      updateProject((current) => ({ ...current, profileId })),
    setDesignOverride: (path: readonly string[], value: string | boolean) =>
      updateProject((current) => ({
        ...current,
        designOverrides: setNestedValue(current.designOverrides, path, value)
      })),
    setProjectPreference: (path: readonly string[], value: string | number | boolean | string[]) =>
      updateProject((current) => setNestedValue(
        current as unknown as Record<string, unknown>,
        path,
        value
      ) as unknown as ProjectDefinition),
    resetDesignOverrides: () =>
      updateProject((current) => ({ ...current, designOverrides: {} })),
    exportProject: async () => {
      try {
        setSyncState("saving");
        setSyncMessage("Preparing portable project…");
        const saved = await persist(project);
        dirtyGeneration.current = 0;
        setProject(saved);
        const response = await fetch(`/api/v1/projects/${encodeURIComponent(saved.id)}/export`);
        if (!response.ok) throw new Error("Export failed");
        const blob = await response.blob();
        const disposition = response.headers.get("content-disposition") ?? "";
        const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `${saved.id}.zip`;
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename;
        document.body.append(anchor);
        anchor.click();
        anchor.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 0);
        setSyncState("saved");
        setSyncMessage(`Exported version ${saved.meta.version}`);
      } catch (error) {
        if (error instanceof ProjectSaveError && error.kind === "conflict") {
          setConflict(error.serverProject ?? null);
          setSyncState("error");
          setSyncMessage("Someone else changed this project on another screen · resolve to export");
          return;
        }
        setSyncState("error");
        setSyncMessage("Export needs the local project service");
      }
    },
    importProject: async (file: File) => {
      try {
        setSyncState("saving");
        setSyncMessage("Validating imported project…");
        const response = await fetch("/api/v1/projects/import", {
          method: "POST",
          headers: { "Content-Type": "application/zip" },
          body: file
        });
        if (!response.ok) throw new Error("Import failed");
        const imported = await response.json() as ProjectDefinition;
        dirtyGeneration.current = 0;
        setProject(imported);
        setSyncState("saved");
        setSyncMessage(`Imported ${imported.name} · version ${imported.meta.version}`);
      } catch {
        setSyncState("error");
        setSyncMessage("Import rejected · choose a valid Scoreboard project ZIP");
      }
    }
  };
}
