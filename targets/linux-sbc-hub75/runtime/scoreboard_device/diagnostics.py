from __future__ import annotations

import asyncio
import json
import signal
import threading
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Mapping

from shared_py.renderer import PixelBuffer

from .buttons import PhysicalButtons
from .bluetooth_remote import BluetoothRemote
from .output import DisplayOutput, create_output


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def diagnostic_frames(width: int, height: int, panel_width: int = 64) -> list[tuple[str, PixelBuffer]]:
    frames = [
        ("red", PixelBuffer(width, height, (255, 0, 0, 255))),
        ("green", PixelBuffer(width, height, (0, 255, 0, 255))),
        ("blue", PixelBuffer(width, height, (0, 0, 255, 255))),
        ("white", PixelBuffer(width, height, (255, 255, 255, 255))),
    ]

    geometry = PixelBuffer(width, height)
    geometry.stroke_rect(0, 0, width, height, (255, 255, 255, 255))
    for x in range(panel_width, width, panel_width):
        geometry.draw_line(x - 1, 0, x - 1, height - 1, (255, 0, 255, 255))
        geometry.draw_line(x, 0, x, height - 1, (0, 255, 255, 255))
    marker = max(2, min(5, height // 6))
    geometry.fill_rect(1, 1, marker, marker, (255, 0, 0, 255))
    geometry.fill_rect(width - marker - 1, 1, marker, marker, (0, 255, 0, 255))
    geometry.fill_rect(1, height - marker - 1, marker, marker, (0, 0, 255, 255))
    geometry.fill_rect(width - marker - 1, height - marker - 1, marker, marker, (255, 255, 0, 255))
    frames.append(("geometry", geometry))

    checker = PixelBuffer(width, height)
    for y in range(height):
        for x in range(width):
            if (x + y) % 2 == 0:
                checker.set_pixel(x, y, (255, 255, 255, 255))
    frames.append(("checkerboard", checker))
    return frames


def _held_indicator(frame: PixelBuffer) -> PixelBuffer:
    result = PixelBuffer(frame.width, frame.height)
    result.data[:] = frame.data
    result.fill_rect(max(0, result.width - 4), 0, 4, 4, (255, 191, 0, 255))
    return result


class DiagnosticController:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.next_presses = 0
        self.hold_presses = 0
        self.advance_requested = False
        self.held = False

    def next(self) -> None:
        with self.lock:
            self.next_presses += 1
            self.advance_requested = True
            self.held = False

    def hold(self) -> None:
        with self.lock:
            self.hold_presses += 1
            self.held = not self.held

    def consume(self) -> tuple[bool, bool]:
        with self.lock:
            advance = self.advance_requested
            self.advance_requested = False
            return advance, self.held

    def report(
        self,
        *,
        output: str,
        completed_cycles: int,
        buttons: PhysicalButtons,
        bluetooth_remote: Mapping[str, Any],
        started: datetime,
        completed: datetime,
        duration_sec: float,
        project: Mapping[str, Any],
        profile: Mapping[str, Any],
        patterns: list[str],
    ) -> dict[str, Any]:
        with self.lock:
            return {
                "schemaVersion": "1.0",
                "status": "complete",
                "startedUtc": _utc_text(started),
                "completedUtc": _utc_text(completed),
                "durationSec": round(duration_sec, 3),
                "project": {
                    "id": str(project.get("id", "unknown")),
                    "version": int(project.get("meta", {}).get("version", 0)),
                },
                "profileId": str(profile.get("id", "unknown")),
                "output": output,
                "patterns": patterns,
                "completedCycles": completed_cycles,
                "buttons": {
                    "available": buttons.available,
                    "error": buttons.error,
                    "nextPresses": self.next_presses,
                    "holdPresses": self.hold_presses,
                },
                "bluetoothRemote": dict(bluetooth_remote),
                "operatorVerificationRequired": [
                    "All pixels and panel boundaries visually correct",
                    "Red, green, blue, and white channels visually correct",
                    "NEXT and HOLD counts match Bluetooth remote presses",
                    "No flicker, resets, odor, discoloration, or hot connectors",
                ],
            }


async def run_diagnostics(
    root: Path,
    *,
    output_kind: str | None = None,
    step_sec: float = 3,
    cycles: int = 0,
) -> dict[str, Any]:
    started = _utc_now()
    started_monotonic = monotonic()
    project: Mapping[str, Any] = _json(root / "config" / "project.json")
    profile: Mapping[str, Any] = _json(root / "config" / "device-profile.json")
    config: Mapping[str, Any] = _json(root / "config" / "runtime-config.json")
    logical = profile["logical"]
    panel_width = int(config.get("panel", {}).get("cols", 64))
    frames = diagnostic_frames(int(logical["width"]), int(logical["height"]), panel_width)
    controller = DiagnosticController()

    # Buttons are opened before the matrix driver, matching normal startup.
    buttons = PhysicalButtons(config.get("buttons", {}), controller.next, controller.hold)
    output: DisplayOutput = create_output(output_kind or str(config.get("output", "hub75")), root, profile, config)
    bluetooth_remote = BluetoothRemote(config.get("bluetoothRemote", {}), controller.next, controller.hold)
    output.set_brightness(min(20, int(config.get("brightness", 35))))
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, stop.set)
        except NotImplementedError:
            pass

    index = 0
    completed_cycles = 0
    last_held: bool | None = None
    deadline = 0.0
    bluetooth_remote_status: Mapping[str, Any] = {}
    try:
        while not stop.is_set() and (cycles <= 0 or completed_cycles < cycles):
            advance, held = controller.consume()
            if advance or deadline == 0.0 or (not held and monotonic() >= deadline):
                if deadline != 0.0:
                    index = (index + 1) % len(frames)
                    if index == 0:
                        completed_cycles += 1
                        if cycles > 0 and completed_cycles >= cycles:
                            break
                deadline = monotonic() + max(0.05, step_sec)
                last_held = None
            if last_held != held:
                frame = _held_indicator(frames[index][1]) if held else frames[index][1]
                output.show(frame)
                last_held = held
            await asyncio.sleep(0.025)
    finally:
        bluetooth_remote_status = bluetooth_remote.status()
        bluetooth_remote.close()
        output.blank()
        buttons.close()
        output.close()
    completed = _utc_now()
    report = controller.report(
        output=output.kind,
        completed_cycles=completed_cycles,
        buttons=buttons,
        bluetooth_remote=bluetooth_remote_status,
        started=started,
        completed=completed,
        duration_sec=monotonic() - started_monotonic,
        project=project,
        profile=profile,
        patterns=[name for name, _ in frames],
    )
    stamp = completed.strftime("%Y%m%dT%H%M%S%fZ")
    history_relative = Path("state") / "diagnostics" / "history" / f"diagnostic-{stamp}.json"
    latest_relative = Path("state") / "diagnostics" / "latest.json"
    report["reportFiles"] = {
        "latest": latest_relative.as_posix(),
        "history": history_relative.as_posix(),
    }
    _atomic_json(root / history_relative, report)
    _atomic_json(root / latest_relative, report)
    return report
