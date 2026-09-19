import numpy as np
import pytest

from mcbuilder.image_proc import BlockGrid
from mcbuilder.palette import Palette
from mcbuilder.plan import MAX_REACH, aim_angles, distance, plan_wall, validate


def make_grid(rows, cols, names=("white_concrete", "black_concrete")):
    pal = Palette.from_names(list(names))
    idx = np.zeros((rows, cols), dtype=int)
    idx[::2] = 1
    return BlockGrid(idx, pal)


# --- aim conventions -------------------------------------------------------
# These four cases pin Minecraft's yaw convention (0 = +Z, increasing toward
# -X). A sign flip here would aim at the mirror image of the wall and is not
# otherwise visible until the character is spinning in-game.

@pytest.mark.parametrize(
    "target,expected_yaw",
    [
        ((0.0, 10.0, 5.0), 0.0),     # +Z, south
        ((-5.0, 10.0, 0.0), 90.0),   # -X, west
        ((5.0, 10.0, 0.0), -90.0),   # +X, east
        ((0.0, 10.0, -5.0), 180.0),  # -Z, north
    ],
)
def test_aim_yaw_conventions(target, expected_yaw):
    yaw, pitch = aim_angles((0.0, 10.0, 0.0), target)
    assert yaw == pytest.approx(expected_yaw)
    assert pitch == pytest.approx(0.0)


def test_aim_pitch_is_positive_looking_down():
    _, pitch = aim_angles((0.0, 10.0, 0.0), (0.0, 5.0, 5.0))
    assert pitch == pytest.approx(45.0)


# --- plan structure --------------------------------------------------------


def test_every_block_is_planned_exactly_once():
    grid = make_grid(7, 11)
    plan = plan_wall(grid, origin=(100, 64, 200))
    coords = [(p.bx, p.by, p.bz) for s in plan.stations for p in s.placements]
    assert len(coords) == 77 == plan.total_blocks
    assert len(set(coords)) == 77
    assert {c[2] for c in coords} == {200}
    assert min(c[0] for c in coords) == 100
    assert max(c[0] for c in coords) == 110
    assert min(c[1] for c in coords) == 64
    assert max(c[1] for c in coords) == 70


def test_support_block_is_always_placed_before_the_block_above():
    grid = make_grid(6, 9)
    plan = plan_wall(grid, origin=(0, 64, 0))
    seen: set[tuple[int, int, int]] = set()
    for station in plan.stations:
        for p in station.placements:
            below = (p.bx, p.by - 1, p.bz)
            # The bottom row rests on pre-existing ground; everything else
            # must already have its support in place or the click has no face.
            if p.by > 64:
                assert below in seen, f"{(p.bx, p.by, p.bz)} placed before its support"
            seen.add((p.bx, p.by, p.bz))


def test_image_top_row_ends_up_at_the_top_of_the_wall():
    pal = Palette.from_names(["white_concrete", "black_concrete"])
    idx = np.zeros((3, 2), dtype=int)
    idx[0] = 1  # top row of the image
    grid = BlockGrid(idx, pal)
    plan = plan_wall(grid, origin=(0, 64, 0))
    by_y = {}
    for s in plan.stations:
        for p in s.placements:
            by_y.setdefault(p.by, set()).add(p.block)
    assert by_y[66] == {"black_concrete"}  # image row 0 -> highest wall row
    assert by_y[64] == {"white_concrete"}


def test_target_is_the_top_face_of_the_block_below():
    grid = make_grid(1, 1)
    p = plan_wall(grid, origin=(10, 64, 20)).stations[0].placements[0]
    assert p.target == (10.5, 64.0, 20.5)


def test_hotbar_slots_are_one_based_and_unique():
    grid = make_grid(4, 4, names=("white_concrete", "red_concrete", "blue_concrete"))
    plan = plan_wall(grid, origin=(0, 64, 0))
    assert sorted(plan.slots.values()) == [1, 2, 3]


def test_palette_larger_than_the_hotbar_is_rejected():
    names = list(Palette.from_names(
        ["white_concrete", "black_concrete", "red_concrete", "blue_concrete",
         "green_concrete", "yellow_concrete", "cyan_concrete", "pink_concrete",
         "lime_concrete", "gray_concrete"]
    ).names)
    pal = Palette.from_names(names)
    grid = BlockGrid(np.zeros((2, 2), dtype=int), pal)
    with pytest.raises(ValueError, match="hotbar holds 9"):
        plan_wall(grid, origin=(0, 64, 0))


# --- geometry --------------------------------------------------------------


def test_default_patch_geometry_is_entirely_within_reach():
    plan = plan_wall(make_grid(12, 20), origin=(0, 64, 0))
    assert validate(plan) == []
    worst = max(
        distance(s.eye, p.target) for s in plan.stations for p in s.placements
    )
    assert worst <= MAX_REACH


def test_eye_stays_above_every_target_face():
    plan = plan_wall(make_grid(9, 9), origin=(0, 64, 0))
    for s in plan.stations:
        for p in s.placements:
            assert s.eye[1] > p.target[1]


def test_validate_flags_an_oversized_patch():
    plan = plan_wall(make_grid(12, 12), patch_width=11, patch_height=9, origin=(0, 64, 0))
    problems = validate(plan)
    assert problems
    assert any("blocks away" in p for p in problems)
