"""Big League pictures, pixel-exact counterpart of shared_ts/arcade_bigleague_frame.ts.

Three views: behind the batter for pitches, a flattened top-down field once
the ball is in play, and a line score between half innings.
"""
from __future__ import annotations

import math

from shared_py.arcade_bigleague import FENCE, BASES, INNINGS, PITCHES, WINDUP_MS, WAIT_MS, base_point, meter_value
from shared_py.renderer import PixelBuffer

WHITE = (221, 240, 237, 255)
TEAL = (58, 226, 180, 255)
GOLD = (255, 201, 58, 255)
RED = (255, 70, 88, 255)
GREEN = (80, 220, 110, 255)
DIM = (90, 140, 130, 255)
FAINT = (25, 61, 56, 255)
OFF = (30, 34, 34, 255)
BLACK = (0, 0, 0, 255)
GRASS = (0, 46, 14, 255)
INFIELD = (0, 64, 20, 255)
FOUL = (0, 18, 6, 255)
DIRT = (74, 40, 14, 255)
WALL = (0, 80, 36, 255)
FENCE_TOP = (70, 210, 100, 255)
CHALK = (150, 160, 150, 255)
SKIN = (230, 170, 120, 255)
BAT = (200, 140, 70, 255)
PANTS = (170, 180, 180, 255)
SHADOW = (0, 20, 6, 255)
# Batter seen from behind, standing left of the plate. T team colour, S skin, W pants, K bat.
STANCE = ('      K', '     K ', '  TTK  ', '  TTT  ', '   S   ', ' TTTTT ', ' TTTSS ', '  TTT  ',
          '  WWW  ', '  W W  ', '  W W  ', ' WW WW ')
SWUNG = ('       ', '       ', '  TT   ', '  TTT  ', '   S   ', ' TTTTSS', ' TTTT  ', '  TTT  ',
         '  WWW  ', '  W W  ', '  W W  ', ' WW WW ')
BATTER_X, BATTER_Y = 49, 18
# Infielders and outfielders as dots in the batting view.
DOTS = ((97, 19), (79, 14), (49, 14), (31, 19), (22, 11), (64, 10), (106, 11))
BASE_DOTS = ((101, 20), (66, 11), (25, 20))  # where runners stand in the batting view


def _rhombus(b: PixelBuffer, top: int, mid: int, bottom: int, half: int, color) -> None:
    for y in range(top, bottom + 1):
        w = (y - top) * half // (mid - top) if y <= mid else (bottom - y) * half // (bottom - mid)
        b.fill_rect(64 - w, y, 2 * w + 1, 1, color)


def _sprite(b: PixelBuffer, rows, x0: int, y0: int, team) -> None:
    colors = {'T': team, 'S': SKIN, 'W': PANTS, 'K': BAT}
    for row, cells in enumerate(rows):
        for col, cell in enumerate(cells):
            if cell != ' ':
                b.set_pixel(x0 + col, y0 + row, colors[cell])


def _ball(b: PixelBuffer, x: int, y: int, size: int) -> None:
    if size == 1:
        b.set_pixel(x, y, WHITE)
    elif size == 2:
        b.fill_rect(x, y, 2, 2, WHITE)
    else:
        b.fill_rect(x - 1, y, 3, 1, WHITE)
        b.fill_rect(x, y - 1, 1, 3, WHITE)


def _dots(b: PixelBuffer, text, label: str, y: int, lit: int, total: int, color) -> None:
    text(label, 2, y, DIM)
    for i in range(total):
        b.fill_rect(8 + i * 3, y + 2, 2, 2, color if i < lit else OFF)


_CACHE: dict[str, bytes] = {}  # static backgrounds, drawn once


def _cached(b: PixelBuffer, key: str, draw) -> None:
    if key not in _CACHE:
        draw(b)
        _CACHE[key] = bytes(b.data)
    b.data[:] = _CACHE[key]


def _ballpark(b: PixelBuffer) -> None:
    b.fill_rect(0, 7, 128, 3, WALL)
    b.fill_rect(0, 7, 128, 1, FENCE_TOP)
    for y in range(10, 32):
        w = min(64, (31 - y) * 64 // 17)
        b.fill_rect(0, y, 128, 1, FOUL)
        b.fill_rect(64 - w, y, 2 * w + 1, 1, GRASS)
    _rhombus(b, 10, 21, 31, 38, DIRT)
    _rhombus(b, 15, 21, 28, 26, INFIELD)
    for y in range(10, 32):
        w = min(64, (31 - y) * 64 // 17)
        if w < 64:
            b.set_pixel(64 - w, y, CHALK)
            b.set_pixel(64 + w, y, CHALK)
    b.fill_rect(62, 18, 5, 2, DIRT)
    for x, y in ((99, 21), (64, 12), (28, 21)):
        b.fill_rect(x - 1, y, 2, 1, WHITE)
    b.fill_rect(62, 29, 5, 1, WHITE)
    b.fill_rect(63, 30, 3, 1, WHITE)


def _batting(b: PixelBuffer, s: dict, text) -> None:
    offense, defense = (TEAL, GOLD) if s['half'] == 0 else (GOLD, TEAL)
    _cached(b, 'ballpark', _ballpark)
    for x, y in DOTS:
        b.fill_rect(x, y, 1, 2, defense)
    for runner in s['runners']:
        k = runner[1] // (90 * 64)
        if 1 <= k <= 3:
            x, y = BASE_DOTS[k - 1]
            b.fill_rect(x, y - 1, 2, 3, offense)
    # Pitcher on the mound; the throwing arm goes up during the windup.
    windup = (s['phase'] == 'wait' and s['timer'] >= WAIT_MS - WINDUP_MS) or s['phase'] == 'meter'
    b.set_pixel(64, 13, SKIN)
    b.fill_rect(63, 14, 3, 2, defense)
    b.set_pixel(63, 16, PANTS)
    b.set_pixel(65, 16, PANTS)
    if windup:
        b.set_pixel(66, 12, defense)
        b.set_pixel(66, 13, defense)
    # Strike zone, then the cursor (where YOU swing or aim).
    b.stroke_rect(58, 17, 12, 9, FAINT)
    if s['half'] == 0 or s['phase'] in ('aim', 'meter'):
        cx, cy = 58 + 4 * (s['aimCol'] + 1), 17 + 3 * (s['aimRow'] + 1)
        for dx, dy in ((0, 0), (3, 0), (0, 2), (3, 2)):
            b.set_pixel(cx + dx, cy + dy, TEAL)
    swinging = s['swing'] >= 0 and s['phase'] in ('pitch', 'result')
    _sprite(b, SWUNG if swinging else STANCE, BATTER_X, BATTER_Y, offense)
    if swinging:
        if s['swing'] < 160:
            b.draw_line(BATTER_X + 6, BATTER_Y + 5, BATTER_X + 17, BATTER_Y + 5, BAT)
        else:
            b.draw_line(BATTER_X + 2, BATTER_Y + 4, BATTER_X - 3, BATTER_Y + 1, BAT)
    if s['phase'] == 'pitch':
        p = s['pitchT'] * 1024 // s['pitchMs']
        if p <= 1100:
            q = p * p // 1024
            ex, ey = 64 + 4 * s['pitchCol'], 21 + 3 * s['pitchRow']
            drop = (3 * (1024 - q)) // 1024 if s['pitchType'] == 1 and q < 1024 else 0
            _ball(b, 64 + (ex - 64) * q // 1024, 15 + (ey - 15) * q // 1024 - drop, 1 if p < 350 else 2 if p < 750 else 3)
    you, pi = f"YOU {s['you']}", f"PI {s['pi']}"
    text(you, 1, 0, TEAL)
    text(pi, 128 - len(pi) * 4, 0, GOLD)
    inning = f"{'TOP' if s['half'] == 0 else 'BOT'} {s['inning']}"
    text(inning, 64 - len(inning) * 2, 0, WHITE)
    _dots(b, text, 'B', 11, s['balls'], 3, GREEN)
    _dots(b, text, 'S', 18, s['strikes'], 2, RED)
    _dots(b, text, 'O', 25, s['outs'], 2, RED)
    if s['half'] == 1 and s['phase'] in ('aim', 'meter', 'pitch'):
        name = f"<{PITCHES[s['pitchType']][0]}>"
        text(name, 110 - len(name) * 2, 26, WHITE)
        b.stroke_rect(95, 20, 31, 4, FAINT)
        b.fill_rect(110, 19, 1, 6, GOLD)
        if s['phase'] == 'aim':
            text('A', 108, 13, GOLD)
        else:
            m = meter_value(s['timer']) if s['phase'] == 'meter' else s['meter']
            if m >= 0:
                b.fill_rect(96 + m * 28 // 100, 21, 2, 2, WHITE)
    if s['phase'] == 'result' and s['call']:
        w = len(s['call']) * 4
        b.fill_rect(62 - w // 2, 8, w + 4, 8, BLACK)
        text(s['call'], 64 - w // 2, 9, GOLD if s['call'] in ('WALK', 'STRIKEOUT!') else WHITE)


def project(x: int, y: int) -> tuple[int, int]:
    """Field position (1/64 ft) to the flattened top-down view."""
    return 64 + (x * 27 + 3200) // 6400, 30 - (y * 85 + 32000) // 64000


def _diamond(b: PixelBuffer) -> None:
    for sx in range(128):
        wx = abs(sx - 64) * 6400 // 27
        fence = math.isqrt(max(0, FENCE * FENCE - wx * wx))
        top = 30 - (fence * 85 + 32000) // 64000
        line = 30 - (wx * 85 + 32000) // 64000
        b.fill_rect(sx, top, 1, line - top + 1, GRASS)
        b.fill_rect(sx, top - 1, 1, 1, FENCE_TOP)
        b.set_pixel(sx, line, CHALK)
    points = [project(*p) for p in BASES]
    for i in range(4):
        (ax, ay), (bx, by) = points[i], points[(i + 1) % 4]
        b.draw_line(ax, ay, bx, by, DIRT)
    b.fill_rect(63, 25, 2, 1, DIRT)
    for x, y in points:
        b.fill_rect(x, y, 2, 1, WHITE)


def _field(b: PixelBuffer, s: dict, text) -> None:
    offense, defense = (TEAL, GOLD) if s['half'] == 0 else (GOLD, TEAL)
    _cached(b, 'field', _diamond)
    for fx, fy in s['fielders']:
        x, y = project(fx, fy)
        b.fill_rect(x - 1, y - 1, 2, 2, defense)
    for runner in s['runners']:
        x, y = project(*base_point(runner[0]))
        b.fill_rect(x - 1, y - 2, 2, 3, offense)
    bx, by, bz = s['ball'][:3]
    x, y = project(bx, by)
    lift = bz // 512
    if lift > 0:
        b.set_pixel(x, y, SHADOW)
    b.set_pixel(x, y - lift, WHITE)
    for i in range(2):
        b.fill_rect(121 + i * 3, 1, 2, 2, RED if i < s['outs'] else OFF)
    if s['phase'] == 'result' and s['call']:
        w = len(s['call']) * 4
        b.fill_rect(62 - w // 2, 0, w + 4, 7, BLACK)
        text(s['call'], 64 - w // 2, 1, GOLD)


def _line_score(b: PixelBuffer, s: dict, text) -> None:
    innings = max(INNINGS, len(s['lineYou']))
    for i in range(innings):
        text(str(i + 1), 26 + i * 9, 1, DIM)
    total_x = 30 + innings * 9
    text('R', total_x, 1, GOLD)
    for row, (name, line, total, color) in enumerate((('YOU', s['lineYou'], s['you'], TEAL), ('PI', s['linePi'], s['pi'], GOLD))):
        y = 9 + row * 8
        text(name, 2, y, color)
        for i, runs in enumerate(line):
            text(str(runs), 26 + i * 9 - (len(str(runs)) - 1) * 4, y, WHITE)
        text(str(total), total_x - (len(str(total)) - 1) * 4, y, GOLD)
    b.draw_line(0, 7, 127, 7, FAINT)
    note = f"TOP {s['inning']}: YOU BAT" if s['half'] == 0 else f"BOTTOM {s['inning']}: YOU PITCH"
    text(note, 64 - len(note) * 2, 25, GOLD)


def bigleague_frame(b: PixelBuffer, s: dict, text) -> None:
    if s['phase'] == 'switch' and s['status'] == 'running':
        _line_score(b, s, text)
    elif s['view'] == 'field' and s['phase'] in ('play', 'result'):
        _field(b, s, text)
    else:
        _batting(b, s, text)
