"""Deterministic 20ms arcade rules, mirrored in shared_ts/arcade.ts."""
from __future__ import annotations

import math
from typing import Any

from shared_py.arcade_bigleague import create_bigleague, press_bigleague, step_bigleague
from shared_py.arcade_soccer import create_soccer, press_soccer, step_soccer
from shared_py.arcade_unicorn import create_unicorn, press_unicorn, step_unicorn

STEP_MS = 20
KINDS = ('baseball', 'snake', 'pong', 'rider', 'bigleague', 'soccer', 'unicorn')
VECTORS = {'up': (0, -1), 'down': (0, 1), 'left': (-1, 0), 'right': (1, 0)}


def _random(seed: int) -> int:
    return (seed * 1664525 + 1013904223) & 0xffffffff


def _food(body: list[dict], seed: int) -> dict | None:
    occupied = {(p['x'], p['y']) for p in body}
    start = seed % (62 * 12)
    for i in range(62 * 12):
        cell = (start + i) % (62 * 12)
        point = {'x': 1 + cell % 62, 'y': 3 + cell // 62}
        if (point['x'], point['y']) not in occupied:
            return point
    return None


def create_game(kind: str, seed: int = 727) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError('Unknown arcade game')
    base = dict(kind=kind, status='ready', time=0, seed=seed & 0xffffffff, message='PRESS START')
    if kind == 'snake':
        body = [{'x': 16, 'y': 8}, {'x': 15, 'y': 8}, {'x': 14, 'y': 8}]
        return dict(base, body=body, direction='right', queued='right', food=_food(body, seed), score=0, accumulator=0)
    if kind == 'pong':
        return dict(base, player=12, computer=12, ball={'x': 64, 'y': 18}, vx=-.8, vy=.35, playerScore=0, computerScore=0, serve=700)
    if kind == 'bigleague':
        return create_bigleague(base)
    if kind == 'soccer':
        return create_soccer(base)
    if kind == 'unicorn':
        return create_unicorn(base)
    if kind == 'rider':
        x = RIDER_START * FP
        return dict(base, x=x, y=rider_ground(seed & 0xffffffff, x), vx=0, vy=0, angle=0, air=False, spin=0,
                    score=0, bonus=0, gems=0, nextGem=4, banner='', bannerMs=0, car=0, color=0, theme=0, gemValue=1)
    return dict(base, phase='pitch', x=110, speed=.075, flight=0, result='', score=0, strikes=0, pitches=0)


def start_game(state: dict) -> dict:
    return dict(state, status='running', message='') if state['status'] == 'ready' else state


def steer_snake(state: dict, direction: str) -> dict:
    if state['status'] != 'running' or direction not in VECTORS:
        return state
    a, b = VECTORS[state['direction']], VECTORS[direction]
    return state if a[0] + b[0] == 0 and a[1] + b[1] == 0 else dict(state, queued=direction)


def swing(state: dict) -> dict:
    if state['status'] != 'running' or state['phase'] != 'pitch':
        return state
    error = abs((state['x'] - 24) / state['speed'])
    result = 'HOME RUN!' if error <= 25 else 'DOUBLE!' if error <= 65 else 'HIT!' if error <= 110 else 'FOUL' if error <= 190 else 'MISS'
    points = {'HOME RUN!': 5, 'DOUBLE!': 3, 'HIT!': 1}.get(result, 0)
    return dict(state, phase='flight', flight=0, x=24, result=result, message=result, score=state['score'] + points,
                strikes=state['strikes'] + (1 if result == 'MISS' else 0), pitches=state['pitches'] + 1)


def press_game(state: dict, button: str) -> dict:
    """A button press for games whose buttons are actions, not held controls."""
    if state['kind'] == 'bigleague':
        return press_bigleague(state, button)
    if state['kind'] == 'soccer':
        return press_soccer(state, button)
    if state['kind'] == 'unicorn':
        return press_unicorn(state, button)
    return state


def step_game(state: dict, held: set[str] | frozenset[str] = frozenset()) -> dict:
    if state['status'] != 'running':
        return state
    time = state['time'] + STEP_MS
    if state['kind'] == 'bigleague':
        return step_bigleague(state, time)
    if state['kind'] == 'soccer':
        return step_soccer(state, held, time)
    if state['kind'] == 'unicorn':
        return step_unicorn(state, time)
    if state['kind'] == 'rider':
        return _step_rider(state, held, time)
    if state['kind'] == 'snake':
        accumulator = state['accumulator'] + STEP_MS
        interval = max(70, 150 - state['score'] * 3)
        if accumulator < interval:
            return dict(state, time=time, accumulator=accumulator)
        dx, dy = VECTORS[state['queued']]
        head = {'x': state['body'][0]['x'] + dx, 'y': state['body'][0]['y'] + dy}
        eating = state['food'] == head
        check = state['body'] if eating else state['body'][:-1]
        if head['x'] < 1 or head['x'] > 62 or head['y'] < 3 or head['y'] > 14 or head in check:
            return dict(state, time=time, status='over', message='GAME OVER')
        body = [head, *state['body']]
        if not eating:
            body.pop()
        seed = _random(state['seed']) if eating else state['seed']
        food = _food(body, seed) if eating else state['food']
        return dict(state, time=time, body=body, seed=seed, food=food, score=state['score'] + (1 if eating else 0),
                    direction=state['queued'], accumulator=accumulator - interval, status='running' if food else 'over', message='' if food else 'YOU WIN!')
    if state['kind'] == 'baseball':
        if state['phase'] == 'pitch':
            x = state['x'] - state['speed'] * STEP_MS
            if x < 10:
                return dict(state, x=x, time=time, phase='flight', flight=0, result='MISS', message='MISS', strikes=state['strikes'] + 1, pitches=state['pitches'] + 1)
            return dict(state, x=x, time=time)
        flight = state['flight'] + STEP_MS
        if flight < 1250:
            return dict(state, time=time, flight=flight)
        if state['strikes'] >= 3 or state['pitches'] >= 10:
            return dict(state, time=time, flight=flight, status='over', message='STRIKE THREE' if state['strikes'] >= 3 else 'ROUND COMPLETE')
        seed = _random(state['seed'])
        return dict(state, time=time, seed=seed, phase='pitch', x=110, speed=.06 + (seed % 45) / 1000, flight=0, result='', message='')
    player = max(6, min(23, state['player'] + (1 if 'down' in held else 0) - (1 if 'up' in held else 0)))
    target = state['ball']['y'] - 3 + math.sin(time / 370) * 4
    computer = max(6, min(23, state['computer'] + max(-.48, min(.48, target - state['computer']))))
    if state['serve'] > 0:
        return dict(state, time=time, player=player, computer=computer, serve=max(0, state['serve'] - STEP_MS))
    x, y = state['ball']['x'] + state['vx'], state['ball']['y'] + state['vy']
    vx, vy = state['vx'], state['vy']
    if y < 6 or y > 29:
        y, vy = max(6, min(29, y)), -vy
    hit_player = vx < 0 and x <= 6 and state['ball']['x'] > 6 and player - 1 <= y <= player + 8
    hit_computer = vx > 0 and x >= 121 and state['ball']['x'] < 121 and computer - 1 <= y <= computer + 8
    if hit_player or hit_computer:
        vx = (1 if hit_player else -1) * min(1.6, abs(vx) + .07)
        vy = (y - (player if hit_player else computer) - 3.5) * .2
        x = 6 if hit_player else 121
    if x < 0 or x > 127:
        player_score = state['playerScore'] + (1 if x > 127 else 0)
        computer_score = state['computerScore'] + (1 if x < 0 else 0)
        over = player_score >= 5 or computer_score >= 5
        return dict(state, time=time, player=player, computer=computer, playerScore=player_score, computerScore=computer_score,
                    ball={'x': 64, 'y': 18}, vx=-.8 if x < 0 else .8, vy=.35, serve=700, status='over' if over else 'running',
                    message=('YOU WIN!' if player_score >= 5 else 'PI WINS') if over else '')
    return dict(state, time=time, player=player, computer=computer, ball={'x': x, 'y': y}, vx=vx, vy=vy)


# Neon Rider: integer fixed-point (1/256 px) physics so both languages agree exactly.
FP = 256
RIDER_START = 40
SEGMENT = 32
GRAVITY = 8
GAS = 5
VMAX = 768
FLIP_SPIN = 10
LAND_TOLERANCE = 45


def _wrap(angle: int) -> int:
    """Signed angle in -180..179 degrees; positive tips the nose down."""
    return ((angle + 180) % 360 + 360) % 360 - 180


def _segment_hash(seed: int, i: int) -> int:
    return _random(_random((seed + i * 2654435761) & 0xffffffff))


def _height(seed: int, i: int) -> int:
    if i < 3:
        return 24
    amp = min(14, 2 + (i - 3) // 2)
    return 27 - (_segment_hash(seed, i) >> 8) % (amp + 1)


def _ground_px(seed: int, px: int) -> int:
    i = px // SEGMENT
    t = px - i * SEGMENT
    h0, h1 = _height(seed, i), _height(seed, i + 1)
    return h0 * FP + (h1 - h0) * FP * (3 * t * t * SEGMENT - 2 * t * t * t) // (SEGMENT ** 3)


def rider_ground(seed: int, x: int) -> int:
    """Ground row in 1/256 px at world x (also 1/256 px)."""
    px = x // FP
    a = _ground_px(seed, px)
    return a + (_ground_px(seed, px + 1) - a) * (x - px * FP) // FP


def _slope(seed: int, x: int) -> int:
    return rider_ground(seed, x + 2 * FP) - rider_ground(seed, x - 2 * FP)


def _slope_angle(seed: int, x: int) -> int:
    return max(-60, min(60, _slope(seed, x) * 45 // (4 * FP)))


def rider_gem(seed: int, i: int) -> dict | None:
    if i < 4:
        return None
    v = _random(_segment_hash(seed, i))
    if (v >> 4) % 3 == 0:
        return None
    x = i * SEGMENT + SEGMENT // 2
    return {'x': x, 'y': (_ground_px(seed, x) + FP // 2) // FP - 5 - (v >> 12) % 6}


def _step_rider(state: dict, held, time: int) -> dict:
    seed = state['seed']
    gas = 'a' in held or 'right' in held
    x, y, vx, vy, angle = state['x'], state['y'], state['vx'], state['vy'], state['angle']
    air, spin, bonus, banner_ms, banner = state['air'], state['spin'], state['bonus'], state['bannerMs'], state['banner']
    banner_ms = max(0, banner_ms - STEP_MS)
    if not air:
        vx += (GAS if gas else 0) + _slope(seed, x) // 128 - (vx + 127) // 128
        vx = max(0, min(VMAX, vx))
        x += vx
        follow = rider_ground(seed, x) - y
        if follow > vy + GRAVITY + 24:
            air, spin = True, 0
            vy += GRAVITY
            y += vy
        else:
            y += follow
            vy = follow
            angle = _slope_angle(seed, x)
    else:
        vy += GRAVITY
        x += vx
        y += vy
        if gas:
            angle -= FLIP_SPIN
            spin += FLIP_SPIN
        else:
            # Released in the air, the car levels toward the ground below it.
            angle += max(-5, min(5, _wrap(_slope_angle(seed, x) - angle)))
        angle = _wrap(angle)
        ground = rider_ground(seed, x)
        if y >= ground:
            if abs(_wrap(angle - _slope_angle(seed, x))) > LAND_TOLERANCE:
                return dict(state, time=time, x=x, y=ground, vx=0, vy=0, angle=angle, air=False, spin=spin,
                            bannerMs=0, status='over', message='CRASH!')
            flips = (spin + 45) // 360
            if flips:
                bonus += 10 * flips
                vx = min(VMAX, vx + 64 * flips)
                banner, banner_ms = ('FLIP!' if flips == 1 else f'{flips}X FLIP!'), 900
            air, spin, y = False, 0, ground
            vy = 0
            angle = _slope_angle(seed, x)
    gems, next_gem = state['gems'], state['nextGem']
    px, cy = x // FP, (y + FP // 2) // FP - 2
    while next_gem * SEGMENT + SEGMENT // 2 + 3 < px:
        next_gem += 1
    gem = rider_gem(seed, next_gem)
    if gem and abs(px - gem['x']) <= 3 and abs(cy - gem['y']) <= 4:
        gems, next_gem = gems + state['gemValue'], next_gem + 1
    score = (x - RIDER_START * FP) // (8 * FP) + bonus
    return dict(state, time=time, x=x, y=y, vx=vx, vy=vy, angle=angle, air=air, spin=spin, score=score, bonus=bonus,
                gems=gems, nextGem=next_gem, banner=banner, bannerMs=banner_ms)
