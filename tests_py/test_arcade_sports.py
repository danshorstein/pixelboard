from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from shared_py.arcade import create_game, press_game, start_game, step_game
from shared_py.arcade_bigleague import BASE, PITCHES, base_point, meter_value
from shared_py.arcade_soccer import FP, MID_Y

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'targets/linux-sbc-hub75/runtime'))
from scoreboard_device.arcade import MENU_ITEMS, ArcadeController
from scoreboard_device.arcade_progress import ArcadeProgress


def steps(s, n, held=()):
    for _ in range(n):
        s = step_game(s, set(held))
    return s


def at_bat(seed=1, **patch):
    """Running Big League game waiting for the next pitch, intro skipped."""
    s = press_game(start_game(create_game('bigleague', seed)), 'a')
    s.update(patch)
    return s


def until(s, done, limit=5000, held=()):
    for _ in range(limit):
        if done(s):
            return s
        s = step_game(s, set(held))
    raise AssertionError('condition never reached')


class BigLeagueRuleTests(unittest.TestCase):
    def test_game_opens_on_the_line_score_and_a_skips_it(self):
        s = start_game(create_game('bigleague'))
        self.assertEqual(('switch', 0, 1), (s['phase'], s['half'], s['inning']))
        self.assertEqual('wait', press_game(s, 'a')['phase'])
        self.assertEqual('wait', steps(s, 200)['phase'])

    def test_taking_pitches_counts_balls_and_strikes(self):
        for seed in range(1, 40):
            s = until(at_bat(seed), lambda s: s['phase'] == 'result')
            in_zone = abs(s['pitchCol']) <= 1 and abs(s['pitchRow']) <= 1
            self.assertEqual((0, 1) if in_zone else (1, 0), (s['balls'], s['strikes']))
            self.assertEqual('STRIKE 1' if in_zone else 'BALL 1', s['call'])

    def test_swinging_at_the_plate_puts_the_ball_in_play(self):
        s = until(at_bat(4, aimCol=0, aimRow=0), lambda s: s['phase'] == 'pitch')
        s['pitchCol'] = s['pitchRow'] = 0
        s = until(s, lambda s: s['pitchT'] >= s['pitchMs'])
        hit = press_game(s, 'a')
        self.assertEqual(('play', 'field'), (hit['phase'], hit['view']))
        self.assertEqual([[0, BASE, 0]], hit['runners'])
        self.assertGreater(hit['ball'][4], 0)

    def test_wild_swings_miss_and_count_as_strikes(self):
        s = until(at_bat(2), lambda s: s['phase'] == 'pitch')
        swung = press_game(s, 'a')  # far too early
        self.assertEqual(('pitch', 0), (swung['phase'], swung['swing']))
        s = until(swung, lambda s: s['phase'] == 'result')
        self.assertEqual((1, 'STRIKE 1'), (s['strikes'], s['call']))

    def test_ball_four_forces_runners_and_scores_with_bases_loaded(self):
        loaded = [[b * BASE] * 3 for b in (1, 2, 3)]
        for seed in range(1, 60):
            s = until(at_bat(seed, balls=3, runners=[r[:] for r in loaded]), lambda s: s['phase'] == 'pitch')
            s['pitchCol'] = 2
            s = until(s, lambda s: s['phase'] == 'result')
            self.assertEqual('WALK', s['call'])
            self.assertEqual((1, 1, [1]), (s['you'], s['score'], s['lineYou']))
            self.assertEqual(sorted(r[1] for r in s['runners']), [BASE, 2 * BASE, 3 * BASE])
            break

    def test_third_strike_with_two_outs_switches_sides_to_pitching(self):
        s = until(at_bat(3, strikes=2, outs=2), lambda s: s['phase'] == 'pitch')
        s['pitchCol'] = s['pitchRow'] = 0
        s = until(s, lambda s: s['phase'] == 'result')
        self.assertEqual('STRIKEOUT!', s['call'])
        s = until(s, lambda s: s['phase'] == 'switch')
        self.assertEqual((1, 0, [0]), (s['half'], s['outs'], s['linePi']))
        s = press_game(s, 'a')
        self.assertEqual('aim', s['phase'])

    def test_pitching_meter_choice_and_accuracy(self):
        s = at_bat(5, half=1, phase='aim', linePi=[0])
        s = press_game(press_game(press_game(s, 'r'), 'up'), 'right')
        self.assertEqual((1, 1, -1), (s['pitchType'], s['aimCol'], s['aimRow']))
        self.assertEqual(2, press_game(press_game(s, 'l'), 'l')['pitchType'])
        s = press_game(s, 'a')
        self.assertEqual('meter', s['phase'])
        self.assertEqual((0, 100, 50), (meter_value(0), meter_value(500), meter_value(250)))
        s = steps(s, 12)  # 240 ms: nearly perfect
        thrown = press_game(s, 'a')
        self.assertEqual(('pitch', 1, -1, PITCHES[1][1]), (thrown['phase'], thrown['pitchCol'], thrown['pitchRow'], thrown['pitchMs']))
        auto = steps(press_game(at_bat(5, half=1, phase='aim', linePi=[0]), 'a'), 100)
        self.assertEqual(('pitch', 0), (auto['phase'], auto['meter']))  # never pressed: worst release

    def test_caught_fly_is_an_out_and_runners_return(self):
        s = at_bat(1, phase='play', view='field', runners=[[BASE + 400, 2 * BASE, BASE], [400, BASE, 0]],
                   ball=[0, 9000, 300, 0, 0, 0], landed=False, chaser=7, target=[0, 9000], timer=1000)
        s['fielders'][7] = [0, 9000]
        s = step_game(s, set())
        self.assertTrue(s['caught'])
        self.assertEqual((1, [[BASE + 350, BASE, BASE]]), (s['outs'], s['runners']))  # already heading back
        s = until(s, lambda s: s['phase'] == 'result')
        self.assertEqual('CAUGHT!', s['call'])

    def test_throw_beats_runner_for_a_force_out(self):
        s = at_bat(1, phase='play', view='field', runners=[[BASE - 400, BASE, 0]], ball=[4073, 4073, 256, 0, 0, 0],
                   landed=True, chaser=3, holder=-1, throwTo=1, timer=1000)
        s = step_game(s, set())
        self.assertEqual((1, [], True), (s['outs'], s['runners'], s['batterOut']))

    def test_home_run_scores_everyone_and_banks_gems(self):
        s = at_bat(1, phase='play', view='field', runners=[[BASE, 2 * BASE, BASE], [0, BASE, 0]],
                   ball=[0, 330 * 64 - 50, 1500, 0, 200, 10], landed=False, chaser=7, target=[0, 0], timer=500, gemValue=3)
        s = until(s, lambda s: s['phase'] == 'result')
        self.assertEqual(('HOME RUN!', 2, 18), (s['call'], s['you'], s['gems']))
        self.assertEqual([], s['runners'])

    def test_runner_path_points(self):
        self.assertEqual((0, 0), base_point(0))
        self.assertEqual((4073, 4073), base_point(BASE))
        self.assertEqual((0, 0), base_point(4 * BASE))
        self.assertEqual((2036, 2036), base_point(BASE // 2))

    def test_walk_off_ends_the_game_and_top_of_final_inning_can_end_it(self):
        s = at_bat(1, half=1, inning=3, phase='result', view='bat', timer=0, you=2, pi=3, lineYou=[1, 1, 0], linePi=[1, 1, 1])
        s = until(s, lambda s: s['status'] == 'over')
        self.assertEqual('PI WINS 3-2', s['message'])
        s = at_bat(1, half=0, inning=3, phase='result', view='bat', outs=3, you=1, pi=2, lineYou=[1, 0, 0], linePi=[1, 1])
        s = until(s, lambda s: s['status'] == 'over')
        self.assertEqual('PI WINS 2-1', s['message'])
        s = at_bat(1, half=1, inning=3, phase='result', view='bat', outs=3, you=4, pi=2, lineYou=[1, 2, 1], linePi=[1, 1, 0])
        s = until(s, lambda s: s['status'] == 'over')
        self.assertEqual(('YOU WIN 4-2', 10), (s['message'], s['gems']))

    def test_tie_goes_to_extra_innings(self):
        s = at_bat(1, half=1, inning=3, phase='result', view='bat', outs=3, you=2, pi=2, lineYou=[1, 1, 0], linePi=[1, 1, 0])
        s = until(s, lambda s: s['phase'] == 'switch')
        self.assertEqual(('running', 4, 0, [1, 1, 0, 0]), (s['status'], s['inning'], s['half'], s['lineYou']))


class SoccerRuleTests(unittest.TestCase):
    def test_kickoff_gives_you_the_ball_and_the_clock_runs(self):
        s = start_game(create_game('soccer'))
        self.assertEqual((1, 1, 180_000), (s['owner'], s['control'], s['clock']))
        s = steps(s, 50)
        self.assertEqual(179_000, s['clock'])

    def test_dribbling_carries_the_ball_ahead_of_the_player(self):
        s = steps(start_game(create_game('soccer')), 10, ['right'])
        p = s['players'][1]
        self.assertEqual((1, p[0] + 3 * FP), (s['owner'], s['ball'][0]))
        self.assertGreater(p[0], 61 * FP)

    def test_kick_toward_goal_and_keeper_saves_a_straight_shot(self):
        s = start_game(create_game('soccer'))
        s['players'][1][:2] = [96 * FP, MID_Y]  # in range, with the PI field players left behind
        s['players'][4][0] = s['players'][5][0] = 40 * FP
        s = steps(s, 3, ['right'])
        shot = press_game(s, 'a')
        self.assertEqual(-1, shot['owner'])
        self.assertGreater(shot['ball'][2], 400)
        s = until(shot, lambda s: s['owner'] >= 0 or s['phase'] == 'goal')
        self.assertEqual((3, 'play'), (s['owner'], s['phase']))  # straight at the keeper

    def test_goal_scores_banks_gems_and_restarts_with_pi(self):
        s = start_game(create_game('soccer'))
        s.update(owner=-1, ball=[124 * FP, 22 * FP, 600, 0], gemValue=3)
        s['players'][3][1] = 10 * FP  # keeper out of position
        s = step_game(s, set())
        self.assertEqual(('goal', 1, 15, 'GOAL!'), (s['phase'], s['you'], s['gems'], s['banner']))
        s = steps(s, 80)
        self.assertEqual(('play', 4, MID_Y), (s['phase'], s['owner'], s['ball'][1]))

    def test_ball_bounces_off_end_line_outside_the_goal(self):
        s = start_game(create_game('soccer'))
        s.update(owner=-1, ball=[124 * FP, 9 * FP, 600, 0])
        s = step_game(s, set())
        self.assertEqual('play', s['phase'])
        self.assertLess(s['ball'][2], 0)

    def test_dash_tackle_sometimes_wins_the_ball_and_sometimes_stumbles(self):
        outcomes = set()
        for seed in range(1, 30):
            s = start_game(create_game('soccer', seed))
            s.update(owner=4)
            s['players'][4][:4] = [70 * FP, MID_Y, -1, 0]
            s['players'][1][:2] = [70 * FP - 4 * FP, MID_Y]
            s = step_game(press_game(s, 'a'), set())
            outcomes.add('won' if s['owner'] == 1 else 'stumbled' if s['players'][1][4] > 0 else 'other')
        self.assertEqual({'won', 'stumbled'}, outcomes)

    def test_full_time_and_golden_goal(self):
        s = start_game(create_game('soccer'))
        s.update(clock=20, you=2, pi=1, gemValue=1)
        s = step_game(s, set())
        self.assertEqual(('over', 'YOU WIN 2-1', 10), (s['status'], s['message'], s['gems']))
        tie = start_game(create_game('soccer'))
        tie.update(clock=20, you=1, pi=1)
        tie = step_game(tie, set())
        self.assertEqual(('running', True, 'GOLDEN GOAL'), (tie['status'], tie['golden'], tie['banner']))
        tie.update(clock=20)
        self.assertEqual('DRAW 1-1', step_game(tie, set())['message'])

    def test_rivals_wait_outside_the_box_while_a_keeper_holds_the_ball(self):
        s = start_game(create_game('soccer'))
        s.update(owner=3, ball=[121 * FP, MID_Y, 0, 0])
        s['players'][1][0] = 118 * FP
        s = step_game(s, set())
        self.assertLessEqual(s['players'][1][0], 111 * FP)


class SportsControllerTests(unittest.TestCase):
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

    def open(self, kind):
        self.press('select')
        self.c.selection = MENU_ITEMS.index(kind)

    def test_menu_shows_new_games_with_their_records(self):
        self.open('bigleague')
        self.assertEqual(('< BIG LEAGUE >', 'MOST RUNS 0'), (self.c._menu_lines()[1][0], self.c._menu_lines()[2][0]))
        self.c.selection = MENU_ITEMS.index('soccer')
        self.assertEqual(('< SOCCER >', 'MOST GOALS 0'), (self.c._menu_lines()[1][0], self.c._menu_lines()[2][0]))
        self.assertEqual('shop', MENU_ITEMS[-1])

    def test_big_league_buttons_reach_the_game(self):
        self.open('bigleague'); self.press('a')
        self.assertEqual(('bigleague', 'switch'), (self.c.state['kind'], self.c.state['phase']))
        self.press('a')
        self.assertEqual('wait', self.c.state['phase'])
        self.press('up', 'left')
        self.assertEqual((-1, -1), (self.c.state['aimCol'], self.c.state['aimRow']))
        self.press('start'); self.assertTrue(self.c.paused)
        self.press('up'); self.assertEqual(-1, self.c.state['aimRow'])
        self.press('start'); self.c.state.update(half=1, phase='aim')
        self.press('r'); self.assertEqual(1, self.c.state['pitchType'])
        self.press('b'); self.assertEqual('menu', self.c.screen)

    def test_soccer_moves_while_held_and_banks_goals(self):
        self.open('soccer'); self.press('a')
        self.assertEqual('soccer', self.c.state['kind'])
        x = self.c.state['players'][1][0]
        self.c.input('right', True)
        self.now += .2; self.c.tick()
        self.assertGreater(self.c.state['players'][1][0], x)
        self.c.input('right', False)
        self.c.state = dict(self.c.state, you=3, pi=1, score=3, gems=25, status='over', message='YOU WIN 3-1')
        self.c.tick()
        self.assertEqual((25, 3), (self.c.store.data['gems'], self.c.store.data['best']['soccer']))
        self.assertEqual({'gems': 25, 'best': True}, self.c.result)


if __name__ == '__main__':
    unittest.main()
