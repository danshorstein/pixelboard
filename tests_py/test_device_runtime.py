from __future__ import annotations

import importlib
import asyncio
import json
import shutil
import tarfile
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.builds import BuildStore
from shared_py.png import PNG_SIGNATURE, decode_rgba_png, encode_rgba_png
from shared_py.renderer import PixelBuffer


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "targets/linux-sbc-hub75/runtime"


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


class DeviceRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import sys
        sys.path.insert(0, str(RUNTIME))
        cls.transport_module = importlib.import_module("scoreboard_device.transport")
        cls.output_module = importlib.import_module("scoreboard_device.output")
        cls.diagnostics_module = importlib.import_module("scoreboard_device.diagnostics")
        cls.verification_module = importlib.import_module("scoreboard_device.verification")
        cls.runtime_module = importlib.import_module("scoreboard_device.runtime")

    def test_next_releases_hold_and_final_auto_resumes(self) -> None:
        clock = FakeClock()
        transport = self.transport_module.TransportController(final_hold_sec=60, clock=clock)
        items = [
            {"kind": "game", "gameId": "g1", "dwellSec": 30},
            {"kind": "game", "gameId": "g2", "dwellSec": 12},
        ]
        games = [{"gameId": "g1", "status": "in_progress"}, {"gameId": "g2", "status": "pregame"}]
        transport.update(items, games)
        self.assertTrue(transport.toggle_hold())
        self.assertEqual("WATCH LIVE", transport.hold_label)
        transport.next()
        self.assertFalse(transport.held)
        self.assertEqual("g2", transport.current["gameId"])

        transport.previous()
        transport.toggle_hold()
        clock.value += 1
        games[0]["status"] = "final"
        transport.update(items, games)
        clock.value += 61
        self.assertTrue(transport.tick())
        self.assertFalse(transport.held)
        self.assertEqual("g2", transport.current["gameId"])

    def _staged_runtime_root(self, directory: Path) -> Path:
        project = json.loads((ROOT / "fixtures/project.json").read_text(encoding="utf-8"))
        store = BuildStore(directory / "builds")
        result = store.build(project)
        _, artifact_path = store.artifact(result["buildId"])
        extracted = directory / "extracted"
        with tarfile.open(artifact_path) as archive:
            archive.extractall(extracted, filter="data")
        config = json.loads((extracted / "config/runtime-config.json").read_text())
        config["buttons"] = {"enabled": False}
        config["bluetoothRemote"] = {"enabled": False}
        (extracted / "config/runtime-config.json").write_text(json.dumps(config))
        pin_path = extracted / "state" / "broadcast-pin"
        pin_path.parent.mkdir(parents=True, exist_ok=True)
        pin_path.write_text("123456\n", encoding="ascii")
        pin_path.chmod(0o600)
        return extracted

    def test_repository_release_identity_overrides_inherited_artifact_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged_runtime_root(Path(directory))
            inherited_manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            release_identity = {
                "buildId": "20260928T031250Z-1708",
                "sourceCommit": "a" * 40,
                "sourceDirty": False,
            }
            (root / "release-identity.json").write_text(json.dumps(release_identity), encoding="utf-8")

            self.assertNotEqual(release_identity["buildId"], inherited_manifest["buildId"])
            self.assertEqual(release_identity, self.runtime_module._installed_identity(root))

    def test_packaged_verification_rejects_repository_definition_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged_runtime_root(Path(directory))
            shutil.rmtree(root / "definition")
            shutil.copytree(ROOT / "definition", root / "definition")

            with self.assertRaisesRegex(FileNotFoundError, "must be flattened during staging"):
                self.verification_module.verify_frames(root, root / "verification")

    def test_physical_next_hold_sequence_triggers_a_bounded_fireworks_celebration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged_runtime_root(Path(directory))
            runtime = self.runtime_module.DeviceRuntime(root, output_kind="simulator")
            try:
                for _ in range(3):
                    runtime.command_next()
                for _ in range(3):
                    runtime.command_hold()
                for _ in range(3):
                    runtime.command_next()

                status = runtime.status()
                self.assertTrue(status["fireworks"]["active"])

                now = datetime.now(timezone.utc)
                frame = runtime._render(now)
                self.assertIsNotNone(frame)
                # The fireworks frame's constant background (see
                # shared_py/fireworks_frame.py) is distinctive versus any
                # normal game/idle/standings scene, so this actually confirms
                # the fireworks branch rendered rather than merely that
                # _render returned something non-None.
                self.assertEqual(tuple(frame.data[0:4]), (5, 12, 34, 255))

                # NEXT exits the celebration early.
                runtime.command_next()
                self.assertFalse(runtime.status()["fireworks"]["active"])
            finally:
                runtime.buttons.close()
                runtime.output.close()
                runtime.status_server.server.server_close()  # never started; shutdown() would hang

    def test_armed_reveal_autoplays_once_on_boot_then_marks_completed(self) -> None:
        from shared_py.reveal import arm, default_reveal, load_reveal, save_reveal

        with tempfile.TemporaryDirectory() as directory:
            root = self._staged_runtime_root(Path(directory))
            project = json.loads((root / "config/project.json").read_text())
            project["reveal"] = {"lines": ["HI THERE"], "lineDwellSec": 0.02, "fireworksDwellSec": 0.02}
            (root / "config/project.json").write_text(json.dumps(project))

            reveal_path = root / "state" / "reveal.json"
            save_reveal(reveal_path, arm(default_reveal()))

            runtime = self.runtime_module.DeviceRuntime(root, output_kind="simulator")
            try:

                async def drive() -> None:
                    task = asyncio.ensure_future(runtime.run())
                    await asyncio.sleep(0.5)
                    runtime.stop()
                    await asyncio.wait_for(task, timeout=5)

                asyncio.run(drive())

                self.assertEqual(load_reveal(reveal_path)["state"], "completed")
            finally:
                runtime.buttons.close()
                runtime.output.close()
                runtime.status_server.server.server_close()

    def test_armed_reveal_defers_during_sleep_quiet_hours_instead_of_playing(self) -> None:
        from shared_py.reveal import arm, default_reveal, load_reveal, save_reveal

        with tempfile.TemporaryDirectory() as directory:
            root = self._staged_runtime_root(Path(directory))
            project = json.loads((root / "config/project.json").read_text())
            project["reveal"] = {"lines": ["HI THERE"], "lineDwellSec": 0.02, "fireworksDwellSec": 0.02}
            # Covers virtually the entire day, so "now" falls inside it
            # regardless of when this test runs.
            project["quietHours"] = {"enabled": True, "start": "00:00", "end": "23:59", "behavior": "sleep"}
            (root / "config/project.json").write_text(json.dumps(project))

            reveal_path = root / "state" / "reveal.json"
            save_reveal(reveal_path, arm(default_reveal()))

            runtime = self.runtime_module.DeviceRuntime(root, output_kind="simulator")
            try:
                async def drive() -> None:
                    task = asyncio.ensure_future(runtime.run())
                    await asyncio.sleep(0.3)
                    runtime.stop()
                    await asyncio.wait_for(task, timeout=5)

                asyncio.run(drive())

                # Quiet hours (sleep) won at boot: the reveal was deferred,
                # not consumed — it stays armed for a later, non-quiet boot.
                self.assertEqual(load_reveal(reveal_path)["state"], "armed")
                # Not silent: an operator can see it was deferred, not lost.
                self.assertTrue(runtime.status()["reveal"]["deferredForQuietHours"])
            finally:
                runtime.buttons.close()
                runtime.output.close()
                runtime.status_server.server.server_close()

    def test_reveal_control_page_and_endpoints_work_over_real_http(self) -> None:
        from shared_py.reveal import load_reveal

        with tempfile.TemporaryDirectory() as directory:
            root = self._staged_runtime_root(Path(directory))
            project = json.loads((root / "config/project.json").read_text())
            project["reveal"] = {"lines": ["HI"], "lineDwellSec": 0.02, "fireworksDwellSec": 0.02}
            (root / "config/project.json").write_text(json.dumps(project))
            config = json.loads((root / "config/runtime-config.json").read_text())
            config["status"] = {"host": "127.0.0.1", "port": 0}
            (root / "config/runtime-config.json").write_text(json.dumps(config))

            runtime = self.runtime_module.DeviceRuntime(root, output_kind="simulator")
            try:
                async def drive() -> None:
                    task = asyncio.ensure_future(runtime.run())
                    await asyncio.sleep(0.1)
                    port = runtime.status_server.server.server_address[1]
                    base = f"http://127.0.0.1:{port}"

                    page = await asyncio.to_thread(lambda: urllib.request.urlopen(base + "/").read())
                    self.assertIn(b"Play reveal now", page)

                    status = await asyncio.to_thread(lambda: json.loads(urllib.request.urlopen(base + "/reveal/status").read()))
                    self.assertEqual(status["state"], "disarmed")

                    # Verify GET /api/config
                    config_res = await asyncio.to_thread(lambda: json.loads(urllib.request.urlopen(base + "/api/config").read()))
                    self.assertIn("quietHours", config_res)
                    self.assertIn("brightness", config_res)
                    self.assertIn("favorites", config_res)
                    self.assertIn("allTeams", config_res)
                    self.assertIn("WSH", config_res["allTeams"])

                    def post(path: str, data: bytes = b"") -> dict:
                        headers = {"X-Scoreboard-Broadcast-Pin": "123456"}
                        if data:
                            headers["Content-Type"] = "application/json"
                        request = urllib.request.Request(
                            base + path,
                            method="POST",
                            data=data,
                            headers=headers,
                        )
                        return json.loads(urllib.request.urlopen(request).read())

                    # Every state-changing route uses the household PIN.
                    unauthenticated = urllib.request.Request(base + "/api/control/next", method="POST")
                    with self.assertRaises(urllib.error.HTTPError) as denied:
                        await asyncio.to_thread(urllib.request.urlopen, unauthenticated)
                    self.assertEqual(denied.exception.code, 401)

                    # Verify POST /api/config
                    update_payload = json.dumps({
                        "expectedVersion": config_res["version"],
                        "quietHours": {"enabled": True, "start": "22:00", "end": "07:00", "behavior": "dim"},
                        "brightness": {"normal": 40, "dim": 15},
                        "favorites": ["WSH", "NYM"],
                    }).encode("utf-8")
                    save_res = await asyncio.to_thread(post, "/api/config", update_payload)
                    self.assertTrue(save_res["ok"])
                    self.assertEqual(save_res["config"]["brightness"]["normal"], 40)
                    self.assertEqual(save_res["config"]["favorites"], ["WSH", "NYM"])
                    # Check disk persistence
                    saved_project = json.loads((runtime.root / "config/project.json").read_text(encoding="utf-8"))
                    self.assertEqual(saved_project["brightness"]["normal"], 40)
                    self.assertEqual(saved_project["favorites"], ["WSH", "NYM"])

                    stale_payload = json.dumps({"expectedVersion": config_res["version"], "favorites": ["WSH"]}).encode("utf-8")
                    with self.assertRaises(urllib.error.HTTPError) as stale:
                        await asyncio.to_thread(post, "/api/config", stale_payload)
                    self.assertEqual(stale.exception.code, 409)

                    # Verify POST /api/control/next and /api/control/hold
                    next_res = await asyncio.to_thread(post, "/api/control/next")
                    self.assertTrue(next_res["ok"])
                    self.assertEqual(next_res["action"], "next")

                    hold_res = await asyncio.to_thread(post, "/api/control/hold")
                    self.assertTrue(hold_res["ok"])
                    self.assertEqual(hold_res["action"], "hold")

                    # Verify GET /api/update/check
                    update_check = await asyncio.to_thread(lambda: json.loads(urllib.request.urlopen(base + "/api/update/check").read()))
                    self.assertIn("available", update_check)
                    self.assertIn("commits", update_check)

                    armed = await asyncio.to_thread(post, "/reveal/arm")
                    self.assertEqual(armed["state"], "armed")

                    rehearsed = await asyncio.to_thread(post, "/reveal/rehearse")
                    self.assertTrue(rehearsed["triggered"])
                    self.assertFalse(rehearsed["consumesState"])
                    await asyncio.sleep(0.5)
                    # Rehearsal must never touch reveal.json.
                    self.assertEqual(load_reveal(runtime.reveal_path)["state"], "armed")

                    triggered = await asyncio.to_thread(post, "/reveal/trigger")
                    self.assertTrue(triggered["consumesState"])
                    await asyncio.sleep(0.5)
                    self.assertEqual(load_reveal(runtime.reveal_path)["state"], "completed")

                    runtime.stop()
                    await asyncio.wait_for(task, timeout=5)

                asyncio.run(drive())
            finally:
                runtime.buttons.close()
                runtime.output.close()

    def test_surprise_ignores_all_viewer_controls_through_text_and_fireworks(self) -> None:
        from time import monotonic
        from scoreboard_device.bluetooth_remote import EV_KEY, DEFAULT_KEY_CODES
        from shared_py.reveal_frame import create_reveal_text_frame
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged_runtime_root(Path(directory))
            runtime = self.runtime_module.DeviceRuntime(root, output_kind="simulator")
            observed = []
            original_show = runtime._show_frame
            def show(frame):
                observed.append(bytes(frame.data)); original_show(frame)
            runtime._show_frame = show
            try:
                async def drive():
                    started = monotonic()
                    task = asyncio.create_task(runtime._play_reveal_sequence(custom_lines=['ONE','TWO','THREE'], line_dwell=.12, fireworks_dwell=.15))
                    await asyncio.sleep(.03)
                    before = runtime.transport.status().copy()
                    while not task.done():
                        runtime.command_next(); runtime.command_hold()
                        for button, code in DEFAULT_KEY_CODES.items():
                            runtime.bluetooth_remote._handle_event(EV_KEY,code,1)
                            runtime.bluetooth_remote._handle_event(EV_KEY,code,0)
                        self.assertFalse(runtime.arcade.active)
                        self.assertFalse(runtime.controller_settings.active)
                        self.assertEqual(before,runtime.transport.status())
                        self.assertEqual(0,runtime.next_presses)
                        self.assertEqual(0,runtime.hold_presses)
                        await asyncio.sleep(.03)
                    await task
                    self.assertGreaterEqual(monotonic()-started,.51)
                    self.assertFalse(runtime._reveal_active)
                    runtime.command_next(); runtime.command_hold()
                    self.assertEqual(1,runtime.next_presses)
                    self.assertEqual(1,runtime.hold_presses)
                asyncio.run(drive())
                for line in ('ONE','TWO','THREE'):
                    expected = create_reveal_text_frame(128,32,[line],runtime.fonts['5x7'])
                    self.assertIn(bytes(expected.data),observed)
                self.assertTrue(any(f[:4]==bytes((5,12,34,255)) for f in observed))
            finally:
                runtime.bluetooth_remote.close(); runtime.buttons.close()
                runtime.output.close(); runtime.status_server.server.server_close()

    def test_fireworks_sequence_recognizes_each_physical_press_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged_runtime_root(Path(directory))
            runtime = self.runtime_module.DeviceRuntime(root, output_kind="simulator")
            try:
                runtime.command_next()
                runtime.command_next()
                self.assertEqual(runtime.next_presses, 2)
                self.assertFalse(runtime.status()["fireworks"]["active"])
                self.assertEqual(runtime.status()["fireworks"]["progress"], 2)
            finally:
                runtime.buttons.close()
                runtime.output.close()
                runtime.status_server.server.server_close()  # never started; shutdown() would hang

    def _write_recap_window(self, root: Path, *, quiet_hours: dict | None = None) -> datetime:
        """Seeds state/recap-window.json with a WSH result + WSH/PHI upcoming
        games, dated relative to the real 'today' so _recap_forward_days sees
        a live forward window. Returns a datetime inside the 07:00-09:00
        morning window in the project timezone."""
        from zoneinfo import ZoneInfo

        project = json.loads((root / "config/project.json").read_text())
        if quiet_hours is not None:
            project["quietHours"] = quiet_hours
        (root / "config/project.json").write_text(json.dumps(project))

        tz = ZoneInfo(project.get("timezone", "America/New_York"))
        today = datetime.now(tz).date()

        def iso(days: int, hour: int) -> str:
            moment = datetime(today.year, today.month, today.day, hour, 5, tzinfo=tz) + timedelta(days=days)
            return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

        games = [
            {"gameId": "mlb-r1", "gameNumber": 1, "doubleheader": False,
             "home": {"abbr": "WSH", "score": 6}, "away": {"abbr": "MIA", "score": 2},
             "status": "final", "startTimeUtc": iso(-2, 19), "startTimeLocal": None},
            {"gameId": "mlb-n1", "gameNumber": 1, "doubleheader": False,
             "home": {"abbr": "WSH"}, "away": {"abbr": "ATL"},
             "status": "pregame", "startTimeUtc": iso(4, 19), "startTimeLocal": None},
            {"gameId": "mlb-n2", "gameNumber": 1, "doubleheader": False,
             "home": {"abbr": "NYM"}, "away": {"abbr": "PHI"},
             "status": "pregame", "startTimeUtc": iso(3, 13), "startTimeLocal": None},
        ]
        window = {
            "schemaVersion": "1.0",
            "startDate": (today - timedelta(days=4)).isoformat(),
            "endDate": (today + timedelta(days=14)).isoformat(),
            "fetchedUtc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "games": games,
        }
        (root / "state").mkdir(exist_ok=True)
        (root / "state/recap-window.json").write_text(json.dumps(window))
        return datetime(today.year, today.month, today.day, 8, 0, tzinfo=tz)

    def test_morning_window_renders_recap_cards_and_cycles_favorites(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged_runtime_root(Path(directory))
            now_in_window = self._write_recap_window(root)
            runtime = self.runtime_module.DeviceRuntime(root, output_kind="simulator")
            try:
                calls: list[str] = []
                real_render_recap = runtime._render_recap

                def spy(now: datetime):
                    calls.append("recap")
                    return real_render_recap(now)

                runtime._render_recap = spy  # type: ignore[method-assign]

                first = runtime._render(now_in_window)
                self.assertEqual(calls, ["recap"])
                self.assertIsNotNone(first)
                self.assertEqual(runtime._recap_index, 0)

                # Force the dwell to elapse; the next render advances to the
                # second favorite and produces a visibly different card.
                runtime._recap_started -= 999
                second = runtime._render(now_in_window)
                self.assertEqual(runtime._recap_index, 1)
                self.assertNotEqual(bytes(first.data), bytes(second.data))
            finally:
                runtime.buttons.close()
                runtime.output.close()
                runtime.status_server.server.server_close()

    def test_recap_card_is_not_shown_outside_the_morning_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged_runtime_root(Path(directory))
            now_in_window = self._write_recap_window(root)
            now_afternoon = now_in_window.replace(hour=14)
            runtime = self.runtime_module.DeviceRuntime(root, output_kind="simulator")
            try:
                calls: list[str] = []
                runtime._render_recap = lambda now: calls.append("x")  # type: ignore[method-assign,return-value]
                runtime._render(now_afternoon)
                self.assertEqual(calls, [])
            finally:
                runtime.buttons.close()
                runtime.output.close()
                runtime.status_server.server.server_close()

    def test_recap_card_yields_to_sleep_quiet_hours(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged_runtime_root(Path(directory))
            now_in_window = self._write_recap_window(
                root,
                quiet_hours={"enabled": True, "start": "00:00", "end": "23:59", "behavior": "sleep"},
            )
            runtime = self.runtime_module.DeviceRuntime(root, output_kind="simulator")
            try:
                calls: list[str] = []
                runtime._render_recap = lambda now: calls.append("x")  # type: ignore[method-assign,return-value]
                frame = runtime._render(now_in_window)
                self.assertIsNotNone(frame)
                self.assertEqual(15, runtime.output.brightness)
                self.assertEqual(calls, [])
            finally:
                runtime.buttons.close()
                runtime.output.close()
                runtime.status_server.server.server_close()

    def test_recap_forward_days_reflects_the_cached_window_not_a_constant(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged_runtime_root(Path(directory))
            now_in_window = self._write_recap_window(root)
            runtime = self.runtime_module.DeviceRuntime(root, output_kind="simulator")
            try:
                self.assertEqual(runtime._recap_forward_days(now_in_window), 14)
                # A window whose end date is already in the past has genuinely
                # checked zero future days.
                runtime._recap_window["endDate"] = (now_in_window.date() - timedelta(days=1)).isoformat()
                self.assertEqual(runtime._recap_forward_days(now_in_window), 0)
            finally:
                runtime.buttons.close()
                runtime.output.close()
                runtime.status_server.server.server_close()

    def test_recap_window_refresh_failure_keeps_serving_the_cached_window(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._staged_runtime_root(Path(directory))
            self._write_recap_window(root)
            runtime = self.runtime_module.DeviceRuntime(root, output_kind="simulator")
            try:
                cached = runtime._recap_window
                self.assertIsNotNone(cached)

                class BoomAdapter:
                    async def get_recap_window(self, **_: object):
                        raise RuntimeError("provider outage")

                runtime.adapter = BoomAdapter()  # type: ignore[assignment]
                asyncio.run(runtime._fetch_recap_window())

                self.assertEqual(runtime._recap_window, cached)
                self.assertIn("provider outage", runtime.status()["recap"]["lastError"])
            finally:
                runtime.buttons.close()
                runtime.output.close()
                runtime.status_server.server.server_close()

    def test_simulator_output_writes_a_valid_png(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = self.output_module.SimulatorOutput(Path(directory), 4, 2)
            frame = PixelBuffer(4, 2, (1, 2, 3, 255))
            output.show(frame)
            payload = (Path(directory) / "latest.png").read_bytes()
            self.assertTrue(payload.startswith(PNG_SIGNATURE))
            self.assertEqual(payload, encode_rgba_png(4, 2, frame.data))

    def test_png_encoder_rejects_wrong_payload_size(self) -> None:
        with self.assertRaises(ValueError):
            encode_rgba_png(2, 2, b"too short")

    def test_png_decoder_round_trips_rgba(self) -> None:
        rgba = bytes((index * 29) % 256 for index in range(3 * 2 * 4))
        self.assertEqual((3, 2, rgba), decode_rgba_png(encode_rgba_png(3, 2, rgba)))

    def test_device_runtime_loads_a_user_supplied_logo_asset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            logo_dir = root / "assets/team-logos"
            logo_dir.mkdir(parents=True)
            rgba = bytes((index * 17) % 256 for index in range(16 * 16 * 4))
            payload = encode_rgba_png(16, 16, rgba)
            (logo_dir / "sample.png").write_bytes(payload)
            (logo_dir / "manifest.json").write_text(json.dumps({"assets": [{
                "path": "sample.png", "teamId": "demo", "width": 16, "height": 16,
                "sha256": __import__("hashlib").sha256(payload).hexdigest()
            }]}))
            loaded = self.runtime_module._load_logo_assets(root)
            self.assertEqual(["team-logo:demo:16"], list(loaded))
            self.assertEqual(rgba, loaded["team-logo:demo:16"]["data"])

    def test_packaged_verification_harness_matches_all_golden_frames(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = self.verification_module.verify_frames(ROOT, Path(directory))
            expected_frames = json.loads(
                (ROOT / "fixtures/expected-render-frames.json").read_text(encoding="utf-8")
            )
            self.assertEqual("pass", report["status"])
            self.assertEqual(len(expected_frames), len(report["frames"]))
            self.assertTrue(all(frame["match"] for frame in report["frames"]))
            self.assertEqual(len(expected_frames), len(list(Path(directory).glob("*.png"))))

    def test_diagnostic_patterns_cover_color_geometry_and_pixel_addressing(self) -> None:
        frames = self.diagnostics_module.diagnostic_frames(128, 32, 64)
        self.assertEqual(
            ["red", "green", "blue", "white", "geometry", "checkerboard"],
            [name for name, _ in frames],
        )
        self.assertTrue(all(frame.width == 128 and frame.height == 32 for _, frame in frames))
        checker = frames[-1][1]
        self.assertNotEqual(checker.data[0:4], checker.data[4:8])

    def test_diagnostic_command_completes_in_simulator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            shutil.copy(
                ROOT / "targets/linux-sbc-hub75/profiles/ticker-128x32-p4.json",
                root / "config/device-profile.json",
            )
            shutil.copy(ROOT / "fixtures/project.json", root / "config/project.json")
            config = json.loads((ROOT / "targets/linux-sbc-hub75/runtime-config.json").read_text())
            config["buttons"]["enabled"] = False
            config["bluetoothRemote"]["enabled"] = False
            (root / "config/runtime-config.json").write_text(json.dumps(config))
            report = asyncio.run(
                self.diagnostics_module.run_diagnostics(
                    root,
                    output_kind="simulator",
                    step_sec=0.05,
                    cycles=1,
                )
            )
            self.assertEqual("complete", report["status"])
            self.assertEqual(1, report["completedCycles"])
            self.assertEqual("ticker-128x32-p4", report["profileId"])
            self.assertEqual(
                ["red", "green", "blue", "white", "geometry", "checkerboard"],
                report["patterns"],
            )
            self.assertTrue(report["operatorVerificationRequired"])
            self.assertFalse(report["bluetoothRemote"]["enabled"])
            self.assertTrue((root / "state/latest.png").is_file())
            latest = root / report["reportFiles"]["latest"]
            history = root / report["reportFiles"]["history"]
            self.assertEqual(report, json.loads(latest.read_text(encoding="utf-8")))
            self.assertEqual(report, json.loads(history.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
