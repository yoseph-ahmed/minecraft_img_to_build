# minecraft_img_to_build

Turn a PNG into a Minecraft mural by taking control of your character and
building it block by block, in creative mode, in the real game client.

This is not a schematic generator. There is no world file to import and no mod
to install. The tool reads the F3 debug overlay off your screen to find out
where your character is, then flies it around and clicks, the same way you
would.

Minecraft **Java Edition** on **Windows** only.

## How it works

Four pieces, each usable on its own:

| Piece | What it does |
|---|---|
| `mcbuilder/image_proc.py` | PNG → downscale → quantise to a 9-block palette, with Floyd–Steinberg dithering |
| `mcbuilder/plan.py` | Lay the wall out in world coordinates and work out where to hover for each patch |
| `mcbuilder/vision/` | Read position and facing back out of the F3 overlay |
| `mcbuilder/controller.py` | Closed-loop flight and aim: measure, correct, repeat |

### Why it reads the screen

Open-loop input does not work. Minecraft movement is continuous rather than
grid-snapped, creative flight glides after you release the key, and mouse
sensitivity is a per-user setting. "Fly right for 90 ms" nine hundred times
accumulates enough error that the mural ends up in the wrong column. So every
movement is measured against the real position and corrected.

Reading the overlay is done by exact bitmap matching rather than OCR.
Minecraft's font is a fixed bitmap at any given resolution and GUI scale, so
once the tool has one clean sample of each glyph, recognition is both fast and
essentially exact. Getting those samples is the one-time `learn-font` step
below: it shows you what it captured and you type what it says.

### Why the wall grows upward

In creative you place a block by clicking a face that already exists. Standing
in front of a wall, the only usable face is the **top of the block underneath**
— aim at a neighbour's side and the raycast hits its south face first, which
would build a second layer out in front of the mural.

That has three consequences worth knowing before you start:

- The wall must be built strictly bottom-up.
- Your eye has to stay above the row being placed, which is why hover stations
  are wide and short rather than square.
- **The row below the mural must already be solid.** Flat ground at `y-1` is a
  precondition; nothing checks the world for you, so uneven ground means a
  failed bottom row.

## Getting it

**Download the executable** from the
[Releases page](https://github.com/yoseph-ahmed/minecraft_img_to_build/releases)
— one file, no Python needed. Double-click it for a guided menu, or run it
from a terminal for the full command line (`mcbuilder.exe --help`).

Windows SmartScreen warns about any unsigned download: **More info** →
**Run anyway**.

Or from source, if you have a working Python 3.10+:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

## Setup

In Minecraft:

- Creative mode, and stand where you want to build.
- **Raw input on** (Options → Controls → Mouse Settings).
- **Windows "Enhance pointer precision" off.** With pointer acceleration on,
  mouse sensitivity stops being a single constant and calibration is
  meaningless.
- Press **F3** so the debug overlay is visible, and leave it up.

Two one-time steps, both of which need redoing if you change resolution or GUI
scale — these are options 1–3 in the menu, or:

```powershell
mcbuilder learn-font    # type out the F3 lines it captures
mcbuilder probe         # check it reads your position correctly
mcbuilder calibrate     # measure degrees of turn per mouse count
```

`probe` is the one to come back to when something misbehaves — it prints
exactly what the reader currently sees.

## Building

Plan first. This needs no game running and changes nothing:

```powershell
mcbuilder plan logo.png --width 64 -x 100 -y 64 -z 200 --preview out.png
```

It prints the mural size, the nine blocks it picked, the `/item replace`
commands to load them, and any placement the geometry cannot reach. Look at
`out.png` before committing to several thousand blocks.

Then build:

```powershell
mcbuilder build logo.png --width 64 -x 100 -y 64 -z 200
```

`-x -y -z` are the bottom-left corner of the mural. The wall occupies the
`z` plane and you build it from the `+Z` side, so stand on the south side and
leave yourself about three blocks of clearance.

**Press F12 to abort.** That releases every held key — important, because the
builder holds movement keys down for seconds at a time and alt-tabbing away
leaves them stuck. `--resume` picks up where an aborted run left off.

Useful flags:

| Flag | |
|---|---|
| `--palette-size N` | fewer than 9 blocks |
| `--blocks a,b,c` | choose the blocks yourself instead of auto-selecting |
| `--no-dither` | flat colour areas instead of error diffusion |
| `--dry-run` | log every action without sending input |
| `--skip-hotbar` | you have already loaded the blocks |
| `--patch-width/height` | smaller patches if placements are being missed |

`mcbuilder blocks` lists the 80 blocks available. They are all full, opaque,
non-gravity cubes — sand and concrete powder would fall out of the mural.

## Building the executable yourself

`.github/workflows/build-exe.yml` builds it on a Windows runner with
PyInstaller, smoke-tests the result and attaches it to a release on any `v*`
tag. Locally:

```powershell
python -m pip install pyinstaller
cd packaging
python -m PyInstaller --clean --noconfirm mcbuilder.spec
```

## Tests

```powershell
python -m pytest
```

The image pipeline, planner, overlay parser, font learner and build
orchestration are all tested without a game or a Windows input stack. The
synthetic font in `tests/test_font.py` stands in for Minecraft's, with the
properties that matter: fixed bitmaps, one-pixel gaps, and a drop shadow that
has to be thresholded away.

## A note on servers

Most multiplayer servers treat input automation as a bannable macro regardless
of creative mode. This is built for singleplayer and for servers you run.
