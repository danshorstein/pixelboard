import { useEffect, useState } from "react";
import { parseBdf, type BdfFont } from "../../shared_ts/bdf";
import { fontUrls } from "./catalog";

type FontName = keyof typeof fontUrls;

export function useBdfFonts() {
  const [fonts, setFonts] = useState<Partial<Record<FontName, BdfFont>>>({});
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        const entries = await Promise.all(
          (Object.entries(fontUrls) as Array<[FontName, string]>).map(async ([name, url]) => {
            const response = await fetch(url, { signal: controller.signal });
            if (!response.ok) throw new Error(`Font ${name} failed (${response.status})`);
            return [name, parseBdf(await response.text())] as const;
          })
        );
        if (!controller.signal.aborted) {
          setFonts(Object.fromEntries(entries));
          setStatus("ready");
        }
      } catch {
        if (!controller.signal.aborted) setStatus("error");
      }
    };
    void load();
    return () => controller.abort();
  }, []);

  return { fonts, status };
}
