"""Soccer: a 3 v 3 match seen from above, mirrored in shared_ts/arcade_soccer.ts.

YOU (teal) attack to the right, PI (gold) to the left. Each side has a
goalkeeper and two field players. The D-pad moves whichever of your field
players is nearest the ball; A kicks (toward the goal unless a direction is
held) or, without the ball, makes a quick dash to win it. The ball bounces off
the side walls and end lines, so play never stops for throw-ins.

All positions are integers in 1/256 px, like Neon Rider.
"""
from __future__ import annotations

import math
from typing import Any

STEP_MS = 20
FP = 256
LEFT, RIGHT, TOP, BOTTOM = 2 * FP, 125 * FP, 7 * FP, 30 * FP  # where the ball and players can be
MOUTH_TOP, MOUTH_BOTTOM = 13 * FP, 25 * FP  # goal opening on both end lines
MID_Y = 18 * FP + FP // 2
MATCH_MS = 180_000
GOLDEN_MS = 60_000
GOAL_MS = 1600
# Kick-off spots: keeper, top player, bottom player for YOU then PI.
FORMATION = ((4, 18), (40, 13), (40, 24), (123, 18), (88, 13), (88, 24))
# Reduced player speeds and matching ball friction keep play readable on the display.
SPEED_YOU, SPEED_MATE, SPEED_PI, SPEED_KEEPER = 115, 95, 100, 55
DASH_MS, DASH_COOL_MS = 600, 2400
KICK, PASS = 450, 310
FAST = 350  # a ball faster than this only keepers can stop
KICK_LOCK_MS, LOST_BALL_MS, STUMBLE_MS, KEEPER_HOLD_MS = 400, 800, 1000, 1400
REACH = 3 * FP
STEAL_STEPS_PI, STEAL_STEPS_YOU = 36, 20  # contact needed for PI / YOU to win the ball
DIAG = 181  # 1/sqrt(2) x 256


def _rand(seed: int) -> int:
    return (seed * 1664525 + 1013904223) & 0xffffffff


def _draw(s: dict) -> int:
    s['seed'] = _rand(s['seed'])
    return s['seed'] >> 8


def _isqrt(n: int) -> int:
    return math.isqrt(n) if n > 0 else 0


def _dist(ax: int, ay: int, bx: int, by: int) -> int:
    return _isqrt((ax - bx) * (ax - bx) + (ay - by) * (ay - by))


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def _shrink(v: int, num: int, den: int) -> int:
    return v * num // den if v >= 0 else 0 - (-v * num // den)


def _sign(v: int) -> int:
    return (v > 0) - (v < 0)


def _team(i: int) -> int:
    return 0 if i < 3 else 1


def _kickoff(s: dict, team: int) -> None:
    """Everyone back to their spots; `team` starts with the ball in the centre."""
    s['players'] = [[x * FP, y * FP + FP // 2, 1 if i < 3 else -1, 0, 0] for i, (x, y) in enumerate(FORMATION)]
    taker = 1 if team == 0 else 4
    s['players'][taker][0] = (61 if team == 0 else 67) * FP
    s['players'][taker][1] = MID_Y
    s['ball'] = [64 * FP, MID_Y, 0, 0]
    s.update(owner=taker, control=1, pressure=0, dash=0, dashCool=0, keeperHold=0)
    _new_possession(s)


def create_soccer(base: dict) -> dict[str, Any]:
    s = dict(base, players=[], ball=[0, 0, 0, 0], owner=-1, control=1, you=0, pi=0, clock=MATCH_MS, golden=False,
             phase='play', timer=0, banner='', pressure=0, dash=0, dashCool=0, keeperHold=0, shootX=0, aimY=0,
             score=0, gems=0, gemValue=1)
    _kickoff(s, 0)
    return s


def _copy(state: dict) -> dict:
    return dict(state, players=[p[:] for p in state['players']], ball=state['ball'][:])


def _new_possession(s: dict) -> None:
    r = _draw(s)
    s['shootX'] = (18 + r % 22) * FP
    s['aimY'] = MOUTH_TOP + FP + (r >> 8) % 10 * FP
    s['pressure'] = 0


def _move(p: list, tx: int, ty: int, speed: int) -> None:
    dx, dy = tx - p[0], ty - p[1]
    d = _isqrt(dx * dx + dy * dy)
    if d == 0:
        return
    if d > speed:
        dx, dy = dx * speed // d, dy * speed // d
    p[0] = _clamp(p[0] + dx, LEFT, RIGHT)
    p[1] = _clamp(p[1] + dy, TOP, BOTTOM)
    if abs(dx) * 2 > abs(dy) or abs(dy) * 2 > abs(dx):
        p[2] = _sign(dx) if abs(dx) * 2 > abs(dy) else 0
        p[3] = _sign(dy) if abs(dy) * 2 > abs(dx) else 0


def _kick(s: dict, kicker: int, dx: int, dy: int, speed: int) -> None:
    """Kick along (dx, dy), any length."""
    d = _isqrt(dx * dx + dy * dy)
    if d == 0:
        dx, d = (1 if kicker < 3 else -1), 1
    s['ball'][2], s['ball'][3] = dx * speed // d, dy * speed // d
    s['owner'] = -1
    s['players'][kicker][4] = KICK_LOCK_MS  # the kicker cannot touch it again straight away
    s['keeperHold'] = 0


def _goal(s: dict, team: int) -> None:
    key = 'you' if team == 0 else 'pi'
    s[key] += 1
    if team == 0:
        s['score'] = s['you']
        s['gems'] += 5 * s['gemValue']
    s.update(phase='goal', timer=0, banner='GOAL!' if team == 0 else 'PI SCORES', owner=-1)
    s['ball'][2] = s['ball'][3] = 0


def _finish(s: dict) -> None:
    you, pi = s['you'], s['pi']
    if you > pi:
        s['message'] = f'YOU WIN {you}-{pi}'
        s['gems'] += 10 * s['gemValue']
    elif pi > you:
        s['message'] = f'PI WINS {pi}-{you}'
    else:
        s['message'] = f'DRAW {you}-{pi}'
    s['status'] = 'over'


def _pickup(s: dict) -> bool:
    """Give a loose ball to the nearest player who can reach it (keepers stop shots too)."""
    ball, players = s['ball'], s['players']
    fast = abs(ball[2]) + abs(ball[3]) > FAST
    best, best_d = -1, REACH + 1
    for i, p in enumerate(players):
        if p[4] > 0 or (fast and i not in (0, 3)):
            continue
        d = _dist(p[0], p[1], ball[0], ball[1])
        if d < best_d:
            best, best_d = i, d
    if best < 0:
        return False
    s['owner'], s['pressure'], s['keeperHold'] = best, 0, 0
    ball[2] = ball[3] = 0
    if _team(best) == 1:
        _new_possession(s)
    return True


def _ball_physics(s: dict) -> None:
    ball = s['ball']
    if s['owner'] >= 0:
        p = s['players'][s['owner']]
        if s['owner'] in (0, 3):
            ball[0], ball[1] = p[0] + (2 * FP if s['owner'] == 0 else -2 * FP), p[1]
        else:
            ball[0] = p[0] + p[2] * 3 * FP
            ball[1] = _clamp(p[1] + p[3] * 3 * FP, TOP, BOTTOM)
        _goal_line(s)
        return
    # Move in sub-steps of at most 2 px so a fast shot cannot skip past a keeper.
    parts = 1 + (abs(ball[2]) + abs(ball[3])) // (2 * FP)
    for _ in range(parts):
        ball[0] += _shrink(ball[2], 1, parts)
        ball[1] += _shrink(ball[3], 1, parts)
        if ball[1] < TOP:
            ball[1], ball[3] = 2 * TOP - ball[1], -ball[3]
        elif ball[1] > BOTTOM:
            ball[1], ball[3] = 2 * BOTTOM - ball[1], -ball[3]
        if _goal_line(s) or _pickup(s):
            return
    ball[2], ball[3] = _shrink(ball[2], 79, 80), _shrink(ball[3], 79, 80)


def _goal_line(s: dict) -> bool:
    """Score, or bounce off the end line beside the goal."""
    ball = s['ball']
    in_mouth = MOUTH_TOP <= ball[1] < MOUTH_BOTTOM
    if ball[0] < LEFT:
        if in_mouth:
            _goal(s, 1)
            return True
        ball[0], ball[2] = 2 * LEFT - ball[0], -ball[2]
    elif ball[0] > RIGHT:
        if in_mouth:
            _goal(s, 0)
            return True
        ball[0], ball[2] = 2 * RIGHT - ball[0], -ball[2]
    return False


def _ai(s: dict, held) -> None:
    ball, players, owner = s['ball'], s['players'], s['owner']
    owning = _team(owner) if owner >= 0 else -1
    bx, by = ball[0], ball[1]
    # Keepers follow the ball across their goal and step out when it comes close.
    for k, line, out in ((0, 4 * FP, 9 * FP), (3, 123 * FP, 118 * FP)):
        if owner == k:
            continue
        near = abs(bx - line) < 30 * FP
        _move(players[k], out if near else line, _clamp(by, MOUTH_TOP + FP, MOUTH_BOTTOM - 2 * FP), SPEED_KEEPER)
        players[k][2] = 1 if k == 0 else -1
    # YOU: the controlled player follows the D-pad; the teammate supports or defends.
    c = s['control']
    mate = 3 - c
    dx = (1 if 'right' in held else 0) - (1 if 'left' in held else 0)
    dy = (1 if 'down' in held else 0) - (1 if 'up' in held else 0)
    if dx or dy:
        speed = SPEED_YOU * (14 if s['dash'] > 0 else 10) // 10
        step = speed * DIAG // 256 if dx and dy else speed
        p = players[c]
        _move(p, p[0] + dx * step, p[1] + dy * step, step)
        p[2], p[3] = dx, dy
    if owning == 0:
        tx, ty = min(players[owner][0] + 24 * FP, 112 * FP), 37 * FP - players[owner][1]
    else:
        tx, ty = (bx + 8 * FP) // 2, (by + MID_Y) // 2
    if owner != mate:
        _move(players[mate], tx, _clamp(ty, TOP, BOTTOM), SPEED_MATE)
    # PI: the nearer field player chases (or carries) the ball, the other supports.
    chaser = 4 if _dist(players[4][0], players[4][1], bx, by) <= _dist(players[5][0], players[5][1], bx, by) else 5
    if owning == 1 and owner in (4, 5):
        chaser = owner
    for i in (4, 5):
        p = players[i]
        if i == owner:
            tx, ty = 2 * FP, MID_Y
            for j in (1, 2):
                q = players[j]
                if 0 < p[0] - q[0] < 12 * FP and abs(q[1] - p[1]) < 5 * FP:
                    ty = q[1] + (8 * FP if q[1] < p[1] or q[1] == p[1] and p[1] > MID_Y else -8 * FP)
            _move(p, tx, _clamp(ty, TOP + 2 * FP, BOTTOM - 2 * FP), SPEED_PI)
        elif i == chaser and owning != 1:
            _move(p, bx, by, SPEED_PI)
        elif owning == 1:
            _move(p, max(players[owner][0] - 22 * FP, 16 * FP), _clamp(37 * FP - players[owner][1], TOP, BOTTOM), SPEED_PI)
        else:
            _move(p, (bx + 120 * FP) // 2, (by + MID_Y) // 2, SPEED_PI)


def _decide(s: dict) -> None:
    """The PI ball carrier shoots or passes; keepers clear the ball."""
    owner, players = s['owner'], s['players']
    if owner in (0, 3):
        s['keeperHold'] += STEP_MS
        if s['keeperHold'] >= KEEPER_HOLD_MS:
            mates = (1, 2) if owner == 0 else (4, 5)
            m = max(mates, key=lambda i: (players[i][0] if owner == 0 else -players[i][0], -i))
            _kick(s, owner, players[m][0] - players[owner][0], players[m][1] - players[owner][1], KICK)
        return
    if owner not in (4, 5):
        return
    p = players[owner]
    if p[0] <= s['shootX']:
        # Aim for the corner away from the keeper, give or take a pixel.
        corner = MOUTH_TOP + 2 * FP if players[0][1] > MID_Y else MOUTH_BOTTOM - 2 * FP
        _kick(s, owner, LEFT - FP - p[0], corner + (s['aimY'] // FP % 3 - 1) * FP - p[1], KICK)
    elif s['pressure'] > 8:
        mate = 9 - owner
        q = players[mate]
        if q[0] < p[0] - 6 * FP:
            _kick(s, owner, q[0] - 6 * FP - p[0], q[1] - p[1], PASS)


def _possession(s: dict) -> None:
    ball, players = s['ball'], s['players']
    owner = s['owner']
    if owner < 0:
        _pickup(s)
        return
    if owner in (0, 3):
        return
    keeper = 3 if owner < 3 else 0
    if players[keeper][4] == 0 and _dist(players[keeper][0], players[keeper][1], ball[0], ball[1]) <= REACH:
        players[owner][4] = LOST_BALL_MS
        s.update(owner=keeper, pressure=0, keeperHold=0)
        return
    rivals = [i for i in ((3, 4, 5) if owner < 3 else (0, 1, 2))
              if i not in (0, 3) and players[i][4] == 0 and _dist(players[i][0], players[i][1], ball[0], ball[1]) <= REACH]
    if not rivals:
        s['pressure'] = 0
        return
    s['pressure'] += 1
    dashing = owner >= 3 and s['dash'] > 0 and s['control'] in rivals
    if dashing:
        s['dash'] = 0
        if _draw(s) % 2:
            players[s['control']][4] = STUMBLE_MS  # a missed tackle: stumble for a moment
            return
    if dashing or s['pressure'] >= (STEAL_STEPS_PI if owner < 3 else STEAL_STEPS_YOU):
        thief = s['control'] if dashing else rivals[0]
        players[owner][4] = LOST_BALL_MS
        s['owner'] = thief
        s['pressure'] = 0
        if _team(thief) == 1:
            _new_possession(s)


def step_soccer(state: dict, held, time: int) -> dict:
    s = _copy(state)
    s['time'] = time
    if s['phase'] == 'goal':
        s['timer'] += STEP_MS
        if s['timer'] >= GOAL_MS:
            scorer_team = 0 if s['banner'] == 'GOAL!' else 1
            if s['golden'] or (s['clock'] <= 0 and s['you'] != s['pi']):
                _finish(s)
                return s
            s.update(phase='play', timer=0, banner='')
            _kickoff(s, 1 - scorer_team)
        return s
    s['clock'] -= STEP_MS
    if s['clock'] <= 0:
        if s['you'] != s['pi'] or s['golden']:
            s['clock'] = 0
            _finish(s)
            return s
        s.update(golden=True, clock=GOLDEN_MS, banner='GOLDEN GOAL', timer=0)
    if s['banner'] and s['phase'] == 'play':
        s['timer'] += STEP_MS
        if s['timer'] >= 1500:
            s['banner'], s['timer'] = '', 0
    s['dash'] = max(0, s['dash'] - STEP_MS)
    s['dashCool'] = max(0, s['dashCool'] - STEP_MS)
    for p in s['players']:
        p[4] = max(0, p[4] - STEP_MS)
    # The field player nearest the ball is the one YOU steer (with a little stickiness).
    if s['owner'] not in (1, 2):
        c, other = s['control'], 3 - s['control']
        bx, by = s['ball'][0], s['ball'][1]
        if _dist(*s['players'][other][:2], bx, by) + 6 * FP < _dist(*s['players'][c][:2], bx, by):
            s['control'] = other
    else:
        s['control'] = s['owner']
    _ai(s, held)
    if s['owner'] in (0, 3):
        # Nobody may crowd a keeper holding the ball: rivals wait outside the box.
        for i in ((4, 5) if s['owner'] == 0 else (1, 2)):
            p = s['players'][i]
            p[0] = max(p[0], 16 * FP) if s['owner'] == 0 else min(p[0], 111 * FP)
    _possession(s)
    _decide(s)
    _ball_physics(s)
    return s


def press_soccer(state: dict, button: str) -> dict:
    if state['status'] != 'running' or state['phase'] != 'play' or button != 'a':
        return state
    s = _copy(state)
    c = s['control']
    if s['owner'] == c:
        p = s['players'][c]
        if p[2] > 0:
            # Facing the goal: shoot at it, high or low corner when steering up or down.
            _kick(s, c, RIGHT + FP - p[0], MID_Y + p[3] * 4 * FP - p[1], KICK)
        else:
            _kick(s, c, p[2] * 256, p[3] * 256, KICK)
    elif s['dashCool'] == 0:
        s['dash'], s['dashCool'] = DASH_MS, DASH_COOL_MS
    else:
        return state
    return s
