import { describe, it, expect } from "vitest";
import { KINDS, createGame, pressGame, startGame, stepGame, steerSnake, swing, type ArcadeState, type BaseballState, type BigLeagueState, type SnakeState, type SoccerState, type UnicornState, type PongState, type RiderState } from "./arcade";
import { arcadeFrame } from "./arcade_frame";
function ticks(s: ArcadeState, n: number) { for (let i = 0; i < n; i++) s = stepGame(s); return s; }
describe("arcade rules", () => {
  it("ready and finished games do not advance", () => { const s = createGame("snake"); expect(stepGame(s)).toBe(s); const over = { ...s, status: "over" as const }; expect(stepGame(over)).toBe(over); });
  it("fixed steps replay identically from a seed", () => { for (const kind of KINDS) expect(ticks(startGame(createGame(kind)), 200)).toEqual(ticks(startGame(createGame(kind)), 200)); });
  it("snake rejects reverse even after a queued turn", () => { const s = startGame(createGame("snake")) as SnakeState; expect(steerSnake(s, "left")).toEqual(s); const queued = steerSnake(s, "up"); expect(steerSnake(queued, "left")).toEqual(queued); });
  it("snake grows and moves food off the body", () => { const s = startGame(createGame("snake")) as SnakeState; const next = ticks({ ...s, food: { x: 17, y: 8 } }, 8) as SnakeState; expect(next.score).toBe(1); expect(next.body.length).toBe(4); expect(next.body).not.toContainEqual(next.food); });
  it("snake loses at a wall", () => { const s = startGame(createGame("snake")) as SnakeState; expect(ticks({ ...s, body: [{ x: 62, y: 8 }], food: { x: 1, y: 3 } }, 8).status).toBe("over"); });
  it("snake loses on its body but may move into a vacating tail", () => { const s = startGame(createGame("snake")) as SnakeState; const blocked = { ...s, body: [{ x: 3, y: 5 }, { x: 4, y: 5 }, { x: 4, y: 6 }, { x: 3, y: 6 }], food: { x: 10, y: 10 } }; expect(ticks(blocked, 8).status).toBe("over"); expect(ticks({ ...blocked, body: [{ x: 3, y: 5 }, { x: 3, y: 6 }, { x: 4, y: 6 }, { x: 4, y: 5 }] }, 8).status).toBe("running"); });
  it.each([[0, "HOME RUN!", 5], [25, "HOME RUN!", 5], [26, "DOUBLE!", 3], [65, "DOUBLE!", 3], [66, "HIT!", 1], [110, "HIT!", 1], [111, "FOUL", 0], [190, "FOUL", 0], [191, "MISS", 0]] as const)("baseball timing %dms becomes %s", (ms, result, points) => { const s = startGame(createGame("baseball")) as BaseballState; const hit = swing({ ...s, x: 24 + ms * s.speed }); expect(hit.result).toBe(result); expect(hit.score).toBe(points); expect(hit.pitches).toBe(1); expect(hit.strikes).toBe(result === "MISS" ? 1 : 0); expect(swing(hit)).toEqual(hit); });
  it("baseball untimed fast pitches are misses, never fouls", () => { const s = startGame(createGame("baseball")) as BaseballState; const next = stepGame({ ...s, speed: .105, x: 10.1 }) as BaseballState; expect(next.result).toBe("MISS"); expect(next.strikes).toBe(1); });
  it("baseball ends after three misses and restart clears scores", () => { const over = ticks(startGame(createGame("baseball")), 700) as BaseballState; expect(over.status).toBe("over"); expect(over.strikes).toBe(3); expect(createGame("baseball")).toMatchObject({ strikes: 0, pitches: 0, score: 0 }); });
  it("baseball ends after ten pitches even with no strikes", () => { const s = startGame(createGame("baseball")) as BaseballState; expect(ticks(swing({ ...s, x: 24, pitches: 9 }), 63).status).toBe("over"); });
  it("pong moves only while held and clamps paddles", () => { let s = startGame(createGame("pong")) as PongState; const still = stepGame(s) as PongState; expect(still.player).toBe(s.player); for (let i = 0; i < 100; i++) s = stepGame(s, new Set(["up"])) as PongState; expect(s.player).toBe(6); expect((stepGame(s) as PongState).player).toBe(6); });
  it("pong bounces at a paddle and wall", () => { const s = startGame(createGame("pong")) as PongState; const hit = stepGame({ ...s, serve: 0, ball: { x: 6.5, y: 15 }, vx: -1 }) as PongState; expect(hit.vx).toBeGreaterThan(0); const wall = stepGame({ ...s, serve: 0, ball: { x: 50, y: 6.1 }, vy: -.5 }) as PongState; expect(wall.vy).toBeGreaterThan(0); });
  it("pong scores and ends at five, then leaves the winner stable", () => { const s = startGame(createGame("pong")) as PongState; const over = stepGame({ ...s, serve: 0, playerScore: 4, ball: { x: 127.5, y: 10 }, vx: 1 }) as PongState; expect(over).toMatchObject({ playerScore: 5, status: "over", message: "YOU WIN!" }); expect(stepGame(over)).toBe(over); });
  it("every game emits a native 128 by 32 opaque frame", () => { for (const k of KINDS) { const f = arcadeFrame(startGame(createGame(k))); expect(f.data.length).toBe(128 * 32 * 4); expect(f.width).toBe(128); expect(f.height).toBe(32); expect([...f.data].filter((_,i)=>i%4===3).every(a=>a===255)).toBe(true); } });
  it("rider only moves with gas and coasts to a stop", () => { const s = startGame(createGame("rider")) as RiderState; expect(ticks(s, 100)).toMatchObject({ vx: 0, score: 0 }); let r: ArcadeState = s; for (let i = 0; i < 100; i++) r = stepGame(r, new Set(["a"])); expect((r as RiderState).vx).toBeGreaterThan(0); expect((ticks(r, 300) as RiderState).vx).toBe(0); });
  it("rider lands a backflip for a bonus and crashes upside down", () => { const s = startGame(createGame("rider")) as RiderState; let r: RiderState = { ...s, air: true, y: s.y - 40 * 256, vx: 300, vy: -256 }; while (r.air) r = stepGame(r, new Set(r.spin < 350 ? ["a"] : [])) as RiderState; expect(r).toMatchObject({ status: "running", bonus: 10, banner: "FLIP!" }); expect(stepGame({ ...s, air: true, y: s.y - 256, vy: 256, angle: 180, spin: 180 })).toMatchObject({ status: "over", message: "CRASH!" }); });
  it("big league opens on the line score, A skips it and taking a pitch makes a call", () => {
    const s = startGame(createGame("bigleague")) as BigLeagueState;
    expect(s.phase).toBe("switch");
    const waiting = pressGame(s, "a") as BigLeagueState;
    expect(waiting.phase).toBe("wait");
    let r: ArcadeState = waiting;
    while ((r as BigLeagueState).phase !== "result") r = stepGame(r);
    const b = r as BigLeagueState;
    expect(b.balls + b.strikes).toBe(1);
  });
  it("big league pitching: L/R choose the pitch, A starts the meter and throws", () => {
    let s = { ...startGame(createGame("bigleague")), half: 1, phase: "aim" as const, linePi: [0] } as BigLeagueState;
    s = pressGame(pressGame(s, "r"), "up") as BigLeagueState;
    expect([s.pitchType, s.aimRow]).toEqual([1, -1]);
    s = pressGame(s, "a") as BigLeagueState; expect(s.phase).toBe("meter");
    s = pressGame(ticks(s, 12), "a") as BigLeagueState;
    expect([s.phase, s.pitchCol, s.pitchRow, s.pitchMs]).toEqual(["pitch", 0, -1, 1000]);
  });
  it("soccer dribbles while a direction is held and A shoots", () => {
    let s: ArcadeState = startGame(createGame("soccer"));
    for (let i = 0; i < 10; i++) s = stepGame(s, new Set(["right"]));
    const carried = s as SoccerState;
    expect(carried.owner).toBe(1);
    expect(carried.ball[0]).toBe(carried.players[1][0] + 3 * 256);
    const shot = pressGame(s, "a") as SoccerState;
    expect(shot.owner).toBe(-1);
    expect(shot.ball[2]).toBeGreaterThan(400);
  });
  it("rainbow unicorn: A skips the intro and toots, B throws a bomb, the clock runs", () => {
    let s = pressGame(startGame(createGame("unicorn")), "a") as UnicornState;
    expect(s.phase).toBe("play");
    s = pressGame(s, "a") as UnicornState;
    expect(s.vy).toBeLessThan(0);
    s = pressGame(s, "b") as UnicornState;
    expect([s.bombs, s.shots.length]).toEqual([2, 1]);
    expect((ticks(s, 50) as UnicornState).clock).toBe(119_000);
  });
  it("rainbow unicorn: the dance needs A after the swaps and starts the star curse", () => {
    const s = { ...pressGame(startGame(createGame("unicorn")), "a"), phase: "dance" as const, bands: 4 } as UnicornState;
    expect((pressGame(ticks(s, 50), "a") as UnicornState).phase).toBe("dance");
    const done = pressGame(ticks(s, 150), "a") as UnicornState;
    expect([done.phase, done.curse]).toEqual(["play", true]);
  });
});
