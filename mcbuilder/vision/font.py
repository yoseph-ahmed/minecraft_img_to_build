"""Learn and recognise Minecraft's bitmap font from the F3 overlay.

General-purpose OCR is both slow and unreliable on Minecraft's 8px font. But
the font is a *fixed bitmap* at any given resolution and GUI scale, so once we
have one clean sample of each glyph, recognition is exact pixel matching --
fast enough to poll at 60Hz and effectively 100% accurate.

Getting labelled samples is the only tricky part, and it is solved socially
rather than technically: `mcbuilder learn-font` shows the user the captured
lines and asks them to type what they say. That takes half a minute once, and
it automatically adapts to their resolution, GUI scale and Minecraft version
instead of shipping templates that only match one setup.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# Foreground threshold. Minecraft draws F3 text bright on a translucent dark
# panel, with a ~25%-brightness drop shadow one pixel down-right. A high cut
# keeps the glyph body and discards the shadow, which would otherwise fatten
# every character and break exact matching.
LUMA_THRESHOLD = 140


def to_mask(rgb: np.ndarray) -> np.ndarray:
    luma = rgb.astype(np.float64) @ np.array([0.299, 0.587, 0.114])
    return luma >= LUMA_THRESHOLD


def _runs(flags: np.ndarray, max_gap: int = 0) -> list[tuple[int, int]]:
    """Contiguous True runs as (start, end_exclusive), merging small gaps."""
    out: list[tuple[int, int]] = []
    start = None
    gap = 0
    for i, on in enumerate(flags):
        if on:
            if start is None:
                start = i
            gap = 0
        elif start is not None:
            gap += 1
            if gap > max_gap:
                out.append((start, i - gap + 1))
                start = None
                gap = 0
    if start is not None:
        out.append((start, len(flags) - gap))
    return out


def find_lines(mask: np.ndarray) -> list[tuple[int, int]]:
    """Row spans holding one line of text each."""
    # Merge a 1px gap so that a glyph's disconnected parts (the dot of an 'i',
    # a colon) stay in one line rather than splitting into two.
    return [(a, b) for a, b in _runs(mask.any(axis=1), max_gap=1) if b - a >= 4]


@dataclass
class Glyph:
    h: int
    w: int
    bits: np.ndarray  # (h, w) bool, cropped to tight bbox

    def key(self) -> tuple[int, int, bytes]:
        return (self.h, self.w, self.bits.tobytes())


def segment_line(mask: np.ndarray, top: int, bottom: int) -> tuple[list[Glyph], list[int]]:
    """Split one text line into glyphs plus the pixel gap before each glyph."""
    band = mask[top:bottom]
    spans = _runs(band.any(axis=0))
    glyphs: list[Glyph] = []
    gaps: list[int] = []
    prev_end: int | None = None
    for a, b in spans:
        sub = band[:, a:b]
        rows = np.where(sub.any(axis=1))[0]
        sub = sub[rows[0] : rows[-1] + 1]
        glyphs.append(Glyph(sub.shape[0], sub.shape[1], sub))
        gaps.append(0 if prev_end is None else a - prev_end)
        prev_end = b
    return glyphs, gaps


@dataclass
class FontModel:
    """Learned glyph templates plus the gap width that means a space."""

    templates: dict[str, list[np.ndarray]] = field(default_factory=dict)
    space_gap: int = 6

    # --- learning -----------------------------------------------------------

    def learn_line(self, mask: np.ndarray, top: int, bottom: int, text: str) -> None:
        glyphs, gaps = segment_line(mask, top, bottom)
        visible = [c for c in text if c != " "]
        if len(glyphs) != len(visible):
            raise ValueError(
                f"segmented {len(glyphs)} glyph(s) but the text has "
                f"{len(visible)} non-space character(s): {text!r}"
            )

        for glyph, ch in zip(glyphs, visible):
            bucket = self.templates.setdefault(ch, [])
            if not any(
                b.shape == glyph.bits.shape and np.array_equal(b, glyph.bits)
                for b in bucket
            ):
                bucket.append(glyph.bits)

        # Work out which gaps sit where the text has a space, and put the
        # threshold between the two populations.
        space_before: list[bool] = []
        pending = False
        first = True
        for ch in text:
            if ch == " ":
                pending = True
                continue
            if not first:
                space_before.append(pending)
            first = False
            pending = False
        with_space = [g for g, s in zip(gaps[1:], space_before) if s]
        without = [g for g, s in zip(gaps[1:], space_before) if not s]
        if with_space and without:
            self.space_gap = (max(without) + min(with_space)) // 2
        elif without:
            self.space_gap = max(without) + 2

    # --- recognition --------------------------------------------------------

    def _match(self, glyph: Glyph) -> str:
        best_char, best_score = "?", -1.0
        for ch, bucket in self.templates.items():
            for tmpl in bucket:
                if tmpl.shape == glyph.bits.shape:
                    if np.array_equal(tmpl, glyph.bits):
                        return ch
                    score = float(np.mean(tmpl == glyph.bits))
                else:
                    # Compare on a common canvas so a 1px rendering difference
                    # degrades the score instead of disqualifying the glyph.
                    h = max(tmpl.shape[0], glyph.bits.shape[0])
                    w = max(tmpl.shape[1], glyph.bits.shape[1])
                    a = np.zeros((h, w), bool)
                    b = np.zeros((h, w), bool)
                    a[: tmpl.shape[0], : tmpl.shape[1]] = tmpl
                    b[: glyph.bits.shape[0], : glyph.bits.shape[1]] = glyph.bits
                    score = float(np.mean(a == b)) * 0.9
                if score > best_score:
                    best_char, best_score = ch, score
        return best_char if best_score >= 0.86 else "?"

    def read_line(self, mask: np.ndarray, top: int, bottom: int) -> str:
        glyphs, gaps = segment_line(mask, top, bottom)
        chars: list[str] = []
        for i, glyph in enumerate(glyphs):
            if i and gaps[i] >= self.space_gap:
                chars.append(" ")
            chars.append(self._match(glyph))
        return "".join(chars)

    def read_all(self, rgb: np.ndarray) -> list[str]:
        mask = to_mask(rgb)
        return [self.read_line(mask, a, b) for a, b in find_lines(mask)]

    # --- persistence --------------------------------------------------------

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = {
            "space_gap": self.space_gap,
            "templates": {
                ch: [
                    {"h": t.shape[0], "w": t.shape[1], "bits": t.flatten().tolist()}
                    for t in bucket
                ]
                for ch, bucket in self.templates.items()
            },
        }
        path.write_text(json.dumps(blob), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "FontModel":
        blob = json.loads(Path(path).read_text(encoding="utf-8"))
        templates = {
            ch: [
                np.array(t["bits"], dtype=bool).reshape(t["h"], t["w"])
                for t in bucket
            ]
            for ch, bucket in blob["templates"].items()
        }
        return cls(templates=templates, space_gap=int(blob["space_gap"]))
