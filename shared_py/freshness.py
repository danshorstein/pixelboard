from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

Freshness = Literal["fresh", "stale", "failed"]


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def classify_freshness(
    fetched_utc: str,
    refresh_sec: int,
    now: datetime | None = None,
) -> Freshness:
    """Classify age using the shared 2x fresh / 6x failed contract."""
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        age_sec = max(0.0, (current - parse_utc(fetched_utc)).total_seconds())
    except (TypeError, ValueError):
        return "failed"
    interval = max(1, int(refresh_sec))
    if age_sec < interval * 2:
        return "fresh"
    if age_sec <= interval * 6:
        return "stale"
    return "failed"
