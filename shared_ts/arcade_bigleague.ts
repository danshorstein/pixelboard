// Big League baseball rules, mirrored line for line in shared_py/arcade_bigleague.py.
// Field positions are integers in 1/64 ft: home plate (0, 0), x toward first base, y toward centre field.
// Runners are [distance along the base path, base distance they are heading for, where the play started].
export type Runner = [number, number, number];
export type BigLeaguePhase = "wait" | "aim" | "meter" | "pitch" | "play" | "result" | "switch";
export interface BigLeagueFields {
  inning: number; half: number; outs: number; balls: number; strikes: number; you: number; pi: number; lineYou: number[]; linePi: number[];
  phase: BigLeaguePhase; view: "bat" | "field"; timer: number; call: string; pitchType: number; pitchCol: number; pitchRow: number; pitchMs: number;
  pitchT: number; aimCol: number; aimRow: number; meter: number; swing: number; cpuSwing: number;
  ball: number[]; landed: boolean; holder: number; throwTo: number; chaser: number; target: number[];
  fielders: number[][]; runners: Runner[]; hold: number; settle: number; homer: boolean; caught: boolean;
  batterOut: boolean; batterHome: boolean; playOuts: number; playRuns: number; score: number; gems: number; gemValue: number;
}
interface Header { status: "ready" | "running" | "over"; time: number; seed: number; message: string }
type S = Header & BigLeagueFields;

const STEP_MS = 20, U = 64;
export const INNINGS = 3;
const MAX_INNINGS = 6, RUN_LIMIT = 6;
export const BASE = 90 * U;
export const BASES: [number, number][] = [[0, 0], [4073, 4073], [0, 8146], [-4073, 4073]];
const POSITIONS: [number, number][] = [[0, 3840], [0, -256], [4352, 5632], [2048, 8960], [-4352, 5632], [-2048, 8960], [-9600, 14720], [0, 18560], [9600, 14720]];
const RUNNER = 50, FIELDER = 26, OUTFIELDER = 34, THROW = 90, REACT_MS = 240, RISK = 20, GRAVITY = 3;
export const FENCE = 330 * U;
const WALL = 10 * U, REACH = 3 * U, CATCH_Z = 7 * U, GLOVE_Z = 4 * U;
export const PITCHES: [string, number][] = [["FAST", 820], ["CURVE", 1000], ["CHANGE", 1150]];
export const WAIT_MS = 900, WINDUP_MS = 400;
const CALL_MS = 800, PLAY_RESULT_MS = 1800, SWITCH_MS = 4000, METER_MS = 2000;
const SIN5 = [0, 22, 44, 66, 88, 108, 128, 147, 165, 181], COS5 = [256, 255, 252, 247, 241, 232, 222, 210, 196, 181];

const rand = (seed: number) => (Math.imul(seed, 1664525) + 1013904223) >>> 0;
const div = (a: number, b: number) => Math.floor(a / b);
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
function draw(s: S) { s.seed = rand(s.seed); return s.seed >>> 8; }
export function isqrt(n: number) {
  if (n <= 0) return 0;
  let r = Math.floor(Math.sqrt(n));
  while (r * r > n) r--;
  while ((r + 1) * (r + 1) <= n) r++;
  return r;
}
const dist = (ax: number, ay: number, bx: number, by: number) => isqrt((ax - bx) * (ax - bx) + (ay - by) * (ay - by));
function toward(x: number, y: number, tx: number, ty: number, speed: number): [number, number] {
  const dx = tx - x, dy = ty - y, d = isqrt(dx * dx + dy * dy);
  return d <= speed ? [tx, ty] : [x + div(dx * speed, d), y + div(dy * speed, d)];
}
/** Scale toward zero (floor division alone never lets negatives reach 0). */
const shrink = (v: number, num: number, den: number) => v >= 0 ? div(v * num, den) : 0 - div((0 - v) * num, den);

/** Field position of a runner at distance pos along the base path. */
export function basePoint(pos: number): [number, number] {
  const leg = clamp(div(pos, BASE), 0, 3), t = pos - leg * BASE;
  const [ax, ay] = BASES[leg], [bx, by] = BASES[(leg + 1) % 4];
  return [ax + div((bx - ax) * t, BASE), ay + div((by - ay) * t, BASE)];
}

export function createBigLeague<T extends Header>(base: T): T & BigLeagueFields {
  return {
    ...base, inning: 1, half: 0, outs: 0, balls: 0, strikes: 0, you: 0, pi: 0, lineYou: [0], linePi: [],
    phase: "switch", view: "bat", timer: 0, call: "", pitchType: 0, pitchCol: 0, pitchRow: 0, pitchMs: 820,
    pitchT: -1, aimCol: 0, aimRow: 0, meter: -1, swing: -1, cpuSwing: -1,
    ball: [0, 0, 0, 0, 0, 0], landed: false, holder: -1, throwTo: -1, chaser: -1, target: [0, 0],
    fielders: POSITIONS.map(p => [...p]), runners: [], hold: 0, settle: 0, homer: false, caught: false,
    batterOut: false, batterHome: false, playOuts: 0, playRuns: 0, score: 0, gems: 0, gemValue: 1,
  };
}
function copy<T extends S>(state: T): T {
  return { ...state, lineYou: [...state.lineYou], linePi: [...state.linePi], ball: [...state.ball], target: [...state.target],
    fielders: state.fielders.map(f => [...f]), runners: state.runners.map(r => [...r] as Runner) };
}

// Pitches --------------------------------------------------------------------

function release(s: S, kind: number, col: number, row: number) {
  Object.assign(s, { phase: "pitch", pitchType: kind, pitchCol: col, pitchRow: row, pitchMs: PITCHES[kind][1], pitchT: 0, swing: -1, cpuSwing: -1, call: "", timer: 0 });
  if (s.half === 1) {
    // The computer batter decides now: it chases fewer balls than strikes, and only
    // times a pitch well when it guessed the speed.
    const r = draw(s), inZone = Math.abs(col) <= 1 && Math.abs(row) <= 1;
    if (r % 100 < (inZone ? 68 : 22)) {
      let guess = (r >>> 7) % 100 < 55 ? PITCHES[0][1] : PITCHES[2][1];
      if ((r >>> 14) % 2 === 0) guess = s.pitchMs;
      const noise = (r >>> 15) % 141 - 70;
      s.cpuSwing = Math.max(200, s.pitchMs + div(guess - s.pitchMs, 2) + noise);
    }
  }
}
function cpuPitch(s: S) {
  const r = draw(s), kind = r % 100 < 50 ? 0 : r % 100 < 75 ? 1 : 2;
  let col: number, row: number;
  if ((r >>> 7) % 100 < 62) { col = (r >>> 12) % 3 - 1; row = (r >>> 14) % 3 - 1; }
  else { const other = (r >>> 14) % 3 - 1; [col, row] = ([[-2, other], [2, other], [other, -2], [other, 2]] as const)[(r >>> 12) % 4]; }
  release(s, kind, col, row);
}
/** Pitching meter 0..100..0 once a second; 50 is a perfect release. */
export function meterValue(timer: number) { const t = timer % 1000; return t < 500 ? div(t, 5) : div(1000 - t, 5); }
function kidPitch(s: S, m: number) {
  const error = Math.abs(m - 50), r = draw(s);
  let dc = 0, dr = 0;
  if (error > 30) { dc = r % 3 - 1; dr = (r >>> 4) % 3 - 1; if (dc === 0 && dr === 0) dc = 1; }
  else if (error > 12) [dc, dr] = ([[1, 0], [-1, 0], [0, 1], [0, -1]] as const)[r % 4];
  s.meter = m;
  release(s, s.pitchType, clamp(s.aimCol + dc, -2, 2), clamp(s.aimRow + dr, -2, 2));
}
/** Resolve a swing `earlyLate` ms from the plate, `missBy` zone cells from where the bat went. */
function contact(s: S, earlyLate: number, missBy: number) {
  const r = draw(s), off = Math.abs(earlyLate);
  s.swing = 0;
  if (missBy >= 2 || off > 170) return;
  if (off > 120) { call(s, "foul"); return; }
  const quality = (off <= 35 ? 100 : 100 - div((off - 35) * 5, 7)) - 25 * missBy + r % 21 - 10;
  const angle = clamp(div(earlyLate * 8, 120) + (r >>> 5) % 5 - 2, -8, 8); // early pulls to left field
  const roll = (r >>> 9) % 100;
  const kind = quality >= 88 ? (roll < 70 ? "fly" : "line") : quality >= 60 ? (roll < 50 ? "line" : roll < 75 ? "fly" : "ground") : roll < 65 ? "ground" : "pop";
  const [speed, vz] = ({ ground: [70 + quality, 6], line: [90 + quality, 45 + (r >>> 16) % 20], fly: [100 + quality, 120 + div(quality, 2)], pop: [25, 150] } as Record<string, [number, number]>)[kind];
  const vx = div(speed * SIN5[Math.abs(angle)], 256);
  s.ball = [0, 0, 3 * U, angle >= 0 ? vx : 0 - vx, div(speed * COS5[Math.abs(angle)], 256), vz];
  Object.assign(s, { phase: "play", view: "field", timer: 0, landed: false, holder: -1, throwTo: -1, hold: 0, settle: 0,
    homer: false, caught: false, batterOut: false, batterHome: false, playOuts: 0, playRuns: 0, call: "" });
  s.fielders = POSITIONS.map(p => [...p]);
  for (const runner of s.runners) { runner[2] = runner[1]; runner[1] += BASE; } // everyone runs on contact
  s.runners.push([0, BASE, 0]);
  plan(s);
}
/** Ball, strike or foul without a ball in play. */
function call(s: S, what: "foul" | "strike" | "ball") {
  Object.assign(s, { phase: "result", view: "bat", timer: 0 });
  if (what === "foul") { s.strikes = Math.min(2, s.strikes + 1); s.call = "FOUL BALL"; }
  else if (what === "strike") {
    s.strikes += 1; s.call = `STRIKE ${s.strikes}`;
    if (s.strikes >= 3) { s.outs += 1; s.call = "STRIKEOUT!"; s.balls = s.strikes = 0; }
  } else {
    s.balls += 1; s.call = `BALL ${s.balls}`;
    if (s.balls >= 4) { s.call = "WALK"; s.balls = s.strikes = 0; walk(s); }
  }
}
function walk(s: S) {
  const occupied = new Set(s.runners.map(r => r[1]));
  for (const b of [3, 2, 1]) {
    let all = true;
    for (let k = 1; k <= b; k++) if (!occupied.has(k * BASE)) all = false;
    if (all) for (const r of s.runners) if (r[1] === b * BASE) r[0] = r[1] = r[2] = (b + 1) * BASE;
  }
  s.runners.push([BASE, BASE, BASE]);
  scoreRunners(s);
}
function score(s: S, runs: number) {
  if (runs <= 0) return;
  if (s.half === 0) s.you += runs; else s.pi += runs;
  const line = s.half === 0 ? s.lineYou : s.linePi;
  line[line.length - 1] += runs;
  s.playRuns += runs;
  if (s.half === 0) { s.score = s.you; s.gems += 3 * runs * s.gemValue; }
}
function scoreRunners(s: S) {
  const home = s.runners.filter(r => r[0] >= 4 * BASE);
  if (home.some(r => r[2] === 0)) s.batterHome = true;
  s.runners = s.runners.filter(r => r[0] < 4 * BASE);
  score(s, home.length);
}

// Ball in play ---------------------------------------------------------------

function fly(ball: number[], landed: boolean): [number[], boolean, string] {
  let [x, y, z, vx, vy, vz] = ball;
  if (z > 0 || vz > 0) {
    vz -= GRAVITY; z += vz;
    if (z <= 0) {
      z = 0; landed = true;
      if (vz < -12) { vz = div((0 - vz) * 2, 5); vx = shrink(vx, 7, 10); vy = shrink(vy, 7, 10); }
      else vz = 0;
    }
  } else { vx = shrink(vx, 31, 32); vy = shrink(vy, 31, 32); }
  let nx = x + vx, ny = y + vy, event = "";
  if (nx * nx + ny * ny > FENCE * FENCE) {
    if (z > WALL && !landed) event = "homer";
    else { event = "wall"; nx = x; ny = y; vx = shrink(0 - vx, 1, 3); vy = shrink(0 - vy, 1, 3); }
  }
  return [[nx, ny, z, vx, vy, vz], landed, event];
}
const speedOf = (f: number) => f >= 6 ? OUTFIELDER : FIELDER;
/** Pick the fielder who can reach the ball first and where. */
function plan(s: S) {
  let ball = [...s.ball], landed = s.landed, event: string;
  for (let t = 1; t < 400; t++) {
    [ball, landed, event] = fly(ball, landed);
    if (event === "homer") break;
    if (ball[2] > CATCH_Z) continue;
    for (let f = 0; f < 9; f++) {
      const [fx, fy] = s.fielders[f];
      if (f === 1 && ball[0] * ball[0] + ball[1] * ball[1] > 3840 * 3840) continue; // the catcher only chases balls near the plate
      if (dist(fx, fy, ball[0], ball[1]) - REACH <= speedOf(f) * t) { s.chaser = f; s.target = [ball[0], ball[1]]; return; }
    }
    if (ball[3] === 0 && ball[4] === 0 && ball[2] === 0) break;
  }
  let nearest = 0;
  for (let f = 1; f < 9; f++) if (dist(s.fielders[f][0], s.fielders[f][1], ball[0], ball[1]) < dist(s.fielders[nearest][0], s.fielders[nearest][1], ball[0], ball[1])) nearest = f;
  s.chaser = nearest; s.target = [ball[0], ball[1]];
}
/** Fielder covering home, first, second and third. */
function covers(s: S): number[] {
  const chaser = s.chaser, first = chaser === 2 ? 0 : 2;
  let second = s.ball[0] < 0 ? 3 : 5;
  if (second === chaser) second = second === 3 ? 5 : 3;
  let third = chaser === 4 ? 5 : 4;
  if (third === second) third = 0;
  return [1, first, second, third];
}
function out(s: S, runner: Runner) {
  s.runners = s.runners.filter(r => r !== runner);
  s.outs += 1; s.playOuts += 1;
  if (runner[2] === 0 && runner[0] < 4 * BASE) s.batterOut = true;
}
function send(s: S, runner: Runner) {
  const next = runner[1] + BASE;
  if (runner[0] !== runner[1] || runner[1] >= 4 * BASE || s.runners.some(r => r[1] === next)) return false;
  runner[1] = next;
  return true;
}
const leadFirst = (runners: Runner[]) => [...runners].sort((a, b) => b[1] - a[1]);
/** Runners take an extra base by themselves when the ball is far enough away. */
function autoRunning(s: S) {
  for (const runner of leadFirst(s.runners)) {
    if (runner[0] !== runner[1] || runner[1] >= 4 * BASE) continue;
    const [bx, by] = BASES[(div(runner[1], BASE) + 1) % 4], bx0 = s.ball[0], by0 = s.ball[1];
    let ballTime: number;
    if (s.holder >= 0) { const [fx, fy] = s.fielders[s.holder]; ballTime = div(dist(fx, fy, bx, by), THROW) + 4; }
    else if (s.throwTo >= 0) { const [tx, ty] = BASES[s.throwTo % 4]; ballTime = div(dist(bx0, by0, tx, ty) + dist(tx, ty, bx, by), THROW) + 4; }
    else { const [cx, cy] = s.fielders[s.chaser]; ballTime = div(dist(cx, cy, bx0, by0), speedOf(s.chaser)) + div(dist(bx0, by0, bx, by), THROW) + 8; }
    if (div(BASE, RUNNER) < ballTime + RISK) send(s, runner);
  }
}
function decideThrow(s: S) {
  const [fx, fy] = s.fielders[s.holder];
  let best = -1, bestTarget = -1, lead = -1;
  for (const runner of s.runners) {
    if (runner[0] === runner[1]) continue;
    const b = div(runner[1], BASE);
    lead = Math.max(lead, b);
    const [bx, by] = BASES[b % 4], throwLength = dist(fx, fy, bx, by);
    if (throwLength <= REACH) continue; // already standing on that base: the runner is tagged on arrival
    if (div(throwLength + THROW - 1, THROW) + 2 < div(Math.abs(runner[1] - runner[0]) + RUNNER - 1, RUNNER) && runner[1] > bestTarget) { best = b; bestTarget = runner[1]; }
  }
  if (best < 0 && fx * fx + fy * fy > 8320 * 8320) best = lead >= 0 ? lead : 2; // from deep, hold the lead runner or return the ball to second
  if (best >= 0) { s.throwTo = best; s.holder = -1; s.ball = [fx, fy, GLOVE_Z, 0, 0, 0]; }
}
function endPlay(s: S) {
  let text: string;
  if (s.homer) {
    for (const runner of s.runners) runner[0] = 4 * BASE;
    scoreRunners(s);
    text = s.playRuns === 4 ? "GRAND SLAM!" : "HOME RUN!";
  } else if (s.batterOut) text = s.playOuts >= 3 ? "TRIPLE PLAY!" : s.playOuts === 2 ? "DOUBLE PLAY!" : s.caught ? "CAUGHT!" : "OUT!";
  else if (s.batterHome) text = "HOME RUN!";
  else {
    const batter = s.runners.filter(r => r[2] === 0);
    text = batter.length ? ["SINGLE!", "DOUBLE!", "TRIPLE!"][clamp(div(batter[0][1], BASE), 1, 3) - 1] : "SAFE!";
  }
  if (s.playRuns && !s.homer) text += ` +${s.playRuns}`;
  for (const runner of s.runners) runner[0] = runner[2] = runner[1];
  Object.assign(s, { phase: "result", timer: 0, call: text, holder: -1, throwTo: -1, balls: 0, strikes: 0 });
}
function stepPlay(s: S) {
  s.timer += STEP_MS;
  if (s.homer) {
    s.ball[0] += s.ball[3]; s.ball[1] += s.ball[4];
    for (const runner of s.runners) runner[0] = Math.min(runner[0] + RUNNER, runner[1]);
    if (s.timer >= 1500) endPlay(s);
    return;
  }
  if (s.holder >= 0) { const [fx, fy] = s.fielders[s.holder]; s.ball = [fx, fy, GLOVE_Z, 0, 0, 0]; }
  else if (s.throwTo >= 0) {
    const b = s.throwTo, [bx, by] = BASES[b % 4], [x, y] = toward(s.ball[0], s.ball[1], bx, by, THROW);
    s.ball = [x, y, GLOVE_Z, 0, 0, 0];
    if (x === bx && y === by) {
      s.holder = covers(s)[b % 4]; s.throwTo = -1; s.hold = 6;
      s.fielders[s.holder] = [bx, by];
      for (const runner of s.runners.filter(r => r[1] === b * BASE && r[0] !== r[1])) out(s, runner);
    }
  } else {
    let event: string;
    [s.ball, s.landed, event] = fly(s.ball, s.landed);
    if (event === "homer") {
      s.homer = true; s.timer = 0;
      for (const runner of s.runners) runner[1] = 4 * BASE;
      return;
    }
    if (event === "wall") plan(s);
  }
  const cover = covers(s), free = s.holder < 0 && s.throwTo < 0;
  for (let f = 0; f < 9; f++) {
    if (f === s.holder || s.timer <= REACT_MS) continue;
    const [x, y] = s.fielders[f];
    let tx: number, ty: number;
    if (f === s.chaser && free) [tx, ty] = x !== s.target[0] || y !== s.target[1] ? s.target : s.ball;
    else if (cover.includes(f)) [tx, ty] = BASES[cover.indexOf(f)];
    else [tx, ty] = POSITIONS[f];
    s.fielders[f] = toward(x, y, tx, ty, speedOf(f));
  }
  const bx = s.ball[0] - s.target[0], by = s.ball[1] - s.target[1];
  if (free && bx * s.ball[3] + by * s.ball[4] > 0 && bx * bx + by * by > REACH * REACH) plan(s); // the ball got past the chaser's spot: whoever can reach it next takes over
  if (free && s.ball[2] <= CATCH_Z) {
    const order = [s.chaser, ...[0, 1, 2, 3, 4, 5, 6, 7, 8].filter(f => f !== s.chaser)];
    for (const f of order) {
      const [fx, fy] = s.fielders[f];
      if (dist(fx, fy, s.ball[0], s.ball[1]) <= REACH) {
        s.holder = f; s.hold = 6;
        if (!s.landed) {
          s.caught = true;
          const batter = s.runners.filter(r => r[2] === 0);
          if (batter.length) out(s, batter[0]);
          for (const runner of s.runners) runner[1] = runner[2]; // tag up: everyone goes back
        }
        break;
      }
    }
  }
  autoRunning(s);
  let holderBase = -1;
  if (s.holder >= 0) {
    const [fx, fy] = s.fielders[s.holder];
    for (let b = 0; b < 4; b++) if (dist(fx, fy, BASES[b][0], BASES[b][1]) <= REACH) { holderBase = b; break; }
  }
  for (const runner of [...s.runners]) {
    if (runner[0] === runner[1]) continue;
    runner[0] = runner[1] > runner[0] ? Math.min(runner[0] + RUNNER, runner[1]) : Math.max(runner[0] - RUNNER, runner[1]);
    if (runner[0] === runner[1] && holderBase >= 0 && div(runner[1], BASE) % 4 === holderBase) out(s, runner);
  }
  scoreRunners(s);
  if (s.outs >= 3) { endPlay(s); return; }
  if (s.holder >= 0 && s.throwTo < 0) {
    if (s.hold > 0) s.hold -= 1;
    else decideThrow(s);
  }
  if (s.holder >= 0 && s.runners.every(r => r[0] === r[1])) {
    s.settle += 1;
    if (s.settle >= 30) endPlay(s);
  } else s.settle = 0;
  if (s.timer >= 20000 && s.phase === "play") endPlay(s);
}

// Innings --------------------------------------------------------------------

function startHalf(s: S) {
  Object.assign(s, { outs: 0, balls: 0, strikes: 0, runners: [], phase: "switch", view: "bat", timer: 0, call: "",
    fielders: POSITIONS.map(p => [...p]), meter: -1, pitchT: -1, swing: -1 });
}
function finish(s: S) {
  const { you, pi } = s;
  if (you > pi) { s.message = `YOU WIN ${you}-${pi}`; s.gems += 10 * s.gemValue; }
  else if (pi > you) s.message = `PI WINS ${pi}-${you}`;
  else s.message = `TIE GAME ${you}-${pi}`;
  s.status = "over";
}
function afterResult(s: S) {
  const final = s.inning >= INNINGS;
  if (s.half === 1 && final && s.pi > s.you) { finish(s); return; } // walk-off
  const line = s.half === 0 ? s.lineYou : s.linePi;
  if (s.outs < 3 && line[line.length - 1] < RUN_LIMIT) {
    Object.assign(s, { phase: s.half === 0 ? "wait" : "aim", timer: 0, call: "", view: "bat", pitchT: -1, swing: -1, meter: -1 });
    return;
  }
  if (s.half === 0) {
    if (final && s.pi > s.you) { finish(s); return; }
    s.half = 1; s.linePi.push(0);
  } else {
    if ((final && s.you !== s.pi) || s.inning >= MAX_INNINGS) { finish(s); return; }
    s.inning += 1; s.half = 0; s.lineYou.push(0);
  }
  startHalf(s);
}

export function stepBigLeague<T extends S>(state: T, time: number): T {
  const s = copy(state);
  s.time = time;
  if (s.phase === "wait") { s.timer += STEP_MS; if (s.timer >= WAIT_MS) cpuPitch(s); }
  else if (s.phase === "meter") { s.timer += STEP_MS; if (s.timer >= METER_MS) kidPitch(s, meterValue(s.timer)); }
  else if (s.phase === "pitch") {
    s.pitchT += STEP_MS;
    if (s.swing >= 0) s.swing += STEP_MS;
    if (s.cpuSwing >= 0 && s.swing < 0 && s.pitchT >= s.cpuSwing) contact(s, s.pitchT - s.pitchMs, Math.max(Math.abs(s.pitchCol), Math.abs(s.pitchRow)));
    else if (s.pitchT >= s.pitchMs + 120) call(s, s.swing >= 0 || (Math.abs(s.pitchCol) <= 1 && Math.abs(s.pitchRow) <= 1) ? "strike" : "ball");
  } else if (s.phase === "play") stepPlay(s);
  else if (s.phase === "result") { s.timer += STEP_MS; if (s.timer >= (s.view === "field" ? PLAY_RESULT_MS : CALL_MS)) afterResult(s); }
  else if (s.phase === "switch") { s.timer += STEP_MS; if (s.timer >= SWITCH_MS) Object.assign(s, { phase: s.half === 0 ? "wait" : "aim", timer: 0 }); }
  return s;
}

const MOVES: Record<string, [number, number]> = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
export function pressBigLeague<T extends S>(state: T, button: string): T {
  if (state.status !== "running") return state;
  const s = copy(state), phase = s.phase, batting = s.half === 0, limit = batting ? 1 : 2;
  if (button in MOVES && ["wait", "pitch", "aim", "result", "switch"].includes(phase)) {
    const [dc, dr] = MOVES[button];
    s.aimCol = clamp(s.aimCol + dc, -limit, limit); s.aimRow = clamp(s.aimRow + dr, -limit, limit);
  } else if ((button === "l" || button === "r") && !batting && phase === "aim") s.pitchType = (s.pitchType + (button === "r" ? 1 : 2)) % 3;
  else if (button === "a") {
    if (phase === "switch") Object.assign(s, { phase: batting ? "wait" : "aim", timer: 0 });
    else if (batting && phase === "pitch" && s.swing < 0) contact(s, s.pitchT - s.pitchMs, Math.max(Math.abs(s.pitchCol - s.aimCol), Math.abs(s.pitchRow - s.aimRow)));
    else if (batting && phase === "play") for (const runner of leadFirst(s.runners)) send(s, runner);
    else if (!batting && phase === "aim") Object.assign(s, { phase: "meter", timer: 0 });
    else if (!batting && phase === "meter") kidPitch(s, meterValue(s.timer));
    else return state;
  } else return state;
  return s;
}
