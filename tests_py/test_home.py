from datetime import datetime, timedelta, timezone
import unittest
import json
import urllib.request
import urllib.error
from unittest.mock import patch

from tests_py import test_controller_settings as helpers
from scoreboard_device.home import home_frame


class HomeTests(unittest.TestCase):
    setUp = helpers.ControllerSettingsTests.setUp
    tearDown = helpers.ControllerSettingsTests.tearDown
    event = helpers.ControllerSettingsTests.event
    press = helpers.ControllerSettingsTests.press

    def test_shortcut_stays_home_and_a_returns_without_skipping_scores(self):
        self.press('y')
        self.assertTrue(self.r.home_active)
        now = datetime(2026, 10, 4, 18, 12, tzinfo=self.r.timezone)
        frame = self.r._render(now)
        self.assertEqual((128, 32), (frame.width, frame.height))
        self.assertEqual('home', self.r.status()['display']['scene'])
        with patch.object(self.r.transport, 'tick') as tick:
            self.r._render(now + timedelta(hours=2))
            tick.assert_not_called()
        self.assertTrue(self.r.home_active)
        self.press('a')
        self.assertFalse(self.r.home_active)
        self.assertEqual(0, self.r.next_presses)
        self.press('a')
        self.assertEqual(1, self.r.next_presses)

    def test_menu_home_and_scoreboard_choices(self):
        self.press('select'); self.press('up'); self.press('a')
        self.assertTrue(self.r.home_active)
        self.assertFalse(self.r.controller_settings.active)
        self.press('select')
        self.assertTrue(self.r.controller_settings.active)
        self.press('a')
        self.assertFalse(self.r.home_active)
        self.assertFalse(self.r.controller_settings.active)

    def test_shortcut_exits_arcade_and_discards_settings_draft(self):
        self.press('select'); self.press('down'); self.press('a')
        self.assertTrue(self.r.arcade.active)
        self.press('y')
        self.assertFalse(self.r.arcade.active)
        original = self.r._web_get_config()
        self.press('select'); self.press('down'); self.press('down'); self.press('a'); self.press('right')
        self.press('y')
        self.assertTrue(self.r.home_active)
        self.assertFalse(self.r.controller_settings.active)
        self.assertEqual(original, self.r._web_get_config())

    def test_home_respects_surprise_and_first_sleep_wake(self):
        self.r._reveal_active = True
        self.press('y'); self.r._web_control_home()
        self.assertFalse(self.r.home_active)
        self.r._reveal_active = False
        self.r._reveal_waiting = True
        self.r._web_control_home()
        self.assertFalse(self.r.home_active)
        self.r._reveal_waiting = False
        self.r.project['quietHours'] = {'enabled': True, 'start': '00:00', 'end': '23:59', 'behavior': 'sleep'}
        self.press('y')
        self.assertFalse(self.r.home_active)
        self.press('y')
        self.assertTrue(self.r.home_active)
        self.r._wake_deadline = 0
        self.assertIsNotNone(self.r._render(datetime.now(self.r.timezone)))
        self.assertEqual(15, self.r.output.brightness)

    def test_clock_uses_local_time_and_changes_at_midnight(self):
        self.press('y')
        utc = datetime(2026, 10, 5, 3, 59, tzinfo=timezone.utc)
        local = utc.astimezone(self.r.timezone)
        expected = home_frame(local, self.r.fonts)
        self.assertEqual(expected.data, self.r._render(utc).data)
        with patch('scoreboard_device.home._draw_text') as draw:
            home_frame(local, self.r.fonts)
            self.assertEqual('11:59 PM', draw.call_args_list[0].args[2])
            self.assertEqual('SUN OCT 4, 2026', draw.call_args_list[1].args[2])
            home_frame(local + timedelta(minutes=1), self.r.fonts)
            self.assertEqual('12:00 AM', draw.call_args_list[3].args[2])
            self.assertEqual('MON OCT 5, 2026', draw.call_args_list[4].args[2])
        self.assertNotEqual(expected.data, self.r._render(utc + timedelta(minutes=1)).data)

    def test_dashboard_home_requires_admin_and_does_not_change_preferences(self):
        before = self.r._web_get_config()
        self.r.status_server.start()
        url = 'http://127.0.0.1:%s/api/control/home' % self.r.status_server.server.server_address[1]
        try:
            with self.assertRaises(urllib.error.HTTPError) as rejected:
                urllib.request.urlopen(urllib.request.Request(url, method='POST'), timeout=5)
            self.assertEqual(401, rejected.exception.code)
            rejected.exception.close()
            self.assertFalse(self.r.home_active)
            request = urllib.request.Request(url, method='POST', headers={'X-Scoreboard-Broadcast-Pin': '123456'})
            with urllib.request.urlopen(request, timeout=5) as response:
                self.assertEqual('home', json.load(response)['display']['scene'])
            self.assertEqual(before, self.r._web_get_config())
        finally:
            self.r.status_server.close()
