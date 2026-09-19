"""Minecraft block palette and perceptual colour matching.

Every block listed here is a full, opaque, non-gravity-affected cube. That
matters for a vertical wall: sand, gravel and concrete *powder* would fall out
of the mural, and anything non-full-cube breaks the "place against the block
below" support chain.

The RGB values are average texture colours, eyeballed against 1.20 textures.
They are close enough for palette selection but worth tuning if a particular
image comes out off-hue -- see tools/README notes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# name -> average texture colour
BLOCKS: dict[str, tuple[int, int, int]] = {
    # --- concrete: flat and saturated, the workhorse for image builds -------
    "white_concrete": (207, 213, 214),
    "orange_concrete": (224, 97, 0),
    "magenta_concrete": (169, 48, 159),
    "light_blue_concrete": (36, 137, 199),
    "yellow_concrete": (241, 175, 21),
    "lime_concrete": (94, 169, 24),
    "pink_concrete": (214, 101, 143),
    "gray_concrete": (54, 57, 61),
    "light_gray_concrete": (125, 125, 115),
    "cyan_concrete": (21, 119, 136),
    "purple_concrete": (100, 32, 156),
    "blue_concrete": (44, 46, 143),
    "brown_concrete": (96, 59, 31),
    "green_concrete": (73, 91, 36),
    "red_concrete": (142, 33, 33),
    "black_concrete": (8, 10, 15),
    # --- terracotta: muted earth tones, good for skin and landscape ---------
    "white_terracotta": (209, 178, 161),
    "orange_terracotta": (161, 83, 37),
    "magenta_terracotta": (149, 88, 108),
    "light_blue_terracotta": (113, 108, 137),
    "yellow_terracotta": (186, 133, 35),
    "lime_terracotta": (103, 117, 52),
    "pink_terracotta": (161, 78, 78),
    "gray_terracotta": (57, 42, 35),
    "light_gray_terracotta": (135, 106, 97),
    "cyan_terracotta": (86, 91, 91),
    "purple_terracotta": (118, 70, 86),
    "blue_terracotta": (74, 59, 91),
    "brown_terracotta": (77, 51, 35),
    "green_terracotta": (76, 83, 42),
    "red_terracotta": (143, 61, 46),
    "black_terracotta": (37, 22, 16),
    # --- wool: slightly softer than concrete, fills palette gaps ------------
    "white_wool": (233, 236, 236),
    "orange_wool": (240, 118, 19),
    "magenta_wool": (189, 68, 179),
    "light_blue_wool": (58, 175, 217),
    "yellow_wool": (248, 197, 39),
    "lime_wool": (112, 185, 25),
    "pink_wool": (237, 141, 172),
    "gray_wool": (62, 68, 71),
    "light_gray_wool": (142, 142, 134),
    "cyan_wool": (21, 137, 145),
    "purple_wool": (121, 42, 172),
    "blue_wool": (53, 57, 157),
    "brown_wool": (114, 71, 40),
    "green_wool": (84, 109, 27),
    "red_wool": (160, 39, 34),
    "black_wool": (20, 21, 25),
    # --- stones, woods and misc neutrals ------------------------------------
    "stone": (125, 125, 125),
    "cobblestone": (127, 127, 127),
    "smooth_stone": (159, 159, 159),
    "andesite": (136, 136, 136),
    "diorite": (188, 188, 188),
    "granite": (149, 103, 85),
    "deepslate": (77, 77, 80),
    "quartz_block": (236, 233, 225),
    "sandstone": (216, 203, 155),
    "red_sandstone": (186, 99, 29),
    "oak_planks": (162, 130, 78),
    "spruce_planks": (114, 84, 48),
    "birch_planks": (196, 179, 123),
    "dark_oak_planks": (66, 43, 20),
    "prismarine": (99, 156, 151),
    "dark_prismarine": (51, 91, 75),
    "netherrack": (97, 38, 38),
    "bricks": (150, 97, 83),
    "nether_bricks": (44, 22, 26),
    "end_stone": (221, 223, 165),
    "snow_block": (249, 254, 254),
    "iron_block": (220, 220, 220),
    "gold_block": (246, 208, 61),
    "diamond_block": (98, 237, 228),
    "emerald_block": (42, 203, 86),
    "lapis_block": (30, 67, 140),
    "redstone_block": (175, 24, 5),
    "coal_block": (16, 15, 15),
    "obsidian": (15, 10, 24),
    "moss_block": (89, 109, 45),
    "packed_mud": (142, 106, 79),
    "mud_bricks": (137, 102, 78),
}


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """Convert sRGB (0-255, any leading shape + trailing 3) to CIE L*a*b*.

    Colour distance in Lab tracks human perception far better than raw RGB
    euclidean distance, which is why palette selection and nearest-block
    lookup both happen here rather than in RGB.
    """
    arr = np.asarray(rgb, dtype=np.float64) / 255.0
    # sRGB -> linear RGB
    linear = np.where(arr <= 0.04045, arr / 12.92, ((arr + 0.055) / 1.055) ** 2.4)
    # linear RGB -> XYZ (D65)
    m = np.array(
        [
            [0.4124564, 0.3575761, 0.1804375],
            [0.2126729, 0.7151522, 0.0721750],
            [0.0193339, 0.1191920, 0.9503041],
        ]
    )
    xyz = linear @ m.T
    # XYZ -> Lab, normalised against the D65 white point
    white = np.array([0.95047, 1.00000, 1.08883])
    t = xyz / white
    delta = 6.0 / 29.0
    f = np.where(t > delta**3, np.cbrt(t), t / (3 * delta**2) + 4.0 / 29.0)
    fx, fy, fz = f[..., 0], f[..., 1], f[..., 2]
    return np.stack([116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)], axis=-1)


@dataclass(frozen=True)
class Palette:
    """A concrete set of blocks chosen for one image, capped at hotbar size."""

    names: list[str]
    rgb: np.ndarray  # (n, 3) uint8
    lab: np.ndarray  # (n, 3) float64

    def __len__(self) -> int:
        return len(self.names)

    @classmethod
    def from_names(cls, names: list[str]) -> "Palette":
        unknown = [n for n in names if n not in BLOCKS]
        if unknown:
            raise ValueError(f"unknown block(s): {', '.join(unknown)}")
        rgb = np.array([BLOCKS[n] for n in names], dtype=np.uint8)
        return cls(list(names), rgb, srgb_to_lab(rgb))

    def nearest(self, lab: np.ndarray) -> np.ndarray:
        """Index of the closest palette entry for each Lab colour given."""
        flat = lab.reshape(-1, 1, 3)
        dist = np.sum((flat - self.lab[None, :, :]) ** 2, axis=-1)
        return np.argmin(dist, axis=-1).reshape(lab.shape[:-1])


def all_blocks_lab() -> tuple[list[str], np.ndarray, np.ndarray]:
    names = list(BLOCKS)
    rgb = np.array([BLOCKS[n] for n in names], dtype=np.uint8)
    return names, rgb, srgb_to_lab(rgb)


def select_palette(pixels_rgb: np.ndarray, size: int = 9, seed: int = 0) -> Palette:
    """Pick the `size` blocks that best cover an image's colours.

    k-means over the image in Lab space, then snap each centroid to the nearest
    real block. Two centroids can land on the same block (common with flat
    art), so collisions fall through to the next-nearest unused block -- that
    keeps the full hotbar useful instead of wasting slots on duplicates.
    """
    if size < 1:
        raise ValueError("palette size must be >= 1")

    lab = srgb_to_lab(pixels_rgb.reshape(-1, 3))
    rng = np.random.default_rng(seed)

    # k-means++ style seeding: spread initial centroids out by distance.
    centroids = [lab[rng.integers(len(lab))]]
    for _ in range(1, min(size, len(lab))):
        d = np.min(
            np.stack([np.sum((lab - c) ** 2, axis=-1) for c in centroids]), axis=0
        )
        total = d.sum()
        if total <= 0:
            centroids.append(lab[rng.integers(len(lab))])
            continue
        centroids.append(lab[rng.choice(len(lab), p=d / total)])
    cent = np.stack(centroids)

    for _ in range(40):
        dist = np.sum((lab[:, None, :] - cent[None, :, :]) ** 2, axis=-1)
        labels = np.argmin(dist, axis=1)
        moved = 0.0
        for i in range(len(cent)):
            members = lab[labels == i]
            if len(members):
                new = members.mean(axis=0)
                moved = max(moved, float(np.linalg.norm(new - cent[i])))
                cent[i] = new
        if moved < 0.05:
            break

    # Order centroids by how much of the image they represent, so that if we
    # run out of distinct blocks the dropped ones are the least important.
    counts = np.bincount(labels, minlength=len(cent))
    order = np.argsort(-counts)

    names, _, block_lab = all_blocks_lab()
    chosen: list[str] = []
    for i in order:
        d = np.sum((block_lab - cent[i]) ** 2, axis=-1)
        for j in np.argsort(d):
            if names[j] not in chosen:
                chosen.append(names[j])
                break
    return Palette.from_names(chosen)
