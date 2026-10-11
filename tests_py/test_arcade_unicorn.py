from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from shared_py.arcade import create_game, press_game, start_game, step_game
from shared_py.arcade_unicorn import (AIR, CURSE_MS, DANCE_LIMIT_MS, FP, GROUND_Y, ROBOT_MS, SEG, UX, unicorn_object)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'targets/linux-sbc-hub75/runtime'))
from scoreboard_device.arcade import MENU_ITEMS, ArcadeController
from scoreboard_device.arcade_progress import ArcadeProgress


def steps(s, n):
    for _ in range(n):
        s = step_game(s)
    return s


def playing(seed=7, **patch):
    s = press_game(start_game(create_game('unicorn', seed)), 'a')
    s.update(patch)
    return s


def place(s, kind, dx=0, y=None):
    """Find a segment ahead holding `kind`, and move the camera so it sits on the unicorn."""
    for i in range(4, 400):
        obj = unicorn_object(s['seed'], i, 0 if kind == 'hive' else 1)
        if obj and obj[0] == kind:
            s = dict(s, cam=(obj[1] - UX - dx) * FP, gone=[], shots=[], fx=[])
            if y is not None:
                s['y'] = y * FP
            return s, obj
    raise AssertionError(f'no {kind} in this world')


class UnicornRuleTests(unittest.TestCase):
    def test_intro_waits_for_a_and_the_clock_starts_with_play(self):
        s = start_game(create_game('unicorn'))
        self.assertEqual('intro', steps(s, 100)['phase'])
        self.assertEqual(120_000, steps(s, 100)['clock'])
        s = press_game(s, 'a')
        self.assertEqual(('play', 119_000), (s['phase'], steps(s, 50)['clock']))

    def test_toot_lifts_and_gravity_brings_the_unicorn_back(self):
        s = playing()
        self.assertEqual(GROUND_Y, steps(s, 5)['y'])
        up = steps(press_game(s, 'a'), 12)
        self.assertLess(up['y'], GROUND_Y - 5 * FP)
        self.assertGreater(up['trail'], 0)
        self.assertEqual(GROUND_Y, steps(up, 80)['y'])

    def test_world_is_seeded_and_glasses_fly_high_and_rare(self):
        self.assertEqual([unicorn_object(5, i, 1) for i in range(200)], [unicorn_object(5, i, 1) for i in range(200)])
        glasses = [unicorn_object(seed, i, 1) for seed in range(1, 40) for i in range(160)]
        glasses = [g for g in glasses if g and g[0] == 'glasses']
        self.assertTrue(glasses)
        self.assertTrue(all(g[2] <= 11 and g[1] >= 30 * SEG for g in glasses))
        self.assertLess(len(glasses) / 39, 1.5)
        self.assertEqual(100 - sum(c for _, c in AIR), 66)

    def test_star_counts_and_banks_gems(self):
        s, star = place(playing(gemValue=3), 'star', y=star_y(playing(), 'star'))
        s = step_game(s)
        self.assertEqual((1, 1, 6, 'YAY!'), (s['stars'], s['score'], s['gems'], s['bubble']))

    def test_hive_hurts_once_then_blinks_and_running_out_of_apples_loses(self):
        s, _ = place(playing(health=2), 'hive', dx=-2)
        s = step_game(s)
        self.assertEqual((1, 1500), (s['health'], s['invuln']))
        self.assertEqual('OUCH!', s['fx'][-1][0])
        again = step_game(dict(s, cam=s['cam']))
        self.assertEqual(1, again['health'])
        s, _ = place(playing(health=1), 'hive', dx=-2)
        self.assertEqual('lose', step_game(s)['phase'])

    def test_bomb_flies_and_blows_up_a_hive(self):
        s, hive = place(playing(), 'hive', dx=-30)
        thrown = press_game(s, 'b')
        self.assertEqual((2, 1), (thrown['bombs'], len(thrown['shots'])))
        for _ in range(40):
            thrown = step_game(thrown)
            if not thrown['shots']:
                break
        self.assertEqual([], thrown['shots'])
        self.assertIn(thrown['fx'][-1][0], ('SPLAT!', 'BOOM!'))
        self.assertGreater(thrown['shake'], 0)
        empty = playing(bombs=0)
        self.assertIs(empty, press_game(empty, 'b'))

    def test_horn_dash_only_with_one_or_two_bands_and_smashes_hives(self):
        no_band = playing(bands=0)
        self.assertIs(no_band, press_game(no_band, 'r'))
        three = playing(bands=3)
        self.assertIs(three, press_game(three, 'r'))
        s, _ = place(playing(bands=1, health=1), 'hive', dx=2)
        s = step_game(press_game(s, 'r'))
        self.assertEqual(('play', 1), (s['phase'], s['health']))
        self.assertEqual('POW!', s['fx'][-1][0])

    def test_fourth_band_starts_the_dance_and_a_is_needed_after_the_six_swaps(self):
        s, _ = place(playing(bands=3), 'band', y=star_y(playing(), 'band'))
        s = step_game(s)
        self.assertEqual('dance', s['phase'])
        clock = s['clock']
        early = press_game(steps(s, 50), 'a')
        self.assertEqual('dance', early['phase'])
        done = press_game(steps(s, 150), 'a')
        self.assertEqual(('play', True), (done['phase'], done['curse']))
        self.assertEqual(clock - 150 * 20, done['clock'])  # the two minutes kept running
        self.assertEqual('lose', steps(s, DANCE_LIMIT_MS // 20)['phase'])

    def test_cursed_star_takes_ten_seconds_then_counts(self):
        s, _ = place(playing(curse=True, bands=4), 'star', y=star_y(playing(), 'star'))
        s = step_game(s)
        self.assertEqual(('curse', 0), (s['phase'], s['stars']))
        s = steps(s, CURSE_MS // 20)
        self.assertEqual(('play', 1), (s['phase'], s['stars']))

    def test_glasses_become_the_crashing_3d_robot_and_lose(self):
        s, _ = place(playing(3), 'glasses', y=9)
        s = step_game(s)
        self.assertEqual('robot', s['phase'])
        self.assertIs(s, press_game(s, 'a'))  # the seven seconds always play
        s = steps(s, ROBOT_MS // 20)
        self.assertEqual(('over', 'YOU LOSE!'), (s['status'], s['message']))

    def test_time_up_wins_with_five_stars_and_ten_is_the_great_prize(self):
        s = steps(playing(clock=20, stars=5, gemValue=1), 1)
        self.assertEqual(('win', 10), (s['phase'], s['gems']))
        self.assertEqual('YOU WIN! 5 STARS', steps(s, 160)['message'])
        s = steps(playing(clock=20, stars=4), 1)
        self.assertEqual('lose', s['phase'])
        self.assertEqual('YOU LOSE!', press_game(steps(s, 40), 'a')['message'])
        s = steps(playing(phase='curse', curse=True, stars=9, gemValue=1), CURSE_MS // 20)
        self.assertEqual(('grand', 10, 52), (s['phase'], s['stars'], s['gems']))
        self.assertEqual('GRAND PRIZE! 10 STARS', steps(s, 260)['message'])


def star_y(s, kind):
    for i in range(4, 400):
        obj = unicorn_object(s['seed'], i, 1)
        if obj and obj[0] == kind:
            return obj[2] - 2
    raise AssertionError(kind)


class UnicornControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 100.0
        self.c = ArcadeController(clock=lambda: self.now, store=ArcadeProgress(Path(self.tmp.name) / 'p.json'))

    def tearDown(self):
        self.tmp.cleanup()

    def press(self, *names):
        for name in names:
            self.c.input(name, True)
            self.c.input(name, False)

    def test_menu_buttons_and_banked_stars(self):
        self.press('select')
        self.c.selection = MENU_ITEMS.index('unicorn')
        self.assertEqual(('< RAINBOW UNICORN >', 'MOST STARS 0'), (self.c._menu_lines()[1][0], self.c._menu_lines()[2][0]))
        self.press('a', 'a')
        self.assertEqual(('unicorn', 'play'), (self.c.state['kind'], self.c.state['phase']))
        self.press('b')  # bomb, not back to the menu
        self.assertEqual(('game', 2), (self.c.screen, self.c.state['bombs']))
        self.press('a')
        self.assertLess(self.c.state['vy'], 0)
        self.c.state = dict(self.c.state, stars=7, score=7, gems=14, time=5000, status='over', message='YOU WIN! 7 STARS')
        self.c.tick()
        self.assertEqual((14, 7), (self.c.store.data['gems'], self.c.store.data['best']['unicorn']))
        self.press('b')
        self.assertEqual('menu', self.c.screen)  # once the game is over B goes back as usual


if __name__ == '__main__':
    unittest.main()
