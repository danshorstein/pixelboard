from __future__ import annotations
import asyncio
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from time import monotonic
import unittest
from unittest.mock import AsyncMock, patch
import urllib.request
import urllib.error
import httpx

from tests_py import test_controller_settings as helpers
from scoreboard_device.history import HistoryController, date_label, final_cards
from scoreboard_device.scoring_alerts import ScoringAlerts, scoring_events
from shared_py.mlb_adapter import MlbStatsApiAdapter
from shared_py.bdf import measure_text

FIXTURE = json.loads((Path(__file__).resolve().parents[1]/'fixtures/scoring-events.json').read_text())


def mlb_game(game_id='mlb-813047',status='final'):
    return dict(gameId=game_id,status=status,away=dict(abbr='CHC',name='Cubs',id=112,score=3),home=dict(abbr='MIL',name='Brewers',id=158,score=9))


def nfl_game(game_id='401772633',day='2025-10-05T13:30:00Z',completed=True):
    return dict(id=game_id,date=day,venue='Test Stadium',completed=completed,state='post' if completed else 'in',status='Final' if completed else 'Q1 12:00',
                away=dict(id='16',abbr='MIN',name='Minnesota Vikings',score='21'),home=dict(id='5',abbr='CLE',name='Cleveland Browns',score='17'))


class HistoryUnitTests(unittest.TestCase):
    def test_ten_minutes_is_absolute_even_while_held_and_late_fetch_cannot_restore(self):
        clock=[100]; h=HistoryController(clock=lambda:clock[0]); h.select('2025-10-05',date(2025,10,6)); generation=h.generation
        h.apply(generation,final_cards([mlb_game()],[],h.date,'America/New_York'),[],8,8)
        h.transport.toggle_hold(); clock[0]=699.9; self.assertTrue(h.status()['active'])
        clock[0]=700; self.assertFalse(h.status()['active'])
        self.assertFalse(h.apply(generation,[],[],8,8)); self.assertFalse(h.active)

    def test_wrong_date_reply_rejected_and_new_selection_gets_own_deadline(self):
        h=HistoryController(); h.select('2025-10-04',date(2025,10,6)); generation=h.generation
        h.select('2025-10-05',date(2025,10,6)); self.assertFalse(h.apply(generation,[],[],8,8)); self.assertTrue(h.loading)
        for invalid in ('2025-02-30','2025-10-07','20251005','1899-01-01'):
            with self.assertRaises(ValueError): h.select(invalid,date(2025,10,6))
        self.assertEqual('2025-10-05',h.date)

    def test_only_finals_with_scores_and_nfl_local_game_date(self):
        mlb=[mlb_game(),mlb_game('mlb-2'),mlb_game('mlb-3','in_progress'),mlb_game('mlb-4','postponed')]
        missing=nfl_game('missing'); missing['home']['score']=None
        nfl=[nfl_game(),nfl_game('late','2025-10-06T00:20:00Z'),nfl_game('other','2025-10-06T13:00:00Z'),nfl_game('live',completed=False),missing]
        cards=final_cards(mlb,nfl,'2025-10-05','America/New_York')
        self.assertEqual(['mlb-813047','mlb-2','401772633','late'],[c['id'] for c in cards])

    def test_refresh_preserves_current_card_and_partial_outage_stays_visible(self):
        h=HistoryController(); h.select('2025-10-05',date(2025,10,6));cards=final_cards([mlb_game(),mlb_game('mlb-2')],[],h.date,'America/New_York')
        h.apply(h.generation,cards,['NFL DATA OFFLINE'],8,8);h.transport.next()
        h.apply(h.generation,cards,['NFL DATA OFFLINE'],8,8);self.assertEqual('mlb-2',h.transport.current['gameId'])
        h.transport.next();self.assertEqual('error:NFL DATA OFFLINE',h.transport.current['gameId'])


class PlayDetectionTests(unittest.TestCase):
    def test_recorded_home_runs_name_the_batting_team_and_ignore_other_plays(self):
        events=scoring_events('MLB','mlb-813047',FIXTURE['mlb'])
        self.assertTrue(events);self.assertEqual('Chicago Cubs',events[0]['team'])
        self.assertTrue(all(e['message']=='HOME RUN' for e in events))
        changed=deepcopy(FIXTURE['mlb']);changed['liveData']['plays']['allPlays'][0]['about']['isComplete']=False
        self.assertEqual(len(events)-1,len(scoring_events('MLB','mlb-813047',changed)))

    def test_recorded_touchdowns_exclude_field_goals_extra_points_and_two_point_tries(self):
        events=scoring_events('NFL','401772633',FIXTURE['nfl'])
        touchdowns=[p for p in FIXTURE['nfl']['scoringPlays'] if p['scoringType']['name']=='touchdown']
        self.assertEqual(len(touchdowns),len(events));self.assertEqual('Cleveland Browns',events[0]['team'])
        p=deepcopy(FIXTURE['nfl']);p['scoringPlays']=[dict(id='1',type={'abbreviation':'TD'},scoringType={'name':'two-point-conversion'},team={'id':'5','displayName':'Cleveland Browns'})]
        self.assertEqual([],scoring_events('NFL','401772633',p))
        for sport,payload in [('MLB',FIXTURE['mlb']),('NFL',FIXTURE['nfl'])]:
            with self.assertRaises(ValueError):scoring_events(sport,'wrong-game',payload)

    def test_empty_zero_zero_summary_baselines_before_first_touchdown(self):
        payload={'header':{'id':'401772633','competitions':[{'competitors':[{'score':'0'},{'score':'0'}]}]}}
        events=scoring_events('NFL','401772633',payload);self.assertEqual([],events)
        monitor=ScoringAlerts();monitor.sync(('NFL','401772633'));monitor.ingest(monitor.generation,events)
        touchdown=scoring_events('NFL','401772633',FIXTURE['nfl'])[:1]
        monitor.ingest(monitor.generation,touchdown);self.assertEqual(touchdown[0],monitor.tick()[0])
        competition=payload['header']['competitions'][0]
        competition['status']={'type':{'state':'pre'}}
        for team in competition['competitors']:team.pop('score')
        self.assertEqual([],scoring_events('NFL','401772633',payload))
        payload['header']['competitions'][0]['competitors'][0]['score']='7'
        with self.assertRaises(ValueError):scoring_events('NFL','401772633',payload)

    def test_seed_deduplicate_expire_and_no_replay_after_switch_outage_or_restart(self):
        clock=[0];s=ScoringAlerts(clock=lambda:clock[0]);events=scoring_events('NFL','401772633',FIXTURE['nfl'])
        s.sync(('NFL','401772633'));g=s.generation;s.ingest(g,events[:1]);self.assertIsNone(s.tick()[0])
        s.ingest(g,events[:2]);self.assertEqual(events[1],s.tick()[0]);s.ingest(g,events[:2]);self.assertEqual([],s.queue)
        clock[0]=8;self.assertEqual((None,True),s.tick())
        s.failed(g);s.ingest(g,events);self.assertIsNone(s.tick()[0])
        s.sync(None);s.sync(('NFL','401772633'));self.assertFalse(s.ingest(g,events))
        s.ingest(s.generation,events);self.assertIsNone(s.tick()[0])


class HistoryAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_official_date_filters_finals_doubleheaders_and_wrong_day(self):
        def raw(pk,day,state):
            return dict(gamePk=pk,officialDate=day,status={'abstractGameState':state},teams={'away':{'team':{'id':1,'abbreviation':'A'},'score':1},'home':{'team':{'id':2,'abbreviation':'B'},'score':2}})
        payload={'dates':[{'date':'2025-10-04','games':[raw(1,'2025-10-04','Final'),raw(2,'2025-10-04','Final'),raw(3,'2025-10-03','Final'),raw(4,'2025-10-04','Live')]}]}
        def respond(request):
            self.assertEqual('2025-10-04',request.url.params['date']);return httpx.Response(200,json=payload)
        async with httpx.AsyncClient(base_url='https://statsapi.mlb.com/api/v1',transport=httpx.MockTransport(respond)) as client:
            a=MlbStatsApiAdapter(client=client)
            self.assertEqual(['mlb-1','mlb-2'],[g['gameId'] for g in await a.get_final_games('2025-10-04')])


class DateAndAlertRuntimeTests(unittest.IsolatedAsyncioTestCase):
    setUp=helpers.ControllerSettingsTests.setUp
    tearDown=helpers.ControllerSettingsTests.tearDown
    event=helpers.ControllerSettingsTests.event
    press=helpers.ControllerSettingsTests.press

    def visible_mlb(self):
        r=self.r;r.home_active=False;r.project['data']['mode']='live';r.last_success=monotonic();r.last_error=None;r.fetched_utc=datetime.now(timezone.utc).isoformat()
        r.games=[mlb_game(status='in_progress')];r.transport.update([dict(kind='game',gameId=r.games[0]['gameId'],scene='live',dwellSec=60)],r.games)
        r._team_day=datetime.now(r.timezone).date()
        r._recap_window=None

    async def test_remote_date_picker_and_timeout_even_hold_and_menu(self):
        self.press('select')
        for _ in range(6):self.press('down')
        self.press('a');self.assertEqual('history',self.r.controller_settings.page)
        expected=datetime.now(self.r.timezone).date()-timedelta(days=1)
        self.assertEqual(expected,self.r.controller_settings.history_date)
        self.press('left');self.press('a');self.assertEqual((expected-timedelta(days=1)).isoformat(),self.r.history.date)
        self.assertFalse(self.r.controller_settings.active)
        self.r.history.apply(self.r.history.generation,final_cards([mlb_game()],[],self.r.history.date,str(self.r.timezone)),[],8,8)
        deadline=self.r.history.deadline;self.press('b');self.assertTrue(self.r.history.transport.held)
        self.press('a');self.press('select');self.assertEqual(deadline,self.r.history.deadline)
        self.r.history.deadline=0;self.r._render(datetime.now(self.r.timezone));self.assertFalse(self.r.history.active)
        self.assertTrue(self.r.controller_settings.active)
        self.press('a');self.assertFalse(self.r.controller_settings.active)

    async def test_history_fetch_isolated_partial_failure_and_full_date_on_each_sport(self):
        r=self.r;live_games=deepcopy(r.games);live_nfl=r.nfl_snapshot
        r._web_set_history({'date':'2025-10-05'})
        with patch('scoreboard_device.runtime.MlbStatsApiAdapter') as adapter, patch.object(r.history_nfl_feed,'fetch',return_value={'games':[nfl_game()],'freshness':'fresh'}):
            adapter.return_value.get_final_games=AsyncMock(return_value=[mlb_game()]);adapter.return_value.close=AsyncMock()
            await r._fetch_history()
        self.assertEqual(['MLB','NFL'],[c['sport'] for c in r.history.cards]);self.assertEqual(live_games,r.games);self.assertIs(live_nfl,r.nfl_snapshot)
        for _ in range(2):
            with patch('scoreboard_device.history._draw_text') as draw:
                frame=r._render(datetime.now(r.timezone))
                self.assertEqual('SUNDAY OCTOBER 5 2025',draw.call_args_list[0].args[2]);self.assertEqual((128,32),(frame.width,frame.height))
            r.command_next()
        r._web_set_history({'date':'2025-10-05'})
        with patch('scoreboard_device.runtime.MlbStatsApiAdapter') as adapter, patch.object(r.history_nfl_feed,'fetch',return_value={'games':[nfl_game()],'freshness':'fresh'}):
            adapter.return_value.get_final_games=AsyncMock(side_effect=RuntimeError('offline'));adapter.return_value.close=AsyncMock();await r._fetch_history()
        self.assertEqual(1,len(r.history.cards));self.assertEqual(['MLB DATA OFFLINE'],r.history.errors)
        r.command_next();r._render(datetime.now(r.timezone))
        for day in ('2025-09-24','2025-10-05','2025-12-31'):
            self.assertLessEqual(measure_text(r.fonts['4x6'],date_label(day)),124)
        self.press('x');self.assertFalse(r.history.active)

    async def test_old_history_reply_cannot_overwrite_new_date_or_exit(self):
        r=self.r;r._web_set_history({'date':'2025-10-04'});started=asyncio.Event();release=asyncio.Event()
        async def delayed(day):started.set();await release.wait();return [mlb_game()]
        with patch('scoreboard_device.runtime.MlbStatsApiAdapter') as adapter,patch.object(r.history_nfl_feed,'fetch',return_value={'games':[],'freshness':'fresh'}):
            adapter.return_value.get_final_games=AsyncMock(side_effect=delayed);adapter.return_value.close=AsyncMock()
            task=asyncio.create_task(r._fetch_history());await started.wait();r._web_set_history({'date':'2025-10-03'});release.set();await task
        self.assertEqual('2025-10-03',r.history.date);self.assertTrue(r.history.loading);self.assertEqual([],r.history.cards)
        r._web_control_home();self.assertFalse(r.history.active)

    async def test_alert_plays_over_every_mlb_layout_and_nfl_layout_then_resumes_same_game(self):
        r=self.r;clock=[0];r.scoring_alerts=ScoringAlerts(clock=lambda:clock[0]);events=scoring_events('MLB','mlb-813047',FIXTURE['mlb'])
        for layout in ('classic','broadcastRows','broadcastLogos'):
            with self.subTest(layout=layout):
                self.visible_mlb();r.project['designOverrides']['layoutPreset']=layout
                r.scoring_alerts.sync(None);r.scoring_alerts.sync(('MLB','mlb-813047'))
                with patch('scoreboard_device.runtime.fetch_scoring_events',side_effect=[events[:1],events[:2]]):
                    await r._fetch_scoring();self.assertIsNone(r.scoring_alerts.active);await r._fetch_scoring()
                with patch('scoreboard_device.scoring_alerts._draw_text') as draw:
                    r._render(datetime.now(r.timezone));self.assertEqual('HOME RUN',draw.call_args_list[0].args[2])
                self.assertEqual('scoringAlert',r.status()['display']['scene']);key=r.transport.current['gameId']
                clock[0]+=8;r._render(datetime.now(r.timezone));self.assertIsNone(r.scoring_alerts.active);self.assertEqual(key,r.transport.current['gameId'])
        for layout in ('rows','compact'):
            g=nfl_game(completed=False,day=datetime.now(timezone.utc).isoformat());r.nfl_snapshot=dict(date=datetime.now(r.timezone).date().isoformat(),games=[g],freshness='fresh',fetchedUtc=datetime.now(timezone.utc).isoformat())
            r.project['nfl']=r._web_get_config()['nfl'];r.project['nfl']['layout']=layout;r.transport.update([dict(kind='nfl',gameId=g['id'],dwellSec=60,completed=False)],[])
            r.scoring_alerts.sync(None);r.scoring_alerts.sync(('NFL',g['id']));events=scoring_events('NFL',g['id'],FIXTURE['nfl'])
            r.scoring_alerts.ingest(r.scoring_alerts.generation,events[:1]);r.scoring_alerts.ingest(r.scoring_alerts.generation,events[:2])
            with patch('scoreboard_device.scoring_alerts._draw_text') as draw:
                r._render(datetime.now(r.timezone));self.assertEqual('TOUCHDOWN',draw.call_args_list[0].args[2])
            self.assertEqual('scoringAlert',r.status()['display']['scene']);clock[0]+=8;r._render(datetime.now(r.timezone))

    async def test_delayed_scoring_reply_cannot_cover_another_game_home_history_or_surprise(self):
        self.visible_mlb();r=self.r;r.scoring_alerts.sync(('MLB','mlb-813047'));events=scoring_events('MLB','mlb-813047',FIXTURE['mlb']);r.scoring_alerts.ingest(r.scoring_alerts.generation,events[:1])
        def switch(*args):r._web_control_home();return events
        with patch('scoreboard_device.runtime.fetch_scoring_events',side_effect=switch):await r._fetch_scoring()
        self.assertEqual([],r.scoring_alerts.queue)
        r._reveal_active=True
        with self.assertRaises(ValueError):r._web_set_history({'date':'2025-10-04'})
        self.press('y');self.assertFalse(r.history.active);self.assertIsNone(r._render(datetime.now(r.timezone)))
        r._reveal_active=False

    async def test_history_endpoint_pin_auth_and_future_rejection_preserve_config(self):
        r=self.r;before=r._web_get_config();r.status_server.start();url='http://127.0.0.1:%s/api/history' % r.status_server.server.server_address[1]
        pin=(self.root/'state/broadcast-pin').read_text().strip()
        def post(value,authorized):
            request=urllib.request.Request(url,data=json.dumps({'date':value}).encode(),headers={'Content-Type':'application/json',**({'X-Scoreboard-Broadcast-Pin':pin} if authorized else {})})
            return urllib.request.urlopen(request,timeout=5)
        try:
            with self.assertRaises(urllib.error.HTTPError) as rejected:post('2025-10-04',False)
            self.assertEqual(401,rejected.exception.code);rejected.exception.close()
            with post('2025-10-04',True) as response:self.assertEqual('2025-10-04',json.load(response)['date'])
            with self.assertRaises(urllib.error.HTTPError) as rejected:post('2099-01-01',True)
            self.assertEqual(400,rejected.exception.code);rejected.exception.close();self.assertEqual('2025-10-04',r.history.date)
            with post(None,True) as response:self.assertFalse(json.load(response)['active'])
            self.assertEqual(before,r._web_get_config())
        finally:r.status_server.close()

    async def test_main_loop_loads_history_resets_to_live_and_polls_alerts_without_replaying(self):
        r=self.r;self.visible_mlb();events=scoring_events('MLB','mlb-813047',FIXTURE['mlb'])
        r._web_set_history({'date':'2025-10-05'})
        for name in ('next_fetch','next_nfl_fetch','next_recap_fetch','next_team_fetch'):
            setattr(r,name,monotonic()+3600)
        async def until(condition):
            for _ in range(100):
                if condition():return
                await asyncio.sleep(.05)
            self.fail('Runtime did not reach the expected state')
        with patch.object(r,'_fetch',new=AsyncMock()),patch.object(r,'_fetch_nfl',new=AsyncMock()),patch.object(r,'_fetch_team',new=AsyncMock()),patch.object(r,'_fetch_recap_window',new=AsyncMock()),patch('scoreboard_device.runtime.MlbStatsApiAdapter') as adapter,patch.object(r.history_nfl_feed,'fetch',return_value={'games':[nfl_game()],'freshness':'fresh'}),patch('scoreboard_device.runtime.fetch_scoring_events',side_effect=lambda *args: events[:1] if r.scoring_alerts.seen is None else events[:2]):
            adapter.return_value.get_final_games=AsyncMock(return_value=[mlb_game()]);adapter.return_value.close=AsyncMock()
            task=asyncio.create_task(r.run())
            try:
                await until(lambda:not r.history.loading)
                self.assertEqual(2,len(r.history.cards));self.assertEqual('history',r.status()['display']['scene'])
                r.history.deadline=0
                await until(lambda:r.scoring_alerts.seen is not None)
                self.assertFalse(r.history.active);self.assertIsNone(r.scoring_alerts.active)
                r.scoring_alerts.next_fetch=0
                await until(lambda:r.scoring_alerts.active is not None)
                self.assertEqual('HOME RUN',r.scoring_alerts.active['message'])
                self.assertEqual('scoringAlert',r.status()['display']['scene'])
            finally:
                r.stop();await asyncio.wait_for(task,5)

    async def test_walkoff_final_poll_and_no_alert_under_other_views(self):
        r=self.r;events=scoring_events('MLB','mlb-813047',FIXTURE['mlb'])
        self.visible_mlb();r.scoring_alerts.sync(('MLB','mlb-813047'));r.scoring_alerts.ingest(r.scoring_alerts.generation,events[:1])
        r.games[0]['status']='final'
        with patch('scoreboard_device.runtime.fetch_scoring_events',return_value=events[:2]):await r._fetch_scoring()
        r._render(datetime.now(r.timezone));self.assertTrue(r.scoring_alerts.finalized);self.assertEqual('HOME RUN',r.scoring_alerts.active['message'])
        for overlay in ('menu','arcade','history','surprise','different-game'):
            self.visible_mlb();r.controller_settings.close();r.arcade.exit();r.history.cancel();r._reveal_active=False
            r.scoring_alerts.sync(None);r.scoring_alerts.sync(('MLB','mlb-813047'));r.scoring_alerts.ingest(r.scoring_alerts.generation,events[:1])
            def switch(*args):
                if overlay=='menu':self.press('select')
                elif overlay=='arcade':r.arcade.input('select',True)
                elif overlay=='history':r._web_set_history({'date':'2025-10-04'})
                elif overlay=='surprise':r._reveal_active=True
                else:r.transport.update([dict(kind='game',gameId='mlb-other',scene='live',dwellSec=60)],[])
                return events
            with patch('scoreboard_device.runtime.fetch_scoring_events',side_effect=switch):await r._fetch_scoring()
            self.assertEqual([],r.scoring_alerts.queue,overlay)
        r._reveal_active=False
