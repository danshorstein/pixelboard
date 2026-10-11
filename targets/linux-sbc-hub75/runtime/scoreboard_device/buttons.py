from __future__ import annotations

from typing import Any, Callable, Mapping


class PhysicalButtons:
    """Initializes button descriptors before the matrix driver drops privileges."""

    def __init__(self, config: Mapping[str, Any], on_next: Callable[[], None], on_hold: Callable[[], None]) -> None:
        self.available = False
        self.error: str | None = None
        self._buttons: list[Any] = []
        if config.get("enabled", True) is not True:
            return
        try:
            from gpiozero import Button

            bounce = float(config.get("bounceSec", 0.08))
            next_button = Button(int(config.get("nextPin", 25)), pull_up=True, bounce_time=bounce)
            hold_button = Button(int(config.get("holdPin", 19)), pull_up=True, bounce_time=bounce)
            next_button.when_pressed = on_next
            hold_button.when_pressed = on_hold
            self._buttons = [next_button, hold_button]
            self.available = True
        except Exception as error:
            self.error = str(error)

    def close(self) -> None:
        for button in self._buttons:
            button.close()
