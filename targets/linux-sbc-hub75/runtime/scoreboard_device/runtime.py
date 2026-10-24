from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import signal
import subprocess
import threading
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import monotonic, perf_counter
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from scoreboard_device.team import TeamSchedule, team_schedule_frame
from scoreboard_device.arcade import ArcadeController
from scoreboard_device.arcade_progress import ArcadeProgress
from scoreboard_device.controller_settings import ControllerSettings
from scoreboard_device.home import home_frame
from scoreboard_device.history import HistoryController, final_cards
from scoreboard_device.scoring_alerts import ScoringAlerts, fetch_scoring_events
from shared_py.nfl_feed import NflFeed, validate_settings, selected_games
from shared_py.nfl_frame import nfl_frame
from shared_py.sports import sports_settings, validate_sports, filter_games, TEAM_CATALOG
from shared_py.league_feed import LeagueFeed
from shared_py.sports_frame import sports_frame
from shared_py.freshness import classify_freshness
from shared_py.bdf import parse_bdf
from shared_py.fireworks_frame import create_fireworks_frame
from shared_py.fireworks_sequence import FIREWORKS_SEQUENCE, SecretCommand, advance_secret_sequence
from shared_py.mlb_adapter import MlbStatsApiAdapter
from shared_py.morning_recap import build_recap
from shared_py.png import decode_rgba_png, encode_rgba_png
from shared_py.recap_cache import load_recap_window, save_recap_window
from shared_py.recap_frame import create_recap_frame
from shared_py.renderer import PixelBuffer, render_scene
from shared_py.reveal import (
    arm,
    begin_playback,
    complete_playback,
    disarm,
    force_start,
    load_reveal,
    save_reveal,
    should_autoplay_on_boot,
)
from shared_py.reveal_frame import create_reveal_text_frame
from shared_py.rotation import build_playlist, is_quiet_time

from .admin_auth import BroadcastPinStore

from . import __version__
from .buttons import PhysicalButtons
from .bluetooth_remote import BluetoothRemote
from .output import DisplayOutput, create_output
from .status_server import StatusServer
from .transport import TransportController



LOGGER = logging.getLogger("scoreboard-device")

FIREWORKS_DURATION_SEC = 30.0
FIREWORKS_RESET_AFTER_SEC = 4.0

# The recap window is slow-moving content — a schedule doesn't change every
# minute. Refresh a few times a day and lean on the cross-restart cache.
RECAP_REFRESH_SEC = 6 * 3600.0
# How far back the fetched window reaches, so an off-day still has a "most
# recent result" to show with a real date.
RECAP_LOOKBACK_DAYS = 4


def _load_logo_assets(root: Path) -> dict[str, dict[str, Any]]:
    directory = (root / "assets" / "team-logos").resolve()
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        return {}
    loaded: dict[str, dict[str, Any]] = {}
    try:
        manifest = _json(manifest_path)
        for entry in manifest.get("assets", []):
            relative = entry.get("path")
            team_id = entry.get("teamId")
            size = entry.get("width")
            if not isinstance(relative, str) or not isinstance(size, int) or entry.get("height") != size:
                continue
            source = (directory / relative).resolve()
            if source.parent != directory or not source.is_file():
                continue
            payload = source.read_bytes()
            if hashlib.sha256(payload).hexdigest() != entry.get("sha256"):
                continue
            width, height, rgba = decode_rgba_png(payload)
            if width != size or height != size:
                continue
            loaded[f"team-logo:{team_id}:{size}"] = {
                "width": width,
                "height": height,
                "data": rgba,
            }
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
        LOGGER.exception("private team logo pack could not be loaded")
        return {}
    return loaded


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _installed_identity(root: Path) -> dict[str, Any]:
    # Repository-based deployments write this file for each activated release.
    # Prefer it over manifest.json because a staged release may inherit the
    # manifest from the previously installed artifact.
    try:
        identity = _json(root / "release-identity.json")
        if not isinstance(identity, dict) or not isinstance(identity.get("buildId"), str):
            raise ValueError("release identity has no build ID")
        return {"buildId": identity.get("buildId"), "sourceCommit": identity.get("sourceCommit"), "sourceDirty": identity.get("sourceDirty")}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass

    try:
        manifest = _json(root / "manifest.json")
        source = manifest.get("source")
        if not isinstance(source, dict) or not isinstance(manifest.get("buildId"), str):
            raise ValueError("manifest has no build or source identity")
        return {"buildId": manifest.get("buildId"), "sourceCommit": source.get("commit"), "sourceDirty": source.get("dirty")}
    except (AttributeError, OSError, ValueError, TypeError, json.JSONDecodeError):
        return {"buildId": "unknown", "sourceCommit": "unknown", "sourceDirty": None}


def _refresh_interval(games: list[Mapping[str, Any]], project: Mapping[str, Any]) -> int:
    statuses = {game.get("status") for game in games}
    data = project["data"]
    if statuses & {"in_progress", "delayed", "suspended"}:
        return int(data["refreshSecLive"])
    if "pregame" in statuses:
        return int(data["refreshSecPregame"])
    return int(data["refreshSecIdle"])


class DeviceRuntime:
    def __init__(self, root: Path, *, output_kind: str | None = None) -> None:
        self.root = root.resolve()
        self.project = _json(self.root / "config" / "project.json")
        self.profile = _json(self.root / "config" / "device-profile.json")
        self.definition = _json(self.root / "definition" / "display-definition.json")
        self.config = _json(self.root / "config" / "runtime-config.json")
        self.installed_identity = _installed_identity(self.root)
        self.fonts = {
            name: parse_bdf((self.root / "definition" / "fonts" / f"{name}.bdf").read_text(encoding="utf-8"))
            for name in ("4x6", "5x7", "6x10")
        }
        self.logo_assets = _load_logo_assets(self.root)
        self.local_standings = _json(self.root / "fixtures" / "team-standings.json")
        self.timezone = ZoneInfo(self.project.get("timezone", "America/New_York"))
        self.team = TeamSchedule(self.root / "state", str(self.timezone))
        self.next_team_fetch = 0.0
        self._team_day = None
        self.started = monotonic()
        self.lock = threading.RLock()
        self.arcade = ArcadeController(store=ArcadeProgress(self.root / 'state' / 'arcade-progress.json'))
        self.transport = TransportController()
        self.games: list[dict[str, Any]] = []
        self.standings: list[dict[str, Any]] = []
        self.fetched_utc: str | None = None
        self.last_success = 0.0
        self.last_error: str | None = None
        self.refresh_sec = int(self.project["data"]["refreshSecIdle"])
        self.next_fetch = 0.0
        self.next_standings_fetch = 0.0
        self.render_count = 0
        self.render_total_ms = 0.0
        self.render_max_ms = 0.0
        self.last_frame: PixelBuffer | None = None
        self.last_frame_png: bytes | None = None
        self.last_frame_hash: str | None = None
        self._cached_commit: str | None = None
        self.next_presses = 0
        self.hold_presses = 0
        self._fireworks_progress = 0
        self._fireworks_last_press: float | None = None
        self._fireworks_started: float | None = None
        self._fireworks_deadline: float | None = None
        self.reveal_path = self.root / "state" / "reveal.json"
        broadcast_pins = BroadcastPinStore(self.root / "state")
        broadcast_pins.get_or_create()
        self._reveal_active = False
        reveal_state = load_reveal(self.reveal_path)
        self._reveal_waiting = reveal_state.get('state') == 'armed' and reveal_state.get('trigger') == 'controller'
        self.controller_settings = ControllerSettings()
        self.home_active = False
        self.history = HistoryController()
        self.scoring_alerts = ScoringAlerts()
        self.history_nfl_feed = NflFeed(self.root / 'state/history-nfl-cache.json')
        self.nfl_feed = NflFeed(self.root / 'state/nfl-cache.json')
        self.nfl_snapshot = None
        self.next_nfl_fetch = 0.0
        self.league_feeds = {k: LeagueFeed(k, self.root / f'state/{k}-cache.json') for k in ('nba', 'nhl')}
        self.history_league_feeds = {k: LeagueFeed(k, self.root / f'state/history-{k}-cache.json') for k in ('nba', 'nhl')}
        self.league_snapshots = {}
        self.next_league_fetch = {'nba': 0.0, 'nhl': 0.0}
        self._consumed_until_release = set()
        self._wake_deadline = 0.0
        self._reveal_deferred_for_quiet_hours = False
        recap_settings = self.project.get("recap") or {}
        self._recap_morning_start = str(recap_settings.get("morningStartLocal", "07:00"))
        self._recap_morning_end = str(recap_settings.get("morningEndLocal", "09:00"))
        self._recap_search_days = max(1, int(recap_settings.get("searchDays", 14)))
        self._recap_dwell_sec = max(1.0, float(recap_settings.get("dwellSec", 8)))
        self.recap_path = self.root / "state" / "recap-window.json"
        self._recap_window: dict[str, Any] | None = load_recap_window(self.recap_path)
        self._recap_error: str | None = None
        self.next_recap_fetch = 0.0
        self._recap_index = 0
        self._recap_started = monotonic()
        self._loop: asyncio.AbstractEventLoop | None = None
        self.stop_event = asyncio.Event()
        self.adapter: MlbStatsApiAdapter | None = None

        # GPIO descriptors must be opened before RGBMatrix initializes and may
        # drop process privileges.
        self.buttons = PhysicalButtons(self.config.get("buttons", {}), self.command_next, self.command_hold)
        self.output: DisplayOutput = create_output(
            output_kind or str(self.config.get("output", "hub75")),
            self.root,
            self.profile,
            self.config,
        )
        status_config = self.config.get("status", {})
        self.status_server = StatusServer(
            str(status_config.get("host", "0.0.0.0")),
            int(status_config.get("port", 8123)),
            self.status,
            actions={
                "reveal_status": self._web_reveal_status,
                "wait": self._web_wait_reveal,
                "arm": self._web_arm_reveal,
                "disarm": self._web_disarm_reveal,
                "trigger": lambda: self._web_play_reveal(consume_state=True),
                "rehearse": lambda: self._web_play_reveal(consume_state=False),
                "get_config": self._web_get_config,
                "update_config": self._web_update_config,
                "control_next": self._web_control_next,
                "control_hold": self._web_control_hold,
                "control_home": self._web_control_home,
                "get_history": self._web_get_history,
                "set_history": self._web_set_history,
                "check_update": self._web_check_update,
                "apply_update": self._web_apply_update,
                "play_message": self._web_play_message,
                "get_screen": self._web_get_screen_png,
                "get_team": self._web_get_team,
                "update_team": self._web_update_team,
                "get_arcade": self._web_get_arcade,
                "update_arcade": self._web_update_arcade,
                "show_team": self._web_show_team,
            },
            authorize_broadcast=lambda pin: BroadcastPinStore.matches(broadcast_pins.get_or_create(), pin),
        )
        self.bluetooth_remote = BluetoothRemote(
            self.config.get("bluetoothRemote", {}), self.command_next, self.command_hold,
            on_input=self._remote_input, on_disconnect=self._remote_disconnected,
        )

        self._refresh_playlist(datetime.now(self.timezone))

    def _remote_disconnected(self) -> None:
        with self.lock:
            self.arcade.suspend()
            self.controller_settings.close()
            self._consumed_until_release.clear()

    def _controller_tick(self) -> None:
        if self.controller_settings.active and monotonic() - self.controller_settings.last_input >= 60:
            self.controller_settings.close()

    def _remote_input(self, button: str, pressed: bool) -> bool:
        with self.lock:
            if button in self._consumed_until_release:
                if not pressed:
                    self._consumed_until_release.discard(button)
                return True
            if self._reveal_waiting:
                if pressed:
                    self._web_play_reveal(consume_state=True)
                    self._consumed_until_release.add(button)
                return True
            if self._reveal_active:
                # Consume every controller edge, including presses held past
                # the final frame, so playback cannot skip or leak into menus.
                if pressed:
                    self._consumed_until_release.add(button)
                return True
            if self._fireworks_deadline is not None:
                self.arcade.exit()
                return button == 'select'
            self._controller_tick()
            if self.controller_settings.active:
                if pressed:
                    action = self.controller_settings.input(button)
                    if button == 'y':
                        self._open_home()
                    elif action == 'home':
                        self._open_home()
                    elif action == 'scoreboard':
                        self.home_active = False
                        self.history.cancel()
                    elif action == 'history':
                        self._web_set_history({'date':self.controller_settings.history_date.isoformat()})
                    elif action == 'arcade':
                        self.home_active = False
                        self.history.cancel()
                        self._arcade_context()
                        self.arcade.input('select', True)
                    elif action == 'save':
                        try:
                            self._web_update_config(self.controller_settings.payload())
                            self.controller_settings.close()
                        except Exception:
                            self.controller_settings.open(self._web_get_config(), self._nfl_games(), datetime.now(self.timezone).date())
                            self.controller_settings.error = 'RELOADED - TRY AGAIN'
                return True
            clock = {'localTime': datetime.now(self.timezone).strftime('%H:%M')}
            sleeping = is_quiet_time(self.project.get('quietHours'), clock) and self.project['quietHours'].get('behavior') == 'sleep'
            if sleeping and monotonic() >= self._wake_deadline:
                self.arcade.suspend()
                if pressed:
                    self._wake_deadline = monotonic() + self._web_get_config()['wakeDurationSec']
                    self._consumed_until_release.add(button)
                return True
            if button == 'y':
                if pressed:
                    self._open_home()
                    self._consumed_until_release.add(button)
                return True
            if button == 'select':
                if pressed:
                    self.arcade.exit()
                    self.controller_settings.open(self._web_get_config(), self._nfl_games(), datetime.now(self.timezone).date())
                return True
            if self.history.active and button == 'x':
                if pressed:
                    self.history.cancel()
                    self._consumed_until_release.add(button)
                return True
            if button == "r" and pressed and not self.arcade.active:
                self._web_show_team()
                self._consumed_until_release.add(button)
                return True
            was_active = self.arcade.active
            self._arcade_context()
            consumed = self.arcade.input(button, pressed)
            if self.arcade.active and not was_active:
                self._fireworks_progress = 0
                self._fireworks_last_press = None
            return consumed

    def _open_home(self) -> None:
        self.history.cancel()
        self.scoring_alerts.sync(None)
        self.arcade.exit()
        self.controller_settings.close()
        self.home_active = True
        self._fireworks_progress = 0
        self._fireworks_last_press = None

    def _web_control_home(self) -> dict[str, Any]:
        with self.lock:
            if not self._reveal_active and not self._reveal_waiting and self._fireworks_deadline is None:
                self._open_home()
        return self.status()

    def command_next(self) -> None:
        with self.lock:
            if self._reveal_active:
                return
            if self.home_active:
                self.home_active = False
                return
            self.history.tick()
            self.next_presses += 1
            if self.history.active:
                self.history.transport.next()
                return
            self.scoring_alerts.sync(None)
            self.arcade.exit()
            self.transport.next()
        self._fireworks_press("next")
        LOGGER.info("control next")

    def command_hold(self) -> None:
        with self.lock:
            if self._reveal_active:
                return
            if self.home_active:
                self.home_active = False
                return
            self.history.tick()
            self.hold_presses += 1
            if self.history.active:
                self.history.transport.toggle_hold()
                return
            self.scoring_alerts.sync(None)
            self.arcade.exit()
            held = self.transport.toggle_hold()
        self._fireworks_press("hold")
        LOGGER.info("control hold=%s", held)

    def _fireworks_press(self, command: SecretCommand) -> None:
        """Feeds the shared NEXT/HOLD secret-sequence contract (see
        frontend/src/easterEgg.ts and shared_py/fireworks_sequence.py). Runs
        alongside, never instead of, the normal short-press command above —
        each physical press is recognized here exactly once."""
        with self.lock:
            if self._fireworks_deadline is not None:
                if command == "next":
                    self._fireworks_deadline = None  # NEXT exits an active celebration early.
                return
            now = monotonic()
            starting = (
                self._fireworks_progress
                if self._fireworks_last_press is not None
                and now - self._fireworks_last_press <= FIREWORKS_RESET_AFTER_SEC
                else 0
            )
            next_progress = advance_secret_sequence(starting, command)
            self._fireworks_last_press = now
            if next_progress == len(FIREWORKS_SEQUENCE):
                self._fireworks_started = now
                self._fireworks_deadline = now + FIREWORKS_DURATION_SEC
                self._fireworks_progress = 0
                LOGGER.info("fireworks armed and triggered")
                return
            self._fireworks_progress = next_progress

    def _fireworks_status(self) -> tuple[bool, float]:
        """Returns (active, elapsed_ms), clearing an expired celebration."""
        with self.lock:
            if self._fireworks_deadline is None:
                return False, 0.0
            now = monotonic()
            if now >= self._fireworks_deadline:
                self._fireworks_deadline = None
                self._fireworks_started = None
                return False, 0.0
            started = self._fireworks_started or now
            return True, (now - started) * 1000

    def _web_get_history(self):
        with self.lock:
            result = self.history.status()
            result['today'] = datetime.now(self.timezone).date().isoformat()
            return result

    def _web_set_history(self, payload):
        with self.lock:
            if self._reveal_active or self._reveal_waiting:
                raise ValueError('Finish or cancel the surprise first')
            if not isinstance(payload,dict) or set(payload) != {'date'}:
                raise ValueError('Provide a date, or null to return to live')
            if payload['date'] is None:
                self.history.cancel()
            elif isinstance(payload['date'],str):
                self.history.select(payload['date'],datetime.now(self.timezone).date())
            else:
                raise ValueError('Date must be YYYY-MM-DD')
            self.home_active = False
            self.arcade.exit()
            self.controller_settings.close()
            self.scoring_alerts.sync(None)
            self._fireworks_deadline = None
            self._fireworks_progress = 0
            self._fireworks_last_press = None
            return self._web_get_history()

    async def _fetch_history(self):
        if 'sports' in self.project:
            return await self._fetch_selected_history()
        with self.lock:
            generation, requested_date = self.history.generation, self.history.date
            if not requested_date: return
        adapter = MlbStatsApiAdapter(timezone_name=str(self.timezone))
        try:
            mlb, nfl = await asyncio.gather(adapter.get_final_games(requested_date),
                asyncio.to_thread(self.history_nfl_feed.fetch,requested_date), return_exceptions=True)
        finally:
            await adapter.close()
        errors = []
        if isinstance(mlb,BaseException):
            mlb = []; errors.append('MLB DATA OFFLINE')
        if isinstance(nfl,BaseException):
            nfl = {'games':[],'freshness':'failed'}
        if nfl.get('freshness') != 'fresh': errors.append('NFL DATA OFFLINE')
        cards = final_cards(mlb,nfl.get('games',[]),requested_date,str(self.timezone))
        with self.lock:
            self.history.apply(generation,cards,errors,self.project['rotation']['otherDwellSec'],self._web_get_config()['nfl']['dwellSec'])

    async def _fetch_selected_history(self):
        with self.lock:
            generation, requested = self.history.generation, self.history.date
            policy = sports_settings(self.project)
            if not requested: return
        adapter = MlbStatsApiAdapter(timezone_name=str(self.timezone))
        tasks, leagues = [], []
        for league in ('mlb','nfl','nba','nhl'):
            if not policy[league]['enabled']: continue
            leagues.append(league)
            if league=='mlb': tasks.append(adapter.get_final_games(requested))
            else:
                feed = self.history_nfl_feed if league=='nfl' else self.history_league_feeds[league]
                tasks.append(asyncio.to_thread(feed.fetch, requested))
        try: values = await asyncio.gather(*tasks, return_exceptions=True)
        finally: await adapter.close()
        cards, errors = [], []
        for league, value in zip(leagues, values):
            if isinstance(value, BaseException): errors.append(league.upper()+' DATA OFFLINE'); continue
            if league=='mlb':
                cards += final_cards(filter_games(policy, 'mlb', value), [], requested, str(self.timezone))
                continue
            source = value.get('source', value)
            if source.get('freshness') not in ('fresh','partial'): errors.append(league.upper()+' DATA OFFLINE')
            for g in filter_games(policy, league, value.get('games', [])):
                try:
                    if not g['completed'] or datetime.fromisoformat(g['date'].replace('Z','+00:00')).astimezone(self.timezone).date().isoformat()!=requested: continue
                    if any(g[side].get('score') is None or int(g[side]['score'])<0 for side in ('home','away')): continue
                    cards.append(dict(sport=league.upper(), id=league+':'+g['id'], away=g['away'], home=g['home']))
                except (ValueError, TypeError, KeyError): continue
        with self.lock:
            self.history.apply(generation, cards, errors, self.project['rotation']['otherDwellSec'], 8)

    def _visible_scoring_game(self):
        now = datetime.now(self.timezone)
        clock = {'localTime':now.strftime('%H:%M')}
        sleeping = is_quiet_time(self.project.get('quietHours'),clock) and self.project['quietHours'].get('behavior') == 'sleep' and monotonic() >= self._wake_deadline
        if (self.home_active or self.history.active or self.controller_settings.active or self.arcade.active
                or self._reveal_active or self._reveal_waiting or self._fireworks_deadline is not None or sleeping
                or (self._in_morning_window(now) and self._recap_window)):
            return None
        item = self.transport.current
        if not item: return None
        if item.get('kind') == 'game':
            game = next((g for g in self.games if g['gameId']==item['gameId']),None)
            if not game or self.project['data']['mode'] != 'live' or self._freshness() != 'fresh': return None
            sport, completed = 'MLB', game['status']=='final'
            live = game['status'] in ('in_progress','delayed','suspended')
        elif item.get('kind') == 'nfl':
            game = next((g for g in self._nfl_games() if g['id']==item['gameId']),None)
            if not game or self._nfl_freshness() != 'fresh': return None
            sport, completed = 'NFL', game['completed']
            live = game['state']=='in'
        else: return None
        key = (sport,item['gameId'])
        # Allow one final poll for a game already watched live (e.g. a walk-off).
        if not live and not (completed and self.scoring_alerts.key == key): return None
        return key, completed

    async def _fetch_scoring(self):
        with self.lock:
            visible = self._visible_scoring_game()
            if not visible: return
            key, completed = visible
            generation = self.scoring_alerts.generation
        try:
            events = await asyncio.to_thread(fetch_scoring_events,*key)
        except Exception:
            with self.lock: self.scoring_alerts.failed(generation)
            return
        with self.lock:
            # HTTP replies cannot celebrate a game that has rotated or been hidden.
            visible = self._visible_scoring_game()
            if visible and visible[0] == key:
                self.scoring_alerts.ingest(generation,events,completed=completed or visible[1])

    def _active_date(self, now: datetime) -> str:
        rollover_hour, rollover_minute = (int(value) for value in self.project["data"]["rolloverLocalTime"].split(":"))
        rollover = now.replace(hour=rollover_hour, minute=rollover_minute, second=0, microsecond=0)
        return (now.date() if now >= rollover else (now - timedelta(days=1)).date()).isoformat()

    def _rules(self, *, quiet_enabled: bool = True) -> dict[str, Any]:
        rules = deepcopy(self.project["rotation"])
        rules["favorites"] = list(self.project["favorites"])
        rules["quietHours"] = deepcopy(self.project["quietHours"])
        if not quiet_enabled:
            rules["quietHours"]["enabled"] = False
        return rules

    def _with_local_standings(self, standings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Replace any prior copy of each private/local snapshot, then append
        the current local rows. This keeps the configured team record visible even when
        the MLB standings request is temporarily unavailable."""
        local_rows = deepcopy(self.local_standings)
        record = self.team.snapshot(datetime.now(self.timezone))
        for snapshot in local_rows:
            for row in snapshot.get("teams", []):
                if row.get("team", {}).get("id") == "sample-team":
                    row.update({key: record[key] for key in ("rank", "wins", "losses")})
        local_ids = {str(item.get("standingsId", "")) for item in local_rows}
        return [
            *(item for item in standings if str(item.get("standingsId", "")) not in local_ids),
            *local_rows,
        ]

    def _team_playlist(self, items, now):
        if not sports_settings(self.project)['team']['enabled']:
            self._team_day = now.astimezone(self.timezone).date()
            self._team_practice_deadline = None
            return [i for i in items if i.get('teamId') != 'sample-team']
        snapshot = self.team.snapshot(now)
        cards = [{'kind': 'team', 'scene': 'team', 'groupId': 'summary', 'dwellSec': 12}]
        cards += [{'kind': 'team', 'scene': 'team', 'groupId': group['id'], 'dwellSec': 10}
                  for group in snapshot['groups']]
        cards.append({'kind': 'team', 'scene': 'team', 'groupId': 'practices', 'dwellSec': 10})
        cards += [{'kind': 'team', 'scene': 'team', 'groupId': 'practice:' + event['id'],
                   'practiceId': event['id'], 'dwellSec': 10} for event in snapshot['upcomingPractices']]
        result = []
        inserted = False
        for item in items:
            if item.get('teamId') == 'sample-team':
                result.extend(cards); inserted = True
            else:
                result.append(item)
        if not inserted: result.extend(cards)
        self._team_day = now.astimezone(self.timezone).date()
        self._team_practice_deadline = min((datetime.fromisoformat(event.get('endUtc') or event['startUtc'])
                                             for event in snapshot['upcomingPractices']), default=None)
        return result

    def _nfl_games(self):
        now_date = datetime.now(self.timezone).date().isoformat()
        return self.nfl_snapshot['games'] if self.nfl_snapshot and self.nfl_snapshot['date'] == now_date else []

    def _nfl_freshness(self):
        value = self.nfl_snapshot or {}
        freshness = value.get('freshness','loading')
        if freshness == 'fresh' and value.get('fetchedUtc'):
            try:
                if (datetime.now(timezone.utc)-datetime.fromisoformat(value['fetchedUtc'])).total_seconds() > 90: return 'stale'
            except (TypeError,ValueError): return 'stale'
        return freshness

    def _nfl_playlist(self, items):
        settings = self._web_get_config()['nfl']
        if 'nfl' in self.project.get('sports', {}): settings['favoritesOnly'] = False
        games = filter_games(sports_settings(self.project), 'nfl', selected_games(self._nfl_games(), settings))
        nfl = [{'kind':'nfl', 'scene':'nfl', 'gameId':g['id'], 'completed':g['completed'], 'dwellSec':settings['dwellSec']} for g in games]
        return [*nfl, *items] if settings['liveFirst'] else [*items, *nfl]

    async def _fetch_nfl(self):
        if not self._web_get_config()['nfl']['enabled']:
            self.next_nfl_fetch = monotonic() + 30
            return
        requested_date = datetime.now(self.timezone).date().isoformat()
        generation = self.project.get('meta', {}).get('version')
        value = await asyncio.to_thread(self.nfl_feed.fetch, requested_date)
        with self.lock:
            if (not sports_settings(self.project)['nfl']['enabled'] or generation != self.project.get('meta', {}).get('version') or requested_date != datetime.now(self.timezone).date().isoformat()):
                self.next_nfl_fetch = 0
                return
            self.nfl_snapshot = value
            self.next_nfl_fetch = monotonic() + 30
            self._refresh_playlist(datetime.now(self.timezone))

    def _league_games(self, league):
        value = self.league_snapshots.get(league, {})
        return value.get('games', []) if value.get('date') == datetime.now(self.timezone).date().isoformat() else []

    def _league_freshness(self, league):
        source = self.league_snapshots.get(league, {}).get('source', {})
        value = source.get('freshness', 'loading')
        if value in ('fresh', 'partial') and source.get('fetchedUtc'):
            try:
                if (datetime.now(timezone.utc)-datetime.fromisoformat(source['fetchedUtc'])).total_seconds() > 90: return 'stale'
            except (ValueError, TypeError): return 'stale'
        return value

    async def _fetch_league(self, league):
        self.next_league_fetch[league] = monotonic() + 30
        if not sports_settings(self.project)[league]['enabled']: return
        requested = datetime.now(self.timezone).date().isoformat()
        generation = self.project.get('meta', {}).get('version')
        try:
            value = await asyncio.to_thread(self.league_feeds[league].fetch, requested)
        except Exception:
            LOGGER.exception('%s feed task failed', league)
            return
        with self.lock:
            if (not sports_settings(self.project)[league]['enabled'] or generation != self.project.get('meta', {}).get('version')
                    or requested != datetime.now(self.timezone).date().isoformat()):
                self.next_league_fetch[league] = 0
                return
            self.league_snapshots[league] = value
            self.next_league_fetch[league] = monotonic() + max(30, value.get('source', {}).get('refreshSec', 30))
            self._refresh_playlist(datetime.now(self.timezone))

    def _refresh_playlist(self, now):
        policy = sports_settings(self.project)
        self.standings = self._with_local_standings(self.standings)
        standings = []
        for snapshot in self.standings:
            local = (snapshot.get('source') or {}).get('provider') == 'local-manual'
            if local:
                if policy['team']['enabled']: standings.append(snapshot)
            elif policy['mlb']['enabled']:
                value = deepcopy(snapshot)
                if policy['mlb']['teams'] is not None:
                    value['teams'] = [row for row in value.get('teams', []) if row.get('team', {}).get('abbr') in policy['mlb']['teams']]
                standings.append(value)
        games = filter_games(policy, 'mlb', self.games)
        items = build_playlist(games, self._rules(quiet_enabled=False),
            {'localTime': now.strftime('%H:%M')}, standings=standings, content_mode='mixed')
        items = self._nfl_playlist(self._team_playlist(items, now))
        extras = []
        for league in ('nba', 'nhl'):
            extras += [dict(kind=league, scene=league, gameId=g['id'], completed=g['completed'], dwellSec=8)
                       for g in filter_games(policy, league, self._league_games(league))]
        extras.sort(key=lambda i: next((g['state'] != 'in' for g in self._league_games(i['kind']) if g['id']==i['gameId']), True))
        items = extras + items
        if any(i.get('kind') != 'idle' for i in items): items = [i for i in items if i.get('kind') != 'idle']
        self.transport.update(items, games)

    async def _fetch_team(self):
        if not sports_settings(self.project)['team']['enabled']:
            self.next_team_fetch = monotonic() + 30
            return
        refreshed = await asyncio.to_thread(self.team.refresh)
        with self.lock:
            self.next_team_fetch = monotonic() + (3600 if refreshed else 60)
            self._refresh_playlist(datetime.now(self.timezone))

    def _arcade_context(self) -> None:
        """Give the arcade wall-clock time and quiet hours (Happy Hour; closed while quiet)."""
        self.arcade.set_context(datetime.now(self.timezone), self.project.get('quietHours'))

    def _web_get_arcade(self):
        with self.lock:
            self._arcade_context()
            return {**self.arcade.store.summary(), 'happyHour': self.arcade.happy(), 'available': not self.arcade.quiet}

    def _web_update_arcade(self, payload):
        action = payload.get('action')
        with self.lock:
            if action == 'resetScores':
                self.arcade.store.reset_scores()
            elif action == 'gems':
                amount = payload.get('amount')
                if not isinstance(amount, int) or isinstance(amount, bool) or not -10000 <= amount <= 10000:
                    raise ValueError('Enter a whole number of gems')
                self.arcade.store.add_gems(amount)
            else:
                raise ValueError('Unknown arcade action')
        return self._web_get_arcade()

    def _web_get_team(self):
        with self.lock:
            return self.team.snapshot(datetime.now(self.timezone))

    def _web_update_team(self, payload):
        with self.lock:
            self.team.update(payload)
            self._refresh_playlist(datetime.now(self.timezone))
            return self._web_get_team()

    def _web_show_team(self):
        with self.lock:
            if self._reveal_active or self._reveal_waiting:
                raise ValueError('Finish or cancel the reveal first')
            self._refresh_playlist(datetime.now(self.timezone))
            self.home_active = False
            self.history.cancel()
            self.scoring_alerts.sync(None)
            self.arcade.exit()
            self.transport.index = next(i for i, item in enumerate(self.transport.items)
                                        if item.get('kind') == 'team' and item['groupId'] == 'summary')
            self.transport.item_started = monotonic()
            self.transport.held = False
            self.transport.final_started = None
            return {'ok': True}

    async def _fetch(self) -> None:
        if not sports_settings(self.project)['mlb']['enabled']:
            self.next_fetch = monotonic() + 30
            return
        mode = self.project["data"]["mode"]
        try:
            if mode == "demo":
                games = _json(self.root / "fixtures" / "demo-day.json")
                standings = _json(self.root / "fixtures" / "demo-standings.json")
                standings_error = None
            else:
                self.adapter = self.adapter or MlbStatsApiAdapter(timezone_name=str(self.timezone))
                now_local = datetime.now(self.timezone)
                requested_date = self._active_date(now_local)
                rollover_hour, rollover_minute = (
                    int(value) for value in self.project["data"]["rolloverLocalTime"].split(":")
                )
                rollover = now_local.replace(
                    hour=rollover_hour,
                    minute=rollover_minute,
                    second=0,
                    microsecond=0,
                )
                previous_date = (now_local.date() - timedelta(days=1)).isoformat()
                include_previous_live = now_local >= rollover
                standings_due = monotonic() >= self.next_standings_fetch or not self.standings
                tasks = [self.adapter.get_game_states(requested_date, mode=mode)]
                if include_previous_live:
                    tasks.append(self.adapter.get_game_states(previous_date, mode=mode))
                if standings_due:
                    tasks.append(self.adapter.get_standings(requested_date, mode=mode))
                results = await asyncio.gather(*tasks, return_exceptions=True)
                if isinstance(results[0], BaseException):
                    raise results[0]
                games = results[0]
                result_index = 1
                partial_errors: list[str] = []
                if include_previous_live:
                    previous_result = results[result_index]
                    result_index += 1
                    if isinstance(previous_result, BaseException):
                        partial_errors.append(f"prior-date games: {previous_result}")
                    else:
                        retained = [
                            game for game in previous_result
                            if game.get("status") in {"in_progress", "delayed", "suspended"}
                        ]
                        known = {str(game.get("gameId")) for game in games}
                        games = [*games, *(game for game in retained if str(game.get("gameId")) not in known)]
                standings = self.standings
                standings_error = " | ".join(partial_errors) or None
                if standings_due:
                    standings_result = results[result_index]
                    if isinstance(standings_result, BaseException):
                        message = f"standings: {standings_result}"
                        standings_error = " | ".join(value for value in (standings_error, message) if value)
                        self.next_standings_fetch = monotonic() + 30
                    else:
                        standings = standings_result
                        self.next_standings_fetch = monotonic() + 300
            standings = self._with_local_standings(standings)
            fetched = games[0]["source"]["fetchedUtc"] if games else _utc_now()
            refresh = _refresh_interval(games, self.project)
            playlist = build_playlist(
                games,
                self._rules(quiet_enabled=False),
                {"localTime": datetime.now(self.timezone).strftime("%H:%M")},
                standings=standings,
                content_mode="mixed",
            )
            with self.lock:
                self.games = games
                self.standings = standings
                self.fetched_utc = fetched
                self.last_success = monotonic()
                self.last_error = standings_error
                self.refresh_sec = refresh
                self.next_fetch = monotonic() + refresh
                self._refresh_playlist(datetime.now(self.timezone))
            LOGGER.info(
                "data refresh games=%d standings=%d game_cadence=%ds standings_due=%s",
                len(games),
                len(standings),
                refresh,
                mode == "demo" or standings_due,
            )
        except Exception as error:
            with self.lock:
                self.last_error = str(error)
                self.next_fetch = monotonic() + min(30, max(5, self.refresh_sec))
            LOGGER.exception("data refresh failed")

    async def _fetch_recap_window(self) -> None:
        if not sports_settings(self.project)['mlb']['enabled']:
            self.next_recap_fetch = monotonic() + 30
            return
        """Refreshes the favorites' recent-result / next-game schedule window
        on its own slow cadence, independent of the baseball-day game cache
        in _fetch. The result is cached under state/ so it survives restarts
        (and a later fetch failure keeps serving the last good window)."""
        self.next_recap_fetch = monotonic() + RECAP_REFRESH_SEC
        if self.project["data"]["mode"] != "live":
            return
        try:
            self.adapter = self.adapter or MlbStatsApiAdapter(timezone_name=str(self.timezone))
            today = datetime.now(self.timezone).date()
            start_date = (today - timedelta(days=RECAP_LOOKBACK_DAYS)).isoformat()
            end_date = (today + timedelta(days=self._recap_search_days)).isoformat()
            games = await self.adapter.get_recap_window(start_date=start_date, end_date=end_date, mode="live")
            fetched = games[0]["source"]["fetchedUtc"] if games else _utc_now()
            with self.lock:
                self._recap_window = save_recap_window(
                    self.recap_path,
                    start_date=start_date,
                    end_date=end_date,
                    fetched_utc=fetched,
                    games=games,
                )
                self._recap_error = None
            LOGGER.info("recap window refresh games=%d window=%s..%s", len(games), start_date, end_date)
        except Exception as error:  # noqa: BLE001 - keep serving the cached window
            with self.lock:
                self._recap_error = str(error)
            LOGGER.exception("recap window refresh failed; serving cached window")

    def _recap_forward_days(self, now: datetime) -> int:
        """How many days past *today* the cached window actually reaches — the
        honest value behind "No game scheduled in the next N days". Clamps at
        0 for a window so stale it no longer covers the future at all."""
        window = self._recap_window
        if not window:
            return 0
        try:
            end = datetime.fromisoformat(window["endDate"]).date()
        except (KeyError, TypeError, ValueError):
            return 0
        return max(0, (end - now.date()).days)

    def _in_morning_window(self, now: datetime) -> bool:
        return is_quiet_time(
            {"enabled": True, "start": self._recap_morning_start, "end": self._recap_morning_end},
            {"localTime": now.strftime("%H:%M")},
        )

    def _render_recap(self, now: datetime) -> PixelBuffer | None:
        """One favorite's morning recap card, cycling across favorites on the
        recap dwell. Returns None if there is nothing cached to show yet."""
        window = self._recap_window
        policy = sports_settings(self.project)['mlb']
        if not policy['enabled']: return None
        favorites = [str(value) for value in self.project.get("favorites", [])
                     if policy['teams'] is None or str(value) in policy['teams']]
        if not window or not favorites:
            return None
        if monotonic() - self._recap_started >= self._recap_dwell_sec:
            self._recap_index += 1
            self._recap_started = monotonic()
        favorite = favorites[self._recap_index % len(favorites)]
        recap = build_recap(window["games"], favorite, now, search_days=self._recap_forward_days(now))
        logical = self.profile["logical"]
        font = self.fonts.get("4x6") or next(iter(self.fonts.values()))
        started = perf_counter()
        frame = create_recap_frame(int(logical["width"]), int(logical["height"]), recap, font, now)
        render_ms = (perf_counter() - started) * 1000
        self._show_frame(frame)
        with self.lock:
            self.render_count += 1
            self.render_total_ms += render_ms
            self.render_max_ms = max(self.render_max_ms, render_ms)
        return frame

    def _show_frame(self, frame: PixelBuffer) -> None:
        self.output.show(frame)
        self.last_frame = frame
        digest = hashlib.sha256(frame.data).hexdigest()
        if digest != self.last_frame_hash:
            self.last_frame_hash = digest
            self.last_frame_png = encode_rgba_png(frame.width, frame.height, frame.data)

    def _freshness(self) -> str:
        if not self.fetched_utc:
            return "failed" if self.last_error else "loading"
        value = classify_freshness(self.fetched_utc, self.refresh_sec)
        if self.last_error and value == "fresh":
            return "stale"
        return value

    def _current_records(self) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
        item = self.transport.current
        if not item:
            return None, None, None
        game = next((candidate for candidate in self.games if candidate.get("gameId") == item.get("gameId")), None)
        standings = next((candidate for candidate in self.standings if candidate.get("standingsId") == item.get("standingsId")), None)
        row = next(
            (candidate for candidate in (standings or {}).get("teams", []) if str(candidate.get("team", {}).get("id")) == str(item.get("teamId"))),
            None,
        )
        return game, standings, row

    def _render(self, now: datetime) -> PixelBuffer | None:
        with self.lock:
            self.history.tick()
        if self._reveal_active:
            # A live-triggered reveal (web "Play now"/"Rehearse", or the
            # boot-time autoplay) owns the display exclusively via its own
            # render loop in _play_reveal_sequence; the main loop must not
            # draw over it.
            return None
        with self.lock:
            self._controller_tick()
            if self._reveal_waiting:
                logical = self.profile['logical']
                font = self.fonts.get('4x6') or next(iter(self.fonts.values()))
                frame = create_reveal_text_frame(
                    int(logical['width']), int(logical['height']),
                    ['PRESS ANY KEY TO CONTINUE...'], font,
                )
                self._show_frame(frame)
                return frame
        clock = {"localTime": now.strftime("%H:%M")}
        quiet = is_quiet_time(self.project.get("quietHours"), clock)
        behavior = self.project["quietHours"].get("behavior")
        if quiet and behavior == "sleep" and monotonic() >= self._wake_deadline and not self.controller_settings.active:
            with self.lock:
                self.arcade.suspend()
            logical = self.profile['logical']
            wake_seconds = int(self._web_get_config()['wakeDurationSec'])
            font = self.fonts.get('4x6') or next(iter(self.fonts.values()))
            frame = create_reveal_text_frame(
                int(logical['width']), int(logical['height']),
                [f'PRESS ANY BUTTON TO CHECK SCORES FOR {wake_seconds} SECONDS...'], font,
            )
            self.output.set_brightness(15)
            self._show_frame(frame)
            return frame
        # Precedence: project.brightness (versioned, user-editable) wins; runtime-config's
        # brightness/dimBrightness are the legacy/hardware-wiring fallback for a project
        # saved before brightness joined the schema.
        project_brightness = self.project.get("brightness") or {}
        normal_brightness = project_brightness.get("normal", self.config.get("brightness", 35))
        dim_brightness = project_brightness.get("dim", self.config.get("dimBrightness", 10))
        self.output.set_brightness(int(dim_brightness) if quiet else int(normal_brightness))
        with self.lock:
            settings = self.controller_settings
            if settings.active:
                draft = settings.draft
                self.output.set_brightness(draft['brightness']['normal' if settings.page == 'settings' and settings.index == 0 else ('dim' if (settings.page == 'settings' and settings.index == 1) or quiet else 'normal')])
                logical = self.profile['logical']
                if not settings.preview:
                    frame = settings.frame(self.fonts['4x6'], int(logical['width']), int(logical['height']))
                    self._show_frame(frame)
                    return frame

        fireworks_active, fireworks_elapsed_ms = self._fireworks_status()
        if fireworks_active:
            with self.lock:
                self.arcade.suspend()
            # Data keeps refreshing on its own schedule (see run()/_fetch());
            # transport is simply not advanced while a celebration plays, so
            # normal rotation resumes from where it left off afterward.
            logical = self.profile["logical"]
            started = perf_counter()
            frame = create_fireworks_frame(int(logical["width"]), int(logical["height"]), fireworks_elapsed_ms)
            render_ms = (perf_counter() - started) * 1000
            self._show_frame(frame)
            with self.lock:
                self.render_count += 1
                self.render_total_ms += render_ms
                self.render_max_ms = max(self.render_max_ms, render_ms)
            return frame

        with self.lock:
            if self.history.active and not self.controller_settings.active:
                frame = self.history.frame(self.fonts)
                self._show_frame(frame)
                return frame
            visible = self._visible_scoring_game()
            self.scoring_alerts.sync(visible[0] if visible else None)
            alert, finished = self.scoring_alerts.tick()
            if finished: self.transport.item_started = monotonic()
            if alert:
                frame = self.scoring_alerts.frame(self.fonts)
                self._show_frame(frame)
                return frame
            if self.home_active and not self.controller_settings.active:
                logical = self.profile['logical']
                frame = home_frame(now.astimezone(self.timezone), self.fonts, int(logical['width']), int(logical['height']))
                self._show_frame(frame)
                return frame

        # Games are a deliberate takeover; live data still refreshes in run().
        with self.lock:
            self._arcade_context()
            self.arcade.tick()
            if self.arcade.active:
                started = perf_counter()
                frame = self.arcade.frame(self.fonts['4x6'])
                render_ms = (perf_counter() - started) * 1000
            else:
                frame = None
        if frame is not None:
            self._show_frame(frame)
            with self.lock:
                self.render_count += 1
                self.render_total_ms += render_ms
                self.render_max_ms = max(self.render_max_ms, render_ms)
            return frame

        # Morning recap window. After quiet+sleep (blanked above) and after a
        # manually-triggered fireworks celebration (which must not lose to a
        # scheduled card), but ahead of normal rotation. Renders at whatever
        # brightness was set above, so a quiet+dim morning still dims it.
        if not self.controller_settings.active and self._in_morning_window(now):
            recap_frame = self._render_recap(now)
            if recap_frame is not None:
                return recap_frame

        with self.lock:
            if (self._team_day != now.astimezone(self.timezone).date() or
                    (getattr(self, '_team_practice_deadline', None) is not None and now >= self._team_practice_deadline)):
                self._refresh_playlist(now)
            self.transport.tick()
            item = deepcopy(self.transport.current)
            game, standings, row = self._current_records()
            freshness = self._freshness()
            elapsed_ms = (monotonic() - self.transport.item_started) * 1000
            transport_held = self.transport.held
        if not self.controller_settings.active and (item is None or item.get('kind') == 'idle') and not sports_settings(self.project)['mlb']['enabled']:
            enabled = [k.upper() for k,v in sports_settings(self.project).items() if v['enabled']]
            active_leagues = [k for k in ('nfl','nba','nhl') if sports_settings(self.project)[k]['enabled']]
            freshness = [self._nfl_freshness() if k=='nfl' else self._league_freshness(k) for k in active_leagues]
            message = ('LOADING SCORES' if any(v=='loading' for v in freshness) else
                       'DATA OFFLINE' if freshness and all(v in ('failed','stale') for v in freshness) else
                       'NO SELECTED GAMES') if enabled else 'NO SPORTS SELECTED'
            frame = create_reveal_text_frame(128,32,[message,
                ' / '.join(enabled) if enabled else 'SELECT MENU: SPORTS'],self.fonts['4x6'])
            self._show_frame(frame)
            return frame
        if item and item.get('kind') in ('nba', 'nhl') and not self.controller_settings.active:
            league = item['kind']
            g = next((g for g in self._league_games(league) if g['id'] == item['gameId']), None)
            started = perf_counter()
            frame = sports_frame(g, self.fonts, self._league_freshness(league) not in ('fresh', 'partial'), transport_held, str(self.timezone))
            elapsed = (perf_counter()-started)*1000
            self._show_frame(frame)
            with self.lock:
                self.render_count += 1; self.render_total_ms += elapsed; self.render_max_ms = max(self.render_max_ms, elapsed)
            return frame
        if item and item.get('kind') == 'nfl' and not self.controller_settings.active:
            nfl_game = next((g for g in self._nfl_games() if g['id'] == item['gameId']), None)
            stale = self._nfl_freshness() != 'fresh'
            frame = nfl_frame(nfl_game, self.fonts, self._web_get_config()['nfl']['layout'], stale, str(self.timezone), self.logo_assets)
            self._show_frame(frame)
            return frame
        if item and item.get('kind') == 'team' and not self.controller_settings.active:
            started = perf_counter()
            with self.lock:
                snapshot = self.team.snapshot(now)
            group = next((g for g in snapshot['groups'] if g['id'] == item.get('groupId')), None)
            practice = next((event for event in snapshot['upcomingPractices'] if event['id'] == item.get('practiceId')), None)
            frame = team_schedule_frame(snapshot, self.fonts, self.logo_assets, group, str(self.timezone),
                                 practice, item.get('groupId') == 'practices')
            render_ms = (perf_counter() - started) * 1000
            self._show_frame(frame)
            with self.lock:
                self.render_count += 1
                self.render_total_ms += render_ms
                self.render_max_ms = max(self.render_max_ms, render_ms)
            return frame
        if item is None:
            scene = "idle"
        else:
            scene = str(item.get("scene", "idle"))
        idle_message = "CONNECTING TO MLB DATA" if freshness == "loading" else None
        if freshness == "failed":
            if game:
                game = deepcopy(game)
                game["status"] = "unknown"
                game["statusDetail"] = "DATA OFFLINE"
                scene = "statusOnly"
            else:
                idle_message = "DATA OFFLINE - CHECK WIFI"
                scene = "idle"
        started = perf_counter()
        standing_logo_key = f"team-logo:{row['team']['id']}:16" if row else None
        away_logo_key = f"team-logo:{game['away']['id']}:16" if game else None
        home_logo_key = f"team-logo:{game['home']['id']}:16" if game else None
        frame = render_scene(
            self.definition,
            scene,
            self.fonts,
            game=game,
            standings=standings,
            standing_team=row,
            logo_asset_key=standing_logo_key,
            away_logo_asset_key=away_logo_key,
            home_logo_asset_key=home_logo_key,
            favorites=self.project["favorites"],
            idle_message=idle_message,
            elapsed_ms=elapsed_ms,
            now=now.isoformat(),
            overrides={**self.project.get("designOverrides", {}), **({'layoutPreset': self.controller_settings.draft['layoutPreset']} if self.controller_settings.active else {})},
            data_freshness=freshness,
            data_error=self.last_error,
            assets=self.logo_assets,
            transport_held=transport_held,
        )
        render_ms = (perf_counter() - started) * 1000
        self._show_frame(frame)
        with self.lock:
            self.render_count += 1
            self.render_total_ms += render_ms
            self.render_max_ms = max(self.render_max_ms, render_ms)
        return frame

    def _get_local_commit(self) -> str:
        if self._cached_commit:
            return self._cached_commit
        repo = self._find_git_repo()
        if not repo:
            return "unknown"
        try:
            res = subprocess.run(
                ["git", "-c", "safe.directory=*", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=3,
                check=True,
            )
            self._cached_commit = res.stdout.strip()
            return self._cached_commit
        except Exception:
            return "unknown"

    def _web_get_screen_png(self) -> bytes:
        with self.lock:
            if self.last_frame_png is not None:
                return self.last_frame_png
            if self.last_frame is not None:
                self.last_frame_png = encode_rgba_png(self.last_frame.width, self.last_frame.height, self.last_frame.data)
                return self.last_frame_png
        logical = self.profile["logical"]
        w, h = int(logical["width"]), int(logical["height"])
        return encode_rgba_png(w, h, bytes(w * h * 4))

    def status(self) -> dict[str, Any]:
        with self.lock:
            history_status = self._web_get_history()
            current = self.transport.current
            average = self.render_total_ms / self.render_count if self.render_count else 0
            game, standings, row = self._current_records()
            active_date = self._active_date(datetime.now(self.timezone))
            display_info: dict[str, Any] = {
                "activeDate": active_date,
                "isReveal": self._reveal_active,
                "isFireworks": self._fireworks_deadline is not None,
                "scene": "reveal" if self._reveal_active else ("fireworks" if self._fireworks_deadline else (current.get("scene") if current else "idle")),
            }
            if self._reveal_waiting:
                display_info['scene'] = 'revealWaiting'
            elif self.controller_settings.active:
                display_info['scene'] = 'settingsPreview' if self.controller_settings.preview else 'settings'
            elif self.home_active and not self._reveal_active and self._fireworks_deadline is None:
                display_info['scene'] = 'home'
            if self.arcade.active:
                display_info["scene"] = "arcade-menu" if self.arcade.menu else "arcade"
            if game and not self.arcade.active:
                start_local = str(game.get("startTimeLocal") or "")
                time_str = ""
                date_str = ""
                if "T" in start_local:
                    try:
                        dt = datetime.fromisoformat(start_local)
                        time_str = dt.strftime("%-I:%M %p")
                        is_today = dt.date().isoformat() == active_date
                        date_str = ("Today (" + dt.strftime("%a, %b %-d") + ")") if is_today else dt.strftime("%a, %b %-d")
                    except Exception:
                        pass
                display_info["game"] = {
                    "gameId": game.get("gameId"),
                    "status": game.get("status"),
                    "statusDetail": game.get("statusDetail"),
                    "isFinal": game.get("status") == "final",
                    "away": game.get("away"),
                    "home": game.get("home"),
                    "startTime": time_str,
                    "gameDate": date_str,
                    "venue": game.get("venue"),
                }
            if standings and row and not self.arcade.active:
                display_info["standings"] = {
                    "division": (standings.get("division") or {}).get("name"),
                    "team": (row.get("team") or {}).get("name"),
                    "rank": row.get("rank"),
                    "record": f"{row.get('wins')}-{row.get('losses')}",
                }

            if current and current.get('kind') in ('nfl', 'nba', 'nhl') and not self.arcade.active and not self.controller_settings.active:
                g = next((v for v in (self._nfl_games() if current['kind']=='nfl' else self._league_games(current['kind'])) if v['id'] == current['gameId']), None)
                if g:
                    try: start = datetime.fromisoformat(g['date'].replace('Z','+00:00')).astimezone(self.timezone) if g.get('date') else None
                    except (TypeError,ValueError): start = None
                    display_info['game'] = dict(gameId=g['id'],status='final' if g['completed'] else 'in_progress' if g['state']=='in' else 'scheduled', statusDetail=g['status'],isFinal=g['completed'],away=g['away'],home=g['home'],venue=g.get('venue', ''),gameDate=start.strftime('%a, %b %-d') if start else '',startTime=start.strftime('%-I:%M %p') if start else '')
                    display_info.pop('standings',None)

            if not self._reveal_active and not self._reveal_waiting and not self.controller_settings.active and self._fireworks_deadline is None:
                if self.history.active:
                    display_info = dict(scene='history',history=history_status)
                elif self.scoring_alerts.active:
                    display_info = dict(scene='scoringAlert',alert=self.scoring_alerts.active)
            return {
                "history": history_status,
                "scoringAlerts": {"active":self.scoring_alerts.active,"error":self.scoring_alerts.error},
                "schemaVersion": "1.0",
                "status": "ok" if self.last_error is None else "degraded",
                "version": __version__,
                "uptimeSec": round(monotonic() - self.started, 1),
                "project": {"id": self.project["id"], "version": self.project["meta"]["version"]},
                "profileId": self.profile["id"],
                "output": self.output.kind,
                "currentGameId": current.get("gameId") if current else None,
                "gameCount": sum(i.get("kind") in ("game","nfl","nba","nhl") for i in self.transport.items),
                "freshness": self._freshness(),
                "fetchedUtc": self.fetched_utc,
                "lastError": self.last_error,
                "logoAssets": len(self.logo_assets),
                "transport": self.transport.status(),
                "currentCommit": self._get_local_commit(),
                "installedBuild": self.installed_identity,
                "display": display_info,
                "fireworks": {
                    "active": self._fireworks_deadline is not None,
                    "progress": self._fireworks_progress,
                },
                "controllerSettings": {"active": self.controller_settings.active, "preview": self.controller_settings.preview, "page": self.controller_settings.page},
                "sports": sports_settings(self.project),
                "leagueFeeds": {k: dict(enabled=sports_settings(self.project)[k]['enabled'], games=len(self._league_games(k)),
                    freshness=self._league_freshness(k), **{n:v for n,v in self.league_snapshots.get(k,{}).get('source',{}).items() if n!='freshness'}) for k in ('nba','nhl')},
                "nfl": {"enabled":self._web_get_config()['nfl']['enabled'], "games":len(self._nfl_games()), "source":"ESPN", "freshness":self._nfl_freshness(), "fetchedUtc":(self.nfl_snapshot or {}).get('fetchedUtc'), "error":(self.nfl_snapshot or {}).get('error')},
                "temporaryWake": {"active": monotonic() < self._wake_deadline, "remainingSec": max(0, round(self._wake_deadline - monotonic()))},
                "reveal": {
                    "active": self._reveal_active,
                    "waitingForController": self._reveal_waiting,
                    "deferredForQuietHours": self._reveal_deferred_for_quiet_hours,
                },
                "recap": {
                    "windowFetchedUtc": (self._recap_window or {}).get("fetchedUtc"),
                    "windowGames": len((self._recap_window or {}).get("games", [])),
                    "lastError": self._recap_error,
                },
                "buttons": {
                    "available": self.buttons.available,
                    "error": self.buttons.error,
                    "nextPresses": self.next_presses,
                    "holdPresses": self.hold_presses,
                },
                "bluetoothRemote": self.bluetooth_remote.status(),
                "arcade": self.arcade.status(),
                "render": {
                    "frames": self.render_count,
                    "averageMs": round(average, 3),
                    "maxMs": round(self.render_max_ms, 3),
                    "lastFrameSha256": self.last_frame_hash,
                },
            }

    async def _play_reveal_sequence(
        self,
        *,
        custom_lines: list[str] | None = None,
        fireworks: bool = True,
        line_dwell: float | None = None,
        fireworks_dwell: float | None = None,
    ) -> None:
        """Staged text (from project.reveal or custom announcement) followed by
        optional fireworks celebration. Viewer controls are ignored until completion."""
        with self.lock:
            self.arcade.exit()
            self._reveal_active = True
        reveal_settings = self.project.get("reveal") or {}
        lines = custom_lines if custom_lines is not None else list(reveal_settings.get("lines") or ["WELCOME", "HAPPY CELEBRATION"])
        line_dwell_sec = float(line_dwell if line_dwell is not None else reveal_settings.get("lineDwellSec", 4))
        fireworks_dwell_sec = float(fireworks_dwell if fireworks_dwell is not None else reveal_settings.get("fireworksDwellSec", 10))
        logical = self.profile["logical"]
        width, height = int(logical["width"]), int(logical["height"])
        font = self.fonts.get("5x7") or next(iter(self.fonts.values()))
        # Honor configured brightness/quiet hours during the reveal exactly
        # as normal rendering does (see _render's identical precedence).
        clock = {"localTime": datetime.now(self.timezone).strftime("%H:%M")}
        quiet = is_quiet_time(self.project.get("quietHours"), clock)
        project_brightness = self.project.get("brightness") or {}
        normal_brightness = project_brightness.get("normal", self.config.get("brightness", 35))
        dim_brightness = project_brightness.get("dim", self.config.get("dimBrightness", 10))
        self.output.set_brightness(int(dim_brightness) if quiet else int(normal_brightness))
        self._reveal_active = True
        try:
            for line in lines:
                frame = create_reveal_text_frame(width, height, [line], font)
                self._show_frame(frame)
                deadline = monotonic() + line_dwell_sec
                while monotonic() < deadline:
                    await asyncio.sleep(0.05)
            if fireworks and fireworks_dwell_sec > 0:
                started = monotonic()
                while monotonic() - started < fireworks_dwell_sec:
                    elapsed_ms = (monotonic() - started) * 1000
                    frame = create_fireworks_frame(width, height, elapsed_ms)
                    self._show_frame(frame)
                    await asyncio.sleep(0.05)
        finally:
            self._reveal_active = False

    # --- Web control (StatusServer actions) ---------------------------------
    # Called from the StatusServer's HTTP handler thread, never the asyncio
    # loop thread, so state-file access is locked and any actual playback is
    # handed to the running loop via run_coroutine_threadsafe rather than
    # awaited here (an HTTP response must not block for the reveal's full
    # duration).

    def _web_reveal_status(self) -> dict[str, Any]:
        with self.lock:
            return {**load_reveal(self.reveal_path), 'waitingForController': self._reveal_waiting}

    def _web_wait_reveal(self) -> dict[str, Any]:
        with self.lock:
            if self._reveal_active:
                raise RuntimeError('reveal is already playing')
            updated = {**load_reveal(self.reveal_path), 'state': 'armed', 'trigger': 'controller'}
            save_reveal(self.reveal_path, updated)
            self._reveal_waiting = True
            self.controller_settings.close()
            self.arcade.exit()
            self._fireworks_deadline = None
            return self._web_reveal_status()

    def _web_arm_reveal(self) -> dict[str, Any]:
        with self.lock:
            updated = arm(load_reveal(self.reveal_path))
            updated.pop('trigger', None)
            self._reveal_waiting = False
            save_reveal(self.reveal_path, updated)
            return updated

    def _web_disarm_reveal(self) -> dict[str, Any]:
        with self.lock:
            updated = disarm(load_reveal(self.reveal_path))
            self._reveal_waiting = False
            save_reveal(self.reveal_path, updated)
            return updated

    def _web_play_reveal(self, *, consume_state: bool) -> dict[str, Any]:
        with self.lock:
            if self._reveal_active:
                raise RuntimeError("reveal is already playing")
            if self._loop is None:
                raise RuntimeError("device is still starting up")
            started = force_start(load_reveal(self.reveal_path)) if consume_state else None
            if started is not None:
                save_reveal(self.reveal_path, started)
            was_waiting = self._reveal_waiting
            self._reveal_waiting = False
            self._reveal_active = True
            self.controller_settings.close()
            self.arcade.exit()

        async def task() -> None:
            try:
                await self._play_reveal_sequence()
                if started is not None:
                    with self.lock:
                        save_reveal(self.reveal_path, complete_playback(started))
            except Exception:
                LOGGER.exception("reveal playback failed")
            finally:
                with self.lock:
                    self._reveal_active = False
                    if not consume_state:
                        self._reveal_waiting = was_waiting

        asyncio.run_coroutine_threadsafe(task(), self._loop)
        return {"triggered": True, "consumesState": consume_state}

    def _web_get_config(self) -> dict[str, Any]:
        with self.lock:
            qh = self.project.get("quietHours") or {}
            br = self.project.get("brightness") or {}
            favs = list(self.project.get("favorites") or [])
            return {
                "quietHours": {
                    "enabled": bool(qh.get("enabled", True)),
                    "start": str(qh.get("start", "21:00")),
                    "end": str(qh.get("end", "06:00")),
                    "behavior": str(qh.get("behavior", "dim")),
                },
                "brightness": {
                    "normal": int(br.get("normal", self.config.get("brightness", 35))),
                    "dim": int(br.get("dim", self.config.get("dimBrightness", 10))),
                },
                "favorites": favs,
                "nfl": {**validate_settings(self.project.get("nfl", {})), 'enabled': sports_settings(self.project)['nfl']['enabled']},
                "sports": sports_settings(self.project),
                "sportTeams": TEAM_CATALOG,
                "wakeDurationSec": int(self.project.get('controllerPreferences', {}).get('wakeDurationSec', 60)),
                "layoutPreset": self.project.get("designOverrides", {}).get("layoutPreset", "classic"),
                "allTeams": [
                    "ARI", "ATH", "ATL", "BAL", "BOS", "CHC", "CWS", "CIN", "CLE", "COL",
                    "DET", "HOU", "KC", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", "NYY",
                    "PHI", "PIT", "SD", "SEA", "SF", "STL", "TB", "TEX", "TOR", "WSH",
                ],
                "version": self.project.get("meta", {}).get("version", 1),
            }

    def _web_update_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Invalid configuration payload; expected JSON object")
        allowed = {"expectedVersion", "quietHours", "brightness", "favorites", "layoutPreset", "wakeDurationSec", "nfl", "sports"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"Unsupported configuration fields: {', '.join(sorted(unknown))}")
        expected_version = payload.get("expectedVersion")
        if type(expected_version) is not int or expected_version < 1:
            raise ValueError("expectedVersion must be the positive version returned by GET /api/config")

        nfl_settings = validate_settings(payload['nfl']) if 'nfl' in payload else None
        sport_changes = validate_sports(payload['sports']) if 'sports' in payload else None
        wake_seconds = payload.get('wakeDurationSec')
        if wake_seconds is not None and (type(wake_seconds) is not int or not 10 <= wake_seconds <= 600):
            raise ValueError('Wake duration must be an integer between 10 and 600 seconds')
        layout = payload.get("layoutPreset")
        if layout is not None and layout not in ("classic", "broadcastRows", "broadcastLogos"):
            raise ValueError("Choose a supported scoreboard layout")

        qh_in = payload.get("quietHours")
        if qh_in is not None:
            if not isinstance(qh_in, dict):
                raise ValueError("quietHours must be an object")
            start = qh_in.get("start", "21:00")
            end = qh_in.get("end", "06:00")
            behavior = qh_in.get("behavior", "dim")
            enabled = qh_in.get("enabled", True)
            if not isinstance(start, str) or not isinstance(end, str):
                raise ValueError("quietHours times must be strings in HH:MM format")
            def valid_time(value: str) -> bool:
                return len(value) == 5 and value[2] == ":" and value[:2].isdigit() and value[3:].isdigit() and 0 <= int(value[:2]) <= 23 and 0 <= int(value[3:]) <= 59
            if not valid_time(start):
                raise ValueError("quietHours start must be a real HH:MM time")
            if not valid_time(end):
                raise ValueError("quietHours end must be a real HH:MM time")
            if type(enabled) is not bool:
                raise ValueError("quietHours enabled must be a boolean")
            if behavior not in ("dim", "sleep"):
                raise ValueError("quietHours behavior must be 'dim' or 'sleep'")

        br_in = payload.get("brightness")
        if br_in is not None:
            if not isinstance(br_in, dict):
                raise ValueError("brightness must be an object")
            normal = br_in.get("normal", 35)
            dim = br_in.get("dim", 10)
            if type(normal) is not int or type(dim) is not int:
                raise ValueError("Brightness values must be integers")
            if not (1 <= normal <= 100):
                raise ValueError("Normal brightness must be between 1 and 100")
            if not (1 <= dim <= 100):
                raise ValueError("Dim brightness must be between 1 and 100")

        favs_in = payload.get("favorites")
        if favs_in is not None:
            if not isinstance(favs_in, list) or not all(isinstance(t, str) for t in favs_in):
                raise ValueError("favorites must be a list of team abbreviations")
            cleaned = [team.strip().upper() for team in favs_in]
            allowed_teams = set(self._web_get_config()["allTeams"])
            if not all(team in allowed_teams for team in cleaned):
                raise ValueError("favorites contains an unsupported team abbreviation")
            if len(cleaned) != len(set(cleaned)):
                raise ValueError("favorites must not contain duplicates")

        with self.lock:
            current_version = int(self.project.get("meta", {}).get("version", 1))
            if expected_version != current_version:
                error = RuntimeError("Configuration has changed; reload before saving")
                setattr(error, "current_config", self._web_get_config())
                raise error
            candidate = deepcopy(self.project)
            if qh_in is not None:
                candidate["quietHours"] = {"enabled": qh_in.get("enabled", True), "start": qh_in.get("start", "21:00"), "end": qh_in.get("end", "06:00"), "behavior": qh_in.get("behavior", "dim")}

            if br_in is not None:
                candidate["brightness"] = {"normal": br_in.get("normal", 35), "dim": br_in.get("dim", 10)}

            if favs_in is not None:
                candidate["favorites"] = [t.strip().upper() for t in favs_in]

            if layout is not None:
                candidate.setdefault("designOverrides", {})["layoutPreset"] = layout

            if wake_seconds is not None:
                candidate.setdefault('controllerPreferences', {})['wakeDurationSec'] = wake_seconds

            if nfl_settings is not None:
                previous_nfl = validate_settings(candidate.get('nfl', {}))
                candidate['nfl'] = nfl_settings
                if 'sports' in candidate:
                    policy = candidate['sports'].setdefault('nfl', {'enabled': False, 'teams': None})
                    policy['enabled'] = nfl_settings['enabled']
                    if (previous_nfl['favoritesOnly'] != nfl_settings['favoritesOnly'] or
                            nfl_settings['favoritesOnly'] and previous_nfl['favorites'] != nfl_settings['favorites']):
                        policy['teams'] = list(nfl_settings['favorites']) if nfl_settings['favoritesOnly'] else None
            if sport_changes is not None:
                candidate['sports'] = {**sports_settings(candidate), **sport_changes}
                candidate['nfl'] = {**validate_settings(candidate.get('nfl', {})), 'enabled': candidate['sports']['nfl']['enabled']}
                if 'nfl' in sport_changes: candidate['nfl']['favoritesOnly'] = False

            meta = candidate.setdefault("meta", {})
            meta["version"] = current_version + 1
            meta["modified"] = datetime.now(timezone.utc).isoformat()

            # Persist to disk atomically
            project_file = self.root / "config" / "project.json"
            project_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = project_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(candidate, indent=2), encoding="utf-8")
            temporary.replace(project_file)
            self.project = candidate

            # Recalculate brightness immediately
            now = datetime.now(self.timezone)
            clock = {"localTime": now.strftime("%H:%M")}
            quiet = is_quiet_time(self.project.get("quietHours"), clock)
            br = self.project.get("brightness", {})
            norm_b = int(br.get("normal", self.config.get("brightness", 35)))
            dim_b = int(br.get("dim", self.config.get("dimBrightness", 10)))
            self.output.set_brightness(dim_b if quiet else norm_b)
            self._refresh_playlist(now)
            if nfl_settings is not None: self.next_nfl_fetch = 0
            if sport_changes is not None:
                self.next_fetch = self.next_recap_fetch = self.next_nfl_fetch = 0
                self.next_league_fetch = {'nba': 0, 'nhl': 0}
                self.history.cancel()

        return {"ok": True, "config": self._web_get_config()}

    def _web_control_next(self) -> dict[str, Any]:
        self.command_next()
        return {"ok": True, "action": "next", "presses": self.next_presses}

    def _web_control_hold(self) -> dict[str, Any]:
        self.command_hold()
        return {"ok": True, "action": "hold", "held": self.transport.held}

    def _find_git_repo(self) -> Path | None:
        # This pointer is created by the root-run updater. Do not use a path
        # under config/: dashboard saves must never select privileged code.
        configured_path_file = Path("/etc/pixelboard/source-repo")
        try:
            stat = configured_path_file.stat()
            if stat.st_uid != 0 or stat.st_mode & 0o022:
                LOGGER.error("refusing unsafe update source pointer: %s", configured_path_file)
                return None
            configured = Path(configured_path_file.read_text(encoding="utf-8").strip()).resolve(strict=True)
            if configured.is_absolute() and (configured / ".git").is_dir():
                return configured
        except (OSError, PermissionError):
            return None
        return None

    def _web_check_update(self) -> dict[str, Any]:
        repo = self._find_git_repo()
        if not repo:
            return {
                "available": False,
                "error": "Git repository was not found on this device.",
                "currentCommit": "unknown",
                "remoteCommit": "unknown",
                "commits": [],
            }
        env_dict = {
            **dict(os.environ),
            "GIT_TERMINAL_PROMPT": "0",
        }
        extra_kwargs: dict[str, Any] = {}
        extra_git_args: list[str] = ["-c", "safe.directory=*"]

        try:
            import pwd
            stat_info = repo.stat()
            pw = pwd.getpwuid(stat_info.st_uid)
            if pw.pw_dir:
                env_dict["HOME"] = pw.pw_dir
                env_dict["USER"] = pw.pw_name
                # If the owner has a .git-credentials file, explicitly point Git to it
                user_creds = Path(pw.pw_dir) / ".git-credentials"
                if user_creds.is_file():
                    extra_git_args.extend(["-c", f"credential.helper=store --file={user_creds}"])
            # If running as root, switch directly to the repo owner via POSIX setuid/setgid (avoids sudo tty/PAM issues)
            if os.geteuid() == 0 and pw.pw_uid != 0:
                extra_kwargs["user"] = pw.pw_uid
                extra_kwargs["group"] = pw.pw_gid
        except Exception:
            pass

        def run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
            cmd = ["git", *extra_git_args, "-C", str(repo), *args]
            try:
                return subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=10, env=env_dict, **extra_kwargs)
            except (PermissionError, subprocess.SubprocessError):
                if extra_kwargs:
                    # Fallback without user switching if OS disallowed it
                    return subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=10, env=env_dict)
                raise

        try:
            # Use git ls-remote first: it is completely read-only and never touches .git/FETCH_HEAD
            ls_remote = run_git(["ls-remote", "origin", "main"])
            remote_full = ls_remote.stdout.split()[0] if ls_remote.stdout.strip() else ""
            remote = remote_full[:7] if remote_full else "unknown"
            local = run_git(["rev-parse", "--short", "HEAD"]).stdout.strip()
            self._cached_commit = local

            if local and remote and remote != "unknown" and local != remote:
                # Different hashes do not imply a newer release. A tested branch
                # may already contain main; never advertise a downgrade as an update.
                try:
                    run_git(["merge-base", "--is-ancestor", remote_full, local])
                except subprocess.CalledProcessError:
                    pass  # New remote commit may not be present locally yet.
                else:
                    return {
                        "available": False, "currentCommit": local,
                        "remoteCommit": remote, "commits": [],
                        "message": "Test release installed; it already includes the current main release. No newer main update is available.",
                    }
                commits = [f"Commit {remote}"]
                try:
                    # Read only: do not write FETCH_HEAD during a dashboard check.
                    log_out = run_git(["log", "-n", "10", "--oneline", f"{local}..{remote_full}"]).stdout.strip()
                    parsed_commits = [c.strip() for c in log_out.split("\n") if c.strip()]
                    if parsed_commits:
                        commits = parsed_commits
                except Exception:
                    pass

                return {
                    "available": True,
                    "currentCommit": local,
                    "remoteCommit": remote,
                    "commits": commits,
                }
            return {
                "available": False,
                "currentCommit": local,
                "remoteCommit": remote if remote != "unknown" else local,
                "commits": [],
            }
        except subprocess.CalledProcessError as err:
            details = (err.stderr or "").strip() or (err.stdout or "").strip() or f"exit status {err.returncode}"
            LOGGER.error("git check failed: %s", details)
            if "could not read Username" in details or "terminal prompts disabled" in details:
                friendly_error = (
                    "GitHub credentials not saved on device. "
                    "Run 'git config --global credential.helper store && git fetch origin main' in the Pi terminal to save credentials."
                )
            else:
                friendly_error = f"git: {details}"
            return {
                "available": False,
                "error": friendly_error,
                "currentCommit": "unknown",
                "remoteCommit": "unknown",
                "commits": [],
            }
        except Exception as err:
            LOGGER.exception("git update check failed")
            return {
                "available": False,
                "error": str(err),
                "currentCommit": "unknown",
                "remoteCommit": "unknown",
                "commits": [],
            }

    def _web_apply_update(self) -> dict[str, Any]:
        repo = self._find_git_repo()
        if not repo:
            raise RuntimeError("Git repository not found on this device.")

        script = repo / "scripts" / "update-device.sh"
        if not script.is_file():
            script = self.root / "scripts" / "update-device.sh"
        if not script.is_file():
            raise RuntimeError("Update script (scripts/update-device.sh) not found.")

        # A child of scoreboard.service inherits ProtectSystem=full and is
        # killed when the installer restarts that service. Run the authorized
        # updater as its own transient systemd unit instead. Always replace
        # the stable installation link, never the resolved active release.
        subprocess.run([
            "systemd-run", "--unit=pixelboard-update", "--collect",
            "--property=Type=exec", "bash", str(script), "/opt/pixelboard",
        ], check=True, capture_output=True, text=True, timeout=10)
        return {"ok": True, "message": "Update initiated. Scoreboard will restart after verification."}

    def _web_play_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("Invalid message payload")

        raw_lines = payload.get("lines") or []
        if isinstance(raw_lines, str):
            lines = [l.strip() for l in raw_lines.split("\n") if l.strip()]
        elif isinstance(raw_lines, list):
            lines = [str(l).strip() for l in raw_lines if str(l).strip()]
        else:
            lines = []
        if not lines:
            lines = ["HAPPY CELEBRATION!"]

        include_fireworks = bool(payload.get("fireworks", True))
        dwell_sec = max(1.0, float(payload.get("dwellSec", 4)))
        arm_for_boot = bool(payload.get("armForBoot", False))

        if payload.get('waitForController', False):
            if not 1 <= len(lines) <= 4 or any(len(line) > 60 for line in lines) or not 1 <= dwell_sec <= 30:
                raise ValueError('Use 1-4 message lines up to 60 characters and 1-30 seconds per line')
            with self.lock:
                if self._reveal_active:
                    raise RuntimeError('A celebration or message is already playing')
                candidate = deepcopy(self.project)
                candidate['reveal'] = {'lines': lines, 'lineDwellSec': dwell_sec, 'fireworksDwellSec': 10 if include_fireworks else 0}
                candidate['meta']['version'] += 1
                candidate['meta']['modified'] = datetime.now(timezone.utc).isoformat()
                project_file = self.root / 'config' / 'project.json'
                temporary = project_file.with_suffix('.tmp')
                temporary.write_text(json.dumps(candidate, indent=2), encoding='utf-8')
                temporary.replace(project_file)
                self.project = candidate
                self._web_wait_reveal()
            return {'ok': True, 'waitingForController': True, 'message': 'Reveal loaded. Prompt displayed until any controller button is pressed.'}

        if arm_for_boot:
            with self.lock:
                self.project.setdefault("reveal", {})
                self.project["reveal"]["lines"] = lines
                self.project["reveal"]["lineDwellSec"] = dwell_sec
                self.project["reveal"]["fireworksDwellSec"] = 10 if include_fireworks else 0
                project_file = self.root / "config" / "project.json"
                temporary = project_file.with_suffix(".tmp")
                temporary.write_text(json.dumps(self.project, indent=2), encoding="utf-8")
                temporary.replace(project_file)
                updated = arm(load_reveal(self.reveal_path))
                updated.pop('trigger', None)
                self._reveal_waiting = False
                save_reveal(self.reveal_path, updated)
            return {"ok": True, "armed": True, "message": f"Message saved & armed for next boot ({len(lines)} lines)"}

        with self.lock:
            if self._reveal_active or self._reveal_waiting:
                raise RuntimeError("Cancel the waiting reveal or wait until the celebration finishes")
            if self._loop is None:
                raise RuntimeError("Scoreboard device is still starting up")
            self._reveal_active = True
            self.controller_settings.close()
            self.arcade.exit()

        async def task() -> None:
            try:
                await self._play_reveal_sequence(
                    custom_lines=lines,
                    fireworks=include_fireworks,
                    line_dwell=dwell_sec,
                    fireworks_dwell=10 if include_fireworks else 0,
                )
            except Exception:
                LOGGER.exception("custom message playback failed")
            finally:
                self._reveal_active = False

        asyncio.run_coroutine_threadsafe(task(), self._loop)
        return {"ok": True, "playing": True, "message": f"Broadcasting message to scoreboard ({len(lines)} lines)"}

    async def run(self) -> None:

        self._loop = asyncio.get_running_loop()
        reveal = load_reveal(self.reveal_path)
        clock = {"localTime": datetime.now(self.timezone).strftime("%H:%M")}
        quiet_sleep = (
            is_quiet_time(self.project.get("quietHours"), clock)
            and self.project["quietHours"].get("behavior") == "sleep"
        )
        if should_autoplay_on_boot(reveal) and quiet_sleep:
            # Quiet hours win: a boot during sleep quiet hours leaves the
            # reveal armed rather than surprising a dark, sleeping room —
            # it autoplays on the next boot that isn't during sleep hours.
            # Not silent: surfaced in status() so an operator monitoring the
            # device can see the reveal is armed-but-deferred, not missing.
            self._reveal_deferred_for_quiet_hours = True
            LOGGER.warning("reveal armed but deferred: quiet hours (sleep) at boot")
        elif should_autoplay_on_boot(reveal):
            # Mark started durably BEFORE the first frame renders — a power
            # loss during playback must leave "started" on disk, not replay
            # endlessly on the next boot.
            started_reveal = begin_playback(reveal)
            save_reveal(self.reveal_path, started_reveal)
            await self._play_reveal_sequence()
            save_reveal(self.reveal_path, complete_playback(started_reveal))

        self.status_server.start()
        fetch_task: asyncio.Task[None] | None = asyncio.create_task(self._fetch())
        recap_task: asyncio.Task[None] | None = asyncio.create_task(self._fetch_recap_window())
        team_task = asyncio.create_task(self._fetch_team())
        nfl_task = asyncio.create_task(self._fetch_nfl())
        league_tasks = {k: asyncio.create_task(self._fetch_league(k)) for k in ('nba','nhl')}
        history_task = None
        scoring_task = None
        frame_interval = 1 / max(1, min(30, int(self.config.get("frameRate", 20))))
        try:
            while not self.stop_event.is_set():
                if fetch_task and fetch_task.done():
                    await fetch_task
                    fetch_task = None
                if fetch_task is None and monotonic() >= self.next_fetch:
                    fetch_task = asyncio.create_task(self._fetch())
                if recap_task and recap_task.done():
                    await recap_task
                    recap_task = None
                if recap_task is None and monotonic() >= self.next_recap_fetch:
                    recap_task = asyncio.create_task(self._fetch_recap_window())
                if team_task and team_task.done():
                    await team_task
                    team_task = None
                if team_task is None and monotonic() >= self.next_team_fetch:
                    team_task = asyncio.create_task(self._fetch_team())
                if nfl_task and nfl_task.done():
                    await nfl_task
                    nfl_task = None
                if nfl_task is None and monotonic() >= self.next_nfl_fetch:
                    nfl_task = asyncio.create_task(self._fetch_nfl())
                for league in ('nba', 'nhl'):
                    task = league_tasks.get(league)
                    if task and task.done():
                        await task
                        league_tasks[league] = None
                    if league_tasks[league] is None and monotonic() >= self.next_league_fetch[league]:
                        league_tasks[league] = asyncio.create_task(self._fetch_league(league))
                if history_task and history_task.done():
                    await history_task
                    history_task = None
                if scoring_task and scoring_task.done():
                    await scoring_task
                    scoring_task = None
                with self.lock:
                    self.history.tick()
                    visible = self._visible_scoring_game()
                    self.scoring_alerts.sync(visible[0] if visible else None)
                    if history_task is None and self.history.active and monotonic() >= self.history.next_fetch:
                        history_task = asyncio.create_task(self._fetch_history())
                    if scoring_task is None and visible and not self.scoring_alerts.finalized and monotonic() >= self.scoring_alerts.next_fetch:
                        scoring_task = asyncio.create_task(self._fetch_scoring())
                self._render(datetime.now(self.timezone))
                await asyncio.sleep(frame_interval)
        finally:
            for pending in (fetch_task, recap_task, team_task, nfl_task, history_task, scoring_task, *league_tasks.values()):
                if pending:
                    pending.cancel()
                    await asyncio.gather(pending, return_exceptions=True)
            if self.adapter:
                await self.adapter.close()
            self.status_server.close()
            self.bluetooth_remote.close()
            self.buttons.close()
            self.output.close()

    def stop(self) -> None:
        self.stop_event.set()


async def run_device(root: Path, output_kind: str | None = None) -> None:
    runtime = DeviceRuntime(root, output_kind=output_kind)
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, runtime.stop)
        except NotImplementedError:
            pass
    await runtime.run()


async def rehearse_reveal(root: Path, output_kind: str | None = None) -> None:
    """Plays the reveal sequence without ever reading or writing
    state/reveal.json — rehearsal must not consume the armed reveal."""
    runtime = DeviceRuntime(root, output_kind=output_kind)
    try:
        await runtime._play_reveal_sequence()
    finally:
        runtime.bluetooth_remote.close()
        runtime.buttons.close()
        runtime.output.close()
        runtime.status_server.server.server_close()  # never started; .close() would hang waiting on shutdown()
