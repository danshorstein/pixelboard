import { createBigLeague, pressBigLeague, stepBigLeague, type BigLeagueFields } from "./arcade_bigleague";
import { createSoccer, pressSoccer, stepSoccer, type SoccerFields } from "./arcade_soccer";
import { createUnicorn, pressUnicorn, stepUnicorn, type UnicornFields } from "./arcade_unicorn";
export type GameKind = "baseball" | "snake" | "pong" | "rider" | "bigleague" | "soccer" | "unicorn";
export type Direction = "up" | "down" | "left" | "right";
export type GameStatus = "ready" | "running" | "over";
export interface Point { x: number; y: number }
interface Base { kind: GameKind; status: GameStatus; time: number; seed: number; message: string }
export interface SnakeState extends Base { kind: "snake"; body: Point[]; direction: Direction; queued: Direction; food: Point | null; score: number; accumulator: number }
export interface PongState extends Base { kind: "pong"; player: number; computer: number; ball: Point; vx: number; vy: number; playerScore: number; computerScore: number; serve: number }
export interface BaseballState extends Base { kind: "baseball"; phase: "pitch" | "flight"; x: number; speed: number; flight: number; result: string; score: number; strikes: number; pitches: number }
export interface RiderState extends Base { kind: "rider"; x: number; y: number; vx: number; vy: number; angle: number; air: boolean; spin: number; score: number; bonus: number; gems: number; nextGem: number; banner: string; bannerMs: number; car: number; color: number; theme: number; gemValue: number }
export interface BigLeagueState extends Base, BigLeagueFields { kind: "bigleague" }
export interface SoccerState extends Base, SoccerFields { kind: "soccer" }
export interface UnicornState extends Base, UnicornFields { kind: "unicorn" }
export type ArcadeState = SnakeState | PongState | BaseballState | RiderState | BigLeagueState | SoccerState | UnicornState;
export const KINDS: GameKind[] = ["baseball", "snake", "pong", "rider", "bigleague", "soccer", "unicorn"];
export const STEP_MS = 20;
const random = (seed: number) => (Math.imul(seed, 1664525) + 1013904223) >>> 0;
const vectors: Record<Direction, Point> = { up: { x: 0, y: -1 }, down: { x: 0, y: 1 }, left: { x: -1, y: 0 }, right: { x: 1, y: 0 } };
function foodFor(body: Point[], seed: number): Point | null {
  const start = seed % (62 * 12);
  for (let i = 0; i < 62 * 12; i++) {
    const cell = (start + i) % (62 * 12); const p = { x: 1 + cell % 62, y: 3 + Math.floor(cell / 62) };
    if (!body.some(b => b.x === p.x && b.y === p.y)) return p;
  }
  return null;
}
export function createGame(kind: GameKind, seed = 727): ArcadeState {
  const base = { kind, status: "ready" as const, time: 0, seed: seed >>> 0, message: "PRESS START" };
  if (kind === "snake") { const body = [{ x: 16, y: 8 }, { x: 15, y: 8 }, { x: 14, y: 8 }]; return { ...base, kind, body, direction: "right", queued: "right", food: foodFor(body, seed), score: 0, accumulator: 0 }; }
  if (kind === "rider") { const x = RIDER_START * FP; return { ...base, kind, x, y: riderGround(seed >>> 0, x), vx: 0, vy: 0, angle: 0, air: false, spin: 0, score: 0, bonus: 0, gems: 0, nextGem: 4, banner: "", bannerMs: 0, car: 0, color: 0, theme: 0, gemValue: 1 }; }
  if (kind === "bigleague") return createBigLeague({ ...base, kind });
  if (kind === "soccer") return createSoccer({ ...base, kind });
  if (kind === "unicorn") return createUnicorn({ ...base, kind });
  if (kind === "pong") return { ...base, kind, player: 12, computer: 12, ball: { x: 64, y: 18 }, vx: -.8, vy: .35, playerScore: 0, computerScore: 0, serve: 700 };
  return { ...base, kind, phase: "pitch", x: 110, speed: .075, flight: 0, result: "", score: 0, strikes: 0, pitches: 0 };
}
export function startGame(state: ArcadeState): ArcadeState { return state.status === "ready" ? { ...state, status: "running", message: "" } : state; }
export function steerSnake(state: SnakeState, direction: Direction): SnakeState {
  if (state.status !== "running") return state;
  const a = vectors[state.direction], b = vectors[direction];
  return a.x + b.x === 0 && a.y + b.y === 0 ? state : { ...state, queued: direction };
}
export function swing(state: BaseballState): BaseballState {
  if (state.status !== "running" || state.phase !== "pitch") return state;
  // Milliseconds relative to the ball reaching the bat, independent of pitch speed.
  const error = Math.abs((state.x - 24) / state.speed);
  const result = error <= 25 ? "HOME RUN!" : error <= 65 ? "DOUBLE!" : error <= 110 ? "HIT!" : error <= 190 ? "FOUL" : "MISS";
  const points = result === "HOME RUN!" ? 5 : result === "DOUBLE!" ? 3 : result === "HIT!" ? 1 : 0;
  return { ...state, phase: "flight", flight: 0, x: 24, result, message: result, score: state.score + points, strikes: state.strikes + (result === "MISS" ? 1 : 0), pitches: state.pitches + 1 };
}
/** A button press for games whose buttons are actions, not held controls. */
export function pressGame(state: ArcadeState, button: string): ArcadeState {
  if (state.kind === "bigleague") return pressBigLeague(state, button);
  if (state.kind === "soccer") return pressSoccer(state, button);
  if (state.kind === "unicorn") return pressUnicorn(state, button);
  return state;
}
export function stepGame(state: ArcadeState, held: ReadonlySet<string> = new Set()): ArcadeState {
  if (state.status !== "running") return state;
  const time = state.time + STEP_MS;
  if (state.kind === "bigleague") return stepBigLeague(state, time);
  if (state.kind === "soccer") return stepSoccer(state, held, time);
  if (state.kind === "unicorn") return stepUnicorn(state, time);
  if (state.kind === "rider") return stepRider(state, held, time);
  if (state.kind === "snake") {
    const accumulator = state.accumulator + STEP_MS; const interval = Math.max(70, 150 - state.score * 3);
    if (accumulator < interval) return { ...state, time, accumulator };
    const v = vectors[state.queued], head = { x: state.body[0].x + v.x, y: state.body[0].y + v.y };
    const eating = state.food?.x === head.x && state.food?.y === head.y;
    const bodyToCheck = eating ? state.body : state.body.slice(0, -1);
    if (head.x < 1 || head.x > 62 || head.y < 3 || head.y > 14 || bodyToCheck.some(p => p.x === head.x && p.y === head.y)) return { ...state, time, status: "over", message: "GAME OVER" };
    const body = [head, ...state.body]; if (!eating) body.pop(); const seed = eating ? random(state.seed) : state.seed; const food = eating ? foodFor(body, seed) : state.food;
    return { ...state, time, body, seed, food, score: state.score + (eating ? 1 : 0), direction: state.queued, accumulator: accumulator - interval, status: food ? "running" : "over", message: food ? "" : "YOU WIN!" };
  }
  if (state.kind === "baseball") {
    if (state.phase === "pitch") {
      const x = state.x - state.speed * STEP_MS;
      return x < 10 ? { ...state, x, time, phase: "flight", flight: 0, result: "MISS", message: "MISS", strikes: state.strikes + 1, pitches: state.pitches + 1 } : { ...state, x, time };
    }
    const flight = state.flight + STEP_MS;
    if (flight < 1250) return { ...state, time, flight };
    if (state.strikes >= 3 || state.pitches >= 10) return { ...state, time, flight, status: "over", message: state.strikes >= 3 ? "STRIKE THREE" : "ROUND COMPLETE" };
    const seed = random(state.seed);
    return { ...state, time, seed, phase: "pitch", x: 110, speed: .06 + (seed % 45) / 1000, flight: 0, result: "", message: "" };
  }
  const player = Math.max(6, Math.min(23, state.player + (held.has("down") ? 1 : 0) - (held.has("up") ? 1 : 0)));
  // Imperfect opponent tracks slowly with a small deterministic aiming error.
  const target = state.ball.y - 3 + Math.sin(time / 370) * 4;
  const computer = Math.max(6, Math.min(23, state.computer + Math.max(-.48, Math.min(.48, target - state.computer))));
  if (state.serve > 0) return { ...state, time, player, computer, serve: Math.max(0, state.serve - STEP_MS) };
  let { x, y } = state.ball; let { vx, vy } = state; x += vx; y += vy;
  if (y < 6 || y > 29) { y = Math.max(6, Math.min(29, y)); vy = -vy; }
  const hitPlayer = vx < 0 && x <= 6 && state.ball.x > 6 && y >= player - 1 && y <= player + 8;
  const hitComputer = vx > 0 && x >= 121 && state.ball.x < 121 && y >= computer - 1 && y <= computer + 8;
  if (hitPlayer || hitComputer) { vx = (hitPlayer ? 1 : -1) * Math.min(1.6, Math.abs(vx) + .07); vy = (y - (hitPlayer ? player : computer) - 3.5) * .2; x = hitPlayer ? 6 : 121; }
  if (x < 0 || x > 127) {
    const playerScore = state.playerScore + (x > 127 ? 1 : 0), computerScore = state.computerScore + (x < 0 ? 1 : 0);
    const over = playerScore >= 5 || computerScore >= 5;
    return { ...state, time, player, computer, playerScore, computerScore, ball: { x: 64, y: 18 }, vx: x < 0 ? -.8 : .8, vy: .35, serve: 700, status: over ? "over" : "running", message: over ? playerScore >= 5 ? "YOU WIN!" : "PI WINS" : "" };
  }
  return { ...state, time, player, computer, ball: { x, y }, vx, vy };
}

// Neon Rider: integer fixed-point (1/256 px) physics so both languages agree exactly.
const FP = 256, RIDER_START = 40, SEGMENT = 32, GRAVITY = 8, GAS = 5, VMAX = 768, FLIP_SPIN = 10, LAND_TOLERANCE = 45;
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
const div = (a: number, b: number) => Math.floor(a / b);
/** Signed angle in -180..179 degrees; positive tips the nose down. */
const wrap = (angle: number) => ((angle + 180) % 360 + 360) % 360 - 180;
const segmentHash = (seed: number, i: number) => random(random((seed + i * 2654435761) >>> 0));
function height(seed: number, i: number) {
  if (i < 3) return 24;
  const amp = Math.min(14, 2 + div(i - 3, 2));
  return 27 - (segmentHash(seed, i) >>> 8) % (amp + 1);
}
function groundPx(seed: number, px: number) {
  const i = div(px, SEGMENT), t = px - i * SEGMENT, h0 = height(seed, i), h1 = height(seed, i + 1);
  return h0 * FP + div((h1 - h0) * FP * (3 * t * t * SEGMENT - 2 * t * t * t), SEGMENT ** 3);
}
/** Ground row in 1/256 px at world x (also 1/256 px). */
export function riderGround(seed: number, x: number) {
  const px = div(x, FP), a = groundPx(seed, px);
  return a + div((groundPx(seed, px + 1) - a) * (x - px * FP), FP);
}
const slope = (seed: number, x: number) => riderGround(seed, x + 2 * FP) - riderGround(seed, x - 2 * FP);
const slopeAngle = (seed: number, x: number) => clamp(div(slope(seed, x) * 45, 4 * FP), -60, 60);
export function riderGem(seed: number, i: number): Point | null {
  if (i < 4) return null;
  const v = random(segmentHash(seed, i));
  if ((v >>> 4) % 3 === 0) return null;
  const x = i * SEGMENT + SEGMENT / 2;
  return { x, y: div(groundPx(seed, x) + FP / 2, FP) - 5 - (v >>> 12) % 6 };
}
function stepRider(state: RiderState, held: ReadonlySet<string>, time: number): RiderState {
  const seed = state.seed, gas = held.has("a") || held.has("right");
  let { x, y, vx, vy, angle, air, spin, bonus, banner } = state;
  let bannerMs = Math.max(0, state.bannerMs - STEP_MS);
  if (!air) {
    vx = clamp(vx + (gas ? GAS : 0) + div(slope(seed, x), 128) - div(vx + 127, 128), 0, VMAX);
    x += vx;
    const follow = riderGround(seed, x) - y;
    // Leave the ground when it falls away faster than gravity can follow.
    if (follow > vy + GRAVITY + 24) { air = true; spin = 0; vy += GRAVITY; y += vy; }
    else { y += follow; vy = follow; angle = slopeAngle(seed, x); }
  } else {
    vy += GRAVITY; x += vx; y += vy;
    if (gas) { angle -= FLIP_SPIN; spin += FLIP_SPIN; }
    // Released in the air, the car levels toward the ground below it.
    else angle += clamp(wrap(slopeAngle(seed, x) - angle), -5, 5);
    angle = wrap(angle);
    const ground = riderGround(seed, x);
    if (y >= ground) {
      if (Math.abs(wrap(angle - slopeAngle(seed, x))) > LAND_TOLERANCE) return { ...state, time, x, y: ground, vx: 0, vy: 0, angle, air: false, spin, bannerMs: 0, status: "over", message: "CRASH!" };
      const flips = div(spin + 45, 360);
      if (flips) { bonus += 10 * flips; vx = Math.min(VMAX, vx + 64 * flips); banner = flips === 1 ? "FLIP!" : `${flips}X FLIP!`; bannerMs = 900; }
      air = false; spin = 0; y = ground; vy = 0; angle = slopeAngle(seed, x);
    }
  }
  let { gems, nextGem } = state;
  const px = div(x, FP), cy = div(y + FP / 2, FP) - 2;
  while (nextGem * SEGMENT + SEGMENT / 2 + 3 < px) nextGem++;
  const gem = riderGem(seed, nextGem);
  if (gem && Math.abs(px - gem.x) <= 3 && Math.abs(cy - gem.y) <= 4) { gems += state.gemValue; nextGem++; }
  const score = div(x - RIDER_START * FP, 8 * FP) + bonus;
  return { ...state, time, x, y, vx, vy, angle, air, spin, score, bonus, gems, nextGem, banner, bannerMs };
}
