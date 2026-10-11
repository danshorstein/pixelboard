"""Temporary past-score browsing, independent of live data and rotation."""
from __future__ import annotations
from datetime import date, datetime
from time import monotonic
from zoneinfo import ZoneInfo
from scoreboard_device.transport import TransportController
from shared_py.renderer import Clip, PixelBuffer, _draw_text

WEEKDAYS = ('MONDAY','TUESDAY','WEDNESDAY','THURSDAY','FRIDAY','SATURDAY','SUNDAY')
MONTHS = ('JANUARY','FEBRUARY','MARCH','APRIL','MAY','JUNE','JULY','AUGUST','SEPTEMBER','OCTOBER','NOVEMBER','DECEMBER')


def date_label(value):
    d = date.fromisoformat(value)
    return f'{WEEKDAYS[d.weekday()]} {MONTHS[d.month-1]} {d.day} {d.year}'


def final_cards(mlb, nfl, requested_date, timezone_name):
    cards = []
    for game in mlb:
        if game.get('status') == 'final':
            cards.append(dict(sport='MLB', id=game['gameId'], away=game['away'], home=game['home'], detail=f" G{game.get('gameNumber',1)}" if game.get('doubleheader') else ''))
    for game in nfl:
        try:
            day = datetime.fromisoformat(game['date'].replace('Z','+00:00')).astimezone(ZoneInfo(timezone_name)).date().isoformat()
        except (KeyError,TypeError,ValueError):
            continue
        if game.get('completed') and day == requested_date:
            cards.append(dict(sport='NFL', id=game['id'], away=game['away'], home=game['home']))
    # Missing results must never be manufactured as zero.
    result = []
    for card in cards:
        try:
            scores = [int(card[side]['score']) for side in ('away','home')]
            if any(score < 0 for score in scores): continue
        except (KeyError,TypeError,ValueError):
            continue
        result.append(card)
    return result


class HistoryController:
    def __init__(self, clock=monotonic):
        self.clock = clock
        self.transport = TransportController(clock=clock)
        self.date = None
        self.deadline = 0
        self.generation = 0
        self.loading = False
        self.cards = []
        self.errors = []
        self.next_fetch = 0

    @property
    def active(self): return self.date is not None

    def select(self, value, today):
        selected = date.fromisoformat(value)
        if selected.isoformat() != value or not date(1900,1,1) <= selected <= today:
            raise ValueError('Choose a date from 1900 through today')
        self.generation += 1
        self.date = value
        self.deadline = self.clock() + 600
        self.loading = True
        self.cards = []
        self.errors = []
        self.transport.update([], [])
        self.next_fetch = 0

    def cancel(self):
        self.generation += 1
        self.date = None
        self.cards = []
        self.errors = []
        self.loading = False
        self.transport.update([], [])

    def tick(self):
        if self.active and self.clock() >= self.deadline:
            self.cancel()
            return True
        return False

    def apply(self, generation, cards, errors, mlb_dwell, nfl_dwell):
        self.tick()
        if not self.active or generation != self.generation: return False
        self.cards = cards
        self.errors = errors
        self.loading = False
        items = [dict(kind='history', gameId=c['id'], index=i,
                      dwellSec=nfl_dwell if c['sport']=='NFL' else mlb_dwell) for i,c in enumerate(cards)]
        # Error cards keep a partial outage visible alongside available finals.
        items += [dict(kind='history', gameId='error:'+error, index=len(cards)+i, dwellSec=6) for i,error in enumerate(errors)]
        self.transport.update(items, [])
        self.next_fetch = self.clock() + 60
        return True

    def status(self):
        self.tick()
        return dict(active=self.active, date=self.date, label=date_label(self.date) if self.active else None,
                    remainingSec=max(0,int(self.deadline-self.clock())) if self.active else 0,
                    loading=self.loading, games=len(self.cards), errors=self.errors,
                    item=self.transport.current, held=self.transport.held)

    def frame(self, fonts):
        frame = PixelBuffer(128,32)
        clip = Clip(0,0,128,32)
        frame.fill_rect(0,0,128,8,(48,27,2,255))
        _draw_text(frame,fonts['4x6'],date_label(self.date),64,1,(255,215,105,255),align='center',outer_clip=clip)
        self.transport.tick()
        item = self.transport.current
        card = self.cards[item['index']] if item and item['index'] < len(self.cards) else None
        if card:
            title = card['sport'] + ' FINAL' + card.get('detail','') + (' HOLD' if self.transport.held else '')
            scores = f"{card['away']['abbr']} {card['away']['score']} - {card['home']['abbr']} {card['home']['score']}"
        else:
            title = 'PAST SCORES'
            scores = ('LOADING FINALS' if self.loading else
                      self.errors[item['index']-len(self.cards)] if item else
                      'NO FINAL GAMES')
        _draw_text(frame,fonts['4x6'],title,64,10,(160,220,255,255),align='center',outer_clip=clip)
        _draw_text(frame,fonts['5x7'],scores,64,22,(255,255,255,255),align='center',outer_clip=clip)
        return frame
