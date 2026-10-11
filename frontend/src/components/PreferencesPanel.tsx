import type { ProjectDefinition } from "../../../shared_ts/models";

interface PreferencesPanelProps {
  project: ProjectDefinition;
  onChange: (path: readonly string[], value: string | number | boolean | string[]) => void;
  /** Division names actually seen in loaded standings, plus whatever the
   *  project has saved — a hand-typed label that doesn't byte-match a
   *  fetched division name silently filters standings to nothing. */
  divisionOptions: readonly string[];
}

const MLB_TEAMS = [
  "ARI", "ATH", "ATL", "BAL", "BOS", "CHC", "CWS", "CIN", "CLE", "COL",
  "DET", "HOU", "KC", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", "NYY",
  "PHI", "PIT", "SD", "SEA", "SF", "STL", "TB", "TEX", "TOR", "WSH"
] as const;

const TIMEZONES = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Phoenix",
  "America/Los_Angeles",
  "America/Anchorage",
  "Pacific/Honolulu"
] as const;

const boundedInteger = (value: string, minimum: number, maximum: number, fallback: number) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(minimum, Math.min(maximum, Math.round(parsed))) : fallback;
};

export function PreferencesPanel({ project, onChange, divisionOptions }: PreferencesPanelProps) {
  const standings = project.rotation.standings;
  const savedTimezone = project.timezone ?? "America/New_York";
  const timezoneChoices = TIMEZONES.includes(savedTimezone as (typeof TIMEZONES)[number])
    ? TIMEZONES
    : [savedTimezone, ...TIMEZONES];
  const selectedDivisions = standings?.divisions ?? [];
  const toggleDivision = (name: string) => {
    if (!standings) return;
    const next = selectedDivisions.includes(name)
      ? selectedDivisions.filter((candidate) => candidate !== name)
      : [...selectedDivisions, name];
    onChange(["rotation", "standings", "divisions"], next);
  };
  const toggleFavorite = (abbr: string) => {
    const selected = project.favorites.includes(abbr);
    if (selected && project.favorites.length === 1) return;
    const favorites = selected
      ? project.favorites.filter((candidate) => candidate !== abbr)
      : [...project.favorites, abbr];
    onChange(["favorites"], favorites);
  };

  return (
    <section className="panel-card preferences-panel" aria-labelledby="preferences-title">
      <div className="panel-heading compact">
        <div>
          <span className="eyebrow">Dashboard controls</span>
          <h2 id="preferences-title">Scoreboard preferences</h2>
        </div>
        <span className="status-pill good">Auto-save</span>
      </div>

      <details open>
        <summary>Favorite teams</summary>
        <p className="settings-help">Favorites get priority and a longer screen time. Keep at least one selected.</p>
        <div className="team-toggle-grid">
          {MLB_TEAMS.map((abbr) => {
            const selected = project.favorites.includes(abbr);
            return (
              <button
                type="button"
                key={abbr}
                className={selected ? "team-toggle is-selected" : "team-toggle"}
                aria-pressed={selected}
                title={selected && project.favorites.length === 1 ? "At least one favorite is required" : undefined}
                onClick={() => toggleFavorite(abbr)}
              >
                {abbr}
              </button>
            );
          })}
        </div>
      </details>

      <details>
        <summary>Rotation and standings</summary>
        <div className="settings-grid">
          <label className="field-stack">
            <span>Favorite screen seconds</span>
            <input
              type="number"
              min="1"
              max="300"
              value={project.rotation.favoriteDwellSec}
              onChange={(event) => onChange(["rotation", "favoriteDwellSec"], boundedInteger(event.target.value, 1, 300, 30))}
            />
          </label>
          <label className="field-stack">
            <span>Other screen seconds</span>
            <input
              type="number"
              min="1"
              max="300"
              value={project.rotation.otherDwellSec}
              onChange={(event) => onChange(["rotation", "otherDwellSec"], boundedInteger(event.target.value, 1, 300, 12))}
            />
          </label>
          <label className="toggle-row settings-span">
            <span>Live games first</span>
            <input type="checkbox" checked={project.rotation.liveFirst} onChange={(event) => onChange(["rotation", "liveFirst"], event.target.checked)} />
          </label>
          <label className="toggle-row settings-span">
            <span>Favorites first</span>
            <input type="checkbox" checked={project.rotation.favoritesFirst} onChange={(event) => onChange(["rotation", "favoritesFirst"], event.target.checked)} />
          </label>
          {standings ? (
            <>
              <label className="toggle-row settings-span">
                <span>Include standings</span>
                <input type="checkbox" checked={standings.enabled} onChange={(event) => onChange(["rotation", "standings", "enabled"], event.target.checked)} />
              </label>
              <label className="field-stack settings-span">
                <span>Show standings after this many game screens</span>
                <input
                  type="number"
                  min="1"
                  max="30"
                  value={standings.afterEveryGameScreens}
                  onChange={(event) => onChange(["rotation", "standings", "afterEveryGameScreens"], boundedInteger(event.target.value, 1, 30, 4))}
                />
              </label>
              <div className="field-stack settings-span">
                <span>Divisions in rotation</span>
                <p className="settings-help">Only divisions present in the loaded standings can be shown.</p>
                <div className="team-toggle-grid">
                  {divisionOptions.map((name) => {
                    const selected = selectedDivisions.includes(name);
                    return (
                      <button
                        type="button"
                        key={name}
                        className={selected ? "team-toggle is-selected" : "team-toggle"}
                        aria-pressed={selected}
                        onClick={() => toggleDivision(name)}
                      >
                        {name}
                      </button>
                    );
                  })}
                  {divisionOptions.length === 0 ? (
                    <span className="settings-help">No standings loaded yet.</span>
                  ) : null}
                </div>
              </div>
              <label className="field-stack">
                <span>Standings card seconds</span>
                <input
                  type="number"
                  min="1"
                  max="60"
                  value={standings.teamDwellSec}
                  onChange={(event) => onChange(["rotation", "standings", "teamDwellSec"], boundedInteger(event.target.value, 1, 60, 4))}
                />
              </label>
              <label className="field-stack">
                <span>Favorite team card seconds</span>
                <input
                  type="number"
                  min="1"
                  max="60"
                  value={standings.favoriteTeamDwellSec}
                  onChange={(event) => onChange(["rotation", "standings", "favoriteTeamDwellSec"], boundedInteger(event.target.value, 1, 60, 6))}
                />
              </label>
            </>
          ) : null}
        </div>
      </details>

      <details>
        <summary>Display and time zone</summary>
        <div className="settings-grid">
          <label className="field-stack settings-span">
            <span>Time zone</span>
            <select value={savedTimezone} onChange={(event) => onChange(["timezone"], event.target.value)}>
              {timezoneChoices.map((zone) => (
                <option key={zone} value={zone}>
                  {zone}
                </option>
              ))}
            </select>
          </label>
          <label className="field-stack">
            <span>Normal brightness (%)</span>
            <input
              type="number"
              min="1"
              max="100"
              value={project.brightness.normal}
              onChange={(event) => onChange(["brightness", "normal"], boundedInteger(event.target.value, 1, 100, 35))}
            />
          </label>
          <label className="field-stack">
            <span>Quiet-hours dim brightness (%)</span>
            <input
              type="number"
              min="1"
              max="100"
              value={project.brightness.dim}
              onChange={(event) => onChange(["brightness", "dim"], boundedInteger(event.target.value, 1, 100, 10))}
            />
          </label>
          <p className="settings-help settings-span">
            The device uses these values; a legacy device without them in its project falls back to its
            installed runtime configuration.
          </p>
        </div>
      </details>

      <details>
        <summary>Refresh timing</summary>
        <div className="settings-grid">
          <label className="field-stack">
            <span>Live game seconds</span>
            <input type="number" min="5" max="300" value={project.data.refreshSecLive} onChange={(event) => onChange(["data", "refreshSecLive"], boundedInteger(event.target.value, 5, 300, 10))} />
          </label>
          <label className="field-stack">
            <span>Pregame seconds</span>
            <input type="number" min="5" max="3600" value={project.data.refreshSecPregame} onChange={(event) => onChange(["data", "refreshSecPregame"], boundedInteger(event.target.value, 5, 3600, 60))} />
          </label>
          <label className="field-stack">
            <span>Idle seconds</span>
            <input type="number" min="5" max="86400" value={project.data.refreshSecIdle} onChange={(event) => onChange(["data", "refreshSecIdle"], boundedInteger(event.target.value, 5, 86400, 300))} />
          </label>
          <label className="field-stack">
            <span>Baseball-day rollover</span>
            <input type="time" value={project.data.rolloverLocalTime} onChange={(event) => onChange(["data", "rolloverLocalTime"], event.target.value)} />
          </label>
        </div>
      </details>

      <details>
        <summary>Quiet hours</summary>
        <div className="settings-grid">
          <label className="toggle-row settings-span">
            <span>Enable quiet hours</span>
            <input type="checkbox" checked={project.quietHours.enabled} onChange={(event) => onChange(["quietHours", "enabled"], event.target.checked)} />
          </label>
          <label className="field-stack">
            <span>Start</span>
            <input type="time" value={project.quietHours.start} onChange={(event) => onChange(["quietHours", "start"], event.target.value)} />
          </label>
          <label className="field-stack">
            <span>End</span>
            <input type="time" value={project.quietHours.end} onChange={(event) => onChange(["quietHours", "end"], event.target.value)} />
          </label>
          <label className="field-stack settings-span">
            <span>Behavior</span>
            <select value={project.quietHours.behavior} onChange={(event) => onChange(["quietHours", "behavior"], event.target.value)}>
              <option value="dim">Dim the display</option>
              <option value="sleep">Turn the display off</option>
            </select>
          </label>
        </div>
      </details>

      <p className="panel-footnote">Changes update the browser preview immediately and save to the project service when it is connected.</p>
    </section>
  );
}
