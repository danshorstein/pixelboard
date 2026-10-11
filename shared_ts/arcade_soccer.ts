// Soccer: a 3 v 3 match seen from above, mirrored line for line in shared_py/arcade_soccer.py.
// YOU (teal) attack to the right, PI (gold) to the left. Positions are integers in 1/256 px.
// Players are [x, y, facing x, facing y, ms before they may touch the ball]; the ball is [x, y, vx, vy].
export interface SoccerFields {
  players: number[][]; ball: number[]; owner: number; control: number; you: number; pi: number; clock: number; golden: boolean;
  phase: "play" | "goal"; timer: number; banner: string; pressure: number; dash: number; dashCool: number; keeperHold: number;
  shootX: number; aimY: number; score: number; gems: number; gemValue: number;
}
interface Header { status: "ready" | "running" | "over"; time: number; seed: number; message: string }
type S = Header & SoccerFields;

const STEP_MS = 20;
export const FP = 256;
const LEFT = 2 * FP, RIGHT = 125 * FP, TOP = 7 * FP, BOTTOM = 30 * FP;
const MOUTH_TOP = 13 * FP, MOUTH_BOTTOM = 25 * FP, MID_Y = 18 * FP + FP / 2;
const MATCH_MS = 180_000, GOLDEN_MS = 60_000, GOAL_MS = 1600;
const FORMATION = [[4, 18], [40, 13], [40, 24], [123, 18], [88, 13], [88, 24]];
// Reduced player speeds and matching ball friction keep play readable on the display.
const SPEED_YOU = 115, SPEED_MATE = 95, SPEED_PI = 100, SPEED_KEEPER = 55;
const DASH_MS = 600, DASH_COOL_MS = 2400, KICK = 450, PASS = 310, REACH = 3 * FP;
const FAST = 350; // a ball faster than this only keepers can stop
const KICK_LOCK_MS = 400, LOST_BALL_MS = 800, STUMBLE_MS = 1000, KEEPER_HOLD_MS = 1400;
const STEAL_STEPS_PI = 36, STEAL_STEPS_YOU = 20, DIAG = 181;

const rand = (seed: number) => (Math.imul(seed, 1664525) + 1013904223) >>> 0;
const div = (a: number, b: number) => Math.floor(a / b);
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
const shrink = (v: number, num: number, den: number) => v >= 0 ? div(v * num, den) : 0 - div((0 - v) * num, den);
const sign = (v: number) => v > 0 ? 1 : v < 0 ? -1 : 0;
const team = (i: number) => i < 3 ? 0 : 1;
function draw(s: S) { s.seed = rand(s.seed); return s.seed >>> 8; }
function isqrt(n: number) {
  if (n <= 0) return 0;
  let r = Math.floor(Math.sqrt(n));
  while (r * r > n) r--;
  while ((r + 1) * (r + 1) <= n) r++;
  return r;
}
const dist = (ax: number, ay: number, bx: number, by: number) => isqrt((ax - bx) * (ax - bx) + (ay - by) * (ay - by));

/** Everyone back to their spots; `side` starts with the ball in the centre. */
function kickoff(s: S, side: number) {
  s.players = FORMATION.map(([x, y], i) => [x * FP, y * FP + FP / 2, i < 3 ? 1 : -1, 0, 0]);
  const taker = side === 0 ? 1 : 4;
  s.players[taker][0] = (side === 0 ? 61 : 67) * FP;
  s.players[taker][1] = MID_Y;
  s.ball = [64 * FP, MID_Y, 0, 0];
  Object.assign(s, { owner: taker, control: 1, pressure: 0, dash: 0, dashCool: 0, keeperHold: 0 });
  newPossession(s);
}
export function createSoccer<T extends Header>(base: T): T & SoccerFields {
  const s = { ...base, players: [], ball: [0, 0, 0, 0], owner: -1, control: 1, you: 0, pi: 0, clock: MATCH_MS, golden: false,
    phase: "play" as const, timer: 0, banner: "", pressure: 0, dash: 0, dashCool: 0, keeperHold: 0, shootX: 0, aimY: 0, score: 0, gems: 0, gemValue: 1 };
  kickoff(s, 0);
  return s;
}
function copy<T extends S>(state: T): T { return { ...state, players: state.players.map(p => [...p]), ball: [...state.ball] }; }
function newPossession(s: S) {
  const r = draw(s);
  s.shootX = (18 + r % 22) * FP;
  s.aimY = MOUTH_TOP + FP + (r >>> 8) % 10 * FP;
  s.pressure = 0;
}
function move(p: number[], tx: number, ty: number, speed: number) {
  let dx = tx - p[0], dy = ty - p[1];
  const d = isqrt(dx * dx + dy * dy);
  if (d === 0) return;
  if (d > speed) { dx = div(dx * speed, d); dy = div(dy * speed, d); }
  p[0] = clamp(p[0] + dx, LEFT, RIGHT);
  p[1] = clamp(p[1] + dy, TOP, BOTTOM);
  if (Math.abs(dx) * 2 > Math.abs(dy) || Math.abs(dy) * 2 > Math.abs(dx)) {
    p[2] = Math.abs(dx) * 2 > Math.abs(dy) ? sign(dx) : 0;
    p[3] = Math.abs(dy) * 2 > Math.abs(dx) ? sign(dy) : 0;
  }
}
/** Kick along (dx, dy), any length. */
function kick(s: S, kicker: number, dx: number, dy: number, speed: number) {
  let d = isqrt(dx * dx + dy * dy);
  if (d === 0) { dx = kicker < 3 ? 1 : -1; d = 1; }
  s.ball[2] = div(dx * speed, d); s.ball[3] = div(dy * speed, d);
  s.owner = -1;
  s.players[kicker][4] = KICK_LOCK_MS; // the kicker cannot touch it again straight away
  s.keeperHold = 0;
}
function goal(s: S, side: number) {
  if (side === 0) { s.you += 1; s.score = s.you; s.gems += 5 * s.gemValue; } else s.pi += 1;
  Object.assign(s, { phase: "goal", timer: 0, banner: side === 0 ? "GOAL!" : "PI SCORES", owner: -1 });
  s.ball[2] = s.ball[3] = 0;
}
function finish(s: S) {
  const { you, pi } = s;
  if (you > pi) { s.message = `YOU WIN ${you}-${pi}`; s.gems += 10 * s.gemValue; }
  else if (pi > you) s.message = `PI WINS ${pi}-${you}`;
  else s.message = `DRAW ${you}-${pi}`;
  s.status = "over";
}
/** Give a loose ball to the nearest player who can reach it (keepers stop shots too). */
function pickup(s: S) {
  const ball = s.ball, fast = Math.abs(ball[2]) + Math.abs(ball[3]) > FAST;
  let best = -1, bestD = REACH + 1;
  s.players.forEach((p, i) => {
    if (p[4] > 0 || (fast && i !== 0 && i !== 3)) return;
    const d = dist(p[0], p[1], ball[0], ball[1]);
    if (d < bestD) { best = i; bestD = d; }
  });
  if (best < 0) return false;
  s.owner = best; s.pressure = 0; s.keeperHold = 0;
  ball[2] = ball[3] = 0;
  if (team(best) === 1) newPossession(s);
  return true;
}
/** Score, or bounce off the end line beside the goal. */
function goalLine(s: S) {
  const ball = s.ball, inMouth = ball[1] >= MOUTH_TOP && ball[1] < MOUTH_BOTTOM;
  if (ball[0] < LEFT) {
    if (inMouth) { goal(s, 1); return true; }
    ball[0] = 2 * LEFT - ball[0]; ball[2] = 0 - ball[2];
  } else if (ball[0] > RIGHT) {
    if (inMouth) { goal(s, 0); return true; }
    ball[0] = 2 * RIGHT - ball[0]; ball[2] = 0 - ball[2];
  }
  return false;
}
function ballPhysics(s: S) {
  const ball = s.ball;
  if (s.owner >= 0) {
    const p = s.players[s.owner];
    if (s.owner === 0 || s.owner === 3) { ball[0] = p[0] + (s.owner === 0 ? 2 * FP : -2 * FP); ball[1] = p[1]; }
    else { ball[0] = p[0] + p[2] * 3 * FP; ball[1] = clamp(p[1] + p[3] * 3 * FP, TOP, BOTTOM); }
    goalLine(s);
    return;
  }
  // Move in sub-steps of at most 2 px so a fast shot cannot skip past a keeper.
  const parts = 1 + div(Math.abs(ball[2]) + Math.abs(ball[3]), 2 * FP);
  for (let k = 0; k < parts; k++) {
    ball[0] += shrink(ball[2], 1, parts);
    ball[1] += shrink(ball[3], 1, parts);
    if (ball[1] < TOP) { ball[1] = 2 * TOP - ball[1]; ball[3] = 0 - ball[3]; }
    else if (ball[1] > BOTTOM) { ball[1] = 2 * BOTTOM - ball[1]; ball[3] = 0 - ball[3]; }
    if (goalLine(s) || pickup(s)) return;
  }
  ball[2] = shrink(ball[2], 79, 80); ball[3] = shrink(ball[3], 79, 80);
}
function ai(s: S, held: ReadonlySet<string>) {
  const { ball, players, owner } = s, owning = owner >= 0 ? team(owner) : -1, bx = ball[0], by = ball[1];
  // Keepers follow the ball across their goal and step out when it comes close.
  for (const [k, line, out] of [[0, 4 * FP, 9 * FP], [3, 123 * FP, 118 * FP]]) {
    if (owner === k) continue;
    const near = Math.abs(bx - line) < 30 * FP;
    move(players[k], near ? out : line, clamp(by, MOUTH_TOP + FP, MOUTH_BOTTOM - 2 * FP), SPEED_KEEPER);
    players[k][2] = k === 0 ? 1 : -1;
  }
  // YOU: the controlled player follows the D-pad; the teammate supports or defends.
  const c = s.control, mate = 3 - c;
  const dx = (held.has("right") ? 1 : 0) - (held.has("left") ? 1 : 0), dy = (held.has("down") ? 1 : 0) - (held.has("up") ? 1 : 0);
  if (dx || dy) {
    const speed = div(SPEED_YOU * (s.dash > 0 ? 14 : 10), 10), step = dx && dy ? div(speed * DIAG, 256) : speed, p = players[c];
    move(p, p[0] + dx * step, p[1] + dy * step, step);
    p[2] = dx; p[3] = dy;
  }
  let tx: number, ty: number;
  if (owning === 0) { tx = Math.min(players[owner][0] + 24 * FP, 112 * FP); ty = 37 * FP - players[owner][1]; }
  else { tx = div(bx + 8 * FP, 2); ty = div(by + MID_Y, 2); }
  if (owner !== mate) move(players[mate], tx, clamp(ty, TOP, BOTTOM), SPEED_MATE);
  // PI: the nearer field player chases (or carries) the ball, the other supports.
  let chaser = dist(players[4][0], players[4][1], bx, by) <= dist(players[5][0], players[5][1], bx, by) ? 4 : 5;
  if (owning === 1 && (owner === 4 || owner === 5)) chaser = owner;
  for (const i of [4, 5]) {
    const p = players[i];
    if (i === owner) {
      let aimY = MID_Y;
      for (const j of [1, 2]) {
        const q = players[j];
        if (p[0] - q[0] > 0 && p[0] - q[0] < 12 * FP && Math.abs(q[1] - p[1]) < 5 * FP) aimY = q[1] + (q[1] < p[1] || (q[1] === p[1] && p[1] > MID_Y) ? 8 * FP : -8 * FP);
      }
      move(p, 2 * FP, clamp(aimY, TOP + 2 * FP, BOTTOM - 2 * FP), SPEED_PI);
    } else if (i === chaser && owning !== 1) move(p, bx, by, SPEED_PI);
    else if (owning === 1) move(p, Math.max(players[owner][0] - 22 * FP, 16 * FP), clamp(37 * FP - players[owner][1], TOP, BOTTOM), SPEED_PI);
    else move(p, div(bx + 120 * FP, 2), div(by + MID_Y, 2), SPEED_PI);
  }
}
/** The PI ball carrier shoots or passes; keepers clear the ball. */
function decide(s: S) {
  const { owner, players } = s;
  if (owner === 0 || owner === 3) {
    s.keeperHold += STEP_MS;
    if (s.keeperHold >= KEEPER_HOLD_MS) {
      const [a, b] = owner === 0 ? [1, 2] : [4, 5];
      const ahead = (i: number) => owner === 0 ? players[i][0] : 0 - players[i][0];
      const m = ahead(b) > ahead(a) ? b : a;
      kick(s, owner, players[m][0] - players[owner][0], players[m][1] - players[owner][1], KICK);
    }
    return;
  }
  if (owner !== 4 && owner !== 5) return;
  const p = players[owner];
  if (p[0] <= s.shootX) {
    // Aim for the corner away from the keeper, give or take a pixel.
    const corner = players[0][1] > MID_Y ? MOUTH_TOP + 2 * FP : MOUTH_BOTTOM - 2 * FP;
    kick(s, owner, LEFT - FP - p[0], corner + (div(s.aimY, FP) % 3 - 1) * FP - p[1], KICK);
  }
  else if (s.pressure > 8) {
    const q = players[9 - owner];
    if (q[0] < p[0] - 6 * FP) kick(s, owner, q[0] - 6 * FP - p[0], q[1] - p[1], PASS);
  }
}
function possession(s: S) {
  const { ball, players, owner } = s;
  if (owner < 0) { pickup(s); return; }
  if (owner === 0 || owner === 3) return;
  const keeper = owner < 3 ? 3 : 0;
  if (players[keeper][4] === 0 && dist(players[keeper][0], players[keeper][1], ball[0], ball[1]) <= REACH) {
    players[owner][4] = LOST_BALL_MS;
    Object.assign(s, { owner: keeper, pressure: 0, keeperHold: 0 });
    return;
  }
  const rivals = (owner < 3 ? [4, 5] : [1, 2]).filter(i => players[i][4] === 0 && dist(players[i][0], players[i][1], ball[0], ball[1]) <= REACH);
  if (!rivals.length) { s.pressure = 0; return; }
  s.pressure += 1;
  const dashing = owner >= 3 && s.dash > 0 && rivals.includes(s.control);
  if (dashing) {
    s.dash = 0;
    if (draw(s) % 2) { players[s.control][4] = STUMBLE_MS; return; } // a missed tackle: stumble for a moment
  }
  if (dashing || s.pressure >= (owner < 3 ? STEAL_STEPS_PI : STEAL_STEPS_YOU)) {
    const thief = dashing ? s.control : rivals[0];
    players[owner][4] = LOST_BALL_MS;
    s.owner = thief; s.pressure = 0;
    if (team(thief) === 1) newPossession(s);
  }
}
export function stepSoccer<T extends S>(state: T, held: ReadonlySet<string>, time: number): T {
  const s = copy(state);
  s.time = time;
  if (s.phase === "goal") {
    s.timer += STEP_MS;
    if (s.timer >= GOAL_MS) {
      const scorer = s.banner === "GOAL!" ? 0 : 1;
      if (s.golden || (s.clock <= 0 && s.you !== s.pi)) { finish(s); return s; }
      Object.assign(s, { phase: "play", timer: 0, banner: "" });
      kickoff(s, 1 - scorer);
    }
    return s;
  }
  s.clock -= STEP_MS;
  if (s.clock <= 0) {
    if (s.you !== s.pi || s.golden) { s.clock = 0; finish(s); return s; }
    Object.assign(s, { golden: true, clock: GOLDEN_MS, banner: "GOLDEN GOAL", timer: 0 });
  }
  if (s.banner && s.phase === "play") {
    s.timer += STEP_MS;
    if (s.timer >= 1500) { s.banner = ""; s.timer = 0; }
  }
  s.dash = Math.max(0, s.dash - STEP_MS);
  s.dashCool = Math.max(0, s.dashCool - STEP_MS);
  for (const p of s.players) p[4] = Math.max(0, p[4] - STEP_MS);
  // The field player nearest the ball is the one YOU steer (with a little stickiness).
  if (s.owner !== 1 && s.owner !== 2) {
    const c = s.control, other = 3 - c, [bx, by] = s.ball;
    if (dist(s.players[other][0], s.players[other][1], bx, by) + 6 * FP < dist(s.players[c][0], s.players[c][1], bx, by)) s.control = other;
  } else s.control = s.owner;
  ai(s, held);
  if (s.owner === 0 || s.owner === 3) {
    // Nobody may crowd a keeper holding the ball: rivals wait outside the box.
    for (const i of s.owner === 0 ? [4, 5] : [1, 2]) {
      const p = s.players[i];
      p[0] = s.owner === 0 ? Math.max(p[0], 16 * FP) : Math.min(p[0], 111 * FP);
    }
  }
  possession(s);
  decide(s);
  ballPhysics(s);
  return s;
}
export function pressSoccer<T extends S>(state: T, button: string): T {
  if (state.status !== "running" || state.phase !== "play" || button !== "a") return state;
  const s = copy(state), c = s.control;
  if (s.owner === c) {
    const p = s.players[c];
    // Facing the goal: shoot at it, high or low corner when steering up or down.
    if (p[2] > 0) kick(s, c, RIGHT + FP - p[0], MID_Y + p[3] * 4 * FP - p[1], KICK);
    else kick(s, c, p[2] * 256, p[3] * 256, KICK);
  } else if (s.dashCool === 0) { s.dash = DASH_MS; s.dashCool = DASH_COOL_MS; }
  else return state;
  return s;
}
