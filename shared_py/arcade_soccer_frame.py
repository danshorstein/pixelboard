"""Soccer picture, pixel-exact counterpart of shared_ts/arcade_soccer_frame.ts."""
from __future__ import annotations

from shared_py.arcade_soccer import FP
from shared_py.renderer import PixelBuffer

WHITE = (221, 240, 237, 255)
TEAL = (58, 226, 180, 255)
GOLD = (255, 201, 58, 255)
BLACK = (0, 0, 0, 255)
PITCH = (0, 40, 12, 255)
STRIPE = (0, 48, 15, 255)
LINE = (80, 120, 95, 255)
NET = (120, 130, 125, 255)
KEEPERS = ((40, 120, 255, 255), (255, 110, 40, 255))  # keepers wear a different colour


def _px(v: int) -> int:
    return (v + FP // 2) // FP


_PITCH: list[bytes] = []  # the empty pitch, drawn once


def _pitch(b: PixelBuffer) -> None:
    b.fill_rect(1, 6, 126, 26, PITCH)
    for x in range(9, 120, 16):
        b.fill_rect(x, 7, 8, 24, STRIPE)
    b.stroke_rect(1, 6, 126, 26, LINE)
    b.draw_line(64, 6, 64, 31, LINE)
    for dx, dy in ((-5, -1), (-5, 0), (-5, 1), (5, -1), (5, 0), (5, 1), (-1, -5), (0, -5), (1, -5),
                   (-1, 5), (0, 5), (1, 5), (-4, -3), (-3, -4), (4, -3), (3, -4), (-4, 3), (-3, 4), (4, 3), (3, 4)):
        b.set_pixel(64 + dx, 18 + dy, LINE)
    b.stroke_rect(1, 10, 12, 18, LINE)
    b.stroke_rect(115, 10, 12, 18, LINE)
    for x in (0, 127):
        b.fill_rect(x, 12, 1, 14, NET)
        b.set_pixel(x, 12, WHITE)
        b.set_pixel(x, 25, WHITE)
    b.fill_rect(0, 12, 2, 1, WHITE)
    b.fill_rect(126, 12, 2, 1, WHITE)
    b.fill_rect(0, 25, 2, 1, WHITE)
    b.fill_rect(126, 25, 2, 1, WHITE)


def soccer_frame(b: PixelBuffer, s: dict, text) -> None:
    if not _PITCH:
        _pitch(b)
        _PITCH.append(bytes(b.data))
    b.data[:] = _PITCH[0]
    for i, p in enumerate(s['players']):
        x, y = _px(p[0]), _px(p[1])
        color = KEEPERS[0 if i == 0 else 1] if i in (0, 3) else TEAL if i < 3 else GOLD
        b.fill_rect(x - 1, y - 2, 2, 3, color)
        if i == s['control'] and s['phase'] == 'play':
            b.fill_rect(x - 1, y - 4, 2, 1, WHITE)
    bx, by = _px(s['ball'][0]), _px(s['ball'][1])
    b.fill_rect(bx - 1, by - 1, 2, 2, WHITE)
    you, pi = f"YOU {s['you']}", f"PI {s['pi']}"
    text(you, 1, 0, TEAL)
    text(pi, 128 - len(pi) * 4, 0, GOLD)
    clock = 'GOLDEN GOAL' if s['golden'] else f"{s['clock'] // 60000}:{s['clock'] // 1000 % 60:02d}"
    text(clock, 64 - len(clock) * 2, 0, GOLD if s['golden'] else WHITE)
    if s['banner'] and s['status'] == 'running':
        w = len(s['banner']) * 4
        b.fill_rect(62 - w // 2, 13, w + 4, 8, BLACK)
        text(s['banner'], 64 - w // 2, 14, GOLD if s['banner'] != 'PI SCORES' else WHITE)
