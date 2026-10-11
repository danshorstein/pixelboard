from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"


def load_recap_window(path: Path) -> dict[str, Any] | None:
    """The last successfully fetched recap schedule window, or None if the
    cache is missing, unreadable, or malformed. Fails closed (like
    load_reveal): a corrupt cache must never crash boot or be treated as
    partially valid — a fresh fetch replaces it."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    start, end = raw.get("startDate"), raw.get("endDate")
    games = raw.get("games")
    if not isinstance(start, str) or not isinstance(end, str) or not isinstance(games, list):
        return None
    return {
        "schemaVersion": str(raw.get("schemaVersion") or SCHEMA_VERSION),
        "startDate": start,
        "endDate": end,
        "fetchedUtc": raw.get("fetchedUtc") if isinstance(raw.get("fetchedUtc"), str) else None,
        "games": games,
    }


def save_recap_window(
    path: Path,
    *,
    start_date: str,
    end_date: str,
    fetched_utc: str,
    games: list[dict[str, Any]],
) -> dict[str, Any]:
    window = {
        "schemaVersion": SCHEMA_VERSION,
        "startDate": start_date,
        "endDate": end_date,
        "fetchedUtc": fetched_utc,
        "games": games,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(window), encoding="utf-8")
    return window
