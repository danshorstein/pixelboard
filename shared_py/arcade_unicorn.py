"""Rainbow Toot Unicorn rules, mirrored line for line in shared_ts/arcade_unicorn.ts.

The unicorn gallops right by itself. A toots (a rainbow boost up), B throws a
bomb forward and down, R makes a horn dash while one or two headbands are on.
Collect stars (5 to win, 10 for the great prize) in two minutes, dodge
beehives and bee swarms, eat apples for health. The fourth headband stops play
for the SIX SEVEN dance (press A when done). After it, every star brings a
10 second SIX SEVEN + shake. 3D glasses turn the unicorn into a 3D robot that
farts nonstop into six beehives in seven seconds: game over.

Everything is integers: heights in 1/256 px, the world scroll in 1/256 px, and
objects come from a seeded hash per 24 px segment so nothing is stored but
what has been collected or destroyed.
"""
from __future__ import annotations

from typing import Any

STEP_MS = 20
FP = 256
ROUND_MS = 120_000
SEG = 24  # world pixels per segment; each segment may hold a ground and an air object
UX = 24  # screen column of the unicorn's left edge
TOP_Y, GROUND_Y = 7 * FP, 19 * FP  # unicorn top row limits (8 px tall, feet on row 26)
GROUND_ROW = 27
SPEED = 150  # scroll per step
GRAVITY, TOOT, FALL_MAX = 7, -165, 230
HEALTH_START, HEALTH_MAX = 3, 5
BOMBS_START, BOMBS_MAX, BOMB_PICKUP = 3, 9, 2
BOMB_VX, BOMB_VY, BOMB_GRAVITY = SPEED + 110, 60, 9
INVULN_MS, DASH_MS, HORN_COOL_MS = 1500, 300, 900
DANCE_REPS_MS, DANCE_LIMIT_MS = 3000, 15_000  # six swaps shown, then A; no A in time loses
CURSE_MS = 10_000
ROBOT_MS, LOSE_MS, WIN_MS, GRAND_MS, INTRO_MS = 7000, 3600, 3000, 5000, 8000
FX_MS, BUBBLE_MS = 700, 1500
STAR_GOAL, STAR_MAX = 5, 10
# Object sizes (w, h) in pixels.
SIZES = {'hive': (7, 7), 'star': (5, 5), 'apple': (4, 4), 'bomb': (5, 5), 'band': (5, 3), 'glasses': (6, 3),
         'swarm': (5, 4)}
PICKUPS = ('star', 'apple', 'bomb', 'band', 'glasses')
# Chance (percent) of each air object per segment; the rest of the sky is empty.
AIR = (('star', 9), ('apple', 6), ('bomb', 7), ('band', 5), ('swarm', 5), ('glasses', 2))
HIVE_CHANCE = 27


def _rand(seed: int) -> int:
    return (seed * 1664525 + 1013904223) & 0xffffffff


def _hash(seed: int, n: int) -> int:
    return _rand(_rand((seed + n * 2654435761) & 0xffffffff))


def unicorn_object(seed: int, i: int, slot: int) -> list | None:
    """[kind, x, y] in world pixels for segment i (slot 0 ground, 1 air), or None."""
    if i < 4:
        return None
    h = _hash(seed, i * 2 + slot)
    if slot == 0:
        if (h >> 8) % 100 < HIVE_CHANCE:
            return ['hive', i * SEG + 5 + (h >> 16) % 12, GROUND_ROW - 7]
        return None
    roll = (h >> 8) % 100
    x, y = i * SEG + 2 + (h >> 16) % 14, 8 + (h >> 21) % 9
    for kind, chance in AIR:
        if roll < chance:
            if kind == 'band' and i < 8 or kind == 'glasses' and (i < 30 or i % 5):
                return None
            if kind == 'swarm':
                return [kind, x, 9 + (h >> 21) % 7]
            if kind == 'glasses':
                return [kind, x, 8 + (h >> 21) % 4]  # always up high: a unicorn on the ground runs under them
            return [kind, x, y]
        roll -= chance
    return None


def object_y(obj: list, time: int) -> int:
    """Swarms bob up and down; everything else stays put."""
    if obj[0] != 'swarm':
        return obj[2]
    t = (time // 60 + obj[1]) % 8
    return obj[2] + (t if t < 4 else 8 - t) - 2


def create_unicorn(base: dict) -> dict[str, Any]:
    return dict(base, phase='intro', timer=0, clock=ROUND_MS, cam=0, y=GROUND_Y, vy=0, toots=0, trail=0,
                health=HEALTH_START, bombs=BOMBS_START, bands=0, stars=0, curse=False, invuln=0, dash=0,
                hornCool=0, shake=0, gone=[], shots=[], fx=[], bubble='', bubbleMs=0, ticker='', tickerT=0,
                score=0, gems=0, gemValue=1)


def _copy(state: dict) -> dict:
    return dict(state, gone=state['gone'][:], shots=[s[:] for s in state['shots']], fx=[f[:] for f in state['fx']])


def _px(v: int) -> int:
    return (v + FP // 2) // FP


def _say(s: dict, text: str) -> None:
    s['bubble'], s['bubbleMs'] = text, BUBBLE_MS


def _tick(s: dict, text: str) -> None:
    s['ticker'], s['tickerT'] = text, 0


def _burst(s: dict, word: str, x: int, y: int) -> None:
    """Comic action word at world pixel (x, y)."""
    s['fx'].append([word, x, y, 0])


def _phase(s: dict, phase: str) -> None:
    s['phase'], s['timer'] = phase, 0


def _lose(s: dict) -> None:
    _phase(s, 'lose')
    s['bubble'] = ''


def _register_star(s: dict) -> None:
    s['stars'] += 1
    s['score'] = s['stars']
    s['gems'] += 2 * s['gemValue']
    if s['stars'] >= STAR_MAX:
        s['gems'] += 50 * s['gemValue']
        _phase(s, 'grand')
    elif s['stars'] == STAR_GOAL:
        _tick(s, 'UNICORN: 5 STARS! KEEP GOING FOR 10 AND A GREAT PRIZE!')


def _time_up(s: dict) -> None:
    if s['stars'] >= STAR_GOAL:
        s['gems'] += 10 * s['gemValue']
        _phase(s, 'win')
    else:
        _lose(s)


def _overlap(ax: int, ay: int, aw: int, ah: int, bx: int, by: int, bw: int, bh: int) -> bool:
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def _nearby(s: dict, left: int, right: int):
    """(id, object) pairs still in the world between world pixels left and right."""
    for i in range(max(0, left // SEG - 1), right // SEG + 1):
        for slot in (0, 1):
            obj = unicorn_object(s['seed'], i, slot)
            if obj and i * 2 + slot not in s['gone']:
                yield i * 2 + slot, obj


def _collect(s: dict, oid: int, obj: list) -> None:
    kind, x, y = obj
    s['gone'].append(oid)
    if kind == 'star':
        if s['curse']:
            _phase(s, 'curse')
            _tick(s, 'STAR CURSE! SIX SEVEN AND SHAKE YOUR TUSHY!')
        else:
            _say(s, 'YAY!')
            _register_star(s)
    elif kind == 'apple':
        s['health'] = min(HEALTH_MAX, s['health'] + 1)
        _say(s, 'YUM!')
    elif kind == 'bomb':
        s['bombs'] = min(BOMBS_MAX, s['bombs'] + BOMB_PICKUP)
        _say(s, 'BOMBS')
    elif kind == 'band':
        if s['curse']:
            return
        s['bands'] += 1
        if s['bands'] == 1:
            _say(s, 'HORN!')
            _tick(s, 'UNICORN: HEADBAND ON! PRESS R FOR A HORN DASH!')
        elif s['bands'] == 3:
            _say(s, 'NO HORN')
            _tick(s, 'UNICORN: 3 BANDS! NO MORE HORN. DO NOT GET A 4TH!')
        elif s['bands'] >= 4:
            _phase(s, 'dance')
            s['bubble'] = ''
    elif kind == 'glasses':
        _phase(s, 'robot')
        s['bubble'] = s['ticker'] = ''


def _hit(s: dict, oid: int, obj: list) -> None:
    """The unicorn touched a beehive or bee swarm."""
    if s['dash'] > 0:
        s['gone'].append(oid)
        _burst(s, 'POW!', obj[1], obj[2] - 2)
        return
    if s['invuln'] > 0:
        return
    s['health'] -= 1
    s['invuln'] = INVULN_MS
    _burst(s, 'OUCH!' if obj[0] == 'hive' else 'BZZZ!', obj[1], obj[2] - 2)
    _say(s, 'OOF!')
    if s['health'] <= 0:
        _lose(s)


def _blast(s: dict, x: int, y: int, word: str) -> None:
    """A bomb went off at world pixel (x, y): hives and swarms close by are gone."""
    _burst(s, word, x - 8, y - 6)
    s['shake'] = 200
    for oid, obj in list(_nearby(s, x - 12, x + 12)):
        if obj[0] in ('hive', 'swarm'):
            w, h = SIZES[obj[0]]
            if _overlap(x - 6, y - 6, 12, 12, obj[1], object_y(obj, s['time']), w, h):
                s['gone'].append(oid)


def _step_shots(s: dict) -> None:
    kept = []
    for shot in s['shots']:
        shot[0] += shot[2]
        shot[1] += shot[3]
        shot[3] += BOMB_GRAVITY
        x, y = _px(shot[0]), _px(shot[1])
        hit = None
        for oid, obj in _nearby(s, x - 8, x + 8):
            if obj[0] in ('hive', 'swarm'):
                w, h = SIZES[obj[0]]
                if _overlap(x - 1, y - 1, 3, 3, obj[1], object_y(obj, s['time']), w, h):
                    hit = obj
                    break
        if hit:
            _blast(s, x, y, 'SPLAT!')
        elif y >= GROUND_ROW:
            _blast(s, x, GROUND_ROW - 1, 'BOOM!')
        elif x < s['cam'] // FP + 136:
            kept.append(shot)
    s['shots'] = kept


def _step_play(s: dict) -> None:
    s['cam'] += SPEED
    s['vy'] = min(FALL_MAX, s['vy'] + GRAVITY)
    s['y'] += s['vy']
    if s['y'] >= GROUND_Y:
        s['y'], s['vy'] = GROUND_Y, 0
    elif s['y'] < TOP_Y:
        s['y'], s['vy'] = TOP_Y, 0
    for key in ('trail', 'invuln', 'dash', 'hornCool', 'shake', 'bubbleMs'):
        s[key] = max(0, s[key] - STEP_MS)
    cam_px = s['cam'] // FP
    ux, uy = cam_px + UX, _px(s['y'])
    s['gone'] = [g for g in s['gone'] if g // 2 >= cam_px // SEG - 2]
    _step_shots(s)
    reach = 4 if s['dash'] > 0 else 0  # the glowing horn reaches a little further
    for oid, obj in list(_nearby(s, ux - 8, ux + 16)):
        if s['phase'] != 'play':
            break  # a pickup started a dance, a curse or the robot
        if oid in s['gone']:
            continue
        w, h = SIZES[obj[0]]
        oy = object_y(obj, s['time'])
        if not _overlap(ux + 1, uy + 1, 8 + reach, 6, obj[1], oy, w, h):
            continue
        if obj[0] in PICKUPS:
            _collect(s, oid, obj)
        elif _overlap(ux + 1, uy + 1, 8 + reach, 6, obj[1] + 1, oy + 1, w - 2, h - 1):
            _hit(s, oid, obj)  # hazards forgive a one-pixel graze


def _end_screen(s: dict) -> None:
    """Leave a finished cutscene for the game-over screen."""
    phase = s['phase']
    if phase in ('lose', 'robot'):
        s['message'] = 'YOU LOSE!'
    elif phase == 'win':
        s['message'] = f"YOU WIN! {s['stars']} STARS"
    else:
        s['message'] = 'GRAND PRIZE! 10 STARS'
    s['status'] = 'over'


def step_unicorn(state: dict, time: int) -> dict:
    s = _copy(state)
    s['time'] = time
    s['timer'] += STEP_MS
    s['fx'] = [f for f in s['fx'] if f[3] + STEP_MS < FX_MS]
    for f in s['fx']:
        f[3] += STEP_MS
    if s['ticker']:
        s['tickerT'] += STEP_MS
        if s['tickerT'] >= (128 + len(s['ticker']) * 4) * 25:
            s['ticker'], s['tickerT'] = '', 0
    phase = s['phase']
    if phase == 'intro':
        if s['timer'] >= INTRO_MS:
            _phase(s, 'play')
        return s
    if phase in ('play', 'dance', 'curse'):
        s['clock'] -= STEP_MS  # the two minutes keep running through the dance and the curse
        if s['clock'] <= 0:
            s['clock'] = 0
            _time_up(s)
            return s
    if phase == 'play':
        _step_play(s)
    elif phase == 'dance':
        if s['timer'] >= DANCE_LIMIT_MS:
            _lose(s)
    elif phase == 'curse':
        if s['timer'] >= CURSE_MS:
            _phase(s, 'play')
            _register_star(s)
    elif phase == 'robot':
        s['cam'] += 2 * SPEED
        if s['timer'] >= ROBOT_MS:
            _end_screen(s)
    elif s['timer'] >= {'lose': LOSE_MS, 'win': WIN_MS, 'grand': GRAND_MS}[phase]:
        _end_screen(s)
    return s


def press_unicorn(state: dict, button: str) -> dict:
    if state['status'] != 'running':
        return state
    s = _copy(state)
    phase = s['phase']
    if button == 'a' and phase == 'intro':
        _phase(s, 'play')
    elif button == 'a' and phase == 'play':
        s['vy'] = TOOT
        s['trail'] = 400
        s['toots'] += 1
        if s['toots'] % 3 == 1:
            _burst(s, 'TOOT!' if s['toots'] % 2 else 'PFFT!', s['cam'] // FP + UX - 14, _px(s['y']) + 2)
    elif button == 'a' and phase == 'dance' and s['timer'] >= DANCE_REPS_MS:
        s['curse'] = True
        _phase(s, 'play')
        _tick(s, 'UNICORN: SIX SEVEN! NOW EVERY STAR MEANS SIX SEVEN!')
    elif button == 'a' and (phase == 'lose' and s['timer'] >= 600 or phase in ('win', 'grand') and s['timer'] >= 1000):
        _end_screen(s)
    elif button == 'b' and phase == 'play' and s['bombs'] > 0 and len(s['shots']) < 2:
        s['bombs'] -= 1
        s['shots'].append([s['cam'] + (UX + 8) * FP, s['y'] + 6 * FP, BOMB_VX, BOMB_VY])
    elif button == 'r' and phase == 'play' and 1 <= s['bands'] <= 2 and s['hornCool'] == 0:
        s['dash'], s['hornCool'] = DASH_MS, HORN_COOL_MS + DASH_MS
        _burst(s, 'POW!', s['cam'] // FP + UX + 10, _px(s['y']) - 4)
    else:
        return state
    return s
