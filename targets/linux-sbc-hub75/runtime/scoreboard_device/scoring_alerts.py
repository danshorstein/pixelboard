"""Confirmed scoring plays for the visible live game, with no catch-up replay."""
from __future__ import annotations
from time import monotonic
import httpx
from shared_py.renderer import Clip, PixelBuffer, _draw_text

MLB_FIELDS = 'gamePk,gameData,teams,away,home,id,name,liveData,plays,allPlays,about,atBatIndex,isTopInning,isComplete,result,eventType'


def scoring_events(sport, game_id, payload):
    events = []
    if sport == 'MLB':
        if str(payload.get('gamePk')) != str(game_id).removeprefix('mlb-'):
            raise ValueError('MLB play response has the wrong game')
        plays = payload.get('liveData',{}).get('plays',{}).get('allPlays')
        teams = payload.get('gameData',{}).get('teams',{})
        if not isinstance(plays,list) or any(not teams.get(side,{}).get('name') or teams.get(side,{}).get('id') is None for side in ('away','home')):
            raise ValueError('MLB plays or teams missing')
        for play in plays:
            about = play.get('about',{})
            if play.get('result',{}).get('eventType') != 'home_run' or not about.get('isComplete'): continue
            side = 'away' if about.get('isTopInning') is True else 'home' if about.get('isTopInning') is False else None
            team = teams.get(side,{})
            if about.get('atBatIndex') is None or not team.get('name') or team.get('id') is None: continue
            events.append(dict(id=f"MLB:{game_id}:{about['atBatIndex']}", message='HOME RUN',
                               team=team['name'], teamId=str(team['id'])))
    else:
        if str(payload.get('header',{}).get('id')) != str(game_id):
            raise ValueError('NFL play response has the wrong game')
        plays = payload.get('scoringPlays')
        if plays is None:
            competitions = payload.get('header',{}).get('competitions',[])
            competitors = competitions[0].get('competitors',[]) if competitions else []
            # ESPN omits this list before any score. Verified scoreless or
            # pregame summaries can safely establish an empty baseline.
            pregame = bool(competitions) and competitions[0].get('status',{}).get('type',{}).get('state') == 'pre'
            if len(competitors)==2 and (all(c.get('score') in (0,'0') for c in competitors)
                    or (pregame and all(c.get('score') in (None,0,'0') for c in competitors))):
                plays = []
        if not isinstance(plays,list): raise ValueError('NFL scoring play list missing')
        for play in plays:
            scoring_type = play.get('scoringType',{}).get('name')
            is_td = scoring_type == 'touchdown' if scoring_type else play.get('type',{}).get('abbreviation') == 'TD'
            team = play.get('team',{})
            if not is_td or not play.get('id') or not team.get('displayName') or team.get('id') is None: continue
            events.append(dict(id=f"NFL:{game_id}:{play['id']}", message='TOUCHDOWN',
                               team=team['displayName'], teamId=str(team['id'])))
    return events


def fetch_scoring_events(sport, game_id):
    if sport == 'MLB':
        response = httpx.get(f'https://statsapi.mlb.com/api/v1.1/game/{str(game_id).removeprefix("mlb-")}/feed/live',
                            params={'fields':MLB_FIELDS},timeout=8)
    else:
        response = httpx.get('https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary',
                            params={'event':game_id},timeout=8)
    response.raise_for_status()
    return scoring_events(sport,game_id,response.json())


class ScoringAlerts:
    def __init__(self, clock=monotonic):
        self.clock = clock
        self.key = None
        self.generation = 0
        self.seen = None
        self.queue = []
        self.active = None
        self.started = 0
        self.next_fetch = 0
        self.finalized = False
        self.error = None

    def sync(self, key):
        if key == self.key: return
        self.key = key
        self.generation += 1
        self.seen = None
        self.queue = []
        self.active = None
        self.finalized = False
        self.next_fetch = 0
        self.error = None

    def ingest(self, generation, events, completed=False):
        if generation != self.generation or self.key is None: return False
        events = list({event['id']:event for event in events}.values())
        ids = {event['id'] for event in events}
        if self.seen is not None:
            self.queue.extend(e for e in events if e['id'] not in self.seen)
            self.queue = self.queue[-8:]
        self.seen = (self.seen or set()) | ids
        self.finalized = completed
        self.error = None
        self.next_fetch = self.clock() + 3
        return True

    def failed(self, generation):
        if generation != self.generation: return
        # Recovery establishes a fresh baseline, never replays an outage's scores.
        self.seen = None
        self.queue = []
        self.error = 'LIVE PLAY DATA OFFLINE'
        self.next_fetch = self.clock() + 10

    def tick(self):
        finished = False
        if self.active and self.clock()-self.started >= 8:
            self.active = None
            finished = True
        if not self.active and self.queue:
            self.active = self.queue.pop(0)
            self.started = self.clock()
        return self.active, finished

    def frame(self, fonts):
        # Slow color pulse (one change per 0.5 seconds), with continuously readable text.
        bright = int((self.clock()-self.started)*2) % 2 == 0
        frame = PixelBuffer(128,32,(28,12,0,255) if bright else (0,0,0,255))
        clip = Clip(0,0,128,32)
        _draw_text(frame,fonts['6x10'],self.active['message'],64,2,(255,225,95,255),align='center',outer_clip=clip)
        _draw_text(frame,fonts['5x7'],self.active['team'].upper(),64,21,(255,255,255,255),align='center',outer_clip=clip)
        return frame
