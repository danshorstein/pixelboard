from __future__ import annotations

import asyncio
import re
from datetime import date as date_type
from datetime import datetime, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

MLB_API_BASE = "https://statsapi.mlb.com/api/v1"


def _dict(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _integer(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _number(value: Any) -> float | None:
    if value in (None, "", "-"):
        return 0.0 if value == "-" else None
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _local_time(value: str | None, timezone_name: str) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(ZoneInfo(timezone_name)).isoformat()
    except (ValueError, ZoneInfoNotFoundError):
        return None


def normalize_status(status: Mapping[str, Any]) -> tuple[str, str | None]:
    abstract = str(status.get("abstractGameState", "")).lower()
    detailed = str(status.get("detailedState", "")).strip()
    detail_lower = detailed.lower()
    if "postpon" in detail_lower:
        return "postponed", detailed or "Postponed"
    if "suspend" in detail_lower:
        return "suspended", detailed or "Suspended"
    if "cancel" in detail_lower:
        return "canceled", detailed or "Canceled"
    if "delay" in detail_lower:
        return "delayed", detailed or "Delayed"
    if abstract == "live" or status.get("codedGameState") in {"I", "M"}:
        return "in_progress", detailed or None
    if abstract == "final" or status.get("codedGameState") in {"F", "O"}:
        return "final", detailed or None
    if abstract == "preview" or status.get("codedGameState") in {"P", "S"}:
        return "pregame", detailed or None
    return "unknown", detailed or None


def _team(side: Mapping[str, Any], include_score: bool) -> dict[str, Any]:
    team = _dict(side.get("team"))
    score = _integer(side.get("score")) if include_score else None
    return {
        "id": team.get("id", "unknown"),
        "abbr": str(team.get("abbreviation") or team.get("fileCode") or "TBD").upper(),
        "name": str(team.get("teamName") or team.get("name") or "Team"),
        "score": score,
    }


def normalize_schedule(
    payload: Mapping[str, Any],
    *,
    mode: str,
    timezone_name: str,
    fetched_utc: str | None = None,
) -> list[dict[str, Any]]:
    fetched = fetched_utc or _utc_now()
    games: list[dict[str, Any]] = []
    for day in _list(payload.get("dates")):
        for raw in _list(_dict(day).get("games")):
            game = _dict(raw)
            status, status_detail = normalize_status(_dict(game.get("status")))
            teams = _dict(game.get("teams"))
            home_side, away_side = _dict(teams.get("home")), _dict(teams.get("away"))
            home = _team(home_side, status != "pregame")
            away = _team(away_side, status != "pregame")
            linescore = _dict(game.get("linescore"))
            active_detail = status in {"in_progress", "delayed", "suspended"}
            inning_half_raw = str(linescore.get("inningHalf") or linescore.get("inningState") or "").lower()
            inning_half = {
                "top": "top",
                "bottom": "bottom",
                "middle": "middle",
                "end": "end",
            }.get(inning_half_raw)
            offense = _dict(linescore.get("offense"))
            count = None
            balls, strikes = _integer(linescore.get("balls")), _integer(linescore.get("strikes"))
            if active_detail and balls is not None and strikes is not None:
                count = {"balls": balls, "strikes": strikes}
            bases = None
            if active_detail:
                bases = {
                    "first": bool(offense.get("first")),
                    "second": bool(offense.get("second")),
                    "third": bool(offense.get("third")),
                }
            start_utc = game.get("gameDate") if isinstance(game.get("gameDate"), str) else None
            double_header = str(game.get("doubleHeader", "N")) not in {"N", "n", ""}
            game_number = _integer(game.get("gameNumber")) or 1
            probables = {
                "home": _dict(home_side.get("probablePitcher")).get("fullName"),
                "away": _dict(away_side.get("probablePitcher")).get("fullName"),
            }
            games.append(
                {
                    "schemaVersion": "1.0",
                    "gameId": f"mlb-{game.get('gamePk', 'unknown')}",
                    "gameNumber": game_number,
                    "doubleheader": double_header,
                    "home": home,
                    "away": away,
                    "status": status,
                    "statusDetail": status_detail,
                    "inning": _integer(linescore.get("currentInning")) if active_detail else None,
                    "inningHalf": inning_half if active_detail else None,
                    "outs": _integer(linescore.get("outs")) if active_detail else None,
                    "count": count,
                    "bases": bases,
                    "startTimeUtc": start_utc,
                    "startTimeLocal": _local_time(start_utc, timezone_name),
                    "probables": probables,
                    "venue": _dict(game.get("venue")).get("name"),
                    "source": {
                        "provider": "mlb-statsapi",
                        "fetchedUtc": fetched,
                        "mode": mode,
                        "freshness": "fresh",
                    },
                }
            )
    return games


def enrich_live_game(game: dict[str, Any], payload: Mapping[str, Any]) -> None:
    """Attach current matchup and confirmed recent play to the existing ticker."""
    if str(payload.get("gamePk")) != game["gameId"].removeprefix("mlb-"):
        raise ValueError("MLB live feed game identity mismatch")
    live = _dict(payload.get("liveData"))
    plays = _dict(live.get("plays"))
    current = _dict(plays.get("currentPlay"))
    matchup = _dict(current.get("matchup"))
    linescore = _dict(live.get("linescore"))
    players = _dict(_dict(payload.get("gameData")).get("players"))
    for field, side, role in (("currentBatter", "offense", "batter"),
                              ("currentPitcher", "defense", "pitcher")):
        person = _dict(_dict(linescore.get(side)).get(role))
        # Linescore identifies the next batter even when currentPlay still
        # describes the plate appearance that just ended.
        if not person and not _dict(current.get("about")).get("isComplete"):
            person = _dict(matchup.get(role))
        person_id = person.get("id")
        name = person.get("fullName") or _dict(players.get(f"ID{person_id}")).get("fullName")
        if person_id is not None and name:
            game[field] = {"id": person_id, "name": str(name)[:100]}
    completed = [p for p in _list(plays.get("allPlays"))
                 if _dict(_dict(p).get("about")).get("isComplete")]
    if not completed:
        return
    last = _dict(completed[-1])
    result = _dict(last.get("result"))
    event, event_type = result.get("event"), result.get("eventType")
    if not event or not event_type:
        return
    parts = []
    for field, label in (("currentBatter", "BAT"), ("currentPitcher", "PITCH")):
        name = _dict(game.get(field)).get("name")
        if name:
            parts.append(f"{label} {str(name).split()[-1]}")
    hitter = _dict(_dict(last.get("matchup")).get("batter")).get("fullName", "")
    parts.append(f"LAST {str(hitter).split()[-1] if hitter else ''} {event}".strip())
    game["lastPlay"] = {
        "playId": f"{game['gameId']}:{_dict(last.get('about')).get('atBatIndex', 0)}",
        "event": str(event)[:100], "eventType": str(event_type)[:100],
        "displayText": "  |  ".join(parts)[:100],
        "rbi": _integer(result.get("rbi")),
        "scoringPlay": bool(_dict(last.get("about")).get("isScoringPlay")),
    }


def _division_name(raw: str) -> str:
    return raw.replace("National League", "NL").replace("American League", "AL")


def normalize_standings(
    payload: Mapping[str, Any],
    *,
    requested_date: str,
    mode: str,
    fetched_utc: str | None = None,
) -> list[dict[str, Any]]:
    fetched = fetched_utc or _utc_now()
    snapshots: list[dict[str, Any]] = []
    for raw_record in _list(payload.get("records")):
        record = _dict(raw_record)
        raw_rows = [_dict(value) for value in _list(record.get("teamRecords"))]
        if not raw_rows:
            continue
        first_team = _dict(raw_rows[0].get("team"))
        division = _dict(first_team.get("division")) or _dict(record.get("division"))
        league = _dict(first_team.get("league")) or _dict(record.get("league"))
        division_name = _division_name(str(division.get("name") or f"Division {division.get('id', '')}"))
        league_code = "AL" if _integer(league.get("id")) == 103 else "NL"
        rows: list[dict[str, Any]] = []
        for index, raw_row in enumerate(raw_rows, start=1):
            team = _dict(raw_row.get("team"))
            rows.append(
                {
                    "rank": _integer(raw_row.get("divisionRank")) or index,
                    "team": {
                        "id": team.get("id", "unknown"),
                        "abbr": str(team.get("abbreviation") or team.get("fileCode") or "TBD").upper(),
                        "name": str(team.get("teamName") or team.get("name") or "Team"),
                    },
                    "wins": _integer(raw_row.get("wins")) or 0,
                    "losses": _integer(raw_row.get("losses")) or 0,
                    "gamesBack": _number(raw_row.get("gamesBack")),
                }
            )
        rows.sort(key=lambda value: (value["rank"], value["team"]["abbr"]))
        slug = re.sub(r"[^a-z0-9]+", "-", division_name.lower()).strip("-")
        snapshots.append(
            {
                "schemaVersion": "1.0",
                "standingsId": f"mlb-{requested_date}-{slug}",
                "date": requested_date,
                "league": league_code,
                "division": {"id": division.get("id", "unknown"), "name": division_name},
                "teams": rows,
                "source": {
                    "provider": "mlb-statsapi",
                    "fetchedUtc": fetched,
                    "mode": mode,
                    "freshness": "fresh",
                },
            }
        )
    return snapshots


class MlbStatsApiAdapter:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timezone_name: str = "America/New_York",
    ) -> None:
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(
            base_url=MLB_API_BASE,
            timeout=httpx.Timeout(10.0),
            headers={"User-Agent": "PixelboardScoreboard/0.2 (personal low-volume display)"},
        )
        self.timezone_name = timezone_name

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def _get(self, path: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = await self.client.get(path, params=params)
                response.raise_for_status()
                value = response.json()
                if not isinstance(value, Mapping) or value.get("message") == "Internal error occurred":
                    raise ValueError("MLB Stats API returned an invalid payload")
                return value
            except (httpx.HTTPError, ValueError) as error:
                last_error = error
                if attempt == 0:
                    await asyncio.sleep(0.25)
        raise RuntimeError(f"MLB Stats API request failed: {last_error}") from last_error

    async def get_game_states(self, requested_date: str, *, mode: str = "live") -> list[dict[str, Any]]:
        payload = await self._get(
            "/schedule",
            {
                "sportId": 1,
                "date": requested_date,
                "hydrate": "team,linescore,probablePitcher,venue",
            },
        )
        games = normalize_schedule(payload, mode=mode, timezone_name=self.timezone_name)
        semaphore = asyncio.Semaphore(4)

        async def enrich(game: dict[str, Any]) -> None:
            if game["status"] != "in_progress":
                return
            try:
                async with semaphore:
                    feed = await self._get(
                        f"https://statsapi.mlb.com/api/v1.1/game/{game['gameId'].removeprefix('mlb-')}/feed/live",
                        {},
                    )
                enrich_live_game(game, feed)
            except (RuntimeError, ValueError):
                # Scores remain usable if optional player/play detail is offline.
                # Fresh schedule objects prevent old matchup data from lingering.
                return

        await asyncio.gather(*(enrich(game) for game in games))
        return games

    async def get_final_games(self, requested_date: str) -> list[dict[str, Any]]:
        """Finals on the provider's official game date, including doubleheaders."""
        payload = await self._get('/schedule', {
            'sportId': 1, 'date': requested_date, 'hydrate': 'team,linescore,venue'})
        if not isinstance(payload.get('dates'), list):
            raise ValueError('MLB response is missing the dated game list')
        filtered = {'dates': [{'games': [g for g in _list(_dict(day).get('games'))
                     if _dict(g).get('officialDate', _dict(day).get('date')) == requested_date]}
                     for day in payload['dates']]}
        return [g for g in normalize_schedule(filtered, mode='live', timezone_name=self.timezone_name)
                if g['status'] == 'final']

    async def get_recap_window(
        self,
        *,
        start_date: str,
        end_date: str,
        mode: str = "live",
    ) -> list[dict[str, Any]]:
        """A date-range schedule fetch used for the morning recap's recent-
        result/next-game lookups. Deliberately independent of
        get_game_states's single-baseball-day cache — this covers a rolling
        multi-day window (recent past through a bounded future search) and
        is cached/refreshed on its own schedule by the caller."""
        payload = await self._get(
            "/schedule",
            {
                "sportId": 1,
                "startDate": start_date,
                "endDate": end_date,
                "hydrate": "team,linescore,probablePitcher,venue",
            },
        )
        return normalize_schedule(
            payload,
            mode=mode,
            timezone_name=self.timezone_name,
        )

    async def get_standings(self, requested_date: str, *, mode: str = "live") -> list[dict[str, Any]]:
        year = date_type.fromisoformat(requested_date).year
        params = {
            "leagueId": "103,104",
            "standingsTypes": "regularSeason",
            "season": year,
            "date": requested_date,
            "hydrate": "team",
        }
        try:
            payload = await self._get("/standings", params)
        except RuntimeError:
            # The service intermittently rejects date-qualified current-season
            # standings. Season-only is its stable equivalent for live mode.
            payload = await self._get("/standings", {key: value for key, value in params.items() if key != "date"})
        return normalize_standings(
            payload,
            requested_date=requested_date,
            mode=mode,
        )
