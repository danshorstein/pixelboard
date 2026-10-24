"""Bounded NBA/NHL ESPN scores with per-league durable, date-scoped fallback."""
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from time import monotonic
import json
import httpx

PATHS = {'nba': 'basketball/nba', 'nhl': 'hockey/nhl', 'nfl': 'football/nfl'}
def normalize(payload, league):
    if not isinstance(payload, dict) or not isinstance(payload.get('events'), list):
        raise ValueError('Missing event list')
    games, rejected = [], 0
    if len(payload['events']) > 100: raise ValueError('Too many events')
    for event in payload['events']:
        try:
            c = event['competitions'][0]
            teams = {}
            for entry in c['competitors']:
                t = entry['team']; raw = entry.get('score')
                if not isinstance(t['abbreviation'], str) or not 1 <= len(t['abbreviation']) <= 8: raise ValueError('Invalid team')
                score = int(raw) if raw is not None and str(raw).isdigit() else None
                teams[entry['homeAway']] = dict(id=str(t['id']), abbr=t['abbreviation'], name=t['displayName'], color=t.get('color') if isinstance(t.get('color'), str) else '394b64', score=score)
            status = c.get('status') or event.get('status', {})
            kind = status.get('type', {})
            if event.get('date'):
                if not isinstance(event['date'], str): raise ValueError('Invalid date')
                datetime.fromisoformat(event['date'].replace('Z', '+00:00'))
            period = status.get('period')
            if period is not None and (type(period) is not int or not 0 <= period <= 99): raise ValueError('Invalid period')
            games.append(dict(id=f"{league}:{event['id']}", providerId=str(event['id']), league=league,
                home=teams['home'], away=teams['away'], date=event.get('date'),
                state=kind.get('state','unknown'), completed=bool(kind.get('completed',False)),
                status=str(kind.get('shortDetail') or kind.get('description') or 'UNKNOWN')[:80],
                period=status.get('period'), clock=str(status['displayClock'])[:12] if status.get('displayClock') is not None else None))
        except (KeyError, IndexError, TypeError, ValueError): rejected += 1
    if rejected and not games: raise ValueError('No usable events')
    return games, rejected

def demo(league, day):
    pairs = {'nba': [('BOS','Boston', '007a33'),('NY','New York','006bb6')],
             'nhl': [('FLA','Florida','c8102e'),('NYR','New York','0038a8')],
             'nfl': [('WSH','Washington','5a1414'),('PHI','Philadelphia','004c54')]}
    a,b = pairs[league]
    cases = [('LIVE','in',False,3,'4:21'),('PREGAME','pre',False,0,None),
             ('FINAL','post',True,4 if league!='nhl' else 3,None),
             ('2OT' if league=='nba' else 'OT','in',False,6 if league=='nba' else 4,'2:12'),
             ('HALFTIME' if league!='nhl' else 'INTERMISSION','in',False,2,'0:00'),
             ('POSTPONED','pre',False,0,None),('DELAYED','in',False,1,None),
             ('FINAL/SO' if league=='nhl' else 'FINAL/OT','post',True,5,None)]
    if league == 'nhl': cases.append(('SO', 'in', False, 5, None))
    result=[]
    for i,(label,state,done,period,clock) in enumerate(cases):
        def team(t,home):
            return dict(id=t[0],abbr=t[0],name=t[1],color=t[2],score=None if state=='pre' else (123 if home else 118) if league=='nba' else (3 if home else 2) if league=='nhl' else (21 if home else 17))
        result.append(dict(id=f'{league}:demo:{i}',providerId=f'demo:{i}',league=league,
            away=team(a,False),home=team(b,True),date=f'{day}T23:30:00Z',state=state,completed=done,
            status=label,period=period,clock=clock))
    return result


def valid_cached_game(game, league):
    try:
        if game['league'] != league or not isinstance(game['id'], str) or not isinstance(game['status'], str): return False
        if type(game['completed']) is not bool or not isinstance(game['state'], str): return False
        if game.get('date'): datetime.fromisoformat(game['date'].replace('Z', '+00:00'))
        if game.get('period') is not None and type(game['period']) is not int: return False
        if game.get('clock') is not None and not isinstance(game['clock'], str): return False
        return all(isinstance(game[side]['abbr'], str) and isinstance(game[side].get('color'), str)
            and (game[side].get('score') is None or type(game[side]['score']) is int and game[side]['score'] >= 0)
            for side in ('away','home'))
    except (KeyError, TypeError, ValueError, AttributeError): return False

class LeagueFeed:
    def __init__(self, league, cache_path):
        if league not in ('nba', 'nhl'): raise ValueError('Unsupported league')
        self.league, self.path = league, Path(cache_path)
        self.value = None
        self.next_attempt = 0
        self.attempt_date = None
        self.failures = 0
        try:
            cached = json.loads(self.path.read_text())
            date.fromisoformat(cached['date'])
            if (cached['league'] == league and isinstance(cached['games'], list) and len(cached['games']) <= 100
                    and isinstance(cached['source'], dict) and all(valid_cached_game(g, league) for g in cached['games'])):
                self.value = cached
        except (OSError, ValueError, KeyError, TypeError): pass

    def fetch(self, requested_date):
        date.fromisoformat(requested_date)
        if self.attempt_date == requested_date and monotonic() < self.next_attempt and self.value:
            return deepcopy(self.value)
        self.attempt_date = requested_date
        delay = 30
        try:
            with httpx.stream('GET', 'https://site.api.espn.com/apis/site/v2/sports/' + PATHS[self.league] + '/scoreboard',
                              params={'dates': requested_date.replace('-', '')}, timeout=12) as response:
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 2_000_000: raise ValueError('Response too large')
                    chunks.append(chunk)
            games, rejected = normalize(json.loads(b''.join(chunks)), self.league)
            value = dict(league=self.league, date=requested_date, games=games,
                source=dict(freshness='partial' if rejected else 'fresh', provider='ESPN',
                    fetchedUtc=datetime.now(timezone.utc).isoformat(), refreshSec=30,
                    error=f'{rejected} malformed events skipped' if rejected else None))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(value)); temporary.replace(self.path)
            self.value = value
            self.failures = 0
        except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError) as error:
            self.failures += 1
            delay = min(300, 30 * 2 ** min(self.failures - 1, 4))
            if isinstance(error, httpx.HTTPStatusError):
                if error.response.status_code == 403: delay = 300
                if error.response.status_code == 429:
                    try: delay = max(delay, min(3600, int(error.response.headers.get('retry-after', '300'))))
                    except ValueError: delay = max(delay, 300)
            value = deepcopy(self.value) if self.value and self.value['date'] == requested_date else dict(
                league=self.league, date=requested_date, games=[], source={'fetchedUtc': None, 'provider': 'ESPN'})
            value['source'].update(freshness='stale' if value['source'].get('fetchedUtc') else 'failed',
                                   error=self.league.upper() + ' DATA OFFLINE', refreshSec=delay)
            self.value = value
        self.next_attempt = monotonic() + delay
        return deepcopy(self.value)
