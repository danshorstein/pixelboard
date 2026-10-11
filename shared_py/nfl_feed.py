"""Public ESPN NFL data with same-date stale fallback and bounded polling."""
from __future__ import annotations
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from time import monotonic
import httpx
URL = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard'
NFL_TEAMS = 'ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LAC LAR LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WSH'.split()
DEFAULT_NFL = dict(enabled=False, favorites=[], favoritesOnly=False, hiddenGames=[], dwellSec=8, liveFirst=True, liveOnly=False, hideFinal=False, layout='rows')
def validate_settings(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULT_NFL):
        raise ValueError('Invalid NFL settings')
    result = deepcopy(DEFAULT_NFL); result.update(value)
    for key in ('enabled','favoritesOnly','liveFirst','liveOnly','hideFinal'):
        if type(result[key]) is not bool: raise ValueError('NFL flags must be booleans')
    if type(result['dwellSec']) is not int or not 3 <= result['dwellSec'] <= 60:
        raise ValueError('NFL dwell must be 3-60 seconds')
    for key in ('favorites','hiddenGames'):
        items = result[key]
        if not isinstance(items,list) or len(items)>500 or any(not isinstance(x,str) or len(x)>64 for x in items) or len(set(items)) != len(items):
            raise ValueError('Invalid NFL selection')
    if any(t not in NFL_TEAMS for t in result['favorites']): raise ValueError('Unknown NFL team')
    if result['layout'] not in ('rows','compact'): raise ValueError('Invalid NFL layout')
    return result

def selected_games(games, settings):
    if not settings['enabled']: return []
    result = [g for g in games if g['id'] not in settings['hiddenGames']
              and (not settings['favoritesOnly'] or any(g[side]['abbr'] in settings['favorites'] for side in ('away','home')))
              and (not settings['liveOnly'] or g['state']=='in')
              and (not settings['hideFinal'] or not g['completed'])]
    return sorted(result,key=lambda g:g['state']!='in') if settings['liveFirst'] else result

def normalize(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get('events'), list):
        raise ValueError('ESPN response is missing the game list')
    games = []
    for event in payload['events']:
        competition = event['competitions'][0]
        teams = {}
        for competitor in competition['competitors']:
            team = competitor['team']
            teams[competitor['homeAway']] = {
                'id': str(team['id']), 'name': team['displayName'],
                'abbr': team['abbreviation'], 'color': team.get('color', 'ffffff'),
                'logo': team.get('logo'), 'score': competitor.get('score'),
                'record': next((r.get('summary', '') for r in competitor.get('records', []) if r.get('type') == 'total'), ''),
            }
        status = competition.get('status') or event.get('status', {})
        situation = competition.get('situation') or {}
        games.append({
            'id': str(event['id']), 'name': event['name'], 'date': event.get('date'),
            'home': teams['home'], 'away': teams['away'],
            'state': status.get('type', {}).get('state', 'unknown'),
            'status': status.get('type', {}).get('shortDetail', 'Status unavailable'),
            'completed': status.get('type', {}).get('completed', False),
            'period': status.get('period'), 'clock': status.get('displayClock'),
            'downDistance': situation.get('shortDownDistanceText'),
            'fieldPosition': situation.get('possessionText'),
            'possession': situation.get('possession'), 'redZone': situation.get('isRedZone', False),
            'homeTimeouts': situation.get('homeTimeouts'), 'awayTimeouts': situation.get('awayTimeouts'),
            'lastPlay': (situation.get('lastPlay') or {}).get('text'),
            'venue': (competition.get('venue') or {}).get('fullName', ''),
            'broadcast': competition.get('broadcast', ''),
        })
    return games


class NflFeed:
    def __init__(self, cache_path):
        self.path = Path(cache_path)
        self.value = None
        self.last_attempt = 0.0
        self.attempt_date = None
        try:
            cached = json.loads(self.path.read_text())
            if isinstance(cached,dict) and isinstance(cached.get('games'),list): self.value=cached
        except (OSError,ValueError): pass

    def fetch(self, requested_date):
        if self.attempt_date == requested_date and monotonic()-self.last_attempt < 30 and self.value:
            return deepcopy(self.value)
        self.attempt_date = requested_date
        self.last_attempt = monotonic()
        try:
            response = httpx.get(URL, params={'dates':requested_date.replace('-','')},timeout=12)
            response.raise_for_status()
            value = dict(date=requested_date,games=normalize(response.json()), freshness='fresh',
                         fetchedUtc=datetime.now(timezone.utc).isoformat(),error=None)
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.path.with_suffix('.tmp'); temporary.write_text(json.dumps(value)); temporary.replace(self.path)
            self.value=value
        except (httpx.HTTPError,OSError,ValueError,KeyError,IndexError,TypeError):
            self.value = deepcopy(self.value) if self.value and self.value.get('date')==requested_date else dict(date=requested_date,games=[],fetchedUtc=None)
            self.value.update(freshness='stale' if self.value['fetchedUtc'] else 'failed', error='NFL DATA OFFLINE')
        return deepcopy(self.value)
