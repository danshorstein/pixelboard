from __future__ import annotations
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / "targets/linux-sbc-hub75/runtime"))
from tests_py import test_device_runtime as helpers
from scoreboard_device.runtime import DeviceRuntime
from scoreboard_device.bluetooth_remote import EV_KEY, DEFAULT_KEY_CODES
import json
import urllib.error
import urllib.request
from scoreboard_device.arcade import ArcadeController
from scoreboard_device.arcade_progress import ArcadeProgress

class ArcadeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = helpers.DeviceRuntimeTests()._staged_runtime_root(Path(self.tmp.name))
        self.runtime = DeviceRuntime(root, output_kind='simulator')
        self.runtime.project['quietHours']['enabled'] = False
        self.now = 100.0
        self.runtime.arcade = ArcadeController(clock=lambda: self.now)

    def tearDown(self):
        self.runtime.bluetooth_remote.close()
        self.runtime.buttons.close()
        self.runtime.output.close()
        self.runtime.status_server.server.server_close()
        self.tmp.cleanup()

    def press(self, name):
        remote = self.runtime.bluetooth_remote
        remote._handle_event(EV_KEY, DEFAULT_KEY_CODES[name], 1)
        remote._handle_event(EV_KEY, DEFAULT_KEY_CODES[name], 0)

    def open_arcade(self):
        self.press('select'); self.press('down'); self.press('a')

    def test_actual_evdev_buttons_enter_play_render_and_exit_without_next_hold(self):
        r = self.runtime
        initial = r.status()['buttons'].copy()
        self.open_arcade(); self.assertTrue(r.status()['arcade']['menu']); self.assertEqual('menu', r.arcade.screen)
        self.press('down'); self.press('a')
        self.assertEqual('snake', r.status()['arcade']['game'])
        self.now += .2
        frame = r._render(datetime.now(r.timezone))
        self.assertEqual((128,32),(frame.width,frame.height))
        self.assertEqual('arcade',r.status()['display']['scene'])
        self.assertEqual(initial,r.status()['buttons'])
        self.press('start'); self.assertTrue(r.arcade.paused)
        self.press('b'); self.assertTrue(r.arcade.menu)
        self.press('select'); self.assertFalse(r.arcade.active)
        self.press('b')
        self.press('a'); self.assertEqual(1,r.bluetooth_remote.status()['nextPresses'])
        self.press('b'); self.assertEqual(1,r.bluetooth_remote.status()['holdPresses'])

    def test_held_pong_input_and_connection_loss_pause_in_real_runtime(self):
        r = self.runtime
        self.open_arcade(); self.press('down'); self.press('down'); self.press('a')
        r.bluetooth_remote._handle_event(EV_KEY,32,1)
        self.now += .08; r._render(datetime.now(r.timezone))
        self.assertEqual(16,r.arcade.state['player'])
        r.bluetooth_remote._clear_input()
        self.assertTrue(r.arcade.paused); self.assertFalse(r.arcade.held)
        self.now += 10; r._render(datetime.now(r.timezone))
        self.assertEqual(16,r.arcade.state['player'])
        self.press('a'); self.assertFalse(r.arcade.paused)
        r.command_next(); self.assertFalse(r.arcade.active)

    def test_quiet_sleep_prevents_entry_and_pauses_active_game(self):
        r = self.runtime
        self.open_arcade(); self.press('a')
        now = datetime.now(r.timezone)
        r.project['quietHours'] = {'enabled':True,'start':'00:00','end':'23:59','behavior':'sleep'}
        self.assertIsNotNone(r._render(now)); self.assertTrue(r.arcade.paused)
        self.assertEqual(15, r.output.brightness)
        r.arcade.exit(); self.press('select'); self.assertFalse(r.arcade.active)

    def test_quiet_hours_show_closed_arcade_instead_of_games(self):
        r = self.runtime
        now = datetime.now(r.timezone)
        r.project['quietHours'] = {'enabled': True, 'behavior': 'dim',
                                   'start': now.strftime('%H:%M'), 'end': (now.replace(hour=(now.hour + 2) % 24)).strftime('%H:%M')}
        self.press('select'); self.press('down'); self.press('a')
        self.assertEqual('closed', r.arcade.screen)
        self.assertFalse(r.status()['arcade']['available'])
        frame = r._render(datetime.now(r.timezone))
        self.assertEqual((128, 32), (frame.width, frame.height))
        self.press('a'); self.assertFalse(r.arcade.active)

    def test_dashboard_arcade_api_needs_pin_and_edits_shared_progress(self):
        r = self.runtime
        store = ArcadeProgress(r.root / 'state' / 'arcade-progress.json')
        store.record('rider', 120, 15)
        r.arcade = ArcadeController(clock=lambda: self.now, store=store)
        r.status_server.start()
        try:
            base = 'http://127.0.0.1:' + str(r.status_server.server.server_address[1])
            with urllib.request.urlopen(base + '/api/arcade') as response:
                data = json.load(response)
            self.assertEqual((15, 120), (data['gems'], data['best']['rider']))
            self.assertIn('happyHour', data)
            payload = json.dumps({'action': 'gems', 'amount': 40}).encode()
            bad = urllib.request.Request(base + '/api/arcade', data=payload, method='POST',
                                         headers={'Content-Type': 'application/json', 'X-Scoreboard-Broadcast-Pin': '000000'})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(bad)
            self.assertEqual(401, error.exception.code)
            from scoreboard_device.admin_auth import BroadcastPinStore
            headers = {'Content-Type': 'application/json',
                       'X-Scoreboard-Broadcast-Pin': BroadcastPinStore(r.root / 'state').get_or_create()}
            with urllib.request.urlopen(urllib.request.Request(base + '/api/arcade', data=payload, headers=headers, method='POST')) as response:
                self.assertEqual(55, json.load(response)['gems'])
            reset = json.dumps({'action': 'resetScores'}).encode()
            with urllib.request.urlopen(urllib.request.Request(base + '/api/arcade', data=reset, headers=headers, method='POST')) as response:
                self.assertEqual(0, json.load(response)['best']['rider'])
            saved = ArcadeProgress(r.root / 'state' / 'arcade-progress.json').data
            self.assertEqual((55, 0), (saved['gems'], saved['best']['rider']))
            with urllib.request.urlopen(base + '/') as response:
                html = response.read().decode()
            self.assertIn('Pixelboard Arcade', html); self.assertIn('loadArcade()', html)
        finally:
            r.status_server.close()
