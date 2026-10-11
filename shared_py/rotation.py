from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

STATUS_RANK = {
    "in_progress": 0,
    "pregame": 1,
    "final": 2,
    "delayed": 3,
    "postponed": 3,
    "suspended": 3,
    "canceled": 3,
    "unknown": 3,
}

STATUS_SCENE = {
    "in_progress": "live",
    "pregame": "pregame",
    "final": "final",
    "delayed": "statusOnly",
    "postponed": "statusOnly",
    "suspended": "statusOnly",
    "canceled": "statusOnly",
    "unknown": "statusOnly",
}


def _minutes(value: str) -> int | None:
    try:
        hour_text, minute_text = value.split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
    except (AttributeError, TypeError, ValueError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour * 60 + minute


def is_quiet_time(quiet_hours: Mapping[str, Any] | None, clock: Mapping[str, str]) -> bool:
    if not quiet_hours or not quiet_hours.get("enabled"):
        return False
    now = _minutes(clock.get("localTime", ""))
    start = _minutes(str(quiet_hours.get("start", "")))
    end = _minutes(str(quiet_hours.get("end", "")))
    if now is None or start is None or end is None or start == end:
        return False
    return start <= now < end if start < end else now >= start or now < end


def _favorite(game: Mapping[str, Any], favorites: set[str]) -> bool:
    home = game.get("home") if isinstance(game.get("home"), Mapping) else {}
    away = game.get("away") if isinstance(game.get("away"), Mapping) else {}
    return home.get("abbr") in favorites or away.get("abbr") in favorites


def _safe_dwell(value: Any) -> int:
    try:
        dwell = int(value)
    except (TypeError, ValueError, OverflowError):
        return 1
    return max(1, dwell)


def _start_key(game: Mapping[str, Any]) -> float:
    value = game.get("startTimeUtc")
    if not isinstance(value, str):
        return float("inf")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return float("inf")


def _game_item(
    game: Mapping[str, Any], rules: Mapping[str, Any], favorites: set[str]
) -> dict[str, Any]:
    favorite = _favorite(game, favorites)
    return {
        "kind": "game",
        "gameId": str(game.get("gameId", "")),
        "scene": STATUS_SCENE.get(str(game.get("status")), "statusOnly"),
        "dwellSec": _safe_dwell(
            rules.get("favoriteDwellSec") if favorite else rules.get("otherDwellSec")
        ),
        "favorite": favorite,
    }


def _idle_item(rules: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": "idle",
        "gameId": None,
        "scene": "idle",
        "dwellSec": _safe_dwell(rules.get("otherDwellSec")),
        "favorite": False,
    }


def _standing_items(
    snapshots: Iterable[Mapping[str, Any]],
    rules: Mapping[str, Any],
    favorites: set[str],
) -> list[dict[str, Any]]:
    config = rules.get("standings")
    if not isinstance(config, Mapping):
        return []
    division_filter = set(config.get("divisions") or [])
    ordered = sorted(
        snapshots,
        key=lambda value: (
            str(value.get("league", "")),
            str((value.get("division") or {}).get("name", "")),
            str(value.get("standingsId", "")),
        ),
    )
    result: list[dict[str, Any]] = []
    for snapshot in ordered:
        division = snapshot.get("division") if isinstance(snapshot.get("division"), Mapping) else {}
        if division_filter and division.get("name") not in division_filter and (snapshot.get("source") or {}).get("provider") != "local-manual":
            continue
        teams = snapshot.get("teams") if isinstance(snapshot.get("teams"), Sequence) else []
        rows = sorted(
            (row for row in teams if isinstance(row, Mapping)),
            key=lambda row: (
                int(row.get("rank", 999)),
                str((row.get("team") or {}).get("abbr", "")),
            ),
        )
        for row in rows:
            team = row.get("team") if isinstance(row.get("team"), Mapping) else {}
            favorite = team.get("abbr") in favorites
            result.append(
                {
                    "kind": "standings",
                    "standingsId": str(snapshot.get("standingsId", "")),
                    "teamId": str(team.get("id", "")),
                    "scene": "standings",
                    "dwellSec": _safe_dwell(
                        config.get("favoriteTeamDwellSec")
                        if favorite
                        else config.get("teamDwellSec")
                    ),
                    "favorite": favorite,
                }
            )
    return result


def build_playlist(
    game_states: Sequence[Mapping[str, Any]],
    rules: Mapping[str, Any],
    clock: Mapping[str, str],
    *,
    standings: Sequence[Mapping[str, Any]] = (),
    content_mode: str = "games",
) -> list[dict[str, Any]]:
    """Pure Python twin of shared_ts/rotation.ts."""
    quiet_hours = rules.get("quietHours")
    if (
        is_quiet_time(quiet_hours if isinstance(quiet_hours, Mapping) else None, clock)
        and (quiet_hours or {}).get("behavior") == "sleep"
    ):
        behavior = str((quiet_hours or {}).get("behavior", "sleep"))
        return [{"kind": "directive", "directive": behavior, "dwellSec": 0}]

    favorites = set(str(value) for value in rules.get("favorites", []))
    pinned_id = rules.get("pinnedGameId")
    if pinned_id:
        pinned = next(
            (
                game
                for game in game_states
                if game.get("gameId") == pinned_id and game.get("status") != "final"
            ),
            None,
        )
        if pinned is not None:
            return [_game_item(pinned, rules, favorites)]

    def sort_key(game: Mapping[str, Any]) -> tuple[Any, ...]:
        return (
            0 if not rules.get("favoritesFirst") else (0 if _favorite(game, favorites) else 1),
            STATUS_RANK.get(str(game.get("status")), 3) if rules.get("liveFirst") else 0,
            _start_key(game),
            int(game.get("gameNumber", 1)),
            str(game.get("gameId", "")),
        )

    games = [_game_item(game, rules, favorites) for game in sorted(game_states, key=sort_key)]
    standing_rows = _standing_items(standings, rules, favorites)
    if content_mode == "standings":
        return standing_rows or [_idle_item(rules)]
    config = rules.get("standings")
    if content_mode == "games" or not isinstance(config, Mapping) or not config.get("enabled"):
        return games or [_idle_item(rules)]

    interval = _safe_dwell(config.get("afterEveryGameScreens"))
    mixed: list[dict[str, Any]] = []
    inserted_standings = False
    for index, game in enumerate(games, start=1):
        mixed.append(game)
        if index % interval == 0:
            mixed.extend(standing_rows)
            inserted_standings = True
    if games and standing_rows and not inserted_standings:
        mixed.extend(standing_rows)
    if not mixed:
        mixed.extend(standing_rows)
    return mixed or [_idle_item(rules)]
