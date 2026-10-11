from __future__ import annotations
import json
import sys
import tempfile
import unittest
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'targets/linux-sbc-hub75/runtime'))
from scoreboard_device.team import TeamSchedule, parse_calendar, upcoming_groups, team_schedule_frame
from scoreboard_device.runtime import DeviceRuntime
from tests_py import test_device_runtime as helpers
from shared_py.renderer import _draw_element, PixelBuffer
from shared_py.rotation import build_playlist

ICS = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:practice
DTSTART:20260618T120000Z
SUMMARY:Practice
END:VEVENT
BEGIN:VEVENT
UID:one
DTSTART:20260618T173000Z
DTEND:20260618T190000Z
SUMMARY:Sample Team vs Example Club
END:VEVENT
BEGIN:VEVENT
UID:two
DTSTART;TZID=America/New_York:20260618T150000
DTEND;TZID=America/New_York:20260618T163000
SUMMARY:Sample Team vs Example Club
END:VEVENT
BEGIN:VEVENT
UID:later
DTSTART:20260625T130000Z
SUMMARY:Sample Team @ Other Team
END:VEVENT
END:VCALENDAR"""
NOW = datetime.fromisoformat('2026-06-18T23:59:59-04:00')

class TeamTests(unittest.TestCase):
    def test_doubleheader_timezone_and_full_game_day_retention(self):
        events = parse_calendar(ICS)
        self.assertEqual(len(events), 4)
        self.assertEqual(events[2]['startUtc'], '2026-06-18T19:00:00+00:00')
        groups = upcoming_groups(events, NOW)
        self.assertEqual(len(groups[0]['games']), 2)
        tomorrow = datetime.fromisoformat('2026-06-19T00:00:00-04:00')
        self.assertEqual([g['date'] for g in upcoming_groups(events, tomorrow)], ['2026-06-25'])
        # The cutoff follows the configured local date, including DST.
        event = dict(events[1], startUtc='2026-11-01T05:30:00+00:00')
        self.assertEqual(len(upcoming_groups([event], datetime.fromisoformat('2026-11-01T23:59:59-05:00'))), 1)
        self.assertEqual(upcoming_groups([event], datetime.fromisoformat('2026-11-02T00:00:00-05:00')), [])

    def test_unfolding_cancellation_and_latest_revision(self):
        text = ICS.replace('Example Club', 'Test \r\n Bombers')
        duplicate = "BEGIN:VEVENT\nUID:one\nSEQUENCE:1\nDTSTART:20260618T173000Z\nSUMMARY:Sample Team vs Example Club\nSTATUS:CANCELLED\nEND:VEVENT\n"
        events = parse_calendar(text.replace('END:VCALENDAR', duplicate + 'END:VCALENDAR'))
        self.assertEqual([e['id'] for e in events], ['practice', 'two', 'later'])
        self.assertEqual(events[1]['opponent'], 'Test Bombers')
        with self.assertRaises(ValueError): parse_calendar('<html>bad</html>')

    def test_results_persist_replace_and_clear_per_game(self):
        with tempfile.TemporaryDirectory() as d:
            team = TeamSchedule(d); team.calendar['events'] = parse_calendar(ICS)
            team.update({'expectedVersion':1,'rank':2,'eventId':'one','result':'win'})
            team.update({'expectedVersion':2,'eventId':'one','result':'win'})
            team.update({'expectedVersion':3,'eventId':'two','result':'loss'})
            record = team.snapshot(NOW)
            self.assertEqual((record['wins'],record['losses'],record['rank']), (1,1,2))
            reloaded = TeamSchedule(d)
            self.assertEqual(reloaded.snapshot(NOW)['losses'], 1)
            reloaded.update({'expectedVersion':4,'eventId':'one','result':None})
            self.assertEqual(reloaded.snapshot(NOW)['wins'], 0)
            with self.assertRaises(RuntimeError): reloaded.update({'expectedVersion':1,'rank':4})
            with self.assertRaises(ValueError): reloaded.update({'expectedVersion':5,'rank':True})
            with self.assertRaises(ValueError): reloaded.update({'expectedVersion':5,'eventId':[],'result':'win'})

    def test_calendar_results_start_at_zero_and_are_added_once(self):
        with tempfile.TemporaryDirectory() as d:
            team = TeamSchedule(d)
            event = dict(parse_calendar(ICS)[1], id='scrimmage', startUtc='2026-06-18T13:00:00+00:00')
            team.calendar['events'] = [event]
            self.assertFalse(team.snapshot(NOW)['events'][0]['includedInStartingRecord'])
            team.update({'expectedVersion':1,'eventId':'scrimmage','result':'win'})
            self.assertEqual(team.snapshot(NOW)['wins'],1)
            team.update({'expectedVersion':2,'eventId':'scrimmage','result':'win'})
            self.assertEqual(team.snapshot(NOW)['wins'],1)
            self.assertTrue((Path(d)/'team-record.json').exists())

    def test_cache_failure_retains_data_and_hides_subscription(self):
        with tempfile.TemporaryDirectory() as d:
            team = TeamSchedule(d); team.calendar['events'] = parse_calendar(ICS)
            Path(d,'team-calendar-url').write_text('https://example.invalid/secret')
            with patch('scoreboard_device.team.urllib.request.urlopen', side_effect=Exception('https://example.invalid/secret')):
                self.assertFalse(team.refresh())
            snapshot = team.snapshot(NOW)
            self.assertEqual(len(snapshot['events']),3)
            self.assertNotIn('secret',json.dumps(snapshot))

    def test_practices_use_same_feed_but_never_game_groups_or_results(self):
        with tempfile.TemporaryDirectory() as d:
            team = TeamSchedule(d)
            events = parse_calendar(ICS.replace('SUMMARY:Practice', 'SUMMARY:Team Practice\nLOCATION:Field 2'))
            team.calendar = {'events': events, 'fetchedUtc': '2026-06-18T10:00:00Z'}
            now = datetime.fromisoformat('2026-06-18T07:00:00-04:00')
            snapshot = team.snapshot(now)
            self.assertEqual([p['id'] for p in snapshot['upcomingPractices']], ['practice'])
            self.assertEqual(snapshot['upcomingPractices'][0]['location'], 'Field 2')
            self.assertEqual([e['id'] for e in snapshot['events']], ['one', 'two', 'later'])
            self.assertTrue(all(e['kind'] == 'game' for g in snapshot['groups'] for e in g['games']))
            with self.assertRaisesRegex(ValueError, 'Practices'):
                team.update({'expectedVersion':1,'eventId':'practice','result':'win'})
            self.assertEqual(team.snapshot(now)['wins'], 0)
            from scoreboard_device.team import _write
            _write(Path(d)/'team-schedule.json', team.calendar)
            self.assertEqual(TeamSchedule(d).snapshot(now)['upcomingPractices'], snapshot['upcomingPractices'])
            self.assertEqual(TeamSchedule(d).snapshot(datetime.fromisoformat('2026-06-19T00:00:00-04:00'))['upcomingPractices'], [])

    def test_cancelled_practice_without_summary_and_ended_practice_are_excluded(self):
        events = parse_calendar(ICS.replace('END:VCALENDAR', 'BEGIN:VEVENT\nUID:practice\nSEQUENCE:1\nSTATUS:CANCELLED\nEND:VEVENT\nEND:VCALENDAR'))
        self.assertFalse(any(e['id'] == 'practice' for e in events))
        from scoreboard_device.team import upcoming_practices
        practice = dict(parse_calendar(ICS)[0], endUtc='2026-06-18T13:00:00+00:00')
        self.assertEqual(upcoming_practices([practice], NOW), [])
        # An event labelled practice must never be classified as a game even with "vs" in its title.
        event = parse_calendar(ICS.replace('SUMMARY:Practice', 'SUMMARY:Practice vs pitching machine'))[0]
        self.assertEqual(event['kind'], 'practice')

    def test_corrupt_cache_and_record_use_safe_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'team-schedule.json').write_text('{"events":[{}]}')
            Path(d,'team-record.json').write_text('{"rank":null,"results":{}}')
            snapshot = TeamSchedule(d).snapshot(NOW)
            self.assertEqual((snapshot['wins'],snapshot['losses'],snapshot['rank']), (0,0,1))
            self.assertEqual(snapshot['groups'],[])

    def test_only_team_logo_contrast_changes_and_transparency_survives(self):
        for key, expected in [('team-logo:test:16',(220,220,220,255)),('plain',(0,0,0,255))]:
            frame = PixelBuffer(4,2)
            _draw_element(frame, {'type':'sprite','asset':key,'mode':'rgb','x':0,'y':0},
                {'assets':{key:{'width':2,'height':1,'data':[0,0,0,255,0,0,0,0]}},'bindings':{}})
            self.assertEqual(tuple(frame.data[:4]),expected)
            self.assertEqual(tuple(frame.data[4:8]),(0,0,0,255))

class TeamRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = helpers.DeviceRuntimeTests()._staged_runtime_root(Path(self.tmp.name))
        path = self.root / 'config/runtime-config.json'
        c=json.loads(path.read_text());c['status']={'host':'127.0.0.1','port':0};path.write_text(json.dumps(c))
        self.r=DeviceRuntime(self.root,output_kind='simulator')
        self.r.project['quietHours']['enabled']=False
        self.r.team.calendar={'events':parse_calendar(ICS),'fetchedUtc':'2026-06-18T10:00:00Z'}
    def tearDown(self):
        self.r.status_server.close() if self.r.status_server.thread.is_alive() else self.r.status_server.server.server_close()
        self.r.bluetooth_remote.close();self.r.buttons.close();self.r.output.close();self.tmp.cleanup()
    def test_all_layouts_show_paper_without_mlb_and_keep_distinct_cards(self):
        for layout in ('classic','broadcastRows','broadcastLogos'):
            self.r.project.setdefault('designOverrides',{})['layoutPreset']=layout
            self.r._refresh_playlist(NOW)
            cards=[i for i in self.r.transport.items if i['kind']=='team']
            self.assertEqual(len(cards),4)
            self.r.transport.index=next(i for i,v in enumerate(self.r.transport.items) if v['kind']=='team')
            frame=self.r._render(NOW)
            self.assertEqual((frame.width,frame.height),(128,32))
            self.assertEqual(bytes(frame.data),bytes(team_schedule_frame(self.r.team.snapshot(NOW),self.r.fonts,self.r.logo_assets).data))
            self.r.transport.next()
            current=dict(self.r.transport.current)
            self.r._refresh_playlist(NOW)
            self.assertEqual(self.r.transport.current,current)
        self.r._render(datetime.fromisoformat('2026-06-19T00:00:00-04:00'))
        self.assertFalse(any('2026-06-18' in i.get('groupId','') for i in self.r.transport.items))
    def test_practice_cards_are_distinct_and_show_time_and_location(self):
        now = datetime.fromisoformat('2026-06-18T07:00:00-04:00')
        self.r.team.calendar['events'][0]['location'] = 'Field 2'
        self.r._refresh_playlist(now)
        cards = [i for i in self.r.transport.items if i.get('practiceId')]
        self.assertEqual([i['practiceId'] for i in cards], ['practice'])
        self.r.transport.index = self.r.transport.items.index(cards[0])
        self.r._in_morning_window = lambda _: False
        from unittest.mock import patch
        import scoreboard_device.team as module
        labels = []
        draw = module._draw_text
        def record(*args, **kwargs):
            labels.append(args[2]); return draw(*args, **kwargs)
        with patch('scoreboard_device.team._draw_text', side_effect=record):
            self.r._render(now)
        self.assertIn('PRACTICE', labels)
        self.assertIn('8:00AM', labels)
        self.assertIn('Field 2', labels)
        self.assertNotIn('GAME DAY', labels)
        self.r._render(datetime.fromisoformat('2026-06-18T08:00:00-04:00'))
        self.assertFalse(any(i.get('practiceId') for i in self.r.transport.items))

    def test_remote_r_opens_team_without_entering_arcade(self):
        self.assertTrue(self.r._remote_input('r',True))
        self.assertTrue(self.r._remote_input('r',False))
        self.assertEqual(self.r.transport.current['groupId'],'summary')
        self.assertFalse(self.r.arcade.active)
    def test_real_http_household_save_and_show(self):
        self.r.status_server.start()
        base='http://127.0.0.1:'+str(self.r.status_server.server.server_address[1])
        with urllib.request.urlopen(base+'/api/team') as response: data=json.load(response)
        self.assertEqual(data['wins'],0)
        payload=json.dumps({'expectedVersion':data['version'],'rank':3,'eventId':'one','result':'win'}).encode()
        bad=urllib.request.Request(base+'/api/team',data=payload,headers={'Content-Type':'application/json','X-Scoreboard-Broadcast-Pin':'000000'},method='POST')
        with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(bad)
        self.assertEqual(error.exception.code,401)
        from scoreboard_device.admin_auth import BroadcastPinStore
        pin=BroadcastPinStore(self.root/'state').get_or_create()
        headers={'Content-Type':'application/json','X-Scoreboard-Broadcast-Pin':pin}
        good=urllib.request.Request(base+'/api/team',data=payload,headers=headers,method='POST')
        with urllib.request.urlopen(good) as response: saved=json.load(response)
        self.assertEqual((saved['wins'],saved['rank']),(1,3))
        with self.assertRaises(urllib.error.HTTPError) as error: urllib.request.urlopen(good)
        self.assertEqual(error.exception.code,409)
        request=urllib.request.Request(base+'/api/team/show',data=b'',headers=headers,method='POST')
        with urllib.request.urlopen(request) as response: self.assertTrue(json.load(response)['ok'])
        self.assertEqual(self.r.transport.current['kind'],'team')
        with urllib.request.urlopen(base+'/') as response: html=response.read().decode()
        self.assertIn('Team Schedule',html)
        self.assertIn('loadTeam()',html)
