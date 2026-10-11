import { useCallback, useEffect, useState } from "react";

export interface ValidationFinding {
  rule: string;
  severity: "pass" | "warning" | "blocking";
  title: string;
  evidence: string;
  remediation: string | null;
  acknowledged: boolean;
}

export interface ValidationReport {
  status: "valid" | "warnings" | "blocked";
  profileId: string;
  summary: {
    pass: number;
    warning: number;
    blocking: number;
    unacknowledgedWarnings: number;
  };
  findings: ValidationFinding[];
}

export interface BuildLogEvent {
  atUtc: string;
  stage: string;
  status: string;
  message: string;
}

export interface DeviceBuildResult {
  buildId: string;
  status: "ready";
  artifactFilename: string;
  artifactSha256: string;
  artifactBytes: number;
  downloadUrl: string;
  logs: BuildLogEvent[];
  readiness: {
    verification: { status: "pass" | "fail"; maxRenderMs: number; frameBudgetMs: number; frames: unknown[] };
  };
}

type ActionState = "idle" | "validating" | "building" | "error";

class RequestFailure extends Error {
  logs: BuildLogEvent[];

  constructor(message: string, logs: BuildLogEvent[] = []) {
    super(message);
    this.logs = logs;
  }
}

const post = async <T,>(url: string, acknowledgedWarnings: readonly string[]): Promise<T> => {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ acknowledgedWarnings })
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
    const detail = payload?.detail;
    const message = typeof detail === "string"
      ? detail
      : detail && typeof detail === "object" && "message" in detail
        ? String((detail as { message: unknown }).message)
        : `Request failed (${response.status})`;
    const logs = detail && typeof detail === "object" && "logs" in detail && Array.isArray(detail.logs)
      ? detail.logs as BuildLogEvent[]
      : [];
    throw new RequestFailure(message, logs);
  }
  return await response.json() as T;
};

export function useDeviceBuild(projectId: string, projectVersion: number) {
  const [action, setAction] = useState<ActionState>("idle");
  const [report, setReport] = useState<ValidationReport | null>(null);
  const [build, setBuild] = useState<DeviceBuildResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<BuildLogEvent[]>([]);

  useEffect(() => {
    setReport(null);
    setBuild(null);
    setError(null);
    setLogs([]);
    setAction("idle");
  }, [projectId, projectVersion]);

  const validate = useCallback(async (acknowledgedWarnings: readonly string[] = []) => {
    setAction("validating");
    setError(null);
    setLogs([]);
    try {
      const value = await post<ValidationReport>(
        `/api/v1/projects/${encodeURIComponent(projectId)}/validate`,
        acknowledgedWarnings
      );
      setReport(value);
      setBuild(null);
      setAction("idle");
      return value;
    } catch (cause) {
      setAction("error");
      setError(cause instanceof Error ? cause.message : "Target validation failed");
      return null;
    }
  }, [projectId]);

  const buildArtifact = useCallback(async (acknowledgedWarnings: readonly string[] = []) => {
    setAction("building");
    setError(null);
    setLogs([]);
    try {
      const value = await post<DeviceBuildResult>(
        `/api/v1/projects/${encodeURIComponent(projectId)}/build`,
        acknowledgedWarnings
      );
      setBuild(value);
      setLogs(value.logs);
      setAction("idle");
      return value;
    } catch (cause) {
      setAction("error");
      setError(cause instanceof Error ? cause.message : "Device build failed");
      setLogs(cause instanceof RequestFailure ? cause.logs : []);
      return null;
    }
  }, [projectId]);

  return { action, report, build, error, logs, validate, buildArtifact };
}
