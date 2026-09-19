"""Run a WallPlan against a live game."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from .controller import Aborted, Controller
from .plan import WallPlan

log = logging.getLogger(__name__)


def hotbar_commands(plan: WallPlan) -> list[str]:
    """Chat commands that load the palette into the hotbar.

    `/item replace` targets a specific slot, which the creative inventory UI
    cannot do without click-dragging. That keeps the whole hotbar setup inside
    the chat box instead of needing inventory-screen automation.
    """
    return [
        f"/item replace entity @s hotbar.{slot - 1} with minecraft:{name}"
        for name, slot in sorted(plan.slots.items(), key=lambda kv: kv[1])
    ]


class ProgressFile:
    """Records how far a build got, so an abort can be resumed.

    Builds take a long time and get interrupted -- by the abort hotkey, a
    disconnect, or the player being knocked off station. Replaying from block
    zero would be slow but harmless in creative; resuming is simply kinder.
    """

    def __init__(self, path: Path):
        self.path = path

    def read(self) -> int:
        if not self.path.exists():
            return 0
        try:
            return int(json.loads(self.path.read_text(encoding="utf-8"))["placed"])
        except (ValueError, KeyError, OSError):
            log.warning("ignoring unreadable progress file %s", self.path)
            return 0

    def write(self, placed: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"placed": placed}), encoding="utf-8")

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


def load_hotbar(controller: Controller, plan: WallPlan) -> None:
    for command in hotbar_commands(plan):
        log.info("chat: %s", command)
        controller.controls.send_chat(command)
        time.sleep(0.15)


def run(
    controller: Controller,
    plan: WallPlan,
    progress: ProgressFile | None = None,
    start_at: int = 0,
    on_progress=None,
) -> int:
    """Execute the plan. Returns the number of blocks placed this run."""
    placed = 0
    index = 0
    try:
        for station in plan.stations:
            # Skip whole stations that finished on a previous run before
            # spending a flight on them.
            if index + len(station.placements) <= start_at:
                index += len(station.placements)
                continue

            controller.goto(station.x, station.y, station.z)
            for p in station.placements:
                if index < start_at:
                    index += 1
                    continue
                controller.place(p.target, p.slot)
                index += 1
                placed += 1
                if progress is not None:
                    progress.write(index)
                if on_progress is not None:
                    on_progress(index, plan.total_blocks, p)
    except (Aborted, KeyboardInterrupt):
        controller.controls.release_all()
        log.warning("aborted after %d block(s); resume with --resume", index)
        raise
    finally:
        controller.controls.release_all()

    if progress is not None:
        progress.clear()
    return placed
