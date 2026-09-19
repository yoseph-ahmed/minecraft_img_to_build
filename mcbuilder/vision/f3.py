"""Parse player position and facing out of recognised F3 overlay text.

The exact wording of the debug screen shifts between Minecraft versions, so
these patterns key off the numeric shapes rather than fixed column positions:

    XYZ: -123.456 / 64.00000 / 789.012
    Facing: south (Towards positive Z) (-0.2 / 31.5)

A '?' from the font matcher means a glyph was not recognised. Rather than
guess, a line containing one is treated as unreadable -- a misread coordinate
would silently fly the character to the wrong place, which is far worse than
skipping a frame and polling again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

NUM = r"(-?\d+(?:\.\d+)?)"
XYZ_RE = re.compile(rf"XYZ\s*:?\s*{NUM}\s*/\s*{NUM}\s*/\s*{NUM}", re.IGNORECASE)
FACING_RE = re.compile(rf"Facing\s*:.*?\(\s*{NUM}\s*/\s*{NUM}\s*\)", re.IGNORECASE)


class F3ReadError(RuntimeError):
    """The overlay could not be read this frame."""


@dataclass(frozen=True)
class PlayerState:
    """Feet position and camera angles, in Minecraft's own conventions.

    yaw:   0 = +Z (south), 90 = -X (west), 180 = -Z (north), -90 = +X (east)
    pitch: -90 = straight up, 0 = horizon, +90 = straight down
    """

    x: float
    y: float
    z: float
    yaw: float
    pitch: float

    @property
    def eye(self) -> tuple[float, float, float]:
        """Eye position. 1.62 above the feet for a standing or flying player."""
        return (self.x, self.y + 1.62, self.z)


def normalise_yaw(yaw: float) -> float:
    """Wrap a yaw into (-180, 180]."""
    y = (yaw + 180.0) % 360.0 - 180.0
    return 180.0 if y == -180.0 else y


def yaw_delta(current: float, target: float) -> float:
    """Shortest signed turn from `current` to `target`, in degrees."""
    return normalise_yaw(target - current)


def parse(lines: list[str]) -> PlayerState:
    pos = None
    facing = None
    for line in lines:
        if "?" in line:
            continue
        if pos is None:
            m = XYZ_RE.search(line)
            if m:
                pos = tuple(float(g) for g in m.groups())
        if facing is None:
            m = FACING_RE.search(line)
            if m:
                facing = tuple(float(g) for g in m.groups())
    if pos is None:
        raise F3ReadError(
            "no readable 'XYZ:' line found -- is F3 open and the capture "
            "region right? Run `mcbuilder probe` to see what was read."
        )
    if facing is None:
        raise F3ReadError(
            "no readable 'Facing:' line with a (yaw / pitch) pair found. "
            "Run `mcbuilder probe` to see what was read."
        )
    return PlayerState(pos[0], pos[1], pos[2], normalise_yaw(facing[0]), facing[1])
