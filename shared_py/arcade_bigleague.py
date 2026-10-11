"""Big League baseball rules, mirrored line for line in shared_ts/arcade_bigleague.ts.

The player team bats in the top of each inning from a view behind
the batter, then pitches in the bottom. A batted ball switches to a top-down
field view where fielders chase it, throw to bases and runners advance.

All state is integers so both languages agree exactly. Field positions are in
1/64 ft with home plate at (0, 0), x toward the first-base side and y toward
centre field. Runners are a distance along the base path (0 = home,
4 * BASE = home again) with the base they are heading for.
"""
from __future__ import annotations

import math
from typing import Any

STEP_MS = 20
U = 64  # 1/64 ft
INNINGS = 3
MAX_INNINGS = 6  # still tied after this: TIE GAME
RUN_LIMIT = 6  # runs per half inning, so a lopsided half never drags on
BASE = 90 * U
BASES = ((0, 0), (4073, 4073), (0, 8146), (-4073, 4073))  # home, 1B, 2B, 3B
# Fielders: P, C, 1B, 2B, 3B, SS, LF, CF, RF.
POSITIONS = ((0, 3840), (0, -256), (4352, 5632), (2048, 8960), (-4352, 5632), (-2048, 8960),
             (-9600, 14720), (0, 18560), (9600, 14720))
RUNNER, FIELDER, OUTFIELDER, THROW = 50, 26, 34, 90  # speeds per 20 ms step
REACT_MS = 240  # fielders start moving after this
RISK = 20  # steps a runner will gamble when deciding to take an extra base
GRAVITY = 3
FENCE = 330 * U
WALL = 10 * U
REACH = 3 * U
CATCH_Z = 7 * U
GLOVE_Z = 4 * U
PITCHES = (('FAST', 820), ('CURVE', 1000), ('CHANGE', 1150))  # name, ms from release to the plate
WAIT_MS = 900  # pitcher sets, the last 400 ms are the windup
WINDUP_MS = 400
CALL_MS = 800
PLAY_RESULT_MS = 1800
SWITCH_MS = 4000
METER_MS = 2000  # the pitch goes by itself if A is not pressed again
SIN5 = (0, 22, 44, 66, 88, 108, 128, 147, 165, 181)  # sin/cos of 0..45 degrees in 5 degree steps, x256
COS5 = (256, 255, 252, 247, 241, 232, 222, 210, 196, 181)


def _rand(seed: int) -> int:
    return (seed * 1664525 + 1013904223) & 0xffffffff


def _draw(s: dict) -> int:
    s['seed'] = _rand(s['seed'])
    return s['seed'] >> 8


def _isqrt(n: int) -> int:
    return math.isqrt(n) if n > 0 else 0


def _dist(ax: int, ay: int, bx: int, by: int) -> int:
    return _isqrt((ax - bx) * (ax - bx) + (ay - by) * (ay - by))


def _toward(x: int, y: int, tx: int, ty: int, speed: int) -> tuple[int, int]:
    dx, dy = tx - x, ty - y
    d = _isqrt(dx * dx + dy * dy)
    if d <= speed:
        return tx, ty
    return x + dx * speed // d, y + dy * speed // d


def _shrink(v: int, num: int, den: int) -> int:
    """Scale toward zero (floor division alone never lets negatives reach 0)."""
    return v * num // den if v >= 0 else 0 - (-v * num // den)


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def base_point(pos: int) -> tuple[int, int]:
    """Field position of a runner at distance pos along the base path."""
    leg = _clamp(pos // BASE, 0, 3)
    t = pos - leg * BASE
    ax, ay = BASES[leg]
    bx, by = BASES[(leg + 1) % 4]
    return ax + (bx - ax) * t // BASE, ay + (by - ay) * t // BASE


def create_bigleague(base: dict) -> dict[str, Any]:
    return dict(base, inning=1, half=0, outs=0, balls=0, strikes=0, you=0, pi=0, lineYou=[0], linePi=[],
                phase='switch', view='bat', timer=0, call='', pitchType=0, pitchCol=0, pitchRow=0, pitchMs=820,
                pitchT=-1, aimCol=0, aimRow=0, meter=-1, swing=-1, cpuSwing=-1,
                ball=[0, 0, 0, 0, 0, 0], landed=False, holder=-1, throwTo=-1, chaser=-1, target=[0, 0],
                fielders=[list(p) for p in POSITIONS], runners=[], hold=0, settle=0, homer=False, caught=False,
                batterOut=False, batterHome=False, playOuts=0, playRuns=0,
                score=0, gems=0, gemValue=1)


def _copy(state: dict) -> dict:
    return dict(state, lineYou=state['lineYou'][:], linePi=state['linePi'][:], ball=state['ball'][:],
                target=state['target'][:], fielders=[f[:] for f in state['fielders']],
                runners=[r[:] for r in state['runners']])


# Pitches --------------------------------------------------------------------

def _release(s: dict, kind: int, col: int, row: int) -> None:
    s.update(phase='pitch', pitchType=kind, pitchCol=col, pitchRow=row, pitchMs=PITCHES[kind][1],
             pitchT=0, swing=-1, cpuSwing=-1, call='', timer=0)
    if s['half'] == 1:
        # The computer batter decides now: it chases fewer balls than strikes, and only
        # times a pitch well when it guessed the speed.
        r = _draw(s)
        in_zone = abs(col) <= 1 and abs(row) <= 1
        if r % 100 < (68 if in_zone else 22):
            guess = PITCHES[0][1] if (r >> 7) % 100 < 55 else PITCHES[2][1]
            if (r >> 14) % 2 == 0:
                guess = s['pitchMs']
            noise = (r >> 15) % 141 - 70
            s['cpuSwing'] = max(200, s['pitchMs'] + (guess - s['pitchMs']) // 2 + noise)


def _cpu_pitch(s: dict) -> None:
    r = _draw(s)
    kind = 0 if r % 100 < 50 else 1 if r % 100 < 75 else 2
    if (r >> 7) % 100 < 62:
        col, row = (r >> 12) % 3 - 1, (r >> 14) % 3 - 1
    else:
        other = (r >> 14) % 3 - 1
        col, row = ((-2, other), (2, other), (other, -2), (other, 2))[(r >> 12) % 4]
    _release(s, kind, col, row)


def meter_value(timer: int) -> int:
    """Pitching meter 0..100..0 once a second; 50 is a perfect release."""
    t = timer % 1000
    return t // 5 if t < 500 else (1000 - t) // 5


def _kid_pitch(s: dict, m: int) -> None:
    error = abs(m - 50)
    r = _draw(s)
    dc = dr = 0
    if error > 30:
        dc, dr = r % 3 - 1, (r >> 4) % 3 - 1
        if dc == 0 and dr == 0:
            dc = 1
    elif error > 12:
        dc, dr = ((1, 0), (-1, 0), (0, 1), (0, -1))[r % 4]
    s['meter'] = m
    _release(s, s['pitchType'], _clamp(s['aimCol'] + dc, -2, 2), _clamp(s['aimRow'] + dr, -2, 2))


def _contact(s: dict, early_late: int, miss_by: int) -> None:
    """Resolve a swing `early_late` ms from the plate, `miss_by` zone cells from where the bat went."""
    r = _draw(s)
    off = abs(early_late)
    s['swing'] = 0
    if miss_by >= 2 or off > 170:
        return
    if off > 120:
        _call(s, 'foul')
        return
    quality = (100 if off <= 35 else 100 - (off - 35) * 5 // 7) - 25 * miss_by + r % 21 - 10
    angle = _clamp(early_late * 8 // 120 + (r >> 5) % 5 - 2, -8, 8)  # early pulls to left field
    roll = (r >> 9) % 100
    if quality >= 88:
        kind = 'fly' if roll < 70 else 'line'
    elif quality >= 60:
        kind = 'line' if roll < 50 else 'fly' if roll < 75 else 'ground'
    else:
        kind = 'ground' if roll < 65 else 'pop'
    speed, vz = {'ground': (70 + quality, 6), 'line': (90 + quality, 45 + (r >> 16) % 20),
                 'fly': (100 + quality, 120 + quality // 2), 'pop': (25, 150)}[kind]
    vx = speed * SIN5[abs(angle)] // 256
    s['ball'] = [0, 0, 3 * U, vx if angle >= 0 else 0 - vx, speed * COS5[abs(angle)] // 256, vz]
    s.update(phase='play', view='field', timer=0, landed=False, holder=-1, throwTo=-1, hold=0, settle=0,
             homer=False, caught=False, batterOut=False, batterHome=False, playOuts=0, playRuns=0, call='')
    s['fielders'] = [list(p) for p in POSITIONS]
    for runner in s['runners']:
        runner[2] = runner[1]
        runner[1] += BASE  # everyone runs on contact
    s['runners'].append([0, BASE, 0])
    _plan(s)


def _call(s: dict, what: str) -> None:
    """Ball, strike or foul without a ball in play."""
    s.update(phase='result', view='bat', timer=0)
    if what == 'foul':
        s['strikes'] = min(2, s['strikes'] + 1)
        s['call'] = 'FOUL BALL'
    elif what == 'strike':
        s['strikes'] += 1
        s['call'] = f"STRIKE {s['strikes']}"
        if s['strikes'] >= 3:
            s['outs'] += 1
            s['call'] = 'STRIKEOUT!'
            s['balls'] = s['strikes'] = 0
    else:
        s['balls'] += 1
        s['call'] = f"BALL {s['balls']}"
        if s['balls'] >= 4:
            s['call'] = 'WALK'
            s['balls'] = s['strikes'] = 0
            _walk(s)


def _walk(s: dict) -> None:
    occupied = {r[1] for r in s['runners']}
    for b in (3, 2, 1):
        if all(k * BASE in occupied for k in range(1, b + 1)):
            for r in s['runners']:
                if r[1] == b * BASE:
                    r[0] = r[1] = r[2] = (b + 1) * BASE
    s['runners'].append([BASE, BASE, BASE])
    _score_runners(s)


def _score(s: dict, runs: int) -> None:
    if runs <= 0:
        return
    team = 'you' if s['half'] == 0 else 'pi'
    s[team] += runs
    line = s['lineYou'] if s['half'] == 0 else s['linePi']
    line[-1] += runs
    s['playRuns'] += runs
    if s['half'] == 0:
        s['score'] = s['you']
        s['gems'] += 3 * runs * s['gemValue']


def _score_runners(s: dict) -> None:
    home = [r for r in s['runners'] if r[0] >= 4 * BASE]
    if any(r[2] == 0 for r in home):
        s['batterHome'] = True
    s['runners'] = [r for r in s['runners'] if r[0] < 4 * BASE]
    _score(s, len(home))


# Ball in play ---------------------------------------------------------------

def _fly(ball: list, landed: bool) -> tuple[list, bool, str]:
    x, y, z, vx, vy, vz = ball
    if z > 0 or vz > 0:
        vz -= GRAVITY
        z += vz
        if z <= 0:
            z, landed = 0, True
            if vz < -12:
                vz = -vz * 2 // 5
                vx, vy = _shrink(vx, 7, 10), _shrink(vy, 7, 10)
            else:
                vz = 0
    else:
        vx, vy = _shrink(vx, 31, 32), _shrink(vy, 31, 32)
    nx, ny, event = x + vx, y + vy, ''
    if nx * nx + ny * ny > FENCE * FENCE:
        if z > WALL and not landed:
            event = 'homer'
        else:
            event = 'wall'
            nx, ny, vx, vy = x, y, _shrink(-vx, 1, 3), _shrink(-vy, 1, 3)
    return [nx, ny, z, vx, vy, vz], landed, event


def _plan(s: dict) -> None:
    """Pick the fielder who can reach the ball first and where."""
    ball, landed = s['ball'][:], s['landed']
    for t in range(1, 400):
        ball, landed, event = _fly(ball, landed)
        if event == 'homer':
            break
        if ball[2] > CATCH_Z:
            continue
        for f, (fx, fy) in enumerate(s['fielders']):
            if f == 1 and ball[0] * ball[0] + ball[1] * ball[1] > 3840 * 3840:
                continue  # the catcher only chases balls near the plate
            if _dist(fx, fy, ball[0], ball[1]) - REACH <= _speed(f) * t:
                s['chaser'], s['target'] = f, [ball[0], ball[1]]
                return
        if ball[3] == 0 and ball[4] == 0 and ball[2] == 0:
            break
    nearest = min(range(9), key=lambda f: (_dist(*s['fielders'][f], ball[0], ball[1]), f))
    s['chaser'], s['target'] = nearest, [ball[0], ball[1]]


def _speed(f: int) -> int:
    return OUTFIELDER if f >= 6 else FIELDER


def _covers(s: dict) -> tuple[int, int, int, int]:
    """Fielder covering home, first, second and third."""
    chaser = s['chaser']
    first = 0 if chaser == 2 else 2
    second = 3 if s['ball'][0] < 0 else 5
    if second == chaser:
        second = 5 if second == 3 else 3
    third = 5 if chaser == 4 else 4
    if third == second:
        third = 0
    return 1, first, second, third


def _out(s: dict, runner: list) -> None:
    s['runners'] = [r for r in s['runners'] if r is not runner]
    s['outs'] += 1
    s['playOuts'] += 1
    if runner[2] == 0 and runner[0] < 4 * BASE:
        s['batterOut'] = True


def _send(s: dict, runner: list) -> bool:
    nxt = runner[1] + BASE
    if runner[0] != runner[1] or runner[1] >= 4 * BASE or any(r[1] == nxt for r in s['runners']):
        return False
    runner[1] = nxt
    return True


def _auto_running(s: dict) -> None:
    """Runners take an extra base by themselves when the ball is far enough away."""
    for runner in sorted(s['runners'], key=lambda r: -r[1]):
        if runner[0] != runner[1] or runner[1] >= 4 * BASE:
            continue
        bx, by = BASES[(runner[1] // BASE + 1) % 4]
        bx0, by0 = s['ball'][0], s['ball'][1]
        if s['holder'] >= 0:
            fx, fy = s['fielders'][s['holder']]
            ball_time = _dist(fx, fy, bx, by) // THROW + 4
        elif s['throwTo'] >= 0:
            tx, ty = BASES[s['throwTo'] % 4]
            ball_time = (_dist(bx0, by0, tx, ty) + _dist(tx, ty, bx, by)) // THROW + 4
        else:
            cx, cy = s['fielders'][s['chaser']]
            ball_time = _dist(cx, cy, bx0, by0) // _speed(s['chaser']) + _dist(bx0, by0, bx, by) // THROW + 8
        if BASE // RUNNER < ball_time + RISK:
            _send(s, runner)


def _decide_throw(s: dict) -> None:
    fx, fy = s['fielders'][s['holder']]
    best, best_target, lead = -1, -1, -1
    for runner in s['runners']:
        if runner[0] == runner[1]:
            continue
        b = runner[1] // BASE
        lead = max(lead, b)
        bx, by = BASES[b % 4]
        throw = _dist(fx, fy, bx, by)
        if throw <= REACH:
            continue  # already standing on that base: the runner is tagged on arrival
        if (throw + THROW - 1) // THROW + 2 < (abs(runner[1] - runner[0]) + RUNNER - 1) // RUNNER and runner[1] > best_target:
            best, best_target = b, runner[1]
    if best < 0 and fx * fx + fy * fy > 8320 * 8320:
        best = lead if lead >= 0 else 2  # from deep, hold the lead runner or return the ball to second
    if best >= 0:
        s['throwTo'], s['holder'] = best, -1
        s['ball'] = [fx, fy, GLOVE_Z, 0, 0, 0]


def _end_play(s: dict) -> None:
    if s['homer']:
        for runner in s['runners']:
            runner[0] = 4 * BASE
        _score_runners(s)
        call = 'GRAND SLAM!' if s['playRuns'] == 4 else 'HOME RUN!'
    elif s['batterOut']:
        call = 'TRIPLE PLAY!' if s['playOuts'] >= 3 else 'DOUBLE PLAY!' if s['playOuts'] == 2 else 'CAUGHT!' if s['caught'] else 'OUT!'
    elif s['batterHome']:
        call = 'HOME RUN!'
    else:
        batter = [r for r in s['runners'] if r[2] == 0]
        call = ('SINGLE!', 'DOUBLE!', 'TRIPLE!')[_clamp(batter[0][1] // BASE, 1, 3) - 1] if batter else 'SAFE!'
    if s['playRuns'] and not s['homer']:
        call += f" +{s['playRuns']}"
    for runner in s['runners']:
        runner[0] = runner[2] = runner[1]
    s.update(phase='result', timer=0, call=call, holder=-1, throwTo=-1, balls=0, strikes=0)


def _step_play(s: dict) -> None:
    s['timer'] += STEP_MS
    if s['homer']:
        s['ball'][0] += s['ball'][3]
        s['ball'][1] += s['ball'][4]
        for runner in s['runners']:
            runner[0] = min(runner[0] + RUNNER, runner[1])
        if s['timer'] >= 1500:
            _end_play(s)
        return
    if s['holder'] >= 0:
        fx, fy = s['fielders'][s['holder']]
        s['ball'] = [fx, fy, GLOVE_Z, 0, 0, 0]
    elif s['throwTo'] >= 0:
        b = s['throwTo']
        bx, by = BASES[b % 4]
        x, y = _toward(s['ball'][0], s['ball'][1], bx, by, THROW)
        s['ball'] = [x, y, GLOVE_Z, 0, 0, 0]
        if (x, y) == (bx, by):
            s['holder'], s['throwTo'], s['hold'] = _covers(s)[b % 4], -1, 6
            s['fielders'][s['holder']] = [bx, by]
            for runner in [r for r in s['runners'] if r[1] == b * BASE and r[0] != r[1]]:
                _out(s, runner)
    else:
        s['ball'], s['landed'], event = _fly(s['ball'], s['landed'])
        if event == 'homer':
            s['homer'], s['timer'] = True, 0
            for runner in s['runners']:
                runner[1] = 4 * BASE
            return
        if event == 'wall':
            _plan(s)
    covers = _covers(s)
    free = s['holder'] < 0 and s['throwTo'] < 0
    for f in range(9):
        if f == s['holder'] or s['timer'] <= REACT_MS:
            continue
        x, y = s['fielders'][f]
        if f == s['chaser'] and free:
            tx, ty = (s['target'] if [x, y] != s['target'] else s['ball'][:2])
        elif f in covers:
            tx, ty = BASES[covers.index(f)]
        else:
            tx, ty = POSITIONS[f]
        s['fielders'][f] = list(_toward(x, y, tx, ty, _speed(f)))
    bx, by = s['ball'][0] - s['target'][0], s['ball'][1] - s['target'][1]
    if free and bx * s['ball'][3] + by * s['ball'][4] > 0 and bx * bx + by * by > REACH * REACH:
        _plan(s)  # the ball got past the chaser's spot: whoever can reach it next takes over
    if free and s['ball'][2] <= CATCH_Z:
        order = [s['chaser']] + [f for f in range(9) if f != s['chaser']]
        for f in order:
            fx, fy = s['fielders'][f]
            if _dist(fx, fy, s['ball'][0], s['ball'][1]) <= REACH:
                s['holder'], s['hold'] = f, 6
                if not s['landed']:
                    s['caught'] = True
                    batter = [r for r in s['runners'] if r[2] == 0]
                    if batter:
                        _out(s, batter[0])
                    for runner in s['runners']:
                        runner[1] = runner[2]  # tag up: everyone goes back
                break
    _auto_running(s)
    holder_base = -1
    if s['holder'] >= 0:
        fx, fy = s['fielders'][s['holder']]
        holder_base = next((b for b in range(4) if _dist(fx, fy, *BASES[b]) <= REACH), -1)
    for runner in list(s['runners']):
        if runner[0] == runner[1]:
            continue
        step = RUNNER if runner[1] > runner[0] else -RUNNER
        runner[0] = min(runner[0] + step, runner[1]) if step > 0 else max(runner[0] + step, runner[1])
        if runner[0] == runner[1] and holder_base >= 0 and runner[1] // BASE % 4 == holder_base:
            _out(s, runner)
    _score_runners(s)
    if s['outs'] >= 3:
        _end_play(s)
        return
    if s['holder'] >= 0 and s['throwTo'] < 0:
        if s['hold'] > 0:
            s['hold'] -= 1
        else:
            _decide_throw(s)
    if s['holder'] >= 0 and all(r[0] == r[1] for r in s['runners']):
        s['settle'] += 1
        if s['settle'] >= 30:
            _end_play(s)
    else:
        s['settle'] = 0
    if s['timer'] >= 20000 and s['phase'] == 'play':
        _end_play(s)


# Innings --------------------------------------------------------------------

def _start_half(s: dict) -> None:
    s.update(outs=0, balls=0, strikes=0, runners=[], phase='switch', view='bat', timer=0, call='',
             fielders=[list(p) for p in POSITIONS], meter=-1, pitchT=-1, swing=-1)


def _finish(s: dict) -> None:
    you, pi = s['you'], s['pi']
    if you > pi:
        s['message'] = f'YOU WIN {you}-{pi}'
        s['gems'] += 10 * s['gemValue']
    elif pi > you:
        s['message'] = f'PI WINS {pi}-{you}'
    else:
        s['message'] = f'TIE GAME {you}-{pi}'
    s['status'] = 'over'


def _after_result(s: dict) -> None:
    final = s['inning'] >= INNINGS
    if s['half'] == 1 and final and s['pi'] > s['you']:
        _finish(s)  # walk-off
        return
    half_runs = (s['lineYou'] if s['half'] == 0 else s['linePi'])[-1]
    if s['outs'] < 3 and half_runs < RUN_LIMIT:
        s.update(phase='wait' if s['half'] == 0 else 'aim', timer=0, call='', view='bat', pitchT=-1, swing=-1, meter=-1)
        return
    if s['half'] == 0:
        if final and s['pi'] > s['you']:
            _finish(s)
            return
        s['half'] = 1
        s['linePi'].append(0)
    else:
        if final and s['you'] != s['pi'] or s['inning'] >= MAX_INNINGS:
            _finish(s)
            return
        s['inning'] += 1
        s['half'] = 0
        s['lineYou'].append(0)
    _start_half(s)


def step_bigleague(state: dict, time: int) -> dict:
    s = _copy(state)
    s['time'] = time
    phase = s['phase']
    if phase == 'wait':
        s['timer'] += STEP_MS
        if s['timer'] >= WAIT_MS:
            _cpu_pitch(s)
    elif phase == 'meter':
        s['timer'] += STEP_MS
        if s['timer'] >= METER_MS:
            _kid_pitch(s, meter_value(s['timer']))
    elif phase == 'pitch':
        s['pitchT'] += STEP_MS
        if s['swing'] >= 0:
            s['swing'] += STEP_MS
        if s['cpuSwing'] >= 0 and s['swing'] < 0 and s['pitchT'] >= s['cpuSwing']:
            _contact(s, s['pitchT'] - s['pitchMs'], max(abs(s['pitchCol']), abs(s['pitchRow'])))
        elif s['pitchT'] >= s['pitchMs'] + 120:
            swung = s['swing'] >= 0
            _call(s, 'strike' if swung or (abs(s['pitchCol']) <= 1 and abs(s['pitchRow']) <= 1) else 'ball')
    elif phase == 'play':
        _step_play(s)
    elif phase == 'result':
        s['timer'] += STEP_MS
        if s['timer'] >= (PLAY_RESULT_MS if s['view'] == 'field' else CALL_MS):
            _after_result(s)
    elif phase == 'switch':
        s['timer'] += STEP_MS
        if s['timer'] >= SWITCH_MS:
            s.update(phase='wait' if s['half'] == 0 else 'aim', timer=0)
    return s


def press_bigleague(state: dict, button: str) -> dict:
    if state['status'] != 'running':
        return state
    s = _copy(state)
    phase, batting = s['phase'], s['half'] == 0
    limit = 1 if batting else 2
    moves = {'up': (0, -1), 'down': (0, 1), 'left': (-1, 0), 'right': (1, 0)}
    if button in moves and phase in ('wait', 'pitch', 'aim', 'result', 'switch'):
        dc, dr = moves[button]
        s['aimCol'] = _clamp(s['aimCol'] + dc, -limit, limit)
        s['aimRow'] = _clamp(s['aimRow'] + dr, -limit, limit)
    elif button in ('l', 'r') and not batting and phase == 'aim':
        s['pitchType'] = (s['pitchType'] + (1 if button == 'r' else 2)) % 3
    elif button == 'a':
        if phase == 'switch':
            s.update(phase='wait' if batting else 'aim', timer=0)
        elif batting and phase == 'pitch' and s['swing'] < 0:
            miss_by = max(abs(s['pitchCol'] - s['aimCol']), abs(s['pitchRow'] - s['aimRow']))
            _contact(s, s['pitchT'] - s['pitchMs'], miss_by)
        elif batting and phase == 'play':
            for runner in sorted(s['runners'], key=lambda r: -r[1]):
                _send(s, runner)
        elif not batting and phase == 'aim':
            s.update(phase='meter', timer=0)
        elif not batting and phase == 'meter':
            _kid_pitch(s, meter_value(s['timer']))
        else:
            return state
    else:
        return state
    return s
