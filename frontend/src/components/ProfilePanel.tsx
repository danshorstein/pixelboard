import type { DeviceProfile } from "../../../shared_ts/models";

interface ProfilePanelProps {
  profiles: readonly DeviceProfile[];
  selected: DeviceProfile;
  definitionLogical: { width: number; height: number };
  calibrated: boolean;
  onSelect: (profileId: string) => void;
  onCalibrate: () => void;
}

const inches = (millimeters: number) => (millimeters / 25.4).toFixed(1);

export function ProfilePanel({
  profiles,
  selected,
  definitionLogical,
  calibrated,
  onSelect,
  onCalibrate
}: ProfilePanelProps) {
  const compatible =
    selected.logical.width === definitionLogical.width &&
    selected.logical.height === definitionLogical.height;

  return (
    <section className="profile-panel panel-card" aria-labelledby="profile-title">
      <div className="panel-heading compact">
        <div>
          <span className="eyebrow">Target catalog</span>
          <h2 id="profile-title">Device profile</h2>
        </div>
        <span className={compatible ? "status-pill good" : "status-pill warning"}>
          {compatible ? "Definition fits" : "Resolution mismatch"}
        </span>
      </div>

      <label className="field-stack">
        <span>Panel configuration</span>
        <select value={selected.id} onChange={(event) => onSelect(event.target.value)}>
          {profiles.map((profile) => (
            <option key={profile.id} value={profile.id}>
              {profile.label ?? profile.id}
            </option>
          ))}
        </select>
      </label>

      <dl className="profile-metrics">
        <div>
          <dt>Logical</dt>
          <dd>
            {selected.logical.width} × {selected.logical.height} px
          </dd>
        </div>
        <div>
          <dt>Pitch</dt>
          <dd>P{selected.physical.pixelPitchMm}</dd>
        </div>
        <div>
          <dt>Active area</dt>
          <dd>
            {selected.physical.widthMm} × {selected.physical.heightMm} mm
          </dd>
        </div>
        <div>
          <dt>Inches</dt>
          <dd>
            {inches(selected.physical.widthMm)} × {inches(selected.physical.heightMm)} in
          </dd>
        </div>
      </dl>

      {!compatible ? (
        <p className="inline-notice warning">
          M1 has one curated 128 × 32 definition. This profile still renders its exact logical grid,
          clipped or padded deliberately; automatic re-layout belongs to validation work after M1.
        </p>
      ) : (
        <p className="inline-notice">
          Switch P3, P4, and P5 in 1:1 view: the pixels and design stay identical while the physical
          sign changes size.
        </p>
      )}

      <button type="button" className="calibration-button" onClick={onCalibrate}>
        <span>
          <strong>{calibrated ? "Screen calibrated" : "1:1 is uncalibrated"}</strong>
          <small>{calibrated ? "Recalibrate or verify this monitor" : "Match a card or enter monitor specs"}</small>
        </span>
        <span aria-hidden="true">→</span>
      </button>
    </section>
  );
}
