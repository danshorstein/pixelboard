"""Pixel-exact counterpart of shared_ts/arcade_frame.ts."""
from __future__ import annotations

import math
from shared_py.arcade import FP, rider_gem, rider_ground
from shared_py.arcade_bigleague_frame import bigleague_frame
from shared_py.arcade_soccer_frame import soccer_frame
from shared_py.arcade_unicorn_frame import unicorn_frame
from shared_py.bdf import BdfFont
from shared_py.renderer import PixelBuffer

WHITE = (221, 240, 237, 255)
TEAL = (58, 226, 180, 255)
GOLD = (255, 201, 58, 255)
RED = (255, 70, 88, 255)
DIM = (25, 61, 56, 255)
NEON = (255, 40, 200, 255)
GLOW = (90, 12, 84, 255)
HILL = (14, 4, 34, 255)
MOON = (34, 18, 80, 255)
GEM = (150, 230, 255, 255)
# cos/sin of 16 headings (22.5 degree steps) scaled by 256, so rotation stays integer.
COS16 = (256, 237, 181, 98, 0, -98, -181, -237, -256, -237, -181, -98, 0, 98, 181, 237)
SIN16 = tuple(COS16[(i + 12) % 16] for i in range(16))
# Car art, drawn around the car centre: x forward, y down, last row on the ground.
# B body, G window, W wheel. Each entry is (rows, centre column).
CARS = (
    (('   BBG  ', ' BBBBBB ', 'BBBBBBBB', ' WW  WW '), 4),  # buggy
    (('   BBG   ', ' BBBBBBB ', 'BBBBBBBBB', ' WW   WW ', ' WW   WW '), 4),  # monster truck
    (('    BBBGG   ', ' BBBBBBBBBB ', 'BBBBBBBBBBBB', ' WW      WW '), 6),  # limo
    (('   G   ', '   BB  ', ' BBBBB ', 'WW   WW', 'WW   WW'), 3),  # bike
    (('   GGG   ', ' BBBBBBB ', 'BBBBBBBBB', ' W  W  W '), 4),  # ufo
)
CAR_COLORS = (TEAL, RED, GOLD, (140, 255, 60, 255), (70, 130, 255, 255))  # last colour index is rainbow
RAINBOW = len(CAR_COLORS)
# line, glow, hill fill (None leaves the sky showing), sky kind, sky colour
THEMES = (
    (NEON, GLOW, HILL, 'moon', MOON),
    ((255, 130, 40, 255), (110, 40, 10, 255), (40, 10, 24, 255), 'sun', (210, 90, 40, 255)),
    ((160, 230, 255, 255), (30, 70, 110, 255), (6, 18, 40, 255), 'snow', (120, 140, 170, 255)),
    ((255, 60, 20, 255), (120, 30, 0, 255), (36, 6, 0, 255), 'embers', (200, 80, 0, 255)),
    ((190, 150, 255, 255), (50, 30, 90, 255), None, 'stars', (150, 150, 190, 255)),
    ((60, 200, 80, 255), (200, 210, 200, 255), (4, 26, 8, 255), 'lights', (230, 230, 200, 255)),
)


def _disc(b: PixelBuffer, x: int, y: int, r: int, color) -> None:
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                b.set_pixel(x + dx, y + dy, color)


def _sky(b: PixelBuffer, kind: str, color, cam: int, t: int) -> None:
    if kind == 'moon':
        _disc(b, 104 - (cam // 24) % 150, 13, 5, color)
    elif kind == 'sun':
        _disc(b, 96 - (cam // 40) % 150, 9, 6, color)
    elif kind in ('snow', 'embers'):
        for k in range(14):
            fall = (k * 11 + t // (90 if kind == 'snow' else 70)) % 30
            b.set_pixel((k * 37 - cam // 2 - t // 150) % 128, 1 + fall if kind == 'snow' else 30 - fall, color)
    elif kind == 'stars':
        for k in range(20):
            if (k + t // 400) % 7:
                b.set_pixel((k * 53 + 7 - cam // 6) % 128, 2 + (k * 7) % 18, color)
    else:
        for tower in (20, 120):
            x = (tower - cam // 5) % 200 - 36
            b.draw_line(x, 7, x, 31, (60, 60, 60, 255))
            b.fill_rect(x - 1, 4, 3, 2, color)


def _rider(b: PixelBuffer, state: dict, text) -> None:
    seed, t = state['seed'], state['time']
    line, glow, fill, sky, sky_color = THEMES[state['theme']]
    gem_color = GOLD if state['gemValue'] > 1 else GEM
    cam = state['x'] // FP - 24
    cy = (state['y'] + FP // 2) // FP - 2
    lift = max(0, 9 - cy)  # Follow high jumps by lowering the world.
    _sky(b, sky, sky_color, cam, t)
    previous = None
    for sx in range(128):
        gy = (rider_ground(seed, (cam + sx) * FP) + FP // 2) // FP + lift
        if fill:
            b.fill_rect(sx, gy + 2, 1, 32 - gy - 2, fill)
        b.set_pixel(sx, gy + 1, glow)
        if previous is not None:
            b.draw_line(sx - 1, previous, sx, gy, line)
        previous = gy
    for i in range(max(state['nextGem'], (cam - 2) // 32), (cam + 130) // 32 + 1):
        gem = rider_gem(seed, i)
        if gem:
            gx, gy = gem['x'] - cam, gem['y'] + lift
            b.set_pixel(gx, gy - 1, gem_color)
            b.fill_rect(gx - 1, gy, 3, 1, gem_color)
            b.set_pixel(gx, gy + 1, gem_color)
            b.set_pixel(gx, gy, WHITE)
    heading = (((state['angle'] * 2 + 22) // 45) % 16 + 16) % 16
    c, s = COS16[heading], SIN16[heading]
    rows, centre = CARS[state['car']]
    for row, cells in enumerate(rows):
        dy = row - len(rows) + 2
        for col, cell in enumerate(cells):
            if cell == ' ':
                continue
            if cell == 'W':
                color = WHITE
            elif cell == 'G':
                color = GEM
            elif state['color'] == RAINBOW:
                color = CAR_COLORS[(col + t // 80) % RAINBOW]
            else:
                color = CAR_COLORS[state['color']]
            dx = col - centre
            b.set_pixel(24 + (dx * c - dy * s + 128) // 256, cy + lift + (dx * s + dy * c + 128) // 256, color)
    text(str(state['score']), 2, 0)
    gems = str(state['gems'])
    text(gems, 120 - len(gems) * 4, 0)
    if state['gemValue'] > 1:
        text(f"{state['gemValue']}X", 110 - len(gems) * 4, 0, GOLD)
    b.set_pixel(124, 1, gem_color)
    b.fill_rect(123, 2, 3, 1, gem_color)
    b.set_pixel(124, 3, gem_color)
    if state['bannerMs'] and state['status'] == 'running':
        text(state['banner'], (128 - len(state['banner']) * 4) // 2, 0, GOLD)


def arcade_frame(state: dict, font: BdfFont | None = None, paused: bool = False) -> PixelBuffer:
    b = PixelBuffer(128, 32)

    def text(s: str, x: int, y: int, color=WHITE, scale: int = 1) -> None:
        if font is None:
            return
        for c in s:
            g = font.glyphs.get(ord(c))
            if g is None:
                x += 4 * scale
                continue
            for row in range(g.height):
                for col in range(g.width):
                    if g.bitmap[row * g.width + col]:
                        px, py = g.x_offset + col, font.ascent - g.y_offset - g.height + row
                        if scale == 1:
                            b.set_pixel(x + px, y + py, color)
                        else:
                            b.fill_rect(x + px * scale, y + py * scale, scale, scale, color)
            x += g.advance_x * scale

    if state['kind'] == 'snake':
        text(f"SNAKE {state['score']}", 2, 0)
        b.stroke_rect(1, 5, 126, 26, DIM)
        for i, p in enumerate(state['body']):
            b.fill_rect(p['x'] * 2, p['y'] * 2, 2, 2, WHITE if i == 0 else TEAL)
        if state['food']:
            b.fill_rect(state['food']['x'] * 2, state['food']['y'] * 2, 2, 2, GOLD)
    elif state['kind'] == 'rider':
        _rider(b, state, text)
    elif state['kind'] == 'bigleague':
        bigleague_frame(b, state, text)
    elif state['kind'] == 'soccer':
        soccer_frame(b, state, text)
    elif state['kind'] == 'unicorn':
        unicorn_frame(b, state, text)
    elif state['kind'] == 'pong':
        text(f"YOU {state['playerScore']}", 2, 0)
        text(f"PI {state['computerScore']}", 104, 0)
        for y in range(7, 31, 4):
            b.fill_rect(63, y, 1, 2, DIM)
        b.draw_line(0, 5, 127, 5, DIM)
        b.draw_line(0, 31, 127, 31, DIM)
        b.fill_rect(3, state['player'], 2, 8, TEAL)
        b.fill_rect(123, state['computer'], 2, 8, GOLD)
        b.fill_rect(state['ball']['x'], state['ball']['y'], 2, 2, WHITE)
    else:
        text(f"PTS {state['score']}", 2, 0)
        text(f"P{min(10, state['pitches'] + (1 if state['phase'] == 'pitch' else 0))}/10", 43, 0)
        text(f"K {state['strikes']}", 106, 0)
        b.draw_line(0, 29, 127, 29, DIM)
        b.draw_line(24, 9, 24, 27, DIM)
        b.fill_rect(21, 27, 6, 2, WHITE)
        b.fill_rect(13, 17, 2, 2, TEAL)
        b.draw_line(14, 19, 15, 24, TEAL)
        b.draw_line(15, 24, 11, 28, TEAL)
        b.draw_line(15, 24, 18, 28, TEAL)
        b.fill_rect(112, 18, 2, 2, GOLD)
        b.draw_line(112, 20, 110, 27, GOLD)
        if state['phase'] == 'pitch':
            b.draw_line(16, 20, 20, 14, WHITE)
            b.fill_rect(state['x'], 21, 2, 2, WHITE)
        else:
            b.draw_line(16, 20, 25, 21, GOLD)
            if state['result'] not in ('MISS', 'FOUL'):
                t = state['flight'] / 1250
                x = 24 + t * 110
                y = 21 - math.sin(t * math.pi * .85) * (17 if state['result'] == 'HOME RUN!' else 12)
                b.fill_rect(x, y, 2, 2, WHITE)
                b.set_pixel(x - 3, y + 1, GOLD)
                b.set_pixel(x - 5, y + 2, DIM)
            text(state['result'], 39, 10, RED if state['result'] == 'MISS' else GOLD)
    if state['status'] != 'running' or paused:
        b.fill_rect(14, 10, 100, 13, (0, 0, 0, 255))
        b.stroke_rect(14, 10, 100, 13, DIM)
        message = 'PAUSED' if paused else 'PRESS START' if state['status'] == 'ready' else state['message']
        text(message, max(16, (128 - len(message) * 4) // 2), 14)
    return b
