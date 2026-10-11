// Rainbow Toot Unicorn rules, mirrored line for line in shared_py/arcade_unicorn.py.
// A toots (rainbow boost), B throws a bomb, R horn-dashes with one or two headbands. Stars win
// (5, or 10 for the great prize) in two minutes; the 4th headband means the SIX SEVEN dance, after
// which every star brings a 10 second curse; 3D glasses turn the unicorn into a crashing 3D robot.
// Objects come from a seeded hash per 24 px segment. Everything is an integer.
export type UnicornPhase = "intro" | "play" | "dance" | "curse" | "robot" | "lose" | "win" | "grand";
export type UnicornObject = [string, number, number];
export interface UnicornFields {
  phase: UnicornPhase; timer: number; clock: number; cam: number; y: number; vy: number; toots: number; trail: number;
  health: number; bombs: number; bands: number; stars: number; curse: boolean; invuln: number; dash: number;
  hornCool: number; shake: number; gone: number[]; shots: number[][]; fx: [string, number, number, number][];
  bubble: string; bubbleMs: number; ticker: string; tickerT: number; score: number; gems: number; gemValue: number;
}
interface Header { status: "ready" | "running" | "over"; time: number; seed: number; message: string }
type S = Header & UnicornFields;

const STEP_MS = 20;
export const FP = 256, SEG = 24, UX = 24, GROUND_ROW = 27, STAR_MAX = 10, CURSE_MS = 10_000, DANCE_REPS_MS = 3000;
const ROUND_MS = 120_000, TOP_Y = 7 * FP, GROUND_Y = 19 * FP, SPEED = 150, GRAVITY = 7, TOOT = -165, FALL_MAX = 230;
const HEALTH_START = 3, HEALTH_MAX = 5, BOMBS_START = 3, BOMBS_MAX = 9, BOMB_PICKUP = 2;
const BOMB_VX = SPEED + 110, BOMB_VY = 60, BOMB_GRAVITY = 9, INVULN_MS = 1500, DASH_MS = 300, HORN_COOL_MS = 900;
const DANCE_LIMIT_MS = 15_000, ROBOT_MS = 7000, LOSE_MS = 3600, WIN_MS = 3000, GRAND_MS = 5000, INTRO_MS = 8000;
const FX_MS = 700, BUBBLE_MS = 1500, STAR_GOAL = 5;
export const SIZES: Record<string, [number, number]> = { hive: [7, 7], star: [5, 5], apple: [4, 4], bomb: [5, 5], band: [5, 3], glasses: [6, 3], swarm: [5, 4] };
const PICKUPS = ["star", "apple", "bomb", "band", "glasses"];
// Chance (percent) of each air object per segment; the rest of the sky is empty.
const AIR: [string, number][] = [["star", 9], ["apple", 6], ["bomb", 7], ["band", 5], ["swarm", 5], ["glasses", 2]];
const HIVE_CHANCE = 27;

const rand = (seed: number) => (Math.imul(seed, 1664525) + 1013904223) >>> 0;
const hash = (seed: number, n: number) => rand(rand((seed + n * 2654435761) >>> 0));
const div = (a: number, b: number) => Math.floor(a / b);
const px = (v: number) => div(v + FP / 2, FP);

/** [kind, x, y] in world pixels for segment i (slot 0 ground, 1 air), or null. */
export function unicornObject(seed: number, i: number, slot: number): UnicornObject | null {
  if (i < 4) return null;
  const h = hash(seed, i * 2 + slot);
  if (slot === 0) return (h >>> 8) % 100 < HIVE_CHANCE ? ["hive", i * SEG + 5 + (h >>> 16) % 12, GROUND_ROW - 7] : null;
  let roll = (h >>> 8) % 100;
  const x = i * SEG + 2 + (h >>> 16) % 14, y = 8 + (h >>> 21) % 9;
  for (const [kind, chance] of AIR) {
    if (roll < chance) {
      if ((kind === "band" && i < 8) || (kind === "glasses" && (i < 30 || i % 5))) return null;
      if (kind === "swarm") return [kind, x, 9 + (h >>> 21) % 7];
      if (kind === "glasses") return [kind, x, 8 + (h >>> 21) % 4]; // always up high: a unicorn on the ground runs under them
      return [kind, x, y];
    }
    roll -= chance;
  }
  return null;
}
/** Swarms bob up and down; everything else stays put. */
export function objectY(obj: UnicornObject, time: number) {
  if (obj[0] !== "swarm") return obj[2];
  const t = (div(time, 60) + obj[1]) % 8;
  return obj[2] + (t < 4 ? t : 8 - t) - 2;
}
export function createUnicorn<T extends Header>(base: T): T & UnicornFields {
  return { ...base, phase: "intro", timer: 0, clock: ROUND_MS, cam: 0, y: GROUND_Y, vy: 0, toots: 0, trail: 0,
    health: HEALTH_START, bombs: BOMBS_START, bands: 0, stars: 0, curse: false, invuln: 0, dash: 0,
    hornCool: 0, shake: 0, gone: [], shots: [], fx: [], bubble: "", bubbleMs: 0, ticker: "", tickerT: 0, score: 0, gems: 0, gemValue: 1 };
}
function copy<T extends S>(state: T): T {
  return { ...state, gone: [...state.gone], shots: state.shots.map(s => [...s]), fx: state.fx.map(f => [...f] as [string, number, number, number]) };
}
function say(s: S, text: string) { s.bubble = text; s.bubbleMs = BUBBLE_MS; }
function tick(s: S, text: string) { s.ticker = text; s.tickerT = 0; }
/** Comic action word at world pixel (x, y). */
function burst(s: S, word: string, x: number, y: number) { s.fx.push([word, x, y, 0]); }
function phaseTo(s: S, phase: UnicornPhase) { s.phase = phase; s.timer = 0; }
function lose(s: S) { phaseTo(s, "lose"); s.bubble = ""; }
function registerStar(s: S) {
  s.stars += 1; s.score = s.stars; s.gems += 2 * s.gemValue;
  if (s.stars >= STAR_MAX) { s.gems += 50 * s.gemValue; phaseTo(s, "grand"); }
  else if (s.stars === STAR_GOAL) tick(s, "UNICORN: 5 STARS! KEEP GOING FOR 10 AND A GREAT PRIZE!");
}
function timeUp(s: S) {
  if (s.stars >= STAR_GOAL) { s.gems += 10 * s.gemValue; phaseTo(s, "win"); }
  else lose(s);
}
const overlap = (ax: number, ay: number, aw: number, ah: number, bx: number, by: number, bw: number, bh: number) =>
  ax < bx + bw && bx < ax + aw && ay < by + bh && by < ay + ah;
/** [id, object] pairs still in the world between world pixels left and right. */
function nearby(s: S, left: number, right: number): [number, UnicornObject][] {
  const out: [number, UnicornObject][] = [];
  for (let i = Math.max(0, div(left, SEG) - 1); i < div(right, SEG) + 1; i++) {
    for (const slot of [0, 1]) {
      const obj = unicornObject(s.seed, i, slot);
      if (obj && !s.gone.includes(i * 2 + slot)) out.push([i * 2 + slot, obj]);
    }
  }
  return out;
}
function collect(s: S, oid: number, obj: UnicornObject) {
  const kind = obj[0];
  s.gone.push(oid);
  if (kind === "star") {
    if (s.curse) { phaseTo(s, "curse"); tick(s, "STAR CURSE! SIX SEVEN AND SHAKE YOUR TUSHY!"); }
    else { say(s, "YAY!"); registerStar(s); }
  } else if (kind === "apple") { s.health = Math.min(HEALTH_MAX, s.health + 1); say(s, "YUM!"); }
  else if (kind === "bomb") { s.bombs = Math.min(BOMBS_MAX, s.bombs + BOMB_PICKUP); say(s, "BOMBS"); }
  else if (kind === "band") {
    if (s.curse) return;
    s.bands += 1;
    if (s.bands === 1) { say(s, "HORN!"); tick(s, "UNICORN: HEADBAND ON! PRESS R FOR A HORN DASH!"); }
    else if (s.bands === 3) { say(s, "NO HORN"); tick(s, "UNICORN: 3 BANDS! NO MORE HORN. DO NOT GET A 4TH!"); }
    else if (s.bands >= 4) { phaseTo(s, "dance"); s.bubble = ""; }
  } else if (kind === "glasses") { phaseTo(s, "robot"); s.bubble = ""; s.ticker = ""; }
}
/** The unicorn touched a beehive or bee swarm. */
function hit(s: S, oid: number, obj: UnicornObject) {
  if (s.dash > 0) { s.gone.push(oid); burst(s, "POW!", obj[1], obj[2] - 2); return; }
  if (s.invuln > 0) return;
  s.health -= 1; s.invuln = INVULN_MS;
  burst(s, obj[0] === "hive" ? "OUCH!" : "BZZZ!", obj[1], obj[2] - 2);
  say(s, "OOF!");
  if (s.health <= 0) lose(s);
}
/** A bomb went off at world pixel (x, y): hives and swarms close by are gone. */
function blast(s: S, x: number, y: number, word: string) {
  burst(s, word, x - 8, y - 6);
  s.shake = 200;
  for (const [oid, obj] of nearby(s, x - 12, x + 12)) {
    if (obj[0] === "hive" || obj[0] === "swarm") {
      const [w, h] = SIZES[obj[0]];
      if (overlap(x - 6, y - 6, 12, 12, obj[1], objectY(obj, s.time), w, h)) s.gone.push(oid);
    }
  }
}
function stepShots(s: S) {
  const kept: number[][] = [];
  for (const shot of s.shots) {
    shot[0] += shot[2]; shot[1] += shot[3]; shot[3] += BOMB_GRAVITY;
    const x = px(shot[0]), y = px(shot[1]);
    let struck = false;
    for (const [, obj] of nearby(s, x - 8, x + 8)) {
      if (obj[0] === "hive" || obj[0] === "swarm") {
        const [w, h] = SIZES[obj[0]];
        if (overlap(x - 1, y - 1, 3, 3, obj[1], objectY(obj, s.time), w, h)) { struck = true; break; }
      }
    }
    if (struck) blast(s, x, y, "SPLAT!");
    else if (y >= GROUND_ROW) blast(s, x, GROUND_ROW - 1, "BOOM!");
    else if (x < div(s.cam, FP) + 136) kept.push(shot);
  }
  s.shots = kept;
}
function stepPlay(s: S) {
  s.cam += SPEED;
  s.vy = Math.min(FALL_MAX, s.vy + GRAVITY);
  s.y += s.vy;
  if (s.y >= GROUND_Y) { s.y = GROUND_Y; s.vy = 0; }
  else if (s.y < TOP_Y) { s.y = TOP_Y; s.vy = 0; }
  for (const key of ["trail", "invuln", "dash", "hornCool", "shake", "bubbleMs"] as const) s[key] = Math.max(0, s[key] - STEP_MS);
  const camPx = div(s.cam, FP), ux = camPx + UX, uy = px(s.y);
  s.gone = s.gone.filter(g => div(g, 2) >= div(camPx, SEG) - 2);
  stepShots(s);
  const reach = s.dash > 0 ? 4 : 0; // the glowing horn reaches a little further
  for (const [oid, obj] of nearby(s, ux - 8, ux + 16)) {
    if (s.phase !== "play") break; // a pickup started a dance, a curse or the robot
    if (s.gone.includes(oid)) continue;
    const [w, h] = SIZES[obj[0]], oy = objectY(obj, s.time);
    if (!overlap(ux + 1, uy + 1, 8 + reach, 6, obj[1], oy, w, h)) continue;
    if (PICKUPS.includes(obj[0])) collect(s, oid, obj);
    else if (overlap(ux + 1, uy + 1, 8 + reach, 6, obj[1] + 1, oy + 1, w - 2, h - 1)) hit(s, oid, obj); // hazards forgive a one-pixel graze
  }
}
/** Leave a finished cutscene for the game-over screen. */
function endScreen(s: S) {
  s.message = s.phase === "lose" || s.phase === "robot" ? "YOU LOSE!" : s.phase === "win" ? `YOU WIN! ${s.stars} STARS` : "GRAND PRIZE! 10 STARS";
  s.status = "over";
}
export function stepUnicorn<T extends S>(state: T, time: number): T {
  const s = copy(state);
  s.time = time;
  s.timer += STEP_MS;
  s.fx = s.fx.filter(f => f[3] + STEP_MS < FX_MS);
  for (const f of s.fx) f[3] += STEP_MS;
  if (s.ticker) {
    s.tickerT += STEP_MS;
    if (s.tickerT >= (128 + s.ticker.length * 4) * 25) { s.ticker = ""; s.tickerT = 0; }
  }
  const phase = s.phase;
  if (phase === "intro") { if (s.timer >= INTRO_MS) phaseTo(s, "play"); return s; }
  if (phase === "play" || phase === "dance" || phase === "curse") {
    s.clock -= STEP_MS; // the two minutes keep running through the dance and the curse
    if (s.clock <= 0) { s.clock = 0; timeUp(s); return s; }
  }
  if (phase === "play") stepPlay(s);
  else if (phase === "dance") { if (s.timer >= DANCE_LIMIT_MS) lose(s); }
  else if (phase === "curse") { if (s.timer >= CURSE_MS) { phaseTo(s, "play"); registerStar(s); } }
  else if (phase === "robot") { s.cam += 2 * SPEED; if (s.timer >= ROBOT_MS) endScreen(s); }
  else if (s.timer >= { lose: LOSE_MS, win: WIN_MS, grand: GRAND_MS }[phase]) endScreen(s);
  return s;
}
export function pressUnicorn<T extends S>(state: T, button: string): T {
  if (state.status !== "running") return state;
  const s = copy(state), phase = s.phase;
  if (button === "a" && phase === "intro") phaseTo(s, "play");
  else if (button === "a" && phase === "play") {
    s.vy = TOOT; s.trail = 400; s.toots += 1;
    if (s.toots % 3 === 1) burst(s, s.toots % 2 ? "TOOT!" : "PFFT!", div(s.cam, FP) + UX - 14, px(s.y) + 2);
  } else if (button === "a" && phase === "dance" && s.timer >= DANCE_REPS_MS) {
    s.curse = true; phaseTo(s, "play");
    tick(s, "UNICORN: SIX SEVEN! NOW EVERY STAR MEANS SIX SEVEN!");
  } else if (button === "a" && ((phase === "lose" && s.timer >= 600) || ((phase === "win" || phase === "grand") && s.timer >= 1000))) endScreen(s);
  else if (button === "b" && phase === "play" && s.bombs > 0 && s.shots.length < 2) {
    s.bombs -= 1;
    s.shots.push([s.cam + (UX + 8) * FP, s.y + 6 * FP, BOMB_VX, BOMB_VY]);
  } else if (button === "r" && phase === "play" && s.bands >= 1 && s.bands <= 2 && s.hornCool === 0) {
    s.dash = DASH_MS; s.hornCool = HORN_COOL_MS + DASH_MS;
    burst(s, "POW!", div(s.cam, FP) + UX + 10, px(s.y) - 4);
  } else return state;
  return s;
}
