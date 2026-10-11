import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import type { DeviceProfile } from "../../../shared_ts/models";
import type { PixelBuffer } from "../../../shared_ts/renderer";
import { physicalSizeCssPx } from "../calibration";
import type { ViewMode } from "./ViewModeControls";

interface EmulatorCanvasProps {
  frame: PixelBuffer;
  profile: DeviceProfile;
  mode: ViewMode;
  zoom: number;
  pxPerMm: number;
  calibrated: boolean;
  grid: boolean;
  ledLook: boolean;
  transition: string;
  frameKey: string;
  label: string;
}

type PixelStyle = CSSProperties & {
  "--pixel-w": string;
  "--pixel-h": string;
};

export function EmulatorCanvas({
  frame,
  profile,
  mode,
  zoom,
  pxPerMm,
  calibrated,
  grid,
  ledLook,
  transition,
  frameKey,
  label
}: EmulatorCanvasProps) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [viewport, setViewport] = useState({ width: 900, height: 440 });

  useLayoutEffect(() => {
    const node = viewportRef.current;
    if (!node) return;
    const update = () => setViewport({ width: node.clientWidth, height: node.clientHeight });
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d", { alpha: false });
    if (!context) return;
    context.imageSmoothingEnabled = false;
    context.putImageData(
      new ImageData(new Uint8ClampedArray(frame.data), frame.width, frame.height),
      0,
      0
    );
  }, [frame, frameKey]);

  const fitScale = Math.max(
    1,
    Math.floor(
      Math.min(
        Math.max(frame.width, viewport.width - 100) / frame.width,
        Math.max(frame.height, viewport.height - 110) / frame.height
      )
    )
  );
  const physical = physicalSizeCssPx(profile, pxPerMm);
  const cssWidth = mode === "physical" ? physical.width : frame.width * (mode === "zoom" ? zoom : fitScale);
  const cssHeight = mode === "physical" ? physical.height : frame.height * (mode === "zoom" ? zoom : fitScale);
  const pixelWidth = cssWidth / frame.width;
  const pixelHeight = cssHeight / frame.height;
  const pixelStyle: PixelStyle = {
    width: cssWidth,
    height: cssHeight,
    "--pixel-w": `${pixelWidth}px`,
    "--pixel-h": `${pixelHeight}px`
  };
  const seamCount = Math.max(0, Math.ceil(profile.logical.width / 64) - 1);
  const modeLabel =
    mode === "physical"
      ? `1:1 ${calibrated ? "calibrated" : "uncalibrated"}`
      : mode === "zoom"
        ? `${zoom}× fixed zoom`
        : `${fitScale}× integer fit`;

  return (
    <div ref={viewportRef} className={mode === "physical" ? "canvas-scroll physical" : "canvas-scroll"}>
      <div
        key={frameKey}
        className={`display-assembly transition-${transition}`}
        style={{ width: cssWidth + 20, height: cssHeight + 20 }}
      >
        <span className="view-badge">
          View <strong>{modeLabel}</strong>
        </span>
        <div className={ledLook ? "canvas-surface led-look" : "canvas-surface"} style={pixelStyle}>
          <canvas
            ref={canvasRef}
            width={frame.width}
            height={frame.height}
            style={{ width: cssWidth, height: cssHeight }}
            role="img"
            aria-label={label}
          >
            {label}
          </canvas>
          {grid ? <span className="pixel-grid" style={pixelStyle} aria-hidden="true" /> : null}
          {Array.from({ length: seamCount }, (_, index) => (
            <span
              className="panel-seam"
              key={`${profile.id}-seam-${index + 1}`}
              style={{ left: `${((index + 1) * 64 * 100) / profile.logical.width}%` }}
              aria-hidden="true"
            />
          ))}
        </div>
        <span className="dimension-width">
          {profile.physical.widthMm} mm · {profile.logical.width} px
        </span>
        <span className="dimension-height">
          {profile.physical.heightMm} mm · {profile.logical.height} px
        </span>
      </div>
    </div>
  );
}
