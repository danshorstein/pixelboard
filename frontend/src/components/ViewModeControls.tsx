export type ViewMode = "fit" | "zoom" | "physical";

interface ViewModeControlsProps {
  mode: ViewMode;
  zoom: number;
  grid: boolean;
  ledLook: boolean;
  calibrated: boolean;
  onModeChange: (mode: ViewMode) => void;
  onZoomChange: (zoom: number) => void;
  onGridChange: (grid: boolean) => void;
  onLedLookChange: (ledLook: boolean) => void;
}

const ZOOM_STEPS = [2, 4, 6, 8, 10, 12, 14, 16];

export function ViewModeControls({
  mode,
  zoom,
  grid,
  ledLook,
  calibrated,
  onModeChange,
  onZoomChange,
  onGridChange,
  onLedLookChange
}: ViewModeControlsProps) {
  return (
    <div className="view-controls" aria-label="Emulator view controls">
      <div className="segmented compact" aria-label="View mode">
        <button type="button" aria-pressed={mode === "fit"} onClick={() => onModeChange("fit")}>
          Fit
        </button>
        <label className={mode === "zoom" ? "select-segment active" : "select-segment"}>
          <span className="sr-only">Fixed zoom</span>
          <select
            value={zoom}
            onChange={(event) => {
              onZoomChange(Number(event.target.value));
              onModeChange("zoom");
            }}
          >
            {ZOOM_STEPS.map((step) => (
              <option key={step} value={step}>
                {step}×
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          aria-pressed={mode === "physical"}
          onClick={() => onModeChange("physical")}
        >
          1:1 <span className={calibrated ? "cal-dot good" : "cal-dot"} aria-hidden="true" />
        </button>
      </div>

      <label className="compact-toggle">
        <input type="checkbox" checked={grid} onChange={(event) => onGridChange(event.target.checked)} />
        <span>Pixel grid</span>
      </label>
      <label className="compact-toggle">
        <input
          type="checkbox"
          checked={ledLook}
          onChange={(event) => onLedLookChange(event.target.checked)}
        />
        <span>LED dots</span>
      </label>
    </div>
  );
}
