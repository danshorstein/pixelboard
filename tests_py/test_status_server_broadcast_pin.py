from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path


RUNTIME = Path(__file__).resolve().parents[1] / "targets/linux-sbc-hub75/runtime"


class HouseholdBroadcastTests(unittest.TestCase):
    def test_broadcast_pin_is_private_and_persistent(self) -> None:
        sys.path.insert(0, str(RUNTIME))
        BroadcastPinStore = importlib.import_module("scoreboard_device.admin_auth").BroadcastPinStore
        with tempfile.TemporaryDirectory() as directory:
            store = BroadcastPinStore(Path(directory))
            pin = store.get_or_create()
            self.assertRegex(pin, r"^[0-9]{6}$")
            self.assertEqual(store.get_or_create(), pin)
            self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)
            self.assertTrue(store.matches(pin, pin))
            self.assertFalse(store.matches(pin, "0000000"))
            rotated = store.rotate()
            self.assertRegex(rotated, r"^[0-9]{6}$")
            self.assertNotEqual(rotated, pin)
            self.assertEqual(store.get_or_create(), rotated)

    def test_household_pin_controls_screens_and_installs_updates(self) -> None:
        sys.path.insert(0, str(RUNTIME))
        StatusServer = importlib.import_module("scoreboard_device.status_server").StatusServer
        called = []
        server = StatusServer("127.0.0.1", 0, lambda: {}, actions={
            **{f"control_{a}": lambda a=a: called.append(a) or {"ok": True}
               for a in ("home", "next", "hold")},
            "apply_update": lambda: called.append("update") or {"ok": True}},
            authorize_broadcast=lambda pin: pin == "123456")
        server.start()
        base = f"http://127.0.0.1:{server.server.server_address[1]}"
        def post(path, headers):
            return urllib.request.urlopen(urllib.request.Request(base + path,
                method="POST", headers=headers))
        pin = {"X-Scoreboard-Broadcast-Pin": "123456"}
        try:
            with urllib.request.urlopen(base + "/") as dashboard:
                self.assertIn("no-store", dashboard.headers.get("Cache-Control", ""))
            for action in ("home", "next", "hold"):
                with post("/api/control/" + action, pin) as response:
                    self.assertEqual(response.status, 200)
            self.assertEqual(called, ["home", "next", "hold"])
            for path, headers in (("/api/control/next", {}),
                ("/api/control/next", {**pin, "Origin": "http://evil.example"})):
                with self.assertRaises(urllib.error.HTTPError):
                    post(path, headers)
            self.assertEqual(called, ["home", "next", "hold"])
            with post("/api/update/apply", pin) as response:
                self.assertEqual(response.status, 200)
            self.assertEqual(called[-1], "update")
            with self.assertRaises(urllib.error.HTTPError):
                post("/api/update/apply", {"X-Scoreboard-Token": "legacy-token"})
        finally:
            server.close()

    def test_live_broadcast_and_boot_surprise_need_household_pin(self) -> None:
        sys.path.insert(0, str(RUNTIME))
        StatusServer = importlib.import_module("scoreboard_device.status_server").StatusServer
        messages: list[dict] = []
        server = StatusServer(
            "127.0.0.1",
            0,
            lambda: {"status": "ok"},
            actions={"play_message": lambda payload: messages.append(payload) or {"ok": True}},
            authorize_broadcast=lambda pin: pin == "123456",
        )
        server.start()
        base = f"http://127.0.0.1:{server.server.server_address[1]}"

        def post(payload: dict, headers: dict[str, str] | None = None) -> dict:
            request = urllib.request.Request(
                base + "/api/message",
                method="POST",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", **(headers or {})},
            )
            return json.loads(urllib.request.urlopen(request).read())

        try:
            with self.assertRaises(urllib.error.HTTPError) as denied_broadcast:
                post({"lines": ["GO TEAM!"], "armForBoot": False})
            self.assertEqual(denied_broadcast.exception.code, 401)
            self.assertEqual(messages, [])

            self.assertTrue(post({"lines": ["GO TEAM!"], "armForBoot": False},
                                 {"X-Scoreboard-Broadcast-Pin": "123456"})["ok"])
            self.assertEqual(messages, [{"lines": ["GO TEAM!"], "armForBoot": False}])

            self.assertTrue(post({"lines": ["LATER"], "armForBoot": True},
                                 {"X-Scoreboard-Broadcast-Pin": "123456"})["ok"])
            self.assertEqual(len(messages), 2)

            with self.assertRaises(urllib.error.HTTPError) as cross_origin:
                post({"lines": ["EVIL"]}, {"Origin": "http://other-site.example",
                                           "X-Scoreboard-Broadcast-Pin": "123456"})
            self.assertEqual(cross_origin.exception.code, 403)
            self.assertEqual(len(messages), 2)

            protected = urllib.request.Request(base + "/api/control/next", method="POST")
            with self.assertRaises(urllib.error.HTTPError) as denied_control:
                urllib.request.urlopen(protected)
            self.assertEqual(denied_control.exception.code, 401)

            # The missing-PIN screen request above is already one failed attempt.
            for _ in range(4):
                with self.assertRaises(urllib.error.HTTPError) as wrong_pin:
                    post({"lines": ["NO"]}, {"X-Scoreboard-Broadcast-Pin": "111111"})
                self.assertEqual(wrong_pin.exception.code, 401)
            with self.assertRaises(urllib.error.HTTPError) as throttled:
                post({"lines": ["NO"]}, {"X-Scoreboard-Broadcast-Pin": "111111"})
            self.assertEqual(throttled.exception.code, 429)
            self.assertEqual(len(messages), 2)
        finally:
            server.close()
