---
name: pixelboard-arcade-games
description: Use when adding a new arcade game, changing an existing one (Baseball, Snake, Pong, Neon Rider, Big League, Soccer, Rainbow Toot Unicorn), or touching the shared gem jar, the style shop, high scores, Happy Hour, quiet-hours closing, or the dashboard Arcade card in Pixelboard. Covers the file map, the step-by-step recipe for a new game, the determinism rules that keep Python and TypeScript byte-identical, the fixture tool, the controller and persistence contracts, and how to test and ship. Pair with pixelboard-arcade-design for what to build and how it should feel.
---

# Building arcade games for the scoreboard

The arcade runs on the Pi's 128x32 panel and is driven by the 8BitDo Zero 2
remote. Every game has two layers that must agree exactly between Python (what
the Pi runs) and TypeScript (the Studio reference), plus device-only layers
that only Python has.

## File map

| Layer | Files | Twin required? |
|---|---|---|
| Rules: state, `create_game`, `step_game`, `press_game`, actions | `shared_py/arcade.py`, `shared_ts/arcade.ts` (dispatch); bigger games in their own module: `arcade_bigleague.*`, `arcade_soccer.*`, `arcade_unicorn.*` | Yes, identical states |
| Picture of a game state | `shared_py/arcade_frame.py`, `shared_ts/arcade_frame.ts`; `arcade_bigleague_frame.*`, `arcade_soccer_frame.*`, `arcade_unicorn_frame.*` | Yes, identical bytes |
| Replays (expectations) | `fixtures/arcade-replays.json` | Shared by both test suites and the Pi installer |
| Fixture tool | `scripts/arcade_fixtures.py` | — |
| Screens around games (menu, shop, closed), input routing, saving results | `targets/linux-sbc-hub75/runtime/scoreboard_device/arcade.py` | No, device-only |
| Household progress (gem jar, shop catalogue, high scores), Happy Hour | `.../scoreboard_device/arcade_progress.py` | No, device-only |
| Runtime wiring (`_arcade_context`, `/api/arcade`) | `.../scoreboard_device/runtime.py`, `status_server.py` | No |
| Tests | `tests_py/test_arcade.py`, `tests_py/test_arcade_sports.py`, `tests_py/test_arcade_unicorn.py`, `tests_py/test_arcade_runtime.py`, `shared_ts/arcade.test.ts`, `shared_ts/arcade-parity.test.ts` | — |

Arcade frames are device-visible, so the parity rule from
`pixelboard-renderer-parity` applies to rules and game pictures. The screens
around the games are composed from `_draw_text` and are device-only like the
settings menu.

## Recipe: add a game

1. **Mock it first.** Write a throwaway state and render it with
   `arcade_frame`, then look at a contact sheet before writing rules.
   It's cheap and catches readability problems early (see the design skill).
2. **Rules in Python** (`shared_py/arcade.py`): add the kind to `KINDS`
   (menu order follows it; append, since tests navigate by position), add a
   `create_game` branch and a `_step_<kind>` called from `step_game`. Button
   presses that are actions (swing, kick, pick a pitch) go through
   `press_game(state, button)`; held directions still arrive in `step_game`.
   A game bigger than ~200 lines gets its own `arcade_<kind>.py`/`.ts` pair
   that `arcade.py` imports (no imports back, to avoid cycles).
3. **Tune with bots** before porting: write 2–4 policy functions (idle,
   naive, skilled) and simulate thousands of steps per seed. See the design
   skill for what to measure.
4. **Picture in Python** (`shared_py/arcade_frame.py`): a `_<kind>` helper
   called from `arcade_frame`. HUD on text row 0. The shared
   paused/ready/over overlay is drawn for you.
5. **Port both to TypeScript** line for line. Add the state interface to the
   `ArcadeState` union.
6. **Fixtures:** append cases with only `name`, `kind`, `operations` (and
   optional `seed`, `patch`, `paused`) to `fixtures/arcade-replays.json`, then
   run `.venv/bin/python scripts/arcade_fixtures.py --update-missing`.
   Operations: `{"action": "start"}`, `{"press": "a", "ticks": N,
   "held": ["right"]}` (press first, then N steps holding). Cover: ready, a
   few step counts, paused, every end state, every scoring branch, and each
   style option. Search seeds/press timings in a throwaway script to hit a
   specific outcome, and record one whole bot-played game as a single case:
   it exercises every AI path in both languages. Then `npx vitest run shared_ts/arcade`:
   TypeScript must reproduce every state and hash.
7. **Controller** (device `arcade.py`): map buttons in `_input_game` (add the
   kind to `ACTION_GAMES` to forward A/L/R/D-pad to `press_game`, and to
   `B_ACTION_GAMES` if B is a game button, so Start then B or Select leaves), make
   sure `_commit` reads `score` (high score) and `gems` (banked), give the
   state a `gemValue` if Happy Hour should multiply it, add `BEST_LABELS` text if "HIGH SCORE" is wrong, add a `LABELS` entry, and add
   the game to `SCORED_GAMES` in `arcade_progress.py` if it has a high score.
8. **Tests:** rule tests in both languages, controller tests through
   `input()`, and a runtime test through real evdev events if routing
   changed.
9. **Docs:** update the reference frame count in `CLAUDE.md`, describe the
   game in `docs/ARCADE.md`, and add its buttons to `docs/CONTROLS.md`.

## Determinism rules (Python and JS must agree bit for bit)

- **Integers only in state.** Use fixed point (Rider uses 1/256 px, `FP`).
  Floats that pass through `Math.sin` and accumulate can drift between
  engines; Pong's float state predates this rule and works only because its
  maths is short and simple. Don't copy that.
- **Division:** Python `//` floors; in TS always write `Math.floor(a / b)`
  (the `div` helper). Never `Math.trunc` or `| 0` for negatives.
- **Modulo:** Python `%` is never negative; JS `%` keeps the sign. Use
  `((a % n) + n) % n` (the `mod` helper) anywhere a value can go negative,
  including camera and parallax maths.
- **32-bit hashing:** Python `& 0xffffffff`; TS `>>> 0` and `Math.imul`.
  Shift unsigned values with `>>>` in TS.
- **Rotation without trig:** use the `COS16`/`SIN16` integer tables and
  round with `(v + 128) // 256`.
- **Rounding pixels from fixed point:** `(v + FP // 2) // FP`. Flooring makes
  one-pixel notches at smooth curve peaks.
- **-0:** `Math.floor(-0)` is `-0`. Keep it out of state (vitest `toEqual`
  can tell -0 from 0). Write negation as `0 - x` in TS (`-x` of 0 is -0), and
  shrink toward zero with `v >= 0 ? div(v*n, d) : 0 - div(-v*n, d)`.
- **Distances:** integer `isqrt` (Python `math.isqrt`; TS floor(sqrt) then
  correct by ±1). Move toward a target with `x + dx * speed // d`.
- **Ordering:** Python `min/max(key=...)` returns the first best item, and JS
  `sort` is stable, so write explicit loops with the same tie-break. Remove
  list items by identity (`r is not x` / `r !== x`), not `list.remove`.
- **State shape:** identical keys, JSON-safe values (ints, bools, strings,
  lists, dicts). Python `assert_state` checks key sets.
- **Style and multipliers are state too** (`car`, `color`, `theme`,
  `gemValue`), so fixtures can cover them with `patch`.

## Fixture tool

```
.venv/bin/python scripts/arcade_fixtures.py                  # check all (exit 1 on mismatch)
.venv/bin/python scripts/arcade_fixtures.py --update NAME ...# rewrite only these
.venv/bin/python scripts/arcade_fixtures.py --update-missing # fill new cases
.venv/bin/python scripts/arcade_fixtures.py --preview out.png --kind rider
```

Never update cases for a game you didn't mean to change: a moved hash there is
a regression. When adding state fields with defaults, update the affected cases
and confirm with `git diff` that only `expectedState` changed and every
`sha256` stayed put. Then the default look is provably unchanged.

## Controller contract (device `arcade.py`)

- Buttons: **A** primary/confirm, **B** back, **X** restart a game, **Start** pause, **D-pad** move or select, **L/R**
  cycle. **Select** always leaves the arcade. **Y** is taken by the runtime
  (Home) before the arcade sees it; **R** opens the Team card only outside the arcade.
- Held buttons: directions are held automatically. Add another button to
  `self.held` explicitly, as Rider does for A, and release clears it.
  Disconnect (`suspend`) clears held buttons and pauses.
- `_commit()` saves a played game exactly once: on game over (from `tick`),
  B to menu, X restart, a new start, `exit()`, and quiet-hours closing.
- Game speed is fixed 20 ms steps. Catch-up is capped at 250 ms per tick, and
  idle exit is 5 minutes.
- `menu` is a read-only property (`screen != 'game'`). The runtime reads it
  for the dashboard scene name.

## Shared progress, shop, Happy Hour, quiet hours

- **No player profiles or names.** This is a deliberate project decision;
  discuss in an issue before reintroducing profiles or initials. The
  household shares one gem jar, one equipped style and one unnamed high
  score per game (Pong counts wins).
- `state/arcade-progress.json` (`ArcadeProgress`) lives under `state/`, so it
  survives updates. It's written atomically. An unreadable file is renamed to
  `.unreadable` and the store starts fresh. New fields get defaults in
  `_empty()` and are merged on load; bump `version` only for incompatible
  changes.
- The shop catalogue (`SHOP`) indexes must match the shared `CARS`,
  `CAR_COLORS` (+ rainbow) and `THEMES` order. New items go at the end.
- Happy Hour: `happy_hour(now, quietHours)` gives a 10-minute window every 3
  hours, skipping windows that start in quiet hours. The controller sets
  `gemValue` each tick.
- Quiet hours (any behavior, `dim` or `sleep`) close the arcade.
  `set_context` must be called before `input` and `tick` (the runtime's
  `_arcade_context`). A running game is saved, then the "ARCADE CLOSED"
  screen shows for 4 s.
- Dashboard: `GET /api/arcade`, and `POST /api/arcade` with the household PIN
  (`gems` to add or remove gems, `resetScores`). Escape `\n` in embedded JS as `\\n`.

## Testing and shipping

- `.venv/bin/python -m unittest tests_py.test_arcade tests_py.test_arcade_runtime`
  and `npx vitest run shared_ts/arcade` are the fast loop. Run the full suites
  (`npm test`, `npm run test:py`, `npm run build`) before committing.
- Both suites pass in a clean checkout without any team-logo pack or
  network access. If something fails, confirm whether it also fails on
  unchanged `main` (`git stash`) before calling it environmental.
- Tests navigate menus by position (`MENU_ITEMS`). Prefer helpers
  (`open_arcade`, `play_rider`) or setting `controller.selection` directly
  over long button chains.
- Pi check: `PYTHONPATH=targets/linux-sbc-hub75/runtime .venv/bin/python -m scoreboard_device --root . verify --output-dir <dir>`
  must pass every arcade frame within the 50 ms budget. Pi 3 A+ is roughly 10×
  slower than a cloud container, so keep a game frame under about 4 ms locally.
  Python `fill_rect` is per pixel: draw a static background once, cache its
  bytes and copy them in (`_cached` in `arcade_bigleague_frame.py`); mirror
  the cache in TS so the two stay structurally alike.
- Big text: the arcade `text(s, x, y, color, scale)` helper takes an optional
  integer scale (2 gives 8x12 letters).
- Devices update from public `main`, so keep it green: work on a branch and
  open a pull request.
