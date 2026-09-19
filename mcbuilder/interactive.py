"""Guided menu for when the tool is launched without arguments.

A double-clicked argparse program prints a usage error and closes before
anyone can read it. The packaged .exe is meant to be usable without a
terminal, so with no arguments it walks through the same commands by asking
questions instead.

Every option here builds an argv list and hands it back to the normal parser
rather than calling the command functions directly. That keeps one definition
of every default and flag -- the menu cannot drift out of sync with the CLI.
"""

from __future__ import annotations

import sys
from pathlib import Path

BANNER = r"""
  mcbuilder -- build a PNG as a Minecraft mural
"""

MENU = """
  Setup (do these once, and again if you change resolution or GUI scale)
    1  Learn the F3 font
    2  Check what the reader sees
    3  Calibrate the mouse

  Building
    4  Preview an image          (no game needed, changes nothing)
    5  Build a mural in-game
    6  List available blocks

    0  Quit
"""


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        value = input(f"  {prompt}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default


def ask_int(prompt: str, default: int | None = None) -> int:
    while True:
        raw = ask(prompt, None if default is None else str(default))
        try:
            return int(raw)
        except ValueError:
            print(f"    '{raw}' is not a whole number.")


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    d = "y/N" if not default else "Y/n"
    raw = ask(f"{prompt} ({d})", "y" if default else "n").lower()
    return raw.startswith("y")


def ask_image() -> str:
    """Prompt for an image path, tolerating a drag-and-dropped one.

    Dragging a file into a console window pastes it quoted, and Windows paths
    often contain spaces, so the quotes have to come back off.
    """
    while True:
        raw = ask("PNG file (you can drag the file into this window)")
        path = Path(raw.strip().strip('"').strip("'"))
        if path.is_file():
            return str(path)
        print(f"    no such file: {path}")


def ask_origin() -> tuple[int, int, int]:
    print()
    print("  Where should the bottom-left corner of the mural go?")
    print("  Press F3 in-game and read the XYZ line; the wall is built on the")
    print("  +Z side of the Z you give, so stand south of it with room to fly.")
    print("  The row directly below Y must already be solid ground.")
    print()
    return ask_int("X"), ask_int("Y"), ask_int("Z")


def ask_image_args() -> list[str]:
    image = ask_image()
    width = ask_int("mural width in blocks", 64)
    x, y, z = ask_origin()
    args = [image, "--width", str(width), "-x", str(x), "-y", str(y), "-z", str(z)]
    if not ask_yes_no("Use dithering? (smoother gradients)", default=True):
        args.append("--no-dither")
    return args


def run(main) -> int:
    """Drive the CLI from a menu. `main` is mcbuilder.cli.main."""
    print(BANNER)
    if not (Path.home() / ".mcbuilder" / "font.json").exists():
        print("  First run: start with option 1 to teach the reader the F3 font.")

    while True:
        print(MENU)
        choice = ask("choose", "0")
        print()
        try:
            if choice == "0":
                return 0
            elif choice == "1":
                main(["learn-font"])
            elif choice == "2":
                main(["probe"])
            elif choice == "3":
                main(["calibrate"])
            elif choice == "4":
                argv = ["plan", *ask_image_args(), "--preview", "preview.png"]
                main(argv)
            elif choice == "5":
                argv = ["build", *ask_image_args()]
                if ask_yes_no("Resume an interrupted build?"):
                    argv.append("--resume")
                if ask_yes_no("Dry run? (log actions, send no input)"):
                    argv.append("--dry-run")
                main(argv)
            elif choice == "6":
                main(["blocks"])
            else:
                print(f"  '{choice}' is not an option.")
        except KeyboardInterrupt:
            print("\n  cancelled")
        except SystemExit as exc:
            # argparse exits on bad input; in a menu that should return to the
            # menu rather than kill the whole program.
            if exc.code not in (0, None):
                print(f"  command failed (exit {exc.code})")
        except Exception as exc:  # noqa: BLE001 - a menu must not crash out
            print(f"  error: {exc}")
        print()


def should_run(argv: list[str] | None) -> bool:
    """True when the program was started with no arguments at all."""
    return not (argv if argv is not None else sys.argv[1:])
