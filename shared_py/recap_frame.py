from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Mapping

from shared_py.bdf import BdfFont
from shared_py.reveal_frame import create_reveal_text_frame
from shared_py.renderer import PixelBuffer

# Fixed, locale-independent names so the rendered card is byte-deterministic
# regardless of the device's locale.
_WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
_MONTHS = (
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)


def _parse(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _game_moment(game: Mapping[str, Any]) -> datetime | None:
    """Prefer the provider's local ISO timestamp; fall back to UTC. Used only
    for the human date/time label, so a naive vs aware mismatch never matters
    here (we format, we don't compare)."""
    return _parse(game.get("startTimeLocal")) or _parse(game.get("startTimeUtc"))


def _short_date(moment: datetime | None) -> str:
    if moment is None:
        return "DATE TBA"
    return f"{_WEEKDAYS[moment.weekday()]} {_MONTHS[moment.month - 1]} {moment.day}"


def _wall_time(game: Mapping[str, Any]) -> str:
    """HH:MM AM/PM from the provider's local ISO string. Mirrors the "TIME
    TBA" wording the scene renderer already uses for an unknown start."""
    raw = game.get("startTimeLocal") or game.get("startTimeUtc")
    match = re.search(r"T(\d{2}):(\d{2})", raw) if isinstance(raw, str) else None
    if not match:
        return "TIME TBA"
    hour, minute = int(match.group(1)), int(match.group(2))
    return f"{hour % 12 or 12}:{minute:02} {'PM' if hour >= 12 else 'AM'}"


def _side(game: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = game.get(key)
    return value if isinstance(value, Mapping) else {}


def _score(value: Any) -> str:
    return str(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else "-"


def _result_line(favorite: str, game: Mapping[str, Any]) -> str:
    home, away = _side(game, "home"), _side(game, "away")
    home_abbr, away_abbr = str(home.get("abbr") or "HOME"), str(away.get("abbr") or "AWAY")
    home_score, away_score = home.get("score"), away.get("score")
    fav_is_home = home_abbr == favorite
    fav_score = home_score if fav_is_home else away_score
    opp_score = away_score if fav_is_home else home_score
    opp_abbr = away_abbr if fav_is_home else home_abbr
    verb = "TIED"
    if isinstance(fav_score, (int, float)) and isinstance(opp_score, (int, float)):
        verb = "BEAT" if fav_score > opp_score else "LOST TO" if fav_score < opp_score else "TIED"
    versus = "VS" if fav_is_home else "AT"
    game_tag = f" G{game.get('gameNumber')}" if game.get("doubleheader") and game.get("gameNumber") else ""
    return f"{verb} {opp_abbr} {_score(fav_score)}-{_score(opp_score)} ({versus}){game_tag}"


def _next_line(favorite: str, game: Mapping[str, Any]) -> str:
    home, away = _side(game, "home"), _side(game, "away")
    home_abbr, away_abbr = str(home.get("abbr") or "HOME"), str(away.get("abbr") or "AWAY")
    fav_is_home = home_abbr == favorite
    versus = "VS" if fav_is_home else "AT"
    opp_abbr = away_abbr if fav_is_home else home_abbr
    game_tag = f" G{game.get('gameNumber')}" if game.get("doubleheader") and game.get("gameNumber") else ""
    return f"{versus} {opp_abbr}{game_tag}  {_wall_time(game)}"


def recap_lines(recap: Mapping[str, Any], now: datetime) -> list[str]:
    """Staged text for one favorite's morning card: the most recent completed
    result (with its real date), then the next scheduled matchup and local
    start time. Honest fallbacks when either is missing — an unknown future
    game is never implied to be imminent."""
    favorite = str(recap.get("favorite") or "").upper()
    lines = [f"{favorite} RECAP" if favorite else "RECAP"]

    recent = recap.get("recentResult")
    if isinstance(recent, Mapping):
        lines.append(_result_line(favorite, recent))
        lines.append(_short_date(_game_moment(recent)))
    else:
        lines.append("NO RECENT RESULT")

    upcoming = recap.get("nextGame")
    if isinstance(upcoming, Mapping):
        lines.append(f"NEXT {_short_date(_game_moment(upcoming))}")
        lines.append(_next_line(favorite, upcoming))
    else:
        days = recap.get("nextGameSearchDays")
        numeric = days if isinstance(days, (int, float)) and not isinstance(days, bool) else None
        if numeric is not None and numeric <= 0:
            # The cached schedule window no longer reaches past today, so we
            # genuinely have not checked any future days — say that rather
            # than claim "no game in the next 0 days".
            lines.append("NEXT GAME: SCHEDULE STALE")
        else:
            span = f"{int(numeric)}" if numeric is not None else "?"
            lines.append(f"NO GAME IN NEXT {span} DAYS")
    return lines


def create_recap_frame(
    width: int,
    height: int,
    recap: Mapping[str, Any],
    font: BdfFont,
    now: datetime,
) -> PixelBuffer:
    """Renders one favorite's morning recap card. Pixel drawing is delegated
    to the shared staged-text frame (word-wrapped, centered) so this module
    adds no new pixel math to keep parity-checked."""
    return create_reveal_text_frame(width, height, recap_lines(recap, now), font)
