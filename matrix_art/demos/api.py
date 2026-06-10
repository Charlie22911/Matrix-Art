from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _clamp_u8(value: Any) -> int:
    try:
        ivalue = int(value)
    except Exception:
        return 0
    return 0 if ivalue < 0 else 255 if ivalue > 255 else ivalue


@dataclass(slots=True)
class EffectContext:
    width: int
    height: int
    fps: int
    frame_index: int = 0
    time: float = 0.0
    dt: float = 0.0


class FrameBuffer:
    """Small beginner-friendly RGB frame buffer for 64x64 effects."""

    def __init__(self, width: int, height: int, background: tuple[int, int, int] = (0, 0, 0)):
        self.width = int(width)
        self.height = int(height)
        self.data = bytearray(self.width * self.height * 3)
        self.fill(*background)

    def clear(self) -> None:
        self.fill(0, 0, 0)

    def fill(self, r: int, g: int, b: int) -> None:
        r = _clamp_u8(r)
        g = _clamp_u8(g)
        b = _clamp_u8(b)
        pixel = bytes((r, g, b))
        self.data[:] = pixel * (self.width * self.height)

    def set_pixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        x = int(x)
        y = int(y)
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return
        i = (y * self.width + x) * 3
        self.data[i] = _clamp_u8(r)
        self.data[i + 1] = _clamp_u8(g)
        self.data[i + 2] = _clamp_u8(b)

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        x = int(x)
        y = int(y)
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return (0, 0, 0)
        i = (y * self.width + x) * 3
        return (self.data[i], self.data[i + 1], self.data[i + 2])

    def fade(self, amount: float) -> None:
        factor = max(0.0, min(1.0, float(amount)))
        for i, value in enumerate(self.data):
            self.data[i] = int(value * factor)

    def line(self, x0: int, y0: int, x1: int, y1: int, r: int, g: int, b: int) -> None:
        x0 = int(x0)
        y0 = int(y0)
        x1 = int(x1)
        y1 = int(y1)
        dx = abs(x1 - x0)
        sx = 1 if x0 < x1 else -1
        dy = -abs(y1 - y0)
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.set_pixel(x0, y0, r, g, b)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def rect(self, x: int, y: int, w: int, h: int, r: int, g: int, b: int, *, fill: bool = False) -> None:
        x = int(x)
        y = int(y)
        w = int(w)
        h = int(h)
        if w <= 0 or h <= 0:
            return
        if fill:
            for yy in range(y, y + h):
                for xx in range(x, x + w):
                    self.set_pixel(xx, yy, r, g, b)
            return
        self.line(x, y, x + w - 1, y, r, g, b)
        self.line(x, y + h - 1, x + w - 1, y + h - 1, r, g, b)
        self.line(x, y, x, y + h - 1, r, g, b)
        self.line(x + w - 1, y, x + w - 1, y + h - 1, r, g, b)

    def circle(self, cx: int, cy: int, radius: int, r: int, g: int, b: int, *, fill: bool = False) -> None:
        cx = int(cx)
        cy = int(cy)
        radius = int(radius)
        if radius < 0:
            return
        rr = radius * radius
        for y in range(cy - radius, cy + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                d = (x - cx) * (x - cx) + (y - cy) * (y - cy)
                if fill:
                    if d <= rr:
                        self.set_pixel(x, y, r, g, b)
                elif rr - radius <= d <= rr + radius:
                    self.set_pixel(x, y, r, g, b)

    def tobytes(self) -> bytes:
        return bytes(self.data)
