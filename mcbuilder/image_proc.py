"""PNG -> grid of block names.

The output grid is indexed [row][col] with row 0 at the TOP of the image, which
is the opposite of the build order (walls grow upward from the bottom). The
planner flips it; keeping image-space here avoids confusing orientation bugs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .palette import Palette, select_palette, srgb_to_lab


@dataclass
class BlockGrid:
    """Quantised image. `indices` are offsets into `palette.names`."""

    indices: np.ndarray  # (rows, cols) int
    palette: Palette

    @property
    def rows(self) -> int:
        return int(self.indices.shape[0])

    @property
    def cols(self) -> int:
        return int(self.indices.shape[1])

    def block_at(self, row: int, col: int) -> str:
        return self.palette.names[int(self.indices[row, col])]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        flat = self.indices.ravel()
        for i, name in enumerate(self.palette.names):
            n = int(np.count_nonzero(flat == i))
            if n:
                out[name] = n
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def to_preview(self, scale: int = 8) -> Image.Image:
        rgb = self.palette.rgb[self.indices]
        img = Image.fromarray(rgb.astype(np.uint8), mode="RGB")
        return img.resize((self.cols * scale, self.rows * scale), Image.NEAREST)


def load_and_fit(path: str | Path, width: int, height: int | None = None) -> np.ndarray:
    """Load a PNG and downscale it to block resolution.

    Transparent pixels are composited onto white -- an alpha channel has no
    meaning once every pixel has to become a solid block, and compositing beats
    letting Pillow drop alpha and leave black fringes.
    """
    img = Image.open(path)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        flat = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(flat, img)
    img = img.convert("RGB")

    if height is None:
        height = max(1, round(img.height * width / img.width))
    img = img.resize((width, height), Image.LANCZOS)
    return np.asarray(img, dtype=np.uint8)


def quantise(
    pixels: np.ndarray, palette: Palette, dither: bool = True
) -> np.ndarray:
    """Map every pixel to a palette index, optionally with Floyd-Steinberg.

    Error diffusion runs in sRGB (cheap and stable) while the nearest-colour
    lookup itself runs in Lab, which is the part that actually needs to be
    perceptual. Doing the diffusion in Lab too tends to produce odd chroma
    smearing on saturated art, so it is deliberately not done there.
    """
    rows, cols, _ = pixels.shape
    if not dither:
        return palette.nearest(srgb_to_lab(pixels))

    work = pixels.astype(np.float64)
    out = np.zeros((rows, cols), dtype=int)
    pal_rgb = palette.rgb.astype(np.float64)

    for r in range(rows):
        for c in range(cols):
            old = work[r, c]
            idx = int(palette.nearest(srgb_to_lab(np.clip(old, 0, 255)[None, :]))[0])
            out[r, c] = idx
            err = old - pal_rgb[idx]
            # Standard Floyd-Steinberg kernel: 7/16 right, then 3/16 5/16 1/16
            # across the row below.
            if c + 1 < cols:
                work[r, c + 1] += err * (7 / 16)
            if r + 1 < rows:
                if c > 0:
                    work[r + 1, c - 1] += err * (3 / 16)
                work[r + 1, c] += err * (5 / 16)
                if c + 1 < cols:
                    work[r + 1, c + 1] += err * (1 / 16)
    return out


def build_grid(
    path: str | Path,
    width: int,
    height: int | None = None,
    palette_size: int = 9,
    dither: bool = True,
    blocks: list[str] | None = None,
) -> BlockGrid:
    pixels = load_and_fit(path, width, height)
    palette = (
        Palette.from_names(blocks)
        if blocks
        else select_palette(pixels, size=palette_size)
    )
    return BlockGrid(quantise(pixels, palette, dither=dither), palette)
