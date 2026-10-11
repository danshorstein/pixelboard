from __future__ import annotations
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from shared_py.nfl_feed import NflFeed,selected_games,validate_settings,DEFAULT_NFL
from shared_py.nfl_frame import nfl_frame
from shared_py.bdf import parse_bdf
from tests_py import test_controller_settings as helpers
ROOT=Path(__file__).resolve().parents[1]
GAMES=json.loads((ROOT/'fixtures/nfl-demo.json').read_text())

class NflFeedTests(unittest.TestCase):
    def test_invalid_settings_rejected_and_selection_filters_real_ids(self):
        for bad in ({'dwellSec':True},{'enabled':1},{'favorites':['FAKE']},{'hiddenGames':['x','x']},{'layout':'unknown'}):
            with self.assertRaises(ValueError): validate_settings(bad)
        settings=validate_settings({'enabled':True,'hiddenGames':[GAMES[0]['id']],'liveOnly':True})
        found=selected_games(GAMES,settings)
        self.assertTrue(all(g['state']=='in' and g['id']!=GAMES[0]['id'] for g in found))
        self.assertEqual([],selected_games(GAMES,DEFAULT_NFL))

    def test_success_persists_and_repeated_requests_are_bounded(self):
        payload = {'events':[{'id':'101','name':'Test','date':'2026-09-13T17:00:00Z','competitions':[{'competitors':[
            {'homeAway':side,'team':{'id':str(i),'displayName':abbr,'abbreviation':abbr},'score':'7'}
            for i,(side,abbr) in enumerate((('home','BUF'),('away','NE')))
        ],'status':{'type':{'state':'in','shortDetail':'Q1','completed':False}}}]}]}
        response=httpx.Response(200,json=payload,request=httpx.Request('GET','https://example.com'))
        with tempfile.TemporaryDirectory() as d, patch('shared_py.nfl_feed.httpx.get',return_value=response) as get:
            feed=NflFeed(Path(d)/'cache.json')
            self.assertEqual('fresh',feed.fetch('2026-09-13')['freshness'])
            self.assertEqual('101',feed.fetch('2026-09-13')['games'][0]['id'])
            get.assert_called_once()
            self.assertEqual('101',NflFeed(feed.path).value['games'][0]['id'])

    def test_outage_same_date_cache_only_and_restart_survives(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'nfl.json';path.write_text(json.dumps(dict(date='2026-09-13',games=GAMES,fetchedUtc='2026-09-13T12:00:00+00:00')))
            feed=NflFeed(path)
            with patch('shared_py.nfl_feed.httpx.get',side_effect=httpx.ConnectError('offline')):
                self.assertEqual('stale',feed.fetch('2026-09-13')['freshness'])
                self.assertEqual(GAMES,NflFeed(path).fetch('2026-09-13')['games'])
                self.assertEqual([],feed.fetch('2026-10-05')['games'])
                self.assertEqual('failed',feed.value['freshness'])

    def test_both_layouts_all_scenarios_match_typescript_references(self):
        fonts={n:parse_bdf((ROOT/f'definition/mlb-classic/fonts/{n}.bdf').read_text()) for n in ('4x6','5x7','6x10')}
        actual=[hashlib.sha256(nfl_frame(g,fonts,l,stale).data).hexdigest() for g in GAMES for l in ('rows','compact') for stale in (False,True)]
        self.assertEqual(json.loads((ROOT/'fixtures/nfl-frame-hashes.json').read_text()),actual)

class NflRuntimeTests(unittest.TestCase):
    setUp = helpers.ControllerSettingsTests.setUp
    tearDown = helpers.ControllerSettingsTests.tearDown
    event = helpers.ControllerSettingsTests.event
    press = helpers.ControllerSettingsTests.press
    def test_nfl_menu_save_selection_rotation_render_and_disable(self):
        from datetime import datetime
        r=self.r
        r.nfl_snapshot=dict(date=datetime.now(r.timezone).date().isoformat(),games=GAMES,freshness='fresh',fetchedUtc=datetime.now(r.timezone).isoformat())
        self.press('select')
        for _ in range(3): self.press('down')
        self.press('a'); self.assertEqual('nfl',r.controller_settings.page)
        self.press('a'); self.press('down'); self.press('right')
        for _ in range(6): self.press('down')
        self.press('a')
        self.assertFalse(r.controller_settings.active)
        self.assertTrue(r._web_get_config()['nfl']['enabled'])
        self.assertEqual(9,r._web_get_config()['nfl']['dwellSec'])
        self.assertTrue(any(i['kind']=='nfl' for i in r.transport.items))
        r.transport.index=next(i for i,v in enumerate(r.transport.items) if v['kind']=='nfl')
        frame=r._render(datetime.now(r.timezone));self.assertEqual((128,32),(frame.width,frame.height))
        self.press('select')
        for _ in range(4): self.press('down')
        self.press('a');self.press('down');self.press('a')
        hidden=r.controller_settings.draft['nfl']['hiddenGames'][0]
        r._web_update_config(r.controller_settings.payload());r.controller_settings.close()
        self.assertFalse(any(i.get('gameId')==hidden and i['kind']=='nfl' for i in r.transport.items))
        c=r._web_get_config();c['nfl']['enabled']=False
        r._web_update_config({'expectedVersion':c['version'],'nfl':c['nfl']})
        self.assertFalse(any(i['kind']=='nfl' for i in r.transport.items))
        saved=json.loads((r.root/'config/project.json').read_text());self.assertFalse(saved['nfl']['enabled'])
