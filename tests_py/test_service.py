from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from backend.service import ScoreboardDataService, active_date


class FakeAdapter:
    def __init__(self) -> None:
        self.game_calls = 0
        self.standings_calls = 0
        self.fail = False

    async def close(self) -> None:
        return None

    async def get_game_states(self, requested_date: str, *, mode: str = "live"):
        self.game_calls += 1
        if self.fail:
            raise RuntimeError("provider offline")
        return [{
            "schemaVersion": "1.0",
            "gameId": f"mlb-{requested_date}",
            "gameNumber": 1,
            "doubleheader": False,
            "home": {"id": 120, "abbr": "WSH", "name": "Nationals", "score": 3},
            "away": {"id": 143, "abbr": "PHI", "name": "Phillies", "score": 2},
            "status": "in_progress",
            "startTimeUtc": "2026-07-16T20:00:00Z",
            "startTimeLocal": "2026-07-16T16:00:00-04:00",
            "source": {
                "provider": "fake",
                "fetchedUtc": "2026-07-16T20:00:00Z",
                "mode": mode,
                "freshness": "fresh",
            },
        }]

    async def get_standings(self, requested_date: str, *, mode: str = "live"):
        self.standings_calls += 1
        if self.fail:
            raise RuntimeError("provider offline")
        return []


class DataServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.adapter = FakeAdapter()
        self.service = ScoreboardDataService(
            adapter=self.adapter,  # type: ignore[arg-type]
            data_dir=Path(self.temporary.name),
        )

    async def asyncTearDown(self) -> None:
        await self.service.close()
        self.temporary.cleanup()

    async def test_demo_mode_never_needs_network(self) -> None:
        snapshot = await self.service.get_snapshot("2026-07-16", mode="demo")
        self.assertEqual("demo", snapshot["mode"])
        self.assertEqual(11, len(snapshot["games"]))
        self.assertEqual(0, self.adapter.game_calls)

    async def test_live_cache_is_shared(self) -> None:
        first = await self.service.get_snapshot("2026-07-14", mode="live")
        second = await self.service.get_snapshot("2026-07-14", mode="live")
        self.assertEqual("mlb-2026-07-14", first["games"][0]["gameId"])
        self.assertEqual(first, second)
        self.assertEqual(1, self.adapter.game_calls)
        self.assertEqual(1, self.adapter.standings_calls)

    async def test_provider_failure_is_explicit(self) -> None:
        self.adapter.fail = True
        snapshot = await self.service.get_snapshot("2026-07-16", mode="live", force=True)
        self.assertEqual("failed", snapshot["source"]["freshness"])
        self.assertIn("provider offline", snapshot["source"]["error"])

    async def test_current_live_schedule_retains_prior_date_active_games(self) -> None:
        with patch("backend.service.active_date", return_value="2026-07-16"):
            snapshot = await self.service.get_snapshot("2026-07-16", mode="live")
        self.assertEqual(
            {"mlb-2026-07-16", "mlb-2026-07-15"},
            {game["gameId"] for game in snapshot["games"]},
        )
        self.assertEqual(2, self.adapter.game_calls)

    def test_active_date_uses_three_am_eastern_rollover(self) -> None:
        timezone = ZoneInfo("America/New_York")
        self.assertEqual(
            "2026-07-15",
            active_date(datetime(2026, 7, 16, 2, 59, tzinfo=timezone)),
        )
        self.assertEqual(
            "2026-07-16",
            active_date(datetime(2026, 7, 16, 3, 0, tzinfo=timezone)),
        )


if __name__ == "__main__":
    unittest.main()
