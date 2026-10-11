# CLAUDE.md — Pixelboard

Pixelboard is an MLB/NFL scoreboard and arcade for a 128×32 HUB75 RGB LED
matrix driven by a Raspberry Pi (`linux-sbc-hub75`). It has three parts:

1. **Studio**: a React/TypeScript frontend (`frontend/`) and FastAPI backend
   (`backend/`) for previewing screens, designing layouts and building device
   packages.
2. **Device runtime**: the Python service
   (`targets/linux-sbc-hub75/runtime/scoreboard_device/`) that runs on the Pi
   as `scoreboard.service` and drives the panel through `rgbmatrix`, or a
   simulator that writes PNGs.
3. **Admin panel**: a dashboard on port 8123 (`http://pixelboard.local:8123/`)
   served by the runtime, with a live preview, controls, settings, quiet
   hours, past scores, a team schedule, arcade gems, announcements and
   one-tap updates.

## Commands

```bash
npm test && npm run test:py   # both suites must pass before committing
npm test                       # TypeScript (vitest)
npm run test:py                # Python (unittest)
npm run build                  # typecheck + frontend production build
npm run dev                    # studio with the backend proxy

# Device runtime in the simulator, and the Pi's reference-frame check
PYTHONPATH=targets/linux-sbc-hub75/runtime .venv/bin/python -m scoreboard_device --root . run
PYTHONPATH=targets/linux-sbc-hub75/runtime .venv/bin/python -m scoreboard_device --root . verify --output-dir /tmp/frames
```

Both suites pass in a clean checkout without a team-logo pack or network
access. A failure is real until shown to also fail on unchanged `main`.

## Code map

- `targets/linux-sbc-hub75/runtime/scoreboard_device/`
  - `runtime.py`: `DeviceRuntime` owns the main loop, data polling, rendering
    (`_render` precedence chain), the cached frame for `/api/screen.png`,
    controller input, the boot surprise, morning recap, past scores and
    scoring alerts.
  - `status_server.py`: the admin panel (`DASHBOARD_PAGE`) and its HTTP API.
  - `arcade.py`, `arcade_progress.py`: the arcade's menus, input routing, gem
    jar, style shop, high scores and Happy Hour (device-only).
  - `controller_settings.py`: the on-panel main menu and settings drafts.
  - `bluetooth_remote.py`: the evdev reader for the 8BitDo Zero 2 (keyboard
    mode), with named press/release events and held-state clearing on
    disconnect.
  - `team.py`: the optional iCalendar team schedule and its card.
  - `home.py`, `history.py`, `scoring_alerts.py`, `transport.py`,
    `output.py`, `verification.py`, `diagnostics.py`.
- `shared_py/` and `shared_ts/`: rendering and game logic shared by the Pi and
  the studio. **Output must be byte-identical.** Reference frames live in
  `fixtures/expected-render-frames.json` (22 MLB), `fixtures/nfl-*.json`
  (24 NFL, 72 NFL logo layouts) and `fixtures/arcade-replays.json` (177
  arcade cases). The Pi installer re-checks all 295 within a 50 ms-per-frame
  budget.
- `scripts/update-device.sh`: stages, verifies and activates a new release on
  the Pi, with rollback. `scripts/arcade_fixtures.py`: the arcade fixture tool.
- `targets/linux-sbc-hub75/package/`: installer, service unit, install and
  assembly guides, BOM, third-party notices.
- `hardware/`: the printable rear enclosure.

## Skills

- `pixelboard-arcade-games`: adding or changing an arcade game (file map,
  recipe, determinism rules, fixtures, controller contract).
- `pixelboard-arcade-design`: designing for 128×32 and a small controller,
  LED colour, tuning with simulated players.
- `pixelboard-renderer-parity`: any change to what gets drawn.
- `pixelboard-device-runtime`: the Pi service, persistence and its tests.
- Agent `pixelboard-parity-porter`: ports a rendering change from one language
  to the other with proof of byte parity.

## Rules and gotchas

1. **JavaScript inside Python strings.** `DASHBOARD_PAGE` is a normal
   (not raw) Python string. Write `\\n` for a JS newline escape, and never put
   an apostrophe inside a single-quoted JS string literal. Either mistake makes
   the whole dashboard script fail to parse, so every button stops working.
   `tests_py/test_dashboard_page.py` runs `node --check` on every inline script.
2. **Query strings.** HTTP handlers match on `self.path.split("?")[0]`, and
   forms use `onsubmit="…; return false;"`.
3. **Reference frames are strict.** Changing `display-definition.json` or a
   renderer changes hashes. Recompute them from both languages and confirm
   they match each other; never hand-edit a hash.
4. **The runtime stays root.** `rgbmatrix` drops to `daemon` by default after
   panel init; `output.py` disables that unless `panel.dropPrivileges` is set,
   because updates and restarts need root.
5. **Updates.** Devices pull public `main` through a source checkout named in
   `/etc/pixelboard/source-repo`. The update check uses read-only
   `git ls-remote`. Git runs as the checkout's owner with
   `GIT_TERMINAL_PROMPT=0`; never blank `credential.helper`.
6. **Persistence.** `config/` carries forward between releases; durable state
   (history, arcade progress, the household PIN, the boot surprise) lives in
   `state/` → `/var/lib/pixelboard`. New persistent data goes in `state/`.
7. **Privacy.** Use synthetic fixtures. Never commit household settings,
   calendar URLs, device state, team-logo images, or credentials.
8. **Panel tuning** (flicker, PWM jumper, CPU isolation) is documented in
   `docs/PI_TIPS.md`.

## Docs

`README.md` (overview), `docs/CONTROLS.md`, `docs/ARCADE.md`,
`docs/PI_TIPS.md`, `docs/ROADMAP.md`, and the guides in
`targets/linux-sbc-hub75/package/`.
