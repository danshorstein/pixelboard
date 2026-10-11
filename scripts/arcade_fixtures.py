#!/usr/bin/env python3
"""Check, regenerate and preview arcade replay fixtures.

fixtures/arcade-replays.json holds deterministic replays shared by the Python
tests, the TypeScript tests and the Pi installer's verification. Each case is
replayed from its seed/patch/operations; its final state and frame hash are
the expectation. TypeScript must reproduce both exactly (npm test).

  scripts/arcade_fixtures.py                      # check every case
  scripts/arcade_fixtures.py --update rider-crash # rewrite named cases only
  scripts/arcade_fixtures.py --update-missing     # fill cases lacking expectations
  scripts/arcade_fixtures.py --preview out.png --kind rider

To add a case, append {"name", "kind", "operations", optional "seed",
"patch", "paused"} to the JSON, then run --update-missing. Never bulk-update
cases for a game you did not mean to change: a changed hash there is a bug.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared_py.arcade import create_game, press_game, start_game, steer_snake, step_game, swing  # noqa: E402
from shared_py.arcade_frame import arcade_frame  # noqa: E402
from shared_py.bdf import parse_bdf  # noqa: E402
from shared_py.png import encode_rgba_png  # noqa: E402

FIXTURES = ROOT / 'fixtures/arcade-replays.json'
FONT = ROOT / 'definition/mlb-classic/fonts/4x6.bdf'


def replay(case: dict) -> dict:
    state = create_game(case['kind'], case.get('seed', 727))
    state.update(case.get('patch', {}))
    for op in case['operations']:
        action = op.get('action')
        if action == 'start':
            state = start_game(state)
        elif action == 'swing':
            state = swing(state)
        elif action in ('up', 'down', 'left', 'right'):
            state = steer_snake(state, action)
        if op.get('press'):
            state = press_game(state, op['press'])
        for _ in range(op.get('ticks', 0)):
            state = step_game(state, set(op.get('held', [])))
    return state


def render(case: dict, state: dict, font):
    return arcade_frame(state, font, case.get('paused', False))


def contact_sheet(frames: list, scale: int = 4, gap: int = 2) -> bytes:
    """Two-column, nearest-neighbour enlargement of 128x32 frames as PNG."""
    cols = 2
    rows = (len(frames) + cols - 1) // cols
    width, height = cols * 128 * scale + gap, rows * (32 * scale + gap)
    data = bytearray([40, 40, 40, 255] * width * height)
    for i, frame in enumerate(frames):
        ox, oy = (i % cols) * (128 * scale + gap), (i // cols) * (32 * scale + gap)
        for y in range(32 * scale):
            for x in range(128 * scale):
                src = ((y // scale) * 128 + x // scale) * 4
                dst = ((oy + y) * width + ox + x) * 4
                data[dst:dst + 4] = frame.data[src:src + 4]
    return encode_rgba_png(width, height, bytes(data))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--update', nargs='*', default=[], metavar='NAME', help='rewrite these cases')
    parser.add_argument('--update-missing', action='store_true', help='fill cases without expectations')
    parser.add_argument('--preview', metavar='PNG', help='write a scaled contact sheet')
    parser.add_argument('--kind', help='limit --preview to one game kind')
    parser.add_argument('--names', nargs='*', default=[], help='limit --preview to these cases')
    args = parser.parse_args()

    font = parse_bdf(FONT.read_text())
    cases = json.loads(FIXTURES.read_text())
    unknown = set(args.update) - {c['name'] for c in cases}
    if unknown:
        print(f'unknown cases: {sorted(unknown)}', file=sys.stderr)
        return 2
    changed, failures, frames = [], [], []
    for case in cases:
        state = replay(case)
        digest = hashlib.sha256(render(case, state, font).data).hexdigest()
        if case['name'] in args.update or (args.update_missing and 'sha256' not in case):
            case['expectedState'], case['sha256'] = state, digest
            changed.append(case['name'])
        elif case.get('expectedState') != state or case.get('sha256') != digest:
            failures.append(case['name'])
        if args.preview and (not args.kind or case['kind'] == args.kind) and (not args.names or case['name'] in args.names):
            frames.append(render(case, state, font))
    if changed:
        FIXTURES.write_text(json.dumps(cases, indent=2) + '\n')
        print(f'updated {len(changed)}: {", ".join(changed)}')
    if args.preview:
        Path(args.preview).write_bytes(contact_sheet(frames))
        print(f'preview of {len(frames)} frames: {args.preview}')
    print(f'{len(cases)} cases, {len(failures)} mismatched' + (f': {", ".join(failures)}' if failures else ''))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
