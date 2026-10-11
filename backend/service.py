from __future__ import annotations

import asyncio
import json
import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Literal
from zoneinfo import ZoneInfo

from shared_py.freshness import classify_freshness
from shared_py.mlb_adapter import MlbStatsApiAdapter

Mode = Literal["live", "demo", "replay"]
ROOT = Path(__file__).resolve().parents[1]
ACTIVE_GAME_STATUSES = {"in_progress", "delayed", "suspended"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def active_date(
    now: datetime | None = None,
    *,
    timezone_name: str = "America/New_York",
    rollover_local_time: str = "03:00",
) -> str:
    local = now.astimezone(ZoneInfo(timezone_name)) if now else datetime.now(ZoneInfo(timezone_name))
    hour, minute = (int(value) for value in rollover_local_time.split(":"))
    rollover = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    value = local.date() if local >= rollover else (local - timedelta(days=1)).date()
    return value.isoformat()


def refresh_interval(games: list[dict[str, Any]]) -> int:
    statuses = {game.get("status") for game in games}
    if statuses & {"in_progress", "delayed", "suspended"}:
        return 10
    if "pregame" in statuses:
        return 60
    return 300


def _records_with_freshness(records: list[dict[str, Any]], freshness: str) -> list[dict[str, Any]]:
    result = deepcopy(records)
    for record in result:
        source = record.get("source")
        if isinstance(source, dict):
            source["freshness"] = freshness
    return result


@dataclass
class CacheEntry:
    value: list[dict[str, Any]]
    fetched_utc: str
    fetched_monotonic: float
    refresh_sec: int
    error: str | None = None

    def due(self) -> bool:
        return monotonic() - self.fetched_monotonic >= self.refresh_sec


class ScoreboardDataService:
    """One courteous polling stream shared by every browser and websocket."""

    def __init__(
        self,
        *,
        adapter: MlbStatsApiAdapter | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self.adapter = adapter or MlbStatsApiAdapter()
        self.data_dir = data_dir or Path(os.environ.get("SCOREBOARD_DATA_DIR", ROOT / "data"))
        self.replay_dir = self.data_dir / "replay"
        self.replay_dir.mkdir(parents=True, exist_ok=True)
        self._games: dict[str, CacheEntry] = {}
        self._standings: dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        await self.adapter.close()

    def _demo_snapshot(self) -> dict[str, Any]:
        games = json.loads((ROOT / "fixtures" / "demo-day.json").read_text())
        standings = json.loads((ROOT / "fixtures" / "demo-standings.json").read_text())
        fetched = games[0]["source"]["fetchedUtc"] if games else _utc_now()
        return {
            "schemaVersion": "1.0",
            "date": "2026-07-15",
            "mode": "demo",
            "games": games,
            "standings": standings,
            "source": {
                "provider": "bundled-fixtures",
                "fetchedUtc": fetched,
                "freshness": "fresh",
                "refreshSec": 0,
                "error": None,
            },
        }

    async def _refresh_games(self, requested_date: str, mode: Mode) -> CacheEntry:
        existing = self._games.get(requested_date)
        try:
            value = await self.adapter.get_game_states(requested_date, mode=mode)
            fetched = value[0]["source"]["fetchedUtc"] if value else _utc_now()
            entry = CacheEntry(value, fetched, monotonic(), refresh_interval(value))
            self._games[requested_date] = entry
            return entry
        except Exception as error:
            if existing is None:
                entry = CacheEntry([], _utc_now(), monotonic(), 10, str(error))
                self._games[requested_date] = entry
                return entry
            existing.error = str(error)
            return existing

    async def _refresh_standings(self, requested_date: str, mode: Mode) -> CacheEntry:
        existing = self._standings.get(requested_date)
        try:
            value = await self.adapter.get_standings(requested_date, mode=mode)
            fetched = value[0]["source"]["fetchedUtc"] if value else _utc_now()
            entry = CacheEntry(value, fetched, monotonic(), 300)
            self._standings[requested_date] = entry
            return entry
        except Exception as error:
            if existing is None:
                entry = CacheEntry([], _utc_now(), monotonic(), 300, str(error))
                self._standings[requested_date] = entry
                return entry
            existing.error = str(error)
            return existing

    async def _live_snapshot(self, requested_date: str, mode: Mode, force: bool) -> dict[str, Any]:
        async with self._lock:
            game_entry = self._games.get(requested_date)
            standings_entry = self._standings.get(requested_date)
            include_previous = mode == "live" and requested_date == active_date()
            previous_date = (date_type.fromisoformat(requested_date) - timedelta(days=1)).isoformat()
            previous_entry = self._games.get(previous_date) if include_previous else None
            tasks: list[asyncio.Task[CacheEntry]] = []
            task_names: list[str] = []
            if force or game_entry is None or game_entry.due():
                tasks.append(asyncio.create_task(self._refresh_games(requested_date, mode)))
                task_names.append("games")
            if include_previous and (force or previous_entry is None or previous_entry.due()):
                tasks.append(asyncio.create_task(self._refresh_games(previous_date, mode)))
                task_names.append("previous-games")
            if force or standings_entry is None or standings_entry.due():
                tasks.append(asyncio.create_task(self._refresh_standings(requested_date, mode)))
                task_names.append("standings")
            if tasks:
                results = await asyncio.gather(*tasks)
                for name, result in zip(task_names, results, strict=True):
                    if name == "games":
                        game_entry = result
                    elif name == "previous-games":
                        previous_entry = result
                    else:
                        standings_entry = result

            game_entry = game_entry or self._games[requested_date]
            standings_entry = standings_entry or self._standings[requested_date]
            game_freshness = classify_freshness(game_entry.fetched_utc, game_entry.refresh_sec)
            previous_freshness: str | None = None
            if previous_entry:
                previous_freshness = classify_freshness(previous_entry.fetched_utc, previous_entry.refresh_sec)
            standings_freshness = classify_freshness(
                standings_entry.fetched_utc,
                standings_entry.refresh_sec,
            )
            if game_entry.error and not game_entry.value:
                game_freshness = "failed"
            elif game_entry.error and game_freshness == "fresh":
                game_freshness = "stale"
            if previous_entry and previous_entry.error and not previous_entry.value:
                previous_freshness = "failed"
            elif previous_entry and previous_entry.error and previous_freshness == "fresh":
                previous_freshness = "stale"
            if standings_entry.error and not standings_entry.value:
                standings_freshness = "failed"
            elif standings_entry.error and standings_freshness == "fresh":
                standings_freshness = "stale"
            overall = "failed" if game_freshness == "failed" else (
                "stale"
                if (
                    "stale" in {game_freshness, standings_freshness, previous_freshness}
                    or "failed" in {standings_freshness, previous_freshness}
                )
                else "fresh"
            )
            games = _records_with_freshness(game_entry.value, game_freshness)
            if previous_entry:
                retained = [game for game in previous_entry.value if game.get("status") in ACTIVE_GAME_STATUSES]
                known = {str(game.get("gameId")) for game in games}
                games.extend(
                    game for game in _records_with_freshness(retained, previous_freshness or "fresh")
                    if str(game.get("gameId")) not in known
                )
            refresh_sec = min(
                game_entry.refresh_sec,
                previous_entry.refresh_sec if previous_entry else game_entry.refresh_sec,
            )
            fetched_utc = min(
                game_entry.fetched_utc,
                previous_entry.fetched_utc if previous_entry else game_entry.fetched_utc,
            )
            errors = [
                value
                for value in [
                    game_entry.error,
                    f"prior-date games: {previous_entry.error}" if previous_entry and previous_entry.error else None,
                    standings_entry.error,
                ]
                if value
            ]
            return {
                "schemaVersion": "1.0",
                "date": requested_date,
                "mode": mode,
                "games": games,
                "standings": _records_with_freshness(standings_entry.value, standings_freshness),
                "source": {
                    "provider": "mlb-statsapi",
                    "fetchedUtc": fetched_utc,
                    "freshness": overall,
                    "refreshSec": refresh_sec,
                    "error": " | ".join(errors) if errors else None,
                },
            }

    def _replay_path(self, requested_date: str) -> Path:
        datetime.strptime(requested_date, "%Y-%m-%d")
        return self.replay_dir / f"{requested_date}.json"

    async def get_snapshot(
        self,
        requested_date: str,
        *,
        mode: Mode = "live",
        force: bool = False,
    ) -> dict[str, Any]:
        datetime.strptime(requested_date, "%Y-%m-%d")
        if mode == "demo":
            return self._demo_snapshot()
        if mode == "replay":
            path = self._replay_path(requested_date)
            if path.exists() and not force:
                return json.loads(path.read_text())
            snapshot = await self._live_snapshot(requested_date, "replay", True)
            if snapshot["source"]["freshness"] == "failed":
                return snapshot
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(snapshot, indent=2) + "\n")
            temporary.replace(path)
            return snapshot
        return await self._live_snapshot(requested_date, "live", force)
