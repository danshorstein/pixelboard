from __future__ import annotations

from pathlib import Path
import hashlib
from typing import Any, Mapping, Protocol

from shared_py.png import encode_rgba_png
from shared_py.renderer import PixelBuffer


class DisplayOutput(Protocol):
    kind: str

    def show(self, frame: PixelBuffer) -> None: ...
    def blank(self) -> None: ...
    def set_brightness(self, percent: int) -> None: ...
    def close(self) -> None: ...


class SimulatorOutput:
    kind = "simulator"

    def __init__(self, state_dir: Path, width: int, height: int) -> None:
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.width = width
        self.height = height
        self.brightness = 100
        self.last_frame: PixelBuffer | None = None
        self.last_hash: str | None = None

    def show(self, frame: PixelBuffer) -> None:
        self.last_frame = frame
        digest = hashlib.sha256(frame.data).hexdigest()
        if digest == self.last_hash:
            return
        self.last_hash = digest
        temporary = self.state_dir / "latest.tmp"
        temporary.write_bytes(encode_rgba_png(frame.width, frame.height, frame.data))
        temporary.replace(self.state_dir / "latest.png")

    def blank(self) -> None:
        frame = PixelBuffer(self.width, self.height)
        self.show(frame)

    def set_brightness(self, percent: int) -> None:
        self.brightness = max(1, min(100, int(percent)))

    def close(self) -> None:
        return


class Hub75Output:
    kind = "hub75"

    def __init__(self, profile: Mapping[str, Any], config: Mapping[str, Any]) -> None:
        try:
            from rgbmatrix import RGBMatrix, RGBMatrixOptions
        except ImportError as error:
            raise RuntimeError("rgbmatrix binding is not installed; run install.sh on the Raspberry Pi") from error
        from PIL import Image
        self._Image = Image
        logical = profile["logical"]
        panel = config.get("panel", {})
        options = RGBMatrixOptions()
        # hzeller's driver drops the process to uid `daemon` right after init by
        # default. That strips the root privileges the local dashboard relies on
        # for git update checks (reading /home/<owner>/.git-credentials, mode 600)
        # and for scripts/update-device.sh (chown, systemctl restart). Keep root
        # unless a device explicitly opts back into privilege dropping.
        options.drop_privileges = bool(panel.get("dropPrivileges", False))
        options.rows = int(panel.get("rows", 32))
        options.cols = int(panel.get("cols", 64))
        options.chain_length = int(panel.get("chainLength", max(1, int(logical["width"]) // options.cols)))
        options.parallel = int(panel.get("parallel", 1))
        options.hardware_mapping = str(panel.get("hardwareMapping", "adafruit-hat"))
        options.brightness = int(config.get("brightness", 35))
        options.gpio_slowdown = int(panel.get("gpioSlowdown", 1))
        if panel.get("panelType"):
            options.panel_type = str(panel["panelType"])
        if panel.get("multiplexing") is not None:
            options.multiplexing = int(panel["multiplexing"])
        # Refresh / PWM tuning to keep the panel visually solid. All optional:
        # unset keys leave the library defaults untouched.
        if panel.get("pwmBits") is not None:
            options.pwm_bits = int(panel["pwmBits"])
        if panel.get("pwmLsbNanoseconds") is not None:
            options.pwm_lsb_nanoseconds = int(panel["pwmLsbNanoseconds"])
        if panel.get("limitRefreshRateHz") is not None:
            options.limit_refresh_rate_hz = int(panel["limitRefreshRateHz"])
        if panel.get("showRefreshRate"):
            options.show_refresh_rate = True
        self.matrix = RGBMatrix(options=options)
        self.canvas = self.matrix.CreateFrameCanvas()
        self.width = int(logical["width"])
        self.height = int(logical["height"])

    def show(self, frame: PixelBuffer) -> None:
        if frame.width != self.width or frame.height != self.height:
            raise ValueError("Rendered frame does not match the physical matrix geometry")
        # One bulk blit instead of width*height SetPixel FFI calls per frame:
        # keeps the render thread's per-frame CPU burst small so it doesn't
        # steal time from the rgbmatrix refresh thread (visible as flicker).
        image = self._Image.frombytes("RGBA", (frame.width, frame.height), bytes(frame.data)).convert("RGB")
        self.canvas.SetImage(image)
        self.canvas = self.matrix.SwapOnVSync(self.canvas)

    def blank(self) -> None:
        self.matrix.Clear()

    def set_brightness(self, percent: int) -> None:
        self.matrix.brightness = max(1, min(100, int(percent)))

    def close(self) -> None:
        self.blank()


def create_output(kind: str, root: Path, profile: Mapping[str, Any], config: Mapping[str, Any]) -> DisplayOutput:
    logical = profile["logical"]
    if kind == "simulator":
        return SimulatorOutput(root / "state", int(logical["width"]), int(logical["height"]))
    if kind == "hub75":
        return Hub75Output(profile, config)
    raise ValueError(f"Unsupported output: {kind}")
