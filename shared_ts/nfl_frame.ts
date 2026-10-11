import { glyphForCodePoint, type BdfFont } from "./bdf";
import { PixelBuffer, type Rgba, type RgbSprite } from "./renderer";
interface Team {
  id: string;
  abbr: string;
  color?: string;
  score?: string | null;
}
export interface NflFrameGame {
  away: Team;
  home: Team;
  state: string;
  status: string;
  completed: boolean;
  date?: string | null;
  period?: number | null;
  clock?: string | null;
  possession?: string | null;
  downDistance?: string | null;
  fieldPosition?: string | null;
  redZone?: boolean;
}
export function nflFrame(
  game: NflFrameGame | undefined,
  fonts: Record<string, BdfFont>,
  layout = "rows",
  stale = false,
  timeZone = "America/New_York",
  assets: Readonly<Record<string, RgbSprite>> = {},
) {
  const frame = new PixelBuffer(128, 32, [3, 8, 7, 255]);
  const text = (
    value: string,
    font: BdfFont,
    x: number,
    y: number,
    color: Rgba,
    maxX = 128,
  ) => {
    for (const ch of value.toUpperCase()) {
      const g = glyphForCodePoint(font, ch.charCodeAt(0));
      if (!g) continue;
      if (x + g.width > maxX) break;
      for (let row = 0; row < g.height; row++)
        for (let col = 0; col < g.width; col++)
          if (g.bitmap[row * g.width + col])
            frame.setPixel(x + col, y + row, color);
      x += g.advanceX;
    }
  };
  const small = fonts["4x6"],
    white: Rgba = [255, 255, 255, 255],
    gold: Rgba = [255, 194, 117, 255];
  if (!game) {
    text("NO NFL GAMES", small, 4, 5, white);
    text("SELECT: MENU", small, 4, 18, [255, 180, 115, 255]);
    return frame;
  }
  const start = game.date
    ? new Date(game.date).toLocaleTimeString("en-US", {
        hour: "numeric",
        minute: "2-digit",
        timeZone,
      })
    : "KICKOFF";
  const score = (t: Team) => (game.state === "pre" ? "--" : t.score || "0");
  if (layout === "compact") {
    const lines = [
      `${game.away.abbr} ${score(game.away)}  ${game.home.abbr} ${score(game.home)}`,
      stale ? "DATA STALE" : game.status,
      game.state === "in"
        ? game.downDistance || game.fieldPosition || ""
        : game.state === "pre"
          ? start
          : "",
    ];
    lines.forEach((line, i) =>
      text(line, small, 2, 2 + i * 10, i === 0 ? white : gold),
    );
    return frame;
  }
  const keys = [game.away, game.home].map(team => `team-logo:nfl:${team.id}:16`);
  const logos = keys.every(key => {
    const asset = assets[key];
    return asset?.width === 16 && asset.height === 16 && asset.data.length === 1024 &&
      Array.from(asset.data).some((v, i) => i % 4 === 3 && v > 0);
  });
  const logo = (key: string, y: number) => {
    const asset = assets[key];
    let peak = 0;
    for (let i = 0; i < asset.data.length; i += 4)
      if (asset.data[i + 3] > 0) peak = Math.max(peak, asset.data[i], asset.data[i + 1], asset.data[i + 2]);
    const channel = (v: number) => peak === 0 ? 220 : peak < 128 ? Math.min(255, Math.round(v * 220 / peak)) : v;
    for (let row = 0; row < 16; row++)
      for (let col = 0; col < 16; col++) {
        const i = (row * 16 + col) * 4;
        frame.blendPixel(3 + col, y + row, [channel(asset.data[i]), channel(asset.data[i + 1]), channel(asset.data[i + 2]), asset.data[i + 3]]);
      }
  };
  [game.away, game.home].forEach((team, i) => {
    const raw = team.color || "",
      color = /^[a-f\d]{6}$/i.test(raw)
        ? [0, 2, 4].map((j) => parseInt(raw.slice(j, j + 2), 16))
        : [36, 59, 87];
    const dim = color.map((c) => Math.floor((c * 2 + 1) / 3));
    const y = i * 16;
    frame.fillRect(0, y, 58, 15, [dim[0], dim[1], dim[2], 255]);
    if (logos) {
      logo(keys[i], y);
      text(team.abbr, small, 21, y + 5, white, 37);
    } else text(team.abbr, fonts["5x7"], 5, y + 4, white, 27);
    text(score(team), fonts["6x10"], logos ? 38 : 33, y + 2, white, logos ? 58 : 56);
    if (String(game.possession) === team.id)
      frame.fillRect(1, y + 6, 2, 3, [255, 202, 116, 255]);
  });
  frame.fillRect(60, 0, 1, 32, [52, 71, 93, 255]);
  const period = game.period,
    headline = game.completed
      ? "FINAL"
      : game.state === "pre"
        ? start
        : /halftime/i.test(game.status)
          ? "HALFTIME"
          : `${period && period > 4 ? "OT" : period ? "Q" + period : ""} ${game.clock || game.status}`;
  text(stale ? "STALE" : headline, small, 65, 3, gold, 126);
  text(
    game.downDistance ||
      (game.state === "pre" ? "KICKOFF" : game.completed ? "FULL TIME" : ""),
    small,
    65,
    13,
    white,
    126,
  );
  text(
    game.fieldPosition || (game.redZone ? "RED ZONE" : "NFL"),
    small,
    65,
    23,
    [155, 230, 181, 255],
    126,
  );
  return frame;
}
