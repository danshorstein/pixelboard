from __future__ import annotations

import random
import unittest
from datetime import datetime, timezone

from shared_py.morning_recap import build_recap, most_recent_result, next_upcoming_game


def _game(
    *,
    status: str,
    home: str,
    away: str,
    start: str | None,
    game_number: int = 1,
) -> dict:
    return {
        "gameId": f"mlb-{home}-{away}-{start}-{game_number}",
        "gameNumber": game_number,
        "doubleheader": game_number > 1,
        "home": {"abbr": home},
        "away": {"abbr": away},
        "status": status,
        "startTimeUtc": start,
    }


class MorningRecapTests(unittest.TestCase):
    def test_overnight_result_picks_the_most_recent_final_for_the_favorite(self) -> None:
        games = [
            _game(status="final", home="WSH", away="MIA", start="2026-09-01T23:00:00Z"),
            _game(status="final", home="WSH", away="ATL", start="2026-09-02T23:00:00Z"),
            _game(status="final", home="PHI", away="NYM", start="2026-09-02T23:00:00Z"),
        ]
        result = most_recent_result(games, "WSH")
        self.assertIsNotNone(result)
        self.assertEqual(result["away"]["abbr"], "ATL")

    def test_off_day_with_no_games_returns_no_recent_result(self) -> None:
        self.assertIsNone(most_recent_result([], "WSH"))

    def test_no_upcoming_game_in_the_search_window_is_reported_honestly(self) -> None:
        now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        games = [_game(status="final", home="WSH", away="MIA", start="2026-09-01T23:00:00Z")]
        recap = build_recap(games, "WSH", now, search_days=14)
        self.assertIsNone(recap["nextGame"])
        self.assertEqual(recap["nextGameSearchDays"], 14)

    def test_doubleheader_prefers_the_later_game_as_the_recent_result(self) -> None:
        games = [
            _game(status="final", home="WSH", away="MIA", start="2026-09-02T18:00:00Z", game_number=1),
            _game(status="final", home="WSH", away="MIA", start="2026-09-02T21:00:00Z", game_number=2),
        ]
        result = most_recent_result(games, "WSH")
        self.assertEqual(result["gameNumber"], 2)

    def test_doubleheader_second_game_can_be_the_next_upcoming_game(self) -> None:
        now = datetime(2026, 9, 2, 19, 0, tzinfo=timezone.utc)
        games = [
            _game(status="final", home="WSH", away="MIA", start="2026-09-02T18:00:00Z", game_number=1),
            _game(status="pregame", home="WSH", away="MIA", start="2026-09-02T21:00:00Z", game_number=2),
        ]
        upcoming = next_upcoming_game(games, "WSH", now)
        self.assertIsNotNone(upcoming)
        self.assertEqual(upcoming["gameNumber"], 2)

    def test_unknown_start_time_is_still_a_valid_next_game(self) -> None:
        now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        games = [_game(status="pregame", home="WSH", away="ATL", start=None)]
        upcoming = next_upcoming_game(games, "WSH", now)
        self.assertIsNotNone(upcoming)
        self.assertIsNone(upcoming["startTimeUtc"])

    def test_postponed_and_suspended_games_are_excluded_from_both_lookups(self) -> None:
        now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        games = [
            _game(status="postponed", home="WSH", away="MIA", start="2026-09-04T23:00:00Z"),
            _game(status="suspended", home="WSH", away="ATL", start="2026-09-05T02:00:00Z"),
        ]
        self.assertIsNone(most_recent_result(games, "WSH"))
        self.assertIsNone(next_upcoming_game(games, "WSH", now))

    def test_a_game_already_underway_today_is_not_reported_as_the_next_game(self) -> None:
        now = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)
        games = [_game(status="in_progress", home="WSH", away="ATL", start="2026-09-05T18:00:00Z")]
        self.assertIsNone(next_upcoming_game(games, "WSH", now))

    def test_results_are_correct_regardless_of_input_order(self) -> None:
        now = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
        games = [
            _game(status="final", home="WSH", away="MIA", start="2026-09-01T23:00:00Z"),
            _game(status="final", home="WSH", away="ATL", start="2026-09-02T23:00:00Z"),
            _game(status="pregame", home="WSH", away="NYM", start="2026-09-04T23:00:00Z"),
            _game(status="pregame", home="WSH", away="NYM", start="2026-09-03T23:00:00Z"),
        ]
        expected_recent = most_recent_result(games, "WSH")
        expected_next = next_upcoming_game(games, "WSH", now)

        shuffled = list(games)
        for _ in range(5):
            random.shuffle(shuffled)
            self.assertEqual(most_recent_result(shuffled, "WSH"), expected_recent)
            self.assertEqual(next_upcoming_game(shuffled, "WSH", now), expected_next)

    def test_ignores_games_for_teams_other_than_the_favorite(self) -> None:
        now = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        games = [_game(status="final", home="PHI", away="NYM", start="2026-09-04T23:00:00Z")]
        self.assertIsNone(most_recent_result(games, "WSH"))
        self.assertIsNone(next_upcoming_game(games, "WSH", now))


if __name__ == "__main__":
    unittest.main()
