import { useEffect, useState } from "react";
import {
  CSS_PX_PER_MM_FALLBACK,
  currentScreenFingerprint,
  sameFingerprint,
  type CalibrationRecord,
  type ScreenFingerprint
} from "./calibration";

const STORAGE_KEY = "scoreboard.calibration.v1";

const loadCalibration = (): CalibrationRecord | null => {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value ? (JSON.parse(value) as CalibrationRecord) : null;
  } catch {
    return null;
  }
};

export function useCalibration() {
  const [record, setRecord] = useState<CalibrationRecord | null>(loadCalibration);
  const [fingerprint, setFingerprint] = useState<ScreenFingerprint>(currentScreenFingerprint);

  useEffect(() => {
    const refresh = () => setFingerprint(currentScreenFingerprint());
    window.addEventListener("resize", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.removeEventListener("resize", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, []);

  const calibrated = record ? sameFingerprint(record.fingerprint, fingerprint) : false;

  const save = (pxPerMm: number, method: CalibrationRecord["method"]) => {
    const next: CalibrationRecord = {
      pxPerMm,
      method,
      fingerprint: currentScreenFingerprint(),
      savedAt: new Date().toISOString()
    };
    setRecord(next);
    setFingerprint(next.fingerprint);
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // Calibration remains available for this session if storage is unavailable.
    }
  };

  const clear = () => {
    setRecord(null);
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Nothing else to do when storage is unavailable.
    }
  };

  return {
    calibrated,
    record,
    fingerprint,
    pxPerMm: calibrated && record ? record.pxPerMm : CSS_PX_PER_MM_FALLBACK,
    save,
    clear
  };
}
