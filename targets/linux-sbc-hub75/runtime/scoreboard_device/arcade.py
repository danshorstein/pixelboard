"""Remote-controlled arcade takeover. Call under DeviceRuntime.lock.

Screens: menu -> game / shop, or closed during quiet hours. The household
shares one gem jar, style and high score per game (ArcadeProgress); there are
no player profiles. Game rules and pictures stay in shared_py.
"""
from __future__ import annotations

from datetime import datetime
from time import monotonic
from typing import Any, Callable, Mapping

from shared_py.arcade import KINDS, STEP_MS, create_game, press_game, start_game, step_game, steer_snake, swing
from shared_py.arcade_frame import arcade_frame
from shared_py.bdf import BdfFont
from shared_py.renderer import PixelBuffer, _draw_text
from shared_py.rotation import is_quiet_time
from scoreboard_device.arcade_progress import CATEGORIES, HAPPY_MULTIPLIER, SHOP, ArcadeProgress, happy_hour

WHITE, GOLD, TEAL, DIM = (221, 240, 237, 255), (255, 201, 58, 255), (58, 226, 180, 255), (90, 140, 130, 255)
BLACK, GEM = (0, 0, 0, 255), (150, 230, 255, 255)
MENU_ITEMS = KINDS + ('shop',)
LABELS = {'baseball': 'BASEBALL', 'snake': 'SNAKE', 'pong': 'PONG', 'rider': 'NEON RIDER', 'bigleague': 'BIG LEAGUE',
          'soccer': 'SOCCER', 'unicorn': 'RAINBOW UNICORN', 'shop': 'STYLE SHOP'}
BEST_LABELS = {'bigleague': 'MOST RUNS', 'soccer': 'MOST GOALS', 'unicorn': 'MOST STARS'}  # others say HIGH SCORE
ACTION_GAMES = ('bigleague', 'soccer', 'unicorn')  # buttons are passed to press_game
B_ACTION_GAMES = ('unicorn',)  # B is a game button here (bomb); Select still leaves
CLOSED_SECONDS = 4
ROWS = (1, 9, 17, 25)  # four readable 4x6 text rows on a 32-pixel panel


def _duration(seconds: int) -> str:
    if seconds >= 3600:
        return f'{seconds // 3600}H {seconds % 3600 // 60:02d}M'
    return f'{max(1, seconds // 60)} MIN'


class ArcadeController:
    def __init__(self, *, clock: Callable[[], float] = monotonic, idle_seconds: float = 300,
                 store: ArcadeProgress | None = None) -> None:
        self.clock = clock
        self.idle_seconds = idle_seconds
        self.store = store or ArcadeProgress(None)
        self.active = False
        self.screen = 'menu'
        self.selection = 0
        self.notice = ''
        self.shop_category = 0
        self.shop_item = 0
        self.state = create_game(KINDS[0])
        self.paused = False
        self.held: set[str] = set()
        self.last_tick = self.clock()
        self.last_input = self.last_tick
        self.accumulator = 0.0
        self.committed = True
        self.result: dict[str, Any] | None = None
        self.closed_since = 0.0
        self.now: datetime | None = None
        self.quiet_hours: Mapping[str, Any] | None = None

    @property
    def menu(self) -> bool:
        return self.screen != 'game'

    @property
    def quiet(self) -> bool:
        return self.now is not None and is_quiet_time(self.quiet_hours, {'localTime': self.now.strftime('%H:%M')})

    def happy(self) -> dict[str, Any]:
        return happy_hour(self.now, self.quiet_hours) if self.now else {'active': False, 'seconds': None}

    def set_context(self, now: datetime, quiet_hours: Mapping[str, Any] | None) -> None:
        """Wall-clock time and quiet hours from the runtime; quiet hours close the arcade."""
        self.now, self.quiet_hours = now, quiet_hours
        if self.active and self.screen != 'closed' and self.quiet:
            self._close()

    def _close(self) -> None:
        self._commit()
        self.screen, self.paused = 'closed', False
        self.held.clear()
        self.closed_since = self.clock()

    def exit(self) -> None:
        self._commit()
        self.active = False
        self.held.clear()
        self.accumulator = 0

    def suspend(self) -> None:
        self.held.clear()
        self.accumulator = 0
        self.last_tick = self.clock()
        if self.active and self.screen == 'game' and self.state['status'] == 'running':
            self.paused = True

    def _commit(self) -> None:
        """Save one played game to the household progress, once."""
        if self.committed or self.screen != 'game':
            return
        self.committed = True
        if self.state['time'] <= 0:
            return
        kind = self.state['kind']
        won = kind == 'pong' and self.state['playerScore'] >= 5
        self.result = self.store.record(kind, self.state.get('score', 0) if kind != 'pong' else 0,
                                        self.state.get('gems', 0), won)

    def _start(self) -> None:
        kind = MENU_ITEMS[self.selection]
        if kind == 'rider':
            state = create_game(kind, int(self.clock() * 1000))
            state.update(self.store.style)
        else:
            state = create_game(kind)
        self.state = start_game(state)
        self.screen, self.paused = 'game', False
        self.committed, self.result = False, None
        self.accumulator = 0
        self.last_tick = self.clock()

    def tick(self, now: float | None = None) -> None:
        now = self.clock() if now is None else now
        elapsed = max(0, min(250, (now - self.last_tick) * 1000))
        self.last_tick = now
        if not self.active:
            return
        if self.screen == 'closed':
            if now - self.closed_since >= CLOSED_SECONDS:
                self.exit()
            return
        if now - self.last_input >= self.idle_seconds and not self.held:
            self.exit()
            return
        if self.screen == 'game' and self.state['status'] == 'over':
            self._commit()
        if self.screen != 'game' or self.paused or self.state['status'] != 'running':
            self.accumulator = 0
            return
        if 'gemValue' in self.state:
            self.state['gemValue'] = HAPPY_MULTIPLIER if self.happy()['active'] else 1
        self.accumulator += elapsed
        while self.accumulator + 1e-7 >= STEP_MS:
            self.state = step_game(self.state, self.held)
            self.accumulator -= STEP_MS
        if self.state['status'] == 'over':
            self._commit()

    def input(self, button: str, pressed: bool) -> bool:
        now = self.clock()
        self.tick(now)
        if not self.active:
            if button != 'select' or not pressed:
                return False
            self.active, self.paused = True, False
            self.last_input = now
            self.held.clear()
            if self.quiet:
                self._close()
                return True
            self.screen, self.notice = 'menu', ''
            return True
        self.last_input = now
        if not pressed:
            self.held.discard(button)
            return True
        if button == 'select' or self.screen == 'closed':
            self.exit()
            return True
        handler = getattr(self, f'_input_{self.screen}')
        handler(button)
        return True

    def _input_menu(self, button: str) -> None:
        if button in ('up', 'left', 'l'):
            self.selection = (self.selection - 1) % len(MENU_ITEMS)
        elif button in ('down', 'right', 'r'):
            self.selection = (self.selection + 1) % len(MENU_ITEMS)
        elif button == 'b':
            self.exit()
        elif button in ('a', 'start'):
            item = MENU_ITEMS[self.selection]
            if item == 'shop':
                self.screen, self.notice = 'shop', ''
                self.shop_item = self.store.style[CATEGORIES[self.shop_category]]
            else:
                self._start()
                if button == 'a' and item == 'rider':
                    self.held.add('a')  # holding A from the menu drives straight away

    def _input_shop(self, button: str) -> None:
        self.notice = ''
        category = CATEGORIES[self.shop_category]
        if button in ('up', 'down'):
            self.shop_category = (self.shop_category + (1 if button == 'down' else -1)) % len(CATEGORIES)
            self.shop_item = self.store.style[CATEGORIES[self.shop_category]]
        elif button in ('left', 'right'):
            self.shop_item = (self.shop_item + (1 if button == 'right' else -1)) % len(SHOP[category])
        elif button == 'b':
            self.screen = 'menu'
        elif button in ('a', 'start'):
            if self.store.buy_or_equip(category, self.shop_item) == 'short':
                self.notice = 'NEED MORE GEMS'

    def _input_game(self, button: str) -> None:
        if button == 'b' and self.state['kind'] in B_ACTION_GAMES and self.state['status'] == 'running' and not self.paused:
            self.state = press_game(self.state, button)
            return
        if button == 'b':
            self._commit()
            self.screen = 'menu'
            self.held.clear()
            return
        if self.state['kind'] in ACTION_GAMES and self.state['status'] == 'running' and not self.paused \
                and button in ('a', 'l', 'r', 'up', 'down', 'left', 'right'):
            if button not in ('a', 'l', 'r'):
                self.held.add(button)
            self.state = press_game(self.state, button)
            return
        if button in ('up', 'down', 'left', 'right'):
            self.held.add(button)
            if self.state['kind'] == 'snake' and not self.paused:
                self.state = steer_snake(self.state, button)
        elif button == 'x':
            self._commit()
            self._start()
            self.state = dict(self.state, status='ready', message='PRESS START')
            self.held.clear()
        elif button == 'start':
            if self.state['status'] != 'running':
                self._start()
            else:
                self.paused = not self.paused
            self.held.clear()
            self.accumulator = 0
        elif button == 'a':
            if self.state['status'] != 'running':
                self._start()
            elif self.paused:
                self.paused = False
                self.held.clear()
                self.accumulator = 0
            elif self.state['kind'] == 'baseball':
                self.state = swing(self.state)
            if self.state['kind'] == 'rider' and not self.paused:
                self.held.add('a')  # Rider accelerates and flips while A is held.

    # Pictures -----------------------------------------------------------

    def frame(self, font: BdfFont) -> PixelBuffer:
        if self.screen == 'game':
            return self._game_frame(font)
        if self.screen == 'shop':
            return self._shop_frame(font)
        frame = PixelBuffer(128, 32)
        lines = getattr(self, f'_{self.screen}_lines')()
        for row, line in zip(ROWS, lines):
            if line:
                text, color = line
                _draw_text(frame, font, text, 64, row, color, align='center')
        return frame

    def _closed_lines(self):
        return ('ARCADE CLOSED', GOLD), ('QUIET HOURS', WHITE), ('SEE YOU TOMORROW!', TEAL), None

    def _menu_lines(self):
        item = MENU_ITEMS[self.selection]
        if item == 'pong':
            info = f"WINS {self.store.data['pongWins']}   FIRST TO 5"
        elif item in KINDS:
            info = f"{BEST_LABELS.get(item, 'HIGH SCORE')} {self.store.data['best'].get(item, 0)}"
        else:
            info = 'SPEND YOUR GEMS'
        happy = self.happy()
        if happy['active']:
            footer = (f"HAPPY HOUR! 3X GEMS {happy['seconds'] // 60}:{happy['seconds'] % 60:02d}", GOLD)
        elif happy['seconds'] is not None:
            footer = (f"HAPPY HOUR IN {_duration(happy['seconds'])}", DIM)
        else:
            footer = ('A PLAY   B EXIT', DIM)
        return (f"PIXELBOARD ARCADE  {self.store.data['gems']} GEMS", TEAL), (f'< {LABELS[item]} >', GOLD), (info, WHITE), footer

    def _game_frame(self, font: BdfFont) -> PixelBuffer:
        frame = arcade_frame(self.state, font, self.paused)
        if self.state['status'] == 'over' and self.result:
            parts = []
            if self.result.get('best'):
                parts.append('NEW HIGH SCORE!')
            if self.result.get('gems'):
                parts.append(f"+{self.result['gems']} GEMS")
            if parts:
                frame.fill_rect(0, 24, 128, 8, BLACK)
                _draw_text(frame, font, '  '.join(parts), 64, 25, GOLD, align='center')
        return frame

    def _shop_frame(self, font: BdfFont) -> PixelBuffer:
        category = CATEGORIES[self.shop_category]
        style = dict(self.store.style)
        style[category] = self.shop_item
        preview = start_game(create_game('rider'))
        preview.update(style, time=int(self.clock() * 1000) % 1_000_000)
        frame = arcade_frame(preview, font)
        frame.fill_rect(0, 0, 128, 14, BLACK)
        name, price = SHOP[category][self.shop_item]
        _draw_text(frame, font, f'{category.upper()} < {name} >', 64, 1, GOLD, align='center')
        if self.notice:
            status, color = self.notice, WHITE
        elif self.store.style[category] == self.shop_item:
            status, color = 'IN USE', TEAL
        elif f'{category}:{self.shop_item}' in self.store.data['owned']:
            status, color = 'OWNED  A TO USE', TEAL
        else:
            status, color = f"COST {price}  YOU HAVE {self.store.data['gems']}", WHITE
        _draw_text(frame, font, status, 64, 8, color, align='center')
        return frame

    def status(self) -> dict:
        game = MENU_ITEMS[self.selection]
        return {'available': not self.quiet, 'active': self.active, 'menu': self.menu, 'screen': self.screen,
                'game': game, 'paused': self.paused,
                'gameStatus': self.state['status'], 'heldButtons': sorted(self.held),
                'score': self.state.get('score', self.state.get('playerScore', 0)),
                'happyHour': self.happy(), **self.store.summary()}
