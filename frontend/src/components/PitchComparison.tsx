import { useEffect, useMemo, useRef, type CSSProperties } from "react";
import type { DeviceProfile } from "../../../shared_ts/models";
import type { PixelBuffer } from "../../../shared_ts/renderer";
import {
  pitchOptionsForProfiles,
  shareOfThirtyInchDresser,
  wholeTickerInches
} from "../pitchComparison";

interface PitchComparisonProps {
  profiles: readonly DeviceProfile[];
  selectedProfileId: string;
  frame: PixelBuffer;
  onSelect: (profileId: string) => void;
}

interface PitchSampleProps {
  profile: DeviceProfile;
  frame: PixelBuffer;
}

function PitchSample({ profile, frame }: PitchSampleProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const widthShare = Math.min(100, shareOfThirtyInchDresser(profile));
  const aspectRatio = `${profile.physical.widthMm} / ${profile.physical.heightMm}`;

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
  }, [frame]);

  return (
    <div className="pitch-room-stage" aria-label={`${profile.label} shown against a 30 inch dresser top`}>
      <span className="pitch-room-label">30 in dresser-top example</span>
      <span className="pitch-room-tick pitch-room-tick-start" aria-hidden="true" />
      <span className="pitch-room-tick pitch-room-tick-end" aria-hidden="true" />
      <div
        className="pitch-device"
        style={{ width: `${widthShare}%`, aspectRatio }}
      >
        <canvas
          ref={canvasRef}
          width={frame.width}
          height={frame.height}
          aria-label={`The same scoreboard frame on ${profile.label}`}
        />
        <span className="pitch-panel-seam" aria-hidden="true" />
      </div>
    </div>
  );
}

export function PitchComparison({ profiles, selectedProfileId, frame, onSelect }: PitchComparisonProps) {
  const choices = useMemo(() => pitchOptionsForProfiles(profiles), [profiles]);

  return (
    <section className="pitch-comparison panel-card" aria-labelledby="pitch-comparison-title">
      <header className="pitch-comparison-header">
        <div>
          <span className="eyebrow">Physical size explorer</span>
          <h2 id="pitch-comparison-title">Same scoreboard. Three real sizes.</h2>
          <p>
            P means millimeter pitch: the center-to-center distance between neighboring LEDs.
            Every option below still uses two 64 × 32 panels, so the game layout remains 128 × 32.
          </p>
        </div>
        <span className="pitch-count">4,096 RGB LEDs in every full ticker</span>
      </header>

      <div className="pitch-choice-grid">
        {choices.map(({ option, profile }) => {
          const ticker = wholeTickerInches(profile);
          const active = selectedProfileId === profile.id;
          return (
            <article key={profile.id} className={active ? "pitch-choice is-active" : "pitch-choice"}>
              <button
                type="button"
                className="pitch-choice-select"
                aria-pressed={active}
                onClick={() => onSelect(profile.id)}
              >
              <span className="pitch-choice-topline">
                <strong>{option.pitchLabel}</strong>
                <span>{profile.physical.pixelPitchMm.toFixed(1)} mm LED centers</span>
              </span>
              <PitchSample profile={profile} frame={frame} />
              <span className="pitch-size-row">
                <strong>{ticker.width.toFixed(1)} × {ticker.height.toFixed(1)} in</strong>
                <span>{profile.physical.widthMm} × {profile.physical.heightMm} mm active face</span>
              </span>
              <span className="pitch-spec-line">
                One panel: {option.singlePanel.widthMm} × {option.singlePanel.heightMm} × {option.singlePanel.depthMm} mm
              </span>
              <span className="pitch-gap-row" style={{ "--pitch-gap": `${profile.physical.pixelPitchMm * 3}px` } as CSSProperties}>
                <i aria-hidden="true" /><i aria-hidden="true" /><i aria-hidden="true" /><i aria-hidden="true" /><i aria-hidden="true" />
                <span>LED spacing</span>
              </span>
              <span className="pitch-choice-note">{option.note}</span>
                <span className="pitch-product-row">Adafruit #{option.productId} · ${option.referencePriceUsd.toFixed(2)} each*</span>
              </button>
              <a className="pitch-product-link" href={option.productUrl} target="_blank" rel="noreferrer">
                Official specs ↗
              </a>
            </article>
          );
        })}
      </div>

      <footer className="pitch-comparison-footnote">
        <span>Tap a card to make that pitch the main preview above.</span>
        <span>*Reference price checked July 20, 2026; availability and price can change.</span>
      </footer>
    </section>
  );
}
