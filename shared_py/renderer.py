from __future__ import annotations

from functools import lru_cache

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from shared_py.bdf import BdfFont, glyph_for, measure_text, parse_bdf

Rgba = tuple[int, int, int, int]
WHITE: Rgba = (255, 255, 255, 255)
BLACK: Rgba = (0, 0, 0, 255)
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
SAFE_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
CONDITION = re.compile(
    r'^([A-Za-z_][A-Za-z0-9_.]*)\s*(==|!=|<=|>=|<|>)\s*'
    r'(null|true|false|-?[0-9]+(?:\.[0-9]+)?|"[^"]*"|\'[^\']*\')$'
)
FORBIDDEN = {"__proto__", "prototype", "constructor"}


@dataclass(frozen=True)
class Clip:
    x: int
    y: int
    width: int
    height: int


@lru_cache(maxsize=1024)
def _rgba_bytes(color):
    """Reuse encoded colors in the hot pixel loop; clamping stays identical."""
    return bytes(max(0, min(255, int(value))) for value in color)


class PixelBuffer:
    def __init__(self, width: int, height: int, background: Rgba = BLACK) -> None:
        self.width = max(1, min(4096, int(width)))
        self.height = max(1, min(4096, int(height)))
        self.data = bytearray(self.width * self.height * 4)
        self.clear(background)

    def clear(self, color: Rgba = BLACK) -> None:
        pixel = bytes(color)
        self.data[:] = pixel * (self.width * self.height)

    def set_pixel(self, x: int, y: int, color: Rgba, clip: Clip | None = None) -> None:
        x, y = int(x), int(y)
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return
        if clip and not (clip.x <= x < clip.x + clip.width and clip.y <= y < clip.y + clip.height):
            return
        offset = (y * self.width + x) * 4
        self.data[offset:offset + 4] = _rgba_bytes(tuple(color))

    def blend_pixel(self, x: int, y: int, color: Rgba, clip: Clip | None = None) -> None:
        alpha = color[3]
        if alpha <= 0:
            return
        if alpha >= 255:
            self.set_pixel(x, y, color, clip)
            return
        x, y = int(x), int(y)
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return
        if clip and not (clip.x <= x < clip.x + clip.width and clip.y <= y < clip.y + clip.height):
            return
        offset = (y * self.width + x) * 4
        ratio, inverse = alpha / 255, 1 - alpha / 255
        for index in range(3):
            self.data[offset + index] = round(color[index] * ratio + self.data[offset + index] * inverse)
        self.data[offset + 3] = 255

    def fill_rect(self, x: int, y: int, width: int, height: int, color: Rgba, clip: Clip | None = None) -> None:
        for py in range(int(y), int(y) + max(0, int(height))):
            for px in range(int(x), int(x) + max(0, int(width))):
                self.set_pixel(px, py, color, clip)

    def draw_line(self, x1: int, y1: int, x2: int, y2: int, color: Rgba, clip: Clip | None = None) -> None:
        x, y, end_x, end_y = int(x1), int(y1), int(x2), int(y2)
        delta_x, step_x = abs(end_x - x), 1 if x < end_x else -1
        delta_y, step_y = -abs(end_y - y), 1 if y < end_y else -1
        error = delta_x + delta_y
        for _ in range(min(32768, delta_x + abs(delta_y) + 2)):
            self.set_pixel(x, y, color, clip)
            if x == end_x and y == end_y:
                break
            doubled = 2 * error
            if doubled >= delta_y:
                error += delta_y
                x += step_x
            if doubled <= delta_x:
                error += delta_x
                y += step_y

    def stroke_rect(self, x: int, y: int, width: int, height: int, color: Rgba) -> None:
        width, height = max(0, int(width)), max(0, int(height))
        if not width or not height:
            return
        self.draw_line(x, y, x + width - 1, y, color)
        self.draw_line(x, y + height - 1, x + width - 1, y + height - 1, color)
        self.draw_line(x, y, x, y + height - 1, color)
        self.draw_line(x + width - 1, y, x + width - 1, y + height - 1, color)


def parse_color(value: Any, fallback: Rgba = WHITE) -> Rgba:
    if not isinstance(value, str) or not HEX_COLOR.fullmatch(value):
        return fallback
    return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16), 255)


def _nested(overrides: Mapping[str, Any], group: str, key: str) -> Any:
    value = overrides.get(group)
    if isinstance(value, Mapping) and key in value:
        return value[key]
    for candidate in (f"{group}.{key}", f"${group}.{key}", key):
        if candidate in overrides:
            return overrides[candidate]
    return None


def resolve_settings(definition: Mapping[str, Any], overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    overrides = overrides or {}
    parameters = definition["parameters"]
    layout_parameter = parameters["layoutPreset"]
    candidate = overrides.get("layoutPreset", layout_parameter["default"])
    layout = candidate if candidate in layout_parameter["options"] else layout_parameter["default"]
    colors: dict[str, Any] = {}
    for key, parameter in parameters["colors"].items():
        override = _nested(overrides, "colors", key)
        if parameter["type"] == "toggle":
            colors[key] = override if isinstance(override, bool) else parameter["default"]
        else:
            colors[key] = override.upper() if isinstance(override, str) and HEX_COLOR.fullmatch(override) else parameter["default"].upper()
    fonts: dict[str, str] = {}
    for key, parameter in parameters["fonts"].items():
        override = _nested(overrides, "fonts", key)
        fonts[key] = override if isinstance(override, str) and override in parameter["options"] else parameter["default"]
    elements: dict[str, bool] = {}
    for key, default in parameters["elements"].items():
        override = _nested(overrides, "elements", key)
        elements[key] = override if isinstance(override, bool) else bool(default)
    transition_override = overrides.get("transition")
    if isinstance(transition_override, Mapping):
        transition_override = transition_override.get("value")
    transition = transition_override if transition_override in parameters["transition"]["options"] else parameters["transition"]["default"]
    return {"layoutPreset": layout, "colors": colors, "fonts": fonts, "elements": elements, "transition": transition}


def _get(context: Any, path: str) -> Any:
    value = context
    for segment in path.split("."):
        if not SAFE_PATH.fullmatch(segment) or segment in FORBIDDEN or not isinstance(value, Mapping) or segment not in value:
            return None
        value = value[segment]
    return value


def evaluate_condition(expression: Any, context: Mapping[str, Any]) -> bool:
    if not isinstance(expression, str):
        return False
    match = CONDITION.fullmatch(expression)
    if not match:
        return False
    left, operator, literal = _get(context, match.group(1)), match.group(2), match.group(3)
    if literal == "null":
        right: Any = None
    elif literal == "true":
        right = True
    elif literal == "false":
        right = False
    elif literal.startswith(("\"", "'")):
        right = literal[1:-1]
    else:
        right = float(literal) if "." in literal else int(literal)
    if right is None:
        return (left is None) if operator == "==" else (left is not None) if operator == "!=" else False
    if operator == "==":
        return type(left) is type(right) and left == right
    if operator == "!=":
        return type(left) is not type(right) or left != right
    if type(left) is not type(right) or not isinstance(left, (int, float, str)):
        return False
    return {"<": left < right, "<=": left <= right, ">": left > right, ">=": left >= right}.get(operator, False)


STATUS_LABEL = {
    "pregame": "PREGAME", "in_progress": "LIVE", "final": "FINAL",
    "delayed": "DELAYED", "postponed": "POSTPONED", "suspended": "SUSPENDED",
    "canceled": "CANCELED", "unknown": "STATUS N/A",
}


def _wall_time(value: Any, format_name: str = "12h") -> str:
    if not isinstance(value, str):
        return "TIME TBA"
    match = re.search(r"T(\d{2}):(\d{2})", value)
    if not match:
        return "TIME TBA"
    hour, minute = int(match.group(1)), int(match.group(2))
    if format_name == "24h":
        return f"{hour:02}:{minute:02}"
    return f"{hour % 12 or 12}:{minute:02} {'PM' if hour >= 12 else 'AM'}"


def _game_bindings(
    game: Mapping[str, Any] | None,
    favorites: Sequence[str],
    favorite: bool | None,
    idle_message: str | None,
    away_logo_key: str | None = None,
    home_logo_key: str | None = None,
    away_logo_available: bool = False,
    home_logo_available: bool = False,
) -> dict[str, Any]:
    away = _get(game or {}, "away.abbr") or "AWAY"
    home = _get(game or {}, "home.abbr") or "HOME"
    is_favorite = favorite if favorite is not None else bool(game and (away in favorites or home in favorites))
    status = game.get("status") if game else None
    inning = game.get("inning") if game else None
    inning_display = "-"
    if status == "final":
        inning_display = "F"
    elif inning is not None:
        prefix = {"top": "T", "bottom": "B", "middle": "M", "end": "E"}.get(str(game.get("inningHalf")), "")
        inning_display = f"{prefix}{inning}"
    home_probable, away_probable = _get(game or {}, "probables.home"), _get(game or {}, "probables.away")
    probable = f"P: {away_probable or 'AWAY TBA'} / {home_probable or 'HOME TBA'}"
    def score(value: Any) -> str:
        return str(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else "-"
    detail = str(game.get("statusDetail") or "").strip().upper() if game else ""
    def short_name(value: Any, fallback: str) -> str:
        parts = str(value or "").strip().split()
        return (parts[-1] if parts else fallback).upper()
    has_pitcher = bool(str(_get(game or {}, "currentPitcher.name") or "").strip())
    has_batter = bool(str(_get(game or {}, "currentBatter.name") or "").strip())
    pitcher_display = short_name(_get(game or {}, "currentPitcher.name"), "") if has_pitcher else ""
    batter_display = short_name(_get(game or {}, "currentBatter.name"), "") if has_batter else ""
    pitch_code = str(_get(game or {}, "lastPitch.code") or _get(game or {}, "lastPitch.type") or "").strip().upper()
    pitch_speed = _get(game or {}, "lastPitch.startSpeedMph")
    pitch_display = f"{pitch_code}{f' {round(pitch_speed)} MPH' if isinstance(pitch_speed, (int, float)) and not isinstance(pitch_speed, bool) else ''}" if pitch_code else ""
    play = (game or {}).get("lastPlay")
    play_display = str(_get(play or {}, "displayText") or "").strip().upper()
    if not play_display and isinstance(play, Mapping):
        if play.get("eventType") == "home_run":
            rbi = play.get("rbi")
            play_display = "GRAND SLAM" if rbi == 4 else f"{rbi}-RUN HR" if isinstance(rbi, int) and rbi > 1 else "HOME RUN"
        else:
            play_display = str(play.get("event") or "").strip().upper()
    distance = _get(game or {}, "battedBall.estimatedDistanceFt")
    exit_velocity = _get(game or {}, "battedBall.exitVelocityMph")
    batted_parts = []
    if isinstance(distance, (int, float)) and not isinstance(distance, bool):
        batted_parts.append(f"{round(distance)} FT")
    if isinstance(exit_velocity, (int, float)) and not isinstance(exit_velocity, bool):
        batted_parts.append(f"{round(exit_velocity)} MPH")
    batted_ball_display = "  ".join(batted_parts)
    # Missing player context falls back to inning/status instead of rendering
    # literal placeholder names like "P PITCHER  B BATTER".
    status_context = (
        (f"{inning_display} · " if inning_display != "-" else "")
        + (detail or STATUS_LABEL.get(str(status), "STATUS N/A"))
    ) if game else "NO GAMES"
    has_player_context = has_pitcher or has_batter
    matchup = f"P {pitcher_display or 'TBD'}  B {batter_display or 'TBD'}" if has_player_context else status_context
    broadcast_context = (
        f"{play_display}{f'  {batted_ball_display}' if batted_ball_display else ''}"
        if play_display
        else (
            f"{pitch_display}  "
            + (f"{pitcher_display or 'TBD'} > {batter_display or 'TBD'}" if has_player_context else status_context)
            if pitch_display
            else matchup
        )
    )
    return {
        "inningDisplay": inning_display,
        "statusLabel": detail or STATUS_LABEL.get(str(status), "STATUS N/A") if game else "NO GAMES",
        "startTimeDisplay": _wall_time((game or {}).get("startTimeLocal") or (game or {}).get("startTimeUtc")),
        "probableDisplay": probable,
        "matchupDisplay": f"{away} AT {home}",
        "scorelineDisplay": f"{away} {score(_get(game or {}, 'away.score'))}-{score(_get(game or {}, 'home.score'))} {home}",
        "gameNumberDisplay": f"G{game.get('gameNumber')}" if game and game.get("doubleheader") else "",
        "venueDisplay": str((game or {}).get("venue") or "VENUE TBA").strip(),
        "idleMessage": (idle_message or "CHECK BACK FOR THE NEXT GAME").strip(),
        "awayLogoAssetKey": away_logo_key or "",
        "homeLogoAssetKey": home_logo_key or "",
        "gameLogosAvailable": bool(game and away_logo_available and home_logo_available),
        "isFavorite": is_favorite,
        "pitcherDisplay": pitcher_display,
        "batterDisplay": batter_display,
        "pitchDisplay": pitch_display,
        "playDisplay": play_display,
        "battedBallDisplay": batted_ball_display,
        "broadcastContextDisplay": broadcast_context,
    }


def _standing_bindings(standings: Mapping[str, Any] | None, row: Mapping[str, Any] | None, favorites: Sequence[str], logo_key: str | None, logo_available: bool) -> dict[str, Any]:
    games_back = row.get("gamesBack") if row else None
    return {
        "rankDisplay": f"#{row.get('rank')}" if row else "#-",
        "recordDisplay": f"{row.get('wins')}-{row.get('losses')}" if row else "-- --",
        "divisionDisplay": str(_get(standings or {}, "division.name") or "STANDINGS").upper(),
        "gamesBackDisplay": "-" if games_back in (None, 0, 0.0) else f"{games_back:g}" if isinstance(games_back, float) else f"{games_back}",
        "logoAssetKey": logo_key or "",
        "logoAvailable": logo_available,
        "isFavorite": bool(row and _get(row, "team.abbr") in favorites),
    }


def _has_visible_logo_pixels(asset: Any) -> bool:
    if not isinstance(asset, Mapping):
        return False
    data = asset.get("data")
    width, height = asset.get("width"), asset.get("height")
    if not isinstance(data, Sequence) or not isinstance(width, int) or not isinstance(height, int):
        return False
    channels = 4 if len(data) >= width * height * 4 else 3
    for offset in range(0, len(data) - channels + 1, channels):
        alpha = data[offset + 3] if channels == 4 else 255
        if alpha:
            return True
    return False


def _font(value: str, settings: Mapping[str, Any], fonts: Mapping[str, BdfFont]) -> BdfFont | None:
    match = re.fullmatch(r"\$fonts\.([A-Za-z][A-Za-z0-9_]*)", value)
    name = settings["fonts"].get(match.group(1), "") if match else value
    return fonts.get(name) or fonts.get("5x7") or next(iter(fonts.values()), None)


def _favorite_abbr(context: Mapping[str, Any]) -> str | None:
    if context["bindings"].get("isFavorite") is not True:
        return None
    row, game, favorites = context.get("standingTeam"), context.get("game"), context["favorites"]
    if row:
        return _get(row, "team.abbr")
    if game:
        away, home = _get(game, "away.abbr"), _get(game, "home.abbr")
        return away if away in favorites else home if home in favorites else home or away
    return None


def _color(value: str | None, context: Mapping[str, Any], binding: str | None = None, fallback: Rgba = WHITE) -> Rgba:
    if not value:
        return fallback
    match = re.fullmatch(r"\$colors\.([A-Za-z][A-Za-z0-9_]*)", value)
    if not match:
        return parse_color(value, fallback)
    role = match.group(1)
    resolved = context["settings"]["colors"].get(role)
    if context["settings"]["colors"].get("useTeamColors") and role == "teamText":
        if context.get("standingTeam"):
            resolved = context["definition"].get("teamColors", {}).get(_get(context["standingTeam"], "team.abbr"), resolved)
        elif context.get("game"):
            side = (binding or "").split(".")[0]
            abbr = _get(context["game"], f"{side}.abbr") if side in {"home", "away"} else None
            resolved = context["definition"].get("teamColors", {}).get(abbr, resolved)
    elif context["settings"]["colors"].get("useTeamColors") and role == "favoriteAccent":
        resolved = context["definition"].get("teamColors", {}).get(_favorite_abbr(context), resolved)
    return parse_color(resolved, fallback)


def _draw_text(buffer: PixelBuffer, font: BdfFont, text: str, x: int, y: int, color: Rgba, align: str = "left", max_width: int | None = None, outer_clip: Clip | None = None) -> None:
    measured = measure_text(font, text)
    origin_x = int(x - measured / 2) if align == "center" else x - measured if align == "right" else x
    clip = outer_clip
    if max_width is not None:
        own_x = int(x - max_width / 2) if align == "center" else x - max_width if align == "right" else x
        own = Clip(own_x, -4096, max(0, int(max_width)), 8192)
        if clip:
            left, top = max(clip.x, own.x), max(clip.y, own.y)
            right, bottom = min(clip.x + clip.width, own.x + own.width), min(clip.y + clip.height, own.y + own.height)
            clip = Clip(left, top, max(0, right - left), max(0, bottom - top))
        else:
            clip = own
    cursor_x, font_top = int(origin_x), font.y_offset + font.height
    for character in str(text):
        glyph = glyph_for(font, ord(character))
        if glyph is None:
            cursor_x += font.width
            continue
        glyph_top = glyph.y_offset + glyph.height
        draw_x = cursor_x + glyph.x_offset - font.x_offset
        draw_y = int(y) + font_top - glyph_top
        for gy in range(glyph.height):
            for gx in range(glyph.width):
                if glyph.bitmap[gy * glyph.width + gx]:
                    buffer.set_pixel(draw_x + gx, draw_y + gy, color, clip)
        cursor_x += glyph.advance_x


def _visible(element: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    visible_when = element.get("visibleWhen")
    if visible_when is not None:
        match = re.fullmatch(r"\$elements\.([A-Za-z][A-Za-z0-9_]*)", str(visible_when))
        if not match or context["settings"]["elements"].get(match.group(1)) is not True:
            return False
    return "when" not in element or evaluate_condition(element["when"], context["bindings"])


def _draw_element(buffer: PixelBuffer, element: Mapping[str, Any], context: Mapping[str, Any]) -> None:
    if not _visible(element, context):
        return
    kind = element.get("type")
    if kind == "box":
        color = _color(element.get("color"), context)
        if element.get("filled"):
            buffer.fill_rect(element["x"], element["y"], element["width"], element["height"], color)
        else:
            buffer.stroke_rect(element["x"], element["y"], element["width"], element["height"], color)
    elif kind == "line":
        buffer.draw_line(element["x1"], element["y1"], element["x2"], element["y2"], _color(element.get("color"), context))
    elif kind in {"text", "scrollText"}:
        font = _font(element["font"], context["settings"], context["fonts"])
        if not font:
            return
        text = str(element["text"]) if "text" in element else str(_get(context["bindings"], element.get("bind", "")) if _get(context["bindings"], element.get("bind", "")) is not None else "N/A")
        color = _color(element.get("color"), context, element.get("bind"))
        if kind == "text":
            _draw_text(buffer, font, text, element["x"], element["y"], color, element.get("align", "left"), element.get("maxWidth"))
        else:
            width, text_width = int(element["width"]), measure_text(font, text)
            origin = int(element["x"])
            viewport = Clip(origin, -4096, max(0, width), 8192)
            if text_width > width and width > 0:
                cycle = text_width + max(4, font.width)
                distance = int(max(0, context["elapsedMs"]) / 1000 * max(0, element["speedPxPerSec"]))
                origin -= distance % cycle
                _draw_text(buffer, font, text, origin, element["y"], color, outer_clip=viewport)
                if origin + text_width < element["x"] + width:
                    _draw_text(buffer, font, text, origin + cycle, element["y"], color, outer_clip=viewport)
            else:
                _draw_text(buffer, font, text, origin, element["y"], color, outer_clip=viewport)
    elif kind == "countText":
        count = _get(context["bindings"], element["bind"])
        font = _font(element["font"], context["settings"], context["fonts"])
        if isinstance(count, Mapping) and font:
            _draw_text(buffer, font, f"{element.get('prefix', '')}{count.get('balls', '-')}-{count.get('strikes', '-')}", element["x"], element["y"], _color(element.get("color"), context, element["bind"]))
    elif kind == "outsDots":
        raw = _get(context["bindings"], element["bind"])
        if isinstance(raw, int) and not isinstance(raw, bool):
            outs, spacing = max(0, min(3, raw)), max(2, min(20, int(element.get("spacing", 5))))
            for index in range(3):
                buffer.fill_rect(element["x"] + index * spacing, element["y"], 2, 2, _color(element.get("activeColor") if index < outs else element.get("color"), context, element["bind"]))
    elif kind == "basesDiamond":
        bases = _get(context["bindings"], element["bind"])
        if isinstance(bases, Mapping):
            size = max(2, min(12, int(element.get("size", 3))))
            for key, cx, cy in (("second", element["x"] + size * 2, element["y"] + size), ("third", element["x"] + size, element["y"] + size * 2), ("first", element["x"] + size * 3, element["y"] + size * 2)):
                occupied = bases.get(key) is True
                color = _color(element.get("occupiedColor") if occupied else element.get("color"), context, element["bind"])
                for dy in range(-size, size + 1):
                    for dx in range(-size, size + 1):
                        distance = abs(dx) + abs(dy)
                        if (occupied and distance <= size) or (not occupied and distance == size):
                            buffer.set_pixel(cx + dx, cy + dy, color)
    elif kind == "clock":
        font = _font(element["font"], context["settings"], context["fonts"])
        if font:
            text = _wall_time(str(context["now"]), element["format"])
            if text == "TIME TBA":
                text = "12:00 AM" if element["format"] == "12h" else "00:00"
            _draw_text(buffer, font, text, element["x"], element["y"], _color(element.get("color"), context))
    elif kind == "sprite":
        key = element.get("asset") or _get(context["bindings"], element.get("bind", ""))
        asset = context["assets"].get(key) if isinstance(key, str) else None
        if not isinstance(asset, Mapping):
            return
        width, height = int(asset.get("width", 0)), int(asset.get("height", 0))
        if element.get("mode") == "1bit" and "pixels" in asset:
            pixels = asset["pixels"]
            for y in range(height):
                for x in range(width):
                    value = pixels[y][x] if isinstance(pixels, Sequence) and pixels and isinstance(pixels[0], str) else pixels[y * width + x]
                    if value not in (0, False, "0", ".", " "):
                        buffer.set_pixel(element["x"] + x, element["y"] + y, _color(element.get("color"), context))
        elif element.get("mode") == "rgb" and "data" in asset:
            data = asset["data"]
            channels = 4 if len(data) >= width * height * 4 else 3
            peak = max((max(data[i:i+3]) for i in range(0, len(data) - channels + 1, channels)
                        if channels == 3 or data[i+3] > 0), default=0) if str(key).startswith('team-logo:') else 255
            for y in range(height):
                for x in range(width):
                    offset = (y * width + x) * channels
                    rgb = tuple(220 if peak == 0 else min(255, int(data[offset+c] * 220 / peak + .5)) if peak < 128 else data[offset+c] for c in range(3))
                    buffer.blend_pixel(element["x"] + x, element["y"] + y, (*rgb, data[offset + 3] if channels == 4 else 255))


def render_scene(
    definition: Mapping[str, Any],
    scene: str,
    fonts: Mapping[str, BdfFont | str],
    *,
    game: Mapping[str, Any] | None = None,
    standings: Mapping[str, Any] | None = None,
    standing_team: Mapping[str, Any] | None = None,
    logo_asset_key: str | None = None,
    away_logo_asset_key: str | None = None,
    home_logo_asset_key: str | None = None,
    logical: Mapping[str, int] | None = None,
    overrides: Mapping[str, Any] | None = None,
    favorite: bool | None = None,
    favorites: Sequence[str] = (),
    idle_message: str | None = None,
    elapsed_ms: float = 0,
    now: Any = 0,
    assets: Mapping[str, Any] | None = None,
    transport_held: bool = False,
    data_freshness: str = "fresh",
    data_error: str | None = None,
) -> PixelBuffer:
    settings = resolve_settings(definition, overrides)
    preset = definition.get("presets", {}).get(settings["layoutPreset"], {})
    scenes = {**definition["scenes"], **preset}
    size = logical or definition["targetLogical"]
    buffer = PixelBuffer(size["width"], size["height"], parse_color(settings["colors"].get("background"), BLACK))
    normalized_fonts = {key: parse_bdf(value) if isinstance(value, str) else value for key, value in fonts.items()}
    assets = assets or {}
    logo_available = bool(logo_asset_key and _has_visible_logo_pixels(assets.get(logo_asset_key)))
    away_logo_available = bool(away_logo_asset_key and _has_visible_logo_pixels(assets.get(away_logo_asset_key)))
    home_logo_available = bool(home_logo_asset_key and _has_visible_logo_pixels(assets.get(home_logo_asset_key)))
    bindings = {
        **(game or {}),
        **(standing_team or {}),
        **_game_bindings(
            game,
            favorites,
            favorite,
            idle_message,
            away_logo_asset_key,
            home_logo_asset_key,
            away_logo_available,
            home_logo_available,
        ),
    }
    if standing_team or standings:
        bindings.update(_standing_bindings(standings, standing_team, favorites, logo_asset_key, logo_available))
    bindings["transportHeld"] = transport_held is True
    bindings["dataFreshness"] = data_freshness
    bindings["dataError"] = data_error
    context = {
        "definition": definition,
        "settings": settings,
        "bindings": bindings,
        "game": game,
        "standingTeam": standing_team,
        "favorites": favorites,
        "fonts": normalized_fonts,
        "assets": assets,
        "elapsedMs": max(0, elapsed_ms),
        "now": now,
    }
    for element in scenes.get(scene, {}).get("elements", []):
        try:
            _draw_element(buffer, element, context)
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    for element in definition.get("overlays", []):
        try:
            _draw_element(buffer, element, context)
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    return buffer
