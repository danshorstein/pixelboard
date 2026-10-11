import type { ProjectDefinition } from "../../shared_ts/models";
import { CURRENT_PROJECT_SCHEMA_VERSION, LEGACY_BRIGHTNESS_DEFAULT } from "../../shared_ts/models";

export interface MigrationResult {
  project: ProjectDefinition;
  changed: boolean;
}

/**
 * Pure, versioned project normalization. Fills in fields missing from an
 * older schema version using the current default project as a source of
 * fallbacks, but never overwrites a present, valid saved value. Reports
 * whether anything actually changed so callers can decide whether the
 * result needs to be persisted.
 */
export const migrateProject = (
  parsed: ProjectDefinition,
  defaults: ProjectDefinition
): MigrationResult => {
  const before = JSON.stringify(parsed);

  const rotation = {
    ...defaults.rotation,
    ...parsed.rotation,
    standings: parsed.rotation.standings ?? defaults.rotation.standings
  };

  const brightness = parsed.brightness
    ? { ...LEGACY_BRIGHTNESS_DEFAULT, ...parsed.brightness }
    : { ...LEGACY_BRIGHTNESS_DEFAULT };

  const migrated: ProjectDefinition = {
    ...parsed,
    schemaVersion: CURRENT_PROJECT_SCHEMA_VERSION,
    displayDefinitionId: parsed.displayDefinitionId ?? defaults.displayDefinitionId,
    data: { ...defaults.data, ...parsed.data },
    quietHours: { ...defaults.quietHours, ...parsed.quietHours },
    brightness,
    rotation
  };

  return { project: migrated, changed: JSON.stringify(migrated) !== before };
};
