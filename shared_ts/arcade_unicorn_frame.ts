// Rainbow Toot Unicorn pictures, pixel-exact counterpart of shared_py/arcade_unicorn_frame.py.
// Speech bubbles, comic action words, a bottom ticker and full-screen scenes replace sound.
// Nothing flashes the whole panel: flashes are borders or text, at most a couple of times a second.
import type { PixelBuffer } from "./renderer";
import { CURSE_MS, DANCE_REPS_MS, FP, GROUND_ROW, SEG, STAR_MAX, UX, objectY, unicornObject, type UnicornFields, type UnicornObject } from "./arcade_unicorn";

type Color = readonly [number, number, number, number];
type Text = (s: string, x: number, y: number, color?: Color, scale?: number) => void;
interface State extends UnicornFields { status: string; time: number; seed: number }
const WHITE: Color = [221, 240, 237, 255], GOLD: Color = [255, 201, 58, 255], RED: Color = [255, 70, 88, 255], DARK_RED: Color = [120, 20, 30, 255];
const CYAN: Color = [60, 220, 255, 255], MAGENTA: Color = [255, 60, 200, 255], BLACK: Color = [0, 0, 0, 255], DIM: Color = [90, 140, 130, 255], OFF: Color = [40, 30, 50, 255];
const BODY: Color = [235, 235, 255, 255], LEG: Color = [190, 170, 215, 255], EYE: Color = [70, 20, 110, 255], HORN: Color = [200, 180, 110, 255];
const GRASS: Color = [60, 200, 90, 255], SOIL: Color = [30, 10, 45, 255], SPARKLE: Color = [255, 120, 220, 255], SKY_DOT: Color = [50, 40, 90, 255];
const AMBER: Color = [255, 170, 30, 255], STRIPE: Color = [130, 70, 0, 255], DOOR: Color = [40, 15, 0, 255], BEE: Color = [255, 240, 60, 255];
const STAR: Color = [255, 230, 60, 255], APPLE: Color = [255, 40, 40, 255], STEM: Color = [60, 200, 60, 255], SHELL: Color = [150, 100, 50, 255], FUSE: Color = [255, 140, 0, 255];
const ROBOT_RED: Color = [255, 40, 40, 255], ROBOT_CYAN: Color = [40, 230, 255, 255];
const RAINBOW: Color[] = [[255, 40, 40, 255], [255, 140, 0, 255], [255, 230, 0, 255], [40, 220, 60, 255], [40, 120, 255, 255], [170, 60, 255, 255]];
const div = (a: number, b: number) => Math.floor(a / b);
const mod = (a: number, n: number) => ((a % n) + n) % n;

// Unicorn 10 x 8 facing right. W body, M mane/tail (rainbow by row), H horn, E eye, L legs.
const RUN = [["        H ", "      MWW ", "     MWWEW", "M   MWWW  ", "MMWWWWWW  ", " MWWWWWW  ", "  L L  L L", "  L L  L L"],
  ["        H ", "      MWW ", "     MWWEW", "M   MWWW  ", "MMWWWWWW  ", " MWWWWWW  ", "   LL   LL", "  L  L L L"]];
const FLY = ["        H ", "      MWW ", "     MWWEW", "M   MWWW  ", "MMWWWWWW  ", " MWWWWWW  ", "  LL   LL ", "          "];
const REAR = ["       H  ", "      MWW ", "     MWWEW", "    MWWLL ", "   MWWW L ", " MWWWW    ", "MM  L     ", "    L L   "];
const ROBOT = ["      A   ", "    GGGGG ", "    GRGRG ", "    GGGGG ", " GGGGGGG  ", " GGGGGGG  ", "  G    G  ", "  G    G  "];
const HIVE = ["  AAA  ", " ASSSA ", " AAAAA ", "ASSSSSA", "AAAAAAA", "ASSDSSA", "AAAAAAA"];
const SPLATTED = ["       ", "       ", "       ", "       ", " A S A ", "ASAASAA", "AAASAAA"];
const STAR_ART = [["  Y  ", " YYY ", "YYYYY", " YYY ", " Y Y "], ["Y   Y", " YYY ", " YWY ", " YYY ", "Y   Y"]];
const APPLE_ART = ["  G ", " RR ", "RRRR", " RR "];
const BOMB_ART = ["   F ", " SS  ", "SSSS ", "SSSS ", " SS  "];
const GLASSES_ART = ["WWWWWW", "RRWWCC", "RR  CC"];
const TROPHY = [" YYYYYYYYYY ", "YYYYYYYYYYYY", "Y YYYYYYYY Y", "Y YYYYYYYY Y", " YYYYYYYYYY ", "  YYYYYYYY  ",
  "   YYYYYY   ", "    YYYY    ", "     YY     ", "     YY     ", "   YYYYYY   ", "  YYYYYYYY  "];

function art(b: PixelBuffer, rows: string[], x: number, y: number, colors: Record<string, Color>) {
  rows.forEach((cells, r) => [...cells].forEach((cell, c) => { if (cell !== " ") b.setPixel(x + c, y + r, colors[cell]); }));
}
/** 3D-glasses look: a red copy one pixel left, a cyan copy one pixel right, white where they meet. */
function anaglyph(b: PixelBuffer, rows: string[], x: number, y: number) {
  const width = rows[0].length;
  rows.forEach((cells, r) => {
    for (let c = -1; c <= width; c++) {
      const red = c + 1 >= 0 && c + 1 < width && cells[c + 1] !== " ", cyan = c - 1 >= 0 && c - 1 < width && cells[c - 1] !== " ";
      if (red || cyan) b.setPixel(x + c, y + r, red && cyan ? BODY : red ? ROBOT_RED : ROBOT_CYAN);
    }
  });
}
function unicorn(b: PixelBuffer, s: State, x: number, y: number, rows?: string[]) {
  const t = s.time;
  if (!rows) rows = s.y >= 19 * FP ? RUN[div(t, 120) % 2] : FLY;
  const hurt = s.invuln > 0 && div(s.invuln, 100) % 2 === 0;
  let horn = HORN;
  if (s.bands >= 1 && s.bands <= 2) horn = div(t, 150) % 2 ? GOLD : CYAN;
  const colors: Record<string, Color> = { W: hurt ? RED : BODY, H: horn, E: EYE, L: LEG };
  rows.forEach((cells, r) => {
    colors.M = RAINBOW[(r + div(t, 200)) % 6];
    [...cells].forEach((cell, c) => { if (cell !== " ") b.setPixel(x + c, y + r, colors[cell]); });
  });
  if (s.dash > 0) b.drawLine(x + 9, y, x + 12, y - 1, GOLD);
  if (s.invuln > 0) {
    for (let k = 0; k < 2; k++) {
      const a = (div(t, 80) + k * 4) % 8;
      b.setPixel(x + 2 + (a < 4 ? a : 8 - a) * 2, y - 1 - (k + a) % 2, AMBER);
    }
  }
}
/** Rainbow toot exhaust behind the unicorn: three bands with sparks. */
function trail(b: PixelBuffer, x: number, y: number, length: number, t: number) {
  for (let k = 0; k < length; k++) for (let band = 0; band < 3; band++) b.setPixel(x - 1 - k, y + 3 + band, RAINBOW[(band * 2 + (k + div(t, 60)) % 2) % 6]);
  for (let k = 0; k < 3; k++) {
    const spark = (div(t, 40) + k * 5) % 9;
    b.setPixel(x - length - 1 - spark, y + 2 + (k * 3 + div(t, 70)) % 5, RAINBOW[(k * 2 + div(t, 90)) % 6]);
  }
}
function hive(b: PixelBuffer, x: number, y: number, t: number, splat = false) {
  art(b, splat ? SPLATTED : HIVE, x, y, { A: AMBER, S: STRIPE, D: DOOR });
  if (!splat) for (let k = 0; k < 2; k++) {
    const a = (div(t, 90) + k * 5) % 10;
    b.setPixel(x + (a < 6 ? a : 12 - a), y - 2 + (k + a) % 2, BEE);
  }
}
function drawObject(b: PixelBuffer, obj: UnicornObject, x: number, t: number) {
  const kind = obj[0], y = objectY(obj, t);
  if (kind === "hive") hive(b, x, y, t);
  else if (kind === "star") art(b, STAR_ART[(div(t, 250) + obj[1]) % 2], x, y, { Y: STAR, W: WHITE });
  else if (kind === "apple") art(b, APPLE_ART, x, y, { R: APPLE, G: STEM });
  else if (kind === "bomb") art(b, BOMB_ART, x, y, { S: SHELL, F: div(t, 100) % 2 ? WHITE : FUSE });
  else if (kind === "band") {
    const [a, c] = div(t, 200) % 2 ? [MAGENTA, CYAN] : [CYAN, MAGENTA];
    for (let k = 0; k < 5; k++) b.fillRect(x + k, y, 1, 3, k % 2 ? a : c);
  } else if (kind === "glasses") art(b, GLASSES_ART, x, y, { W: WHITE, R: ROBOT_RED, C: ROBOT_CYAN });
  else for (let k = 0; k < 3; k++) { // bee swarm: three bees buzzing around a point
    const a = (div(t, 70) + k * 3) % 6, bx = x + (k * 2 + (a < 3 ? a : 6 - a)) % 5, by = y + (k + div(a, 2)) % 4;
    b.setPixel(bx, by, BEE); b.setPixel(bx + 1, by, STRIPE);
  }
}
function ground(b: PixelBuffer, cam: number, oy: number) {
  b.fillRect(0, GROUND_ROW + oy, 128, 1, GRASS); b.fillRect(0, GROUND_ROW + 1 + oy, 128, 4, SOIL);
  for (let k = 0; k < 10; k++) b.setPixel((k * 13 - cam % 13 + 13) % 130, GROUND_ROW + 2 + k % 3 + oy, SPARKLE);
}
function sky(b: PixelBuffer, cam: number, t: number) {
  for (let k = 0; k < 9; k++) if ((k + div(t, 500)) % 4) b.setPixel(mod(k * 29 + 5 - div(cam, 4), 128), 8 + (k * 7) % 15, SKY_DOT);
}
function world(b: PixelBuffer, s: State, oy = 0) {
  const t = s.time, cam = div(s.cam, FP);
  sky(b, cam, t);
  for (let i = Math.max(0, div(cam, SEG) - 1); i < div(cam + 128, SEG) + 1; i++) for (const slot of [0, 1]) {
    const obj = unicornObject(s.seed, i, slot);
    if (obj && !s.gone.includes(i * 2 + slot)) drawObject(b, [obj[0], obj[1], obj[2] + oy], obj[1] - cam, t);
  }
  ground(b, cam, oy);
  for (const shot of s.shots) {
    const x = div(shot[0] + FP / 2, FP) - cam, y = div(shot[1] + FP / 2, FP) + oy;
    b.fillRect(x - 1, y - 1, 3, 3, SHELL); b.setPixel(x, y - 2, FUSE);
  }
}
function boxed(b: PixelBuffer, text: Text, word: string, x: number, y: number, color: Color) {
  b.fillRect(x - 1, y, word.length * 4 + 1, 7, BLACK); text(word, x, y, color);
}
function bursts(b: PixelBuffer, s: State, text: Text) {
  const cam = div(s.cam, FP);
  for (const [word, wx, wy, age] of s.fx) {
    const x = wx - cam, y = wy - div(age, 140);
    if (word === "TOOT!" || word === "PFFT!") {
      b.fillRect(x - 1, y, word.length * 4 + 1, 7, BLACK);
      [...word].forEach((ch, k) => text(ch, x + k * 4, y, RAINBOW[(k + div(age, 80)) % 6]));
    } else if (word === "BOOM!" || word === "SPLAT!") boxed(b, text, word, x, y, div(age, 100) % 2 ? GOLD : FUSE);
    else if (word === "OUCH!" || word === "BZZZ!") boxed(b, text, word, x, y, div(age, 120) % 2 === 0 ? RED : WHITE);
    else boxed(b, text, word, x, y, GOLD);
  }
}
/** Speech bubble over the unicorn's head (beside it when there is no room above). */
function bubble(b: PixelBuffer, word: string, ms: number, text: Text, x: number, y: number) {
  const w = word.length * 4 + 3;
  let left = Math.max(0, Math.min(127 - w, x + 5 - div(w, 2))), top = y - 11 + (ms > 1400 ? 1 : 0);
  const beside = top < 6;
  if (beside) { left = Math.min(127 - w, x + 12); top = Math.max(6, y - 1); }
  if (ms < 150) { b.setPixel(left + 2, top + 3, CYAN); b.setPixel(left + w - 3, top + 5, WHITE); return; } // pops into two particles
  b.fillRect(left, top, w, 9, BLACK); b.strokeRect(left, top, w, 9, CYAN);
  text(word, left + 2, top + 2, WHITE);
  if (beside) b.setPixel(left - 1, top + 4, CYAN); else b.setPixel(x + 7, top + 9, CYAN);
}
function ticker(b: PixelBuffer, s: State, text: Text, y = 26) {
  if (!s.ticker) return;
  b.fillRect(0, y, 128, 32 - y, BLACK);
  text(s.ticker, 128 - div(s.tickerT, 25), y, GOLD);
}
function clock(s: State) { const seconds = div(s.clock + 999, 1000); return `${div(seconds, 60)}:${String(seconds % 60).padStart(2, "0")}`; }
function hud(b: PixelBuffer, s: State, text: Text) {
  const t = s.time;
  b.fillRect(0, 0, 128, 6, BLACK);
  art(b, APPLE_ART, 1, 1, { R: APPLE, G: STEM });
  text(`x${s.health}`, 6, 0, s.health === 1 && div(t, 300) % 2 ? RED : WHITE);
  art(b, STAR_ART[0], 19, 0, { Y: STAR });
  text(`${String(s.stars).padStart(2, "0")}/${STAR_MAX}`, 25, 0, s.stars >= 5 ? GOLD : WHITE);
  text(clock(s), 50, 0, s.clock <= 10_000 ? (div(t, 500) % 2 ? RED : GOLD) : WHITE);
  art(b, BOMB_ART.slice(1), 70, 1, { S: SHELL });
  text(String(s.bombs), 75, 0, WHITE);
  for (let k = 0; k < 4; k++) b.fillRect(84 + k * 5, 1, 3, 4, k < s.bands ? (k % 2 ? MAGENTA : CYAN) : OFF);
  if (s.bands >= 1 && s.bands <= 2) b.drawLine(104, 4, 106, 1, GOLD);
  if (s.curse) text("6 7", 112, 0, GOLD);
}
function play(b: PixelBuffer, s: State, text: Text) {
  const oy = s.shake > 0 && div(s.shake, 40) % 2 ? 1 : 0;
  world(b, s, oy);
  const uy = div(s.y + FP / 2, FP) + oy;
  if (s.trail > 0) trail(b, UX, uy, 6 + div(s.trail, 100), s.time);
  unicorn(b, s, UX, uy);
  bursts(b, s, text);
  if (s.bubble && s.bubbleMs > 0) bubble(b, s.bubble, s.bubbleMs, text, UX, uy);
  hud(b, s, text);
  ticker(b, s, text);
}
/** SIX SEVEN dancer: one arm straight up, the other straight down, swapping. */
function stick(b: PixelBuffer, x: number, y: number, flip: boolean, color: Color) {
  b.fillRect(x - 1, y, 3, 3, color); b.drawLine(x, y + 3, x, y + 9, color);
  const up = flip ? -1 : 1, down = flip ? 1 : -1;
  b.drawLine(x + up, y + 4, x + up * 3, y - 1, color); b.drawLine(x + down, y + 5, x + down * 3, y + 9, color);
  b.drawLine(x, y + 9, x - 2, y + 14, color); b.drawLine(x, y + 9, x + 2, y + 14, color);
}
function border(b: PixelBuffer, t: number, color: Color) { if (div(t, 500) % 2 === 0) b.strokeRect(0, 0, 128, 32, color); }
function dance(b: PixelBuffer, s: State, text: Text) {
  const t = s.timer, flip = div(t, 500) % 2 === 1;
  border(b, t, GOLD);
  text("DANCE SIX SEVEN!", 28, 2, GOLD); text(clock(s), 108, 2, WHITE);
  unicorn(b, s, 8 + (flip ? 1 : 0), 15, RUN[0]);
  stick(b, 112, 11, flip, CYAN);
  text(`SIX SEVEN ${Math.min(6, div(t, 500) + 1)}/6`, 32, 12, WHITE);
  if (t >= DANCE_REPS_MS) { if (div(t, 400) % 3) text("PRESS A WHEN DONE", 24, 22, GOLD); }
  else text("STAND UP + DANCE", 26, 22, DIM);
}
function curse(b: PixelBuffer, s: State, text: Text) {
  const t = s.timer, flip = div(t, 500) % 2 === 1;
  border(b, t, MAGENTA);
  text("STAR CURSE!", 36, 2, MAGENTA); text(clock(s), 108, 2, WHITE);
  stick(b, 112, 11, flip, CYAN);
  text("SIX SEVEN + SHAKE!", 22, 10, WHITE);
  // The unicorn shakes its rainbow tail at you.
  const wiggle = div(t, 150) % 2;
  unicorn(b, s, 6, 18, RUN[0].map(row => row.slice(0, 2).replace(/M/g, " ") + row.slice(2)));
  for (let r = 0; r < 3; r++) {
    b.setPixel(5 - wiggle, 21 + r, RAINBOW[(r + div(t, 100)) % 6]);
    b.setPixel(6 - wiggle, 22 + r, RAINBOW[(r + 2 + div(t, 100)) % 6]);
  }
  art(b, STAR_ART[0], 44, 22, { Y: STAR });
  text(String(div(CURSE_MS - t + 999, 1000)), 52, 19, GOLD, 2);
}
const ROBOT_HITS = [0, 1, 2, 3, 4, 5].map(k => 700 + k * 1000);
function robot(b: PixelBuffer, s: State, text: Text) {
  const t = s.timer, cam = div(s.cam, FP);
  sky(b, cam, s.time); ground(b, cam, 0);
  ROBOT_HITS.forEach((hitAt, k) => {
    const x = 34 + div((hitAt - t) * 48, 1000);
    if (x > -8 && x < 128) {
      if (t >= hitAt) art(b, SPLATTED, x, GROUND_ROW - 7, { A: AMBER, S: STRIPE });
      else anaglyph(b, HIVE, x, GROUND_ROW - 7);
    }
    if (t >= hitAt && t < hitAt + 600) boxed(b, text, `#${k + 1}!`, x, 12 - div(t - hitAt, 150), div(t, 100) % 2 ? GOLD : RED);
  });
  const d = Math.abs(mod(t - 200, 1000) - 500), y = 19 - div(d * 10, 500);
  trail(b, 30, y, 9, s.time);
  anaglyph(b, ROBOT, 30, y);
  const word = div(t, 600) % 2 ? "PFFT!" : "TOOT!";
  [...word].forEach((ch, k) => text(ch, 6 + k * 4, Math.max(6, y - 3), RAINBOW[(k + div(t, 80)) % 6]));
  text("3D ROBOT MODE!", 35, 0, ROBOT_RED); text("3D ROBOT MODE!", 37, 0, ROBOT_CYAN);
}
function loseScene(b: PixelBuffer, s: State, text: Text) {
  const t = s.timer;
  text("YOU LOSE!", 28, 0, div(t, 300) % 2 === 0 ? RED : DARK_RED, 2);
  const hives = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map(k => 113 - k * 12);
  let x: number, y: number;
  if (t < 1100) {
    x = UX; y = 19 - div(6 * Math.max(0, t - 600), 500);
    const target = x + 5;
    for (const edge of [0, 127]) b.fillRect(edge + div((target - edge) * Math.min(t, 600), 600), 13, 1, y - 13 + 8, div(t, 80) % 2 ? CYAN : WHITE);
  } else if (t < 3100) { x = 118 - div((t - 1100) * 128, 2000); y = 18; }
  else { x = -20; y = 18; }
  hives.forEach((hx, k) => {
    const smashed = t >= 1100 && x <= hx + 3;
    hive(b, hx, 25, s.time, smashed);
    if (smashed && t < 3100 && hx - 8 < x) boxed(b, text, `#${k + 1}!`, hx - 1, 15, GOLD);
  });
  if (x > -12) unicorn(b, s, x, y, FLY);
  if (t >= 3100) for (let k = 0; k < 24; k++) {
    const r = div(t - 3100, 25), a = k * 15;
    b.setPixel(64 + div(r * (a % 7 - 3), 3), 16 + div(r * (div(a, 7) % 5 - 2), 4), k % 3 ? RAINBOW[k % 6] : GOLD);
  }
}
function confetti(b: PixelBuffer, t: number) {
  for (let k = 0; k < 30; k++) {
    const h = (k * 2654435761) >>> 0;
    if ((k + div(t, 150)) % 3) b.setPixel(h % 128, ((h >>> 8) % 32 + div(t, 50)) % 32, RAINBOW[(k + div(t, 200)) % 6]);
  }
}
function win(b: PixelBuffer, s: State, text: Text) {
  world(b, s);
  unicorn(b, s, 59, 19, REAR);
  confetti(b, s.timer);
  bubble(b, "PRIZE!", 1000, text, 59, 19);
  hud(b, s, text);
}
function grand(b: PixelBuffer, s: State, text: Text) {
  const t = s.timer, x = -10 + div(Math.min(t, 2500) * 138, 2500);
  for (let row = 0; row < 13; row++) b.fillRect(0, 10 + row, Math.max(0, x), 1, RAINBOW[Math.min(5, div(row, 2))]);
  if (t < 2500) unicorn(b, s, x, 11, RUN[div(t, 120) % 2]);
  else { b.fillRect(56, 9, 16, 14, BLACK); art(b, TROPHY, 58, 10, { Y: div(t, 300) % 2 ? GOLD : WHITE }); }
  confetti(b, t);
  b.fillRect(0, 0, 128, 7, BLACK);
  text("10 STARS!", 46, 1, GOLD);
  b.fillRect(0, 26, 128, 6, BLACK);
  const message = "*** PERFECT 10 STARS! GRAND PRIZE WINNER! ***";
  text(message, 128 - div(t, 20) % (128 + message.length * 4), 26, GOLD);
}
function intro(b: PixelBuffer, s: State, text: Text) {
  world(b, s);
  unicorn(b, s, UX, 19, RUN[0]);
  [..."RAINBOW TOOT UNICORN"].forEach((ch, k) => text(ch, 24 + k * 4, 7, RAINBOW[(k + div(s.timer, 120)) % 6]));
  text("A TOOT  B BOMB  R HORN", 20, 14, WHITE);
  const message = "GET 5 STARS TO WIN, 10 FOR A GREAT PRIZE! TOOT OVER THE BEES!  PRESS A";
  b.fillRect(0, 26, 128, 6, BLACK);
  text(message, 128 - div(s.timer, 25) % (128 + message.length * 4), 26, GOLD);
  hud(b, s, text);
}
export function unicornFrame(b: PixelBuffer, s: State, text: Text) {
  ({ intro, play, dance, curse, robot, lose: loseScene, win, grand })[s.phase](b, s, text);
}
