import numpy as np
from PIL import Image

from mcbuilder.image_proc import build_grid, load_and_fit, quantise
from mcbuilder.palette import Palette


def write_png(tmp_path, array, mode="RGB"):
    path = tmp_path / "img.png"
    Image.fromarray(array, mode=mode).save(path)
    return path


def test_load_and_fit_preserves_aspect(tmp_path):
    src = np.zeros((50, 100, 3), dtype=np.uint8)
    out = load_and_fit(write_png(tmp_path, src), width=20)
    assert out.shape == (10, 20, 3)


def test_transparency_composites_onto_white(tmp_path):
    src = np.zeros((4, 4, 4), dtype=np.uint8)  # fully transparent black
    out = load_and_fit(write_png(tmp_path, src, mode="RGBA"), width=4, height=4)
    # Without compositing this would come back black and quantise to a dark
    # block, which is the classic "why is my logo on a black square" bug.
    assert (out == 255).all()


def test_quantise_without_dither_is_exact():
    pal = Palette.from_names(["white_concrete", "black_concrete"])
    pixels = np.array([[[255, 255, 255], [0, 0, 0]]], dtype=np.uint8)
    assert list(quantise(pixels, pal, dither=False)[0]) == [0, 1]


def test_dither_mixes_two_blocks_on_a_midtone():
    # A flat mid grey has no exact match in a black/white palette, so error
    # diffusion should produce both rather than one solid field.
    pal = Palette.from_names(["white_concrete", "black_concrete"])
    pixels = np.full((8, 8, 3), 128, dtype=np.uint8)
    out = quantise(pixels, pal, dither=True)
    assert set(np.unique(out)) == {0, 1}


def test_build_grid_reports_counts(tmp_path):
    src = np.zeros((8, 8, 3), dtype=np.uint8)
    src[:4] = (255, 255, 255)
    grid = build_grid(write_png(tmp_path, src), width=8, height=8, palette_size=2, dither=False)
    assert grid.rows == 8 and grid.cols == 8
    assert sum(grid.counts().values()) == 64
    assert grid.to_preview(scale=4).size == (32, 32)
