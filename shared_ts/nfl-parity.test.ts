import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { it, expect } from "vitest";
import { parseBdf } from "./bdf";
import { nflFrame, type NflFrameGame } from "./nfl_frame";
const fonts = Object.fromEntries(
  ["4x6", "5x7", "6x10"].map((n) => [
    n,
    parseBdf(
      readFileSync(
        new URL(`../definition/mlb-classic/fonts/${n}.bdf`, import.meta.url),
        "utf8",
      ),
    ),
  ]),
);
const games = JSON.parse(
  readFileSync(new URL("../fixtures/nfl-demo.json", import.meta.url), "utf8"),
) as NflFrameGame[];
it("NFL rows and compact frames match frozen cross-language references", () => {
  const hashes = games.flatMap((g) =>
    ["rows", "compact"].flatMap((layout) =>
      [false, true].map((stale) =>
        createHash("sha256")
          .update(nflFrame(g, fonts, layout, stale).data)
          .digest("hex"),
      ),
    ),
  );
  expect(hashes).toEqual(
    JSON.parse(
      readFileSync(
        new URL("../fixtures/nfl-frame-hashes.json", import.meta.url),
        "utf8",
      ),
    ),
  );
});
