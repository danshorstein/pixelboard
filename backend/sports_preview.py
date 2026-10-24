"""Isolated browser experiment. Never imported by the Pi runtime."""
from __future__ import annotations
import asyncio
from copy import deepcopy
from datetime import date, datetime, timezone
from time import monotonic, perf_counter
from typing import Literal
import httpx
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager

PATHS = {'nba': 'basketball/nba', 'nhl': 'hockey/nhl', 'nfl': 'football/nfl'}

from shared_py.league_feed import normalize, demo

class SportsService:
    def __init__(self, client=None, clock=monotonic):
        self.client=client or httpx.AsyncClient(timeout=12, follow_redirects=False)
        self.clock=clock
        self.cache={}
        self.locks={k:asyncio.Lock() for k in PATHS}

    async def close(self): await self.client.aclose()

    async def snapshot(self, league, day, mode):
        date.fromisoformat(day)
        if mode != 'live':
            games=[] if mode in ('empty','failed') else demo(league,day)
            return dict(league=league,date=day,mode=mode,games=games,
                source=dict(provider='Synthetic demo',freshness=mode, fetchedUtc=None,refreshSec=30,
                            error='Simulated provider outage' if mode in ('stale','failed') else None),metrics=None)
        async with self.locks[league]:
            key=(league,day); entry=self.cache.get(key)
            if entry and self.clock()<entry['next']: return deepcopy(entry['value'])
            started=perf_counter()
            try:
                async with self.client.stream('GET',f'https://site.api.espn.com/apis/site/v2/sports/{PATHS[league]}/scoreboard', params={'dates':day.replace('-','')}) as response:
                    response.raise_for_status()
                    chunks=[]; size=0
                    async for chunk in response.aiter_bytes():
                        size+=len(chunk)
                        if size>2_000_000: raise ValueError('Response too large')
                        chunks.append(chunk)
                network_ms=(perf_counter()-started)*1000
                def parse():
                    import json
                    t=perf_counter(); games,rejected=normalize(json.loads(b''.join(chunks)),league)
                    return games,rejected,(perf_counter()-t)*1000
                games,rejected,parse_ms=await asyncio.to_thread(parse)
                value=dict(league=league,date=day,mode='live',games=games,
                    source=dict(provider='ESPN',freshness='partial' if rejected else 'fresh',fetchedUtc=datetime.now(timezone.utc).isoformat(),refreshSec=30,error=f'{rejected} malformed events skipped' if rejected else None),
                    metrics=dict(bytes=size,requestMs=round(network_ms,2),parseMs=round(parse_ms,3),games=len(games)))
                failures=0; delay=30
            except (httpx.HTTPError,ValueError,KeyError,TypeError) as exc:
                failures=(entry or {}).get('failures',0)+1
                delay=min(300,30*2**min(failures-1,4))
                if isinstance(exc,httpx.HTTPStatusError):
                    if exc.response.status_code==403: delay=300
                    if exc.response.status_code==429:
                        try: delay=max(delay,min(3600,int(exc.response.headers.get('retry-after','300'))))
                        except ValueError: delay=max(delay,300)
                value=deepcopy(entry['value']) if entry else dict(league=league,date=day,mode='live',games=[],source=dict(provider='ESPN',fetchedUtc=None),metrics=None)
                value['source'].update(freshness='stale' if value['source'].get('fetchedUtc') else 'failed',error=f'ESPN unavailable; retry in {delay}s',refreshSec=delay)
            self.cache[key]=dict(next=self.clock()+delay,value=value,failures=failures)
            while len(self.cache)>24: del self.cache[next(iter(self.cache))]
            return deepcopy(value)

@asynccontextmanager
async def lifespan(app):
    app.state.sports=SportsService()
    yield
    await app.state.sports.close()

app=FastAPI(title='NBA / NHL browser preview',lifespan=lifespan)

@app.get('/api/sports/{league}')
async def snapshot(league: Literal['nba','nhl','nfl'], day: str | None=None,
                   mode: Literal['live','demo','stale','failed','empty']='live'):
    from zoneinfo import ZoneInfo
    day=day or datetime.now(ZoneInfo('America/New_York')).date().isoformat()
    try: return await app.state.sports.snapshot(league,day,mode)
    except ValueError: raise HTTPException(400,'Invalid date')
