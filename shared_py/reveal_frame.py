from __future__ import annotations

from shared_py.bdf import BdfFont, measure_text
from shared_py.renderer import BLACK, WHITE, Clip, PixelBuffer, Rgba, _draw_text


def _wrap_to_width(font: BdfFont, text: str, max_width: int) -> list[str]:
    """Greedy word-wrap so staged reveal text fits the panel instead of
    being clipped or running off-screen."""
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if measure_text(font, candidate) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def create_reveal_text_frame(
    width: int,
    height: int,
    lines: list[str],
    font: BdfFont,
    *,
    color: Rgba = WHITE,
    background: Rgba = BLACK,
) -> PixelBuffer:
    """Renders staged, data-driven reveal text centered on the panel,
    word-wrapping any line too wide to fit. Used for both the reveal's own
    lines and (via the caller) any other short staged message."""
    frame = PixelBuffer(width, height, background)
    max_width = max(1, width - 4)
    wrapped = [wrapped_line for source in lines for wrapped_line in _wrap_to_width(font, source, max_width)]
    line_height = font.height + 2
    block_height = len(wrapped) * line_height
    start_y = max(0, (height - block_height) // 2)
    clip = Clip(0, 0, width, height)
    for index, line in enumerate(wrapped):
        _draw_text(frame, font, line, width // 2, start_y + index * line_height, color, align="center", outer_clip=clip)
    return frame
