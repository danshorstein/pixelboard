from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from shared_py.renderer import _game_bindings, render_scene


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: str):
    with (ROOT / path).open(encoding="utf-8") as handle:
        return json.load(handle)


class RendererParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.definition = load_json("definition/mlb-classic/display-definition.json")
        cls.games = load_json("fixtures/demo-day.json")
        cls.standings = load_json("fixtures/demo-standings.json")
        cls.frame_cases = load_json("fixtures/expected-render-frames.json")
        cls.fonts = {
            name: (ROOT / f"definition/mlb-classic/fonts/{name}.bdf").read_text(encoding="utf-8")
            for name in ("4x6", "5x7", "6x10")
        }

    @staticmethod
    def logo_asset(tone=None) -> dict:
        data: list[int] = []
        for i in range(16 * 16):
            x, y = i % 16, i // 16
            rgb = (0, 0, 0) if tone == 'black' else (16, 32, 64) if tone == 'dark' else (20, 110, 255)
            alpha = (0 if x < 2 or y < 2 or x > 13 or y > 13 else 128 if x % 2 else 255) if tone else 255
            data.extend((*rgb, alpha))
        return {"width": 16, "height": 16, "data": data}

    def test_frames_are_byte_identical_to_typescript_renderer(self) -> None:
        by_game_id = {game["gameId"]: game for game in self.games}
        standings = self.standings[0]
        by_abbr = {row["team"]["abbr"]: row for row in standings["teams"]}
        for frame_case in self.frame_cases:
            with self.subTest(frame=frame_case["name"]):
                game = by_game_id.get(frame_case.get("gameId"))
                standing_team = by_abbr.get(frame_case.get("standingAbbr"))
                asset_key = None
                away_logo_asset_key = None
                home_logo_asset_key = None
                assets = {}
                if frame_case.get("logo") and standing_team:
                    asset_key = f"team-logo:{standing_team['team']['id']}:16"
                    assets[asset_key] = self.logo_asset(frame_case.get("logoTone"))
                if frame_case.get("gameLogos") and game:
                    away_logo_asset_key = f"team-logo:{game['away']['id']}:16"
                    home_logo_asset_key = f"team-logo:{game['home']['id']}:16"
                    assets[away_logo_asset_key] = self.logo_asset(frame_case.get("logoTone"))
                    assets[home_logo_asset_key] = self.logo_asset(frame_case.get("logoTone"))
                frame = render_scene(
                    self.definition,
                    frame_case["scene"],
                    self.fonts,
                    game=game,
                    standings=standings if standing_team else None,
                    standing_team=standing_team,
                    logo_asset_key=asset_key,
                    away_logo_asset_key=away_logo_asset_key,
                    home_logo_asset_key=home_logo_asset_key,
                    favorites=("WSH", "PHI"),
                    elapsed_ms=frame_case["elapsedMs"],
                    now="2026-07-15T17:05:00-04:00",
                    assets=assets,
                    transport_held=bool(frame_case.get("transportHeld")),
                    overrides={"layoutPreset": frame_case["layoutPreset"]} if frame_case.get("layoutPreset") else None,
                )
                actual = hashlib.sha256(frame.data).hexdigest()
                self.assertEqual(frame_case["sha256"], actual)


class MissingPlayerContextTests(unittest.TestCase):
    """Mirrors shared_ts/renderer.test.ts's equivalent case for TS/Python parity."""

    def test_falls_back_to_inning_status_instead_of_placeholder_player_names(self) -> None:
        game = {
            "status": "in_progress",
            "inning": 7,
            "inningHalf": "top",
            "away": {"abbr": "MIA", "score": 2},
            "home": {"abbr": "WSH", "score": 3},
            "currentPitcher": None,
            "currentBatter": None,
            "lastPitch": None,
            "lastPlay": None,
        }
        bindings = _game_bindings(game, favorites=(), favorite=None, idle_message=None)
        context = bindings["broadcastContextDisplay"]
        self.assertNotIn("PITCHER", context)
        self.assertNotIn("BATTER", context)
        self.assertIn(bindings["inningDisplay"], context)
        self.assertIn(bindings["statusLabel"], context)


if __name__ == "__main__":
    unittest.main()
