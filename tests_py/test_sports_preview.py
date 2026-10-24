import asyncio
import unittest
import httpx
from backend.sports_preview import SportsService, normalize, demo, app
from fastapi.testclient import TestClient

def payload(score='123'):
    return {'events':[{'id':'1','date':'2026-10-24T23:00Z','competitions':[{'competitors':[
        {'homeAway':side,'team':{'id':str(i),'abbreviation':abbr,'displayName':abbr},'score':score}
        for i,(side,abbr) in enumerate([('home','BOS'),('away','NY')])],
        'status':{'type':{'state':'in','completed':False,'shortDetail':'3rd'},'period':3,'displayClock':'1:22'}}]}]}

class SportsTests(unittest.IsolatedAsyncioTestCase):
    async def test_cache_single_flight_and_league_isolation(self):
        calls=[]
        async def handler(request):
            calls.append(str(request.url)); await asyncio.sleep(.01)
            return httpx.Response(200,json=payload())
        service=SportsService(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        try:
            values=await asyncio.gather(*[service.snapshot('nba','2026-10-24','live') for _ in range(3)])
            self.assertEqual(len(calls),1)
            self.assertEqual(values[0]['games'][0]['id'],'nba:1')
            await service.snapshot('nhl','2026-10-24','live')
            self.assertEqual(len(calls),2)
            values[0]['games'].clear()
            self.assertEqual(len((await service.snapshot('nba','2026-10-24','live'))['games']),1)
        finally: await service.close()

    async def test_outage_date_isolation_backoff_and_recovery(self):
        now=[0]; fail=[False]; calls=[]
        def handler(request):
            calls.append(request)
            return httpx.Response(503) if fail[0] else httpx.Response(200,json=payload())
        service=SportsService(httpx.AsyncClient(transport=httpx.MockTransport(handler)),clock=lambda:now[0])
        try:
            await service.snapshot('nba','2026-10-24','live')
            fail[0]=True; now[0]=31
            stale=await service.snapshot('nba','2026-10-24','live')
            self.assertEqual(stale['source']['freshness'],'stale')
            self.assertEqual(len(stale['games']),1)
            failed=await service.snapshot('nba','2026-10-23','live')
            self.assertEqual(failed['source']['freshness'],'failed');self.assertFalse(failed['games'])
            count=len(calls);await service.snapshot('nba','2026-10-23','live');self.assertEqual(len(calls),count)
            now[0]=62; second=await service.snapshot('nba','2026-10-24','live')
            self.assertEqual(second['source']['refreshSec'],60)
            fail[0]=False;now[0]=123
            self.assertEqual((await service.snapshot('nba','2026-10-24','live'))['source']['freshness'],'fresh')
        finally: await service.close()

    async def test_retry_after_and_size_bound(self):
        now=[0];code=[429]
        def handler(request): return httpx.Response(code[0],headers={'Retry-After':'600'},content=b'x'*2_000_001 if code[0]==200 else b'')
        service=SportsService(httpx.AsyncClient(transport=httpx.MockTransport(handler)),clock=lambda:now[0])
        try:
            self.assertEqual((await service.snapshot('nhl','2026-10-24','live'))['source']['refreshSec'],600)
            code[0]=200; now[0]=601
            self.assertEqual((await service.snapshot('nhl','2026-10-24','live'))['source']['freshness'],'failed')
        finally: await service.close()

    async def test_synthetic_modes_never_use_network(self):
        def handler(request): raise AssertionError('No network in demo')
        service=SportsService(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        try:
            for mode in ['demo','stale','failed','empty']:
                s=await service.snapshot('nhl','2026-10-24',mode)
                self.assertEqual(s['source']['provider'],'Synthetic demo')
                self.assertEqual(bool(s['games']), mode in ['demo','stale'])
            self.assertFalse(service.cache)
        finally: await service.close()

class NormalizeTests(unittest.TestCase):
    def test_unknown_scores_and_partial_events(self):
        p=payload(None);p['events'].append({})
        games,rejected=normalize(p,'nba');self.assertEqual(rejected,1)
        self.assertIsNone(games[0]['home']['score'])
        with self.assertRaises(ValueError):normalize({'events':[{}]},'nba')
        self.assertEqual(normalize({'events':[]},'nba'),([],0))
    def test_demo_scenarios_and_http_contract(self):
        self.assertIn('FINAL/SO',[g['status'] for g in demo('nhl','2026-10-24')])
        with TestClient(app) as client:
            r=client.get('/api/sports/nba?day=2026-10-24&mode=demo')
            self.assertEqual(r.status_code,200);self.assertEqual(len(r.json()['games']),8)
            self.assertEqual(client.get('/api/sports/nba?day=bad').status_code,400)
            self.assertEqual(client.get('/api/sports/mlb').status_code,422)
