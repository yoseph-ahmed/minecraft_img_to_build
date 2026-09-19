"""High-level input actions with guaranteed key release.

The builder holds movement keys down for long stretches. If the process dies
mid-flight without releasing them, the character keeps flying into the
distance -- so every held key is tracked and `release_all` is wired to both the
abort hotkey and process exit.

`dry_run=True` swaps the Win32 layer for logging, which is what makes the
planner testable off-Windows.
"""

from __future__ import annotations

import atexit
import logging
import time

log = logging.getLogger(__name__)


class Controls:
    def __init__(self, dry_run: bool = False, key_delay: float = 0.012):
        self.dry_run = dry_run
        self.key_delay = key_delay
        self._held: set[str] = set()
        self._buttons: set[str] = set()
        self._si = None
        if not dry_run:
            from . import sendinput

            self._si = sendinput
        atexit.register(self.release_all)

    # --- keys ---------------------------------------------------------------

    def hold(self, key: str) -> None:
        if key in self._held:
            return
        self._held.add(key)
        if self._si:
            self._si.key_down(key)
        else:
            log.debug("hold %s", key)

    def release(self, key: str) -> None:
        if key not in self._held:
            return
        self._held.discard(key)
        if self._si:
            self._si.key_up(key)
        else:
            log.debug("release %s", key)

    def tap(self, key: str, duration: float | None = None) -> None:
        self.hold(key)
        time.sleep(self.key_delay if duration is None else duration)
        self.release(key)

    def release_all(self) -> None:
        for key in list(self._held):
            self.release(key)
        for button in list(self._buttons):
            self.mouse_up(button)

    # --- mouse --------------------------------------------------------------

    def move(self, dx: int, dy: int) -> None:
        if dx == 0 and dy == 0:
            return
        if self._si:
            self._si.mouse_move(dx, dy)
        else:
            log.debug("mouse_move %d %d", dx, dy)

    def mouse_down(self, button: str = "right") -> None:
        self._buttons.add(button)
        if self._si:
            self._si.mouse_button(button, True)
        else:
            log.debug("mouse_down %s", button)

    def mouse_up(self, button: str = "right") -> None:
        self._buttons.discard(button)
        if self._si:
            self._si.mouse_button(button, False)
        else:
            log.debug("mouse_up %s", button)

    def click(self, button: str = "right", duration: float = 0.03) -> None:
        self.mouse_down(button)
        time.sleep(duration)
        self.mouse_up(button)

    # --- composites ---------------------------------------------------------

    def select_hotbar(self, slot: int) -> None:
        """Select hotbar slot 1-9."""
        if not 1 <= slot <= 9:
            raise ValueError(f"hotbar slot out of range: {slot}")
        self.tap(str(slot))

    def toggle_fly(self) -> None:
        """Double-tap space, the creative-mode flight toggle."""
        self.tap("space")
        time.sleep(0.08)
        self.tap("space")
        time.sleep(0.25)

    def send_chat(self, message: str) -> None:
        """Open chat, type a line, submit."""
        if self._si is None:
            log.debug("chat %s", message)
            return
        self.tap("t")
        time.sleep(0.25)
        self._si.type_text(message)
        time.sleep(0.12)
        self.tap("enter")
        time.sleep(0.2)
