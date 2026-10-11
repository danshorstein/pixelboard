import { useRef } from "react";

interface ProjectPanelProps {
  name: string;
  version: number;
  state: "local" | "saving" | "saved" | "offline" | "error";
  message: string;
  onExport: () => Promise<void>;
  onImport: (file: File) => Promise<void>;
}

export function ProjectPanel({
  name,
  version,
  state,
  message,
  onExport,
  onImport
}: ProjectPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <section className="panel-card project-panel" aria-labelledby="project-title">
      <div className="panel-heading compact">
        <div>
          <span className="eyebrow">Portable project</span>
          <h2 id="project-title">{name}</h2>
        </div>
        <span className={state === "error" || state === "offline" ? "status-pill warning" : "status-pill good"}>
          v{version}
        </span>
      </div>
      <p className={`project-sync sync-${state}`} role="status">{message}</p>
      <div className="project-actions">
        <button type="button" className="button-primary" onClick={() => void onExport()}>
          Export backup
        </button>
        <button type="button" className="button-quiet" onClick={() => inputRef.current?.click()}>
          Import
        </button>
        <input
          ref={inputRef}
          className="sr-only"
          type="file"
          accept=".zip,application/zip"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void onImport(file);
            event.target.value = "";
          }}
        />
      </div>
      <p className="panel-footnote">Includes the project, exact display definition, profile, fonts, manifest, and checksums.</p>
    </section>
  );
}
