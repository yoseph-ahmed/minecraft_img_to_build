"""Command line entry point."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from . import config
from .builder import ProgressFile, hotbar_commands, load_hotbar, run
from .image_proc import build_grid
from .palette import BLOCKS
from .plan import plan_wall, validate

log = logging.getLogger("mcbuilder")


def _grid_from_args(args):
    return build_grid(
        args.image,
        width=args.width,
        height=args.height,
        palette_size=args.palette_size,
        dither=not args.no_dither,
        blocks=args.blocks.split(",") if args.blocks else None,
    )


def _plan_from_args(args):
    grid = _grid_from_args(args)
    plan = plan_wall(
        grid,
        origin=(args.x, args.y, args.z),
        patch_width=args.patch_width,
        patch_height=args.patch_height,
        standoff=args.standoff,
    )
    return grid, plan


# --- commands --------------------------------------------------------------


def cmd_blocks(args) -> int:
    for name, (r, g, b) in sorted(BLOCKS.items()):
        print(f"{name:26s} #{r:02x}{g:02x}{b:02x}")
    print(f"\n{len(BLOCKS)} blocks available")
    return 0


def cmd_plan(args) -> int:
    grid, plan = _plan_from_args(args)

    print(f"image  : {args.image}")
    print(f"size   : {grid.cols} x {grid.rows} blocks ({plan.total_blocks} total)")
    print(f"origin : x={args.x} y={args.y} z={args.z} (bottom-left of the mural)")
    print(f"flights: {len(plan.stations)} station(s)\n")

    print("hotbar:")
    counts = grid.counts()
    for name, slot in sorted(plan.slots.items(), key=lambda kv: kv[1]):
        print(f"  {slot}. {name:26s} x{counts.get(name, 0)}")

    print("\nload the hotbar with:")
    for command in hotbar_commands(plan):
        print(f"  {command}")

    problems = validate(plan)
    if problems:
        print(f"\n{len(problems)} geometry problem(s):")
        for line in problems[:10]:
            print(f"  ! {line}")
        if len(problems) > 10:
            print(f"  ... and {len(problems) - 10} more")
        print("  try a smaller --patch-width / --patch-height")

    if args.preview:
        grid.to_preview(scale=args.preview_scale).save(args.preview)
        print(f"\npreview written to {args.preview}")

    return 1 if problems else 0


def cmd_learn_font(args) -> int:
    from .vision import FontModel
    from .vision.capture import ScreenCapture
    from .vision.font import find_lines, to_mask

    settings = config.Settings.load()
    if args.region:
        settings.region = tuple(int(v) for v in args.region.split(","))  # type: ignore

    capture = ScreenCapture(settings.region)
    print("Open Minecraft, press F3, and make sure the debug text is visible.")
    input(f"Capturing region {settings.region} in 3 seconds -- press Enter when ready. ")
    time.sleep(3)

    rgb = capture.grab()
    mask = to_mask(rgb)
    lines = find_lines(mask)
    if not lines:
        print(
            "No text found in that region. Pass --region LEFT,TOP,WIDTH,HEIGHT "
            "covering the top-left of the Minecraft window.",
            file=sys.stderr,
        )
        return 1

    debug = Path(args.debug_image)
    from PIL import Image

    Image.fromarray(rgb).save(debug)
    print(f"\nCaptured {len(lines)} line(s); saved to {debug} so you can read them.")
    print("Type each line EXACTLY as it appears (Enter alone to skip).\n")

    font = FontModel.load(config.FONT_PATH) if config.FONT_PATH.exists() else FontModel()
    learned = 0
    for n, (top, bottom) in enumerate(lines):
        text = input(f"  line {n + 1}: ").rstrip("\n")
        if not text.strip():
            continue
        try:
            font.learn_line(mask, top, bottom, text)
        except ValueError as exc:
            print(f"    skipped: {exc}", file=sys.stderr)
            continue
        learned += 1

    if not learned:
        print("Nothing learned.", file=sys.stderr)
        return 1

    font.save(config.FONT_PATH)
    try:
        import mss

        with mss.mss() as sct:
            mon = sct.monitors[0]
            settings.screen_size = (mon["width"], mon["height"])
    except Exception:  # pragma: no cover - screen metrics are a nicety
        pass
    settings.save()
    print(
        f"\nLearned {len(font.templates)} glyph(s) from {learned} line(s) "
        f"-> {config.FONT_PATH}"
    )
    print("Check it with: mcbuilder probe")
    return 0


def cmd_probe(args) -> int:
    from .vision import F3ReadError, FontModel, ScreenCapture, parse

    if not config.FONT_PATH.exists():
        print("No font learned yet. Run: mcbuilder learn-font", file=sys.stderr)
        return 1

    settings = config.Settings.load()
    if args.region:
        settings.region = tuple(int(v) for v in args.region.split(","))  # type: ignore
    font = FontModel.load(config.FONT_PATH)
    capture = ScreenCapture(settings.region)

    for _ in range(args.count):
        lines = font.read_all(capture.grab())
        print("--- overlay ---")
        for line in lines:
            print(f"  {line}")
        try:
            state = parse(lines)
            print(
                f"  => x={state.x:.3f} y={state.y:.3f} z={state.z:.3f} "
                f"yaw={state.yaw:.1f} pitch={state.pitch:.1f}"
            )
        except F3ReadError as exc:
            print(f"  => parse failed: {exc}", file=sys.stderr)
        time.sleep(args.interval)
    return 0


def cmd_calibrate(args) -> int:
    from .controller import calibrate_mouse
    from .input import Controls
    from .vision import FontModel, ScreenCapture

    if not config.FONT_PATH.exists():
        print("No font learned yet. Run: mcbuilder learn-font", file=sys.stderr)
        return 1

    settings = config.Settings.load()
    font = FontModel.load(config.FONT_PATH)
    capture = ScreenCapture(settings.region)
    controls = Controls()

    print("Click into Minecraft so the cursor is grabbed. Do not touch the mouse.")
    print("Windows 'Enhance pointer precision' must be OFF.")
    input("Press Enter, then switch to Minecraft within 5 seconds. ")
    time.sleep(5)

    dpc_x, dpc_y = calibrate_mouse(capture, font, controls, counts=args.counts)
    settings.deg_per_count_x = dpc_x
    settings.deg_per_count_y = dpc_y
    settings.save()
    print(f"\ndegrees per mouse count: x={dpc_x:.6f} y={dpc_y:.6f}")
    print(f"saved to {config.SETTINGS_PATH}")
    return 0


def cmd_build(args) -> int:
    from .controller import AbortWatcher, Controller, Tuning
    from .input import Controls
    from .vision import FontModel, ScreenCapture

    grid, plan = _plan_from_args(args)
    problems = validate(plan)
    if problems and not args.force:
        print(
            f"{len(problems)} placement(s) are out of reach; "
            "run `mcbuilder plan` for details, or pass --force to build anyway.",
            file=sys.stderr,
        )
        return 1

    if not config.FONT_PATH.exists():
        print("No font learned yet. Run: mcbuilder learn-font", file=sys.stderr)
        return 1
    settings = config.Settings.load()
    if not settings.calibrated:
        print("Mouse not calibrated. Run: mcbuilder calibrate", file=sys.stderr)
        return 1

    font = FontModel.load(config.FONT_PATH)
    capture = ScreenCapture(settings.region)
    controls = Controls(dry_run=args.dry_run)
    abort = AbortWatcher()
    controller = Controller(
        capture,
        font,
        controls,
        settings.deg_per_count_x,
        settings.deg_per_count_y,
        tuning=Tuning(move_timeout=args.move_timeout),
        abort=abort,
    )

    progress = ProgressFile(config.CONFIG_DIR / "progress.json")
    start_at = progress.read() if args.resume else 0
    if start_at:
        print(f"resuming after block {start_at}/{plan.total_blocks}")

    print(f"{plan.total_blocks} block(s) across {len(plan.stations)} station(s)")
    print("Press F12 at any time to abort and release all keys.")
    input("Press Enter, then switch to Minecraft within 5 seconds. ")
    time.sleep(5)

    if not args.skip_hotbar:
        load_hotbar(controller, plan)
    if not args.no_fly_toggle:
        controls.toggle_fly()

    abort.start()
    started = time.monotonic()

    def report(index: int, total: int, placement) -> None:
        if index % 10 == 0 or index == total:
            rate = index / max(1e-6, time.monotonic() - started)
            print(f"  {index}/{total} blocks  ({rate:.1f}/s)", flush=True)

    try:
        placed = run(controller, plan, progress=progress, start_at=start_at, on_progress=report)
    finally:
        abort.stop()
        controls.release_all()

    print(f"\nplaced {placed} block(s) in {time.monotonic() - started:.0f}s")
    return 0


# --- argument parsing ------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mcbuilder",
        description="Build a PNG as a Minecraft wall mural by driving the game client.",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    def add_image_args(sp):
        sp.add_argument("image", help="source PNG")
        sp.add_argument("--width", type=int, default=64, help="mural width in blocks")
        sp.add_argument("--height", type=int, default=None, help="mural height (default: keep aspect)")
        sp.add_argument("--palette-size", type=int, default=9, help="blocks to use (max 9)")
        sp.add_argument("--blocks", default=None, help="comma-separated block names, overrides auto-selection")
        sp.add_argument("--no-dither", action="store_true", help="disable Floyd-Steinberg dithering")
        sp.add_argument("-x", type=int, required=True, help="mural bottom-left X")
        sp.add_argument("-y", type=int, required=True, help="mural bottom row Y (needs solid ground at Y-1)")
        sp.add_argument("-z", type=int, required=True, help="mural Z plane; you build from the +Z side")
        sp.add_argument("--patch-width", type=int, default=5)
        sp.add_argument("--patch-height", type=int, default=3)
        sp.add_argument("--standoff", type=float, default=2.0, help="blocks between eye and wall")

    sp = sub.add_parser("blocks", help="list the available block palette")
    sp.set_defaults(func=cmd_blocks)

    sp = sub.add_parser("plan", help="quantise an image and print the build plan (no game needed)")
    add_image_args(sp)
    sp.add_argument("--preview", default=None, help="write a PNG preview of the quantised result")
    sp.add_argument("--preview-scale", type=int, default=8)
    sp.set_defaults(func=cmd_plan)

    sp = sub.add_parser("learn-font", help="teach the reader Minecraft's F3 font (one-time)")
    sp.add_argument("--region", default=None, help="LEFT,TOP,WIDTH,HEIGHT of the F3 text")
    sp.add_argument("--debug-image", default="f3_capture.png")
    sp.set_defaults(func=cmd_learn_font)

    sp = sub.add_parser("probe", help="show what the reader currently sees on the F3 overlay")
    sp.add_argument("--region", default=None)
    sp.add_argument("--count", type=int, default=3)
    sp.add_argument("--interval", type=float, default=1.0)
    sp.set_defaults(func=cmd_probe)

    sp = sub.add_parser("calibrate", help="measure mouse sensitivity (one-time per settings change)")
    sp.add_argument("--counts", type=int, default=200)
    sp.set_defaults(func=cmd_calibrate)

    sp = sub.add_parser("build", help="build the mural in-game")
    add_image_args(sp)
    sp.add_argument("--resume", action="store_true", help="continue from the last aborted run")
    sp.add_argument("--dry-run", action="store_true", help="log actions instead of sending input")
    sp.add_argument("--skip-hotbar", action="store_true", help="do not run the /item replace commands")
    sp.add_argument("--no-fly-toggle", action="store_true", help="assume you are already flying")
    sp.add_argument("--move-timeout", type=float, default=20.0)
    sp.add_argument("--force", action="store_true", help="build even if some blocks are out of reach")
    sp.set_defaults(func=cmd_build)

    return p


def main(argv: list[str] | None = None) -> int:
    from . import interactive

    if interactive.should_run(argv):
        return interactive.run(main)

    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)


def frozen_main() -> int:
    """Entry point for the packaged .exe.

    A double-clicked console program closes the instant it returns, taking any
    error message with it. When there is no parent terminal to fall back to,
    hold the window open so whatever happened can actually be read.
    """
    try:
        return main()
    finally:
        if getattr(sys, "frozen", False):
            try:
                input("\nPress Enter to close. ")
            except (EOFError, KeyboardInterrupt):
                pass


if __name__ == "__main__":
    raise SystemExit(main())
