from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from shared_py.recap_cache import load_recap_window, save_recap_window


class RecapCacheTests(unittest.TestCase):
    def test_round_trips_a_saved_window(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "recap-window.json"
            saved = save_recap_window(
                path,
                start_date="2026-09-01",
                end_date="2026-09-20",
                fetched_utc="2026-09-06T12:00:00Z",
                games=[{"gameId": "mlb-1"}],
            )
            self.assertEqual(load_recap_window(path), saved)

    def test_missing_file_fails_closed_to_none(self) -> None:
        self.assertIsNone(load_recap_window(Path("/nonexistent/recap-window.json")))

    def test_corrupt_json_fails_closed_to_none(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "recap-window.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertIsNone(load_recap_window(path))

    def test_structurally_wrong_payload_fails_closed_to_none(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "recap-window.json"
            path.write_text('{"startDate": "2026-09-01", "games": "not a list"}', encoding="utf-8")
            self.assertIsNone(load_recap_window(path))


if __name__ == "__main__":
    unittest.main()
