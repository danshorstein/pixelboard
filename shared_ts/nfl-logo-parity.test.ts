import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { it, expect } from "vitest";
import { parseBdf } from "./bdf";
import { nflFrame, type NflFrameGame } from "./nfl_frame";
import type { RgbSprite } from "./renderer";
const fonts = Object.fromEntries(["4x6", "5x7", "6x10"].map(n => [n, parseBdf(readFileSync(`definition/mlb-classic/fonts/${n}.bdf`, "utf8"))]));
const games = JSON.parse(readFileSync("fixtures/nfl-demo.json", "utf8")) as NflFrameGame[];
const sprite = (tone: number): RgbSprite => ({width:16,height:16,data:Array.from({length:256}, (_, i) => [tone, tone ? 2*tone : 0, tone ? 3*tone : 0, [0,64,128,255][i%4]]).flat()});
const cases = games.flatMap(game => ["rows", "compact"].flatMap(layout => [false,true].flatMap(stale => [0,20,80].map(tone => ({game,layout,stale,assets:Object.fromEntries([game.away,game.home].map(t => [`team-logo:nfl:${t.id}:16`,sprite(tone)]))})))));
it("NFL logos have identical RGBA bytes across languages, including dark marks and partial alpha", () => {
  const hashes = cases.map(c => createHash("sha256").update(nflFrame(c.game,fonts,c.layout,c.stale,"America/New_York",c.assets).data).digest("hex"));
  const python = execFileSync(".venv/bin/python", ["-c", `import hashlib,json,sys\nfrom pathlib import Path\nfrom shared_py.bdf import parse_bdf\nfrom shared_py.nfl_frame import nfl_frame\nfonts={n:parse_bdf(Path(f'definition/mlb-classic/fonts/{n}.bdf').read_text()) for n in ('4x6','5x7','6x10')}\ncases=json.load(sys.stdin)\nprint(json.dumps([hashlib.sha256(nfl_frame(c['game'],fonts,c['layout'],c['stale'],'America/New_York',c['assets']).data).hexdigest() for c in cases]))`], {input:JSON.stringify(cases),encoding:"utf8"});
  expect(hashes).toEqual(JSON.parse(python));
  expect(hashes).toEqual(JSON.parse(readFileSync("fixtures/nfl-logo-frame-hashes.json", "utf8")));
});
it("missing or transparent NFL logos retain the complete abbreviation fallback", () => {
  const game=games[0];
  const baseline=nflFrame(game,fonts).data;
  expect(nflFrame(game,fonts,"rows",false,"America/New_York",{[`team-logo:nfl:${game.away.id}:16`]:sprite(80)}).data).toEqual(baseline);
  const transparent={width:16,height:16,data:new Array(1024).fill(0)};
  expect(nflFrame(game,fonts,"rows",false,"America/New_York",Object.fromEntries([game.away,game.home].map(t => [`team-logo:nfl:${t.id}:16`,transparent]))).data).toEqual(baseline);
});
