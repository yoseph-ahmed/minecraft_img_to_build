import builtins

import numpy as np
import pytest
from PIL import Image

from mcbuilder import interactive


@pytest.fixture
def png(tmp_path):
    path = tmp_path / "pic.png"
    Image.fromarray(np.zeros((8, 8, 3), dtype=np.uint8)).save(path)
    return path


def scripted(monkeypatch, answers):
    it = iter(answers)
    monkeypatch.setattr(builtins, "input", lambda *_: next(it))


class Recorder:
    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        return 0


def test_should_run_only_with_no_arguments():
    assert interactive.should_run([])
    assert not interactive.should_run(["plan"])


def test_menu_quits_cleanly(monkeypatch):
    scripted(monkeypatch, ["0"])
    assert interactive.run(Recorder()) == 0


def test_preview_builds_the_expected_command(monkeypatch, png):
    scripted(monkeypatch, ["4", str(png), "32", "10", "64", "20", "y", "0"])
    rec = Recorder()
    interactive.run(rec)
    assert rec.calls == [[
        "plan", str(png), "--width", "32",
        "-x", "10", "-y", "64", "-z", "20",
        "--preview", "preview.png",
    ]]


def test_declining_dither_adds_the_flag(monkeypatch, png):
    scripted(monkeypatch, ["4", str(png), "16", "0", "64", "0", "n", "0"])
    rec = Recorder()
    interactive.run(rec)
    assert "--no-dither" in rec.calls[0]


def test_build_collects_resume_and_dry_run(monkeypatch, png):
    scripted(monkeypatch, ["5", str(png), "64", "1", "2", "3", "y", "y", "y", "0"])
    rec = Recorder()
    interactive.run(rec)
    argv = rec.calls[0]
    assert argv[0] == "build"
    assert "--resume" in argv and "--dry-run" in argv


def test_quoted_drag_and_dropped_path_is_accepted(monkeypatch, png):
    # Dragging a file into a console pastes it quoted; Windows paths have
    # spaces often enough that the quotes must be stripped.
    scripted(monkeypatch, ["4", f'"{png}"', "8", "0", "64", "0", "y", "0"])
    rec = Recorder()
    interactive.run(rec)
    assert rec.calls[0][1] == str(png)


def test_bad_path_reprompts(monkeypatch, png, capsys):
    scripted(monkeypatch, ["4", "no-such-file.png", str(png), "8", "0", "64", "0", "y", "0"])
    rec = Recorder()
    interactive.run(rec)
    assert "no such file" in capsys.readouterr().out
    assert len(rec.calls) == 1


def test_non_numeric_width_reprompts(monkeypatch, png, capsys):
    scripted(monkeypatch, ["4", str(png), "wide", "8", "0", "64", "0", "y", "0"])
    rec = Recorder()
    interactive.run(rec)
    assert "not a whole number" in capsys.readouterr().out
    assert rec.calls[0][3] == "8"


def test_unknown_choice_returns_to_the_menu(monkeypatch, capsys):
    scripted(monkeypatch, ["99", "0"])
    assert interactive.run(Recorder()) == 0
    assert "not an option" in capsys.readouterr().out


def test_a_failing_command_does_not_exit_the_menu(monkeypatch, capsys):
    def boom(argv):
        raise RuntimeError("kaboom")

    scripted(monkeypatch, ["6", "0"])
    assert interactive.run(boom) == 0
    assert "kaboom" in capsys.readouterr().out


def test_argparse_exit_does_not_kill_the_menu(monkeypatch, capsys):
    def bail(argv):
        raise SystemExit(2)

    scripted(monkeypatch, ["6", "0"])
    assert interactive.run(bail) == 0
    assert "exit 2" in capsys.readouterr().out
