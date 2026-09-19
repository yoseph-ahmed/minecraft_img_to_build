"""Turn a block grid into an ordered flight plan for a vertical wall.

Geometry
--------
The mural occupies the plane ``z = z0``, one block thick. Image column ``i``
maps to ``x = x0 + i`` and image row ``j`` (counted from the bottom) maps to
``y = y0 + j``. The player works from the ``+Z`` side, facing north.

Why every block is placed on the face *below* it
------------------------------------------------
In creative you place a block by clicking an existing face, and the new block
appears against that face's normal. From in front of the wall the only usable
face is the **top** of the block underneath: the south face of a neighbour is
what the raycast hits first when you try to aim at its side, and clicking that
would build a second layer out in front of the mural instead of extending it.

That constraint drives two things. The wall must grow strictly bottom-up, and
the player's eye has to sit *above* the row being placed, otherwise the ray
enters the supporting block through its south face rather than its top. The
eye-above-target rule is also why stations are wide and short rather than
square -- vertical span is spent out of the same reach budget as everything
else, so a tall patch would put its bottom row out of range.

It also means the row below ``y0`` must already be solid. Flat ground under the
mural is a precondition; ``mcbuilder build`` checks nothing about the world, so
if the ground is uneven the bottom row will fail to place.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .image_proc import BlockGrid

# Creative block-placement reach is 5.0 blocks. Staying under 4.3 leaves room
# for the position controller's own tolerance without losing placements.
MAX_REACH = 4.3


@dataclass(frozen=True)
class Placement:
    """One block to place, and the face to aim at to place it."""

    bx: int
    by: int
    bz: int
    block: str
    slot: int  # hotbar slot, 1-9

    @property
    def target(self) -> tuple[float, float, float]:
        """Centre of the top face of the supporting block directly below."""
        return (self.bx + 0.5, float(self.by), self.bz + 0.5)


@dataclass(frozen=True)
class Station:
    """A hover position and the blocks reachable from it, in placement order."""

    x: float
    y: float
    z: float
    placements: tuple[Placement, ...]

    @property
    def eye(self) -> tuple[float, float, float]:
        return (self.x, self.y + 1.62, self.z)


@dataclass(frozen=True)
class WallPlan:
    origin: tuple[int, int, int]
    cols: int
    rows: int
    stations: tuple[Station, ...]
    slots: dict[str, int]  # block name -> hotbar slot

    @property
    def total_blocks(self) -> int:
        return sum(len(s.placements) for s in self.stations)


def aim_angles(
    eye: tuple[float, float, float], target: tuple[float, float, float]
) -> tuple[float, float]:
    """Yaw/pitch that point the camera from `eye` at `target`.

    Follows Minecraft's conventions: yaw 0 faces +Z and increases toward -X,
    pitch is positive looking down.
    """
    dx = target[0] - eye[0]
    dy = target[1] - eye[1]
    dz = target[2] - eye[2]
    # `0.0 - dx` rather than `-dx`: negating an exact 0.0 gives -0.0, which
    # sends atan2 to -180 instead of +180 for a due-north target. Both are the
    # same heading, but the sign churn is noise in logs and test expectations.
    yaw = math.degrees(math.atan2(0.0 - dx, dz))
    horizontal = math.hypot(dx, dz)
    pitch = -math.degrees(math.atan2(dy, horizontal))
    return yaw, pitch


def distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.dist(a, b)


def plan_wall(
    grid: BlockGrid,
    origin: tuple[int, int, int],
    patch_width: int = 5,
    patch_height: int = 3,
    standoff: float = 2.0,
    eye_clearance: float = 0.8,
) -> WallPlan:
    """Tile the wall into stations and order every placement bottom-up.

    `standoff` is the horizontal gap from the wall plane to the player's eye,
    and `eye_clearance` how far the eye sits above the top row of the patch.
    The defaults are the largest patch that keeps the far bottom corner inside
    MAX_REACH; widening either without lowering the other will start dropping
    blocks, which `validate` will report.
    """
    x0, y0, z0 = origin
    slots = {name: i + 1 for i, name in enumerate(grid.palette.names)}
    if len(slots) > 9:
        raise ValueError(
            f"palette has {len(slots)} blocks but the hotbar holds 9; "
            "re-run with --palette-size 9 or fewer"
        )

    stations: list[Station] = []
    # Bottom-up over row bands, then left-to-right over column bands. Support
    # for any block is always the block directly beneath it, so this order
    # never depends on a neighbouring station having run first.
    for band_start in range(0, grid.rows, patch_height):
        band_rows = list(range(band_start, min(band_start + patch_height, grid.rows)))
        y_top = y0 + band_rows[-1]
        for col_start in range(0, grid.cols, patch_width):
            cols = list(range(col_start, min(col_start + patch_width, grid.cols)))
            placements: list[Placement] = []
            for j in band_rows:  # already bottom-up
                # Grid row 0 is the top of the image; the wall builds upward.
                r = grid.rows - 1 - j
                for i in cols:
                    name = grid.block_at(r, i)
                    placements.append(
                        Placement(x0 + i, y0 + j, z0, name, slots[name])
                    )
            if not placements:
                continue
            stations.append(
                Station(
                    x=x0 + (cols[0] + cols[-1]) / 2 + 0.5,
                    y=y_top + eye_clearance - 1.62,
                    z=z0 + 0.5 + standoff,
                    placements=tuple(placements),
                )
            )

    return WallPlan(
        origin=(x0, y0, z0),
        cols=grid.cols,
        rows=grid.rows,
        stations=tuple(stations),
        slots=slots,
    )


def validate(plan: WallPlan) -> list[str]:
    """Report placements the geometry cannot actually reach.

    Run as part of `mcbuilder plan` so bad patch settings surface before the
    character is flying around rather than as mysteriously missing blocks.
    """
    problems: list[str] = []
    for n, station in enumerate(plan.stations):
        for p in station.placements:
            d = distance(station.eye, p.target)
            if d > MAX_REACH:
                problems.append(
                    f"station {n} at ({station.x:.1f},{station.y:.1f},{station.z:.1f}): "
                    f"block ({p.bx},{p.by},{p.bz}) is {d:.2f} blocks away "
                    f"(max {MAX_REACH})"
                )
            if station.eye[1] <= p.target[1]:
                problems.append(
                    f"station {n}: eye at y={station.eye[1]:.2f} is not above the "
                    f"top face at y={p.target[1]:.2f} for block "
                    f"({p.bx},{p.by},{p.bz}); the raycast would hit the south face"
                )
    return problems
