from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

UPCOMING_STATUS = "pregame"


def _is_favorite_game(game: Mapping[str, Any], favorite_abbr: str) -> bool:
    return game.get("home", {}).get("abbr") == favorite_abbr or game.get("away", {}).get("abbr") == favorite_abbr


def _parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _sort_key(game: Mapping[str, Any]) -> tuple[datetime, int]:
    # A missing start time must not silently win a comparison against a
    # known one — sort_key never returns None, so this function's result is
    # correct regardless of what order the caller's data arrives in.
    start = _parse_utc(game.get("startTimeUtc")) or datetime.min.replace(tzinfo=timezone.utc)
    return start, int(game.get("gameNumber") or 1)


def most_recent_result(
    games: Sequence[Mapping[str, Any]],
    favorite_abbr: str,
) -> dict[str, Any] | None:
    """The most recent COMPLETED game for a favorite team, regardless of the
    input order (sorted here rather than trusted from the caller). A
    doubleheader's second game is preferred over its first when both are
    final. Postponed/canceled/suspended games are not "results" and are
    excluded; a suspended game does not surface here until it resumes and
    finishes."""
    finals = [
        game for game in games
        if _is_favorite_game(game, favorite_abbr) and game.get("status") == "final"
    ]
    if not finals:
        return None
    return dict(max(finals, key=_sort_key))


def next_upcoming_game(
    games: Sequence[Mapping[str, Any]],
    favorite_abbr: str,
    now: datetime,
) -> dict[str, Any] | None:
    """The earliest not-yet-started game for a favorite team at/after `now`,
    regardless of the input order. A game with an unknown start time is
    still eligible (renders as "TIME TBA" downstream) since a missing time
    does not mean it isn't the next game — such a game sorts first among
    upcoming candidates since its time is unknown rather than known-later."""
    candidates = []
    for game in games:
        if not _is_favorite_game(game, favorite_abbr) or game.get("status") != UPCOMING_STATUS:
            continue
        start = _parse_utc(game.get("startTimeUtc"))
        if start is not None and start <= now:
            continue
        candidates.append(game)
    if not candidates:
        return None
    return dict(min(candidates, key=lambda game: _parse_utc(game.get("startTimeUtc")) or now))


def build_recap(
    games: Sequence[Mapping[str, Any]],
    favorite_abbr: str,
    now: datetime,
    *,
    search_days: int,
) -> dict[str, Any]:
    """Combines the two lookups into the recap payload a card renders from.
    `search_days` records how far forward the caller's fetch window actually
    searched, so the renderer can say "No game scheduled in the next N days"
    truthfully rather than implying an unknown future game is imminent."""
    return {
        "favorite": favorite_abbr,
        "recentResult": most_recent_result(games, favorite_abbr),
        "nextGame": next_upcoming_game(games, favorite_abbr, now),
        "nextGameSearchDays": search_days,
    }
