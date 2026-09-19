import numpy as np
import pytest

from mcbuilder.builder import ProgressFile, hotbar_commands, run
from mcbuilder.controller import Aborted
from mcbuilder.image_proc import BlockGrid
from mcbuilder.palette import Palette
from mcbuilder.plan import plan_wall


class FakeControls:
    def __init__(self):
        self.released = 0

    def release_all(self):
        self.released += 1


class FakeController:
    """Records the flight/place sequence without touching Windows or a game."""

    def __init__(self, fail_at: int | None = None):
        self.controls = FakeControls()
        self.moves: list[tuple[float, float, float]] = []
        self.placed: list[tuple[tuple[float, float, float], int]] = []
        self.fail_at = fail_at

    def goto(self, x, y, z):
        self.moves.append((x, y, z))

    def place(self, target, slot):
        if self.fail_at is not None and len(self.placed) == self.fail_at:
            raise Aborted("hotkey")
        self.placed.append((target, slot))


def make_plan(rows=4, cols=6):
    pal = Palette.from_names(["white_concrete", "black_concrete"])
    idx = np.zeros((rows, cols), dtype=int)
    idx[::2] = 1
    return plan_wall(BlockGrid(idx, pal), origin=(0, 64, 0))


def test_hotbar_commands_are_slot_ordered_and_zero_indexed():
    plan = make_plan()
    commands = hotbar_commands(plan)
    # Chat uses hotbar.0-8 while the plan and the number keys are 1-9.
    assert commands[0].startswith("/item replace entity @s hotbar.0 with minecraft:")
    assert all(c.startswith("/item replace entity @s hotbar.") for c in commands)
    assert len(commands) == len(plan.slots)


def test_run_places_every_block_once():
    plan = make_plan()
    ctl = FakeController()
    placed = run(ctl, plan)
    assert placed == plan.total_blocks == len(ctl.placed)
    assert len(ctl.moves) == len(plan.stations)


def test_run_visits_one_station_per_flight():
    plan = make_plan(rows=6, cols=11)
    ctl = FakeController()
    run(ctl, plan)
    assert ctl.moves == [(s.x, s.y, s.z) for s in plan.stations]


def test_abort_releases_keys_and_records_progress(tmp_path):
    plan = make_plan()
    progress = ProgressFile(tmp_path / "progress.json")
    ctl = FakeController(fail_at=5)
    with pytest.raises(Aborted):
        run(ctl, plan, progress=progress)
    assert ctl.controls.released > 0
    assert progress.read() == 5


def test_resume_skips_what_was_already_placed(tmp_path):
    plan = make_plan()
    first = FakeController(fail_at=5)
    progress = ProgressFile(tmp_path / "progress.json")
    with pytest.raises(Aborted):
        run(first, plan, progress=progress)

    second = FakeController()
    placed = run(second, plan, progress=progress, start_at=progress.read())
    assert placed == plan.total_blocks - 5
    # The two runs together must cover the wall exactly once.
    combined = first.placed + second.placed
    assert len(combined) == plan.total_blocks
    assert len({c[0] for c in combined}) == plan.total_blocks


def test_completed_run_clears_the_progress_file(tmp_path):
    progress = ProgressFile(tmp_path / "progress.json")
    progress.write(3)
    run(FakeController(), make_plan(), progress=progress)
    assert progress.read() == 0


def test_resume_skips_whole_stations_without_flying_to_them():
    plan = make_plan(rows=6, cols=11)
    first_station = len(plan.stations[0].placements)
    ctl = FakeController()
    run(ctl, plan, start_at=first_station)
    assert len(ctl.moves) == len(plan.stations) - 1


def test_corrupt_progress_file_is_ignored(tmp_path):
    path = tmp_path / "progress.json"
    path.write_text("not json")
    assert ProgressFile(path).read() == 0
