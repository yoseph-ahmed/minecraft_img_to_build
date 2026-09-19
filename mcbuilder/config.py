"""Where the learned font and mouse calibration live between runs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

CONFIG_DIR = Path.home() / ".mcbuilder"
FONT_PATH = CONFIG_DIR / "font.json"
SETTINGS_PATH = CONFIG_DIR / "settings.json"


@dataclass
class Settings:
    """Per-machine setup. Invalidated by anything that changes glyph size.

    Screen resolution and GUI scale both change how the F3 font renders, so a
    font learned at one setting will not match another. The values are stored
    alongside the templates and checked on load rather than left to produce
    confusing recognition failures later.
    """

    region: tuple[int, int, int, int] = (0, 0, 760, 260)
    deg_per_count_x: float = 0.0
    deg_per_count_y: float = 0.0
    screen_size: tuple[int, int] = (0, 0)

    @property
    def calibrated(self) -> bool:
        return self.deg_per_count_x != 0.0 and self.deg_per_count_y != 0.0

    def save(self, path: Path = SETTINGS_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path = SETTINGS_PATH) -> "Settings":
        if not path.exists():
            return cls()
        blob = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            region=tuple(blob.get("region", cls.region)),  # type: ignore[arg-type]
            deg_per_count_x=float(blob.get("deg_per_count_x", 0.0)),
            deg_per_count_y=float(blob.get("deg_per_count_y", 0.0)),
            screen_size=tuple(blob.get("screen_size", (0, 0))),  # type: ignore[arg-type]
        )
