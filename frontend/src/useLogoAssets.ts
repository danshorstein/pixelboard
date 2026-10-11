import { useEffect, useMemo, useState } from "react";
import type { RgbSprite, SpriteAsset } from "../../shared_ts/renderer";

interface LogoManifestEntry {
  teamId: number | string;
  abbr: string;
  width: 16 | 20 | 24;
  height: 16 | 20 | 24;
  path: string;
  sha256: string;
  source: string;
  usageStatus: "private-personal-use" | "licensed" | "owner-provided" | "review-required";
}

interface LogoManifest {
  schemaVersion: "1.0";
  id: string;
  private: true;
  assets: LogoManifestEntry[];
}

export type LogoPackStatus = "checking" | "available" | "unavailable" | "invalid";

const MANIFEST_URL = "/private-assets/team-logos/manifest.json";
const SAFE_PATH = /^(?!.*(?:^|\/)\.\.(?:\/|$))[A-Za-z0-9][A-Za-z0-9._/-]*\.png$/;
const SHA256 = /^[A-Fa-f0-9]{64}$/;

const bytesToHex = (bytes: ArrayBuffer) =>
  Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, "0")).join("");

const decodeSprite = async (bytes: ArrayBuffer, width: number, height: number): Promise<RgbSprite> => {
  const blobUrl = URL.createObjectURL(new Blob([bytes], { type: "image/png" }));
  try {
    const image = new Image();
    image.decoding = "sync";
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error("Unable to decode logo PNG"));
      image.src = blobUrl;
    });
    if (image.naturalWidth !== width || image.naturalHeight !== height) {
      throw new Error("Logo dimensions do not match manifest");
    }
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d", { alpha: true, willReadFrequently: true });
    if (!context) throw new Error("Canvas unavailable");
    context.imageSmoothingEnabled = false;
    context.drawImage(image, 0, 0);
    return { width, height, data: context.getImageData(0, 0, width, height).data };
  } finally {
    URL.revokeObjectURL(blobUrl);
  }
};

const validManifest = (value: unknown): value is LogoManifest => {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const manifest = value as Partial<LogoManifest>;
  return manifest.schemaVersion === "1.0" && manifest.private === true &&
    typeof manifest.id === "string" && Array.isArray(manifest.assets);
};

/** Loads optional, same-origin logo sprites without making them a product dependency. */
export function useLogoAssets() {
  const [assets, setAssets] = useState<Record<string, SpriteAsset>>({});
  const [status, setStatus] = useState<LogoPackStatus>("checking");
  const [loadedCount, setLoadedCount] = useState(0);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const load = async () => {
      try {
        const manifestResponse = await fetch(MANIFEST_URL, {
          cache: "no-store",
          signal: controller.signal
        });
        if (manifestResponse.status === 404) {
          if (active) setStatus("unavailable");
          return;
        }
        if (!manifestResponse.ok) throw new Error("Logo manifest unavailable");
        if (!manifestResponse.headers.get("content-type")?.includes("application/json")) {
          if (active) setStatus("unavailable");
          return;
        }
        const manifest: unknown = await manifestResponse.json();
        if (!validManifest(manifest)) throw new Error("Invalid logo manifest");

        const loaded: Record<string, SpriteAsset> = {};
        for (const entry of manifest.assets) {
          if (
            !SAFE_PATH.test(entry.path) || !SHA256.test(entry.sha256) ||
            ![16, 20, 24].includes(entry.width) || entry.width !== entry.height
          ) continue;
          const url = new URL(entry.path, new URL(MANIFEST_URL, window.location.href));
          const response = await fetch(url, { cache: "no-store", signal: controller.signal });
          if (!response.ok) continue;
          const bytes = await response.arrayBuffer();
          const digest = bytesToHex(await crypto.subtle.digest("SHA-256", bytes));
          if (digest.toLowerCase() !== entry.sha256.toLowerCase()) continue;
          loaded[`team-logo:${entry.teamId}:${entry.width}`] = await decodeSprite(
            bytes,
            entry.width,
            entry.height
          );
        }
        if (!active) return;
        setAssets(loaded);
        setLoadedCount(Object.keys(loaded).length);
        setStatus(Object.keys(loaded).length > 0 ? "available" : "invalid");
      } catch {
        if (active) setStatus("invalid");
      }
    };
    void load();
    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  return useMemo(() => ({
    assets,
    status,
    loadedCount,
    keyFor: (teamId: number | string, size: 16 | 20 | 24 = 16) => {
      const key = `team-logo:${teamId}:${size}`;
      return Object.prototype.hasOwnProperty.call(assets, key) ? key : null;
    }
  }), [assets, loadedCount, status]);
}
