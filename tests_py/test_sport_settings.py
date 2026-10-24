import asyncio
from copy import deepcopy
from datetime import datetime
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from shared_py.sports import sports_settings, validate_sports, filter_games, TEAM_CATALOG
from shared_py.league_feed import LeagueFeed, demo
from shared_py.sports_frame import sports_frame
from shared_py.bdf import parse_bdf
from tests_py import test_controller_settings as helpers
ROOT=Path(__file__).resolve().parents[1]

class SportPolicyTests(unittest.TestCase):
    def test_old_projects_retain_choices_and_filters_are_league_scoped(self):
        settings=sports_settings({'nfl':{'enabled':True}})
        self.assertEqual([k for k,v in settings.items() if v['enabled']],['mlb','nfl','team'])
        legacy=sports_settings({'nfl':{'enabled':True,'favoritesOnly':True,'favorites':['BUF']}})
        self.assertEqual(['BUF'],legacy['nfl']['teams'])
        game=demo('nba','2026-10-24')[0]
        settings['nba']={'enabled':True,'teams':['BOS']}
        self.assertEqual([game],filter_games(settings,'nba',[game]))
        settings['nba']['teams']=[];self.assertEqual([],filter_games(settings,'nba',[game]))
        for value in [{'fake':{}},{'nba':{'enabled':1,'teams':None}},{'nhl':{'enabled':True,'teams':['BOS','BOS']}},{'nba':{'enabled':True,'teams':['FLA']}}]:
            with self.assertRaises(ValueError):validate_sports(value)
        self.assertEqual(30,len(TEAM_CATALOG['nba']));self.assertEqual(32,len(TEAM_CATALOG['nhl']))
    def test_project_schema_preserves_optional_sports_on_save_and_reload(self):
        from backend.project_store import ProjectStore
        project=json.loads((ROOT/'fixtures/project.json').read_text())
        project['sports']={'nhl':{'enabled':True,'teams':['PHI']},'mlb':{'enabled':False,'teams':None}}
        with tempfile.TemporaryDirectory() as d:
            store=ProjectStore(Path(d))
            valid=store.validate(project)
            self.assertEqual(project['sports'],valid['sports'])
            valid['sports']['nhl']['teams']=['NOT_A_TEAM']
            with self.assertRaises(ValueError):store.validate(valid)
    def test_exact_frames_match_ts_frozen_references(self):
        fonts={n:parse_bdf((ROOT/f'definition/mlb-classic/fonts/{n}.bdf').read_text()) for n in ('4x6','6x10')}
        for case in json.loads((ROOT/'fixtures/sports-frame-cases.json').read_text()):
            self.assertEqual(case['sha256'],hashlib.sha256(sports_frame(case['game'],fonts,case['stale'],case['held']).data).hexdigest(),case['name'])
    def test_durable_feed_cache_is_same_date_only_and_bounded(self):
        from tests_py.test_sports_preview import payload
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'nba.json'
            client=httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,json=payload())))
            with patch('shared_py.league_feed.httpx.stream',side_effect=lambda *a,**kw:client.stream(*a,**kw)):
                value=LeagueFeed('nba',path).fetch('2026-10-24')
            self.assertEqual('fresh',value['source']['freshness'])
            with patch('shared_py.league_feed.httpx.stream',side_effect=httpx.ConnectError('offline')):
                feed=LeagueFeed('nba',path)
                self.assertEqual('stale',feed.fetch('2026-10-24')['source']['freshness'])
                self.assertEqual('failed',feed.fetch('2026-10-25')['source']['freshness'])
                self.assertEqual([],feed.value['games'])
            client.close()

class SportRuntimeTests(unittest.TestCase):
    setUp=helpers.ControllerSettingsTests.setUp
    tearDown=helpers.ControllerSettingsTests.tearDown
    event=helpers.ControllerSettingsTests.event
    press=helpers.ControllerSettingsTests.press
    def enable_only(self,league,teams=None):
        c=self.r._web_get_config();s=deepcopy(c['sports'])
        for k in s:s[k]['enabled']=k==league
        s[league]['teams']=teams
        return self.r._web_update_config({'expectedVersion':c['version'],'sports':s})
    def seed(self):
        r=self.r;day=datetime.now(r.timezone).date().isoformat()
        r.league_snapshots={k:dict(date=day,games=demo(k,day),source=dict(freshness='fresh',fetchedUtc=datetime.now(r.timezone).isoformat())) for k in ('nba','nhl')}
    def test_nhl_only_removes_baseball_standings_calendar_and_nfl(self):
        self.seed();self.enable_only('nhl');r=self.r
        self.assertEqual({'nhl'},{i['kind'] for i in r.transport.items})
        frame=r._render(datetime.now(r.timezone));self.assertEqual(128,frame.width)
        self.assertEqual('nhl',r.status()['display']['scene'])
        self.assertTrue(r.status()['display']['game']['away']['abbr'])
        saved=json.loads((r.root/'config/project.json').read_text());self.assertTrue(saved['sports']['nhl']['enabled'])
        self.assertFalse(saved['sports']['mlb']['enabled'])
    def test_selected_teams_none_and_all_off_never_show_other_sports(self):
        self.seed();self.enable_only('nhl',['BOS']);self.assertFalse(any(i['kind']!='idle' for i in self.r.transport.items))
        self.enable_only('nhl',[]);self.assertFalse(any(i['kind']!='idle' for i in self.r.transport.items))
        c=self.r._web_get_config();s=c['sports']
        for v in s.values():v['enabled']=False
        self.r._web_update_config({'expectedVersion':c['version'],'sports':s})
        self.assertEqual({'idle'},{i['kind'] for i in self.r.transport.items})
        self.assertEqual(32,self.r._render(datetime.now(self.r.timezone)).height)
    def test_partial_save_preserves_teams_night_policy_and_rejects_conflict(self):
        self.seed();self.enable_only('nhl',['FLA']);r=self.r;c=r._web_get_config();night=deepcopy(c['quietHours'])
        r._web_update_config({'expectedVersion':c['version'],'brightness':{'normal':42}})
        self.assertEqual(['FLA'],r._web_get_config()['sports']['nhl']['teams']);self.assertEqual(night,r._web_get_config()['quietHours'])
        with self.assertRaises(RuntimeError):r._web_update_config({'expectedVersion':c['version'],'sports':{'nhl':{'enabled':False,'teams':None}}})
        self.assertTrue(r._web_get_config()['sports']['nhl']['enabled'])
    def test_remote_sports_menu_toggle_cancel_and_save(self):
        self.press('select');self.r.controller_settings.index=self.r.controller_settings.labels.index('SPORTS');self.press('a')
        self.assertEqual('sports',self.r.controller_settings.page)
        self.r.controller_settings.index=3;self.press('a')
        self.assertTrue(self.r.controller_settings.draft['sports']['nhl']['enabled'])
        self.press('select');self.assertFalse(self.r._web_get_config()['sports']['nhl']['enabled'])
        self.press('select');self.r.controller_settings.index=self.r.controller_settings.labels.index('SPORTS');self.press('a');self.r.controller_settings.index=3;self.press('a');self.r.controller_settings.index=5;self.press('a')
        self.assertTrue(self.r._web_get_config()['sports']['nhl']['enabled'])
    def test_disabled_and_late_fetch_never_reappears_in_rotation(self):
        r=self.r
        class Feed:
            def fetch(_self,day):
                self.enable_only('mlb')
                return dict(date=day,games=demo('nhl',day),source={'freshness':'fresh','refreshSec':30})
        self.enable_only('nhl');r.league_feeds['nhl']=Feed();asyncio.run(r._fetch_league('nhl'))
        self.assertNotIn('nhl',r.league_snapshots)
        self.assertFalse(any(i['kind']=='nhl' for i in r.transport.items))
        with patch.object(r.league_feeds['nba'],'fetch',side_effect=AssertionError('Disabled league requested')):asyncio.run(r._fetch_league('nba'))
    def test_hold_survives_snapshots_and_disabled_game_is_released(self):
        self.seed();self.enable_only('nhl');r=self.r
        key=r.transport.current['gameId'];r.transport.toggle_hold();r._refresh_playlist(datetime.now(r.timezone))
        self.assertTrue(r.transport.held);self.assertEqual(key,r.transport.current['gameId'])
        self.enable_only('nba');self.assertFalse(r.transport.held);self.assertTrue(all(i['kind']=='nba' for i in r.transport.items))
