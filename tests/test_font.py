"""Round-trip the glyph learner against a synthetic bitmap font.

The real templates come from the user's own screen, so these tests use a
stand-in font with the properties that matter: fixed bitmaps, one-pixel gaps
between glyphs, a wider gap for a space, and a dim drop shadow that must be
thresholded away.
"""

import numpy as np
import pytest

from mcbuilder.vision.font import (
    LUMA_THRESHOLD,
    FontModel,
    find_lines,
    segment_line,
    to_mask,
)

# 3x5 glyphs, enough to spell the lines the F3 screen actually shows.
GLYPHS = {
    "0": ["111", "101", "101", "101", "111"],
    "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"],
    "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"],
    "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"],
    "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"],
    "9": ["111", "101", "111", "001", "111"],
    "X": ["101", "101", "010", "101", "101"],
    "Y": ["101", "101", "010", "010", "010"],
    "Z": ["111", "001", "010", "100", "111"],
    ":": ["000", "010", "000", "010", "000"],
    "/": ["001", "001", "010", "100", "100"],
    "-": ["000", "000", "111", "000", "000"],
    ".": ["000", "000", "000", "000", "010"],
}

CHAR_GAP = 1
SPACE_GAP = 4
PAD = 2


def render(text: str, shadow: bool = True) -> np.ndarray:
    """Render text as an RGB image, optionally with a dim drop shadow."""
    width = PAD * 2
    for i, ch in enumerate(text):
        if ch == " ":
            width += SPACE_GAP
        else:
            width += 3 + (CHAR_GAP if i else 0)
    img = np.zeros((5 + PAD * 2 + 1, width + 1, 3), dtype=np.uint8)

    x = PAD
    first = True
    for ch in text:
        if ch == " ":
            x += SPACE_GAP
            continue
        if not first:
            x += CHAR_GAP
        for r, row in enumerate(GLYPHS[ch]):
            for c, bit in enumerate(row):
                if bit == "1":
                    if shadow:
                        img[PAD + r + 1, x + c + 1] = (60, 60, 60)
                    img[PAD + r, x + c] = (255, 255, 255)
        x += 3
        first = False
    return img


def test_shadow_is_below_the_threshold():
    assert 60 < LUMA_THRESHOLD <= 255
    mask = to_mask(render("8", shadow=True))
    # Exactly the glyph's lit pixels survive; the shadow must not fatten it.
    assert mask.sum() == sum(row.count("1") for row in GLYPHS["8"])


def test_segmentation_splits_on_gaps():
    img = render("XYZ")
    mask = to_mask(img)
    (top, bottom), = find_lines(mask)
    glyphs, _ = segment_line(mask, top, bottom)
    assert len(glyphs) == 3
    assert all(g.w == 3 for g in glyphs)


def test_learn_then_read_round_trips():
    font = FontModel()
    text = "XYZ: -123.456 / 64.0 / 789.012"
    mask = to_mask(render(text))
    (top, bottom), = find_lines(mask)
    font.learn_line(mask, top, bottom, text)
    assert font.read_line(mask, top, bottom) == text


def test_learned_font_reads_text_it_was_never_shown():
    font = FontModel()
    trained = "XYZ: 0123456789 / -. /"
    mask = to_mask(render(trained))
    (top, bottom), = find_lines(mask)
    font.learn_line(mask, top, bottom, trained)

    fresh = "XYZ: -98.7 / 64.0 / 512.25"
    mask2 = to_mask(render(fresh))
    (t2, b2), = find_lines(mask2)
    assert font.read_line(mask2, t2, b2) == fresh


def test_text_length_mismatch_is_rejected():
    font = FontModel()
    mask = to_mask(render("123"))
    (top, bottom), = find_lines(mask)
    with pytest.raises(ValueError, match="segmented 3 glyph"):
        font.learn_line(mask, top, bottom, "1234")


def test_unknown_glyph_reads_as_question_mark():
    font = FontModel()
    mask = to_mask(render("123"))
    (top, bottom), = find_lines(mask)
    font.learn_line(mask, top, bottom, "123")

    mask2 = to_mask(render("1X3"))
    (t2, b2), = find_lines(mask2)
    # 'X' was never taught, so it must come back as '?' -- which f3.parse then
    # treats as an unreadable line rather than guessing a coordinate.
    assert font.read_line(mask2, t2, b2) == "1?3"


def test_multiple_lines_are_found_separately():
    a = render("XYZ: 1.0 / 64.0 / 2.0")
    b = render("Y: 123")
    width = max(a.shape[1], b.shape[1])
    canvas = np.zeros((a.shape[0] + b.shape[0] + 3, width, 3), dtype=np.uint8)
    canvas[: a.shape[0], : a.shape[1]] = a
    canvas[a.shape[0] + 3 :, : b.shape[1]] = b
    assert len(find_lines(to_mask(canvas))) == 2


def test_save_and_load_preserves_recognition(tmp_path):
    font = FontModel()
    text = "XYZ: 0123456789 -./"
    mask = to_mask(render(text))
    (top, bottom), = find_lines(mask)
    font.learn_line(mask, top, bottom, text)

    path = tmp_path / "font.json"
    font.save(path)
    reloaded = FontModel.load(path)
    assert reloaded.space_gap == font.space_gap
    assert reloaded.read_line(mask, top, bottom) == text
