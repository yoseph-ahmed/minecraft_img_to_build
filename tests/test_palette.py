import numpy as np
import pytest

from mcbuilder.palette import BLOCKS, Palette, select_palette, srgb_to_lab


def test_lab_reference_values():
    # Known sRGB -> Lab anchors; white is L=100 and mid grey sits near L=53.
    lab = srgb_to_lab(np.array([[255, 255, 255], [0, 0, 0], [128, 128, 128]]))
    assert lab[0][0] == pytest.approx(100.0, abs=0.1)
    assert lab[1][0] == pytest.approx(0.0, abs=0.1)
    assert lab[2][0] == pytest.approx(53.6, abs=0.5)
    # Neutrals must have no chroma.
    assert lab[2][1] == pytest.approx(0.0, abs=0.01)
    assert lab[2][2] == pytest.approx(0.0, abs=0.01)


def test_palette_from_names_rejects_unknown():
    with pytest.raises(ValueError, match="unknown block"):
        Palette.from_names(["white_concrete", "not_a_block"])


def test_nearest_picks_the_obvious_block():
    pal = Palette.from_names(["white_concrete", "black_concrete", "red_concrete"])
    lab = srgb_to_lab(np.array([[250, 250, 250], [0, 0, 0], [150, 30, 30]]))
    assert list(pal.nearest(lab)) == [0, 1, 2]


def test_select_palette_returns_distinct_blocks():
    rng = np.random.default_rng(1)
    pixels = rng.integers(0, 256, size=(40, 40, 3), dtype=np.uint8)
    pal = select_palette(pixels, size=9)
    assert len(pal) == 9
    assert len(set(pal.names)) == 9
    assert all(n in BLOCKS for n in pal.names)


def test_select_palette_on_flat_image_still_fills_the_hotbar():
    # Every centroid collapses onto one colour here; the collision fallback
    # has to keep handing out distinct blocks rather than nine duplicates.
    pixels = np.full((20, 20, 3), (200, 40, 40), dtype=np.uint8)
    pal = select_palette(pixels, size=9)
    assert len(set(pal.names)) == 9
