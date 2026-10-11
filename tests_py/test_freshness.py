from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from shared_py.freshness import classify_freshness


class FreshnessTests(unittest.TestCase):
    def test_shared_thresholds(self) -> None:
        now = datetime(2026, 7, 16, 20, 0, tzinfo=timezone.utc)
        self.assertEqual(
            "fresh",
            classify_freshness((now - timedelta(seconds=19)).isoformat(), 10, now),
        )
        self.assertEqual(
            "stale",
            classify_freshness((now - timedelta(seconds=20)).isoformat(), 10, now),
        )
        self.assertEqual(
            "failed",
            classify_freshness((now - timedelta(seconds=61)).isoformat(), 10, now),
        )

    def test_invalid_timestamp_fails_closed(self) -> None:
        self.assertEqual("failed", classify_freshness("not-a-time", 10))


if __name__ == "__main__":
    unittest.main()
