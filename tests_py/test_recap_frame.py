from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from shared_py.bdf import parse_bdf
from shared_py.morning_recap import build_recap
from shared_py.recap_frame import create_recap_frame, recap_lines

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 6, 8, 0, tzinfo=timezone.utc)


def _game(**overrides: object) -> dict:
    game = {
        "gameId": "mlb-1",
        "gameNumber": 1,
        "doubleheader": False,
        "home": {"abbr": "WSH", "score": 5},
        "away": {"abbr": "MIA", "score": 3},
        "status": "final",
        "startTimeUtc": "2026-09-02T23:05:00Z",
        "startTimeLocal": "2026-09-02T19:05:00-04:00",
    }
    game.update(overrides)
    return game


class RecapLinesTests(unittest.TestCase):
    def test_win_result_names_the_opponent_and_real_date(self) -> None:
        lines = recap_lines(
            {"favorite": "WSH", "recentResult": _game(), "nextGame": None, "nextGameSearchDays": 14},
            NOW,
        )
        self.assertEqual(lines[0], "WSH RECAP")
        self.assertEqual(lines[1], "BEAT MIA 5-3 (VS)")
        self.assertEqual(lines[2], "WED SEP 2")

    def test_loss_when_favorite_is_the_away_team(self) -> None:
        game = _game(home={"abbr": "ATL", "score": 7}, away={"abbr": "WSH", "score": 2})
        lines = recap_lines(
            {"favorite": "WSH", "recentResult": game, "nextGame": None, "nextGameSearchDays": 14},
            NOW,
        )
        self.assertEqual(lines[1], "LOST TO ATL 2-7 (AT)")

    def test_no_recent_result_is_stated_plainly(self) -> None:
        lines = recap_lines(
            {"favorite": "PHI", "recentResult": None, "nextGame": None, "nextGameSearchDays": 14},
            NOW,
        )
        self.assertIn("NO RECENT RESULT", lines)

    def test_next_game_shows_weekday_date_and_local_time(self) -> None:
        upcoming = _game(
            status="pregame",
            home={"abbr": "WSH"},
            away={"abbr": "NYM"},
            startTimeUtc="2026-09-07T23:05:00Z",
            startTimeLocal="2026-09-07T19:05:00-04:00",
        )
        lines = recap_lines(
            {"favorite": "WSH", "recentResult": None, "nextGame": upcoming, "nextGameSearchDays": 14},
            NOW,
        )
        self.assertEqual(lines[-2], "NEXT MON SEP 7")
        self.assertEqual(lines[-1], "VS NYM  7:05 PM")

    def test_unknown_start_time_falls_back_to_time_tba_not_invented_copy(self) -> None:
        upcoming = _game(status="pregame", startTimeUtc=None, startTimeLocal=None)
        lines = recap_lines(
            {"favorite": "WSH", "recentResult": None, "nextGame": upcoming, "nextGameSearchDays": 14},
            NOW,
        )
        self.assertEqual(lines[-2], "NEXT DATE TBA")
        self.assertIn("TIME TBA", lines[-1])

    def test_no_upcoming_game_reports_the_actual_window_checked(self) -> None:
        lines = recap_lines(
            {"favorite": "WSH", "recentResult": _game(), "nextGame": None, "nextGameSearchDays": 9},
            NOW,
        )
        self.assertIn("NO GAME IN NEXT 9 DAYS", lines)

    def test_doubleheader_game_two_is_tagged(self) -> None:
        game = _game(doubleheader=True, gameNumber=2)
        lines = recap_lines(
            {"favorite": "WSH", "recentResult": game, "nextGame": None, "nextGameSearchDays": 14},
            NOW,
        )
        self.assertTrue(lines[1].endswith("G2"))

    def test_lines_are_built_from_build_recap_output_directly(self) -> None:
        games = [
            _game(startTimeUtc="2026-09-05T23:00:00Z", startTimeLocal="2026-09-05T19:00:00-04:00"),
            _game(
                gameId="mlb-2",
                status="pregame",
                home={"abbr": "WSH"},
                away={"abbr": "ATL"},
                startTimeUtc="2026-09-08T23:00:00Z",
                startTimeLocal="2026-09-08T19:00:00-04:00",
            ),
        ]
        recap = build_recap(games, "WSH", NOW, search_days=14)
        lines = recap_lines(recap, NOW)
        self.assertEqual(lines[0], "WSH RECAP")
        self.assertTrue(any("ATL" in line for line in lines))


class RecapFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.font = parse_bdf((ROOT / "definition/mlb-classic/fonts/4x6.bdf").read_text(encoding="utf-8"))

    def test_renders_a_full_size_panel_frame(self) -> None:
        recap = {"favorite": "WSH", "recentResult": _game(), "nextGame": None, "nextGameSearchDays": 14}
        frame = create_recap_frame(128, 32, recap, self.font, NOW)
        self.assertEqual((frame.width, frame.height), (128, 32))
        self.assertEqual(len(frame.data), 128 * 32 * 4)

    def test_never_lights_a_pixel_past_the_panel_edge(self) -> None:
        recap = {
            "favorite": "WSH",
            "recentResult": _game(away={"abbr": "MIA", "score": 12}, home={"abbr": "WSH", "score": 11}),
            "nextGame": None,
            "nextGameSearchDays": 14,
        }
        frame = create_recap_frame(128, 32, recap, self.font, NOW)
        lit_columns = {
            (index // 4) % 128
            for index in range(0, len(frame.data), 4)
            if frame.data[index:index + 3] != bytes((0, 0, 0))
        }
        self.assertTrue(lit_columns)
        self.assertLess(max(lit_columns), 128)


if __name__ == "__main__":
    unittest.main()
