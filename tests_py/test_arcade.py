from __future__ import annotations

import json
import tempfile
from datetime import datetime
import hashlib
import sys
import unittest
from pathlib import Path
from shared_py.arcade import KINDS, create_game, press_game, start_game, step_game, steer_snake, swing
from shared_py.arcade_frame import arcade_frame
from shared_py.bdf import parse_bdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'targets/linux-sbc-hub75/runtime'))
from scoreboard_device.arcade import MENU_ITEMS, ArcadeController
from scoreboard_device.arcade_progress import ArcadeProgress, happy_hour


def replay(case):
    s = create_game(case['kind'], case.get('seed', 727))
    s.update(case.get('patch', {}))
    for op in case['operations']:
        if op.get('action') == 'start': s = start_game(s)
        elif op.get('action') == 'swing': s = swing(s)
        elif op.get('action') in ('up', 'down', 'left', 'right'): s = steer_snake(s, op['action'])
        if op.get('press'): s = press_game(s, op['press'])
        for _ in range(op.get('ticks', 0)): s = step_game(s, set(op.get('held', [])))
    return s


class ArcadeParityTests(unittest.TestCase):
    def assert_state(self, actual, expected):
        if isinstance(expected, dict):
            self.assertEqual(set(expected), set(actual))
            for k in expected: self.assert_state(actual[k], expected[k])
        elif isinstance(expected, list):
            self.assertEqual(len(actual), len(expected))
            for a, b in zip(actual, expected): self.assert_state(a, b)
        elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
            self.assertAlmostEqual(actual, expected, delta=1e-10)
        else: self.assertEqual(actual, expected)

    def test_reference_replays_and_all_pixels(self):
        font = parse_bdf((ROOT / 'definition/mlb-classic/fonts/4x6.bdf').read_text())
        for case in json.loads((ROOT / 'fixtures/arcade-replays.json').read_text()):
            with self.subTest(case=case['name']):
                state = replay(case)
                self.assert_state(state, case['expectedState'])
                self.assertEqual(hashlib.sha256(arcade_frame(state, font, case.get('paused', False)).data).hexdigest(), case['sha256'])


class ArcadeControllerTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.c = ArcadeController(clock=lambda: self.now)

    def input(self, name):
        result = self.c.input(name, True)
        self.c.input(name, False)
        return result

    def test_scoreboard_actions_preserved_and_select_opens_menu(self):
        self.assertFalse(self.input('a')); self.assertFalse(self.input('b'))
        self.assertTrue(self.input('select')); self.assertEqual('menu', self.c.screen); self.assertTrue(self.c.menu)
        self.assertTrue(self.input('a')); self.assertEqual('running', self.c.state['status'])
        self.assertFalse(self.c.menu)
        self.assertTrue(self.input('select')); self.assertFalse(self.c.active)
        self.assertFalse(self.input('b'))

    def test_menu_choices_and_back_controls(self):
        self.input('select'); self.input('down'); self.input('a')
        self.assertEqual('snake', self.c.state['kind'])
        self.input('b'); self.assertTrue(self.c.menu)
        self.input('up'); self.input('up'); self.input('a')  # wraps to STYLE SHOP
        self.assertEqual('shop', self.c.screen)
        self.input('b'); self.input('up'); self.input('a')
        self.assertEqual('unicorn', self.c.state['kind'])
        self.input('start'); self.input('b'); self.input('up'); self.input('a')  # B is the bomb while playing
        self.assertEqual('soccer', self.c.state['kind'])
        self.input('b'); self.input('up'); self.input('a')
        self.assertEqual('bigleague', self.c.state['kind'])
        self.input('b'); self.input('b'); self.assertFalse(self.c.active)

    def test_pause_resume_and_restart_do_not_catch_up(self):
        self.input('select'); self.input('a'); self.now += .1; self.c.tick()
        before = self.c.state.copy()
        self.input('start'); self.now += 20; self.c.tick()
        self.assertEqual(before, self.c.state)
        self.input('start'); self.now += .02; self.c.tick()
        self.assertEqual(before['time'] + 20, self.c.state['time'])
        self.input('x'); self.assertEqual('ready', self.c.state['status'])
        self.input('a'); self.assertEqual('running', self.c.state['status'])

    def test_held_movement_stops_on_release_and_disconnect_requires_resume(self):
        self.input('select'); self.input('down'); self.input('down'); self.input('a')
        self.c.input('down', True); self.now += .08; self.c.tick()
        self.assertEqual(16, self.c.state['player'])
        self.c.input('down', False); self.now += .08; self.c.tick()
        self.assertEqual(16, self.c.state['player'])
        self.c.input('up', True); self.c.suspend()
        self.assertFalse(self.c.held); self.assertTrue(self.c.paused)
        self.now += .08; self.c.tick(); self.assertEqual(16, self.c.state['player'])
        self.input('a'); self.assertFalse(self.c.paused)

    def test_stall_is_bounded_and_inactivity_returns_to_scoreboard(self):
        self.input('select'); self.input('a'); self.now += 30; self.c.tick()
        self.assertLessEqual(self.c.state['time'], 250)
        self.now += 301; self.c.tick(); self.assertFalse(self.c.active)

    def test_held_input_prevents_idle_exit(self):
        self.input('select'); self.input('down'); self.input('down'); self.input('a'); self.c.input('up', True)
        self.now += 301; self.c.tick(); self.assertTrue(self.c.active)
        self.c.input('up', False); self.now += 301; self.c.tick(); self.assertFalse(self.c.active)

    def test_rider_accelerates_only_while_a_is_held(self):
        self.input('select'); self.c.selection = MENU_ITEMS.index('rider')
        self.assertEqual('rider', self.c.status()['game'])
        self.c.input('a', True)
        self.assertEqual(('rider', 'running'), (self.c.state['kind'], self.c.state['status']))
        start = self.c.state['x']
        self.now += 1; self.c.tick()
        self.assertGreater(self.c.state['vx'], 0); self.assertIn('a', self.c.held)
        self.c.input('a', False); self.assertNotIn('a', self.c.held)
        moving = self.c.state['vx']
        self.now += .2; self.c.tick()
        self.assertLess(self.c.state['vx'], moving); self.assertGreater(self.c.state['x'], start)

    def test_every_screen_renders_a_full_frame(self):
        font = parse_bdf((ROOT / 'definition/mlb-classic/fonts/4x6.bdf').read_text())
        self.c.set_context(datetime(2026, 10, 10, 15, 4), None)
        self.input('select'); self.assertEqual(128 * 32 * 4, len(self.c.frame(font).data))
        self.input('up'); self.input('a'); self.assertEqual('shop', self.c.screen)
        self.assertEqual(128 * 32 * 4, len(self.c.frame(font).data))
        self.input('b'); self.input('down'); self.input('a'); self.assertEqual('game', self.c.screen)
        self.assertEqual(128 * 32 * 4, len(self.c.frame(font).data))


class ArcadeProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'state' / 'arcade-progress.json'
        self.now = 100.0
        self.c = ArcadeController(clock=lambda: self.now, store=ArcadeProgress(self.path))

    def tearDown(self):
        self.tmp.cleanup()

    def press(self, *names):
        for name in names:
            self.c.input(name, True); self.c.input(name, False)

    def play_rider(self):
        self.press('select'); self.c.selection = KINDS.index('rider'); self.press('a')
        self.assertEqual(('game', 'rider'), (self.c.screen, self.c.state['kind']))

    def test_finished_rider_run_banks_gems_and_records_unnamed_high_score(self):
        self.play_rider()
        self.c.state = dict(self.c.state, score=42, gems=7, time=500, status='over')
        self.c.tick()
        self.assertEqual({'gems': 7, 'best': True}, self.c.result)
        self.c.tick(); self.press('b')
        saved = ArcadeProgress(self.path).data
        self.assertEqual((7, 42), (saved['gems'], saved['best']['rider']))  # committed exactly once
        self.assertNotIn('profiles', saved); self.assertNotIn('initials', json.dumps(saved))

    def test_lower_score_keeps_high_score_and_leaving_mid_run_still_banks(self):
        store = ArcadeProgress(self.path)
        store.record('snake', 9)
        self.assertEqual({'gems': 0, 'best': False}, store.record('snake', 5))
        self.assertEqual(9, store.data['best']['snake'])
        self.play_rider()
        self.c.state = dict(self.c.state, score=10, gems=3, time=200)
        self.press('select')
        self.assertEqual(3, ArcadeProgress(self.path).data['gems'])

    def test_pong_counts_household_wins(self):
        self.press('select'); self.c.selection = KINDS.index('pong'); self.press('a')
        self.c.state = dict(self.c.state, playerScore=5, time=900, status='over'); self.c.tick()
        self.assertEqual(1, ArcadeProgress(self.path).data['pongWins'])

    def test_shop_buys_once_then_equips_and_style_reaches_the_game(self):
        self.c.store.data['gems'] = 100
        self.press('select'); self.c.selection = MENU_ITEMS.index('shop'); self.press('a')
        self.assertEqual('shop', self.c.screen)
        self.press('right'); self.press('a')  # TRUCK costs 60
        self.assertEqual((40, 1), (self.c.store.data['gems'], self.c.store.style['car']))
        self.press('right'); self.press('a'); self.assertEqual('NEED MORE GEMS', self.c.notice)
        self.press('left'); self.press('left'); self.press('a'); self.press('right'); self.press('a')
        self.assertEqual(40, self.c.store.data['gems'])  # owned truck re-equipped for free
        self.press('down'); self.press('right'); self.press('a')  # RED costs 20
        self.assertEqual((20, 1), (self.c.store.data['gems'], self.c.store.style['color']))
        self.press('b'); self.c.selection = KINDS.index('rider'); self.press('a')
        self.assertEqual((1, 1, 0), (self.c.state['car'], self.c.state['color'], self.c.state['theme']))
        saved = ArcadeProgress(self.path).data
        self.assertIn('car:1', saved['owned']); self.assertEqual(20, saved['gems'])

    def test_unreadable_progress_file_is_kept_aside_not_overwritten(self):
        self.path.parent.mkdir(parents=True); self.path.write_text('{oops')
        store = ArcadeProgress(self.path)
        self.assertEqual(0, store.data['gems'])
        self.assertTrue(self.path.with_name('arcade-progress.json.unreadable').exists())

    def test_quiet_hours_close_the_arcade_and_end_a_running_game(self):
        quiet = {'enabled': True, 'start': '21:00', 'end': '07:00', 'behavior': 'sleep'}
        self.c.set_context(datetime(2026, 10, 10, 22, 0), quiet)
        self.press('select'); self.assertEqual('closed', self.c.screen); self.assertFalse(self.c.status()['available'])
        self.press('a'); self.assertFalse(self.c.active)
        self.c.set_context(datetime(2026, 10, 10, 20, 59), quiet)
        self.play_rider()
        self.c.state = dict(self.c.state, score=12, gems=4, time=300)
        self.c.set_context(datetime(2026, 10, 10, 21, 0), quiet)
        self.assertEqual('closed', self.c.screen); self.assertEqual(4, self.c.store.data['gems'])
        self.now += 5; self.c.tick(); self.assertFalse(self.c.active)

    def test_happy_hour_triples_gems_ten_minutes_every_three_hours_outside_quiet(self):
        quiet = {'enabled': True, 'start': '21:00', 'end': '07:00'}
        at = lambda h, m=0: datetime(2026, 10, 10, h, m)
        self.assertEqual({'active': True, 'seconds': 600}, happy_hour(at(15), quiet))
        self.assertEqual({'active': True, 'seconds': 60}, happy_hour(at(15, 9), quiet))
        self.assertEqual({'active': False, 'seconds': 3 * 3600 - 600}, happy_hour(at(15, 10), quiet))
        self.assertFalse(happy_hour(at(21, 5), quiet)['active'])  # 21:00 window falls in quiet hours
        # 21:00 and the overnight windows are quiet, so the next one is 09:00 tomorrow.
        self.assertEqual((datetime(2026, 10, 11, 9) - at(18, 10)).total_seconds(), happy_hour(at(18, 10), quiet)['seconds'])
        self.assertTrue(happy_hour(at(0, 5), None)['active'])  # quiet hours off: every window counts
        self.c.set_context(at(12, 2), quiet); self.play_rider()
        self.now += .02; self.c.tick()
        self.assertEqual(3, self.c.state['gemValue'])
        self.c.set_context(at(12, 11), quiet); self.now += .02; self.c.tick()
        self.assertEqual(1, self.c.state['gemValue'])


class RiderRuleTests(unittest.TestCase):
    def run_policy(self, seed, policy, steps):
        s = start_game(create_game('rider', seed))
        for _ in range(steps):
            s = step_game(s, policy(s))
            if s['status'] != 'running':
                break
        return s

    def test_ready_rider_waits_and_idle_rider_stays_parked(self):
        s = create_game('rider')
        self.assertIs(s, step_game(s, {'a'}))
        parked = self.run_policy(727, lambda s: set(), 200)
        self.assertEqual((0, 0, 'running'), (parked['vx'], parked['score'], parked['status']))

    def test_gas_on_ground_and_coasting_in_air_never_crashes(self):
        for seed in (727, 5, 123, 9001):
            with self.subTest(seed=seed):
                s = self.run_policy(seed, lambda s: set() if s['air'] else {'a'}, 3000)
                self.assertEqual('running', s['status'])
                self.assertGreater(s['score'], 400); self.assertGreater(s['gems'], 20)

    def test_flip_scores_bonus_and_over_rotation_crashes(self):
        s = start_game(create_game('rider'))
        s = dict(s, air=True, y=s['y'] - 40 * 256, vx=300, vy=-256)
        landed = s
        while landed['air']:
            landed = step_game(landed, {'a'} if landed['spin'] < 350 else set())
        self.assertEqual(('running', 10, 'FLIP!'), (landed['status'], landed['bonus'], landed['banner']))
        ground = start_game(create_game('rider'))
        upside_down = dict(ground, air=True, y=ground['y'] - 256, vy=256, angle=180, spin=180)
        crashed = step_game(upside_down, {'a'})
        self.assertEqual(('over', 'CRASH!'), (crashed['status'], crashed['message']))
        self.assertIs(crashed, step_game(crashed, {'a'}))
