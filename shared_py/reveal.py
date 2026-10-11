from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

RevealState = Literal["disarmed", "armed", "started", "completed"]

_VALID_STATES: tuple[RevealState, ...] = ("disarmed", "armed", "started", "completed")


class RevealTransitionError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_reveal() -> dict[str, Any]:
    return {"schemaVersion": "1.0", "state": "disarmed", "updatedUtc": _utc_now()}


def load_reveal(path: Path) -> dict[str, Any]:
    """Fails closed to 'disarmed' on any missing/corrupt state file — an
    unreadable state must never be treated as armed."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("state") not in _VALID_STATES:
            return default_reveal()
        return data
    except (OSError, ValueError):
        return default_reveal()


def save_reveal(path: Path, reveal: dict[str, Any]) -> None:
    """Atomic write (tmp + rename) so a crash mid-write cannot leave a
    corrupt or half-written state file behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**reveal, "updatedUtc": _utc_now()}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(path)


def _transition(reveal: dict[str, Any], allowed_from: tuple[RevealState, ...], to: RevealState) -> dict[str, Any]:
    current = reveal.get("state")
    if current not in allowed_from:
        raise RevealTransitionError(f"cannot move to '{to}' from '{current}' (expected one of {allowed_from})")
    return {**reveal, "state": to}


def arm(reveal: dict[str, Any]) -> dict[str, Any]:
    """Operator-only action. Never called automatically by a boot or package
    update — that is what keeps 'ordinary boots... must not rearm the
    reveal' true structurally rather than by convention."""
    return _transition(reveal, ("disarmed", "completed"), "armed")


def disarm(reveal: dict[str, Any]) -> dict[str, Any]:
    return _transition(reveal, ("armed",), "disarmed")


def begin_playback(reveal: dict[str, Any]) -> dict[str, Any]:
    """Must be persisted (save_reveal) BEFORE the first reveal frame renders,
    so a power loss during playback leaves 'started' on disk and a
    subsequent boot does not autoplay again — bounded to a single surprise,
    not an endless replay loop."""
    return _transition(reveal, ("armed",), "started")


def complete_playback(reveal: dict[str, Any]) -> dict[str, Any]:
    return _transition(reveal, ("started",), "completed")


def replay(reveal: dict[str, Any]) -> dict[str, Any]:
    """Explicit operator action to watch it again — distinct from re-arming,
    and available without disarming/rearming first."""
    return _transition(reveal, ("completed", "started"), "started")


def force_start(reveal: dict[str, Any]) -> dict[str, Any]:
    """An explicit, unconditional 'play it now' request (e.g. a 'Play
    reveal now' web button) — unlike begin_playback/replay, allowed from any
    state, because the whole point is that an operator can trigger it
    regardless of whether it happens to be armed, disarmed, or already
    completed. Still moves through 'started' so the same durability and
    single-playback bookkeeping applies."""
    return {**reveal, "state": "started"}


def should_autoplay_on_boot(reveal: dict[str, Any]) -> bool:
    return reveal.get("state") == "armed" and reveal.get("trigger") != "controller"
