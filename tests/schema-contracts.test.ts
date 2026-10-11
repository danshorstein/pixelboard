import { readFileSync, readdirSync } from "node:fs";
import { join, resolve } from "node:path";
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { describe, expect, it } from "vitest";

const root = resolve(import.meta.dirname, "..");
const readJson = (path: string) => JSON.parse(readFileSync(path, "utf8"));

const schemaPaths = {
  project: join(root, "schemas/project.schema.json"),
  profile: join(root, "schemas/device-profile.schema.json"),
  definition: join(root, "schemas/display-definition.schema.json"),
  game: join(root, "schemas/game-state.schema.json"),
  standings: join(root, "schemas/standings-state.schema.json"),
  assets: join(root, "schemas/asset-pack.schema.json"),
  snapshot: join(root, "schemas/data-snapshot.schema.json"),
  validation: join(root, "schemas/validation-report.schema.json"),
  verification: join(root, "schemas/verification-report.schema.json"),
  manifest: join(root, "schemas/artifact-manifest.schema.json"),
  readiness: join(root, "schemas/readiness-report.schema.json")
};

const createAjv = () => {
  const ajv = new Ajv2020({ allErrors: true, strict: true, allowUnionTypes: true });
  addFormats(ajv);
  return ajv;
};

describe("versioned JSON contracts", () => {
  it("loads each schema as strict draft 2020-12 JSON Schema", () => {
    const ajv = createAjv();
    const schemas = Object.values(schemaPaths).map(readJson);
    for (const schema of schemas) {
      expect(schema.$schema).toBe("https://json-schema.org/draft/2020-12/schema");
      expect(schema.properties.schemaVersion).toBeDefined();
      expect(() => ajv.addSchema(schema)).not.toThrow();
    }
    for (const schema of schemas) {
      expect(ajv.getSchema(schema.$id)).toBeDefined();
    }
  });

  it("validates every catalog profile when profiles exist", () => {
    const directory = join(root, "targets/linux-sbc-hub75/profiles");
    let filenames: string[] = [];
    try {
      filenames = readdirSync(directory).filter((name) => name.endsWith(".json"));
    } catch {
      return;
    }

    const validate = createAjv().compile(readJson(schemaPaths.profile));
    for (const filename of filenames) {
      const value = readJson(join(directory, filename));
      expect(validate(value), `${filename}: ${JSON.stringify(validate.errors)}`).toBe(true);
    }
  });

  it("validates the curated definition when it exists", () => {
    const path = join(root, "definition/mlb-classic/display-definition.json");
    try {
      readFileSync(path);
    } catch {
      return;
    }

    const validate = createAjv().compile(readJson(schemaPaths.definition));
    expect(validate(readJson(path)), JSON.stringify(validate.errors)).toBe(true);
  });

  it("validates project and every normalized fixture when they exist", () => {
    const ajv = createAjv();
    const validateProject = ajv.compile(readJson(schemaPaths.project));
    const validateGame = ajv.compile(readJson(schemaPaths.game));
    const validateStandings = ajv.compile(readJson(schemaPaths.standings));
    const validateAssets = ajv.compile(readJson(schemaPaths.assets));
    const snapshotAjv = createAjv();
    snapshotAjv.addSchema(readJson(schemaPaths.game));
    snapshotAjv.addSchema(readJson(schemaPaths.standings));
    const validateSnapshot = snapshotAjv.compile(readJson(schemaPaths.snapshot));
    const projectPath = join(root, "fixtures/project.json");
    const demoPath = join(root, "fixtures/demo-day.json");
    const standingsPath = join(root, "fixtures/demo-standings.json");
    const assetExamplePath = join(
      root,
      "frontend/public/private-assets/team-logos/manifest.example.json"
    );

    try {
      expect(validateProject(readJson(projectPath)), JSON.stringify(validateProject.errors)).toBe(true);
      const games = readJson(demoPath);
      for (const game of games) {
        expect(validateGame(game), `${game.gameId}: ${JSON.stringify(validateGame.errors)}`).toBe(true);
      }
      const standings = readJson(standingsPath);
      for (const snapshot of standings) {
        expect(
          validateStandings(snapshot),
          `${snapshot.standingsId}: ${JSON.stringify(validateStandings.errors)}`
        ).toBe(true);
        expect(new Set(snapshot.teams.map((row: { rank: number }) => row.rank)).size)
          .toBe(snapshot.teams.length);
      }
      expect(
        validateAssets(readJson(assetExamplePath)),
        JSON.stringify(validateAssets.errors)
      ).toBe(true);
      expect(validateSnapshot({
        schemaVersion: "1.0",
        date: "2026-07-15",
        mode: "demo",
        games,
        standings,
        source: {
          provider: "bundled-fixtures",
          fetchedUtc: "2026-07-15T21:00:00Z",
          freshness: "fresh",
          refreshSec: 0,
          error: null
        }
      }), JSON.stringify(validateSnapshot.errors)).toBe(true);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
  });
});
