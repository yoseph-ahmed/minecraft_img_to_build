"""Screen capture of the F3 debug region."""

from __future__ import annotations

import numpy as np


class ScreenCapture:
    """Thin wrapper over mss, kept alive across grabs.

    mss is noticeably faster when its object is reused, and the builder polls
    the overlay tens of times per second while flying, so a fresh grab object
    per read would dominate the control loop.
    """

    def __init__(self, region: tuple[int, int, int, int]):
        import mss

        self.region = region
        self._sct = mss.mss()

    @property
    def region(self) -> tuple[int, int, int, int]:
        return self._region

    @region.setter
    def region(self, value: tuple[int, int, int, int]) -> None:
        left, top, width, height = value
        if width <= 0 or height <= 0:
            raise ValueError(f"invalid capture region: {value}")
        self._region = (left, top, width, height)
        self._monitor = {"left": left, "top": top, "width": width, "height": height}

    def grab(self) -> np.ndarray:
        """Return the region as an (h, w, 3) uint8 RGB array."""
        raw = self._sct.grab(self._monitor)
        # mss hands back BGRA; drop alpha and flip to RGB.
        arr = np.asarray(raw, dtype=np.uint8)[:, :, :3]
        return arr[:, :, ::-1].copy()

    def close(self) -> None:
        self._sct.close()
