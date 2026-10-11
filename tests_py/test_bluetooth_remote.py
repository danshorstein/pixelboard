from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "targets/linux-sbc-hub75/runtime"
sys.path.insert(0, str(RUNTIME))

from scoreboard_device.bluetooth_remote import BluetoothRemote, EV_KEY, INPUT_EVENT  # noqa: E402


class BluetoothRemoteTests(unittest.TestCase):
    def test_press_dispatches_once_while_release_and_repeat_are_ignored(self) -> None:
        actions: list[str] = []
        remote = BluetoothRemote({}, lambda: actions.append("next"), lambda: actions.append("hold"), autostart=False)

        remote._handle_event(EV_KEY, 34, 1)
        remote._handle_event(EV_KEY, 34, 2)
        remote._handle_event(EV_KEY, 34, 0)
        remote._handle_event(EV_KEY, 36, 1)
        remote._handle_event(EV_KEY, 35, 1)

        self.assertEqual(["next", "hold"], actions)
        self.assertEqual(1, remote.status()["nextPresses"])
        self.assertEqual(1, remote.status()["holdPresses"])

    def test_hotplug_disconnect_and_reconnect(self) -> None:
        actions: list[str] = []
        descriptors: list[int] = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sysfs = root / "sys"
            inputs = root / "input"
            sysfs.mkdir()
            inputs.mkdir()
            remote = BluetoothRemote(
                {},
                lambda: actions.append("next"),
                lambda: actions.append("hold"),
                sysfs_root=sysfs,
                input_root=inputs,
                scan_interval=0.05,
            )
            try:
                first_read, first_write = os.pipe()
                descriptors.extend((first_read, first_write))
                self._attach_pipe(sysfs, inputs, "event4", first_read)
                os.write(first_write, INPUT_EVENT.pack(0, 0, EV_KEY, 34, 1))
                self._wait_for(lambda: actions == ["next"])

                (sysfs / "event4" / "device" / "name").unlink()
                (inputs / "event4").unlink()
                os.close(first_write)
                descriptors.remove(first_write)
                self._wait_for(lambda: not remote.status()["connected"])

                second_read, second_write = os.pipe()
                descriptors.extend((second_read, second_write))
                self._attach_pipe(sysfs, inputs, "event7", second_read)
                os.write(second_write, INPUT_EVENT.pack(0, 0, EV_KEY, 36, 1))
                self._wait_for(lambda: actions == ["next", "hold"])
                self.assertTrue(remote.status()["connected"])
                self.assertEqual(str(inputs / "event7"), remote.status()["devicePath"])
            finally:
                remote.close()
                for descriptor in descriptors:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass

    def test_all_mapped_buttons_deliver_edges_once_without_scoreboard_actions(self):
        from scoreboard_device.bluetooth_remote import DEFAULT_KEY_CODES
        edges, legacy = [], []
        remote = BluetoothRemote({}, lambda: legacy.append('a'), lambda: legacy.append('b'),
            on_input=lambda name, down: edges.append((name, down)) or True, autostart=False)
        for name, code in DEFAULT_KEY_CODES.items():
            for value in (1, 1, 2, 0, 0): remote._handle_event(EV_KEY, code, value)
        self.assertEqual([(name, down) for name in DEFAULT_KEY_CODES for down in (True, False)], edges)
        self.assertEqual([], legacy)
        self.assertEqual([], remote.status()['heldButtons'])
        self.assertTrue(all(v == 1 for v in remote.status()['buttonPresses'].values()))

    def test_disconnect_and_lost_events_clear_held_input(self):
        losses, edges = [], []
        remote = BluetoothRemote({}, lambda: None, lambda: None,
            on_input=lambda n, p: edges.append((n,p)) or True,
            on_disconnect=lambda: losses.append(True), autostart=False)
        remote._set_connection(Path('/dev/input/event2'))
        remote._handle_event(EV_KEY, 46, 1)
        remote._set_connection(None)
        self.assertEqual([], remote.status()['heldButtons']); self.assertEqual(1, len(losses))
        remote._handle_event(EV_KEY, 32, 1)
        remote._handle_event(0, 3, 0)  # SYN_DROPPED
        remote._handle_event(EV_KEY, 18, 1)
        self.assertEqual([], remote.status()['heldButtons']); self.assertEqual(2, len(edges))
        remote._handle_event(0, 0, 0)  # SYN_REPORT
        remote._handle_event(EV_KEY, 18, 1)
        self.assertEqual(['left'], remote.status()['heldButtons'])

    def _attach_pipe(self, sysfs: Path, inputs: Path, event_name: str, descriptor: int) -> None:
        device = sysfs / event_name / "device"
        device.mkdir(parents=True)
        (device / "name").write_text("8BitDo Zero 2 gamepad Keyboard\n", encoding="utf-8")
        (inputs / event_name).symlink_to(f"/dev/fd/{descriptor}")

    def _wait_for(self, condition: Callable[[], bool], timeout: float = 2.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(0.02)
        self.fail("condition was not met before timeout")


if __name__ == "__main__":
    unittest.main()
