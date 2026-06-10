from __future__ import annotations

from pathlib import Path
from threading import RLock

from PIL import Image

from .base import DisplayDriver


class MockDisplayDriver(DisplayDriver):
    name = "mock"

    def __init__(self, width: int = 64, height: int = 64, snapshot_path: Path | None = None, brightness: int = 70):
        self._width = width
        self._height = height
        self.snapshot_path = snapshot_path
        self.brightness = brightness
        self.last_image = Image.new("RGB", (width, height), (0, 0, 0))
        self.lock = RLock()
        if snapshot_path:
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            self.last_image.save(snapshot_path)

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    def show_image(self, image: Image.Image) -> None:
        with self.lock:
            img = image.convert("RGB").resize((self._width, self._height), Image.Resampling.NEAREST)
            self.last_image = img
            if self.snapshot_path:
                img.save(self.snapshot_path)

    def clear(self) -> None:
        self.show_image(Image.new("RGB", (self._width, self._height), (0, 0, 0)))

    def set_brightness(self, value: int) -> None:
        with self.lock:
            self.brightness = max(1, min(100, int(value)))
