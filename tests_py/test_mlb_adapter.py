from __future__ import annotations

import unittest

from shared_py.mlb_adapter import enrich_live_game

from shared_py.mlb_adapter import normalize_schedule, normalize_standings, normalize_status


class MlbAdapterNormalizationTests(unittest.TestCase):
    def test_status_detail_preserves_rain_delay(self) -> None:
        self.assertEqual(
            ("delayed", "Rain Delay"),
            normalize_status({"abstractGameState": "Live", "detailedState": "Rain Delay"}),
        )

    def test_normalizes_live_game_without_provider_objects_leaking(self) -> None:
        payload = {
            "dates": [{
                "games": [{
                    "gamePk": 777,
                    "gameDate": "2026-07-16T23:10:00Z",
                    "gameNumber": 2,
                    "doubleHeader": "Y",
                    "status": {"abstractGameState": "Live", "detailedState": "In Progress"},
                    "teams": {
                        "away": {"team": {"id": 121, "abbreviation": "NYM", "teamName": "Mets"}, "score": 2},
                        "home": {"team": {"id": 143, "abbreviation": "PHI", "teamName": "Phillies"}, "score": 4},
                    },
                    "linescore": {
                        "currentInning": 7,
                        "inningHalf": "Top",
                        "outs": 2,
                        "balls": 3,
                        "strikes": 1,
                        "offense": {"first": {"id": 1}, "third": {"id": 2}},
                    },
                    "venue": {"name": "Citizens Bank Park"},
                }]
            }]
        }
        games = normalize_schedule(
            payload,
            mode="live",
            timezone_name="America/New_York",
            fetched_utc="2026-07-16T23:11:00Z",
        )
        self.assertEqual(1, len(games))
        self.assertEqual("mlb-777", games[0]["gameId"])
        self.assertEqual({"balls": 3, "strikes": 1}, games[0]["count"])
        self.assertEqual(
            {"first": True, "second": False, "third": True},
            games[0]["bases"],
        )
        self.assertTrue(games[0]["doubleheader"])
        self.assertEqual("2026-07-16T19:10:00-04:00", games[0]["startTimeLocal"])

    def test_live_ticker_uses_next_batter_and_only_completed_hits(self) -> None:
        game = {"gameId": "mlb-777"}
        feed = {"gamePk": 777, "gameData": {"players": {
            "ID10": {"fullName": "New Batter"}, "ID20": {"fullName": "Live Pitcher"}}},
            "liveData": {"linescore": {"offense": {"batter": {"id": 10}},
                "defense": {"pitcher": {"id": 20}}}, "plays": {
                "currentPlay": {"about": {"isComplete": True},
                    "matchup": {"batter": {"id": 9, "fullName": "Old Hitter"}}},
                "allPlays": [
                    {"about": {"isComplete": True, "atBatIndex": 4},
                     "matchup": {"batter": {"fullName": "Old Hitter"}},
                     "result": {"event": "Double", "eventType": "double", "rbi": 1}},
                    {"about": {"isComplete": False},
                     "result": {"event": "Home Run", "eventType": "home_run"}}]}}}
        enrich_live_game(game, feed)
        self.assertEqual("New Batter", game["currentBatter"]["name"])
        self.assertEqual("Live Pitcher", game["currentPitcher"]["name"])
        self.assertEqual("double", game["lastPlay"]["eventType"])
        self.assertEqual("BAT Batter  |  PITCH Pitcher  |  LAST Hitter Double",
                         game["lastPlay"]["displayText"])

    def test_missing_live_detail_and_wrong_game(self) -> None:
        game = {"gameId": "mlb-777"}
        enrich_live_game(game, {"gamePk": 777})
        self.assertEqual({"gameId": "mlb-777"}, game)
        with self.assertRaises(ValueError):
            enrich_live_game(game, {"gamePk": 778})

    def test_normalizes_division_standings_and_leader_games_back(self) -> None:
        payload = {
            "records": [{
                "league": {"id": 104},
                "division": {"id": 204},
                "teamRecords": [{
                    "team": {
                        "id": 143,
                        "abbreviation": "PHI",
                        "teamName": "Phillies",
                        "league": {"id": 104},
                        "division": {"id": 204, "name": "National League East"},
                    },
                    "wins": 54,
                    "losses": 43,
                    "divisionRank": "1",
                    "gamesBack": "-",
                }],
            }]
        }
        result = normalize_standings(
            payload,
            requested_date="2026-07-16",
            mode="live",
            fetched_utc="2026-07-16T20:00:00Z",
        )
        self.assertEqual("NL East", result[0]["division"]["name"])
        self.assertEqual(0.0, result[0]["teams"][0]["gamesBack"])


if __name__ == "__main__":
    unittest.main()
