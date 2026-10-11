from __future__ import annotations

import json
import unittest
from pathlib import Path

from shared_py.rotation import build_playlist, is_quiet_time

ROOT = Path(__file__).resolve().parents[1]


def load(name: str):
    return json.loads((ROOT / "fixtures" / name).read_text())


class RotationParityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.games = load("demo-day.json")
        self.standings = load("demo-standings.json")
        project = load("project.json")
        self.rules = {
            **project["rotation"],
            "favorites": project["favorites"],
            "quietHours": project["quietHours"],
        }
        self.clock = {"nowUtc": "2026-07-15T21:00:00Z", "localTime": "17:00"}

    def test_matches_original_shared_game_contract(self) -> None:
        actual = [
            {
                "gameId": item["gameId"],
                "scene": item["scene"],
                "dwellSec": item["dwellSec"],
            }
            for item in build_playlist(self.games, self.rules, self.clock)
        ]
        self.assertEqual(load("expected-playlist.json"), actual)

    def test_matches_mixed_game_and_standings_contract(self) -> None:
        actual = build_playlist(
            self.games,
            self.rules,
            self.clock,
            standings=self.standings,
            content_mode="mixed",
        )
        self.assertEqual(load("expected-mixed-playlist.json"), actual)

    def test_quiet_hours_cross_midnight(self) -> None:
        quiet = {"enabled": True, "start": "20:30", "end": "07:00", "behavior": "sleep"}
        self.assertTrue(is_quiet_time(quiet, {**self.clock, "localTime": "23:30"}))
        self.assertTrue(is_quiet_time(quiet, {**self.clock, "localTime": "06:59"}))
        self.assertFalse(is_quiet_time(quiet, {**self.clock, "localTime": "12:00"}))

    def test_dim_quiet_hours_keep_rotating_standings(self) -> None:
        rules = {
            **self.rules,
            "quietHours": {
                "enabled": True,
                "start": "21:30",
                "end": "07:00",
                "behavior": "dim",
            },
        }
        result = build_playlist(
            [],
            rules,
            {**self.clock, "localTime": "22:04"},
            standings=self.standings,
            content_mode="standings",
        )
        self.assertEqual(["standings"] * 5, [item["kind"] for item in result])

    def test_short_schedule_still_gets_one_full_standings_block(self) -> None:
        result = build_playlist(
            self.games[:1],
            self.rules,
            self.clock,
            standings=self.standings,
            content_mode="mixed",
        )
        self.assertEqual(["game"] + ["standings"] * 5, [item["kind"] for item in result])

    def test_empty_schedule_still_rotates_standings(self) -> None:
        for content_mode in ("standings", "mixed"):
            with self.subTest(content_mode=content_mode):
                result = build_playlist(
                    [],
                    self.rules,
                    self.clock,
                    standings=self.standings,
                    content_mode=content_mode,
                )
                self.assertEqual(["standings"] * 5, [item["kind"] for item in result])

    def test_does_not_mutate_inputs(self) -> None:
        before = json.dumps([self.games, self.standings, self.rules], sort_keys=True)
        build_playlist(
            self.games,
            self.rules,
            self.clock,
            standings=self.standings,
            content_mode="mixed",
        )
        self.assertEqual(before, json.dumps([self.games, self.standings, self.rules], sort_keys=True))


if __name__ == "__main__":
    unittest.main()
