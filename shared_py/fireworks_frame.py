from __future__ import annotations

import math

from shared_py.renderer import PixelBuffer, Rgba


def _js_round(value: float) -> int:
    """Matches JS Math.round (half rounds toward +Infinity), unlike Python's
    round() (half rounds to even) — needed for exact TS/Python parity here."""
    return math.floor(value + 0.5)

# Mirrors frontend/src/fireworks.ts exactly (same constants, same math) so the
# browser and device renderers produce byte-identical celebration frames.
COLORS: tuple[Rgba, ...] = (
    (255, 82, 104, 255),
    (255, 208, 71, 255),
    (88, 214, 141, 255),
    (127, 221, 255, 255),
    (190, 121, 255, 255),
)


def _burst(frame: PixelBuffer, center_x: int, center_y: int, radius: float, color: Rgba) -> None:
    for ray in range(18):
        angle = (math.pi * 2 * ray) / 18
        length = radius * (0.68 + ((ray * 7) % 5) / 10)
        point = 1
        while point <= length:
            if point < length * 0.35 or point % 2 == 0:
                fade = 1 - point / (length + 2)
                x = _js_round(center_x + math.cos(angle) * point)
                y = _js_round(center_y + math.sin(angle) * point + (point * point) / 120)
                spark: Rgba = (color[0], color[1], color[2], _js_round(255 * max(0.25, fade)))
                frame.blend_pixel(x, y, spark)
                frame.blend_pixel(x + 1, y, spark)
                if point < length * 0.75:
                    frame.blend_pixel(x, y + 1, spark)
            point += 1
    frame.set_pixel(center_x, center_y, (255, 255, 255, 255))


def create_fireworks_frame(width: int, height: int, elapsed_ms: float) -> PixelBuffer:
    """A deliberately low-resolution celebration frame for the physical 128x32 display."""
    frame = PixelBuffer(width, height, (5, 12, 34, 255))
    frame.fill_rect(0, height - 5, width, 5, (11, 18, 42, 255))
    beat = (elapsed_ms % 3_600) / 3_600
    centers = (
        (width * 0.22, height * 0.43, 0.0),
        (width * 0.52, height * 0.26, 0.31),
        (width * 0.79, height * 0.49, 0.62),
    )

    for index, (x, y, offset) in enumerate(centers):
        phase = (beat + offset) % 1
        if phase < 0.18:
            # drawLine truncates internally (matching PixelBuffer.set_pixel's
            # int()); pass the raw floats through exactly as the TS source
            # does rather than rounding them first.
            frame.draw_line(x, height - 2, x + (index - 1) * 5, y, (215, 226, 255, 210))
            continue
        if phase < 0.82:
            _burst(frame, _js_round(x), _js_round(y), 4 + phase * min(width, height) * 0.52, COLORS[index % len(COLORS)])

    for star in range(max(12, width // 6)):
        x = (star * 37 + 11) % width
        y = (star * 13 + 5) % max(1, height - 4)
        if (star + math.floor(elapsed_ms / 220)) % 3 == 0:
            frame.set_pixel(x, y, (190, 220, 255, 255))
            frame.set_pixel(x + 1, y, (120, 170, 255, 255))
    return frame
