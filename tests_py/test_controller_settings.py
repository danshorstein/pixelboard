from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
import urllib.request
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'targets/linux-sbc-hub75/runtime'))
from scoreboard_device.runtime import DeviceRuntime
from scoreboard_device.bluetooth_remote import EV_KEY, DEFAULT_KEY_CODES
from shared_py.reveal import load_reveal, should_autoplay_on_boot
from shared_py.png import decode_rgba_png
from shared_py.reveal_frame import create_reveal_text_frame
from tests_py import test_device_runtime as helpers


class ControllerSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = helpers.DeviceRuntimeTests()._staged_runtime_root(Path(self.tmp.name))
        p = self.root / 'config/runtime-config.json'
        c = json.loads(p.read_text()); c['status'] = {'host': '127.0.0.1', 'port': 0}; p.write_text(json.dumps(c))
        self.r = DeviceRuntime(self.root, output_kind='simulator')
        self.r.project['quietHours']['enabled'] = False

    def tearDown(self):
        self.r.bluetooth_remote.close(); self.r.buttons.close(); self.r.output.close()
        self.r.status_server.server.server_close(); self.tmp.cleanup()

    def event(self, button, value):
        self.r.bluetooth_remote._handle_event(EV_KEY, DEFAULT_KEY_CODES[button], value)

    def press(self, button):
        self.event(button, 1); self.event(button, 0)

    def open_settings(self):
        self.press('select')
        self.press('down'); self.press('down'); self.press('a')
        self.assertTrue(self.r.controller_settings.active)
        self.assertEqual('settings', self.r.controller_settings.page)
        self.assertFalse(self.r.arcade.active)

    def test_single_select_opens_main_on_press_and_release_has_no_action(self):
        self.event('select',1)
        self.assertTrue(self.r.controller_settings.active)
        self.assertEqual('main',self.r.controller_settings.page)
        self.event('select',2); self.event('select',0)
        self.assertEqual('main',self.r.controller_settings.page)
        self.press('select'); self.assertFalse(self.r.controller_settings.active)
        self.assertFalse(self.r.arcade.active)

    def test_settings_save_all_values_and_persist(self):
        self.open_settings()
        old = self.r._web_get_config()
        self.press('right')
        self.press('down'); self.press('right')
        self.press('down'); self.press('right')
        self.press('down'); self.press('right')
        self.press('down'); self.press('right')
        draft = self.r.controller_settings.draft.copy()
        self.press('a')
        result = self.r._web_get_config()
        self.assertFalse(self.r.controller_settings.active)
        for k in ('brightness', 'layoutPreset', 'quietHours', 'wakeDurationSec'):
            self.assertEqual(draft[k], result[k])
        self.assertEqual(old['version'] + 1, result['version'])
        saved = json.loads((self.root / 'config/project.json').read_text())
        self.assertEqual(120, saved['controllerPreferences']['wakeDurationSec'])
        self.assertEqual(0, self.r.next_presses)

    def test_cancel_disconnect_and_timeout_discard_draft(self):
        old = self.r._web_get_config()
        for exit_kind in ('cancel', 'disconnect', 'timeout'):
            self.open_settings(); self.press('right')
            if exit_kind == 'cancel': self.press('b'); self.press('b')
            elif exit_kind == 'disconnect': self.r.bluetooth_remote._clear_input()
            else:
                self.r.controller_settings.last_input -= 61
                self.r._render(datetime.now(self.r.timezone))
            self.assertFalse(self.r.controller_settings.active)
            self.assertEqual(old, self.r._web_get_config())

    def test_web_conflict_reloads_instead_of_overwriting(self):
        self.open_settings(); self.press('right')
        c = self.r._web_get_config()
        self.r._web_update_config({'expectedVersion': c['version'], 'layoutPreset': 'broadcastLogos'})
        self.press('a')
        self.assertTrue(self.r.controller_settings.active)
        self.assertEqual('broadcastLogos', self.r.controller_settings.draft['layoutPreset'])
        self.assertIn('RELOADED', self.r.controller_settings.error)
        self.assertEqual(c['brightness'], self.r._web_get_config()['brightness'])

    def test_preview_uses_draft_without_persisting_and_return_shows_menu(self):
        self.open_settings(); self.press('down'); self.press('down'); self.press('right')
        self.press('x')
        with patch('scoreboard_device.runtime.render_scene', wraps=__import__('shared_py.renderer', fromlist=['render_scene']).render_scene) as render:
            f = self.r._render(datetime.now(self.r.timezone))
            self.assertEqual('broadcastRows', render.call_args.kwargs['overrides']['layoutPreset'])
            self.assertEqual((128, 32), (f.width, f.height))
        self.assertEqual('classic', self.r._web_get_config()['layoutPreset'])
        self.press('x'); self.assertFalse(self.r.controller_settings.preview)
        f = self.r._render(datetime.now(self.r.timezone)); self.assertTrue(any(f.data[i] for i in range(0, len(f.data), 4)))

    def test_sleep_wakes_on_first_button_without_next_then_expires(self):
        self.r.project['quietHours'] = {'enabled': True, 'start': '00:00', 'end': '23:59', 'behavior': 'sleep'}
        config = self.r._web_get_config()
        self.r._web_update_config({'expectedVersion': config['version'], 'wakeDurationSec': 120})
        self.press('a'); self.assertEqual(0, self.r.next_presses)
        self.assertTrue(self.r.status()['temporaryWake']['active'])
        self.assertIsNotNone(self.r._render(datetime.now(self.r.timezone)))
        self.r._wake_deadline -= 121
        sleeping_frame = self.r._render(datetime.now(self.r.timezone))
        expected = create_reveal_text_frame(
            sleeping_frame.width, sleeping_frame.height,
            ['PRESS ANY BUTTON TO CHECK SCORES FOR 120 SECONDS...'], self.r.fonts['4x6'],
        )
        self.assertEqual(expected.data, sleeping_frame.data)
        self.assertEqual(15, self.r.output.brightness)

    def test_second_select_after_waking_opens_main(self):
        self.r.project['quietHours'] = {'enabled': True, 'start': '00:00', 'end': '23:59', 'behavior': 'sleep'}
        self.press('select'); self.assertFalse(self.r.arcade.active)
        self.press('select'); self.assertTrue(self.r.controller_settings.active)

    def test_invalid_wake_duration_does_not_mutate_configuration(self):
        old = self.r._web_get_config()
        for value in (0, 601, True, '60'):
            with self.assertRaises(ValueError):
                self.r._web_update_config({'expectedVersion': old['version'], 'wakeDurationSec': value})
        self.assertEqual(old, self.r._web_get_config())

    def test_single_select_can_open_settings_after_waking(self):
        self.r.project['quietHours'] = {'enabled': True, 'start': '00:00', 'end': '23:59', 'behavior': 'sleep'}
        self.press('a'); self.open_settings(); self.assertIsNotNone(self.r._render(datetime.now(self.r.timezone)))

    def test_waiting_reveal_prompt_survives_reload_without_boot_autoplay(self):
        self.r._web_wait_reveal()
        self.assertTrue(self.r._web_reveal_status()['waitingForController'])
        self.assertFalse(should_autoplay_on_boot(load_reveal(self.r.reveal_path)))
        f = self.r._render(datetime.now(self.r.timezone))
        expected = create_reveal_text_frame(f.width, f.height, ['PRESS ANY KEY TO CONTINUE...'], self.r.fonts['4x6'])
        self.assertEqual(expected.data, f.data)
        other = DeviceRuntime(self.root, output_kind='simulator')
        try: self.assertTrue(other._reveal_waiting)
        finally:
            other.bluetooth_remote.close(); other.buttons.close(); other.output.close(); other.status_server.server.server_close()
        self.r._web_disarm_reveal(); self.assertFalse(self.r._reveal_waiting)

    def test_repeat_and_release_do_not_trigger_waiting_reveal(self):
        self.r._web_wait_reveal()
        with patch.object(self.r, '_web_play_reveal') as play:
            self.event('a', 2); self.event('a', 0); play.assert_not_called()

    def test_wait_http_uses_pin_and_stages_actual_message_and_cancel(self):
        self.r.status_server.start()
        try:
            base = 'http://127.0.0.1:' + str(self.r.status_server.server.server_address[1])
            def post(path, data):
                req = urllib.request.Request(base + path, data=json.dumps(data).encode(), method='POST', headers={'Content-Type': 'application/json', 'X-Scoreboard-Broadcast-Pin': '123456'})
                return json.load(urllib.request.urlopen(req))
            response = post('/api/message', {'lines': ['HELLO THERE'], 'dwellSec': 1, 'fireworks': False, 'waitForController': True})
            self.assertTrue(response['waitingForController'])
            self.assertEqual(['HELLO THERE'], self.r.project['reveal']['lines'])
            self.assertEqual(0, self.r.project['reveal']['fireworksDwellSec'])
            self.assertEqual('controller', load_reveal(self.r.reveal_path)['trigger'])
            self.assertEqual('disarmed', post('/reveal/disarm', {})['state'])
            c = self.r._web_get_config()
            post('/api/config', {'expectedVersion': c['version'], 'wakeDurationSec': 120})
            self.assertEqual(120, self.r._web_get_config()['wakeDurationSec'])
        finally: self.r.status_server.close()


class WaitingRevealPlaybackTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_run_waits_then_any_button_starts_once_without_skipping(self):
        for button in ('a', 'b', 'select', 'start', 'left', 'r'):
            with tempfile.TemporaryDirectory() as directory:
                root = helpers.DeviceRuntimeTests()._staged_runtime_root(Path(directory))
                p = root / 'config/runtime-config.json'; c = json.loads(p.read_text()); c['status'] = {'host': '127.0.0.1', 'port': 0}; p.write_text(json.dumps(c))
                r = DeviceRuntime(root, output_kind='simulator')
                r.project['data']['mode'] = 'demo'
                r.project['quietHours']['enabled'] = False
                r.project['reveal'] = {'lines': ['HI'], 'lineDwellSec': .1, 'fireworksDwellSec': 0}
                r._web_wait_reveal()
                task = asyncio.create_task(r.run())
                try:
                    await asyncio.sleep(.06)
                    self.assertTrue(r._reveal_waiting)
                    self.assertEqual('armed', load_reveal(r.reveal_path)['state'])
                    r.bluetooth_remote._handle_event(EV_KEY, DEFAULT_KEY_CODES[button], 1)
                    self.assertEqual('started', load_reveal(r.reveal_path)['state'])
                    r.bluetooth_remote._handle_event(EV_KEY, DEFAULT_KEY_CODES[button], 1)
                    r.bluetooth_remote._handle_event(EV_KEY, DEFAULT_KEY_CODES[button], 0)
                    await asyncio.sleep(.03)
                    self.assertTrue(r._reveal_active)
                    for code in DEFAULT_KEY_CODES.values():
                        r.bluetooth_remote._handle_event(EV_KEY, code, 1)
                        r.bluetooth_remote._handle_event(EV_KEY, code, 0)
                    r.command_next(); r.command_hold()
                    self.assertTrue(r._reveal_active)
                    self.assertFalse(r.arcade.active); self.assertEqual(0, r.next_presses); self.assertEqual(0, r.hold_presses)
                    r.bluetooth_remote._handle_event(EV_KEY, DEFAULT_KEY_CODES['select'], 1)
                    await asyncio.sleep(.15)
                    self.assertEqual('completed', load_reveal(r.reveal_path)['state'])
                    self.assertFalse(r._reveal_waiting); self.assertFalse(r._reveal_active)
                    r.bluetooth_remote._handle_event(EV_KEY, DEFAULT_KEY_CODES['select'], 0)
                    self.assertFalse(r.controller_settings.active)
                    r.bluetooth_remote._handle_event(EV_KEY, DEFAULT_KEY_CODES['select'], 1)
                    r.bluetooth_remote._handle_event(EV_KEY, DEFAULT_KEY_CODES['select'], 0)
                    self.assertTrue(r.controller_settings.active)
                finally:
                    r.stop(); await asyncio.wait_for(task, 2)
