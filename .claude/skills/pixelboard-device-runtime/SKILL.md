---
name: pixelboard-device-runtime
description: Use when working on targets/linux-sbc-hub75/runtime/scoreboard_device (DeviceRuntime, transport, reveal, fireworks, status_server, __main__ CLI) or targets/linux-sbc-hub75/package/install.sh for Pixelboard. Architecture map, state/persistence conventions, and testing gotchas specific to this device runtime.
---

# Device runtime architecture

`targets/linux-sbc-hub75/runtime/scoreboard_device/` is the Python service
that actually runs on the Raspberry Pi. Key modules:

- `runtime.py` — `DeviceRuntime`: the main class. Owns the render loop
  (`run()`), data fetching (`_fetch()` for the baseball-day games,
  `_fetch_recap_window()` for the slow morning-recap schedule window),
  NEXT/HOLD button handling (`command_next`/`command_hold`), the fireworks
  secret-sequence detector, the boot-surprise reveal sequence, and the
  morning-recap card branch.
- **`_render` precedence chain** (top to bottom, first match wins):
  reveal-active (own render loop owns the panel) → quiet+`sleep` (blank) →
  set brightness (normal or `dim`) → fireworks celebration → morning-recap
  window (`_render_recap`, cycles one card per favorite) → normal
  rotation. Any new takeover branch (victory celebrations, favorite
  shortcut) slots into this chain deliberately — a manual/secret action
  should generally beat a scheduled one; see where fireworks sits relative
  to recap.
- **Morning recap**: `_fetch_recap_window()` pulls
  `(today-4d)..(today+searchDays)` via `MlbStatsApiAdapter.get_recap_window`
  on a 6-hour cadence, caches to `state/recap-window.json`
  (`shared_py/recap_cache.py`, fails closed like `load_reveal`), and a
  fetch failure keeps serving the last good window. `_render_recap` builds
  a `shared_py/morning_recap.build_recap` payload per favorite and renders
  `shared_py/recap_frame.create_recap_frame` (device-only staged text — no
  scene, no TS twin; see the `pixelboard-renderer-parity` skill's
  "device-only frames" section). The window/dwell settings
  (`project.recap`) are read once at `__init__`, so changing them needs a
  service restart.
- `transport.py` — `TransportController`: NEXT/HOLD/playlist-advance state
  machine, shared conceptually with the browser's `useTransport` but not
  code-shared (separate implementations, no parity requirement here since
  it's control-flow, not pixels).
- `status_server.py` — `StatusServer`: a `ThreadingHTTPServer` wrapper on port 8123.
  Serves the full local dashboard (`/`), health checks (`/health`), JSON status (`/status`),
  live screen capture PNG (`/api/screen.png`), config editing (`/api/config`), live controls
  (`/api/control/next`, `/api/control/hold`), custom stadium announcements (`/api/message`),
  git auto-update (`/api/update/check`, `/api/update/apply`), and reveal controls (`/reveal/*`).
  *Important gotcha*: when writing JavaScript inside Python multiline strings in this file,
  newlines in JS literals MUST be escaped as `\\n` (e.g. `lines.join('\\n')`); otherwise Python
  turns `\n` into a literal line break in the HTML string, creating a JS `SyntaxError` that kills
  all client-side scripting on page load. All routes must strip query params with `self.path.split("?")[0]`.
- `buttons.py` — `PhysicalButtons`: wraps `gpiozero.Button`, callbacks run
  on gpiozero's own background thread, independent of whatever the main
  thread/event loop is doing. This is why a blocking `time.sleep`-style
  sequence (like the reveal) can still be interrupted by a button press.
- `__main__.py` — CLI: `run`, `verify`, `diagnose`, `rehearse`,
  `reveal {arm,disarm,replay,status}`.
- `output.py` — `Hub75Output` (real panel) and `SimulatorOutput` (PNG to
  `state/latest.png`). `Hub75Output.__init__` builds `RGBMatrixOptions`
  from `runtime-config.json` `panel.*`; `show()` does a single
  `canvas.SetImage(PIL RGB)` blit (a per-pixel `SetPixel` loop starved the
  refresh thread and caused flicker). Panel tuning keys, all optional/no-op
  unless set: `pwmBits`, `pwmLsbNanoseconds`, `limitRefreshRateHz`,
  `showRefreshRate`, plus `gpioSlowdown`, `panelType`, `multiplexing`,
  `hardwareMapping`, and `dropPrivileges` (see gotcha below).

## Gotcha: rgbmatrix drops the process to `daemon` (uid 1)

`RGBMatrix(options=...)` in `Hub75Output.__init__` drops privileges right
after init — `RGBMatrixOptions.drop_privileges` defaults on,
`drop_priv_user` defaults to `daemon`. So even though `scoreboard.service`
is `User=root`, everything that runs *after* the first `_render` (the
whole status-server request lifetime) is uid 1. That silently broke
`_web_check_update` / `_web_apply_update` (couldn't `setuid` to the source
checkout's owner, couldn't `chown` or `systemctl restart`). `output.py` now sets
`options.drop_privileges = bool(panel.get("dropPrivileges", False))` so
the runtime stays root. If you add any device feature that shells out and
needs root or a specific user, remember it runs as `daemon` unless
`drop_privileges` is off. GPIO descriptors are opened in `buttons.py`
*before* `RGBMatrix()` for the same reason. Check with
`sudo cat /proc/$(systemctl show -p MainPID --value scoreboard.service)/status | grep Uid`.

## Gotcha: updates keep the device's own `config/`

`install.sh` (first install) and `scripts/update-device.sh` (dashboard and
manual updates) both stage a new release under `/opt/pixelboard/releases/`,
verify it, and only then swap the `/opt/pixelboard` symlink, rolling back if
the health check fails. An update copies the running release first and then
replaces `runtime/`, `shared_py/`, `definition/`, `fixtures/`, `scripts/` and
the service unit from the source checkout named in
`/etc/pixelboard/source-repo`. It does **not** copy
`targets/linux-sbc-hub75/runtime-config.json`: the device's
`/opt/pixelboard/config/runtime-config.json` carries forward, so the repo
file is only the default for new installs. Changing panel tuning on a device
means editing the on-device file.

## Persistence: STATE_DIR survives everything

Settings in `config/` carry forward from release to release, but a fresh
install replaces them. Anything that
must survive an update — the reveal's armed/started/completed state
(`state/reveal.json`), the morning-recap schedule cache
(`state/recap-window.json`), diagnostics, verification output — must live
under `state/`, which `install.sh` symlinks (`${RELEASE_DIR}/state` →
`/var/lib/pixelboard`) into the persistent, install-independent
`STATE_DIR`. If you add new device-side persistent state, put it under
`self.root / "state" / ...` and verify it survives a simulated reinstall
(see `tests_py/test_project_store.py`'s pattern, or just trace that your
new state path goes through the `state` symlink, not `config`).

## The reveal state machine

`shared_py/reveal.py` — pure `disarmed → armed → started → completed`
transitions. Two properties that must never regress:

1. `arm()` is **never** called automatically by boot code or the installer.
   Only an explicit operator action (CLI `reveal arm`, or the web control
   page's "Arm as Boot Surprise" button) reaches it. This is what keeps
   "ordinary boots must not rearm the reveal" true structurally.
2. `begin_playback()` must be persisted to disk **before** the first reveal
   frame renders (`DeviceRuntime.run()` does `save_reveal(...,
   begin_playback(reveal))` then `await self._play_reveal_sequence()`, not
   the other way around). This is what bounds a power-loss-mid-playback to
   "doesn't replay," not "replays forever."
3. `force_start()` is deliberately unrestricted (works from any state) —
   it exists specifically for an explicit "play it now" action (the web
   control page's primary button) where the whole point is to work
   regardless of current arm state. Don't reuse the restricted
   `begin_playback`/`replay` transitions for a manual trigger — that bug
   shipped once already and was only caught by an actual
   HTTP-level test, not a state-machine unit test.

## Concurrency: HTTP handler thread vs asyncio loop thread

`StatusServer` runs its HTTP handling on its own OS thread
(`ThreadingHTTPServer` + a dedicated `threading.Thread`), separate from
`DeviceRuntime`'s asyncio event loop. Synchronous state (reveal.json
read/write, protected by `self.lock`) can be touched directly from either
thread. Anything that needs to actually **play** on the display (an async
coroutine like `_play_reveal_sequence`) must be scheduled onto the running
loop via `asyncio.run_coroutine_threadsafe(coro, self._loop)` — `self._loop`
is captured via `asyncio.get_running_loop()` at the top of `run()`, so it's
`None` until the service has actually started. An HTTP handler must not
`await` that future directly (it would block the HTTP response for the
full playback duration) — fire it and return immediately, and make sure any
exception inside the detached task is logged (`LOGGER.exception(...)`)
since nothing else will surface it.

## Testing gotchas

- **`StatusServer.close()` hangs if `.start()` was never called.**
  `close()` calls `self.server.shutdown()`, which blocks waiting for the
  `serve_forever()` loop (started by `.start()`) to notice and exit. If a
  test constructs a `DeviceRuntime` but never calls `.run()` (so the status
  server thread never started), clean up with
  `runtime.status_server.server.server_close()` directly instead —
  `.close()` will hang the test process. Only call `.close()` after
  `.start()` (or after `run()`'s own `finally` block does it for you).
- **`DeviceRuntime` needs a fully staged root** (`config/project.json`,
  `config/device-profile.json`, `config/runtime-config.json`,
  `definition/display-definition.json`, `definition/fonts/*.bdf`). Don't
  hand-build this — use `backend.builds.BuildStore` to produce a real
  artifact and extract it, matching production packaging exactly (see
  `tests_py/test_device_runtime.py::_staged_runtime_root` for the pattern).
  This also means any test using it is implicitly exercising the real
  build pipeline, which is a feature, not overhead.
- **Driving `run()` in a test**: it runs until `stop_event` is set.
  Schedule it as a task, `await asyncio.sleep(...)` for however long the
  scenario needs, call `runtime.stop()`, then
  `await asyncio.wait_for(task, timeout=...)`. For anything involving the
  reveal/fireworks with real dwell times, override `project["reveal"]` (or
  the fireworks constants) to near-zero durations in the staged config
  before constructing `DeviceRuntime` — don't wait through real 10-30s
  timers in a test.
- **Button callbacks fire on gpiozero's thread, independent of whatever
  the main thread is doing** — so a test simulating "NEXT pressed during
  a blocking reveal sequence" should call `runtime.command_next()`
  directly (simulating the GPIO callback), not try to interrupt the
  `asyncio.sleep` loop some other way.
- **Testing the recap / morning-window branch without live data or real
  timers**: seed `state/recap-window.json` directly (see
  `tests_py/test_device_runtime.py::_write_recap_window` — dates relative
  to the real "today" so `_recap_forward_days` sees a live forward
  window), pass an arbitrary `now` into `runtime._render(now)` to force
  being inside/outside the window, and spy on `runtime._render_recap` (or
  compare frame bytes) to assert which branch ran. Advance the recap
  cycle by setting `runtime._recap_started -= 999` rather than sleeping
  through the dwell. `_fetch_recap_window` is exception-safe — a test can
  set `runtime.adapter` to a stub that raises and assert the cached
  window is untouched.
- **`install.sh` cannot be tested end-to-end** in this sandbox (needs real
  systemd + hardware). It's checked at the text/shape level in
  `tests_py/test_builds.py` (required substrings: staging directory usage,
  explicit `systemctl restart`, rollback markers) and with `bash -n` for
  syntax. If you change it, keep those markers meaningful — don't just
  add a string that satisfies a grep without matching the described
  behavior.
