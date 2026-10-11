from __future__ import annotations

from typing import Literal

# Command identity, not physical button color — mirrors
# frontend/src/easterEgg.ts's SecretCommand/FIREWORKS_SEQUENCE exactly, so the
# browser and the Python/GPIO device runtime recognize the same secret code.
SecretCommand = Literal["next", "hold"]

FIREWORKS_SEQUENCE: tuple[SecretCommand, ...] = (
    "next", "next", "next",
    "hold", "hold", "hold",
    "next", "next", "next",
)


def advance_secret_sequence(progress: int, press: SecretCommand) -> int:
    if 0 <= progress < len(FIREWORKS_SEQUENCE) and FIREWORKS_SEQUENCE[progress] == press:
        return progress + 1
    return 1 if press == FIREWORKS_SEQUENCE[0] else 0
