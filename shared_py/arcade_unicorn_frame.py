"""Rainbow Toot Unicorn pictures, pixel-exact counterpart of shared_ts/arcade_unicorn_frame.ts.

Everything the original design said with sound is shown instead: speech
bubbles over the unicorn, comic action words in the world (TOOT!, SPLAT!),
a bottom ticker for longer lines, and full-screen scenes for the SIX SEVEN
dance, the star curse, the 3D robot, losing and winning. Nothing flashes the
whole panel: flashes are borders or text, at most a couple of times a second.
"""
from __future__ import annotations

from shared_py.arcade_unicorn import (CURSE_MS, DANCE_REPS_MS, FP, GROUND_ROW, SEG, STAR_MAX, UX, object_y,
                                      unicorn_object)
from shared_py.renderer import PixelBuffer

WHITE = (221, 240, 237, 255)
GOLD = (255, 201, 58, 255)
RED = (255, 70, 88, 255)
DARK_RED = (120, 20, 30, 255)
CYAN = (60, 220, 255, 255)
MAGENTA = (255, 60, 200, 255)
BLACK = (0, 0, 0, 255)
DIM = (90, 140, 130, 255)
OFF = (40, 30, 50, 255)
BODY = (235, 235, 255, 255)
LEG = (190, 170, 215, 255)
EYE = (70, 20, 110, 255)
HORN = (200, 180, 110, 255)
GRASS = (60, 200, 90, 255)
SOIL = (30, 10, 45, 255)
SPARKLE = (255, 120, 220, 255)
SKY_DOT = (50, 40, 90, 255)
AMBER = (255, 170, 30, 255)
STRIPE = (130, 70, 0, 255)
DOOR = (40, 15, 0, 255)
BEE = (255, 240, 60, 255)
STAR = (255, 230, 60, 255)
APPLE = (255, 40, 40, 255)
STEM = (60, 200, 60, 255)
SHELL = (150, 100, 50, 255)
FUSE = (255, 140, 0, 255)
ROBOT_RED, ROBOT_CYAN = (255, 40, 40, 255), (40, 230, 255, 255)
RAINBOW = ((255, 40, 40, 255), (255, 140, 0, 255), (255, 230, 0, 255), (40, 220, 60, 255), (40, 120, 255, 255),
           (170, 60, 255, 255))

# Unicorn 10 x 8 facing right. W body, M mane/tail (rainbow by row), H horn, E eye, L legs.
RUN = (('        H ', '      MWW ', '     MWWEW', 'M   MWWW  ', 'MMWWWWWW  ', ' MWWWWWW  ', '  L L  L L', '  L L  L L'),
       ('        H ', '      MWW ', '     MWWEW', 'M   MWWW  ', 'MMWWWWWW  ', ' MWWWWWW  ', '   LL   LL', '  L  L L L'))
FLY = ('        H ', '      MWW ', '     MWWEW', 'M   MWWW  ', 'MMWWWWWW  ', ' MWWWWWW  ', '  LL   LL ', '          ')
REAR = ('       H  ', '      MWW ', '     MWWEW', '    MWWLL ', '   MWWW L ', ' MWWWW    ', 'MM  L     ', '    L L   ')
ROBOT = ('      A   ', '    GGGGG ', '    GRGRG ', '    GGGGG ', ' GGGGGGG  ', ' GGGGGGG  ', '  G    G  ', '  G    G  ')
HIVE = ('  AAA  ', ' ASSSA ', ' AAAAA ', 'ASSSSSA', 'AAAAAAA', 'ASSDSSA', 'AAAAAAA')
SPLATTED = ('       ', '       ', '       ', '       ', ' A S A ', 'ASAASAA', 'AAASAAA')
STAR_ART = (('  Y  ', ' YYY ', 'YYYYY', ' YYY ', ' Y Y '), ('Y   Y', ' YYY ', ' YWY ', ' YYY ', 'Y   Y'))
APPLE_ART = ('  G ', ' RR ', 'RRRR', ' RR ')
BOMB_ART = ('   F ', ' SS  ', 'SSSS ', 'SSSS ', ' SS  ')
GLASSES_ART = ('WWWWWW', 'RRWWCC', 'RR  CC')
TROPHY = (' YYYYYYYYYY ', 'YYYYYYYYYYYY', 'Y YYYYYYYY Y', 'Y YYYYYYYY Y', ' YYYYYYYYYY ', '  YYYYYYYY  ',
          '   YYYYYY   ', '    YYYY    ', '     YY     ', '     YY     ', '   YYYYYY   ', '  YYYYYYYY  ')


def _art(b: PixelBuffer, rows, x: int, y: int, colors: dict) -> None:
    for r, cells in enumerate(rows):
        for c, cell in enumerate(cells):
            if cell != ' ':
                b.set_pixel(x + c, y + r, colors[cell])


def _anaglyph(b: PixelBuffer, rows, x: int, y: int) -> None:
    """3D-glasses look: a red copy one pixel left, a cyan copy one pixel right, white where they meet."""
    width = len(rows[0])
    for r, cells in enumerate(rows):
        for c in range(-1, width + 1):
            red = 0 <= c + 1 < width and cells[c + 1] != ' '
            cyan = 0 <= c - 1 < width and cells[c - 1] != ' '
            if red or cyan:
                b.set_pixel(x + c, y + r, BODY if red and cyan else ROBOT_RED if red else ROBOT_CYAN)


def _unicorn(b: PixelBuffer, s: dict, x: int, y: int, rows=None) -> None:
    t = s['time']
    if rows is None:
        ground = s['y'] >= 19 * FP
        rows = RUN[(t // 120) % 2] if ground else FLY
    hurt = s['invuln'] > 0 and (s['invuln'] // 100) % 2 == 0
    body = RED if hurt else BODY
    horn = HORN
    if 1 <= s['bands'] <= 2:
        horn = GOLD if (t // 150) % 2 else CYAN
    colors = {'W': body, 'H': horn, 'E': EYE, 'L': LEG}
    for r, cells in enumerate(rows):
        colors['M'] = RAINBOW[(r + t // 200) % 6]
        for c, cell in enumerate(cells):
            if cell != ' ':
                b.set_pixel(x + c, y + r, colors[cell])
    if s['dash'] > 0:
        b.draw_line(x + 9, y, x + 12, y - 1, GOLD)
    if s['invuln'] > 0:
        for k in range(2):
            a = (t // 80 + k * 4) % 8
            b.set_pixel(x + 2 + (a if a < 4 else 8 - a) * 2, y - 1 - (k + a) % 2, AMBER)


def _trail(b: PixelBuffer, x: int, y: int, length: int, t: int) -> None:
    """Rainbow toot exhaust behind the unicorn: three bands with sparks."""
    for k in range(length):
        for band in range(3):
            b.set_pixel(x - 1 - k, y + 3 + band, RAINBOW[(band * 2 + (k + t // 60) % 2) % 6])
    for k in range(3):
        spark = (t // 40 + k * 5) % 9
        b.set_pixel(x - length - 1 - spark, y + 2 + (k * 3 + t // 70) % 5, RAINBOW[(k * 2 + t // 90) % 6])


def _hive(b: PixelBuffer, x: int, y: int, t: int, splat: bool = False) -> None:
    _art(b, SPLATTED if splat else HIVE, x, y, {'A': AMBER, 'S': STRIPE, 'D': DOOR})
    if not splat:
        for k in range(2):
            a = (t // 90 + k * 5) % 10
            b.set_pixel(x + (a if a < 6 else 12 - a), y - 2 + (k + a) % 2, BEE)


def _object(b: PixelBuffer, obj: list, x: int, t: int) -> None:
    kind, y = obj[0], object_y(obj, t)
    if kind == 'hive':
        _hive(b, x, y, t)
    elif kind == 'star':
        _art(b, STAR_ART[(t // 250 + obj[1]) % 2], x, y, {'Y': STAR, 'W': WHITE})
    elif kind == 'apple':
        _art(b, APPLE_ART, x, y, {'R': APPLE, 'G': STEM})
    elif kind == 'bomb':
        _art(b, BOMB_ART, x, y, {'S': SHELL, 'F': WHITE if (t // 100) % 2 else FUSE})
    elif kind == 'band':
        a, c = (MAGENTA, CYAN) if (t // 200) % 2 else (CYAN, MAGENTA)
        for k in range(5):
            b.fill_rect(x + k, y, 1, 3, a if k % 2 else c)
    elif kind == 'glasses':
        _art(b, GLASSES_ART, x, y, {'W': WHITE, 'R': ROBOT_RED, 'C': ROBOT_CYAN})
    else:  # bee swarm: three bees buzzing around a point
        for k in range(3):
            a = (t // 70 + k * 3) % 6
            bx, by = x + (k * 2 + (a if a < 3 else 6 - a)) % 5, y + (k + a // 2) % 4
            b.set_pixel(bx, by, BEE)
            b.set_pixel(bx + 1, by, STRIPE)


def _ground(b: PixelBuffer, cam: int, oy: int) -> None:
    b.fill_rect(0, GROUND_ROW + oy, 128, 1, GRASS)
    b.fill_rect(0, GROUND_ROW + 1 + oy, 128, 4, SOIL)
    for k in range(10):
        x = (k * 13 - cam % 13 + 13) % 130
        b.set_pixel(x, GROUND_ROW + 2 + k % 3 + oy, SPARKLE)


def _sky(b: PixelBuffer, cam: int, t: int) -> None:
    for k in range(9):
        if (k + t // 500) % 4:
            b.set_pixel((k * 29 + 5 - cam // 4) % 128, 8 + (k * 7) % 15, SKY_DOT)


def _world(b: PixelBuffer, s: dict, oy: int = 0) -> None:
    t, cam = s['time'], s['cam'] // FP
    _sky(b, cam, t)
    for i in range(max(0, cam // SEG - 1), (cam + 128) // SEG + 1):
        for slot in (0, 1):
            obj = unicorn_object(s['seed'], i, slot)
            if obj and i * 2 + slot not in s['gone']:
                _object(b, [obj[0], obj[1], obj[2] + oy], obj[1] - cam, t)
    _ground(b, cam, oy)
    for shot in s['shots']:
        x, y = (shot[0] + FP // 2) // FP - cam, (shot[1] + FP // 2) // FP + oy
        b.fill_rect(x - 1, y - 1, 3, 3, SHELL)
        b.set_pixel(x, y - 2, FUSE)


def _boxed(b: PixelBuffer, text, word: str, x: int, y: int, color) -> None:
    b.fill_rect(x - 1, y, len(word) * 4 + 1, 7, BLACK)
    text(word, x, y, color)


def _bursts(b: PixelBuffer, s: dict, text) -> None:
    cam = s['cam'] // FP
    for word, wx, wy, age in s['fx']:
        x, y = wx - cam, wy - age // 140
        if word in ('TOOT!', 'PFFT!'):
            b.fill_rect(x - 1, y, len(word) * 4 + 1, 7, BLACK)
            for k, ch in enumerate(word):
                text(ch, x + k * 4, y, RAINBOW[(k + age // 80) % 6])
        elif word in ('BOOM!', 'SPLAT!'):
            _boxed(b, text, word, x, y, GOLD if (age // 100) % 2 else FUSE)
        elif word in ('OUCH!', 'BZZZ!'):
            _boxed(b, text, word, x, y, RED if (age // 120) % 2 == 0 else WHITE)
        else:
            _boxed(b, text, word, x, y, GOLD)


def _bubble(b: PixelBuffer, word: str, ms: int, text, x: int, y: int) -> None:
    """Speech bubble over the unicorn's head (beside it when there is no room above)."""
    w = len(word) * 4 + 3
    left = max(0, min(127 - w, x + 5 - w // 2))
    top = y - 11 + (1 if ms > 1400 else 0)
    beside = top < 6
    if beside:
        left, top = min(127 - w, x + 12), max(6, y - 1)
    if ms < 150:  # pops into two particles
        b.set_pixel(left + 2, top + 3, CYAN)
        b.set_pixel(left + w - 3, top + 5, WHITE)
        return
    b.fill_rect(left, top, w, 9, BLACK)
    b.stroke_rect(left, top, w, 9, CYAN)
    text(word, left + 2, top + 2, WHITE)
    if beside:
        b.set_pixel(left - 1, top + 4, CYAN)
    else:
        b.set_pixel(x + 7, top + 9, CYAN)


def _ticker(b: PixelBuffer, s: dict, text, y: int = 26) -> None:
    if not s['ticker']:
        return
    b.fill_rect(0, y, 128, 32 - y, BLACK)
    text(s['ticker'], 128 - s['tickerT'] // 25, y, GOLD)


def _clock(s: dict) -> str:
    seconds = (s['clock'] + 999) // 1000
    return f'{seconds // 60}:{seconds % 60:02d}'


def _hud(b: PixelBuffer, s: dict, text) -> None:
    t = s['time']
    b.fill_rect(0, 0, 128, 6, BLACK)
    _art(b, APPLE_ART, 1, 1, {'R': APPLE, 'G': STEM})
    text(f"x{s['health']}", 6, 0, RED if s['health'] == 1 and (t // 300) % 2 else WHITE)
    _art(b, STAR_ART[0], 19, 0, {'Y': STAR})
    text(f"{s['stars']:02d}/{STAR_MAX}", 25, 0, GOLD if s['stars'] >= 5 else WHITE)
    late = s['clock'] <= 10_000
    text(_clock(s), 50, 0, (RED if (t // 500) % 2 else GOLD) if late else WHITE)
    _art(b, BOMB_ART[1:], 70, 1, {'S': SHELL})
    text(str(s['bombs']), 75, 0, WHITE)
    for k in range(4):
        b.fill_rect(84 + k * 5, 1, 3, 4, (MAGENTA if k % 2 else CYAN) if k < s['bands'] else OFF)
    if 1 <= s['bands'] <= 2:
        b.draw_line(104, 4, 106, 1, GOLD)
    if s['curse']:
        text('6 7', 112, 0, GOLD)


def _play(b: PixelBuffer, s: dict, text) -> None:
    oy = 1 if s['shake'] > 0 and (s['shake'] // 40) % 2 else 0
    _world(b, s, oy)
    uy = (s['y'] + FP // 2) // FP + oy
    if s['trail'] > 0:
        _trail(b, UX, uy, 6 + s['trail'] // 100, s['time'])
    _unicorn(b, s, UX, uy)
    _bursts(b, s, text)
    if s['bubble'] and s['bubbleMs'] > 0:
        _bubble(b, s['bubble'], s['bubbleMs'], text, UX, uy)
    _hud(b, s, text)
    _ticker(b, s, text)


def _stick(b: PixelBuffer, x: int, y: int, flip: bool, color) -> None:
    """SIX SEVEN dancer: one arm straight up, the other straight down, swapping."""
    b.fill_rect(x - 1, y, 3, 3, color)
    b.draw_line(x, y + 3, x, y + 9, color)
    up, down = (-1, 1) if flip else (1, -1)
    b.draw_line(x + up, y + 4, x + up * 3, y - 1, color)
    b.draw_line(x + down, y + 5, x + down * 3, y + 9, color)
    b.draw_line(x, y + 9, x - 2, y + 14, color)
    b.draw_line(x, y + 9, x + 2, y + 14, color)


def _frame_border(b: PixelBuffer, t: int, color) -> None:
    if (t // 500) % 2 == 0:
        b.stroke_rect(0, 0, 128, 32, color)


def _dance(b: PixelBuffer, s: dict, text) -> None:
    t = s['timer']
    _frame_border(b, t, GOLD)
    text('DANCE SIX SEVEN!', 28, 2, GOLD)
    text(_clock(s), 108, 2, WHITE)
    flip = (t // 500) % 2 == 1
    _unicorn(b, s, 8 + (1 if flip else 0), 15, RUN[0])
    _stick(b, 112, 11, flip, CYAN)
    reps = min(6, t // 500 + 1)
    text(f'SIX SEVEN {reps}/6', 32, 12, WHITE)
    if t >= DANCE_REPS_MS:
        if (t // 400) % 3:
            text('PRESS A WHEN DONE', 24, 22, GOLD)
    else:
        text('STAND UP + DANCE', 26, 22, DIM)


def _curse(b: PixelBuffer, s: dict, text) -> None:
    t = s['timer']
    _frame_border(b, t, MAGENTA)
    text('STAR CURSE!', 36, 2, MAGENTA)
    text(_clock(s), 108, 2, WHITE)
    flip = (t // 500) % 2 == 1
    _stick(b, 112, 11, flip, CYAN)
    text('SIX SEVEN + SHAKE!', 22, 10, WHITE)
    # The unicorn shakes its rainbow tail at you.
    wiggle = (t // 150) % 2
    tail = tuple(row[:2].replace('M', ' ') + row[2:] for row in RUN[0])
    _unicorn(b, s, 6, 18, tail)
    for r in range(3):
        b.set_pixel(5 - wiggle, 21 + r, RAINBOW[(r + t // 100) % 6])
        b.set_pixel(6 - wiggle, 22 + r, RAINBOW[(r + 2 + t // 100) % 6])
    left = str((CURSE_MS - t + 999) // 1000)
    _art(b, STAR_ART[0], 44, 22, {'Y': STAR})
    text(left, 52, 19, GOLD, 2)


ROBOT_HITS = tuple(700 + k * 1000 for k in range(6))


def _robot(b: PixelBuffer, s: dict, text) -> None:
    t, cam = s['timer'], s['cam'] // FP
    _sky(b, cam, s['time'])
    _ground(b, cam, 0)
    for k, hit in enumerate(ROBOT_HITS):
        x = 34 + (hit - t) * 48 // 1000
        if -8 < x < 128:
            if t >= hit:
                _art(b, SPLATTED, x, GROUND_ROW - 7, {'A': AMBER, 'S': STRIPE})
            else:
                _anaglyph(b, HIVE, x, GROUND_ROW - 7)
        if hit <= t < hit + 600:
            word = f'#{k + 1}!'
            _boxed(b, text, word, x, 12 - (t - hit) // 150, GOLD if (t // 100) % 2 else RED)
    d = abs((t - 200) % 1000 - 500)
    y = 19 - d * 10 // 500
    _trail(b, 30, y, 9, s['time'])
    _anaglyph(b, ROBOT, 30, y)
    word = 'PFFT!' if (t // 600) % 2 else 'TOOT!'
    for k, ch in enumerate(word):
        text(ch, 6 + k * 4, max(6, y - 3), RAINBOW[(k + t // 80) % 6])
    text('3D ROBOT MODE!', 35, 0, ROBOT_RED)
    text('3D ROBOT MODE!', 37, 0, ROBOT_CYAN)


def _lose(b: PixelBuffer, s: dict, text) -> None:
    t = s['timer']
    text('YOU LOSE!', 28, 0, RED if (t // 300) % 2 == 0 else DARK_RED, 2)
    hives = [113 - k * 12 for k in range(10)]
    if t < 1100:
        x, y = UX, 19 - (6 * max(0, t - 600) // 500)
        target = x + 5
        for edge in (0, 127):
            bx = edge + (target - edge) * min(t, 600) // 600
            b.fill_rect(bx, 13, 1, y - 13 + 8, CYAN if (t // 80) % 2 else WHITE)
    elif t < 3100:
        x, y = 118 - (t - 1100) * 128 // 2000, 18
    else:
        x, y = -20, 18
    for k, hx in enumerate(hives):
        smashed = t >= 1100 and x <= hx + 3
        _hive(b, hx, 25, s['time'], smashed)
        if smashed and t < 3100 and hx - 8 < x:
            _boxed(b, text, f'#{k + 1}!', hx - 1, 15, GOLD)
    if x > -12:
        _unicorn(b, s, x, y, FLY)
    if t >= 3100:
        for k in range(24):
            r = (t - 3100) // 25
            a = k * 15
            b.set_pixel(64 + (r * (a % 7 - 3)) // 3, 16 + (r * ((a // 7) % 5 - 2)) // 4, RAINBOW[k % 6] if k % 3 else GOLD)


def _confetti(b: PixelBuffer, t: int) -> None:
    for k in range(30):
        h = (k * 2654435761) & 0xffffffff
        if (k + t // 150) % 3:
            b.set_pixel(h % 128, ((h >> 8) % 32 + t // 50) % 32, RAINBOW[(k + t // 200) % 6])


def _win(b: PixelBuffer, s: dict, text) -> None:
    _world(b, s)
    _unicorn(b, s, 59, 19, REAR)
    _confetti(b, s['timer'])
    _bubble(b, 'PRIZE!', 1000, text, 59, 19)
    _hud(b, s, text)


def _grand(b: PixelBuffer, s: dict, text) -> None:
    t = s['timer']
    x = -10 + min(t, 2500) * 138 // 2500
    for row in range(13):
        b.fill_rect(0, 10 + row, max(0, x), 1, RAINBOW[min(5, row // 2)])
    if t < 2500:
        _unicorn(b, s, x, 11, RUN[(t // 120) % 2])
    else:
        b.fill_rect(56, 9, 16, 14, BLACK)
        _art(b, TROPHY, 58, 10, {'Y': GOLD if (t // 300) % 2 else WHITE})
    _confetti(b, t)
    b.fill_rect(0, 0, 128, 7, BLACK)
    text('10 STARS!', 46, 1, GOLD)
    b.fill_rect(0, 26, 128, 6, BLACK)
    message = '*** PERFECT 10 STARS! GRAND PRIZE WINNER! ***'
    text(message, 128 - t // 20 % (128 + len(message) * 4), 26, GOLD)


def _intro(b: PixelBuffer, s: dict, text) -> None:
    _world(b, s)
    _unicorn(b, s, UX, 19, RUN[0])
    title = 'RAINBOW TOOT UNICORN'
    for k, ch in enumerate(title):
        text(ch, 24 + k * 4, 7, RAINBOW[(k + s['timer'] // 120) % 6])
    text('A TOOT  B BOMB  R HORN', 20, 14, WHITE)
    message = 'GET 5 STARS TO WIN, 10 FOR A GREAT PRIZE! TOOT OVER THE BEES!  PRESS A'
    b.fill_rect(0, 26, 128, 6, BLACK)
    text(message, 128 - s['timer'] // 25 % (128 + len(message) * 4), 26, GOLD)
    _hud(b, s, text)


def unicorn_frame(b: PixelBuffer, s: dict, text) -> None:
    {'intro': _intro, 'play': _play, 'dance': _dance, 'curse': _curse, 'robot': _robot, 'lose': _lose,
     'win': _win, 'grand': _grand}[s['phase']](b, s, text)
