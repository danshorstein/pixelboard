"""Household arcade progress: one shared gem jar, style shop and high scores; plus Happy Hour.

There are deliberately no player profiles or names (owner decision). Progress
lives in state/arcade-progress.json so it survives software updates; the file
is small, written only when something changes, and always atomically.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from shared_py.rotation import is_quiet_time

LOGGER = logging.getLogger(__name__)

SCORED_GAMES = ('baseball', 'snake', 'rider', 'bigleague', 'soccer', 'unicorn')  # Pong counts wins instead.
# Item order matches CARS / CAR_COLORS(+rainbow) / THEMES in shared arcade_frame.
SHOP: dict[str, tuple[tuple[str, int], ...]] = {
    'car': (('BUGGY', 0), ('TRUCK', 60), ('LIMO', 90), ('BIKE', 120), ('UFO', 300)),
    'color': (('TEAL', 0), ('RED', 20), ('GOLD', 30), ('LIME', 30), ('BLUE', 30), ('RAINBOW', 150)),
    'theme': (('NEON', 0), ('SUNSET', 50), ('ICE', 70), ('LAVA', 90), ('SPACE', 120), ('BALLPARK', 150)),
}
CATEGORIES = tuple(SHOP)
HAPPY_EVERY_HOURS = 3
HAPPY_MINUTES = 10
HAPPY_MULTIPLIER = 3


def _empty() -> dict[str, Any]:
    return {'version': 2, 'gems': 0, 'owned': [f'{c}:0' for c in CATEGORIES],
            'style': {c: 0 for c in CATEGORIES}, 'best': {g: 0 for g in SCORED_GAMES}, 'pongWins': 0}


class ArcadeProgress:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        data = _empty()
        if self.path is None or not self.path.exists():
            return data
        try:
            saved = json.loads(self.path.read_text())
            if not isinstance(saved, dict) or saved.get('version') != 2:
                raise ValueError('unexpected arcade progress format')
        except (OSError, ValueError) as error:
            # Keep the unreadable file for inspection rather than silently overwriting it.
            LOGGER.error('Arcade progress unreadable (%s); starting fresh', error)
            try:
                self.path.replace(self.path.with_name(self.path.name + '.unreadable'))
            except OSError:
                pass
            return data
        # Start from defaults so fields added later appear with sensible values.
        for key in ('gems', 'pongWins', 'owned'):
            data[key] = saved.get(key, data[key])
        data['style'].update(saved.get('style', {}))
        data['best'].update(saved.get('best', {}))
        return data

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + '.tmp')
        temporary.write_text(json.dumps(self.data, indent=2, sort_keys=True))
        os.replace(temporary, self.path)

    @property
    def style(self) -> dict[str, int]:
        return self.data['style']

    def record(self, game: str, score: int, gems: int = 0, won: bool = False) -> dict[str, Any]:
        """Store one finished (or abandoned) game; returns what to celebrate."""
        result: dict[str, Any] = {'gems': gems}
        self.data['gems'] += gems
        if game == 'pong':
            self.data['pongWins'] += 1 if won else 0
        elif game in SCORED_GAMES:
            result['best'] = score > self.data['best'].get(game, 0)
            self.data['best'][game] = max(score, self.data['best'].get(game, 0))
        self.save()
        return result

    def buy_or_equip(self, category: str, index: int) -> str:
        price = SHOP[category][index][1]
        key = f'{category}:{index}'
        if key not in self.data['owned']:
            if self.data['gems'] < price:
                return 'short'
            self.data['gems'] -= price
            self.data['owned'].append(key)
        self.data['style'][category] = index
        self.save()
        return 'equipped'

    def add_gems(self, amount: int) -> None:
        self.data['gems'] = max(0, self.data['gems'] + amount)
        self.save()

    def reset_scores(self) -> None:
        self.data['best'] = {g: 0 for g in SCORED_GAMES}
        self.data['pongWins'] = 0
        self.save()

    def summary(self) -> dict[str, Any]:
        return {'gems': self.data['gems'], 'best': dict(self.data['best']), 'pongWins': self.data['pongWins'],
                'owned': len(self.data['owned'])}


def happy_hour(now: datetime, quiet_hours: Mapping[str, Any] | None) -> dict[str, Any]:
    """Triple gems for ten minutes every three hours, never inside quiet hours.

    Returns {'active': bool, 'seconds': remaining or until next (None if none soon)}.
    """
    def quiet(moment: datetime) -> bool:
        return is_quiet_time(quiet_hours, {'localTime': moment.strftime('%H:%M')})

    base = now.replace(minute=0, second=0, microsecond=0)
    start = base - timedelta(hours=base.hour % HAPPY_EVERY_HOURS)
    if now < start + timedelta(minutes=HAPPY_MINUTES) and not quiet(start) and not quiet(now):
        return {'active': True, 'seconds': int((start + timedelta(minutes=HAPPY_MINUTES) - now).total_seconds())}
    for step in range(1, 17):
        candidate = start + timedelta(hours=HAPPY_EVERY_HOURS * step)
        if not quiet(candidate):
            return {'active': False, 'seconds': int((candidate - now).total_seconds())}
    return {'active': False, 'seconds': None}
