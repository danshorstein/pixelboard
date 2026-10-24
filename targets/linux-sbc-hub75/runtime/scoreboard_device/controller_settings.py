from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
from scoreboard_device.history import date_label
from time import monotonic
from shared_py.nfl_feed import NFL_TEAMS
from shared_py.sports import LEAGUES, sports_settings
from shared_py.reveal_frame import create_reveal_text_frame

LAYOUTS = ("classic", "broadcastRows", "broadcastLogos")
LAYOUT_NAMES = ("ORIGINAL", "PREVIEW 3", "LOGOS + TICKER")
WAKE_SECONDS = (30, 60, 120, 300)


class ControllerSettings:
    """Device-only settings draft. The runtime owns persistence and input timing."""
    settings_labels = ("BRIGHTNESS", "NIGHT BRIGHTNESS", "LAYOUT", "QUIET MODE", "WAKE TIME")

    def __init__(self):
        self.page = "main"
        self.games = []
        self.active = False
        self.preview = False
        self.index = 0
        self.draft = None
        self.error = None
        self.last_input = 0.0

    @property
    def labels(self):
        if self.page == 'main': return ('SCOREBOARD', 'ARCADE GAMES', 'SETTINGS', 'NFL SETTINGS', 'PICK NFL GAMES', 'NFL FAVORITES', 'PAST SCORES', 'SPORTS', 'HOME CLOCK')
        if self.page == 'sports': return ('MLB', 'NFL', 'NBA', 'NHL', 'TEAM CALENDAR', 'SAVE CHANGES')
        if self.page == 'nfl': return ('NFL SCORES','SECONDS PER GAME','FAVORITES ONLY','LIVE FIRST','ONLY LIVE','HIDE FINALS','NFL LAYOUT','SAVE CHANGES')
        if self.page == 'games': return ('SHOW ALL', *[g['away']['abbr']+' @ '+g['home']['abbr'] for g in self.games], 'SAVE CHANGES')
        if self.page == 'teams': return (*NFL_TEAMS, 'SAVE CHANGES')
        return self.settings_labels

    def open(self, config, games=(), today=None):
        self.history_today = today or datetime.now().date()
        self.history_date = self.history_today - timedelta(days=1)
        self.page = "main"
        self.games = deepcopy(list(games))
        self.draft = deepcopy(config)
        self.draft['sports'] = sports_settings(config)
        self.initial_sports = deepcopy(self.draft['sports'])
        self.active = True
        self.preview = False
        self.index = 0
        self.error = None
        self.last_input = monotonic()

    def close(self):
        self.active = False
        self.preview = False
        self.draft = None
        self.error = None

    def input(self, button):
        self.last_input = monotonic()
        self.error = None
        if button == 'select':
            self.close()
        elif button == 'b':
            if self.page == 'main': self.close()
            else: self.page = 'main'; self.index = 0; self.preview = False
        elif self.page == 'main':
            if button in ('up','down'):
                self.index = (self.index + (1 if button=='down' else -1)) % len(self.labels)
            elif button == 'a':
                if self.index == 0: self.close(); return 'scoreboard'
                elif self.index == 1: self.close(); return 'arcade'
                elif self.index == 7: self.page = 'sports'; self.index = 0
                elif self.index == 8: self.close(); return 'home'
                elif self.index == 6: self.page = 'history'; self.index = 0
                else: self.page = ('settings','nfl','games','teams')[self.index-2]; self.index=0
        elif self.page == 'sports':
            if button in ('up', 'down'): self.index = (self.index + (1 if button=='down' else -1)) % 6
            elif button in ('a', 'left', 'right'):
                if self.index == 5: return 'save'
                league = LEAGUES[self.index]
                self.draft['sports'][league]['enabled'] = not self.draft['sports'][league]['enabled']
                if league == 'nfl': self.draft['nfl']['enabled'] = self.draft['sports']['nfl']['enabled']
        elif self.page == 'history':
            if button in ('left','right','l','r'):
                delta = {'left':-1,'right':1,'l':-7,'r':7}[button]
                self.history_date = min(self.history_today,max(date(1900,1,1),self.history_date+timedelta(days=delta)))
            elif button == 'a': return 'history'
            elif button == 'x': self.close(); return 'scoreboard'
        elif self.page != 'settings':
            if button in ('up','down'):
                self.index = (self.index + (1 if button=='down' else -1)) % len(self.labels)
            elif button in ('a','left','right'):
                n = self.draft['nfl']; delta = -1 if button=='left' else 1
                if self.index == len(self.labels)-1: return 'save'
                if self.page == 'nfl':
                    keys = ('enabled','dwellSec','favoritesOnly','liveFirst','liveOnly','hideFinal','layout')
                    key = keys[self.index]
                    if key == 'dwellSec': n[key] = max(3,min(60,n[key]+delta))
                    elif key == 'layout': n[key] = 'compact' if n[key]=='rows' else 'rows'
                    else: n[key] = not n[key]
                elif self.page == 'teams':
                    team = NFL_TEAMS[self.index]
                    if team in n['favorites']: n['favorites'].remove(team)
                    else: n['favorites'].append(team)
                elif self.index == 0: n['hiddenGames'] = []
                else:
                    game = self.games[self.index-1]['id']
                    if game in n['hiddenGames']: n['hiddenGames'].remove(game)
                    else: n['hiddenGames'].append(game)
        elif button == 'a':
            return 'save'
        elif button == 'x':
            self.preview = not self.preview
        elif button in ('up', 'down'):
            self.index = (self.index + (1 if button == 'down' else -1)) % len(self.labels)
            self.preview = False
        elif button in ('left', 'right'):
            delta = 1 if button == 'right' else -1
            d = self.draft
            if self.index in (0, 1):
                key = 'normal' if self.index == 0 else 'dim'
                d['brightness'][key] = max(1, min(100, d['brightness'][key] + delta * 5))
            elif self.index == 2:
                current = d['layoutPreset'] if d['layoutPreset'] in LAYOUTS else 'classic'
                d['layoutPreset'] = LAYOUTS[(LAYOUTS.index(current) + delta) % len(LAYOUTS)]
            elif self.index == 3:
                q = d['quietHours']
                choices = ('off', 'dim', 'sleep')
                current = q['behavior'] if q['enabled'] else 'off'
                selected = choices[(choices.index(current) + delta) % 3]
                q['enabled'] = selected != 'off'
                if selected != 'off':
                    q['behavior'] = selected
            else:
                value = d['wakeDurationSec']
                choices = sorted(set(WAKE_SECONDS + (value,)))
                d['wakeDurationSec'] = choices[(choices.index(value) + delta) % len(choices)]

    def payload(self):
        payload = {'expectedVersion': self.draft['version'], **{
            key: deepcopy(self.draft[key]) for key in ('brightness', 'quietHours', 'layoutPreset', 'wakeDurationSec', 'nfl')}}
        if self.draft['sports'] != self.initial_sports: payload['sports'] = deepcopy(self.draft['sports'])
        return payload

    def frame(self, font, width=128, height=32):
        d = self.draft
        if self.page == 'history':
            return create_reveal_text_frame(width,height,['PAST SCORES',date_label(self.history_date.isoformat()),
                'LEFT/RIGHT DATE L/R WEEK','A SHOW X LIVE B BACK'],font)
        if self.page != 'settings':
            value = 'A OPEN B BACK'
            n = d['nfl']
            if self.page == 'sports' and self.index < 5:
                value = 'ON' if d['sports'][LEAGUES[self.index]]['enabled'] else 'OFF'
            if self.page == 'nfl' and self.index < 7:
                value = str(n[('enabled','dwellSec','favoritesOnly','liveFirst','liveOnly','hideFinal','layout')[self.index]]).upper()
                if value in ('TRUE','FALSE'): value = 'ON' if value=='TRUE' else 'OFF'
            elif self.page == 'teams' and self.index < len(NFL_TEAMS):
                value = 'FAVORITE' if NFL_TEAMS[self.index] in n['favorites'] else 'OFF'
            elif self.page == 'games' and 0 < self.index <= len(self.games):
                value = 'HIDDEN' if self.games[self.index-1]['id'] in n['hiddenGames'] else 'SHOW'
            return create_reveal_text_frame(width,height,[self.labels[self.index],self.error or value,'A OK B BACK'],font)
        values = (str(d['brightness']['normal']) + '%', str(d['brightness']['dim']) + '%',
                  LAYOUT_NAMES[LAYOUTS.index(d['layoutPreset'])] if d['layoutPreset'] in LAYOUTS else 'ORIGINAL',
                  d['quietHours']['behavior'].upper() if d['quietHours']['enabled'] else 'OFF',
                  str(d['wakeDurationSec']) + ' SECONDS')
        return create_reveal_text_frame(width, height,
            [self.labels[self.index], self.error or values[self.index], 'A SAVE B BACK X VIEW'], font)
