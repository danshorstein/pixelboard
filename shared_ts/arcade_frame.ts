import { PixelBuffer } from "./renderer";
import type { BdfFont } from "./bdf";
import { riderGem, riderGround, type ArcadeState, type RiderState } from "./arcade";
import { bigLeagueFrame } from "./arcade_bigleague_frame";
import { soccerFrame } from "./arcade_soccer_frame";
import { unicornFrame } from "./arcade_unicorn_frame";
const white = [221, 240, 237, 255] as const, teal = [58, 226, 180, 255] as const, gold = [255, 201, 58, 255] as const, red = [255, 70, 88, 255] as const, dim = [25, 61, 56, 255] as const;
type Color = readonly [number, number, number, number];
const neon = [255, 40, 200, 255] as const, glow = [90, 12, 84, 255] as const, hill = [14, 4, 34, 255] as const, moon = [34, 18, 80, 255] as const, gemColor = [150, 230, 255, 255] as const;
const FP = 256, div = (a: number, b: number) => Math.floor(a / b);
// cos/sin of 16 headings (22.5 degree steps) scaled by 256, so rotation stays integer.
const COS16 = [256, 237, 181, 98, 0, -98, -181, -237, -256, -237, -181, -98, 0, 98, 181, 237], SIN16 = COS16.map((_, i) => COS16[(i + 12) % 16]);
const mod = (a: number, n: number) => ((a % n) + n) % n;
// Car art, drawn around the car centre: x forward, y down, last row on the ground.
// B body, G window, W wheel. Each entry is [rows, centre column].
const CARS: [string[], number][] = [
  [["   BBG  ", " BBBBBB ", "BBBBBBBB", " WW  WW "], 4], // buggy
  [["   BBG   ", " BBBBBBB ", "BBBBBBBBB", " WW   WW ", " WW   WW "], 4], // monster truck
  [["    BBBGG   ", " BBBBBBBBBB ", "BBBBBBBBBBBB", " WW      WW "], 6], // limo
  [["   G   ", "   BB  ", " BBBBB ", "WW   WW", "WW   WW"], 3], // bike
  [["   GGG   ", " BBBBBBB ", "BBBBBBBBB", " W  W  W "], 4], // ufo
];
const CAR_COLORS: Color[] = [teal, red, gold, [140, 255, 60, 255], [70, 130, 255, 255]]; // last colour index is rainbow
const RAINBOW = CAR_COLORS.length;
type SkyKind = "moon" | "sun" | "snow" | "embers" | "stars" | "lights";
// line, glow, hill fill (null leaves the sky showing), sky kind, sky colour
const THEMES: [Color, Color, Color | null, SkyKind, Color][] = [
  [neon, glow, hill, "moon", moon],
  [[255, 130, 40, 255], [110, 40, 10, 255], [40, 10, 24, 255], "sun", [210, 90, 40, 255]],
  [[160, 230, 255, 255], [30, 70, 110, 255], [6, 18, 40, 255], "snow", [120, 140, 170, 255]],
  [[255, 60, 20, 255], [120, 30, 0, 255], [36, 6, 0, 255], "embers", [200, 80, 0, 255]],
  [[190, 150, 255, 255], [50, 30, 90, 255], null, "stars", [150, 150, 190, 255]],
  [[60, 200, 80, 255], [200, 210, 200, 255], [4, 26, 8, 255], "lights", [230, 230, 200, 255]],
];
function disc(b: PixelBuffer, x: number, y: number, r: number, color: Color) {
  for (let dy = -r; dy <= r; dy++) for (let dx = -r; dx <= r; dx++) if (dx * dx + dy * dy <= r * r) b.setPixel(x + dx, y + dy, color);
}
function sky(b: PixelBuffer, kind: SkyKind, color: Color, cam: number, t: number) {
  if (kind === "moon") disc(b, 104 - mod(div(cam, 24), 150), 13, 5, color);
  else if (kind === "sun") disc(b, 96 - mod(div(cam, 40), 150), 9, 6, color);
  else if (kind === "snow" || kind === "embers") {
    for (let k = 0; k < 14; k++) {
      const fall = mod(k * 11 + div(t, kind === "snow" ? 90 : 70), 30);
      b.setPixel(mod(k * 37 - div(cam, 2) - div(t, 150), 128), kind === "snow" ? 1 + fall : 30 - fall, color);
    }
  } else if (kind === "stars") {
    for (let k = 0; k < 20; k++) if (mod(k + div(t, 400), 7)) b.setPixel(mod(k * 53 + 7 - div(cam, 6), 128), 2 + mod(k * 7, 18), color);
  } else {
    for (const tower of [20, 120]) {
      const x = mod(tower - div(cam, 5), 200) - 36;
      b.drawLine(x, 7, x, 31, [60, 60, 60, 255]); b.fillRect(x - 1, 4, 3, 2, color);
    }
  }
}
function rider(b: PixelBuffer, state: RiderState, text: (s: string, x: number, y: number, color?: Color) => void) {
  const seed = state.seed, t = state.time, [line, glowColor, fill, skyKind, skyColor] = THEMES[state.theme];
  const gemTint: Color = state.gemValue > 1 ? gold : gemColor;
  const cam = div(state.x, FP) - 24, cy = div(state.y + FP / 2, FP) - 2, lift = Math.max(0, 9 - cy); // Follow high jumps by lowering the world.
  sky(b, skyKind, skyColor, cam, t);
  let previous: number | null = null;
  for (let sx = 0; sx < 128; sx++) {
    const gy = div(riderGround(seed, (cam + sx) * FP) + FP / 2, FP) + lift;
    if (fill) b.fillRect(sx, gy + 2, 1, 32 - gy - 2, fill);
    b.setPixel(sx, gy + 1, glowColor);
    if (previous !== null) b.drawLine(sx - 1, previous, sx, gy, line);
    previous = gy;
  }
  for (let i = Math.max(state.nextGem, div(cam - 2, 32)); i <= div(cam + 130, 32); i++) {
    const gem = riderGem(seed, i); if (!gem) continue;
    const gx = gem.x - cam, gy = gem.y + lift;
    b.setPixel(gx, gy - 1, gemTint); b.fillRect(gx - 1, gy, 3, 1, gemTint); b.setPixel(gx, gy + 1, gemTint); b.setPixel(gx, gy, white);
  }
  const heading = (div(state.angle * 2 + 22, 45) % 16 + 16) % 16, c = COS16[heading], s = SIN16[heading];
  const [rows, centre] = CARS[state.car];
  rows.forEach((cells, row) => {
    const dy = row - rows.length + 2;
    [...cells].forEach((cell, col) => {
      if (cell === " ") return;
      const color = cell === "W" ? white : cell === "G" ? gemColor : state.color === RAINBOW ? CAR_COLORS[mod(col + div(t, 80), RAINBOW)] : CAR_COLORS[state.color];
      const dx = col - centre;
      b.setPixel(24 + div(dx * c - dy * s + 128, 256), cy + lift + div(dx * s + dy * c + 128, 256), color);
    });
  });
  text(String(state.score), 2, 0);
  const gems = String(state.gems); text(gems, 120 - gems.length * 4, 0);
  if (state.gemValue > 1) text(`${state.gemValue}X`, 110 - gems.length * 4, 0, gold);
  b.setPixel(124, 1, gemTint); b.fillRect(123, 2, 3, 1, gemTint); b.setPixel(124, 3, gemTint);
  if (state.bannerMs && state.status === "running") text(state.banner, div(128 - state.banner.length * 4, 2), 0, gold);
}
export function arcadeFrame(state: ArcadeState, font?: BdfFont, paused = false) {
  const b = new PixelBuffer(128, 32);
  const text = (s: string, x: number, y: number, color: Color = white, scale = 1) => {
    if (!font) return;
    for (const c of s) { const g = font.glyphs.get(c.charCodeAt(0)); if (!g) { x += 4 * scale; continue; }
      for (let row = 0; row < g.height; row++) for (let col = 0; col < g.width; col++) if (g.bitmap[row * g.width + col]) {
        const px = g.xOffset + col, py = font.ascent - g.yOffset - g.height + row;
        if (scale === 1) b.setPixel(x + px, y + py, color); else b.fillRect(x + px * scale, y + py * scale, scale, scale, color);
      }
      x += g.advanceX * scale;
    }
  };
  if (state.kind === "snake") {
    text(`SNAKE ${state.score}`, 2, 0); b.strokeRect(1, 5, 126, 26, dim);
    state.body.forEach((p, i) => b.fillRect(p.x * 2, p.y * 2, 2, 2, i === 0 ? white : teal));
    if (state.food) b.fillRect(state.food.x * 2, state.food.y * 2, 2, 2, gold);
  } else if (state.kind === "rider") rider(b, state, text);
  else if (state.kind === "bigleague") bigLeagueFrame(b, state, text);
  else if (state.kind === "soccer") soccerFrame(b, state, text);
  else if (state.kind === "unicorn") unicornFrame(b, state, text);
  else if (state.kind === "pong") {
    text(`YOU ${state.playerScore}`, 2, 0); text(`PI ${state.computerScore}`, 104, 0);
    for (let y = 7; y < 31; y += 4) b.fillRect(63, y, 1, 2, dim);
    b.drawLine(0, 5, 127, 5, dim); b.drawLine(0, 31, 127, 31, dim);
    b.fillRect(3, state.player, 2, 8, teal); b.fillRect(123, state.computer, 2, 8, gold); b.fillRect(state.ball.x, state.ball.y, 2, 2, white);
  } else {
    text(`PTS ${state.score}`, 2, 0); text(`P${Math.min(10, state.pitches + (state.phase === "pitch" ? 1 : 0))}/10`, 43, 0); text(`K ${state.strikes}`, 106, 0);
    b.drawLine(0, 29, 127, 29, dim); b.drawLine(24, 9, 24, 27, dim); b.fillRect(21, 27, 6, 2, white);
    // Batter and pitcher, deliberately readable at native resolution.
    b.fillRect(13, 17, 2, 2, teal); b.drawLine(14, 19, 15, 24, teal); b.drawLine(15, 24, 11, 28, teal); b.drawLine(15, 24, 18, 28, teal);
    b.fillRect(112, 18, 2, 2, gold); b.drawLine(112, 20, 110, 27, gold);
    if (state.phase === "pitch") { b.drawLine(16, 20, 20, 14, white); b.fillRect(state.x, 21, 2, 2, white); }
    else {
      b.drawLine(16, 20, 25, 21, gold);
      if (!["MISS", "FOUL"].includes(state.result)) {
        const t = state.flight / 1250; const x = 24 + t * 110; const y = 21 - Math.sin(t * Math.PI * .85) * (state.result === "HOME RUN!" ? 17 : 12);
        b.fillRect(x, y, 2, 2, white); b.setPixel(x - 3, y + 1, gold); b.setPixel(x - 5, y + 2, dim);
      }
      text(state.result, 39, 10, state.result === "MISS" ? red : gold);
    }
  }
  if (state.status !== "running" || paused) {
    b.fillRect(14, 10, 100, 13, [0, 0, 0, 255]); b.strokeRect(14, 10, 100, 13, dim);
    const message = paused ? "PAUSED" : state.status === "ready" ? "PRESS START" : state.message;
    text(message, Math.max(16, Math.floor((128 - message.length * 4) / 2)), 14);
  }
  return b;
}
