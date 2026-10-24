from __future__ import annotations

from time import monotonic
from typing import Any, Mapping, Sequence


def item_key(item: Mapping[str, Any]) -> str:
    kind = str(item.get("kind", "unknown"))
    if kind == "team":
        return f"team:{item.get('groupId', 'summary')}"
    if kind in ("game", "nfl", "nba", "nhl", "history"):
        return f"{kind}:{item.get('gameId', '')}"
    if kind == "standings":
        return f"standings:{item.get('standingsId', '')}:{item.get('teamId', '')}"
    return kind


class TransportController:
    """Button-safe NEXT/HOLD transport shared by GPIO and runtime tests."""

    def __init__(self, *, final_hold_sec: float = 60.0, clock=monotonic) -> None:
        self._clock = clock
        self.final_hold_sec = final_hold_sec
        self.items: list[dict[str, Any]] = []
        self.games: dict[str, Mapping[str, Any]] = {}
        self.index = 0
        self.held = False
        self.item_started = clock()
        self.final_started: float | None = None

    @property
    def current(self) -> dict[str, Any] | None:
        return self.items[self.index] if self.items else None

    @property
    def hold_label(self) -> str:
        current = self.current
        return "WATCH LIVE" if current and current.get("kind") in ("game", "nfl", "nba", "nhl") else "HOLD"

    def update(self, items: Sequence[Mapping[str, Any]], games: Sequence[Mapping[str, Any]]) -> None:
        now = self._clock()
        current_key = item_key(self.current) if self.current else None
        self.items = [dict(item) for item in items]
        self.games = {str(game.get("gameId", "")): game for game in games}
        if not self.items:
            self.index = 0
            self.held = False
            self.final_started = None
            return
        matched = next(
            (index for index, item in enumerate(self.items) if item_key(item) == current_key),
            None,
        )
        if matched is not None:
            self.index = matched
        else:
            self.index = min(self.index, len(self.items) - 1)
            self.item_started = now
            self.final_started = None
            if self.held:
                self.held = False
        current = self.current
        game = self.games.get(str(current.get("gameId"))) if current and current.get("kind") == "game" else None
        if self.held and ((game and game.get("status") == "final") or (current and current.get("kind") in ("nfl", "nba", "nhl") and current.get("completed"))):
            self.final_started = self.final_started or now
        else:
            self.final_started = None

    def _move(self, delta: int, *, release: bool = True) -> None:
        if not self.items:
            return
        if release:
            self.held = False
        self.final_started = None
        self.index = (self.index + delta) % len(self.items)
        self.item_started = self._clock()

    def next(self) -> None:
        self._move(1)

    def previous(self) -> None:
        self._move(-1)

    def toggle_hold(self) -> bool:
        if not self.current:
            self.held = False
            return False
        self.held = not self.held
        self.item_started = self._clock()
        self.final_started = None
        return self.held

    def tick(self) -> bool:
        current = self.current
        if not current:
            return False
        now = self._clock()
        if self.held:
            if self.final_started is not None and now - self.final_started >= self.final_hold_sec:
                self._move(1)
                return True
            return False
        dwell = max(1.0, float(current.get("dwellSec", 1)))
        if now - self.item_started >= dwell:
            self._move(1, release=False)
            return True
        return False

    def status(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "count": len(self.items),
            "held": self.held,
            "holdLabel": self.hold_label,
            "item": self.current,
        }
