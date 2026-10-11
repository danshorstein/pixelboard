import { useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import {
  CREDIT_CARD_WIDTH_MM,
  calibrationFromCard,
  calibrationFromMonitor,
  type CalibrationRecord
} from "../calibration";

interface CalibrationPanelProps {
  open: boolean;
  current: CalibrationRecord | null;
  onClose: () => void;
  onSave: (pxPerMm: number, method: CalibrationRecord["method"]) => void;
  onClear: () => void;
}

export function CalibrationPanel({
  open,
  current,
  onClose,
  onSave,
  onClear
}: CalibrationPanelProps) {
  const [method, setMethod] = useState<CalibrationRecord["method"]>("card");
  const [cardWidth, setCardWidth] = useState(324);
  const [diagonal, setDiagonal] = useState(24);
  const [resolutionWidth, setResolutionWidth] = useState(
    Math.round(window.screen.width * window.devicePixelRatio)
  );
  const [resolutionHeight, setResolutionHeight] = useState(
    Math.round(window.screen.height * window.devicePixelRatio)
  );
  const dragStart = useRef<{ x: number; width: number } | null>(null);

  if (!open) return null;

  const cardPxPerMm = calibrationFromCard(cardWidth);
  const monitorPxPerMm = calibrationFromMonitor(
    diagonal,
    resolutionWidth,
    resolutionHeight,
    window.devicePixelRatio || 1
  );
  const candidate = method === "card" ? cardPxPerMm : monitorPxPerMm;

  const beginDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    dragStart.current = { x: event.clientX, width: cardWidth };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const continueDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (!dragStart.current) return;
    const width = dragStart.current.width + event.clientX - dragStart.current.x;
    setCardWidth(Math.max(180, Math.min(520, width)));
  };

  const endDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    dragStart.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  return (
    <div className="sheet-backdrop">
      <section
        className="calibration-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="calibration-title"
      >
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Physical preview</span>
            <h2 id="calibration-title">Calibrate this screen</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close calibration">
            ×
          </button>
        </div>

        <p className="helper-copy">
          This converts CSS pixels into millimeters. Recalibrate after moving the window to another
          monitor or changing display scaling.
        </p>

        <div className="segmented" aria-label="Calibration method">
          <button
            type="button"
            aria-pressed={method === "card"}
            onClick={() => setMethod("card")}
          >
            Credit card
          </button>
          <button
            type="button"
            aria-pressed={method === "monitor"}
            onClick={() => setMethod("monitor")}
          >
            Monitor specs
          </button>
        </div>

        {method === "card" ? (
          <div className="calibration-card-area">
            <p>
              Hold a standard card against the screen. Drag the right edge until both widths match
              ({CREDIT_CARD_WIDTH_MM} mm).
            </p>
            <div
              className="credit-card-reference"
              style={{ width: cardWidth, height: cardWidth * (53.98 / CREDIT_CARD_WIDTH_MM) }}
            >
              <span>STANDARD CARD</span>
              <span>85.6 × 53.98 mm</span>
              <button
                type="button"
                className="card-drag-handle"
                aria-label="Drag to resize credit card reference"
                onPointerDown={beginDrag}
                onPointerMove={continueDrag}
                onPointerUp={endDrag}
                onPointerCancel={endDrag}
              />
            </div>
          </div>
        ) : (
          <div className="monitor-fields">
            <label>
              <span>Diagonal size</span>
              <span className="input-with-unit">
                <input
                  type="number"
                  min="5"
                  max="100"
                  step="0.1"
                  value={diagonal}
                  onChange={(event) => setDiagonal(Number(event.target.value))}
                />
                <span>in</span>
              </span>
            </label>
            <label>
              <span>Native resolution</span>
              <span className="resolution-fields">
                <input
                  aria-label="Monitor resolution width"
                  type="number"
                  min="320"
                  value={resolutionWidth}
                  onChange={(event) => setResolutionWidth(Number(event.target.value))}
                />
                <span>×</span>
                <input
                  aria-label="Monitor resolution height"
                  type="number"
                  min="240"
                  value={resolutionHeight}
                  onChange={(event) => setResolutionHeight(Number(event.target.value))}
                />
              </span>
            </label>
          </div>
        )}

        <div className="calibration-result" aria-live="polite">
          <span>Calculated density</span>
          <strong>{candidate.toFixed(3)} CSS px/mm</strong>
          <small>One physical inch will render as {(candidate * 25.4).toFixed(1)} CSS px.</small>
        </div>

        <div className="sheet-actions">
          {current ? (
            <button type="button" className="button-quiet" onClick={onClear}>
              Clear saved calibration
            </button>
          ) : (
            <span />
          )}
          <button
            type="button"
            className="button-primary"
            onClick={() => {
              onSave(candidate, method);
              onClose();
            }}
          >
            Save calibration
          </button>
        </div>
      </section>
    </div>
  );
}
