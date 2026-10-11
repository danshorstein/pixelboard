// Big League pictures, pixel-exact counterpart of shared_py/arcade_bigleague_frame.py.
// Three views: behind the batter for pitches, a flattened top-down field once the
// ball is in play, and a line score between half innings.
import type { PixelBuffer } from "./renderer";
import { BASES, FENCE, INNINGS, PITCHES, WAIT_MS, WINDUP_MS, basePoint, isqrt, meterValue, type BigLeagueFields } from "./arcade_bigleague";

type Color = readonly [number, number, number, number];
type Text = (s: string, x: number, y: number, color?: Color) => void;
interface State extends BigLeagueFields { status: string }
const WHITE: Color = [221, 240, 237, 255], TEAL: Color = [58, 226, 180, 255], GOLD: Color = [255, 201, 58, 255], RED: Color = [255, 70, 88, 255];
const GREEN: Color = [80, 220, 110, 255], DIM: Color = [90, 140, 130, 255], FAINT: Color = [25, 61, 56, 255], OFF: Color = [30, 34, 34, 255], BLACK: Color = [0, 0, 0, 255];
const GRASS: Color = [0, 46, 14, 255], INFIELD: Color = [0, 64, 20, 255], FOUL: Color = [0, 18, 6, 255], DIRT: Color = [74, 40, 14, 255];
const WALL: Color = [0, 80, 36, 255], FENCE_TOP: Color = [70, 210, 100, 255], CHALK: Color = [150, 160, 150, 255];
const SKIN: Color = [230, 170, 120, 255], BAT: Color = [200, 140, 70, 255], PANTS: Color = [170, 180, 180, 255], SHADOW: Color = [0, 20, 6, 255];
const div = (a: number, b: number) => Math.floor(a / b);
// Batter seen from behind, standing left of the plate. T team colour, S skin, W pants, K bat.
const STANCE = ["      K", "     K ", "  TTK  ", "  TTT  ", "   S   ", " TTTTT ", " TTTSS ", "  TTT  ", "  WWW  ", "  W W  ", "  W W  ", " WW WW "];
const SWUNG = ["       ", "       ", "  TT   ", "  TTT  ", "   S   ", " TTTTSS", " TTTT  ", "  TTT  ", "  WWW  ", "  W W  ", "  W W  ", " WW WW "];
const BATTER_X = 49, BATTER_Y = 18;
// Infielders and outfielders as dots in the batting view.
const DOTS = [[97, 19], [79, 14], [49, 14], [31, 19], [22, 11], [64, 10], [106, 11]];
const BASE_DOTS = [[101, 20], [66, 11], [25, 20]]; // where runners stand in the batting view

function rhombus(b: PixelBuffer, top: number, mid: number, bottom: number, half: number, color: Color) {
  for (let y = top; y <= bottom; y++) {
    const w = y <= mid ? div((y - top) * half, mid - top) : div((bottom - y) * half, bottom - mid);
    b.fillRect(64 - w, y, 2 * w + 1, 1, color);
  }
}
function sprite(b: PixelBuffer, rows: string[], x0: number, y0: number, team: Color) {
  const colors: Record<string, Color> = { T: team, S: SKIN, W: PANTS, K: BAT };
  rows.forEach((cells, row) => [...cells].forEach((cell, col) => { if (cell !== " ") b.setPixel(x0 + col, y0 + row, colors[cell]); }));
}
function ball(b: PixelBuffer, x: number, y: number, size: number) {
  if (size === 1) b.setPixel(x, y, WHITE);
  else if (size === 2) b.fillRect(x, y, 2, 2, WHITE);
  else { b.fillRect(x - 1, y, 3, 1, WHITE); b.fillRect(x, y - 1, 1, 3, WHITE); }
}
function dots(b: PixelBuffer, text: Text, label: string, y: number, lit: number, total: number, color: Color) {
  text(label, 2, y, DIM);
  for (let i = 0; i < total; i++) b.fillRect(8 + i * 3, y + 2, 2, 2, i < lit ? color : OFF);
}
const cache = new Map<string, Uint8ClampedArray>(); // static backgrounds, drawn once
function cached(b: PixelBuffer, key: string, draw: (b: PixelBuffer) => void) {
  if (!cache.has(key)) { draw(b); cache.set(key, b.data.slice()); }
  b.data.set(cache.get(key)!);
}
function ballpark(b: PixelBuffer) {
  b.fillRect(0, 7, 128, 3, WALL); b.fillRect(0, 7, 128, 1, FENCE_TOP);
  for (let y = 10; y < 32; y++) {
    const w = Math.min(64, div((31 - y) * 64, 17));
    b.fillRect(0, y, 128, 1, FOUL); b.fillRect(64 - w, y, 2 * w + 1, 1, GRASS);
  }
  rhombus(b, 10, 21, 31, 38, DIRT); rhombus(b, 15, 21, 28, 26, INFIELD);
  for (let y = 10; y < 32; y++) {
    const w = Math.min(64, div((31 - y) * 64, 17));
    if (w < 64) { b.setPixel(64 - w, y, CHALK); b.setPixel(64 + w, y, CHALK); }
  }
  b.fillRect(62, 18, 5, 2, DIRT);
  for (const [x, y] of [[99, 21], [64, 12], [28, 21]]) b.fillRect(x - 1, y, 2, 1, WHITE);
  b.fillRect(62, 29, 5, 1, WHITE); b.fillRect(63, 30, 3, 1, WHITE);
}
function batting(b: PixelBuffer, s: State, text: Text) {
  const [offense, defense] = s.half === 0 ? [TEAL, GOLD] : [GOLD, TEAL];
  cached(b, "ballpark", ballpark);
  for (const [x, y] of DOTS) b.fillRect(x, y, 1, 2, defense);
  for (const runner of s.runners) {
    const k = div(runner[1], 90 * 64);
    if (k >= 1 && k <= 3) { const [x, y] = BASE_DOTS[k - 1]; b.fillRect(x, y - 1, 2, 3, offense); }
  }
  // Pitcher on the mound; the throwing arm goes up during the windup.
  const windup = (s.phase === "wait" && s.timer >= WAIT_MS - WINDUP_MS) || s.phase === "meter";
  b.setPixel(64, 13, SKIN); b.fillRect(63, 14, 3, 2, defense); b.setPixel(63, 16, PANTS); b.setPixel(65, 16, PANTS);
  if (windup) { b.setPixel(66, 12, defense); b.setPixel(66, 13, defense); }
  // Strike zone, then the cursor (where YOU swing or aim).
  b.strokeRect(58, 17, 12, 9, FAINT);
  if (s.half === 0 || s.phase === "aim" || s.phase === "meter") {
    const cx = 58 + 4 * (s.aimCol + 1), cy = 17 + 3 * (s.aimRow + 1);
    for (const [dx, dy] of [[0, 0], [3, 0], [0, 2], [3, 2]]) b.setPixel(cx + dx, cy + dy, TEAL);
  }
  const swinging = s.swing >= 0 && (s.phase === "pitch" || s.phase === "result");
  sprite(b, swinging ? SWUNG : STANCE, BATTER_X, BATTER_Y, offense);
  if (swinging) {
    if (s.swing < 160) b.drawLine(BATTER_X + 6, BATTER_Y + 5, BATTER_X + 17, BATTER_Y + 5, BAT);
    else b.drawLine(BATTER_X + 2, BATTER_Y + 4, BATTER_X - 3, BATTER_Y + 1, BAT);
  }
  if (s.phase === "pitch") {
    const p = div(s.pitchT * 1024, s.pitchMs);
    if (p <= 1100) {
      const q = div(p * p, 1024), ex = 64 + 4 * s.pitchCol, ey = 21 + 3 * s.pitchRow;
      const drop = s.pitchType === 1 && q < 1024 ? div(3 * (1024 - q), 1024) : 0;
      ball(b, 64 + div((ex - 64) * q, 1024), 15 + div((ey - 15) * q, 1024) - drop, p < 350 ? 1 : p < 750 ? 2 : 3);
    }
  }
  const you = `YOU ${s.you}`, pi = `PI ${s.pi}`;
  text(you, 1, 0, TEAL); text(pi, 128 - pi.length * 4, 0, GOLD);
  const inning = `${s.half === 0 ? "TOP" : "BOT"} ${s.inning}`;
  text(inning, 64 - inning.length * 2, 0, WHITE);
  dots(b, text, "B", 11, s.balls, 3, GREEN); dots(b, text, "S", 18, s.strikes, 2, RED); dots(b, text, "O", 25, s.outs, 2, RED);
  if (s.half === 1 && (s.phase === "aim" || s.phase === "meter" || s.phase === "pitch")) {
    const name = `<${PITCHES[s.pitchType][0]}>`;
    text(name, 110 - name.length * 2, 26, WHITE);
    b.strokeRect(95, 20, 31, 4, FAINT); b.fillRect(110, 19, 1, 6, GOLD);
    if (s.phase === "aim") text("A", 108, 13, GOLD);
    else {
      const m = s.phase === "meter" ? meterValue(s.timer) : s.meter;
      if (m >= 0) b.fillRect(96 + div(m * 28, 100), 21, 2, 2, WHITE);
    }
  }
  if (s.phase === "result" && s.call) {
    const w = s.call.length * 4;
    b.fillRect(62 - div(w, 2), 8, w + 4, 8, BLACK);
    text(s.call, 64 - div(w, 2), 9, s.call === "WALK" || s.call === "STRIKEOUT!" ? GOLD : WHITE);
  }
}
/** Field position (1/64 ft) to the flattened top-down view. */
export function project(x: number, y: number): [number, number] { return [64 + div(x * 27 + 3200, 6400), 30 - div(y * 85 + 32000, 64000)]; }
function diamond(b: PixelBuffer) {
  for (let sx = 0; sx < 128; sx++) {
    const wx = div(Math.abs(sx - 64) * 6400, 27), fence = isqrt(Math.max(0, FENCE * FENCE - wx * wx));
    const top = 30 - div(fence * 85 + 32000, 64000), line = 30 - div(wx * 85 + 32000, 64000);
    b.fillRect(sx, top, 1, line - top + 1, GRASS); b.fillRect(sx, top - 1, 1, 1, FENCE_TOP); b.setPixel(sx, line, CHALK);
  }
  const points = BASES.map(([x, y]) => project(x, y));
  for (let i = 0; i < 4; i++) { const [ax, ay] = points[i], [bx, by] = points[(i + 1) % 4]; b.drawLine(ax, ay, bx, by, DIRT); }
  b.fillRect(63, 25, 2, 1, DIRT);
  for (const [x, y] of points) b.fillRect(x, y, 2, 1, WHITE);
}
function field(b: PixelBuffer, s: State, text: Text) {
  const [offense, defense] = s.half === 0 ? [TEAL, GOLD] : [GOLD, TEAL];
  cached(b, "field", diamond);
  for (const [fx, fy] of s.fielders) { const [x, y] = project(fx, fy); b.fillRect(x - 1, y - 1, 2, 2, defense); }
  for (const runner of s.runners) { const [x, y] = project(...basePoint(runner[0])); b.fillRect(x - 1, y - 2, 2, 3, offense); }
  const [x, y] = project(s.ball[0], s.ball[1]), lift = div(s.ball[2], 512);
  if (lift > 0) b.setPixel(x, y, SHADOW);
  b.setPixel(x, y - lift, WHITE);
  for (let i = 0; i < 2; i++) b.fillRect(121 + i * 3, 1, 2, 2, i < s.outs ? RED : OFF);
  if (s.phase === "result" && s.call) {
    const w = s.call.length * 4;
    b.fillRect(62 - div(w, 2), 0, w + 4, 7, BLACK);
    text(s.call, 64 - div(w, 2), 1, GOLD);
  }
}
function lineScore(b: PixelBuffer, s: State, text: Text) {
  const innings = Math.max(INNINGS, s.lineYou.length);
  for (let i = 0; i < innings; i++) text(String(i + 1), 26 + i * 9, 1, DIM);
  const totalX = 30 + innings * 9;
  text("R", totalX, 1, GOLD);
  ([["YOU", s.lineYou, s.you, TEAL], ["PI", s.linePi, s.pi, GOLD]] as const).forEach(([name, line, total, color], row) => {
    const y = 9 + row * 8;
    text(name, 2, y, color);
    line.forEach((runs, i) => text(String(runs), 26 + i * 9 - (String(runs).length - 1) * 4, y, WHITE));
    text(String(total), totalX - (String(total).length - 1) * 4, y, GOLD);
  });
  b.drawLine(0, 7, 127, 7, FAINT);
  const note = s.half === 0 ? `TOP ${s.inning}: YOU BAT` : `BOTTOM ${s.inning}: YOU PITCH`;
  text(note, 64 - note.length * 2, 25, GOLD);
}
export function bigLeagueFrame(b: PixelBuffer, s: State, text: Text) {
  if (s.phase === "switch" && s.status === "running") lineScore(b, s, text);
  else if (s.view === "field" && (s.phase === "play" || s.phase === "result")) field(b, s, text);
  else batting(b, s, text);
}
