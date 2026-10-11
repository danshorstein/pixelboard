export interface ChoiceParameter {
  type: "choice";
  default: string;
  options: string[];
}

export interface ColorParameter {
  type: "color";
  default: string;
}

export interface ToggleParameter {
  type: "toggle";
  default: boolean;
}

export interface ParameterBlock {
  layoutPreset: ChoiceParameter;
  colors: Record<string, ColorParameter | ToggleParameter>;
  fonts: Record<string, ChoiceParameter>;
  elements: Record<string, boolean>;
  transition: ChoiceParameter;
}

export interface DesignOverrides {
  layoutPreset?: string;
  colors?: Record<string, string | boolean>;
  fonts?: Record<string, string>;
  elements?: Record<string, boolean>;
  transition?: string;
}

interface DesignPanelProps {
  parameters: ParameterBlock;
  overrides: DesignOverrides;
  onChange: (path: readonly string[], value: string | boolean) => void;
  onReset: () => void;
}

const LABELS: Record<string, string> = {
  layoutPreset: "Layout preset",
  background: "Background",
  scoreColor: "Score color",
  teamText: "Team text",
  statusText: "Status text",
  favoriteAccent: "Favorite accent",
  useTeamColors: "Use team colors",
  scoreFont: "Score font",
  labelFont: "Label font",
  showBases: "Show bases",
  showOuts: "Show outs",
  showCount: "Show count",
  showProbables: "Show probables",
  showClockWhenIdle: "Show idle clock",
  transition: "Screen transition"
};

const titleCase = (value: string) =>
  value
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/^./, (letter) => letter.toUpperCase());

const labelFor = (key: string) => LABELS[key] ?? titleCase(key);

export function DesignPanel({ parameters, overrides, onChange, onReset }: DesignPanelProps) {
  const changed = Object.keys(overrides).length > 0;

  return (
    <aside className="design-panel panel-card" aria-labelledby="design-panel-title">
      <div className="panel-heading compact">
        <div>
          <span className="eyebrow">Definition controls</span>
          <h2 id="design-panel-title">Design</h2>
        </div>
        <button type="button" className="button-quiet" onClick={onReset} disabled={!changed}>
          Reset
        </button>
      </div>

      <fieldset className="control-group">
        <legend>Layout</legend>
        <label className="field-stack">
          <span>{labelFor("layoutPreset")}</span>
          <select
            value={overrides.layoutPreset ?? parameters.layoutPreset.default}
            onChange={(event) => onChange(["layoutPreset"], event.target.value)}
          >
            {parameters.layoutPreset.options.map((option) => (
              <option key={option} value={option}>
                {titleCase(option)}
              </option>
            ))}
          </select>
        </label>
      </fieldset>

      <fieldset className="control-group">
        <legend>Colors</legend>
        {Object.entries(parameters.colors).map(([key, parameter]) => {
          if (parameter.type === "toggle") {
            const checked = (overrides.colors?.[key] as boolean | undefined) ?? parameter.default;
            return (
              <label className="toggle-row" key={key}>
                <span>{labelFor(key)}</span>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(event) => onChange(["colors", key], event.target.checked)}
                />
              </label>
            );
          }

          const value = (overrides.colors?.[key] as string | undefined) ?? parameter.default;
          return (
            <label className="color-row" key={key}>
              <span>{labelFor(key)}</span>
              <span className="color-control">
                <code>{value.toUpperCase()}</code>
                <input
                  type="color"
                  value={value}
                  aria-label={`${labelFor(key)} color`}
                  onChange={(event) => onChange(["colors", key], event.target.value.toUpperCase())}
                />
              </span>
            </label>
          );
        })}
      </fieldset>

      <fieldset className="control-group">
        <legend>Type</legend>
        {Object.entries(parameters.fonts).map(([key, parameter]) => (
          <label className="field-inline" key={key}>
            <span>{labelFor(key)}</span>
            <select
              value={overrides.fonts?.[key] ?? parameter.default}
              onChange={(event) => onChange(["fonts", key], event.target.value)}
            >
              {parameter.options.map((option) => (
                <option key={option} value={option}>
                  {option} BDF
                </option>
              ))}
            </select>
          </label>
        ))}
      </fieldset>

      <fieldset className="control-group">
        <legend>Elements</legend>
        {Object.entries(parameters.elements).map(([key, fallback]) => (
          <label className="toggle-row" key={key}>
            <span>{labelFor(key)}</span>
            <input
              type="checkbox"
              checked={overrides.elements?.[key] ?? fallback}
              onChange={(event) => onChange(["elements", key], event.target.checked)}
            />
          </label>
        ))}
      </fieldset>

      <fieldset className="control-group">
        <legend>Motion</legend>
        <label className="field-stack">
          <span>{labelFor("transition")}</span>
          <select
            value={overrides.transition ?? parameters.transition.default}
            onChange={(event) => onChange(["transition"], event.target.value)}
          >
            {parameters.transition.options.map((option) => (
              <option key={option} value={option}>
                {titleCase(option)}
              </option>
            ))}
          </select>
        </label>
      </fieldset>

      <p className="panel-footnote">
        Controls are generated from <code>mlb-classic@1.0</code>. Coordinates remain definition-owned.
      </p>
    </aside>
  );
}
