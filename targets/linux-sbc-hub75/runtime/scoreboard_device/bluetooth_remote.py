from __future__ import annotations

import logging
import os
import select
import struct
import threading
from pathlib import Path
from typing import Any, Callable, Mapping


LOGGER = logging.getLogger("scoreboard-device")
EV_KEY = 1
KEY_PRESSED = 1
DEFAULT_KEY_CODES = {"up": 46, "down": 32, "left": 18, "right": 33, "a": 34, "b": 36, "x": 35, "y": 23, "l": 37, "r": 50, "select": 49, "start": 24}
INPUT_EVENT = struct.Struct("@llHHI")


class BluetoothRemote:
    """Reads a paired Bluetooth keyboard remote from Linux evdev."""

    def __init__(
        self,
        config: Mapping[str, Any],
        on_next: Callable[[], None],
        on_hold: Callable[[], None],
        *,
        on_input: Callable[[str, bool], bool] | None = None,
        on_disconnect: Callable[[], None] | None = None,
        sysfs_root: Path = Path("/sys/class/input"),
        input_root: Path = Path("/dev/input"),
        scan_interval: float = 1.0,
        autostart: bool = True,
    ) -> None:
        self.enabled = config.get("enabled", True) is True
        self.device_name = str(config.get("deviceName", "8BitDo Zero 2 gamepad Keyboard"))
        self.next_key_code = int(config.get("nextKeyCode", 34))  # A in the Zero 2 keyboard profile (KEY_G)
        self.hold_key_code = int(config.get("holdKeyCode", 36))  # B in the Zero 2 keyboard profile (KEY_J)
        self.key_codes = {**DEFAULT_KEY_CODES, **dict(config.get("keyCodes") or {})}
        self.key_codes['a'] = int(config.get('nextKeyCode', self.key_codes['a']))
        self.key_codes['b'] = int(config.get('holdKeyCode', self.key_codes['b']))
        self._names = {int(code): name for name, code in self.key_codes.items()}
        if len(self._names) != len(self.key_codes):
            raise ValueError('Remote keycodes must be unique')
        self._on_input = on_input
        self._on_disconnect = on_disconnect
        self.held_buttons: set[str] = set()
        self.button_presses = {name: 0 for name in self.key_codes}
        self.last_input: dict | None = None
        self._sync_lost = False
        self._on_next = on_next
        self._on_hold = on_hold
        self._sysfs_root = sysfs_root
        self._input_root = input_root
        self._scan_interval = max(0.05, float(scan_interval))
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.connected = False
        self.device_path: str | None = None
        self.error: str | None = None
        self.next_presses = 0
        self.hold_presses = 0

        if self.enabled and autostart:
            self._thread = threading.Thread(target=self._run, name="bluetooth-remote", daemon=True)
            self._thread.start()

    def _find_device(self) -> Path | None:
        try:
            candidates = sorted(self._sysfs_root.glob("event*"), key=lambda path: path.name)
        except OSError as error:
            with self._lock:
                self.error = str(error)
            return None
        for candidate in candidates:
            try:
                name = (candidate / "device" / "name").read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if name == self.device_name:
                return self._input_root / candidate.name
        return None

    def _clear_input(self) -> None:
        with self._lock:
            self.held_buttons.clear()
        if self._on_disconnect is not None:
            self._on_disconnect()

    def _set_connection(self, path: Path | None, error: str | None = None) -> None:
        with self._lock:
            lost = path is None and (self.connected or bool(self.held_buttons))
            self.connected = path is not None
            self.device_path = str(path) if path is not None else None
            self.error = error
        if lost:
            self._clear_input()

    def _handle_event(self, event_type: int, code: int, value: int) -> None:
        # SYN_DROPPED means the kernel lost events, including possible releases.
        if event_type == 0 and code == 3:
            self._sync_lost = True
            self._clear_input()
            return
        if self._sync_lost:
            if event_type == 0 and code == 0:
                self._sync_lost = False
            return
        if event_type != EV_KEY or value not in (0, 1):
            return
        name = self._names.get(code)
        if name is None:
            return
        pressed = value == 1
        with self._lock:
            if pressed == (name in self.held_buttons):
                return
            if pressed:
                self.held_buttons.add(name)
                self.button_presses[name] += 1
            else:
                self.held_buttons.discard(name)
            self.last_input = {'button': name, 'pressed': pressed}
        try:
            consumed = self._on_input(name, pressed) if self._on_input is not None else False
            if pressed and not consumed:
                if name == 'a':
                    with self._lock:
                        self.next_presses += 1
                    self._on_next()
                elif name == 'b':
                    with self._lock:
                        self.hold_presses += 1
                    self._on_hold()
        except Exception:
            LOGGER.exception('Bluetooth remote callback failed')

    def _run(self) -> None:
        while not self._stop.is_set():
            path = self._find_device()
            if path is None:
                self._set_connection(None)
                self._stop.wait(self._scan_interval)
                continue

            descriptor: int | None = None
            try:
                descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                self._set_connection(path)
                LOGGER.info("Bluetooth remote connected device=%s", path)
                pending = b""
                while not self._stop.is_set():
                    readable, _, _ = select.select([descriptor], [], [], 0.5)
                    if not readable:
                        continue
                    payload = os.read(descriptor, INPUT_EVENT.size * 16)
                    if not payload:
                        raise OSError("input device disconnected")
                    pending += payload
                    while len(pending) >= INPUT_EVENT.size:
                        raw, pending = pending[: INPUT_EVENT.size], pending[INPUT_EVENT.size :]
                        _, _, event_type, code, value = INPUT_EVENT.unpack(raw)
                        self._handle_event(event_type, code, value)
            except OSError as error:
                if not self._stop.is_set():
                    LOGGER.warning("Bluetooth remote unavailable: %s", error)
                    self._set_connection(None, str(error))
            finally:
                if descriptor is not None:
                    os.close(descriptor)
                self._set_connection(None, self.error)
            self._stop.wait(self._scan_interval)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.enabled,
                "connected": self.connected,
                "deviceName": self.device_name,
                "devicePath": self.device_path,
                "error": self.error,
                "nextPresses": self.next_presses,
                "holdPresses": self.hold_presses,
                "heldButtons": sorted(self.held_buttons),
                "buttonPresses": dict(self.button_presses),
                "lastInput": dict(self.last_input) if self.last_input else None,
            }

    def close(self) -> None:
        self._stop.set()
        self._clear_input()
        if self._thread is not None:
            self._thread.join(timeout=2)
