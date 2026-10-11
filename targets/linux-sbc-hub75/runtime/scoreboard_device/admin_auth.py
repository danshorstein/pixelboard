from __future__ import annotations

import hmac
import os
import secrets
from pathlib import Path


class BroadcastPinStore:
    """Persistent six-digit household PIN for dashboard authorization."""

    def __init__(self, state_dir: Path) -> None:
        self.path = state_dir / "broadcast-pin"

    def get_or_create(self) -> str:
        try:
            pin = self.path.read_text(encoding="ascii").strip()
            if len(pin) == 6 and pin.isascii() and pin.isdecimal():
                return pin
        except FileNotFoundError:
            pass
        return self._write(self._new_pin())

    def rotate(self) -> str:
        previous = self.get_or_create()
        pin = self._new_pin()
        while pin == previous:
            pin = self._new_pin()
        return self._write(pin)

    @staticmethod
    def _new_pin() -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    def _write(self, pin: str) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="ascii") as stream:
            stream.write(pin + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.path)
        self.path.chmod(0o600)
        return pin

    @staticmethod
    def matches(expected: str, supplied: str | None) -> bool:
        return isinstance(supplied, str) and hmac.compare_digest(expected, supplied)
