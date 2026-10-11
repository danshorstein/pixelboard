import { useEffect, useMemo, useState } from "react";
import type { BuildLogEvent, DeviceBuildResult, ValidationReport } from "../useDeviceBuild";

interface DeviceBuildPanelProps {
  syncReady: boolean;
  action: "idle" | "validating" | "building" | "error";
  report: ValidationReport | null;
  build: DeviceBuildResult | null;
  error: string | null;
  logs: readonly BuildLogEvent[];
  onValidate: (acknowledgedWarnings: readonly string[]) => Promise<ValidationReport | null>;
  onBuild: (acknowledgedWarnings: readonly string[]) => Promise<DeviceBuildResult | null>;
}

const formatBytes = (value: number) => value < 1024 * 1024
  ? `${Math.ceil(value / 1024)} KB`
  : `${(value / 1024 / 1024).toFixed(1)} MB`;

export function DeviceBuildPanel({
  syncReady,
  action,
  report,
  build,
  error,
  logs,
  onValidate,
  onBuild
}: DeviceBuildPanelProps) {
  const [acknowledged, setAcknowledged] = useState<string[]>([]);
  useEffect(() => setAcknowledged([]), [report?.profileId, report?.status]);
  const warningRules = useMemo(
    () => report?.findings.filter((finding) => finding.severity === "warning").map((finding) => finding.rule) ?? [],
    [report]
  );
  const allWarningsAcknowledged = warningRules.every((rule) => acknowledged.includes(rule));
  const busy = action === "validating" || action === "building";
  const readyToBuild = report?.status === "valid" || (
    report?.status === "warnings" && allWarningsAcknowledged
  );
  const status = build
    ? "ready"
    : report?.status === "blocked"
      ? "blocked"
      : report?.status === "valid"
        ? "validated"
        : "check";

  return (
    <section className="panel-card device-build-panel" aria-labelledby="device-build-title">
      <div className="panel-heading compact">
        <div>
          <span className="eyebrow">Physical device</span>
          <h2 id="device-build-title">Pi package</h2>
        </div>
        <span className={status === "ready" || status === "validated" ? "status-pill good" : status === "blocked" ? "status-pill danger" : "status-pill warning"}>
          {status}
        </span>
      </div>

      <p className="panel-footnote">
        128×32 P4 · two HUB75 panels · NEXT + HOLD on GPIO
      </p>

      {report ? (
        <div className="validation-summary" aria-label="Target validation summary">
          <span className="finding-pass">{report.summary.pass} pass</span>
          <span className="finding-warning">{report.summary.warning} warning</span>
          <span className="finding-blocking">{report.summary.blocking} block</span>
        </div>
      ) : null}

      {report ? (
        <div className="finding-list">
          {report.findings.map((finding) => (
            <details key={finding.rule} className={`finding finding-${finding.severity}`}>
              <summary>
                <span aria-hidden="true">{finding.severity === "pass" ? "✓" : finding.severity === "warning" ? "!" : "×"}</span>
                {finding.title}
              </summary>
              <p>{finding.evidence}</p>
              {finding.remediation ? <p>{finding.remediation}</p> : null}
              {finding.severity === "warning" ? (
                <label className="warning-ack">
                  <input
                    type="checkbox"
                    checked={acknowledged.includes(finding.rule)}
                    onChange={(event) => setAcknowledged((current) => event.target.checked
                      ? [...new Set([...current, finding.rule])]
                      : current.filter((rule) => rule !== finding.rule))}
                  />
                  I reviewed this warning
                </label>
              ) : null}
            </details>
          ))}
        </div>
      ) : null}

      {build ? (
        <div className="build-proof">
          <strong>Ready for supported device</strong>
          <span>{build.readiness.verification.frames.length} exact frames · {build.readiness.verification.maxRenderMs.toFixed(2)} ms max</span>
          <span>{formatBytes(build.artifactBytes)} · SHA {build.artifactSha256.slice(0, 12)}…</span>
        </div>
      ) : null}

      {error ? <p className="inline-notice warning" role="alert">{error}</p> : null}
      {logs.length ? (
        <details className="build-log">
          <summary>Build log · {logs.length} stages</summary>
          <ol>
            {logs.map((event, index) => (
              <li key={`${event.atUtc}-${event.stage}-${index}`}>
                <strong>{event.stage}</strong>
                <span>{event.status}</span>
                <p>{event.message}</p>
              </li>
            ))}
          </ol>
        </details>
      ) : null}
      {!syncReady ? <p className="inline-notice warning">Wait for the project service to finish saving before checking the device.</p> : null}

      <div className="project-actions device-actions">
        <button
          type="button"
          className="button-quiet"
          disabled={!syncReady || busy}
          onClick={() => void onValidate(acknowledged)}
        >
          {action === "validating" ? "Checking…" : report ? "Recheck" : "Check device"}
        </button>
        {!build ? (
          <button
            type="button"
            className="button-primary"
            disabled={!syncReady || busy || !readyToBuild}
            onClick={() => void onBuild(acknowledged)}
          >
            {action === "building" ? "Building…" : "Build Pi package"}
          </button>
        ) : (
          <a className="button-primary download-artifact" href={build.downloadUrl} download={build.artifactFilename}>
            Download .tar.gz
          </a>
        )}
      </div>
    </section>
  );
}
